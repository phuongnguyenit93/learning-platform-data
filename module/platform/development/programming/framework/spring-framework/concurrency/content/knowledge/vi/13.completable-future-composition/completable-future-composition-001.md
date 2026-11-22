# thenApply() biến đổi kết quả và thenCompose() nối công việc phụ thuộc

> **Module:** Spring Framework – concurrency  
> **Nhóm:** Kết hợp CompletableFuture  
> **Mục tiêu:** Hiểu cách tạo một pipeline phụ thuộc bằng `CompletableFuture`: `thenApply()` biến đổi **giá trị** của một giai đoạn đã hoàn tất, còn `thenCompose()` dùng kết quả để **khởi động hoặc kết nối một giai đoạn bất đồng bộ khác** rồi làm phẳng kết quả. Phân biệt rõ kiểu trả về, thời điểm chạy callback, executor, lỗi và giới hạn vận hành trong ứng dụng Spring.

## 1. Câu trả lời ngắn: map khác flatMap

Hai phương thức cùng chỉ được kích hoạt khi giai đoạn trước **hoàn tất bình thường** và cùng nhận giá trị của giai đoạn đó. Khác biệt nằm ở **giá trị mà hàm callback trả về** và **kiểu của future kế tiếp**:

- `thenApply(fn)`: callback nhận `T`, trả `U`. Kết quả là `CompletableFuture<U>`. Dùng khi đã có giá trị và chỉ cần chuyển nó thành một giá trị mới, ví dụ `User -> user.name()`, `Order -> OrderDto`, `Integer -> String`.
- `thenCompose(fn)`: callback nhận `T`, trả một `CompletionStage<U>`. Kết quả là `CompletableFuture<U>` **được nối/làm phẳng**, chỉ hoàn tất theo kết quả của giai đoạn mà callback trả về. Dùng khi bước kế tiếp **phụ thuộc vào kết quả bước trước** và bản thân bước kế tiếp đã trả về một async stage, ví dụ `userId -> fetchOrdersAsync(userId)`.

Có thể ghi nhớ bằng phép so sánh về hình dạng dữ liệu:

~~~text
CompletableFuture<T>
    .thenApply(T -> U)
          => CompletableFuture<U>

CompletableFuture<T>
    .thenApply(T -> CompletableFuture<U>)
          => CompletableFuture<CompletableFuture<U>>  [LỒNG NHAU]

CompletableFuture<T>
    .thenCompose(T -> CompletionStage<U>)
          => CompletableFuture<U>                     [LÀM PHẲNG]
~~~

`thenCompose` gần với `flatMap` trong cách tổ hợp giá trị bọc; `thenApply` gần với `map`. Đây là cách giải thích bằng tương tự, không phải chữ ký API thực tế giống `Stream` hoặc `Optional`.

## 2. CompletableFuture và CompletionStage biểu diễn điều gì?

`CompletableFuture<T>` của JDK vừa là `Future<T>` (quan sát/đợi kết quả), vừa triển khai `CompletionStage<T>` (đăng ký bước xử lý phụ thuộc).

Một stage có thể ở trạng thái **chưa hoàn tất**, **hoàn tất bình thường với giá trị T** hoặc **hoàn tất ngoại lệ**. Hàm `thenApply`/`thenCompose` tạo ra một stage mới; nó không biến đổi hay thay thế chính đối tượng future nguồn, và cũng không bảo đảm callback chạy trên thread khác.

Ví dụ pipeline:

~~~text
fetchUserAsync("u-17") : CompletableFuture<User>
                  |
                  v  thenApply(user -> user.id())
              CompletableFuture<String>
                  |
                  v  thenCompose(id -> fetchOrdersAsync(id))
              CompletableFuture<List<Order>>
                  |
                  v  thenApply(orders -> toSummary(orders))
              CompletableFuture<Summary>
~~~

Trong sơ đồ, bước lấy đơn hàng cần `id` của user. Vì `fetchOrdersAsync(id)` tự trả về `CompletableFuture<List<Order>>`, dùng `thenCompose` ở đoạn đó sẽ giữ pipeline có kiểu cuối dễ sử dụng, không phải `CompletableFuture<CompletableFuture<List<Order>>>`.

**“Bất đồng bộ” không có nghĩa mọi callback đều chạy bất đồng bộ.** Future có thể đã hoàn tất trước khi gắn callback; callback không có hậu tố `Async` có thể chạy ngay khi đăng ký hoặc trên thread đang hoàn tất stage nguồn. Việc đợi bằng `join()`/`get()` ở caller vẫn là hành động chặn nếu giá trị chưa sẵn sàng.

## 3. Chữ ký kiểu và cách chọn

Trong `CompletableFuture<T>`, các phương thức có dạng tổng quát:

~~~java
<U> CompletableFuture<U> thenApply(Function<? super T, ? extends U> fn)

