# anyOf và xử lý kết quả hoàn thành trước trong Java

## 1. Vấn đề: nhiều tác vụ cạnh tranh, chỉ cần kết quả đầu tiên

Khi triển khai hệ thống Java, đôi khi bạn gửi **nhiều tác vụ bất đồng bộ** cùng lúc và muốn phản hồi ngay khi **một tác vụ bất kỳ hoàn tất**:

- Hỏi hai replica đọc dữ liệu, chọn phản hồi đến trước để giảm độ trễ.
- Chạy nhiều phép tính độc lập, lấy kết quả nào kết thúc trước.
- Đua một thao tác IO với một tín hiệu hết thời hạn (deadline).
- Đọc kết quả từ cache và service bên ngoài, nhận nguồn trả lời nhanh hơn.
- Chờ một trong nhiều sự kiện để chuyển trạng thái workflow.

`CompletableFuture.anyOf(...)` trong `java.util.concurrent` là công cụ cốt lõi cho mô hình đó. Đây là API được hỗ trợ từ **Java 8**, tiếp tục có mặt trong Java hiện đại.

Tuy nhiên, một hiểu lầm rất nguy hiểm là: **`anyOf` trả về “kết quả thành công đầu tiên”**. Trên thực tế, nó hoàn tất khi **một input hoàn tất đầu tiên**, kể cả khi input ấy **thất bại hoặc bị hủy**. Một input thành công đến sau **không tự sửa được kết quả anyOf đã thất bại**.

Để dùng đúng, bạn cần trả lời năm câu hỏi trước khi chọn `anyOf`:

1. **Thế nào là thắng?** Bất kỳ completion, chỉ completion thành công, hay kết quả thỏa điều kiện chất lượng?
2. **Nếu tác vụ đầu tiên lỗi thì sao?** Trả lỗi ngay, chờ nguồn khác, hay retry?
3. **Dữ liệu kết quả thuộc kiểu gì?** `anyOf` trả `CompletableFuture<Object>`; caller có mất type safety không?
4. **Các tác vụ còn lại phải làm gì?** Tiếp tục chạy, hủy nếu sở hữu được, hay vẫn cần kết quả để cập nhật cache?
5. **Có deadline không?** Hết hạn chờ một kết quả khác với ngắt/bỏ công việc nền.

Bài này thuộc nhóm **“Ghép tác vụ”** của chuyên đề Java 8, tập trung vào **“anyOf và xử lý kết quả hoàn thành trước”**. Tất cả kiến thức và API minh họa đều còn áp dụng trong Java hiện đại; các API bổ sung sau Java 8 được ghi rõ. Chương trình hoàn chỉnh dùng **JDK 17+**, không dựa vào các cách làm lỗi thời.

## 2. Hợp đồng chính xác của CompletableFuture.anyOf

Chữ ký:

```java
public static CompletableFuture<Object> anyOf(
        CompletableFuture<?>... cfs);
```

Các điểm quan trọng của hợp đồng:

- Đầu vào là **một mảng varargs các `CompletableFuture<?>`**, không phải `Future<?>` chung hay `CompletionStage<?>` tùy ý.
- Trả về **một `CompletableFuture<Object>` mới**, được hoàn tất khi **một trong các input** hoàn tất.
- Nếu input thắng **hoàn tất bình thường**, future trả về hoàn tất bình thường với **cùng giá trị**, kể cả `null`.
- Nếu input thắng **hoàn tất ngoại lệ**, future trả về cũng hoàn tất ngoại lệ; quan sát bằng `join()` thường nhận `CompletionException` chứa nguyên nhân lỗi.
- Nếu input thắng **bị cancel**, đó cũng là exceptional completion; output bất thường với nguyên nhân `CancellationException`.
- Nếu truyền **không có future nào**, `anyOf()` trả về **một CompletableFuture chưa hoàn tất**. Đừng gọi `join()` và chờ vô hạn trên kết quả này.
- Nếu chính mảng varargs hoặc **bất kỳ phần tử** là `null`, API ném `NullPointerException`.
- `anyOf` **không tự hủy** những future khác, không rollback side effect của chúng và không bảo đảm thứ tự hoàn thành giữa những input đồng thời.

Các điểm này thuộc hợp đồng API hiện hành của `CompletableFuture`, không phải hành vi tình cờ của một bản JDK.

### 2.1. Hiểu từ “any”: hoàn tất, không phải thành công

`CompletableFuture` có những trạng thái quan sát được như:

| Input A | Input B | Kết quả anyOf điển hình nếu A hoàn tất trước |
| --- | --- | --- |
| A thành công với `"A"` | B vẫn chờ | Thành công với `"A"` |
| A thành công với `null` | B vẫn chờ | Thành công với `null` |
| A ném `IllegalStateException` | B sẽ thành công sau | Thất bại theo lỗi của A |
| A bị `cancel` | B vẫn làm việc | Exceptional completion liên quan `CancellationException` |
| A và B đều đang chờ | Chưa ai hoàn tất | anyOf tiếp tục chờ |
| A và B đều hoàn tất gần đồng thời | Cả hai có kết quả | Một input thắng theo cuộc đua completion, không có thứ tự kết quả được đảm bảo |
| Không có input nào | — | Future trả về vẫn chưa hoàn tất |

**Chú ý:** Nếu bạn đã có nhiều futures **hoàn tất sẵn** trước khi gọi `anyOf`, đừng coi thứ tự phần tử trong varargs là một quy tắc chọn giá trị đáng tin cậy. API chỉ cam kết lấy completion của một input phù hợp, không hứa luôn chọn phần tử đầu, nhỏ nhất hoặc giá trị có timestamp sớm nhất.

### 2.2. Kết quả output được “chốt” sau lần thắng

Khi CompletableFuture đã hoàn tất bình thường hoặc ngoại lệ, một `complete(...)`/`completeExceptionally(...)` tiếp theo không thể đổi trạng thái bằng cơ chế completion bình thường.

Giả sử A thắng với `"FAST"`; B hoàn tất sau với `"SLOW"`. Kết quả `anyOf(A,B)` vẫn là `"FAST"`. Nếu A thắng bằng một exception, B thành công sau cũng **không phục hồi** exception của output.

`CompletableFuture.obtrudeValue`/`obtrudeException` tồn tại cho những trường hợp quản trị rất đặc biệt, nhưng không phải cách triển khai “sửa người thắng” thông thường; không dùng chúng như recovery policy trong bài toán này.

## 3. Ví dụ nhỏ nhất: kiểm soát ai hoàn tất trước

Thay vì dùng `Thread.sleep` và hi vọng một tác vụ “nhanh hơn” theo lịch thread, hãy chủ động tạo hai future chưa hoàn tất:

```java
CompletableFuture<String> slow = new CompletableFuture<>();
CompletableFuture<String> fast = new CompletableFuture<>();

CompletableFuture<Object> first =
        CompletableFuture.anyOf(slow, fast);

fast.complete("FAST");   // Chủ động cho fast hoàn tất trước.
System.out.println(first.join());  // FAST

System.out.println(slow.isDone()); // false
slow.complete("SLOW");

System.out.println(first.join());  // Vẫn FAST.
```

Đây là đoạn mã **nằm trong một method** với `import java.util.concurrent.*;`. Kết quả không phụ thuộc race của scheduler, vì test điều khiển thời điểm hoàn tất bằng `complete`.

Dòng `first.join()` **có thể chặn** nếu mọi input chưa hoàn tất; ở ví dụ này ta hoàn tất `fast` trước khi gọi, nên không chặn. Trong production, hạn chế dùng `join()` giữa các callback và thiết kế deadline rõ ràng nếu tác vụ có thể không bao giờ phản hồi.

### 3.1. Sơ đồ thời gian

```text
Thời điểm        future fast        future slow           anyOf(fast, slow)
--------------------------------------------------------------------------------
t0               pending            pending               pending
t1               complete("FAST")   pending               complete("FAST")
t2               done               complete("SLOW")     vẫn "FAST"
--------------------------------------------------------------------------------
```

`anyOf` giúp chọn **kết quả hoàn tất trước**, nhưng không hứa rằng **toàn bộ hệ thống** chỉ thực thi một công việc. `slow` vẫn có thể tiêu thụ CPU/network và gây side effect cho đến khi tự kết thúc hoặc được hủy bằng cơ chế phù hợp.

### 3.2. Nếu A và B thực sự chạy trên hai executor thread

Bạn có thể tạo:

```java
CompletableFuture<String> fromReplicaA =
        CompletableFuture.supplyAsync(
                () -> readFromReplica("A"), executor);

CompletableFuture<String> fromReplicaB =
        CompletableFuture.supplyAsync(
                () -> readFromReplica("B"), executor);

CompletableFuture<Object> first =
        CompletableFuture.anyOf(fromReplicaA, fromReplicaB);
```

Đây là **đoạn minh họa**, cần hàm `readFromReplica` và `Executor executor` đã khai báo. `supplyAsync` thực thi Supplier trên executor; `anyOf` chỉ **quan sát completion**, không tự quyết định nguồn nào được chạy trước. Với hai replica trả dữ liệu khác nhau, kết quả cuối phụ thuộc môi trường, độ trễ, contention và trạng thái hoàn thành.

