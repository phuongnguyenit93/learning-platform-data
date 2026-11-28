# ThenApply, thenCompose và kết hợp kết quả độc lập

Trong Java 27, `CompletableFuture<T>` và `CompletionStage<T>` cho phép mô tả một **đồ thị các tác vụ có quan hệ phụ thuộc** thay vì viết chuỗi lệnh chờ kết quả bằng `get()` hay `join()` ở từng bước. Ba thao tác quan trọng nhất khi tổ chức đồ thị này là:

- **`thenApply`:** biến đổi kết quả của một tác vụ đã hoàn tất bình thường, từ `T` thành `U`.
- **`thenCompose`:** dùng kết quả của tác vụ trước để **khởi tạo một tác vụ bất đồng bộ tiếp theo**, rồi nối thành một stage phẳng `U`.
- **`thenCombine`:** kết hợp kết quả của **hai tác vụ độc lập** khi cả hai đã hoàn tất bình thường; với nhiều tác vụ có thể dùng `CompletableFuture.allOf` rồi thu thập từng kết quả.

Bài thuộc chương **Tác vụ bất đồng bộ** trong module **Java 27 và các kiến thức liên quan**. Những API được trình bày đều là tính năng chính thức của Java SE 27, không cần Preview. Bài tránh những giả định không còn đúng về một thread duy nhất cho mọi tác vụ, về “Async” luôn tạo thread mới, hay về `CompletableFuture.cancel` tự động ngắt được công việc đang chạy.

**Thông điệp chính:** chọn toán tử theo **quan hệ dữ liệu** giữa các tác vụ, rồi mới chọn executor và chính sách lỗi. Hai thao tác độc lập không nên bị xếp tuần tự chỉ vì mã nguồn dễ viết theo thứ tự.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Đọc và khai báo `CompletableFuture<T>` / `CompletionStage<T>` đúng kiểu.
2. Dùng `thenApply` cho phép biến đổi đồng bộ từ giá trị `T` sang `U` mà không tạo future lồng nhau.
3. Dùng `thenCompose` cho phép biến đổi **trả về stage** để làm phẳng `CompletionStage<CompletionStage<U>>` về `CompletionStage<U>`.
4. Thiết kế pipeline theo quan hệ **A → B** so với **A song song với B → kết hợp**.
5. Dùng `thenCombine`, `thenAcceptBoth`, `runAfterBoth` và `allOf` đúng mục đích.
6. Thu thập một danh sách `CompletableFuture<T>` thành `CompletableFuture<List<T>>` mà không dùng unchecked cast.
7. Phân biệt non-Async, Async mặc định và Async có `Executor` tùy chọn.
8. Xử lý exceptional completion, timeout, cancellation và vấn đề chặn thread đúng ranh giới.
9. Nhận diện những mẫu anti-pattern như `thenApply(x -> loadAsync(x).join())` hoặc ép toàn bộ futures độc lập chờ tuần tự.
10. Quyết định khi nào nên dùng `CompletableFuture` thay vì một abstraction khác như structured concurrency.

## 2. CompletionStage là gì, CompletableFuture là gì?

### 2.1. Stage biểu diễn kết quả có thể hoàn tất sau

`CompletionStage<T>` là interface mô tả một giai đoạn của tính toán có thể hoàn tất sau. Nó cung cấp các phép nối tiếp, kết hợp và xử lý lỗi.

`CompletableFuture<T>` triển khai cả `CompletionStage<T>` và `Future<T>`. Ngoài những phép nối stage, nó còn cho phép hoàn tất trực tiếp, lấy kết quả bằng `join()/get()`, kiểm tra trạng thái và áp dụng timeout.

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> completed =
        CompletableFuture.completedFuture(21);

CompletableFuture<Integer> doubled =
        completed.thenApply(value -> value * 2);

System.out.println(doubled.join()); // 42
~~~

`completedFuture(21)` tạo một future đã hoàn tất bình thường. `thenApply` tạo **future mới** đại diện cho phép biến đổi; future nguồn vẫn chứa giá trị `21`.

### 2.2. Stage không nhất thiết đang chạy trên thread riêng

Một `CompletableFuture<T>` có thể:

- Đã hoàn tất tại thời điểm được tạo, ví dụ `completedFuture`.
- Hoàn tất sau nhờ một tác vụ do executor chạy.
- Được hoàn tất từ một callback, event handler hoặc thread khác.
- Hoàn tất bất thường (*exceptionally*) thay vì có giá trị thành công.

Bản thân việc giữ một biến `CompletableFuture<T>` không chứng minh có một thread đang chạy. Future là **đối tượng biểu diễn trạng thái hoàn tất và kết quả**, không phải đồng nghĩa một thread chuyên trách.

### 2.3. Tạo tác vụ với supplyAsync và runAsync

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> name =
        CompletableFuture.supplyAsync(() -> "Java 27");

CompletableFuture<Void> action =
        CompletableFuture.runAsync(() -> System.out.println("Working"));
~~~

- `supplyAsync(Supplier<T>)` nhận công việc trả về một giá trị `T`.
- `runAsync(Runnable)` nhận công việc không trả về giá trị, nên future có kiểu `Void`.
- Các lời gọi trên **lên lịch thực thi** công việc; chúng không chặn caller để lấy kết quả trước khi trả về future.
- Không truyền `Executor` thì `CompletableFuture` thường dùng `ForkJoinPool.commonPool()` theo chính sách API, với trường hợp ngoại lệ được tài liệu hóa khi pool không đáp ứng mức parallelism tối thiểu. Trong thực tế không nên giả định mọi workload phù hợp common pool.

### 2.4. Đồ thị dependency quyết định hành vi

~~~mermaid
flowchart LR
    A[Stage A] --> B[thenApply: biến đổi kết quả]
    B --> C[thenCompose: stage phụ thuộc]
    C --> D[Stage cuối]
~~~

Một stage phụ thuộc chỉ có thể chạy callback thành công khi **stage nguồn hoàn tất bình thường** và điều kiện riêng của toán tử được đáp ứng.

Nếu stage nguồn hoàn tất bất thường, những callback thành công thông thường như `thenApply`, `thenCompose` và `thenCombine` sẽ không được gọi, còn kết quả phụ thuộc có thể hoàn tất bất thường theo contract của `CompletionStage`.

## 3. thenApply: biến đổi giá trị, tương tự map

### 3.1. Chữ ký và kiểu đầu ra

Trên `CompletionStage<T>`, ý tưởng kiểu của `thenApply` là:

~~~java
<U> CompletionStage<U> thenApply(Function<? super T, ? extends U> fn);
~~~

Hàm `fn` nhận kết quả `T` và **trả trực tiếp một giá trị `U`**. Stage mới có kiểu kết quả `U`.

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<String> raw =
        CompletableFuture.completedFuture("  java 27  ");