<U> CompletableFuture<U> thenCompose(
    Function<? super T, ? extends CompletionStage<U>> fn)
~~~

Đây là **chữ ký API rút gọn**, không phải hai phương thức cần chép vào class Java. `CompletionStage<U>` là interface: callback của `thenCompose` không bắt buộc trả đúng class `CompletableFuture<U>`, chỉ cần trả một stage tương thích.

Bảng lựa chọn nhanh:

| Callback trả về | Dùng | Kiểu kết quả mong muốn |
| --- | --- | --- |
| Giá trị đơn `String`, `int`, `Dto`, `List<Order>` | `thenApply` | `CompletableFuture<U>` |
| `CompletionStage<U>` hoặc `CompletableFuture<U>` | `thenCompose` | `CompletableFuture<U>` đã flatten |
| Cần dùng cả hai future **độc lập** và chờ chúng xong | Thường `thenCombine`/`allOf` | Phối hợp song song, không phụ thuộc đầu ra trước |
| Không cần tạo giá trị mới, chỉ tiêu thụ kết quả | `thenAccept` | `CompletableFuture<Void>` |
| Không cần input của stage trước, chỉ chạy hành động khi xong | `thenRun` | `CompletableFuture<Void>` |

**Không chọn theo kích thước công việc.** “Bước xử lý nặng thì dùng `thenCompose`” là sai. Chọn `thenCompose` vì callback trả một *stage*, còn chuyện chạy trên executor nào được điều khiển bằng cơ chế khác.

## 4. thenApply(): biến đổi một giá trị đồng bộ về mặt callback

Với `CompletableFuture<User>`, ta có thể đổi `User` thành DTO ngay sau khi nhận dữ liệu:

~~~java
CompletableFuture<String> displayName =
    userFuture.thenApply(user -> user.name().trim().toUpperCase());
~~~

Đây là **đoạn ghép vào ứng dụng** giả định đã có `userFuture` kiểu `CompletableFuture<User>` và `User.name()` trả `String`. Khi user future thành công, callback chạy và sinh một chuỗi; future mới hoàn tất với chuỗi đó.

Những điều quan trọng:

1. `thenApply` **không yêu cầu tạo một task mới** trên thread pool. Hàm mapper có thể được thực thi inline theo chính sách completion của `CompletableFuture`.
2. Nếu stage nguồn hoàn tất ngoại lệ, callback mapping thông thường **không chạy**; stage phụ thuộc hoàn tất ngoại lệ.
3. Nếu mapper ném exception, stage mới hoàn tất ngoại lệ, không ném trực tiếp sang luồng caller đang đăng ký một continuation đang đợi.
4. Mapper trả `null` là hợp lệ và stage mới hoàn tất bình thường với `null`; cần xử lý khi nghiệp vụ không cho phép giá trị null.
5. Mapper không tự làm I/O bất đồng bộ. Nếu bên trong nó gọi network/DB theo kiểu blocking, nó vẫn giữ thread chạy callback cho đến khi lời gọi xong.

**Dùng `thenApply` cho biến đổi ngắn, thuần hoặc nhẹ** là lựa chọn thường thuận tiện; khi callback cần CPU nặng hoặc có yêu cầu cách ly tài nguyên, cân nhắc `thenApplyAsync(fn, executor)` trên executor được cấp phát và giới hạn rõ.

## 5. thenCompose(): một bước phụ thuộc trả về stage khác

Giả sử API của hệ thống đã có:

~~~java
CompletableFuture<User> fetchUserAsync(String userId);
CompletableFuture<List<Order>> fetchOrdersAsync(String userId);
~~~

Đây là **hai chữ ký minh họa**, không phải chương trình độc lập; `User` và `Order` là kiểu nghiệp vụ cần định nghĩa.

Khi bước lấy orders cần ID user từ bước trước:

~~~java
CompletableFuture<List<Order>> ordersFuture =
    fetchUserAsync("u-17")
        .thenCompose(user -> fetchOrdersAsync(user.id()));
~~~

Cơ chế:

1. `fetchUserAsync` trả một future. Callback bên trong `thenCompose` **chưa chạy** khi future nguồn chưa hoàn thành bình thường.
2. Khi user sẵn sàng, callback lấy `user.id()` rồi gọi `fetchOrdersAsync`, nhận về **một stage khác**.
3. Future do `thenCompose` trả ra sẽ hoàn tất dựa trên outcome của stage orders, chứ không hoàn tất chỉ vì callback đã trả về object future.
4. Bước kế tiếp `.thenApply(orders -> ...)` sẽ nhận trực tiếp `List<Order>`, không cần bóc thêm một lớp future.

