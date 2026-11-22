# Hủy future và giới hạn ngắt công việc phía dưới trong Java

**`CompletableFuture.cancel(...)` không đồng nghĩa “dừng thread đang chạy”.** Trong Java, việc **một future đã bị hủy về mặt trạng thái kết quả** và việc **tác vụ I/O/CPU/remote thực sự ngừng làm việc** là hai hiện tượng khác nhau. Phân biệt đúng giúp tránh rò tài nguyên, request vẫn chạy sau timeout, tác vụ con bị bỏ mặc và những kết luận sai khi xây pipeline `CompletableFuture`.

Chủ đề này thuộc **Ghép tác vụ** của Java 8, tập trung vào:
- Hợp đồng hủy giữa `Future`, `FutureTask` và `CompletableFuture`.
- `cancel(true)` / `cancel(false)`, `CancellationException`, `isCancelled`, `isDone` và `isCompletedExceptionally`.
- Sự lan truyền **trạng thái lỗi** từ future cha sang dependent stage và giới hạn của **lan truyền lệnh hủy tác vụ**.
- Hủy future con, `thenCompose`, `allOf`, `anyOf`, timeout và các kết quả đua tranh.
- Cơ chế ngắt thread của `ExecutorService.submit`, cooperative cancellation, điểm kiểm tra, cleanup và I/O.
- Cách thiết kế API có ownership/cancel handle rõ ràng và test hành vi không dựa vào `Thread.sleep`.
- Những API hiện vẫn áp dụng với Java hiện đại; phân biệt chức năng Java 8 và Java 9+.

Các chương trình Java 17+ trong bài là **class độc lập**, có lệnh `javac`/`java` và stdout đã kiểm thử. Những mẫu nâng cao chỉ minh họa trong phương thức sẽ được ghi rõ, không giả là chương trình tự chạy.

## 1. Hai thứ phải hủy: kết quả và công việc

Một hệ thống bất đồng bộ thường có ít nhất hai thực thể:

1. **Future/CompletionStage**: một đối tượng đại diện cho giá trị hoặc lỗi *sẽ được công bố* cho consumer.
2. **Tác vụ phía dưới (underlying work)**: đoạn tính toán, HTTP request, truy vấn database, job nền, tiến trình hoặc một chuỗi downstream tasks thực sự tiêu thụ tài nguyên.

Đối với `CompletableFuture` thuần, hai thực thể **không có một mối quan hệ điều khiển hủy mặc định bắt buộc**. Bạn có thể hủy *quyền nhận kết quả* trước khi logic thực tế ngừng thực thi.

Ví dụ:

```java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> slowWork(), executor);

boolean accepted = result.cancel(true);
```

Đây là đoạn thiết kế **trong service**, có `slowWork()` và `executor` do ứng dụng cung cấp. Với `CompletableFuture` thông thường, `accepted` có thể true và `result.isCancelled()` thành true, **nhưng không có bảo đảm rằng `slowWork` đã dừng hoặc bị interrupt**.

Các ngữ nghĩa cần phân biệt trong log:

| Điều đã quan sát | Điều có thể kết luận | Điều **chưa** được kết luận |
| --- | --- | --- |
| `cancel(...)` trả true | Future hiện ở trạng thái hủy theo hợp đồng cụ thể | Worker đã ngừng |
| `future.isDone() == true` | Future đã có trạng thái cuối (success/error/cancel) | Side effect/I/O đã kết thúc |
| `future.isCancelled() == true` | Future đã bị hủy | Upstream/remote task bị hủy |
| `future.isCompletedExceptionally() == true` | Future lỗi hoặc cancel | Nguyên nhân nhất thiết là cancel |
| `future.join()` ném `CancellationException` | Kết quả future này đã bị hủy | Thread đã nhận interrupt |
| `Future.cancel(true)` trên task thông thường | Có thể yêu cầu interrupt worker nếu implementation hỗ trợ | Tác vụ bắt buộc dừng tức khắc |

Một quy trình **hủy đúng** thường gồm: công bố trạng thái cancel tới caller, yêu cầu ngừng tác vụ theo cơ chế mà tác vụ hiểu, xử lý giải phóng tài nguyên và đối chiếu trạng thái thực tế. **Hủy một future không phải phép rollback**.

## 2. Vai trò `Future`, `FutureTask` và `CompletableFuture`

`Future<V>` là interface cho kết quả bất đồng bộ, có từ lâu trước Java 8. `cancel(boolean mayInterruptIfRunning)` **cố gắng** hủy task theo hợp đồng của implementation.

`FutureTask<V>` là một implementation có quan hệ trực tiếp tới `Callable`/`Runnable` mà nó bao bọc. Các future thông dụng do `ExecutorService.submit(...)` trả về thường hỗ trợ yêu cầu **interrupt task đang chạy** khi gọi `cancel(true)`.

`CompletableFuture<T>`, xuất hiện ở Java 8, đồng thời triển khai `Future<T>` và `CompletionStage<T>`. Tuy nhiên, nó **không trực tiếp kiểm soát computation đã làm nó hoàn thành** như FutureTask, vì CompletableFuture có thể được hoàn thành bằng `complete`, callback khác, stage tổng hợp, một sự kiện ngoài chương trình, hoặc `supplyAsync`.

| Thành phần | Mục tiêu | `cancel(true)` về cơ bản |
| --- | --- | --- |
| `Future` | Interface theo dõi kết quả và yêu cầu hủy | Tùy implementation; có thể yêu cầu interrupt |
| `FutureTask` | Đại diện và điều khiển một Callable/Runnable cụ thể | Có thể interrupt worker thực thi khi đang chạy |
| `CompletableFuture` thông thường | Stage và trạng thái kết quả có thể ghép | **Exceptional completion bằng CancellationException; không dùng mayInterruptIfRunning để điều khiển task** |
| `CompletionStage` | Interface khai báo các bước xử lý phụ thuộc | Không có method `cancel` trong interface; cần quyền/handle phù hợp để hủy |
| `ExecutorService` | Quản lý nơi task được gửi và vòng đời executor | Hỗ trợ `submit` trả Future; `shutdownNow` cố dừng task, không bảo đảm |
| Thư viện I/O trả CompletableFuture đặc biệt | Có thể thêm cơ chế hủy request cụ thể | **Phụ thuộc contract thư viện**, không áp dụng tự động cho mọi CompletableFuture |

Điểm học thuật quan trọng: **interface `Future` không bảo đảm mỗi implementation có cùng năng lực quản lý thread**. Hãy đọc hợp đồng của **đối tượng cụ thể** trước khi dựa vào khả năng interruption.

## 3. `CompletableFuture.cancel(boolean)` làm gì?

Tài liệu Java 8+ của `CompletableFuture` quy định: nếu chưa hoàn thành, gọi `cancel(mayInterruptIfRunning)` làm future hoàn thành **exceptionally** bằng `CancellationException`. Theo API:

- `mayInterruptIfRunning` **không có tác dụng** trong implementation `CompletableFuture` thông thường; interrupt không được dùng để điều khiển xử lý.
- Về trạng thái kết quả, `cancel` tương đương `completeExceptionally(new CancellationException())`.
- `isCancelled()` có thể true; `isDone()` true; `isCompletedExceptionally()` true.
- Future đã thành công trước đó **không chuyển sang canceled** chỉ vì bạn gọi `cancel` muộn.
- Các dependent `CompletableFuture` **chưa hoàn tất** thường được hoàn thành exceptionally với `CompletionException` có cause `CancellationException`.
- Lời gọi `complete(value)` **sau khi cancel thắng** không thể thay thế kết quả đã chốt, và trả false.
- Nhiều thread có thể gọi `complete`, `completeExceptionally`, `cancel` cùng lúc; chỉ một trạng thái thắng đầu tiên ở future chưa hoàn thành (trừ các API sửa trạng thái đặc biệt như `obtrudeValue` vốn không dùng trong luồng bình thường).

```java
CompletableFuture<Integer> f = new CompletableFuture<>();
boolean cancelled = f.cancel(true);

System.out.println(cancelled);                  // true
System.out.println(f.isDone());                 // true
System.out.println(f.isCancelled());            // true
System.out.println(f.isCompletedExceptionally()); // true
System.out.println(f.complete(42));            // false
```

