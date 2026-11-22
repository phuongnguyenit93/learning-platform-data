# Phân biệt bao quanh một lời gọi đồng bộ với toàn bộ tác vụ bất đồng bộ

## 1. Vấn đề cốt lõi: “method đã trả về” không có nghĩa “công việc đã hoàn tất”

Trong **Aspect-Oriented Programming (AOP)**, **around advice** có thể bao quanh một **join point** được **pointcut** chọn. Với một lời gọi đồng bộ thông thường, khoảng từ khi bắt đầu gọi đến khi nhận giá trị/ngoại lệ thường tương ứng gần với khoảng công việc mà caller quan tâm. Nhưng với API bất đồng bộ, phương thức có thể chỉ **khởi tạo hoặc lên lịch công việc rồi trả ngay** một handle như `CompletionStage`, `CompletableFuture`, promise hoặc một đối tượng biểu diễn quá trình thực thi.

Ví dụ ý tưởng:

```text
caller
  |
  v
around advice: bắt đầu đo
  |
  v
target.fetchAsync() ----> gửi tác vụ vào hàng đợi
  |
  v
trả về CompletionStage ngay
  |
  v
around advice: kết thúc đo, trả stage về caller
                                      ... tác vụ vẫn đang chạy ...
                                      -> hoàn tất thành công hoặc thất bại
```

Nếu advice chỉ đo thời gian bao quanh **lời gọi `fetchAsync()`**, số đo là *invocation/dispatch latency*, **không nhất thiết** là thời gian thực sự lấy dữ liệu. Việc future hoàn tất có thể xảy ra nhiều mili giây hoặc nhiều giây sau, ở thread khác, và thậm chí không bao giờ hoàn tất nếu tác vụ bị treo hoặc thiếu xử lý timeout.

Bài học giúp bạn:

1. Phân biệt **lời gọi đồng bộ**, **phương thức trả về handle bất đồng bộ**, **thời điểm bắt đầu xử lý**, **thời điểm completion** và **thời điểm caller quan sát kết quả**.
2. Đọc đúng ngữ nghĩa của `before`, `after-returning`, `after-throwing`, `after/finally` và `around/proceed` khi method trả `CompletionStage`.
3. Nhận diện ba đường lỗi khác nhau: **ném đồng bộ trước return**, **future hoàn tất exceptionally**, và **lỗi ở callback/advice quan sát**.
4. Thiết kế phép đo **thời gian gọi**, **thời gian ở hàng đợi**, **thời gian thực thi** hoặc **end-to-end latency** theo đúng ranh giới.
5. Gắn callback quan sát kết quả cuối, hiểu sự khác biệt giữa **trả lại stage gốc** và **trả stage phụ thuộc**, cùng rủi ro thay đổi semantics.
6. Phân tích cancellation, timeout, retry, context propagation, threading và resource lifecycle.
7. Kiểm thử qua ví dụ Java 17 hoàn chỉnh, có stdout xác định, cả success, failure, lỗi đồng bộ và đường đi bỏ qua proxy.

Phạm vi ở đây là **AOP tổng quát**, không giả định một thư viện nào có khả năng tự mở rộng một join point method-execution thành toàn bộ vòng đời của tác vụ bất đồng bộ.

## 2. Hai ranh giới cần đặt tên rõ

### 2.1. Ranh giới lời gọi phương thức (invocation boundary)

Đây là khoảng một method **được gọi rồi kết thúc lời gọi**, tức trả về bình thường hoặc ném exception ra ngoài. Nếu method đồng bộ thực hiện công việc ngay trong call stack, ranh giới này có thể đủ để đánh giá outcome.

```java
String loadSync(String id) throws java.io.IOException {
    return queryRemote(id); // ví dụ minh họa, queryRemote chưa định nghĩa
}
```

Nếu `queryRemote` chạy đồng bộ rồi trả dữ liệu, `loadSync` chỉ return khi việc nó gọi đã xong. Around advice bao quanh *execution của `loadSync`* (nếu công cụ hỗ trợ và được cấu hình) có thể đo khoảng thời gian của lời gọi này, bao gồm các công việc đồng bộ diễn ra bên trong.

Nếu target ném `IOException` ra khỏi method, after-throwing trên execution phù hợp có thể nhìn thấy lỗi. Nếu target bắt lỗi và trả fallback, execution kết thúc bình thường và after-throwing của execution đó không tự thấy lỗi đã được xử lý nội bộ.

### 2.2. Ranh giới vòng đời công việc bất đồng bộ (task/completion boundary)

Xét:

```java
CompletionStage<String> loadAsync(String id) {
    return requestRemoteLater(id); // giả mã, requestRemoteLater chưa định nghĩa
}
```

Method **có thể trả về bình thường** một stage ngay cả khi công việc chưa thực hiện xong. Kết cục của lời gọi là **trả handle**, còn kết cục của tác vụ được thể hiện bởi **stage** vào thời điểm sau.

```text
T0: caller gọi loadAsync(id)
T1: method lập lịch/gửi công việc
T2: method return stage         <-- invocation hoàn thành
T3: worker bắt đầu làm việc
T4: stage hoàn tất             <-- task outcome có thể quan sát
T5: caller đọc/chuyển tiếp kết quả hoặc lỗi
```

Các mốc T0–T5 là **một kịch bản minh họa**, không phải thứ tự bắt buộc của mọi API: stage có thể hoàn thành ngay trước T2; task có thể bắt đầu trước lúc method return; callback có thể xử lý trước hoặc sau caller tùy tình huống.

**Nguyên tắc:** Đừng suy diễn thứ tự trong một sơ đồ lý tưởng thành bảo đảm scheduling. Hãy xác định sự kiện nào thật sự được công cụ AOP chọn và sự kiện nào được abstraction bất đồng bộ công bố.

### 2.3. Phải phân biệt ít nhất ba độ trễ

