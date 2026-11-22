# CompletableFuture: thenApply, thenAccept và thenRun (Java 8+)

## 1. Ba phương thức, ba vai trò trong pipeline bất đồng bộ

Trong một ứng dụng Java, bạn có thể có một tác vụ trả về tên khách hàng, sau đó muốn chuẩn hóa tên, gửi tên cho thành phần ghi nhận kết quả và cuối cùng phát một tín hiệu cho biết chuỗi thao tác đã hoàn tất.

**CompletableFuture** cho phép mô tả các bước phụ thuộc bằng callback, thay vì tự gọi một tác vụ, chờ xong rồi mới viết lệnh cho tác vụ tiếp theo.

Ba phương thức trọng tâm:

- **thenApply**: nhận kết quả của stage trước, **biến đổi thành một giá trị khác** và tạo stage kiểu kết quả mới.
- **thenAccept**: nhận kết quả của stage trước để **tiêu thụ hoặc thực hiện side effect**, nhưng **không tạo giá trị trả về**.
- **thenRun**: **không nhận kết quả của stage trước**, chỉ thực hiện một tác vụ sau khi stage trước hoàn tất bình thường; cũng không tạo giá trị trả về.

Ví dụ ngắn:

~~~java
CompletableFuture<String> name =
        CompletableFuture.completedFuture("  lan  ");

CompletableFuture<String> normalized =
        name.thenApply(String::trim);

CompletableFuture<Void> displayed =
        normalized.thenAccept(System.out::println);

CompletableFuture<Void> done =
        displayed.thenRun(() -> System.out.println("Xong"));

done.join();
~~~

Đây là đoạn minh họa **trong một method** đã import java.util.concurrent.CompletableFuture. Với input này, chương trình in lần lượt tên sau khi trim là **lan**, rồi **Xong**.

**Cốt lõi:** đuôi chuỗi **thenApply → thenAccept → thenRun** nói rằng bước sau phụ thuộc bước trước, nhưng không có nghĩa tất cả stage luôn chạy trên thread mới. Những khác biệt về thread và phiên bản Async được giải thích ở các phần sau.

Tất cả ba phương thức này đã có từ Java 8, vẫn hiện diện trong Java SE hiện hành. Bài chỉ sử dụng API còn được hỗ trợ.

## 2. Mental model: CompletableFuture<T> là một stage có kết quả

**CompletableFuture<T>** vừa là Future có thể được hoàn tất, vừa là một **CompletionStage<T>** cho phép tạo các stage phụ thuộc.

- **T** là kiểu kết quả khi stage hoàn tất bình thường.
- Stage có thể ở trạng thái **chưa hoàn tất**, **hoàn tất bình thường** (kể cả kết quả null), hoặc **hoàn tất ngoại lệ**.
- Khi một stage nguồn hoàn tất bình thường, các phương thức **then...** đã đăng ký có cơ hội chạy.
- Mỗi lời gọi **thenApply/thenAccept/thenRun** trả về **một stage phụ thuộc mới**. Không phải chỉ thực hiện một dòng lệnh rồi bỏ kết quả; stage mới còn mang trạng thái hoàn tất hoặc lỗi của callback.

Một hình dung:

~~~text
CompletableFuture<T> (source)
       |
       +-- thenApply(Function<T,U>) ---> CompletableFuture<U>
       |
       +-- thenAccept(Consumer<T>) ----> CompletableFuture<Void>
       |
       +-- thenRun(Runnable) ----------> CompletableFuture<Void>
~~~

Ba nhánh trong sơ đồ là **ba cách gọi độc lập trên cùng một source**. Khi cần thứ tự bắt buộc, phải **nối chuỗi** từ stage trả về của bước trước, thay vì đăng ký ba nhánh rồi mặc định chúng chạy theo thứ tự xuất hiện trong source code.

Một stage **Void** vẫn có ý nghĩa: nó biểu diễn **kết thúc công việc hoặc lỗi**, dù không chứa kết quả nghiệp vụ.

## 3. Bảng so sánh chính xác: Function, Consumer, Runnable

| Phương thức | Callback nhận gì? | Callback trả gì? | Kiểu stage trả về | Dùng khi nào? |
| --- | --- | --- | --- | --- |
| **thenApply(fn)** | Giá trị T | Một giá trị U | **CompletableFuture<U>** | Chuyển đổi, tính toán, chuẩn hóa, lập DTO |
| **thenAccept(action)** | Giá trị T | Không có giá trị (void) | **CompletableFuture<Void>** | Hiển thị, cập nhật trạng thái, gửi dữ liệu đến một sink |
| **thenRun(action)** | Không nhận giá trị T | Không có giá trị (void) | **CompletableFuture<Void>** | Tín hiệu hoặc việc phụ sau stage thành công |

Chữ ký khái niệm, với đối tượng nguồn **CompletableFuture<T>**:

~~~java
<U> CompletableFuture<U> thenApply(
        Function<? super T, ? extends U> fn);

CompletableFuture<Void> thenAccept(
        Consumer<? super T> action);

CompletableFuture<Void> thenRun(
        Runnable action);
~~~

Đây là **chữ ký API để đọc và hiểu**, không phải các method có thể tự khai báo lại bên ngoài CompletableFuture.

Các kiểu callback thuộc **java.util.function**:

- **Function<T,U>** có method **U apply(T value)**.
- **Consumer<T>** có method **void accept(T value)**.
- **Runnable** có method **void run()** (java.lang.Runnable).

**Dấu hiệu ghi nhớ:** Apply = **biến đổi**, Accept = **nhận và làm**, Run = **chạy không nhận dữ liệu**.

## 4. thenApply: chuyển đổi giá trị và giữ được dữ liệu tiếp theo

Giả sử future trả một chuỗi có khoảng trắng:

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("  java 8  ");

CompletableFuture<String> trimmed =
        source.thenApply(String::trim);

CompletableFuture<Integer> length =
        trimmed.thenApply(String::length);
~~~

Ta có chuỗi các kiểu:

~~~text
CompletableFuture<String>  "  java 8  "
             |
             + thenApply(trim)
             v
CompletableFuture<String>  "java 8"
             |
             + thenApply(length)
             v
CompletableFuture<Integer>  6
~~~

**thenApply** nhận giá trị T và trả U; T và U có thể giống hoặc khác nhau. Trong ví dụ đầu, String → String; sau đó String → Integer.