Đây là **đoạn minh họa trong phương thức**, không có worker phía dưới. Nó chứng minh trạng thái future, **không chứng minh một thread nào nhận interrupt**.

### `cancel(true)` và `cancel(false)` trên CompletableFuture

Với `CompletableFuture` chuẩn, **hai giá trị boolean không khác nhau về khả năng ngắt computation**. Tham số tồn tại vì lớp triển khai interface `Future`; JavaDoc nói rõ giá trị này không có hiệu lực ở implementation này.

**Không diễn giải rằng gọi `cancel(true)` sẽ tự động hủy request HTTP/DB nếu bạn chỉ nhận về một CompletableFuture từ `supplyAsync`.** Nếu API provider có contract hủy đặc biệt (chẳng hạn HttpClient mặc định), đánh giá riêng trường hợp đó: xem phần I/O phía dưới.

## 4. Những trạng thái và exception cần phân biệt

`CompletableFuture` thường có các trạng thái quan sát:

| Trạng thái | `isDone()` | `isCancelled()` | `isCompletedExceptionally()` | `join()` |
| --- | --- | --- | --- | --- |
| Chưa hoàn thành | false | false | false | Chờ |
| Hoàn thành bình thường | true | false | false | Trả giá trị |
| Hoàn thành với exception thường | true | false | true | Thường ném `CompletionException` |
| Bị hủy trực tiếp | true | true | true | Ném `CancellationException` |
| Stage phụ thuộc lỗi do cha bị hủy | true | **thường false** | true | `CompletionException` với cause `CancellationException` |

Bảng cuối mô tả một chuỗi `thenApply` thông thường: stage dependent được **hoàn thành exceptionally do propagation**, không nhất thiết bị gọi `cancel` trực tiếp. Mức độ bọc cause có thể khác nếu có các stage xử lý lỗi/custom implementation; đừng đoán bằng class exception ở mọi tầng mà không kiểm tra.

**`get()` và `join()` khác nhau:**
- `get()` khai báo `InterruptedException`/`ExecutionException` (checked), và có thể ném `CancellationException` nếu future bị hủy.
- `join()` không buộc caller xử lý checked exception; khi stage thất bại thường ném `CompletionException`, còn direct cancel có thể ném `CancellationException`.
- `get(timeout, unit)` giới hạn **thời gian chờ của caller**, không tự phát lệnh cancel tác vụ.
- `CancellationException` không có nghĩa là ứng dụng đã dừng hết side effect.

Khi xử lý lỗi, giữ nguyên ngữ nghĩa “người dùng chủ động hủy” và “tác vụ thất bại do bug/network” nếu domain cần phân biệt, thay vì catch `RuntimeException` chung rồi coi tất cả là timeout.

## 5. Hủy future nguồn làm gì với dependent stages?

Một pipeline:

```java
CompletableFuture<Integer> source =
        new CompletableFuture<>();

CompletableFuture<Integer> mapped =
        source.thenApply(v -> v * 2);

CompletableFuture<String> recovered =
        source.handle((value, error) ->
                error == null ? "success" : "fallback");
```

Đoạn minh họa bên trong phương thức, chưa có executor/worker. Nếu `source.cancel(true)` thắng trước khi source hoàn thành:
- `source` chuyển sang trạng thái hủy.
- `mapped` không chạy lambda “`v * 2`” vì source không thành công; `mapped` thường hoàn thành exceptionally với `CompletionException` có cause `CancellationException`.
- `recovered` chạy `handle` vì handle nhận cả result/error; nó có thể **chuyển cancellation thành fallback** tùy logic.
- `mapped.isCancelled()` **không nhất thiết true**, vì nó chỉ nhận lỗi phụ thuộc, không bị hủy trực tiếp.
- Không có cuộc gọi interrupt nào được thực hiện chỉ vì propagation nói trên.

### Lan truyền trạng thái ≠ lan truyền yêu cầu ngắt

Từ “propagation” rất dễ gây hiểu nhầm. JavaDoc nói dependent futures chưa hoàn tất sẽ nhận **exceptional completion**. Nó **không nói** tất cả tác vụ nền đang chạy trong pipeline đều bị dừng, hay API I/O tự nhận một `cancel` tương ứng.

Nếu pipeline có một stage đã bắt đầu chạy, việc upstream hoàn thành exceptionally **không hoàn tác công việc đã chạy**, không đảo ngược thao tác ghi database và không bảo đảm hủy request phía ngoài process.

## 6. Chương trình Java: cancel cha, trạng thái con và `handle`

Tạo tệp `CancellationGraphDemo.java`:

```java
import java.util.concurrent.*;

public class CancellationGraphDemo {
    public static void main(String[] args) throws Exception {
        CompletableFuture<Integer> root =
                new CompletableFuture<>();

        CompletableFuture<Integer> mapped =
                root.thenApply(v -> v * 2);

        CompletableFuture<String> recovered =
                root.handle((v, e) ->
                        e == null ? "value-" + v : "fallback");

        boolean cancelled = root.cancel(true);

        System.out.println("cancel returned = " + cancelled);
        System.out.println(
                "root cancelled = " + root.isCancelled());
        System.out.println("root done = " + root.isDone());
        System.out.println(
                "root exceptional = " +
                        root.isCompletedExceptionally());

        System.out.println(
                "mapped cancelled = " + mapped.isCancelled());
        System.out.println(
                "mapped exceptional = " +
                        mapped.isCompletedExceptionally());

        try {
            root.join();
        } catch (CancellationException ex) {
            System.out.println(
                    "root join = CancellationException");
        }

        try {
            mapped.join();
        } catch (CompletionException ex) {
            System.out.println(
                    "mapped join cause = " +
                            ex.getCause().getClass().getSimpleName());
        }

        try {
            root.get();
        } catch (CancellationException ex) {
            System.out.println(
                    "root get = CancellationException");
        }

        System.out.println(
                "handle recovery = " + recovered.join());
        System.out.println(
                "late completion accepted = " + root.complete(42));

        CompletableFuture<Integer> completed =
                CompletableFuture.completedFuture(9);

        System.out.println(
                "cancel completed = " + completed.cancel(true));
        System.out.println(
                "completed value = " + completed.join());
    }
}
```

Chạy trên JDK 17+:

```bash
javac -encoding UTF-8 CancellationGraphDemo.java
java CancellationGraphDemo
```

Đầu ra đã kiểm thử:

```text
cancel returned = true
root cancelled = true
root done = true
root exceptional = true
mapped cancelled = false
mapped exceptional = true
root join = CancellationException
mapped join cause = CancellationException
root get = CancellationException
handle recovery = fallback
late completion accepted = false
cancel completed = false
completed value = 9
```

Đây là chương trình deterministic vì `root` chỉ được hoàn thành **sau khi các dependent được đăng ký**. `mapped.isCancelled() == false` không có nghĩa stage đó thành công: nó **hoàn thành exceptionally**, như dòng tiếp theo cho thấy.

`handle recovery = fallback` còn nhắc rằng **bắt cancellation rồi trả fallback là lựa chọn nghiệp vụ**, không phải lúc nào cũng đúng. Nếu người dùng hủy một đơn hàng, âm thầm biến trạng thái thành “đã xử lý mặc định” có thể sai ý nghĩa.

## 7. Hủy stage con có tự hủy cha không?

**Không có quy tắc lan truyền ngược mặc định cho đồ thị `CompletableFuture` thuần.** Nếu bạn tạo:

```java
CompletableFuture<Integer> parent =
        new CompletableFuture<>();
CompletableFuture<Integer> child =
        parent.thenApply(x -> x + 1);
```

sau đó gọi `child.cancel(true)`, điều này chỉ giải quyết **kết quả của child**. `parent` có thể vẫn đang đợi I/O, giữ kết nối hoặc tiếp tục tính toán; các dependent khác của parent không tự chuyển sang cancelled chỉ vì một child bị hủy.

Một lý do thiết kế: **parent có thể có nhiều consumer**. Hủy một branch không thể mặc nhiên hủy shared source mà các branch khác vẫn cần.

Sơ đồ:

```text
             ┌── child A  ← cancel(A)
source ──────┤
             └── child B  ← vẫn cần source

cancel(child A)
  ≠ cancel(source)
  ≠ cancel(child B)
  ≠ interrupt(worker của source)
```

