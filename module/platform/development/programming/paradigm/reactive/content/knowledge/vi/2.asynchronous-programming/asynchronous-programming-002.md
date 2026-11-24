# Chặn và không chặn: phân biệt với đồng bộ và bất đồng bộ

## Vì sao cần tách hai khái niệm này?

Trong lập trình Java, các từ *blocking*, *non-blocking*, *synchronous* và *asynchronous* thường xuất hiện cùng nhau. Chúng mô tả hai khía cạnh khác nhau:

- **Chặn (blocking) hay không chặn (non-blocking)** mô tả luồng gọi phải chờ kết quả theo cách nào. Lời gọi chặn giữ luồng tại điểm gọi cho đến khi thao tác hoàn tất hoặc điều kiện chờ được thỏa mãn. Lời gọi không chặn trả quyền điều khiển về cho luồng gọi mà không buộc luồng đó đứng chờ thao tác hoàn tất.
- **Đồng bộ (synchronous) hay bất đồng bộ (asynchronous)** mô tả cách thức và thời điểm kết quả được cung cấp so với lời gọi. Với cách đồng bộ, kết quả được cung cấp trong luồng thực thi của lời gọi. Với cách bất đồng bộ, thao tác được khởi phát và kết quả được thông báo hoặc xử lý sau đó, thường qua callback, future, event hay một luồng dữ liệu.

Vì vậy, không nên dùng “bất đồng bộ” như từ đồng nghĩa với “không chặn”. Một API bất đồng bộ vẫn có thể bị sử dụng theo cách chặn nếu chương trình gọi `get()` hoặc `join()` để đợi kết quả. Ngược lại, một thao tác đồng bộ có thể hoàn tất rất nhanh và không gây ra thời gian chờ đáng kể, dù nó vẫn trả kết quả trực tiếp trong lời gọi.

## Hai trục độc lập

Có thể xem hai cặp thuật ngữ như hai trục phân loại:

| Cách phân loại | Câu hỏi cần trả lời | Dấu hiệu thường gặp |
|---|---|---|
| Blocking / non-blocking | Luồng gọi có phải dừng lại để chờ không? | `Thread.sleep`, `Future.get`, thao tác I/O chặn; API trả quyền điều khiển ngay |
| Synchronous / asynchronous | Kết quả được xử lý trong lời gọi hiện tại hay được thông báo sau? | Giá trị trả về trực tiếp; callback, `CompletionStage`, event |

Bốn cách kết hợp có thể xảy ra:

| Kết hợp | Diễn giải | Ví dụ điển hình |
|---|---|---|
| Đồng bộ, chặn | Lời gọi thực hiện công việc và luồng gọi đợi cho đến khi có kết quả | Đọc file bằng API I/O chặn rồi nhận nội dung qua giá trị trả về |
| Bất đồng bộ, không chặn | Khởi chạy công việc, trả quyền điều khiển; kết quả đến qua cơ chế hoàn tất | `CompletableFuture.supplyAsync(...).thenApply(...)` |
| Bất đồng bộ, chặn tại điểm sử dụng | Công việc được khởi chạy bất đồng bộ nhưng luồng gọi lại đợi kết quả | Gọi `future.get()` hoặc `future.join()` ngay sau khi tạo future |
| Đồng bộ, không chặn | Lời gọi xử lý ngay trong luồng hiện tại, trả kết quả ngay mà không chờ một công việc bên ngoài | Tra cứu trong cấu trúc dữ liệu trong bộ nhớ và trả kết quả tức thời |

“Không chặn” không có nghĩa là không thực hiện công việc; nó nói rằng lời gọi không giữ luồng chờ một điều kiện hoàn tất. “Đồng bộ” cũng không có nghĩa là chậm; nó nói về quan hệ giữa lời gọi và kết quả.

## Blocking: luồng gọi bị giữ lại

