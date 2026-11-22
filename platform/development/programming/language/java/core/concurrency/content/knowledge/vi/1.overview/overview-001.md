# Concurrency, parallelism và asynchronous execution khác nhau thế nào trong Java?

Ba thuật ngữ này thường đi cùng nhau vì đều liên quan đến việc thực hiện nhiều công việc, nhưng chúng trả lời **ba câu hỏi khác nhau**:

- **Concurrency (xử lý đồng thời theo nghĩa tổ chức):** Hệ thống quản lý tiến độ của nhiều tác vụ trong cùng một khoảng thời gian như thế nào?
- **Parallelism (thực thi song song):** Có thực sự từ hai tác vụ đang chạy **cùng một thời điểm** trên các tài nguyên tính toán khác nhau hay không?
- **Asynchronous execution (thực thi bất đồng bộ):** Sau khi yêu cầu một công việc, phía gọi có thể **tiếp tục** mà chưa cần đợi kết quả ngay hay không?

Một ứng dụng có thể dùng cả ba, chỉ một hoặc hai trong số đó. **Asynchronous không đồng nghĩa non-blocking; concurrency không đồng nghĩa parallelism; nhiều thread không tự động bảo đảm tăng tốc.**

## 1. Concurrency: nhiều tác vụ cùng được quản lý tiến độ

**Concurrency** là khả năng cấu trúc chương trình sao cho nhiều tác vụ có tiến độ chồng lấn trong một khoảng thời gian. Tại một thời điểm quan sát ngắn, mỗi tác vụ có thể đang chạy, chờ CPU, chờ I/O, chờ khóa hoặc đã sẵn sàng chạy.

Trên hệ thống chỉ có một lõi CPU khả dụng, bộ lập lịch có thể lần lượt cho các thread chạy một lát rồi chuyển sang thread khác. Nhìn trên khoảng thời gian dài, cả hai công việc đều tiến triển; tại mỗi thời điểm thực thi CPU, chỉ một công việc chạy.

```text
Thời gian ------->

Một lõi CPU:
CPU:  [A chạy][B chạy][A chạy][B chạy][A chạy]
A:    [chạy]    [chạy]           [chạy]
B:             [chạy]    [chạy]

Hai tác vụ A và B có thời gian tồn tại chồng lấn,
nhưng không có hai đoạn "chạy" trên CPU diễn ra cùng lúc.
```

Sơ đồ là mô hình minh họa việc chia lượt chạy, không phải lịch chạy được Java bảo đảm. Trong Java, nhiều `Thread` hoặc tác vụ được gửi đến `ExecutorService` là những cách tổ chức công việc concurrent. Việc có thực sự chạy đồng thời trên nhiều lõi hay không phụ thuộc số thread hoạt động, số lõi khả dụng và quyết định của scheduler.

Điểm mạnh của concurrency không chỉ là tốc độ: nó giúp chương trình phản hồi các yêu cầu độc lập, xử lý công việc đang chờ và sử dụng tài nguyên linh hoạt. Đổi lại, các tác vụ có thể tranh chấp dữ liệu chung, khóa và tài nguyên; cần quản lý đồng bộ và vòng đời cẩn thận.

## 2. Parallelism: thực sự chạy cùng lúc

**Parallelism** xảy ra khi hai hoặc nhiều phần công việc **đang thực thi đồng thời về thời gian thực**, chẳng hạn trên hai lõi CPU. Đây là thuộc tính của quá trình chạy thực tế, không chỉ của cách viết code.

```text
Thời gian ------->

Hai lõi CPU:
Core 1: [A chạy][A chạy][A chạy]
Core 2: [B chạy][B chạy][B chạy]

Các đoạn chạy của A và B chồng nhau trên hai lõi.
```

Ví dụ: chia một phép tính lớn thành hai phần độc lập rồi giao cho hai worker trên hai lõi CPU. Nếu thực sự cùng chạy, bài toán có parallelism. Trong Java có thể biểu đạt ý định này bằng `ExecutorService` với nhiều worker, `ForkJoinPool`, parallel streams hoặc thuật toán chia để trị.

Tuy nhiên:

- Pool có hai worker **cho phép** hai tác vụ cùng chạy; nó không cam kết chúng luôn được đặt trên hai lõi hay luôn nhanh hơn.
- Tăng số thread không làm tăng số lõi CPU; quá nhiều thread có thể làm tăng chi phí chuyển ngữ cảnh và tranh chấp.
- Một thuật toán không tách được thành phần độc lập, hoặc thường xuyên phải khóa cùng dữ liệu, có thể không hưởng lợi từ parallelism.
- Trên máy nhiều lõi, concurrent tasks có thể cũng parallel. Vì thế parallel execution là một trường hợp thể hiện concurrency về mặt tiến độ, nhưng không phải mọi concurrent execution đều parallel.

## 3. Asynchronous execution: không buộc caller đứng chờ ngay

**Asynchronous execution** nói về **quan hệ thời gian giữa phía gọi và kết quả**. Caller khởi tạo công việc và có thể làm việc khác trước khi nhận kết quả thông qua `Future`, `CompletableFuture`, callback hoặc cơ chế thông báo hoàn tất.

Đối lập về luồng điều khiển:

```text
Synchronous:
Caller: [gọi A........chờ A xong][xử lý kết quả][việc khác]

Asynchronous:
Caller: [khởi động A][việc khác................][dùng kết quả]
Worker:       [thực hiện A......................]
```

Với lời gọi đồng bộ thông thường, phương thức chỉ trả về khi phần việc của nó hoàn thành hoặc thất bại. Với API bất đồng bộ, phương thức thường trả về sớm một đối tượng đại diện cho công việc; kết quả đến sau. Caller vẫn **có thể tự chọn chờ**, chẳng hạn gọi `Future.get()` hoặc `CompletableFuture.join()`. Tại đúng điểm chờ đó, thread gọi có thể bị block.

Bất đồng bộ không chỉ có một mô hình thực thi:

- **Async bằng thread:** Một worker thread làm công việc thay caller. Nếu worker gọi I/O blocking, chính worker vẫn bị block.
- **Async event-driven/non-blocking I/O:** Một event loop có thể đăng ký nhiều hoạt động I/O và xử lý khi chúng sẵn sàng, không cần giữ riêng một thread chờ mỗi yêu cầu. Java NIO `Selector` là một API nền tảng cho hướng này.
- **Async completion chain:** Phần xử lý tiếp theo được mô tả bằng `thenApply`, `thenCompose`, `thenCombine`… để kích hoạt khi điều kiện hoàn tất phù hợp.

Vì vậy, **async không tự chứng minh non-blocking I/O**. Ví dụ `CompletableFuture.supplyAsync(() -> Thread.sleep(...), executor)` trả về cho caller sớm, nhưng worker bị block trong `sleep`. Ngược lại, một thao tác non-blocking cũng không mặc nhiên tạo parallelism trên CPU.

## 4. So sánh theo tiêu chí

| Tiêu chí | Concurrency | Parallelism | Asynchronous execution |
| --- | --- | --- | --- |
| Câu hỏi chính | Nhiều tác vụ có thể cùng tiến triển/được quản lý như thế nào? | Nhiều tác vụ có thực sự chạy cùng lúc không? | Caller có cần đợi kết quả ngay sau khi gọi không? |
| Đối tượng quan sát | Vòng đời và phối hợp giữa các tác vụ | Sự chồng lấn **thực thi** theo thời gian thực | Giao diện gọi, hoàn tất và nhận kết quả |
| Cần nhiều lõi CPU? | Không | Cần tài nguyên thực thi đồng thời để có CPU parallelism thực sự | Không |
| Cần nhiều thread? | Không nhất thiết (có thể dùng event loop) | CPU parallelism thường cần nhiều worker/lõi | Không nhất thiết |
| Mục tiêu hay gặp | Khả năng đáp ứng, tổ chức công việc độc lập | Tăng thông lượng tính toán khi chia việc hiệu quả | Tránh buộc caller chờ, ghép các tác vụ phụ thuộc |
| Rủi ro cần chú ý | Race condition, deadlock, starvation | Overhead, tranh chấp, tải CPU | Callback/chain lỗi, mất kiểm soát vòng đời, vô tình block |

