# thenCombine() kết hợp hai kết quả độc lập

> **Module:** Spring Framework – concurrency  
> **Nhóm kiến thức:** Kết hợp `CompletableFuture`  
> **Trọng tâm:** `thenCombine()` dùng để **kết hợp kết quả của hai tác vụ không phụ thuộc dữ liệu lẫn nhau**, sau khi cả hai `CompletionStage` hoàn thành bình thường. Nó tạo **một stage mới**, không tự khởi chạy hai tác vụ, không đòi hỏi phải đợi tuần tự bằng `get()`/`join()` và không bảo đảm hai việc luôn chạy trên hai thread khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích đúng điều kiện chạy `thenCombine`, kiểu tham số hàm `BiFunction` và kiểu trả về `CompletableFuture<V>`.
2. Tạo hai `CompletableFuture` độc lập bằng `supplyAsync` hoặc nhận chúng từ hai API bất đồng bộ rồi kết hợp thành kết quả có kiểu rõ ràng.
3. Phân biệt “độc lập” với “song song”, và phân biệt `thenCombine` với `thenCombineAsync`.
4. Dự đoán cách hoạt động nếu một/both upstream thất bại, bị hủy, không bao giờ hoàn thành hoặc nếu chính hàm kết hợp ném exception.
5. Biết sử dụng `exceptionally`, `handle`, `whenComplete`, timeout và cancellation có chủ đích.
6. Dùng `thenCombine` trong một service Spring phối hợp hai nguồn dữ liệu, không tự chặn request thread và không đánh mất khả năng quan sát lỗi.
7. Biết khi nào nên dùng `thenCompose`, `thenApply`, `allOf` hoặc `applyToEither` thay vì `thenCombine`.
8. Chạy ví dụ Java 17 và ví dụ Spring Context có output xác định, cùng các bài kiểm thử không phụ thuộc `Thread.sleep()`.

## 2. Bài toán: hai kết quả độc lập, một phản hồi tổng hợp

Giả sử endpoint cần trả báo giá gồm:

- **Thông tin sản phẩm**: dịch vụ A trả tên sản phẩm theo mã.
- **Giá hiện tại**: dịch vụ B trả giá của cùng mã.
- **Báo giá cuối**: ghép tên và giá thành một `Quote`.

Hai lời gọi A và B chỉ cần cùng mã sản phẩm, không cần lấy kết quả A để bắt đầu B. Vì vậy, chúng có thể được **khởi động độc lập** và kết quả được kết hợp sau khi cả hai hoàn thành.

Cách dễ viết nhưng có thể tạo chờ tuần tự:

~~~java
String product = productClient.fetchName(id);  // Có thể chặn.
int price = pricingClient.fetchPrice(id);      // Chỉ gọi sau bước trước.
return new Quote(product, price);
~~~

Đây là **pseudocode Java trong service đồng bộ**, giả định hai client đã tồn tại. Nếu mỗi lời gọi mất khoảng 300 ms và 500 ms, trong trường hợp không chồng lấp, tổng thời gian thường khoảng 800 ms cộng overhead.

Nếu hai API đã hỗ trợ bất đồng bộ:

~~~java
CompletableFuture<String> nameFuture = productClient.fetchNameAsync(id);
CompletableFuture<Integer> priceFuture = pricingClient.fetchPriceAsync(id);

CompletableFuture<Quote> quoteFuture =
        nameFuture.thenCombine(priceFuture, Quote::new);
~~~

Đây là **snippet cho ứng dụng có hai async client và record/class Quote**, chưa phải chương trình độc lập. `quoteFuture` chỉ có giá trị sau khi cả hai nguồn hoàn thành bình thường.

Sơ đồ:

~~~text
                              +--> fetchNameAsync(id) ----> "Book" ---+
Request / orchestration ------|                                      | 
                              +--> fetchPriceAsync(id) ----> 50 -----+--> thenCombine
                                                                            |
                                                                            v
                                                                  Quote("Book", 50)
                                                                            |
                                                                            v
                                                                  CompletableFuture<Quote>
~~~

Điểm quan trọng là **không chờ lấy kết quả A rồi mới nộp B**. Tuy nhiên, cấu trúc này chỉ tạo điều kiện để chồng lấp thời gian; nếu backend, connection pool hoặc executor chỉ cho chạy một task tại thời điểm, hai công việc vẫn có thể thực thi nối tiếp.

## 3. Chữ ký API và ý nghĩa từng thành phần

Với `CompletableFuture<T>`:

~~~java
<U, V> CompletableFuture<V> thenCombine(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn);
~~~

Ý nghĩa:

- **`T`:** kiểu kết quả của stage bên trái (`this`).
- **`U`:** kiểu kết quả của stage `other`.
- **`V`:** kiểu kết quả do hàm kết hợp `fn` tạo ra.
- **`other`:** một `CompletionStage` độc lập cần có kết quả.
- **`fn`:** hàm nhận **hai giá trị**, trả **một giá trị**; ví dụ `(name, price) -> new Quote(name, price)`.
- **Giá trị trả về:** một `CompletableFuture<V>` **mới** đại diện cho phép kết hợp.

Javadoc Java nói stage mới thực hiện hàm khi **cả hai stage hoàn thành bình thường** (*both complete normally*). “Hoàn thành bình thường” là completed không có exception/cancellation, không có nghĩa kết quả phải khác `null`.

### Ví dụ nhỏ nhất

~~~java
CompletableFuture<Integer> left =
        CompletableFuture.completedFuture(20);
CompletableFuture<Integer> right =
        CompletableFuture.completedFuture(22);

CompletableFuture<Integer> total =
        left.thenCombine(right, Integer::sum);

System.out.println(total.join());
~~~

Đây là **snippet Java**, đặt trong một phương thức có import `java.util.concurrent.CompletableFuture`. Output:

~~~text
42
~~~

Vì hai input đã hoàn thành, phép cộng rất có thể được thực hiện **ngay khi đăng ký continuation**; đó là hành vi hợp lệ. Đừng suy “CompletableFuture thì mọi callback luôn chạy ở worker”.

### thenCombine không làm những việc nào?

- Không tự gọi `supplyAsync` hoặc tự tạo task cho `left`/`right`.
- Không đảm bảo chạy hàm kết hợp trên một thread riêng.
- Không quyết định executor nào xử lý hai nguồn đã tạo trước đó.
- Không chặn bên gọi để đợi cả hai input hoàn tất giống như hai lệnh `get()`; tuy nhiên, **hàm kết hợp có thể chạy inline ngay khi đăng ký** nếu cả hai đã xong, nên nếu `fn` làm việc nặng/blocking, chính lời gọi đăng ký có thể mất thời gian.
- Không làm failure của hai upstream “biến mất”; stage mới hoàn thành exceptional khi không thể có kết quả kết hợp bình thường.
- Không bảo đảm cancel stage mới sẽ cancel các nguồn đầu vào.