CompletableFuture<String> normalized =
        raw.thenApply(String::strip)
           .thenApply(String::toUpperCase);

System.out.println(normalized.join()); // JAVA 27
~~~

Đây là một pipeline biến đổi dữ liệu thuần; không cần gọi `join()` ở giữa các bước.

### 3.2. Không nhất thiết phải có thêm tác vụ bất đồng bộ

Ví dụ:

~~~java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture("15")
                .thenApply(Integer::parseInt)
                .thenApply(value -> value + 5);
~~~

Hai lambda chỉ biến đổi giá trị. Không có lý do bắt buộc chúng phải được đưa lên các thread riêng.

`thenApply` **không cam kết** callback chạy trên thread nào. Với implementation `CompletableFuture`, một action non-Async có thể chạy trên thread hoàn tất source hoặc một thread gọi phương thức hoàn tất liên quan. Nếu source đã hoàn tất, callback cũng có thể chạy trong lời gọi gắn thêm stage.

Vì vậy, không dùng `thenApply` như một lời hứa rằng code sẽ không chạy trên request thread, UI thread hoặc event loop. Nếu phép biến đổi nặng, cân nhắc `thenApplyAsync` với executor thích hợp.

### 3.3. Biến đổi sang kiểu khác

~~~java
record User(int id, String name) {}

CompletableFuture<User> userFuture =
        CompletableFuture.completedFuture(new User(7, "Lan"));

CompletableFuture<String> greeting =
        userFuture.thenApply(user -> "Xin chào " + user.name());
~~~

Kiểu ở từng bước:

~~~text
CompletableFuture<User>
    -- thenApply(User -> String) -->
CompletableFuture<String>
~~~

Compiler theo dõi kiểu, nên nếu dùng `thenApply(User::id)` thì stage đích là `CompletableFuture<Integer>`.

### 3.4. Sai lầm: trả về future bên trong thenApply

Giả sử đã có API:

~~~java
static CompletableFuture<String> loadProfileAsync(int userId) {
    return CompletableFuture.completedFuture("profile:" + userId);
}
~~~

Viết:

~~~java
CompletableFuture<Integer> idFuture =
        CompletableFuture.completedFuture(7);

CompletableFuture<CompletableFuture<String>> nested =
        idFuture.thenApply(id -> loadProfileAsync(id));
~~~

Đây là kiểu **lồng future**. Stage bên ngoài thành công khi lambda trả về **đối tượng future bên trong**, kể cả khi future bên trong chưa hoàn tất.

Vấn đề không phải câu lệnh trên sai cú pháp: nó hợp lệ. Nhưng nếu mục tiêu là nhận `CompletableFuture<String>` đại diện cho **kết quả cuối**, cần dùng `thenCompose`.

## 4. thenCompose: nối tác vụ phụ thuộc, tương tự flatMap

### 4.1. Khi kết quả của A quyết định cách chạy B

Giả sử phải lấy `User` trước rồi mới biết `user.id()` để gọi service lấy quyền truy cập:

~~~java
static CompletableFuture<User> loadUserAsync(int id) {
    return CompletableFuture.completedFuture(new User(id, "Lan"));
}

static CompletableFuture<Boolean> canReadAsync(User user) {
    return CompletableFuture.completedFuture(user.id() > 0);
}
~~~

Stage thứ hai **phụ thuộc dữ liệu** từ stage đầu:

~~~java
CompletableFuture<Boolean> canRead =
        loadUserAsync(7)
                .thenCompose(user -> canReadAsync(user));
~~~

Kiểu đầu ra được làm phẳng:

~~~text
CompletableFuture<User>
    -- thenCompose(User -> CompletionStage<Boolean>) -->
CompletableFuture<Boolean>
~~~

### 4.2. Chữ ký của thenCompose

~~~java
<U> CompletionStage<U> thenCompose(
        Function<? super T, ? extends CompletionStage<U>> fn);
~~~

Lambda `fn` trả về **một `CompletionStage<U>`**, thay vì một `U` thông thường. Stage mà `thenCompose` trả về sẽ hoàn tất theo stage được lambda tạo/trao lại.

Ví dụ:

~~~java
CompletableFuture<String> userSummary =
        loadUserAsync(7)
                .thenCompose(user ->
                        canReadAsync(user)
                                .thenApply(canRead ->
                                        user.name() + ": " + canRead));
~~~

Ở đây `canReadAsync(user)` chỉ được gọi sau khi `loadUserAsync(7)` hoàn tất bình thường và tạo ra `user`. Đây là **phụ thuộc đúng thứ tự**, không phải lỗi làm chương trình mất tính bất đồng bộ.

### 4.3. So sánh trực tiếp với thenApply

| Đặc điểm | `thenApply` | `thenCompose` |
|---|---|---|
| Lambda trả về | Giá trị `U` | `CompletionStage<U>` |
| Ý nghĩa | Biến đổi kết quả | Nối một tác vụ bất đồng bộ tiếp theo |
| Loại kiểu nếu lambda trả future | `CompletionStage<CompletionStage<U>>` | `CompletionStage<U>` |
| Tương tự | `Optional.map` / `Stream.map` | `Optional.flatMap` / `Stream.flatMap` |
| Khi dùng | Format, parse, tính toán thuần | Gọi thêm API async dựa trên kết quả bước trước |
| Tác vụ tiếp theo có phụ thuộc dữ liệu bước trước? | Không phải tiêu chí bắt buộc | Thường là lý do chính để dùng |

### 4.4. Không dùng join để “làm phẳng”

**Không nên:**

~~~java
CompletableFuture<Boolean> awkward =
        loadUserAsync(7).thenApply(user -> canReadAsync(user).join());
~~~

`join()` trong lambda có thể **chặn thread đang thực thi callback** để đợi một future khác. Điều này làm mất lợi ích của việc mô tả quan hệ bất đồng bộ bằng stage; trong executor ít thread, nó còn có thể góp phần gây starvation/deadlock nếu công việc được chờ cần chính executor đó.

**Nên:**

~~~java
CompletableFuture<Boolean> natural =
        loadUserAsync(7).thenCompose(user -> canReadAsync(user));
~~~

`thenCompose` không cần block để đợi kết quả của future trong lambda. Nó gắn kết quả của stage trả về vào stage mới.

### 4.5. Không tạo “stage sẽ không bao giờ hoàn tất”

Theo tài liệu `CompletionStage`, function dùng trong `thenCompose` phải sắp xếp để stage trả về **cuối cùng có thể hoàn tất**, nếu muốn pipeline tiến triển.

Ví dụ:

~~~java
CompletableFuture<String> never = new CompletableFuture<>();

CompletableFuture<String> dependent =
        CompletableFuture.completedFuture(1)
                .thenCompose(id -> never);
~~~

Nếu không có code nào gọi `never.complete(...)` hoặc hoàn tất bất thường, `dependent` cũng sẽ chờ mãi. `thenCompose` không tự đặt deadline hoặc tạo kết quả thay cho stage chưa hoàn tất.