| Chỉ số | Mốc bắt đầu | Mốc kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| **Invocation latency** | Ngay trước lời gọi method. | Method return/throw. | Chi phí kiểm tra, chuẩn bị request, schedule, bọc kết quả. |
| **End-to-end task latency** | Mốc nhận/yêu cầu tác vụ theo hợp đồng. | Tác vụ hoàn tất success/failure/cancelled. | Chi phí tổng thể gồm chờ hàng đợi, xử lý, I/O, retry nếu nằm trong cùng task. |
| **Execution time** | Worker thực sự bắt đầu xử lý. | Worker thực sự kết thúc xử lý. | Không nhất thiết bao gồm thời gian queue/dispatch. |

Nếu chỉ có hook vào method return, không thể chính xác khẳng định đã đo *execution time* hoặc *end-to-end latency*. Nếu chỉ có completion timestamp mà không biết mốc bắt đầu thực sự của worker, không thể tự suy được queue delay.

## 3. Around advice bao quanh cái gì?

Một around advice thường có cấu trúc khái niệm:

```text
around selectedJoinPoint:
    before()
    try:
        result = proceed()
        afterReturn(result)
        return result
    catch error:
        afterThrow(error)
        throw same error
    finally:
        cleanup()
```

Đây là **giả mã**, không phải cú pháp chung. `proceed` là thao tác tiếp tục vào phần bên trong chuỗi advice/target theo cơ chế công cụ, không phải lời hứa rằng phần đó đã hoàn tất mọi tác vụ logic được tạo ra trong tương lai.

Nếu target trả một `CompletionStage` chưa hoàn tất, `proceed()` có thể kết thúc bình thường bằng cách trả chính đối tượng stage. Sau đó:

- Nhánh **after-returning** ở *method invocation* chạy.
- Nhánh **after-throwing** ở *method invocation* **không** chạy chỉ vì stage sau đó hoàn tất exceptionally.
- `finally` của around advice cho *method invocation* chạy khi lời gọi trả stage hoặc ném đồng bộ.
- Callback theo **stage completion** có thể chạy về sau nếu được đăng ký rõ ràng.
- Nếu công cụ AOP có một mô hình join point riêng dành cho hoàn tất task, ngữ nghĩa có thể khác; phải xét API và hợp đồng cụ thể.

### 3.1. Bảng các tình huống

| Tình huống | Method invocation | Task outcome | Advice chỉ bao method sẽ quan sát |
| --- | --- | --- | --- |
| Đồng bộ trả `"OK"` | Return `"OK"`. | Không có stage riêng. | Return bình thường; có thể coi đồng bộ hoàn tất. |
| Đồng bộ ném `IOException` | Throw. | Không có stage riêng. | Throw đồng bộ. |
| Async trả stage chưa hoàn tất | Return stage. | Chưa biết. | Return bình thường với handle. |
| Async trả stage đã hoàn tất success | Return stage. | Đã success. | Vẫn là return stage; có thể kiểm tra trạng thái nếu abstraction cho phép. |
| Async trả stage đã hoàn tất exceptionally | Return stage. | Đã fail. | Vẫn là method return bình thường, không tự thành after-throwing. |
| Async trả stage rồi fail sau đó | Return stage. | Failure sau return. | Chỉ biết method trả stage nếu không gắn hook completion. |
| Async ném lỗi trước khi tạo stage | Throw trực tiếp. | Không có stage hợp lệ. | After-throwing của invocation có thể ghi lỗi đó. |
| Async stage bị cancel | Return stage. | Cancellation/terminal state theo abstraction. | Không tự biết cancellation nếu chỉ nhìn return. |

Khi nói “phương thức bất đồng bộ bị lỗi”, hãy nói rõ đang nói đến **ngoại lệ ném đồng bộ** hay **exceptional completion** của stage.

### 3.2. Một kết quả “bình thường” có thể là một handle của thất bại

`CompletableFuture.failedFuture(new IOException("offline"))` tạo một future hoàn tất exceptionally, nhưng method **trả về** future này vẫn có thể kết thúc **bình thường**. Trạng thái exception là thuộc **giá trị được trả về**, không phải exception thoát ra khỏi lời gọi.

Điều này rất quan trọng với metric: “method return success” và “operation success” không phải luôn cùng định nghĩa.

## 4. `proceed` và quyền điều khiển trong trường hợp bất đồng bộ

Around advice có thể quyết định có gọi continuation không, nhưng quyền đó cần được hiểu đúng khi kết quả là một handle.

### 4.1. Không gọi `proceed`

Ví dụ kiểm soát rate limit có thể trả ngay một **failed stage** thay vì ném exception đồng bộ:

```text
if rateLimited:
    return failedStage(RateLimitError)
return proceed()
```

Ở nhánh trả failed stage, **target có thể không chạy** nhưng *method invocation của advice* vẫn trả bình thường một handle. Advice nằm ở tầng ngoài có thể báo after-returning nếu chỉ xét việc trả handle.

Nếu lựa chọn `throw RateLimitError` thay vì `return failedStage(...)`, caller thấy ngữ nghĩa khác hẳn: throw ngay lúc gọi so với nhận stage báo lỗi khi completion. Một API đã công bố hợp đồng bất đồng bộ không nên chuyển ngẫu nhiên giữa hai hình thức này mà không có yêu cầu rõ ràng.

### 4.2. Gọi `proceed` một lần

`proceed` có thể trả `CompletionStage`. Advice có thể đăng ký callback để quan sát completion và **trả lại stage gốc** cho caller.

Tuy nhiên, việc đính thêm callback không chứng minh task chưa được thực hiện hay callback chắc chắn chạy trên thread hiện tại. `whenComplete` có thể kích hoạt xử lý ngay nếu stage đã hoàn tất; nếu chưa, callback được kích hoạt khi completion xảy ra theo chính sách thực thi của implementation.

### 4.3. Gọi `proceed` nhiều lần