Một thao tác chặn khiến luồng gọi không thể tiếp tục thực hiện các câu lệnh phía sau cho đến khi điều kiện chờ được thỏa mãn. Ví dụ sau dùng `Future.get()`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BlockingExample {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<String> future = executor.submit(() -> {
                Thread.sleep(1_000);
                return "đã tải xong";
            });

            System.out.println("Bắt đầu chờ kết quả");
            String result = future.get(); // Luồng main chờ tại đây.
            System.out.println(result);
        } finally {
            executor.shutdown();
        }
    }
}
```

Tác vụ chạy trên executor, nhưng `get()` khiến luồng `main` chờ cho đến khi future hoàn tất. Việc công việc chạy trên một luồng khác không tự động làm cho toàn bộ luồng gọi trở thành không chặn. Vị trí chờ trong chương trình mới là điều cần kiểm tra.

Các API chặn vẫn hữu ích khi cần luồng tuần tự đơn giản, khi thời gian chờ được kiểm soát, hoặc tại ranh giới mà việc chờ là chủ ý. Tuy nhiên, nếu nhiều yêu cầu cùng chiếm các luồng để chờ I/O, số luồng cần thiết có thể tăng mạnh, tài nguyên bị giữ trong lúc không tạo ra tiến triển và độ trễ toàn hệ thống có thể tăng.

## Non-blocking: trả quyền điều khiển để tiếp tục

Một API không chặn cho phép luồng gọi tiếp tục công việc khác trong khi thao tác được xử lý. Kết quả thường được chuyển đến qua callback, future hoặc luồng sự kiện. Với `CompletableFuture`, có thể nối các bước xử lý mà không gọi `get()` ở giữa:

```java
import java.util.concurrent.CompletableFuture;

public class NonBlockingExample {
    public static void main(String[] args) {
        CompletableFuture<String> result = CompletableFuture
            .supplyAsync(() -> loadData())
            .thenApply(data -> data.toUpperCase())
            .thenApply(value -> "Kết quả: " + value);

        result.thenAccept(System.out::println);
        System.out.println("Luồng gọi đã đăng ký xử lý tiếp theo");
    }

    private static String loadData() {
        return "reactive streams";
    }
}
```

Các bước tiếp theo được đăng ký vào chuỗi hoàn tất. Luồng gọi không cần lấy kết quả bằng cách chờ tại `get()` hay `join()`. Thứ tự in giữa dòng thông báo và kết quả phụ thuộc vào thời điểm tác vụ hoàn tất; không nên dựa vào thứ tự cố định giữa chúng.

`CompletableFuture` không làm mọi hàm bên trong tự nhiên không chặn. Nếu `loadData()` gọi một API I/O chặn, luồng thực thi tác vụ vẫn bị giữ trong lúc I/O chờ. Công việc chặn chỉ được chuyển sang luồng khác. Muốn có thiết kế không chặn ở tầng I/O, cần dùng API và driver hỗ trợ I/O không chặn, đồng thời tránh các điểm chờ đồng bộ trong chuỗi xử lý.

## Đọc đúng hành vi của Future và CompletionStage

`Future` biểu diễn một kết quả có thể có trong tương lai. Nó không cam kết rằng mọi cách truy cập kết quả đều không chặn:

| API | Hành vi cần hiểu |
|---|---|
| `future.isDone()` | Kiểm tra trạng thái; không đợi kết quả hoàn tất |
| `future.get()` | Chặn đến khi có kết quả, bị hủy hoặc gặp lỗi; overload có timeout giới hạn thời gian chờ |
| `future.cancel(...)` | Yêu cầu hủy; không đồng nghĩa tác vụ chắc chắn dừng ngay |
| `stage.thenApply(...)` | Đăng ký phép biến đổi khi stage trước hoàn tất |
| `stage.thenAccept(...)` | Đăng ký hành động tiêu thụ kết quả |
| `stage.thenCompose(...)` | Nối một stage phụ thuộc vào kết quả của stage trước, tránh tạo stage lồng nhau |
| `stage.join()` | Lấy kết quả bằng cách chờ; ngoại lệ được biểu diễn theo cơ chế của `CompletionException` |

`thenApply` và `thenAccept` không phải lời hứa rằng callback luôn chạy trên một luồng riêng. Các biến thể không có hậu tố `Async` có thể chạy trên luồng hoàn tất stage trước hoặc luồng gọi nếu stage đã hoàn tất tại thời điểm đăng ký. Các biến thể `thenApplyAsync` cho phép thực thi callback bất đồng bộ thông qua executor được chọn; nếu không truyền executor, cơ chế executor mặc định của `CompletableFuture` được sử dụng. Cần chọn executor phù hợp với loại công việc và kiểm soát tài nguyên của nó.

## Liên hệ với lập trình reactive

Trong Reactive Streams, `Publisher` phát các tín hiệu đến `Subscriber` theo hợp đồng đăng ký và yêu cầu dữ liệu. Việc một pipeline được mô tả theo kiểu khai báo hoặc trả về `Mono`/`Flux` không tự đảm bảo rằng mọi thao tác bên trong đều không chặn. Cần xem xét nguồn dữ liệu, toán tử, scheduler và cách tiêu thụ kết quả.

Ví dụ với Reactor:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> pipeline = Mono.fromCallable(() -> blockingRead())
    .subscribeOn(Schedulers.boundedElastic())
    .map(String::toUpperCase);

pipeline.subscribe(
    value -> System.out.println("Nhận: " + value),
    error -> System.err.println("Lỗi: " + error.getMessage())
);
```

