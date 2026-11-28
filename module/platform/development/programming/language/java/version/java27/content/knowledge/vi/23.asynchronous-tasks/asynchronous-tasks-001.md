# CompletableFuture và mô hình kết quả hoàn thành sau trong Java 27

Khi ứng dụng gọi cơ sở dữ liệu, dịch vụ HTTP, hệ thống lưu trữ hoặc thực hiện một phép tính dài, kết quả không phải lúc nào cũng có ngay tại thời điểm gọi. Nếu luồng hiện tại phải đợi từng công việc hoàn tất trước khi bắt đầu công việc độc lập tiếp theo, thời gian phản hồi có thể tăng không cần thiết. Ngược lại, việc khởi động hàng loạt công việc mà không kiểm soát trạng thái, lỗi hay tài nguyên cũng có thể làm hệ thống quá tải.

Trong chương **Tác vụ bất đồng bộ** của **Java 27**, `CompletableFuture<T>` biểu diễn một **kết quả kiểu `T` có thể hoàn thành trong tương lai**. Ngoài việc chờ kết quả, nó cho phép khai báo các bước **phụ thuộc vào kết quả trước đó**, kết hợp những tác vụ độc lập, xử lý ngoại lệ và chỉ định nơi chạy phần việc tiếp theo.

Đây là API chính thức, ổn định thuộc `java.util.concurrent`, không cần preview. Bài học tập trung vào các cách dùng còn phù hợp với Java 27: `CompletionStage`, `CompletableFuture`, `Executor`, các phương thức `thenApply`/`thenCompose`/`thenCombine`, xử lý lỗi, timeout, hủy, chia sẻ kết quả và việc sử dụng virtual threads khi cần.

Nguồn chính thức: [CompletableFuture — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html), [CompletionStage — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionStage.html), [Executors — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html).

## 1. Kết quả hoàn thành sau khác gì giá trị thông thường?

Một phương thức đồng bộ trả giá trị trực tiếp:

~~~~java
String loadName(String id) {
    return "Customer-" + id;
}

String name = loadName("C01");
System.out.println(name);
~~~~

Với `CompletableFuture`, phương thức có thể trả về **đại diện cho kết quả** trước khi phép tính bên dưới hoàn tất:

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> "Customer-C01");

// Chỉ chạy sau khi future hoàn thành bình thường.
CompletableFuture<Integer> nameLength =
        future.thenApply(String::length);

System.out.println(nameLength.join()); // 12
~~~~

`supplyAsync` ở đây sắp xếp Supplier chạy bất đồng bộ; `thenApply` không cần chờ bằng cách chặn luồng tại điểm khai báo. Nó **đăng ký một bước phụ thuộc**: khi `future` có giá trị, bước ấy sẽ chuyển `String` thành `Integer`.

Sơ đồ:

~~~~text
       supplyAsync(load)
               |
       CompletableFuture<String>
               |
             thenApply
               |
       CompletableFuture<Integer>
               |
              join()
               |
      Giá trị cuối hoặc exception
~~~~

**Điểm phân biệt:** “không chặn luồng khi đăng ký continuation” không có nghĩa toàn bộ công việc không dùng thread hoặc không bao giờ chặn. Supplier có thể gọi I/O blocking, `join()` có thể chờ và một số continuation có thể chạy ngay trong thread đang gọi nếu stage đã hoàn tất.

### 1.1. Ba loại quan trọng

| Loại | Vai trò | Khả năng |
| --- | --- | --- |
| `Future<T>` | Tay nắm để kiểm tra/chờ một kết quả tương lai | `get`, `cancel`, trạng thái |
| `CompletionStage<T>` | Hợp đồng khai báo những bước xử lý khi kết quả có sẵn | `thenApply`, `thenCompose`, kết hợp, recovery |
| `CompletableFuture<T>` | Implementation của cả `Future` và `CompletionStage` | Đăng ký continuation, `get/join`, có thể chủ động `complete`/`completeExceptionally` |

`CompletionStage` **không công bố trực tiếp** phương thức tạo mới, hoàn tất thủ công hoặc chờ kết quả như `CompletableFuture`. Khi thiết kế API chỉ cần cho phép bên gọi **nối các bước xử lý**, có thể trả về `CompletionStage<T>` thay vì một đối tượng `CompletableFuture<T>` mà caller có quyền tự hoàn tất.

Không được hiểu `CompletionStage` là cơ chế bảo mật: một implementation có thể có API khác, và caller có thể gọi `toCompletableFuture()` để tương tác với một future phù hợp. Việc không muốn bên nhận can thiệp trạng thái là quyết định **thiết kế hợp đồng**, không phải thay thế kiểm soát quyền.

## 2. Trạng thái hoàn thành và vòng đời

Một `CompletableFuture<T>` thường bắt đầu ở trạng thái **chưa hoàn tất** (*incomplete*) rồi đi đến một trong ba kết quả:

~~~~text
                 Incomplete
                 /   |    \
                /    |     \
               v     v      v
        Normal(T)  Exceptional(Throwable)  Cancelled
                                              |
                                một dạng exceptional completion
~~~~

- **Hoàn thành bình thường:** có giá trị `T`; với reference type có thể là `null` nếu API cho phép.
- **Hoàn thành ngoại lệ:** công việc thất bại và future giữ exception để chuyển tới bên nhận.
- **Bị hủy:** với `CompletableFuture`, `cancel(...)` được biểu diễn như một trường hợp **exceptional completion** với `CancellationException`.

Một future đã hoàn tất bình thường hoặc ngoại lệ sẽ không tự chuyển về chưa hoàn tất. Những thao tác như `complete`, `completeExceptionally` và `cancel` **cạnh tranh** để quyết định kết quả lần đầu; chỉ một bên có thể thành công.

### 2.1. Tạo future đã hoàn tất

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> ready =
        CompletableFuture.completedFuture("OK");

CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("Invalid code"));

System.out.println(ready.join()); // OK
// failed.join(); // CompletionException chứa IllegalArgumentException
~~~~

`completedFuture(value)` hữu ích khi kết quả đã có ngay, ví dụ từ cache. `failedFuture(exception)` có ích nếu một API bất đồng bộ muốn báo lỗi **dưới dạng stage đã thất bại** thay vì ném trực tiếp tại thời điểm gọi.

`CompletableFuture.completedStage(value)` và `failedStage(exception)` là những factory trả về giao diện `CompletionStage` hạn chế; chúng phù hợp khi không muốn trao trực tiếp quyền hoàn tất của concrete future.

### 2.2. Hoàn tất thủ công

Khi nguồn kết quả là **callback API**, có thể tạo future chưa hoàn tất và hoàn tất nó khi callback đến:

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> response = new CompletableFuture<>();

boolean first = response.complete("received");
boolean second = response.complete("different");

System.out.println(first);             // true
System.out.println(second);            // false
System.out.println(response.join());   // received
~~~~

Lỗi có thể được báo bằng:

~~~~java
CompletableFuture<String> response = new CompletableFuture<>();
response.completeExceptionally(
        new IllegalStateException("Service unavailable"));
~~~~

Một `complete` hoặc `completeExceptionally` thành công sẽ kích hoạt các stage phụ thuộc tương ứng. Khi có nhiều callback cạnh tranh (thành công, timeout, lỗi, hủy), cần quy định rõ đường nào có quyền hoàn tất trước và đường nào phải bỏ qua khi future đã hoàn tất.

**Không tạo một `new CompletableFuture<>()` rồi quên gọi `complete` hoặc `completeExceptionally`.** Future đó có thể treo vĩnh viễn ở trạng thái incomplete, khiến `join()` hoặc các bước phụ thuộc không có điểm kết thúc.

## 3. Bắt đầu tác vụ bất đồng bộ: `supplyAsync` và `runAsync`

### 3.1. Phân biệt có giá trị và không có giá trị

| API | Đầu vào | Kết quả |
| --- | --- | --- |
| `supplyAsync(Supplier<U>)` | Hàm tính và trả về `U` | `CompletableFuture<U>` |
| `runAsync(Runnable)` | Công việc không trả dữ liệu | `CompletableFuture<Void>` |
| `supplyAsync(Supplier<U>, Executor)` | Hàm và nơi thực thi do caller chọn | `CompletableFuture<U>` |
| `runAsync(Runnable, Executor)` | Công việc và nơi thực thi do caller chọn | `CompletableFuture<Void>` |

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> count =
        CompletableFuture.supplyAsync(() -> 3 + 4);

CompletableFuture<Void> notification =
        CompletableFuture.runAsync(() -> System.out.println("Started"));

System.out.println(count.join()); // 7
notification.join();              // Chờ công việc hoàn thành
~~~~

`runAsync` phù hợp khi không có một giá trị nghiệp vụ cần trả, ví dụ tác vụ phát thông báo **trong bối cảnh đã có cơ chế xử lý retry/độ tin cậy phù hợp**. Không coi `CompletableFuture<Void>` là bằng chứng đã ghi bền vững vào queue hoặc dịch vụ ngoài nếu việc đó chưa được đảm bảo bởi hệ thống.

