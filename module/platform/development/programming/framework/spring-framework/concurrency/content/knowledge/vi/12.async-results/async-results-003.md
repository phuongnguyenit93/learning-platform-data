# `CompletableFuture` cho phép kết hợp các bước xử lý

**Module:** Spring Framework - concurrency  
**Nhóm:** Kết quả bất đồng bộ  
**Mục tiêu:** Biết mô hình hóa một quy trình gồm nhiều bước không đồng bộ bằng `CompletableFuture<T>`/`CompletionStage<T>`, chọn đúng `thenApply`, `thenCompose`, `thenCombine`, `allOf` và các nhánh xử lý lỗi, đồng thời hiểu ranh giới executor, timeout và cách tích hợp với Spring `@Async`.

## 1. Từ một Future đến một luồng công việc

Trong ứng dụng Spring, việc tạo báo giá có thể cần:

1. Lấy giá sản phẩm.
2. Tính thuế từ giá — **phụ thuộc vào bước 1**.
3. Lấy phí vận chuyển — **độc lập với việc tính thuế**.
4. Ghép giá có thuế và phí vận chuyển thành tổng tiền.
5. Dựa trên tổng tiền, gọi dịch vụ giữ chỗ hàng — **phụ thuộc vào bước 4 và cũng trả về future**.
6. Lấy loại khách hàng độc lập; chỉ khi cả phần giữ chỗ và loại khách hàng hoàn thành thì tạo kết quả.
7. Nếu một bước lỗi hoặc quá hạn, chuyển lỗi, dùng fallback đúng phạm vi hoặc từ chối theo hợp đồng nghiệp vụ.

Viết kiểu blocking truyền thống:

```java
int price = priceFuture.get();          // Chờ giá.
int shipping = shippingFuture.get();    // Chờ phí vận chuyển.
String reservation = reserve(total).get(); // Chờ tác vụ tiếp.
```

Đây là đoạn **minh họa**, chưa đủ biến `priceFuture`, `shippingFuture`, `total` và `reserve` để biên dịch riêng. Mỗi `get()` có thể chặn thread hiện tại, và việc lấy kết quả từng bước dễ làm người viết đặt các điểm chờ không cần thiết.

Với `CompletableFuture`, ta mô tả **quan hệ phụ thuộc** giữa các kết quả:

```text
getPrice() ------- thenApply(tính thuế) ---+
                                           +-- thenCombine(tổng) -- thenCompose(giữ chỗ) --+
getShipping() -----------------------------+                                             |
                                                                                         +-- allOf --> kết quả
getCustomerTier() ----------------------------------------------------------------------+
```

Mỗi mũi tên là một **stage** (bước phụ thuộc). Stage phía sau được kích hoạt theo điều kiện hoàn thành của stage phía trước, thay vì buộc thread đang xây pipeline chờ ở từng bước. **Kết hợp bất đồng bộ không đồng nghĩa mọi đoạn code đều chạy trên thread khác**; thread thực thi còn tùy executor và cách dùng các phương thức có hậu tố `Async`.

## 2. Bản chất của `CompletableFuture`

`java.util.concurrent.CompletableFuture<T>` (có từ Java 8; dùng tốt trong Java 17+) vừa:

- Triển khai `Future<T>`: biểu diễn một kết quả có thể lấy bằng `get()`, theo dõi `isDone()`, `cancel()`.
- Triển khai `CompletionStage<T>`: mô tả các thao tác **tiếp nối, ghép, rẽ nhánh và xử lý lỗi** khi kết quả sẵn sàng.
- Cho phép hoàn thành thủ công bằng `complete(value)` hoặc `completeExceptionally(error)`; thường được dùng khi thích nghi API callback sang mô hình Future.

Một future có thể ở trạng thái **chưa hoàn thành**, **hoàn thành bình thường** với giá trị `T`, hoặc **hoàn thành ngoại lệ**. Một trong các thao tác hoàn thành thắng cuộc; kết quả đã hoàn thành thông thường không được ghi đè bằng `complete` lần nữa.

```java
CompletableFuture<Integer> result = new CompletableFuture<>();

boolean first = result.complete(42);   // true: lần hoàn thành đầu tiên.
boolean second = result.complete(99);  // false: đã hoàn thành.
System.out.println(result.join());     // 42.
```

Đây là đoạn Java 17 hợp lệ khi đặt vào một method và import `java.util.concurrent.CompletableFuture`. `join()` **cũng chờ** nếu future chưa xong; tên `join` không làm việc chờ trở thành non-blocking.

### `completedFuture`, `failedFuture`, `supplyAsync` và `runAsync`

| Cách tạo | Kết quả |
| --- | --- |
| `CompletableFuture.completedFuture(42)` | Đã hoàn thành thành công với `42`; không tạo task mới |
| `CompletableFuture.failedFuture(error)` | Đã hoàn thành ngoại lệ; hữu ích trong kiểm thử/đường lỗi |
| `CompletableFuture.supplyAsync(supplier, executor)` | Giao một phép tính **có giá trị trả về** cho executor chỉ định |
| `CompletableFuture.runAsync(runnable, executor)` | Giao tác vụ `void`, trả `CompletableFuture<Void>` |
| `new CompletableFuture<>()` | Future chưa hoàn thành; bên khác phải gọi `complete`/`completeExceptionally` hoặc tương đương |

Chỉ tạo `new CompletableFuture<>()` không làm một tác vụ tự chạy. Chỉ gọi `completedFuture` không làm một method đang chạy trở thành asynchronous.

## 3. Chọn toán tử kết hợp: một nguồn, nguồn phụ thuộc, hai nguồn độc lập