## 5. Quan hệ tuần tự và độc lập: phân biệt trước khi chọn API

### 5.1. Hai luồng công việc khác nhau

**Phụ thuộc A → B:**

~~~text
Tìm User ──> lấy user.id ──> tải quyền của User
~~~

B chỉ có thể bắt đầu sau khi A cung cấp dữ liệu cần thiết. Đây là bài toán điển hình của `thenCompose`.

**Độc lập A và B:**

~~~text
             ┌──> tải giá
Bắt đầu ─────┤
             └──> tải tồn kho

Cả hai hoàn tất ──> ghép thành báo giá
~~~

Nếu tải giá không cần kết quả tải tồn kho và ngược lại, có thể khởi tạo **cả hai futures trước khi nối kết quả**. Đây là bài toán điển hình của `thenCombine`.

### 5.2. Tránh biến độc lập thành tuần tự

Giả sử:

~~~java
static CompletableFuture<Integer> priceAsync() {
    return CompletableFuture.completedFuture(100);
}

static CompletableFuture<Integer> stockAsync() {
    return CompletableFuture.completedFuture(4);
}
~~~

Mẫu không cần thiết:

~~~java
CompletableFuture<String> sequential =
        priceAsync().thenCompose(price ->
                stockAsync().thenApply(stock ->
                        "Price=" + price + ", stock=" + stock));
~~~

Cú pháp hợp lệ, nhưng `stockAsync()` chỉ được gọi sau khi `priceAsync()` hoàn tất bình thường. Nếu hai API thực tế thực hiện I/O độc lập, điều này tạo dependency không cần thiết, kéo dài tổng latency.

Mẫu phù hợp hơn:

~~~java
CompletableFuture<Integer> price = priceAsync();
CompletableFuture<Integer> stock = stockAsync();

CompletableFuture<String> combined =
        price.thenCombine(stock, (p, s) ->
                "Price=" + p + ", stock=" + s);
~~~

Với `priceAsync`/`stockAsync` thực sự thực thi bất đồng bộ, hai tác vụ có thể tiến triển đồng thời. Dù vậy, **khả năng song song thực tế** vẫn phụ thuộc executor, nguồn dữ liệu và tài nguyên sẵn có; chỉ viết `thenCombine` không bảo đảm hai tác vụ chắc chắn chạy cùng một thời điểm.

## 6. thenCombine: kết hợp kết quả hai stage độc lập

### 6.1. Chữ ký và điều kiện kích hoạt

~~~java
<U, V> CompletionStage<V> thenCombine(
        CompletionStage<? extends U> other,
        BiFunction<? super T, ? super U, ? extends V> fn);
~~~

Nếu stage đầu cho giá trị `T`, stage còn lại cho giá trị `U`, function kết hợp cả hai thành `V`. Callback được gọi khi **cả hai** stage hoàn tất bình thường.

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> unitPrice =
        CompletableFuture.completedFuture(120);

CompletableFuture<Integer> quantity =
        CompletableFuture.completedFuture(3);

CompletableFuture<Integer> total =
        unitPrice.thenCombine(quantity,
                (price, count) -> price * count);

System.out.println(total.join()); // 360
~~~

`thenCombine` không tự biến input thành các task đang chạy: trong ví dụ trên hai future vốn đã hoàn tất. Muốn có công việc bất đồng bộ thực sự, phải khởi tạo hai lời gọi async riêng hoặc dùng `supplyAsync`/thư viện phù hợp.

### 6.2. Khi một nhánh thất bại

Nếu một trong hai stage không hoàn tất bình thường, BiFunction của `thenCombine` không được chạy và dependent stage hoàn tất bất thường theo quy tắc `CompletionStage`.

Không giả định ngoại lệ của hai nhánh sẽ được tổng hợp đầy đủ. Nếu cả hai đều lỗi, stage kết hợp không có hợp đồng “tự trả một danh sách hai nguyên nhân”; thứ tự/nguồn exception có thể khác theo tiến trình completion. Nếu phải ghi nhận **mọi** lỗi độc lập, cần mô hình hóa outcome từng nhánh rõ ràng trước khi kết hợp.

### 6.3. thenCombine không tự chọn scheduler

Biến thể:

~~~java
CompletableFuture<String> result =
        price.thenCombine(stock,
                (p, s) -> "Price=" + p + ", stock=" + s);
~~~

Không có hậu tố `Async`, nên callback ghép kết quả có thể chạy trong thread hoàn tất một trong hai stage hoặc thread liên quan tới hành động completion. Không thể dựa vào thứ tự hoàn thành A/B để suy ra chính xác thread sẽ chạy callback.

Nếu việc kết hợp nặng CPU hoặc phải chạy trên một executor cụ thể, dùng `thenCombineAsync(other, fn, executor)`.

### 6.4. thenAcceptBoth và runAfterBoth

Khi **không cần trả giá trị** nhưng cần đợi cả hai stage:

~~~java
CompletableFuture<Void> report =
        unitPrice.thenAcceptBoth(quantity, (p, q) ->
                System.out.println("Total = " + (p * q)));
~~~

`thenAcceptBoth` nhận hai kết quả, chạy side effect và trả `CompletableFuture<Void>`.

~~~java
CompletableFuture<Void> markFinished =
        unitPrice.runAfterBoth(quantity,
                () -> System.out.println("Both done"));
~~~

`runAfterBoth` chỉ đợi cả hai hoàn tất bình thường rồi chạy một `Runnable`, **không truyền giá trị** từ hai stage cho callback.

| Phương thức | Cần dữ liệu từ hai stage? | Trả về |
|---|---|---|
| `thenCombine` | Có | Stage của giá trị mới `V` |
| `thenAcceptBoth` | Có | Stage `Void` |
| `runAfterBoth` | Không | Stage `Void` |

## 7. Sơ đồ chọn thenApply, thenCompose, thenCombine

~~~mermaid
flowchart TD
    Start[Đã có một hoặc nhiều CompletionStage] --> Q1{Bước kế tiếp cần gì?}
    Q1 -->|Biến đổi T thành U| Apply[thenApply]
    Q1 -->|Từ T gọi API trả stage U| Compose[thenCompose]
    Q1 -->|Ghép hai kết quả độc lập| Combine[thenCombine]
    Q1 -->|Chờ N futures| All[CompletableFuture.allOf]
    Apply --> Observe[Quan sát completion hoặc trả stage]
    Compose --> Observe
    Combine --> Observe
    All --> Collect[Thu thập từng kết quả sau allOf]
    Collect --> Observe
~~~

**Câu hỏi kiểm tra quan hệ phụ thuộc:** “Nếu bỏ kết quả A đi, có thể bắt đầu B ngay bây giờ không?”