Đây là **nối giai đoạn phụ thuộc**, không phải tự tạo concurrency song song. Việc gọi `fetchOrdersAsync` xảy ra **sau khi** user stage hoàn tất; bất đồng bộ thực tế của việc lấy orders phụ thuộc implementation của `fetchOrdersAsync`.

Nếu callback trả `null` thay vì một `CompletionStage` hợp lệ, stage kết quả sẽ thất bại (thường bằng `NullPointerException`). Không nên dùng `null` để biểu diễn “không có bước kế tiếp”; hãy dùng `CompletableFuture.completedFuture(defaultValue)` hoặc stage hoàn tất phù hợp theo hợp đồng nghiệp vụ.

## 6. Lỗi future lồng nhau khi dùng thenApply cho thao tác async

Một sự nhầm lẫn thường gặp:

~~~java
CompletableFuture<CompletableFuture<List<Order>>> nested =
    fetchUserAsync("u-17")
        .thenApply(user -> fetchOrdersAsync(user.id()));
~~~

Kiểu lồng nhau là **đúng về mặt Java**, nhưng thường bất tiện:

- `nested` có thể hoàn tất bình thường ngay khi callback trả về object `ordersFuture`, **dù orders vẫn chưa tải xong**.
- `nested.get()` trả về **một future nữa**, không trả danh sách orders.
- Lỗi ở **future bên trong** có thể chưa phản ánh như một exceptional completion của future bên ngoài. Nếu code chỉ kiểm tra future ngoài, có thể kết luận sai rằng cả công việc thành công.
- Các đoạn mã sau cần hai lần bóc lớp hoặc tự nối thêm callback, dễ tăng độ phức tạp và rủi ro xử lý lỗi thiếu.

Cách sửa:

~~~java
CompletableFuture<List<Order>> flat =
    fetchUserAsync("u-17")
        .thenCompose(user -> fetchOrdersAsync(user.id()));
~~~

Mọi bước sau nhận trực tiếp `List<Order>`; lỗi phát sinh trong một trong hai giai đoạn sẽ đi theo đường exceptional completion của chuỗi kết quả.

**Chú ý:** `thenCompose` không “hủy” stage nội bộ hay ngăn nó chạy; nó chỉ biểu diễn phụ thuộc và điều phối completion. Tác vụ đang chạy, cơ chế cancel/timeout và tài nguyên downstream vẫn cần thiết kế riêng.

## 7. Ví dụ Java 17+ chạy độc lập

Ví dụ sau minh họa đồng thời biến đổi giá trị, future lồng nhau, nối future phụ thuộc, tạo báo cáo và fallback lỗi. Nó chỉ dùng JDK, không cần Spring để thấy sự khác biệt kiểu và hành vi; khi tích hợp Spring, nguồn future có thể đến từ `@Async` hoặc `AsyncTaskExecutor`.

Tạo file **ComposeDemo.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ComposeDemo {
    static CompletableFuture<String> findOrderAsync(
            String userId, ExecutorService pool) {
        return CompletableFuture.supplyAsync(
            () -> "order-" + userId, pool);
    }

    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            CompletableFuture<String> user =
                CompletableFuture.supplyAsync(() -> "u-17", pool);

            CompletableFuture<String> transformed =
                user.thenApply(id -> "user=" + id);

            CompletableFuture<CompletableFuture<String>> nested =
                user.thenApply(id -> findOrderAsync(id, pool));

            CompletableFuture<String> flattened =
                user.thenCompose(id -> findOrderAsync(id, pool));

            CompletableFuture<String> report =
                user.thenCompose(id -> findOrderAsync(id, pool))
                    .thenApply(order -> "summary:" +
                        order.toUpperCase(Locale.ROOT));

            System.out.println("apply = " + transformed.join());
            System.out.println("nested = " + nested.join().join());
            System.out.println("compose = " + flattened.join());
            System.out.println("chain = " + report.join());

            CompletableFuture<String> failure =
                CompletableFuture.<String>failedFuture(
                    new IllegalStateException("downstream unavailable"))
                .thenApply(String::toUpperCase);
            System.out.println("recovery = " +
                failure.exceptionally(error -> "fallback").join());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac ComposeDemo.java
java ComposeDemo
~~~

**Stdout chính xác của chương trình**:

~~~text
apply = user=u-17
nested = order-u-17
compose = order-u-17
chain = summary:ORDER-U-17
recovery = fallback
~~~

Ví dụ đã được **biên dịch và thực thi với JDK hỗ trợ Java 17+**; các dòng `System.out.println` có thứ tự xác định vì caller `join()` từng future theo thứ tự mong muốn, bất kể hai worker hoàn tất công việc lúc nào.

Đọc theo kiểu:

- `transformed`: `CompletableFuture<String>` từ một phép chuyển giá trị đơn.
- `nested`: `CompletableFuture<CompletableFuture<String>>`; chỉ để minh họa ta gọi `nested.join().join()` ở **thread main**. Không nên sao chép cách blocking lồng nhau đó vào callback chạy trong pool.
- `flattened`: `CompletableFuture<String>` trực tiếp, chỉ cần một `join()` tại ranh giới cuối của chương trình.
- `report`: `thenCompose` lấy order theo user, `thenApply` biến order thành chuỗi báo cáo.
- `failure`: stage trước hoàn tất ngoại lệ, `thenApply` không thực thi mapper, `exceptionally` trả chuỗi fallback.

Trong ví dụ, `findOrderAsync` mô phỏng việc bất đồng bộ bằng `supplyAsync`, chưa phải một HTTP client thật. Một client HTTP hỗ trợ API bất đồng bộ có thể trả future mà không chiếm worker trong thời gian chờ network; ngược lại, đặt blocking call trong `supplyAsync` vẫn dùng một worker suốt thời gian call.

## 8. Kết hợp với Spring @Async đúng cách

Spring `@Async` có thể trả `CompletableFuture<T>` để caller tiếp tục ghép stage. Điều kiện chính:

1. Bật `@EnableAsync` trong `ApplicationContext` phù hợp.
2. Gọi method `@Async` **qua proxy Spring**; self-invocation `this.method()` trong proxy mode thường bỏ qua interceptor.
3. Có executor phù hợp, tránh để công việc sản phẩm phụ thuộc vào cấu hình concurrency không kiểm soát.
4. Method `@Async` trả `CompletableFuture` đã hoàn tất cục bộ từ **worker** khi công việc trong thân method xong; proxy cung cấp future cho caller để quan sát/nối bước tiếp theo.
5. Đặt các bước async phụ thuộc vào một service được inject, không gọi `join()` trong worker chỉ để đợi một task khác của cùng pool.

Ví dụ **tích hợp Spring Framework**, cần dependency Spring context, được ApplicationContext nạp; không phải tệp Java độc lập chỉ bằng `javac`:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfig {
    @Bean("ioExecutor")
    ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("io-");
        return pool;
    }
}