Nếu quanh một API async mà retry bằng cách **gọi `proceed` thêm lần nữa**, có thể tạo **nhiều task khác nhau**. Không thể coi đây là retry cùng một stage.

Ngược lại, nếu chỉ retry bằng cách gọi lại `join()` trên **cùng một future đã exceptional**, bạn thường chỉ đọc lại cùng một trạng thái thất bại, **không tạo attempt mới**. Vì vậy cần phân biệt:

- **Tạo một task mới:** gọi lại phần khởi tạo tác vụ hoặc một hàm retry hợp đồng rõ.
- **Quan sát một stage đã có:** đăng ký callback hoặc đọc completion; không tự khởi động lại công việc.
- **Compose thành chuỗi fallback:** khi stage fail, kích hoạt task khác nếu retry semantics và API cho phép.

Retry bên trong around advice phải tính đến idempotency, sự cố mạng không rõ commit, backoff, timeout tổng và cách chống phát sinh side effect lặp.

## 5. Quan sát toàn bộ tác vụ: hook theo completion

Trong Java, `CompletionStage<T>` cho phép gắn hành vi khi stage hoàn tất, chẳng hạn `whenComplete`, `handle`, `thenApply`, `exceptionally`. Nhưng chúng không đồng nghĩa:

| API / nhóm thao tác | Ý nghĩa điển hình | Rủi ro cần chú ý |
| --- | --- | --- |
| `whenComplete` | Chạy action quan sát giá trị hoặc lỗi, tạo **dependent stage**. | Callback có thể ném lỗi; stage phụ thuộc có thể đổi outcome. |
| `handle` | Tính giá trị mới từ success hoặc failure. | Có thể biến thất bại thành thành công hay ngược lại. |
| `exceptionally` | Có thể phục hồi từ exceptional completion. | Có thể che lỗi gốc nếu trả fallback. |
| `thenApply` | Biến đổi giá trị khi thành công. | Có thể tạo lỗi mới; không chạy trên failure bình thường. |
| `whenCompleteAsync` hoặc biến thể async | Lên lịch callback theo executor/mặc định. | Thread, scheduling, context, latency và exception callback cần kiểm soát. |
| `toCompletableFuture().join()` | Chờ/đọc kết quả ở caller nếu chưa xong. | Có thể block; failure có thể xuất hiện dưới dạng `CompletionException`. |

Mỗi operation trên `CompletionStage` trả về một **stage mới**, trừ những API khác được tài liệu quy định. Vì vậy có hai thiết kế khác biệt.

### 5.1. Trả lại stage gốc: quan sát mà không thay handle của caller

Giả mã Java minh họa (các tên biến là bối cảnh đã có):

```java
CompletionStage<Result> original = invokeAsync();
original.whenComplete((value, failure) -> {
    if (failure == null) {
        recordSuccess();
    } else {
        recordFailure(failure);
    }
});
return original;
```

Ở đây **caller nhận `original`**, không phải stage mà `whenComplete` trả về. Vì thế, exception của callback có thể làm **dependent stage bị lỗi**, nhưng không nhất thiết đổi trạng thái `original`; nếu bỏ qua dependent stage, lỗi callback có thể bị mất tín hiệu quan sát. Cần thiết kế nơi báo lỗi instrumentation hoặc quan sát stage phụ thuộc khi chính sách yêu cầu.

Đoạn này không phải chương trình độc lập; `Result`, `invokeAsync` và các hàm `record...` chỉ là tên minh họa.

### 5.2. Trả stage phụ thuộc: có thể thay đổi semantics của caller

```java
CompletionStage<Result> original = invokeAsync();
return original.whenComplete((value, failure) -> record(value, failure));
```

Ở đây caller nhận stage **phụ thuộc**. Theo hợp đồng `CompletionStage.whenComplete`, kết quả thường được truyền tiếp nếu action không làm lỗi; tuy nhiên lỗi từ callback có thể khiến stage phụ thuộc exceptional, và quy tắc ưu tiên nếu cả source lẫn callback lỗi là một phần hợp đồng API. Điều này nghĩa là **chỉ một thay đổi dòng return** cũng có thể làm một lời gọi tưởng “chỉ quan sát” trở nên có tác động lên kết quả mà caller nhận.

Không thể hứa “đính callback luôn không đổi hợp đồng” nếu không kiểm soát **stage nào được trả ra** và lỗi của callback.

### 5.3. Callback có thể chạy ở thời điểm bất ngờ

Với `CompletableFuture`, một callback không có hậu tố `Async` có thể được chạy bởi thread đang hoàn tất future hoặc thread khác tương tác với completion. Khi stage đã hoàn tất, việc đăng ký callback có thể khiến action thực thi ngay. Không nên dựa vào **thread cố định** hoặc thứ tự tương đối với một log ở nơi khác, trừ khi dùng cơ chế scheduler/executor với hợp đồng thích hợp.

Callback phải không block lâu, không giữ lock gây deadlock và không giả định thread context đã tồn tại. Nếu cần I/O telemetry nặng, dùng pipeline riêng có kiểm soát backpressure hoặc executor phù hợp.

## 6. Ví dụ Java 17 hoàn chỉnh: return-handle khác completion

Chương trình sau dùng **JDK dynamic proxy** để minh họa around advice ở ranh giới phương thức theo interface. `JobApi.schedule` trả `CompletionStage<String>`; target lưu một `CompletableFuture` chưa hoàn tất và chương trình test điều khiển lúc nó hoàn thành.

Mục đích điều khiển completion trong một luồng là để **stdout có thứ tự xác định**, không phụ thuộc sleep, network hoặc scheduler. Ví dụ này **không phải một AOP engine tổng quát** và đối tượng lưu future hiện tại chỉ phục vụ demo tuần tự, **không an toàn cho nhiều job đồng thời**.

