# Fan-out / fan-in và tổng hợp kết quả trong Java Concurrency

**Fan-out / fan-in** là mô hình thiết kế đồng thời gồm hai pha: **fan-out** tách một công việc thành nhiều tác vụ có thể chạy độc lập; **fan-in** chờ hoặc phối hợp các kết quả và tạo đầu ra chung. Trong Java, mô hình này có thể được xây dựng bằng `ExecutorService`, `Future`, `CompletionService` và `CompletableFuture`. Mục tiêu là tận dụng thời gian chờ I/O hoặc năng lực xử lý song song **khi các tác vụ thật sự có thể chạy đồng thời**, đồng thời giữ được tính đúng đắn khi có lỗi, timeout, hủy và áp lực tài nguyên.

Ví dụ: một chương trình cần tính giá từ ba nguồn độc lập. Fan-out gửi ba tác vụ lấy giá; fan-in ghép kết quả theo thứ tự nguồn rồi tính tổng hoặc ra quyết định. Ba tác vụ có thể kết thúc theo thứ tự khác thứ tự gửi, nhưng **quy tắc tổng hợp do chương trình quyết định**, không nên phụ thuộc ngẫu nhiên vào lịch chạy thread.

Bài này chỉ xét **concurrency trong Java**, không gắn với framework cụ thể.

## 1. Fan-out và fan-in là hai trách nhiệm khác nhau

```text
                       ┌── Task A ── Result A ──┐
Input / Request ───────┼── Task B ── Result B ──┼── Aggregate ── Output
                       └── Task C ── Result C ──┘
               fan-out                         fan-in
```

Ở pha **fan-out**, cần xác định:
- Những phần việc nào **độc lập về dữ liệu và thứ tự**? Nếu B cần output của A thì B phụ thuộc A, không thể coi là một nhánh chạy song song hoàn toàn.
- Mỗi tác vụ cần đầu vào riêng gì? Có dùng dữ liệu mutable chung không?
- Tối đa được chạy bao nhiêu tác vụ cùng lúc? Executor, connection pool, CPU, API giới hạn tốc độ và bộ nhớ đều có thể là nút thắt.
- Khi người gọi hủy hay hết hạn, tác vụ còn cần tiếp tục không?

Ở pha **fan-in**, cần xác định:
- **All-or-nothing:** thiếu một kết quả thì cả phép tổng hợp thất bại.
- **Partial success:** lấy mọi kết quả thành công, đồng thời trả về lỗi của từng nhánh.
- **First result / quorum:** chỉ cần kết quả đầu tiên hoặc đủ một số kết quả hợp lệ; đây là chính sách khác với “đợi tất cả”.
- **Thứ tự:** giữ thứ tự đầu vào, sắp xếp theo một khóa nghiệp vụ, hay xử lý theo thứ tự hoàn thành?
- **Thời hạn:** là timeout cho từng nhánh, cho lần chờ, hay một **deadline chung** cho toàn bộ yêu cầu?

Một thiết kế tốt phải nêu rõ **hợp đồng tổng hợp** trước khi chọn API. Không nên chạy đồng thời rồi chỉ gọi `join()` trên bất kỳ future nào có sẵn mà chưa quyết định cách xử lý thất bại.

### Độ trễ kỳ vọng và giới hạn thực tế

Nếu ba nhánh độc lập có thời gian lần lượt là 100 ms, 180 ms và 250 ms, chạy tuần tự mất xấp xỉ 530 ms (chưa kể overhead). Nếu đủ tài nguyên để thực thi đồng thời và fan-in cần tất cả, độ trễ lý tưởng xấp xỉ **250 ms cộng chi phí lập lịch/tổng hợp**, vì phải chờ nhánh chậm nhất. Đây chỉ là mô hình minh họa: tài nguyên tranh chấp, I/O, CPU, hàng đợi executor và biến động mạng có thể khiến kết quả khác nhiều.

**Concurrency không mặc nhiên giúp chương trình nhanh hơn.** Nếu các tác vụ là CPU-bound, số lõi CPU giới hạn mức song song hữu ích. Nếu các tác vụ đều gọi một dịch vụ có connection pool nhỏ, fan-out lớn chỉ làm hàng đợi tại pool dài hơn.

## 2. Chọn cơ chế fan-out / fan-in của Java