| Tình huống | API | Đầu vào → đầu ra | Chờ điều kiện nào? |
| --- | --- | --- | --- |
| Biến đổi một kết quả đã có | `thenApply(fn)` | `T -> U` | Future nguồn hoàn thành bình thường |
| Làm việc phụ không trả dữ liệu | `thenAccept(consumer)` | `T -> Void` | Future nguồn hoàn thành bình thường |
| Chạy bước tiếp theo không dùng giá trị | `thenRun(runnable)` | `T -> Void` | Future nguồn hoàn thành bình thường |
| Bước tiếp theo **tự trả CompletionStage** | `thenCompose(fn)` | `T -> CompletionStage<U>`, kết quả ghép `U` | Nguồn xong rồi stage được trả về cũng xong |
| Kết hợp kết quả **hai future độc lập** | `thenCombine(other, fn)` | `T + U -> V` | **Cả hai** hoàn thành bình thường |
| Hành động dùng hai kết quả | `thenAcceptBoth(other, action)` | `T + U -> Void` | Cả hai hoàn thành bình thường |
| Đợi **tất cả** một danh sách future | `CompletableFuture.allOf(...)` | `... -> Void` | Tất cả hoàn thành |
| Lấy future hoàn thành **đầu tiên** | `CompletableFuture.anyOf(...)` | `... -> Object` | Một future hoàn thành, **kể cả ngoại lệ** |
| Xử lý thành công/lỗi để đổi kết quả | `handle((value, error) -> ...)` | `T hoặc lỗi -> U` | Nguồn hoàn thành theo bất kỳ cách nào |
| Chỉ phục hồi khi lỗi | `exceptionally(error -> fallback)` | Lỗi `T -> T` | Nguồn hoàn thành ngoại lệ |
| Quan sát thành công/lỗi | `whenComplete((value, error) -> ...)` | Thường giữ kết quả gốc | Nguồn hoàn thành theo bất kỳ cách nào |

**Ghi nhớ:** `thenApply` biến đổi **giá trị**; `thenCompose` nối một **công việc bất đồng bộ khác**; `thenCombine` ghép **hai việc độc lập**. Ba phương thức này giải quyết ba dạng phụ thuộc khác nhau.

## 4. `thenApply`: biến đổi kết quả của một bước

Giả sử giá gốc là 200, thuế được tính bằng 10%:

```java
CompletableFuture<Integer> price =
        CompletableFuture.completedFuture(200);

CompletableFuture<Integer> priceWithTax =
        price.thenApply(p -> p + p / 10);

System.out.println(priceWithTax.join()); // 220
```

`thenApply` nhận một hàm `T -> U`; kết quả được đặt trong **future mới**. Nó **không** thay đổi giá trị của `price`. Nếu nguồn hoàn thành ngoại lệ thì lambda `thenApply` **không được chạy theo đường thành công**; stage tiếp theo trở thành exceptional, trừ khi có cơ chế phục hồi phù hợp.

Dùng `thenApply` cho phép biến đổi đồng bộ **nhẹ và nhanh**, chẳng hạn mapping DTO, chuẩn hóa dữ liệu nhỏ, tính toán ít CPU. Nếu lambda phải chờ DB/HTTP hoặc tính CPU nặng, không nên vô tình chạy nó trên completion thread của một phần việc khác. Khi cần chủ động chọn pool cho phép biến đổi, dùng `thenApplyAsync(fn, executor)` và một executor có giới hạn phù hợp.

## 5. `thenCompose`: nối một tác vụ mới và loại bỏ future lồng nhau

Đây là khác biệt quan trọng nhất khi học kết hợp nhiều bước.

Giả sử sau khi biết tổng tiền, ta phải gọi một dịch vụ khác trả về `CompletableFuture<String>` chứa mã giữ chỗ:

```java
CompletableFuture<Integer> total =
        CompletableFuture.completedFuture(245);

CompletableFuture<String> reservation =
        total.thenCompose(amount ->
                CompletableFuture.supplyAsync(
                        () -> "RES-" + amount,
                        ioExecutor));
```

Ví dụ trên là **đoạn minh họa**, cần có biến `ioExecutor` kiểu `Executor` và import `CompletableFuture`. Khi total có giá trị, hàm trả về một stage khác. `thenCompose` trả về `CompletableFuture<String>` được hoàn thành theo stage bên trong.

Nếu viết bằng `thenApply`, kiểu kết quả trở thành **future lồng future**:

```java
CompletableFuture<CompletableFuture<String>> nested =
        total.thenApply(amount ->
                CompletableFuture.supplyAsync(
                        () -> "RES-" + amount,
                        ioExecutor));
```

Cần chờ/ghép thêm để có giá trị thật. Vì vậy, khi lambda **trả một future**, mặc định nên nghĩ tới `thenCompose` thay cho `thenApply`.

So sánh tương tự:

```text
thenApply(fn):    Future<T> + (T -> U)            -> Future<U>
thenCompose(fn):  Future<T> + (T -> Future<U>)     -> Future<U>
```

Không nhét `join()` bên trong lambda để “làm phẳng” thủ công:

```java
// Tránh: blocking trong continuation, dễ gây nghẽn/deadlock.
total.thenApply(amount -> reserveAsync(amount).join());
```

Đoạn minh họa trên giả sử `reserveAsync(amount)` có tồn tại. Nếu nó đặt task vào **chính pool có số worker nhỏ** và continuation đang chiếm một worker để chờ, có thể xảy ra starvation hoặc deadlock. Dùng `thenCompose(amount -> reserveAsync(amount))` để mô tả phụ thuộc mà **không giữ thread chờ**.

### `thenComposeAsync` khác `thenCompose` như thế nào?

`thenCompose` chạy **hàm tạo stage tiếp theo** theo quy tắc completion không-async; `thenComposeAsync(fn, executor)` chủ động giao việc chạy hàm đó sang executor. Nhưng **executor này không tự quyết định nơi chạy mọi task trong future mà `fn` trả về**: future bên trong có nguồn phát, network client, executor và quy tắc riêng. Phân biệt “chạy callback nối stage” với “chạy tác vụ nghiệp vụ bên trong”.

## 6. `thenCombine`: kết hợp hai kết quả độc lập

Giá có thuế và phí vận chuyển có thể được tìm đồng thời, rồi ghép khi cả hai xong:

```java
CompletableFuture<Integer> priceWithTax =
        CompletableFuture.supplyAsync(() -> 220, executor);

CompletableFuture<Integer> shipping =
        CompletableFuture.supplyAsync(() -> 25, executor);

CompletableFuture<Integer> grandTotal =
        priceWithTax.thenCombine(shipping, Integer::sum);

// Không có stage nào gọi get()/join() để chờ stage kia.
System.out.println(grandTotal.join()); // 245
```

Đoạn trên cần biến `executor` kiểu `Executor` trong chương trình thực tế. `thenCombine` chỉ chạy hàm khi **cả hai nguồn hoàn thành bình thường**. Nếu một nguồn lỗi, future kết quả cũng thất bại; không tự dùng giá trị `0` cho nguồn bị lỗi.

Sự khác biệt về cấu trúc:

- **Phụ thuộc tuần tự:** bước B cần giá trị A mới biết làm gì → `A.thenCompose(a -> B(a))`.
- **Độc lập:** có thể gửi A và B từ đầu, chỉ ghép kết quả sau → `A.thenCombine(B, combiner)`.
- **Đừng viết** `A.thenCompose(a -> B())` nếu B thực sự không phụ thuộc A: điều đó làm B khởi động chậm không cần thiết.

Nếu hai phép tính có cùng kết quả nhưng ưu tiên kết quả nào đến trước, `applyToEither` có thể hữu ích; nó kích hoạt khi có một nguồn **hoàn thành bình thường** phù hợp. Đừng nhầm với `anyOf`, vì `anyOf` có thể hoàn thành **ngoại lệ** ngay khi nguồn đầu tiên lỗi.

## 7. `allOf`: đợi nhiều nhánh; `anyOf`: lấy kết quả đầu tiên

### `CompletableFuture.allOf`

```java
CompletableFuture<String> a =
        CompletableFuture.completedFuture("A");
CompletableFuture<String> b =
        CompletableFuture.completedFuture("B");
CompletableFuture<String> c =
        CompletableFuture.completedFuture("C");

CompletableFuture<String> summary =
        CompletableFuture.allOf(a, b, c)
                .thenApply(ignored -> a.join() + b.join() + c.join());

System.out.println(summary.join()); // ABC
```

`allOf` trả `CompletableFuture<Void>`, **không trả một danh sách kết quả**. Chỉ sau khi `allOf` hoàn thành bình thường, việc lấy `a.join()`, `b.join()`, `c.join()` trong continuation trên không phải chờ thêm; chúng đã xong. Nếu một thành phần lỗi, `allOf` hoàn thành ngoại lệ; continuation thành công sẽ không chạy. Muốn tổng hợp cả **thành công lẫn lỗi của từng nguồn**, phải chuyển từng nhánh thành kết quả có trạng thái (`handle`) trước khi `allOf`.

Ví dụ tổng hợp theo **thứ tự input** (không phụ thuộc thứ tự chạy):

```java
List<CompletableFuture<String>> futures = List.of(a, b, c);

CompletableFuture<List<String>> values =
        CompletableFuture.allOf(
                futures.toArray(new CompletableFuture[0]))
                .thenApply(ignored ->
                        futures.stream()
                                .map(CompletableFuture::join)
                                .toList());
```

Đoạn trên cần import `java.util.List` và `java.util.concurrent.CompletableFuture`; là phần code có thể đặt trong method. Khi một future lỗi, cả `values` sẽ lỗi; nó không mặc định bỏ qua nguồn thất bại.

### `CompletableFuture.anyOf`

```java
CompletableFuture<String> fast =
        CompletableFuture.completedFuture("cache");
CompletableFuture<String> slow =
        new CompletableFuture<>();

CompletableFuture<Object> first =
        CompletableFuture.anyOf(fast, slow);

System.out.println(first.join()); // cache
```

`anyOf` hoàn thành theo **future đầu tiên hoàn thành**, dù thành công hay ngoại lệ, và trả `Object` vì input có thể khác kiểu. Trong ví dụ này `fast` đã hoàn thành từ trước, nên kết quả xác định. Với hai nguồn thực sự tranh đua nhau, không thể dự đoán nguồn thắng nếu không kiểm soát lịch hoàn thành.

**Cảnh báo:** “đã có một kết quả” không có nghĩa các công việc còn lại tự dừng hoặc tự được cancel. Với các lời gọi HTTP tới hai nhà cung cấp, cần chính sách timeout/cancel/resilience thực tế nếu không muốn tiếp tục tiêu thụ tài nguyên.

### Không biến `allOf` thành “chạy tất cả song song” một cách thần kỳ

`allOf` chỉ **đợi** các future đã có. Tính song song phụ thuộc lúc **khởi động từng future** và tài nguyên executor. Nếu bạn tạo tất cả bằng `completedFuture` thì không có I/O nào phát sinh. Nếu từng future gọi API đồng bộ trên cùng pool 1 thread, chúng vẫn có thể chạy tuần tự dù dùng `allOf`.

## 8. `thenApply` và các phương thức hậu tố `Async`: thread nào chạy?

Các phương thức như `thenApply`, `thenCompose`, `thenCombine`, `whenComplete` **không có hậu tố `Async`** có thể chạy callback trên thread hoàn thành future nguồn, hoặc thread khác đang thực hiện thao tác completion. Nếu nguồn đã hoàn thành khi đăng ký callback, phần xử lý có thể chạy ngay trong thread đang đăng ký.

Các biến thể có hậu tố `Async`:

- `thenApplyAsync(fn)`, `thenComposeAsync(fn)` không truyền executor: với `CompletableFuture` thông thường, mặc định dùng `ForkJoinPool.commonPool()` của JDK (có quy tắc fallback khi common pool không hỗ trợ đủ parallelism).
- `thenApplyAsync(fn, executor)` và `thenComposeAsync(fn, executor)`: giao callback cho **executor chỉ định**, giúp kiểm soát thread/queue/rejection.
- `CompletableFuture.supplyAsync(supplier, executor)`: chủ động chạy supplier trong pool được chọn.
- **Khai báo `@Async` trên một Spring method không làm các lời gọi `thenApplyAsync()` không tham số trong code khác tự chuyển sang Spring executor.** Cần truyền executor rõ ràng khi muốn dùng cùng pool.