`fromCallable` trì hoãn việc gọi hàm cho đến khi có subscription. `subscribeOn` chuyển việc thực thi nguồn sang scheduler được chỉ định. `boundedElastic` phù hợp để cô lập một số tác vụ chặn có thời gian chờ, nhưng nó không biến `blockingRead()` thành I/O không chặn; luồng thực thi tác vụ vẫn chờ bên trong hàm đó. Cách tổ chức này giúp tránh chiếm các luồng dành cho xử lý sự kiện hoặc công việc có độ trễ thấp.

Trong ứng dụng Reactor, không nên gọi các phương thức chặn như `block()`, `blockFirst()` hoặc `blockLast()` trên luồng xử lý không được phép chặn, đặc biệt là các luồng event loop. Những phương thức này có thể hữu ích ở ranh giới tích hợp hoặc trong một số bài kiểm thử, nhưng đặt chúng giữa pipeline sẽ làm mất lợi ích của xử lý không chặn và có thể gây nghẽn hoặc deadlock tùy cấu trúc hệ thống.

### Backpressure không đồng nghĩa với non-blocking

Backpressure là cơ chế điều tiết lượng dữ liệu mà `Subscriber` sẵn sàng nhận thông qua yêu cầu (`request(n)`). Nó giúp phối hợp tốc độ phát và tiêu thụ dữ liệu, hạn chế việc bên nhận bị áp đảo. Non-blocking mô tả việc luồng gọi không phải đứng chờ. Hai khái niệm có thể hỗ trợ một thiết kế reactive hiệu quả, nhưng chúng giải quyết hai vấn đề khác nhau: backpressure điều tiết nhu cầu dữ liệu; non-blocking tránh giữ luồng trong thời gian chờ.

## Cách đánh giá một API trong thực tế

Khi xem một API hoặc một đoạn pipeline, hãy lần lượt xác định:

1. **Điểm gọi trả quyền điều khiển lúc nào?** Nếu luồng gọi phải đợi I/O, khóa, semaphore hoặc kết quả future, điểm đó có hành vi chặn.
2. **Kết quả đến bằng cách nào?** Giá trị trả về trực tiếp thường thể hiện cách đồng bộ; callback, future hoặc tín hiệu thể hiện cách bất đồng bộ.
3. **Công việc thực sự chạy ở đâu?** Kiểm tra executor, scheduler, event loop và cách chúng được cấu hình. Chuyển công việc sang luồng khác không loại bỏ bản chất chặn của hàm được chuyển.
4. **Có điểm chặn ẩn trong pipeline không?** Tìm `get()`, `join()`, `block()`, thao tác I/O chặn, chờ khóa và các API đồng bộ được gọi bên trong callback.
5. **Tải đồng thời ảnh hưởng ra sao?** Đánh giá số luồng bị giữ, giới hạn hàng đợi, timeout, hủy tác vụ, backpressure và cách xử lý lỗi.

Ví dụ, một HTTP client trả `CompletableFuture<Response>` có giao diện bất đồng bộ. Nếu tầng gọi ngay lập tức dùng `join()`, luồng tầng gọi vẫn chặn. Nếu callback của future thực hiện truy vấn JDBC đồng bộ, callback đó cũng chặn luồng đang chạy nó. Muốn hiểu hành vi toàn tuyến, cần lần theo các bước từ nơi khởi phát cho đến nơi tiêu thụ kết quả.

## Ví dụ so sánh cách sử dụng

Giả sử cần tải hồ sơ người dùng rồi chuyển tên thành chữ hoa. Cách lấy kết quả bằng chờ đồng bộ:

```java
CompletableFuture<String> future = CompletableFuture.supplyAsync(
    () -> fetchUserName(userId)
);

String upperName = future.join(); // Luồng hiện tại chờ tại đây.
render(upperName);
```

Cách nối bước xử lý bất đồng bộ:

```java
CompletableFuture<Void> completion = CompletableFuture
    .supplyAsync(() -> fetchUserName(userId))
    .thenApply(String::toUpperCase)
    .thenAccept(this::render);

completion.exceptionally(error -> {
    logFailure(error);
    return null;
});
```

Ở đoạn thứ hai, luồng hiện tại đăng ký chuỗi xử lý và có thể tiếp tục công việc khác. `completion` vẫn biểu diễn trạng thái hoàn tất của chuỗi; nếu một nơi khác gọi `completion.join()`, nơi đó lại tạo ra điểm chặn. Xử lý lỗi cũng được nối vào chuỗi để lỗi không bị bỏ qua.

## Những ngộ nhận thường gặp

- **“Chạy trên thread pool là non-blocking.”** Thread pool chỉ quyết định nơi thực thi. Một tác vụ gọi `Thread.sleep()` hoặc I/O chặn vẫn chiếm luồng pool trong thời gian chờ.
- **“Có kiểu trả về Future là không chặn.”** Future cho phép biểu diễn kết quả sẽ có; `get()` và `join()` vẫn chặn.
- **“Non-blocking nghĩa là không phải chờ ở bất kỳ đâu.”** Một hệ thống vẫn có thể có hàng đợi, độ trễ và thời điểm hoàn tất. Điểm phân biệt là luồng gọi không bị giữ để chờ tại thao tác đó.
- **“Asynchronous luôn nhanh hơn synchronous.”** Bất đồng bộ có chi phí điều phối, chuyển ngữ cảnh và quản lý trạng thái. Lựa chọn phù hợp phụ thuộc vào tải, loại công việc và yêu cầu độ trễ.
- **“Reactive đồng nghĩa với không chặn.”** Pipeline reactive có thể chứa lời gọi chặn. Cần chọn nguồn, driver và scheduler thích hợp, đồng thời tránh chặn luồng xử lý sự kiện.

Khi thiết kế hệ thống Java, hãy mô tả rõ cả hai khía cạnh: thao tác có trả quyền điều khiển ngay hay không, và kết quả được cung cấp theo cách đồng bộ hay bất đồng bộ. Cách phân biệt này giúp chọn API, executor và scheduler đúng với đặc điểm công việc, đồng thời phát hiện sớm các điểm chặn làm giảm khả năng phục vụ đồng thời.