**Ba khái niệm nằm trên các trục khác nhau.** Ví dụ một chương trình nhận nhiều kết nối bằng event loop có concurrency và thao tác I/O bất đồng bộ nhưng vẫn chỉ xử lý callback bằng một thread tại từng thời điểm. Một chương trình dùng hai worker tính toán đồng thời có concurrency và parallelism. Chương trình trả về `CompletableFuture` có tính async ở phía caller, nhưng nếu chỉ dùng một worker thì chưa thể kết luận có CPU parallelism.

## 5. Ví dụ Java 17+: ba khía cạnh xuất hiện trong một chương trình

Chương trình sau gửi **hai tác vụ độc lập** vào pool hai worker, cho thread `main` tiếp tục xử lý trước khi dùng kết quả. `Thread.sleep` chỉ **mô phỏng công việc chờ blocking** để dễ quan sát cấu trúc; nó không đại diện cho non-blocking I/O.

Lưu thành `ExecutionModesDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutionModesDemo {
    private static String load(String id) {
        try {
            Thread.sleep(150); // Giả lập thao tác chờ có blocking
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Task interrupted", e);
        }
        return id;
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<String> first =
                    CompletableFuture.supplyAsync(() -> load("A"), pool);
            CompletableFuture<String> second =
                    CompletableFuture.supplyAsync(() -> load("B"), pool);

            System.out.println("Da gui hai tac vu");

            CompletableFuture<String> combined =
                    first.thenCombine(second, (a, b) -> a + " + " + b);

            System.out.println("Main tiep tuc viec khac");
            System.out.println(combined.join());
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ExecutionModesDemo.java
java ExecutionModesDemo
```

**Stdout chính xác** (các worker không in ra màn hình, nên thứ tự ba dòng ổn định):

```text
Da gui hai tac vu
Main tiep tuc viec khac
A + B
```

Phân tích từng phần:

1. **Concurrency:** `first` và `second` đại diện cho hai công việc độc lập có thể cùng ở trạng thái chưa hoàn thành; `main` cũng tiếp tục chạy.
2. **Asynchronous execution:** `supplyAsync` lên lịch tác vụ và trả về `CompletableFuture`. Thread `main` in thông báo tiếp theo mà không đợi hai tác vụ hoàn tất ngay tại lời gọi. `thenCombine` biểu diễn một bước xử lý khi **cả hai** kết quả sẵn sàng.
3. **Parallelism có thể xảy ra:** Pool có hai worker nên hai tác vụ có cơ hội thực thi trùng thời điểm trên các lõi khác nhau. Code không bảo đảm điều này trên mọi môi trường; thời lượng đo được cũng không phải bằng chứng tuyệt đối.
4. **Blocking vẫn có mặt:** Mỗi worker bị block trong `Thread.sleep(150)`. Sau khi in dòng thứ hai, `main` gọi `combined.join()`; nếu kết quả chưa xong, `main` cũng bị block đến lúc hoàn tất.
5. **Không tạo thread vô hạn:** `Executors.newFixedThreadPool(2)` giới hạn hai worker và xếp hàng tác vụ dư. `shutdown()` yêu cầu executor ngừng nhận công việc mới và kết thúc sau các công việc đã gửi; trong ví dụ này `join()` đã đợi cả hai hoàn tất thành công trước đó.

Đừng lấy một lần chạy đo thời gian khoảng 150 ms để kết luận chắc chắn "có parallelism": thời gian khởi động, scheduling, chờ và số lõi khả dụng đều ảnh hưởng kết quả.

## 6. CompletableFuture: async API không đồng nghĩa một thread mới cho mỗi bước

Khi đã có `CompletableFuture<T>`, Java cung cấp các kiểu ghép bước khác nhau:

| API | Ý nghĩa | Điều cần nhớ |
| --- | --- | --- |
| `supplyAsync(supplier, executor)` | Lên lịch tính ra giá trị trên executor được chỉ định | Supplier vẫn có thể blocking |
| `runAsync(runnable, executor)` | Lên lịch tác vụ không tạo giá trị | Kết quả kiểu `CompletableFuture<Void>` |
| `thenApply(fn)` | Biến đổi kết quả khi stage trước thành công | Không tự bảo đảm tạo task/thread riêng; hàm có thể chạy trên thread hoàn tất stage |
| `thenApplyAsync(fn, executor)` | Lên lịch bước biến đổi bất đồng bộ qua executor | Thời điểm chạy phụ thuộc executor |
| `thenCompose(fn)` | Nối một tác vụ async phụ thuộc kết quả trước đó | Tránh cấu trúc lồng `CompletableFuture<CompletableFuture<T>>` |
| `thenCombine(other, fn)` | Kết hợp kết quả hai stage khi cả hai hoàn tất | Thích hợp với các công việc đầu vào độc lập |
| `allOf(futures...)` | Stage hoàn tất khi tất cả stage đã cho hoàn tất | Không tự tạo danh sách kết quả; phải lấy từ từng future |
| `exceptionally(fn)`, `handle(fn)` | Xử lý hoặc biến đổi lỗi | Cần xác định cách phục hồi và giữ ngữ cảnh lỗi |
| `join()` / `get()` | Đợi và lấy giá trị cuối | Đều có thể block; `join()` bọc lỗi bằng `CompletionException`, `get()` dùng `ExecutionException` và có thể ném `InterruptedException` |

Một điểm thường bị hiểu sai: tên `thenApply` **không có hậu tố `Async`** không có nghĩa là nó luôn chạy trên caller thread; ngược lại, tên `thenApplyAsync` cũng không có nghĩa Java tạo một thread hoàn toàn mới. Với các phương thức `Async` không truyền executor, chúng thường sử dụng `ForkJoinPool.commonPool()` theo chính sách thực thi mặc định của `CompletableFuture`; khi cần kiểm soát tài nguyên, hãy cung cấp executor phù hợp.

Nếu B cần kết quả A, chuỗi `A.thenCompose(a -> startB(a))` thể hiện **phụ thuộc tuần tự về dữ liệu**, mặc dù caller vẫn có thể tương tác bất đồng bộ với cả chuỗi. Nếu A và B độc lập, tạo cả hai trước rồi `thenCombine` để tận dụng khả năng chạy chồng lấn; đừng khởi động B chỉ sau `A.join()` nếu không có quan hệ phụ thuộc.

`Future.get()` chỉ đơn giản lấy kết quả, có thể phải đợi; `CompletableFuture` cung cấp thêm cơ chế kết hợp và xử lý hoàn tất mà không buộc caller phải `get()` ở mỗi bước. Tuy nhiên, một hệ thống vẫn cần điểm đồng bộ ở ranh giới sử dụng kết quả, và cần chính sách timeout, lỗi, hủy tác vụ phù hợp.

## 7. Ví dụ riêng về ý định CPU parallelism

Với phép tính có thể chia thành các phần độc lập, parallel stream là một API Java diễn đạt **ý định** phân chia tính toán. Để ví dụ có kết quả tái lập được, dùng phép cộng số nguyên:

Lưu thành `ParallelSumDemo.java`:

```java
import java.util.stream.LongStream;

public class ParallelSumDemo {
    public static void main(String[] args) {
        long total = LongStream.rangeClosed(1, 1_000_000)
                .parallel()
                .sum();

        System.out.println(total);
    }
}
```

```bash
javac ParallelSumDemo.java
java ParallelSumDemo
```

Stdout:

```text
500000500000
```

Kết quả toán học là `1_000_000 × 1_000_001 / 2 = 500_000_500_000`. `parallel()` cho phép stream chia công việc để thực hiện trên nhiều worker, thường sử dụng common fork/join pool. Điều đó không bảo đảm nhanh hơn bản `.sequential()`. Với phép tính đơn giản hoặc dữ liệu nhỏ, overhead chia/ghép công việc có thể chiếm ưu thế. Mã này minh họa cách biểu đạt parallel computation; muốn chứng minh hiệu năng cần benchmark đúng phương pháp, trên dữ liệu thực và môi trường xác định.