@Service
class RemoteLookup {
    @Async("ioExecutor")
    public CompletableFuture<String> fetchUserId(String ref) {
        // Minh họa: thay bằng tác vụ I/O thực tế.
        return CompletableFuture.completedFuture("u-" + ref);
    }

    @Async("ioExecutor")
    public CompletableFuture<String> fetchOrder(String userId) {
        return CompletableFuture.completedFuture("order-" + userId);
    }
}

@Service
class SummaryService {
    private final RemoteLookup remote;

    SummaryService(RemoteLookup remote) {
        this.remote = remote;
    }

    public CompletableFuture<String> summary(String ref) {
        return remote.fetchUserId(ref)
            .thenCompose(remote::fetchOrder)
            .thenApply(order -> "summary:" + order);
    }
}
~~~

Một caller bên ngoài gọi `SummaryService.summary("17")` sẽ nhận `CompletableFuture<String>` có giá trị thành công là **`summary:order-u-17`**. Trong cấu hình này, `RemoteLookup` là **bean khác** so với `SummaryService`, nên `remote::fetchOrder` đi qua proxy `@Async`. Nếu đổi thành `this.fetchOrder(...)` trong cùng instance đang annotate, hiệu lực async có thể khác vì self-invocation.

**Không kết luận rằng `thenCompose` tự thêm một lần submit lên `ioExecutor`.** Lệnh submit ở bước thứ hai có được thực hiện là do lời gọi `remote.fetchOrder` đi qua `@Async` interceptor. `thenCompose` chỉ gắn kết future trả về. Nếu `fetchOrder` là API không async, chỉ dùng `thenCompose` không làm nó trở thành I/O bất đồng bộ.

Có thể tạo future trực tiếp từ `AsyncTaskExecutor.submitCompletable(Callable<T>)` trong Spring Framework 6.0+, hoặc từ các API I/O bất đồng bộ. Để kết hợp, chỉ cần các stage có kiểu tương thích; nguồn future không nhất thiết cùng thư viện hay executor.

## 9. thenApplyAsync / thenComposeAsync khác ở đâu?

Hai phương thức chính có các biến thể `Async`:

~~~java
future.thenApply(x -> transform(x));
future.thenApplyAsync(x -> transform(x));
future.thenApplyAsync(x -> transform(x), executor);

future.thenCompose(x -> fetchAsync(x));
future.thenComposeAsync(x -> fetchAsync(x));
future.thenComposeAsync(x -> fetchAsync(x), executor);
~~~

Đây là **đoạn API tích hợp minh họa**; các hàm `transform`, `fetchAsync`, biến `future`/`executor` cần có trong ứng dụng.