Tạo tệp `AsyncBoundaryDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

public class AsyncBoundaryDemo {
    interface JobApi {
        CompletionStage<String> schedule(String id);
    }

    static final class JobService implements JobApi {
        private CompletableFuture<String> current;

        @Override
        public CompletionStage<String> schedule(String id) {
            System.out.println("TARGET schedule " + id);
            if ("BAD".equals(id)) {
                throw new IllegalArgumentException("invalid-id");
            }
            current = new CompletableFuture<>();
            return current;
        }

        void succeed(String value) {
            current.complete(value);
        }

        void fail(String message) {
            current.completeExceptionally(
                    new IllegalStateException(message));
        }
    }

    static JobApi observed(JobApi target) {
        return (JobApi) Proxy.newProxyInstance(
                JobApi.class.getClassLoader(),
                new Class<?>[] { JobApi.class },
                (proxy, method, arguments) -> {
                    System.out.println("AROUND enter " + method.getName());
                    try {
                        Object result = method.invoke(target, arguments);
                        System.out.println("AROUND return-handle "
                                + method.getName());

                        if (result instanceof CompletionStage<?> stage) {
                            stage.whenComplete((value, error) -> {
                                if (error == null) {
                                    System.out.println("ASYNC success " + value);
                                } else {
                                    System.out.println("ASYNC failure "
                                            + error.getClass().getSimpleName()
                                            + ": " + error.getMessage());
                                }
                            });
                        }
                        return result;
                    } catch (InvocationTargetException wrapped) {
                        Throwable cause = wrapped.getCause();
                        System.out.println("AROUND sync-throw "
                                + cause.getClass().getSimpleName());
                        throw cause;
                    } finally {
                        System.out.println("AROUND exit-call "
                                + method.getName());
                    }
                }
        );
    }

    public static void main(String[] args) {
        JobService target = new JobService();
        JobApi proxy = observed(target);

        CompletionStage<String> a = proxy.schedule("A");
        System.out.println("CALLER received A");
        target.succeed("done-A");
        System.out.println("CALLER joined A="
                + a.toCompletableFuture().join());

        CompletionStage<String> b = proxy.schedule("B");
        System.out.println("CALLER received B");
        target.fail("network-down");
        try {
            b.toCompletableFuture().join();
        } catch (CompletionException ex) {
            System.out.println("CALLER caught "
                    + ex.getClass().getSimpleName() + ": "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            proxy.schedule("BAD");
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER caught sync " + ex.getMessage());
        }

        CompletionStage<String> direct = target.schedule("DIRECT");
        System.out.println("CALLER direct received");
        target.succeed("done-direct");
        System.out.println("CALLER direct joined "
                + direct.toCompletableFuture().join());
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac AsyncBoundaryDemo.java
java AsyncBoundaryDemo
```

**Stdout kỳ vọng:**

```text
AROUND enter schedule
TARGET schedule A
AROUND return-handle schedule
AROUND exit-call schedule
CALLER received A
ASYNC success done-A
CALLER joined A=done-A
AROUND enter schedule
TARGET schedule B
AROUND return-handle schedule
AROUND exit-call schedule
CALLER received B
ASYNC failure IllegalStateException: network-down
CALLER caught CompletionException: IllegalStateException
AROUND enter schedule
TARGET schedule BAD
AROUND sync-throw IllegalArgumentException
AROUND exit-call schedule
CALLER caught sync invalid-id
TARGET schedule DIRECT
CALLER direct received
CALLER direct joined done-direct
```

### 6.1. Đường thành công A: method return trước completion

1. `proxy.schedule("A")` đi vào proxy: in `AROUND enter schedule`.
2. Target in `TARGET schedule A`, tạo một `CompletableFuture` còn pending và **trả handle**.
3. Handler in `AROUND return-handle schedule`, đăng ký `whenComplete` lên stage gốc rồi in `AROUND exit-call schedule` trong `finally`.
4. Caller in `CALLER received A`: tại thời điểm này **đã có return-handle nhưng chưa có ASYNC success**.
5. `target.succeed("done-A")` hoàn tất future. Vì demo tuần tự và callback không-async, `ASYNC success done-A` xuất hiện tại completion trước câu lệnh `CALLER joined A=...`.
6. `join()` đọc kết quả đã hoàn tất và in `done-A`.

Điều được minh họa là **hai sự kiện tách biệt**. Không dùng thứ tự log của demo này để suy ra mọi callback trong ứng dụng có executor đa luồng đều chạy cùng thread hoặc luôn trước một log ở thread khác.

### 6.2. Đường B: method trả bình thường, task thất bại

`proxy.schedule("B")` cũng in `AROUND return-handle schedule`, tức **method invocation thành công theo nghĩa trả handle**. Sau đó `target.fail("network-down")` hoàn tất future exceptionally với `IllegalStateException`. Callback in `ASYNC failure IllegalStateException: network-down`.

Caller dùng `join()` trên future exceptional nên bắt `CompletionException`; `getCause()` ở đây là `IllegalStateException`. `AROUND sync-throw` **không xuất hiện** cho B bởi target **không ném lỗi trước khi return stage**.

### 6.3. Đường BAD: lỗi đồng bộ ngay trong lời gọi

Target in `TARGET schedule BAD` rồi ném `IllegalArgumentException` trước khi trả future. `Method.invoke` bao cause trong `InvocationTargetException`, handler gỡ wrapper và in `AROUND sync-throw IllegalArgumentException` trước khi ném lại.

Ở nhánh này:

- Không có `AROUND return-handle`.
- Không đăng ký `whenComplete` bởi không nhận được stage.
- Vẫn chạy `AROUND exit-call` trong `finally`.
- Caller bắt exception **ngay tại lời gọi `schedule`**, không phải khi `join`.

### 6.4. Đường DIRECT: bypass proxy