## 4. Quy tắc hoàn thành và thứ tự thực thi

### 4.1. Khi cả hai thành công

~~~text
left:  ---- running ------------> completed("A")
right: ---- running -----> completed(10)

thenCombine(left, right, (a, b) -> a + b)
                                |
                         đủ cả hai giá trị
                                |
                                v
                           completed("A10")
~~~

Hàm `BiFunction` nhận kết quả **theo vị trí tham số**: tham số thứ nhất lấy từ stage gọi `thenCombine`, tham số thứ hai lấy từ `other`. Thứ tự **ai hoàn thành trước** không đảo thứ tự tham số:

~~~java
CompletableFuture<String> name = ...;
CompletableFuture<Integer> price = ...;

CompletableFuture<String> label = name.thenCombine(
        price, (n, p) -> n + " : " + p);
~~~

**Đoạn minh họa:** các future phải được tạo từ trước. Cho dù `price` hoàn thành trước, `n` vẫn là tên và `p` vẫn là giá.

### 4.2. Khi mới có một kết quả

Khi `left` đã completed nhưng `right` chưa completed, `thenCombine` **chưa có hai giá trị** nên `fn` chưa thể chạy. Future kết quả vẫn pending, trừ khi có tình huống exception/cancellation được implementation xử lý theo quy tắc completion.

Một cách kiểm thử chuẩn là tạo hai `new CompletableFuture<>()`, complete từng nguồn một và quan sát `isDone()` của stage mới.

### 4.3. Khi cả hai đã hoàn thành trước khi đăng ký

Nếu cả hai `CompletableFuture.completedFuture(...)` đã hoàn thành, bản **non-Async `thenCombine`** có thể chạy `fn` ngay trong thread gọi `thenCombine`. Hợp đồng không dành riêng một worker thread cho continuation này.

Vì vậy, không nên đặt một phép gọi HTTP blocking hoặc tính toán CPU rất nặng bên trong `thenCombine` non-Async nếu call site cần giữ latency nhỏ. Nếu cần tách tài nguyên cho bước tổng hợp, cân nhắc `thenCombineAsync(..., executor)` có executor riêng và được quản lý.

### 4.4. Nếu hai input “độc lập” nhưng cùng executor một thread

~~~java
ExecutorService single = Executors.newSingleThreadExecutor();

CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 20, single);
CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 22, single);

CompletableFuture<Integer> result =
        a.thenCombine(b, Integer::sum);
~~~

Đây là **snippet**; cần shutdown `single` trong ứng dụng. Cả hai tác vụ dùng cùng executor một thread nên có thể thực thi lần lượt. Kết quả vẫn là 42, nhưng không nên mô tả chúng như hai CPU job thật sự chạy song song.

**Độc lập** = dữ liệu của tác vụ A không cần kết quả B để bắt đầu, và ngược lại. **Song song** = hệ thống thật sự chạy công việc đồng thời trên nhiều tài nguyên. `thenCombine` yêu cầu tính độc lập logic, không tự cung cấp song song vật lý.

## 5. thenCombine và thenCombineAsync khác gì?

Có ba overload quan trọng:

~~~java
left.thenCombine(right, combiner);

left.thenCombineAsync(right, combiner);

left.thenCombineAsync(right, combiner, customExecutor);
~~~

| Cách dùng | Điều kiện gọi `combiner` | Nơi chạy combiner |
| --- | --- | --- |
| `thenCombine` | Khi hai nguồn completed normally | Có thể inline trên thread hoàn thành một source hoặc thread đăng ký nếu đã xong; không bảo đảm thread riêng |
| `thenCombineAsync` không executor | Cùng điều kiện | Dùng default asynchronous execution facility của stage; với `CompletableFuture` thông dụng là `ForkJoinPool.commonPool()`, có ngoại lệ được Javadoc mô tả |
| `thenCombineAsync(..., executor)` | Cùng điều kiện | Dispatch theo executor được truyền, ví dụ một `ThreadPoolTaskExecutor` do Spring quản lý |

**Async ở đây là đặc tính của bước kết hợp**, không tự chuyển đổi cách thực thi hai upstream. Ví dụ:

~~~java
CompletableFuture<Price> price = pricingService.loadPriceAsync(id);
CompletableFuture<Stock> stock = stockService.loadStockAsync(id);

return price.thenCombineAsync(
        stock,
        (p, s) -> new Offer(p, s),
        aggregationExecutor);
~~~

Đây là **snippet** yêu cầu các class/service `Price`, `Stock`, `Offer` và `aggregationExecutor` đã tồn tại.

### Khi nên chọn loại nào?

- Nếu `combiner` chỉ tạo DTO, cộng vài số hoặc nối hai chuỗi, `thenCombine` thường đủ và tránh thêm một lần schedule.
- Nếu `combiner` thực hiện mapping phức tạp/CPU đáng kể, dùng `thenCombineAsync(..., executor)` với pool có giới hạn là lựa chọn dễ kiểm soát.
- Nếu combiner gọi I/O blocking, tốt hơn nên tách thành **một stage bất đồng bộ rõ ràng** (thường là `thenCompose` hoặc `thenCombine(...).thenCompose(...)`) thay vì vô tình block thread hoàn tất stage.
- Không mặc nhiên dùng common pool cho blocking I/O nặng; thread starvation có thể ảnh hưởng những công việc bất đồng bộ khác trên JVM.
- Một `Executor` được cung cấp tùy biến vẫn có thể chạy inline (ví dụ direct executor), nên không thể bảo đảm “Async overload chắc chắn khác thread” bất chấp executor cụ thể.

### Rejection của executor dùng cho continuation

Nếu `thenCombineAsync` cần schedule hàm kết hợp nhưng executor đã shutdown/bão hòa và từ chối, stage kết quả có thể hoàn thành bất thường do việc điều phối thất bại. Chính sách ở đây nên được kiểm thử theo executor thực tế. **Không chỉ giám sát lỗi của hai nguồn**; hãy giám sát cả lỗi của bước kết hợp và việc schedule nó.

## 6. Ví dụ Java 17 chạy được với hai nguồn độc lập

Chương trình dưới đây tạo **hai worker** để tính thông tin riêng, dùng `CountDownLatch` giữ chúng ở ranh giới trước khi hoàn thành, sau đó:

1. Chứng minh hai tác vụ đã bắt đầu độc lập.
2. Chứng minh `thenCombine` chưa kết thúc khi chưa đủ cả hai kết quả.
3. Nhận kết quả ghép bằng `thenCombine`.
4. Chạy một phép ghép khác bằng `thenCombineAsync(..., aggregationExecutor)` và quan sát đúng thread được cấu hình.
5. Thử một nguồn thất bại rồi khôi phục với `exceptionally`.

