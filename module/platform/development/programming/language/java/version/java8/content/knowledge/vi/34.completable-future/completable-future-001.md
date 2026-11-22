# CompletionStage và mô hình công việc phụ thuộc trong Java

## 1. Mục tiêu: diễn đạt một luồng công việc dưới dạng đồ thị phụ thuộc

Trong ứng dụng, một thao tác thường không phải là **một** hàm chạy rồi kết thúc. Ví dụ để xây trang hồ sơ, hệ thống cần:

1. Tải thông tin người dùng theo ID.
2. Sau khi biết người dùng, **đồng thời có thể** tải hồ sơ chi tiết và tùy chọn giao diện.
3. Chuẩn bị lời chào dựa trên tên, độc lập với nhánh tải hồ sơ.
4. Chỉ khi các dữ liệu cần thiết sẵn sàng mới ghép thành trang kết quả.
5. Nếu một nhánh lỗi, quyết định trả lỗi, hồi phục bằng giá trị dự phòng, hoặc chạy một thao tác thay thế bất đồng bộ.

`java.util.concurrent.CompletionStage<T>` là một giao diện của Java, mô tả **một chặng công việc có thể hoàn tất trong tương lai** và các **chặng kế tiếp phụ thuộc vào kết quả hoặc trạng thái hoàn tất của chặng trước**. Các phương thức như `thenApply`, `thenCompose` và `thenCombine` tạo các **stage mới** và kết nối chúng thành một **đồ thị phụ thuộc**. Đây là API xuất hiện từ Java 8 và vẫn là mô hình cốt lõi đang được sử dụng trong Java hiện đại.

`CompletableFuture<T>` là implementation phổ biến nhất của `CompletionStage<T>`. Nó đồng thời implements `Future<T>`, cung cấp cách tạo, hoàn thành, theo dõi, chờ và hủy một công việc. Cần phân biệt **contract phụ thuộc** của `CompletionStage` với **khả năng quản lý completion** của `CompletableFuture`.

Bài này làm rõ:

- Thế nào là **stage**, **dependency**, **fan-out**, **fan-in**, **composition**, và vì sao mô hình điển hình là đồ thị có hướng không chu trình (DAG).
- Phân biệt xử lý tuần tự phụ thuộc (`thenApply`, `thenCompose`) và xử lý phối hợp nhiều nhánh (`thenCombine`, `allOf`, `anyOf`, `applyToEither`).
- Cách callback được kích hoạt và **ai có thể thực thi callback**, bao gồm biến thể `Async` và `Executor` tường minh.
- Sự lan truyền completion bình thường, lỗi và cancellation; các cách phục hồi `exceptionally`, `handle`, `whenComplete`, `exceptionallyCompose`.
- Cách tổ chức một workflow bất đồng bộ có kiểm thử, timeout và tài nguyên có vòng đời rõ ràng.
- Ví dụ Java 17+ **biên dịch và chạy được**, stdout cố định để dễ đối chiếu.

Bài chỉ dùng những API vẫn còn được hỗ trợ; phương thức hiện đại như `exceptionallyCompose` (Java 12+) và `orTimeout` (Java 9+) sẽ được phân biệt với API gốc Java 8 thay vì suy diễn mọi phương thức đều có trong bản phát hành đầu tiên.

## 2. CompletionStage là gì? CompletableFuture bổ sung điều gì?

### 2.1. Một stage có ba kiểu hoàn tất cần phân biệt

Một `CompletionStage<T>` biểu diễn **kết quả tương lai thuộc kiểu `T`**:

- **Đang chờ:** kết quả/ngoại lệ chưa được xác định, stage chưa hoàn tất.
- **Hoàn tất bình thường:** có kết quả kiểu `T`, **có thể là `null`** nếu contract của stage cho phép.
- **Hoàn tất ngoại lệ:** có lỗi, bao gồm những lỗi phát sinh trong hàm xử lý phụ thuộc. Với `CompletableFuture`, **cancel** được xem là một dạng exceptional completion.

Một stage mới được tạo bằng `thenApply` không phải thao tác chặn luồng gọi để chờ kết quả. Nó mô tả **việc cần làm sau khi upstream hoàn tất bình thường**. Nếu upstream đã hoàn tất sẵn, callback có thể chạy rất sớm, thậm chí ngay khi gắn.

`CompletionStage` tự nó **không có** `get()`, `join()`, `complete()`, `cancel()` hay phương thức tạo `supplyAsync`. Đó là API của `CompletableFuture` hoặc các loại liên quan.

### 2.2. Vai trò của interface và implementation

| Khái niệm | `CompletionStage<T>` | `CompletableFuture<T>` |
| --- | --- | --- |
| Vai trò | Contract phối hợp các stage | Implementation cụ thể của stage và Future |
| Khởi tạo | Không có factory `supplyAsync` trên interface | `supplyAsync`, `runAsync`, constructor, `completedFuture` |
| Gắn continuation | `thenApply`, `thenCompose`, `thenCombine`… | Có tất cả và trả CompletableFuture theo implementation |
| Hoàn tất chủ động | Không định nghĩa | `complete`, `completeExceptionally` |
| Chờ kết quả | Không có `get`/`join` trực tiếp | `get`, `join` |
| Hủy | Không có `cancel` trực tiếp | `cancel` theo chính sách CompletableFuture |
| Timeout | Không định nghĩa `orTimeout` | `orTimeout`, `completeOnTimeout` |
| Khả năng liên thông | `toCompletableFuture()` | `toCompletableFuture()` có thể trả chính instance |

**Nguyên tắc thiết kế API:** Một service có thể trả `CompletionStage<Result>` để người gọi **ghép tiếp công việc** mà không nhất thiết được trao quyền quyết định hoàn tất thủ công. Nếu bạn trả trực tiếp `CompletableFuture`, caller có thể thấy thêm `complete`, `cancel` và những thao tác điều khiển trạng thái.

`CompletionStage` không phải “cách chạy một thread” và bản thân một interface không thể **bắt đầu** một công việc. Một stage có thể đã hoàn tất sẵn, có thể được hoàn tất bởi network callback, timer, queue hoặc một tác vụ trên executor. **Chỉ có graph phụ thuộc** không bảo đảm toàn bộ hệ thống non-blocking nếu các callback bên trong vẫn dùng IO/blocking.

### 2.3. Tạo stage đầu tiên

Các factory thông dụng trên `CompletableFuture`:

```java
CompletionStage<Integer> alreadyDone =
        CompletableFuture.completedFuture(10);

CompletionStage<Integer> background =
        CompletableFuture.supplyAsync(() -> 10, executor);

CompletionStage<Void> sideEffect =
        CompletableFuture.runAsync(() -> doWork(), executor);
```

Đây là **đoạn minh họa**, cần `Executor executor` và `doWork()` được khai báo trong ngữ cảnh. `completedFuture` tạo stage đã hoàn tất; `supplyAsync` chạy `Supplier<T>` trên executor, hoàn tất với giá trị hoặc ngoại lệ; `runAsync` chạy `Runnable` và hoàn tất với kết quả kiểu `Void`.

Có thể tạo một promise chờ external event:

```java
CompletableFuture<String> promise = new CompletableFuture<>();
CompletionStage<Integer> length = promise.thenApply(String::length);

// Một nơi khác, theo quyền sở hữu của promise:
promise.complete("Java");
```

Sau `complete("Java")`, stage `length` có kết quả 4. **Việc tạo promise không tự khởi chạy công việc**; bên sản xuất kết quả phải có trách nhiệm hoàn tất nó đúng lúc.

## 3. Đọc đồ thị phụ thuộc: pipeline, fan-out và fan-in

Một workflow có thể biểu diễn:

```text
                  loadUser(id)
                 /     |       \
                /      |        \
       greet(user)  loadProfile  loadPreferences
                \       \       /
                 \      combine(profile, preference)
                  \               /
                   \             /
                     combine(page)
                          |
                    final result
```

Đồ thị ở đây có:

- **Nodes (đỉnh):** stage hoặc computation được hoàn tất.
- **Edges (cạnh):** quan hệ “đầu ra của node A kích hoạt node B” hoặc “B cần giá trị A”.
- **Pipeline:** A → B → C, các bước có phụ thuộc dữ liệu tuần tự.
- **Fan-out:** một kết quả của A được nhiều bước B, C, D dùng. B và C không nhất thiết phụ thuộc nhau.
- **Fan-in:** hai hoặc nhiều nhánh kết hợp thành một bước sau, ví dụ `thenCombine` hoặc `allOf`.
- **Terminal boundary:** nơi kết quả được đưa ra ngoài API, hoặc nơi caller chủ động chờ/đọc kết quả.

Trong thực tế graph thường được thiết kế như **DAG (directed acyclic graph)**. Nếu vô tình tạo vòng tự phụ thuộc, một stage có thể không bao giờ hoàn thành vì đang chờ chính kết quả của mình. `CompletionStage` không phải một công cụ tự phát hiện mọi vòng phụ thuộc trong business graph.

**Quan trọng:** Dependency chỉ nói **khi nào** stage đủ điều kiện chạy. Nó **không mặc định bảo đảm** thứ tự chạy giữa hai nhánh độc lập, một thread cụ thể, hoặc thời lượng thực thi. Nếu hai nhánh hoàn tất đồng thời, thứ tự callback quan sát được có thể khác qua các lần chạy; code đúng phải dựa vào **giá trị/kết quả cuối**, không dựa vào thứ tự `println` của các nhánh.

## 4. Ba nhóm trigger cơ bản trong CompletionStage