- Không hậu tố `Async`: hành động phụ thuộc có thể chạy ở thread hoàn tất future nguồn hoặc thread khác tham gia completion; nếu nguồn đã hoàn tất trước khi gắn stage, callback có thể chạy ngay trên thread đang đăng ký.
- Hậu tố `Async`, **không truyền executor**: với `CompletableFuture` chuẩn của JDK 17, sử dụng default async executor; thông thường là `ForkJoinPool.commonPool()`, trừ điều kiện parallelism nhỏ hoặc subclass thay đổi default executor. Không mặc định dùng `ThreadPoolTaskExecutor` của Spring đã tạo future nguồn.
- Hậu tố `Async`, **truyền executor**: lịch callback trên executor được chỉ rõ, giúp giới hạn/cách ly CPU hoặc I/O callback theo thiết kế. Nếu executor từ chối task, stage phụ thuộc có thể hoàn tất ngoại lệ do việc lập lịch thất bại.
- Dù có hậu tố `Async`, **`thenApply` vẫn chỉ biến đổi giá trị** và **`thenCompose` vẫn nối một stage khác**. Hai trục khái niệm độc lập: *kiểu kết quả* và *cách lên lịch callback*.

Không mặc định biến mọi stage thành `thenApplyAsync` hay `thenComposeAsync`: liên tục chuyển pool có overhead, làm rối thread context và tạo các giới hạn tải riêng. Biến đổi chuỗi rất nhẹ thường không cần một lần scheduling riêng. Công việc CPU nặng hoặc callback có khả năng chặn cần được phân bổ executor phù hợp.

## 10. Không gọi join/get bên trong callback để “tháo” future

Một anti-pattern:

~~~java
CompletableFuture<List<Order>> result =
    fetchUserAsync("u-17")
        .thenApply(user ->
            fetchOrdersAsync(user.id()).join());
~~~

Mặc dù kiểu trả về lúc này là `CompletableFuture<List<Order>>`, callback phải **chờ đồng bộ** future orders qua `join()`. Nếu nó chạy trên một worker của pool nhỏ mà orders cũng cần pool đó, các worker có thể bị giữ để đợi việc đang xếp hàng, thậm chí dẫn đến **thread starvation/deadlock**. Đường xử lý còn khó quản lý timeout và cancellation.

Cách sửa:

~~~java
CompletableFuture<List<Order>> result =
    fetchUserAsync("u-17")
        .thenCompose(user -> fetchOrdersAsync(user.id()));
~~~

Ở đây callback **trả stage**, không đợi kết quả của stage bên trong. Khi orders hoàn tất, chain tự hoàn tất; thread chạy callback có thể tiếp tục phục vụ tác vụ khác. Caller vẫn có thể dùng `get()`/`join()` tại **ranh giới đồng bộ thật sự**, như chương trình CLI hoặc test, khi nó chấp nhận blocking.

**Ngoại lệ kỹ thuật:** nếu stage bên trong đã hoàn tất, `join()` có thể trả về ngay. Nhưng mã nghiệp vụ không nên dựa vào điều đó như bảo đảm cho mọi lần chạy.

## 11. Lỗi truyền theo chuỗi và vị trí recovery

Nếu giai đoạn nguồn hoàn tất ngoại lệ, `thenApply`/`thenCompose` được gắn vào nó **không chạy callback bình thường**. Stage phụ thuộc sẽ hoàn tất ngoại lệ; lỗi có thể được bọc trong `CompletionException` khi gọi `join()`, hoặc `ExecutionException` khi gọi `get()`.

Ví dụ:

~~~java
CompletableFuture<String> safeReport =
    fetchUserAsync("u-17")
        .thenCompose(user -> fetchOrdersAsync(user.id()))
        .thenApply(orders -> renderReport(orders))
        .exceptionally(error -> "report unavailable");
~~~

Đây là **đoạn tích hợp minh họa**. `exceptionally` trả một giá trị thay thế, nghĩa là chain mới có thể kết thúc **thành công** với `"report unavailable"`. Đặt fallback cuối chuỗi như vậy có thể nuốt cả lỗi lập trình ở `renderReport`, lỗi downstream và cancellation. Cần phân loại lỗi, log correlation ID, gắn metric và chỉ fallback những lỗi mà nghiệp vụ thực sự cho phép.

Phân biệt công cụ:

| API | Khi nào callback chạy | Kết quả |
| --- | --- | --- |
| `thenApply` | Source hoàn tất bình thường | Tạo giá trị mới, lỗi mapper làm stage mới exceptional |
| `thenCompose` | Source hoàn tất bình thường | Chạy bước phụ thuộc trả stage, kết quả đi theo stage đó |
| `exceptionally(fn)` | Source hoàn tất ngoại lệ | Trả giá trị fallback để **khôi phục** stage mới |
| `handle((value,error) -> ...)` | Source thành công hoặc lỗi | Biến cả hai tình huống thành một kết quả do handler quyết định |
| `whenComplete((value,error) -> ...)` | Source thành công hoặc lỗi | Thích hợp ghi nhận side effect/log; thường giữ outcome gốc nếu callback không tự gây lỗi |

