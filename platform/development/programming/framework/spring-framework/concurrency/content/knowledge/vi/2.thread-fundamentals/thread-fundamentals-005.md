# Quan hệ happens-before khi gửi tác vụ và nhận kết quả

Khi một ứng dụng Spring Framework giao công việc cho executor, hai câu hỏi phải được trả lời rõ: **dữ liệu mà luồng gọi đã chuẩn bị có hiển thị đúng với tác vụ không?** Và **sau khi tác vụ hoàn thành, luồng gọi có đọc được kết quả cùng các thay đổi mà tác vụ đã thực hiện không?** Java Memory Model (JMM) trả lời bằng quan hệ `happens-before`. Đây là nền tảng để dùng `Executor`, `ExecutorService`, `Future`, Spring `TaskExecutor` và `@Async` một cách an toàn.

## 1. `happens-before` nghĩa là gì?

`A happens-before B` (viết tắt là `A hb B`) là quan hệ thứ tự bộ nhớ: nếu A ghi dữ liệu và B đọc dữ liệu đó, quan hệ này giúp bảo đảm B nhìn thấy những ghi được công bố từ A theo quy tắc JMM, miễn là không có ghi cạnh tranh khác gây thay đổi giá trị. Nó không có nghĩa hai sự kiện buộc phải chạy trên cùng luồng, cũng không có nghĩa mọi tác vụ trong pool đều chạy tuần tự.

Ba quy tắc cần nhớ:

1. **Thứ tự trong cùng luồng:** hành động đứng trước trong thứ tự chương trình `hb` hành động đứng sau trong luồng ấy.
2. **Cạnh đồng bộ:** thao tác giữa các luồng như `volatile`, khóa `synchronized`, submit qua executor hoặc lấy kết quả từ `Future` có thể thiết lập quan hệ `hb`.
3. **Tính bắc cầu:** nếu `A hb B` và `B hb C` thì `A hb C`.

Quan hệ `hb` giải quyết **thứ tự và khả năng quan sát bộ nhớ**; nó **không tự biến** phép toán `counter++` thành nguyên tử và không bảo vệ đối tượng khỏi những luồng khác đang sửa nó đồng thời.

## 2. Hai cạnh quan trọng nhất trong vòng đời tác vụ

Đặc tả `java.util.concurrent` nêu hai bảo đảm trực tiếp:

- **Trước submit → bên trong tác vụ.** Các hành động của luồng gọi **trước khi** gửi `Runnable` tới `Executor`, hoặc `Runnable`/`Callable` tới `ExecutorService`, `happen-before` việc thực thi tác vụ. Ví dụ, luồng gọi gán `request.id = 7` rồi submit tác vụ đọc `request.id`: nếu không có luồng khác sửa giá trị, tác vụ nhận được dữ liệu đã công bố.
- **Bên trong tác vụ → sau `Future.get()`.** Các hành động của phép tính bất đồng bộ được đại diện bằng `Future` `happen-before` những hành động tiếp theo của luồng đã lấy kết quả bằng `Future.get()`. Bởi vậy, sau khi `get()` trả về bình thường, luồng chờ có thể dùng kết quả và quan sát các ghi của tác vụ trước khi hoàn tất.

```text
Luồng gọi (caller)                         Luồng thực thi (worker)
------------------                         ---------------------
ghi input = 41
       |                                             |
       +--- submit(task) --------------------------> đọc input = 41
                    [cạnh happens-before 1]          tính output = 42
                                                     hoàn tất Future
       <-------------------- get() trả về -----------+
                    [cạnh happens-before 2]
đọc output = 42
```

Từ tính bắc cầu: **ghi trước submit → thao tác trong task → thao tác sau `get()`**. Trái lại, một ghi của caller **sau** submit không tự nhiên `happen-before` lượt đọc của worker. Tương tự, hai task được submit độc lập không mặc nhiên có quan hệ thứ tự với nhau.

Lưu ý: `submit()` thường trả về trước khi tác vụ hoàn thành; việc trả về từ `submit()` **không phải** tín hiệu đã có kết quả. `get()` là điểm chờ hoàn tất và nhận kết quả của `Future` tương ứng.

## 3. Ví dụ Java 17+ chạy độc lập