### 6.1. Tệp ThenCombineDemo.java

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThenCombineDemo {

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("latch timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("interrupted", ex);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService fetchPool = Executors.newFixedThreadPool(2);
        ExecutorService aggregatePool =
                Executors.newSingleThreadExecutor(
                        r -> new Thread(r, "aggregate-worker"));

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            CompletableFuture<String> name =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        await(release);
                        return "Book";
                    }, fetchPool);

            CompletableFuture<Integer> price =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        await(release);
                        return 50;
                    }, fetchPool);

            CompletableFuture<String> quote =
                    name.thenCombine(price,
                            (n, p) -> n + "-" + p);

            CompletableFuture<String> asyncQuote =
                    name.thenCombineAsync(
                            price,
                            (n, p) -> n + "-" + p
                                    + "@" + Thread.currentThread().getName(),
                            aggregatePool);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("tasks did not start");
            }

            System.out.println("both started = true");
            System.out.println("quote done before release = "
                    + quote.isDone());

            release.countDown();

            System.out.println("quote = "
                    + quote.get(5, TimeUnit.SECONDS));
            System.out.println("async quote = "
                    + asyncQuote.get(5, TimeUnit.SECONDS));

            CompletableFuture<Integer> broken =
                    CompletableFuture.failedFuture(
                            new IllegalArgumentException("price missing"));
            CompletableFuture<Integer> fee =
                    CompletableFuture.completedFuture(5);

            CompletableFuture<Integer> failed =
                    broken.thenCombine(fee, Integer::sum);

            try {
                failed.join();
            } catch (CompletionException ex) {
                System.out.println("failure cause = "
                        + ex.getCause().getMessage());
            }

            CompletableFuture<Integer> fallback =
                    broken.exceptionally(ex -> 10)
                          .thenCombine(fee, Integer::sum);

            System.out.println("fallback total = " + fallback.join());
        } finally {
            // Dọn cả đường lỗi để không giữ worker mắc kẹt.
            release.countDown();
            fetchPool.shutdown();
            aggregatePool.shutdown();

            if (!fetchPool.awaitTermination(5, TimeUnit.SECONDS)) {
                fetchPool.shutdownNow();
            }
            if (!aggregatePool.awaitTermination(5, TimeUnit.SECONDS)) {
                aggregatePool.shutdownNow();
            }
        }
    }
}
~~~

### 6.2. Biên dịch, chạy và kết quả

~~~bash
javac ThenCombineDemo.java
java ThenCombineDemo
~~~

**Stdout của chương trình khi chạy thành công:**

~~~text
both started = true
quote done before release = false
quote = Book-50
async quote = Book-50@aggregate-worker
failure cause = price missing
fallback total = 15
~~~

### 6.3. Vì sao output xác định?

- `fetchPool` có hai worker để cả hai `supplyAsync` có thể đi tới `started.countDown()` trong ví dụ tải nhẹ.
- Main chỉ vượt `started.await(...)` khi cả hai nguồn báo đã bắt đầu; khi ấy `release` vẫn chưa mở, nên cả hai chưa thể trả `"Book"` và `50`. Do đó `quote.isDone()` ở dòng in bắt buộc là `false`.
- Sau `release.countDown()`, hai tác vụ kết thúc; `quote.get(timeout)` chờ kết quả gộp và in `Book-50`.
- `thenCombineAsync(..., aggregatePool)` chạy bước ghép trên thread do factory đặt tên `aggregate-worker`, không dựa vào tên thread ngẫu nhiên của common pool.
- `failedFuture` là một nguồn đã exceptional, `thenCombine` không gọi `Integer::sum` để tạo kết quả từ nguồn lỗi. `join()` ném `CompletionException`, qua `getCause()` thấy thông điệp `price missing`.
- `exceptionally(ex -> 10)` khôi phục **nguồn broken** thành 10, nên `10 + 5 = 15`.
- Hai pool được shutdown trong `finally` và được chờ có timeout, tránh giữ tiến trình chạy mãi chỉ vì worker chưa kết thúc.

**Giới hạn của demo:** nó điều phối bằng latch để kiểm chứng thứ tự, không mô phỏng thời gian phản hồi mạng. Khi chạy sản phẩm thật, thời điểm hoàn thành phụ thuộc scheduler, I/O, giới hạn connection và lượng tải. Không nên dùng `Thread.sleep` như một cơ chế đồng bộ hóa test.

## 7. Kết quả có kiểu: từ hai nguồn sang DTO/record

Một lợi ích lớn của `thenCombine` là xây **một đối tượng có kiểu** từ hai nguồn không phụ thuộc lẫn nhau:

~~~java
record Product(String id, String name) {}
record Price(long cents, String currency) {}
record ProductView(Product product, Price price) {}

CompletableFuture<Product> productFuture = findProductAsync(id);
CompletableFuture<Price> priceFuture = findPriceAsync(id);

CompletableFuture<ProductView> viewFuture =
        productFuture.thenCombine(priceFuture, ProductView::new);
~~~

Đây là **snippet Java 17**, gồm ba record hợp lệ khi đặt trong phạm vi class/package thích hợp; hai hàm `findProductAsync` và `findPriceAsync` là API giả định, không phải chương trình độc lập.

Ở đây:

- `T = Product`, `U = Price`, `V = ProductView`.
- `thenCombine` nhận `Product` và `Price` thành hai tham số.
- `ProductView::new` là constructor reference có hai tham số tương ứng.
- Future kết quả mang đúng kiểu `CompletableFuture<ProductView>`, không cần ép kiểu hay lưu tạm vào hai biến mutable dùng chung.

Nếu cả hai stage đều hoàn thành bình thường, `ProductView` được tạo đúng một lần cho continuation đó. Tránh thay đổi một shared mutable `ProductView` từ hai callback riêng lẻ vì dễ tạo race condition và trạng thái chưa đầy đủ.

### Nếu nguồn trả null?

`CompletableFuture.completedFuture(null)` là **normal completion**, khác với exceptional completion. Hàm `BiFunction` vẫn có thể được gọi với giá trị `null`. Nếu constructor không cho phép null hoặc business coi null là lỗi, kiểm tra rõ:

~~~java
CompletableFuture<ProductView> viewFuture =
        productFuture.thenCombine(priceFuture, (p, price) -> {
            if (p == null || price == null) {
                throw new IllegalStateException("missing product data");
            }
            return new ProductView(p, price);
        });
~~~

Đây là **snippet tích hợp**. Exception từ `BiFunction` làm **future kết hợp** hoàn thành exceptional; nó không mặc nhiên thay đổi trạng thái của `productFuture` và `priceFuture`.

## 8. Ngoại lệ: khi một hoặc hai upstream thất bại

`thenCombine` chỉ chạy `fn` khi **cả hai stage hoàn thành bình thường**. Nếu một nguồn exceptional, stage kết hợp sẽ không tạo kết quả bình thường từ hai giá trị. Cần hiểu từng đường:

| Tình huống | `fn` có được gọi? | Stage kết hợp |
| --- | --- | --- |
| Cả A, B thành công | Có | Thành công với `V`, trừ khi `fn` ném lỗi |
| A thành công, B thất bại | Không | Hoàn thành exceptional |
| A thất bại, B thành công | Không | Hoàn thành exceptional |
| Cả A, B thất bại | Không | Hoàn thành exceptional; không nên dựa vào thứ tự/cause được chọn khi có nhiều lỗi |
| A, B thành công nhưng `fn` ném exception | Có, rồi ném | Hoàn thành exceptional do chính bước kết hợp |
| Một stage không bao giờ hoàn thành | Không đủ hai kết quả | Có thể tiếp tục pending; thiết kế timeout cho toàn operation |

**Không coi thenCombine là fail-fast có cam kết.** Nếu một source đã lỗi nhưng source còn lại chưa hoàn thành, không nên dựa vào việc stage kết hợp chắc chắn phản hồi lỗi ngay lập tức. Quy tắc/scheduling thực tế phụ thuộc implementation. Hãy áp deadline ở ranh giới API/service thay vì chờ không giới hạn.

### 8.1. Lấy exception bằng get hoặc join

~~~java
CompletableFuture<Integer> broken =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("no price"));
CompletableFuture<Integer> healthy =
        CompletableFuture.completedFuture(5);

CompletableFuture<Integer> total =
        broken.thenCombine(healthy, Integer::sum);

try {
    total.join();
} catch (CompletionException ex) {
    System.out.println(ex.getCause().getMessage());
}
~~~

Đây là **snippet** với import `CompletableFuture` và `CompletionException`. Output:

~~~text
no price
~~~

- `join()` thường ném `CompletionException` (unchecked) cho lỗi bình thường của stage; `get()` thường ném `ExecutionException` (checked), và cả hai cần unwrap để biết nguyên nhân.
- Nếu future bị cancel trực tiếp, `join/get` có thể ném `CancellationException`, nên không ép mọi failure vào một exception class duy nhất.
- Nếu cả hai nguồn cùng thất bại, **đừng dựa vào một thứ tự hoàn thành để chọn cause**. Nếu cần thu thập cả hai lỗi, phải thiết kế wrapper/result hoặc quan sát riêng từng input.

### 8.2. Exception trong BiFunction

~~~java
CompletableFuture<Integer> a =
        CompletableFuture.completedFuture(10);
CompletableFuture<Integer> b =
        CompletableFuture.completedFuture(0);

CompletableFuture<Integer> invalid =
        a.thenCombine(b, (x, y) -> x / y);
~~~

Đây là **snippet**. Hai upstream vẫn hoàn thành bình thường, nhưng continuation chia cho 0 tạo `ArithmeticException` khiến `invalid` exceptional. Đừng chỉ giám sát lỗi khi fetch A/B; phép ghép/mapping/validation cũng có thể thất bại.

## 9. Chọn chiến lược khôi phục lỗi (fallback)

Có hai điểm đặt fallback, và chúng có ngữ nghĩa khác nhau.

### 9.1. Khôi phục từng nguồn trước khi ghép

Nếu giá thiếu thì dùng giá mặc định:

~~~java
CompletableFuture<Integer> safePrice =
        priceFuture.exceptionally(error -> 0);

CompletableFuture<Quote> quote =
        productFuture.thenCombine(safePrice, Quote::new);
~~~

Đây là **snippet**, cần `priceFuture`, `productFuture`, class `Quote`. Chỉ nguồn giá được recover; nếu sản phẩm thất bại thì stage cuối vẫn thất bại. Phù hợp khi nghiệp vụ cho phép degraded response cho **một trường dữ liệu**.

### 9.2. Khôi phục cả kết quả sau khi ghép

~~~java
CompletableFuture<Quote> quote =
        productFuture.thenCombine(priceFuture, Quote::new)
                     .exceptionally(error -> Quote.unavailable());
~~~

Đây là **snippet**, `Quote.unavailable()` là factory method giả định. Nếu **bất kỳ upstream hoặc combiner** thất bại, toàn bộ quote sẽ chuyển sang giá trị dự phòng. Bạn mất khả năng phân biệt giá thiếu với lỗi mapping nếu không log/metric/unwrap trước.

### 9.3. handle và whenComplete khác exceptionally

| API | Khi nào chạy? | Có đổi kết quả? |
| --- | --- | --- |
| `exceptionally(fn)` | Khi stage trước exceptional | Có thể thay lỗi thành fallback `T` |
| `handle((value, error) -> result)` | Khi stage trước thành công hoặc lỗi | Có thể biến đổi cả success lẫn failure sang một `U` mới |
| `whenComplete((value, error) -> ...)` | Khi stage hoàn tất theo cả hai trạng thái | Thường dùng quan sát/log/metrics; **không tự recover** failure chỉ bằng việc ghi log |
| `thenApply(fn)` | Khi stage trước thành công | Biến đổi một kết quả |
| `thenCombine(other, fn)` | Khi hai stage đều thành công | Ghép hai kết quả |

Ví dụ quan sát lỗi:

~~~java
CompletableFuture<Quote> observed =
        productFuture.thenCombine(priceFuture, Quote::new)
                     .whenComplete((value, error) -> {
                         if (error != null) {
                             logger.error("quote aggregation failed", error);
                         }
                     });
~~~

**Snippet tích hợp Spring/logging**, cần `logger`. Nếu `whenComplete` chỉ log, future vẫn có thể hoàn thành exceptional. Nếu callback tự ném lỗi, downstream có thể nhận lỗi từ callback (phụ thuộc trạng thái ban đầu). Đừng lạm dụng logging callback để nuốt failure rồi trả báo giá sai.

### Chọn chính sách theo nghiệp vụ

- Dữ liệu bắt buộc: giữ exceptional completion, trả lỗi phù hợp cho tầng trên.
- Dữ liệu tùy chọn: fallback ở **đúng source** và gắn cờ degraded result nếu API yêu cầu.
- Muốn audit cả hai source: lưu từng kết quả vào kiểu `Result<T>` chứa cả error/value hoặc gắn `handle` riêng trước khi kết hợp.
- Không nên cứ `exceptionally(e -> null)` rồi tiếp tục tạo DTO mà không kiểm tra, vì điều đó che lỗi thành dữ liệu trống khó phát hiện.

## 10. Cancellation, timeout và deadline

### 10.1. Hủy stage mới không đồng nghĩa hủy hai nguồn

~~~java
CompletableFuture<Quote> quote =
        productFuture.thenCombine(priceFuture, Quote::new);

quote.cancel(true);
~~~

Đây là **snippet**. Hủy `quote` không bảo đảm `productFuture` hay `priceFuture` bị cancel tự động. `CompletableFuture.cancel` bản thân nó chủ yếu điều khiển **trạng thái completion**, không phải một cơ chế interrupt đáng tin cậy cho mọi task nền; tham số `mayInterruptIfRunning` không có tác dụng điều khiển interrupt theo cách của `FutureTask`.