### 3.2. Không có Executor tường minh thì chạy ở đâu?

Với `CompletableFuture` chuẩn, các phương thức async **không truyền Executor** thường sử dụng `ForkJoinPool.commonPool()` khi common pool có mức song song lớn hơn 1; trường hợp không đáp ứng, JDK dùng executor tạo một thread mới cho mỗi async task. Subclass của `CompletableFuture` có thể override `defaultExecutor()` cho các phương thức async không tĩnh.

Không được mặc định:

- Mỗi lần `supplyAsync` sẽ tạo **virtual thread**.
- Lời gọi sẽ chạy trên chính thread HTTP đang xử lý request.
- Common pool là nơi thích hợp cho mọi I/O blocking.
- Hàng nghìn tác vụ không có giới hạn sẽ không gây vấn đề tài nguyên.

Nếu ứng dụng cần giới hạn concurrency, đặt tên thread, theo dõi metrics hoặc tách công việc CPU/I/O, hãy **truyền một Executor có vòng đời do ứng dụng quản lý**.

### 3.3. Ví dụ dùng Executor được quản lý

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExplicitExecutorDemo {
    static int calculate(int input) {
        return Math.multiplyExact(input, 2);
    }

    public static void main(String[] args) {
        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            CompletableFuture<Integer> first =
                    CompletableFuture.supplyAsync(
                            () -> calculate(10), executor);

            CompletableFuture<Integer> second =
                    CompletableFuture.supplyAsync(
                            () -> calculate(15), executor);

            System.out.println(first.thenCombine(
                    second, Integer::sum).join()); // 50
        }
    }
}
~~~~

Trong Java 27, `ExecutorService` hỗ trợ `AutoCloseable` nên có thể dùng `try-with-resources`. Đóng executor theo hợp đồng `close()` là một thao tác có thể chờ các công việc đã gửi hoàn thành; **không** tạo một executor cục bộ rồi đóng nó ngay nếu method cần trả về future đang chờ những continuation có thể còn được lên lịch trên executor đó.

`newFixedThreadPool` dùng một hàng đợi không giới hạn theo hợp đồng factory, vì vậy **giới hạn số worker không đồng nghĩa giới hạn số việc đang chờ**. Ứng dụng tải cao có thể cần một `ThreadPoolExecutor` với hàng đợi có giới hạn và chính sách từ chối phù hợp.

## 4. Từ một kết quả đến pipeline: `thenApply`, `thenAccept`, `thenRun`

Ba phương thức thường gặp có ngữ nghĩa khác nhau:

| Phương thức | Nhận kết quả trước? | Trả kết quả mới? | Kiểu stage mới |
| --- | --- | --- | --- |
| `thenApply(Function<T,U>)` | Có | Có, `U` | `CompletionStage<U>` |
| `thenAccept(Consumer<T>)` | Có | Không | `CompletionStage<Void>` |
| `thenRun(Runnable)` | Không nhận giá trị trước | Không | `CompletionStage<Void>` |

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> name =
        CompletableFuture.completedFuture("  Alice  ");

CompletableFuture<String> normalized =
        name.thenApply(String::strip)
            .thenApply(String::toUpperCase);

CompletableFuture<Void> printed =
        normalized.thenAccept(System.out::println);

CompletableFuture<Void> after =
        printed.thenRun(() -> System.out.println("Done"));

after.join();
// ALICE
// Done
~~~~

Mỗi `then...` tạo một stage mới đại diện cho kết quả xử lý tiếp theo. Nếu stage trước hoàn thành ngoại lệ, những bước `thenApply`/`thenAccept`/`thenRun` cần kết quả bình thường thường **không chạy**; future phụ thuộc hoàn thành ngoại lệ tương ứng, trừ khi có bước recovery.

### 4.1. Phương thức không có `Async` có chạy trên một thread khác không?

**Không có bảo đảm như vậy.** Theo hợp đồng `CompletableFuture`, continuation của các phương thức không mang hậu tố `Async` có thể chạy trong thread hoàn tất future trước đó **hoặc một thread khác gọi thao tác hoàn tất**. Nếu stage đã hoàn tất trước lúc đăng ký, callback có thể chạy ngay trong thread đang đăng ký.

~~~~java
CompletableFuture<String> ready =
        CompletableFuture.completedFuture("ready");

CompletableFuture<String> mapped =
        ready.thenApply(text -> text + "!");

System.out.println(mapped.join()); // ready!
~~~~

Ví dụ trên không chứng minh có thêm thread. Nếu callback chặn dài, nó có thể làm chậm thread đã hoàn tất nguồn hoặc thread đăng ký.

### 4.2. `thenApplyAsync` là gì?

`thenApplyAsync` yêu cầu chạy bước biến đổi theo **chế độ thực thi bất đồng bộ** của stage, với executor mặc định hoặc executor chỉ định:

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    CompletableFuture<String> result =
            CompletableFuture.completedFuture("input")
                    .thenApplyAsync(String::toUpperCase, executor);

    System.out.println(result.join()); // INPUT
}
~~~~

Những phương thức tương ứng còn có `thenAcceptAsync`, `thenRunAsync` và các overload nhận `Executor`. Hậu tố `Async` **không phải lời hứa về một thread mới cho mỗi lời gọi**; hành vi phụ thuộc executor. Nếu đưa một executor chạy trực tiếp trên thread caller, kết quả có thể không song song.

## 5. `thenCompose`: nối chuỗi các tác vụ bất đồng bộ

Giả sử cần lấy mã tài khoản, sau đó dùng mã đó truy vấn trạng thái. Bước thứ hai **phụ thuộc kết quả** của bước thứ nhất và bản thân cũng trả về future.

Nếu dùng `thenApply`:

~~~~java
CompletableFuture<CompletableFuture<String>> nested =
        loadAccountIdAsync()
                .thenApply(id -> loadStatusAsync(id));
~~~~

Kết quả trở thành `CompletableFuture<CompletableFuture<String>>`: một future chứa future khác. Đây thường không phải điều caller muốn.

Hãy dùng `thenCompose`:

~~~~java
CompletableFuture<String> status =
        loadAccountIdAsync()
                .thenCompose(id -> loadStatusAsync(id));
~~~~

`thenCompose` **làm phẳng** hai bước nối tiếp: khi stage đầu trả ID, nó gọi hàm tạo stage thứ hai, rồi stage mới phụ thuộc vào kết quả của stage thứ hai. Đây là cách diễn đạt bất đồng bộ tương tự phép `flatMap` trên một cấu trúc giá trị.

Đoạn dưới đây là chương trình **hoàn chỉnh**, lưu thành `ComposeDemo.java`:

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class ComposeDemo {
    static CompletionStage<String> loadAccountIdAsync() {
        return CompletableFuture.completedStage("A-100");
    }

    static CompletionStage<String> loadStatusAsync(String id) {
        return CompletableFuture.completedStage("active:" + id);
    }

    static CompletionStage<String> loadAccountStatusAsync() {
        return loadAccountIdAsync()
                .thenCompose(ComposeDemo::loadStatusAsync);
    }

    public static void main(String[] args) {
        System.out.println(
                loadAccountStatusAsync().toCompletableFuture().join());
        // active:A-100
    }
}
~~~~

**Lưu ý:** các stage trong ví dụ đã hoàn tất sẵn để minh họa kiểu trả về. `thenCompose` không tự tạo thêm thread hay khiến một lời gọi đồng bộ trở thành bất đồng bộ. Với ứng dụng thực, `loadAccountIdAsync` và `loadStatusAsync` thường nhận kết quả từ I/O async hoặc công việc đã được lập lịch qua executor.

### 5.1. `thenApply` so với `thenCompose`

| Hàm ở bước sau | Phương thức đúng | Kiểu kết quả |
| --- | --- | --- |
| `String -> Integer` | `thenApply` | `CompletionStage<Integer>` |
| `String -> CompletionStage<Integer>` | `thenCompose` | `CompletionStage<Integer>` |
| `String -> void` | `thenAccept` | `CompletionStage<Void>` |
| `() -> void`, không cần input cũ | `thenRun` | `CompletionStage<Void>` |

Đừng dùng `join()` bên trong `thenApply` để “làm phẳng” một future nếu có thể dùng `thenCompose`: điều đó dễ tạo blocking không cần thiết và có thể gây deadlock/starvation khi dùng executor nhỏ.

## 6. Kết hợp hai công việc độc lập: `thenCombine`

Nếu hai tác vụ **không phụ thuộc nhau**, hãy khởi động chúng độc lập rồi kết hợp kết quả khi cả hai hoàn thành. Không cần đợi tác vụ A xong mới bắt đầu tác vụ B.

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> customer =
        CompletableFuture.supplyAsync(() -> "Lan");

CompletableFuture<Integer> availableItems =
        CompletableFuture.supplyAsync(() -> 8);

CompletableFuture<String> summary =
        customer.thenCombine(
                availableItems,
                (name, count) -> name + " có " + count + " sản phẩm");

