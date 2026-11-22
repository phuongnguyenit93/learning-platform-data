# CompletableFuture.allOf và thu kết quả nhiều future trong Java

## 1. Mục tiêu bài học

Khi ứng dụng cần thực hiện nhiều công việc độc lập — chẳng hạn tải hồ sơ, lấy đơn hàng, kiểm tra quyền truy cập hoặc gọi nhiều dịch vụ — `CompletableFuture` cho phép bắt đầu các tác vụ bất đồng bộ rồi ghép chúng thành một pipeline. `CompletableFuture.allOf(...)` là công cụ chuẩn để **đợi tất cả những future đã cho hoàn tất**.

Nhưng `allOf` **không** tự trả về danh sách giá trị của từng future. Kết quả của nó là `CompletableFuture<Void>`, vì vậy muốn “đợi tất cả và thu kết quả” phải kết hợp thêm `join()`, `thenApply(...)` hoặc chuyển từng kết quả thành một đối tượng thể hiện thành công/thất bại.

Mục tiêu cụ thể:

1. Hiểu chính xác signature và hành vi của `allOf`.
2. Tạo nhiều `CompletableFuture<T>` bằng `completedFuture` hoặc `supplyAsync`; phân biệt tác vụ độc lập với tác vụ phụ thuộc.
3. Thu `List<T>` theo **thứ tự đầu vào**, bất kể thứ tự hoàn tất.
4. Viết tiện ích generic `sequence` trả về `CompletableFuture<List<T>>`, tránh chờ chặn không cần thiết.
5. Ghép các future **khác kiểu dữ liệu** thành một record/DTO đã định kiểu.
6. Phân biệt lỗi của *một future* và lỗi của *aggregate allOf*; xử lý partial success, fallback và báo cáo lỗi đầy đủ.
7. Biết sự khác nhau của `join` và `get`, cũng như `CompletionException` và `ExecutionException`.
8. Hiểu thời hạn đợi, timeout, cancellation và vì sao `allOf` **không tự dừng** các công việc đang chạy.
9. Xử lý trường hợp tập đầu vào rỗng, phần tử `null`, giá trị kết quả `null` và giới hạn tài nguyên.
10. Kiểm thử kết quả xác định mà không phụ thuộc timing, `Thread.sleep` hoặc thứ tự thread chạy.

`CompletableFuture` và `allOf` được giới thiệu từ **Java 8** và vẫn là API hiện hành. Các chương trình đầy đủ trong bài sử dụng **Java 17+**; những API ra đời sau Java 8 sẽ được ghi rõ, ví dụ `CompletableFuture.failedFuture` và `orTimeout` từ Java 9, `Stream.toList()` từ Java 16. Nội dung sử dụng khả năng đang được hỗ trợ, không dựa vào API lỗi thời.

## 2. Vị trí của `allOf` trong pipeline bất đồng bộ

Signature:

```java
public static CompletableFuture<Void> allOf(
        CompletableFuture<?>... cfs)
```

*Đây là khai báo API minh họa, không phải một chương trình độc lập.*

Nó nhận một mảng varargs các `CompletableFuture<?>`, tức có thể chứa future nhiều kiểu, và trả về **một future tổng hợp kiểu `Void`**.

Các quy tắc cần thuộc:

- Aggregate hoàn tất **khi tất cả các future đầu vào đều hoàn tất**. “Hoàn tất” bao gồm thành công, thất bại hoặc bị hủy.
- Nếu **mọi đầu vào thành công**, aggregate hoàn tất bình thường với giá trị `null`.
- Nếu **bất kỳ đầu vào thất bại**, aggregate cũng hoàn tất **exceptionally** với `CompletionException` mang nguyên nhân lỗi; nó vẫn là mốc đồng bộ cho tất cả đầu vào.
- Nếu **không có future nào**, `allOf()` trả một `CompletableFuture<Void>` đã hoàn tất bình thường với `null`.
- `allOf` **không** mang kết quả `T` của từng future. Các kết quả phải được lấy từ **chính các future thành phần** sau đó.
- Mảng đầu vào `null` hoặc bất kỳ phần tử future nào `null` khiến `allOf` ném `NullPointerException`.

Hình dung:

```text
Future<User>   f1 ----------- [User]
                                 \
Future<List>   f2 ------ [List] ----> allOf(f1,f2,f3) -> Future<Void>
                                 /                         |
Future<Boolean> f3 ------------- [true]                   | barrier
                                                           v
                                  Đọc f1.join(), f2.join(), f3.join()
                                                           |
                                                           v
                                         Ghép User + List + Boolean
```

**Vì sao trả `Void`?** `allOf` được thiết kế là *barrier* (mốc hội tụ). Nó không áp đặt cách bạn muốn tổng hợp các giá trị khác kiểu thành một danh sách hay object. Bạn có thể tạo `List<T>` nếu cùng kiểu, hoặc `record Dashboard(...)` khi khác kiểu.

Một lỗi thường gặp:

```java
CompletableFuture<Void> barrier =
        CompletableFuture.allOf(first, second);

// KHÔNG tồn tại List<Result> trả ra chỉ nhờ barrier.join():
barrier.join(); // nhận null khi thành công
```

*Snippet giả định `first` và `second` đã được khai báo. Không phải chương trình độc lập.*

## 3. Kiểm chứng barrier: đợi tất cả, không thu giá trị

Để hiểu `allOf`, chưa cần thread. Tạo hai future chưa hoàn tất, hoàn tất từng cái bằng tay, rồi kiểm tra trạng thái.

Lưu `AllOfBarrierDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class AllOfBarrierDemo {
    public static void main(String[] args) {
        CompletableFuture<String> user =
                new CompletableFuture<>();
        CompletableFuture<Integer> points =
                new CompletableFuture<>();

        CompletableFuture<Void> barrier =
                CompletableFuture.allOf(user, points);

        System.out.println("initialDone = " + barrier.isDone());

        user.complete("Lan");
        System.out.println("afterUser = " + barrier.isDone());

        points.complete(42);
        System.out.println("afterPoints = " + barrier.isDone());

        System.out.println("barrierReturnsNull = " +
                (barrier.join() == null));
        System.out.println("user = " + user.join());
        System.out.println("points = " + points.join());
    }
}
```

Biên dịch và chạy:

```bash
javac AllOfBarrierDemo.java
java AllOfBarrierDemo
```

Stdout:

```text
initialDone = false
afterUser = false
afterPoints = true
barrierReturnsNull = true
user = Lan
points = 42
```

Những điều quan sát được:

1. `allOf` chỉ hoàn tất khi **cả** `user` và `points` hoàn tất.
2. `barrier.join()` không trả `Lan`, `42`, `List<?>` hay tuple; kết quả bình thường là `null`.
3. Các future thành phần vẫn giữ kết quả của chính chúng.
4. Không cần `Thread.sleep` để kiểm thử: hành vi hội tụ có thể được kiểm chứng bằng complete thủ công, rõ ràng và không flaky.

`CompletableFuture.complete(value)` chỉ cố gắng hoàn tất future bằng giá trị. Nếu future đã kết thúc, lần gọi sau không thay thế kết quả (trừ các API đặc biệt vốn không cần dùng trong bài này). Trong ví dụ, `complete` chạy đồng bộ trong thread gọi nên thứ tự in là xác định.

## 4. Thu `List<T>` khi mọi future cùng kiểu

Giả sử có danh sách future `CompletableFuture<String>`. Công thức đơn giản nhất:

1. Tạo mảng `CompletableFuture<?>[]` cho `allOf`.
2. Gọi `allOf(...).join()` để chờ tất cả.
3. Lấy kết quả từng future theo thứ tự của danh sách ban đầu bằng `f.join()`.
4. Đưa vào `List<String>`.

Lưu `AllOfCollectionDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfCollectionDemo {
    public static void main(String[] args) {
        List<CompletableFuture<String>> futures = List.of(
                CompletableFuture.completedFuture("alpha"),
                CompletableFuture.completedFuture("beta"),
                CompletableFuture.completedFuture("gamma"));

        CompletableFuture<?>[] array =
                futures.toArray(new CompletableFuture<?>[0]);

        CompletableFuture.allOf(array).join();

        List<String> results = futures.stream()
                .map(CompletableFuture::join)
                .toList();

        System.out.println("size = " + results.size());
        System.out.println("results = " + results);
        System.out.println("first = " + results.get(0));
    }
}
```

```bash
javac AllOfCollectionDemo.java
java AllOfCollectionDemo
```

```text
size = 3
results = [alpha, beta, gamma]
first = alpha
```

Sau khi barrier đã hoàn tất **bình thường**, mỗi future thành phần đã hoàn tất thành công, nên `join` trên các future đó **không chờ thêm**. Nếu barrier thất bại, `barrier.join()` sẽ ném exception và các dòng thu kết quả phía dưới **không tự chạy**. Cần chiến lược riêng để lấy partial results; xem mục 9–11.

Ở đây `Stream.toList()` là API có từ Java 16, nên mẫu code yêu cầu Java 17+ như đã nêu. Nếu ứng dụng vẫn chạy Java 8, thay bằng `collect(Collectors.toList())` với import thích hợp; API đó **không bảo đảm tính bất biến** của List. `Stream.toList()` trả danh sách không thể sửa qua `add/remove`.

### 4.1. Thứ tự list không phải thứ tự hoàn thành

`map(CompletableFuture::join)` duyệt theo **thứ tự encounter order của stream** khi nguồn là `List`. Nó không tự sắp xếp theo việc future nào xong trước. Đây là ưu điểm khi cần giữ quan hệ giữa input và output.

Nếu cần “kết quả nào xong thì xử lý ngay”, đó là mô hình khác, ví dụ mỗi future có callback, queue kết quả hoặc publisher. Đừng đổi ý nghĩa từ “đợi tất cả rồi thu kết quả” thành “completion order” khi chưa có yêu cầu.

## 5. `supplyAsync` thực sự chạy trên executor: đừng đoán thứ tự