Nếu callback của `thenCompose` ném exception **trước khi** trả stage, future ngoài thất bại. Nếu callback trả một stage rồi stage đó thất bại, future ngoài cũng thất bại theo outcome của stage được nối. Đây là một lợi ích lớn của flatten: người dùng chain chỉ cần quan sát một future kết quả.

Đừng giả định `Future.get()` sẽ trả `null` khi có lỗi; nó ném exception. Nếu dùng `exceptionally` để biến lỗi thành kết quả hợp lệ thì phải quy định rõ trạng thái lỗi nghiệp vụ, không vô tình đánh dấu đơn hàng thất bại thành thành công.

## 12. Timeout và cancellation không tự dừng mọi tác vụ bên trong

Các hàm của `CompletableFuture` như `orTimeout` và `completeOnTimeout` hỗ trợ chính sách thời gian:

~~~java
CompletableFuture<Summary> withDeadline =
    reportFuture.orTimeout(2, TimeUnit.SECONDS);

CompletableFuture<Summary> withFallback =
    reportFuture.completeOnTimeout(defaultSummary, 2, TimeUnit.SECONDS);
~~~

Đây là **đoạn API minh họa** (cần import `TimeUnit` và biến nghiệp vụ). Cả hai phương thức thời gian này có thể **hoàn tất chính future được gọi** khi đến hạn. Nếu cùng gọi hai phương thức trên *cùng một instance*, chúng có thể tác động lẫn nhau; ví dụ tách biệt để minh họa, không phải hai timeout độc lập cùng áp lên một future.

- `orTimeout`: hoàn tất future bằng `TimeoutException` nếu chưa hoàn tất đúng hạn.
- `completeOnTimeout`: hoàn tất future bằng giá trị fallback nếu chưa xong đúng hạn.
- Timeout của future **không bảo đảm** tự hủy HTTP request, JDBC query, downstream job hoặc thread đã bắt đầu chạy. Cần timeout/cancel ở client thực, transaction và I/O boundary.
- `cancel(true)` trên `CompletableFuture` của JDK không có cơ chế interrupt tác vụ tính toán bên dưới như một `FutureTask` gắn với worker; nó là một kiểu exceptional completion. Các stage đã khởi động có thể tiếp tục gây side effect.
- Cancellation ở một stage không đồng nghĩa với propagation toàn bộ chain phụ thuộc đã được triển khai. Việc dừng tác vụ, thu hồi tài nguyên và tránh tạo dữ liệu trùng phải thiết kế theo hệ thống thực.

Một pipeline phụ thuộc có thể bị timeout trong khi stage nội bộ vẫn xử lý xong sau đó. Vì vậy dùng idempotency key, trạng thái cuối rõ ràng và metrics để xử lý kết quả đến muộn.

## 13. Hiệu năng, thread pool và context trong Spring

`thenCompose` giúp loại bỏ việc đợi blocking trong callback nhưng **không làm hệ thống có thêm công suất**. Khi ứng dụng dùng Spring `@Async` và nhiều task cùng dùng một `ThreadPoolTaskExecutor`:

1. Chọn `corePoolSize`, `maxPoolSize`, `queueCapacity`, chính sách từ chối và shutdown phù hợp. Queue quá dài có thể che giấu quá tải; queue hữu hạn cần xử lý rejection.
2. Ghi metric queue length, active worker, wait time, task duration, failure và timeout. Một future được tạo ra không có nghĩa là task chắc chắn được nhận/chạy thành công.
3. Callback CPU-heavy nên chạy trên executor chuyên dụng hoặc executor được kiểm soát; tránh biến `commonPool` thành nơi xử lý I/O blocking khối lượng lớn.
4. `ThreadLocal`, MDC, security và request context không tự bảo đảm truyền sang thread hoàn tất future/continuation. Khi cần context propagation, dùng `TaskDecorator` hoặc adapter/context mechanism phù hợp và dọn dữ liệu theo phạm vi.
5. Trong ứng dụng Spring imperative, transaction gắn với thread hiện tại. `thenCompose` **không truyền transaction caller sang worker khác**; mỗi bước ghi DB cần giao dịch đúng ranh giới và không giả định việc của stage trước đã commit trừ khi contract bảo đảm.
6. Bean singleton được nhiều stage cùng gọi phải thread-safe; `thenApply` không bảo vệ một `HashMap` mutable hay biến đếm dùng chung.
7. Nếu task cần sống qua JVM restart hoặc phải chạy đúng ít nhất một lần, `CompletableFuture` chỉ là trạng thái **trong bộ nhớ**, không phải durable queue. Dùng job store, outbox/idempotency, retry/backpressure thích hợp.