Cũng cần phân biệt: phép cộng `sum()` có quy tắc tổng hợp an toàn; không nên dùng `parallelStream().forEach(...)` để sửa một `ArrayList` chung hoặc trông đợi thứ tự phần tử, vì dễ tạo data race hoặc kết quả không ổn định.

## 8. Các tổ hợp thường gặp trong ứng dụng Java

| Tình huống | Concurrency? | Parallelism? | Async đối với caller? |
| --- | --- | --- | --- |
| Hai `Thread` được scheduler luân phiên trên một lõi | Có | Không tại mức CPU đang xét | Tùy cách caller khởi động/chờ |
| Hai tác vụ tính toán đang cùng chạy trên hai lõi | Có | Có | Có thể có hoặc không tùy API |
| Caller dùng `supplyAsync`, nhưng executor chỉ có một worker và task blocking | Có thể tổ chức nhiều task cùng tồn tại | Không có hai task chạy song song trong pool đó | Có, đến khi caller gọi phương thức đợi |
| Một event loop Java NIO xử lý các kết nối sẵn sàng | Có | Không nhất thiết | Có thể có, phụ thuộc API/cách thông báo |
| Caller gọi phương thức đồng bộ, phương thức bên trong tự chia việc trên nhiều CPU rồi đợi xong mới trả về | Có (bên trong) | Có thể có | Không tại giao diện caller |
| Một lời gọi HTTP đồng bộ đơn lẻ chạy trong một thread | Không nhất thiết | Không | Không |

Cột parallelism dựa vào **hành vi thực thi thực tế**, không thể suy ra chắc chắn chỉ từ việc nhìn thấy `parallel()`, số thread hoặc một đối tượng `Future`.

## 9. Chọn cách tiếp cận theo loại công việc

**CPU-bound** (tính toán, phân tích dữ liệu, mã hóa khối dữ liệu): nếu công việc tách được thành các phần đủ lớn và độc lập, hãy cân nhắc `ForkJoinPool`, executor có mức song song phù hợp hoặc parallel streams. Đo hiệu năng thực tế. Giới hạn số task chạy thật sự để tránh nhiều worker hơn khả năng CPU xử lý hiệu quả.

**I/O-bound** (đọc/ghi, kết nối mạng, gọi dịch vụ): concurrency hữu ích vì các tác vụ có thời gian chờ. Có thể dùng pool thực hiện I/O blocking hoặc API I/O không blocking nếu thư viện và kiến trúc phù hợp. Async giúp caller tiếp tục xử lý và kết hợp kết quả; nó không biến một lời gọi blocking thành non-blocking ở worker.

**Cần giao diện phản hồi nhanh:** dùng async để không giữ caller tại điểm chờ ngay lập tức, nhưng phải thiết kế nơi nhận kết quả, kiểm soát số tác vụ đang mở và cách báo lỗi. Nếu chỉ chuyển tác vụ sang worker rồi gọi `join()` ngay lập tức, lợi ích bất đồng bộ đối với caller gần như biến mất.

**Cần dữ liệu theo thứ tự:** xác định quan hệ phụ thuộc. Những bước phụ thuộc phải đợi dữ liệu trước; các bước độc lập có thể gửi đồng thời. Parallelize mù quáng có thể gây sai thứ tự hoặc lỗi dữ liệu.

## 10. Các lỗi nhận thức và kỹ thuật thường gặp

