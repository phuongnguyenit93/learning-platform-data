# orTimeout và hoàn tất bằng TimeoutException trong Java

Java 9 bổ sung `CompletableFuture.orTimeout(long, TimeUnit)` để đặt thời hạn cho một CompletableFuture. Nếu future chưa hoàn tất khi thời hạn trôi qua, chính future đó được hoàn tất bất thường với `TimeoutException`.

Cần phân biệt ba cách đặt giới hạn thời gian thường gặp:

- `orTimeout(timeout, unit)`: thay đổi trạng thái của CompletableFuture; nếu hết hạn trước khi có kết quả, future hoàn tất bất thường với TimeoutException.
- `completeOnTimeout(value, timeout, unit)`: nếu hết hạn trước khi có kết quả, future hoàn tất bình thường bằng giá trị dự phòng.
- `get(timeout, unit)`: chỉ giới hạn thời gian luồng hiện tại chờ kết quả; bản thân future không bị hoàn tất hoặc hủy chỉ vì lần chờ này hết hạn.

Chọn đúng API giúp xác định rõ timeout thuộc về kết quả dùng chung, một người gọi cụ thể hay chỉ là thời gian chờ của một luồng.

## 1. CompletableFuture và trạng thái hoàn tất

`CompletableFuture<T>` biểu diễn một kết quả có thể được cung cấp trong tương lai. Future có thể:

- Chưa hoàn tất: chưa có kết quả hoặc ngoại lệ.
- Hoàn tất bình thường: có giá trị kiểu T, kể cả null nếu API cho phép.
- Hoàn tất bất thường: có ngoại lệ làm kết quả không thể được cung cấp bình thường.

Ví dụ tạo một future chưa có kết quả:

~~~java
CompletableFuture<String> response = new CompletableFuture<>();
~~~

Future có thể được hoàn tất từ một luồng khác:

~~~java
response.complete("OK");
~~~

Hoặc hoàn tất bất thường:

~~~java
response.completeExceptionally(
    new IllegalStateException("Không thể lấy dữ liệu")
);
~~~

Các phương thức như `thenApply`, `thenCompose`, `thenAccept` và `whenComplete` cho phép nối các bước xử lý sau khi kết quả có mặt. Nếu một stage hoàn tất bất thường, trạng thái lỗi thường được truyền tiếp xuống các stage phụ thuộc cho tới khi có bước xử lý hoặc phục hồi lỗi.

Timeout là một cách để bảo đảm một future không ở trạng thái pending vô thời hạn. Nó không tự xác định nguyên nhân vì sao công việc chưa xong; nó chỉ áp đặt thời hạn cho việc hoàn tất kết quả.

## 2. orTimeout: hoàn tất bất thường khi quá hạn

Chữ ký:

~~~java
public CompletableFuture<T> orTimeout(
    long timeout,
    TimeUnit unit
)
~~~

Phương thức được bổ sung từ Java 9. Nếu CompletableFuture chưa hoàn tất trước thời hạn, nó được hoàn tất bất thường với `TimeoutException`.

~~~java
CompletableFuture<String> response = new CompletableFuture<>();

response.orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu không có luồng nào hoàn tất `response` trong khoảng thời gian đó, các thao tác chờ kết quả sẽ nhận lỗi timeout.

Điểm quan trọng trong hợp đồng API là `orTimeout` trả về chính đối tượng CompletableFuture được gọi. Nó không tạo một future độc lập mới:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> timed = source.orTimeout(1, TimeUnit.SECONDS);

System.out.println(source == timed); // true
~~~

Vì hai biến cùng tham chiếu một đối tượng, timeout tác động đến mọi nơi đang giữ tham chiếu tới future đó. Khi timeout thắng cuộc đua hoàn tất, future nguồn cũng đã ở trạng thái hoàn tất bất thường.

### Timeout và hoàn tất bình thường cạnh tranh

Giả sử một luồng đang tải dữ liệu và một timeout được đăng ký:

~~~java
CompletableFuture<String> result = loadAsync()
    .orTimeout(3, TimeUnit.SECONDS);
~~~

Có hai khả năng:

1. Tác vụ hoàn tất trước thời hạn: future giữ kết quả bình thường, timeout không còn thay đổi được trạng thái.
2. Thời hạn đến trước khi tác vụ hoàn tất: future được hoàn tất bất thường với TimeoutException; kết quả đến sau không thể thay đổi trạng thái đã hoàn tất đó.