System.out.println(summary.join()); // Lan có 8 sản phẩm
~~~~

`thenCombine` nhận kết quả của hai stage và gọi `BiFunction<T,U,V>` một khi **cả hai hoàn thành bình thường**. Đây là phép kết hợp **fan-in**. Những công việc độc lập có thể chạy đồng thời, nhưng thời gian và mức song song thực tế phụ thuộc executor và trạng thái của hệ thống.

### 6.1. Sơ đồ phụ thuộc

~~~~text
        loadCustomerAsync()       loadInventoryAsync()
                 \                  /
                  \                /
                   thenCombine(...)
                         |
                  buildSummary
                         |
                 CompletableFuture<Summary>
~~~~

**Sai lầm thường gặp:** viết:

~~~~java
CompletableFuture<String> sequential =
        loadCustomerAsync()
                .thenCompose(customer ->
                        loadInventoryAsync()
                                .thenApply(inventory ->
                                        customer + inventory));
~~~~

Trong biểu thức trên, `loadInventoryAsync()` chỉ được gọi sau khi customer hoàn tất, nên hai tác vụ **không còn được khởi động độc lập**. Nếu không có phụ thuộc dữ liệu, hãy khởi chạy cả hai trước và dùng `thenCombine`.

### 6.2. Các phương thức kết hợp khác

| API | Mục đích |
| --- | --- |
| `thenCombine(other, fn)` | Chờ hai kết quả và tạo giá trị mới |
| `thenAcceptBoth(other, action)` | Chờ hai kết quả và thực hiện một hành động, trả stage `Void` |
| `runAfterBoth(other, action)` | Chờ cả hai nhưng không cần đọc giá trị |
| `applyToEither(other, fn)` | Khi **một trong hai hoàn thành bình thường**, dùng giá trị của nó để tính kết quả |
| `acceptEither(other, action)` | Khi một trong hai hoàn thành bình thường, chạy Consumer |
| `runAfterEither(other, action)` | Chạy Runnable khi một trong hai stage hoàn tất bình thường |

Các nhóm `either` không nên được xem là cơ chế “race hai tác vụ rồi tự động hủy tác vụ thua”. Việc hủy hoặc ngừng side effect của các nhánh còn lại phải được thiết kế riêng.

Nếu một nhánh thất bại còn nhánh kia thành công, hợp đồng các stage kiểu `either` không bảo đảm rằng kết quả nhất định lấy nhánh thành công trong mọi cuộc đua; cần đọc rõ quy tắc exception của `CompletionStage`. Nếu yêu cầu **first successful result** với chính sách cụ thể cho các thất bại, hãy thiết kế thuật toán và quy tắc hoàn tất rõ ràng thay vì suy diễn từ tên phương thức.

## 7. Đợi nhiều futures: `allOf` và `anyOf`

### 7.1. `allOf`: tất cả đã hoàn thành

`CompletableFuture.allOf(...)` tạo một `CompletableFuture<Void>` hoàn tất khi **tất cả các future đầu vào hoàn tất**. Nó không tự kết hợp giá trị đầu ra thành `List<T>`.

~~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

public class AllOfDemo {
    public static void main(String[] args) {
        CompletableFuture<String> a =
                CompletableFuture.supplyAsync(() -> "A");
        CompletableFuture<String> b =
                CompletableFuture.supplyAsync(() -> "B");
        CompletableFuture<String> c =
                CompletableFuture.supplyAsync(() -> "C");

        CompletableFuture<List<String>> combined =
                CompletableFuture.allOf(a, b, c)
                        .thenApply(ignored ->
                                List.of(a.join(), b.join(), c.join()));

        System.out.println(combined.join()); // [A, B, C]
    }
}
~~~~

Vì `thenApply` chỉ chạy khi `allOf` hoàn thành bình thường, các lời gọi `join()` trên các future đã thành công sẽ không phải đợi thêm trong trường hợp này. **Thứ tự list đầu ra do code định nghĩa** (a, b, c), không phụ thuộc thứ tự các tác vụ hoàn tất.

Nếu một hoặc nhiều input hoàn thành ngoại lệ, kết quả `allOf` hoàn thành ngoại lệ; nếu có nhiều lỗi, **không có bảo đảm chọn lỗi nào để báo trước**. `allOf` không phải một collector tự tập hợp tất cả nguyên nhân thất bại; nếu cần danh sách lỗi đầy đủ, hãy biến đổi kết quả từng task thành một kiểu báo trạng thái rồi thu thập theo chính sách riêng.

### 7.2. `allOf` với danh sách có số lượng động

~~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

static CompletableFuture<List<String>> combine(
        List<CompletableFuture<String>> futures) {

    CompletableFuture<?>[] array =
            futures.toArray(new CompletableFuture<?>[0]);

    return CompletableFuture.allOf(array)
            .thenApply(ignored -> futures.stream()
                    .map(CompletableFuture::join)
                    .toList());
}
~~~~

Đoạn này giả định danh sách `futures` không chứa null và **không bị sửa trong khi xử lý**. Trong API thực tế, có thể chụp cấu trúc bằng `List.copyOf(futures)` để tránh thay đổi số phần tử sau khi đã tạo mảng. Đây là **ví dụ method cần đặt trong class**, không phải chương trình độc lập.

Với đầu vào rỗng, `allOf()` **hoàn thành bình thường ngay**, còn đoạn `combine` phía trên trả danh sách rỗng.

### 7.3. `anyOf`: kết quả đầu tiên hoàn thành, kể cả lỗi

`CompletableFuture.anyOf(a, b, ...)` tạo một `CompletableFuture<Object>` nhận kết quả hoặc ngoại lệ của **một future hoàn thành đầu tiên**.

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> first =
        CompletableFuture.completedFuture("cached");

CompletableFuture<String> second =
        CompletableFuture.supplyAsync(() -> "remote");

Object winner = CompletableFuture.anyOf(first, second).join();
System.out.println(winner); // cached
~~~~

Trong ví dụ, `first` đã hoàn tất trước khi gọi `anyOf`. Với hai tác vụ chạy thật, **không dự đoán trước** nhánh nào sẽ thắng.

Phân biệt:

| Đặc tính | `allOf` | `anyOf` |
| --- | --- | --- |
| Điều kiện hoàn thành | Tất cả input hoàn tất | Một input hoàn tất |
| Kiểu trả về | `CompletableFuture<Void>` | `CompletableFuture<Object>` |
| Lấy dữ liệu từng input | Phải đọc từng future riêng | Nhận giá trị của future thắng |
| Nếu có lỗi | Kết quả có thể hoàn thành ngoại lệ | Lỗi có thể là kết quả đầu tiên |
| Tự dừng tác vụ còn lại? | Không | Không |
| Danh sách rỗng | Hoàn thành ngay | Kết quả **không hoàn thành** |

Đặc biệt, `anyOf()` **không có input** trả về một future incomplete. Không gọi `join()` trên đó nếu hệ thống không có cách hoàn tất nó, vì có thể chờ vô hạn. Nếu API cho phép danh sách rỗng, hãy xử lý trường hợp rỗng ngay ở ranh giới nghiệp vụ.

## 8. Lỗi là một nhánh kết quả: `exceptionally`, `handle`, `whenComplete`

Trong hệ bất đồng bộ, một exception không nhất thiết xuất hiện tại thời điểm **tạo** future. Nó có thể xảy ra trên một worker thread, hoàn tất future dưới dạng exception và tiếp tục lan truyền qua các stage phụ thuộc.

### 8.1. `exceptionally`: dùng giá trị thay thế khi có lỗi

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> result =
        CompletableFuture.<String>failedFuture(
                new IllegalStateException("Backend unavailable"))
        .exceptionally(error -> "temporary-unavailable");

System.out.println(result.join()); // temporary-unavailable
~~~~

`exceptionally` chỉ chạy khi stage trước hoàn thành ngoại lệ, rồi tạo **giá trị thay thế cùng kiểu `T`**. Nếu stage trước thành công, callback không chạy và giá trị bình thường được giữ.

Không nên trả một giá trị “thành công giả” nếu downstream không thể phân biệt sự cố. Ví dụ, trong dịch vụ thanh toán, thay exception bằng `"PAID"` sẽ khiến hệ thống hiểu sai trạng thái. Hãy chọn một fallback có ngữ nghĩa rõ, hoặc dùng kiểu kết quả phân biệt thành công/thất bại.

### 8.2. `handle`: quan sát cả thành công lẫn thất bại và tạo giá trị mới

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> status =
        CompletableFuture.supplyAsync(() -> 100 / 2)
                .handle((value, error) ->
                        error == null
                                ? "OK:" + value
                                : "FAILED:" + error.getClass().getSimpleName());

System.out.println(status.join()); // OK:50
~~~~

`handle(BiFunction<T,Throwable,U>)` **luôn** được gọi khi stage trước hoàn tất, với `error == null` trong đường thành công hoặc `error != null` trong đường thất bại. `value` có thể là null ngay cả khi thành công nếu kết quả hợp lệ là null; vì thế **không dùng `value == null` để phân biệt lỗi**.