| Nhóm | Điều kiện kích hoạt | API điển hình | Ví dụ |
| --- | --- | --- | --- |
| **Một upstream** | Stage A hoàn tất **bình thường** | `thenApply`, `thenAccept`, `thenRun`, `thenCompose` | Tính tên hiển thị sau khi có user |
| **Cả hai upstream** | A và B đều hoàn tất **bình thường** | `thenCombine`, `thenAcceptBoth`, `runAfterBoth` | Ghép hồ sơ và cấu hình |
| **Một trong hai upstream** | Một kết quả **bình thường** sẵn có theo contract | `applyToEither`, `acceptEither`, `runAfterEither` | Dùng kết quả đầu tiên thỏa điều kiện |
| **Bình thường hoặc lỗi** | Stage hoàn tất theo bất kỳ hướng nào | `handle`, `whenComplete` | Chuẩn hóa kết quả hoặc ghi log |
| **Chỉ lỗi** | Stage hoàn tất ngoại lệ | `exceptionally`, `exceptionallyCompose` | Fallback/recovery |

Mọi continuation tạo **một stage mới**. Các từ trong tên API mang nghĩa:

- `apply` — nhận dữ liệu và **trả một giá trị mới**, kiểu có thể đổi từ T sang U.
- `accept` — nhận dữ liệu và **thực thi hành động**, kết quả stage là `Void`.
- `run` — chạy một `Runnable` **không nhận dữ liệu trước**, kết quả stage là `Void`.
- `compose` — hàm trả về **một CompletionStage khác**; kết quả được flatten thành một stage logic.
- `Combine` — nhận hai giá trị từ hai stage độc lập, trả một giá trị kết hợp.
- `Async` — yêu cầu continuation được sắp lịch theo cơ chế async của implementation hoặc executor được chỉ định.

Không phải tên nào có “Then” cũng có nghĩa nó chạy trên thread mới. `thenApply` bình thường có thể chạy ở thread hoàn thành upstream hoặc caller đăng ký, tùy trạng thái và implementation. Chỉ tin vào những bảo đảm cụ thể của API, không dựa vào kết quả một lần chạy.

## 5. `thenApply`: biến đổi một giá trị sau khi upstream thành công

Đây là dạng cơ bản nhất:

```java
CompletionStage<String> name =
        getUser(userId).thenApply(User::name);
```

Đoạn này là ví dụ **trong một service đã có `getUser`, `userId`, `User`**. `thenApply` chỉ được chạy khi `getUser` hoàn tất bình thường. Nếu công việc tải user lỗi, stage `name` hoàn tất ngoại lệ (trừ khi đã có bước recovery phù hợp) và callback không chạy.

Một ví dụ độc lập trong method:

```java
CompletionStage<Integer> start = CompletableFuture.completedFuture(5);

CompletionStage<Integer> doubled = start.thenApply(n -> n * 2);
CompletionStage<String> printable = doubled.thenApply(Object::toString);
// Khi lấy kết quả: "10".
```

### 5.1. Kiểu dữ liệu trước/sau

Có thể tóm tắt:

```text
CompletionStage<T>
     .thenApply(Function<T,U>)
        => CompletionStage<U>
```

`Function<T,U>` trả **U bình thường**. Nếu hàm trả chính một `CompletionStage<U>`, kết quả của `thenApply` sẽ là **stage lồng bên trong stage**. Đây là lý do cần `thenCompose` ở mục tiếp theo.

### 5.2. Side effect nên ở đâu?

`thenApply` phù hợp với biến đổi dữ liệu. Nếu mục tiêu chỉ gửi log/metric hoặc gọi một hành động không có kết quả, `thenAccept` hay `whenComplete` có thể thể hiện ý định rõ hơn, tùy mục đích và chính sách lỗi.

Không đặt logic có side effect khó rollback trong `thenApply` rồi giả định rằng vì “async” nên nó tự được retry, transaction hoặc đồng bộ. `CompletionStage` chỉ phối hợp completion; không tự quản lý transaction.

## 6. `thenCompose`: bước sau tạo ra một công việc bất đồng bộ khác

Khi bước B **chỉ bắt đầu được sau khi A cung cấp dữ liệu**, và B **trả một CompletionStage**, dùng `thenCompose`:

```java
CompletionStage<User> user = loadUser(id, executor);

CompletionStage<Profile> profile =
        user.thenCompose(u -> loadProfile(u, executor));
```

Phương thức `loadProfile` được gọi khi user đã tải xong và trả một stage cho kết quả hồ sơ. `thenCompose` trả một stage đại diện cho kết quả cuối của công việc ấy, không yêu cầu chặn `join()` ở giữa.

### 6.1. Cạm bẫy stage lồng nhau

**Không đúng kiểu kết quả mong muốn:**

```java
CompletionStage<CompletionStage<Profile>> nested =
        user.thenApply(u -> loadProfile(u, executor));
```

Ở đây `thenApply` không tự “chờ” stage trả về; giá trị U của nó chính là một đối tượng `CompletionStage<Profile>`. Bạn phải xử lý thêm một lớp.

**Đúng:**

```java
CompletionStage<Profile> flat =
        user.thenCompose(u -> loadProfile(u, executor));
```

Tương tự, sơ đồ kiểu:

```text
thenApply:   T -> CompletionStage<U>  => CompletionStage<CompletionStage<U>>
thenCompose: T -> CompletionStage<U>  => CompletionStage<U>
```

Đây là phép **flatten** tương tự `Optional.flatMap`/`Stream.flatMap` về hình dáng kiểu dữ liệu, nhưng ngữ nghĩa thực thi vẫn là completion bất đồng bộ.

### 6.2. Không dùng `join()` trong `thenApply` để giả làm compose

**Anti-pattern:**

```java
CompletionStage<Profile> bad =
        user.thenApply(u -> loadProfile(u, executor)
                              .toCompletableFuture()
                              .join());
```

Đoạn minh họa này có thể **chặn thread chạy callback**. Nếu pool nhỏ và công việc con cần chính pool đó, nguy cơ nghẽn tài nguyên hoặc deadlock tăng lên.

**Sửa:** `user.thenCompose(u -> loadProfile(u, executor))` không chặn thread để đợi kết quả con. Đặc biệt với server nhiều request, giữ graph compose thay vì chèn các `get()`/`join()` ở giữa giúp mô hình rõ ràng và dễ quản lý hơn.

### 6.3. `thenComposeAsync` có giúp công việc con nhanh hơn không?

`thenComposeAsync(fn,executor)` yêu cầu **chính callback tạo stage con** được đưa lên executor. Nó không tự quyết định executor cho toàn bộ công việc bên trong stage trả về. Nếu `fn` gọi API async khác, executor của API đó vẫn theo cách nó được thiết kế.

Đừng hiểu `thenComposeAsync` là “bắt stage con chạy trong một thread mới bằng mọi giá”, hay mặc định nhanh hơn `thenCompose`. Chọn Async khi cần ranh giới scheduling, tách công việc CPU/blocking phù hợp hoặc quyền kiểm soát executor.

## 7. Fan-out: một kết quả cung cấp cho nhiều nhánh

Có thể dùng một stage làm upstream cho nhiều dependent:

```java
CompletionStage<User> user = loadUser(id, executor);

CompletionStage<String> display =
        user.thenApply(u -> "Hello " + u.name());

CompletionStage<Profile> profile =
        user.thenCompose(u -> loadProfile(u, executor));

CompletionStage<String> theme =
        user.thenCompose(u -> loadTheme(u.id(), executor));
```

Khi `user` hoàn tất bình thường, ba continuation có cơ hội bắt đầu. Hai nhánh tải profile và theme **độc lập sau khi đã có user**; chúng có thể tiến hành gần như song song nếu các API/executor thực sự hỗ trợ.

**Không bảo đảm thứ tự giữa các nhánh.** `display`, `profile` và `theme` không được đặc tả phải hoàn tất theo thứ tự code đăng ký. Nếu business logic yêu cầu profile trước theme, phải biểu diễn dependency thật sự, chẳng hạn `profile.thenCompose(p -> ...)`. Không dựa vào thứ tự các dòng nối stage để suy ra thứ tự chạy.

### 7.1. Fan-out không có nghĩa một tác vụ upstream được chạy nhiều lần

Các dependent được nối với **cùng một stage user**. Khi user hoàn tất, mỗi continuation tương ứng được kích hoạt theo contract. Điều này khác với việc gọi `loadUser` lại ba lần rồi tạo ba stage mới.

Khi muốn tránh tải user trùng, tạo **một stage shared** trước và dùng nó cho các nhánh. Nhưng đừng mặc định chia sẻ mọi CompletableFuture lâu dài như một cache: cần chính sách thời hạn, lỗi, memory retention và lifecycle.

### 7.2. Phân biệt concurrency và parallelism

- **Concurrency**: nhiều công việc có thể tiến triển xen kẽ hoặc đồng thời.
- **Parallelism**: nhiều tính toán thực sự chạy cùng lúc trên các thread/CPU.
- Graph CompletionStage mô tả **phụ thuộc completion**, không tự bảo đảm parallelism.
- Một executor đơn luồng có thể chạy các dependent tuần tự dù chúng là hai nhánh logic độc lập.
- Với IO bất đồng bộ thật, công việc có thể chờ network mà không chiếm thread, nhưng điều này phụ thuộc implementation của API IO, không phụ thuộc chỉ riêng CompletionStage.

## 8. Fan-in: `thenCombine` chờ cả hai kết quả

Khi hai nhánh đều phải thành công, có thể ghép:

```java
CompletionStage<String> summary =
        profile.thenCombine(theme,
                (p, t) -> p.city() + " [" + t + "]");
```

`thenCombine` tạo một stage kích hoạt hàm BiFunction khi **cả hai** stage hoàn tất bình thường. Không quan trọng profile hay theme hoàn thành trước; hàm sẽ được gọi khi đã có đủ hai giá trị.

Sơ đồ:

```text
                 loadProfile(user) ----\
                                       thenCombine ---> summary
                 loadTheme(userId) ----/
```

Sau đó có thể ghép tiếp với title:

```java
CompletionStage<String> page = title.thenCombine(
        summary, (a, b) -> a + " | " + b);
```

Nếu một trong hai nhánh lỗi, dependent yêu cầu cả hai **không chạy hàm kết hợp với một giá trị thiếu**; kết quả mang exceptional completion. Nếu cả hai cùng lỗi, **không nên dựa vào việc nguyên nhân nào được chọn** để xuất hiện ở stage kết hợp.

### 8.1. Chọn các biến thể khi không cần trả dữ liệu

- `thenCombine(other, BiFunction)`: cần **hai kết quả**, tạo kết quả U mới.
- `thenAcceptBoth(other, BiConsumer)`: cần hai kết quả để thực hiện một hành động, stage trả `Void`.
- `runAfterBoth(other,Runnable)`: chỉ cần biết cả hai đã hoàn tất bình thường, không dùng kết quả của chúng.
- Các biến thể `...Async` thêm scheduling theo default executor hoặc executor chỉ định.

Chọn API dựa trên **dependency và kiểu output**, không chọn theo cảm giác “Combine nghe có vẻ mạnh hơn”.

### 8.2. Khi nào `thenCombine` tốt hơn hai lần `thenCompose`?

Giả sử profile và theme **không phụ thuộc nhau sau khi biết user**. Nếu viết:

```java
user.thenCompose(u -> loadProfile(u, executor)
        .thenCompose(p -> loadTheme(u.id(), executor)
                .thenApply(themeValue -> combine(p, themeValue))));
```

thì loadTheme chỉ bắt đầu **sau khi loadProfile hoàn tất**. Đây là một chuỗi phụ thuộc tuần tự do code tạo ra, dù nghiệp vụ không cần vậy.

Tốt hơn là tạo hai branch từ `user` rồi `thenCombine`, cho phép hai công việc bắt đầu sau cùng một upstream mà không bắt chờ nhau. Hiệu năng thực tế còn phụ thuộc executor, network, số lượng kết nối và tài nguyên.

## 9. `CompletableFuture.allOf`: barrier cho nhiều công việc

`CompletableFuture.allOf(f1,f2,...,fn)` là **phương thức static của CompletableFuture**, không thuộc interface `CompletionStage`. Nó tạo `CompletableFuture<Void>` hoàn tất khi các future truyền vào đã hoàn tất; nếu có một future thất bại, barrier cũng hoàn tất ngoại lệ.

```java
CompletableFuture<Integer> quantity =
        CompletableFuture.completedFuture(3);
CompletableFuture<Integer> unitPrice =
        CompletableFuture.completedFuture(20);

CompletableFuture<Integer> total =
        CompletableFuture.allOf(quantity, unitPrice)
                .thenApply(ignored -> quantity.join() * unitPrice.join());
// total.join() == 60
```

Lý do các `join()` trong callback này chấp nhận được: callback chỉ chạy **sau khi `allOf` đã hoàn tất bình thường**, tức các future thành phần đã thành công. Chúng đã có giá trị; không có việc chặn để đợi công việc chưa hoàn tất. Đừng sao chép mô hình này thành `join()` ở bất kỳ chỗ nào trước barrier.

### 9.1. `allOf` không tự gom kết quả thành List

`allOf` trả `CompletableFuture<Void>`, **không phải** `CompletableFuture<List<T>>`. Muốn danh sách kết quả theo một thứ tự xác định, phải giữ các future riêng và thu sau barrier.

Ví dụ:

```java
List<CompletableFuture<String>> futures = List.of(
        CompletableFuture.completedFuture("A"),
        CompletableFuture.completedFuture("B"));

CompletableFuture<List<String>> grouped =
        CompletableFuture.allOf(
                futures.toArray(CompletableFuture[]::new))
            .thenApply(ignored -> futures.stream()
                    .map(CompletableFuture::join)
                    .toList());
// [A, B]
```

`Stream.toList()` cần Java 16+, nên mã mẫu trong bài dùng Java 17+. Danh sách kết quả ở đây theo thứ tự của `futures`, không phải thứ tự future hoàn thành.

**Lưu ý:** nếu futures rất nhiều và được tạo ồ ạt, `allOf` **không tự giới hạn concurrency**; phải thiết kế giới hạn fan-out ở nguồn hoặc executor/semaphore/rate limiter, tránh bắn hàng chục nghìn request cùng lúc.

### 9.2. allOf với lỗi

Nếu một future lỗi, barrier cũng lỗi, và callback `thenApply` nối sau barrier không chạy bình thường. Nếu muốn workflow tiếp tục với kết quả một phần, hãy **chủ động phục hồi từng nhánh** bằng `exceptionally`/`handle` hoặc mô hình hóa `Result<T>`/sealed type trước khi gom. Không ngầm dùng `allOf` như “allSettled” của mọi nền tảng.

### 9.3. allOf với mảng rỗng

`CompletableFuture.allOf()` không có đối số trả một future đã hoàn tất với giá trị `null`. Điều này hữu ích với tập công việc rỗng, nhưng business logic có thể vẫn muốn trả một danh sách rỗng thay vì một “tổng hợp thành công” không dữ liệu.

## 10. `applyToEither`, `acceptEither` và `anyOf`: chỉ cần một nhánh

Khi business logic có thể sử dụng **một kết quả thành công** từ hai stage kiểu tương thích:

```java
CompletionStage<Integer> chosen =
        first.applyToEither(second, value -> value * 3);
```

Các biến thể:

- `applyToEither(other, Function)`: lấy một giá trị từ một stage hoàn tất bình thường rồi tính U.
- `acceptEither(other, Consumer)`: xử lý giá trị từ một stage hoàn tất bình thường, trả stage Void.
- `runAfterEither(other, Runnable)`: chạy hành động khi có completion bình thường của một trong hai, không nhận giá trị.

Ví dụ xác định:

```java
CompletableFuture<Integer> first =
        CompletableFuture.completedFuture(4);
CompletableFuture<Integer> unresolved = new CompletableFuture<>();

int result = first.applyToEither(unresolved,
        value -> value * 3).join();
// 12
```

Ví dụ này tránh race và dùng `first` đã hoàn tất sẵn. Trong thực tế hai stage cạnh tranh có thể hoàn thành gần đồng thời, **không được dựa vào thứ tự lựa chọn**. `applyToEither` cũng **không** tự hủy công việc thua cuộc.

### 10.1. Lỗi của nhánh “either”: cần hiểu đúng bảo đảm

Theo contract `CompletionStage`, nếu một trong hai stage lỗi và stage kia bình thường, không có bảo đảm chung rằng dependent “either” nhất thiết đợi và ưu tiên thành công kia trong mọi implementation/timing. Đừng dùng `applyToEither` làm chiến lược “tự động bỏ qua lỗi của nhánh nhanh hơn” mà không kiểm thử và định nghĩa lỗi.

Nếu mục tiêu thật là **trả kết quả thành công đầu tiên, bỏ qua lỗi từng nhánh**, cần thiết kế một phép phối hợp rõ ràng, hoặc biến lỗi thành kết quả có cấu trúc rồi chọn theo policy. “Bất kỳ completion đầu tiên” cũng khác “completion bình thường đầu tiên”.

### 10.2. `CompletableFuture.anyOf` có gì khác?

`CompletableFuture.anyOf(f1,f2,...)` tạo `CompletableFuture<Object>` hoàn tất theo **một future bất kỳ đã hoàn tất đầu tiên**, có thể bình thường **hoặc ngoại lệ**. Vì kiểu output `Object`, bạn có thể mất type safety nếu truyền các future khác kiểu và ép kiểu kết quả tùy tiện.

```java
CompletableFuture<String> a = CompletableFuture.completedFuture("OK");
CompletableFuture<String> b = new CompletableFuture<>();

Object value = CompletableFuture.anyOf(a, b).join();
// "OK" trong ví dụ b còn chờ, a đã hoàn tất.
```

`anyOf` không có đối số trả một future **chưa hoàn tất**, nên có thể treo mã chờ nếu ai đó `join()` nó mà không có nguồn hoàn thành. Luôn xem xét tình huống tập nguồn rỗng.

**Tóm lại:** `applyToEither` hữu ích khi hai stage kiểu T phối hợp và bạn cần map kết quả; `anyOf` có thể phối hợp nhiều CompletableFuture và trả Object. Không coi chúng là hệ thống retry, consensus hoặc cancellation tự động.

## 11. Đồng bộ, Async, Executor: cái gì thực sự chạy ở đâu?

Mỗi continuation thường có ba cách đăng ký:

```java
stage.thenApply(fn);
stage.thenApplyAsync(fn);
stage.thenApplyAsync(fn, executor);
```

Đây là đoạn minh họa với biến `stage`, `fn`, `executor` đã tồn tại.

| Hình thức | Ý nghĩa cốt lõi |
| --- | --- |
| `thenApply(fn)` | Continuation không mang yêu cầu scheduling async riêng; có thể chạy ở luồng hoàn tất upstream hoặc luồng đăng ký |
| `thenApplyAsync(fn)` | Sắp lịch qua **default asynchronous execution facility** của implementation |
| `thenApplyAsync(fn, executor)` | Sắp lịch qua `Executor` truyền vào |
| `thenComposeAsync(fn, executor)` | Sắp lịch việc **tạo ra stage con** trên executor; stage con vẫn có executor/cơ chế riêng |
| `thenCombineAsync(other,fn,executor)` | Sau khi hai upstream đủ điều kiện, callback kết hợp được đưa lên executor |