CompletableFuture chỉ được hoàn tất một lần. Khi kết quả và timeout xảy ra gần như đồng thời, thao tác hoàn tất thành công trước sẽ quyết định trạng thái cuối cùng. Không nên dựa vào một thứ tự thời gian chính xác đến từng mili giây để điều khiển logic nghiệp vụ.

## 3. TimeoutException được quan sát như thế nào?

`orTimeout` không ném TimeoutException trực tiếp tại chỗ gọi phương thức. Nó đăng ký hành vi hoàn tất bất thường cho future. Ngoại lệ được quan sát khi chờ kết quả hoặc xử lý stage phụ thuộc.

### Dùng get()

`get()` ném `ExecutionException` khi future hoàn tất bất thường. Với timeout do `orTimeout`, nguyên nhân nằm trong `getCause()`:

~~~java
try {
    String value = future.get();
} catch (ExecutionException ex) {
    if (ex.getCause() instanceof TimeoutException) {
        System.out.println("Đã hết thời gian chờ");
    } else {
        throw ex;
    }
}
~~~

Cần phân biệt:

- `TimeoutException` là nguyên nhân khiến future hoàn tất bất thường do `orTimeout`.
- `ExecutionException` là lớp bọc mà `get()` dùng để báo future đã hoàn tất bất thường.

### Dùng join()

`join()` không khai báo checked exception. Khi future hoàn tất bất thường, nó ném `CompletionException`; nguyên nhân có thể được lấy qua `getCause()`.

~~~java
try {
    String value = future.join();
} catch (CompletionException ex) {
    if (ex.getCause() instanceof TimeoutException) {
        System.out.println("Future đã timeout");
    } else {
        throw ex;
    }
}
~~~

Không nên bắt mọi CompletionException rồi coi là timeout. Future cũng có thể lỗi do IOException, lỗi nghiệp vụ, lỗi lập trình hoặc một ngoại lệ khác.

## 4. So sánh orTimeout, completeOnTimeout và get(timeout)

Ba API đều có liên quan đến thời gian nhưng có tác động khác nhau:

| API | Khi hết hạn | Future có bị thay đổi không? | Kết quả quan sát |
|---|---|---|---|
| `orTimeout(t, unit)` | Hoàn tất bất thường với TimeoutException | Có, trên chính future | Lỗi timeout |
| `completeOnTimeout(value, t, unit)` | Hoàn tất bình thường bằng value | Có, trên chính future | Giá trị dự phòng |
| `get(t, unit)` | Luồng gọi ngừng chờ và nhận TimeoutException | Không | Future vẫn có thể tiếp tục hoàn tất sau đó |

### completeOnTimeout: dùng giá trị thay thế

Chữ ký:

~~~java
public CompletableFuture<T> completeOnTimeout(
    T value,
    long timeout,
    TimeUnit unit
)
~~~

Phương thức này cũng có từ Java 9 và cũng trả về chính future được gọi. Nếu future chưa hoàn tất trước thời hạn, nó được hoàn tất bình thường bằng giá trị đã cung cấp.

~~~java
CompletableFuture<String> response = loadAsync()
    .completeOnTimeout("Dữ liệu mặc định", 2, TimeUnit.SECONDS);
~~~

Đây là lựa chọn phù hợp khi ứng dụng chấp nhận một kết quả dự phòng, ví dụ dùng cấu hình mặc định hoặc hiển thị dữ liệu cache nếu dịch vụ phản hồi quá chậm.

Chỉ dùng giá trị dự phòng khi nó có ý nghĩa nghiệp vụ. Nếu timeout phải được coi là lỗi để tầng gọi retry, báo lỗi hoặc ghi nhận sự cố, dùng `orTimeout` sẽ thể hiện đúng trạng thái hơn.

### get(timeout, unit): chỉ giới hạn thời gian chờ của người gọi

~~~java
try {
    String value = future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    System.out.println("Luồng hiện tại chờ quá thời hạn");
}
~~~

Nếu `get(timeout, unit)` ném TimeoutException, điều đó không có nghĩa future đã hoàn tất bất thường. Future vẫn có thể đang pending và một luồng khác vẫn có thể gọi `complete(value)` sau đó.

Dùng `get(timeout, unit)` khi chỉ cần giới hạn thời gian chờ của luồng hiện tại mà không muốn thay đổi kết quả dùng chung của future.

## 5. orTimeout không tự dừng công việc nền

Đây là giới hạn quan trọng nhất khi dùng timeout với tác vụ bất đồng bộ.