Các ví dụ trên có future hoàn thành thủ công hoặc đã hoàn thành. Trong ứng dụng, nhiều tác vụ bất đồng bộ có thể chạy trên executor:

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> loadFromService(), executor);
```

*Snippet này yêu cầu `loadFromService()` và `executor` được định nghĩa trong ứng dụng; nó không tự chạy độc lập.*

Dùng `supplyAsync` khi có kết quả; dùng `runAsync` khi tác vụ không trả giá trị (`CompletableFuture<Void>`). Khi tạo nhiều future, nên xác định rõ **executor** và hạn mức tài nguyên, đặc biệt với blocking I/O.

Lưu `AllOfAsyncTasksDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AllOfAsyncTasksDemo {
    public static void main(String[] args) {
        ExecutorService executor =
                Executors.newFixedThreadPool(3);

        try {
            List<Integer> inputs = List.of(3, 1, 2);

            List<CompletableFuture<Integer>> futures =
                    inputs.stream()
                    .map(n -> CompletableFuture.supplyAsync(
                            () -> n * n, executor))
                    .toList();

            CompletableFuture.allOf(
                    futures.toArray(
                            new CompletableFuture<?>[0]))
                    .join();

            List<Integer> squares = futures.stream()
                    .map(CompletableFuture::join)
                    .toList();

            System.out.println("inputs = " + inputs);
            System.out.println("squares = " + squares);
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac AllOfAsyncTasksDemo.java
java AllOfAsyncTasksDemo
```

```text
inputs = [3, 1, 2]
squares = [9, 1, 4]
```

Ba phép tính có thể hoàn tất theo thứ tự bất kỳ tùy scheduler, nhưng kết quả in ra vẫn theo `inputs`. Không in thread name hoặc thời gian thực nếu bạn cần stdout ổn định.

**Quản lý tài nguyên:** executor phải có cơ chế lifecycle phù hợp. Ví dụ dùng `finally` để `shutdown()` và chỉ có những tác vụ tính toán ngắn; trong ứng dụng lâu dài, cần cân nhắc `awaitTermination`, yêu cầu ngừng, xử lý lỗi và shutdown graceful theo contract. Không dùng pool vô hạn cho hàng nghìn request đang chờ I/O.

### 5.1. Default executor không phải lựa chọn tối ưu cho mọi workload

Các bản `supplyAsync` không truyền executor thường dùng `ForkJoinPool.commonPool()` (với các chi tiết fallback theo điều kiện JDK). Pool chung phù hợp với nhiều tác vụ tính toán ngắn nhưng có thể không phù hợp với blocking I/O kéo dài. Hệ thống có thể dùng executor do ứng dụng quản lý, giới hạn concurrency theo downstream và timeout theo ngân sách request.

**`allOf` không lập lịch tác vụ.** Nó chỉ theo dõi những future bạn đã cung cấp. Việc future bắt đầu chạy, số thread và giới hạn concurrency là trách nhiệm của phần tạo tác vụ/executor hoặc client bất đồng bộ.

## 6. Biến allOf thành `CompletableFuture<List<T>>`: hàm `sequence`

Trong code nghiệp vụ, muốn tiếp tục pipeline mà **không chặn thread gọi** bằng `join()` ngay lập tức, hãy trả một future tổng hợp **có kiểu kết quả**:

```text
List<CompletableFuture<T>>
              |
              v
allOf(futures...) -> CompletableFuture<Void>
              |
           thenApply
              |
              v
join từng future (tất cả đã xong nếu barrier thành công)
              |
              v
CompletableFuture<List<T>>
```

Chú ý: `thenApply` chỉ thực thi khi `allOf` hoàn tất bình thường. Nếu một future thất bại, future `sequence` cũng thất bại; nó **không** tự trả danh sách các kết quả còn lại.

Lưu `AllOfSequenceDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfSequenceDemo {
    public static <T> CompletableFuture<List<T>> sequence(
            List<CompletableFuture<T>> futures) {

        CompletableFuture<Void> barrier =
                CompletableFuture.allOf(
                        futures.toArray(
                                new CompletableFuture<?>[0]));

        return barrier.thenApply(ignored ->
                futures.stream()
                        .map(CompletableFuture::join)
                        .toList());
    }

    public static void main(String[] args) {
        CompletableFuture<String> first =
                new CompletableFuture<>();
        CompletableFuture<String> second =
                new CompletableFuture<>();

        CompletableFuture<List<String>> together =
                sequence(List.of(first, second));

        System.out.println("before = " + together.isDone());

        second.complete("B");
        System.out.println("afterSecond = " +
                together.isDone());

        first.complete("A");
        System.out.println("result = " + together.join());

        CompletableFuture<List<String>> empty =
                sequence(List.of());
        System.out.println("empty = " + empty.join());
    }
}
```

```bash
javac AllOfSequenceDemo.java
java AllOfSequenceDemo
```

```text
before = false
afterSecond = false
result = [A, B]
empty = []
```

**Vì sao bên trong `thenApply` lại dùng `join`?** Callback chỉ chạy sau khi `allOf` hoàn tất bình thường, nên những future thành phần đã hoàn tất; `join` ở đây chỉ **lấy kết quả**, không còn chờ công việc đang chạy. Mẫu này an toàn hơn việc đưa nhiều lời gọi `join` vào một task đang chiếm thread của chính executor cần thực hiện các công việc đó.

**Lưu ý với input List:** ví dụ giả định danh sách đầu vào không bị sửa trong lúc chạy. Nếu caller truyền một danh sách mutable và chỉnh sửa nó giữa lúc gọi `allOf` và callback `thenApply`, danh sách được dùng để dựng barrier có thể khác danh sách được duyệt để lấy kết quả. Trong code dùng lại, có thể tạo snapshot `new ArrayList<>(futures)` (và kiểm tra null) trước khi dựng barrier, rồi dùng snapshot trong callback.

**Lưu ý null:** `Stream.toList()` chấp nhận phần tử `null`. Nếu một future hoàn tất bình thường với `null`, danh sách kết quả vẫn có thể chứa `null`; nếu gọi `List.copyOf(results)` sẽ bị từ chối vì `List.copyOf` không cho phép phần tử null. Hãy định nghĩa rõ contract dữ liệu kết quả.

## 7. Thu nhiều future khác kiểu bằng DTO hoặc record

`CompletableFuture.allOf(...)` nhận `CompletableFuture<?>` nên có thể chờ `CompletableFuture<String>`, `CompletableFuture<List<String>>` và `CompletableFuture<Boolean>` cùng lúc. Không ép các giá trị đó thành `List<Object>` nếu domain có kiểu rõ ràng: một record/DTO giúp biên dịch kiểm tra lỗi kiểu dữ liệu.

Lưu `AllOfDashboardDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfDashboardDemo {
    record Dashboard(
            String username,
            int roleCount,
            boolean active) {
    }

    public static void main(String[] args) {
        CompletableFuture<String> user =
                CompletableFuture.completedFuture("Linh");
        CompletableFuture<List<String>> roles =
                CompletableFuture.completedFuture(
                        List.of("editor", "viewer"));
        CompletableFuture<Boolean> active =
                CompletableFuture.completedFuture(true);

        CompletableFuture<Dashboard> dashboard =
                CompletableFuture.allOf(user, roles, active)
                .thenApply(ignored -> new Dashboard(
                        user.join(),
                        roles.join().size(),
                        active.join()));

        System.out.println("dashboard = " +
                dashboard.join());
    }
}
```

```bash
javac AllOfDashboardDemo.java
java AllOfDashboardDemo
```

```text
dashboard = Dashboard[username=Linh, roleCount=2, active=true]
```

`record` đã trở thành tính năng chuẩn từ Java 16, dùng được trên Java 17+. Nếu chạy Java 8, có thể thay record bằng POJO immutable.

**Không dựa vào việc `allOf` đã “lưu” các giá trị.** Nó không có chúng trong kiểu `Void`. Callback tự đọc `user.join()`, `roles.join()`, `active.join()` từ các future thành phần.

### 7.1. Khi nào `thenCombine` đơn giản hơn?

Nếu chỉ có **hai** future thành công cần gộp, `thenCombine` cung cấp callback nhận hai giá trị đã định kiểu trực tiếp:

```java
CompletableFuture<String> user =
        CompletableFuture.completedFuture("Linh");
CompletableFuture<Integer> count =
        CompletableFuture.completedFuture(2);

CompletableFuture<String> label =
        user.thenCombine(count,
                (name, n) -> name + ": " + n);
```

*Đây là snippet hoàn chỉnh về biểu thức nhưng không có class/`main`; cần import `CompletableFuture`. `label.join()` trả `"Linh: 2"`.*

Sử dụng `thenCombine` khi có hai nhánh rõ ràng; `allOf` đặc biệt tiện khi có **danh sách động N future** hoặc ba nhánh trở lên và bạn cần một barrier chung. `thenCompose` lại dùng cho **phụ thuộc dữ liệu**: tác vụ B chỉ được tạo khi A có giá trị. Những mục đích này không hoán đổi cho nhau.

## 8. Khi một future thất bại, `allOf` sẽ như thế nào?

Theo hợp đồng Java:

- Nếu có future hoàn tất exceptionally, `allOf` cũng hoàn tất exceptionally **sau khi toàn bộ các future đã hoàn tất**.
- Khi gọi `join` trên aggregate, bạn thường gặp `CompletionException` với nguyên nhân gốc bên trong `getCause()`.
- `allOf` **không tự “fail-fast cancel”** các future còn lại và cũng không biến lỗi thành giá trị bình thường.
- Nếu **nhiều** future cùng thất bại, **không có bảo đảm bạn lấy được tất cả exception từ riêng `allOf`**; cause đại diện cho một lỗi. Nếu cần tất cả, phải quan sát từng future.
- Một future hoàn tất exceptionally **không** khiến mọi future khác tự thất bại nếu chúng độc lập.

Lưu `AllOfFailureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AllOfFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("remote error"));
        CompletableFuture<String> pending =
                new CompletableFuture<>();

        CompletableFuture<Void> barrier =
                CompletableFuture.allOf(failed, pending);

        System.out.println("beforeSibling = " +
                barrier.isDone());

        pending.complete("fallback-independent");
        System.out.println("afterSibling = " +
                barrier.isDone());
        System.out.println("exceptional = " +
                barrier.isCompletedExceptionally());

        try {
            barrier.join();
            System.out.println("unexpected");
        } catch (CompletionException e) {
            System.out.println("cause = " +
                    e.getCause().getClass().getSimpleName());
        }

        System.out.println("siblingValue = " +
                pending.join());
    }
}
```

```bash
javac AllOfFailureDemo.java
java AllOfFailureDemo
```

```text
beforeSibling = false
afterSibling = true
exceptional = true
cause = IllegalStateException
siblingValue = fallback-independent
```

`CompletableFuture.failedFuture` được bổ sung từ Java 9; trên Java 8 có thể tạo `new CompletableFuture<T>()` rồi gọi `completeExceptionally(exception)` để dựng case tương đương.

**Không viết** `allOf(futures...).join(); futures.stream().map(join)...` nếu hệ thống phải giữ kết quả từ các task thành công khi một task lỗi. Câu lệnh đầu sẽ ném exception và bỏ qua phần collect. Trường hợp cần partial success phải dùng pattern riêng ở mục 9.

## 9. Thu cả kết quả thành công và lỗi của từng future

Một mẫu đáng tin cậy cho **best-effort bulk processing** là biến mỗi future thành một future **trả kết quả dạng dữ liệu**, ví dụ:

```text
CompletableFuture<T>
     |
     +--- success --------> Outcome(id, value, null)
     |
     +--- exception ------> Outcome(id, null, error)
     |
  handle((value,error) -> Outcome(...))
     |