**thenApply không thay đổi stage gốc.** Source vẫn biểu diễn chuỗi ban đầu. Các stage trimmed và length là những stage kết quả khác có thể được truyền đến phần khác của chương trình.

**Không cần gọi join giữa mỗi thenApply.** Việc gọi join quá sớm có thể chặn thread người gọi, làm mất lợi ích phối hợp bất đồng bộ. Thông thường nên **trả stage cuối** lên tầng gọi và chỉ chờ tại ranh giới khi thật sự cần.

### Khi nào nên ưu tiên thenApply?

- Chuẩn hóa một giá trị đã có: trim, uppercase, map tên thành mã.
- Chuyển đổi đối tượng: từ dữ liệu service thành DTO.
- Thực hiện phép tính CPU nhỏ từ kết quả trước.
- Parse hoặc validate kết quả của tác vụ trước và trả giá trị mới. Nếu callback ném exception, stage phụ thuộc sẽ hoàn tất ngoại lệ.

Nên viết function **rõ ràng, ít side effect** khi có thể; cách này dễ test và dễ nối pipeline hơn.

## 5. thenAccept: tiêu thụ kết quả mà không trả về giá trị mới

~~~java
CompletableFuture<Integer> count =
        CompletableFuture.completedFuture(6);

CompletableFuture<Void> logged =
        count.thenAccept(n ->
                System.out.println("Count: " + n));

logged.join();
~~~

**thenAccept** là **Consumer<T>**: nhận n = 6 và chạy action, nhưng không trả thêm U cho stage sau.

**Không ghi**:

~~~java
// Không biên dịch: thenAccept trả CompletableFuture<Void>,
// không phải CompletableFuture<Integer>.
// CompletableFuture<Integer> wrong =
//         count.thenAccept(n -> System.out.println(n));
~~~

Nếu bạn muốn **in và vẫn giữ kết quả** trong một pipeline, có thể dùng **whenComplete** để quan sát, hoặc dùng một thenApply có trả lại giá trị nếu quy tắc nghiệp vụ cho phép. Tuy nhiên khi chỉ làm side effect sau khi nhận một kết quả, **thenAccept** diễn đạt mục đích rõ nhất.

**Lưu ý:** sau thenAccept, stage trả về mang **Void**, nên callback **thenApply** tiếp theo nếu có sẽ nhận giá trị **null** (nếu stage hoàn tất bình thường). Nó không còn tự nhận kết quả T ban đầu. Nếu bước sau cần giá trị T, hãy nối từ stage trước hoặc thiết kế lại pipeline.

### Side effect và độ tin cậy

Một Consumer ghi log, gửi email, ghi database hoặc cập nhật UI có thể ném exception. Khi đó **stage trả về của thenAccept hoàn tất ngoại lệ**. Không nên giả định "thao tác side effect không có kết quả nên có lỗi cũng không ảnh hưởng".

Nếu side effect là giao tiếp với hệ thống bên ngoài (gửi email, thanh toán), cần **timeout, retry có kiểm soát, idempotency** và xác định executor thích hợp. CompletableFuture cung cấp cơ chế composition, chứ không tự bảo đảm side effect chỉ xảy ra một lần trong mọi môi trường phân tán.

## 6. thenRun: không nhận giá trị, chỉ chạy sau khi stage cha thành công

~~~java
CompletableFuture<String> source =
        CompletableFuture.completedFuture("ready");

CompletableFuture<Void> done =
        source.thenRun(() ->
                System.out.println("Previous stage succeeded"));

done.join();
~~~

**Runnable không có tham số**. thenRun không nhận "ready" mặc dù nó phụ thuộc vào việc source hoàn tất. Điều này hữu ích khi công việc chỉ cần biết **bước trước đã thành công**, chẳng hạn phát tín hiệu, đổi một cờ trạng thái hoặc giải phóng một bước workflow có chính sách phù hợp.

**Quan trọng:** **thenRun KHÔNG phải finally**. Nó **không chạy** nếu stage cha hoàn tất ngoại lệ hoặc bị hủy; khi đó stage của thenRun hoàn tất ngoại lệ. Nếu cần logic kiểm tra kết quả cả khi thành công và khi lỗi, xem **whenComplete** hoặc **handle**.

Không cố lấy kết quả của source bằng cách viết:

~~~java
// Không biên dịch: Runnable không có tham số.
// source.thenRun(value -> System.out.println(value));
~~~

Nếu cần dùng kết quả, chọn **thenAccept** hoặc **thenApply**.

## 7. Nối chuỗi và rẽ nhánh là hai ngữ nghĩa khác nhau

### Nối chuỗi: đảm bảo phụ thuộc theo thứ tự

~~~java
CompletableFuture<Void> done =
        CompletableFuture.completedFuture("alice")
            .thenApply(String::toUpperCase)
            .thenAccept(System.out::println)
            .thenRun(() -> System.out.println("Completed"));

done.join();
~~~

Ở đây **thenRun** đợi stage **thenAccept** trước đó hoàn tất bình thường, chứ không chỉ đợi source ban đầu. Nếu Consumer ném exception, thenRun bị bỏ qua và stage done báo lỗi.

### Rẽ nhánh: không bảo đảm callback nào đến trước

~~~java
CompletableFuture<String> source = new CompletableFuture<>();

CompletableFuture<Void> audit =
        source.thenAccept(value -> auditValue(value));

CompletableFuture<Void> metrics =
        source.thenRun(() -> incrementMetric());

source.complete("ok");
~~~

Đây là **mã minh họa**: auditValue và incrementMetric là method giả định của ứng dụng, không có định nghĩa trong đoạn này.

Hai callback **đều phụ thuộc source**, nhưng **không có hợp đồng thứ tự** chỉ vì audit được đăng ký trước metrics. Không dùng thứ tự các dòng đăng ký để suy ra thứ tự side effect.

Nếu cần đảm bảo metrics chạy **sau audit**, dùng **audit.thenRun(...)**. Nếu chỉ cần cả hai hoàn tất, có thể dùng **CompletableFuture.allOf(audit, metrics)** để tạo stage chờ cả hai, nhưng thứ tự giữa audit/metrics vẫn không do allOf quyết định.