Ví dụ cố ý dùng hai trường `int` thông thường, không khai báo `volatile`, để chỉ ra **đúng hai ranh giới đồng bộ**. Không có luồng thứ ba truy cập hoặc sửa `SharedState` đồng thời.

Tạo tệp `HappensBeforeTask.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class HappensBeforeTask {
    private static final class SharedState {
        int input;
        int output;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        SharedState state = new SharedState();
        state.input = 41; // Hành động xảy ra trước submit.

        try {
            Future<Integer> future = executor.submit(() -> {
                int observed = state.input; // Thấy 41 nhờ cạnh submit -> task.
                state.output = observed + 1;
                return state.output;
            });

            int result = future.get(); // Chờ task và thiết lập cạnh task -> caller.
            System.out.println("Future: " + result);
            System.out.println("State: " + state.output);
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac HappensBeforeTask.java
java HappensBeforeTask
```

Kết quả chuẩn:

```text
Future: 42
State: 42
```

**Vì sao kết quả ổn định?** Lệnh `state.input = 41` đứng trước `submit`; task đọc `input` sau ranh giới submit. Task ghi `state.output = 42` trước khi hoàn tất; caller chỉ đọc `output` **sau** `future.get()`. `Future` cũng trả trực tiếp giá trị `42`. Ví dụ này chứng minh bảo đảm của API, không dựa vào `Thread.sleep()`, may mắn về lịch lập lịch hay việc CPU có cache chung. `shutdown()` ở `finally` để giải phóng pool, không thay thế `get()`.

## 4. Điều gì xảy ra nếu đọc quá sớm?

Xem đoạn minh họa sau (giả sử `executor` là một `ExecutorService` đang hoạt động và `state` là đối tượng chỉ chứa trường `int output`):

```java
executor.execute(() -> state.output = 42);
System.out.println(state.output); // Có thể thấy giá trị cũ: chưa chờ task.
```

`execute()` chỉ giao việc, không trả về `Future` để caller chờ. Caller có thể đọc trước khi worker chạy, và với dữ liệu chia sẻ không đồng bộ còn có **data race**. Việc thử vài lần đều in `42` cũng không chứng minh mã đúng.

Khi cần xác nhận task đã hoàn tất, có thể dùng:

```java
Future<?> finished = executor.submit(() -> state.output = 42);
finished.get();
System.out.println(state.output); // 42 nếu không có luồng khác ghi cạnh tranh.
```

Đây là **đoạn trích minh họa**, không phải tệp Java chạy độc lập. Nếu không cần chia sẻ trạng thái, thiết kế dễ hiểu hơn là trả giá trị từ `Callable` rồi đọc trực tiếp qua `Future<Integer>.get()`.

## 5. Áp dụng cho Spring Framework

Spring `TaskExecutor` là abstraction triển khai `java.util.concurrent.Executor`: `execute(Runnable)` có ý nghĩa giao tác vụ tương tự. `AsyncTaskExecutor` bổ sung `submit(...)` để nhận `Future`; `ThreadPoolTaskExecutor` là triển khai phổ biến và dùng pool JDK bên dưới. Do đó các quy tắc xuất bản dữ liệu theo submit và chờ kết quả vẫn là quy tắc JMM của Java. Lưu ý một số executor (như `SyncTaskExecutor`) chạy ngay trên luồng gọi: tên `TaskExecutor` tự nó không hứa luôn có luồng khác.

Trong ứng dụng Spring, nếu cần lấy kết quả, hãy giữ `Future` do `AsyncTaskExecutor.submit` trả về rồi dùng `get()` ở nơi cần giá trị. Ví dụ logic bên trong một Spring bean đã được inject `AsyncTaskExecutor executor`:

```java
int input = 21;
Future<Integer> future = executor.submit(() -> input * 2);
int value = future.get(); // value = 42
```

Đoạn này cần bean `executor` và xử lý `InterruptedException`/`ExecutionException` trong ngữ cảnh ứng dụng; nó là **mảnh mã tích hợp**, không phải chương trình Java độc lập.

### Với `@Async`

Khi `@EnableAsync` đã được bật, một lệnh gọi **đi qua Spring proxy** tới phương thức `@Async` được gửi cho executor cấu hình. Phương thức có thể trả `Future<T>` hoặc `CompletableFuture<T>`. Ví dụ phương thức trong Spring-managed service:

```java
@Async("workExecutor")
public CompletableFuture<Integer> twice(int number) {
    return CompletableFuture.completedFuture(number * 2);
}
```

Giả sử `workExecutor` là bean executor được cấu hình, và một **bean khác** nhận service này qua injection:

```java
CompletableFuture<Integer> future = asyncCalculationService.twice(21);
int result = future.get(); // result = 42
```

Hai đoạn trên là **mảnh mã Spring**, cần import, bean/service, `@EnableAsync`, executor và wiring tương ứng để chạy trong ứng dụng thực tế. Dù phần thân phương thức trả `completedFuture` khi xử lý xong, **Future mà proxy trả cho caller** đại diện cho quá trình async; caller chỉ dùng kết quả sau khi Future đó hoàn tất. Nếu một phương thức gọi `this.twice(...)` bên trong cùng bean trong chế độ proxy mặc định, lời gọi có thể bỏ qua proxy nên **không có hand-off bất đồng bộ như dự tính**.

Với phương thức `@Async void`, caller không có `Future` để chờ hoặc nhận lỗi/kết quả. Nếu cần xác nhận hoàn tất, ưu tiên một kiểu trả về Future phù hợp hoặc dùng cơ chế đồng bộ rõ ràng; đừng đọc trực tiếp một biến chia sẻ rồi coi nó là kết quả tác vụ.

### `CompletableFuture` và callback

`CompletableFuture` là một `Future`: `get()` chờ kết quả; `join()` cũng lấy kết quả sau khi hoàn tất nhưng khác cách báo ngoại lệ (thường bọc lỗi trong `CompletionException` thay vì checked `ExecutionException`). Các stage như `thenApply` chỉ chạy khi stage nguồn có kết quả; tuy nhiên hậu tố `Async` và executor được chỉ định mới quyết định lịch thực thi stage, **không nên suy luận tên luồng từ việc callback tồn tại**.

Khi diễn giải bảo đảm theo tài liệu JDK một cách chính xác, hãy lấy **`Future.get()`** làm mốc đối chiếu rõ nhất cho cạnh *task → consumer*. Nếu xử lý chuỗi CompletableFuture, thiết kế để stage phụ thuộc vào đúng Future, không dựa vào việc hai tác vụ tình cờ chạy chung pool.

## 6. Kết nối nhiều tác vụ bằng tính bắc cầu

Giả sử task A viết một giá trị, task B phải đọc giá trị đó. Chỉ submit A rồi submit B liên tiếp **không đủ** để khẳng định A đã xong trước B; pool nhiều luồng có thể chạy chúng song song.

Nếu caller cần B nhìn thấy ghi của A, một cách trực tiếp là chờ A trước khi gửi B:

```java
Future<?> writer = executor.submit(() -> state.output = 99);
writer.get();
Future<Integer> reader = executor.submit(() -> state.output);
System.out.println(reader.get()); // 99, nếu không có ghi cạnh tranh khác.
```

Chuỗi lý do là: **ghi của A → `writer.get()` trở về → caller submit B → B đọc**. Các cạnh kết hợp bằng tính bắc cầu. Đây cũng là lý do luồng xử lý nhiều giai đoạn nên thể hiện quan hệ phụ thuộc bằng Future/CompletionStage hoặc cơ chế đồng bộ rõ ràng.

Ngược lại, đợi **tất cả** Future sau khi đã submit các task không tự sửa race **giữa chính các task**. Ví dụ hai task cùng làm `counter++` trên `int` thường có thể mất cập nhật; cần `AtomicInteger`, `synchronized`, lock hoặc phân chia dữ liệu hợp lý. `Future.get()` giúp caller nhận **kết quả đã hoàn tất**, không làm các thao tác đồng thời bên trong trở thành atomic.

## 7. Các ranh giới cần phân biệt