Ví dụ mapping nhẹ:

```java
CompletableFuture<OrderDto> dto =
        orderFuture.thenApply(OrderDto::from);
```

Ví dụ mapping CPU nặng được tách pool:

```java
CompletableFuture<byte[]> compressed =
        fileFuture.thenApplyAsync(
                bytes -> compress(bytes),
                cpuExecutor);
```

Hai đoạn trên là **minh họa trong ứng dụng**: cần các kiểu `OrderDto`, `orderFuture`, `fileFuture`, `compress` và `cpuExecutor` do dự án định nghĩa.

**Không mặc định coi `thenApplyAsync` nhanh hơn**: nó còn thêm một lần schedule/queue và có thể gây rejection. Chọn async boundary khi thật sự cần tách công việc khỏi completion thread, bảo vệ một tài nguyên hoặc phân loại loại tải.

## 9. Các kiểu lỗi và cách phục hồi có kiểm soát

Khi một stage hoàn thành ngoại lệ, các stage “thành công” phụ thuộc nó (ví dụ `thenApply`, `thenCompose`, `thenCombine`) thông thường cũng hoàn thành ngoại lệ; hàm success callback không chạy. Phải xử lý lỗi như một phần **của pipeline**, không trông đợi caller nhận trực tiếp exception từ worker.

| API | Khi được gọi? | Dùng để làm gì? | Giá trị stage sau |
| --- | --- | --- | --- |
| `exceptionally(error -> fallback)` | Chỉ khi lỗi | Phục hồi bằng giá trị cùng loại `T` | Bình thường nếu fallback không lỗi |
| `handle((value, error) -> newValue)` | Cả thành công và lỗi | Biến đổi cả hai nhánh thành một kết quả `U` | Tùy hàm xử lý |
| `whenComplete((value, error) -> log(...))` | Cả thành công và lỗi | Quan sát log/metric/cleanup | Thường giữ nguyên thành công/lỗi; callback cũng có thể ném |
| `exceptionallyCompose(error -> otherFuture)` (Java 12+) | Khi lỗi | Phục hồi bằng một **stage bất đồng bộ mới** | Theo stage fallback |
| `completeExceptionally(error)` | Được gọi chủ động | Đánh dấu **future hiện tại** lỗi nếu chưa hoàn thành | Boolean cho biết có thắng race hay không |

Ví dụ fallback cho một lỗi có thể chấp nhận:

```java
CompletableFuture<String> displayName =
        lookupNameAsync(userId)
                .exceptionally(error -> "Khách");

```

Đoạn này chưa độc lập: `lookupNameAsync(userId)` và `userId` thuộc ứng dụng. **Chỉ dùng fallback khi không phá hỏng bất biến nghiệp vụ.** Có thể dùng tên hiển thị mặc định, nhưng không được tự dùng `0` cho số tiền thanh toán nếu lỗi đang là không lấy được giá thật.

Ví dụ cần fallback bất đồng bộ:

```java
CompletableFuture<Profile> profile =
        fetchFromPrimary(userId)
                .exceptionallyCompose(error ->
                        fetchFromReplica(userId));
```

Cần định nghĩa `Profile`, `fetchFromPrimary`, `fetchFromReplica` trong ứng dụng; ví dụ chỉ mô tả flow. `exceptionallyCompose` tránh việc fallback stage bị lồng nhau và không cần chặn bằng `join()`.

### `handle` có thể vô tình nuốt lỗi

```java
CompletableFuture<Integer> parsed =
        CompletableFuture.<Integer>failedFuture(
                new IllegalArgumentException("invalid"))
                .handle((value, error) ->
                        error == null ? value : -1);
```

`parsed` hoàn thành bình thường với `-1`: lỗi gốc đã được **chuyển thành dữ liệu**. Đây là một quyết định rõ ràng của hợp đồng, không phải hiệu ứng phụ vô hại. Nếu không có fallback hợp lệ, ghi nhận lỗi rồi **duy trì** trạng thái lỗi.

### `whenComplete` dùng để quan sát, không phải phương thức thay giá trị

```java
CompletableFuture<String> result =
        workFuture.whenComplete((value, error) -> {
            if (error != null) {
                metrics.recordFailure(error);
            } else {
                metrics.recordSuccess();
            }
        });
```

Đây là đoạn minh họa (`workFuture`, `metrics` do ứng dụng cung cấp). Callback có thể được gọi trên thread không dự đoán trước khi dùng phiên bản không-Async. Callback cũng phải xử lý được exception của chính nó; nếu callback ném lỗi khi nguồn thành công, stage hậu quả có thể thành exceptional. Không đưa một công việc blocking kéo dài vào callback quan sát dùng chung.

## 10. `get()` và `join()`: điểm chặn thật sự nằm ở đâu?

Cả `get()` và `join()` **có thể block thread gọi** tới lúc future hoàn thành.

- `get()` có `InterruptedException`, `ExecutionException`; `get(timeout, unit)` còn có `TimeoutException` khi thread chờ quá thời gian. Phù hợp ở ranh giới cần xử lý checked exception/interrupt có chủ đích.
- `join()` trả giá trị hoặc ném unchecked `CompletionException` (hoặc trường hợp cancel là `CancellationException`); tiện khi các stage đã hoàn thành hoặc khi xử lý ở ranh giới ngoài cùng.
- `getNow(fallback)` không chờ, nhưng trả fallback nếu chưa xong; nếu đã hoàn thành ngoại lệ vẫn có thể ném.
- `isDone()` không có nghĩa thành công: có thể complete bình thường, lỗi hoặc cancel.
- `get(timeout)` **giới hạn thời gian chờ của caller**, không nhất thiết hoàn thành exceptionally hoặc dừng future gốc.

Đừng gọi `join` trong controller ngay sau khi tạo pipeline rồi tuyên bố endpoint đã non-blocking:

```java
// Có thể block Servlet thread tới khi xử lý xong.
String value = someFuture.join();
```

Trong Spring MVC, có thể trả `CompletableFuture<T>` hoặc `CompletionStage<T>` theo cơ chế async return type được hỗ trợ, hoặc dùng `DeferredResult`/`Callable` phù hợp, thay vì chặn request thread. Tuy nhiên endpoint trả future có thể vẫn **giữ HTTP response mở** chờ kết quả. Nếu cần trả `202 Accepted` ngay và xử lý sau, phải tạo hợp đồng job ID/trạng thái và khả năng lưu bền vững riêng.

## 11. Timeout, cancellation và nghĩa vụ dừng công việc

Java 9+ cung cấp:

```java
CompletableFuture<String> timed =
        remoteCallAsync()
                .orTimeout(2, java.util.concurrent.TimeUnit.SECONDS);
```

Đây là **đoạn minh họa**; cần có `remoteCallAsync()` trả `CompletableFuture<String>`. `orTimeout` làm **chính CompletableFuture nhận lời gọi** hoàn thành ngoại lệ với `TimeoutException` nếu quá hạn. Nó **không tự hủy** network call, query DB hoặc task đang chạy. Các continuation đã xếp hàng cũng có thể còn hoạt động tùy thiết kế. Nếu muốn trả giá trị mặc định:

```java
CompletableFuture<String> withFallback =
        remoteCallAsync()
                .completeOnTimeout(
                        "tạm-không-có",
                        2, java.util.concurrent.TimeUnit.SECONDS);
```

`completeOnTimeout` cũng tác động lên **chính future gọi phương thức**, không phải “tạo một bản clone độc lập để timeout”. Nếu future được chia sẻ cho nhiều người tiêu thụ, việc đặt timeout có thể thay đổi kết quả mà những người tiêu thụ khác nhìn thấy. Cân nhắc tạo một dependent stage độc lập rồi đặt timeout lên stage đó khi cần cô lập chính sách timeout (và hiểu rõ cách lan truyền lỗi).

`cancel(true)` đối với `CompletableFuture` được xem như **hoàn thành ngoại lệ bằng `CancellationException`**; tham số `mayInterruptIfRunning` không bảo đảm ngắt thread thực thi supplier. Muốn hủy tác vụ thực, phải tích hợp đúng cancel API của HTTP/JDBC client, cooperative cancellation/interrupt hoặc token, cùng quy tắc đóng resource.

Timeout và cancel nên đi từ **deadline tổng** của yêu cầu, không phải mỗi bước tự nhận một timeout lớn rồi cộng dồn. Ví dụ một request có 2 giây end-to-end không thể cho ba lời gọi tuần tự mỗi lời gọi 2 giây mà vẫn đảm bảo SLA.

## 12. Chương trình Java 17 độc lập: pipeline tuần tự + song song + lỗi

Ví dụ sau có thể biên dịch bằng **JDK 17 trở lên**, không cần Spring. Nó minh họa:

- `supplyAsync` với `ExecutorService` được truyền tường minh.
- `thenApply` tính thuế sau khi có giá.
- `thenCombine` ghép giá với phí vận chuyển **độc lập**.
- `thenCompose` gọi bước giữ chỗ trả future mà không tạo future lồng nhau.
- `allOf` chờ kết quả giữ chỗ và hạng khách hàng.
- `exceptionally`, `handle`, `whenComplete` theo các hợp đồng khác nhau.
- `shutdown` executor có trách nhiệm, không đoán thứ tự worker.