~~~java
CompletableFuture<String> work = CompletableFuture.supplyAsync(() -> {
    performSlowOperation();
    return "done";
});

work.orTimeout(1, TimeUnit.SECONDS);
~~~

Khi quá một giây, future có thể hoàn tất bất thường với TimeoutException trong khi `performSlowOperation()` vẫn đang chạy. Timeout thay đổi trạng thái của CompletableFuture; nó không tự gửi tín hiệu dừng tới mã đang thực thi bên trong Supplier, không tự đóng socket và không tự hủy truy vấn cơ sở dữ liệu.

Vì vậy cần phân biệt:

- **Timeout của kết quả:** caller không còn chờ kết quả bình thường sau thời hạn.
- **Hủy công việc:** yêu cầu tác vụ đang chạy dừng thực thi và giải phóng tài nguyên.

Hai việc này không đồng nghĩa. Nếu cần hủy công việc thực sự, phải dùng cơ chế hủy của chính API nền, chẳng hạn hủy request HTTP, đóng tài nguyên đang chờ, truyền cancellation token hoặc quản lý một Future của ExecutorService có thể hủy theo chính sách của tác vụ.

Đối với `CompletableFuture.cancel(true)`, tham số `mayInterruptIfRunning` không được dùng để điều khiển việc thực thi trong implementation CompletableFuture. Không nên dựa vào `cancel(true)` để chắc chắn ngắt một Supplier đang chạy.

## 6. Đặt timeout cho future dùng chung và copy()

Vì `orTimeout` thay đổi chính future được gọi, hãy chú ý khi nhiều thành phần cùng giữ một tham chiếu:

~~~java
CompletableFuture<Response> shared = service.fetchAsync();

// Lời gọi này cũng đặt timeout cho mọi nơi đang dùng shared.
shared.orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu mỗi caller cần một thời hạn riêng, có thể tạo một future độc lập bằng `copy()` rồi đặt timeout lên bản sao:

~~~java
CompletableFuture<Response> callerView = shared.copy()
    .orTimeout(2, TimeUnit.SECONDS);
~~~

`copy()` cũng có từ Java 9. Bản sao sẽ phản ánh kết quả hoặc lỗi của future nguồn khi nguồn hoàn tất. Nếu callerView timeout, future nguồn không vì thế mà bị timeout; công việc nguồn vẫn có thể hoàn tất và cung cấp kết quả cho caller khác.

Cách này tách trạng thái hoàn tất của future dành cho caller khỏi trạng thái của future nguồn. Nó vẫn không tự dừng tác vụ nền khi callerView hết hạn.

## 7. Xử lý timeout trong chuỗi CompletionStage

Có thể đặt timeout trước khi nối các bước xử lý:

~~~java
CompletableFuture<User> user = loadUserAsync(userId)
    .orTimeout(2, TimeUnit.SECONDS)
    .thenApply(this::validateUser);
~~~

Nếu tải người dùng timeout, bước `thenApply` không chạy với giá trị bình thường; stage kết quả hoàn tất bất thường và lỗi được truyền tiếp.

### Phục hồi riêng trường hợp timeout bằng exceptionally

`exceptionally` tạo một stage phụ thuộc và cho phép chuyển lỗi thành giá trị dự phòng:

~~~java
CompletableFuture<String> response = loadAsync()
    .orTimeout(2, TimeUnit.SECONDS)
    .exceptionally(error -> {
        Throwable cause = error;
        while (cause instanceof CompletionException
                && cause.getCause() != null) {
            cause = cause.getCause();
        }

        if (cause instanceof TimeoutException) {
            return "fallback";
        }

        throw new CompletionException(cause);
    });
~~~

Ví dụ này chỉ phục hồi TimeoutException. Các lỗi khác tiếp tục được truyền đi bằng CompletionException để không vô tình che giấu lỗi thật.

### handle và whenComplete

- `handle((value, error) -> ...)` xử lý cả kết quả bình thường lẫn lỗi và có thể tạo giá trị thay thế.
- `whenComplete((value, error) -> ...)` phù hợp để ghi log hoặc quan sát kết quả; nó không phải API chuyên dùng để phục hồi lỗi.

Nếu mục tiêu chỉ là ghi nhận timeout, có thể dùng whenComplete:

~~~java
future.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Future hoàn tất với lỗi: " + error);
    }
});
~~~