`CompletableFuture` thông thường dùng `ForkJoinPool.commonPool()` cho các static async factory và callback `Async` không truyền executor, có một số chính sách fallback theo cấu hình. Nhưng **`CompletionStage` interface không cam kết một thread pool chung áp dụng cho mọi implementation**. Với hệ thống server, truyền executor tường minh giúp quản lý tài nguyên và quan sát hành vi tốt hơn.

### 11.1. Không có Async không có nghĩa “chạy trên thread hiện tại luôn”

Nếu upstream chưa hoàn tất, `thenApply` được đăng ký rồi trả về, callback có thể chạy trên thread hoàn tất upstream sau này. Nếu upstream đã hoàn tất, việc gắn callback có thể khiến nó chạy ngay trong caller. Vì vậy không đưa logic dựa vào thread-local, transaction context hay giả định tên thread nếu không có cơ chế context propagation chính thức.

### 11.2. Async không tự làm thao tác blocking thành non-blocking

`CompletableFuture.supplyAsync(() -> blockingHttpCall(), pool)` vẫn có một thread trong pool bị chiếm khi `blockingHttpCall` chờ IO. Nó chỉ **chuyển việc chặn khỏi thread gọi** sang thread pool.

Nếu dùng HTTP async client hoặc event-loop, hãy dùng API trả `CompletionStage` thực sự. Không bọc mọi lời gọi blocking trong `supplyAsync` rồi tuyên bố hệ thống non-blocking. Các giới hạn thread, connection, queue và timeout vẫn cần được thiết kế.

### 11.3. Tránh deadlock do cùng một executor nhỏ

Một anti-pattern điển hình:

```java
CompletableFuture<Integer> computed =
        CompletableFuture.supplyAsync(() -> {
            CompletableFuture<Integer> child =
                    CompletableFuture.supplyAsync(() -> 7, oneThreadPool);
            return child.join(); // Chặn thread duy nhất của oneThreadPool.
        }, oneThreadPool);
```

Đây là đoạn **anti-pattern minh họa**, yêu cầu `Executor oneThreadPool` đã tồn tại. Nếu thread duy nhất đang chờ `child.join()`, công việc child lại đang đợi chính thread đó để được chạy. Kết quả có thể deadlock.

Thay bằng graph:

```java
CompletionStage<Integer> computed =
        CompletableFuture.completedFuture(1)
            .thenCompose(n ->
                CompletableFuture.supplyAsync(() -> 7, oneThreadPool));
```

Ở đây việc kết nối không block thread callback để đợi child; vẫn cần executor thực thi được. Trong production, sizing, queue, giới hạn request và shutdown phải được xác định, không chỉ sửa cú pháp.

### 11.4. Java 21+ virtual threads có loại bỏ dependency graph không?

Không. Virtual threads có thể hữu ích khi bạn dùng API blocking theo mô hình thread-per-task, nhưng **dependency semantics** và yêu cầu phối hợp nhiều nguồn vẫn có ý nghĩa. `CompletionStage` không trở thành legacy chỉ vì Java hiện đại có virtual threads. Chọn mô hình phù hợp với ứng dụng và phiên bản JDK; đừng trộn IO/blocking, cancellation và timeout theo những giả định không có trong contract.

## 12. Hoàn tất bình thường và lỗi: graph chuyển trạng thái như thế nào?

Khi một upstream hoàn tất bình thường:

- `thenApply`, `thenCompose`, `thenAccept`, `thenRun` có cơ hội thực hiện callback.
- Callback có thể thành công và tạo kết quả mới.
- Callback cũng có thể ném exception, khiến **dependent stage** hoàn tất ngoại lệ.

Khi một upstream hoàn tất ngoại lệ:

- Những continuation **yêu cầu upstream bình thường** thường **không chạy callback**.
- Exceptional completion lan xuống các dependent chưa phục hồi; các cause thường được bọc trong `CompletionException` ở ranh giới nhất định.
- Các callback xử lý lỗi như `exceptionally`, `handle`, `whenComplete` được kích hoạt theo semantics riêng.

Ví dụ:

```java
AtomicInteger counter = new AtomicInteger();

CompletableFuture<Integer> source =
        CompletableFuture.failedFuture(
                new IllegalStateException("service down"));

CompletionStage<Integer> skipped = source.thenApply(value -> {
    counter.incrementAndGet();
    return value * 2;
});

int fallback = skipped.exceptionally(error -> 42)
        .toCompletableFuture().join();
// counter.get() == 0
// fallback == 42
```

`failedFuture` được bổ sung trong Java 9; ví dụ trong chương trình Java 17+ đầy đủ ở mục 17. Nó cho thấy callback `thenApply` không bị gọi khi upstream đã lỗi, nhưng recovery sau đó vẫn có thể cung cấp kết quả fallback.

### 12.1. Lỗi từ callback cũng là lỗi của một dependent stage

```java
CompletionStage<Integer> failedTransform =
        CompletableFuture.completedFuture(5)
            .thenApply(value -> {
                throw new IllegalArgumentException("bad value");
            });
```

Đoạn này tạo một dependent lỗi vì callback ném exception. `thenApply` không ném trực tiếp exception cho caller ở thao tác gắn trong mọi trường hợp; quan sát lỗi thông qua kết quả dependent và xử lý đúng vị trí.

**Không bỏ qua stage trả về.** Nếu có `stage.thenAccept(value -> sendMessage(value))` rồi không ai giữ/quan sát dependent trả về, exception trong `sendMessage` có thể không được xử lý theo contract nghiệp vụ. Với hành động quan trọng, gắn logging, recovery hoặc propagate stage tới boundary.

## 13. Phân biệt `exceptionally`, `handle`, `whenComplete`, `exceptionallyCompose`

| API | Khi nào chạy callback? | Trả gì? | Dùng khi nào? |
| --- | --- | --- | --- |
| `exceptionally(fn)` | Chỉ khi upstream **lỗi** | Giá trị dự phòng **cùng kiểu T** | Default/fallback đồng bộ |
| `handle((value,error)->...)` | Khi upstream bình thường **hoặc lỗi** | Giá trị loại **U** bất kỳ | Chuẩn hóa thành Result, chuyển lỗi thành dữ liệu |
| `whenComplete((value,error)->...)` | Cả bình thường **hoặc lỗi** | Stage mới **bảo toàn kết quả/lỗi upstream** nếu callback không lỗi | Logging/metrics/cleanup quan sát |
| `exceptionallyCompose(fn)` | Chỉ khi upstream lỗi | `CompletionStage<T>` làm công việc fallback, được flatten | Retry/fallback bất đồng bộ |
| `exceptionallyAsync` | Khi lỗi và có yêu cầu chạy async | Giá trị dự phòng T | Recovery đồng bộ được sắp lịch riêng |
| `exceptionallyComposeAsync` | Khi lỗi và fallback stage được tạo async | Stage hợp nhất | Recovery bất đồng bộ có scheduling |

### 13.1. `exceptionally`: thay lỗi bằng giá trị dự phòng

```java
CompletionStage<Integer> safe = failure
        .exceptionally(error -> 42);
```

Đây là đoạn minh họa với `failure` thuộc `CompletionStage<Integer>`. Nếu upstream đã thành công, callback không chạy; kết quả được chuyển nguyên theo nhánh thành công. Nếu upstream lỗi, callback trả 42 và **stage mới** hoàn tất bình thường với 42.

**Đặt recovery ở đâu quan trọng:** nếu gắn `exceptionally` vào stage chứa bước parse, bạn có thể chọn fallback cho lỗi parse. Nếu gắn `exceptionally` **ở cuối graph**, nó có thể bắt lỗi từ nhiều nhánh trước và che khuất nguyên nhân cụ thể. Chỉ phục hồi những lỗi mà nghiệp vụ cho phép; không nên mặc định mọi Throwable đều tương đương “không có dữ liệu”.

### 13.2. `handle`: luôn nhận (value, error)

```java
CompletionStage<Integer> recovered = failure.handle(
        (value, error) -> error == null ? value : -1);
```

Khi upstream thành công, `error == null` và `value` có thể là null nếu T cho phép. Khi upstream lỗi, `error != null`. **Không kiểm tra `value == null` để suy ra có lỗi**, vì null có thể là một kết quả bình thường.

`handle` cho phép đổi kiểu:

```java
record Outcome<T>(T value, Throwable failure) {}

CompletionStage<Outcome<Integer>> result =
        source.handle(Outcome::new);
```

Đoạn này cần `source` kiểu `CompletionStage<Integer>`, dùng Java 17+ cho `record`. Kết quả biến lỗi thành dữ liệu có cấu trúc thay vì bắt exception ở boundary, nếu đó là contract được thiết kế.

### 13.3. `whenComplete`: quan sát nhưng không phải recovery

```java
CompletionStage<Integer> observed = source.whenComplete(
        (value, error) -> {
            if (error != null) {
                metrics.incrementFailures();
            }
        });
```

Đoạn này có `source` và `metrics` giả định đã tồn tại. `whenComplete` trả stage mới mang cùng kết quả/lỗi như upstream khi callback không ném thêm exception. Nếu bạn chỉ log rồi `whenComplete` thì lỗi **vẫn phải xử lý ở nơi khác**.

Nếu callback của `whenComplete` tự ném lỗi:

- Upstream thành công → dependent mới có thể lỗi vì callback.
- Upstream đã lỗi → lỗi upstream được **ưu tiên bảo toàn** theo contract, không mặc định bị thay thế bởi exception mới của callback.

Giữ callback quan sát đơn giản, tránh thao tác dễ lỗi để không che luồng xử lý chính.

### 13.4. `exceptionallyCompose`: recovery cũng trả một stage

Khi fallback cần gọi một dịch vụ async khác:

```java
CompletionStage<User> recovered = primaryUser()
        .exceptionallyCompose(error -> backupUser());
```