**Đừng đặt assertion vào tên replica thắng** trong một bài test chạy thực sự song song khi không kiểm soát tín hiệu. Nếu muốn test chắc chắn, dùng `CompletableFuture.complete(...)` hoặc `CountDownLatch` như chương trình đầy đủ phía dưới.

## 4. Lỗi đến đầu tiên: anyOf có thể thất bại dù nguồn sau thành công

Đây là bẫy quan trọng nhất:

```java
CompletableFuture<String> primary = new CompletableFuture<>();
CompletableFuture<String> backup = new CompletableFuture<>();

CompletableFuture<Object> first =
        CompletableFuture.anyOf(primary, backup);

primary.completeExceptionally(
        new IllegalStateException("primary down"));

backup.complete("BACKUP_OK");

// first đã thất bại; "BACKUP_OK" không thay đổi nó.
```

Nếu gọi `first.join()` sẽ nhận exceptional completion; `CompletionException.getCause()` cho bạn nguyên nhân `IllegalStateException`. **Không có rollback hoặc tự động chọn backup**.

Tình huống này đặc biệt phổ biến với **hedged requests**: gọi replica chính và replica dự phòng để lấy dữ liệu nhanh. Nếu replica chính **báo lỗi nhanh hơn**, dùng `anyOf` nguyên bản sẽ làm request fail sớm, dù replica dự phòng có thể trả dữ liệu tốt một lát sau.

### 4.1. Vì sao `exceptionally` ở cuối chưa đủ?

Giả sử:

```java
CompletableFuture<Object> result =
        CompletableFuture.anyOf(primary, backup)
                .exceptionally(error -> "DEFAULT");
```

Khi primary lỗi trước, fallback `"DEFAULT"` được chọn ngay, **không chờ backup**. Đây là một lựa chọn hợp lệ nếu business policy là “bất kỳ lỗi đầu tiên thì dùng DEFAULT”, nhưng **không** phải “tìm nguồn thành công đầu tiên”.

Nếu mục tiêu là **first-success**, cần một thuật toán riêng: cho mỗi input lỗi, ghi nhận nó; chỉ báo thất bại khi **tất cả** input đã lỗi; cho input thành công đầu tiên hoàn tất output. Mục 11 sẽ trình bày một helper Java 17+ đã kiểm thử.

### 4.2. Không che loại lỗi

Một `IllegalArgumentException` do input không hợp lệ, một `TimeoutException` do deadline và một lỗi xác thực/ủy quyền **không nên mặc định** được coi như nhau. Chiến lược first-success chỉ phù hợp nếu business thực sự cho phép tiếp tục đợi nguồn khác sau mỗi lỗi.

Ví dụ với đăng nhập, “một endpoint báo quyền truy cập bị từ chối” không nhất thiết cho phép thử endpoint khác để có kết quả thuận lợi. Lỗi bảo mật hay tác vụ có side effect cần chính sách riêng.

## 5. Cancellation cũng có thể thắng cuộc đua

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` làm future bị hủy hoàn tất **ngoại lệ** bằng `CancellationException`. Theo hợp đồng của `CompletableFuture`, tham số `mayInterruptIfRunning` không được dùng để điều khiển interrupt tác vụ underlying.

```java
CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();
CompletableFuture<Object> first = CompletableFuture.anyOf(a, b);

a.cancel(true);
System.out.println(a.isCancelled());              // true
System.out.println(first.isCompletedExceptionally()); // true
System.out.println(first.isCancelled());          // false với anyOf của demo
System.out.println(b.isDone());                   // false
```

Phân biệt hai trạng thái:

- **Input a** được cancel trực tiếp nên `a.isCancelled()` là true.
- **Output anyOf** được hoàn tất **ngoại lệ theo lỗi của input**, thường có `CompletionException` chứa `CancellationException`. Vì output **không bị gọi cancel trực tiếp**, `first.isCancelled()` không nhất thiết true và trong ví dụ này là false.

**Đừng chỉ kiểm tra `anyOfResult.isCancelled()` để phát hiện một input đã bị cancel.** Hãy quan sát lỗi/`getCause()` và quy ước cancellation của workflow.

### 5.1. Hủy người thắng hoặc người thua không tự hủy các nguồn còn lại

`anyOf` không sở hữu công việc bên trong. Cả khi output hoàn tất bình thường, lỗi hoặc hủy:

- Nguồn khác **vẫn có thể chạy**.
- Hủy output **không tự propagate ngược** để hủy các input.
- Nếu một nguồn được dùng chung cho nhiều request, hủy nó sau khi một request “đã đủ kết quả” có thể làm ảnh hưởng request khác.
- Một HTTP/database request có thể tiếp tục thực hiện dù CompletableFuture bao bọc đã hoàn tất/hủy.

Để tiết kiệm tài nguyên, hãy quản lý **ownership** và dùng API hủy của client/task nền thực sự (khi có), thay vì cho rằng `cancel(true)` luôn ngắt ngay mọi tác vụ.

## 6. Mảng input rỗng, null và kết quả null

### 6.1. `anyOf()` không có input

```java
CompletableFuture<Object> empty = CompletableFuture.anyOf();
System.out.println(empty.isDone()); // false
```

Future này **không tự hoàn tất**, bởi không có input nào làm nó chuyển trạng thái. Không được tự viết:

```java
// Anti-pattern: có thể chờ vô hạn.
Object value = CompletableFuture.anyOf().join();
```

Hãy xác thực số lượng input từ trước:

```java
if (candidates.isEmpty()) {
    throw new IllegalArgumentException("Cần ít nhất một nguồn");
}
```

Đây là đoạn thân method với `candidates` đã được truyền vào. Nếu API muốn chấp nhận danh sách rỗng, cần định nghĩa một hành vi cụ thể như `CompletableFuture.failedFuture(...)` hoặc `completedFuture(defaultValue)`, không để workflow treo.

### 6.2. Một input hoàn tất với `null` vẫn là thành công

```java
CompletableFuture<String> one =
        CompletableFuture.completedFuture(null);
CompletableFuture<String> pending = new CompletableFuture<>();

Object result = CompletableFuture.anyOf(one, pending).join();
// result == null, không có exception.
```

Không dùng `value == null` để suy luận một future thất bại. Trong `whenComplete((value,error)->...)`, cờ nhận biết lỗi là **`error != null`**; giá trị `null` có thể hợp lệ khi stage hoàn tất bình thường.

Nếu trong domain `null` nghĩa là “không tìm thấy” và bạn muốn bỏ qua để đợi nguồn tiếp theo, đó là **policy bổ sung**. Dùng `Optional<T>` hoặc record outcome có trường status để phân biệt “thành công không có dữ liệu” với “kết quả hợp lệ”, rồi viết logic chọn tương ứng.

### 6.3. Không truyền phần tử future null

`CompletableFuture.anyOf((CompletableFuture<?>[]) null)` hoặc mảng chứa `null` dẫn đến `NullPointerException`. Với danh sách từ caller, validate trước hoặc dùng `List.copyOf` để tạo snapshot và từ chối phần tử null.

Không lẫn **một future object null** với **một future hoàn tất bằng kết quả null**. Trường hợp đầu là đối số sai; trường hợp sau có thể hoàn toàn hợp lệ.

## 7. `anyOf` trả `CompletableFuture<Object>`: hiểu hệ quả type safety

Kể cả khi cả hai input đều là `CompletableFuture<String>`:

```java
CompletableFuture<String> a = CompletableFuture.completedFuture("A");
CompletableFuture<String> b = new CompletableFuture<>();

CompletableFuture<Object> result = CompletableFuture.anyOf(a, b);
```

Kiểu compile-time của output vẫn là **`CompletableFuture<Object>`**, không phải `CompletableFuture<String>`. Nguyên nhân: `anyOf` chấp nhận **nhiều future có kiểu khác nhau** qua varargs `CompletableFuture<?>...`.

### 7.1. Nếu tất cả input cùng kiểu, chuyển đổi có kiểm soát

```java
CompletableFuture<String> typed =
        CompletableFuture.anyOf(a, b)
                .thenApply(String.class::cast);
```

Cách này an toàn **theo contract ứng dụng** khi bạn bảo đảm toàn bộ input thắng có kết quả non-null thuộc kiểu `String`. `String.class::cast` cũng chấp nhận `null`, nhưng nếu có một input kiểu khác trong danh sách thì có thể phát sinh `ClassCastException` trong dependent.

Không làm:

```java
// Anti-pattern: cast không được compiler bảo vệ đúng kiểu.
CompletableFuture<String> bad =
        (CompletableFuture<String>) (Object)
                CompletableFuture.anyOf(a, b);
```

Đây là ví dụ sai về generic cast không kiểm chứng; cách ép kiểu thô có thể che lỗi runtime. Với API dùng ở nhiều nơi, cân nhắc tạo wrapper/helper generic có hợp đồng đầu vào đồng nhất.

### 7.2. Nếu nhiều kiểu, trả một result có discriminator

Giả sử race giữa nguồn **cache** và **remote**. Nên đưa thông tin nguồn vào kết quả:

```java
record Reply(String source, String body) {}

