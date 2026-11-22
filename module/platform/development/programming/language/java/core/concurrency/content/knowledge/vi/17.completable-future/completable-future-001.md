# CompletionStage và CompletableFuture khác Future truyền thống

## 1. Phân biệt ba abstraction trước khi chạy task

Một ứng dụng Java có thể cần một kết quả **sau này**. Nhưng có ba nhu cầu khác nhau: giữ handle để đợi, khai báo cách xử lý **khi kết quả đến**, và chủ động quyết định khi nào kết quả được công bố.

- **Future** là hợp đồng kết quả của một tác vụ đã được nộp: `get()` có thể block caller, `isDone()` cho biết đã có trạng thái terminal, `cancel(...)` yêu cầu hủy theo hợp đồng implementation. Interface Future truyền thống không cho ghép callback phụ thuộc bằng `thenApply()`.
- **CompletionStage** là giao diện mô tả *đồ thị các giai đoạn hoàn tất*: biến đổi result, nối tác vụ phụ thuộc, ghép hai nhánh hoặc phục hồi lỗi. Nó không đồng nghĩa một thread mới hay parallelism.
- **CompletableFuture** vừa là Future vừa là CompletionStage; lớp này còn có `complete(value)`, `completeExceptionally(error)`, `join()`, `getNow(...)`, `supplyAsync()`, các factory cho stage đã hoàn tất.

**Phân biệt:** Future/CompletionStage là hợp đồng Java API, còn pool/thread là tài nguyên chạy computation; hai tầng này tác động nhau nhưng không đồng nhất. Một API async có thể được thực thi bằng worker dùng I/O blocking; việc trả về nhanh cho caller không chứng minh non-blocking I/O.

| Vấn đề | Future | CompletionStage | CompletableFuture |
| --- | --- | --- | --- |
| Chờ trực tiếp kết quả | `get()` | Chuyển qua `toCompletableFuture()` khi cần bridge | `get()`, `join()` |
| Tạo dependent stage | Không có API compose chuẩn | `thenApply`, `thenCompose`, `thenCombine`... | Kế thừa interface đó |
| Chủ động hoàn tất giá trị/lỗi | Không có qua interface | Không có qua interface | `complete`, `completeExceptionally` |
| Kiểm tra terminal state | `isDone`, `isCancelled` | Quan sát qua stages | Có cả API Future và stage |
| Quyền của caller | Chờ/hủy handle theo contract | Ghép dependent stage | Có thể tự complete object nếu được trao source thật |

## 2. Future.get và khái niệm điểm chờ

```java
Future<Integer> a = executor.submit(() -> 20);
Future<Integer> b = executor.submit(() -> 22);
int sum = a.get() + b.get();
```

A và B có thể chạy đồng thời khi executor có tài nguyên, vì cả hai đã được nộp trước khi caller bắt đầu đợi. Nhưng `get()` là một **điểm đồng bộ có thể block**. Nếu code submit A, get A rồi mới submit B, hai công việc độc lập có thể bị tuần tự hóa không cần thiết.

CompletionStage mô tả dependency trước, và chỉ cần block ở ranh giới tiêu thụ kết quả:

```java
CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 20, executor);
CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 22, executor);
CompletableFuture<Integer> sum = a.thenCombine(b, Integer::sum);
```

Ở đây `thenCombine` chỉ chạy BiFunction khi cả hai source thành công. Nó **không tự khởi tạo** tác vụ a/b hay tạo lõi CPU mới. Nếu task B thật sự phụ thuộc giá trị A, dùng `thenCompose` để khởi động B sau A; nếu chỉ biến đổi một giá trị, dùng `thenApply`.

```text
Một nguồn: A ──thenApply(transform)──> U
Phụ thuộc: A ──thenCompose(startB)───> B
Độc lập:   A ─┐
              ├──thenCombine(combine)──> kết quả chung
           B ─┘
```

Các bài sau sẽ dạy hợp đồng chi tiết của từng combinator. Đối với bài nền tảng này, hãy đọc graph theo **đầu vào phụ thuộc** và **điều kiện hoàn tất**, không suy ra thứ tự scheduling.

## 3. Ví dụ Java 17: handle truyền thống so với pipeline

Lưu thành `FutureAndCompletionStageDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureAndCompletionStageDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> ordinary = executor.submit(() -> 20);
            int oldStyle = ordinary.get() + 22;

            CompletableFuture<Integer> pipeline =
                    CompletableFuture.supplyAsync(() -> 20, executor)
                            .thenApply(value -> value + 22);

            System.out.println("Future=" + oldStyle);
            System.out.println("CompletionStage=" + pipeline.join());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

```bash
javac FutureAndCompletionStageDemo.java
java FutureAndCompletionStageDemo
```

Stdout xác định khi các task thành công:

```text
Future=42
CompletionStage=42
```

Bên Future, thread `main` lấy 20 rồi cộng 22. Với CompletableFuture, phép cộng được đăng ký như một dependent stage và thread `main` chỉ gọi `join()` ở cuối. Không có cam kết callback `thenApply` sẽ chạy trên worker cụ thể: nếu source chưa hoàn tất, completer thread có thể chạy callback; nếu source đã xong, thread đăng ký callback cũng có thể chạy nó.

`shutdown()` chặn task mới nhưng không xóa task đã nhận; `awaitTermination` chỉ chờ executor dừng trong một giới hạn. Một I/O task production vẫn cần deadline và cleanup của riêng mình. Ví dụ có hai worker chỉ để minh họa code, không phải cấu hình mặc định an toàn cho mọi tải.

## 4. Completion state khác execution state

Một CompletableFuture có thể pending, hoàn tất bình thường với giá trị (kể cả `null`), hoàn tất với exception, hoặc bị cancel (một dạng exceptional completion). `isDone()` có thể là true trong cả normal, exceptional và canceled; **nó không chứng minh thành công**.

`new CompletableFuture<>()` tạo một promise pending. Một producer có thể gọi `complete(result)` hoặc `completeExceptionally(cause)`; lần hoàn tất thắng cuộc đua thông thường sẽ quyết định terminal outcome. Các API `orTimeout` hoặc `completeOnTimeout` cũng có thể tranh quyền hoàn tất. Việc kết quả đã terminal không bảo đảm supplier/I/O bên dưới đã dừng, vì trạng thái Future và vòng đời worker là hai chuyện khác nhau.

Nếu source exceptional, callback normal như `thenApply` thường không được gọi; dependent stage chuyển theo exceptional completion. `exceptionally`/ `handle` có thể phục hồi theo hợp đồng; `whenComplete` chủ yếu dùng để quan sát log/metrics và không mặc định biến lỗi thành success. Lỗi ở dependent callback không tự làm source đã thành công trở lại trạng thái failure.

```java
CompletableFuture<Integer> value =
        CompletableFuture.<Integer>failedFuture(
                new IllegalArgumentException("invalid"))
                .exceptionally(error -> 0)
                .thenApply(number -> number + 1);