`target.schedule("DIRECT")` gọi thẳng target, nên không xuất hiện bất kỳ `AROUND` hoặc `ASYNC` nào từ handler. Việc target tạo future và future hoàn tất vẫn diễn ra; chỉ có **cơ chế quan sát của proxy** bị bỏ qua. Đây là giới hạn của kỹ thuật proxy trong demo, không phải tuyên bố mọi cơ chế AOP đều giới hạn tương tự.

### 6.5. Stage mà handler trả ra là stage nào?

Handler gọi `stage.whenComplete(...)` để đăng ký quan sát nhưng **bỏ qua stage phụ thuộc được trả từ khi đăng ký**, sau đó `return result`: caller nhận stage gốc của target. Điều này giúp phân biệt việc gắn hook quan sát với thay thế handle. Trong production vẫn phải xử lý lỗi callback, lifecycle, resource, masking và telemetry best-effort để tránh mất lỗi trong stage phụ thuộc bị bỏ qua.

### 6.6. Giới hạn của ví dụ cần nói rõ

- `JobService.current` chỉ hỗ trợ **một job pending tại một thời điểm** trong demo tuần tự; không là thiết kế concurrent production.
- Không có executor, I/O mạng hoặc timer: các sự kiện hoàn tất được `main` gọi trực tiếp để stdout ổn định.
- `whenComplete` là cơ chế completion của Java, còn proxy handler là ranh giới around advice; hai thứ **không phải cùng một join point**.
- Không có pointcut DSL, weaving bytecode hoặc các loại join point khác.
- Lỗi của callback in log không được xử lý đầy đủ; example tập trung vào ngữ nghĩa return-handle và completion.
- `System.out.println` chỉ để quan sát thứ tự, không đại diện cách lưu log an toàn, phi đồng bộ và có kiểm soát trong production.

## 7. Khi mục tiêu là đo độ trễ, đặt điểm bắt đầu và kết thúc đúng chỗ

Một kỹ thuật an toàn để đo *end-to-end latency* của một stage: **lấy `System.nanoTime()` ngay trước invocation** và **tính delta tại completion**. Với Java, `System.nanoTime()` phù hợp đo khoảng thời gian tương đối; không lấy `System.currentTimeMillis()` rồi giả định đồng hồ lịch không thể bị chỉnh.

Giả mã:

```text
started = monotonicClock()
try:
    stage = proceed()
catch synchronousError:
    recordSyncFailure(synchronousError, monotonicClock() - started)
    rethrow

registerCompletionObserver(stage, (value, error) -> {
    duration = monotonicClock() - started
    if error == null:
        recordTaskSuccess(duration)
    else:
        recordTaskFailure(duration, error)
})
return originalStage
```

Cần chú ý **cùng một invocation** chỉ nên tạo một kết quả terminal trong mô hình metric đã chọn. Đừng đồng thời ghi `operation_success` ở nhánh *method return* và `operation_failure` ở callback failure rồi gộp cả hai thành kết quả cuối; chúng đo **hai loại kết cục khác nhau**.

### 7.1. Đồng bộ ném lỗi và async fail: cùng chỉ số hay khác?

Một method async có thể:
- **Throw đồng bộ:** chưa trả handle.
- **Return failed stage:** trả handle, nhưng stage đã exceptional.
- **Return pending stage rồi fail:** lỗi ở completion muộn hơn.

Nếu metric là **logical task outcome**, có thể phân loại cả ba thành “operation failed”, nhưng cần đường ghi **chỉ một lần** cho mỗi logical invocation. Nếu metric là **invocation outcome**, throw đồng bộ là failure còn return stage là normal return, bất kể stage sau đó fail. Hai metric khác nhau và không được trộn tên.

### 7.2. Đo thời gian chờ hàng đợi

Nếu cần tách **queue wait** khỏi **execution time**, phải có dấu mốc worker bắt đầu. Một advice chỉ bao method gửi task không tự biết khi nào scheduler thực sự chạy. Có thể cần instrumentation tại queue/executor/worker hoặc context/tracing xuyên hệ thống.

### 7.3. Timeout không phải lúc nào cũng có nghĩa task đã dừng

Một future có thể hoàn tất exceptionally do timeout, trong khi công việc phía sau vẫn đang chạy, tùy cơ chế cancellation/deadline và executor. Khi đó “time to timeout signal” khác “thời điểm worker dừng tài nguyên”. Không tự coi timeout của handle là bằng chứng thao tác remote đã hủy hoặc chưa commit.

## 8. Exception, cancellation và kết quả async

### 8.1. `CompletionException` và `ExecutionException`

Với `CompletableFuture`, `join()` có thể ném `CompletionException` khi hoàn tất exceptional; `get()` theo hợp đồng `Future` có thể ném `ExecutionException` cho lỗi tính toán, ngoài `InterruptedException` và các ngoại lệ liên quan. Một callback `whenComplete` có thể nhận một `Throwable` biểu diễn lỗi được stage lưu hoặc lớp wrapper; không giả định mọi đường luôn cùng một kiểu Throwable.

Không tùy tiện `getCause()` mọi lúc và ném cause thay thế cho mọi caller. Việc bọc lỗi là một phần hợp đồng cụ thể; nếu cần phân loại lỗi, có thể tìm nguyên nhân sâu hơn để **ghi metric**, nhưng giữ nguyên trạng thái stage nếu mục tiêu là quan sát thuần.

### 8.2. Cancellation là một trạng thái terminal đáng phân loại riêng

`CompletableFuture.cancel(...)` đánh dấu future cancelled theo semantics của Java. Với một số stage, cancellation được biểu diễn như exceptional completion và callback có thể thấy `CancellationException`. Nhưng **cancellation của handle không tự bảo đảm worker đã dừng**, nhất là tác vụ đã gửi tới hệ thống khác.

Nếu phân loại cancellation như failure vận hành, dashboard có thể báo động sai; nếu không ghi cancellation, việc theo dõi tài nguyên có thể thiếu. Nên định nghĩa các outcome như `success`, `failed`, `cancelled`, `timed_out` theo abstraction thực tế, thay vì chỉ kiểm tra `error != null` rồi coi mọi error tương đương.