CompletableFuture<Reply> fromCache = new CompletableFuture<>();
CompletableFuture<Reply> fromRemote = new CompletableFuture<>();

CompletableFuture<Reply> first =
        CompletableFuture.anyOf(fromCache, fromRemote)
                .thenApply(Reply.class::cast);

fromCache.complete(new Reply("cache", "CACHED"));
fromRemote.complete(new Reply("remote", "FRESH"));

// first.join().source() == "cache".
```

`record` yêu cầu Java 16+, nên ví dụ bài dùng Java 17+. Kết quả thắng cho biết **nguồn nào**, có thể được đưa vào metric và log. Việc output mang `source` không thay đổi tính chất anyOf: nếu một nguồn **lỗi** trước, output vẫn lỗi trừ khi bạn chuyển lỗi thành dữ liệu trước đó.

### 7.3. Khi dùng CompletionStage thay vì CompletableFuture

`anyOf` nhận trực tiếp `CompletableFuture<?>`. Một API của bạn có thể trả `CompletionStage<T>`:

```java
CompletionStage<String> serviceA = requestA();
CompletionStage<String> serviceB = requestB();

CompletableFuture<Object> first = CompletableFuture.anyOf(
        serviceA.toCompletableFuture(),
        serviceB.toCompletableFuture());
```

Đây là đoạn minh họa với `requestA/requestB` đã có. `toCompletableFuture()` là cách chuyển theo contract `CompletionStage`; implementation bên ngoài có thể trả một future biểu diễn cùng completion properties, **không nhất thiết là chính upstream object** mà bạn được phép complete/cancel tùy ý.

**Tránh phụ thuộc vào đặc điểm không được API cam kết** như “chắc chắn trả về cùng instance”, “cancel output sẽ hủy network call”, hay “mọi loại CompletionStage đều do CompletableFuture sở hữu”.

## 8. So sánh với `allOf` và `applyToEither`

| API | Điều kiện hoàn tất chính | Kiểu kết quả | Có tự hủy nhánh còn lại? | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `CompletableFuture.anyOf(a,b,...)` | Một input bất kỳ hoàn tất, **kể cả lỗi** | `CompletableFuture<Object>` | Không | **First completion** |
| `CompletableFuture.allOf(a,b,...)` | **Tất cả** input hoàn tất; nếu có lỗi thì output lỗi | `CompletableFuture<Void>` | Không | **Barrier** |
| `stageA.applyToEither(stageB,fn)` | Một stage hoàn tất **bình thường** để chạy fn, với quy tắc lỗi theo CompletionStage | `CompletionStage<U>` | Không | Hai nhánh, lấy một giá trị bình thường để biến đổi |
| `stageA.acceptEither(stageB,action)` | Một completion bình thường để thực hiện action | `CompletionStage<Void>` | Không | Quan sát/xử lý một giá trị |
| `stageA.runAfterEither(stageB,action)` | Một completion bình thường, không cần kết quả | `CompletionStage<Void>` | Không | Chạy bước tiếp theo |
| Helper `firstSuccess` tự xây | Một input **thành công**, hoặc **mọi input thất bại** | `CompletableFuture<T>` | Không tự động | **First successful result** |

### 8.1. `allOf` khác ngay cả khi chỉ có hai input

```java
CompletableFuture<Integer> a = new CompletableFuture<>();
CompletableFuture<Integer> b = new CompletableFuture<>();
CompletableFuture<Void> all = CompletableFuture.allOf(a, b);

a.complete(2);
System.out.println(all.isDone()); // false, vẫn chờ b.

b.complete(3);
System.out.println(all.isDone()); // true.
int sum = all.thenApply(ignored -> a.join() + b.join()).join();
// sum == 5.
```

`allOf` đợi cả hai, trong khi `anyOf` đã có thể hoàn tất khi a=2. `allOf` **không trả danh sách các kết quả**; giữ các future thành phần để đọc sau barrier. Với lỗi, `allOf` có exceptional completion, không phải “đợi tất cả rồi tự trả danh sách lỗi” một cách có cấu trúc.

### 8.2. `applyToEither` không thay thế mọi chính sách first-success

`applyToEither` về mô tả API dùng **kết quả hoàn tất bình thường** từ một trong hai stage cùng kiểu T để thực hiện function. Nhưng khi một stage đã lỗi, việc kết hợp trường hợp exceptional completion còn chịu các quy tắc của `CompletionStage`; **đừng dựa vào đó như một thuật toán chắc chắn bỏ qua mọi lỗi và chỉ fail sau khi cả hai đều fail**.

Nếu yêu cầu rõ ràng là **“bất kỳ nguồn nào lỗi cũng phải tiếp tục chờ những nguồn khác, chỉ khi tất cả lỗi mới trả lỗi”**, hãy dùng cơ chế first-success chủ động như mục 11.

### 8.3. `anyOf` không tự tạo một Executor

`CompletableFuture.anyOf` là phép kết nối completion. Nó **không tạo thread để chạy các nguồn**, không biến `CompletableFuture.completedFuture(...)` thành IO song song, và không quyết định executor cho nguồn. Các source task phải được khởi chạy theo đúng API của chúng: `supplyAsync`, HTTP client bất đồng bộ, callback, scheduler, v.v.

## 9. Phân biệt “first completion” và “first successful response”

Hai business requirement nghe gần giống nhưng khác hẳn:

**Yêu cầu A: “Nguồn nào báo trạng thái trước thì gửi ngay, kể cả lỗi.”**

- `anyOf` phù hợp.
- Kết quả lỗi nhanh có thể kết thúc toàn bộ request nhanh.
- Có thể dùng để xử lý event đầu tiên hoặc cuộc đua với deadline.

**Yêu cầu B: “Ưu tiên dữ liệu hợp lệ nhanh nhất; nếu một nguồn lỗi, vẫn đợi nguồn khác. Chỉ khi hết nguồn đều lỗi thì mới thất bại.”**

- `anyOf` trực tiếp **không đáp ứng**.
- Cần helper **first-success**, quản lý completion từng nguồn.
- Nếu có một nguồn thành công với `null` mà null không phải dữ liệu chấp nhận, cần xử lý nó như **“không có kết quả hợp lệ”** theo policy riêng.

Sơ đồ:

```text
Nguồn A: ---- fail -------------------------
Nguồn B: ---------- success("DATA") --------

anyOf(A, B): -------- X (fail từ A), không tự phục hồi

firstSuccess(A, B): -------- chờ --------> "DATA"
```

Với trường hợp cả hai lỗi:

```text
Nguồn A: ---- fail ----------
Nguồn B: -------- fail ------

firstSuccess(A, B): ---------- FAIL (không còn nguồn thành công)
```

Nếu thời hạn tổng của request bị vượt trước khi mọi nguồn trả kết quả, bạn còn cần **deadline** tách biệt. Helper first-success chỉ giải quyết điều kiện hoàn tất, không tự tạo timeout.

## 10. Mô hình hóa outcome khi cần quan sát cả thành công và thất bại

Một chiến lược khác là **biến lỗi của từng nguồn thành dữ liệu** trước khi chạy anyOf, để output không bị hoàn tất ngoại lệ khi một nguồn gốc lỗi. Ví dụ:

```java
record Outcome<T>(String source, T value, Throwable error) {
    boolean succeeded() {
        return error == null;
    }
}

CompletableFuture<String> raw = someAsyncCall();

CompletableFuture<Outcome<String>> observed =
        raw.handle((value, error) ->
                new Outcome<>("primary", value, error));
