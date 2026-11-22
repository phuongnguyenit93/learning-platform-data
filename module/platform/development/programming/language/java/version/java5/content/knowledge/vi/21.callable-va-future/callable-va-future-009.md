# FutureTask kết hợp Runnable với Future

## 1. Một đối tượng có hai vai trò

`Runnable` mô tả một công việc có thể chạy bằng `run()`, nhưng phương thức đó trả `void`. `Future<V>` cho phép theo dõi một lần tính toán, chờ lấy kết quả hoặc yêu cầu hủy, nhưng bản thân giao diện Future không có phương thức để thực thi công việc.

`FutureTask<V>` kết hợp hai phía đó: nó nhận một công việc để chạy và đồng thời là đối tượng giữ kết quả/trạng thái của công việc ấy.

```text
Bên thực thi nhìn FutureTask như Runnable
    → gọi run() để chạy công việc

Bên nhận kết quả nhìn cùng đối tượng như Future<V>
    → gọi get(), isDone(), cancel(...)
```

Ví dụ, một nơi chỉ nhận `Runnable` như `Executor.execute` vẫn có thể chạy một phép tính có kết quả nếu ta bọc phép tính trong FutureTask và giữ đối tượng đó để lấy kết quả. Không cần tự dựng thêm biến chia sẻ, cờ hoàn thành và cơ chế chờ cho mỗi phép tính.

FutureTask là API còn được dùng trong Java hiện nay. Ví dụ trong bài tương thích Java 17 trở lên.

## 2. Quan hệ kiểu: RunnableFuture là chiếc cầu

Khai báo rút gọn để đọc mô hình:

```java
public interface RunnableFuture<V> extends Runnable, Future<V> { }

public class FutureTask<V> implements RunnableFuture<V> { }
```

Đây chỉ là sơ đồ khai báo, không phải mã để tự tạo lại các lớp chuẩn. `RunnableFuture<V>` kết hợp hợp đồng chạy và hợp đồng Future; FutureTask là một lớp triển khai cụ thể. [RunnableFuture](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/RunnableFuture.html).

Cùng một đối tượng có thể được dùng qua hai kiểu:

```java
FutureTask<Integer> task = new FutureTask<>(() -> 6 * 7);
Runnable runnableView = task;
Future<Integer> futureView = task;
```

Đoạn minh họa cần các import từ `java.util.concurrent`. `runnableView` và `futureView` không phải hai phép tính khác nhau; chúng là hai tham chiếu tới cùng một đối tượng. Kiểu tĩnh quyết định phương thức mà nơi gọi thấy; trạng thái thực vẫn thuộc cùng FutureTask.

## 3. Hai cách tạo và ý nghĩa kết quả

### Từ Callable<V>

```java
FutureTask<Integer> calculation = new FutureTask<>(() -> 42);
```

Hàm tạo nhận `Callable<Integer>`. Khi công việc được chạy và hoàn thành bình thường, `calculation.get()` trả `42`.

### Từ Runnable và một kết quả định trước

```java
Runnable refresh = () -> {
    // Công việc không tự trả giá trị.
};
FutureTask<String> completion = new FutureTask<>(refresh, "done");
```

Khi Runnable kết thúc bình thường, `get()` trả `"done"`. Đây là kết quả được truyền sẵn vào hàm tạo, không phải giá trị do `run()` tính rồi trả ra. Nếu Runnable ném lỗi thì FutureTask ghi nhận lỗi thay vì trả giá trị định trước.

Khi không có dữ liệu hữu ích, có thể dùng:

```java
FutureTask<Void> completion = new FutureTask<>(refresh, null);
```