`handle` có thể đổi kiểu kết quả. Trong ví dụ, `T=Integer` và `U=String`.

### 8.3. `whenComplete`: quan sát mà không đổi kết quả

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> value =
        CompletableFuture.completedFuture(42)
                .whenComplete((result, error) -> {
                    if (error == null) {
                        System.out.println("Completed: " + result);
                    } else {
                        System.out.println("Failed");
                    }
                });

System.out.println(value.join()); // 42
~~~~

`whenComplete` phù hợp để **ghi metrics hoặc quan sát**. Nó giữ kết quả hoặc exception từ stage nguồn khi callback hoàn thành bình thường. Nếu callback tự ném exception mà nguồn thành công, stage phụ thuộc sẽ thất bại vì exception của callback. Nếu nguồn đã thất bại và callback cũng thất bại, lỗi từ nguồn được ưu tiên theo hợp đồng.

**Không dùng `whenComplete` để recovery bằng cách `return` một giá trị:** callback của nó là `BiConsumer`, không phải hàm tạo giá trị. Dùng `exceptionally` hoặc `handle` khi muốn thay đổi kết quả.

### 8.4. So sánh ngắn

| API | Khi nào callback chạy? | Có tạo kết quả mới không? | Mục đích |
| --- | --- | --- | --- |
| `thenApply(fn)` | Thành công | Có | Biến đổi kết quả |
| `exceptionally(fn)` | Thất bại | Có, cùng kiểu | Recovery đồng bộ |
| `handle(fn)` | Thành công **hoặc** thất bại | Có, có thể đổi kiểu | Phân nhánh kết quả |
| `whenComplete(action)` | Thành công **hoặc** thất bại | Không chủ đích đổi giá trị | Logging/metrics/cleanup nhẹ |
| `exceptionallyCompose(fn)` | Thất bại | Dùng **CompletionStage<T>** do fn tạo | Recovery bất đồng bộ |

### 8.5. `exceptionallyCompose`: fallback cũng là tác vụ async

Một đường khắc phục có thể cần gọi dịch vụ dự phòng, tức là trả **một stage khác**:

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

static CompletionStage<String> primaryAsync() {
    return CompletableFuture.failedFuture(
            new IllegalStateException("Primary failed"));
}

static CompletionStage<String> fallbackAsync() {
    return CompletableFuture.completedStage("secondary-response");
}

static CompletionStage<String> loadWithFallback() {
    return primaryAsync()
            .exceptionallyCompose(error -> fallbackAsync());
}
~~~~

`exceptionallyCompose` là phương án rõ ràng hơn `exceptionally` khi fallback **tự trả future**. Đoạn trên là các phương thức minh họa để đặt trong class; với bài toán thật, không nên tự retry vô hạn. Cần policy cụ thể về loại lỗi nào được retry, số lần thử, timeout và tính idempotency của thao tác.

### 8.6. Tránh xử lý lỗi quá rộng

Một pipeline có thể thất bại vì lỗi nghiệp vụ, lỗi dữ liệu, timeout, bị hủy hoặc bug lập trình. Không nên gộp mọi `Throwable` thành một giá trị mặc định mà không phân biệt:

~~~~java
// Phản ví dụ nếu đây là API phải báo lỗi thanh toán chính xác:
future.exceptionally(error -> new PaymentResult("SUCCESS"));
~~~~

Đối với hệ cần báo cáo nhất quán, có thể dùng một sealed interface/record kết quả:

~~~~java
sealed interface LookupOutcome permits Found, Unavailable {
}

record Found(String value) implements LookupOutcome {
}

record Unavailable(String reason) implements LookupOutcome {
}
~~~~

`CompletableFuture<LookupOutcome>` khi đó thể hiện kết quả **nghiệp vụ**, trong khi exceptional completion đại diện cho lỗi tính toán/hạ tầng hoặc những trạng thái không thể cung cấp kết quả bình thường. Quyết định cách ánh xạ lỗi vào outcome cần được công bố trong hợp đồng của API.

## 9. Lấy kết quả: `join()`, `get()`, `getNow()`

Các phương thức lấy kết quả có chính sách blocking và exception khác nhau. Chọn chúng theo **ranh giới đồng bộ** của chương trình.

| API | Có thể chờ? | Ngoại lệ chính khi thất bại | Ghi chú |
| --- | --- | --- | --- |
| `join()` | Có | `CompletionException` (unchecked), hoặc `CancellationException` | Tiện ở điểm cuối pipeline |
| `get()` | Có | `ExecutionException`, `InterruptedException` (checked), hoặc `CancellationException` | Theo hợp đồng `Future` |
| `get(timeout, unit)` | Có, tối đa thời gian chờ | Thêm `TimeoutException` (checked) | Timeout **chờ** của caller |
| `getNow(valueIfAbsent)` | Không | `CompletionException`/`CancellationException` nếu đã thất bại | Trả fallback khi chưa hoàn tất, không tự hoàn tất future |
| `isDone()` | Không | Không | Chỉ báo đã hoàn tất (bất kỳ cách nào) |
| `isCompletedExceptionally()` | Không | Không | Kiểm tra đã hoàn tất bất thường |
| `isCancelled()` | Không | Không | Kiểm tra đã bị hủy theo trạng thái future |

### 9.1. `join` so với `get`

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

CompletableFuture<String> failed =
        CompletableFuture.failedFuture(
                new IllegalArgumentException("Invalid ID"));

try {
    failed.join();
} catch (CompletionException exception) {
    System.out.println(exception.getCause().getMessage());
    // Invalid ID
}

try {
    failed.get();
} catch (ExecutionException exception) {
    System.out.println(exception.getCause().getMessage());
    // Invalid ID
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
}
~~~~

`get()` là API có thể bị interrupt theo hợp đồng `Future`, do đó caller phải xử lý `InterruptedException`. Với `join()`, caller không phải khai báo checked exception; khi công việc thất bại, thường nhận `CompletionException` với cause gốc, trừ các trường hợp như cancellation.

Đối với API đang chạy trong luồng có chính sách interrupt, không nên chuyển toàn bộ `get()` thành `join()` chỉ để tránh xử lý checked exception. Cần cân nhắc nơi có thể chờ và cách phản hồi tín hiệu hủy.

### 9.2. `getNow` không phải thao tác kích hoạt phép tính

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> pending = new CompletableFuture<>();

System.out.println(pending.getNow("not-ready")); // not-ready
System.out.println(pending.isDone());             // false

pending.complete("ready");
System.out.println(pending.getNow("not-ready")); // ready
~~~~

`getNow` không chờ và **không đổi trạng thái** của future. Nếu stage hoàn tất bất thường, nó vẫn ném exception tương ứng thay vì trả giá trị fallback. Vì một kết quả hợp lệ có thể là null, đừng suy luận future chưa hoàn thành chỉ bằng cách kiểm tra `getNow(null) == null`.

### 9.3. Đặt điểm blocking ở ranh giới rõ ràng

Trong một service trả `CompletionStage<T>`, hãy để client quyết định khi nào đợi hoặc đăng ký callback:

~~~~java
CompletionStage<String> stage = loadStatusAsync();

// Không chặn tại thời điểm tạo:
CompletionStage<String> upper = stage.thenApply(String::toUpperCase);

// Chỉ dùng join nếu đây thực sự là ranh giới cần kết quả đồng bộ:
String result = upper.toCompletableFuture().join();
~~~~

Không chèn `join()` giữa các bước của pipeline chỉ để đọc trung gian nếu có thể dùng `thenApply`, `thenCompose` hoặc `thenCombine`. Các lệnh blocking nằm trên executor có số worker nhỏ có thể khiến công việc cần thiết để hoàn tất future bị đói luồng (*thread starvation*), thậm chí deadlock.

## 10. Timeout: giới hạn thời gian chờ không đồng nghĩa dừng tác vụ

Một cuộc gọi từ xa có thể treo hoặc trả kết quả quá muộn. `CompletableFuture` cung cấp những phương thức xử lý giới hạn thời gian, nhưng cần phân biệt **trạng thái của future** và **công việc đang chạy**.

### 10.1. `orTimeout`: hoàn thành ngoại lệ khi quá hạn

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

CompletableFuture<String> stage =
        CompletableFuture.supplyAsync(() -> "OK");

stage.orTimeout(2, TimeUnit.SECONDS);
System.out.println(stage.join()); // OK nếu hoàn thành trước 2 giây
~~~~

Nếu stage chưa hoàn tất trong thời hạn, `orTimeout` hoàn thành nó **ngoại lệ với `TimeoutException`**. Hàm trả **chính future đó** (`this`), chứ không tạo stage độc lập.

Vì vậy:

~~~~java
CompletableFuture<String> raw = new CompletableFuture<>();
CompletableFuture<String> limited =
        raw.orTimeout(1, TimeUnit.SECONDS);

System.out.println(raw == limited); // true
~~~~