- Nếu **không**, B phụ thuộc A: `thenCompose` thường là lựa chọn phù hợp khi B trả về stage.
- Nếu **có**, B độc lập A: hãy tạo cả hai trước và ghép bằng `thenCombine` hoặc `allOf`.
- Nếu bước sau chỉ tính một giá trị từ A, không có lời gọi async khác: `thenApply`.

## 8. allOf: phối hợp nhiều kết quả độc lập

### 8.1. allOf đợi nhiều CompletableFuture

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<Integer> a = CompletableFuture.completedFuture(10);
CompletableFuture<Integer> b = CompletableFuture.completedFuture(20);
CompletableFuture<Integer> c = CompletableFuture.completedFuture(30);

CompletableFuture<Void> all =
        CompletableFuture.allOf(a, b, c);

all.join();
System.out.println(a.join() + b.join() + c.join()); // 60
~~~

`allOf` trả `CompletableFuture<Void>`. Nó hoàn tất khi **tất cả** futures được truyền vào hoàn tất; nếu có future kết thúc bất thường thì `allOf` cũng hoàn tất bất thường. Các giá trị của từng nhánh không được gộp vào kết quả `Void`.

Nếu mảng đầu vào rỗng, `allOf()` trả một future đã hoàn tất bình thường với giá trị `null`.

### 8.2. allOf không đồng nghĩa chạy song song

~~~java
CompletableFuture<Void> done =
        CompletableFuture.allOf(taskA, taskB, taskC);
~~~

Câu lệnh này chỉ **đăng ký điều kiện hoàn tất tổng hợp**. Nó không lập lịch tác vụ A/B/C nếu chúng chưa được lên lịch; không tạo thread mới; không bảo đảm các nguồn task có khả năng tiến triển.

Phải tạo/khởi động các task trước:

~~~java
CompletableFuture<Integer> left =
        CompletableFuture.supplyAsync(() -> 10);

CompletableFuture<Integer> right =
        CompletableFuture.supplyAsync(() -> 20);

CompletableFuture<Integer> sum =
        left.thenCombine(right, Integer::sum);
~~~

Ở ví dụ này `left` và `right` được schedule độc lập, sau đó mới ghép. Dù cả hai có thể chạy đồng thời, mức độ thực tế phụ thuộc executor và môi trường.

### 8.3. Thu thập danh sách future cùng kiểu

Một utility hữu ích nhận `List<CompletableFuture<T>>` và trả `CompletableFuture<List<T>>`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;

static <T> CompletableFuture<List<T>> sequence(
        List<CompletableFuture<T>> futures) {

    CompletableFuture<?>[] array =
            futures.toArray(CompletableFuture<?>[]::new);

    return CompletableFuture.allOf(array)
            .thenApply(ignored ->
                    futures.stream()
                            .map(CompletableFuture::join)
                            .toList());
}
~~~

**Vì sao `join` ở đây có thể chấp nhận được?** `thenApply` chỉ chạy sau khi `allOf(array)` hoàn tất **bình thường**, khi đó từng future đầu vào cũng đã hoàn tất bình thường. Những `join()` chỉ lấy kết quả đã có, không phải chờ từng tác vụ mới được khởi động.

Khác với `thenApply(x -> doAsync(x).join())` ở mục 4, utility không block để chờ một stage còn đang chạy.

~~~java
List<CompletableFuture<Integer>> items = List.of(
        CompletableFuture.completedFuture(3),
        CompletableFuture.completedFuture(7),
        CompletableFuture.completedFuture(11)
);

CompletableFuture<List<Integer>> values = sequence(items);

System.out.println(values.join()); // [3, 7, 11]
~~~

Kết quả được thu theo **thứ tự danh sách đầu vào**, không phải theo thứ tự từng future hoàn tất.

### 8.4. Không gom hết dữ liệu nếu tập công việc quá lớn

Dù có `allOf`, việc khởi tạo hàng chục nghìn tác vụ I/O đồng thời có thể gây:

- Quá tải API, database connection pool hoặc file descriptor.
- Giữ nhiều object kết quả trong heap trước khi tổng hợp.
- Tăng contention và độ trễ khi bị giới hạn rate.
- Khó kiểm soát failure/cancellation và retry.

Với số lượng tác vụ lớn, nên giới hạn concurrency bằng executor, semaphore, batching, streaming hoặc abstraction có backpressure phù hợp. `allOf` là toán tử completion, **không phải cơ chế tự giới hạn số tác vụ đang chạy**.

### 8.5. CompletableFuture và CompletionStage khác nhau về allOf

`thenApply`, `thenCompose`, `thenCombine` là phương thức của `CompletionStage`; còn `allOf` là **static method trên `CompletableFuture`**.

Nếu đang giữ một `CompletionStage<T>` chung, không thể gọi `CompletionStage.allOf(...)`. Có thể cân nhắc `stage.toCompletableFuture()` khi cần dùng `allOf`, nhưng việc chuyển đổi phải phù hợp hợp đồng của implementation; không ép kiểu tùy tiện sang `CompletableFuture`.

## 9. allOf, anyOf và applyToEither khác nhau

### 9.1. Chờ tất cả hay chờ một?

| Công cụ | Khi nào hoàn tất? | Dạng kết quả | Ghi chú |
|---|---|---|---|
| `thenCombine` | Hai stage hoàn tất bình thường để chạy hàm ghép | `V` | Giữ kiểu hai nhánh |
| `CompletableFuture.allOf` | Mọi future hoàn tất | `Void` | Không tự gom giá trị |
| `CompletableFuture.anyOf` | Một future hoàn tất, bình thường hoặc bất thường | `Object` | Kiểu trả về rộng và có thể hoàn tất exceptional |
| `applyToEither` | Một trong hai stage hoàn tất bình thường để chạy hàm | `U` | Hữu ích cho cùng kiểu kết quả |
| `acceptEither` | Một trong hai stage hoàn tất bình thường để chạy action | `Void` | Không tạo giá trị mới |

### 9.2. anyOf không phải “đợi phần tử thành công đầu tiên” trong mọi trường hợp

~~~java
CompletableFuture<Integer> first = CompletableFuture.completedFuture(1);
CompletableFuture<Integer> second = CompletableFuture.completedFuture(2);

CompletableFuture<Object> any =
        CompletableFuture.anyOf(first, second);
~~~

`anyOf` hoàn tất với kết quả **hoặc lỗi** của một future hoàn tất trước trong cuộc đua. Nếu một future thất bại trước, future tổng hợp cũng có thể thất bại dù các future còn lại có thể thành công sau.

Ngoài ra, đầu ra của `anyOf` là `CompletableFuture<Object>` vì các future đầu vào có thể có kiểu khác nhau. Không nên dùng unchecked cast để tự cho rằng kết quả chắc chắn là kiểu `T`.

### 9.3. applyToEither dùng kết quả hoàn tất bình thường

~~~java
CompletableFuture<String> primary =
        CompletableFuture.completedFuture("primary");