**Một nguyên tắc hữu ích:** phụ thuộc thực → nối chuỗi; công việc độc lập → rẽ nhánh, rồi phối hợp bằng một stage kết hợp khi thật sự cần.

## 8. Ví dụ Java 17 hoàn chỉnh: giá trị, tiêu thụ, tín hiệu và lỗi

Tạo tệp **ThreeContinuationsDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.Locale;

public class ThreeContinuationsDemo {
    public static void main(String[] args) {
        CompletableFuture<String> source =
                CompletableFuture.completedFuture("  java 8  ");
        CompletableFuture<String> normalized =
                source.thenApply(String::trim)
                      .thenApply(text -> text.toUpperCase(Locale.ROOT));
        CompletableFuture<Integer> length =
                normalized.thenApply(String::length);
        CompletableFuture<Void> accepted =
                length.thenAccept(n ->
                        System.out.println("accepted length: " + n));
        CompletableFuture<Void> finished =
                accepted.thenRun(() ->
                        System.out.println("audit completed"));

        finished.join();
        System.out.println("normalized: " + normalized.join());
        System.out.println("length: " + length.join());
        System.out.println("accept result: " + accepted.join());
        System.out.println("run result: " + finished.join());

        CompletableFuture<String> nullable =
                CompletableFuture.completedFuture(null);
        System.out.println("null handled: " +
                nullable.thenApply(s -> s == null ? "missing" : s).join());

        CompletableFuture<Integer> broken = new CompletableFuture<>();
        AtomicInteger callbackRuns = new AtomicInteger();
        CompletableFuture<Integer> mapped =
                broken.thenApply(x -> {
                    callbackRuns.incrementAndGet();
                    return x + 1;
                });
        CompletableFuture<Void> consumed =
                broken.thenAccept(x -> callbackRuns.incrementAndGet());
        CompletableFuture<Void> signaled =
                broken.thenRun(callbackRuns::incrementAndGet);
        broken.completeExceptionally(new IllegalArgumentException("bad-input"));

        System.out.println("callbacks after failure: " + callbackRuns.get());
        System.out.println("mapped exceptional: " + mapped.isCompletedExceptionally());
        System.out.println("consumed exceptional: " + consumed.isCompletedExceptionally());
        System.out.println("signaled exceptional: " + signaled.isCompletedExceptionally());
        System.out.println("recovered: " + mapped.exceptionally(ex -> -1).join());

        CompletableFuture<Integer> completed =
                CompletableFuture.completedFuture(7);
        CompletableFuture<CompletableFuture<Integer>> nested =
                completed.thenApply(n ->
                        CompletableFuture.completedFuture(n * 3));
        CompletableFuture<Integer> flat =
                completed.thenCompose(n ->
                        CompletableFuture.completedFuture(n * 3));
        System.out.println("nested result: " + nested.join().join());
        System.out.println("flat result: " + flat.join());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac ThreeContinuationsDemo.java
java ThreeContinuationsDemo
~~~

**Stdout đã chạy và kiểm chứng chính xác:**

~~~text
accepted length: 6
audit completed
normalized: JAVA 8
length: 6
accept result: null
run result: null
null handled: missing
callbacks after failure: 0
mapped exceptional: true
consumed exceptional: true
signaled exceptional: true
recovered: -1
nested result: 21
flat result: 21
~~~

### Đọc kết quả

- **thenApply** biến chuỗi thành **JAVA 8**, rồi tính length = 6.
- **thenAccept** nhận số 6 và in nó; trả stage **Void**.
- **thenRun** chạy sau accepted, in tín hiệu **audit completed**; cũng trả stage **Void**.
- **join() của CompletableFuture<Void>** trả **null** khi hoàn tất bình thường. Đây không phải "stage chưa xong".
- Một source được phép hoàn tất bình thường với **kết quả null**. Trong ví dụ, Function chủ động biến null thành chuỗi **missing**.
- Khi source **broken** hoàn tất ngoại lệ, cả ba callback trực tiếp đều bị bỏ qua. Do vậy AtomicInteger vẫn bằng 0 và cả ba stage phụ thuộc báo hoàn tất ngoại lệ.
- **exceptionally(ex -> -1)** tạo một stage phục hồi có kết quả -1, không tự viết lại kết quả lỗi của source.
- **thenApply** với function trả CompletableFuture tạo future lồng nhau; **thenCompose** dùng khi cần "làm phẳng" stage của tác vụ kế tiếp.

Ví dụ chủ ý dùng **completedFuture** để kiểm thử deterministic thay vì dựa vào timing/thread ngẫu nhiên. Trong ứng dụng thật, source có thể được cung cấp bởi supplyAsync, một HTTP client bất đồng bộ hoặc một nguồn CompletionStage khác.

## 9. Tại sao thenAccept và thenRun trả CompletableFuture<Void>?

**Void** ở đây nói rằng **không có giá trị dữ liệu đầu ra**; không có nghĩa không thể chờ hoặc kiểm tra lỗi.

~~~java
CompletableFuture<Void> stage =
        CompletableFuture.completedFuture(10)
            .thenAccept(System.out::println);

stage.join(); // Hoàn tất bình thường: trả null.
~~~

Stage này vẫn có thể:

- Hoàn tất bình thường sau khi Consumer hoàn tất.
- Hoàn tất ngoại lệ nếu Consumer ném exception hoặc source lỗi.
- Được dùng làm nguồn cho **thenRun** sau đó.
- Được đưa vào **CompletableFuture.allOf(...)** để phối hợp hoàn tất.
- Được trả ra từ một service dưới dạng **CompletionStage<Void>** nhằm báo "công việc đã xong".

**Phân biệt với thenApply trả null:**

~~~java
CompletableFuture<String> nullableResult =
        CompletableFuture.completedFuture("x")
            .thenApply(value -> null);
~~~

Đây vẫn là **CompletableFuture<String>** theo type inference/ngữ cảnh, nhưng kết quả bình thường có thể là null. Còn thenAccept/thenRun được khai báo kiểu **CompletableFuture<Void>**, không có kết quả nghiệp vụ để dùng tiếp.

**Nếu bước sau cần T**, không chọn thenAccept chỉ vì muốn "truyền tiếp" T. Tiêu thụ giá trị và chuyển giá trị là hai vai trò khác nhau.

## 10. Completion bình thường và completion ngoại lệ

Các phương thức **thenApply, thenAccept, thenRun** được kích hoạt khi stage cha **hoàn tất bình thường**. Nếu cha kết thúc lỗi:

- Function/Consumer/Runnable của những phương thức này **không được gọi**.
- Stage phụ thuộc **hoàn tất ngoại lệ** theo quy tắc truyền lỗi của CompletionStage.
- Nếu callback tự ném exception, stage do callback tạo ra cũng hoàn tất ngoại lệ.
- Việc gọi join trên stage lỗi có thể ném **CompletionException**. Với get, người gọi có thể gặp **ExecutionException** theo hợp đồng Future.

Ví dụ xử lý lỗi:

~~~java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture("not-a-number")
            .thenApply(Integer::parseInt)
            .exceptionally(error -> -1);

System.out.println(result.join()); // -1
~~~

Ở đây **Integer.parseInt** ném NumberFormatException. Nó làm stage chuyển đổi hoàn tất ngoại lệ; **exceptionally** xử lý và trả giá trị dự phòng -1.

**Không đặt thenRun để "dọn dẹp bất kể thành công hay thất bại"**:

~~~java
// Không phù hợp nếu bắt buộc chạy cả khi source lỗi:
source.thenRun(() -> cleanup());
~~~

Đó là mã minh họa phụ thuộc biến source và method cleanup của ứng dụng. Muốn quan sát cả success/failure, cân nhắc **whenComplete((value,error) -> {...})**. Với tài nguyên phải đóng, vẫn cần quản lý vòng đời tài nguyên bằng cơ chế thích hợp, không giả định whenComplete tự tương đương mọi hành vi finally trong cấu trúc try-with-resources.

## 11. thenApply, thenAccept, thenRun không phải bộ xử lý lỗi

Ba callback này **chỉ thuộc đường thành công**. Java cung cấp các phương thức hiện hành cho nhánh lỗi và quan sát:

| API | Khi chạy | Kết quả |
| --- | --- | --- |
| **exceptionally(fn)** | Khi stage hoàn tất ngoại lệ | Trả giá trị fallback cùng kiểu T |
| **handle((v,e) -> ...)** | Khi stage hoàn tất bình thường hoặc ngoại lệ | Có thể tạo giá trị mới U |
| **whenComplete((v,e) -> ...)** | Khi stage hoàn tất bình thường hoặc ngoại lệ | Quan sát side effect, thường giữ kết quả/trạng thái của source |
| **thenApply(fn)** | Chỉ khi hoàn tất bình thường | Biến đổi T thành U |
| **thenAccept(action)** | Chỉ khi hoàn tất bình thường | Tiêu thụ T |
| **thenRun(action)** | Chỉ khi hoàn tất bình thường | Runnable không nhận T |

Ví dụ:

~~~java
CompletableFuture<String> safe =
        CompletableFuture.completedFuture("7")
            .thenApply(Integer::parseInt)
            .handle((value, error) ->
                    error == null ? "OK:" + value : "FAILED");

System.out.println(safe.join()); // OK:7
~~~

**handle** có hai tham số để kiểm tra giá trị hoặc exception. **whenComplete** cũng nhận cả value/exception nhưng không có mục đích biến đổi kết quả; nếu chính action trong whenComplete ném lỗi thì quy tắc kết hợp ngoại lệ theo hợp đồng API phải được xem xét.

**Trình tự đặt handler có tác động:** đặt **exceptionally** trước một thenApply có thể phục hồi lỗi ở đoạn trước, khiến thenApply được chạy với giá trị fallback. Đặt exceptionally sau các bước chuyển đổi có thể xử lý lỗi của cả những bước đó.

## 12. thenRun khác runAsync, thenApply khác supplyAsync

Hai họ method thường bị nhầm:

| Phương thức | Tạo stage bắt đầu công việc? | Phụ thuộc một stage khác? | Đầu ra |
| --- | --- | --- | --- |
| **CompletableFuture.supplyAsync(supplier)** | Khởi tạo một tác vụ sản xuất kết quả | Không cần stage trước | CompletableFuture<U> |
| **CompletableFuture.runAsync(runnable)** | Khởi tạo tác vụ không có kết quả | Không cần stage trước | CompletableFuture<Void> |
| **source.thenApply(fn)** | Đăng ký bước phụ thuộc | Có | CompletableFuture<U> |
| **source.thenAccept(action)** | Đăng ký bước phụ thuộc | Có | CompletableFuture<Void> |
| **source.thenRun(action)** | Đăng ký bước phụ thuộc | Có | CompletableFuture<Void> |

**runAsync** là phương thức **static** tạo một stage bắt đầu Runnable. **thenRun** là phương thức **instance** đăng ký Runnable chỉ chạy sau stage nguồn hoàn tất bình thường.

Ví dụ:

~~~java
CompletableFuture<String> load =
        CompletableFuture.supplyAsync(() -> "data");

CompletableFuture<String> uppercase =
        load.thenApply(String::toUpperCase);

CompletableFuture<Void> done =
        uppercase.thenAccept(System.out::println);
~~~

**Không kết luận rằng toàn bộ pipeline chạy bất đồng bộ chỉ vì một method có từ then.** Chỉ có nguồn ở đây được tạo bằng supplyAsync; các callback non-async có quy tắc thực thi riêng. Cần xem executor và tính chất của stage để biết thread nào thực hiện hành động.

## 13. Non-async: không bảo đảm một thread mới

Các phương thức **thenApply**, **thenAccept** và **thenRun** không có hậu tố Async.

Với một **CompletableFuture** thông thường, tài liệu Oracle cho biết callback non-async có thể được chạy bởi **thread hoàn tất stage trước**, hoặc bởi một thread đang thực hiện thao tác completion liên quan. Khi stage đã hoàn tất trước thời điểm đăng ký, callback có thể được thực thi ngay trong ngữ cảnh đăng ký. **Không có bảo đảm mọi callback được đưa sang một thread mới.**

Do đó:

- Không đưa công việc **chặn lâu, gọi I/O chặn hoặc tính toán nặng** một cách vô thức vào callback non-async của stage được hoàn tất ở thread quan trọng.
- Đừng dựa vào tên thread quan sát được trong một lần chạy làm hợp đồng chương trình.
- Callback non-async nhỏ và nhanh thường phù hợp cho bước chuyển đổi đơn giản.
- Nếu cần kiểm soát môi trường chạy, dùng **thenApplyAsync/thenAcceptAsync/thenRunAsync** với một Executor được cấp và quản lý rõ.

**Dùng CompletableFuture không biến lệnh blocking thành non-blocking.** Ví dụ, gọi I/O đồng bộ bên trong thenApply vẫn có thể chặn thread đang thực thi callback.

## 14. Ba biến thể Async và cách chọn Executor

Mỗi phương thức có biến thể **Async**:

~~~java
stage.thenApplyAsync(fn);
stage.thenApplyAsync(fn, executor);

stage.thenAcceptAsync(action);
stage.thenAcceptAsync(action, executor);

stage.thenRunAsync(task);
stage.thenRunAsync(task, executor);
~~~

Đây là **chữ ký gọi minh họa**: biến stage/fn/action/task/executor do ứng dụng cung cấp và có kiểu phù hợp.

Với **CompletableFuture mặc định**, các overload Async không truyền Executor thường sử dụng **ForkJoinPool.commonPool()** (hoặc cơ chế fallback được JDK quy định khi common pool không đủ parallelism). Tài liệu Java cho phép subclass thay đổi cơ sở thực thi Async mặc định.

**Async không hứa mỗi callback có một thread mới**, và cũng không hứa task chạy ngay. Nó chỉ chỉ định cơ chế sắp lịch bất đồng bộ. Executor có thể dùng lại thread hoặc xếp hàng công việc; thứ tự hoàn tất của các nhánh độc lập không được bảo đảm.

**Overload có Executor** là lựa chọn để kiểm soát tài nguyên, phân tách workload và quan sát dễ hơn.

~~~java
ExecutorService executor =
        Executors.newFixedThreadPool(4);

try {
    CompletableFuture<String> stage =
            CompletableFuture.completedFuture("abc");

    CompletableFuture<Integer> computed =
            stage.thenApplyAsync(String::length, executor);

    System.out.println(computed.join()); // 3
} finally {
    executor.shutdown();
}
~~~

**Lưu ý quản lý tài nguyên:** ExecutorService cần được đóng/chấm dứt phù hợp sau khi tác vụ đã hoàn tất. Đừng shutdown sớm nếu các callback tiếp theo vẫn cần executor. FixedThreadPool thông thường có hàng đợi có thể tích lũy nhiều tác vụ; với tải lớn cần chính sách backpressure/giới hạn lượng công việc, không coi một executor 4 thread là giới hạn luôn cả số công việc đang chờ.

## 15. Chương trình Java 17: Async rõ ràng với một Executor riêng

Tạo tệp **ThreeContinuationsAsyncDemo.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.*;

public class ThreeContinuationsAsyncDemo {
    public static void main(String[] args) {
        ExecutorService executor =
                Executors.newSingleThreadExecutor(task ->
                        new Thread(task, "pipeline-worker"));
        try {
            CompletableFuture<String> source =
                    CompletableFuture.completedFuture("order-7");

            CompletableFuture<String> transformed =
                    source.thenApplyAsync(value -> {
                        System.out.println("apply thread: "
                                + Thread.currentThread().getName());
                        return value.toUpperCase(Locale.ROOT);
                    }, executor);
            CompletableFuture<Void> consumed =
                    transformed.thenAcceptAsync(value ->
                            System.out.println("accept: " + value
                                    + " thread: "
                                    + Thread.currentThread().getName()),
                            executor);
            CompletableFuture<Void> done =
                    consumed.thenRunAsync(() ->
                            System.out.println("run thread: "
                                    + Thread.currentThread().getName()),
                            executor);
            done.join();
            System.out.println("transformed: " + transformed.join());
            System.out.println("consumed result: " + consumed.join());
            System.out.println("done result: " + done.join());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ThreeContinuationsAsyncDemo.java
java ThreeContinuationsAsyncDemo
~~~

**Stdout đã chạy và kiểm chứng:**

~~~text
apply thread: pipeline-worker
accept: ORDER-7 thread: pipeline-worker
run thread: pipeline-worker
transformed: ORDER-7
consumed result: null
done result: null
~~~

**Giải thích:**

- **Executor riêng** tạo một worker được đặt tên pipeline-worker để thuận tiện chứng minh tại đây.
- Cả ba callback đều là Async và đều dùng executor này; chúng chạy **theo chuỗi phụ thuộc**, không phải được cho phép chạy song song tự do.
- Do dùng executor một thread và join vào stage cuối, đầu ra deterministic: apply → accept → run, rồi các dòng kết quả.
- Việc dùng **thenRunAsync** ở đây là sau stage **consumed**, không phải sau source; vì vậy được bảo đảm không chạy trước Consumer.
- **join** ở main chỉ dùng để kiểm thử/chờ chương trình mẫu hoàn tất. Không cần gọi join sau mỗi callback trong một pipeline production.

**Không khái quát tên thread**: đó là tên do ví dụ tự cấu hình. Với Executor khác, callback có thể chạy trong các thread khác nhau và có lịch thực thi khác.

## 16. Khi nào tránh common pool và công việc blocking?

**ForkJoinPool.commonPool** thường được chia sẻ giữa nhiều phần của một JVM. Một callback Async không có Executor riêng có thể dùng common pool; nếu callback thực hiện I/O chặn lâu hoặc không kiểm soát số lượng tác vụ, có nguy cơ gây cạnh tranh tài nguyên với công việc khác.

Ví dụ kém an toàn nếu dùng tràn lan:

~~~java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("id-42");

// I/O chặn giả định, không nên cho mặc định vào common pool tải lớn:
// CompletableFuture<String> loaded =
//         ready.thenApplyAsync(id -> blockingNetworkCall(id));
~~~

**blockingNetworkCall** là phương thức giả định; đoạn được comment để không thể bị hiểu lầm là chương trình runnable.

Hướng cải thiện:

1. Nếu thư viện cung cấp API **thực sự bất đồng bộ**, ưu tiên dùng nó và kết hợp các CompletionStage.
2. Nếu buộc dùng blocking I/O, cân nhắc một **Executor được quản lý riêng**, cùng giới hạn số tác vụ, timeout và chính sách tải.
3. Nếu cần xử lý tác vụ CPU ngắn, dùng executor phù hợp CPU thay vì trộn với tác vụ blocking không giới hạn.
4. Kiểm tra metric: queue length, concurrency, latency, số stage hoàn tất lỗi và thời gian đợi.
5. Không gọi join/get bên trong task của một pool nhỏ để chờ một task khác cũng phải chạy trên cùng pool, vì có thể gây thiếu tiến triển hoặc deadlock.

**Với Java 21+**, virtual threads là một lựa chọn hiện hành cho nhiều tác vụ blocking I/O; nhưng chúng không làm cho việc gọi I/O chặn trở thành API bất đồng bộ, và không tự giải quyết backpressure. Chủ đề chính ở đây vẫn là cách dùng thenApply/thenAccept/thenRun từ Java 8.

## 17. CompletableFuture<Void> là điểm kết thúc workflow hợp lệ

Một service có thể định nghĩa:

~~~java
CompletionStage<Void> notifyAndAudit(String message) {
    return CompletableFuture.completedFuture(message)
        .thenAccept(value -> sendNotification(value))
        .thenRun(() -> markNotificationStageDone());
}
~~~

Đây là **mã minh họa**: sendNotification và markNotificationStageDone là các method cần hiện thực trong service.

Giá trị trả về **CompletionStage<Void>** cho phép tầng gọi:

- Tiếp tục đăng ký callback khi chuỗi thao tác hoàn tất.
- Gắn xử lý lỗi cho cả bước notification và bước mark done.
- Chờ/kiểm tra trạng thái khi ở ranh giới ứng dụng, không cần một giá trị trả về.
- Kết hợp nhiều workflow bằng allOf sau khi chuyển sang CompletableFuture khi cần.

**Thực tế side effect:** nếu sendNotification thất bại, stage của thenAccept hoàn tất ngoại lệ; thenRun không chạy. Nhưng nếu hệ thống bên ngoài đã thực thi một phần trước khi throw, CompletableFuture không thể tự rollback. Thiết kế nghiệp vụ phải xác định retry/idempotency riêng.

## 18. thenApply khác thenCompose: đừng tạo Future lồng nhau vô tình

Giả sử hàm biến đổi trả một **CompletableFuture<Integer>**, thay vì số nguyên trực tiếp.

~~~java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(7);

CompletableFuture<CompletableFuture<Integer>> nested =
        source.thenApply(n ->
                CompletableFuture.completedFuture(n * 3));

CompletableFuture<Integer> flat =
        source.thenCompose(n ->
                CompletableFuture.completedFuture(n * 3));
~~~

**thenApply** biến T thành U, nên U ở đây chính là **CompletableFuture<Integer>** và kết quả là stage lồng nhau. Để lấy 21 từ nested trong ví dụ, phải join hai lần.

**thenCompose** được thiết kế khi callback tạo ra **một CompletionStage mới**, tự làm phẳng để nhận một stage có kết quả cuối.

Đây là phân biệt có giá trị khi logic thực tế cần thêm một lời gọi service bất đồng bộ dựa trên kết quả trước. Đừng viết thenApply trả Future rồi chờ **join() ngay trong Function** chỉ để loại một lớp CompletableFuture; thường nên dùng thenCompose để giữ composition bất đồng bộ.

## 19. Sau thenAccept có thể thenApply gì?

**thenAccept** trả **CompletableFuture<Void>**, vì vậy kiểu đầu vào của bước tiếp theo là Void:

~~~java
CompletableFuture<Void> afterAccept =
        CompletableFuture.completedFuture("hello")
            .thenAccept(System.out::println);

CompletableFuture<String> signal =
        afterAccept.thenApply(ignored -> "acknowledged");
~~~

Ở đây callback thenApply nhận một tham số **Void**, có giá trị null khi stage trước hoàn tất bình thường. Nó tạo ra "acknowledged" **bất kể kết quả String ban đầu là gì**; đây là bước tạo tín hiệu mới từ completion, không phải cách lấy lại String gốc.

Với nhu cầu chỉ chạy tác vụ không cần đầu vào, **afterAccept.thenRun(...)** thường rõ ràng hơn. Với nhu cầu cần kết quả ban đầu, hãy giữ source hoặc stage chứa T.

### Tránh gán nhầm kiểu

~~~java
CompletableFuture<Integer> f =
        CompletableFuture.completedFuture("abc")
            .thenApply(String::length); // Đúng.

CompletableFuture<Void> consumed =
        f.thenAccept(System.out::println); // Đúng.

CompletableFuture<Void> finished =
        consumed.thenRun(() -> System.out.println("finish")); // Đúng.
~~~

Các kiểu generic là một phần quan trọng của hợp đồng API. Trình biên dịch sẽ ngăn nhiều lỗi gán Void thành Integer hoặc dùng lambda có tham số cho Runnable.

## 20. Kết thúc lỗi, hủy và ném lỗi từ callback

Xét một CompletableFuture chưa hoàn tất:

~~~java
CompletableFuture<Integer> broken = new CompletableFuture<>();

CompletableFuture<Integer> next =
        broken.thenApply(n -> n + 1);

broken.completeExceptionally(
        new IllegalStateException("failed"));
~~~

**thenApply** không chạy vì broken không hoàn tất bình thường, và next hoàn tất ngoại lệ. Với thenAccept và thenRun gắn trực tiếp vào broken, hành vi tương tự.

**Cancellation** trong CompletableFuture được xem là một dạng hoàn tất ngoại lệ. Khi source bị cancel, các dependent thông thường sẽ không chạy callback thành công. Tuy nhiên **cancel của một dependent không phải một giao thức hủy ngược tác vụ upstream đang chạy**; phải thiết kế cancellation và giải phóng tài nguyên rõ ràng.

**Nếu callback ném exception**, chỉ stage do callback đó tạo ra và các stage phụ thuộc vào nó chịu ảnh hưởng theo completion. Các nhánh độc lập đã bắt đầu không tự bị rollback.

### join và get

- **join()** đợi khi cần, trả kết quả T hoặc ném exception không được kiểm tra (thường CompletionException).
- **get()** đợi khi cần và có hợp đồng checked exceptions như InterruptedException, ExecutionException.
- **get(timeout, unit)** cho phép một giới hạn đợi ở thread người gọi; giới hạn đợi không tự triển khai timeout của tất cả nghiệp vụ upstream.
- Khi kết quả của **CompletableFuture<Void>** hoàn tất bình thường, join/get trả null.

Đừng gọi join/get trên thread UI/event-loop hoặc trong executor dễ deadlock. Trong chương trình console test, gọi ở main để chờ stage cuối là hợp lý.

## 21. Test chính xác các continuation, không dựa vào timing

Để kiểm thử ba phương thức:

**Kiểm thử biến đổi (thenApply)**

- Dùng completedFuture có giá trị định trước.
- Kiểm tra stage trả ra có kết quả và kiểu đúng.
- Với lambda ném exception, kiểm tra stage trả ra hoàn tất ngoại lệ.

**Kiểm thử tiêu thụ (thenAccept)**

- Dùng AtomicReference/AtomicInteger hoặc một test double để ghi nhận giá trị đã nhận.
- Join stage do thenAccept trả ra, rồi kiểm tra side effect.
- Không dựa vào System.out nếu cần assert mạnh trong unit test.

**Kiểm thử tín hiệu (thenRun)**

- Dùng AtomicBoolean/AtomicInteger để xác nhận Runnable chạy sau stage cha thành công.
- Thử source hoàn tất ngoại lệ và bảo đảm callback không chạy.
- Đừng xác định thứ tự hai nhánh độc lập bằng sleep vài millisecond.

**Kiểm thử Async**

- Dùng Executor do test kiểm soát, có thể là single-thread executor đặt tên hoặc executor thủ công.
- Đồng bộ bằng stage hoàn tất/latch thay vì Thread.sleep tùy ý.
- Không khẳng định thread cụ thể với non-async methods vì contract không bảo đảm.

**Kiểm thử lỗi và hủy**

- Tạo source với **new CompletableFuture<>()**, rồi gọi completeExceptionally/cancel.
- Kiểm tra callback không được gọi và stage phụ thuộc được đánh dấu lỗi.
- Nếu có stage recovery, kiểm tra fallback được trả về và chỉ ảnh hưởng nhánh được nối.

## 22. Java 8 thuần: ví dụ ngắn biên dịch được

Hai ví dụ chính ở trên dùng các API đã có từ Java 8. Bài có thêm một ví dụ tối giản, đã được biên dịch bằng **javac --release 8** để kiểm tra tương thích cú pháp và API.

Tạo tệp **BasicContinuationsJava8.java**:

~~~java
import java.util.Locale;
import java.util.concurrent.*;

public class BasicContinuationsJava8 {
    public static void main(String[] args) {
        CompletableFuture<Integer> stage =
                CompletableFuture.completedFuture(" hello ")
                    .thenApply(String::trim)
                    .thenApply(String::length);
        CompletableFuture<Void> accepted =
                stage.thenAccept(x ->
                        System.out.println("length: " + x));
        CompletableFuture<Void> done =
                accepted.thenRun(() ->
                        System.out.println("done"));
        done.join();
        System.out.println("value: " + stage.join());
        System.out.println("void value: " + done.join());
    }
}
~~~

Lệnh với JDK có javac:

~~~bash
javac BasicContinuationsJava8.java
java BasicContinuationsJava8
~~~

**Stdout kiểm chứng:**

~~~text
length: 5
done
value: 5
void value: null
~~~

Chương trình chỉ dùng CompletableFuture, lambda, method reference và các phương thức đã có từ Java 8; không cần thư viện bên ngoài.

**Ghi chú về ngữ nghĩa:** stdout của ví dụ này cố định bởi quan hệ phụ thuộc. Đừng dùng kết quả chạy một lần để khẳng định callback không có Async luôn sử dụng thread main trong mọi tình huống.

## 23. Chọn phương thức trong tình huống thực tế

| Nhu cầu | Cách thường hợp lý | Lưu ý |
| --- | --- | --- |
| Chuẩn hóa tên khách hàng | thenApply(String::trim) | Trả dữ liệu String mới |
| Tính tổng tiền từ danh sách đã tải | thenApply(items -> calculate(items)) | Trả kiểu tổng tiền |
| Ghi một giá trị đã xử lý ra sink | thenAccept(value -> write(value)) | Trả stage Void; kiểm soát side effect |
| Phát tín hiệu sau khi gửi dữ liệu thành công | sentStage.thenRun(() -> signal()) | Không nhận payload; chỉ đường thành công |
| Dùng nguồn API bất đồng bộ thứ hai | thenCompose(value -> fetchAsync(value)) | Tránh CompletableFuture lồng |
| Xử lý lỗi thành giá trị fallback | exceptionally(error -> fallback) | Đổi nhánh lỗi thành kết quả cùng kiểu |
| Xem cả kết quả và lỗi | whenComplete((v,e) -> audit(v,e)) | Không dùng thenRun thay finally |
| Điều khiển thread chạy callback | thenApplyAsync(fn, executor), ... | Quản lý Executor và tải |
| Hai nhánh độc lập phải cùng xong | allOf(first, second) | Không tự áp thứ tự giữa hai nhánh |

**Thực tế dự án:** sử dụng CompletableFuture để mô tả **chuỗi công việc có phụ thuộc**, không để thay thế mọi loại xử lý đồng bộ. Một phép toán nhỏ trên giá trị đã có có thể dùng thenApply không Async; một tác vụ I/O chặn cần lựa chọn môi trường thực thi phù hợp; một workflow side effect quan trọng cần giám sát completion/lỗi.

## 24. Những sai lầm cần tránh

1. **Dùng thenAccept khi còn cần kết quả T:** nó trả CompletableFuture<Void>, không giữ T làm output.
2. **Dùng thenRun rồi cố đọc T:** Runnable không có tham số.
3. **Dùng thenApply chỉ để println mà không trả giá trị:** lambda của Function phải trả U; dùng thenAccept cho side effect.
4. **Coi thenRun là finally:** nó chỉ chạy sau completion bình thường của stage cha.
5. **Cho rằng non-async luôn chạy trên main thread:** không có bảo đảm đó.
6. **Cho rằng Async luôn tạo thread mới:** thường chạy qua pool hoặc Executor được cấp.
7. **Dựa vào thứ tự đăng ký callback trên cùng source:** các nhánh độc lập không có cam kết thứ tự.
8. **Chặn bằng join sau mọi bước:** khiến luồng đáng lẽ bất đồng bộ trở thành chuỗi chờ đồng bộ.
9. **Dùng thenApply với Function trả CompletionStage rồi join ở trong Function:** tạo thiết kế lồng hoặc blocking; cân nhắc thenCompose.
10. **Nuốt ngoại lệ:** stage có thể lỗi; cần xử lý hoặc chuyển tiếp phù hợp.
11. **Không join/quan sát stage của side effect ở ranh giới cần độ tin cậy:** có thể bỏ lỡ lỗi.
12. **Dùng common pool cho I/O chặn nặng không kiểm soát:** gây cạnh tranh tài nguyên và độ trễ.
13. **Quên shutdown ExecutorService riêng:** rò tài nguyên/giữ JVM không kết thúc.
14. **Coi callback nhận null là lỗi completion:** CompletableFuture có thể hoàn tất bình thường với kết quả null; lambda cần chính sách null.
15. **Coi hủy một stage chắc chắn hủy cả tác vụ gốc:** hủy và tiến triển cần chính sách phối hợp riêng.
16. **Đưa side effect không idempotent vào các nhánh được retry tùy ý:** có thể thực thi nhiều lần theo điều phối ứng dụng.

## 25. Bài tập và đáp án

### Bài 1 — Chọn phương thức

**Đề:** từ CompletableFuture<String> biến tên thành chữ hoa và tiếp tục dùng kết quả.

**Đáp án:** **thenApply(String::toUpperCase)**; kết quả là CompletableFuture<String>.

### Bài 2 — In dữ liệu

**Đề:** từ CompletableFuture<Integer> in giá trị ra console, không trả dữ liệu mới.

**Đáp án:** **thenAccept(System.out::println)**; kết quả là CompletableFuture<Void>.

### Bài 3 — Tín hiệu hoàn thành

**Đề:** sau khi một stage thành công, in "Xong", không cần giá trị stage trước.

**Đáp án:** **thenRun(() -> System.out.println("Xong"))**.

### Bài 4 — Có chạy khi source lỗi?

**Đề:** stage source lỗi, rồi source.thenRun(() -> sendSignal()).

**Đáp án:** **Không chạy Runnable**, stage thenRun hoàn tất ngoại lệ. Muốn quan sát cả thành công/thất bại, xem whenComplete/handle.

### Bài 5 — thenRun sau thenAccept hay cùng source?

**Đề:** bắt buộc thao tác cập nhật metric chỉ chạy sau gửi thông báo.

**Đáp án:** **source.thenAccept(send).thenRun(updateMetric)**, không đặt hai nhánh độc lập trên source rồi dựa vào thứ tự dòng code.

### Bài 6 — Kiểu trả về

**Đề:** CompletableFuture<String> gọi thenApply(String::length), rồi thenAccept(n -> ...), sau đó thenRun(...). Kiểu stage theo thứ tự?

**Đáp án:** CompletableFuture<Integer>, CompletableFuture<Void>, CompletableFuture<Void>.

### Bài 7 — Future lồng

**Đề:** callback trả CompletableFuture<User> từ một service bất đồng bộ.

**Đáp án:** cân nhắc **thenCompose** thay thenApply để tránh CompletableFuture<CompletableFuture<User>>.

### Bài 8 — Cần callback chạy trên Executor riêng?

**Đáp án:** dùng overload như **thenAcceptAsync(action, executor)**; executor cần do ứng dụng quản lý vòng đời và tài nguyên.

### Bài 9 — thenAccept trả null nghĩa là chưa chạy?

**Đáp án:** không. Stage kiểu Void hoàn tất bình thường không mang kết quả, vì vậy join trả null; kiểm tra hoàn tất/exception riêng.

### Bài 10 — Ba nhánh từ cùng một future có thứ tự?

**Đáp án:** không bảo đảm thứ tự các callback độc lập. Muốn thứ tự thì nối stage; muốn tất cả hoàn tất thì dùng allOf.

### Bài 11 — Callback của thenApply ném exception?

**Đáp án:** stage phụ thuộc hoàn tất ngoại lệ; các stage then... thành công nối sau nó sẽ không chạy. Có thể dùng exceptionally/handle để xử lý theo chính sách.

### Bài 12 — Có nên dùng thenApplyAsync để chạy I/O chặn dài mà không truyền Executor?

**Đáp án:** không nên mặc định; nó thường dùng common pool của CompletableFuture. Với blocking I/O, cân nhắc API bất đồng bộ hoặc Executor chuyên dụng, giới hạn tải, timeout và metric.

## 26. Tổng kết và tham khảo chính thức

**Ghi nhớ 10 ý:**

1. **thenApply** nhận T, trả U, tạo CompletableFuture<U>.
2. **thenAccept** nhận T để thực hiện action, tạo CompletableFuture<Void>.
3. **thenRun** không nhận T, tạo CompletableFuture<Void>.
4. Cả ba **chạy trên đường hoàn tất bình thường** của stage cha, không phải handler chạy bất kể lỗi.
5. thenAccept/thenRun **không có kết quả nghiệp vụ**; join của stage Void hoàn tất bình thường trả null.
6. **Nối chuỗi** tạo quan hệ phụ thuộc rõ; **rẽ nhánh** không mang bảo đảm thứ tự giữa callback độc lập.
7. Non-async **không bảo đảm thread**; Async dùng cơ chế thực thi bất đồng bộ, có overload nhận Executor.
8. Dùng **thenCompose** khi callback tạo CompletionStage mới; thenApply khi callback trả giá trị trực tiếp.
9. **exceptionally, handle, whenComplete** có vai trò riêng trong xử lý và quan sát lỗi.
10. Chọn Executor và side effect phù hợp, tránh blocking và bỏ quên stage lỗi.

**Tài liệu chính thức Oracle Java SE 25 (API còn áp dụng):**

- CompletableFuture: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- CompletionStage: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionStage.html
- Function: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html
- Consumer: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Consumer.html
- Runnable: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Runnable.html
- Executor và ExecutorService: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executor.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html
- ForkJoinPool: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html

**Phạm vi phiên bản:** các phương thức thenApply, thenAccept, thenRun và overload Async có từ Java 8 và vẫn được hỗ trợ. Các chương trình chính đã chạy trên JDK 17+; ví dụ ngắn đã được biên dịch bằng mục tiêu Java 8. Bài không sử dụng API legacy làm giải pháp chính.