### 8.3. Lỗi do callback quan sát gây ra

`whenComplete` tạo dependent stage. Nếu callback ném lỗi và bạn **bỏ qua dependent stage**, lỗi callback có thể không được báo ở nơi bạn mong muốn. Nếu **trả dependent stage** cho caller, callback failure có thể tác động lên outcome của caller.

Một chiến lược best-effort instrumentation có thể cố gắng không để lỗi telemetry phá nghiệp vụ, nhưng vẫn cần một kênh báo lỗi riêng được kiểm soát và tránh ném lỗi trong những tình huống tài nguyên cạn kiệt. Một chiến lược audit bắt buộc lại có hợp đồng khác. Không tự động dùng một kiểu catch-all cho mọi chính sách.

## 9. Context propagation và giới hạn thread-local

Một around advice đồng bộ có thể mở scope trace trong một thread:

```text
around:
    context.open(traceId)
    try:
        return proceed()
    finally:
        context.close()
```

Với API async, `finally` phía trên thường chạy khi **method trả handle**, không phải khi job hoàn tất. Nếu context đóng quá sớm, callback/worker có thể mất correlation ID; nếu giữ `ThreadLocal` mở đến task completion trong thread caller, có thể **rò context** và làm ô nhiễm request kế tiếp sử dụng lại thread.

Các điểm cần xác định:

- Context lưu ở **thread**, **logical task**, **request context** hay object gắn với stage?
- Có truyền snapshot context sang executor/worker không?
- Completion callback có khôi phục và dọn context theo scope chính xác không?
- Nếu một task tạo nhiều task con, thông tin quan hệ cha-con truyền như thế nào?
- Nếu stage hoàn tất trên thread do bên khác quản lý, có được phép sửa thread-local tại đó không?
- Cancellation hoặc lỗi trước khi đăng ký callback có gây rò tài nguyên không?

Không có một cách truyền `ThreadLocal` xuyên mọi executor, promise, coroutine hay event loop tự động đúng trong mọi ngôn ngữ. Tư duy AOP giúp xác định biên hook, còn **cơ chế async context propagation** phải được thiết kế riêng.

## 10. Vòng đời resource và cleanup: chỗ `finally` dễ gây sai lầm

### 10.1. Cleanup cho chính lời gọi đồng bộ

Nếu around advice cấp phát tài nguyên chỉ cần cho *invocation* (ví dụ bộ đếm tạm thời hoặc scope dành riêng cho việc tạo request), cleanup trong `finally` sau `proceed` có thể hợp lý.

### 10.2. Cleanup cho toàn bộ tác vụ

Nếu tài nguyên phải sống tới khi job hoàn tất (ví dụ span bao cả network call), dọn trong `finally` của method trả future sẽ **quá sớm**. Cần quản lý tài nguyên bằng callback terminal, lifecycle object hoặc abstraction async chuyên dụng.

Tuy nhiên, cũng không được mở tài nguyên lúc invocation và chỉ đóng khi future hoàn tất nếu stage **không bao giờ complete**. Phải có timeout/deadline, cancellation, giám sát pending tasks và xử lý trường hợp đăng ký callback thất bại. Với tài nguyên nhạy cảm, nên chọn API cung cấp scope rõ thay vì ghép ad hoc từ ThreadLocal và callback.

### 10.3. Cleanup có thể ném exception

Trong Java, lỗi cleanup có thể che lỗi gốc nếu không xử lý đúng. Với async callbacks, lỗi cleanup có thể ảnh hưởng dependent stage hoặc bị bỏ qua tùy thiết kế. Cần giữ nguyên error của công việc khi chính sách là quan sát, quản lý suppressed error hoặc kênh cảnh báo riêng nếu cleanup lỗi.

## 11. Thứ tự nhiều advice và nghĩa của “thành công”

Một chuỗi có thể gồm:

```text
Metrics(Trace(Retry(TaskScheduler)))
```

Tùy vị trí mỗi advice:

- **Metrics ở ngoài Retry:** có thể đo một logical operation gồm nhiều attempts, nếu continuation/abstraction bao gồm toàn bộ retry lifecycle.
- **Metrics ở trong Retry:** có thể ghi từng attempt.
- **Metrics chỉ quanh method submit:** có thể chỉ đo thời gian **lên lịch** của mỗi attempt, chưa đo task completion.
- **Trace được đóng khi method trả stage:** có thể không bao phủ các sự kiện worker phía sau.
- **Trace được đóng trong completion callback:** có thể bao phủ thêm vòng đời task, nếu context và error handling được tổ chức đúng.

Đừng suy từ tên aspect rằng nó đang đo end-to-end. Phải vẽ **điểm bắt đầu, điểm kết thúc và đối tượng kết quả đang được truyền trả**.

### 11.1. Skip và cache

Một quanh advice có thể trả `CompletableFuture.completedFuture(cached)` mà không gọi target. Về mặt invocation, caller nhận stage bình thường; về mặt task, stage đã success ngay. Nếu cache hit không tạo công việc remote, metric “remote execution time” không nên bao gồm trường hợp này như một lần remote call. Nhưng metric “request resolved” có thể bao gồm cache hit.

### 11.2. Retry bất đồng bộ

Nếu cần retry khi **stage thất bại về sau**, việc bắt `Throwable` quanh `proceed()` thường không bắt được failure đó. Phải compose logic retry tại completion hoặc ở task abstraction chuyên dụng, có stop condition, timeout tổng, backoff, idempotency và phân biệt attempt/logical outcome.

## 12. Đừng ép mọi loại bất đồng bộ về cùng một mẫu future

Một số API trả promise/future **eager**; một số abstraction như stream/publisher có thể **lazy**, nghĩa là công việc chỉ bắt đầu khi consumer đăng ký (*subscribe*) hoặc khi có demand. Trong hệ thống event-driven, một method chỉ đăng ký callback mà không trả handle có thể không cho caller cách chờ completion. Với coroutine, suspend/resume và context propagation tạo những biên thực thi riêng.