Một lưu ý quan trọng về quá tải: khi executor nộp task cho `@Async` bị reject, lời gọi `remote.fetchOrder(id)` có thể ném `TaskRejectedException`. Nếu chuyện này diễn ra bên trong callback `thenCompose`, chain sẽ hoàn tất ngoại lệ. Khi đó không retry nóng, không nộp dồn ngay vào pool bão hòa; sử dụng chính sách retry có giới hạn, backoff và jitter khi nghiệp vụ cho phép.

## 14. Phụ thuộc tuần tự hay độc lập song song?

Đừng dùng `thenCompose` cho hai yêu cầu **thực sự độc lập** chỉ vì cả hai đều bất đồng bộ. Ví dụ hai nguồn dữ liệu được gọi độc lập:

~~~java
CompletableFuture<Customer> customer = fetchCustomerAsync(id);
CompletableFuture<Discount> discount = fetchDiscountAsync(id);

CompletableFuture<Pricing> pricing =
    customer.thenCombine(discount,
        (c, d) -> calculatePricing(c, d));
~~~

Đây là **đoạn tích hợp minh họa**, giả định có API và kiểu `Customer`, `Discount`, `Pricing`. Hai yêu cầu đã có thể chạy song song vì cả hai được khởi tạo trước khi kết hợp; `thenCombine` chờ cả hai hoàn tất bình thường để tính pricing.

So sánh khi bước hai **thực sự cần kết quả bước một**:

~~~java
CompletableFuture<Pricing> pricing =
    fetchCustomerAsync(id)
        .thenCompose(customer ->
            fetchDiscountAsync(customer.tier())
                .thenApply(discount ->
                    calculatePricing(customer, discount)));
~~~

Trong trường hợp thứ hai, bước discount phụ thuộc `customer.tier()`, nên không thể khởi chạy đúng trước khi có customer. `thenCompose` nối request thứ hai, `thenApply` bên trong dùng cả customer đã capture và discount để tạo Pricing.

Phân biệt giúp thiết kế latency tốt hơn:

- **Dependency:** stage B cần output của A → `thenCompose`.
- **Independent:** A và B có thể khởi tạo ngay → `thenCombine`/`allOf`.
- **Synchronous mapping:** từ kết quả thành định dạng/DTO mới → `thenApply`.
- **Side effect không trả giá trị:** `thenAccept`/`thenRun` thích hợp hơn việc viết mapper luôn trả dummy value.

## 15. Các lỗi điển hình và cách sửa

| Hiểu nhầm / anti-pattern | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Dùng `thenApply` cho callback trả `CompletableFuture<U>` nhưng mong `U` | Tạo future lồng nhau | Dùng `thenCompose` |
| Dùng `thenApply(x -> fetchAsync(x).join())` | Chặn callback thread, có thể starvation | Dùng `thenCompose(this::fetchAsync)` |
| Nghĩ `thenCompose` mặc định tạo thread mới | Sai về scheduling và resource | Phân biệt `thenCompose` với `thenComposeAsync`/executor |
| Luôn dùng `thenApplyAsync` không truyền executor trong ứng dụng Spring | Callback có thể chạy trong commonPool, khác pool Spring | Cấp executor tường minh khi cần kiểm soát |
| Bỏ qua future kết quả, chỉ nhìn future nguồn | Không theo dõi lỗi xảy ra ở stage phụ thuộc | Theo dõi **future cuối** của pipeline |
| Gọi `get()` ngay sau mỗi stage | Vô tình tuần tự hóa blocking ở caller | Nối stage, chỉ chờ tại boundary thật |
| Đặt `exceptionally` tổng quát và coi fallback là thành công nghiệp vụ | Nuốt lỗi dữ liệu hoặc lỗi lập trình | Chỉ recover lỗi cho phép; tách status/metric |
| Tin `orTimeout` đã dừng remote I/O | Tác vụ có thể tiếp tục sau timeout | Đặt client I/O timeout và cancel/compensation riêng |
| Gọi `@Async` bằng `this.method()` | Bỏ qua proxy, method chạy đồng bộ | Gọi bean thông qua Spring proxy / cấu trúc service phù hợp |
| Tin `thenCompose` chuyển transaction, MDC, security context | Context phụ thuộc thread và cơ chế propagation | Truyền context đúng quy định; giao dịch riêng |
| Trả `null` từ callback của `thenCompose` | Lỗi completion thay vì bỏ qua stage | Trả một `CompletionStage` hợp lệ |
| Cho nhiều task blocking dùng chung pool quá nhỏ | Queue tích tụ, có thể starvation/rejection | Phân biệt I/O và CPU pool, đo tải, giới hạn queue |

## 16. Kiểm thử để chứng minh pipeline hoạt động đúng