CompletableFuture<Outcome<T>>
```

Vì callback `handle` bắt cả hai trạng thái và **trả giá trị bình thường** nếu chính handler không lỗi, những future đã chuẩn hóa này có thể hoàn tất thành công bất kể tác vụ gốc thành công hay thất bại. `allOf` trên chúng khi đó cho phép thu **đầy đủ danh sách outcomes**. Cách này cũng giữ được quan hệ **task ID → kết quả/lỗi**.

Lưu `AllOfOutcomesDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfOutcomesDemo {
    record Outcome(
            String taskId,
            String value,
            Throwable error) {
        boolean success() {
            return error == null;
        }
    }

    public static void main(String[] args) {
        List<CompletableFuture<String>> raw = List.of(
                CompletableFuture.completedFuture("A"),
                CompletableFuture.failedFuture(
                        new IllegalStateException("not found")),
                CompletableFuture.completedFuture("C"));

        List<CompletableFuture<Outcome>> normalized =
                new ArrayList<>();

        for (int i = 0; i < raw.size(); i++) {
            final String taskId = "task" + (i + 1);
            normalized.add(raw.get(i).handle(
                    (value, error) ->
                            new Outcome(taskId, value, error)));
        }

        CompletableFuture<List<Outcome>> combined =
                CompletableFuture.allOf(
                        normalized.toArray(
                                new CompletableFuture<?>[0]))
                .thenApply(ignored -> normalized.stream()
                        .map(CompletableFuture::join)
                        .toList());

        List<Outcome> results = combined.join();

        System.out.println("successCount = " +
                results.stream()
                        .filter(Outcome::success)
                        .count());
        System.out.println("failureCount = " +
                results.stream()
                        .filter(o -> !o.success())
                        .count());
        System.out.println("summary = " +
                results.stream().map(o ->
                        o.taskId() + ":" +
                        (o.success()
                                ? o.value()
                                : o.error().getClass()
                                        .getSimpleName()))
                        .toList());
    }
}
```

```bash
javac AllOfOutcomesDemo.java
java AllOfOutcomesDemo
```

```text
successCount = 2
failureCount = 1
summary = [task1:A, task2:IllegalStateException, task3:C]
```

### 9.1. Những giới hạn của pattern `handle`

- Nếu handler tự ném exception, future normalized **vẫn có thể thất bại**, khiến aggregate thất bại.
- `error` đôi khi là exception trực tiếp, đôi khi đã được bọc trong `CompletionException`. Khi cần phân loại lỗi nghiệp vụ, viết hàm unwrap có chủ đích; không in toàn bộ stack trace vào kết quả công khai.
- `null` ở `value` không tự đồng nghĩa thất bại: một future có thể hoàn tất **thành công với null**. Dùng `error == null` hoặc một kiểu trạng thái rõ ràng để phân biệt.
- Chỉ ghi lỗi và message được phép hiển thị; thông tin nhạy cảm trong exception từ downstream không nên lộ ra API.
- Khi nhiều task cùng truy cập tài nguyên, đừng dùng `ArrayList` được sửa đồng thời từ nhiều handler. Ở ví dụ trên, list được **xây trong thread main** trước khi chờ; handler chỉ tạo object, không đẩy kết quả vào một collection mutable dùng chung. Đây là một cách tránh race condition.

Có thể định nghĩa generic `Outcome<T>` để giữ nguyên kiểu kết quả, hoặc dùng `record Result<T>(T value, Throwable error)`. Việc lựa chọn kiểu kết quả là phần của contract domain.

## 10. `exceptionally`, `handle`, `whenComplete`: khác nhau trước allOf

Ba phương thức đều liên quan tới lỗi, nhưng không tương đương:

| Phương thức | Khi nào chạy? | Thay đổi kết quả? | Cách dùng thường thấy |
| --- | --- | --- | --- |
| `exceptionally(fn)` | Chỉ khi stage thất bại | Có: trả giá trị fallback cùng kiểu `T` | Recover một tác vụ |
| `handle((value,error) -> ...)` | Cả thành công và thất bại | Có: có thể chuyển `T` sang `U` | Tạo `Outcome`, ghi trạng thái |
| `whenComplete((value,error) -> ...)` | Cả thành công và thất bại | Theo hợp đồng dùng để quan sát, không recover giá trị/lỗi nguồn | Logging/metrics/tracing |

Nếu `whenComplete` tự ném exception, stage trả ra có quy tắc ưu tiên lỗi riêng. Đừng dùng nó làm “recover fallback”; hãy dùng `exceptionally` hoặc `handle`.

Lưu `AllOfRecoveryDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.atomic.AtomicInteger;

public class AllOfRecoveryDemo {
    public static void main(String[] args) {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalArgumentException("bad input"));

        AtomicInteger observed = new AtomicInteger();

        CompletableFuture<String> observedStage =
                failed.whenComplete(
                        (value, error) ->
                                observed.incrementAndGet());

        CompletableFuture<String> recovered =
                failed.exceptionally(error -> "FALLBACK");

        CompletableFuture<String> healthy =
                CompletableFuture.completedFuture("OK");

        CompletableFuture.allOf(
                recovered, healthy).join();

        System.out.println("results = " +
                List.of(recovered.join(), healthy.join()));
        System.out.println("observed = " + observed.get());