| Cơ chế | Phù hợp khi | Cách thu kết quả | Lưu ý |
|---|---|---|---|
| `ExecutorService.submit` + `Future.get` | Muốn kiểm soát tác vụ, executor và hủy | Gọi `get()` lần lượt trên danh sách future | Các tác vụ đã submit vẫn chạy đồng thời; việc chờ theo danh sách có thể làm chậm xử lý kết quả hoàn thành sớm |
| `ExecutorService.invokeAll` | Có sẵn tập `Callable`, cần đợi cả nhóm | Trả danh sách `Future` theo **thứ tự input** | `invokeAll` chờ nhóm hoàn thành, không đồng nghĩa mọi kết quả đều thành công; từng `get()` có thể ném lỗi |
| `ExecutorCompletionService` | Muốn xử lý kết quả theo **thứ tự hoàn thành** | `take()`/`poll()` nhận future đã hoàn thành | `take()` có thể chờ; `get()` trên future nhận được vẫn có thể ném lỗi |
| `CompletableFuture.allOf` | Đợi **tất cả** các future | Lấy kết quả riêng sau khi `allOf` hoàn tất | Future tổng hợp trả `Void`; lỗi của các nhánh không được liệt kê đầy đủ tự động |
| `CompletableFuture.thenCombine` | Ghép **hai** công việc độc lập | Nhận cả hai giá trị để tổng hợp | Có thể nối nhiều cặp; với N nhánh thường dùng `allOf` |
| `CompletableFuture.anyOf` | Muốn quan sát **một nhánh hoàn thành đầu tiên** | Trả `Object` hoặc lỗi của nhánh hoàn thành | **Không phải** “kết quả thành công đầu tiên”; nhánh đầu tiên cũng có thể thất bại |
| `handle`, `exceptionally` | Muốn biến lỗi nhánh thành kết quả/fallback | Tạo stage có chính sách phục hồi rõ ràng | Phải phân biệt lỗi được xử lý và lỗi vẫn phải trả cho caller |

`CompletableFuture.supplyAsync(supplier)` mặc định thường dùng `ForkJoinPool.commonPool()` nếu không truyền `Executor` (trừ tình huống đặc biệt của runtime). Trong ví dụ thực hành, truyền executor tường minh để phân biệt nơi tác vụ chạy với nơi tập hợp kết quả, và để kiểm soát mức độ song song.

## 3. Ví dụ đầy đủ: fan-out ba phép tính, fan-in giữ thứ tự đầu vào