Ngược lại, khi một nguồn bị cancel, dependent có thể hoàn thành exceptional, nhưng điều đó không thay thế một chính sách cleanup cho những nguồn còn lại.

### 10.2. Đặt timeout ở ranh giới operation

~~~java
CompletableFuture<Quote> result =
        productFuture.thenCombine(priceFuture, Quote::new)
                     .orTimeout(2, TimeUnit.SECONDS);
~~~

**Snippet**, cần import `TimeUnit`. `orTimeout` (Java 9+) khiến chính `CompletableFuture` nhận timeout completion nếu chưa xong trong thời gian này; nó **không tự dừng** thao tác HTTP/database đang chạy trong hai nguồn. Khi dùng trên một future có nhiều consumer, lưu ý các method như `orTimeout` tác động tới chính đối tượng future được gọi, không nhất thiết tạo bản sao độc lập.

Với `get(2, TimeUnit.SECONDS)`, timeout là **hạn chờ của caller**; việc future có bị complete exceptionally hay không là chuyện khác. Cần hiểu khác biệt giữa timeout thao tác, timeout chờ kết quả và timeout của HTTP client nguồn.

### 10.3. Khi request đã hết hạn

Nếu API không còn cần kết quả:

1. Ghi nhận deadline và cancellation policy ở orchestration layer.
2. Hủy các tác vụ nguồn **nếu** contract của async client hỗ trợ, tránh công việc vô ích.
3. Release permit, connection hoặc subscription theo đúng lifecycle.
4. Phân biệt lỗi timeout với lỗi dữ liệu/validation trong metric và response.
5. Không giả định `future.cancel(true)` chắc chắn interrupt được thread HTTP client đang làm I/O.

Không để `join()` hoặc `get()` không deadline trên request thread khi yêu cầu latency là hữu hạn.

## 11. thenCombine so với thenCompose, thenApply, allOf, applyToEither

| API | Mô hình | Khi nào dùng |
| --- | --- | --- |
| `thenApply(fn)` | `A -> f(A) -> B` | Một kết quả đã có, biến đổi đồng bộ |
| `thenCompose(fn)` | `A -> asyncOperation(A) -> B` | Công việc thứ hai **phụ thuộc kết quả** thứ nhất, cần flatten future |
| `thenCombine(other, fn)` | `A` và `B` độc lập, sau đó `f(A, B) -> C` | Cần **cả hai kết quả** để tổng hợp |
| `thenAcceptBoth(other, action)` | Hai kết quả -> `BiConsumer` | Cần side effect, không trả giá trị tổng hợp (`Void`) |
| `runAfterBoth(other, action)` | Hai stage xong -> `Runnable` | Chỉ cần đợi cả hai, không đọc kết quả |
| `allOf(a,b,c,...)` | Barrier cho nhiều future | Chờ **nhiều nguồn**, trả `CompletableFuture<Void>`, tự lấy giá trị có kiểu sau đó |
| `applyToEither(other, fn)` | Chọn nguồn hoàn thành bình thường trước theo semantics API | Muốn kết quả từ **một trong hai**, không cần cả hai |

### 11.1. thenCompose: phụ thuộc tuần tự về dữ liệu

~~~java
CompletableFuture<Customer> customer = loadCustomerAsync(customerId);

CompletableFuture<Orders> orders =
        customer.thenCompose(c -> loadOrdersAsync(c.id()));
~~~

Đây là **snippet** dùng type/service giả định. `loadOrdersAsync` không thể bắt đầu khi chưa có `c.id()`. Dùng `thenCombine` cho dạng phụ thuộc này là sai về dependency; `thenCompose` loại bỏ dạng lồng `CompletableFuture<CompletableFuture<Orders>>`.

### 11.2. thenCombine: hai nguồn độc lập

~~~java
CompletableFuture<Customer> customer = loadCustomerAsync(customerId);
CompletableFuture<Recommendations> recommendations =
        loadRecommendationsAsync(customerId);

CompletableFuture<HomePage> page =
        customer.thenCombine(recommendations, HomePage::new);
~~~

**Snippet**: cùng có `customerId` nhưng recommendations không cần object `Customer` mới bắt đầu. Hai call có thể được thực hiện chồng lấp.

### 11.3. allOf: nhiều hơn hai nguồn

~~~java
CompletableFuture<Product> product = findProductAsync(id);
CompletableFuture<Price> price = findPriceAsync(id);
CompletableFuture<Stock> stock = findStockAsync(id);

CompletableFuture<ProductPage> page =
        CompletableFuture.allOf(product, price, stock)
                .thenApply(ignored -> new ProductPage(
                        product.join(),
                        price.join(),
                        stock.join()));
~~~

Đây là **snippet**, yêu cầu các type và hàm nghiệp vụ tương ứng. Sau khi `allOf` hoàn thành bình thường, ba `join()` dùng để lấy giá trị đã có nên không phải ba lượt chờ tuần tự tách rời như khi bắt đầu từng call rồi đợi ngay. Nếu bất kỳ nguồn nào lỗi, `allOf` sẽ exceptional, không chạy `thenApply` bình thường.

Khi chỉ có **hai nguồn**, `thenCombine` thường súc tích và giữ type tốt hơn, không cần `join()` trong callback.

### 11.4. Không nhầm with applyToEither

Nếu yêu cầu là “dùng kết quả của server A hoặc B, cái nào có kết quả hợp lệ trước” thì cân nhắc `applyToEither`. Nó không phải API **hợp nhất cả hai**. Với quota, timeout hoặc nguồn thất bại, cần kiểm tra chính xác semantics completion và chọn chiến lược lỗi phù hợp.

## 12. Tích hợp Spring: không để controller tự chạy hai tác vụ nối tiếp

### 12.1. Executor bean và @EnableAsync

Một cấu hình Spring để chạy các lời gọi bất đồng bộ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {

    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(64);
        pool.setThreadNamePrefix("io-");
        return pool; // Spring container gọi initialize/destroy.
    }
}
~~~

Đây là **class cấu hình** trong dự án Spring, chưa có main. `@EnableAsync` cho phép xử lý `@Async`; một `ThreadPoolTaskExecutor` là bean do container quản lý được inject/sử dụng theo tên.

Các con số **chỉ minh họa**, phải chọn theo giới hạn connection, throughput, queue, error budget và độ trễ của downstream. `queueCapacity=64` nghĩa là task có thể phải chờ; nó không bảo đảm hai source của một yêu cầu luôn được chạy cùng lúc nếu pool đang bận.

### 12.2. Hai service độc lập

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    @Async("ioExecutor")
    public CompletableFuture<String> getName(String productId) {
        return CompletableFuture.completedFuture("Book-" + productId);
    }
}
~~~

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    @Async("ioExecutor")
    public CompletableFuture<Integer> getPrice(String productId) {
        return CompletableFuture.completedFuture(50);
    }
}
~~~