        try {
            observedStage.join();
            System.out.println("unexpected");
        } catch (CompletionException e) {
            System.out.println("observedStillFailed = true");
        }
    }
}
```

```bash
javac AllOfRecoveryDemo.java
java AllOfRecoveryDemo
```

```text
results = [FALLBACK, OK]
observed = 1
observedStillFailed = true
```

**Cân nhắc kinh doanh:** fallback có thể được chấp nhận ở hệ thống tìm kiếm gợi ý, nơi một nguồn dữ liệu lỗi không làm hỏng toàn bộ màn hình. Với thanh toán, xác thực hoặc đặt hàng, việc biến lỗi thành dữ liệu “thành công” có thể nguy hiểm. Thiết kế chính sách *all-or-nothing*, *best-effort* hoặc *partial success* trước khi chọn kiểu recovery.

### 10.1. Lỗi ở giai đoạn tạo future

Nếu bạn chạy một hàm có thể ném exception **trước khi** nó trả `CompletableFuture`, `allOf` chưa được gọi và lỗi là **synchronous**. Ví dụ `buildFuture(id)` có thể throw ngay khi kiểm tra input, khác với một future được tạo thành công nhưng về sau completeExceptionally. Với bulk requests, xác định rõ nơi chuyển exceptions synchronous thành `failedFuture` (Java 9+) hoặc báo lỗi ngay cho caller; không giả định mọi exception đều xuất hiện như một future thất bại.

## 11. `join()` và `get()` khác nhau ra sao?

Sau `allOf`, hai phương thức thường dùng:

- `join()`: đợi và lấy giá trị; exception bất đồng bộ thường được chuyển thành **unchecked `CompletionException`** (khi future được hủy trực tiếp còn có thể gặp `CancellationException`).
- `get()`: tuân theo `Future`, đợi và lấy giá trị; có thể ném **checked `InterruptedException`**, **`ExecutionException`**, và `CancellationException` khi bị hủy.
- `get(timeout, unit)`: chỉ giới hạn **thời gian chờ của caller**, ném `TimeoutException` nếu chưa hoàn thành; nó **không mặc định hoàn tất exceptionally/cancel future**.
- `join()` không có overload timeout theo kiểu `get(timeout,unit)`. Có thể tổ hợp với `orTimeout` (Java 9+) nhưng phải hiểu ý nghĩa đột biến trạng thái như mục 12.

Lưu `AllOfGetJoinDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class AllOfGetJoinDemo {
    public static void main(String[] args) {
        CompletableFuture<String> failed =
                CompletableFuture.failedFuture(
                        new IllegalStateException("failure"));

        try {
            failed.join();
            System.out.println("unexpected join");
        } catch (CompletionException e) {
            System.out.println("joinCause = " +
                    e.getCause().getClass().getSimpleName());
        }

        try {
            failed.get();
            System.out.println("unexpected get");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.out.println("interrupted");
        } catch (ExecutionException e) {
            System.out.println("getCause = " +
                    e.getCause().getClass().getSimpleName());
        }
    }
}
```

```bash
javac AllOfGetJoinDemo.java
java AllOfGetJoinDemo
```

```text
joinCause = IllegalStateException
getCause = IllegalStateException
```

Trong code xử lý `InterruptedException`, nên **khôi phục interrupt flag** hoặc truyền exception lên trên theo contract thay vì nuốt mất tín hiệu hủy của thread.

**Đừng** ép mọi exception từ `join` thành `CompletionException`: khi một `CompletableFuture` bị hủy trực tiếp, `join` có thể ném `CancellationException`, một unchecked exception khác.

## 12. Timeout: phân biệt giới hạn chờ và trạng thái tương lai

`CompletableFuture.allOf(...)` không có tham số timeout. Có vài cách quản lý deadline:

1. `all.get(timeout, TimeUnit.MILLISECONDS)`: giới hạn **caller đợi bao lâu**; các future vẫn có thể chạy tiếp, aggregate không tự hoàn tất exceptionally vì timeout này.
2. `all.orTimeout(timeout, unit)` (Java 9+): **hoàn tất exceptionally chính aggregate** nếu hết hạn mà nó chưa xong. Phương thức trả **chính instance đã gọi**, không phải một future độc lập.
3. `child.orTimeout(timeout, unit)`: ảnh hưởng **chính future con** nếu timeout, không mặc định interrupt/hủy tác vụ vật lý phía sau.
4. `completeOnTimeout(value, timeout, unit)` (Java 9+): hoàn tất chính future bằng **fallback value** nếu hết hạn.
5. Với hệ thống thực, timeout client mạng/database, hủy request và giới hạn tài nguyên cần được cấu hình ở **tầng tác vụ** tương ứng, không chỉ ở wrapper `CompletableFuture`.

Lưu `AllOfTimeoutDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class AllOfTimeoutDemo {
    public static void main(String[] args) {
        CompletableFuture<String> slow =
                new CompletableFuture<>();
        CompletableFuture<Void> aggregate =
                CompletableFuture.allOf(slow);

        aggregate.orTimeout(0, TimeUnit.MILLISECONDS);

        try {
            aggregate.join();
            System.out.println("unexpected");
        } catch (CompletionException e) {
            System.out.println("aggregateCause = " +
                    e.getCause().getClass().getSimpleName());
        }

        System.out.println("slowStillPending = " +
                !slow.isDone());

        CompletableFuture<String> separate =
                new CompletableFuture<>();

        try {
            separate.get(0, TimeUnit.MILLISECONDS);
            System.out.println("unexpected get");
        } catch (TimeoutException e) {
            System.out.println("getTimedOut = true");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.out.println("interrupted");
        } catch (java.util.concurrent.ExecutionException e) {
            System.out.println("failed");
        }

        System.out.println("getDidNotCompleteFuture = " +
                !separate.isDone());
    }
}
```

```bash
javac AllOfTimeoutDemo.java
java AllOfTimeoutDemo
```

```text
aggregateCause = TimeoutException
slowStillPending = true
getTimedOut = true
getDidNotCompleteFuture = true
```

`orTimeout(0, ...)` trong ví dụ được dùng để tạo timeout xác định, không phải một benchmark độ chính xác bộ hẹn giờ. Quan trọng nhất: aggregate đã thất bại vì timeout nhưng `slow` **vẫn pending**. Nếu nó thực sự đại diện cho một lệnh I/O, ứng dụng cần có cơ chế kiểm soát I/O đó riêng.

**Tránh sai lầm:** gọi `allOf(...).orTimeout(...).exceptionally(... )` rồi coi như toàn bộ tác vụ đã ngừng tiêu thụ CPU, thread hoặc connection. Timeout của stage không đồng nghĩa đóng socket/cancel database query.

### 12.1. Timeout tổng và timeout từng task

Có hai contract khác nhau:

- **Deadline tổng:** “Toàn bộ report phải hoàn tất trong 2 giây” → timeout ở aggregate.
- **Deadline thành phần:** “Mỗi dịch vụ có tối đa 400 ms” → timeout hoặc deadline riêng cho từng future/request.

Khi một vài task timeout nhưng sản phẩm vẫn muốn partial success, có thể chuyển exception/timeout mỗi task thành `Outcome` bằng `handle` rồi dùng `allOf` trên các outcome. Cần tính toán tổng ngân sách request: không nên chờ từng future tuần tự với mỗi timeout đầy đủ vì có thể vượt deadline tổng.

## 13. Cancellation: hủy aggregate không có nghĩa hủy mọi task

`CompletableFuture.cancel(boolean)` không phải một giao thức ngắt thread chắc chắn. Theo Javadoc `CompletableFuture`, `mayInterruptIfRunning` **không có hiệu lực** đối với implementation này vì interrupt không dùng để điều khiển quá trình xử lý của nó. Cancellation là một dạng completion exceptional bằng `CancellationException`.

Đặc biệt:

- `allOf(a,b).cancel(true)` chuyển **aggregate** sang trạng thái canceled (nếu trước đó chưa hoàn tất).
- Nó **không tự gọi cancel** trên `a` và `b`.
- Nếu một future con bị hủy, aggregate có thể hoàn tất exceptionally sau khi các future khác cũng xong.
- Muốn hủy tác vụ thực tế, phải biết task, executor, network client hoặc cancellation token có hỗ trợ gì. Việc chỉ hủy `CompletableFuture` không phải lúc nào cũng dừng work đã bắt đầu.

Lưu `AllOfCancellationDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AllOfCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<String> first =
                new CompletableFuture<>();
        CompletableFuture<String> second =
                new CompletableFuture<>();

        CompletableFuture<Void> aggregate =
                CompletableFuture.allOf(first, second);

        System.out.println("cancelAggregate = " +
                aggregate.cancel(true));
        System.out.println("childrenCancelled = " +
                first.isCancelled() + "," +
                second.isCancelled());

        first.complete("A");
        second.complete("B");

        System.out.println("childrenValues = " +
                first.join() + "," + second.join());
        System.out.println("aggregateCancelled = " +
                aggregate.isCancelled());

        CompletableFuture<String> child =
                new CompletableFuture<>();
        CompletableFuture<String> sibling =
                CompletableFuture.completedFuture("OK");
        CompletableFuture<Void> secondAggregate =
                CompletableFuture.allOf(child, sibling);

        child.cancel(false);

        try {
            secondAggregate.join();
            System.out.println("unexpected");
        } catch (CompletionException e) {
            System.out.println("childCancelCause = " +
                    e.getCause().getClass().getSimpleName());
        }

        try {
            aggregate.join();
            System.out.println("unexpected aggregate join");
        } catch (CancellationException e) {
            System.out.println("directCancelThrows = " +
                    e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac AllOfCancellationDemo.java
java AllOfCancellationDemo
```

```text
cancelAggregate = true
childrenCancelled = false,false
childrenValues = A,B
aggregateCancelled = true
childCancelCause = CancellationException
directCancelThrows = CancellationException
```

Với bulk workflow cần ngừng thực sự, thường phải truyền cancellation/deadline xuống các API I/O hoặc tác vụ và có chính sách thu hồi tài nguyên. Không đưa ra bảo đảm “cancel(true) ngắt mọi supplier đã bắt đầu” nếu ứng dụng chỉ đang dùng `CompletableFuture`.

## 14. Tập rỗng, phần tử null và kết quả null

Ba trường hợp dễ bị nhầm:

**Tập đầu vào rỗng:** `CompletableFuture.allOf()` trả future đã hoàn tất bình thường, `join()` trả `null`. Điều này thuận tiện cho hàm `sequence(emptyList)` trả một danh sách rỗng.

**Future đầu vào null:** `allOf` không chấp nhận mảng null hoặc phần tử null. Lỗi `NullPointerException` xuất hiện ngay khi gọi, thay vì một future được hoàn tất exceptionally ở tương lai.

**Future thành công với giá trị null:** `CompletableFuture.completedFuture(null)` hoàn toàn hợp lệ. Một future có giá trị `null` vẫn được xem là **thành công**, và `allOf` không ném exception chỉ vì giá trị là null.

Lưu `AllOfEdgeCasesDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfEdgeCasesDemo {
    public static void main(String[] args) {
        CompletableFuture<Void> empty =
                CompletableFuture.allOf();

        System.out.println("emptyDone = " + empty.isDone());
        System.out.println("emptyValueNull = " +
                (empty.join() == null));

        CompletableFuture<String> missingValue =
                CompletableFuture.completedFuture(null);
        CompletableFuture<String> present =
                CompletableFuture.completedFuture("OK");

        CompletableFuture.allOf(
                missingValue, present).join();

        List<String> results = List.of(
                missingValue, present).stream()
                .map(CompletableFuture::join)
                .toList();

        System.out.println("results = " + results);
        System.out.println("firstIsNull = " +
                (results.get(0) == null));

        try {
            CompletableFuture.allOf(
                    present, (CompletableFuture<?>) null);
            System.out.println("unexpected null future");
        } catch (NullPointerException e) {
            System.out.println("nullFutureRejected = true");
        }

        try {
            List.copyOf(results);
            System.out.println("unexpected copy");
        } catch (NullPointerException e) {
            System.out.println("copyOfRejectsNull = true");
        }
    }
}
```

```bash
javac AllOfEdgeCasesDemo.java
java AllOfEdgeCasesDemo
```

```text
emptyDone = true
emptyValueNull = true
results = [null, OK]
firstIsNull = true
nullFutureRejected = true
copyOfRejectsNull = true
```

**Không dùng `result == null` để phân loại task thất bại.** Trạng thái failure là exceptional completion; một thành công có thể có giá trị null. Nếu domain không chấp nhận null, hãy kiểm tra trước khi tạo giá trị cuối và gắn lỗi domain rõ ràng.

Một caveat khác: `CompletableFuture.anyOf()` với **không đầu vào** trả future **chưa hoàn tất**, trái với `allOf()` rỗng; không gọi `join` trên đó nếu không có future nào khác có khả năng complete.

## 15. Khống chế độ đồng thời khi N lớn: allOf không tạo backpressure

Một mẫu có vẻ đơn giản:

```java
List<CompletableFuture<Response>> futures = ids.stream()
        .map(id -> CompletableFuture.supplyAsync(
                () -> fetch(id), executor))
        .toList();
CompletableFuture.allOf(
        futures.toArray(new CompletableFuture<?>[0])).join();
```

*Snippet cần `Response`, `fetch`, `ids` và `executor` của ứng dụng; không độc lập.*

Nếu `ids` chứa 100.000 phần tử, việc tạo 100.000 future và gửi công việc quá nhanh có thể làm đầy queue, tăng bộ nhớ, gây quá tải downstream hoặc cạn connection. **`allOf` không cung cấp giới hạn concurrency hay backpressure.**

Các chiến lược thực tế:

- Chia thành các **batch** cỡ giới hạn, đợi mỗi batch xong rồi mới khởi tạo batch kế tiếp.
- Giới hạn task bằng **bounded executor/queue** hoặc semaphore có cơ chế cấp phép và giải phóng chuẩn.
- Dùng API client bất đồng bộ có connection pool, rate limit và timeout thích hợp.
- Nếu cần dữ liệu theo stream không bị dồn vào RAM, xem xét mô hình publisher/subscriber thay vì tạo một collection khổng lồ trước.
- Kiểm tra policy lỗi: một batch thất bại có được dừng các batch sau hay tiếp tục tạo outcomes?

Lưu `AllOfBatchingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AllOfBatchingDemo {
    public static void main(String[] args) {
        ExecutorService executor =
                Executors.newFixedThreadPool(2);

        try {
            List<Integer> work = List.of(1, 2, 3, 4, 5);
            int batchSize = 2;

            CompletableFuture<List<Integer>> chain =
                    CompletableFuture.completedFuture(List.of());

            for (int from = 0; from < work.size();
                 from += batchSize) {

                List<Integer> batch = List.copyOf(
                        work.subList(
                                from,
                                Math.min(from + batchSize,
                                        work.size())));

                chain = chain.thenCompose(previous -> {
                    List<CompletableFuture<Integer>> active =
                            batch.stream()
                            .map(n -> CompletableFuture.supplyAsync(
                                    () -> n * n, executor))
                            .toList();

                    return CompletableFuture.allOf(
                            active.toArray(
                                    new CompletableFuture<?>[0]))
                            .thenApply(ignored -> {
                                List<Integer> next =
                                        new ArrayList<>(previous);
                                active.forEach(f ->
                                        next.add(f.join()));
                                return List.copyOf(next);
                            });
                });
            }

            System.out.println("squares = " +
                    chain.join());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac AllOfBatchingDemo.java
java AllOfBatchingDemo
```

```text
squares = [1, 4, 9, 16, 25]
```

Trong ví dụ, một batch có tối đa hai future vừa được tạo; batch tiếp theo chỉ được khởi tạo sau khi batch trước hoàn tất. Executor hai thread là **một lớp giới hạn bổ sung**, nhưng việc kiểm soát queue/connection thực tế còn tùy công việc downstream.

Đây là ví dụ học thuật dùng phép nhân đơn giản, không phải thư viện batching tổng quát. Nếu một future trong batch thất bại, `chain` sẽ thất bại và các batch tiếp theo **không được tạo** bởi `thenCompose`. Nếu yêu cầu “tiếp tục best-effort”, cần kết hợp `handle`/`Outcome` để chính sách lỗi không tự dừng mọi batch.

### 15.1. Tránh thread starvation và deadlock tự tạo

Ví dụ sai về thiết kế: tạo một task **trong chính executor một thread**, rồi task ấy gọi `join` chờ các task khác **cũng phải chạy trong executor đó**, trong khi thread duy nhất đã bị chặn. Khi queue không có thread rảnh, chương trình có thể bị treo.

Hãy **ghép dependency bằng `thenApply`, `thenCompose` và `allOf`** thay vì gửi một tác vụ chỉ để ngồi đợi chặn cùng executor. `join` ở phía sau một barrier đã hoàn tất bình thường là đọc kết quả, không chờ. Tách callback CPU nặng khỏi thread hoàn tất I/O bằng executor thích hợp nếu cần.

Các callback **không có hậu tố Async** như `thenApply` có thể chạy trên thread vừa hoàn tất stage hoặc thread khác gọi phương thức hoàn tất theo contract. Không được giả định chúng tự chạy ở một worker thread chuyên dụng.

## 16. Kiểm thử thứ tự hoàn tất bằng future được điều khiển thủ công

Unit test bất đồng bộ không nên lệ thuộc `Thread.sleep(100)` rồi hy vọng các thread hoàn thành theo thứ tự mong muốn. Dùng `CompletableFuture` chưa hoàn tất và gọi `complete` theo **thứ tự test tự điều khiển**.

Lưu `AllOfDeterministicTestDemo.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfDeterministicTestDemo {
    public static void main(String[] args) {
        CompletableFuture<String> a = new CompletableFuture<>();
        CompletableFuture<String> b = new CompletableFuture<>();
        CompletableFuture<String> c = new CompletableFuture<>();

        CompletableFuture<List<String>> combined =
                CompletableFuture.allOf(a, b, c)
                .thenApply(ignored ->
                        List.of(a.join(), b.join(), c.join()));

        c.complete("C");
        System.out.println("afterC = " + combined.isDone());

        a.complete("A");
        System.out.println("afterA = " + combined.isDone());

        b.complete("B");
        System.out.println("afterB = " + combined.isDone());

        System.out.println("resultOrder = " +
                combined.join());
    }
}
```

```bash
javac AllOfDeterministicTestDemo.java
java AllOfDeterministicTestDemo
```

```text
afterC = false
afterA = false
afterB = true
resultOrder = [A, B, C]
```

Dù completion order là **C → A → B**, kết quả vẫn **A → B → C** theo thứ tự input. Test cũng xác minh aggregate chưa hoàn tất khi chỉ có một hoặc hai future hoàn tất.

Có thể mở rộng test bằng `completeExceptionally` để xác minh hành vi lỗi, bằng `cancel` để kiểm tra aggregate và child, và bằng `get(timeout)`/`orTimeout(0)` để kiểm tra deadline **không cần sleep**. Với business logic, đừng dừng ở test `isDone`; hãy assert kết quả, loại exception, ID task và policy partial success.

## 17. So sánh với `anyOf`, `thenCombine` và `thenCompose`

| API | Quan hệ giữa các tác vụ | Giá trị kết quả | Khi nên dùng |
| --- | --- | --- | --- |
| `allOf(f1, ..., fn)` | Đợi **tất cả hoàn tất** | `CompletableFuture<Void>` | Barrier nhiều tác vụ độc lập |
| `anyOf(f1, ..., fn)` | Hoàn tất khi **một** input hoàn tất, có thể là lỗi | `CompletableFuture<Object>` | Lấy kết quả đầu tiên hoàn tất theo contract, không đồng nghĩa “thành công đầu tiên” |
| `f1.thenCombine(f2, fn)` | Chờ **hai** tác vụ thành công | `CompletableFuture<R>` | Kết hợp hai giá trị có kiểu |
| `f1.thenCompose(value -> f2(value))` | Tác vụ sau **phụ thuộc** kết quả trước | `CompletableFuture<R>` | Chuỗi dependent operations |
| `f.thenApply(fn)` | Biến đổi kết quả của một stage | `CompletableFuture<R>` | Mapping sau allOf hoặc future đơn |
| `f.handle(fn)` | Quan sát cả thành công và lỗi rồi tạo kết quả mới | `CompletableFuture<R>` | Thu outcomes, policy lỗi |
| `f.exceptionally(fn)` | Tạo giá trị thay thế khi lỗi | `CompletableFuture<T>` | Fallback khi được phép |

**Đừng nhầm `anyOf` với “future đầu tiên thành công”**: một future thất bại sớm có thể làm `anyOf` thất bại theo ngay kết quả đó, kể cả những future còn lại về sau thành công. `anyOf` cũng không tự cancel các future chưa xong.

**Đừng dùng `allOf` để chạy các nhánh có dependency thực sự**. Nếu B cần dữ liệu từ A, bắt đầu B trước khi A hoàn tất có thể sai logic hoặc lãng phí. Dùng `thenCompose` khi B phụ thuộc A, và chỉ dùng `allOf` cho những nhánh độc lập hoặc đã được dựng hợp lệ.

### 17.1. Khi nào không cần `allOf`?

Nếu `userFuture` và `rolesFuture` là hai nhánh cố định, `thenCombine` có thể ngắn và an toàn về kiểu hơn `allOf`. Nếu chỉ có **một future**, `thenApply` có thể biến đổi thẳng giá trị. Nếu cần xử lý từng kết quả khi đến mà không đợi tất cả, dùng callback/stream/queue phù hợp. `allOf` phát huy ưu điểm khi cần một **hàng rào kết thúc chung** và danh sách N tác vụ có thể động.

## 18. Hàm thu kết quả dùng trong ứng dụng: chọn contract đúng

Trước khi viết helper `sequence(...)` cho dự án thực, xác định:

**Input:**
- Danh sách future có thể rỗng không?
- Có chấp nhận phần tử future null không? Thường nên từ chối sớm.
- Danh sách có thể bị sửa trong khi pipeline chưa hoàn tất không? Nên snapshot.
- Có cần giữ thứ tự đầu vào hay thứ tự hoàn tất?

**Output:**
- List kết quả có thể chứa `null` không?
- List có cần bất biến? `Stream.toList()` trả unmodifiable list.
- Lỗi của một future làm thất bại toàn bộ hay vẫn trả partial success?
- Có cần giữ key/id gốc để đối chiếu lỗi?

**Thời gian và tài nguyên:**
- Timeout tổng hay từng task?
- Có hủy công việc thực khi caller ngừng đợi không?
- Bao nhiêu task được tạo cùng lúc?
- Executor và client I/O có giới hạn queue/rate/connection không?

**Quan sát và test:**
- Có trace ID và trạng thái cho từng task?
- Có test exception từ supplier, exception từ callback và cancellation?
- Có kiểm tra input empty, null value, duplicate IDs và trường hợp nhiều lỗi?
- Có đo latency của batch theo đơn vị phù hợp mà không tự in stdout thay đổi?

Đây là một phần quan trọng của thiết kế bất đồng bộ. “Thu kết quả nhiều future” không chỉ là một câu lệnh `toList()`: nó là contract về **all-or-nothing**, **partial success**, **deadline**, **ordering** và **tài nguyên**.

## 19. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Nghĩ `allOf` trả `List<T>` | Signature trả `CompletableFuture<Void>` | Tạo `thenApply`/helper sequence |
| Gọi `allOf(...).join()` rồi giả định không thể lỗi | Future con có thể hoàn tất exceptionally | Bắt exception hoặc normalize bằng `handle` |
| Đọc kết quả từng future từ callback trước barrier | `join` có thể chặn nếu future chưa xong | Chờ barrier hoặc ghép stage |
| Nghĩ allOf thất bại ⇒ các sibling đã bị cancel | Không có tự động cancellation | Quản lý task và cancellation riêng |
| Nghĩ allOf fail-fast khi task đầu lỗi | Aggregate hoàn tất khi các input đều hoàn tất | Nếu cần fail-fast phải thiết kế khác |
| Chỉ xem cause của allOf để thu **mọi** lỗi | Aggregate chỉ mang một exceptional cause | `handle` từng future thành Outcome |
| Đưa `null` vào mảng future | `allOf` ném NPE | Validate input |
| Coi result `null` là thất bại | Null value vẫn có thể là successful completion | Phân biệt bằng trạng thái/error |
| Giả định completion order = result order | List stream duyệt theo input order | Giữ index/id hoặc dùng thứ tự theo contract |
| Gọi `List.copyOf` với kết quả có null | Ném `NullPointerException` | Loại null hoặc dùng List cho phép null |
| Nghĩ `orTimeout` dừng task I/O | Chỉ complete future theo timeout policy | Hủy/timeout tầng I/O thật |
| Nghĩ `get(timeout)` làm future fail | Chỉ giới hạn caller chờ | Phân biệt get vs orTimeout |
| Dùng `cancel(true)` để chắc chắn interrupt supplier | `CompletableFuture` không dùng interrupt để control | Cancellation token/client contract riêng |
| Dùng `exceptionally` làm fallback trong nghiệp vụ cấm fallback | Biến lỗi thành thành công giả | Chọn policy domain |
| In stdout từ mỗi thread rồi khẳng định thứ tự | Thread scheduler không xác định | Chỉ in sau collect hoặc test theo ID |
| Đưa quá nhiều task vào commonPool không giới hạn | Có thể gây quá tải/queue/memory | Executor/batch/backpressure |
| Block `join` trong worker duy nhất cần chạy các task đó | Starvation hoặc deadlock | Compose stage, tách executors |
| Dùng API Java 16/9 nhưng gọi là Java 8 thuần túy | Không có `Stream.toList`/`failedFuture`/`orTimeout` trên Java 8 | Ghi version và dùng API tương đương nếu cần |

## 20. Bài tập thực hành

**Bài 1 — Thu kết quả theo thứ tự input.** Tạo ba `CompletableFuture<Integer>` cho các số `4, 2, 3`. Giải thích vì sao sau `allOf` và `stream().map(join)` kết quả theo đúng thứ tự input, kể cả nếu future thứ ba hoàn tất trước.

**Bài 2 — Viết helper typed.** Tạo `static <T> CompletableFuture<List<T>> sequence(List<CompletableFuture<T>> input)`. Kiểm tra khi danh sách rỗng, khi cả ba thành công và khi một future thất bại.

**Bài 3 — Partial success.** Một batch có ba future; thứ hai thất bại. Thu hai giá trị thành công và thông tin lỗi của future thứ hai mà **không** làm stage aggregate cuối cùng thất bại. Hãy dùng `handle`/`Outcome`.

**Bài 4 — Timeout/cancellation.** Tạo một future chưa complete và bọc trong `allOf`. Dùng `orTimeout(0, TimeUnit.MILLISECONDS)`. Kiểm tra future con vẫn pending. Giải thích cách xử lý nếu tương ứng một HTTP request đang mở.

**Bài 5 — Giới hạn concurrent work.** Có 5 công việc, chỉ muốn tạo tối đa 2 tác vụ đang hoạt động trong một batch. Dùng các batch 2, 2, 1 và `thenCompose`. Giải thích cách xử lý nếu một batch thất bại.

**Bài 6 — Không trộn `allOf` và `thenCompose`.** Có hai công việc A và B độc lập, còn C phải dùng kết quả A. Thiết kế pipeline để B chạy song song với A, C chỉ bắt đầu sau A, và chỉ trả report khi cả B và C xong.

### 20.1. Lời giải chạy được cho bài 1

Lưu `AllOfPractice.java`:

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfPractice {
    public static void main(String[] args) {
        CompletableFuture<Integer> first =
                new CompletableFuture<>();
        CompletableFuture<Integer> second =
                new CompletableFuture<>();
        CompletableFuture<Integer> third =
                new CompletableFuture<>();

        List<CompletableFuture<Integer>> futures =
                List.of(first, second, third);

        CompletableFuture<List<Integer>> sum =
                CompletableFuture.allOf(
                        futures.toArray(
                                new CompletableFuture<?>[0]))
                .thenApply(ignored -> futures.stream()
                        .map(CompletableFuture::join)
                        .toList());

        third.complete(9);
        first.complete(16);
        second.complete(4);

        List<Integer> results = sum.join();

        System.out.println("ordered = " + results);
        System.out.println("total = " +
                results.stream().mapToInt(Integer::intValue)
                        .sum());
    }
}
```

```bash
javac AllOfPractice.java
java AllOfPractice
```

```text
ordered = [16, 4, 9]
total = 29
```

Ở bài này completion order là **third → first → second**, còn output order là **first → second → third**. Lời giải bài 2 xem `AllOfSequenceDemo`; bài 3 xem `AllOfOutcomesDemo`; bài 4 xem `AllOfTimeoutDemo`; bài 5 xem `AllOfBatchingDemo`. Với bài 6, dùng `c = a.thenCompose(...)`, sau đó `CompletableFuture.allOf(b, c).thenApply(...)` hoặc `b.thenCombine(c, ...)` để ghép hai nhánh đã thành công.

## 21. Checklist trước khi đưa vào production

- Tôi có thật sự cần **đợi tất cả** hay cần kết quả **đầu tiên** hoặc ghép hai stage?
- Các future đã được tạo/khởi chạy đúng cách trước khi gọi `allOf` chưa?
- Tôi biết `allOf` trả `CompletableFuture<Void>`, không phải danh sách không?
- Nếu cần `List<T>`, đã dùng `thenApply` sau barrier và giữ đúng thứ tự input?
- Các future có kiểu khác nhau thì đã tạo DTO/record typed thay vì cast thủ công?
- Nếu future con lỗi, policy **all-or-nothing** hay **partial success** đã được mô tả?
- Nếu cần mọi lỗi, đã chuyển từng future qua `handle` thành outcome riêng?
- Có trường hợp future con hoàn tất thành công với `null`? Đã phân biệt với lỗi?
- Đầu vào có thể rỗng hoặc chứa future null? Đã test?
- Có biết `join`/`get` dùng loại exception khác nhau? Có xử lý interrupt đúng?
- Deadline có ở aggregate, task, client I/O hay cả ba? Timeout có được áp đặt đúng tầng?
- Có cần hủy công việc thật? Đã hiểu `cancel(true)` của CompletableFuture không bảo đảm interrupt?
- Có giới hạn N future chạy đồng thời/bounded executor để tránh làm quá tải downstream?
- Có tránh chặn thread trong chính executor cần chạy các công việc đang chờ?
- Có giữ identifier/index của task để đối chiếu kết quả và lỗi, thay vì chỉ so vị trí vô danh?
- Test có mô phỏng completion và failure bằng future điều khiển thủ công thay vì sleep?
- Các API sau Java 8 như `Stream.toList`, `failedFuture`, `orTimeout` đã ghi rõ yêu cầu Java 17+ của ví dụ?
- Nếu callback trong `thenApply`/`handle` nặng hoặc có I/O, đã cân nhắc executor rõ ràng?

## 22. Tài liệu Oracle Java hiện hành

- Java SE 26 — `CompletableFuture`, `allOf`, `anyOf`, `join`, `get`, `orTimeout`, `cancel`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Java SE 26 — `CompletionStage`, `thenApply`, `thenCombine`, `thenCompose`, `handle` và `whenComplete`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html
- Java SE 26 — `Future`, `get`, timeout và interruption: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 26 — `ExecutorService` và quản lý vòng đời executor: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 26 — `TimeUnit`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/TimeUnit.html
- Java SE 26 — `Stream`/`toList`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html
- Java SE 26 — `CompletionException`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionException.html

**Kết luận:** `CompletableFuture.allOf` là **barrier chờ tất cả future**, không phải hàm trả `List<T>`. Để lấy tất cả giá trị, kết hợp `allOf(...).thenApply(...)` với `join()` của từng future, hoặc xây helper `sequence`. Nếu cần partial success, dùng `handle` chuyển từng future thành outcome; nếu cần timeout/hủy, quản lý đúng tầng và không ngầm suy ra task đã bị dừng. Với nhiều công việc, giới hạn concurrency và giữ thứ tự/ID đầu vào quan trọng không kém câu lệnh thu kết quả.