Lưu thành **`FanOutFanInDemo.java`** (Java 17+):

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FanOutFanInDemo {
    public static void main(String[] args) {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            List<Integer> inputs = List.of(3, 5, 7);

            // FAN-OUT: tạo cả ba tác vụ trước khi chờ.
            List<CompletableFuture<Integer>> tasks = inputs.stream()
                    .map(n -> CompletableFuture.supplyAsync(
                            () -> n * n, executor))
                    .toList();

            CompletableFuture<?>[] allTasks =
                    tasks.toArray(new CompletableFuture<?>[0]);

            // FAN-IN: chờ cả nhóm, sau đó đọc kết quả theo thứ tự input.
            CompletableFuture<List<Integer>> results =
                    CompletableFuture.allOf(allTasks)
                            .thenApply(ignored -> tasks.stream()
                                    .map(CompletableFuture::join)
                                    .toList());

            List<Integer> values = results.join();
            int sum = values.stream().mapToInt(Integer::intValue).sum();

            System.out.println("Results: " + values);
            System.out.println("Sum: " + sum);
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy:

```bash
javac FanOutFanInDemo.java
java FanOutFanInDemo
```

Kết quả chính xác:

```text
Results: [9, 25, 49]
Sum: 83
```

**Giải thích:**
1. `supplyAsync(..., executor)` lập lịch ba phép tính độc lập trên executor. Việc tạo cả ba future **trước** khi đợi giúp chúng có cơ hội chạy đồng thời.
2. `allOf(allTasks)` trả một `CompletableFuture<Void>`: nó hoàn thành sau khi tất cả future thành phần đã hoàn thành. Bản thân `allOf` **không gom một `List<Integer>`**.
3. `thenApply` chỉ chạy khi `allOf` hoàn thành **bình thường**; lúc đó `join()` trên từng `tasks` không còn phải đợi. Danh sách kết quả đi theo thứ tự của `inputs`, dù thứ tự tác vụ thực thi/hoàn thành có thể khác.
4. `executor.shutdown()` chỉ dừng nhận công việc mới và cho tác vụ đã submit tiếp tục; ở đường chạy bình thường, việc đợi `results.join()` đã bảo đảm các tác vụ cần thiết hoàn tất.

Ví dụ dùng `newFixedThreadPool(3)` để thấy ba tác vụ được thực thi bằng tối đa ba worker threads. Trong hệ thống thực, số worker phải dựa vào loại công việc và tài nguyên, không mặc định “cứ N nhánh thì mở N platform threads”.

### Lỗi thường gặp: vô tình biến fan-out thành tuần tự

Sai về ý đồ song song:

```java
for (int n : inputs) {
    int result = CompletableFuture
            .supplyAsync(() -> expensiveWork(n), executor)
            .join(); // Chờ ngay sau mỗi lần submit.
    consume(result);
}
```

Đây là **snippet** dùng các biến/hàm đã có, không phải chương trình độc lập. Vì mỗi vòng đợi xong mới submit vòng sau, các tác vụ không cùng tiến hành. Đúng hơn là tạo danh sách future trước, sau đó xây nhánh fan-in hoặc `allOf`.

## 4. Ghép hai nhánh trực tiếp bằng thenCombine

Khi có đúng hai nguồn độc lập, `thenCombine` biểu diễn quan hệ hợp nhất gọn hơn `allOf`:

```java
CompletableFuture<Integer> price =
        CompletableFuture.supplyAsync(() -> 100, executor);
CompletableFuture<Integer> tax =
        CompletableFuture.supplyAsync(() -> 10, executor);

CompletableFuture<Integer> total =
        price.thenCombine(tax, Integer::sum);

System.out.println(total.join()); // 110
```

Đây là snippet trong một method có `executor` phù hợp và import `CompletableFuture`. Hàm kết hợp chỉ chạy khi **cả hai** nhánh hoàn thành bình thường. Nếu một nhánh thất bại thì future kết hợp sẽ hoàn thành ngoại lệ; muốn fallback phải quyết định chính sách xử lý lỗi.

**Phân biệt `thenCombine` và `thenCompose`:** `thenCombine` kết hợp **hai tương lai độc lập**. `thenCompose` nối tác vụ B phụ thuộc giá trị tương lai của A, tức một chuỗi có quan hệ dữ liệu; không nên gọi phần phụ thuộc này là fan-out độc lập.

## 5. Thu kết quả theo thứ tự hoàn thành với CompletionService

Một tác vụ hoàn thành sớm có thể được xử lý ngay, không cần chờ future nằm trước nó trong danh sách. `ExecutorCompletionService` nhận `Callable<T>` và đưa **future đã hoàn thành** vào hàng đợi; `take()` nhận phần tử hoàn thành tiếp theo. Thứ tự có thể thay đổi mỗi lần chạy.

Ví dụ đầy đủ, kết quả tổng không phụ thuộc thứ tự hoàn thành. Lưu thành **`CompletionOrderDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class CompletionOrderDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService executor = Executors.newFixedThreadPool(3);
        try {
            List<Callable<Integer>> jobs = List.of(
                    () -> 40,
                    () -> 2,
                    () -> 7
            );

            ExecutorCompletionService<Integer> completions =
                    new ExecutorCompletionService<>(executor);

            for (Callable<Integer> job : jobs) {
                completions.submit(job);
            }

            int sum = 0;
            for (int i = 0; i < jobs.size(); i++) {
                // take() đợi một Future đã hoàn thành.
                sum += completions.take().get();
            }

            System.out.println("Sum: " + sum);
        } finally {
            executor.shutdown();
        }
    }
}
```

Chạy:

```bash
javac CompletionOrderDemo.java
java CompletionOrderDemo
```

Kết quả:

```text
Sum: 49
```

Đặc điểm cần nhớ:
- `take()` lấy tương lai theo **thứ tự hoàn thành**, không theo thứ tự gửi.
- `take()` có thể ném `InterruptedException` khi thread đang đợi bị interrupt.
- `take().get()` vẫn có thể ném `ExecutionException` do lỗi của tác vụ, hoặc `CancellationException` nếu future bị hủy. Bản thân “đã hoàn thành” **không đồng nghĩa thành công**.
- Nếu cần ghép kết quả vào đúng vị trí nguồn, hãy trả một kiểu dữ liệu bao gồm `requestId`/chỉ số hoặc lưu quan hệ future → input, thay vì dựa vào thứ tự từ hàng đợi completion.
- `CompletionService` phù hợp để tính tích lũy, trả từng phần, hoặc xử lý những kết quả có sẵn trước; phải giải quyết việc các tác vụ còn lại đang chạy ra sao nếu quyết định dừng sớm.

## 6. allOf không tự tổng hợp giá trị hoặc đầy đủ mọi lỗi

Hợp đồng quan trọng của `CompletableFuture.allOf(f1, f2, ...)`:

1. Nó hoàn thành khi **tất cả các `CompletableFuture` được truyền vào hoàn thành**; không có nghĩa trả thành công ngay khi một future trả về.
2. Nếu bất kỳ nhánh nào hoàn thành ngoại lệ, future kết hợp cũng hoàn thành ngoại lệ (thường quan sát bằng `CompletionException` tại `join()`).
3. Nó **không tạo danh sách kết quả**, và **không tự trả danh sách mọi nguyên nhân thất bại**. Lỗi được cung cấp tại `join()` của future kết hợp không đủ để suy ra mọi nhánh hỏng.
4. Gọi `allOf()` với **mảng rỗng** trả về future đã hoàn thành bình thường với giá trị `null`; với danh sách rỗng, ta có thể chủ động trả `List.of()` nếu đó là hợp đồng chương trình.

Các trường hợp xử lý lỗi phải được thiết kế riêng, ví dụ:

| Chính sách fan-in | Cách triển khai | Ý nghĩa |
|---|---|---|
| Tất cả phải thành công | `allOf`, sau đó `join()` các nhánh | Nếu một nhánh thất bại, toàn bộ aggregate thất bại; `allOf` tự nó không dừng sớm các nhánh còn lại |
| Một số nhánh được phép thất bại | Bọc từng nhánh bằng `handle` thành kiểu `Outcome`, sau đó `allOf` | Thu được cả giá trị và lỗi của từng nhánh |
| Một nhánh có giá trị dự phòng | `exceptionally(...)` trên nhánh phù hợp trước khi `allOf` | Tổng hợp tiếp với fallback; cần thông báo là dữ liệu đã fallback nếu nghiệp vụ cần |
| Chỉ cần một nhánh hoàn thành | `anyOf` | Nhánh hoàn thành đầu tiên **có thể là lỗi**, và các nhánh khác không tự bị hủy |
| Cần mọi lỗi chứ không chỉ lỗi đầu tiên | Lưu `Outcome` theo từng nhánh | Không dựa vào exception của `allOf` làm báo cáo toàn bộ |

**Chú ý:** “all-or-nothing” là chính sách **giá trị kết quả**; nó không tự cung cấp rollback cho I/O hoặc tác dụng phụ ở các tác vụ đã chạy. Nếu ba nhánh cập nhật ba hệ thống và một nhánh lỗi, các thao tác thành công khác **không tự đảo ngược**. Phải có cơ chế bù trừ hoặc quy tắc idempotency riêng nếu có side effects.

## 7. Ví dụ đầy đủ: gom cả kết quả thành công lẫn lỗi từng nhánh

Một cách chắc chắn để làm **partial success** là biến mỗi completion thành một kết quả mang trạng thái. `handle` thực thi với cả hai đường bình thường và thất bại, nên future kiểu `Outcome` có thể hoàn thành bình thường với thông tin thất bại được lưu như dữ liệu.

Lưu thành **`PartialFanInDemo.java`** (Java 17+):

```java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.stream.IntStream;

public class PartialFanInDemo {
    record Outcome(int index, Integer value, String error) {}

    public static void main(String[] args) {
        List<CompletableFuture<Integer>> branches = List.of(
                CompletableFuture.completedFuture(10),
                CompletableFuture.failedFuture(
                        new IllegalStateException("source unavailable")),
                CompletableFuture.completedFuture(30)
        );

        List<CompletableFuture<Outcome>> safeBranches =
                IntStream.range(0, branches.size())
                        .mapToObj(i -> branches.get(i).handle((value, failure) -> {
                            Throwable root = failure;
                            while (root instanceof CompletionException
                                    && root.getCause() != null) {
                                root = root.getCause();
                            }
                            return new Outcome(
                                    i,
                                    value,
                                    root == null
                                            ? null
                                            : root.getClass().getSimpleName());
                        }))
                        .toList();

        CompletableFuture<?>[] all =
                safeBranches.toArray(new CompletableFuture<?>[0]);
        CompletableFuture.allOf(all).join();

        List<Outcome> outcomes =
                safeBranches.stream()
                        .map(CompletableFuture::join)
                        .toList();

        int successSum = 0;
        for (Outcome outcome : outcomes) {
            if (outcome.error() == null) {
                System.out.println("task " + outcome.index()
                        + ": value=" + outcome.value());
                successSum += outcome.value();
            } else {
                System.out.println("task " + outcome.index()
                        + ": error=" + outcome.error());
            }
        }
        System.out.println("Sum of successes: " + successSum);
    }
}
```

Chạy:

```bash
javac PartialFanInDemo.java
java PartialFanInDemo
```

Stdout chính xác:

```text
task 0: value=10
task 1: error=IllegalStateException
task 2: value=30
Sum of successes: 40
```

**Điểm đáng chú ý:**
- `Outcome` là một `record` Java 17, chứa chỉ số nguồn, giá trị hoặc tên loại lỗi. Ở hệ thống thực, có thể giữ `Throwable` và metadata chi tiết, nhưng cần hạn chế lộ thông tin nhạy cảm khi trả về cho người dùng.
- Ba nhánh của ví dụ được tạo sẵn để output có thể tái lập chính xác; mã này minh họa **chính sách fan-in khi lỗi**. Phần tạo concurrent tasks đã được minh họa bằng executor ở mục 3.
- Một nhánh lỗi không làm mất hai nhánh thành công. `allOf` ở đây nhận **future đã qua `handle`**, vì vậy mỗi nhánh báo trạng thái qua `Outcome`.
- Nếu callback `handle` tự ném lỗi, stage tương ứng vẫn có thể thất bại. “Bọc lỗi vào dữ liệu” là chiến lược phải được kiểm tra như bất kỳ đoạn mã nào khác.
- Không mặc định mọi lỗi đều được phép bỏ qua. Nếu một nhánh bắt buộc (ví dụ xác thực dữ liệu quan trọng) thất bại, chính sách tổng hợp có thể yêu cầu fail request dù nhánh tùy chọn khác thành công.

### exceptionally, handle và whenComplete khác nhau ra sao?

- `exceptionally(error -> fallback)` chạy trên nhánh lỗi và trả một **giá trị thay thế**; không có thông tin lỗi nữa nếu chỉ giữ giá trị sau fallback.
- `handle((value, error) -> outcome)` nhận cả hai trường hợp và thích hợp để tạo kiểu kết quả mang trạng thái.
- `whenComplete((value, error) -> log(...))` chủ yếu để quan sát; nó **không biến thất bại thành thành công** chỉ vì callback chạy xong. Nếu callback ném lỗi thì kết quả stage còn tùy nhánh đầu vào; không nên dùng `whenComplete` làm cơ chế recovery.

Một lỗi thường gặp là log trong `whenComplete` rồi gọi `allOf(...).join()` và ngạc nhiên khi `CompletionException` vẫn xuất hiện.

## 8. Giới hạn số nhánh chạy đồng thời: backpressure và tài nguyên

Dù một executor có nhiều thread, các nguồn I/O vẫn có giới hạn: connection pool, file descriptors, API quota, bộ nhớ, CPU, DB sessions. Fan-out 50.000 tác vụ rồi fan-in tất cả có thể gây backlog lớn, timeout và tăng bộ nhớ dù tác vụ phần lớn đang chờ.

Có ba phạm vi cần phân biệt:

1. **Số tác vụ đã tạo/submit:** ảnh hưởng bộ nhớ, queue và áp lực hệ thống.
2. **Số tác vụ thật sự đang chạy:** bị giới hạn bởi scheduler/executor và khả năng tài nguyên.
3. **Số thao tác đến một tài nguyên hữu hạn:** thường cần chính sách bulkhead/rate limit/`Semaphore` theo tài nguyên, có thể nhỏ hơn số tác vụ.

Ví dụ giới hạn tối đa hai tác vụ cùng đi vào vùng sử dụng tài nguyên:

```java
import java.util.concurrent.Semaphore;

// Snippet bên trong một class có limiter và thao tác cần giới hạn.
private final Semaphore limiter = new Semaphore(2);

String callLimited() throws InterruptedException {
    limiter.acquire();
    try {
        return callExternalService();
    } finally {
        limiter.release();
    }
}
```

Đây là mã minh họa, **không phải một file Java độc lập**: `callExternalService()` là phương thức của ứng dụng. Luôn `release()` trong `finally` sau khi acquire thành công. `Semaphore` giới hạn số công việc **đang giữ permit**, nhưng nếu tạo vô hạn future chờ permit thì vẫn tích lũy công việc; do đó thực tế còn cần **giới hạn đầu vào/queue**, batch hoặc cơ chế trả lỗi khi quá tải.

Với tác vụ CPU-bound, dùng nhóm worker có kích thước hợp lý theo CPU. Với tác vụ I/O-bound, có thể tăng concurrency có kiểm soát và xác nhận bằng đo đạc. Tránh dùng một pool nhỏ cho những tác vụ phải đợi công việc được submit **vào chính pool đó**; nếu tất cả worker đều đang chờ con, các tác vụ con có thể không bao giờ được chạy (thread starvation deadlock).

### Virtual Threads (Java 21+) có thay thế giới hạn concurrency không?

Không. Có thể dùng `Executors.newVirtualThreadPerTaskExecutor()` để tạo một virtual thread cho mỗi tác vụ chờ I/O; nhưng virtual threads **không tạo thêm connection, CPU hay database capacity**. Vẫn cần semaphore/bulkhead hoặc giới hạn số request đồng thời tại nguồn dữ liệu.

Snippet Java 21+ (đặt trong method, không phải chương trình độc lập):

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> first = executor.submit(() -> fetchFirst());
    Future<String> second = executor.submit(() -> fetchSecond());
    // Xử lý kết quả và lỗi theo hợp đồng fan-in của bài toán.
}
```

`ExecutorService` hỗ trợ `AutoCloseable` từ Java 19; đoạn `try-with-resources` này cần Java 21+ để dùng Virtual Threads chính thức. Nếu dùng Java 17, dùng `ExecutorService` với `shutdown()`/`awaitTermination()` trong vòng đời phù hợp.

## 9. Timeout và deadline chung: không nhân đôi ngân sách chờ

Đặt riêng timeout cho từng lần `Future.get(timeout)` có thể tạo ra tổng thời gian vượt mức mong muốn nếu gọi tuần tự. Ví dụ ba lần `get(1, SECONDS)` trên ba nhánh chưa hoàn thành có thể khiến người gọi đợi gần ba giây, thay vì một giây **cho toàn request**.

Những công cụ thường dùng:

| API | Tác động timeout |
|---|---|
| `Future.get(timeout, unit)` | Chỉ giới hạn **lần đợi của caller**; tự nó không đánh dấu Future thất bại hay hủy công việc |
| `CompletableFuture.orTimeout(timeout, unit)` | Sắp xếp để **chính future** hoàn thành ngoại lệ bằng `TimeoutException` nếu chưa xong khi hết hạn |
| `CompletableFuture.completeOnTimeout(value, timeout, unit)` | Nếu chưa xong thì hoàn thành bình thường bằng giá trị fallback khi hết hạn |
| `ExecutorService.invokeAll(tasks, timeout, unit)` | Chờ toàn bộ nhóm đến giới hạn thời gian; tác vụ chưa hoàn thành bị cancel khi return do timeout |
| `CompletionService.poll(timeout, unit)` | Chờ tối đa một khoảng thời gian để **lấy một future đã hoàn thành**; nếu quá hạn trả `null` |

Với `CompletableFuture`, cả `orTimeout` và `completeOnTimeout` hoạt động trên **chính future nhận lời gọi** (không tự tạo bản sao chỉ để timeout). Nếu nhiều thành phần đang tham chiếu future đó, chúng đều thấy trạng thái mới.

**Deadline chung:** tính một mốc hết hạn theo đồng hồ monotonic tại đầu request (ví dụ `System.nanoTime()`), rồi khi mỗi bước phải chờ thì chỉ dùng **thời gian còn lại**. Tránh dùng `currentTimeMillis()` để đo khoảng chờ vì đồng hồ hệ thống có thể bị chỉnh. Hết deadline cần quyết định: fail, trả partial success, hoặc trả fallback và xử lý/cancel các nhánh chưa hoàn thành.

Khi đã đạt deadline, hủy các `Future` không còn cần thiết bằng `cancel(true)` nếu mô hình tác vụ cho phép. Tuy nhiên:
- `Future.cancel(true)` với một tác vụ submit qua executor có thể gửi interrupt cho thread đang chạy, nhưng công việc phải **hợp tác** với interrupt mới dừng đúng nghĩa.
- `CompletableFuture.cancel(true)` chỉ làm future hoàn thành dưới dạng cancellation; tham số `mayInterruptIfRunning` **không được dùng để interrupt công việc bên trong** theo hợp đồng lớp này.
- Hủy future kết hợp bằng `allOf(...).cancel(...)` **không tự bảo đảm mọi nhánh con được hủy**. Nếu muốn dừng tất cả, phải lưu và chủ động quản lý các future hoặc tài nguyên tác vụ.

Do đó cần phân biệt “caller không còn muốn đợi” với “thực sự dừng tác vụ và side effects”.

## 10. Xử lý interruption, lỗi và lifecycle

Ở ranh giới chờ, `Future.get()` có thể ném `InterruptedException` (thread đợi bị ngắt), `ExecutionException` (tác vụ thất bại), và có thể ném trực tiếp `CancellationException`. Với `CompletableFuture.join()`, lỗi thường được bọc bằng `CompletionException` (unchecked), còn cancellation có thể ném `CancellationException` trực tiếp. Đừng xử lý chung mọi trường hợp bằng `catch (Exception)` rồi trả danh sách rỗng.

Ví dụ mẫu trong method đã có `List<Future<T>> futures`:

```java
try {
    for (Future<String> future : futures) {
        consume(future.get());
    }
} catch (InterruptedException interrupted) {
    for (Future<String> future : futures) {
        future.cancel(true);
    }
    Thread.currentThread().interrupt();
    // Hoặc truyền tiếp InterruptedException khi chữ ký method cho phép.
    throw new IllegalStateException("Fan-in interrupted", interrupted);
} catch (ExecutionException failed) {
    Throwable cause = failed.getCause();
    // Ghi nhận nguyên nhân và quyết định cancel, retry hoặc partial result.
    report(cause);
}
```

Đây là **snippet**, cần bổ sung các biến/hàm, import và xử lý `CancellationException` theo ngữ cảnh. Khôi phục interrupt flag khi bạn bắt nhưng không truyền tiếp `InterruptedException`, vì việc giữ tín hiệu này có ích cho tầng gọi và quản lý lifecycle.

**Executor lifecycle:** khi tạo executor riêng, phải `shutdown()` hoặc đóng đúng quy tắc; trong ứng dụng chạy lâu, thường có executor dùng chung với vòng đời được quản lý và không tạo pool mới cho mỗi request. Phân biệt `shutdown()` (không nhận tác vụ mới) với `shutdownNow()` (cố gắng interrupt các tác vụ đang chạy và trả tác vụ chưa bắt đầu); không phương thức nào bảo đảm mọi tác vụ lập tức ngừng.

## 11. Tổng hợp theo input order, completion order hoặc khóa nghiệp vụ

Có ít nhất ba quy tắc thứ tự độc lập:

- **Input order:** cần kết quả tương ứng `[A, B, C]` để render hoặc đối chiếu; lưu vị trí mỗi task rồi ghép theo input. Ví dụ `allOf` + `tasks.stream().map(join)`.
- **Completion order:** cần xử lý cái sẵn trước để giảm latency hiển thị/tích lũy; dùng `ExecutorCompletionService.take()`, nhưng kết quả có thể đến `[C, A, B]`.
- **Business key order:** kết quả của mỗi nhánh có `id`/`timestamp`/độ ưu tiên; cần sort/group theo khóa trước khi công bố tổng hợp. Thứ tự hoàn thành của thread không được dùng làm khóa nghiệp vụ.

Tổng hợp không giao hoán hoặc không kết hợp được (ghép chuỗi có thứ tự, chọn bản ghi mới nhất, áp dụng patch, tính toán floating-point nhạy cảm với thứ tự) phải nêu quy tắc rõ ràng. Với phép cộng số thực, thay đổi thứ tự có thể tạo sai khác nhỏ do làm tròn dấu phẩy động; không mặc định cách reduce theo completion order cho kết quả bit-for-bit giống nhau.

Thay vì để các tác vụ đồng thời cập nhật `ArrayList` chung hoặc biến `int sum` không được đồng bộ, cách an toàn đơn giản là **trả kết quả riêng từng tác vụ** và tổng hợp sau khi chúng hoàn thành. Nếu bắt buộc cập nhật trạng thái đồng thời, dùng các cấu trúc đồng bộ/atomic phù hợp và đánh giá tranh chấp.

## 12. Xử lý lỗi chiến lược: fail, fallback, retry hay partial

Một chiến lược nhất quán cần trả lời:

| Tình huống | Chính sách thường hợp lý | Rủi ro nếu bỏ qua |
|---|---|---|
| Nhánh bắt buộc thất bại | Fail request, ghi nguyên nhân và quyết định hủy những nhánh còn lại | Tổng hợp sai dữ liệu bắt buộc |
| Nhánh tùy chọn thất bại | Trả `Outcome` hoặc fallback được đánh dấu | Người dùng không biết thông tin thiếu hoặc bị thay thế |
| Lỗi tạm thời | Retry có giới hạn, có delay/backoff/jitter và deadline | Retry storm, tải tăng gấp bội |
| Rate limit / overload | Giảm concurrency, queue bounded, trả tín hiệu quá tải | Hàng đợi vô hạn và timeout lan rộng |
| Request hết deadline | Dừng chờ, trả lỗi hoặc partial theo hợp đồng; cleanup/cancel nếu hợp lệ | Tiêu thụ tài nguyên cho kết quả không còn ai cần |
| Side effect thành công một phần | Idempotency/bù trừ/transaction tương ứng | Không thể “rollback” chỉ bằng `CompletableFuture` |

**Retry phải cân nhắc side effects:** gửi lại một yêu cầu ghi dữ liệu không idempotent có thể tạo hai giao dịch. Với fan-out lớn, retry đồng loạt có thể làm dịch vụ phía sau quá tải nặng hơn. Giới hạn số lần retry, dùng mã nhận dạng/idempotency key khi phù hợp và dành ngân sách timeout cho toàn workflow.

Nếu bài toán cần “lấy đủ 2 trong 3 kết quả” (*quorum*) hoặc “chọn kết quả thành công đầu tiên”, đó là thuật toán fan-in riêng với trạng thái số lượng thành công, lỗi và tác vụ đang chạy. `CompletableFuture.anyOf` không giải quyết tự động chính sách này, vì nó hoàn thành theo **future đầu tiên hoàn thành**, kể cả khi thất bại.

## 13. Quan sát và kiểm thử tính đúng đắn

Các phép đo có ích với fan-out/fan-in:
- **Độ trễ tổng** và độ trễ từng nhánh (p50/p95/p99), đặc biệt nhánh chậm nhất khi đợi tất cả.
- **Số nhánh được tạo**, đang chạy, đang chờ queue, thành công, lỗi, timeout, cancel và retry.
- **Tài nguyên thực**: kích thước executor/queue, CPU, connection pool, số thao tác I/O đang mở, giới hạn của downstream.
- **Mã tương quan** cho mỗi request và mỗi nhánh; log lỗi gốc theo nhánh để xác định nhánh nào khiến fan-in thất bại.

Kiểm thử nên bao phủ ít nhất các tình huống: tất cả thành công; một nhánh lỗi sớm trong khi nhánh khác vẫn chạy; nhiều nhánh đồng thời thất bại; kết quả trả sai thứ tự; timeout; interrupt; cancellation; executor từ chối tác vụ (`RejectedExecutionException`); danh sách input rỗng; và nhánh lặp với dữ liệu đầu vào giống nhau. Với concurrency, đừng dựa vào `Thread.sleep` và hy vọng scheduler chạy theo thứ tự cố định: dùng `CountDownLatch`, `Phaser` hoặc công cụ điều phối có chủ đích để kiểm soát điểm đồng bộ trong test.

Khi debug, xem **tác vụ có được submit đồng loạt không**, có stage nào thực thi công việc blocking trên chính executor đang chạy fan-in không, và có tác vụ nào đang giữ khóa/tài nguyên mà nhánh khác cần hay không.

## 14. Checklist thiết kế fan-out / fan-in

1. Tách các nhánh **thực sự độc lập**; không vô tình đợi từng nhánh ngay sau khi submit.
2. Xác định **chính sách tổng hợp** trước: all-or-nothing, partial, first, quorum, hay fallback.
3. Chọn API theo cách cần lấy kết quả: `allOf`/`thenCombine`, `CompletionService` hoặc `Future`/`invokeAll`.
4. Quy định **thứ tự kết quả** (input, completion hoặc business key), không phụ thuộc ngẫu nhiên vào scheduler.
5. Quản lý executor, queue, giới hạn tài nguyên, và deadline chung; cân bằng throughput với latency.
6. Phân biệt `ExecutionException`, `CompletionException`, cancellation và interruption; giữ nguyên nhân lỗi và tín hiệu dừng.
7. Định nghĩa rõ retry, fallback, cleanup và side effects; hủy future không đồng nghĩa rollback công việc.
8. Đo lường và test khi các nhánh hoàn thành, thất bại hoặc bị ngắt **theo thứ tự bất kỳ**.

**Kết luận:** Fan-out giúp triển khai nhiều công việc độc lập cùng lúc; fan-in biến các kết quả bất đồng bộ thành một câu trả lời có **hợp đồng rõ ràng**. Nắm được giới hạn tài nguyên, kiểu dữ liệu kết quả, thứ tự tổng hợp và chính sách lỗi quan trọng hơn việc chỉ tăng số lượng thread.

### API Java chính thức

- [Java 21: `CompletableFuture`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 21: `ExecutorCompletionService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)
- [Java 21: `ExecutorService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