Đây là đoạn minh họa với hai hàm `primaryUser`/`backupUser` trả `CompletionStage<User>`. Nó làm việc tương tự `thenCompose` nhưng trên **nhánh lỗi**: tạo stage fallback và flatten. Phương thức này có từ **Java 12**, phù hợp Java 17+ và JDK hiện đại.

Đừng dùng `exceptionally(error -> backupUser())` khi upstream kiểu `User`: callback đó trả `CompletionStage<User>` chứ không phải `User`; cần `exceptionallyCompose` hoặc một chiến lược phối hợp khác. Và **không thực hiện retry vô hạn** khi service lỗi; có giới hạn số lần, timeout, idempotency và circuit breaker theo yêu cầu sản phẩm.

## 14. `join`, `get` và ranh giới chờ

`CompletionStage` không định nghĩa thao tác blocking; `CompletableFuture` có:

- `join()`: trả kết quả hoặc ném unchecked `CompletionException` (hay `CancellationException` khi hủy) và có thể chặn cho tới khi hoàn tất.
- `get()`: theo `Future`, có thể ném checked `InterruptedException`/`ExecutionException`.
- `get(timeout, unit)`: chờ tối đa một lượng thời gian, có thể ném `TimeoutException` mà **không tự hoàn tất future**.
- `toCompletableFuture()`: trên CompletionStage, cung cấp một CompletableFuture tương ứng; implementation **có thể** trả chính object nếu vốn là CompletableFuture, hoặc một object khác bảo toàn completion properties.

**Nguyên tắc:** Chỉ chờ ở **boundary thực sự phải đưa kết quả ra giao diện blocking** (ví dụ chương trình dòng lệnh kết thúc, endpoint blocking có timeout rõ). Không chèn `join` ở giữa mọi bước phụ thuộc vì sẽ đánh mất lợi ích composition và dễ gây nghẽn thread pool.

### 14.1. `join()` trong main của demo không làm mẫu cho mọi callback

Chương trình ở mục 17 có `page.toCompletableFuture().join()` **một lần ở nơi in kết quả** để đảm bảo stdout xác định. Các stage bên trong vẫn nối bất đồng bộ. Đó là một boundary chủ động; không có nghĩa trong production mọi business service cũng nên `join()` trước khi trả về.

Với Spring MVC/WebFlux hoặc các framework khác, phải tuân thủ cơ chế thread/reactive của framework; nội dung bài này không giả định môi trường cụ thể.

### 14.2. Exception wrapper tại boundary

Một exception gốc ném trong Supplier/Function có thể được quan sát dưới dạng `CompletionException`, với `getCause()` là nguyên nhân hữu ích. `get()` thường chuyển thành `ExecutionException`, cũng có cause. Không dựa vào chính xác chuỗi message được JVM tạo ra; test type và cause.

Nếu cần logging, tránh log lỗi nhiều lần tại từng node gây spam. Chọn điểm logging phù hợp, vẫn giữ nguyên cause để debug.

## 15. Cancellation không tự chặn mọi công việc đã chạy

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` hoàn tất target future với `CancellationException` nếu chưa hoàn tất. Với `CompletableFuture`, tham số `mayInterruptIfRunning` **không có tác dụng ngắt công việc** theo contract của implementation này; nó không sở hữu một thread cụ thể để luôn interrupt.

Đừng suy luận rằng gọi `cancel(true)` đảm bảo dừng ngay network request, CPU task, hay IO blocking đang diễn ra. Cancellation ở một CompletableFuture là **thay đổi trạng thái completion**, không thay thế một cơ chế hủy tác vụ bên dưới.

### 15.1. Hủy cha và hủy con là hai hướng khác nhau

Khi một CompletableFuture upstream bị hủy, các dependent chưa hoàn tất thường sẽ nhận exceptional completion tương ứng. Tuy nhiên, **hủy riêng dependent con không tự hủy upstream cha**.

Ví dụ xác định:

```java
CompletableFuture<Integer> parent = new CompletableFuture<>();
CompletableFuture<Integer> child =
        parent.thenApply(x -> x + 1);

boolean cancelled = child.cancel(true);
boolean parentStillPending = !parent.isDone();
parent.complete(9);

// cancelled == true
// parentStillPending == true
// parent.join() == 9
// child.isCancelled() == true
```

Điều này đặc biệt quan trọng khi **nhiều nhánh dùng chung một upstream**. Nếu một caller bỏ chờ kết quả A, không được tự động hủy một upstream mà các caller hoặc nhánh khác vẫn cần, trừ khi chính sách ownership cho phép.

### 15.2. Deadline, timeout và underlying task

`CompletableFuture` có từ Java 9:

- `orTimeout(timeout,unit)`: nếu chưa hoàn tất tới hạn, hoàn tất **chính CompletableFuture đó** một cách ngoại lệ với `TimeoutException`.
- `completeOnTimeout(value,timeout,unit)`: nếu chưa hoàn tất tới hạn, hoàn tất **chính CompletableFuture đó** bằng giá trị dự phòng.
- `get(timeout,unit)`: caller chỉ **chờ có giới hạn**, không tự làm future hoàn tất sau khi hết chờ.

Ví dụ:

```java
CompletableFuture<String> fetch = startFetch();
CompletableFuture<String> bounded =
        fetch.orTimeout(2, TimeUnit.SECONDS);