Lưu nguyên văn **`CompletableFutureCompositionDemo.java`**:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CompletableFutureCompositionDemo {

    private static CompletableFuture<Integer> fetchBasePrice(Executor executor) {
        return CompletableFuture.supplyAsync(() -> 200, executor);
    }

    private static CompletableFuture<Integer> fetchShipping(Executor executor) {
        return CompletableFuture.supplyAsync(() -> 25, executor);
    }

    private static CompletableFuture<String> fetchCustomerTier(Executor executor) {
        return CompletableFuture.supplyAsync(() -> "GOLD", executor);
    }

    private static CompletableFuture<String> reserveInventory(
            int total, Executor executor) {
        return CompletableFuture.supplyAsync(
                () -> "RES-" + total, executor);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(4);
        try {
            CompletableFuture<Integer> withTax =
                    fetchBasePrice(executor)
                            .thenApply(price -> price + price / 10);

            // Được khởi tạo độc lập với withTax.
            CompletableFuture<Integer> shipping =
                    fetchShipping(executor);

            CompletableFuture<Integer> total =
                    withTax.thenCombine(shipping, Integer::sum);

            // Callback tạo ra một future khác: dùng thenCompose.
            CompletableFuture<String> reservation =
                    total.thenCompose(amount ->
                            reserveInventory(amount, executor));

            CompletableFuture<String> tier =
                    fetchCustomerTier(executor);

            CompletableFuture<String> report =
                    CompletableFuture.allOf(reservation, tier)
                            .thenApply(ignored ->
                                    reservation.join() + "/" + tier.join());

            System.out.println("total=" + total.join());
            System.out.println("reservation=" + reservation.join());
            System.out.println("report=" + report.join());

            CompletableFuture<String> recovered =
                    CompletableFuture.<String>failedFuture(
                            new IllegalStateException("service down"))
                            .exceptionally(error -> "fallback");

            System.out.println("recovered=" + recovered.join());

            CompletableFuture<String> handled =
                    CompletableFuture.<String>failedFuture(
                            new IllegalArgumentException("invalid"))
                            .handle((value, error) ->
                                    error == null ? value : "invalid-input");

            System.out.println("handled=" + handled.join());

            AtomicInteger observedCount = new AtomicInteger();
            CompletableFuture<String> observed =
                    CompletableFuture.completedFuture("ok")
                            .whenComplete((value, error) ->
                                    observedCount.incrementAndGet())
                            .thenApply(String::toUpperCase);

            System.out.println("observed=" + observed.join());
            System.out.println("observedCount=" + observedCount.get());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
javac CompletableFutureCompositionDemo.java
java CompletableFutureCompositionDemo
```

**Stdout do chương trình in khi kết thúc bình thường:**

```text
total=245
reservation=RES-245
report=RES-245/GOLD
recovered=fallback
handled=invalid-input
observed=OK
observedCount=1
```

Giải thích:

1. `fetchBasePrice` trả `200`, `thenApply` thêm thuế 10% thành `220`.
2. Phí vận chuyển độc lập là `25`, `thenCombine` cho `245`.
3. `thenCompose` gửi bước giữ chỗ mới với tổng `245`, trả `RES-245` không lồng future.
4. `allOf` yêu cầu cả giữ chỗ và hạng `GOLD` hoàn thành; `report` ghép chúng theo thứ tự trong lambda, bất kể worker nào chạy xong trước.
5. Hai future thất bại được `exceptionally`/`handle` chuyển thành giá trị fallback minh họa. Trong nghiệp vụ tính tiền, việc fallback có hợp lệ hay không phải được đánh giá riêng.
6. `whenComplete` tăng bộ đếm đúng một lần rồi để giá trị `"ok"` đi qua `thenApply` thành `"OK"`.

Vì chương trình chỉ in ở thread `main` **sau khi chờ các future tương ứng** nên thứ tự và nội dung các dòng là xác định; thứ tự chạy thật của 4 worker không xác định. `Executors.newFixedThreadPool` có queue không giới hạn theo lượng bộ nhớ và chỉ được dùng để đơn giản hóa ví dụ; dịch vụ thật nên dùng executor giới hạn queue/admission phù hợp.

**Điểm học quan trọng:** pipeline thể hiện đúng *phụ thuộc* của công việc, nhưng tại cuối chương trình CLI vẫn cần `join()` để in kết quả sau khi hoàn tất. Điều này hoàn toàn khác việc `join()` ngay bên trong continuation hoặc trong request thread đang cần duy trì tính responsive.

## 13. Ghép với Spring `@Async` đúng ranh giới

Một Spring service có thể trả `CompletableFuture<T>` từ method `@Async`. Spring giao invocation qua executor đã cấu hình, sau đó caller kết hợp các future trả về bằng JDK API.

Trong một dự án **Spring Boot 3.x, Java 17+** có `spring-boot-starter-web` hoặc Spring Context phù hợp, ví dụ ba file sau minh họa cách nối các thành phần. Đây là **các class thuộc dự án Spring**, không phải một chương trình `javac` thuần độc lập; chương trình JDK chạy được nằm ở phần 12.

### 13.1. Executor có giới hạn và bật `@Async`

File `src/main/java/com/example/quote/AsyncConfig.java`:

```java
package com.example.quote;

import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncConfig {

    @Bean("quoteIoExecutor")
    public ThreadPoolTaskExecutor quoteIoExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("quote-io-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
```

Đây là cấu hình **minh họa**, các giá trị 4/8/32 phải được đo với tải và giới hạn kết nối DB/HTTP thật. Executor là Spring bean nên container quản lý lifecycle của `ThreadPoolTaskExecutor`. Chỉ gắn `@EnableAsync` không tự bảo đảm các method được gọi đúng qua Spring proxy.

### 13.2. Hai nguồn kết quả độc lập

File `src/main/java/com/example/quote/QuoteDataService.java`:

```java
package com.example.quote;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class QuoteDataService {

    @Async("quoteIoExecutor")
    public CompletableFuture<Integer> fetchPrice(long productId) {
        // Mô phỏng đọc dữ liệu; ứng dụng thật dùng DB/API client có timeout.
        return CompletableFuture.completedFuture(200);
    }

    @Async("quoteIoExecutor")
    public CompletableFuture<Integer> fetchShipping(long addressId) {
        return CompletableFuture.completedFuture(25);
    }
}
```

Khi Spring proxy intercept lời gọi, method body chạy theo executor được chọn và trả một future **đã có kết quả từ bên trong worker**; caller nhận `CompletableFuture` đại diện lời gọi async. Không cần tạo `CompletableFuture.supplyAsync` thêm bên trong mỗi method chỉ để có một future, vì điều đó có thể tạo thêm một tầng scheduling và dùng pool khác ngoài dự tính.

### 13.3. Service orchestrator ghép future mà không chặn

File `src/main/java/com/example/quote/QuoteService.java`:

```java
package com.example.quote;

import java.util.concurrent.CompletableFuture;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {

    private final QuoteDataService data;

    public QuoteService(QuoteDataService data) {
        this.data = data;
    }

    public CompletableFuture<Integer> calculateQuote(
            long productId, long addressId) {

        CompletableFuture<Integer> priceWithTax =
                data.fetchPrice(productId)
                        .thenApply(p -> p + p / 10);

        CompletableFuture<Integer> shipping =
                data.fetchShipping(addressId);

        return priceWithTax.thenCombine(shipping, Integer::sum);
    }
}
```

`QuoteService` **không cần** annotation `@Async` cho method orchestration này: nó chỉ xây pipeline từ các future mà `QuoteDataService` đã khởi chạy; không dùng `get()`/`join()` để chặn. Hai nguồn được khởi chạy độc lập, và `thenCombine` đợi khi chúng đều thành công.

Ví dụ này hoạt động nếu `QuoteService` và `QuoteDataService` là **hai Spring beans** được gọi đúng qua proxy. Nếu `fetchPrice()` gọi `this.fetchShipping()` bên trong cùng `QuoteDataService`, lời gọi nội bộ có thể bỏ qua async proxy.

Khi đưa ra HTTP endpoint, cần quyết định rõ:

- Trả kết quả cuối trong cùng request? Có thể cho framework xử lý response bất đồng bộ qua return type phù hợp, thay vì `.join()` trên Servlet thread.
- Trả `202` để xử lý lâu và theo dõi sau? Cần job ID, trạng thái, persistence/retry; `CompletableFuture` **không phải durable job queue**.
- Nếu `fetchPrice()` lỗi? Kết quả `calculateQuote()` thất bại; controller/global handler cần ánh xạ thành error đúng hợp đồng, không trả tổng tiền với giá `0` âm thầm.

## 14. Ranh giới executor và bẫy `commonPool`

`CompletableFuture` trong Spring có hai cách tạo công việc thường bị trộn lẫn:

1. **Spring `@Async("quoteIoExecutor")`:** proxy gửi invocation vào **Spring bean executor** đã chỉ định.
2. **JDK `CompletableFuture.supplyAsync(...)` hoặc `thenApplyAsync(...)` không truyền executor:** mặc định dùng cơ chế executor bất đồng bộ của JDK (thường `ForkJoinPool.commonPool()`), **không tự động dùng Spring bean**.

Nếu team muốn mọi I/O blocking qua một pool Spring có queue hữu hạn, dùng:

```java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(
                () -> blockingCall(),
                quoteIoExecutor);
```

Đây là đoạn minh họa cần `Result`, `blockingCall()` và tham chiếu bean `quoteIoExecutor`. Không đưa JDBC blocking liên tục vào `ForkJoinPool.commonPool()` mà chưa hiểu áp lực của phần khác trong ứng dụng.

Một vài cảnh báo:

- `thenApply` không đảm bảo chạy trên caller thread hay trên cùng worker của nguồn; đừng phụ thuộc vào thread name để bảo vệ trạng thái.
- `thenApplyAsync` không đảm bảo “sẽ luôn có thêm một thread rảnh”: executor có thể từ chối hoặc queue đầy.
- `@Async` trên method không có nghĩa callback `thenApplyAsync` ở phần khác tự thừa hưởng `@Async` executor.
- Nếu một callback muốn dùng `ThreadLocal` request/trace/security, cần **propagation và cleanup rõ ràng**. `@Transactional` trong caller không tự lan sang worker; mỗi worker cần ranh giới transaction đúng.
- Executor có 2 thread nhưng trong callback có `join()` đợi tác vụ xếp trong **cùng executor** có thể bị nghẽn vĩnh viễn nếu cả 2 worker đều đang chờ.
- `CompletableFuture` không cung cấp backpressure ở cấp hệ thống. Gửi 10.000 tác vụ tới một executor/HTTP client có giới hạn mà không có admission control vẫn có thể làm queue lớn, timeout hoặc reject.

## 15. Những lỗi thực tế khi ghép pipeline

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `thenApply` cho hàm trả future | `CompletableFuture<CompletableFuture<T>>`, khó xử lý lỗi/chờ | `thenCompose` |
| Dùng `thenCompose` khi B độc lập A | Tạo phụ thuộc giả, B khởi chạy chậm | Khởi chạy A và B sớm, `thenCombine` |
| Gọi `.join()` trong callback để chờ tác vụ cùng pool | Giữ worker, starvation/deadlock | Ghép qua `thenCompose`/`thenCombine` |
| Gọi `.join()` ngay trong HTTP controller | Chặn request thread | Trả async result hoặc thiết kế job async theo contract |
| Nghĩ `allOf` trả kết quả các future | `allOf` thực ra trả `Void` | Lấy kết quả từ từng future sau `allOf`; kiểm tra lỗi |
| Nghĩ `anyOf` luôn trả future thành công nhanh nhất | Nó có thể hoàn thành ngoại lệ trước | Chọn điều kiện “first normal”/fallback phù hợp |
| Dùng `exceptionally(e -> null)` ở mọi nơi | Nuốt lỗi và chuyển sang dữ liệu sai | Phân loại lỗi, dùng fallback chỉ khi hợp lệ |
| Dùng `whenComplete` như `handle` để đổi giá trị | Không có ý nghĩa thay giá trị theo hợp đồng | Dùng `handle`/`thenApply` cho biến đổi |
| Dùng `thenApplyAsync()` mặc định và tưởng dùng pool Spring | Tác vụ có thể chạy ở `commonPool` | Truyền executor tường minh |
| Bỏ qua future hoàn thành ngoại lệ | Lỗi nền không được ghi nhận đúng | `whenComplete`/`handle` ở ranh giới quan sát hoặc job status |
| Dùng `orTimeout` rồi nghĩ đã hủy HTTP call | I/O có thể vẫn chạy và chiếm connection | Timeout client thực, cancellation/cooperation và resource cleanup |
| `cancel(true)` rồi nghĩ supplier đã bị interrupt | Với `CompletableFuture`, cancel chủ yếu là exceptional completion | Thiết kế cơ chế hủy riêng |
| Trong `@Async` tạo thêm `supplyAsync()` không kiểm soát | Double scheduling, pool sai, khó trace | Để proxy chạy method và trả result future phù hợp |
| Một tenant fan-out hàng nghìn nhánh không giới hạn | Quá tải connection pool, RAM, queue, downstream | Semaphore/bulkhead, batching, giới hạn concurrency |
| Trả `202` vì đã có `CompletableFuture` trong RAM | Crash làm mất công việc đã hứa xử lý | Durable job/queue, trạng thái và idempotency |
| Dùng `join()` để kiểm tra `isDone` | `isDone` có thể là lỗi/cancel | Quan sát `isCompletedExceptionally` và xử lý `CompletionException` |

## 16. Kiểm thử pipeline như thế nào?

Để test **logic kết hợp** mà không phụ thuộc timing/sleep:

1. Dùng `new CompletableFuture<>()` tạo nguồn chưa hoàn thành.
2. Kết nối `thenApply`, `thenCompose` hoặc `thenCombine`.
3. Chủ động `complete(value)` hoặc `completeExceptionally(error)` theo thứ tự bạn muốn.
4. Dùng `join()`/assertion **ở test thread cuối cùng**, không bên trong callback.
5. Kiểm tra kết quả, lỗi, thứ tự phụ thuộc và callback không chạy khi nguồn chưa đủ.

Ví dụ JUnit 5:

```java
@Test
void thenCombineWaitsForBoth() {
    CompletableFuture<Integer> left = new CompletableFuture<>();
    CompletableFuture<Integer> right = new CompletableFuture<>();

    CompletableFuture<Integer> combined =
            left.thenCombine(right, Integer::sum);

    left.complete(10);
    assertFalse(combined.isDone());

    right.complete(7);
    assertEquals(17, combined.join());
}
```

Đây là **đoạn test minh họa**, cần đặt trong test class có import `org.junit.jupiter.api.Test`, `org.junit.jupiter.api.Assertions.*` và `java.util.concurrent.CompletableFuture`, cùng dependency JUnit 5. Không cần `Thread.sleep` hay đoán lịch scheduling.

Test thêm các nhánh:

- Nguồn A lỗi, B thành công: `thenCombine` phải hoàn thành ngoại lệ, không tự tính với `null`.
- `thenCompose`: sau khi A xong nhưng future do hàm tạo chưa xong, kết quả ghép cũng chưa xong.
- `allOf`: một nhánh chưa xong thì toàn bộ chưa hoàn thành; khi tất cả xong, nguồn lỗi làm `allOf` lỗi.
- `anyOf`: hoàn thành trước bằng **ngoại lệ** để xác minh đây không phải “đầu tiên thành công”.
- `handle` đổi lỗi thành giá trị: assertion phải kiểm tra đó là **quyết định fallback**, không phải thành công nghiệp vụ bất ngờ.
- Đặt executor queue nhỏ, giữ worker bằng latch và xác minh rejection/timeout đúng như thiết kế.
- Với `@Async`, gọi qua Spring proxy/bean khác; dùng `@SpringBootTest`/slice tương ứng để kiểm tra executor, propagation và exceptional completion.

Ở môi trường production, cần kiểm thử integration với DB, HTTP client thực, timeout, retry storm và shutdown. Unit test logic future **không** chứng minh tính bền vững của job sau restart.

## 17. Câu hỏi tự kiểm tra

**1.** `CompletableFuture<Integer>` cần nhân 2 kết quả sau khi có dữ liệu. Dùng gì?  
**Đáp:** `thenApply(x -> x * 2)`; callback nhận một **giá trị**, trả giá trị khác.

**2.** Sau khi lấy `userId`, cần gọi `fetchOrdersAsync(userId)` trả `CompletableFuture<List<Order>>`. Dùng gì?  
**Đáp:** `thenCompose(userId -> fetchOrdersAsync(userId))`, vì callback trả một stage.

**3.** Lấy tỷ giá và phí vận chuyển từ hai nguồn độc lập, rồi cộng/ghép. Dùng gì?  
**Đáp:** Khởi động cả hai, rồi `thenCombine` khi cả hai sẵn sàng.

**4.** `allOf(f1, f2)` trả `CompletableFuture<List<T>>` đúng hay sai?  
**Đáp:** Sai. Nó trả `CompletableFuture<Void>`; lấy kết quả từng future sau khi cả nhóm hoàn thành bình thường.

**5.** `anyOf(f1, f2)` có bảo đảm bỏ qua future lỗi và lấy kết quả thành công không?  
**Đáp:** Không. Future đầu tiên hoàn thành ngoại lệ có thể làm `anyOf` hoàn thành ngoại lệ.

**6.** Khác nhau giữa `thenApply` và `thenApplyAsync` không truyền executor?  
**Đáp:** `thenApply` dùng quy tắc completion không-async; `thenApplyAsync` mặc định dùng executor bất đồng bộ của `CompletableFuture` (thường common pool), không tự động dùng Spring pool.

**7.** `orTimeout(1, SECONDS)` có dừng JDBC query đang chạy không?  
**Đáp:** Không. Nó hoàn thành future ngoại lệ khi quá hạn; cần timeout/cancel ở client/driver/resource nếu muốn chặn công việc thật.

**8.** `@Async` service trả `CompletableFuture`, nhưng caller gọi `join` ngay trong controller. Controller có hoàn toàn non-blocking không?  
**Đáp:** Không. `join` vẫn có thể chặn thread caller.

**9.** `handle` và `whenComplete` đều nhận `(value, error)`; có dùng thay thế nhau hoàn toàn được không?  
**Đáp:** Không. `handle` **biến đổi** kết quả/lỗi thành stage mới; `whenComplete` dùng để **quan sát** và thường giữ kết quả/lỗi gốc.

**10.** Callback gọi `join()` đợi task nằm trong chính executor có một worker; rủi ro gì?  
**Đáp:** Starvation/deadlock vì worker duy nhất đang chờ thay vì chạy task được xếp hàng. Dùng `thenCompose` và tránh blocking trong continuation.

## 18. Kết luận và tài liệu chính thức

**`CompletableFuture` hữu ích vì mô tả được đồ thị phụ thuộc giữa các bước:**

- **Tuần tự phụ thuộc:** `thenApply` cho biến đổi đồng bộ, `thenCompose` khi bước kế tiếp trả một future.
- **Ghép song song:** `thenCombine` với hai nguồn độc lập; `allOf` cho nhiều nguồn.
- **Rẽ nhánh:** `anyOf` khi muốn kết quả hoàn thành sớm nhất và chấp nhận cả khả năng lỗi; chọn API khác nếu muốn “thành công đầu tiên”.
- **Lỗi:** `exceptionally`, `handle`, `whenComplete`, cùng ranh giới lỗi rõ ràng.
- **Executor:** callback không-Async và Async có hành vi scheduling khác nhau; truyền executor tường minh khi cần kiểm soát tài nguyên.
- **Vận hành:** tránh `join` trong worker, dùng timeout/cancel thực, bounded concurrency, quan sát future lỗi; `CompletableFuture` không thay thế durable job queue.

Tài liệu tham khảo:

- [Java SE 17 — `CompletableFuture` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): mọi combinator, lỗi, timeout, cancellation và quy tắc executor.
- [Java SE 17 — `CompletionStage` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): khái niệm stage và phụ thuộc.
- [Java SE 17 — `ExecutorService` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): quản lý thực thi và shutdown.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, future, executor và exception handling.
- [Spring Framework — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): vì sao self-invocation không đi qua async proxy.