```

Đây là **đoạn minh họa**; `someAsyncCall` cần được định nghĩa trong dịch vụ. Vì `handle` nhận cả completion bình thường và lỗi, `observed` được hoàn tất bình thường bằng một `Outcome` (trừ khi chính callback handle ném lỗi).

Khi đưa nhiều `observed` vào `anyOf`:

- Output chứa **thông tin về completion đầu tiên**.
- Nó có thể là `Outcome` **thất bại**, nhưng không làm `anyOf` hoàn tất ngoại lệ nếu callback handle đã chuyển lỗi thành dữ liệu.
- Caller có thể quyết định tiếp tục chờ, log hoặc trả lỗi dựa trên `Outcome.succeeded()`.

**Không suy luận** chỉ bọc `handle` là có sẵn thuật toán first-success. `anyOf` của các Outcome vẫn chọn **Outcome đến trước**, dù `error != null`. Muốn chờ tiếp sau một lỗi cần **thuật toán điều phối** như `firstSuccess`.

### 10.1. Có thể phân biệt lỗi riêng của từng nguồn

Nếu cần audit toàn bộ failures, bạn có thể lưu `Outcome<T>` cho mỗi nguồn, kết hợp qua `allOf`, rồi trả một tập kết quả có trạng thái của từng nguồn. Nếu chỉ cần kết quả đầu tiên nhưng muốn log những nguồn còn chạy, gắn `whenComplete` vào từng nguồn dưới một cơ chế log thread-safe.

Không log cùng Throwable ở từng stage vô tội vạ; có thể tạo nhiều log trùng nhau cho một lỗi upstream.

## 11. Xây helper `firstSuccess` đơn giản, đúng với nhiều nguồn cùng kiểu

Nếu yêu cầu là **đợi nguồn thành công đầu tiên**, ta có thể tạo một `CompletableFuture<T>` trả về và đăng ký callback trên mỗi input:

- Khi một source **thành công**, thử `winner.complete(value)`.
- Khi một source **lỗi**, tăng đếm lỗi.
- Chỉ khi **số lỗi bằng tổng số nguồn**, cho output hoàn tất ngoại lệ.
- Khi output đã thành công, những callback lỗi đến sau không thay đổi nó.
- Không hủy nguồn còn lại một cách tự động.

Mã Java 17+:

```java
static <T> CompletableFuture<T> firstSuccess(
        List<? extends CompletableFuture<? extends T>> candidates) {
    Objects.requireNonNull(candidates);

    // Snapshot danh sách, đồng thời từ chối phần tử future null.
    List<? extends CompletableFuture<? extends T>> snapshot =
            List.copyOf(candidates);

    if (snapshot.isEmpty()) {
        throw new IllegalArgumentException(
                "At least one source required");
    }

    CompletableFuture<T> winner = new CompletableFuture<>();
    AtomicInteger failures = new AtomicInteger();

    for (CompletableFuture<? extends T> source : snapshot) {
        source.whenComplete((value, error) -> {
            if (error == null) {
                winner.complete(value);
            } else if (failures.incrementAndGet() == snapshot.size()) {
                winner.completeExceptionally(
                        new IllegalStateException(
                                "All sources failed", error));
            }
        });
    }
    return winner;
}
```

Đây là **phương thức** cần `import java.util.*;`, `import java.util.concurrent.*;` và `import java.util.concurrent.atomic.*;`. Nó có mặt trong chương trình đầy đủ ở mục 17.

### 11.1. Vì sao dùng `AtomicInteger`?

Callbacks của các futures có thể chạy ở nhiều thread khác nhau. `AtomicInteger.incrementAndGet()` cho phép đếm nguồn lỗi mà không bị mất cập nhật. `CompletableFuture.complete` cũng xử lý cạnh tranh hoàn tất: chỉ một completion đầu tiên có hiệu lực, các lần sau trả false.

Mã dùng `List.copyOf` (Java 10+) để tránh caller thay đổi số phần tử trong danh sách giữa khi các callback đang chạy. Nó **chỉ snapshot danh sách**, không clone/cancel các future.

### 11.2. Chính sách null trong helper

Bản này coi `error == null` là **thành công**, kể cả `value == null`. Đây là semantics hợp lệ của CompletableFuture. Nếu ứng dụng muốn “chỉ nhận non-null”, cần định nghĩa `value == null` như một kết quả không đạt yêu cầu và xử lý riêng — nhưng phải phân biệt rõ chính sách domain với hợp đồng API.

### 11.3. Khi tất cả lỗi thì chọn nguyên nhân gì?

Để demo dễ hiểu, helper trả một `IllegalStateException("All sources failed", error)` và giữ **lỗi của callback cuối** làm cause. Nó **không tự thu đủ mọi nguyên nhân**. Trong production, bạn có thể lưu từng lỗi theo nguồn rồi tổng hợp bằng một exception chuyên biệt, `getSuppressed()` hoặc một `Result` object có danh sách failure, tùy yêu cầu audit/observability.

Đừng giả định thứ tự lỗi là cố định khi các nguồn thực sự đồng thời.

### 11.4. Những giới hạn của helper này

Helper chủ động là **một minh họa mô hình điều phối**, chưa phải một framework đầy đủ:

- Không tạo request hay giới hạn số nguồn; caller sở hữu việc khởi chạy.
- Không tự retry, không backoff, không circuit breaker.
- Không tự cancel nguồn thua; nếu cần, làm sau khi đã xét ownership.
- Không áp deadline; nếu mọi input pending mãi, output cũng pending.
- Không bảo đảm chọn một “thời điểm vật lý sớm nhất” khi nhiều callback chạy cạnh tranh; winner là callback thành công hoàn tất output trước.
- Không ngăn cùng một future xuất hiện lặp trong danh sách; nếu cần tránh double count, validate danh sách nguồn duy nhất trước.
- Không giúp giải quyết các hệ thống có side effect không idempotent, như thanh toán trùng.

Đối với ứng dụng cần ưu tiên nguồn theo trọng số, quorum, hợp nhất nhiều kết quả, hoặc ưu tiên kết quả mới nhất, phải dùng mô hình chuyên biệt — “first-success” không còn là toàn bộ yêu cầu.

## 12. Xử lý deadline và timeout khi đang đua nhiều nguồn

Một request thường cần **thời hạn tối đa**: “chờ kết quả đầu tiên trong 500 ms”. Đây là một bài toán liên quan nhưng khác với chính phép `anyOf`.

### 12.1. `orTimeout` hoàn tất chính CompletableFuture

Từ Java 9:

```java
CompletableFuture<String> request = startRequest();

CompletableFuture<String> bounded =
        request.orTimeout(500, TimeUnit.MILLISECONDS);
```

Đây là **đoạn minh họa**, `startRequest` do ứng dụng cung cấp. `orTimeout` trả về **chính request future** và sắp đặt để nó hoàn tất ngoại lệ bằng `TimeoutException` nếu chưa hoàn tất khi hết hạn.

**Điểm rất quan trọng:** nếu `request` được chia sẻ giữa nhiều nhánh, `orTimeout` **không tạo một wrapper timeout độc lập**. Nó thay đổi completion của chính input. Các nhánh khác cùng chờ request có thể cùng bị ảnh hưởng.

Tương tự, `completeOnTimeout(value, timeout,unit)` (Java 9+) hoàn tất **chính future đó** bằng fallback value khi hết hạn, chứ không tự ngắt tác vụ nền.

### 12.2. Dùng một future deadline để đua với kết quả

Nếu muốn giữ nguyên completion của source và chỉ cho **workflow kết thúc khi đến deadline**, có thể tạo tín hiệu deadline riêng:

```java
CompletableFuture<String> deadline = new CompletableFuture<>();

CompletableFuture.delayedExecutor(
        500, TimeUnit.MILLISECONDS)
        .execute(() -> deadline.completeExceptionally(
                new TimeoutException("Deadline exceeded")));

CompletableFuture<Object> winner =
        CompletableFuture.anyOf(actualRequest, deadline);
```

Đây là **đoạn minh họa**, `actualRequest` là `CompletableFuture<String>` đã khởi chạy, và `TimeoutException`/`TimeUnit` cần import. `delayedExecutor` có từ Java 9.

Ở đây:

- `actualRequest` hoàn tất trước → winner nhận kết quả hoặc lỗi của nó.
- `deadline` hoàn tất trước → winner thất bại do deadline.
- `actualRequest` **không tự bị cancel** chỉ vì deadline thắng.
- Tác vụ hẹn giờ có thể vẫn chạy callback sau khi request đã xong; code có thể kiểm tra `winner.isDone()` để tránh side effect không cần thiết.
- Hãy cân nhắc cơ chế scheduling/cleanup phù hợp ứng dụng thay vì tạo vô hạn deadline callbacks.

Nếu muốn **first-success với deadline**, gắn deadline vào output của helper first-success (hoặc một wrapper riêng) theo policy, không dùng `anyOf` trực tiếp trên các raw sources rồi hy vọng lỗi nhanh bị bỏ qua.

### 12.3. `get(timeout,unit)` chỉ giới hạn thời gian chờ

`future.get(500, TimeUnit.MILLISECONDS)` ném `TimeoutException` cho caller nếu hết thời gian chờ, nhưng **không tự làm future hoàn tất ngoại lệ**. Khác với `orTimeout`.

Trong server, nên tránh chặn luồng request không cần thiết; dùng composition và deadline ở boundary phù hợp. Với chương trình dòng lệnh hoặc API blocking thực sự, một lần `get(timeout)` ở đầu ra có thể hợp lý.

## 13. Hedged request: kỹ thuật giảm độ trễ nhưng không miễn phí

**Hedging** là gửi cùng một thao tác đọc tới nhiều replica/endpoint, nhằm giảm rủi ro một replica có tail latency cao.

Ví dụ:

```text
Request user/42
   |
   +---- Replica A ------------- result?
   |
   +---- Replica B ----- result?   <-- nguồn hoàn tất trước
   |
   +---- Selector (anyOf / firstSuccess theo policy)