### 12.1. Future/promise eager

Method gọi một API và trả handle cho tác vụ đã được bắt đầu hoặc lên lịch. Hook vào future completion có thể dùng để quan sát outcome.

### 12.2. Publisher/stream lazy

Method tạo một mô tả pipeline và return **trước khi pipeline thực thi**. Nếu caller subscribe nhiều lần, tùy loại publisher có thể có **nhiều execution** từ cùng object mô tả. Around advice bao quanh method *tạo publisher* chưa chắc bao quanh từng sự kiện data, error, completion hay cancellation. Cần hook theo lifecycle của subscription/stream khi mục tiêu là đo thời gian xử lý thật.

### 12.3. Event/callback không có handle

Một method `registerListener(...)` có thể return ngay còn callback nhận sự kiện nhiều lần về sau. Không có một “completion” duy nhất nếu listener hoạt động tới khi unsubscribe. Cần định nghĩa tuổi thọ subscription, events, errors và cleanup riêng.

**Kết luận phần này:** Không dùng một công thức “method trả nhanh + callback một lần” cho mọi hình thức async. Phải nắm hợp đồng của abstraction được chọn.

## 13. Kiểm thử đúng hai ranh giới

### 13.1. Những ca bắt buộc

| Trường hợp | Kết cục của invocation | Kết cục của tác vụ | Điều cần xác nhận |
| --- | --- | --- | --- |
| Đồng bộ trả result | Return value. | Cùng lời gọi đã xong. | After-returning và thời gian lời gọi đúng. |
| Đồng bộ throw | Throw. | Không có handle. | After-throwing ngay tại call; cleanup. |
| Future pending | Return handle. | Chưa terminal. | Chưa báo task success/failure chỉ vì method return. |
| Future success sau return | Return handle. | Success sau đó. | Completion hook chạy đúng, không ghi trùng. |
| Future fail sau return | Return handle. | Exceptional completion. | Không gán nhầm thành sync-throw. |
| Future đã success trước return | Return handle. | Đã success. | Callback vẫn có thể quan sát completion; thứ tự xử lý hợp lệ. |
| Future đã fail trước return | Return handle. | Đã fail. | Không gọi after-throwing đồng bộ nếu method không throw. |
| Cancellation | Return handle. | Cancelled/terminal. | Phân loại riêng; không khẳng định worker chắc đã dừng. |
| Timeout | Return handle. | Có thể signal timeout. | Định nghĩa có/không ngừng task nền. |
| Handler bỏ qua proxy | Return từ target. | Task tùy target. | Advice không chạy trên đường bypass. |
| Callback instrumentation ném lỗi | Return handle. | Outcome stage gốc/phụ thuộc khác nhau. | Caller có nhận stage nào; lỗi telemetry có được báo? |
| Multi-attempt retry | Một logical call, nhiều attempts. | Có thể cuối cùng success/failure. | Metric và idempotency đúng. |
| Concurrency | Nhiều jobs sống cùng lúc. | Completion không theo thứ tự gửi. | Không trộn trace ID, attempt, resource scope. |
| Never-completing stage | Return handle. | Không terminal. | Deadline/watchdog và resource cleanup có thiết kế. |

### 13.2. Cách làm test không phụ thuộc `Thread.sleep`

Dùng `CompletableFuture` chưa hoàn tất, gọi qua advice và assert:

1. Ngay sau method return: bộ đếm invocation-return = 1; task-success = 0; task-failure = 0.
2. Gọi `future.complete(value)`: task-success = 1; task-failure = 0.
3. Tạo một future khác rồi `completeExceptionally(error)`: task-failure tăng, sync-throw **không tăng**.
4. Cho target ném trước khi trả future: sync-throw tăng; không có task callback từ nhánh đó.
5. Gọi target trực tiếp không qua proxy: không có marker/metric do advice proxy ghi.

Với test đa luồng, thay sleep bằng synchronization primitives như `CountDownLatch`, barrier hoặc stage được điều khiển để assertions diễn ra sau khi sự kiện mong đợi đã thực sự phát sinh. Chỉ dựa vào số mili giây chờ có thể khiến test flakey.

### 13.3. Hai assertion quan trọng nhất

- **Invocation đã return** không tự làm bộ đếm **task completed** tăng.
- **Stage completed exceptionally** không tự làm bộ đếm **method threw synchronously** tăng.

Nếu dashboard hoặc test đang coi hai mệnh đề này tương đương, cách đo đã sai ranh giới.

## 14. Các lỗi thiết kế thường gặp

**“Around advice đo tới lúc `proceed()` return nghĩa là đo xong toàn bộ job.”** Không đúng khi `proceed` chỉ trả handle chưa hoàn tất.

**“Stage hoàn tất exceptionally thì after-throwing của method đã phải chạy.”** Sai nếu method trả stage bình thường. Failure nằm ở completion event, không phải synchronous throw.

**“Đính `whenComplete` rồi trả stage phụ thuộc hay stage gốc cũng như nhau.”** Sai. Callback có thể thay đổi trạng thái stage phụ thuộc khi tự ném lỗi.

**“Để đo end-to-end chỉ cần `Thread.sleep` đủ lâu.”** Không. Dùng completion signal thật và nguồn thời gian đơn điệu; thời gian chờ tùy đoán không định nghĩa outcome.

**“Callback `whenComplete` luôn chạy trên thread đã gọi advice.”** Không có bảo đảm như vậy; không-async callback có thể chạy trên thread tham gia completion, hoặc khi đăng ký nếu stage đã completed.

**“Cancellation của future luôn dừng network request.”** Không. Phụ thuộc API và việc cancellation có được truyền xuống hoạt động thực tế hay không.