Nếu ứng dụng muốn “khi tất cả consumer hủy thì dừng shared computation”, phải **thiết kế ownership/reference counting/cancellation token** riêng. `CompletableFuture` không tự giải bài toán này chỉ vì có phương thức `cancel`.

## 8. `thenCompose`: hủy future ngoài không đồng nghĩa hủy inner future

`thenCompose` làm phẳng một future bên trong:

```java
CompletableFuture<Integer> inner =
        new CompletableFuture<>();

CompletableFuture<Integer> outer =
        CompletableFuture.completedFuture(1)
                .thenCompose(v -> inner);
```

`outer` là stage đại diện kết quả `inner` trong pipeline. Nhưng việc gọi `outer.cancel(true)` **không phải một hợp đồng tự động gọi `inner.cancel(true)`**.

Tương tự, cancel một stage của pipeline không mặc nhiên đi ngược về mọi nguồn ở phía trên. Nếu inner I/O có handle hủy riêng, ứng dụng cần giữ handle và gọi nó có chủ đích tại ranh giới ownership phù hợp.

Một số thư viện trả về CompletableFuture subclass có override/cancellation hook đặc biệt; **không suy ra từ những implementation đó thành quy tắc của CompletableFuture chuẩn**.

## 9. Chương trình Java: cancel child, sibling và composed result

Tạo `ChildCancellationDemo.java`:

```java
import java.util.concurrent.*;

public class ChildCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> parent =
                new CompletableFuture<>();

        CompletableFuture<Integer> first =
                parent.thenApply(v -> v + 1);

        CompletableFuture<Integer> second =
                parent.thenApply(v -> v * 10);

        System.out.println(
                "child cancelled = " + first.cancel(true));
        System.out.println(
                "parent done after child cancel = " +
                        parent.isDone());

        System.out.println(
                "parent complete = " + parent.complete(3));
        System.out.println(
                "sibling value = " + second.join());
        System.out.println(
                "cancelled child still cancelled = " +
                        first.isCancelled());

        CompletableFuture<Integer> upstream =
                CompletableFuture.completedFuture(7);
        CompletableFuture<Integer> inner =
                new CompletableFuture<>();

        CompletableFuture<Integer> composed =
                upstream.thenCompose(v -> inner);

        System.out.println(
                "composed cancelled = " + composed.cancel(true));
        System.out.println(
                "inner done after composed cancel = " +
                        inner.isDone());
        System.out.println(
                "inner complete = " + inner.complete(70));
        System.out.println(
                "composed remains cancelled = " +
                        composed.isCancelled());
    }
}
```

```bash
javac -encoding UTF-8 ChildCancellationDemo.java
java ChildCancellationDemo
```

```text
child cancelled = true
parent done after child cancel = false
parent complete = true
sibling value = 30
cancelled child still cancelled = true
composed cancelled = true
inner done after composed cancel = false
inner complete = true
composed remains cancelled = true
```

Kết quả chứng minh **hai chiều lan truyền khác nhau**: cancel một child không hủy parent/sibling; cancel stage đã flatten bằng thenCompose không tự hủy `inner`. Điều này quan trọng nếu `inner` chứa request mạng dài: **đã hủy màn hình chờ** không có nghĩa request thật đã dừng.

## 10. `supplyAsync(...)` không biến `CompletableFuture` thành `FutureTask`

Ví dụ:

```java
ExecutorService worker =
        Executors.newSingleThreadExecutor();

CompletableFuture<String> cf =
        CompletableFuture.supplyAsync(
                () -> blockingCall(), worker);
```

Đây là đoạn minh họa có `blockingCall()` thuộc ứng dụng và ownership của `worker`. `supplyAsync` gửi Supplier tới Executor và trả future, nhưng **future trả về không phải trực tiếp handle `FutureTask` của `ExecutorService.submit`**.

Nếu gọi `cf.cancel(true)`:
- `cf` có thể đổi ngay sang trạng thái canceled.
- Một Supplier đã chạy có thể **tiếp tục thực thi**.
- `cancel(true)` trên CompletableFuture thuần **không được thiết kế để gọi `Thread.interrupt()`** trên worker đó.
- Nếu Supplier sau đó tính ra kết quả, nó có thể **không ghi đè được** trạng thái canceled của CompletableFuture.
- Side effect của Supplier (ghi file, DB, HTTP request, gửi message) **không tự bị rollback**.

Trong một vài tình huống task chưa bắt đầu và future đã được hoàn thành/cancel, implementation có thể bỏ qua chạy body; tuy vậy **không dùng khả năng tối ưu đó làm cam kết rằng underlying task sẽ không bao giờ khởi động hoặc dừng trong mọi race**. Thiết kế an toàn phải có cơ chế hủy của chính tác vụ.

## 11. Chương trình Java: cancel CompletableFuture nhưng worker vẫn đợi

Tạo `CancelDoesNotInterruptDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelDoesNotInterruptDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);

        try {
            CompletableFuture<String> cf =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "finished";
                        } catch (InterruptedException ex) {
                            interrupted.set(true);
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            finished.countDown();
                        }
                    }, worker);

            if (!started.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "worker not started");
            }

            System.out.println(
                    "cf cancel true = " + cf.cancel(true));
            System.out.println(
                    "cf isCancelled = " + cf.isCancelled());
            System.out.println(
                    "worker finished before release = " +
                            (finished.getCount() == 0));

            release.countDown();

            if (!finished.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "worker not finished");
            }

            System.out.println(
                    "worker observed interrupt = " +
                            interrupted.get());

            try {
                cf.join();
            } catch (CancellationException ex) {
                System.out.println(
                        "cf join = CancellationException");
            }
        } finally {
            release.countDown();
            worker.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 CancelDoesNotInterruptDemo.java
java CancelDoesNotInterruptDemo
```

```text
cf cancel true = true
cf isCancelled = true
worker finished before release = false
worker observed interrupt = false
cf join = CancellationException
```

Chương trình dùng `CountDownLatch` để biết chắc Supplier **đã bắt đầu** trước khi gọi `cancel`. Vì vậy kết quả không phụ thuộc vào việc task được lên lịch sớm/muộn. `cancel(true)` khiến kết quả future bị hủy, nhưng worker vẫn ở `release.await()` cho tới khi main chủ động mở latch; nó **không thấy interrupt do `cf.cancel`**.

`finally` mở latch và `shutdownNow` chỉ nhằm cleanup đề phòng test thất bại. Lời gọi shutdownNow ở cuối **khác** với `cf.cancel(true)`; không lấy nó làm bằng chứng rằng CF hỗ trợ interrupt.

## 12. `Future` từ `ExecutorService.submit` có thể yêu cầu interrupt

Đối lập với `CompletableFuture.supplyAsync`, khi dùng:

```java
Future<String> task =
        executor.submit(() -> doBlockingWork());
```

thì `Future` thông thường do `ExecutorService.submit` trả về có handle quản lý một Runnable/Callable được đưa vào executor (thường là `FutureTask` hoặc task tương đương).

Theo contract `Future.cancel(boolean)`:
- Nếu chưa bắt đầu, yêu cầu hủy thành công có thể **ngăn task được chạy**.
- Nếu đã bắt đầu, `cancel(true)` **cố gắng interrupt** thread chạy task khi implementation biết thread ấy.
- `cancel(false)` yêu cầu hủy **kết quả/khả năng tiếp tục** nhưng **không yêu cầu interrupt running thread**; task đã bắt đầu có thể vẫn chạy.
- Có thể có race giữa task completion và cancellation.
- Dù interrupt được gửi thành công, **không có bảo đảm task lập tức dừng**: code có thể bỏ qua interrupted status, bị chặn trong API không đáp ứng interruption hoặc đang ở đoạn native/blocking đặc biệt.

`Future.cancel(true)` **không phải** `Thread.stop()` và không thực hiện rollback. Nó là một nỗ lực hợp tác với code và API chặn tương thích interruption.

Lưu ý khi một task được cancel, `Future.get()` sẽ ném `CancellationException` thay vì trả giá trị Callable ngay cả khi worker vẫn đang trong quá trình kết thúc/cleanup.

## 13. Chương trình Java: `submit`, `cancel(true)` và interrupt quan sát được

Tạo `SubmittedFutureInterruptDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class SubmittedFutureInterruptDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService ex =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch observed = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        try {
            Future<String> f = ex.submit(() -> {
                started.countDown();
                try {
                    new CountDownLatch(1).await();
                    return "unreachable";
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    observed.countDown();
                    Thread.currentThread().interrupt();
                    return "stopped";
                }
            });

            if (!started.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("not started");
            }

            System.out.println(
                    "submit cancel true = " + f.cancel(true));

            if (!observed.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "interrupt not observed");
            }

            System.out.println(
                    "submitted task saw interrupt = " +
                            sawInterrupt.get());
            System.out.println(
                    "submit cancelled = " + f.isCancelled());

            try {
                f.get();
            } catch (CancellationException e) {
                System.out.println(
                        "submit get = CancellationException");
            }
        } finally {
            ex.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 SubmittedFutureInterruptDemo.java
java SubmittedFutureInterruptDemo
```

```text
submit cancel true = true
submitted task saw interrupt = true
submit cancelled = true
submit get = CancellationException
```

Đây là một **ví dụ có chủ đích dùng một blocking operation biết interruption** (`CountDownLatch.await()`) để minh họa khả năng `cancel(true)` trên Future do submit trả về. Sau khi main chắc chắn task đã bắt đầu, `cancel(true)` yêu cầu interrupt; worker bắt `InterruptedException` và báo vào latch `observed`.

Với một Callable tùy ý như phép tính CPU không kiểm tra interrupt, hoặc thao tác I/O không có cơ chế ngắt rõ, **không thể lấy stdout này làm cam kết mọi task luôn dừng khi bị cancel**.

## 14. Interruption là tín hiệu hợp tác, không phải hủy cưỡng chế

`Thread.interrupt()` chủ yếu là cơ chế **đặt cờ interrupted** và khiến một số thao tác chặn đáp ứng bằng `InterruptedException`. Ví dụ:
- `Thread.sleep(...)`.
- `Object.wait(...)`.
- `CountDownLatch.await(...)`.
- `BlockingQueue.put/take(...)`.
- Nhiều thao tác lock/wait của java.util.concurrent.

Tác vụ CPU chạy vòng lặp cần **chủ động kiểm tra**:

```java
while (!Thread.currentThread().isInterrupted()) {
    doSmallUnitOfWork();
}
```

Đây là đoạn minh họa có `doSmallUnitOfWork()` do ứng dụng cung cấp; **không chạy vòng lặp không điều kiện dừng** trên main. Cần thiết kế điểm check, cleanup và trả trạng thái/cancellation hợp lệ.

Hai API dễ bị nhầm:
- `Thread.currentThread().isInterrupted()` kiểm tra trạng thái mà **không xóa cờ**.
- `Thread.interrupted()` (static) đọc và **xóa cờ** của thread hiện tại.

Khi bắt `InterruptedException` mà method không khai báo ném tiếp, thường nên khôi phục trạng thái:

```java
try {
    queue.take();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Thoát/cancel hoặc trả trạng thái đúng.
}
```

Đây là đoạn trong phương thức với `queue` được cung cấp. **Không chỉ khôi phục flag rồi tiếp tục vòng lặp vô tận**; thread vẫn phải rời đi hoặc có policy rõ. Nếu có thể, cho phép exception đi ngược lên boundary biết cách xử lý cũng là phương án tốt.

Không tự gọi interrupt tùy ý lên thread thuộc thread pool dùng chung nếu không sở hữu tác vụ: cờ interrupt/cleanup có thể tác động đến công việc khác hoặc vòng đời worker tùy implementation.

## 15. Cooperative cancellation: token độc lập với trạng thái Future

Một cơ chế rõ ràng cho tác vụ dài là **cancellation token**:

- `AtomicBoolean cancelled` hoặc một primitive thread-safe lưu ý định hủy.
- Worker kiểm tra token tại những điểm hợp lý giữa các bước.
- Nếu worker đang đợi API blocking có hỗ trợ interrupt, handle task có thể gửi interrupt để worker thức dậy.
- Với I/O/remote task, dùng API hủy của provider, timeout hoặc đóng resource theo hợp đồng.
- Worker chủ động dọn tài nguyên trong `finally` và rời đi.

Token **không tự stop** task: nếu worker không đọc token, thay đổi `AtomicBoolean` cũng không làm gì. Token giúp hủy **hợp tác**, chứ không thay thế interrupt ở thao tác chặn dài.

Khi sử dụng token chung cho nhiều worker, chú ý ownership: hủy một branch không nên thay đổi token của một nguồn **được chia sẻ với các consumer khác**, trừ khi toàn bộ nhóm đã đồng ý dừng.

`AtomicBoolean` cho phép nhiều thread quan sát cờ một cách thread-safe. Một biến `boolean` thông thường không có đồng bộ hóa phù hợp có thể không bảo đảm visibility theo Java Memory Model.

## 16. Chương trình Java: token hủy tại checkpoint xác định

Tạo `CooperativeTokenDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeTokenDemo {
    static final class Token {
        final AtomicBoolean stopped =
                new AtomicBoolean();

        void cancel() {
            stopped.set(true);
        }

        boolean isCancelled() {
            return stopped.get();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService ex =
                Executors.newSingleThreadExecutor();
        Token token = new Token();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch check = new CountDownLatch(1);

        try {
            Future<String> task = ex.submit(() -> {
                started.countDown();

                if (!check.await(2, TimeUnit.SECONDS)) {
                    throw new AssertionError(
                            "release timed out");
                }

                if (token.isCancelled()) {
                    return "stopped cooperatively";
                }
                return "work completed";
            });

            if (!started.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "worker not started");
            }

            token.cancel();
            check.countDown();

            System.out.println(
                    "token cancelled = " +
                            token.isCancelled());
            System.out.println(
                    "worker result = " +
                            task.get(2, TimeUnit.SECONDS));
        } finally {
            check.countDown();
            ex.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 CooperativeTokenDemo.java
java CooperativeTokenDemo
```

```text
token cancelled = true
worker result = stopped cooperatively
```

Ở đây **không gọi `task.cancel(...)`**. Worker nhận tín hiệu bằng token và trả về một chuỗi kết quả mang nghĩa “đã dừng hợp tác”. Vì vậy `Future.get()` **có thể trả kết quả bình thường**, khác với `FutureTask` bị cancel thật sự (khi ấy `get()` ném CancellationException).

Bài học: **tín hiệu dừng tác vụ, trạng thái future và cách API trả kết quả là các quyết định riêng**. Trong ứng dụng production, bạn có thể chọn chuẩn hóa thành `CancellationException`/result enum thay cho chuỗi mô tả, nhưng phải nhất quán và có test.

## 17. `allOf` và `anyOf` không tự dừng các nguồn

Hai combinator của `CompletableFuture`:

`CompletableFuture.allOf(a, b)`:
- Trả một `CompletableFuture<Void>` hoàn thành khi **tất cả** nguồn được hoàn tất.
- Nếu một nguồn lỗi, aggregate hoàn thành exceptionally theo hợp đồng của API.
- Hủy **aggregate** không mang ý nghĩa tự gọi `cancel` trên từng `a` và `b` trong CompletableFuture chuẩn.
- Nếu muốn **fail-fast và cancel phần còn lại**, cần thiết kế cơ chế riêng; `allOf` không phải một scope tự hủy mọi task.

`CompletableFuture.anyOf(a, b)`:
- Hoàn thành khi **một** trong các nguồn hoàn thành, với kết quả/error của nguồn đó.
- **Không tự dừng tác vụ thua cuộc** khi đã có một nguồn thắng.
- Hủy aggregate cũng không đồng nghĩa gửi interrupt tới tất cả nguồn.

Đặc biệt, **“race first result” và “race then cancel losers” là hai yêu cầu khác nhau**. Nếu task thua cuộc có side effect, bạn phải cân nhắc hủy nó có đúng hay không, và kể cả gọi cancel cũng không bảo đảm side effect chưa xảy ra.

Với các future đến từ nhiều thư viện khác nhau, chỉ có thể quyết định chính sách hủy khi bạn sở hữu/biết rõ cancellation handle của từng nguồn.

## 18. Chương trình Java: hủy aggregate và để nguồn chạy tiếp

Tạo `AggregateCancellationDemo.java`:

```java
import java.util.concurrent.*;

public class AggregateCancellationDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> a =
                new CompletableFuture<>();
        CompletableFuture<Integer> b =
                new CompletableFuture<>();
        CompletableFuture<Void> all =
                CompletableFuture.allOf(a, b);

        System.out.println(
                "all cancelled = " + all.cancel(true));
        System.out.println(
                "a cancelled = " + a.isCancelled());
        System.out.println(
                "b cancelled = " + b.isCancelled());

        System.out.println(
                "a complete = " + a.complete(2));
        System.out.println(
                "b complete = " + b.complete(3));
        System.out.println(
                "all still cancelled = " + all.isCancelled());

        CompletableFuture<Integer> left =
                new CompletableFuture<>();
        CompletableFuture<Integer> right =
                new CompletableFuture<>();
        CompletableFuture<Object> any =
                CompletableFuture.anyOf(left, right);

        left.complete(7);

        System.out.println(
                "any value = " + any.join());
        System.out.println(
                "loser still incomplete = " + !right.isDone());
        System.out.println(
                "loser complete = " + right.complete(9));
    }
}
```

```bash
javac -encoding UTF-8 AggregateCancellationDemo.java
java AggregateCancellationDemo
```

```text
all cancelled = true
a cancelled = false
b cancelled = false
a complete = true
b complete = true
all still cancelled = true
any value = 7
loser still incomplete = true
loser complete = true
```

Mẫu dùng các CompletableFuture chưa hoàn thành để kiểm soát thứ tự một cách chính xác, không phụ thuộc thread scheduling. `all.cancel(true)` **không làm `a`/`b` bị canceled**. Khi `any` đã có kết quả từ `left`, `right` vẫn pending và có thể hoàn thành sau đó.

Nếu đây là hai HTTP request chạy thật, **tác vụ thua cuộc có thể còn sử dụng mạng/server** dù aggregate đã có kết quả. Khi cần cancel losers, phải giữ từng request handle và xử lý riêng.

## 19. Timeout có ít nhất ba nghĩa khác nhau

Trong Java, “timeout” không phải lúc nào cũng hủy tác vụ.

| API | Điều xảy ra khi hết hạn | Tự dừng underlying work? |
| --- | --- | --- |
| `future.get(timeout, unit)` | Caller ngừng **chờ** và nhận `TimeoutException` | **Không** |
| `cf.orTimeout(timeout, unit)` (Java 9+) | **Chính `cf`** hoàn thành exceptionally bằng TimeoutException nếu chưa xong | **Không mặc định** |
| `cf.completeOnTimeout(value, timeout, unit)` (Java 9+) | **Chính `cf`** hoàn thành bình thường bằng fallback | **Không mặc định** |
| Timeout của HTTP client/driver | Phụ thuộc thư viện: có thể yêu cầu dừng I/O/đóng stream | Đọc contract cụ thể |
| `Future.cancel(true)` | Yêu cầu hủy task, có thể interrupt | Nỗ lực, **không chắc chắn** |
| Deadline nghiệp vụ end-to-end | Quy tắc hết hạn của cả request/transaction | Phải áp dụng ở mọi layer thích hợp |

Hai method `orTimeout` và `completeOnTimeout` **trả về chính receiver CompletableFuture**, không tạo ra một future timeout độc lập theo kiểu `thenApply`. Vì vậy chúng có thể ảnh hưởng tới **tất cả consumer** đang quan sát cùng một source future.

Ví dụ:

```java
CompletableFuture<String> shared = fetchAsync();

// Đây là cùng một future. Timeout có thể áp đặt lên mọi consumer.
CompletableFuture<String> timed =
        shared.orTimeout(500, TimeUnit.MILLISECONDS);
```

Đoạn minh họa trong phương thức có `fetchAsync()` và import `java.util.concurrent.*`. Nếu `shared` được nhiều consumer dùng, việc một consumer gọi `orTimeout` lên shared future có thể làm các consumer còn lại cũng thấy TimeoutException. Nếu cần timeout riêng cho từng view, thiết kế wrapper stage độc lập và policy rõ ràng, không mutate source chung.

**Timeout result, cancellation và resource cleanup phải phối hợp**: sau khi caller nhận TimeoutException, request HTTP/DB underlying có thể vẫn chạy nếu không có cơ chế hủy phù hợp.

## 20. Chương trình Java: `orTimeout` không interrupt Supplier đang chạy