```

Đây là đoạn minh họa với `startFetch` được định nghĩa ngoài ví dụ. **`bounded` về bản chất tham chiếu tới chính `fetch`**, không phải một timeout-stage độc lập. Nếu `fetch` được nhiều nhánh dùng chung, thêm `orTimeout` lên nó sẽ ảnh hưởng cả các nhánh dùng chung khi thời hạn tới.

Timeout cũng **không đảm bảo ngắt** tác vụ IO/CPU cơ sở. Với HTTP/network/database, cần phối hợp timeout của chính client và cancellation nếu API hỗ trợ, tránh request quá hạn vẫn tiêu thụ tài nguyên.

### 15.3. Khi graph có nhiều nhánh, một timeout áp dụng ở đâu?

- Nếu timeout cho **toàn bộ request**, áp dụng tại boundary của workflow hoặc tạo một stage kết quả riêng có chính sách tổng.
- Nếu timeout riêng cho **một cuộc gọi đến service**, áp dụng trên stage của service đó (sau khi cân nhắc share/ownership).
- Nếu một nhánh có fallback, đảm bảo fallback không làm vượt deadline tổng.
- Khi triển khai retry, tổng thời gian của mọi lần thử và backoff cần nằm trong policy đã định.

`CompletionStage` **không tự tạo một “structured scope”** đóng/cancel mọi nhánh con theo lifecycle của request. Việc theo dõi tài nguyên vẫn là trách nhiệm của ứng dụng.

## 16. Vòng đời Executor, tải hệ thống và an toàn dữ liệu

### 16.1. Quản lý ExecutorService

Nếu tạo `ExecutorService` riêng:

```java
ExecutorService pool = Executors.newFixedThreadPool(3);
try {
    // Xây và tiêu thụ graph.
} finally {
    pool.shutdown();
}
```

Đây là dạng rút gọn. Trong chương trình đầy đủ, ví dụ còn dùng `awaitTermination` để kiểm tra shutdown. Trong dịch vụ thực, pool thường được **inject và quản lý tập trung** trong lifecycle ứng dụng; không tạo mới một pool cho mỗi HTTP request nếu không có lý do.

### 16.2. Chọn pool cho loại công việc

- **CPU-bound:** kích thước pool thường gắn với năng lực CPU và chính sách scheduling.
- **Blocking IO:** cần kiểm soát số lượng tác vụ đang chờ, hạn chế queue, giới hạn kết nối và timeout. Một pool tính toán nhỏ không phải nơi phù hợp để block lâu.
- **Async IO thật:** ưu tiên API không chiếm thread khi chờ, nhưng vẫn cần giới hạn số request và tài nguyên nền.
- **Tác vụ rất nhẹ:** đừng buộc mọi `thenApply` thành `thenApplyAsync` nếu overhead scheduling không cần thiết.

Không mặc định “càng nhiều thread càng nhanh”. Đo thực tế workload và theo dõi queue length, latency, saturation, error rate.

### 16.3. Fan-out lớn không có backpressure mặc định

Nếu một stage tạo hàng nghìn downstream task ngay khi hoàn tất, `CompletionStage` không tự áp giới hạn tốc độ/độ sâu/độ rộng. Bạn có thể bị nghẽn executor, rate-limit từ API ngoài, out-of-memory do giữ quá nhiều future hoặc mất khả năng phục vụ request khác.

Cần thiết kế:

- Giới hạn concurrency (semaphore, bounded worker queue, rate limiter).
- Phân trang/chia batch công việc.
- Timeout và khả năng hủy tác vụ nền thật sự.
- Giải phóng tài nguyên và dọn tham chiếu tới stage/callback sau khi hoàn tất.
- Quan sát lối lỗi/timeout trên **mọi nhánh quan trọng**.

### 16.4. Side effect và dữ liệu mutable dùng chung

Stage A và B có thể chạy trên hai thread khác nhau. Nếu cả hai sửa cùng `ArrayList` hoặc object mutable, **data race** có thể xuất hiện. Dùng immutable snapshots, cơ chế đồng bộ hoặc cấu trúc concurrent phù hợp.

Một graph đúng về dependency không tự làm object của application thread-safe. Ví dụ `thenCombine` bảo đảm hai stage đã có kết quả khi callback gọi, nhưng không có nghĩa hai stage trước đó không thể cùng sửa shared mutable state theo cách nguy hiểm.

## 17. Chương trình Java 17+ hoàn chỉnh: pipeline, fan-out/fan-in, lỗi và hủy

Tạo file **`CompletionStageGraphDemo.java`** với nội dung sau. Mọi giá trị sử dụng cho output đều cố định, executor được shutdown, không in tên thread và không dựa vào thứ tự hoàn thành giữa hai nhánh.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class CompletionStageGraphDemo {
    record User(int id, String name) {}
    record Profile(int userId, String city) {}

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static CompletionStage<User> loadUser(int id, Executor executor) {
        return CompletableFuture.supplyAsync(
                () -> new User(id, "Lan"), executor);
    }

    static CompletionStage<Profile> loadProfile(
            User user, Executor executor) {
        return CompletableFuture.supplyAsync(
                () -> new Profile(user.id(), "Ha Noi"), executor);
    }

    static CompletionStage<String> loadTheme(
            int userId, Executor executor) {
        return CompletableFuture.supplyAsync(
                () -> "dark", executor);
    }

    public static void main(String[] args)
            throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(3);

        try {
            // Một upstream, ba nhánh phụ thuộc vào kết quả user.
            CompletionStage<User> user = loadUser(7, pool);

            CompletionStage<String> title =
                    user.thenApply(u -> "Hello " + u.name());
            CompletionStage<Profile> profile =
                    user.thenCompose(u -> loadProfile(u, pool));
            CompletionStage<String> theme =
                    user.thenCompose(u -> loadTheme(u.id(), pool));

            // Chỉ ghép khi hai kết quả đã sẵn sàng.
            CompletionStage<String> details =
                    profile.thenCombine(theme,
                            (p, t) -> p.city() + " [" + t + "]");
            CompletionStage<String> page =
                    title.thenCombine(details,
                            (t, d) -> t + " | " + d);

            String result = page.toCompletableFuture().join();
            check(result.equals("Hello Lan | Ha Noi [dark]"),
                    "page");
            System.out.println("page=" + result);

            // thenApply trả giá trị, thenCompose flatten stage con.
            CompletionStage<Integer> five =
                    CompletableFuture.completedFuture(5);
            System.out.println("mapped=" +
                    five.thenApply(x -> x * 2)
                            .toCompletableFuture().join());
            System.out.println("composed=" +
                    five.thenCompose(x ->
                            CompletableFuture.completedFuture(x * 2))
                            .toCompletableFuture().join());
            System.out.println("explicitExecutorResult=" +
                    five.thenApplyAsync(x -> x + 1, pool)
                            .toCompletableFuture().join());

            // thenAccept nhận dữ liệu, kết quả stage là Void.
            AtomicInteger received = new AtomicInteger(-1);
            five.thenAccept(received::set)
                    .toCompletableFuture().join();
            System.out.println("thenAcceptValue=" + received.get());

            CompletableFuture<Integer> qty =
                    CompletableFuture.completedFuture(3);
            CompletableFuture<Integer> unit =
                    CompletableFuture.completedFuture(20);
            int total = CompletableFuture.allOf(qty, unit)
                    .thenApply(ignored ->
                            qty.join() * unit.join())
                    .join();
            System.out.println("allOfTotal=" + total);

            // Một nhánh hoàn tất sẵn, kết quả either ổn định.
            CompletableFuture<Integer> one =
                    CompletableFuture.completedFuture(4);
            CompletableFuture<Integer> unresolved =
                    new CompletableFuture<>();
            int chosen = one.applyToEither(
                    unresolved, value -> value * 3).join();
            System.out.println("eitherResult=" + chosen);

            // Lỗi upstream khiến thenApply không chạy.
            CompletableFuture<Integer> failed =
                    CompletableFuture.failedFuture(
                            new IllegalStateException("service down"));
            AtomicInteger invoked = new AtomicInteger();
            CompletionStage<Integer> skipped =
                    failed.thenApply(value -> {
                        invoked.incrementAndGet();
                        return value * 2;
                    });

            int fallback = skipped.exceptionally(error -> 42)
                    .toCompletableFuture().join();
            System.out.println("failedDownstreamRuns=" +
                    invoked.get());
            System.out.println("exceptionallyFallback=" + fallback);
            System.out.println("handleFallback=" +
                    failed.handle(
                            (value, error) -> error == null ? value : -1)
                            .join());
            System.out.println("exceptionallyComposeFallback=" +
                    failed.exceptionallyCompose(error ->
                            CompletableFuture.completedFuture(77))
                            .join());

            // whenComplete chỉ quan sát, không xóa lỗi.
            AtomicInteger observed = new AtomicInteger();
            CompletionStage<Integer> observedFailure =
                    failed.whenComplete(
                            (value, error) ->
                                    observed.incrementAndGet());
            boolean propagated = false;
            try {
                observedFailure.toCompletableFuture().join();
            } catch (CompletionException expected) {
                propagated = true;
            }
            check(propagated, "propagate");
            System.out.println("whenCompleteObserved=" +
                    observed.get());
            System.out.println("whenCompleteStillFailed=" +
                    propagated);

            // Hủy riêng stage con KHÔNG tự hủy stage cha.
            CompletableFuture<Integer> upstream =
                    new CompletableFuture<>();
            CompletableFuture<Integer> child =
                    upstream.thenApply(value -> value + 1);
            boolean cancelled = child.cancel(true);
            boolean parentStillPending = !upstream.isDone();
            upstream.complete(9);

            check(cancelled && child.isCancelled()
                    && parentStillPending,
                    "independent cancellation");
            System.out.println("cancelChildLeavesParentPending=" +
                    parentStillPending);
            System.out.println("parentValueAfterCancel=" +
                    upstream.join());
            System.out.println("childCancelled=" +
                    child.isCancelled());

            System.out.println("ALL CHECKS PASSED");
        } finally {
            pool.shutdown();
            check(pool.awaitTermination(
                    5, TimeUnit.SECONDS), "executor shutdown");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac CompletionStageGraphDemo.java
java CompletionStageGraphDemo
```

**Stdout chính xác (không phụ thuộc thứ tự hoàn thành các nhánh):**

```text
page=Hello Lan | Ha Noi [dark]
mapped=10
composed=10
explicitExecutorResult=6
thenAcceptValue=5
allOfTotal=60
eitherResult=12
failedDownstreamRuns=0
exceptionallyFallback=42
handleFallback=-1
exceptionallyComposeFallback=77
whenCompleteObserved=1
whenCompleteStillFailed=true
cancelChildLeavesParentPending=true
parentValueAfterCancel=9
childCancelled=true
ALL CHECKS PASSED
```

### 17.1. Giải thích từng nhóm trong ví dụ

**Pipeline và fan-out/fan-in:**

- `loadUser(7,pool)` sản sinh `User(7,"Lan")`.
- `title` chỉ cần user và tạo `"Hello Lan"`.
- `profile` gọi một stage async mới và được kết hợp bằng `thenCompose`.
- `theme` cũng phụ thuộc user ID nhưng không phụ thuộc profile.
- `details` chờ **cả** profile và theme, rồi ghép `"Ha Noi [dark]"`.
- `page` chờ title và details, tạo `"Hello Lan | Ha Noi [dark]"`. Thứ tự in cuối được cố định bởi việc chờ kết quả cuối, không bởi thời điểm các branch hoàn tất.

**Apply, compose, explicit executor:**

- `thenApply(x->x*2)` biến 5 thành 10.
- `thenCompose(x->completedFuture(x*2))` flatten stage con để có 10.
- `thenApplyAsync(x->x+1,pool)` sắp lịch callback qua executor được truyền, kết quả 6. Demo **không in thread name**, vì thread cụ thể không phải contract của kết quả.

**Chờ nhiều công việc:**

- `allOf(qty,unit)` kết thúc sau khi qty=3, unit=20 đã thành công, rồi nhân ra 60.
- `applyToEither` nhận nhánh `one` đã completedFuture(4), nên ra 12. Nhánh `unresolved` vẫn là một future riêng, không tự bị hủy.

**Xử lý lỗi:**

- `failedFuture` lỗi ngay, `thenApply` phía sau không chạy, nên counter bằng 0.
- `exceptionally` hồi phục bằng 42, `handle` bằng -1, `exceptionallyCompose` bằng stage có kết quả 77.
- `whenComplete` đã được gọi đúng một lần để quan sát lỗi nhưng stage trả về vẫn hoàn tất ngoại lệ; `join` ném `CompletionException` được catch.

**Hủy:**

- Hủy `child` không làm `upstream` hoàn tất hay bị hủy.
- Sau đó `upstream.complete(9)` vẫn thành công, nên parent có giá trị 9 và child vẫn ở trạng thái cancelled.

### 17.2. Vì sao dùng `AtomicInteger` dù ví dụ nhỏ?

`AtomicInteger` là holder có phép cập nhật thread-safe để ghi nhận callback đã được gọi. Đừng dùng biến local mutable không an toàn được lambda capture hoặc một `int[]` chia sẻ giữa các callback chạy trên nhiều thread. Trong code production, logging/metrics có thể dùng những API thread-safe chuyên dụng; ví dụ sử dụng AtomicInteger chỉ để minh họa đếm lượt một cách an toàn.

## 18. Thiết kế service trả CompletionStage thay vì chặn ngay

Một API hướng graph có thể là:

```java
interface UserService {
    CompletionStage<User> findUser(int userId);
}

interface ProfileService {
    CompletionStage<Profile> findProfile(int userId);
}
```

Đây là giao diện minh họa với `User`/`Profile` được khai báo trong domain. Caller có thể compose:

```java
CompletionStage<Profile> stage = users.findUser(id)
        .thenCompose(user ->
                profiles.findProfile(user.id()));
```

**Ưu điểm:** code caller có thể ghép tiếp, timeout hoặc xử lý lỗi mà không bị buộc phải block ngay tại service boundary. Nhưng cần hiểu loại `CompletionStage` cụ thể có thể do framework/client cung cấp; đừng lấy instance từ bên ngoài rồi gọi `toCompletableFuture().complete(...)` và giả định bạn đang điều khiển upstream gốc. `toCompletableFuture` có thể cho một future độc lập giữ cùng completion properties.