CompletableFuture<String> backup =
        CompletableFuture.completedFuture("backup");

CompletableFuture<String> chosen =
        primary.applyToEither(backup, String::toUpperCase);
~~~

`applyToEither` chạy function với kết quả của một trong hai stage đã hoàn tất bình thường; không bảo đảm một quy tắc ưu tiên cố định nếu cả hai cùng sẵn sàng. Hành vi failure khi các nhánh hoàn tất bất thường cần được đọc theo đặc tả thay vì suy đoán đây là một cơ chế “retry/failover” hoàn chỉnh.

Nếu mục tiêu là thực hiện fallback khi lỗi, `exceptionallyCompose` hoặc một chính sách recovery có kiểm soát thường nói rõ ý định hơn `anyOf`/`applyToEither`.

## 10. Async có nghĩa là gì? Lựa chọn Executor

### 10.1. Các biến thể quan trọng

Với một toán tử như `thenApply`, thường có ba dạng:

~~~java
stage.thenApply(fn);
stage.thenApplyAsync(fn);
stage.thenApplyAsync(fn, executor);
~~~

Tương tự với `thenComposeAsync` và `thenCombineAsync`.

- **Non-Async**: không yêu cầu lên lịch callback vào executor bất đồng bộ riêng; callback có thể chạy ở thread thực hiện completion hoặc tham gia vào completion.
- **Async không truyền executor**: sử dụng cơ chế asynchronous execution mặc định của stage. Với `CompletableFuture` thông thường, thường là `ForkJoinPool.commonPool()`.
- **Async có executor**: đăng ký callback để chạy theo `Executor` được cung cấp; caller chịu trách nhiệm lựa chọn, vòng đời và giới hạn tài nguyên của executor.

`thenApplyAsync` **không hứa tạo một thread mới** và không làm phép tính biến thành non-blocking I/O. Nó chỉ ảnh hưởng **cách lên lịch thực thi callback**.

### 10.2. Callback ngắn, không block thường không cần Async

~~~java
CompletableFuture<String> label =
        userFuture.thenApply(user -> user.name().toUpperCase());
~~~

Đây là phép biến đổi ngắn, không có I/O, thường phù hợp với `thenApply`.

Nếu callback thực hiện CPU-bound transformation lớn, cân nhắc executor riêng:

~~~java
CompletableFuture<Result> analyzed =
        inputFuture.thenApplyAsync(
                input -> analyzeCpuIntensive(input), cpuExecutor);
~~~

Snippet này mang tính cấu trúc: `Result`, `inputFuture`, `analyzeCpuIntensive` và `cpuExecutor` được định nghĩa trong ứng dụng thực tế. Executor phải được cấu hình tương ứng đặc điểm workload.

### 10.3. Ví dụ với virtual-thread-per-task executor

Java 27 hỗ trợ virtual threads ổn định. Với các tác vụ có lời gọi I/O **blocking truyền thống**, có thể cung cấp executor tạo virtual thread cho mỗi task:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    CompletableFuture<String> a =
            CompletableFuture.supplyAsync(() -> "A", executor);
    CompletableFuture<String> b =
            CompletableFuture.supplyAsync(() -> "B", executor);

    String together = a.thenCombine(b, (x, y) -> x + y).join();
    System.out.println(together);
}
~~~

`ExecutorService` được đóng bởi `try`-with-resources; `close()` chờ các task đã nộp hoàn tất theo contract. Đối với ứng dụng sống lâu, hãy quản lý vòng đời executor ở ranh giới service, không tạo một executor mới cho mỗi request mà không có chính sách đóng.

Virtual threads giảm chi phí của nhiều tác vụ chờ I/O trong những trường hợp phù hợp, nhưng **không tăng số lõi CPU** và không bỏ yêu cầu giới hạn database connections, rate limit hoặc memory. `thenApplyAsync` không tự chạy trên virtual thread trừ khi executor được chọn thực sự dùng virtual threads.

### 10.4. Đừng chặn executor trong callback

Ví dụ không nên:

~~~java
CompletableFuture<Integer> risk =
        futureA.thenApply(value ->
                futureB.join() + value);
~~~

Nếu `futureB` chưa hoàn tất, một thread đang chạy callback có thể bị chặn. Nếu các task phụ thuộc cùng một executor giới hạn thread, code có thể gây starvation hoặc deadlock.

Nếu A và B độc lập, nên:

~~~java
CompletableFuture<Integer> better =
        futureA.thenCombine(futureB, Integer::sum);
~~~

Nếu B thực sự phải được tạo từ A, dùng `thenCompose`, không dùng `join` để nối stage.

## 11. Exceptional completion và vị trí xử lý lỗi

### 11.1. Một pipeline có thể hoàn tất bất thường

~~~java
CompletableFuture<Integer> parsed =
        CompletableFuture.completedFuture("not-a-number")
                .thenApply(Integer::parseInt);
~~~

Callback `Integer.parseInt` ném `NumberFormatException`; dependent stage sẽ hoàn tất exceptionally. Các bước thành công tiếp sau không được thực thi bình thường.

Đây không phải tình huống `thenApply` trả một giá trị lỗi đặc biệt; stage có **hai kênh kết quả**: hoàn tất thành công hoặc bất thường.

### 11.2. exceptionally: chuyển lỗi thành một giá trị dự phòng

~~~java
CompletableFuture<Integer> safe =
        CompletableFuture.completedFuture("not-a-number")
                .thenApply(Integer::parseInt)
                .exceptionally(error -> 0);

System.out.println(safe.join()); // 0
~~~

`exceptionally` chạy khi upstream hoàn tất bất thường và trả một giá trị thành công thay thế.

Chỉ dùng fallback `0` nếu **0 là giá trị có ý nghĩa** trong contract. Nếu thất bại parse phải được báo cho caller, không nên che lỗi bằng một số mặc định tùy ý.

### 11.3. handle: biến đổi cả thành công và lỗi

~~~java
record Outcome<T>(T value, Throwable error) {
    boolean succeeded() {
        return error == null;
    }
}

CompletableFuture<Outcome<Integer>> observed =
        parsed.handle((value, error) -> new Outcome<>(value, error));
~~~

`handle` nhận cả giá trị và exception (một trong hai có thể là `null`). Nó dùng khi cần mô hình hóa outcome mỗi nhánh để kết hợp hoặc báo cáo lỗi thay vì để exception tự lan truyền.

Lưu ý: completion thành công **cũng có thể mang giá trị null**; nếu dùng `null` để xác định thất bại phải dựa vào tham số `error`, không chỉ `value`.

### 11.4. whenComplete: quan sát, không chủ yếu để phục hồi

~~~java
CompletableFuture<Integer> tracked =
        parsed.whenComplete((value, error) -> {
            if (error != null) {
                System.err.println("Parse failed: " + error);
            }
        });
~~~