| Tình huống | Bảo đảm nên dựa vào | Điều không được suy luận |
| --- | --- | --- |
| Caller ghi dữ liệu, rồi `submit(task)` | Ghi trước submit `hb` hành động trong task | Submit tạo bản sao bất biến của mọi object; ghi sau submit sẽ tự hiện ra |
| `Executor.execute(task)` trả về | Task được gửi để thực thi theo hợp đồng executor | Task đã hoàn tất hoặc caller đã nhận các ghi của nó |
| `Future.get()` trở về bình thường | Tác vụ đã xong, trả kết quả và công bố ghi của tác vụ cho caller | Những task khác cũng xong hoặc mọi thao tác trên shared object đều thread-safe |
| `get(timeout, unit)` ném `TimeoutException` | Chưa lấy được kết quả hoàn tất trong thời hạn chờ | Task đã dừng hay có thể đọc state kết quả ngay |
| `future.isDone()` | Có thể kiểm tra trạng thái hoàn tất của Future | Có thể thay thế tùy ý cho giao thức lấy kết quả và xử lý lỗi |
| `shutdown()` trên `ExecutorService` | Không nhận task mới và cho phép các task đã nộp tiếp tục theo hợp đồng | Phương thức này chờ hết task hoặc là mốc lấy kết quả |
| Hai task cùng pool | Cùng dùng cơ chế thực thi | Một task luôn `hb` task kia chỉ vì thứ tự submit |

Nếu `get()` ném `ExecutionException`, tác vụ đã kết thúc với lỗi nhưng caller **không có kết quả thành công** để sử dụng; cần kiểm tra nguyên nhân. `InterruptedException` cho biết luồng chờ bị ngắt; khi tự bắt ngoại lệ thay vì chuyển tiếp, thường cần khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()`. `CancellationException` cho biết Future bị hủy. Hủy Future hoặc timeout không phải lời cam kết mọi code của task đã dừng ngay.

## 8. Những lỗi thường gặp và cách sửa

1. **Ghi dữ liệu sau khi submit rồi mong task thấy.** Chuẩn bị input hoàn chỉnh **trước** submit; nếu input thay đổi trong khi task chạy, dùng cấu trúc immutable, `volatile`, lock hoặc giao thức đồng bộ phù hợp.
2. **Dùng `Thread.sleep()` để “đợi đủ lâu”.** Ngủ không tạo ra cạnh kết quả như `Future.get()`; nó phụ thuộc tốc độ máy và lịch CPU. Chờ đúng Future hoặc tín hiệu đồng bộ đã định nghĩa.
3. **Đọc shared field ngay khi `execute()` trả về.** Dùng `submit()+get()`, `CompletableFuture` hoặc giao thức đồng bộ khác nếu cần kết quả.
4. **Tưởng `get()` chữa mọi race.** Nó giải quyết điểm công bố kết quả từ một tác vụ tới caller; truy cập ghi/đọc đồng thời bên trong nhiều task vẫn cần bảo vệ riêng.
5. **Chờ `get()` ngay sau mọi lần submit trong một vòng lặp.** Cách đó đúng về đồng bộ nhưng có thể tuần tự hóa luồng gọi và làm mất lợi ích song song. Khi các task độc lập, submit trước rồi lấy kết quả từ các Future sau.
6. **Giả định `@Async` luôn chạy async khi gọi trong cùng bean.** Kiểm tra việc đi qua Spring proxy và kiểu trả về; dùng bean khác gọi qua injection để interceptor xử lý.
7. **Coi `Future.get()` thành công dù timeout, hủy hoặc lỗi.** Phân biệt kết quả bình thường với các nhánh ngoại lệ; chỉ xử lý dữ liệu thành công khi thực sự có kết quả.

## 9. Cách tự kiểm tra thiết kế

Trước khi chia sẻ một đối tượng giữa caller và worker, hãy lần theo bốn điểm: **(1)** ghi input nằm trước lời gọi submit hay không, **(2)** có ai khác vẫn đang sửa input không, **(3)** consumer chờ đúng Future/tín hiệu hoàn tất nào, và **(4)** có nhiều task đồng thời đọc-ghi state đó hay không. Nếu không chỉ ra được đường `happens-before` từ write tới read, chưa nên kết luận mã an toàn chỉ vì chạy thử thấy đúng.

**Tài liệu chuẩn để đối chiếu:**
- [Java SE 17 — `java.util.concurrent`, Memory Consistency Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html)
- [Java SE 17 — `ExecutorService`, Memory consistency effects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