1. **"Concurrent nghĩa là luôn chạy cùng lúc."** Sai: trên một lõi CPU, scheduler có thể cho các tác vụ tiến triển luân phiên. Parallelism mới nói đến khoảng thời gian thực thi thật sự trùng nhau.
2. **"Async nghĩa là non-blocking."** Sai: caller có thể không chờ nhưng worker vẫn block khi đọc file, `sleep` hoặc gọi I/O đồng bộ.
3. **"Dùng `CompletableFuture` thì chắc chắn song song."** Sai: executor một worker có thể thực thi lần lượt; các stage phụ thuộc nhau cũng không chạy đồng thời chỉ vì tên API.
4. **"Nhiều thread luôn nhanh hơn."** Sai: CPU contention, context switching, lock contention, memory bandwidth và overhead chia/ghép có thể làm chậm hơn.
5. **"Gọi `join()` ngay sau mỗi `supplyAsync` là tận dụng tốt concurrency."** Thường sai nếu hai tác vụ độc lập: cách này có thể tuần tự hóa thời điểm bắt đầu công việc. Hãy khởi tạo các tác vụ độc lập trước, rồi mới ghép/đợi kết quả.
6. **"Tác vụ async tự xử lý lỗi."** Sai: lỗi có thể làm future hoàn tất bất thường; phải quan sát thất bại qua `join/get` hoặc stage xử lý lỗi. Không được bỏ qua future quan trọng.
7. **"`shutdown()` là hủy tức thì mọi việc."** Sai: `shutdown()` dừng nhận task mới và cho các task đã gửi hoàn tất; `shutdownNow()` cố gắng ngắt/hủy theo khả năng nhưng cũng không bảo đảm task dừng lập tức. Tác vụ blocking cần thiết kế phản ứng interruption hợp lý.
8. **"Thread-safe tự động khi dùng async."** Sai: `count++` trên biến chia sẻ không trở nên atomic chỉ nhờ chạy trong task. Cần thiết kế immutable data, thread confinement, `AtomicInteger`, lock hoặc cấu trúc concurrent phù hợp theo tình huống.
9. **"Tất cả continuation luôn chạy trên cùng thread."** Sai: một continuation không có hậu tố `Async` có thể chạy trên thread hoàn tất stage trước, hoặc thread gọi nếu stage đã hoàn tất; đừng dựa vào thread identity khi thiết kế logic.
10. **"Cancellation luôn ngắt được công việc đang chạy."** Không có cam kết chung như vậy với `CompletableFuture.cancel(...)`; riêng cơ chế này không dùng interrupt để điều khiển quá trình xử lý. Hãy thiết kế timeout, cờ hủy và đóng tài nguyên theo API cụ thể.

Với Java 21 trở lên, **virtual threads** giúp mô hình thread-per-task thuận tiện hơn cho nhiều tác vụ blocking I/O, nhưng **không tạo thêm lõi CPU** và không làm một phép tính CPU-bound tự nhiên nhanh hơn. Chúng cũng không thay đổi định nghĩa của ba khái niệm trên. Ví dụ chính của bài vẫn dùng API có sẵn trên Java 17.

## 11. Tự kiểm tra cách hiểu

**Tình huống A:** Một thread xử lý nhiều socket bằng cách nhận thông báo I/O sẵn sàng, rồi lần lượt xử lý sự kiện. Có concurrency giữa các kết nối và có thể có asynchronous/non-blocking I/O; không có bằng chứng xử lý callback song song trên CPU.

**Tình huống B:** Hai phép tính độc lập được giao cho hai worker và thật sự chạy cùng lúc trên hai lõi. Đây là concurrency **và** parallelism; giao diện gọi có async hay không phụ thuộc việc caller có phải đợi ngay tại lệnh gọi.

**Tình huống C:** Hàm trả về `CompletableFuture` ngay, nhưng worker đọc dữ liệu bằng phương thức blocking, còn caller tiếp tục xử lý. Đây là async đối với caller; worker vẫn blocking. Chưa đủ thông tin để nói có CPU parallelism.

**Tình huống D:** Caller gọi một hàm đồng bộ tính tổng lớn bằng nhiều worker; hàm đợi tất cả xong mới trả kết quả. Phần tính có thể concurrent và parallel, nhưng **lời gọi bên ngoài vẫn synchronous**.

Khi gặp một API hoặc thiết kế mới, hãy lần lượt hỏi:

1. **Có bao nhiêu tác vụ đang cùng tồn tại và tiến triển?** → xét concurrency.
2. **Có những đoạn tính toán thực sự đang chạy trùng thời gian trên các tài nguyên khác nhau?** → xét parallelism.
3. **Caller có thể làm việc khác trước khi cần lấy kết quả, hay bị buộc chờ tại điểm gọi?** → xét asynchronous execution.

Ba câu hỏi này giúp chọn đúng cơ chế của Java, phân tích bottleneck rõ hơn và tránh suy luận sai từ tên API hoặc số lượng thread.