Một bộ kiểm thử tốt cho hai phương thức này không chỉ assert giá trị cuối, mà cần chứng minh cấu trúc và đường lỗi:

1. **Transform:** tạo `CompletableFuture.completedFuture(5)`, gọi `.thenApply(n -> n * 2)`; xác nhận `join() == 10`.
2. **Compose:** cho mapper trả một `CompletableFuture<String>` chưa hoàn tất; xác nhận outer stage sau `thenCompose` **chưa xong**, rồi complete inner và assert result.
3. **Nested type:** viết biến kiểu `CompletableFuture<CompletableFuture<String>>` với `thenApply`; compiler cho thấy chính xác lớp future lồng nhau.
4. **Source failure:** `failedFuture(new IllegalArgumentException(...))` phải khiến mapper thường không chạy; stage phụ thuộc fail.
5. **Inner stage failure:** callback của `thenCompose` trả stage fail; outer stage cũng fail và lỗi phải quan sát được.
6. **Executor:** dùng thread-name prefix hoặc custom executor kiểm chứng `thenApplyAsync(fn, executor)` sử dụng executor chỉ định; không assert một thread name cố định khi API không cam kết.
7. **Spring proxy:** gọi `@Async` qua bean được inject; không dùng `new Service()` hoặc self-invocation trong test kỳ vọng async.
8. **Concurrency:** dùng `CountDownLatch` hoặc test scheduler để tránh test giòn dựa vào `Thread.sleep` và thứ tự chạy không xác định.
9. **Timeout/cancellation:** mô phỏng stage chạy lâu và side effect; xác nhận timeout của future không tự rollback kết quả external.
10. **Saturation:** làm đầy executor có queue hữu hạn, xác nhận rejection được phản ánh ở đường hoàn tất lỗi thay vì bị nuốt.

Một ví dụ có thể kiểm tra riêng logic flatten mà không tạo thread:

~~~java
CompletableFuture<String> inner = new CompletableFuture<>();
CompletableFuture<String> flat =
    CompletableFuture.completedFuture("id")
        .thenCompose(ignored -> inner);

System.out.println(flat.isDone()); // false
inner.complete("ready");
System.out.println(flat.join());   // ready
~~~

Đây là **đoạn code ghép vào phương thức Java** (cần import `CompletableFuture`), không phải một class độc lập. Output của hai lệnh `println` lần lượt là `false` và `ready` vì inner chưa hoàn tất trước khi gọi `inner.complete`.

## 17. Checklist dùng trong code review

- Tôi biết callback trả **giá trị U** hay **CompletionStage<U>** trước khi chọn `thenApply` hoặc `thenCompose`.
- Tôi không vô tình tạo `CompletableFuture<CompletableFuture<U>>` khi muốn kết quả phẳng.
- Tôi không dùng `join()`/`get()` bên trong continuation để ép một công việc bất đồng bộ thành đồng bộ.
- Tôi biết callback không hậu tố `Async` có thể chạy inline hoặc trên thread hoàn tất stage nguồn.
- Tôi dùng `thenApplyAsync/thenComposeAsync` và executor tường minh khi có lý do kiểm soát thread pool.
- Tôi không nhầm `thenCompose` với cách chạy song song những công việc không phụ thuộc nhau.
- Tôi kiểm soát lỗi của cả source stage và stage được nối, và đặt recovery đúng ranh giới nghiệp vụ.
- Tôi có chính sách timeout, cancel, backpressure và retry, không nhầm timeout với việc dừng side effect.
- Tôi xác nhận Spring `@Async` được gọi qua proxy, transaction/context không bị giả định lan truyền.
- Tôi biết ai sở hữu **future cuối** và có nhiệm vụ quan sát trạng thái hoàn tất của toàn pipeline.

**Kết luận:** Dùng `thenApply()` khi chỉ cần biến đổi **giá trị hiện có**; dùng `thenCompose()` khi bước kế tiếp phụ thuộc vào giá trị đó và trả về **một giai đoạn bất đồng bộ**, nhờ đó ta có một future **phẳng** để theo dõi toàn bộ kết quả. Trong Spring, thiết kế đúng còn cần chọn executor, kiểm soát số thread, lỗi, timeout và ranh giới proxy/giao dịch.

## Tài liệu tham khảo chính thức

- Java SE 17: [CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — semantics của `thenApply`, `thenCompose`, async variants, completion, exceptions và cancellation.
- Java SE 17: [CompletionStage Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html) — pipeline phụ thuộc, kiểu callback và quy tắc hoàn tất lỗi.
- Spring Framework: [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — `@EnableAsync`, `@Async`, cách chọn executor và `CompletableFuture` return type.
- Spring Framework: [AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html) — `submitCompletable` và cách đưa task vào executor theo abstraction Spring.
- Spring Framework: [@Async Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html) — signature, qualifier và ràng buộc khi dùng Spring proxy.