```

Nếu policy là **phản hồi đầu tiên bất kể lỗi**, `anyOf` phù hợp. Nếu muốn **dữ liệu thành công đầu tiên**, dùng helper first-success hoặc một thư viện chuyên dụng có contract tương ứng. Nhưng các nguy cơ vẫn tồn tại:

1. **Chi phí nhân đôi:** Hai request chiếm connection, bandwidth, CPU và capacity backend.
2. **Không phải thao tác nào cũng idempotent:** Gửi hai lệnh thanh toán/ghi dữ liệu có thể gây hai side effect, ngay cả khi caller chỉ dùng một result.
3. **Dữ liệu stale:** Replica nhanh hơn có thể không mới nhất; “nhanh” không đồng nghĩa “đúng hơn”.
4. **Có thể chạm rate limit:** Hedging ồ ạt làm tăng tải đúng lúc backend đang chậm.
5. **Loser vẫn chạy:** `anyOf` không tự hủy network call hoặc rollback; việc hủy cần kiểm soát ownership và API underlying.
6. **Winner không nhất thiết phản ánh thời điểm hoàn thành vật lý:** callback scheduling có thể ảnh hưởng winner nếu các completion quá gần nhau.

Một chiến lược thực tế có thể **chỉ gửi request dự phòng sau khi nguồn chính chậm tới một ngưỡng**, thay vì luôn gửi cả hai ngay. Nhưng threshold, concurrency cap, cân nhắc kết quả stale và theo dõi metrics là chính sách ứng dụng, không có sẵn trong `anyOf`.

### 13.1. Khi cần thông tin về nguồn thắng

Đừng chỉ trả body; trả một giá trị có metadata:

```java
record Reply(String source, String body) {}
```

Log có thể ghi `source`, latency, timeout, error code. Khi nhiều nhánh chia sẻ một object mutable làm counters, dùng collector/metric thread-safe, không phụ thuộc vào thứ tự log của các callbacks.

## 14. Executor, thread và thời điểm callback có thể chạy

`anyOf` không thực thi Supplier, nên cần hiểu vòng đời của input:

```java
ExecutorService executor = Executors.newFixedThreadPool(2);

CompletableFuture<String> a =
        CompletableFuture.supplyAsync(() -> fetchA(), executor);
CompletableFuture<String> b =
        CompletableFuture.supplyAsync(() -> fetchB(), executor);

CompletableFuture<Object> first = CompletableFuture.anyOf(a, b);
```

Đây là đoạn minh họa có `fetchA/fetchB` từ bên ngoài. Khi dùng trong ứng dụng thực, executor cần được quản lý lifecycle; sau khi kết quả được dùng, đảm bảo các task đã dừng hoặc có chính sách hoàn tất, và đóng pool theo đúng owner.

### 14.1. Non-async callback có thể chạy trên thread hoàn tất upstream

`first.thenApply(v -> ...)` có thể chạy ngay nếu first đã hoàn tất, hoặc được thực hiện bởi thread kích hoạt completion. **Không giả định** callback luôn chạy trên một thread tên cố định.

Nếu phần xử lý winner tốn CPU hoặc blocking, bạn có thể dùng:

```java
CompletionStage<String> rendered =
        first.thenApplyAsync(value -> render(value), executor);
```

Đoạn minh họa có `render` trả `String`. `thenApplyAsync(..., executor)` yêu cầu scheduling trên executor đã chọn, nhưng **không làm hàm `render` tự trở nên non-blocking**. Một task blocking vẫn chiếm thread tương ứng.

### 14.2. Tránh deadlock khi dùng chung pool chật

Đừng gọi `join()` cho một child future chưa hoàn tất bên trong callback đang chiếm thread cuối cùng của chính executor mà child cần. Dùng `thenCompose` để nối công việc async thay vì chặn:

```java
CompletableFuture<String> first = callFirstAsync();

CompletionStage<Result> result =
        first.thenCompose(value -> callNextAsync(value));
```

Đây là ví dụ minh họa với `Result` và các hàm do service định nghĩa. Nếu viết `thenApply(value -> callNextAsync(value).join())`, callback có thể block, giảm concurrency và có nguy cơ deadlock.

### 14.3. Nhận kết quả không đồng nghĩa dừng task nguồn

Một callback `whenComplete` của loser vẫn có thể chạy sau khi caller đã trả HTTP response cho winner. Nếu nó cập nhật shared state hoặc phát thông báo, side effect ấy **vẫn có thật**. Dù bạn không đọc kết quả loser, phải quản lý lifecycle và logging thích hợp.

## 15. Ngoại lệ, join, get và tầng bọc cause

Một `CompletableFuture` hoàn tất ngoại lệ có thể được quan sát qua:

- `join()`: ném unchecked `CompletionException`, hoặc `CancellationException` nếu **chính future đó** bị cancel trực tiếp.
- `get()`: theo `Future`, có thể ném checked `ExecutionException` / `InterruptedException`; nếu future bị cancel trực tiếp có thể ném `CancellationException`.
- `whenComplete((value,error)->...)`: observer nhận lỗi khi có exceptional completion, không tự recover.
- `handle((value,error)->...)`: tạo một dependent có thể chuyển completion thành kết quả có cấu trúc.
- `exceptionally(error -> fallback)`: phục hồi một lỗi bằng giá trị fallback.
- `exceptionallyCompose(error -> asyncFallback())`: từ Java 12+, phục hồi bằng một stage async khác.

Đặc biệt với `anyOf`, nếu input bị cancel hoặc lỗi, output thường mang `CompletionException` liên quan đến cause của input. Nên lấy `getCause()` khi thiết kế xử lý, nhưng không dựng business logic trên chính **chuỗi thông báo** của exception.

### 15.1. `whenComplete` không phải `catch`

```java
CompletableFuture<Object> observed =
        CompletableFuture.anyOf(primary, backup)
                .whenComplete((value, error) -> {
                    if (error != null) {
                        System.err.println("first completion failed");
                    }
                });
```

Đây là đoạn minh họa, `primary/backup` đã khai báo. `whenComplete` chỉ quan sát; nếu upstream lỗi thì dependent vẫn lỗi (trừ những tình huống callback có exception khác theo hợp đồng). Để phục hồi, dùng `exceptionally`/`handle` hoặc điều phối first-success đúng policy.

### 15.2. Recovery quá sớm thay đổi semantics của cuộc đua

Nếu viết:

```java
CompletableFuture<String> normalizedA =
        primary.exceptionally(error -> "DEFAULT_A");
CompletableFuture<String> normalizedB =
        backup.exceptionally(error -> "DEFAULT_B");

CompletableFuture<Object> first =
        CompletableFuture.anyOf(normalizedA, normalizedB);
```

thì lỗi từ một input sẽ biến thành giá trị `DEFAULT_*`, và `anyOf` có thể chọn fallback đó trước kết quả thật của input kia. Đây là một **policy** có chủ đích (“lỗi A được xem là kết quả mặc định A”), không đồng nghĩa first-success theo nghĩa chỉ chọn kết quả thực sự thành công.

Phân biệt rõ **business success**, **technical success**, **fallback value** và **failure**.

## 16. Kiểm thử deterministic mà không cần Thread.sleep

Kiểm thử concurrency bằng cách giả định một request mất 20 ms và request kia mất 50 ms thường dễ bị **flaky** khi CPU chậm hoặc scheduler đổi thứ tự. Thay vào đó:

### 16.1. Kiểm soát thời điểm hoàn tất

```java
CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();
CompletableFuture<Object> race = CompletableFuture.anyOf(a, b);