Đây là **hai tệp Java riêng trong một ứng dụng Spring**, yêu cầu import/package/component scanning phù hợp. Trong ví dụ, target method trả một `completedFuture` sau khi hoàn thành phép tính; khi gọi qua **Spring proxy**, Spring async interceptor nộp việc lên executor và caller nhận future đại diện cho invocation bất đồng bộ. Với service thực tế, nội dung method thường là lời gọi I/O blocking hoặc thao tác nghiệp vụ. Không gọi `this.getPrice(...)` bên trong chính bean rồi suy rằng `@Async` sẽ được intercept; self-invocation mặc định bỏ qua proxy.

### 12.3. Service tổng hợp bằng thenCombine

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private final CatalogService catalog;
    private final PricingService pricing;

    public QuoteService(CatalogService catalog, PricingService pricing) {
        this.catalog = catalog;
        this.pricing = pricing;
    }

    public CompletableFuture<String> quote(String productId) {
        CompletableFuture<String> name =
                catalog.getName(productId);
        CompletableFuture<Integer> price =
                pricing.getPrice(productId);

        return name.thenCombine(
                price, (n, p) -> n + " : " + p);
    }
}
~~~

Đây là **service component** trong cùng ứng dụng, không có `main` độc lập. Gọi `catalog.getName` rồi `pricing.getPrice` **không đồng nghĩa đợi task thứ nhất hoàn tất**: hai lời gọi trả future và không `join` trước khi bắt đầu lời gọi thứ hai. Nếu một phép gọi bị từ chối **ngay lúc submit** (ví dụ executor đã shutdown), cần xử lý lỗi đồng bộ ngay tại orchestration layer; nếu một future thất bại sau đó, future kết hợp sẽ phản ánh failure.

### 12.4. Controller trả CompletableFuture

Trong Spring MVC có thể trả một `CompletableFuture` để framework tích hợp xử lý async result:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuoteController {
    private final QuoteService quotes;

    public QuoteController(QuoteService quotes) {
        this.quotes = quotes;
    }

    @GetMapping("/quotes/{id}")
    public CompletableFuture<String> get(@PathVariable String id) {
        return quotes.quote(id);
    }
}
~~~

**Đây là Spring MVC snippet**, cần web starter/dependency, không phải tệp Java 17 chạy độc lập. Tránh ép controller gọi `quote(id).join()` không timeout khi request đang theo mô hình async; việc đó block servlet thread và có thể đánh mất lợi ích chồng lấp/giải phóng tài nguyên. Cần exception mapping phù hợp với contract HTTP và deadline.

### 12.5. Tại sao @Async và thenCombine không thay thế nhau?

- `@Async`/`supplyAsync` quyết định **cách khởi chạy một tác vụ** lên executor.
- `thenCombine` quyết định **dependency kết quả**: kết hợp A và B sau khi cả hai hoàn thành bình thường.
- `thenCombineAsync(..., executor)` thêm lựa chọn **nơi chạy bước ghép**.
- Quản lý transaction/security/MDC không tự xuyên thread. Nếu cần truyền ngữ cảnh, phải dùng cơ chế propagation rõ ràng, không giả định các worker dùng chung `ThreadLocal` của caller.

## 13. Ví dụ Spring Context Java 17 chạy được bằng Maven

Ví dụ kế tiếp **không cần Spring Boot/Web server**: chỉ cần Spring Context, tạo hai bean `@Async` và kết hợp chúng trong một bean orchestration. Đầu ra được xác định bằng kết quả, không phụ thuộc thứ tự hai worker in log.

### 13.1. Cấu trúc dự án

~~~text
spring-combine-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringCombineDemo.java
~~~