Khi cần phân biệt timeout với các lỗi khác, hãy kiểm tra nguyên nhân sau khi xử lý lớp bọc CompletionException.

## 8. Chọn thời hạn và đặt timeout đúng vị trí

Một số nguyên tắc thực tế:

1. Đặt timeout ở ranh giới của thao tác có thời hạn nghiệp vụ rõ ràng, chẳng hạn gọi dịch vụ, truy vấn hoặc xử lý một request.
2. Chọn đơn vị phù hợp qua `TimeUnit`, ví dụ MILLISECONDS, SECONDS hoặc MINUTES.
3. Đặt timeout của từng bước nhỏ hơn hoặc bằng thời hạn tổng của request nếu ứng dụng có deadline tổng.
4. Không đặt một timeout quá ngắn cho công việc có thời gian xử lý dao động tự nhiên.
5. Ghi nhận timeout riêng với lỗi nghiệp vụ và lỗi hạ tầng để theo dõi chính xác.
6. Nếu có retry, tính thời gian còn lại trong deadline tổng; không để mỗi lần retry tự dùng toàn bộ thời hạn ban đầu.
7. Nếu công việc cần dừng thật sự, kết hợp timeout với cơ chế cancellation của dịch vụ hoặc tác vụ nền.

Thời điểm timeout là thời điểm hệ thống kích hoạt hành động hoàn tất bất thường. Việc callback hoặc luồng quan sát kết quả được chạy còn phụ thuộc lịch thực thi; không nên xem timeout là cam kết rằng mọi luồng đã dừng chính xác tại một mili giây cụ thể.

## 9. Ví dụ Java chạy được

Ví dụ sau kiểm tra:

- `orTimeout` trả về cùng đối tượng và hoàn tất bất thường.
- `completeOnTimeout` cung cấp giá trị mặc định.
- `get(timeout, unit)` hết thời gian chờ nhưng không thay đổi future.
- `copy()` cho phép đặt timeout riêng lên future của caller.
- `exceptionally` phục hồi riêng TimeoutException.
- Supplier chạy nền vẫn hoàn tất sau khi future đã timeout.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class CompletableFutureTimeoutExample {
    public static void main(String[] args) throws Exception {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletableFuture<String> timed = pending.orTimeout(
            80, TimeUnit.MILLISECONDS
        );
        System.out.println("orTimeout returns same future="
            + (pending == timed));

        try {
            timed.get(2, TimeUnit.SECONDS);
        } catch (ExecutionException ex) {
            System.out.println("orTimeout cause="
                + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("timed exceptionally="
            + timed.isCompletedExceptionally());

        CompletableFuture<String> fallback = new CompletableFuture<>();
        fallback.completeOnTimeout("fallback", 50, TimeUnit.MILLISECONDS);
        System.out.println("completeOnTimeout value="
            + fallback.get(2, TimeUnit.SECONDS));

        CompletableFuture<String> waitOnly = new CompletableFuture<>();
        try {
            waitOnly.get(50, TimeUnit.MILLISECONDS);
        } catch (TimeoutException ex) {
            System.out.println("get timeout="
                + ex.getClass().getSimpleName());
        }
        System.out.println("future done after get timeout=" + waitOnly.isDone());
        waitOnly.complete("later");
        System.out.println("future result after completion=" + waitOnly.get());

        CompletableFuture<String> sharedSource = new CompletableFuture<>();
        CompletableFuture<String> callerView = sharedSource.copy()
            .orTimeout(50, TimeUnit.MILLISECONDS);
        try {
            callerView.get(2, TimeUnit.SECONDS);
        } catch (ExecutionException ex) {
            System.out.println("copy timeout cause="
                + ex.getCause().getClass().getSimpleName());
        }
        System.out.println("source still pending=" + !sharedSource.isDone());
        sharedSource.complete("source value");
        System.out.println("source result=" + sharedSource.join());

        CompletableFuture<String> recovered = new CompletableFuture<String>()
            .orTimeout(50, TimeUnit.MILLISECONDS)
            .exceptionally(error -> {
                Throwable cause = error;
                while (cause instanceof CompletionException
                        && cause.getCause() != null) {
                    cause = cause.getCause();
                }
                if (cause instanceof TimeoutException) {
                    return "fallback after timeout";
                }
                throw new CompletionException(cause);
            });
        System.out.println("recovered value="
            + recovered.get(2, TimeUnit.SECONDS));

        CompletableFuture<String> running = CompletableFuture.supplyAsync(() -> {
            try {
                Thread.sleep(250);
                System.out.println("supplier finished");
                return "work result";
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new CompletionException(ex);
            }
        });

        CompletableFuture<String> runningTimed =
            running.orTimeout(40, TimeUnit.MILLISECONDS);
        try {
            runningTimed.get(2, TimeUnit.SECONDS);
        } catch (ExecutionException ex) {
            System.out.println("running timeout cause="
                + ex.getCause().getClass().getSimpleName());
        }

        Thread.sleep(350);
        System.out.println("underlying supplier completed after timeout");
    }
}
~~~

Lưu trong tệp `CompletableFutureTimeoutExample.java`, biên dịch và chạy với Java 9 trở lên:

~~~shell
javac --release 9 -Xlint:all CompletableFutureTimeoutExample.java
java CompletableFutureTimeoutExample
~~~

Kết quả stdout chính xác:

~~~text
orTimeout returns same future=true
orTimeout cause=TimeoutException
timed exceptionally=true
completeOnTimeout value=fallback
get timeout=TimeoutException
future done after get timeout=false
future result after completion=later
copy timeout cause=TimeoutException
source still pending=true
source result=source value
recovered value=fallback after timeout
running timeout cause=TimeoutException
supplier finished
underlying supplier completed after timeout
~~~

Phân tích:

1. `orTimeout` trả về cùng đối tượng future và làm future hoàn tất bất thường khi hết hạn.
2. `get()` nhận ExecutionException; nguyên nhân bên trong là TimeoutException.
3. `completeOnTimeout` hoàn tất bình thường bằng chuỗi `fallback`.
4. `get(timeout, unit)` ném TimeoutException cho lần chờ, nhưng `waitOnly.isDone()` vẫn false. Future có thể được hoàn tất sau đó bằng `complete("later")`.
5. Timeout trên bản sao `callerView` không làm `sharedSource` hoàn tất. Future nguồn vẫn có thể nhận kết quả bình thường.
6. `exceptionally` nhận lỗi timeout và chuyển thành giá trị dự phòng; các lỗi khác vẫn được truyền tiếp.
7. Supplier của `supplyAsync` in `supplier finished` sau khi future đã timeout. Đây là bằng chứng timeout không tự dừng công việc nền.

## 10. Những lỗi thường gặp

- **Nghĩ orTimeout chỉ làm luồng gọi ngừng chờ:** sai. Nó hoàn tất chính CompletableFuture bất thường.
- **Nghĩ orTimeout tạo một future mới:** sai. Nó trả lại cùng đối tượng; các tham chiếu khác cũng thấy trạng thái timeout.
- **Dùng get(timeout) rồi cho rằng future đã lỗi:** sai. Chỉ lần chờ bị timeout; future vẫn có thể hoàn tất sau đó.
- **Dùng completeOnTimeout khi timeout phải là lỗi:** giá trị mặc định có thể che giấu sự cố dịch vụ nếu nghiệp vụ cần biết timeout.
- **Cho rằng orTimeout tự hủy HTTP request hoặc truy vấn:** sai. Phải gọi cơ chế cancellation của API nền nếu muốn dừng công việc thật sự.
- **Bắt mọi ExecutionException rồi coi là TimeoutException:** hãy kiểm tra `getCause()` để phân biệt timeout với lỗi khác.
- **Bắt mọi CompletionException rồi trả fallback:** có thể che giấu lỗi lập trình hoặc lỗi nghiệp vụ; chỉ phục hồi các nguyên nhân đã xác định.
- **Đặt timeout lên future dùng chung mà không để ý alias:** caller khác có thể bị ảnh hưởng vì orTimeout thay đổi chính future nguồn.
- **Dùng timeout riêng cho từng caller nhưng sửa future nguồn:** dùng `copy().orTimeout(...)` nếu cần tách trạng thái timeout của caller.
- **Dựa vào timeout để giải phóng tài nguyên:** timeout không thay thế finally, close, cancellation hoặc cơ chế dọn dẹp của tác vụ nền.

## 11. Tài liệu tham khảo chính thức

- [CompletableFuture — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): hợp đồng của `orTimeout`, `completeOnTimeout`, `copy`, `get`, `join`, `cancel` và các stage xử lý lỗi.
- [CompletionStage — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html): cách nối stage và truyền kết quả/lỗi.
- [TimeUnit — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/TimeUnit.html): các đơn vị thời gian dùng trong timeout.
- [Future — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html): hợp đồng chờ, timeout và hủy tác vụ.