// value.join() == 1
```

`Future.get()` báo task failure qua checked `ExecutionException` và có thể ném `InterruptedException`; `CompletableFuture.join()` báo lỗi dưới dạng unchecked `CompletionException` trong trường hợp thông thường. Cancellation cần xử lý riêng. Những bài về exception sẽ phân tích cause chain, timeout và lỗi riêng của callback.

## 5. Chọn API trả về mà không lộ quyền hoàn tất

Phần code **sở hữu producer** có thể giữ một CompletableFuture private để hoàn tất sau khi nhận callback NIO hoặc sự kiện bên ngoài. Caller thường chỉ cần ghép các bước: `CompletionStage` phù hợp làm kiểu API. Nhưng **chỉ đổi return type thành interface không nhất thiết chặn caller ép kiểu** nếu đối tượng CompletableFuture thật bị trao trực tiếp. `minimalCompletionStage()` và `copy()` có hợp đồng cụ thể về việc giữ nguồn private; bài riêng sẽ kiểm chứng.

Giữ dữ liệu kết quả immutable hoặc công bố an toàn nếu chia sẻ giữa threads. Một stage có thể complete chính xác nhưng payload vẫn là một mutable object bị hai thread sửa đồng thời. `ThreadLocal` cũng không tự truyền qua stage chạy trên thread khác.

## 6. Chính sách nơi chạy callback và những giới hạn

- Callback **không Async** như `thenApply` có thể chạy trên completer thread hoặc thread gọi đăng ký sau khi source hoàn tất. Đừng đặt I/O blocking dài ở completion path nếu không kiểm soát latency.
- `thenApplyAsync(fn)` dùng default asynchronous execution facility (thường là common ForkJoinPool khi không truyền executor); nó không hứa tạo một thread riêng cho callback.
- `thenApplyAsync(fn, executor)` giao scheduling cho executor đó. Custom executor có thể giới hạn queue, worker hoặc từ chối callback khi shutdown/saturated; lỗi scheduling cũng cần được quan sát.
- `CompletableFuture.cancel(true)` không có bảo đảm ngắt supplier đang chạy theo semantics của cancel trên FutureTask. Timeout của future cũng không tự hủy I/O. Cần cancellation hợp tác, I/O timeout và lifecycle rõ ràng.

Một callback phụ thuộc mà gọi `join()` để đợi một task cần chính worker đang bị chiếm trong pool một worker có thể tự gây deadlock/starvation. Composition diễn đạt dependency trực tiếp và tránh giữ worker chỉ để chờ.

## 7. Checklist ra quyết định và tự luyện

| Câu hỏi thiết kế | Hướng xử lý |
| --- | --- |
| Chỉ cần handle để đợi/hủy? | Future khi hợp đồng không đòi compose |
| Cần mô tả tiếp xử lý khi có result? | CompletionStage và các dependent stages |
| Ai được phép complete kết quả? | Giữ CompletableFuture nguồn ở component sở hữu |
| B phụ thuộc dữ liệu A? | thenCompose thay nested future hoặc join trong worker |
| A/B độc lập, cần kết quả chung? | thenCombine hoặc aggregate phù hợp |
| Callback tiêu CPU hoặc blocking? | Chọn executor/capacity và quản lý lifecycle |
| Cần timeout và hủy? | Phân biệt chờ, completion, interrupt và underlying operation |

Tự trả lời bằng nội dung ví dụ:

1. Vì sao Future truyền thống không có thenApply nhưng CompletableFuture có?
2. Vì sao một API trả CompletionStage không bảo đảm luôn tạo task chạy song song?
3. Điều gì xảy ra khi mapper phụ thuộc source lỗi?
4. Khi nào B phải dùng thenCompose thay cho thenCombine?
5. Vì sao isDone không đủ để chứng minh underlying computation đã dừng?
6. Có những rủi ro gì nếu trao nguyên CompletableFuture mutable ra API public?

**Điểm cần nhớ:** Future là **handle nhận kết quả**, CompletionStage là **hợp đồng ghép bước phụ thuộc**, và CompletableFuture triển khai cả hai với khả năng complete thủ công. Công việc nền còn cần policy executor, error, timeout và ownership độc lập; các bài tiếp theo đi sâu vào từng contract này.