Tệp `pom.xml` dùng Java 17 và Spring Framework 6.2.16:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-combine-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/SpringCombineDemo.java`:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SpringCombineDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    static class Config {
        @Bean("ioExecutor")
        ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(2);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("io-");
            return pool;
        }

        @Bean
        Catalog catalog() {
            return new Catalog();
        }

        @Bean
        Pricing pricing() {
            return new Pricing();
        }

        @Bean
        QuoteService quoteService(Catalog catalog, Pricing pricing) {
            return new QuoteService(catalog, pricing);
        }
    }

    static class Catalog {
        @Async("ioExecutor")
        public CompletableFuture<String> name(long id) {
            return CompletableFuture.completedFuture("Book-" + id);
        }
    }

    static class Pricing {
        @Async("ioExecutor")
        public CompletableFuture<Integer> price(long id) {
            return CompletableFuture.completedFuture(50);
        }
    }

    static class QuoteService {
        private final Catalog catalog;
        private final Pricing pricing;

        QuoteService(Catalog catalog, Pricing pricing) {
            this.catalog = catalog;
            this.pricing = pricing;
        }

        CompletableFuture<String> quote(long id) {
            CompletableFuture<String> name = catalog.name(id);
            CompletableFuture<Integer> price = pricing.price(id);
            return name.thenCombine(
                    price, (n, p) -> n + ":" + p);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            QuoteService service = context.getBean(QuoteService.class);
            String result = service.quote(7)
                                   .get(5, TimeUnit.SECONDS);
            System.out.println("quote = " + result);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SpringCombineDemo
~~~

**Stdout do lớp demo tạo ra** (bỏ qua log Maven/Spring nếu có):

~~~text
quote = Book-7:50
~~~

Giải thích:

1. `@EnableAsync` kích hoạt proxy-based async support.
2. Bean `Catalog` và `Pricing` được gọi qua bean reference được Spring inject, không phải self-invocation.
3. Mỗi method `@Async("ioExecutor")` chạy theo executor được chỉ định và trả future kết quả.
4. `QuoteService.quote` tạo cả hai future rồi đăng ký `thenCombine`; không lấy giá trị `name.get` trước khi tạo `price`.
5. `main` chỉ chờ **tại ranh giới trình diễn** bằng `get(timeout)`, không biến phương thức service thành synchronous. `AnnotationConfigApplicationContext` đóng qua try-with-resources, nên executor bean được Spring hủy theo lifecycle.

**Lưu ý:** chương trình tạo hai task rất ngắn; việc có hai worker không chứng minh chúng thật sự chạy đồng thời trong mỗi lần chạy. Tính đúng đắn của bài là **không có phụ thuộc dữ liệu và hợp nhất sau khi cả hai stage thành công**, không phải việc đo tốc độ của ví dụ quá nhỏ này.

## 14. Những bẫy hiệu năng khi kết hợp future

### 14.1. join quá sớm làm mất sự độc lập

Không nên:

~~~java
String name = catalog.getName(id).join();
int price = pricing.getPrice(id).join();
return CompletableFuture.completedFuture(name + ":" + price);
~~~

Đây là **snippet**. Lời gọi thứ hai chỉ xuất hiện **sau** khi `join()` của future thứ nhất hoàn thành, nên bạn đã biến dependency thành tuần tự và block caller.

Nên:

~~~java
CompletableFuture<String> name = catalog.getName(id);
CompletableFuture<Integer> price = pricing.getPrice(id);

return name.thenCombine(price, (n, p) -> n + ":" + p);
~~~

Hai nguồn được khởi chạy trước khi tổng hợp; caller nhận future và có thể làm việc khác.

### 14.2. Blocking bên trong combiner

~~~java
return a.thenCombine(b, (x, y) -> {
    return externalClient.fetchBlocking(x, y);
});
~~~

**Snippet nguy hiểm**, vì `externalClient.fetchBlocking` giả định chặn. Với `thenCombine` non-Async, chính thread hoàn tất stage cuối có thể bị giữ quá lâu trong combiner. Nếu cần một bước I/O thứ ba phụ thuộc A và B, tạo stage tiếp theo:

~~~java
return a.thenCombine(b, Pair::new)
        .thenCompose(pair ->
                externalClient.fetchAsync(pair.first(), pair.second()));
~~~

Đây là **snippet** với `Pair`/`externalClient` do ứng dụng định nghĩa. `thenCompose` flatten future trả về từ lời gọi I/O kế tiếp thay vì giữ thread của continuation để chờ.

### 14.3. Thread starvation/deadlock do join trong chính pool nhỏ

Với pool chỉ có 1 worker, nếu một task đang chạy trong worker đó gửi thêm hai task về cùng pool rồi gọi `join()` đợi chúng, worker có thể bị chặn và không còn worker nào để thực hiện hai task đã enqueue. Đây có thể là **starvation deadlock** do việc chờ bên trong cùng pool.

Cách tránh: dùng composition không chặn, quản lý pool phù hợp, tách blocking I/O/CPU và tránh thiết kế task trong pool tự đợi các task con ở cùng pool mà không có khả năng thực thi.

### 14.4. Hai nguồn đều dùng chung downstream giới hạn thấp

`thenCombine` không tạo ra “năng lực hệ thống” mới. Nếu A và B đều gọi cùng DB pool 5 connection, số request đồng thời tăng có thể làm latency xấu hơn. Cần giới hạn concurrency, queue capacity, timeout, circuit breaker/bulkhead phù hợp thay vì cứ tăng thread count.

### 14.5. Bỏ Future kết quả

Nếu chỉ viết:

~~~java
nameFuture.thenCombine(priceFuture, (n, p) -> send(n, p));
~~~

**Snippet** với `send` giả định. Nếu `send` thất bại mà bạn bỏ future kết quả, lỗi của continuation có thể bị bỏ sót. Hãy giữ Future, trả về cho caller hoặc gắn observer có ownership rõ ràng. Đừng coi việc gọi `thenCombine` là cam kết side effect đã chạy thành công.

## 15. Kiểm thử không phụ thuộc scheduler

### 15.1. Test thenCombine chỉ chạy sau khi đủ hai kết quả

JUnit 5 snippet (cần imports và assertion tương ứng):

~~~java
CompletableFuture<Integer> left = new CompletableFuture<>();
CompletableFuture<Integer> right = new CompletableFuture<>();

CompletableFuture<Integer> combined =
        left.thenCombine(right, Integer::sum);

left.complete(20);
assertFalse(combined.isDone());

right.complete(22);
assertEquals(42, combined.join());
~~~

Không cần `Thread.sleep`, pool hay network; test kiểm tra trực tiếp **điều kiện về trạng thái** của hai stage.

### 15.2. Test thứ tự hoàn thành đảo ngược

~~~java
CompletableFuture<String> name = new CompletableFuture<>();
CompletableFuture<Integer> price = new CompletableFuture<>();

CompletableFuture<String> quote =
        name.thenCombine(price, (n, p) -> n + ":" + p);

price.complete(50);
assertFalse(quote.isDone());

name.complete("Book");
assertEquals("Book:50", quote.join());
~~~

Đây là JUnit snippet. Thứ tự tham số `(n,p)` không thay đổi khi `price` hoàn thành trước.

### 15.3. Test lỗi upstream và lỗi combiner

~~~java
CompletableFuture<Integer> left = new CompletableFuture<>();
CompletableFuture<Integer> right = new CompletableFuture<>();

CompletableFuture<Integer> sum =
        left.thenCombine(right, Integer::sum);

left.completeExceptionally(
        new IllegalArgumentException("left failed"));
right.complete(2);

CompletionException ex =
        assertThrows(CompletionException.class, sum::join);
assertEquals("left failed", ex.getCause().getMessage());
~~~

Đây là JUnit 5 snippet; cần import các type và `assertThrows/assertEquals`. Với **một nguồn lỗi, một nguồn thành công**, cause kiểm tra được. Với **cả hai nguồn lỗi**, đừng khóa test vào một cause được chọn nếu contract không quy định.

Để kiểm tra combiner exception, cho cả hai thành công và làm `BiFunction` ném `IllegalStateException`; xác minh combined stage exceptional và hai nguồn vẫn successful.

### 15.4. Kiểm thử executor và performance

- Với `thenCombineAsync(..., executor)`, cấp executor có `ThreadFactory` đặt tên kiểm soát được rồi assert tên thread hoặc dùng probe phù hợp; test nên đợi `Future` có timeout.
- Kiểm tra saturation/rejection của executor cấp cho continuation.
- Dùng `CountDownLatch` khi muốn chứng minh hai task đã bắt đầu trước khi mở cổng hoàn tất.
- Đo latency p95/p99, số task active/queued, lỗi upstream và exception từ combiner.
- Kiểm tra cancellation, timeout và graceful shutdown; xác nhận không rò rỉ thread/connection.
- Với Spring `@Async`, test gọi qua bean proxy trong `ApplicationContext`, không gọi trực tiếp một instance `new` rồi khẳng định async support đang hoạt động.

## 16. Checklist triển khai thực tế

- [ ] Hai công việc thật sự **không cần kết quả của nhau** để bắt đầu; nếu cần, chuyển sang `thenCompose`.
- [ ] Hai future đã được tạo/khởi động trước khi chờ kết quả, không `join` ngay sau future thứ nhất.
- [ ] `BiFunction` chỉ ghép/mapping dữ liệu và không block lâu ở default non-Async path.
- [ ] Nếu combiner nặng, đã chọn `thenCombineAsync(..., executor)` với executor có giới hạn và được quản lý.
- [ ] Có chính sách riêng cho lỗi upstream, lỗi trong combiner và lỗi schedule continuation.
- [ ] Fallback được đặt đúng source hoặc ở cả kết quả, không vô ý che lỗi thành giá trị `null`.
- [ ] Có deadline/timeouts cho toàn operation và từng downstream khi phù hợp.
- [ ] Cancellation/cleanup của hai nguồn được thiết kế rõ, không giả định hủy stage cuối tự hủy tất cả.
- [ ] Có chủ sở hữu Future kết hợp; không bỏ kết quả khi lỗi nghiệp vụ phải được ghi nhận.
- [ ] Với Spring: executor bean, `@EnableAsync`/`@Async` và lời gọi qua proxy hoạt động đúng; không self-invocation.
- [ ] Không chờ `get/join` vô hạn trên request thread hay worker thread có thể gây starvation.
- [ ] Kiểm tra connection pool, queue, thread pool, metric latency/error và quá tải khi nhiều request gọi hai nguồn.
- [ ] Test thành công/lỗi/null/timeout/cancel/đảo thứ tự hoàn thành với cơ chế đồng bộ xác định.

## 17. Những ngộ nhận thường gặp

**1. “thenCombine tự chạy hai tác vụ cùng lúc.”** Sai. Nó chỉ đăng ký dependency kết hợp; hai future phải được tạo/khởi chạy bởi API của nguồn.

**2. “Hai future độc lập nghĩa là chắc chắn chạy song song.”** Sai. Có thể dùng một worker, hoặc upstream thực thi đồng bộ; vẫn độc lập về dữ liệu.

**3. “thenCombine chờ bằng cách block thread gọi.”** Không phải như gọi hai `get()`. Nó tạo stage mới. Tuy nhiên `BiFunction` có thể chạy inline khi cả hai đã hoàn thành; tránh blocking combiner.

**4. “thenCombineAsync làm hai API nguồn trở thành async.”** Sai. Nó chỉ quyết định scheduling của bước kết hợp.

**5. “thenCombine luôn chạy trên commonPool.”** Sai. Bản non-Async có thể chạy inline; chỉ overload Async không executor mới sử dụng default async facility của stage.

**6. “B hoàn thành trước A nên tham số đầu tiên là B.”** Sai. Tham số giữ vị trí nguồn `this` và `other`.

**7. “Một nguồn lỗi thì combiner vẫn có thể tạo partial result.”** Không theo default normal-path. Muốn partial, recover input bằng `exceptionally/handle` trước khi ghép.

**8. “Khi một nguồn lỗi, thenCombine luôn fail-fast ngay lập tức.”** Không nên phụ thuộc vào timing này; cần deadline rõ.

**9. “whenComplete đã log lỗi thì future kết hợp tự thành công.”** Sai. Quan sát lỗi không đồng nghĩa recover.

**10. “Hủy future kết hợp sẽ tự hủy cả hai HTTP request.”** Sai nếu không xây explicit cancellation propagation cho async clients.

**11. “orTimeout tự cancel downstream I/O.”** Sai. Timeout hoàn thành future exceptional, còn tác vụ nền có thể tiếp tục.

**12. “thenCombine phù hợp hơn thenCompose cho mọi trường hợp.”** Sai. `thenCompose` dùng cho bước tiếp theo phụ thuộc kết quả trước; `thenCombine` cho hai nguồn độc lập.

**13. “allOf trả danh sách kết quả của từng future.”** Sai. `allOf` trả `CompletableFuture<Void>`, cần truy xuất kết quả từ từng nguồn sau khi barrier hoàn thành.

**14. “Đã có @Async thì không cần @EnableAsync hoặc proxy.”** Sai đối với Spring default async interception.

**15. “Nhiều thread hơn luôn làm thenCombine nhanh hơn.”** Sai khi giới hạn chính là DB, HTTP connection, CPU hoặc downstream; tăng concurrency có thể gây queue/timeout.

**16. “Future combined không cần lưu vì đã đăng ký callback rồi.”** Sai nếu kết quả/exception cần được quan sát hoặc dùng ở API response.

## 18. Câu hỏi tự luyện

**Câu 1:** `CompletableFuture.completedFuture(10).thenCombine(completedFuture(32), Integer::sum)` cho kết quả gì?

**Đáp án:** 42. Hai nguồn đã hoàn thành bình thường và combiner cộng hai giá trị.

**Câu 2:** Bạn cần lấy `userId` trước rồi mới gọi API tải đơn hàng theo `userId`. Dùng `thenCombine` hay `thenCompose`?

**Đáp án:** `thenCompose`; lời gọi tải đơn hàng phụ thuộc vào kết quả lookup user.

**Câu 3:** Giá hoàn thành trước tên sản phẩm. Tham số đầu tiên trong `name.thenCombine(price, (n,p)->...)` là gì?

**Đáp án:** vẫn là tên `n`. Thứ tự tham số do vị trí `this`/`other`, không phải thời điểm kết thúc.

**Câu 4:** Hàm kết hợp ném `IllegalArgumentException`, hai future đầu đã thành công. Future kết hợp sẽ thế nào?

**Đáp án:** completed exceptionally; hai future nguồn không mặc nhiên bị chuyển thành failed.

**Câu 5:** Vì sao `thenCombineAsync(right, fn, executor)` chưa chắc làm API A và B chạy song song?

**Đáp án:** executor chỉ dùng cho **fn**; hai nguồn vẫn do cơ chế riêng của chúng khởi chạy và có thể cùng chạy trên pool một worker.

**Câu 6:** Một input bị cancel; gọi `combined.join()` có chắc trả giá trị bình thường không?

**Đáp án:** không. Dependent có thể exceptional do cancellation của nguồn; cần xử lý riêng và hiểu rằng hủy stage cuối không tự hủy nguồn còn lại.

**Câu 7:** Có nên gọi `nameFuture.join()` trước khi tạo `priceFuture` trên request thread?

**Đáp án:** không, nếu hai nguồn độc lập và yêu cầu khai thác concurrency. Hãy tạo cả hai future trước rồi combine.

**Câu 8:** Hai upstream đều chậm; `thenCombine` có giới hạn chờ mặc định không?

**Đáp án:** không có deadline nghiệp vụ tự động. Thiết kế timeout ở async client/source và whole-operation boundary.

## 19. Tóm tắt cốt lõi

**Công thức:** khởi chạy hai nguồn độc lập để có `CompletableFuture<A>` và `CompletableFuture<B>`, sau đó dùng `a.thenCombine(b, (x, y) -> combine(x, y))` để tạo `CompletableFuture<C>`. Hàm kết hợp chạy khi cả hai nguồn **thành công**. Bản non-Async không đòi hỏi thread riêng; bản Async chọn default facility hoặc executor được truyền.

Dùng `thenCompose` khi lời gọi thứ hai **phụ thuộc** giá trị thứ nhất; dùng `allOf` khi cần barrier cho nhiều nguồn. Với Spring, kết hợp `@Async`/async client và `ThreadPoolTaskExecutor` cấu hình có giới hạn để điều phối nguồn, rồi trả future kết hợp cho tầng trên. Đừng bỏ quên lỗi, timeout, cancellation, context propagation và chi phí chờ/queue khi vận hành.

## Tài liệu tham khảo chính thức

- Java SE 17 — `CompletableFuture` (thenCombine, thenCombineAsync, exceptionally, cancel): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Java SE 17 — `CompletionStage`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- Spring Framework 6.2 — Task Execution and Scheduling / @Async: https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework — Spring MVC async requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