`whenComplete` phù hợp ghi metric/log quan sát completion. Nó được thiết kế để truyền tiếp cùng kết quả hoặc ngoại lệ gốc; không giống `handle`, callback không trả giá trị thay thế.

Nếu callback của `whenComplete` tự ném exception, outcome của dependent stage có thể thay đổi theo quy tắc API. Vì vậy side effect nên ngắn, ổn định và không tạo lỗi mới không cần thiết.

### 11.5. exceptionallyCompose: fallback cũng là tác vụ async

Khi lỗi yêu cầu gọi một API dự phòng **trả về future**:

~~~java
static CompletableFuture<String> fromPrimary() {
    return CompletableFuture.failedFuture(
            new IllegalStateException("Primary unavailable"));
}

static CompletableFuture<String> fromBackup() {
    return CompletableFuture.completedFuture("backup-value");
}

CompletableFuture<String> recovered =
        fromPrimary().exceptionallyCompose(error -> fromBackup());
~~~

`exceptionallyCompose` làm phẳng stage dự phòng tương tự cách `thenCompose` làm phẳng stage thành công. Nó phù hợp hơn việc `exceptionally(error -> fromBackup().join())` vì không cần block để chờ fallback.

### 11.6. Xử lý lỗi ở từng nhánh hay sau khi kết hợp?

**Fallback cho mỗi nhánh trước khi kết hợp:**

~~~java
CompletableFuture<Integer> safePrice =
        priceFuture.exceptionally(error -> 0);

CompletableFuture<Integer> safeStock =
        stockFuture.exceptionally(error -> 0);

CompletableFuture<String> result =
        safePrice.thenCombine(safeStock,
                (p, s) -> "price=" + p + ", stock=" + s);
~~~

Cách này cho phép pipeline kết hợp khi mỗi lỗi đều có chính sách fallback hợp lệ. Nhưng nếu `0` gây hiểu lầm rằng giá thật hoặc tồn kho thật bằng 0, đây là thiết kế không an toàn về nghiệp vụ. Thay bằng outcome kiểu hóa hoặc thông báo thất bại rõ ràng.

**Bắt sau khi kết hợp:**

~~~java
CompletableFuture<String> resultOrError =
        priceFuture.thenCombine(stockFuture,
                (p, s) -> "price=" + p + ", stock=" + s)
        .exceptionally(error -> "Not available");
~~~

Cách này có thể đơn giản nếu mọi lỗi đều dẫn tới một response thất bại chung. Nó không bảo đảm kết quả nào trong hai nhánh gây lỗi sẽ được báo riêng đầy đủ.

## 12. join, get và trạng thái completion

### 12.1. join() để lấy kết quả tại boundary

~~~java
CompletableFuture<String> future =
        CompletableFuture.completedFuture("done");

String result = future.join();
~~~

`join()` đợi nếu future chưa hoàn tất. Khi hoàn tất exceptionally, nó có thể ném `CompletionException`, hoặc `CancellationException` nếu future bị hủy.

Vì `join` là blocking operation ở boundary, cần tránh gọi nó trong những callback đang dùng executor bận hoặc event loop, trừ trường hợp đã chắc chắn kết quả hoàn tất (như sau `allOf` hoàn tất bình thường).

### 12.2. get() là API Future với checked exceptions

~~~java
try {
    String result = future.get();
    System.out.println(result);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} catch (java.util.concurrent.ExecutionException e) {
    System.err.println("Task failed: " + e.getCause());
}
~~~

`get()` có thể ném checked `InterruptedException` / `ExecutionException`; `join()` dùng unchecked exception trên đường lỗi. `get(timeout, unit)` còn có thể ném `TimeoutException`.

Chọn API theo ranh giới tích hợp. Trong pipeline stage, ưu tiên tổ chức bằng `thenApply`, `thenCompose` và `thenCombine` thay vì `get` liên tục.

### 12.3. Error vẫn cần được giữ và báo đúng

Một lỗi từ computation có thể bị bọc trong `CompletionException` hoặc `ExecutionException`. Không dùng `error.getMessage()` rồi vứt mất cause trong hệ thống observability.

Khi chuẩn hóa lỗi cho API, giữ chain và phân biệt thất bại do dữ liệu đầu vào, timeout, cancellation, lỗi kết nối hay lỗi lập trình. `CompletableFuture` là cơ chế truyền completion, không thay thế thiết kế contract lỗi nghiệp vụ.

## 13. Timeout và cancellation: điều gì thực sự bị giới hạn?

### 13.1. orTimeout thay đổi outcome của chính CompletableFuture

~~~java
import java.util.concurrent.TimeUnit;

CompletableFuture<String> timed =
        externalCall.orTimeout(2, TimeUnit.SECONDS);
~~~

`orTimeout` khiến **chính future được gọi** hoàn tất exceptionally với `TimeoutException` nếu nó chưa hoàn tất trước thời gian đặt ra. Theo tài liệu API, phương thức trả về **`this`**, không tạo một dependent future mới.

Vì vậy nếu `externalCall` được chia sẻ bởi nhiều caller, đặt timeout trực tiếp trên nó có thể ảnh hưởng các dependent khác. Thiết kế pipeline nên xác định rõ future nào có quyền thay đổi completion và nơi đặt deadline.

### 13.2. completeOnTimeout đưa ra giá trị mặc định

~~~java
CompletableFuture<String> withDefault =
        externalCall.completeOnTimeout("not-available",
                2, TimeUnit.SECONDS);
~~~

`completeOnTimeout` cũng trả **chính future được gọi**, nhưng hoàn tất bình thường với giá trị dự phòng nếu chưa xong trước hạn.

Dùng nó chỉ khi default có nghĩa rõ ràng. Một response `not-available` không thể tự chứng minh request backend đã dừng.

### 13.3. Timeout không tự hủy computation bên dưới

Timeout/cancellation ở tầng `CompletableFuture` thường là thay đổi **trạng thái completion** của future. Chúng không nhất thiết dừng HTTP call, database query hay task đã được executor khởi động.

Đặc biệt, với implementation `CompletableFuture`, tham số `mayInterruptIfRunning` của `cancel(...)` **không được dùng để điều khiển việc xử lý bằng interruption** theo contract hiện hành.

Muốn kiểm soát tài nguyên thực, cần có timeout/cancellation ở đúng API I/O, giới hạn số task, đóng tài nguyên và truyền tín hiệu hủy xuống lớp thực hiện công việc.

### 13.4. Lỗi một nhánh không tự hủy nhánh còn lại

Khi `thenCombine` hoặc `allOf` hoàn tất exceptionally, các tác vụ nguồn không mặc nhiên bị hủy hay rollback. Một nhánh khác có thể vẫn chạy và tạo side effect.