Điều này đặc biệt quan trọng nếu `raw` được chia sẻ cho nhiều client: gắn `orTimeout` lên nó có thể thay đổi **trạng thái chung** và ảnh hưởng tất cả các client đang phụ thuộc.

### 10.2. `completeOnTimeout`: trả giá trị dự phòng

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

CompletableFuture<String> cachedValue = new CompletableFuture<>();

cachedValue.completeOnTimeout(
        "temporarily-unavailable",
        100, TimeUnit.MILLISECONDS);

System.out.println(cachedValue.join());
// temporarily-unavailable nếu không ai hoàn tất trước hạn
~~~~

`completeOnTimeout(value, timeout, unit)` hoàn thành future bình thường với **giá trị được cung cấp** khi hết hạn; nó cũng **trả chính future đó**. Một service có thể dùng phương pháp này nếu giá trị dự phòng là một **kết quả nghiệp vụ được phép**.

Không dùng fallback kiểu “đã thanh toán” hoặc “đã ghi dữ liệu” khi công việc thật chưa hoàn tất. Cần phân biệt **kết quả thành công thực sự** với **dữ liệu dự phòng**; có thể dùng kiểu kết quả riêng, ví dụ `CacheHit` hoặc `Unavailable`.

### 10.3. Timeout khi đợi: `get(timeout, unit)`

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.ExecutionException;

CompletableFuture<String> pending = new CompletableFuture<>();

try {
    pending.get(50, TimeUnit.MILLISECONDS);
} catch (TimeoutException exception) {
    System.out.println("Caller stopped waiting");
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
} catch (ExecutionException exception) {
    System.out.println("Task failed");
}

System.out.println(pending.isDone()); // false
~~~~

`get(timeout, unit)` **chỉ giới hạn thời gian chờ của lời gọi `get`**. Khi nó ném `TimeoutException`, future nguồn có thể vẫn chưa hoàn tất và vẫn được xử lý bởi nơi sản sinh kết quả.

So sánh:

| API | Khi hết hạn | Future nguồn bị thay đổi? |
| --- | --- | --- |
| `get(timeout, unit)` | Caller nhận `TimeoutException` | **Không** do chính việc chờ hết hạn |
| `orTimeout(timeout, unit)` | Future hoàn tất **ngoại lệ** | **Có**, ngay trên future được gọi |
| `completeOnTimeout(value, timeout, unit)` | Future hoàn tất **bình thường** bằng fallback | **Có**, ngay trên future được gọi |

### 10.4. Timeout không tự interrupt công việc nền

`orTimeout`, `completeOnTimeout` và `get(timeout)` không cung cấp lời hứa rằng phép tính, câu truy vấn database hoặc HTTP request đang chạy đã bị dừng. Tác vụ có thể tiếp tục giữ tài nguyên hoặc gây side effect dù bên gọi đã nhận kết quả timeout.

Vì vậy:

- Cấu hình **connect/read/request timeout** ngay tại thư viện I/O hoặc client.
- Dùng phương tiện **cancellation** riêng của client hoặc task nếu nó hỗ trợ.
- Giới hạn số tác vụ đang chạy hoặc số request đồng thời.
- Thiết kế ghi dữ liệu ngoài theo tính **idempotent** khi có retry.
- Không để việc hoàn thành future với timeout thay thế việc đóng tài nguyên hoặc ngăn công việc không cần thiết.

Nếu muốn giới hạn thời gian chờ của **một nhánh người gọi** mà không đổi trạng thái future nguồn, cân nhắc tạo **dependent stage riêng** rồi áp dụng timeout lên nhánh ấy, hoặc dùng API `get(timeout)` tại điểm chờ:

~~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> view = source.copy();

view.orTimeout(1, TimeUnit.SECONDS);
// Timeout thay đổi view; không trực tiếp hoàn tất source.
~~~~

`copy()` trả một future phụ thuộc phản ánh kết quả của nguồn, nhưng không tạo một computation mới. Sau khi `view` bị timeout, việc `source` hoàn thành sau đó không tự làm `view` trở lại thành công. Và **tác vụ của source vẫn có thể tiếp tục chạy**.