### 18.1. Khi service có nhiều nguồn

```java
CompletionStage<AccountView> view = accountService.fetch(id)
        .thenCompose(account -> {
            CompletionStage<Balance> balance =
                    balanceService.fetch(account.id());
            CompletionStage<Preferences> prefs =
                    preferenceService.fetch(account.userId());
            return balance.thenCombine(prefs,
                    (b, p) -> new AccountView(account, b, p));
        });
```

Đây là **đoạn minh họa** dùng các kiểu/factory dịch vụ chưa khai báo trong chương trình chạy đầy đủ. Nó diễn tả:

1. Cần Account trước để biết ID liên quan.
2. Sau đó Balance và Preferences không phụ thuộc nhau, có thể tiến hành song song.
3. AccountView chỉ được tạo sau khi hai kết quả sẵn sàng.

Nếu Balance và Preferences cùng cần một số dữ liệu bổ sung, hãy gắn đúng dependency graph; đừng tạo những cuộc gọi lặp không cần thiết.

### 18.2. Cách gắn logging và recovery theo chính sách

```java
CompletionStage<AccountView> safe = view
        .whenComplete((value, error) -> {
            if (error != null) {
                logger.warn("Unable to build account view", error);
            }
        })
        .exceptionally(error -> defaultView);
```

Đoạn minh họa với `view`, `logger`, `defaultView` tồn tại. `whenComplete` **không chữa lỗi**, `exceptionally` mới trả fallback. Trong sản phẩm, chỉ fallback nếu đúng business policy; một lỗi bảo mật/authorization không nên bị biến thành một account view giả có vẻ hợp lệ.

**Tránh quên chờ/sử dụng stage kết quả cuối.** Nếu bạn gắn callback lên stage rồi không trả stage hoặc không theo dõi nó, một thất bại hậu kỳ có thể bị bỏ sót.

## 19. Unit test và kiểm thử các dependency

### 19.1. Dùng CompletableFuture chưa hoàn tất để kiểm soát thứ tự

Một test dependency không cần dùng `Thread.sleep`:

```java
CompletableFuture<Integer> parent = new CompletableFuture<>();
AtomicInteger calls = new AtomicInteger();

CompletionStage<Integer> child = parent.thenApply(value -> {
    calls.incrementAndGet();
    return value + 1;
});

// Lúc này calls.get() == 0.
parent.complete(10);
// child.toCompletableFuture().join() == 11
// calls.get() == 1
```

Vì parent chỉ hoàn tất sau khi test gọi `complete(10)`, test có thể xác định chính xác **khi nào** callback đủ điều kiện thực thi. Với các biến thể `Async` cần executor, bạn chờ child hoàn tất bằng API thích hợp thay vì lập tức assert callback đã chạy trên thread khác.

### 19.2. Test fan-in

Để kiểm chứng `thenCombine` cần cả hai kết quả:

```java
CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();

CompletionStage<String> both =
        a.thenCombine(b, (x, y) -> x + y);

a.complete("A");
// both.toCompletableFuture().isDone() == false.
b.complete("B");
// both.toCompletableFuture().join().equals("AB") == true.
```

Không cần sleep hoặc lịch thread ngẫu nhiên. Test này chứng minh graph đúng dependency, không chỉ cho kết quả đúng khi dữ liệu đã có sẵn.

### 19.3. Test nhánh lỗi và fallback

- Cho upstream hoàn tất ngoại lệ bằng `completeExceptionally` hoặc `failedFuture`.
- Kiểm tra callback yêu cầu success **không chạy**.
- Kiểm tra `exceptionally`/`handle`/`exceptionallyCompose` tạo đúng kết quả fallback.
- Kiểm tra `whenComplete` chỉ quan sát và error vẫn propagate.
- Kiểm tra lỗi của một nhánh kết hợp làm stage fan-in lỗi theo contract.
- Kiểm tra việc hủy một child không tự hủy upstream.
- Test timeout bằng deadline/policy kiểm soát được, tránh sleep dài làm CI chậm hoặc flaky.

### 19.4. Không assert thứ tự log giữa các branch

Nếu hai branch được chạy trên executor khác nhau, không có bảo đảm branch A log trước branch B. Chỉ assert **thứ tự dependency** và output cuối. Với test concurrency, dùng latch/barrier có kiểm soát hoặc CompletableFuture chủ động hoàn thành; không dựa vào `Thread.sleep(100)` để tạo xác suất “đúng lịch”.

### 19.5. Các tiêu chí nên có

| Test | Dữ liệu | Expected |
| --- | --- | --- |
| Upstream success | `completedFuture(5)` | thenApply → 10 |
| Compose stage con | 5 → future(10) | thenCompose → stage(10), không nested |
| Fan-out | một User | các nhánh có thể dùng cùng user result |
| Fan-in | two independent futures | thenCombine chỉ chạy khi cả hai bình thường |
| allOf | quantity=3, price=20 | tính được 60 sau barrier |
| Either một nhánh sẵn | first=4, second=pending | applyToEither → 12 |
| Upstream failure | IllegalStateException | thenApply không chạy; lỗi propagate |
| Recovery | failedFuture | exceptionally=42, handle=-1 |
| Async recovery | stage fallback | exceptionallyCompose flatten |
| Observer | whenComplete | callback được gọi, lỗi vẫn propagate |
| Hủy child | parent pending | parent không tự cancel |
| Hủy upstream | upstream.cancel | dependent chưa xong nhận exceptional completion |
| Executor riêng | fixed thread pool | kết quả đúng, shutdown được |
| Timeout | pending stage | API và policy lỗi/fallback đúng |
| Tài nguyên | nhiều stages | không chặn pool, không giữ vô hạn |

## 20. Các lỗi phổ biến cần tránh

### Lỗi 1: Dùng `thenApply` cho hàm trả CompletionStage

Dẫn đến stage lồng nhau và có thể phải xử lý hai tầng. **Sửa:** dùng `thenCompose`.

### Lỗi 2: Gọi `join`/`get` trong callback dùng chính executor chật

Có thể làm nghẽn thread pool và deadlock. **Sửa:** ghép graph bằng `thenCompose`, `thenCombine` hoặc `allOf`.

### Lỗi 3: Tưởng viết hai callback liên tiếp nghĩa là hai callback chạy theo thứ tự

Hai dependent gắn vào cùng upstream là fan-out, **không có thứ tự tương đối được đảm bảo**. **Sửa:** biểu diễn dependency trực tiếp nếu cần thứ tự.

### Lỗi 4: Tưởng `thenApplyAsync` đồng nghĩa không blocking

Async chỉ sắp lịch callback trên executor; callback vẫn có thể block. **Sửa:** phân biệt async scheduling và IO non-blocking thật, kiểm soát pool.

### Lỗi 5: Quên Executor khi có blocking IO nhiều

Default common pool có thể không phù hợp với workload blocking hoặc yêu cầu isolation. **Sửa:** dùng IO client async hoặc executor phù hợp và giới hạn số tác vụ.

### Lỗi 6: Không quản lý lifecycle executor

Pool custom có thể giữ thread sống lâu sau khi request kết thúc. **Sửa:** sở hữu pool rõ ràng, shutdown đúng lifecycle; không tạo pool vô hạn.

### Lỗi 7: Nghĩ `allOf` tự trả `List<T>`

Thực tế nó trả `CompletableFuture<Void>`. **Sửa:** giữ danh sách futures và collect kết quả sau barrier.

### Lỗi 8: Dùng `anyOf` làm “first success” có fallback

`anyOf` có thể hoàn tất lỗi nếu future lỗi đầu; còn semantics “either” khi một nhánh lỗi cần xem contract. **Sửa:** viết workflow chọn success theo policy, theo dõi failures rõ.

### Lỗi 9: Dùng `whenComplete` như `catch`

`whenComplete` là observer, lỗi thường tiếp tục lan truyền. **Sửa:** dùng `exceptionally` hoặc `handle` khi thật sự cần recover.

### Lỗi 10: Catch lỗi quá sớm, biến mọi lỗi thành dữ liệu giả

Một upstream lỗi về authorization/network có thể bị che bằng fallback vô tội vạ. **Sửa:** phân loại lỗi theo miền nghiệp vụ, chỉ recover lỗi được chấp nhận.

### Lỗi 11: Đánh đồng `null` với exceptional completion

Một stage có thể hoàn tất bình thường với null. **Sửa:** trong `handle/whenComplete` kiểm tra `error == null`, không kiểm tra `value == null` để kết luận lỗi.

### Lỗi 12: Nghĩ `cancel(true)` sẽ interrupt task nền

Với CompletableFuture, tham số mayInterruptIfRunning không có hiệu lực như FutureTask. **Sửa:** có cancellation protocol phù hợp với service hoặc client underlying.

### Lỗi 13: Hủy một child rồi tưởng parent và sibling tự bị hủy

Hủy child không tự propagate ngược graph. **Sửa:** quản lý ownership, tránh hủy nguồn shared khi một nhánh bỏ cuộc.

### Lỗi 14: Dùng `orTimeout` trên future shared mà quên nó mutate chính future

Ảnh hưởng mọi nhánh đang chờ future đó. **Sửa:** thiết kế timeout tại boundary phù hợp, tránh áp trên shared upstream không sở hữu.

### Lỗi 15: Không giới hạn fan-out và queue

Tạo hàng nghìn request đồng thời có thể gây rate limit, cạn thread/connections/memory. **Sửa:** giới hạn concurrency, phân batch, có backpressure tại hệ thống nguồn.

### Lỗi 16: Không theo dõi stage trả về từ `thenAccept`