b.complete("B");
assert "B".equals(race.join());
a.complete("A");
assert "B".equals(race.join());
```

Đây là đoạn minh họa trong method; `assert` của Java có thể **bị tắt nếu không chạy với `-ea`**, nên khi kiểm thử production nên dùng JUnit assertions hoặc hàm kiểm tra ném `AssertionError` như chương trình dưới. Kết quả ổn định vì ta điều khiển completion.

### 16.2. Kiểm soát các task thực sự bất đồng bộ bằng CountDownLatch

`CountDownLatch` cho phép hai task chạy trên executor nhưng chờ tín hiệu. Test thả latch của B trước, chờ anyOf trả B, sau đó mới thả A. Nó mô phỏng một cuộc đua nhưng **thứ tự hoàn tất được xác định** thay vì dựa vào sleep.

Lưu ý đảm bảo thả **mọi latch trong `finally`**, nếu không một assertion fail có thể để pool treo mãi. Chương trình đầy đủ dưới đây áp dụng điều này.

### 16.3. Kiểm tra lỗi và cancel theo type

Test nên kiểm tra:

- `join` của anyOf lỗi có một cause phù hợp.
- Input lỗi sớm làm output exceptional, cho dù input khác thành công sau.
- Input hủy sớm khiến output exceptional, nhưng source khác vẫn chưa bị hủy.
- Input thành công null làm output có giá trị null bình thường.
- Tập nguồn rỗng không được `join` nếu không có completion.
- first-success không báo lỗi chỉ vì một source lỗi, nhưng báo lỗi nếu **mọi source đều lỗi**.
- Không assert thứ tự callback/log của các source không được điều khiển bằng tín hiệu.

## 17. Chương trình Java 17+ hoàn chỉnh: anyOf, first-success, lỗi và real concurrency

Tạo tệp **`AnyOfFirstCompletionDemo.java`** sau đây. Chương trình dùng `CompletableFuture.complete` để tạo thứ tự chắc chắn cho các test logic, sau đó dùng `ExecutorService` + `CountDownLatch` cho một cuộc đua hai task thực sự. Không cần thư viện ngoài, không phụ thuộc tốc độ CPU.

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class AnyOfFirstCompletionDemo {
    record Reply(String source, String body) {}

    static void check(boolean good, String label) {
        if (!good) {
            throw new AssertionError(label);
        }
    }

    static <T> CompletableFuture<T> firstSuccess(
            List<? extends CompletableFuture<? extends T>> candidates) {
        Objects.requireNonNull(candidates);

        List<? extends CompletableFuture<? extends T>> snapshot =
                List.copyOf(candidates);
        if (snapshot.isEmpty()) {
            throw new IllegalArgumentException(
                    "At least one source required");
        }

        CompletableFuture<T> winner = new CompletableFuture<>();
        AtomicInteger failures = new AtomicInteger();
        for (CompletableFuture<? extends T> source : snapshot) {
            source.whenComplete((value, error) -> {
                if (error == null) {
                    winner.complete(value);
                } else if (failures.incrementAndGet()
                        == snapshot.size()) {
                    winner.completeExceptionally(
                            new IllegalStateException(
                                    "All sources failed", error));
                }
            });
        }
        return winner;
    }

    static String awaitGate(CountDownLatch latch, String result) {
        try {
            latch.await();
            return result;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new CompletionException(error);
        }
    }

    public static void main(String[] ignored) throws Exception {
        // 1. Kết quả nhanh nhất thắng và được chốt.
        CompletableFuture<String> slow = new CompletableFuture<>();
        CompletableFuture<String> fast = new CompletableFuture<>();
        CompletableFuture<Object> first =
                CompletableFuture.anyOf(slow, fast);

        fast.complete("FAST");
        check(first.join().equals("FAST"), "fast wins");
        System.out.println("firstCompleted=" + first.join());
        System.out.println("loserStillPending=" + !slow.isDone());

        slow.complete("SLOW");
        System.out.println("winnerUnchanged=" + first.join());

        // 2. Nguồn lỗi trước, nguồn sau thành công: anyOf vẫn lỗi.
        CompletableFuture<String> failing = new CompletableFuture<>();
        CompletableFuture<String> eventual = new CompletableFuture<>();
        CompletableFuture<Object> failedRace =
                CompletableFuture.anyOf(failing, eventual);

        failing.completeExceptionally(
                new IllegalStateException("endpoint down"));
        eventual.complete("LATE_SUCCESS");

        boolean causeConfirmed = false;
        try {
            failedRace.join();
        } catch (CompletionException error) {
            causeConfirmed =
                    error.getCause() instanceof IllegalStateException;
        }
        check(causeConfirmed, "exception first");
        System.out.println("firstExceptionIsIllegalState=" +
                causeConfirmed);
        System.out.println("lateSuccessDoesNotRepair=" +
                failedRace.isCompletedExceptionally());

        // 3. Cancel một input: anyOf hoàn tất ngoại lệ.
        CompletableFuture<String> toCancel = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        CompletableFuture<Object> cancelRace =
                CompletableFuture.anyOf(toCancel, second);

        toCancel.cancel(true);
        boolean cancelWin = false;
        try {
            cancelRace.join();
        } catch (CompletionException error) {
            cancelWin = error.getCause()
                    instanceof CancellationException;
        } catch (CancellationException error) {
            cancelWin = true;
        }
        check(cancelWin, "cancellation first");
        System.out.println("cancellationWins=" + cancelWin);
        System.out.println("otherStillPendingAfterCancel=" +
                !second.isDone());
        System.out.println("anyOfIsCancelled=" +
                cancelRace.isCancelled());
        second.complete("too late");

        // 4. Empty input không có completion nào.
        CompletableFuture<Object> noCandidates =
                CompletableFuture.anyOf();
        System.out.println("emptyAnyOfDone=" + noCandidates.isDone());

        // 5. Null có thể là kết quả thành công.
        CompletableFuture<String> presentNull =
                CompletableFuture.completedFuture(null);
        CompletableFuture<String> never = new CompletableFuture<>();
        System.out.println("nullCanWin=" +
                (CompletableFuture.anyOf(
                        presentNull, never).join() == null));

        // 6. Kết quả có metadata nguồn và kiểu Reply.
        CompletableFuture<Reply> remote = new CompletableFuture<>();
        CompletableFuture<Reply> cache = new CompletableFuture<>();
        CompletableFuture<Reply> taggedWinner =
                CompletableFuture.anyOf(remote, cache)
                        .thenApply(Reply.class::cast);

        cache.complete(new Reply("cache", "CACHED"));
        remote.complete(new Reply("remote", "FRESH"));
        Reply tag = taggedWinner.join();
        System.out.println("taggedWinner=" +
                tag.source() + ":" + tag.body());

        // 7. Helper first-success bỏ qua lỗi một nguồn.
        CompletableFuture<String> primary = new CompletableFuture<>();
        CompletableFuture<String> backup = new CompletableFuture<>();
        CompletableFuture<String> success =
                firstSuccess(List.of(primary, backup));

        primary.completeExceptionally(
                new IllegalArgumentException("failed"));
        System.out.println("firstSuccessPendingAfterFailure=" +
                !success.isDone());
        backup.complete("BACKUP");
        System.out.println("firstSuccessValue=" + success.join());

        // 8. Helper trả lỗi khi TẤT CẢ nguồn đều lỗi.
        CompletableFuture<String> e1 = new CompletableFuture<>();
        CompletableFuture<String> e2 = new CompletableFuture<>();
        CompletableFuture<String> allFailed =
                firstSuccess(List.of(e1, e2));

        e1.completeExceptionally(new IllegalArgumentException("a"));
        e2.completeExceptionally(new IllegalArgumentException("b"));
        boolean allFailedRejected = false;
        try {
            allFailed.join();
        } catch (CompletionException error) {
            allFailedRejected = error.getCause()
                    instanceof IllegalStateException;
        }
        check(allFailedRejected, "all failures propagate");
        System.out.println("allFailuresRejected=" +
                allFailedRejected);

        // 9. allOf là barrier, không phải cuộc đua.
        CompletableFuture<Integer> a = new CompletableFuture<>();
        CompletableFuture<Integer> b = new CompletableFuture<>();
        CompletableFuture<Void> barrier =
                CompletableFuture.allOf(a, b);

        a.complete(2);
        System.out.println("allOfWaitsForB=" + !barrier.isDone());
        b.complete(3);
        System.out.println("allOfSum=" +
                barrier.thenApply(v -> a.join() + b.join()).join());

        // 10. Either trên hai stage có cùng kiểu.
        CompletableFuture<String> good =
                CompletableFuture.completedFuture("OK");
        CompletableFuture<String> pending = new CompletableFuture<>();
        System.out.println("eitherNormal=" +
                good.applyToEither(
                        pending, String::toLowerCase).join());

        // 11. Hai task chạy thật trên executor.
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch releaseA = new CountDownLatch(1);
        CountDownLatch releaseB = new CountDownLatch(1);
        try {
            CompletableFuture<String> workA =
                    CompletableFuture.supplyAsync(
                            () -> awaitGate(releaseA, "A"), pool);
            CompletableFuture<String> workB =
                    CompletableFuture.supplyAsync(
                            () -> awaitGate(releaseB, "B"), pool);
            CompletableFuture<Object> live =
                    CompletableFuture.anyOf(workA, workB);

            releaseB.countDown();
            check(live.join().equals("B"), "real async race");
            System.out.println("controlledAsyncWinner=" + live.join());
        } finally {
            releaseA.countDown();
            releaseB.countDown();
            pool.shutdown();
            check(pool.awaitTermination(
                    5, TimeUnit.SECONDS), "pool terminates");
        }

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch, chạy:

```bash
javac AnyOfFirstCompletionDemo.java
java AnyOfFirstCompletionDemo
```

**Stdout chính xác mong đợi:**

```text
firstCompleted=FAST
loserStillPending=true
winnerUnchanged=FAST
firstExceptionIsIllegalState=true
lateSuccessDoesNotRepair=true
cancellationWins=true
otherStillPendingAfterCancel=true
anyOfIsCancelled=false
emptyAnyOfDone=false
nullCanWin=true
taggedWinner=cache:CACHED
firstSuccessPendingAfterFailure=true
firstSuccessValue=BACKUP
allFailuresRejected=true
allOfWaitsForB=true
allOfSum=5
eitherNormal=ok
controlledAsyncWinner=B
ALL CHECKS PASSED
```

### 17.1. Nhóm kết quả “first completion”

- `firstCompleted=FAST`: ta chủ động hoàn tất fast trước nên winner xác định.
- `loserStillPending=true`: output hoàn tất **không hủy** slow.
- `winnerUnchanged=FAST`: khi slow hoàn tất sau, output đã được chốt.
- `firstExceptionIsIllegalState=true`: input lỗi đầu tiên làm anyOf lỗi, `join()` cho phép quan sát cause.
- `lateSuccessDoesNotRepair=true`: nguồn eventual thành công sau không thể biến output đã lỗi thành thành công.

### 17.2. Nhóm cancellation và null

- `cancellationWins=true`: `cancel(true)` trên input làm output có exceptional completion.
- `otherStillPendingAfterCancel=true`: future còn lại chưa tự bị cancel.
- `anyOfIsCancelled=false`: output không bị cancel trực tiếp; nó **báo exceptional completion** theo nguyên nhân cancellation của input.
- `emptyAnyOfDone=false`: không có nguồn hoàn tất, nên future output vẫn pending.
- `nullCanWin=true`: future thành công bằng null là completion bình thường, không phải lỗi.

### 17.3. Nhóm type và first-success

- `taggedWinner=cache:CACHED`: dữ liệu source-tagged cho phép biết nguồn trả lời.
- `firstSuccessPendingAfterFailure=true`: helper chủ động **đợi tiếp** sau khi primary lỗi.
- `firstSuccessValue=BACKUP`: backup thành công được dùng, đúng với first-success policy.
- `allFailuresRejected=true`: nếu cả hai lỗi, helper báo failure thay vì chờ vô hạn.

### 17.4. Nhóm phối hợp và executor

- `allOfWaitsForB=true`: sau khi chỉ a hoàn tất, `allOf` vẫn pending.
- `allOfSum=5`: barrier xong sau khi cả a và b sẵn sàng, cho phép cộng 2+3.
- `eitherNormal=ok`: `applyToEither` xử lý normal completion với dữ liệu String từ một stage đã hoàn tất sẵn.
- `controlledAsyncWinner=B`: hai task thật chạy trên pool riêng; latch B được thả trước, A vẫn đợi cho tới finally, nên result B xác định.
- `ALL CHECKS PASSED`: các assertion và shutdown pool đều thành công.

## 18. Ma trận kiểm thử khi thiết kế cuộc đua

| Test | Chuẩn bị | Kết quả phải khẳng định |
| --- | --- | --- |
| Nguồn B thành công trước | A=pending, B.complete("B") | anyOf trả B |
| Nguồn A hoàn tất sau | B đã thắng | anyOf vẫn B |
| Nguồn A lỗi trước | A.completeExceptionally; B sẽ success | anyOf vẫn lỗi |
| Nguồn A bị cancel | A.cancel | anyOf exceptional, B không tự cancel |
| Future trả kết quả null | completedFuture(null) | anyOf bình thường với null |
| Tập input rỗng | anyOf() | output pending, không gọi join vô hạn |
| Input chứa future null | anyOf(a,null) | NullPointerException |
| Nhiều futures cùng kiểu | CompletableFuture<String> | Output vẫn CompletableFuture<Object> |
| Nguồn có metadata | CompletableFuture<Reply> | Đọc được Reply.source() và body() |
| allOf sau một thành công | A done, B pending | Barrier chưa done |
| allOf sau hai thành công | A done, B done | Barrier hoàn tất |
| applyToEither với một normal | A completedFuture, B pending | Callback xử lý A |
| firstSuccess sau một lỗi | A failed, B pending | Output pending |
| firstSuccess sau một thành công | A failed, B success | Output có giá trị B |
| firstSuccess mọi lỗi | A failed, B failed | Output exceptional |
| Hai task chạy song song | CountDownLatch điều khiển completion | Winner ổn định, không dùng sleep |
| Deadline sớm hơn response | Deadline future lỗi trước | Race báo TimeoutException cause |
| Hủy output không hủy input | output.cancel | Input không tự bị hủy theo chiều ngược |
| Non-idempotent workload | Hai request ghi cùng giao dịch | Phải có idempotency/ownership, không dùng hedging mù quáng |

### 18.1. Cẩn thận với `join()` khi input chưa có tín hiệu hoàn tất

Một unit test sai như sau có thể treo:

```java
CompletableFuture<String> a = new CompletableFuture<>();
CompletableFuture<String> b = new CompletableFuture<>();