Nếu hệ thống cần **fail-fast và hủy các tác vụ còn lại**, phải thiết kế chính sách này tường minh hoặc chọn abstraction hỗ trợ quản lý lifetime của nhóm tác vụ. Đừng dựa vào việc future tổng hợp đã lỗi để kết luận tất cả công việc bên dưới đã dừng.

## 14. Ví dụ Java hoàn chỉnh: dependent + independent

Lưu mã sau thành `AsyncCompositionDemo.java`. Ví dụ dùng các bản ghi bất biến và `ExecutorService` tạo virtual thread cho mỗi task (ổn định trong Java 27). Không cần database, HTTP server hay thư viện ngoài.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class AsyncCompositionDemo {

    record User(int id, String name) {}
    record Permission(boolean canViewPrice) {}
    record Price(String sku, int amount) {}
    record Stock(String sku, int quantity) {}
    record Offer(String sku, int amount, int quantity) {}

    static CompletableFuture<User> findUserAsync(
            int userId, Executor executor) {

        return CompletableFuture.supplyAsync(
                () -> new User(userId, "Lan"), executor);
    }

    static CompletableFuture<Permission> loadPermissionAsync(
            int userId, Executor executor) {

        return CompletableFuture.supplyAsync(
                () -> new Permission(userId > 0), executor);
    }

    static CompletableFuture<Price> loadPriceAsync(
            String sku, Executor executor) {

        return CompletableFuture.supplyAsync(
                () -> new Price(sku, 125_000), executor);
    }

    static CompletableFuture<Stock> loadStockAsync(
            String sku, Executor executor) {

        return CompletableFuture.supplyAsync(
                () -> new Stock(sku, 8), executor);
    }

    public static void main(String[] args) {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            // Nhánh phụ thuộc: cần User rồi mới gọi quyền truy cập.
            CompletableFuture<User> userFuture =
                    findUserAsync(7, executor);

            CompletableFuture<Permission> permissionFuture =
                    userFuture.thenCompose(user ->
                            loadPermissionAsync(user.id(), executor));

            // Nhánh biến đổi đồng bộ từ User sang chuỗi.
            CompletableFuture<String> greetingFuture =
                    userFuture.thenApply(user ->
                            "Xin chào " + user.name());

            // Hai tác vụ độc lập: bắt đầu cả hai trước khi kết hợp.
            CompletableFuture<Price> priceFuture =
                    loadPriceAsync("SKU-01", executor);

            CompletableFuture<Stock> stockFuture =
                    loadStockAsync("SKU-01", executor);

            CompletableFuture<Offer> offerFuture =
                    priceFuture.thenCombine(stockFuture,
                            (price, stock) -> new Offer(
                                    price.sku(),
                                    price.amount(),
                                    stock.quantity()));

            // Khi cả quyền và offer đã sẵn sàng, tạo nội dung hiển thị.
            CompletableFuture<String> reportFuture =
                    permissionFuture.thenCombine(offerFuture,
                            (permission, offer) -> {
                                if (!permission.canViewPrice()) {
                                    return "Không có quyền xem giá";
                                }

                                return "SKU=" + offer.sku()
                                        + ", price=" + offer.amount()
                                        + ", stock=" + offer.quantity();
                            });

            // Đợi hai nhánh kết quả trước khi đọc tại main().
            CompletableFuture.allOf(greetingFuture, reportFuture).join();

            System.out.println(greetingFuture.join());
            System.out.println(reportFuture.join());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AsyncCompositionDemo.java
java AsyncCompositionDemo
~~~

Kết quả gồm lời chào và báo cáo mặt hàng `SKU-01` có giá `125000`, số lượng `8`. **Thứ tự thực thi nội bộ của các supplier không được cố định**, nhưng câu lệnh in ra sau `allOf(...).join()` được đặt theo thứ tự do `main` quy định.

### 14.1. Đọc đồ thị tác vụ của ví dụ

~~~mermaid
flowchart LR
    U[findUserAsync] --> G[thenApply: greeting]
    U --> C[thenCompose: loadPermissionAsync]
    P[loadPriceAsync] --> O[thenCombine: Offer]
    S[loadStockAsync] --> O
    C --> R[thenCombine: report]
    O --> R
    G --> A[allOf]
    R --> A
~~~

Những quan hệ cần ghi nhớ:

- `loadPermissionAsync` **phụ thuộc** `User`, do đó được gọi trong `thenCompose`.
- `greetingFuture` chỉ biến đổi `User` thành `String`, do đó dùng `thenApply`.
- `loadPriceAsync` và `loadStockAsync` không cần kết quả của nhau, nên bắt đầu riêng rồi dùng `thenCombine`.
- `reportFuture` phụ thuộc **cả** permission và offer.
- `allOf` chỉ dùng để chờ hai nhánh cuối; việc đọc giá trị bằng `join` xảy ra khi cả hai đã hoàn tất bình thường.

### 14.2. Một số lưu ý production

Mẫu demo dùng giá trị cố định, không đại diện cho hoạt động mạng hoặc DB thật. Trong ứng dụng thực:

- Gọi API I/O thật cần deadline, bảo vệ connection pool và giới hạn concurrency.
- Không giữ dữ liệu nhạy cảm trong exception message/log.
- Quyền truy cập phải được kiểm tra **trước khi lộ dữ liệu** ở mọi ranh giới, chứ không chỉ ẩn một chuỗi ở tầng render.
- Thất bại ở bất kỳ nhánh bắt buộc nào cần được chuyển thành outcome thích hợp, không tự mặc định thành success.
- Cần quản lý vòng đời executor theo phạm vi service; ví dụ đóng executor khi ra khỏi `try` là hợp lý cho một ứng dụng console.

## 15. Những hiểu lầm và lỗi thường gặp

| Hiểu nhầm/lỗi | Hệ quả | Cách làm đúng |
|---|---|---|
| `thenApply` và `thenCompose` tương đương | Tạo future lồng nhau hoặc sai type | `thenApply` nhận `T -> U`, `thenCompose` nhận `T -> Stage<U>` |
| `thenApply(x -> async(x).join())` là async tốt | Chặn callback thread, có thể gây starvation | Dùng `thenCompose(x -> async(x))` |
| Hai thao tác độc lập luôn viết trong một chuỗi `thenCompose` | Vô tình tuần tự hóa workload | Tạo cả hai trước, dùng `thenCombine` |
| `thenCombine` tự khởi chạy hai công việc | Hiểu sai về scheduling | Nguồn tasks phải được khởi tạo/lên lịch |
| `thenApplyAsync` luôn sinh thread mới | Sai về executor | Chọn Executor phù hợp và đo workload |
| Không có hậu tố Async nghĩa là callback chạy trên thread caller | Không có bảo đảm thread affinity | Không dựa vào thread cụ thể; dùng executor khi cần |
| `allOf` trả danh sách `T` | Chỉ trả `CompletableFuture<Void>` | Thu kết quả typed riêng sau khi allOf thành công |
| `anyOf` luôn chờ một success | Future lỗi cũng có thể quyết định outcome | Phân biệt race và recovery |
| `allOf` tự hủy các nhánh khi một nhánh thất bại | Nhánh còn lại có thể tiếp tục chạy | Thiết kế cancellation/cleanup riêng |
| `thenCombine` tự gom mọi exception của hai nhánh | Thiếu thông tin lỗi từng nhánh | Dùng `handle`/outcome cho từng nhánh nếu cần |
| `exceptionally(error -> 0)` luôn an toàn | Che lỗi nghiệp vụ dưới dạng 0 | Fallback phải có ngữ nghĩa hợp lệ |
| `whenComplete` được thiết kế để thay giá trị | Không phải mục tiêu của nó | Dùng `handle`/`exceptionally` để biến đổi outcome |
| `orTimeout` tạo stage mới | Nó trả chính future được gọi | Chú ý future dùng chung và mutation |
| `cancel(true)` chắc chắn interrupt công việc CF | API không dùng flag này để điều khiển interruption | Cancellation phải có cơ chế ở lớp chạy thực tế |
| `join` luôn non-blocking | Nó có thể chờ future hoàn tất | Chỉ join ở boundary thích hợp hoặc sau allOf normal |
| Dùng commonPool cho mọi I/O blocking | Có thể tranh chấp tài nguyên | Chọn executor, giới hạn concurrency và timeout phù hợp |
| Dùng virtual threads là không cần backpressure | Có thể quá tải backend/heap | Giới hạn số tác vụ và tài nguyên bên ngoài |

## 16. Checklist thiết kế pipeline CompletableFuture

Trước khi chốt một pipeline bất đồng bộ:

1. **Vẽ dependency graph.** Bước nào cần giá trị bước trước? Bước nào độc lập?
2. **Chọn đúng phép nối.** Biến đổi giá trị dùng `thenApply`; gọi API trả stage dùng `thenCompose`; ghép hai nhánh độc lập dùng `thenCombine`.
3. **Khởi động nhánh độc lập sớm.** Không đưa một tác vụ độc lập vào lambda phụ thuộc nếu nó không cần kết quả upstream.
4. **Giữ type.** Tránh future lồng nhau và unchecked cast khi dùng `allOf`/`anyOf`.
5. **Xác định executor.** CPU-bound và blocking I/O có đặc điểm khác nhau; không mặc định common pool phù hợp mọi việc.
6. **Tránh block trong callback.** Không gọi `join`/`get` để nối một future còn đang chạy khi có toán tử stage tương ứng.
7. **Chọn vị trí xử lý lỗi.** Fallback từng nhánh hay lỗi chung cả pipeline? Có cần giữ nguyên cause?
8. **Quy định deadline.** Timeout của future và timeout của I/O thật là hai khái niệm.
9. **Quản lý cancellation.** Future tổng hợp lỗi/hủy không tự đảm bảo các task nguồn dừng.
10. **Giới hạn concurrency.** Một danh sách lớn futures không được tự động kiểm soát bằng `allOf`.
11. **Quản lý executor lifecycle.** Tạo/đóng có chủ đích, tránh dùng tài nguyên đã bị shutdown.
12. **Kiểm thử.** Success, một nhánh lỗi, nhiều nhánh lỗi, timeout, empty input, cancellation, null result và kết quả hoàn tất khác thứ tự.
13. **Quan sát hệ thống.** Ghi nhận latency, lỗi từng dependency, queueing và saturation của executor.
14. **Ưu tiên API sẵn có.** Nếu cần task lifetime được quản lý thành nhóm và cancellation tập thể, cân nhắc abstraction thiết kế riêng cho nhóm tác vụ thay vì tự chắp vá bằng `allOf`.

## 17. Câu hỏi tự kiểm tra

1. `thenApply` khác `thenCompose` ở kiểu trả về của lambda như thế nào?
2. Nếu `fetchUserAsync` trả `CompletableFuture<User>`, vì sao `thenApply(user -> fetchPermissionsAsync(user))` có thể tạo nested future?
3. Khi nào `thenCompose` giúp tránh một `join()` có nguy cơ chặn thread?
4. Hai HTTP requests không dùng kết quả của nhau nên được bắt đầu trước hay sau khi nối `thenCombine`?
5. `thenCombine` khác `thenAcceptBoth` và `runAfterBoth` về dữ liệu và kiểu kết quả?
6. `CompletableFuture.allOf` trả kết quả có kiểu gì? Làm thế nào lấy lại `List<T>`?
7. Vì sao gọi `join` trong `thenApply` sau khi `allOf` thành công có thể hợp lý?
8. Khi một nhánh của `thenCombine` hoàn tất exceptionally, lambda ghép kết quả có được gọi không?
9. `thenApplyAsync` không có `Executor` dùng cơ chế scheduling nào với `CompletableFuture` thông thường?
10. Một callback non-Async có bảo đảm chạy trong thread gọi `thenApply` không?
11. Khi nào dùng `exceptionally`, `handle`, `whenComplete` và `exceptionallyCompose`?
12. `allOf` hoàn tất exceptionally có nghĩa mọi task con đã bị cancel hay rollback không?
13. `anyOf` có bảo đảm trả success đầu tiên và kiểu `T` từ các input khác kiểu không?
14. `orTimeout` trả một dependent future mới hay mutate future được gọi?
15. Vì sao timeout ở tầng future không đủ để bảo đảm một HTTP request hoặc database query thực sự dừng?
16. Khi nào virtual-thread-per-task executor phù hợp và tại sao vẫn phải giới hạn kết nối tới backend?
17. Vì sao một executor có rất ít worker kết hợp với callback `join` có thể gặp starvation?
18. Trong `AsyncCompositionDemo`, vì sao permission dùng `thenCompose` nhưng offer dùng `thenCombine`?

## 18. Tài liệu chính thức cho Java SE 27

- [Java SE 27 API — CompletionStage](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionStage.html): chữ ký và ngữ nghĩa `thenApply`, `thenCompose`, `thenCombine`, `applyToEither`, `handle` và `whenComplete`.
- [Java SE 27 API — CompletableFuture](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `supplyAsync`, `allOf`, `anyOf`, `join`, `get`, `orTimeout`, `completeOnTimeout`, `cancel` và lựa chọn executor.
- [Java SE 27 API — Executor](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executor.html): hợp đồng lên lịch công việc thay cho giả định mỗi action có một thread mới.
- [Java SE 27 API — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): vòng đời executor, `close` và quản lý task.
- [Java SE 27 API — Executors](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor` và các factory executor khác.
- [Java SE 27 API — CompletionException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CompletionException.html): bọc nguyên nhân khi completion bất thường.
- [Java SE 27 API — ExecutionException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutionException.html): exception khi sử dụng `get`.
- [Java SE 27 API — TimeUnit](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/TimeUnit.html): đơn vị timeout.