Nếu callback có lỗi, lỗi nằm ở dependent trả về mà caller bỏ đi. **Sửa:** giữ/return/observe stage chứa hành động quan trọng.

### Lỗi 17: Dùng shared mutable object trong nhiều branch

Có thể có race, state không nhất quán. **Sửa:** immutable values, snapshot, đồng bộ hoặc concurrent collections phù hợp.

### Lỗi 18: Định nghĩa vòng tự chờ

Một stage chờ chính kết quả của mình có thể không bao giờ hoàn tất. **Sửa:** thiết kế graph không có chu trình, tránh capture future tự tham chiếu và joins trong callback.

### Lỗi 19: Dùng retry không có giới hạn

`exceptionallyCompose` mở đường cho async recovery nhưng không tạo retry policy, delay/backoff hoặc idempotency. **Sửa:** giới hạn số lần retry, deadline tổng và kiểm soát side effects.

### Lỗi 20: Cho rằng CompletableFuture sẽ tự đóng network/file connection

Graph chỉ quản lý completion. **Sửa:** tài nguyên cần được đóng ở phần sở hữu chúng, cả nhánh thành công, lỗi, timeout và cancellation.

## 21. Bài tập có đáp án

**Bài 1.** `thenApply` và `thenCompose` khác nhau thế nào khi hàm trả một future mới?

**Đáp án:** `thenApply` trả `CompletionStage<CompletionStage<U>>`; `thenCompose` flatten thành `CompletionStage<U>`.

**Bài 2.** Cần load user rồi mới load orders theo ID user. Chọn `thenApply` hay `thenCompose`?

**Đáp án:** `thenCompose`, vì loadOrders trả một stage mới và chỉ bắt đầu khi đã có user.

**Bài 3.** Sau khi có user, hai lời gọi profile và theme độc lập. Nối bằng hai `thenCompose` tuần tự hay hai branch rồi `thenCombine`?

**Đáp án:** Tạo hai branch từ cùng upstream user và `thenCombine`, vì các lời gọi không phụ thuộc nhau. Nó cho phép overlap khi executor/IO hỗ trợ.

**Bài 4.** `thenCombine` thực thi hàm BiFunction khi nào?

**Đáp án:** Khi cả hai upstream hoàn tất **bình thường** và đủ dữ liệu. Không quy định branch nào phải hoàn thành trước.

**Bài 5.** `CompletableFuture.allOf(a,b)` trả gì? Có tự tạo List kết quả không?

**Đáp án:** `CompletableFuture<Void>`. Không tự gom List. Có thể gom dữ liệu qua các future thành phần sau khi barrier thành công.

**Bài 6.** `anyOf` nhận hai futures, một lỗi ngay và một thành công sau. Có chắc kết quả trả thành công không?

**Đáp án:** Không. `anyOf` hoàn tất theo một future hoàn thành đầu tiên, có thể là ngoại lệ. Nếu cần first-success, thiết kế riêng theo policy.

**Bài 7.** Tại sao `thenApplyAsync(fn)` không bảo đảm callback dùng executor của ứng dụng?

**Đáp án:** Nó dùng default async facility do implementation quyết định. Truyền `thenApplyAsync(fn, executor)` để yêu cầu dùng executor cụ thể.

**Bài 8.** Khi upstream lỗi, `thenApply` có được gọi không?

**Đáp án:** Không. Callback yêu cầu success không chạy; dependent hoàn tất ngoại lệ trừ khi được phục hồi sau đó.

**Bài 9.** `exceptionally` và `whenComplete` khác nhau thế nào?

**Đáp án:** `exceptionally` trả kết quả fallback khi lỗi, còn `whenComplete` quan sát và thường giữ nguyên lỗi cho stage mới.

**Bài 10.** Trong `handle((value,error)->...)`, `value==null` có luôn nghĩa thất bại không?

**Đáp án:** Không. Stage bình thường vẫn có thể trả null. Kiểm tra `error != null` để biết exceptional completion.

**Bài 11.** `exceptionallyCompose` phù hợp với tình huống nào?

**Đáp án:** Khi fallback/recovery tạo một `CompletionStage<T>` mới, ví dụ gọi dịch vụ dự phòng bất đồng bộ. Phương thức này hỗ trợ từ Java 12+.

**Bài 12.** Nếu hủy `child` thì `parent` và `sibling` có tự hủy không?

**Đáp án:** Không theo mặc định. Hủy một dependent không tự propagate ngược upstream. Cần cơ chế ownership/cancellation riêng.

**Bài 13.** `orTimeout` trả một future mới độc lập hay thay đổi future hiện tại?

**Đáp án:** Với CompletableFuture, nó trả lại **chính future đó** và có thể làm future hoàn tất ngoại lệ khi hết hạn; không tự hủy tác vụ underlying.

**Bài 14.** Vì sao không nên đặt `join` ở giữa một callback chạy trên pool đơn luồng?

**Đáp án:** Công việc con có thể đang chờ chính thread bị block để chạy, dẫn đến deadlock. Dùng composition thay vì blocking.

**Bài 15.** Khi hai stage cùng lỗi và được nối bằng `thenCombine`, có thể dựa vào việc lỗi nào thắng không?

**Đáp án:** Không nên. Contract cho phép exceptional completion tương ứng một trong hai cause khi cả hai lỗi; hãy thu thông tin lỗi của từng nguồn nếu cần audit đầy đủ.

**Bài 16.** Một stage hoàn tất bình thường với `null`. `whenComplete` nhận những gì?

**Đáp án:** `value=null` và `error=null`. Null result khác lỗi.

**Bài 17.** Vì sao graph fan-out không được coi là backpressure?

**Đáp án:** Vì việc nối dependency không tự giới hạn số tác vụ IO, queue, connection hay request được kích hoạt. Hệ thống phải đặt hạn mức riêng.

**Bài 18.** Có thể gọi `thenApply` trên một CompletionStage đã hoàn tất không?

**Đáp án:** Có. Continuation có thể chạy ngay hoặc được thực thi theo policy implementation; không được giả định nó luôn chờ một thread khác.

## 22. Checklist áp dụng production

- [ ] Xác định stage nào thực sự phụ thuộc dữ liệu từ stage nào; tránh biến nhánh độc lập thành chuỗi tuần tự.
- [ ] Dùng `thenApply` khi callback trả **giá trị**, `thenCompose` khi trả **stage khác**.
- [ ] Dùng `thenCombine` cho hai kết quả bắt buộc; `allOf` cho nhiều CompletableFuture và tự thu dữ liệu sau barrier.
- [ ] Chỉ dùng `applyToEither`/`anyOf` khi hiểu chính sách chọn nhánh và exceptional completion.
- [ ] Đã lựa chọn executor và non-async/Async theo workload, không giả định thread cụ thể.
- [ ] Không gọi blocking `join/get` ở giữa callback, nhất là trên executor ít thread.
- [ ] Phân biệt `CompletionStage` interface và `CompletableFuture` implementation, không nhầm quyền complete/cancel.
- [ ] Không bỏ quên stage trả về từ callback có side effects quan trọng.
- [ ] Đã thiết kế logging, exceptional completion, fallback và quyền propagate lỗi theo từng nhánh.
- [ ] Chỉ dùng `whenComplete` để quan sát/cleanup, `exceptionally`/`handle` để recover khi chính sách cho phép.
- [ ] Với fallback async, dùng `exceptionallyCompose` hoặc một flow tương đương được kiểm soát.
- [ ] Nhớ `cancel(true)` không bảo đảm interrupt tác vụ underlying của CompletableFuture.
- [ ] Đã đặt timeout tại boundary hợp lý, biết `orTimeout` mutate chính CompletableFuture.
- [ ] Đã có policy riêng cho retry, idempotency, rate limit, backpressure, pool sizing và shutdown.
- [ ] Giá trị mutable được chia sẻ giữa branch đã được thiết kế thread-safe hoặc dùng immutable snapshot.
- [ ] Unit test dùng CompletableFuture có thể hoàn tất chủ động, không phụ thuộc sleep/thread race.
- [ ] Output cuối được kiểm tra qua đúng boundary; không dựa vào thứ tự in log của các branch.
- [ ] Mọi thông tin trong bài dùng API còn hỗ trợ; chương trình biên dịch với Java 17+.

## Tham khảo chính thức (API hiện hành)

1. [Oracle Java SE 25 — CompletionStage: contract, thenApply, thenCompose, thenCombine, applyToEither, handle, whenComplete và exceptionallyCompose](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionStage.html)
2. [Oracle Java SE 25 — CompletableFuture: supplyAsync, allOf, anyOf, failedFuture, join, cancellation, orTimeout và completeOnTimeout](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
3. [Oracle Java SE 25 — Executor và chính sách thực thi task](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executor.html)
4. [Oracle Java SE 25 — ExecutorService: shutdown, awaitTermination và quản lý vòng đời](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html)
5. [Oracle Java SE 25 — CompletionException: lỗi khi hoàn tất stage](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionException.html)
6. [Oracle Java SE 25 — Future: get và cancellation semantics](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)
7. [Oracle Java SE 25 — TimeUnit: đơn vị thời gian cho timeout](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/TimeUnit.html)

**Ý chính:** `CompletionStage` không chỉ là “chạy async”, mà là **cách biểu diễn điều kiện hoàn tất và phụ thuộc dữ liệu** trong một workflow. Chọn `thenCompose` cho bước cần stage con, `thenCombine` cho hai nhánh cần đồng thời, `allOf` cho nhiều future, và đặt error/cancellation/timeout/Executor tại đúng ranh giới. Đồ thị đúng vừa mô tả logic nghiệp vụ rõ ràng, vừa tránh blocking không cần thiết — nhưng không tự bảo đảm non-blocking IO, thứ tự scheduling, hủy nguồn hay giới hạn tài nguyên.