// Anti-pattern: chưa có thread/nguồn nào complete a hoặc b.
// Object result = CompletableFuture.anyOf(a, b).join();
```

Để test đúng, tạo các future rồi **complete có chủ đích**, hoặc chạy task trên executor và có timeout phù hợp. Không dùng indefinite join trong test ngoại trừ khi đã chứng minh nguồn chắc chắn phát tín hiệu.

### 18.2. Cẩn thận với `orTimeout` trên future chia sẻ

Test nên xác minh liệu output timeout đang **ảnh hưởng chính source** hay chỉ ảnh hưởng một wrapper. Khi dùng `orTimeout` với shared input, cùng đối tượng future bị thay đổi completion. Với một deadline future riêng, input vẫn có thể hoàn tất sau khi deadline thắng. Hai thiết kế có hệ quả khác nhau đối với những consumer khác.

## 19. Các lỗi phổ biến và cách sửa

### Lỗi 1: Hiểu `anyOf` là “first successful result”

**Sai:** một endpoint lỗi nhanh thì được bỏ qua tự động. **Đúng:** bất kỳ completion đầu tiên, kể cả lỗi. Muốn đợi success thì dùng chính sách first-success riêng.

### Lỗi 2: Nghĩ `anyOf` sẽ tự cancel các task còn lại

**Sai:** winner hoàn tất không dừng loser. **Sửa:** quản lý ownership/cancellation ở task/client thực, tránh cancel nguồn shared.

### Lỗi 3: Dùng `anyOf()` trên danh sách rỗng rồi `join()`

**Sai:** output vẫn pending. **Sửa:** validate input hoặc định nghĩa fallback/failedFuture cho tập rỗng.

### Lỗi 4: Bỏ qua kiểu `Object` trả về

**Sai:** ép kiểu thô `CompletableFuture<String>` và kỳ vọng compiler bảo vệ. **Sửa:** wrapper đồng nhất kiểu, cast có kiểm chứng hoặc thiết kế một `Reply`/`Outcome` chung.

### Lỗi 5: Nhầm result null với failure

**Sai:** `value == null` là lỗi. **Sửa:** dùng `error != null` để phát hiện exceptional completion; có policy domain riêng cho missing data.

### Lỗi 6: Không biết input nào thắng

**Sai:** chỉ lưu value khiến không giải thích được latency hay nguồn dữ liệu stale. **Sửa:** tag source trước khi race và log metadata có cấu trúc.

### Lỗi 7: Coi thứ tự varargs là thứ tự ưu tiên

**Sai:** `anyOf(a,b,c)` luôn chọn a nếu a đã có kết quả. **Sửa:** không giả định thứ tự giữa các completion đã có/đồng thời; nếu cần priority, viết selector theo policy.

### Lỗi 8: Dùng `anyOf` cho tất cả kết quả cần có

**Sai:** chỉ lấy một kết quả trong khi cần hai. **Sửa:** `thenCombine` hoặc `allOf` để chờ đầy đủ.

### Lỗi 9: Coi `applyToEither` là first-success tổng quát

**Sai:** hy vọng mọi tình huống lỗi được bỏ qua cho tới khi có kết quả tốt. **Sửa:** đọc contract exceptional completion và dùng một helper first-success có test.

### Lỗi 10: Recovery `exceptionally` ngay sau anyOf rồi tưởng backup đã được xét

**Sai:** fallback có thể được chọn trước khi backup hoàn tất. **Sửa:** quyết định muốn fallback tức thì hay first-success và triển khai đúng.

### Lỗi 11: Cancel future bằng `cancel(true)` rồi coi network đã bị ngắt

**Sai:** CompletableFuture không đảm bảo interrupt công việc nền. **Sửa:** cancellation API của HTTP/database client và cleanup riêng, có đo lường.

### Lỗi 12: Gắn `orTimeout` vào shared future mà không nhận ra mutation

**Sai:** cho rằng timeout-stage mới độc lập được tạo. **Sửa:** cân nhắc wrapper deadline nếu không được phép thay đổi upstream.

### Lỗi 13: Hedging thao tác ghi không idempotent

**Sai:** gửi hai lệnh tạo đơn hàng và lấy “phản hồi nhanh nhất” rồi tưởng chỉ có một lệnh đã thực thi. **Sửa:** ưu tiên áp dụng hedging cho read-only/idempotent, hoặc có idempotency key/transaction policy chặt chẽ.

### Lỗi 14: Không giới hạn concurrency

**Sai:** gửi hàng nghìn request dự phòng đồng thời. **Sửa:** rate limit, semaphore, bounded executor/queue và theo dõi tail latency.

### Lỗi 15: Dùng `Thread.sleep` để test nguồn nào thắng

**Sai:** race thay đổi theo CPU/scheduler/CI. **Sửa:** dùng futures chưa hoàn tất và `CountDownLatch` để điều khiển completion.

### Lỗi 16: Chặn pool thread bằng `join()` ở giữa graph

**Sai:** tạo child trên cùng pool rồi chờ nó trong callback; có thể nghẽn/deadlock. **Sửa:** nối bằng `thenCompose` và chờ ở boundary thực sự cần kết quả đồng bộ.

### Lỗi 17: Quên lỗi của loser

**Sai:** chỉ log winner, loser báo lỗi rồi không ai theo dõi; có thể mất thông tin vận hành. **Sửa:** gắn `whenComplete`/metrics phù hợp cho các nguồn khi cần, tránh double logging.

### Lỗi 18: Đếm lỗi bằng int dùng chung thiếu đồng bộ

**Sai:** callbacks của nhiều nguồn có thể tăng cùng một biến từ nhiều thread. **Sửa:** `AtomicInteger` hoặc cơ chế đồng bộ phù hợp.

### Lỗi 19: Không xử lý case cả nguồn đều thất bại

**Sai:** first-success helper chỉ xử lý success, còn mọi failures khiến output pending mãi. **Sửa:** đếm exceptional completions và hoàn tất lỗi khi hết nguồn khả thi, hoặc deadline.

### Lỗi 20: Không quản lý side effect sau khi winner đã trả về

**Sai:** loser có thể cập nhật shared state sau đó, khiến người dùng thấy trạng thái không nhất quán. **Sửa:** ownership, idempotency, cancellation và business transaction boundary rõ ràng.

## 20. Bài tập thực hành và đáp án

**Bài 1.** A lỗi ở 10 ms, B thành công ở 20 ms. `anyOf(A,B)` trả gì?

**Đáp án:** Exceptional completion theo lỗi của A; kết quả B tới sau không thay đổi output.

**Bài 2.** A hoàn tất bình thường với `null` ở 10 ms, B thành công với `"OK"` ở 20 ms. `anyOf` trả gì?

**Đáp án:** Hoàn tất bình thường với `null`. Nếu muốn bỏ qua null, phải có policy và thuật toán riêng.

**Bài 3.** Có `List<CompletableFuture<String>> futures` rỗng. Gọi `CompletableFuture.anyOf()` rồi `join` có an toàn không?

**Đáp án:** Không. Khi không có nguồn, output chưa hoàn tất và `join` có thể chờ mãi.

**Bài 4.** `CompletableFuture.anyOf(a,b)` trả `CompletableFuture<String>` khi cả a,b đều có kiểu String?

**Đáp án:** Không. Chữ ký trả `CompletableFuture<Object>`; có thể áp dụng `thenApply(String.class::cast)` khi chắc chắn mọi input cùng kiểu.

**Bài 5.** `anyOf` có tự hủy kết nối tới replica thua cuộc không?

**Đáp án:** Không. Phải dùng cơ chế quản lý request/cancellation của client, với ownership đúng.

**Bài 6.** Một input bị `cancel(true)` trước. Future output anyOf có nhất thiết `isCancelled()==true` không?

**Đáp án:** Không. Output có thể hoàn tất ngoại lệ với `CompletionException` chứa `CancellationException`; phân biệt source bị cancel và output bị hoàn tất theo cancellation của source.

**Bài 7.** `allOf` với a done và b pending có hoàn tất không?

**Đáp án:** Chưa. Nó là barrier đợi tất cả nguồn hoàn tất, khác anyOf.

**Bài 8.** Muốn dùng một trong hai kết quả cùng kiểu để map sang U khi bình thường, tên API gì?

**Đáp án:** `applyToEither` là API tương ứng; vẫn phải hiểu quy tắc lỗi và không mặc định nó thay thế first-success tổng quát.

**Bài 9.** Muốn đợi nguồn thành công đầu tiên và một nguồn đã lỗi. Có dùng `anyOf` trực tiếp không?

**Đáp án:** Không. Dùng helper first-success hoặc điều phối có contract chờ nguồn khác sau lỗi.

**Bài 10.** Nếu hai nguồn cùng thành công gần như đồng thời, có thể assert luôn source A thắng không?

**Đáp án:** Không, trừ khi test kiểm soát thứ tự completion bằng tín hiệu. Thứ tự scheduling không phải một cam kết của business logic.

**Bài 11.** Vì sao nên gắn `source` vào kết quả Reply?

**Đáp án:** Để biết nguồn trả lời, phân tích latency, chất lượng dữ liệu, log/metrics và xác định một kết quả stale từ replica nào.

**Bài 12.** `orTimeout` trên một CompletableFuture tạo một wrapper mới độc lập?

**Đáp án:** Không. Nó hoàn tất và trả **chính CompletableFuture đó** khi điều kiện timeout được kích hoạt.

**Bài 13.** `get(timeout,unit)` có tự làm future kết thúc lỗi khi thời gian chờ hết không?

**Đáp án:** Không. Nó giới hạn thời gian chờ của caller; future vẫn có thể pending và hoàn tất sau.

**Bài 14.** Có thể dùng `anyOf` để đua HTTP request với deadline không?

**Đáp án:** Có, nếu deadline được biểu diễn bằng một CompletableFuture riêng hoàn tất đúng lúc. Nhưng khi deadline thắng, HTTP request nền không tự bị cancel.

**Bài 15.** Chọn kết quả đầu tiên khi hai lệnh chuyển tiền cạnh tranh có an toàn không?

**Đáp án:** Không nếu mỗi lệnh có side effect có thể thực thi riêng. Một output được chọn không xóa giao dịch thua; cần idempotency, transaction design và ownership.

**Bài 16.** Helper first-success chỉ đếm failures, khi nào báo lỗi?

**Đáp án:** Khi **mọi nguồn** báo thất bại. Nếu còn ít nhất một nguồn pending, nó tiếp tục chờ; một nguồn thành công trước sẽ thắng.

**Bài 17.** Nếu app muốn chỉ chấp nhận result khi giá trị đủ mới, liệu `anyOf` hoặc first-success cơ bản có đủ không?

**Đáp án:** Chưa. Cần predicate/phiên bản dữ liệu và logic lựa chọn “đạt tiêu chuẩn” riêng; “đầu tiên hoàn tất” không đồng nghĩa “đúng nhất”.

**Bài 18.** Có nên gọi `join()` trên anyOf ở giữa callback `supplyAsync` trên pool chỉ một thread không?

**Đáp án:** Không nên nếu các nguồn anyOf cũng cần thread đó; có thể deadlock. Hãy composition và boundary chờ hợp lý.

## 21. Checklist thiết kế trước khi triển khai

- [ ] Nghiệp vụ cần **first completion** hay **first success**? Đã viết chính sách bằng một câu rõ ràng?
- [ ] Nếu lỗi đầu tiên xuất hiện, output phải báo lỗi ngay, fallback hay tiếp tục chờ nguồn khác?
- [ ] Có phân biệt success với giá trị `null` hoặc “not found” theo domain không?
- [ ] Đã xử lý input rỗng, phần tử future null, nhiều input đã completed sẵn?
- [ ] Đã hiểu return type `CompletableFuture<Object>` và tránh unchecked cast không kiểm chứng?
- [ ] Nếu cần biết ai thắng, đã gắn source metadata vào kết quả?
- [ ] Không giả định thứ tự winner ổn định khi nhiều nguồn hoàn tất đồng thời?
- [ ] Nếu cần đủ mọi kết quả, dùng `allOf`/`thenCombine` thay vì anyOf?
- [ ] Nếu dùng applyToEither, đã kiểm tra exceptional semantics thay vì đoán?
- [ ] Đã có timeout/deadline, không cho `join()` chờ vô hạn với nguồn có thể treo?
- [ ] Biết `orTimeout`/`completeOnTimeout` mutate chính CompletableFuture?
- [ ] Không giả định `cancel(true)` luôn interrupt hoặc hủy IO nền?
- [ ] Khi có loser, đã xác định ownership, cancellation, resource cleanup và metrics?
- [ ] Chỉ hedging tác vụ đọc/idempotent hoặc có chính sách chống double side effect?
- [ ] Đã giới hạn số nguồn đồng thời và có rate limit/backpressure phù hợp?
- [ ] Có executor phù hợp, shutdown đúng lifecycle, không block thread cuối pool?
- [ ] Helper first-success đã xử lý **tất cả thất bại**, kết quả null, callback chạy nhiều thread và deadline?
- [ ] Unit test kiểm soát completion bằng future/latch thay vì sleep?
- [ ] Khi parse exception tại boundary, đã quan sát cause và không phụ thuộc chuỗi message JVM?
- [ ] Không bỏ qua lỗi của các nguồn thua nếu cần observability/audit?

## Tham khảo chính thức, vẫn áp dụng

1. [Oracle Java SE 26 — CompletableFuture: anyOf, allOf, cancellation, complete, completeExceptionally, join, orTimeout, completeOnTimeout, delayedExecutor](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
2. [Oracle Java SE 26 — CompletionStage: applyToEither, thenCompose, thenCombine, handle, whenComplete, exceptionally và các quy tắc exceptional completion](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html)
3. [Oracle Java SE 26 — Future: get, timeout, cancellation, state và hợp đồng chờ kết quả](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html)
4. [Oracle Java SE 26 — ExecutorService: shutdown, awaitTermination và quản lý tài nguyên](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ExecutorService.html)
5. [Oracle Java SE 26 — CompletionException và cause khi completion thất bại](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionException.html)
6. [Oracle Java SE 26 — CountDownLatch để phối hợp thứ tự trong bài kiểm thử bất đồng bộ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

**Ghi nhớ:** `CompletableFuture.anyOf` là phép đua để lấy **completion đầu tiên**, **không mặc định** là **kết quả thành công đầu tiên**. Lỗi và cancellation có thể thắng; output là `CompletableFuture<Object>`; nguồn thua không tự dừng. Chỉ chọn anyOf khi đúng business requirement; nếu cần first-success, hãy điều phối và kiểm thử việc bỏ qua failures, xử lý all-failed, deadline, kiểu dữ liệu, idempotency và tài nguyên một cách tường minh.