**“Đóng trace trong `finally` của method luôn đúng.”** Chỉ đúng nếu trace scope thực sự là lời gọi đồng bộ; nếu trace phải bao task, đóng lúc method return có thể quá sớm.

**“Chỉ cần `ThreadLocal` để correlation tự truyền qua mọi async job.”** Sai. Phải có context propagation và cleanup cho từng biên executor/callback.

**“Gọi lại `join()` là retry tác vụ.”** Sai. `join` chỉ chờ/đọc trạng thái của stage đã có, không tự tạo attempt mới.

**“Gọi `proceed` hai lần là retry vô hại.”** Không. Có thể tạo hai task/side effects, yêu cầu idempotency và xác minh engine cho phép.

**“Mọi async API đều trả `CompletableFuture` eager.”** Sai. Publisher/stream/callback và coroutine có mô hình lifecycle khác.

## 15. Bài tập vận dụng

### Bài 1 — Phân loại outcome

Một method `submit()` trả `CompletableFuture<String>` ngay, rồi remote call thất bại 300 ms sau. Around advice in “success” sau khi `proceed()` trả về.

**Câu hỏi:** Log có sai không?

**Giải thích:** Nếu “success” được định nghĩa là **method return handle**, log nhất quán nhưng dễ gây hiểu nhầm. Nếu nó được dùng làm **task success**, log sai. Cần đổi tên metric hoặc gắn completion hook ở ranh giới tác vụ.

### Bài 2 — Hai lần ném lỗi

Một nhánh `submit()` ném `IllegalArgumentException` trước khi tạo future; nhánh khác trả `failedFuture(new IllegalArgumentException(...))`.

**Đáp án:** Nhánh đầu là synchronous throw. Nhánh sau là normal method return với exceptional stage. Advice chỉ quan sát method execution nhìn thấy hai kết cục khác nhau.

### Bài 3 — Callback lỗi

Advice dùng `return stage.whenComplete(logger)` và `logger` thỉnh thoảng ném exception. Đây có còn là instrumentation trong suốt không?

**Đáp án:** Không được bảo đảm. Caller nhận dependent stage, và callback failure có thể làm thay đổi outcome được quan sát. Cần có chính sách handling rõ, xem hợp đồng của `whenComplete` và chọn có trả stage gốc hay stage phụ thuộc.

### Bài 4 — Retry

Một `CompletionStage` đã exceptional. Bạn gọi `join()` ba lần.

**Đáp án:** Không tự tạo ba task; đó là ba lần đọc cùng stage. Muốn retry phải tạo hoặc compose các attempt mới, có điều kiện và idempotency phù hợp.

### Bài 5 — Span và context

Một around advice mở span, gọi async method, đóng span trong `finally`. Công việc còn chạy một giây sau return.

**Đáp án:** Span chỉ bao phần invocation. Nếu span cần bao cả tác vụ, phải quản lý scope tới completion mà không giữ nhầm ThreadLocal trên thread caller, tránh rò resource và có xử lý timeout/cancel.

### Bài 6 — Test thời gian

Test sử dụng `Thread.sleep(100)` rồi assert future đã xong. Vì sao không đáng tin?

**Đáp án:** Scheduler, CI load, I/O, GC và môi trường có thể làm task chậm hơn hoặc kết thúc theo thứ tự khác. Dùng future được điều khiển/latch/barrier và assert sau tín hiệu hoàn tất.

### Bài 7 — Bypass

Target trả stage và được gọi trực tiếp thay vì qua proxy. Callback do proxy advice đăng ký có chạy không?

**Đáp án:** Không, vì handler proxy không nhận invocation. Stage bản thân vẫn có thể hoàn tất; công cụ AOP khác có weaving có thể có độ phủ khác.

## 16. Checklist trước khi triển khai

1. **Join point:** Around advice chọn loại điểm nào và cơ chế AOP thật sự thấy những đường gọi nào?
2. **Abstraction:** Result đồng bộ, future eager, publisher lazy hay callback/subscription có vòng đời riêng?
3. **Outcome:** “Success” được định nghĩa là return-handle, task completion, commit hay consumer đã nhận dữ liệu?
4. **Thời gian:** Điểm bắt đầu/kết thúc có đo invocation, queue wait, execution hay end-to-end?
5. **Errors:** Đã phân biệt sync throw, exceptional completion, cancellation, timeout và callback failure?
6. **Result identity:** Caller được trả stage gốc hay stage phụ thuộc? Có biến đổi kết quả/exception không?
7. **Context:** Trace ID, security context và ThreadLocal được truyền/dọn đúng qua executor/callback?
8. **Resources:** Scope cần sống tới method return hay task terminal? Nếu task không complete thì sao?
9. **Retry/cache:** Có thể skip hoặc gọi lại continuation không, và nghiệp vụ có idempotent không?
10. **Concurrency:** Có thể nhiều jobs tồn tại cùng lúc; state của aspect có race hoặc lẫn task không?
11. **Observability:** Metric có tránh đếm trùng attempt và logical operation, đã giới hạn dữ liệu nhạy cảm?
12. **Validation:** Có test pending, immediate completion, delayed success/failure, sync throw, cancel, bypass và callback error?

## Kết luận

**Bao quanh một lời gọi đồng bộ** chỉ giúp around advice nắm khoảng từ lúc lời gọi bắt đầu đến khi method **return hoặc throw**. Khi method trả một handle bất đồng bộ, khoảng đó có thể kết thúc **trước khi tác vụ thực sự xong**. Muốn bao trọn tác vụ phải dựa vào **completion/error/cancellation semantics của abstraction bất đồng bộ**, quản lý context, resource và stage được trả về một cách có chủ đích. Tên “around” không tự kéo dài join point của method đến tương lai. Đo đúng ranh giới, giữ nguyên hợp đồng kết quả/ngoại lệ, và kiểm thử thời điểm return-handle độc lập với thời điểm task-completion là nền tảng để áp dụng AOP có kiểm soát.