Tạo `TimeoutNoStopDemo.java`:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutNoStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService ex =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        try {
            CompletableFuture<Integer> cf =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return 42;
                        } catch (InterruptedException e) {
                            interrupted.set(true);
                            Thread.currentThread().interrupt();
                            return -1;
                        } finally {
                            finished.countDown();
                        }
                    }, ex);

            if (!started.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "worker not started");
            }

            CompletableFuture<Integer> returned =
                    cf.orTimeout(0, TimeUnit.MILLISECONDS);

            System.out.println(
                    "orTimeout same object = " +
                            (cf == returned));

            try {
                cf.join();
            } catch (CompletionException e) {
                System.out.println(
                        "timeout cause = " +
                                e.getCause()
                                        .getClass().getSimpleName());
            }

            System.out.println(
                    "worker finished before release = " +
                            (finished.getCount() == 0));

            release.countDown();

            if (!finished.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError(
                        "worker not finished");
            }

            System.out.println(
                    "worker saw interrupt = " +
                            interrupted.get());
            System.out.println(
                    "future exceptional after worker finish = " +
                            cf.isCompletedExceptionally());
        } finally {
            release.countDown();
            ex.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 TimeoutNoStopDemo.java
java TimeoutNoStopDemo
```

```text
orTimeout same object = true
timeout cause = TimeoutException
worker finished before release = false
worker saw interrupt = false
future exceptional after worker finish = true
```

Chương trình dùng timeout **0 milliseconds** để chủ động chuyển trạng thái ngay sau khi worker đã bắt đầu. Nó không phụ thuộc vào thời gian ngủ hoặc tải scheduler. `cf.orTimeout(...)` cho TimeoutException, nhưng worker vẫn **đang chờ latch** cho đến khi chúng ta gọi `release.countDown()`.

Đây là ví dụ rõ rằng **timeout trạng thái future không tự dừng computation**. Khi worker chạy xong và trả 42, trạng thái exception của `cf` đã được chốt trước đó nên không bị ghi đè bởi kết quả 42.

`completeOnTimeout(fallback, ...)` hoạt động khác ở **kết quả công bố** (success fallback) nhưng cũng không mặc nhiên ngừng Supplier phía dưới.

## 21. Khi dùng `get(timeout)`, `join()` và xử lý interruption

`Future.get(timeout, unit)` phù hợp khi một caller buộc phải chặn trong tối đa một khoảng. Nếu hết thời gian chờ:
- Nó ném `TimeoutException`.
- Future có thể vẫn pending, và underlying work có thể vẫn chạy.
- Nếu muốn yêu cầu hủy task, caller phải **quyết định gọi `cancel`** (với implementation phù hợp) hoặc gửi cancellation token/provider request riêng.

`CompletableFuture.join()` không có overload timeout từ Java 8; thường dùng `get(timeout, unit)` khi cần giới hạn thời gian chờ trên caller. JDK mới có `orTimeout`, nhưng như đã thấy, nó thay đổi **trạng thái future**, không phải tương đương một lần `get(timeout)`.

**Interruption của caller khi chờ không đồng nghĩa interrupt worker**:
- `Future.get()`/`get(timeout)` có thể ném `InterruptedException` nếu **thread đang chờ** bị interrupt.
- Việc thread chờ bị interrupt không tự ra lệnh hủy worker ở chỗ khác.
- Nếu ứng dụng quyết định hủy khi caller bị interrupt, phải gọi cancel đúng handle, bảo toàn interrupt status theo policy và cleanup tài nguyên cần thiết.
- `join()` dùng exception unchecked, không khai báo `InterruptedException`; đừng nhầm nó với contract chờ có thể interrupt của `get()`.

Đừng gọi `get`/`join` trong một task ở **single-thread executor** khi kết quả đang chờ cũng chỉ có thể chạy trên executor đó: có thể tạo **thread starvation deadlock**. Dùng stage composition không blocking (`thenCompose`, `thenCombine`) khi phù hợp.

## 22. I/O là trường hợp cần đọc contract của provider

Một `CompletableFuture` có thể đại diện cho:
- Supplier tự viết nằm trên executor.
- Một callback được kích hoạt khi RPC kết thúc.
- Một Future đã được bridge từ thư viện khác.
- Một HTTP exchange mà provider giữ handle hủy.
- Một query JDBC blocking nằm trong thread riêng.

**Không có một nút cancel chung chắc chắn dừng tất cả những đối tượng này.**

Ví dụ đặc biệt có tài liệu chính thức: `java.net.http.HttpClient.sendAsync(...)` của **default HttpClient implementation** có thể trả một future hủy được; JavaDoc nói việc gọi `cancel(true)` trên cancelable future **cố gắng hủy HTTP exchange** và giải phóng tài nguyên. Tuy nhiên:
- Không bảo đảm request chưa được gửi hoặc server chưa xử lý.
- Cancellation có thể được xử lý bất đồng bộ.
- HTTP/1.1 có thể đóng connection đột ngột; HTTP/2 có thể reset stream.
- Đây là **cơ chế bổ sung riêng của implementation HttpClient**, không phải hợp đồng chung rằng `CompletableFuture.supplyAsync(...).cancel(true)` sẽ interrupt mọi Supplier.

Với JDBC blocking, kiểm tra `Statement.cancel()`, query timeout, connection timeout và khả năng driver đáp ứng; không suy từ CompletableFuture cancellation ra DB đã ngừng truy vấn. Với API gửi message/file, tìm cancellation hoặc close handle do thư viện cung cấp. Có provider không hỗ trợ hủy request đã gửi.

**Không dùng `Thread.stop()` để cưỡng chế**, vì nó có thể làm hỏng invariant/trạng thái đồng bộ và là API không phù hợp với thiết kế hiện đại. Dùng interruption hợp tác, provider cancellation và quản lý tài nguyên rõ ràng.

## 23. Hủy không rollback side effect

Giả sử task thực hiện:
1. Ghi hàng vào database.
2. Gửi email.
3. Tính kết quả.
4. Hoàn thành future.

Nếu caller cancel giữa bước 2 và 3:
- Future có thể báo canceled.
- Hàng DB và email **có thể đã tồn tại**.
- Retry ngây thơ có thể tạo duplicate side effect.
- Không thể chỉ nhìn `isCancelled()` mà kết luận “giao dịch chưa xảy ra”.

Các kỹ thuật cần thiết ở domain phù hợp:
- **Idempotency key** cho thao tác có thể retry.
- Transaction có ranh giới rõ với DB, hiểu rằng transaction local không tự rollback một HTTP call đã thực hiện.
- **Compensating action** nếu nghiệp vụ cho phép đảo thao tác đã commit.
- Trạng thái riêng **cancel requested**, **cancelling**, **stopped**, **completed**, **unknown/compensation needed** khi theo dõi job dài.
- Chốt quyền sở hữu thao tác (owner) trước khi thực hiện cancel chung.
- Deadline và chính sách kiểm tra token ở những điểm có thể dừng an toàn.

**Cancellation là một yêu cầu thay đổi luồng thực thi**, không phải đảm bảo “không có hậu quả đã xảy ra”. Trong hệ thống thanh toán/đặt hàng, phân biệt hủy UI request và hủy nghiệp vụ của giao dịch đặc biệt quan trọng.

## 24. Mô hình API hủy có ownership rõ ràng

Đối với công việc do ứng dụng tự tạo, có thể đóng gói:

```text
JobHandle<T>
  ├── CompletableFuture<T> result     // Công bố kết quả
  ├── CancellationToken token         // Tín hiệu dừng hợp tác
  ├── Future<?> taskHandle             // Nếu gửi bằng ExecutorService.submit
  └── close/cancel resourceHandle      // Nếu provider có API riêng
```

Đây là sơ đồ kiến trúc, không bắt buộc mọi job phải có đủ bốn trường.

Một method `JobHandle.cancel()` do ứng dụng định nghĩa có thể:
1. Ghi `cancelRequested` một cách thread-safe.
2. Gửi tín hiệu tới worker qua token.
3. Nếu sở hữu `FutureTask`, cân nhắc `taskHandle.cancel(true)`.
4. Nếu sở hữu provider request, gọi API cancel/abort/close theo contract.
5. Công bố kết quả canceled/failed cho consumer khi đúng policy.
6. Trả trạng thái yêu cầu đã nhận, **không tuyên bố worker đã dừng nếu chưa quan sát**.

**Không chỉ giữ CompletableFuture rồi vứt mọi handle phía dưới** nếu tính năng yêu cầu hủy chủ động. Nhưng cũng không hủy một nguồn dùng chung khi chỉ một caller không muốn nhận kết quả nữa.

Các task phối hợp nên biết ai sở hữu root cancellation token. Nếu nhiều branch có thể cancel độc lập, thiết kế “consumer ownership” hoặc reference counting để tránh một bên cắt công việc của bên khác.

## 25. Race: completion và cancellation cạnh tranh nhau

`CompletableFuture` cho phép nhiều thread đua hoàn thành:

```java
boolean a = cf.complete(value);
boolean b = cf.cancel(true);
```

Đoạn minh họa có `cf` và `value` đã định nghĩa. **Một trong các operation** có thể thắng nếu chúng đua khi future chưa xong. Không được dựa vào thứ tự code trên hai thread để đoán ai sẽ thắng trong mọi lần chạy.

- `complete(value)` trả true nếu lời gọi đó chuyển future từ chưa hoàn thành sang hoàn thành bình thường.
- `cancel` đưa future vào trạng thái hủy khi có thể; return value của `cancel` có ngữ nghĩa riêng “future nay bị hủy”, không đồng nhất máy móc với return value của `complete`.
- `completeExceptionally(ex)` có thể thắng race như một kết quả lỗi khác.
- Caller có thể thấy `cancel` quá muộn vì task đã xong bình thường.
- Ngay cả khi cancel thắng trạng thái kết quả, side effect của worker có thể tiếp tục.

Để tránh race làm hỏng dữ liệu nghiệp vụ, **đặt điểm kiểm tra cancel ở ranh giới commit**, giữ thao tác transaction/idempotency tương ứng, và không cho rằng boolean returned của một thao tác đủ chứng minh toàn bộ trạng thái hệ thống.

`obtrudeValue`/`obtrudeException` (API đặc biệt của CompletableFuture) có thể cưỡng chế thay đổi giá trị được quan sát sau completion trong trường hợp recovery, nhưng không nên dùng để “hồi sinh” task bị cancel: dependent stages có thể đã quan sát trạng thái cũ, tạo hệ thống không nhất quán.

## 26. Hủy giữa pipeline: lý do cần phân tách cancel propagation và failure propagation

Một pipeline có thể là:

```text
source supplyAsync ── thenApply ── thenCompose(inner IO)
       │                  │               │
       │                  └── metrics      └── request provider
       └── shared by other consumers
```

Nếu hủy:
- **Stage cuối**: thường chỉ future cuối đổi trạng thái; source và inner task không tự nhận lệnh cancel.
- **Source**: dependent chưa hoàn tất có thể nhận exceptional completion; nhưng underlying source Supplier có thể vẫn chạy.
- **Inner I/O**: nếu provider có cancel handle, cần gọi theo ownership của request đó, không suy ra từ việc outer future bị hủy.
- **Một nhánh metrics**: cancel branch chỉ nên bỏ phần metric nếu đúng policy, không mặc định cancel toàn bộ source.

**Khả năng lan truyền lỗi trong đồ thị completion không tương đương một cây scope quản lý hủy**. Java 8 CompletableFuture tập trung vào quan hệ phụ thuộc kết quả; nó không áp đặt ownership/cancellation scope kiểu “cha hủy thì mọi con và mọi resource phải dừng”.

Nếu nghiệp vụ cần một scope mà tất cả tác vụ con phải được dừng khi scope kết thúc, hãy dùng framework/quy tắc lifecycle phù hợp và kiểm thử, không chỉ dựa vào `thenCompose`/`allOf`.

## 27. Executor shutdown không thay cho future cancellation

Với `ExecutorService`:
- `shutdown()`: ngừng nhận task mới, cho phép task đã gửi tiếp tục; **không có nghĩa dừng ngay**.
- `shutdownNow()`: cố ngừng task đang chạy (thường qua interrupt), ngăn task đang chờ bắt đầu và trả danh sách queued tasks; **không bảo đảm task đang chạy đã kết thúc**.
- `awaitTermination(timeout, unit)`: chờ executor thực sự kết thúc hoặc hết thời gian chờ.
- `ExecutorService.close()` ở các JDK hiện đại có semantics quản lý vòng đời riêng; không nhầm với `cancel` của một stage đơn lẻ.

Không tự shutdown một executor **được inject/dùng chung** chỉ vì một request/future bị hủy. Điều đó có thể làm hỏng request khác và gây RejectedExecutionException cho dependent stage còn cần được lập lịch.

Ngược lại, nếu bạn **tự tạo pool cho một job**, người sở hữu cần đảm bảo đóng và chờ chấm dứt có giới hạn phù hợp, đặc biệt khi worker bỏ qua interrupt. Mẫu cleanup:

```java
executor.shutdown();
try {
    if (!executor.awaitTermination(
            5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là đoạn minh họa trong phương thức, giả định `executor` thuộc quyền sở hữu của thành phần đang đóng; không phải recipe đóng mọi pool share trong server. Sau `shutdownNow` có thể vẫn cần chờ/giám sát nếu nhiệm vụ đòi xác nhận dừng.

## 28. Kiểm thử hủy mà không dựa vào `sleep` may rủi

Test cancellation khó ở **races** và timing. Thay vì “sleep 50ms rồi cancel”, hãy:
- Dùng `CountDownLatch started` để xác nhận worker **thật sự đã bắt đầu**.
- Dùng `CountDownLatch release` để giữ worker ở một đoạn chặn có kiểm soát.
- Dùng `AtomicBoolean interrupted`/`CountDownLatch finished` để quan sát có interrupt và worker đã thoát.
- Đặt **timeout hữu hạn** khi chờ latch, tránh test suite treo vô tận.
- Trong `finally`, luôn release latch và shutdown executor thử nghiệm.
- Test riêng **future state** và **worker/resource state**.
- Test parent/child/sibling và `thenCompose` inner future.
- Test aggregate `allOf`/`anyOf` không mặc định hủy sources/losers.
- Test `Future.submit cancel(true)` với blocking operation có contract interrupt.
- Test `CompletableFuture.supplyAsync cancel(true)` với cùng kịch bản chờ latch, quan sát **không interrupt**.
- Test `get(timeout)` khác `orTimeout`, và cả trường hợp task hoàn thành ngay trước deadline.
- Kiểm tra cancellation không tạo side effect mới sau điểm dừng an toàn; với network/DB cần integration tests theo provider thực.
- Kiểm tra cleanup và hủy lặp nhiều lần không gây leak hoặc lỗi state.

**Không assert chính xác milliseconds từ `Thread.sleep`**. Các ví dụ trong bài tạo điều kiện đồng bộ hóa để stdout đáng tin và chỉ kiểm tra kết quả sau khi trạng thái đã được xác nhận.

Đối với queue/scheduler, thêm test capacity/rejection trong môi trường tách biệt. Đừng test bằng cách cố tạo hàng nghìn task chặn vô hạn lên common pool, vì chúng có thể ảnh hưởng cả test suite.

## 29. Các lỗi phổ biến và cách sửa

| Sai lầm | Vấn đề | Cách đúng hơn |
| --- | --- | --- |
| `cf.cancel(true)` rồi nghĩ worker chắc chắn bị interrupt | CompletableFuture chuẩn bỏ qua mayInterruptIfRunning | Giữ task/provider cancel handle riêng |
| `cf.isDone()` rồi suy resource đã giải phóng | Future có thể đã cancel nhưng worker còn chạy | Theo dõi worker completion/cleanup |
| `dependent.isCancelled() == false` rồi nghĩ không có lỗi | Dependent có thể exceptionally do parent cancellation | Kiểm tra `isCompletedExceptionally`/cause |
| Hủy child mà không hủy nguồn dùng riêng khi cần | Underlying task tiếp tục chạy | Ownership và explicit cancellation |
| Hủy child làm dừng source dùng chung | Ảnh hưởng consumer khác nếu tự viết propagation sai | Phân biệt shared và owned scope |
| Hủy composed future rồi nghĩ inner future đã hủy | Không có propagation ngược bắt buộc | Giữ handle của inner |
| `allOf.cancel` rồi tin các thành phần bị hủy | Aggregate chỉ là result stage | Hủy source riêng theo policy |
| `anyOf` xong rồi nghĩ loser tự dừng | Loser có thể còn chạy/side effects | Chủ động hủy loser nếu an toàn |
| `orTimeout` rồi tưởng Supplier đã dừng | Timeout chỉ chốt trạng thái CF | Provider timeout/cancel/token |
| `get(timeout)` ném TimeoutException rồi nghĩ future tự cancelled | Timeout chỉ giới hạn thời gian chờ caller | Quyết định cancel riêng |
| Bắt `CancellationException` và biến thành thành công mọi lúc | Che ý định hủy của người dùng | Policy rõ, chỉ recover khi phù hợp |
| Bắt `InterruptedException` rồi bỏ qua cờ | Task có thể tiếp tục thay vì dừng | Propagate hoặc restore + exit |
| Dùng `Thread.interrupted()` khi chỉ muốn quan sát | API static xóa cờ interruption | `isInterrupted()` |
| Xem `Future.cancel(true)` như dừng cưỡng chế | Interrupt chỉ là tín hiệu | Cooperative checkpoints và cleanup |
| Sử dụng `Thread.stop()` để bắt buộc dừng task | Không an toàn cho invariants/resources | Không sử dụng; dùng interruption/provider cancel |
| Shutdown pool share khi một future cancel | Hủy luôn các request khác | Chỉ owner quản lý executor |
| Không đóng executor tự tạo | Thread/resource leak | Shutdown/awaitTermination |
| Task bị hủy sau khi ghi DB rồi nghĩ transaction rollback | Side effects có thể đã commit | Idempotency/transaction/compensation |
| Chỉ test bằng `sleep` | Flaky do scheduler | Latches/timeouts hữu hạn |
| Đọc kết quả future mà không phân biệt `get`/`join` | Khác checked/unchecked exceptions | Xử lý đúng exception boundary |
| Dùng token AtomicBoolean nhưng worker không kiểm tra | Token không tự ngắt computation | Checkpoints và interruptible waits |
| Gọi cancel trên bridge mà không đọc provider contract | Bridge có thể chỉ hủy view | API hủy chính thức của provider |
| Bỏ qua cancellation khi retry | Retry có thể làm tác vụ vừa hủy chạy lại | Kiểm tra token/deadline trước retry |
| Coi `HttpClient.sendAsync` mặc định là mọi CompletableFuture | Đây là provider có hủy đặc biệt | Dựa vào JavaDoc riêng của thư viện |

**Không nên thêm `cancel(true)` vào mọi nhánh như một “biện pháp an toàn” mà không có ownership và policy rõ ràng.** Hủy nhầm request chia sẻ có thể tệ hơn giữ một công việc đang chờ.

## 30. Quy trình thiết kế hủy tác vụ đúng trong production

Trước khi viết code, trả lời các câu hỏi:

1. **Ai yêu cầu hủy?** Người dùng rời trang, server timeout, shutdown, lỗi upstream hay consumer không còn cần kết quả?
2. **Ai sở hữu công việc?** Source dùng riêng hay được nhiều subscriber dùng chung?
3. **Mục tiêu hủy là gì?** Chỉ từ chối kết quả, yêu cầu worker dừng, cancel remote request, rollback transaction hay giải phóng resource?
4. **Handle nào thực sự có quyền?** CompletableFuture, FutureTask, token, HttpClient response, JDBC Statement, subscription hoặc resource handle?
5. **Tác vụ đã bắt đầu chưa?** Nếu chưa, có thể ngăn scheduling; nếu đã chạy, cần cooperative stop.
6. **Tại điểm nào an toàn để dừng?** Giữa hai bước, trước commit, sau cleanup, trong retry/backoff?
7. **Có khả năng side effect đã xảy ra không?** Bổ sung idempotency/compensation khi cần.
8. **Nếu tác vụ không phản hồi interrupt, kế hoạch là gì?** Timeout, đóng resource theo provider, giám sát và isolation.
9. **Các stage phụ thuộc nhận cancellation thế nào?** Cần propagate exception, skip, recover hay hủy toàn bộ scope?
10. **Đã phân biệt result state và worker state chưa?** Đừng báo “stopped” chỉ vì `isCancelled()==true`.
11. **Có dễ kiểm thử không?** Inject executor/token hoặc latches, tránh phụ thuộc sleep/timing.
12. **Tài nguyên được ai đóng?** Executor ownership, connection, file, transaction và listener.
13. **Có ghi log nguyên nhân hủy không?** User cancel, timeout và system shutdown cần metrics khác nhau.
14. **Có yêu cầu version không?** `CompletableFuture.cancel` có từ Java 8; `orTimeout`/`completeOnTimeout` là Java 9+, một số thư viện provider còn có semantics riêng.

Một API cancellation tốt không nhất thiết **dừng ngay mọi thread**; điều quan trọng là đưa ra **hợp đồng trung thực**: “đã nhận yêu cầu hủy”, “kết quả không còn được công bố”, “task đã ngừng” và “resource đã được giải phóng” là các mốc có thể khác nhau.

## 31. Câu hỏi tự kiểm tra

**Câu 1.** `CompletableFuture.cancel(true)` có bắt buộc interrupt Supplier đã chạy trong `supplyAsync`?  
**Đáp án:** Không. Tham số mayInterruptIfRunning không có hiệu lực trong CompletableFuture chuẩn.

**Câu 2.** Sau khi `cf.cancel(true)` thành công, `cf.isDone()` trả gì?  
**Đáp án:** true, vì cancel là một trạng thái hoàn thành kết quả; không chứng minh worker ngừng.

**Câu 3.** Khi nguồn `cf` bị cancel, `cf.thenApply(...)` chưa hoàn tất có thể ở trạng thái nào?  
**Đáp án:** Hoàn thành exceptionally với `CompletionException` chứa `CancellationException`; dependent có thể `isCancelled()==false`.

**Câu 4.** `join()` trên một CompletableFuture bị cancel trực tiếp thường ném gì?  
**Đáp án:** `CancellationException`.

**Câu 5.** `handle(...)` trên stage bị cancel có thể trả fallback không?  
**Đáp án:** Có, nếu callback được thiết kế để biến lỗi thành giá trị, nhưng làm vậy cần đúng chính sách nghiệp vụ.

**Câu 6.** Hủy một dependent stage có tự hủy parent và các sibling không?  
**Đáp án:** Không, cancellation ngược không mặc định áp dụng.

**Câu 7.** Hủy stage `thenCompose` đã flatten có chắc inner future dừng không?  
**Đáp án:** Không. Nếu cần dừng inner task, giữ handle/cancellation token riêng.

**Câu 8.** Hủy `allOf(a,b)` có tương đương `a.cancel(true); b.cancel(true);` không?  
**Đáp án:** Không. CompletableFuture chuẩn không tự hủy các source như vậy.

**Câu 9.** `anyOf` hoàn thành sớm có dừng loser không?  
**Đáp án:** Không. Các future khác có thể còn hoạt động.

**Câu 10.** `Future` từ `ExecutorService.submit` có thể khác CompletableFuture ở đâu?  
**Đáp án:** Nó có thể quản lý trực tiếp Callable/Runnable và cố interrupt worker khi `cancel(true)`.

**Câu 11.** `Future.cancel(true)` có bảo đảm computation dừng ngay?  
**Đáp án:** Không. Interruption cần code/API hợp tác và có thể không đủ cho mọi I/O.

**Câu 12.** Khi bắt `InterruptedException` nhưng không ném tiếp, cách xử lý thường cần gì?  
**Đáp án:** Khôi phục flag bằng `Thread.currentThread().interrupt()` và rời khỏi/đi theo luồng cancellation phù hợp.

**Câu 13.** `get(timeout)` tự cancel Future không?  
**Đáp án:** Không. Nó chỉ giới hạn thời gian caller chờ và có thể ném TimeoutException.

**Câu 14.** `orTimeout`/`completeOnTimeout` tạo một future mới tách biệt source không?  
**Đáp án:** Không. Chúng trả chính CompletableFuture receiver, làm thay đổi trạng thái receiver khi hết hạn.

**Câu 15.** `orTimeout` đã xảy ra thì Supplier đang đợi latch có tự nhận interrupt không?  
**Đáp án:** Không mặc định. Cần tín hiệu hủy của task hoặc provider.

**Câu 16.** Vì sao cancellation không đồng nghĩa rollback database?  
**Đáp án:** Side effect đã commit có thể vẫn tồn tại dù kết quả future bị hủy.

**Câu 17.** Tại sao `AtomicBoolean` token chưa đủ để ngắt một read I/O chặn vô hạn?  
**Đáp án:** Worker không thể kiểm tra token khi đang chặn; cần provider timeout/cancel/close hoặc interruption được hỗ trợ.

**Câu 18.** Java HttpClient mặc định có thể khác CompletableFuture thông thường ở điểm gì?  
**Đáp án:** Future từ `sendAsync` có contract cancelable đặc biệt, có thể cố hủy HTTP exchange; vẫn không bảo đảm server chưa nhận/xử lý request.

**Câu 19.** Có nên gọi `shutdownNow` lên executor toàn ứng dụng khi một user cancel một request?  
**Đáp án:** Không. Executor dùng chung có thể phục vụ nhiều request; chỉ owner quản lý shutdown.

**Câu 20.** Test nào phân biệt được “future canceled” và “worker không interrupt”?  
**Đáp án:** Dùng latch xác nhận worker bắt đầu, cancel future, kiểm tra worker còn đợi và cờ interrupt, sau đó release và xác nhận worker hoàn tất.

## 32. Tổng kết

- **`CompletableFuture.cancel` chủ yếu là exceptional completion của một kết quả**, không phải lệnh dừng computation phía dưới. Tham số `mayInterruptIfRunning` không được CompletableFuture chuẩn dùng để interrupt.
- **Propagation trong dependent stages chủ yếu là propagation của trạng thái**: parent cancel có thể khiến các dependent chưa hoàn tất lỗi; child cancel không tự hủy parent/sibling/inner task.
- **`allOf`/`anyOf` không tự xử lý cancellation của mọi source**; nếu cần fail-fast hoặc cancel losers phải có policy và handle thật.
- **`ExecutorService.submit` trả Future có thể yêu cầu interrupt** theo implementation, nhưng interrupt vẫn là cơ chế hợp tác, không phải hard stop.
- **`get(timeout)` chỉ giới hạn chờ; `orTimeout`/`completeOnTimeout` thay đổi chính CompletableFuture**, nhưng không tự hủy mọi I/O hoặc worker.
- **Cooperative token, provider cancellation, deadline, cleanup và ownership** là các công cụ cần thiết khi mục tiêu là ngừng tác vụ hoặc giải phóng tài nguyên thật.
- **Future canceled ≠ worker stopped ≠ request undone ≠ DB rollback.** Hãy đo và báo cáo từng trạng thái đúng ý nghĩa.
- Các API chuẩn Java 8+ vẫn hiện hành; khi dùng bổ sung Java 9+ hoặc API của thư viện I/O, kiểm tra version và hợp đồng cụ thể.

### Tài liệu API chính thức đang áp dụng

- [`CompletableFuture` (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `cancel`, `join`, `get`, `isCancelled`, dependent completion, `orTimeout` và `completeOnTimeout`.
- [`Future` (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): hợp đồng `cancel(mayInterruptIfRunning)`, `get(timeout)` và trạng thái hủy.
- [`FutureTask` (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/FutureTask.html): computation có thể hủy trực tiếp.
- [`ExecutorService` (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `shutdown`, `shutdownNow`, `awaitTermination`.
- [`CompletionStage` (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html): `thenApply`, `thenCompose`, `handle`, `whenComplete` và semantics dependent stages.
- [`Thread` (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html): `interrupt`, `isInterrupted`, `interrupted`.
- [`CancellationException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CancellationException.html), [`CompletionException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionException.html) và [`TimeoutException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/TimeoutException.html).
- [`HttpClient` (Java SE 26)](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): `sendAsync` và hợp đồng cancellation đặc biệt của HTTP exchange.