Các đoạn này là minh họa trong một phương thức đã import các kiểu cần thiết. Tạo FutureTask chỉ tạo đối tượng; công việc **chưa tự chạy**. [Các hàm tạo FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

## 4. Cách đưa FutureTask vào thực thi

Có ba cách cần phân biệt:

| Cách gọi | Công việc chạy ở đâu? | Điều cần lưu ý |
|---|---|---|
| `task.run()` | Ngay trên luồng gọi phương thức này | Không tự tạo luồng nền |
| `new Thread(task).start()` | Luồng mới được tạo | Chủ sở hữu cần quản lý vòng đời luồng |
| `executor.execute(task)` | Theo chính sách executor | Có thể là nhóm luồng hoặc cơ chế khác |

Ví dụ minh họa bên trong phương thức đã có `Executor executor`:

```java
FutureTask<Integer> task = new FutureTask<>(() -> 21 * 2);
executor.execute(task);
int answer = task.get();
```

`execute` trả `void`, nhưng kết quả không bị mất vì ta giữ FutureTask. Đây cũng là lý do không thể chỉ nhìn tên phương thức `execute` để kết luận lỗi chắc chắn sẽ đến bộ xử lý ngoại lệ chưa bắt của luồng: chính FutureTask có thể giữ lỗi của phép tính.

Nếu tạo FutureTask rồi gọi `get()` trước khi có ai chạy nó, lời chờ không tự kích hoạt công việc. Một chương trình không có bên gọi run/execute/start có thể chờ mãi. Dùng get có thời hạn có thể giúp phát hiện việc chưa tiến triển, nhưng vẫn cần sửa luồng điều khiển.

## 5. Cơ chế một lần và vòng đời kết quả

Với FutureTask thông thường, các lời `run()` cạnh tranh không làm cùng một phép tính được chạy lặp đồng thời; sau khi đã kết thúc, gọi run lần nữa cũng không chạy lại công việc. Kết quả hoặc lỗi của lần thực thi được giữ để các bên quan sát.

Mô hình khái niệm:

```text
chưa hoàn tất
    ├─ chạy thành công → kết quả
    ├─ chạy thất bại   → lỗi
    └─ hủy            → trạng thái cancelled
```

Đây là sơ đồ học tập, không liệt kê các trạng thái nội bộ hay đòi ứng dụng phụ thuộc vào giá trị số của chúng. [Mã nguồn OpenJDK FutureTask](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/FutureTask.java) cho thấy việc chạy được bảo vệ để chỉ một bên thực hiện công việc, còn kết quả được công bố theo trạng thái hoàn tất.

Có thể gọi `get()` nhiều lần hoặc từ nhiều bên quan sát để nhận kết quả của cùng lần thực thi. Việc đó không tự tạo một lần tính toán mới. Nếu kết quả là đối tượng có thể thay đổi, các bên có thể nhận cùng một tham chiếu; FutureTask không tự sao chép sâu dữ liệu hay bảo vệ các lần sửa sau khi công bố.

Muốn chạy một công việc mới, thường tạo FutureTask mới. Không dùng FutureTask đã hoàn tất như một tác vụ lặp định kỳ. `runAndReset()` là phương thức `protected` cho các triển khai chuyên biệt; nó không phải thao tác đặt lại công khai nên dựa vào trong mã ứng dụng thông thường.

## 6. Chương trình kiểm chứng đầy đủ

Chương trình có ba phần: một FutureTask lấy kết quả qua executor, một FutureTask giữ lỗi, và một FutureTask bị hủy trước khi chạy. Latch kiểm soát phần đầu để việc đọc trạng thái trước hoàn thành không phụ thuộc máy nhanh hay chậm.

Lưu thành `FutureTaskDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureTaskDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger executions = new AtomicInteger();

        FutureTask<Integer> task = new FutureTask<>(() -> {
            executions.incrementAndGet();
            started.countDown();
            release.await();
            return 42;
        });

        try {
            System.out.println("done after construction: " + task.isDone());
            pool.execute(task);
            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Task did not start");
            }
            System.out.println("done while blocked: " + task.isDone());

            release.countDown();
            System.out.println("result: " + task.get(10, TimeUnit.SECONDS));
            System.out.println("result again: " + task.get());

            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Executor did not terminate");
            }
            task.run();
            System.out.println("executions after extra run: "
                    + executions.get());

            FutureTask<Integer> failure = new FutureTask<>(() -> {
                throw new IllegalArgumentException("invalid value");
            });
            failure.run();
            System.out.println("failure.run returned normally");
            try {
                failure.get();
                throw new AssertionError("Expected ExecutionException");
            } catch (ExecutionException ex) {
                System.out.println("stored failure: "
                        + ex.getCause().getClass().getSimpleName());
            }

            AtomicInteger cancelledExecutions = new AtomicInteger();
            FutureTask<Integer> cancelled = new FutureTask<>(
                    () -> cancelledExecutions.incrementAndGet());
            System.out.println("cancel before run: " + cancelled.cancel(false));
            cancelled.run();
            System.out.println("cancelled executions: "
                    + cancelledExecutions.get());
            try {
                cancelled.get();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException ex) {
                System.out.println("cancelled get: CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
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
javac --release 17 FutureTaskDemo.java
java FutureTaskDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
done after construction: false
done while blocked: false
result: 42
result again: 42
executions after extra run: 1
failure.run returned normally
stored failure: IllegalArgumentException
cancel before run: true
cancelled executions: 0
cancelled get: CancellationException
```

Cách đọc kết quả:

1. Tạo đối tượng không làm FutureTask hoàn thành hay bắt đầu tính toán.
2. Trong khi Callable bị giữ ở latch, Future chưa done.
3. `get` lấy kết quả; lần get sau lấy lại cùng kết quả.
4. Sau khi executor đã kết thúc, gọi `task.run()` nữa không tăng số lần thực thi.
5. Lỗi bên trong Callable không thoát trực tiếp khỏi `failure.run()` thông thường; nó được lưu rồi báo bằng `ExecutionException` ở `get()`.
6. FutureTask bị hủy trước khi chạy không thực hiện Callable; get báo trạng thái hủy.

Các dòng in do luồng `main` thực hiện theo thứ tự quan sát; không phải thứ tự in ngẫu nhiên của các luồng tác vụ.

## 7. Lỗi, hết hạn chờ và hủy

### Lỗi tính toán được giữ lại

Trong FutureTask chuẩn, `run()` thực thi công việc và ghi kết quả hoặc lỗi vào đối tượng. `get()` báo `ExecutionException` với nguyên nhân gốc khi công việc thất bại. Không trông đợi một khối catch chỉ bọc `executor.execute(task)` tự bắt lỗi chạy nền.

Điều đó cũng có nghĩa bỏ FutureTask mà không quan sát kết quả hoặc có cơ chế giám sát khác có thể làm lỗi không được xử lý. Trả về bình thường từ run không tự chứng minh Callable thành công.

### Hết thời gian chờ không tự hủy

`get(timeout, unit)` có thể ném `TimeoutException`; đó là giới hạn chờ của nơi gọi. Nó không tự gọi cancel. Nếu công việc còn chạy, FutureTask có thể hoàn tất bình thường về sau.

### Hủy có thể sớm hơn việc mã tác vụ ngừng

`cancel(true)` cho phép cố ngắt luồng đang thực thi; công việc cần hợp tác với tín hiệu đó. `cancel(false)` không yêu cầu ngắt phần đã chạy. Một FutureTask đã cancelled có thể được quan sát là done trong khi thân công việc đang dọn dẹp hoặc tiếp tục chạy nếu không bị ngắt.

`get()` của FutureTask đã hủy báo `CancellationException`, không trả kết quả mà Callable có thể tính ra sau đó. Hủy cũng không hoàn tác tác dụng phụ đã xảy ra. [Hợp đồng Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

## 8. execute(task) khác submit(task) ở điểm dễ nhầm nào?

Khi đã tự tạo một FutureTask, cách trực tiếp thường là:

```java
FutureTask<Integer> inner = new FutureTask<>(() -> 42);
pool.execute(inner);
Integer value = inner.get();
```

Đây là đoạn minh họa trong phương thức đã có `ExecutorService pool` và xử lý các ngoại lệ của get.

Nếu thay bằng:

```java
FutureTask<Integer> inner = new FutureTask<>(() -> 42);
Future<?> outer = pool.submit(inner);
```

`inner` được nhận như một `Runnable`. Trong triển khai mặc định của `AbstractExecutorService`, `submit` tạo thêm một RunnableFuture bao quanh đối tượng Runnable đó. [AbstractExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/AbstractExecutorService.html).

Lúc này có hai lớp cần theo dõi:

- `inner.get()` là kết quả phép tính `42`.
- `outer.get()` của dạng submit(Runnable) là kết quả theo hợp đồng Runnable, thông thường là `null` khi `inner.run()` kết thúc bình thường.

Nếu Callable bên trong inner thất bại, inner có thể giữ lỗi và `inner.run()` vẫn trả bình thường. Khi đó outer có thể thành công trong khi inner thất bại. Tương tự, hủy outer và hủy inner không nên bị coi là cùng một trạng thái tự động ở mọi lịch chạy.

Không tạo hai lớp chỉ để có Future, vì FutureTask sẵn đã cung cấp nó. Trong trường hợp cần gửi Callable thông thường và không cần tự kiểm soát đối tượng bọc, `pool.submit(callable)` thường gọn hơn; dùng FutureTask khi thật sự cần một đối tượng có thể chạy và theo dõi do mình giữ trước lúc giao việc.

## 9. Khi nào việc tự giữ FutureTask có ích?

- Một API tiếp nhận Runnable nhưng nơi giao việc cần giá trị trả về hoặc trạng thái hủy.
- Cần tạo đối tượng công việc trước, công bố tay cầm Future cho bên quan sát, rồi quyết định cơ chế thực thi sau.
- Xây một lớp công cụ cần kiểm soát đối tượng công việc và có chính sách hoàn thành riêng.

Đối với công việc ứng dụng đơn giản đã dùng ExecutorService, không bắt buộc tự tạo FutureTask cho mọi lần submit. Bản thân `submit(Callable)` đã cung cấp Future.

Nếu công bố FutureTask trước khi gửi vào executor, phải xử lý cả khả năng executor từ chối nhận việc. Đối tượng không tự biến thành thất bại chỉ vì `execute(task)` bị từ chối; nếu không còn ai chạy nó, bên đang chờ Future có thể chờ mãi. Chủ sở hữu cần một chính sách như hủy tay cầm và báo rõ chưa giao được việc, thay vì bỏ qua lỗi giao việc.

## 10. done() và các điểm mở rộng: dùng khi có nhu cầu cụ thể

FutureTask có phương thức `protected done()` để lớp con quan sát việc chuyển sang trạng thái hoàn tất, kể cả hủy. Nó hữu ích cho việc ghi nhận hoàn thành hoặc thông báo, nhưng không nên là nơi chạy công việc dài, chờ vòng phụ thuộc hoặc ném lỗi không được quản lý.

Không giả định done luôn chạy trên luồng của executor. Trong trường hợp hủy, nó có thể được gọi bởi luồng thực hiện yêu cầu hủy. Cũng không dùng “done đã được gọi” để chứng minh thân tác vụ bị hủy đã thoát và dọn tài nguyên xong.

Một bên đang chờ get cũng không nên giả định mọi xử lý do lớp con thêm vào done đã hoàn tất ngay lúc get nhận kết quả; nếu thông báo phụ là điều kiện bắt buộc thì cần một hợp đồng đồng bộ riêng. Đây là chi tiết dành cho người xây công cụ; ứng dụng thông thường có thể dùng FutureTask mà không kế thừa nó.

Các phương thức protected khác như `set`, `setException` và `runAndReset` phục vụ triển khai mở rộng. Đừng tự gọi chúng qua thủ thuật chỉ để đổi kết quả một FutureTask đã hoàn tất. Tạo một lần thực thi mới giúp giữ rõ ranh giới kết quả và quyền hủy.

## 11. Lỗi phổ biến và tự kiểm tra

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| FutureTask là một luồng | Nó là công việc có khả năng theo dõi; luồng/executor là cơ chế chạy |
| Gọi get thì Callable bắt đầu chạy | Phải có bên thực thi run hoặc giao cho executor |
| run trả void nên không thể lấy kết quả | Kết quả được giữ để lấy qua Future |
| Gọi run nhiều lần sẽ tính nhiều lần | FutureTask thông thường bảo vệ một lần tính toán |
| run không ném lỗi nghĩa công việc thành công | Có thể lỗi đã được lưu để get báo |
| execute luôn làm lỗi đến handler của luồng | FutureTask có thể giữ lỗi bên trong |
| submit một FutureTask trả ngay Future của phép tính bên trong | Có thể tạo thêm Future ngoài theo hợp đồng Runnable |
| done đồng nghĩa mọi đoạn dọn dẹp đã xong | Với hủy, cần xét riêng sự kết thúc thực tế của mã tác vụ |

Tự kiểm tra:

1. Một đối tượng FutureTask có thể truyền cho Thread vì sao? **Nó triển khai Runnable qua RunnableFuture.**
2. Cùng FutureTask được nhìn qua Runnable và Future có tạo hai công việc không? **Không**, đó là cùng đối tượng với hai vai trò.
3. Runnable được bọc bằng FutureTask có cần tự return kết quả không? **Không**, giá trị kết quả có thể được định trước qua hàm tạo.
4. Sau khi hủy trước lúc chạy, gọi run có làm Callable được thực hiện không? **Không với FutureTask chuẩn đã hủy thành công.**

Thực hành: thay Callable tính `42` trong ví dụ bằng một Runnable tăng bộ đếm và dùng hàm tạo nhận kết quả định trước `"done"`. Đổi kiểu FutureTask thành `FutureTask<String>`, dự đoán hai lần get sẽ trả gì và số lần công việc được thực hiện. Sau đó thử tạo thêm FutureTask mới từ cùng công việc để phân biệt “lấy lại kết quả cũ” với “thực hiện một lần tính toán mới”.