## 11. Cancellation: hủy future khác với hủy công việc

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` cố hoàn tất future bằng `CancellationException` nếu nó chưa hoàn tất. Hợp đồng `CompletableFuture` cho biết đối số `mayInterruptIfRunning` **không có tác dụng thực tế** ở đây: lớp future không trực tiếp điều khiển phép tính nền, nên việc cancel **không dùng interrupt để bảo đảm dừng computation**.

~~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> pending = new CompletableFuture<>();

boolean cancelled = pending.cancel(true);
System.out.println(cancelled);         // true
System.out.println(pending.isCancelled()); // true

try {
    pending.join();
} catch (CancellationException exception) {
    System.out.println("Cancelled");
}
~~~~

Các dependent futures chưa hoàn tất có thể hoàn thành ngoại lệ với `CompletionException` có cause là `CancellationException`. Cancellation không được tự động lan truyền như một tín hiệu ngắt công việc ở toàn bộ chuỗi nguồn–phụ thuộc.

### 11.1. Cancellation hợp tác (*cooperative cancellation*)

Với tác vụ do mình điều khiển, hệ thống có thể có một đối tượng cancellation token hoặc cách yêu cầu task dừng theo cơ chế executor/client cụ thể. Ví dụ, mã chạy trên một thread có thể kiểm tra `Thread.currentThread().isInterrupted()` hoặc chấp hành `InterruptedException` từ API blocking.

~~~~java
static String performInterruptibleWork() {
    try {
        Thread.sleep(200);
        return "done";
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Work interrupted", exception);
    }
}
~~~~

Đây là ví dụ về **một tác vụ hợp tác với interrupt**, không phải minh họa rằng `CompletableFuture.cancel(true)` sẽ interrupt thread chạy `supplyAsync`. Nếu cần hủy thật sự, hãy thiết kế đường kết nối giữa cancellation của caller và tác vụ do executor hoặc client sở hữu.

### 11.2. Không nhầm “đã bỏ chờ” với “đã rollback”

Một giao dịch chuyển tiền có thể đã gửi request đến máy chủ trước khi caller timeout. Nếu không nhận được phản hồi, trạng thái thực có thể là “chưa biết”, chứ không nhất thiết là “thất bại” hoặc “đã hủy”.

Những hệ thống có tác dụng phụ cần cơ chế xác định trạng thái thực như idempotency key, truy vấn lại trạng thái, transaction ID hoặc workflow chuyên biệt. `CompletableFuture` chỉ phản ánh kết quả một lời hứa tính toán trong JVM, không tự cung cấp giao dịch phân tán.

## 12. Executor, virtual threads và lựa chọn mô hình thực thi trong Java 27

CompletableFuture mô tả **phụ thuộc kết quả**. Executor mô tả **nơi một công việc được lên lịch để chạy**. Hai khái niệm không nên bị đồng nhất.

| Tình huống | Lựa chọn phù hợp để cân nhắc | Điều phải kiểm soát |
| --- | --- | --- |
| Tính toán CPU-bound độc lập | Pool có số worker phù hợp với CPU | Mức song song và tải CPU |
| I/O blocking có nhiều yêu cầu | `Executors.newVirtualThreadPerTaskExecutor()` | Số request đồng thời đến dịch vụ, timeout, tài nguyên |
| Bước biến đổi rất nhanh sau khi hoàn tất | `thenApply` | Callback có thể chạy trên thread hoàn tất stage |
| Continuation có thể chặn hoặc cần cách ly khỏi thread hoàn tất | `thenApplyAsync(..., executor)` | Executor phải còn sống và có chính sách tải phù hợp |
| Kết nối thực sự bất đồng bộ từ thư viện client | CompletionStage do client tạo | Không bọc thêm `supplyAsync` nếu không cần |
| Công việc con có vòng đời gắn chặt với request | Thiết kế vòng đời rõ, hủy và thu dọn | Không để task chạy trôi sau khi request kết thúc |

### 12.1. Virtual threads là tính năng ổn định

Virtual threads chính thức từ Java 21 và có mặt trong Java 27. Có thể tạo executor cho **mỗi task một virtual thread**:

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class VirtualThreadFutureDemo {
    public static void main(String[] args) {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            CompletableFuture<String> a =
                    CompletableFuture.supplyAsync(
                            () -> "first:" + Thread.currentThread().isVirtual(),
                            executor);

            CompletableFuture<String> b =
                    CompletableFuture.supplyAsync(
                            () -> "second:" + Thread.currentThread().isVirtual(),
                            executor);

            System.out.println(a.thenCombine(b,
                    (left, right) -> left + ", " + right).join());
            // first:true, second:true
        }
    }
}
~~~~

Không cần flag preview cho `Executors.newVirtualThreadPerTaskExecutor()`. Khác với một thread pool cố định, executor này có thể tạo **rất nhiều virtual thread**; số task đang tác động đến database hoặc HTTP service vẫn cần giới hạn.

Virtual threads giúp code blocking theo phong cách tuần tự mở rộng tốt hơn ở nhiều bài toán I/O, nhưng không làm công việc CPU-heavy sử dụng ít CPU hơn, không làm các cuộc gọi ra dịch vụ ngoài nhanh lên, và không tự biến mọi API I/O thành nonblocking.

### 12.2. Giới hạn concurrency ngay cả khi dùng virtual threads

Ví dụ một hệ thống chỉ cho phép tối đa năm tác vụ cùng gọi dịch vụ ngoài:

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.Semaphore;
import java.util.function.Supplier;

static <T> CompletableFuture<T> limitedAsync(
        Supplier<T> operation,
        Executor executor,
        Semaphore permits) {

    return CompletableFuture.supplyAsync(() -> {
        try {
            permits.acquire();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CompletionException(exception);
        }

        try {
            return operation.get();
        } finally {
            permits.release();
        }
    }, executor);
}
~~~~

Đây là method minh họa đặt trong class. `permits` phải là **một Semaphore dùng chung cho những cuộc gọi cần cùng giới hạn**, ví dụ `new Semaphore(5)`. Nhờ đó, tối đa năm lời gọi `operation.get()` có thể chạy đồng thời qua adapter này.

**Giới hạn quan trọng:** Semaphore ở đây giới hạn **số tác vụ đã vào vùng gọi**, không giới hạn tổng số future/task được tạo hoặc đang chờ permit. Với tải cực lớn, ứng dụng còn cần **hạn chế số lượng request nhận vào**, hàng đợi có giới hạn, rate limiting hoặc backpressure ở tầng hệ thống.

### 12.3. Không lẫn `CompletionStage` với structured concurrency preview

Java SE 27 còn có `StructuredTaskScope` ở **trạng thái preview**, nghĩa là chỉ dùng được khi bật preview features và API vẫn có thể tiếp tục thay đổi. Vì phạm vi bài này yêu cầu **chỉ dùng kiến thức ổn định, hiện hành và không dựa vào preview**, các ví dụ **không sử dụng `StructuredTaskScope`**.

Điều này không làm `CompletableFuture` trở nên lỗi thời: nó vẫn là API chính thức cho kết quả hoàn thành sau và phối hợp các stage. Khi thiết kế một tác vụ cha cần kiểm soát toàn bộ vòng đời các tác vụ con, phải đánh giá công cụ và yêu cầu phiên bản của ứng dụng riêng thay vì tự cho rằng CompletableFuture tự cung cấp cấu trúc vòng đời như một scope.

## 13. Thiết kế API bất đồng bộ an toàn

### 13.1. Trả `CompletionStage<T>` thay vì mở quyền `complete` khi không cần

Một interface có thể công bố **hợp đồng xử lý tiếp** chứ không cho caller chủ động quyết định trạng thái kết quả:

~~~~java
import java.util.concurrent.CompletionStage;

interface AccountService {
    CompletionStage<AccountView> loadAccount(String accountId);
}

record AccountView(String accountId, String ownerName) {
}
~~~~

Điều này làm rõ rằng bên gọi có thể đăng ký `thenApply`, `handle` hoặc chuyển sang `toCompletableFuture()` khi cần, còn implementation giữ quyền quản lý quá trình thực thi. Tuy nhiên, chỉ đổi **kiểu tĩnh** của biến không phải cơ chế khóa toàn bộ khả năng can thiệp.

### 13.2. `minimalCompletionStage` và `copy`

Nếu đã có một `CompletableFuture<T>` nội bộ:

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

CompletableFuture<String> internal = new CompletableFuture<>();

CompletionStage<String> publicStage =
        internal.minimalCompletionStage();

CompletableFuture<String> dependentCopy =
        internal.copy();
~~~~

| Phương thức | Ý định | Hệ quả |
| --- | --- | --- |
| `minimalCompletionStage()` | Công bố bề mặt `CompletionStage` tối thiểu | Một số thao tác `CompletableFuture` ngoài giao diện không được hỗ trợ trên đối tượng minimal |
| `copy()` | Tạo future phụ thuộc phản ánh kết quả cuối, không cho caller `complete` trực tiếp **future gốc** | Caller có thể hoàn tất/cancel **bản sao**, không phải source |
| Chỉ trả `CompletionStage<T>` theo chữ ký | Hạn chế API nhìn thấy ở thời gian biên dịch | Không tự bảo đảm implementation bên dưới không bị truy cập khác |

`copy()` không tạo **bản sao sâu của giá trị `T`**. Nếu `T` là một `List` mutable, bên nhận vẫn có thể thay đổi các phần tử qua alias nếu ứng dụng không defensive copy.

**Lưu ý:** `CompletionStage.toCompletableFuture()` là một phần của hợp đồng. Khi thiết kế ranh giới giữa các bên tin cậy khác nhau, phải thực thi quyền tại tầng nghiệp vụ/dữ liệu, không xem “chỉ trả CompletionStage” là sandbox.

### 13.3. Giá trị kết quả có thể là null

`CompletableFuture.completedFuture(null)` hợp lệ. Đối với stage thông thường, `null` có thể là kết quả hoàn thành bình thường; do đó:

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> absent =
        CompletableFuture.completedFuture(null);

System.out.println(absent.isCompletedExceptionally()); // false
System.out.println(absent.join() == null);             // true
~~~~

Không suy luận “`null` nghĩa là exception” hay “chưa hoàn tất”. Nếu domain cần phân biệt **không tìm thấy**, **hợp lệ nhưng rỗng** và **lỗi**, hãy dùng `Optional<T>` hoặc kiểu kết quả miền với ý nghĩa rõ, rồi giữ exceptional completion cho những lỗi được định nghĩa.

### 13.4. Chia sẻ dữ liệu và memory visibility

Theo hợp đồng `CompletionStage`, những hành động trước khi gửi một computation được sắp xếp trước (*happen-before*) computation đó, và những hành động của một stage xảy ra trước những hành động trong dependent stage sau khi stage hoàn tất.

Tuy nhiên, điều này **không biến tất cả object được chia sẻ thành thread-safe**. Nếu stage trả một `ArrayList` mutable rồi nhiều continuation cùng sửa nó, vẫn có thể có data race.

~~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

CompletableFuture<List<String>> names =
        CompletableFuture.supplyAsync(() -> {
            List<String> result = new ArrayList<>();
            result.add("An");
            result.add("Binh");
            return List.copyOf(result);
        });

// Hai continuation chỉ đọc một snapshot không sửa được.
CompletableFuture<Integer> count = names.thenApply(List::size);
CompletableFuture<String> first = names.thenApply(List::getFirst);
~~~~

Trong ví dụ, `List.copyOf` bảo vệ **cấu trúc list** khỏi các lời gọi thêm/xóa/thay thế sau đó; các phần tử là `String` bất biến nên phù hợp để chia sẻ. Nếu phần tử là object mutable, cần thêm chính sách về aliasing và defensive copy.

### 13.5. Context và `ThreadLocal`

Vì continuation có thể chạy trên thread khác và `*Async` có thể chuyển sang executor khác, **không giả định một `ThreadLocal` ở thread tạo future sẽ tự xuất hiện trong mọi callback**. Bên cạnh đó, việc tái sử dụng worker thread có thể làm dữ liệu request cũ bị rò nếu không xóa context đúng cách.

Với những thông tin như correlation ID, tenant ID hoặc ID người dùng, hãy truyền **tường minh** qua tham số hoặc đối tượng context bất biến, hoặc dùng cơ chế context propagation đã được hệ thống lựa chọn và kiểm thử. Không dựa vào ngẫu nhiên thread scheduling để duy trì phân quyền.

## 14. Ví dụ tổng hợp: dựng kết quả tổng quan từ hai dịch vụ

Giả sử một trang quản trị cần hiển thị:

- Hồ sơ khách hàng: `Profile`.
- Tồn kho một sản phẩm: `Availability`.
- Kết quả tổng hợp: `Dashboard`.

Hai nguồn độc lập, nên khởi động chúng đồng thời; sau đó ghép kết quả, thiết lập giới hạn thời gian cho **kết quả phía caller**, và chỉ blocking ở ranh giới ứng dụng console.

Đoạn sau là chương trình đầy đủ có thể lưu thành `DashboardAsyncDemo.java`:

~~~~java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

record Profile(String customerId, String displayName) {
}

record Availability(String sku, int remaining) {
}

record Dashboard(Profile profile, Availability availability) {
}

public class DashboardAsyncDemo {
    private static void simulateBlockingIo() {
        try {
            Thread.sleep(30);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CompletionException(exception);
        }
    }

    private static Profile fetchProfile(String customerId) {
        simulateBlockingIo();
        return new Profile(customerId, "Nguyen An");
    }

    private static Availability fetchAvailability(String sku) {
        simulateBlockingIo();
        return new Availability(sku, 12);
    }

    static CompletionStage<Dashboard> loadDashboard(
            String customerId,
            String sku,
            Executor executor) {

        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(executor, "executor");

        if (customerId.isBlank() || sku.isBlank()) {
            return CompletableFuture.failedStage(
                    new IllegalArgumentException("IDs must not be blank"));
        }

        CompletableFuture<Profile> profile =
                CompletableFuture.supplyAsync(
                        () -> fetchProfile(customerId), executor);

        CompletableFuture<Availability> availability =
                CompletableFuture.supplyAsync(
                        () -> fetchAvailability(sku), executor);

        return profile.thenCombine(availability, Dashboard::new);
    }

    public static void main(String[] args) {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            // Chỉ phiên bản của client này có giới hạn 2 giây.
            CompletableFuture<Dashboard> result =
                    loadDashboard("C01", "BOOK-01", executor)
                            .toCompletableFuture()
                            .orTimeout(2, TimeUnit.SECONDS);

            Dashboard dashboard = result.join();
            System.out.println(dashboard.profile().displayName());
            // Nguyen An
            System.out.println(dashboard.availability().remaining());
            // 12
        }
    }
}
~~~~

### 14.1. Phân tích dòng xử lý

~~~~text
main()
   |
   +--> virtual-thread executor
   |
   +--> loadDashboard(C01, BOOK-01)
         |                    |
         v                    v
    fetchProfile         fetchAvailability
         |                    |
         +-----thenCombine----+
                    |
                    v
               Dashboard
                    |
                orTimeout
                    |
                  join()
                    |
                 Hiển thị
~~~~

1. Đầu vào được kiểm tra null và blank. Trường hợp blank trả stage đã hoàn tất **ngoại lệ**, phù hợp với hợp đồng bất đồng bộ.
2. Hai supplier được gửi đến executor **trước** khi `thenCombine`; chúng không phụ thuộc kết quả của nhau.
3. `thenCombine` chỉ tạo `Dashboard` khi cả hai hoàn thành bình thường.
4. Kết quả được giới hạn 2 giây bằng `orTimeout`. Trong chương trình, future này **không chia sẻ cho caller khác**, nên việc timeout làm thay đổi chính future kết quả là có chủ đích.
5. `join` chỉ xuất hiện ở ranh giới `main`, nơi chương trình console cần giá trị để in.
6. `try-with-resources` quản lý vòng đời executor; khi rời khối, executor được đóng theo hợp đồng.

Nếu một supplier thất bại, result có thể hoàn thành ngoại lệ và `join` ném `CompletionException`. Trong ứng dụng production, tầng gọi cần có chính sách map lỗi thành HTTP response, thông điệp UI hoặc kiểu kết quả nghiệp vụ. Ví dụ không làm giả rằng một backend thật sẽ luôn phản hồi sau 30 ms.

### 14.2. Nếu muốn fallback?

Ví dụ một trang thống kê cho phép hiển thị số lượng tồn kho là “chưa biết”:

~~~~java
record StockDisplay(String sku, Integer available) {
    // available == null nghĩa là chưa có dữ liệu; nên công bố rõ
    // hoặc dùng kiểu kết quả riêng thay cho null trong API thật.
}

CompletableFuture<StockDisplay> stockDisplay =
        CompletableFuture.supplyAsync(
                () -> new StockDisplay("BOOK-01", 12), executor)
        .exceptionally(error ->
                new StockDisplay("BOOK-01", null));
~~~~

Đây là đoạn minh họa đặt **trong một phương thức có biến `executor` được quản lý**. Fallback kiểu này chỉ phù hợp nếu “chưa biết” là một trạng thái chấp nhận được. Đừng dùng nó cho một quyết định **có cho phép đặt hàng hay không** nếu hệ thống yêu cầu dữ liệu tồn kho đáng tin cậy.

## 15. Kiểm thử bất đồng bộ theo trạng thái, không dựa vào giấc ngủ

Một kiểm thử dựa vào `Thread.sleep(100)` rồi đoán future phải hoàn tất rất dễ không ổn định trên máy chạy chậm hoặc CI đông tải. Nên dùng future do test **chủ động hoàn tất** để kiểm tra điều kiện chính xác.

### 15.1. Test `thenApply` và `thenCompose` không cần thread thật

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> source = new CompletableFuture<>();
CompletableFuture<Integer> transformed =
        source.thenApply(value -> value * 2);

System.out.println(transformed.isDone()); // false

source.complete(21);

System.out.println(transformed.join()); // 42
~~~~

Lợi ích:

- Không phụ thuộc scheduler.
- Không cần tạo executor chỉ để test logic.
- Kiểm tra được trạng thái trước và sau khi nguồn hoàn tất.

Tương tự, với `thenCompose`, có thể dùng hai future chưa hoàn tất riêng để xác minh stage kết quả **chỉ hoàn tất sau cả hai mốc cần thiết**:

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> first = new CompletableFuture<>();
CompletableFuture<String> second = new CompletableFuture<>();

CompletableFuture<String> composed =
        first.thenCompose(ignored -> second);

first.complete("ID");
System.out.println(composed.isDone()); // false

second.complete("READY");
System.out.println(composed.join()); // READY
~~~~

### 15.2. Test xử lý ngoại lệ

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> failed = new CompletableFuture<>();
CompletableFuture<String> recovered =
        failed.exceptionally(error -> "fallback");

failed.completeExceptionally(
        new IllegalStateException("simulated failure"));

System.out.println(recovered.join()); // fallback
~~~~

Khi cần kiểm tra exception gốc, dùng `join` và bắt `CompletionException`; với cancellation trực tiếp, bắt thêm `CancellationException`. Không chỉ xác nhận có “một exception bất kỳ”, vì như vậy có thể bỏ sót bug như `ClassCastException` hoặc `NullPointerException` không mong muốn.

### 15.3. Test `allOf` chỉ phát kết quả sau khi đủ input

~~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> first = new CompletableFuture<>();
CompletableFuture<String> second = new CompletableFuture<>();

CompletableFuture<Void> all =
        CompletableFuture.allOf(first, second);

first.complete("A");
System.out.println(all.isDone()); // false

second.complete("B");
System.out.println(all.isDone()); // true
all.join();
~~~~

### 15.4. Test timeout mà không phụ thuộc thời gian thực nếu có thể

Muốn test việc caller **nhận timeout** từ một stage chưa hoàn thành, có thể kiểm tra thao tác `get(timeout)` bằng một timeout nhỏ; nhưng các test theo đồng hồ thực có thể không ổn định khi môi trường quá tải. Với logic nghiệp vụ, nên tách phần quyết định **xử lý lỗi timeout** thành một hàm riêng để test trực tiếp bằng `CompletableFuture.failedFuture(new TimeoutException(...))`.

~~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeoutException;

CompletableFuture<String> timedOut =
        CompletableFuture.failedFuture(
                new TimeoutException("simulated"));

String display = timedOut
        .exceptionally(error -> "not-available")
        .join();

System.out.println(display); // not-available
~~~~

Ví dụ này **không kiểm thử cơ chế đếm thời gian** của JDK. Nó chỉ kiểm thử nhánh xử lý khi stage đã hoàn thành với exception timeout. Nếu ứng dụng cần kiểm thử deadline thực, dùng framework phù hợp và đặt ngưỡng có dự phòng, thay vì giả định lệnh `sleep` hoàn thành chính xác đến mili giây.

### 15.5. Ma trận trạng thái cần bao phủ

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Nguồn chưa hoàn tất | Dependent `thenApply` chưa có giá trị |
| Nguồn hoàn tất bình thường | Callback nhận đúng giá trị |
| Nguồn hoàn tất với `null` | Được coi là bình thường; callback phải xử lý theo hợp đồng |
| Nguồn hoàn tất ngoại lệ | Bước `thenApply` không chạy; lỗi lan qua stage |
| Có `exceptionally` | Đường thất bại có thể trở thành giá trị fallback |
| `whenComplete` quan sát bình thường | Không tự đổi giá trị |
| `whenComplete` tự ném lỗi khi nguồn bình thường | Dependent stage hoàn tất ngoại lệ |
| `thenCompose` trả stage chưa hoàn tất | Future kết quả tiếp tục chờ stage thứ hai |
| `thenCombine` có một nguồn chưa hoàn tất | Kết quả chưa hoàn tất |
| `allOf` có một input thất bại | `allOf` hoàn tất ngoại lệ khi các input đã hoàn tất |
| `anyOf` với đầu vào rỗng | Future vẫn incomplete |
| `get(timeout)` hết thời gian chờ | Caller ném `TimeoutException`, future nguồn không tự bị hoàn tất |
| `orTimeout` hết hạn | Future được gọi hoàn tất ngoại lệ |
| `completeOnTimeout` hết hạn | Future được gọi có giá trị fallback |
| `cancel` trước khi hoàn tất | Future có trạng thái hủy; không bảo đảm worker dừng |
| Hai luồng cùng gọi `complete` | Chỉ một lời gọi thành công |
| Continuation chạy trong executor bị đóng trước khi lên lịch | Có thể gặp lỗi lập lịch như `RejectedExecutionException` |

Không cần ép mọi kiểm thử dùng executor thật. Hãy dùng **future điều khiển được** cho quy tắc kết quả, và chỉ dùng tác vụ concurrent thực tế khi muốn kiểm tra phối hợp thread, tải và shutdown.

## 16. Những lỗi phổ biến trong ứng dụng Java 27

| Sai lầm | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Nghĩ `supplyAsync` luôn tạo virtual thread | Mặc định thường dùng common pool | Chọn executor tường minh khi cần |
| Gọi `join()` giữa nhiều bước async | Chặn thread, có thể gây starvation | Dùng `thenCompose` hoặc `thenCombine` |
| Dùng `thenApply` cho hàm trả future | Tạo future lồng nhau | Dùng `thenCompose` |
| Khởi chạy tác vụ phụ thuộc thành chuỗi dù thật ra độc lập | Tăng thời gian tổng | Khởi động cả hai rồi `thenCombine` |
| Mong `allOf` trả `List<T>` | `allOf` chỉ trả `Void` | Thu giá trị từng future sau khi allOf thành công |
| Dùng `anyOf` như “first successful” chắc chắn | Nhánh hoàn tất ngoại lệ có thể thắng | Định nghĩa chính sách race rõ ràng |
| Gọi `anyOf()` với mảng rỗng rồi `join` | Có thể chờ vô hạn | Xử lý danh sách rỗng trước |
| Dùng `whenComplete` để thay dữ liệu | Nó không phải hàm recovery | Dùng `handle` hoặc `exceptionally` |
| Bắt mọi exception rồi trả kết quả thành công | Che giấu lỗi thật | Phân biệt lỗi hạ tầng và trạng thái nghiệp vụ |
| Dùng `getNow(null) == null` để suy ra incomplete | `null` có thể là kết quả thành công | Dùng `isDone` và chính sách kiểu kết quả rõ |
| Tưởng `orTimeout` chỉ giới hạn một bản sao độc lập | Nó sửa chính future được gọi | Áp dụng trên dependent copy khi muốn giới hạn riêng |
| Tưởng timeout dừng computation | Future state và task state là hai chuyện khác | Cấu hình I/O timeout, cancellation và tài nguyên riêng |
| Gọi `cancel(true)` rồi chắc rằng worker bị interrupt | CompletableFuture không điều khiển worker theo cách đó | Dùng cancellation hợp tác với tác vụ có quyền sở hữu |
| Đóng executor trước khi continuation async hoàn thành | Có thể từ chối công việc chưa lên lịch | Quản lý lifecycle cho cả pipeline |
| Tạo thread pool cố định với hàng đợi không giới hạn và không kiểm soát tải | Task chờ có thể tích lũy quá lớn | Queue/limiter/backpressure phù hợp |
| Dùng virtual threads và cho phép request vô hạn | Tạo tải quá lớn lên dịch vụ ngoài | Giới hạn số lời gọi đang chạy |
| Chia sẻ collection mutable giữa nhiều continuation | Data race và kết quả khó lặp lại | Immutable DTO, defensive copy, đồng bộ khi cần |
| Phụ thuộc `ThreadLocal` tự lan sang mọi callback | Execution context có thể đổi thread | Truyền context tường minh hoặc cơ chế propagation kiểm thử được |
| Bỏ exception của future `Void` | Lỗi có thể không được quan sát | Gắn error handling và theo dõi kết quả tác vụ |
| Không hoàn tất future do callback tạo ra | Client treo vô hạn | Bảo đảm mọi nhánh callback complete hoặc completeExceptionally |

## 17. Checklist thiết kế một phương thức bất đồng bộ

Trước khi phát hành, kiểm tra các câu hỏi:

- [ ] Phương thức có thực sự tạo/đại diện cho công việc bất đồng bộ không, hay chỉ trả future đã hoàn tất để giữ đồng nhất giao diện?
- [ ] Hợp đồng kết quả có kiểu rõ, gồm cả trường hợp không tìm thấy, null và lỗi?
- [ ] Đã phân biệt việc **tính giá trị** (`supplyAsync`) và **thực hiện hành động không trả dữ liệu** (`runAsync`)?
- [ ] Đã chọn executor theo loại công việc và giới hạn tài nguyên?
- [ ] Có thể nối chuỗi qua `thenCompose` thay vì `join` chặn giữa pipeline?
- [ ] Các tác vụ độc lập đã được khởi động độc lập và kết hợp phù hợp?
- [ ] Có chính sách exception: lan truyền, chuyển kiểu kết quả, fallback hoặc retry có giới hạn?
- [ ] Timeout có ý nghĩa gì: caller ngừng đợi, future hoàn tất ngoại lệ hay dùng giá trị dự phòng?
- [ ] Có cơ chế hủy và đóng tài nguyên **công việc thật**, không chỉ đổi trạng thái future?
- [ ] Nếu dùng virtual threads, đã giới hạn số tác vụ đang tác động tới backend?
- [ ] Các continuation có thể chạy trên thread nào, và liệu callback có được phép blocking?
- [ ] Có nguy cơ đóng executor trước khi các bước `*Async` được lên lịch?
- [ ] Dữ liệu kết quả, shared state và context của request có an toàn khi được chuyển qua thread?
- [ ] Có test điều khiển được các trạng thái success, failure, cancellation, timeout và input rỗng?
- [ ] Có metrics và log lỗi mà không làm lộ dữ liệu nhạy cảm?

## 18. Hướng dẫn lựa chọn nhanh

| Nhu cầu | API hoặc thiết kế được ưu tiên |
| --- | --- |
| Kết quả đã có ngay | `completedFuture` / `completedStage` |
| Cần thông báo lỗi bất đồng bộ ngay | `failedFuture` / `failedStage` |
| Chạy một Supplier trên executor | `supplyAsync(..., executor)` |
| Chạy Runnable không trả dữ liệu | `runAsync(..., executor)` |
| Biến đổi giá trị bình thường | `thenApply` |
| Biến đổi bằng một bước cần executor | `thenApplyAsync(..., executor)` |
| Phụ thuộc vào một tác vụ async thứ hai | `thenCompose` |
| Kết hợp hai kết quả độc lập | `thenCombine` |
| Đợi N tác vụ và thu kết quả riêng | `allOf` + đọc mỗi future sau khi hoàn thành |
| Muốn một kết quả của task hoàn thành đầu | `anyOf`, phải chấp nhận khả năng lỗi thắng |
| Recovery thành một giá trị | `exceptionally` |
| Recovery bằng một tác vụ bất đồng bộ khác | `exceptionallyCompose` |
| Xử lý cả success/failure thành kết quả mới | `handle` |
| Ghi metrics/quan sát không đổi kết quả | `whenComplete` |
| Chặn để lấy kết quả ở ranh giới đồng bộ | `join` hoặc `get` |
| Đợi có hạn nhưng không thay đổi future | `get(timeout, unit)` |
| Thay đổi chính future khi quá hạn | `orTimeout` hoặc `completeOnTimeout` |
| I/O blocking nhiều tác vụ với JDK hiện hành | Virtual-thread executor có kiểm soát tải |

## Tài liệu tham khảo chính thức

- [Java SE 27 — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html): creation/completion, `join`, `get`, `allOf`, `anyOf`, timeout, cancellation, `copy` và `minimalCompletionStage`.
- [Java SE 27 — CompletionStage](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionStage.html): dependency stages, `thenApply`, `thenCompose`, `thenCombine`, `handle`, `whenComplete` và memory consistency.
- [Java SE 27 — Future](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Future.html): `get`, `cancel`, completion state và kết quả.
- [Java SE 27 — Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): `newFixedThreadPool`, `newVirtualThreadPerTaskExecutor` và các executor factory.
- [Java SE 27 — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): vòng đời, `close` và shutdown.
- [Java SE 27 — CompletionException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionException.html): wrapper lỗi của các continuation.
- [Java SE 27 — CancellationException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CancellationException.html): trạng thái hủy.
- [Java SE 27 — Semaphore](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Semaphore.html): giới hạn số tác vụ ở vùng tài nguyên được phép.
- [Java SE 27 — StructuredTaskScope (preview)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): tham khảo **trạng thái preview** để phân biệt, không dùng API này trong ví dụ khuyến nghị của bài.

**Kết luận:** `CompletableFuture` trong Java 27 giúp coi một kết quả chưa sẵn có là **một giá trị có trạng thái hoàn thành**, từ đó định nghĩa pipeline xử lý bằng `CompletionStage` thay vì chặn luồng sau mỗi bước. Dùng `thenCompose` cho phụ thuộc tuần tự, `thenCombine`/`allOf` cho các công việc độc lập, và xử lý rõ ngoại lệ, timeout, cancellation. Đặc biệt, **future hoàn tất không đồng nghĩa công việc ngoài đã dừng hoặc giao dịch đã chắc chắn thành công**. Thiết kế executor, giới hạn tài nguyên, vòng đời và hợp đồng kết quả rõ ràng mới tạo ra một hệ bất đồng bộ an toàn, có thể kiểm thử và dễ bảo trì.
