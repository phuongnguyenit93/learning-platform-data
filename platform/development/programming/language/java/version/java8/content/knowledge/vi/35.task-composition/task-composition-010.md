# Lan truyền lỗi qua chuỗi và qua các nhánh độc lập trong CompletableFuture

> **Module:** Java 8 — Ghép tác vụ. Bài phân tích cách một lỗi đi qua chuỗi `CompletableFuture`, sự khác nhau giữa một chuỗi phụ thuộc và các nhánh độc lập, cách ghép bằng `thenCompose`/`thenCombine`/`allOf`/`anyOf`, và vị trí xử lý lỗi bằng `exceptionally`, `handle`, `whenComplete`. Mọi API dùng trong chương trình chạy đầy đủ đều tương thích Java 8 và tiếp tục được hỗ trợ trên Java hiện đại.

## 1. Một lỗi lan truyền theo quan hệ phụ thuộc, không phải lan toàn hệ thống

Giả sử chương trình xử lý một đơn đặt hàng qua ba bước:

~~~text
Lấy đơn hàng
    |
    v
Kiểm tra dữ liệu
    |
    v
Tính phí
    |
    v
Xuất kết quả
~~~

Đây là một **chuỗi phụ thuộc**. Nếu bước kiểm tra bị lỗi và không được phục hồi, bước tính phí không có một kết quả hợp lệ để tiếp tục; future của các bước tiếp theo thường hoàn thành **exceptionally**.

Nhưng trong nhiều ứng dụng, một kết quả nguồn được dùng theo nhiều nhánh:

~~~text
                 Lấy dữ liệu nguồn
                       |
            +----------+-----------+
            |                      |
            v                      v
      Tính báo cáo          Gửi thống kê phụ
            |                      |
          lỗi A                  thành công
            |                      |
            v                      v
      nhánh A lỗi             nhánh B vẫn ổn
~~~

Khi nguồn **thành công**, một lỗi phát sinh bên trong **nhánh A** không tự động làm hỏng **nguồn** hoặc **nhánh B**. Đây là khác biệt căn bản: *lỗi lan truyền theo các cạnh dependency đi xuống*, không chạy ngược lên nguồn hay chạy ngang sang mọi sibling stage.

Ngược lại, nếu chính **nguồn chung** hoàn thành exceptional, các dependent stage yêu cầu đầu vào thành công có thể cùng chuyển sang exceptional. Mỗi nhánh vẫn có thể lựa chọn **cơ chế recovery riêng**, tạo kết quả bình thường cho nhánh của mình.

### 1.1. Ba quy tắc cần nhớ

1. **Chỉ chạy phép biến đổi thành công khi đầu vào thành công.** `thenApply`, `thenCompose` và action của `thenCombine` được định nghĩa cho đường thành công theo điều kiện của chúng.
2. **Mỗi stage là một kết quả riêng.** Khi stage con thất bại, điều đó không sửa lại kết quả của stage cha đã hoàn tất; các sibling stage cũng không tự bị biến thành failed.
3. **Recovery tạo một stage mới.** `exceptionally` và `handle` có thể biến một kết quả failed thành giá trị fallback cho **đường đi bên dưới stage recovery**, không làm thay đổi nguồn.

### 1.2. Một đoạn Java 8 tối thiểu

~~~java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(10);

CompletableFuture<Integer> bad = source.thenApply(x -> {
    throw new IllegalStateException("branch A failed");
});

CompletableFuture<Integer> good =
        source.thenApply(x -> x * 3);

// bad.isCompletedExceptionally() == true.
// good.join() == 30.
// source.join() == 10.
~~~

Đây là **đoạn minh họa**, cần import `java.util.concurrent.CompletableFuture`. Vì source đã hoàn thành bình thường bằng `10`, cả hai nhánh có thể chạy độc lập; nhánh lỗi không tự “đầu độc” nhánh khác.

## 2. Trạng thái completion của CompletableFuture

Một `CompletableFuture<T>` có thể:

- **Chưa hoàn thành:** kết quả chưa sẵn sàng.
- **Hoàn thành bình thường:** có kết quả kiểu `T`, kể cả `null`.
- **Hoàn thành exceptional:** chứa một Throwable làm lý do không có kết quả bình thường.
- **Bị cancel:** cancellation là một dạng exceptional completion đối với `CompletableFuture`, nhưng có trạng thái `isCancelled` để nhận diện riêng.

| API | Ý nghĩa |
| --- | --- |
| `isDone()` | Đã hoàn thành dưới bất kỳ hình thức nào |
| `isCompletedExceptionally()` | Kết quả đã hoàn thành exceptional, kể cả cancellation |
| `isCancelled()` | Chính future đó đã được cancel |
| `complete(value)` | Thử chốt giá trị bình thường; trả boolean cho biết có thành công |
| `completeExceptionally(error)` | Thử chốt lỗi; trả boolean |
| `cancel(boolean)` | Thử hoàn thành cancellation; không cam kết interrupt task nguồn |
| `join()` | Chờ/đọc kết quả; có thể ném unchecked exception |
| `get()` | Chờ/đọc kết quả; có checked exception, bao gồm interruption |

**`isDone()==true` không có nghĩa thành công.** Trong pipeline, phải xác định stage nào thất bại và tại sao, không chỉ nhìn future cuối là “đã xong”.

### 2.1. Exception ném bên trong lambda cũng làm stage mới exceptional

~~~java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(5);

CompletableFuture<Integer> failed = source.thenApply(x -> {
    if (x == 5) {
        throw new IllegalArgumentException("invalid value");
    }
    return x * 2;
});
~~~

Đây là **đoạn minh họa**. Lỗi xảy ra khi action `thenApply` chạy. Future `failed` nhận exceptional completion; `source` vẫn hoàn thành bình thường với 5. Chỗ gọi `thenApply` không nhất thiết nhận exception trực tiếp để caller xử lý bằng `try/catch`: lỗi thường được biểu diễn trong stage phụ thuộc.

### 2.2. completeExceptionally và throw trong stage

Có hai cách nguồn lỗi xuất hiện:

~~~java
CompletableFuture<String> manual = new CompletableFuture<>();
manual.completeExceptionally(
        new IllegalStateException("backend unavailable"));
~~~

và:

~~~java
CompletableFuture<String> computed =
        CompletableFuture.supplyAsync(() -> {
            throw new IllegalStateException("backend unavailable");
        });
~~~

Cả hai có thể tạo exceptional completion. Khác biệt: một bên **chủ động** chốt lỗi từ bên ngoài, bên kia lỗi xảy ra **trong task**. Consumer thường xử lý qua dependent stage hoặc `get`/`join`.

**Không** dùng `completeExceptionally` như phương thức “ném exception ngay tại dòng gọi”. Nó chủ yếu thay đổi outcome của future; chỉ các lỗi khi gọi API không hợp lệ (ví dụ Throwable null) là một vấn đề khác.

## 3. Lỗi đi dọc chuỗi thenApply, thenAccept và thenRun

### 3.1. Một stage lỗi khiến các action cần success phía sau bị bỏ qua

~~~java
CompletableFuture<Integer> root =
        CompletableFuture.completedFuture(3);

CompletableFuture<Integer> failed = root
        .thenApply(x -> x + 1)
        .thenApply(x -> {
            throw new IllegalStateException("step2");
        });

CompletableFuture<Integer> next = failed
        .thenApply(x -> x * 2);

// failed và next đều exceptional.
// Action x -> x * 2 không được thực thi.
~~~

Đây là **đoạn minh họa**. `thenApply` thứ hai ném lỗi; stage `failed` không có giá trị `Integer` để cung cấp cho bước tiếp theo. Stage `next` **được hoàn thành exceptional**, chứ không phải bị bỏ pending vô hạn.

Tương tự:

- `thenAccept` chỉ tiêu thụ value khi upstream hoàn thành bình thường.
- `thenRun` chạy sau upstream hoàn thành bình thường, không nhận value.
- Nếu upstream đã exceptional, action bình thường của các stage này không được thực thi.
- Một stage `thenApplyAsync` cũng không làm cho lambda xử lý thành công chạy với một exception như giá trị giả.

### 3.2. Lỗi không làm thay đổi stage đã thành công trước đó

~~~java
CompletableFuture<Integer> original =
        CompletableFuture.completedFuture(5);

CompletableFuture<Integer> later = original
        .thenApply(x -> x + 1)
        .thenApply(x -> {
            throw new IllegalStateException("later failed");
        });

// original.join() vẫn là 5.
// later.isCompletedExceptionally() có thể là true.
~~~

Một completion downstream không có phép “rollback” tự động đối với upstream. Nếu bước trước đã ghi cơ sở dữ liệu hoặc gửi message, CompletableFuture cũng không tự khôi phục side effect đó.

### 3.3. Đăng ký callback trước hoặc sau khi stage hoàn tất

Có thể gắn `thenApply`/`handle`/`exceptionally` trước hoặc sau khi future completed. Khi stage đã exceptional, callback bình thường không được chạy, còn error handler có thể được gọi theo hợp đồng.

**Đừng viết vòng polling `isDone()` để quyết định có gắn error handler hay không.** CompletableFuture có thiết kế callback và dependent stages xử lý được cả source đã hoàn thành.

## 4. Lỗi trong thenCompose: phụ thuộc vào stage lồng bên trong

`thenCompose` phục vụ một hàm trả về `CompletionStage<U>`, rồi **làm phẳng** thành một stage kết quả. Đây là cách ghép tác vụ bất đồng bộ theo trình tự mà không tạo `CompletableFuture<CompletableFuture<U>>`.

### 4.1. Nếu outer stage failed

~~~java
CompletableFuture<String> outer = new CompletableFuture<>();

CompletableFuture<Integer> derived =
        outer.thenCompose(value ->
                CompletableFuture.completedFuture(value.length()));

outer.completeExceptionally(
        new IllegalArgumentException("outer error"));

// Hàm trong thenCompose không được gọi.
// derived cũng hoàn thành exceptional.
~~~

Đây là **đoạn minh họa**. Nếu outer không có kết quả thành công, không thể lấy `value` để quyết định stage kế tiếp theo đường bình thường.

### 4.2. Nếu hàm thenCompose ném lỗi

~~~java
CompletableFuture<Integer> derived =
        CompletableFuture.completedFuture("x")
                .thenCompose(value -> {
                    throw new IllegalStateException("composer failed");
                });
~~~

Đây là **đoạn minh họa**. Stage derived thành exceptional vì action tạo inner stage đã ném lỗi. Loại generic vẫn có thể được suy luận từ ngữ cảnh gán; trong code phức tạp nên khai báo rõ kiểu tham số hoặc return type nếu compiler cần.

### 4.3. Nếu inner stage failed

~~~java
CompletableFuture<Integer> composed =
        CompletableFuture.completedFuture(4)
                .thenCompose(x -> {
                    CompletableFuture<Integer> inner =
                            new CompletableFuture<>();
                    inner.completeExceptionally(
                            new UnsupportedOperationException("inner"));
                    return inner;
                });

// composed.isCompletedExceptionally() == true.
~~~

**Lỗi của inner stage được phản ánh qua composed stage**, không bị ẩn trong một future lồng mà caller quên chờ. Nhưng inner future có thể tiếp tục chạy side effect khác nếu bị completed exceptional từ bên ngoài; composition không tự cung cấp cancellation của tác vụ nguồn.

### 4.4. Sự khác biệt với thenApply

~~~java
CompletableFuture<CompletableFuture<Integer>> nested =
        CompletableFuture.completedFuture(4)
                .thenApply(x -> CompletableFuture.completedFuture(x * 2));

CompletableFuture<Integer> flat =
        CompletableFuture.completedFuture(4)
                .thenCompose(x -> CompletableFuture.completedFuture(x * 2));
~~~

Đây là **đoạn minh họa**. `thenApply` trả future **lồng**, còn `thenCompose` trả future **đã làm phẳng**. Điều này quan trọng với đường error handling: nếu lỡ giữ nested future rồi chỉ kiểm tra outer, bạn có thể bỏ sót lỗi của inner.

## 5. Xử lý lỗi bằng exceptionally: vị trí recovery quyết định phạm vi

`exceptionally(Function<Throwable, ? extends T>)` trả một **stage mới**:

- Nếu stage nguồn **thành công**, giá trị được truyền qua; lambda recovery không chạy.
- Nếu stage nguồn **exceptional**, lambda được gọi và có thể trả `T` fallback.
- Nếu lambda recovery **ném exception**, stage trả về tiếp tục exceptional với lỗi mới.
- Nó **không sửa** trạng thái của stage nguồn và **không phục hồi các sibling branch khác** một cách tự động.

### 5.1. Recovery sớm và recovery muộn không tương đương

~~~java
CompletableFuture<Integer> input = new CompletableFuture<>();

CompletableFuture<Integer> early = input
        .exceptionally(ex -> 5)
        .thenApply(x -> x + 1);

CompletableFuture<Integer> late = input
        .thenApply(x -> x * 2)
        .exceptionally(ex -> -7);

input.completeExceptionally(
        new IllegalArgumentException("bad input"));

// early.join() == 6.
// late.join() == -7.
// input vẫn completed exceptionally.
~~~

**Giải thích:**

- `early` đặt fallback 5 **trước** phép `+1`, nên phép biến đổi vẫn chạy và trả 6.
- `late` đặt fallback **sau** phép nhân, vì phép nhân bị skip khi input lỗi nên kết quả fallback là -7.
- Cả hai là **hai nhánh độc lập** xuất phát từ `input` và có chính sách recovery khác nhau.
- Không một nhánh nào làm `input` thành công lại.

Nếu một bước cần dữ liệu thật để có nghĩa nghiệp vụ, hãy cân nhắc **không** phục hồi sớm bằng một số giả như 0/5 một cách tùy tiện. Đặt fallback theo contract, không chỉ để pipeline không throw.

### 5.2. Exceptionally xử lý lỗi tại chính stage mà nó gắn vào

Ví dụ:

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<String> recovered = source.exceptionally(
        error -> "DEFAULT");
~~~

Nếu source failed, `recovered` có thể thành công bằng `DEFAULT`. Nhưng:

~~~java
CompletableFuture<Integer> otherBranch =
        source.thenApply(String::length);
~~~

`otherBranch` vẫn có thể exceptional nếu source failed. **Recovery một nhánh không “chữa” toàn bộ các nhánh khác cùng source**.

### 5.3. Exceptionally không phải cuối cùng mới được dùng

Có thể đặt recovery:

- **Sớm:** khi muốn những bước sau được chạy trên fallback.
- **Muộn:** khi muốn bỏ qua biến đổi lỗi và trả kết quả tổng hợp.
- **Tại từng nhánh:** khi các nhánh có chính sách fallback độc lập.
- **Sau `allOf`/`thenCombine`:** khi muốn xử lý lỗi tổng thể, nhưng có thể mất thông tin cụ thể từng nhánh nếu không giữ future con.

Lựa chọn vị trí quyết định những action nào **thực sự chạy**, và liệu lỗi có được quan sát/log tại thời điểm phù hợp hay không.

### 5.4. Exception bên trong recovery

~~~java
CompletableFuture<String> bad = new CompletableFuture<>();
CompletableFuture<String> recoveryFailed = bad.exceptionally(error -> {
    throw new IllegalStateException("fallback unavailable");
});

bad.completeExceptionally(
        new IllegalArgumentException("original"));
~~~

Đây là **đoạn minh họa**. `recoveryFailed` thành exceptional bởi exception từ recovery. `bad` vẫn giữ lý do lỗi ban đầu. Nếu cần lưu cả hai nguyên nhân, ứng dụng phải định nghĩa logging/exception wrapping riêng; không mặc định mọi framework tự lưu một error tree đầy đủ.

## 6. handle và whenComplete: hai công cụ có mục tiêu khác nhau

### 6.1. handle có thể chuyển cả success và failure thành dữ liệu mới

`handle(BiFunction<T,Throwable,U>)` được gọi khi stage nguồn hoàn thành **bình thường hoặc exceptional**. Nó nhận:

- `value` nếu có kết quả bình thường; có thể null nếu future success bằng null.
- `error` khi exceptional; thường null khi thành công.
- Kết quả `U` do callback trả về, tạo ra dependent stage mới.

~~~java
CompletableFuture<Integer> source = new CompletableFuture<>();

CompletableFuture<String> status = source.handle(
        (value, error) -> error == null
                ? "SUCCESS:" + value
                : "FAILED");

source.completeExceptionally(
        new IllegalStateException("problem"));

// status.join().equals("FAILED") == true.
~~~

**Ưu điểm:** `handle` có thể làm **đổi kiểu kết quả** từ `T` sang `U`, không chỉ dùng fallback cùng kiểu `T` như `exceptionally`.

### 6.2. handle có thể tạo một lỗi mới

Nếu lambda của `handle` ném lỗi, **dependent stage của handle** sẽ exceptional; stage nguồn vẫn giữ kết quả cũ. Đừng dùng `handle` với side effect có khả năng lỗi cao nếu bạn chỉ muốn quan sát.

### 6.3. whenComplete dùng quan sát, không phải toán tử recovery

`whenComplete(BiConsumer<T,Throwable>)` có thể xem kết quả và lỗi:

~~~java
CompletableFuture<String> observed = source.whenComplete(
        (value, error) -> {
            if (error != null) {
                // Ghi metric, trace hoặc log.
            }
        });
~~~

Nếu callback hoàn thành bình thường, stage `observed` thường giữ nguyên success/failure outcome của source. `whenComplete` **không có return value để thay thế** như `handle`; nếu muốn trả fallback, chọn `exceptionally` hoặc `handle`.

### 6.4. Khi observer cũng ném lỗi: quy tắc ưu tiên

Đây là một điểm dễ nhầm:

- Nếu source **đã thành công**, nhưng observer `whenComplete` ném lỗi, **stage trả về bởi whenComplete** trở thành exceptional với lỗi của observer.
- Nếu source **đã exceptional** và observer cũng ném lỗi, stage trả về **giữ lỗi của source làm nguyên nhân ưu tiên** theo hợp đồng `CompletionStage`; đừng dựa vào lỗi observer thay thế nguyên nhân gốc.

Ví dụ minh họa:

~~~java
CompletableFuture<Integer> good =
        CompletableFuture.completedFuture(9);

CompletableFuture<Integer> observedGood = good.whenComplete(
        (value, error) -> {
            throw new IllegalStateException("observer");
        });

// observedGood failed vì "observer".

CompletableFuture<Integer> fail = new CompletableFuture<>();
CompletableFuture<Integer> observedFail = fail.whenComplete(
        (value, error) -> {
            throw new IllegalStateException("observer");
        });

fail.completeExceptionally(
        new IllegalArgumentException("original-error"));

// observedFail vẫn có lỗi nguồn "original-error".
~~~

Điểm quan trọng với logging: một observer không nên ném lỗi chỉ vì hệ thống metrics bị tạm thời lỗi, trừ khi bạn **chủ đích** biến failure của observer thành failure của stage phụ thuộc. Thiết kế action của `whenComplete` nhỏ, không blocking, có xử lý lỗi phù hợp.

### 6.5. Bảng quyết định cho ba công cụ

| Mục tiêu | `exceptionally` | `handle` | `whenComplete` |
| --- | --- | --- | --- |
| Chạy khi success | Không gọi recovery; truyền value qua | Có | Có |
| Chạy khi failure | Có | Có | Có |
| Có thể trả kết quả mới | Có, cùng kiểu `T` | Có, kiểu `U` tùy chọn | Không; quan sát |
| Dùng tạo fallback | Có | Có | Không trực tiếp |
| Giữ source không đổi | Có | Có | Có |
| Callback tự throw | Stage mới exceptional | Stage mới exceptional | Hành vi phụ thuộc outcome nguồn |
| Dùng log/metrics | Có thể, nhưng không phải lựa chọn tốt nhất nếu chỉ quan sát | Có thể | Thường phù hợp |

Một quy tắc thiết kế hữu ích: `whenComplete` **quan sát**, `exceptionally` **hồi phục lỗi**, `handle` **đọc và chuyển đổi cả hai outcome**.

## 7. Các nhánh độc lập xuất phát từ cùng một nguồn

### 7.1. Source thành công, một nhánh thất bại

~~~java
CompletableFuture<Integer> source = new CompletableFuture<>();

CompletableFuture<Integer> report = source.thenApply(value -> {
    throw new IllegalStateException("report failed");
});

CompletableFuture<Integer> statistics =
        source.thenApply(value -> value * 3);

source.complete(10);

// source.join() == 10.
// report.isCompletedExceptionally() == true.
// statistics.join() == 30.
~~~

Đây là **đoạn minh họa**. `report` và `statistics` là các sibling dependent futures. Lỗi bên trong `report` **không** tự ảnh hưởng kết quả của `statistics`; source vẫn có value 10.

### 7.2. Khôi phục một nhánh, nhánh còn lại không cần sửa

~~~java
CompletableFuture<Integer> reportFallback =
        report.exceptionally(error -> 20);

// reportFallback.join() == 20.
// report vẫn failed.
// statistics vẫn là 30.
~~~

Recovery là stage con mới chỉ trên đường `report -> reportFallback`.

### 7.3. Source chung thất bại: nhiều nhánh có thể cùng thất bại

~~~java
CompletableFuture<Integer> source = new CompletableFuture<>();

CompletableFuture<Integer> a = source.thenApply(x -> x + 1);
CompletableFuture<Integer> b = source.thenApply(x -> x * 3);

source.completeExceptionally(
        new IllegalStateException("source failed"));

// a và b đều có thể completed exceptionally.
// Các hàm x -> ... không được gọi.
~~~

**Khác biệt:** Ở tình huống này, lỗi thuộc **ancestor chung**. Tất cả downstream stages yêu cầu success đều không nhận được giá trị. Nếu muốn xử lý riêng, thêm handler trên mỗi branch; nếu muốn **chỉ một fallback chung** cho cả hai, có thể đặt recovery trên một stage trung gian rồi cho cả hai nhánh phụ thuộc **stage đã recover** đó.

### 7.4. Chọn điểm rẽ nhánh trước hay sau recovery

~~~text
Cách A: recovery chung

              root có thể lỗi
                    |
              exceptionally
                    |
            kết quả đã fallback
               /         \
              /           \
          nhánh A        nhánh B


Cách B: recovery riêng

              root có thể lỗi
               /         \
              /           \
           nhánh A        nhánh B
              |             |
         recover A       recover B
~~~

Ở **Cách A**, một chính sách fallback được chia sẻ, có thể phù hợp nếu tất cả nhánh cùng hiểu một giá trị dự phòng. Ở **Cách B**, từng nhánh có quyền quyết định bỏ qua, retry, trả default hoặc chuyển lỗi thành dữ liệu.

**Không có cách nào tốt cho mọi nghiệp vụ.** Cần biết mỗi nhánh có độc lập về mục tiêu và side effect hay không.

## 8. Ghép hai kết quả bằng thenCombine và các biến thể cả hai

`thenCombine(other, fn)` chỉ chạy `fn` khi **cả hai đầu vào hoàn thành bình thường**. Nó thường dùng khi cần kết quả từ hai tác vụ độc lập.

~~~java
CompletableFuture<Integer> price = new CompletableFuture<>();
CompletableFuture<Integer> tax = new CompletableFuture<>();

CompletableFuture<Integer> total =
        price.thenCombine(tax, (p, t) -> p + t);
~~~

Đây là **đoạn minh họa**.

### 8.1. Một nhánh thất bại: combiner không được gọi

~~~java
price.completeExceptionally(
        new IllegalStateException("price unavailable"));
tax.complete(8);

// total hoàn thành exceptional.
// Hàm (p,t)->p+t không chạy.
~~~

Nếu `price` không có giá trị hợp lệ, combiner không nhận đủ hai `Integer`. Tuy nhiên, **`tax` không tự bị hủy** vì `price` failed; nó vẫn có thể hoàn thành bình thường và giữ giá trị 8.

Thời điểm chính xác stage kết hợp chuyển sang done khi một đầu vào lỗi phụ thuộc cơ chế completion và trạng thái các đầu vào; **đừng dựa vào thời điểm bắt exception của combined** làm cơ chế hủy công việc còn lại. Thiết kế cancellation/lifecycle riêng nếu cần.

### 8.2. Recover nhánh lỗi trước khi combine

~~~java
CompletableFuture<Integer> safePrice =
        price.exceptionally(error -> 0);

CompletableFuture<Integer> safeTotal =
        safePrice.thenCombine(tax, (p, t) -> p + t);

// Nếu price failed, tax thành công bằng 8,
// safeTotal có thể trả 8 theo chính sách fallback price=0.
~~~

Đây là **đoạn minh họa**. Fallback `0` có thể phù hợp với thành phần tùy chọn nhưng **không phù hợp** nếu thiếu giá thật khiến việc thu tiền sai. Kiến thức kỹ thuật cần đi kèm quyết định nghiệp vụ.

### 8.3. Recover sau khi combine

~~~java
CompletableFuture<Integer> displayTotal =
        total.exceptionally(error -> -1);
~~~

Lúc này fallback áp cho **toàn kết quả ghép**, không chỉ riêng lỗi `price`. Nếu cần phân loại lỗi của từng nguồn, hãy gắn handler tại từng nhánh trước khi combine hoặc giữ các future con để đọc nguyên nhân.

### 8.4. thenAcceptBoth và runAfterBoth

Các method `thenAcceptBoth` và `runAfterBoth` cũng cần hai upstream hoàn thành bình thường để chạy action. Chúng khác ở số lượng value được chuyển cho callback và kiểu stage kết quả thường là `Void`:

- `thenAcceptBoth(other,(a,b)->...)` nhận cả hai giá trị.
- `runAfterBoth(other,()->...)` chạy khi cả hai hoàn thành bình thường nhưng không nhận giá trị.

Nếu một trong hai upstream failed, callback bình thường không chạy và downstream phản ánh lỗi theo hợp đồng.

## 9. allOf: đợi nhiều futures và nhận exceptional completion

`CompletableFuture.allOf(f1,f2,f3)` trả `CompletableFuture<Void>`:

- Hoàn thành sau khi **tất cả** những futures được cung cấp hoàn thành.
- Nếu tất cả bình thường, kết quả aggregate hoàn thành bình thường với `null`.
- Nếu có **ít nhất một** future hoàn thành exceptional, aggregate cũng hoàn thành exceptional.
- Không tự gộp giá trị từ các future vào một danh sách.
- Không tự dừng/hủy các nhánh còn lại khi có một nhánh lỗi.

### 9.1. Ví dụ có một nhánh lỗi và một nhánh hoàn tất muộn hơn

~~~java
CompletableFuture<String> a =
        CompletableFuture.completedFuture("A");
CompletableFuture<String> b = new CompletableFuture<>();
CompletableFuture<String> c = new CompletableFuture<>();

CompletableFuture<Void> all = CompletableFuture.allOf(a, b, c);

b.completeExceptionally(
        new IllegalStateException("b failed"));

// all chưa hoàn thành nếu c còn pending.

c.complete("C");

// all hoàn thành exceptional.
// c.join() vẫn trả "C".
~~~

Đây là **đoạn minh họa**, không có task ngoài nào chạy. Trong code thật, `allOf` không phải cơ chế fail-fast dừng mọi nguồn: nó được mô tả là hoàn thành **khi tất cả** đã completed.

### 9.2. allOf không thu thập tất cả exception thành một danh sách

Nếu nhiều input failed, `allOf` báo exceptional nhưng **không cam kết tạo một collection chứa toàn bộ nguyên nhân lỗi**. Không nên dựa vào `allOf.join()` để lấy đủ mọi lỗi của từng nhánh. Nó có thể ném một `CompletionException` tương ứng một nguyên nhân theo đặc tả.

Muốn biết kết quả đầy đủ:

- Giữ reference tới mỗi future.
- Đặt `handle`/`whenComplete` riêng ở từng nhánh để ghi trạng thái và nguyên nhân.
- Đợi đủ các stage đã **chuyển về kết quả an toàn**, rồi đọc aggregate data.

### 9.3. Mẫu thu thập kết quả tất cả nhánh mà không bỏ mất lỗi

~~~java
CompletableFuture<String> safeA = a.handle(
        (value, error) -> error == null ? "A=" + value : "A=ERROR");
CompletableFuture<String> safeB = b.handle(
        (value, error) -> error == null ? "B=" + value : "B=ERROR");
CompletableFuture<String> safeC = c.handle(
        (value, error) -> error == null ? "C=" + value : "C=ERROR");

CompletableFuture<Void> safelyAll =
        CompletableFuture.allOf(safeA, safeB, safeC);

safelyAll.join();

String summary = safeA.join() + "," + safeB.join() + "," + safeC.join();
// "A=A,B=ERROR,C=C"
~~~

Đây là **đoạn minh họa** tiếp nối giá trị `a,b,c` ở mục 9.1. `handle` chuyển từng outcome thành nhãn rõ ràng; aggregate trên **safe stages** có thể hoàn thành bình thường nếu các handler này không ném lỗi. Bản gốc `b` vẫn exceptional, không bị làm thành công lại.

**Đừng che mất lỗi trong ứng dụng thật:** thay `"B=ERROR"` bằng một result type có code/nguyên nhân nếu cần audit, retry hoặc báo cáo đầy đủ.

### 9.4. allOf với mảng rỗng

`CompletableFuture.allOf()` không có arguments trả một CompletableFuture **đã hoàn thành bình thường** với null. Đừng nhầm điều này với `anyOf()` rỗng ở mục tiếp theo.

## 10. anyOf: kết quả của future hoàn thành đầu tiên, kể cả lỗi

`CompletableFuture.anyOf(f1,f2,...)` trả `CompletableFuture<Object>`. Nó hoàn thành khi một input hoàn thành và dùng **cùng outcome** của input được chọn:

- Nếu input đầu tiên được phản ánh là **success**, aggregate thành success.
- Nếu input đầu tiên được phản ánh là **exception**, aggregate thành exceptional.
- Các input khác không tự bị cancel hay dừng.
- Kết quả thường là `Object`, cần kiểm soát kiểu dữ liệu nếu inputs khác nhau.

~~~java
CompletableFuture<String> fast = new CompletableFuture<>();
CompletableFuture<String> slow = new CompletableFuture<>();

CompletableFuture<Object> first =
        CompletableFuture.anyOf(fast, slow);

fast.completeExceptionally(
        new IllegalArgumentException("fast failed"));

slow.complete("LATER_OK");

// first đã exceptional.
// slow.join() vẫn là "LATER_OK".
~~~

Đây là **đoạn minh họa** có thứ tự completion rõ. **`anyOf` không phải “lấy kết quả thành công đầu tiên”**. Nếu một nhánh lỗi hoàn thành sớm, kết quả anyOf có thể lỗi dù nhánh khác sau đó thành công.

### 10.1. anyOf và thenCombine khác nhau

| Công cụ | Điều kiện ghép | Khi có lỗi |
| --- | --- | --- |
| `thenCombine` | Cả hai hoàn thành bình thường để chạy combiner | Combined stage exceptional, combiner không chạy |
| `allOf` | Tất cả input đã hoàn thành | Aggregate exceptional nếu bất kỳ input lỗi |
| `anyOf` | Một input đã hoàn thành | Aggregate nhận outcome của input được chọn, kể cả lỗi |
| `thenCompose` | Source success rồi theo một inner stage | Lỗi outer/inner phản ánh ở flattened stage |

Nếu cần “đua lấy **một thành công** nhưng bỏ qua thất bại sớm”, phải thiết kế orchestration có trạng thái để đếm fail, lựa chọn success, xử lý khi **tất cả** đều fail, và ngừng task không cần thiết theo lifecycle cụ thể. Không thay bằng `anyOf` rồi hy vọng nó tự bỏ qua exception.

### 10.2. anyOf với mảng rỗng

`CompletableFuture.anyOf()` không có arguments trả một future **chưa hoàn thành**. Với yêu cầu runtime không được phép chờ vô hạn, đây là case cần xử lý khi danh sách input có thể rỗng. Không gọi `join()` trên kết quả rỗng mà không có contract/timeout.

## 11. "Either" không đồng nghĩa "bất kỳ một nhánh, kể cả lỗi"

`applyToEither`, `acceptEither` và `runAfterEither` dùng concept “hoàn thành bình thường của một trong hai input” để chạy callback theo Javadoc.

Ví dụ:

~~~java
CompletableFuture<String> a =
        CompletableFuture.completedFuture("A");
CompletableFuture<String> b =
        CompletableFuture.completedFuture("B");

CompletableFuture<String> chosen = a.applyToEither(
        b, String::toLowerCase);
~~~

Đây là **đoạn minh họa**. Callback nhận một kết quả bình thường và trả một giá trị đã biến đổi, nhưng không nên đòi đúng A hay B nếu cả hai đã completed và runtime có thể chọn một ứng viên hợp lệ.

**Cẩn trọng với race giữa exceptional completion và normal completion:** đừng diễn giải `applyToEither` như một retry strategy luôn chờ đến khi có một success, đặc biệt khi một nhánh thất bại sớm hoặc cả hai thất bại. Kiểu xử lý lỗi cụ thể cần được kiểm tra theo hợp đồng `CompletionStage` và JDK đang chạy. Nếu business cần semantics “first successful result”, thiết kế rõ luật hoàn thành và test concurrency thay vì suy đoán.

### 11.1. Khi callback của either ném lỗi

Dù một input đã success, chính callback `fn` của `applyToEither` vẫn có thể ném exception; dependent stage lúc đó exceptional. Vì vậy **success của nguồn** chưa bảo đảm **success của mọi descendant**.

## 12. Cancellation và lỗi trên các nhánh

`CompletableFuture.cancel(...)` đánh dấu một future là canceled, và với CompletableFuture nó được coi là **exceptional completion** với `CancellationException`. Các dependent stages cần thành công có thể hoàn thành exceptional với nguyên nhân cancellation.

~~~java
CompletableFuture<Integer> source = new CompletableFuture<>();
CompletableFuture<Integer> child = source.thenApply(x -> x + 1);

source.cancel(true);

// source.isCancelled() == true.
// child.isCompletedExceptionally() == true.
// child có thể isCancelled() == false vì child không bị gọi cancel trực tiếp.
~~~

Đây là **đoạn minh họa**.

### 12.1. Cancellation của child có hủy source không?

Không tự động. Nếu `child.cancel(...)` được gọi, nó quyết định completion của **child**, không quay ngược lại `source` để hủy computation nguồn theo mặc định. Các sibling stages khác có thể vẫn chạy/hoàn thành.

Do đó, nếu một UI view không còn cần kết quả, việc cancel một dependent future không đủ bảo đảm ngừng network request nguồn hay xử lý của các view khác.

### 12.2. cancel(true) không cam kết interrupt supplier

`CompletableFuture` không trực tiếp quản lý vòng đời tất cả tác vụ làm nó hoàn thành. Theo Javadoc, tham số `mayInterruptIfRunning` **không có hiệu lực để interrupt computation của CompletableFuture**. Nếu cần cancel I/O thực sự, quản lý task handle, interrupt/cooperative cancellation, request cancellation và timeout ở tầng liên quan.

### 12.3. Lỗi cancellation qua dependents có thể được wrap

Một future bị cancel trực tiếp có thể khiến `join()` ném `CancellationException`. Nhưng một child bị hoàn thành exceptional do cancellation của parent thường thấy một `CompletionException` có nguyên nhân `CancellationException`. Khi log nguyên nhân, cần unwrap phù hợp thay vì mặc định mọi stage canceled đều có cùng lớp exception bên ngoài.

### 12.4. Đừng đồng nhất cancellation với failure do business rule

Cancellation có thể nghĩa là user không còn chờ, tác vụ bị đóng hoặc timeout policy; business failure có thể nghĩa dữ liệu không hợp lệ. Một handler tổng quát bắt `Throwable` có thể khiến mọi thứ bị coi là cùng một lỗi retry. Hãy phân loại đúng để quyết định log, retry, warning và luồng kiểm soát.

## 13. Exception wrapping: get, join và root cause

### 13.1. get và join có kiểu wrapper khác nhau

Với một future completed exceptionally bằng `IllegalArgumentException`:

~~~java
CompletableFuture<Integer> bad = new CompletableFuture<>();
bad.completeExceptionally(
        new IllegalArgumentException("bad input"));
~~~

Khi đọc:

~~~java
try {
    bad.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
    // cause thường là IllegalArgumentException.
}
~~~

~~~java
try {
    bad.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // cause thường là IllegalArgumentException.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Giữ interrupt status cho tầng cao hơn.
}
~~~

Đây là **đoạn minh họa**, cần import `CompletionException`, `ExecutionException`. `join()` tránh checked exceptions, nhưng **không làm lỗi biến mất**. `get()` có checked `InterruptedException`; không nuốt ngầm interruption.

### 13.2. Lỗi có thể được bọc nhiều tầng

Khi exception đi qua nhiều dependent stages, các callback và adapters có thể cung cấp một `CompletionException` bên ngoài một cause. **Không dựa vào đúng số lớp wrapper** để xác định lỗi domain. Hãy unwrap các lớp wrapper tiêu chuẩn khi cần diagnostics, nhưng lưu ý:

- Chỉ unwrap loại wrapper mà contract của hệ thống định nghĩa.
- Không biến mọi Throwable thành một loại nghiệp vụ vô nghĩa.
- Giữ original cause/stack trace khi log hoặc chuyển lỗi.
- Không lặp vô hạn nếu gặp một exception graph bất thường.

Một helper minh họa trong chương trình chạy đầy đủ:

~~~java
static String rootCause(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current.getClass().getSimpleName()
            + ": " + current.getMessage();
}
~~~

Đây là **đoạn phương thức minh họa đặt bên trong class**, không phải file độc lập.

### 13.3. Khi giá trị thành công là null

`complete(null)` tạo success. Trong `handle((value,error))`, cả value và error có thể null. Vì vậy:

~~~java
CompletableFuture<String> f =
        CompletableFuture.completedFuture(null);

String label = f.handle((value, error) ->
        error == null ? "SUCCESS" : "FAILED").join();

// label == "SUCCESS".
~~~

Đừng dùng `value == null` để kết luận stage lỗi. Phải nhìn `error` và contract kiểu dữ liệu đầu ra.

## 14. Ví dụ Java 8 hoàn chỉnh: chuỗi, nhánh, ghép và thu lỗi

Lưu toàn bộ chương trình sau thành **ErrorPropagationDemo.java**. Nó chỉ dùng future được hoàn thành bằng dữ liệu cố định và callbacks đồng bộ, nên stdout không phụ thuộc thread scheduling, thời điểm thực hay timezone. Chương trình đã được kiểm thử bằng `javac --release 8`.

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class ErrorPropagationDemo {
    static String rootCause(Throwable error) {
        Throwable current = error;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current.getClass().getSimpleName() + ": " + current.getMessage();
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger skipped = new AtomicInteger();
        CompletableFuture<Integer> original = new CompletableFuture<>();
        CompletableFuture<Integer> chainFailed = original
                .thenApply(x -> x + 1)
                .thenApply(x -> {
                    throw new IllegalStateException("step2");
                });
        CompletableFuture<Integer> skippedStage = chainFailed.thenApply(x -> {
            skipped.incrementAndGet();
            return x * 2;
        });
        CompletableFuture<Integer> chainRecovered =
                skippedStage.exceptionally(error -> -1);
        original.complete(3);
        System.out.println("chain root = " + original.join());
        System.out.println("chain failed = "
                + chainFailed.isCompletedExceptionally());
        System.out.println("chain skipped calls = " + skipped.get());
        System.out.println("chain recovered = " + chainRecovered.join());

        CompletableFuture<Integer> failedInput = new CompletableFuture<>();
        CompletableFuture<Integer> recoverEarly =
                failedInput.exceptionally(error -> 5)
                        .thenApply(x -> x + 1);
        CompletableFuture<Integer> recoverLate =
                failedInput.thenApply(x -> x * 2)
                        .exceptionally(error -> -7);
        failedInput.completeExceptionally(
                new IllegalArgumentException("input"));
        System.out.println("early recovery = " + recoverEarly.join());
        System.out.println("late recovery = " + recoverLate.join());
        System.out.println("source still failed = "
                + failedInput.isCompletedExceptionally());

        CompletableFuture<Integer> forkRoot = new CompletableFuture<>();
        CompletableFuture<Integer> badBranch = forkRoot.thenApply(x -> {
            throw new IllegalStateException("branch-A");
        });
        CompletableFuture<Integer> goodBranch =
                forkRoot.thenApply(x -> x * 3);
        CompletableFuture<Integer> recoveredBranch =
                badBranch.exceptionally(error -> 20);
        forkRoot.complete(10);
        System.out.println("fork root = " + forkRoot.join());
        System.out.println("fork branch A failed = "
                + badBranch.isCompletedExceptionally());
        System.out.println("fork branch B = " + goodBranch.join());
        System.out.println("fork recovered A = " + recoveredBranch.join());

        CompletableFuture<Integer> left = new CompletableFuture<>();
        CompletableFuture<Integer> right = new CompletableFuture<>();
        AtomicInteger combineCalls = new AtomicInteger();
        CompletableFuture<Integer> combination = left.thenCombine(
                right, (a, b) -> {
                    combineCalls.incrementAndGet();
                    return a + b;
                });
        left.completeExceptionally(new IllegalStateException("left"));
        right.complete(8);
        System.out.println("combine failed = "
                + combination.isCompletedExceptionally());
        System.out.println("combine action calls = " + combineCalls.get());
        System.out.println("independent right = " + right.join());

        CompletableFuture<Integer> composed =
                CompletableFuture.completedFuture(4)
                        .thenCompose(x -> {
                            CompletableFuture<Integer> inner =
                                    new CompletableFuture<>();
                            inner.completeExceptionally(
                                    new UnsupportedOperationException("inner"));
                            return inner;
                        });
        System.out.println("compose failed cause = "
                + composed.handle((value, error) ->
                        rootCause(error)).join());

        CompletableFuture<String> allA =
                CompletableFuture.completedFuture("A");
        CompletableFuture<String> allB = new CompletableFuture<>();
        CompletableFuture<String> allC = new CompletableFuture<>();
        CompletableFuture<Void> all =
                CompletableFuture.allOf(allA, allB, allC);
        allB.completeExceptionally(
                new IllegalStateException("all-B"));
        System.out.println("all before last done = " + all.isDone());
        allC.complete("C");
        System.out.println("all after last failed = "
                + all.isCompletedExceptionally());
        System.out.println("all cause = " + all.handle(
                (unused, error) -> rootCause(error)).join());
        System.out.println("all independent C = " + allC.join());

        CompletableFuture<String> safeA =
                allA.handle((value, error) ->
                        error == null ? "A=" + value : "A=ERROR");
        CompletableFuture<String> safeB =
                allB.handle((value, error) ->
                        error == null ? "B=" + value : "B=ERROR");
        CompletableFuture<String> safeC =
                allC.handle((value, error) ->
                        error == null ? "C=" + value : "C=ERROR");
        CompletableFuture.allOf(safeA, safeB, safeC).join();
        System.out.println("aggregate statuses = "
                + safeA.join() + "," + safeB.join() + "," + safeC.join());

        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        CompletableFuture<Object> any =
                CompletableFuture.anyOf(first, second);
        first.completeExceptionally(
                new IllegalArgumentException("first-error"));
        second.complete("LATER_OK");
        System.out.println("any failed = "
                + any.isCompletedExceptionally());
        System.out.println("any cause = "
                + any.handle((value, error) -> rootCause(error)).join());
        System.out.println("any independent second = " + second.join());

        CompletableFuture<Integer> good =
                CompletableFuture.completedFuture(9);
        CompletableFuture<Integer> observeGood = good.whenComplete(
                (value, error) -> {
                    throw new IllegalStateException("observer");
                });
        System.out.println("observer on good = "
                + observeGood.handle((value, error) ->
                        rootCause(error)).join());

        CompletableFuture<Integer> fail =
                new CompletableFuture<>();
        CompletableFuture<Integer> observeFail = fail.whenComplete(
                (value, error) -> {
                    throw new IllegalStateException("observer");
                });
        fail.completeExceptionally(
                new IllegalArgumentException("original-error"));
        System.out.println("observer on failure = "
                + observeFail.handle((value, error) ->
                        rootCause(error)).join());

        CompletableFuture<Integer> canceled = new CompletableFuture<>();
        CompletableFuture<Integer> cancelChild =
                canceled.thenApply(x -> x + 1);
        canceled.cancel(true);
        System.out.println("source canceled = " + canceled.isCancelled());
        System.out.println("child canceled = " + cancelChild.isCancelled());
        System.out.println("child exceptional = "
                + cancelChild.isCompletedExceptionally());
        System.out.println("child cause = "
                + cancelChild.handle((value, error) ->
                        rootCause(error)).join());

        CompletableFuture<Integer> failedRead = new CompletableFuture<>();
        failedRead.completeExceptionally(
                new IllegalArgumentException("read-error"));
        try {
            failedRead.join();
        } catch (CompletionException error) {
            System.out.println("join wrapper = "
                    + error.getClass().getSimpleName());
        }
        try {
            failedRead.get();
        } catch (ExecutionException error) {
            System.out.println("get wrapper = "
                    + error.getClass().getSimpleName());
        }
    }
}
~~~

Lệnh biên dịch với JDK có hỗ trợ `--release 8` (ví dụ JDK 17+):

~~~bash
javac --release 8 ErrorPropagationDemo.java
java ErrorPropagationDemo
~~~

**Stdout chính xác đã được xác minh bằng JDK:**

~~~text
chain root = 3
chain failed = true
chain skipped calls = 0
chain recovered = -1
early recovery = 6
late recovery = -7
source still failed = true
fork root = 10
fork branch A failed = true
fork branch B = 30
fork recovered A = 20
combine failed = true
combine action calls = 0
independent right = 8
compose failed cause = UnsupportedOperationException: inner
all before last done = false
all after last failed = true
all cause = IllegalStateException: all-B
all independent C = C
aggregate statuses = A=A,B=ERROR,C=C
any failed = true
any cause = IllegalArgumentException: first-error
any independent second = LATER_OK
observer on good = IllegalStateException: observer
observer on failure = IllegalArgumentException: original-error
source canceled = true
child canceled = false
child exceptional = true
child cause = CancellationException: null
join wrapper = CompletionException
get wrapper = ExecutionException
~~~

### 14.1. Giải thích nhóm kết quả chuỗi

- `original` thành công bằng 3. Bước `+1` hoàn thành, bước kế tiếp ném `IllegalStateException("step2")`.
- `chainFailed` exceptional; lambda của `skippedStage` không chạy, nên `skipped.get()==0`.
- `chainRecovered` có giá trị -1 nhờ `exceptionally`, nhưng source và stage failed vẫn giữ outcome tương ứng.

### 14.2. Giải thích vị trí recovery

- `recoverEarly` xử lý lỗi thành 5 **trước** phép cộng nên trả 6.
- `recoverLate` bỏ qua phép nhân 2 và trả fallback -7 vì xử lý lỗi **sau**.
- `failedInput` vẫn failed, cho thấy handler tạo stage mới chứ không sửa nguồn.

### 14.3. Giải thích các sibling branches

- `forkRoot` thành công bằng 10.
- `badBranch` ném lỗi nên exceptional.
- `goodBranch` chạy phép nhân 3 và thành công bằng 30.
- `recoveredBranch` xử lý lỗi nhánh A thành 20. Cả source lẫn nhánh B không bị thay đổi.

### 14.4. Giải thích ghép hai nguồn và thenCompose

- `left` failed, `right` thành công 8: `thenCombine` không chạy combiner, nên `combineCalls==0` và stage kết hợp failed.
- `composed` failed vì inner stage được trả về từ `thenCompose` hoàn thành exceptional. Helper `rootCause` giải thích lý do `UnsupportedOperationException: inner`.

### 14.5. Giải thích allOf và anyOf

- `allOf` chưa completed khi `allC` còn pending, dù `allB` đã failed. Sau `allC.complete("C")`, aggregate failed theo `allB` trong ví dụ có một lỗi.
- `allC` vẫn thành công, minh họa `allOf` không hủy sibling.
- `safeA/safeB/safeC` dùng `handle` để tạo ba outcome đọc được và đợi đủ tất cả.
- `anyOf` failed khi `first` hoàn thành exceptional trước; `second` hoàn thành sau bằng `LATER_OK` nhưng không thay đổi outcome của aggregate.

### 14.6. Giải thích callback, cancel và exception wrapping

- `whenComplete` trên success rồi throw làm stage trả về failed với lỗi observer.
- `whenComplete` trên failed source rồi observer cũng throw giữ lỗi nguồn ưu tiên.
- `canceled` bị cancel trực tiếp nhưng `cancelChild` nhận lỗi lan truyền, không nhất thiết `isCancelled()==true`.
- `join` và `get` đọc một failed future qua wrapper khác nhau: `CompletionException` và `ExecutionException`.

**Phạm vi kiểm chứng:** Đây là ví dụ deterministic về semantics của `CompletableFuture`, không phải benchmark hiệu năng hoặc kiểm thử thứ tự callback giữa nhiều thread. Code chạy trong một tiến trình và không cần network/database.

## 15. Những lỗi thường gặp khi lan truyền lỗi

### Lỗi 1 — Nghĩ lỗi của một nhánh làm hỏng toàn bộ các nhánh khác

Nếu source success, lỗi bên trong nhánh A chỉ lan xuống descendants của A, không ngược lên source hoặc ngang sang nhánh B. **Sửa:** đọc đúng đồ thị dependency; giữ branch-specific handlers khi cần.

### Lỗi 2 — Nghĩ lỗi ở nguồn chung chỉ ảnh hưởng một nhánh

Nếu source failed, các nhánh yêu cầu source success đều không nhận được value. **Sửa:** recovery tại source trung gian nếu cần chính sách chung, hoặc recover riêng từng nhánh.

### Lỗi 3 — Giả định thenApply sẽ chạy cả khi upstream failed

Không. `thenApply` là đường success. **Sửa:** dùng `exceptionally`/`handle` để xử lý exceptional completion thay vì chờ biến đổi bình thường chạy với một Throwable.

### Lỗi 4 — Bỏ qua vị trí đặt exceptionally

Recovery sớm có thể khiến bước sau chạy trên fallback; recovery muộn bỏ qua bước biến đổi trước nó. **Sửa:** vẽ đồ thị chain trước khi chọn vị trí handler.

### Lỗi 5 — Nghĩ exceptionally sửa source

Không. Nó tạo một dependent stage. **Sửa:** giữ reference tới stage đã recovery khi muốn downstream nhận fallback.

### Lỗi 6 — Chỉ dùng whenComplete để biến lỗi thành success

`whenComplete` không trả value; nếu observer không throw thì outcome cũ được chuyển qua. **Sửa:** dùng `handle` hoặc `exceptionally` khi cần recovery.

### Lỗi 7 — Observer khi source thành công lại ném exception

Stage trả về bởi `whenComplete` có thể thành failed vì lỗi observer, làm hỏng pipeline dù business computation thành công. **Sửa:** logger/metrics observer nên quản lý lỗi riêng.

### Lỗi 8 — Tưởng observer throw sẽ ghi đè lỗi nguồn đã failed

Trong trường hợp source đã exceptional, quy tắc `whenComplete` ưu tiên lỗi nguồn trên stage trả về. **Sửa:** đừng dựa vào observer throw để thay thế nguyên nhân đã có.

### Lỗi 9 — Nghĩ thenCompose che mất lỗi của inner future

`thenCompose` làm phẳng stage; lỗi inner đi qua flattened stage. **Sửa:** dùng thenCompose thay vì thenApply trả nested future khi cần chờ đúng outcome.

### Lỗi 10 — Tưởng thenCombine chạy khi một trong hai branch lỗi

Combiner cần **cả hai** hoàn thành bình thường. **Sửa:** định nghĩa fallback tại mỗi nhánh trước combine hoặc recovery aggregate sau combine.

### Lỗi 11 — Nghĩ allOf là fail-fast và tự dừng các tác vụ khác

`allOf` đợi mọi input completed theo contract; không tự cancel/interrupt các nguồn khác. **Sửa:** quản lý cancellation, deadline và task lifecycle riêng.

### Lỗi 12 — Nghĩ allOf thu thập đủ mọi nguyên nhân lỗi

Aggregate không hứa tạo list tất cả failures. **Sửa:** xử lý từng input bằng `handle`/status object rồi ghép kết quả báo cáo.

### Lỗi 13 — Dùng anyOf để đợi thành công đầu tiên

`anyOf` có thể chốt exception từ nhánh hoàn thành sớm. **Sửa:** nếu cần first success, viết orchestration có chính sách bỏ qua lỗi sớm và xử lý all-failed.

### Lỗi 14 — Gọi anyOf() rỗng rồi join vô hạn

Không có input, result future chưa completed. **Sửa:** validation danh sách input trước khi ghép, định nghĩa trường hợp rỗng.

### Lỗi 15 — Nhầm allOf() rỗng với anyOf() rỗng

`allOf()` rỗng đã completed bình thường với null; `anyOf()` rỗng pending. **Sửa:** kiểm thử cả hai biên.

### Lỗi 16 — Xem cancellation giống mọi business error khác

Cancellation có ngữ nghĩa riêng, có thể cần bỏ retry/log. **Sửa:** xét `CancellationException` và tình trạng `isCancelled` theo stage cụ thể.

### Lỗi 17 — Tin cancel child sẽ cancel source và siblings

Cancellation không tự truyền ngược lên cha hoặc ngang qua siblings. **Sửa:** hủy tác vụ nguồn riêng khi nghiệp vụ thật sự không còn cần nó.

### Lỗi 18 — Nghĩ cancel(true) chắc chắn interrupt supplyAsync

CompletableFuture không dùng flag này để dừng underlying processing. **Sửa:** điều khiển task/IO/executor theo API cụ thể.

### Lỗi 19 — Dùng join ở giữa chuỗi nonblocking và gây deadlock

Nếu cùng executor nhỏ phải chạy task hoàn thành future mà worker đang block chờ `join`, hệ thống có thể deadlock. **Sửa:** dùng `thenCompose`/`thenCombine`/`handle` để ghép không blocking.

### Lỗi 20 — Nuốt InterruptedException từ get

`get()` có thể bị interrupt. **Sửa:** xử lý chính sách cancellation hoặc khôi phục interrupt status khi phù hợp.

### Lỗi 21 — Mất nguyên nhân gốc sau nhiều lần wrapping

`CompletionException` và `ExecutionException` có thể bọc lỗi business. **Sửa:** unwrap có kiểm soát, giữ stacktrace/cause và log tại boundary thích hợp.

### Lỗi 22 — Nghĩ isDone() đồng nghĩa thành công

`isDone` true cả lỗi/cancel. **Sửa:** xem outcome thực tế hoặc dùng handler để diễn giải đúng.

### Lỗi 23 — Dùng một giá trị fallback giả cho dữ liệu quan trọng

Nếu giá sản phẩm không tồn tại, fallback 0 có thể tạo thanh toán sai. **Sửa:** chỉ recover khi business cho phép; nếu không, giữ exceptional completion và trả lỗi đúng contract.

### Lỗi 24 — Truyền Throwable raw ra API công khai

Các exception internal có thể chứa thông tin nhạy cảm hoặc stacktrace. **Sửa:** phân loại và map thành error code/message an toàn tại boundary; log nội bộ đầy đủ nguyên nhân khi được phép.

### Lỗi 25 — Ghi side effect trước recovery nhưng nghĩ recovery rollback nó

CompletableFuture không tự transactionally undo email/DB/network trước đó. **Sửa:** dùng transaction, idempotency key, saga/compensation theo yêu cầu nghiệp vụ.

### Lỗi 26 — Test thứ tự callback sibling cứng nhắc

Hai sibling stages có thể chạy trên các thread/tại các thời điểm không cố định. **Sửa:** test giá trị và bất biến, không assert thứ tự log trừ khi chain phụ thuộc rõ ràng.

### Lỗi 27 — Dùng async method mà không kiểm soát executor

`thenApplyAsync` hoặc `supplyAsync` có thể dùng executor mặc định; với workload blocking, resource có thể không phù hợp. **Sửa:** chọn executor rõ theo tải và quản lý shutdown.

### Lỗi 28 — Dùng API thêm sau Java 8 trên baseline Java 8

`failedFuture`, `orTimeout`, `completeOnTimeout` được thêm sau Java 8; các biến thể `exceptionallyCompose`/`exceptionallyAsync` cũng không có trong Java 8 gốc. **Sửa:** khi target Java 8, dùng `new CompletableFuture` + `completeExceptionally`, `ScheduledExecutorService` và `handle/thenCompose` phù hợp; nếu dùng JDK mới, nêu baseline rõ.

## 16. Thiết kế pipeline lỗi an toàn trong ứng dụng thật

### 16.1. Phân loại lỗi ngay tại boundary

Không phải mọi exception đều cùng chính sách:

| Loại failure | Ví dụ | Chính sách thường gặp |
| --- | --- | --- |
| Input validation | `IllegalArgumentException`, business validation | Không tự retry cùng dữ liệu |
| Transient network | Timeout tạm thời, kết nối chập chờn | Retry giới hạn nếu idempotent |
| Authorization | Quyền truy cập không hợp lệ | Fail fast, thông báo kiểm soát |
| Cancellation | User không còn chờ | Hủy/giải phóng tài nguyên nếu có thể |
| Downstream unavailable | DB/service khác lỗi | Fallback có kiểm soát hoặc fail theo SLA |
| Programming bug | NPE trong lambda | Báo lỗi/giám sát; không nuốt rồi trả success giả |

Một `exceptionally(error -> defaultValue)` toàn cục có thể khiến các lỗi lập trình nghiêm trọng bị ẩn. Nên phân loại root cause ở nơi có đủ ngữ cảnh và chỉ recover những tình huống thật sự có giải pháp.

### 16.2. Log tại boundary, tránh log trùng trên mọi stage

Nếu cùng một lỗi lan qua 5 stages, việc gắn `whenComplete` log cùng stacktrace ở mọi stage có thể tạo 5 bản ghi giống nhau. Chọn một vài boundary có ý nghĩa:

- Lúc nguồn I/O thất bại, ghi context request/correlation ID.
- Lúc chuyển lỗi thành fallback, ghi rõ policy đã sử dụng.
- Lúc trả API, map domain error sang response mã hóa an toàn.

Hãy giữ **correlation ID** hoặc tracing context theo thư viện phù hợp, không giả định context của `ThreadLocal` tự đi qua các async callbacks.

### 16.3. Không làm mất lỗi khi thu thập nhánh

Một cấu trúc kết quả minh họa:

~~~java
final class BranchResult<T> {
    final T value;
    final Throwable error;

    private BranchResult(T value, Throwable error) {
        this.value = value;
        this.error = error;
    }

    static <T> BranchResult<T> success(T value) {
        return new BranchResult<>(value, null);
    }

    static <T> BranchResult<T> failure(Throwable error) {
        return new BranchResult<>(null, error);
    }
}
~~~

Đây là **class minh họa riêng**, cần đặt trong file Java phù hợp khi áp dụng. Một nhánh có thể chuyển outcome thành `BranchResult` bằng `handle`, rồi `allOf` các futures chứa result này. Điều quan trọng: **giữ cả value và error** để quyết định sau khi biết kết quả của toàn bộ nhánh.

### 16.4. Không coi lỗi async là câu trả lời "không có kết quả"

`null` có thể là success theo hợp đồng. Nếu API cần phân biệt:

- Không có object do nghiệp vụ (not found).
- Task thất bại.
- Task bị cancel.
- Task chưa hoàn thành.

Hãy biểu diễn thành result type/error policy rõ ràng, không nhét tất cả vào `null` hoặc cùng một chuỗi `"N/A"`.

### 16.5. Retry cần xem task có idempotent không

Một branch failed sau khi side effect đã gửi thành công nhưng ack thất bại. Retry ngay có thể gây duplicate. CompletableFuture chỉ mang outcome, không bảo đảm operation thật chưa thực hiện. Trước khi retry, xác định transaction boundary, idempotency key, backoff và khả năng rollback/compensation.

## 17. Bảng chọn API theo quan hệ phụ thuộc

| Ý định | Dùng | Chú ý lỗi |
| --- | --- | --- |
| Biến đổi sau khi một nguồn thành công | `thenApply` | Upstream lỗi → action không chạy |
| Tiếp tục tác vụ bất đồng bộ theo trình tự | `thenCompose` | Lỗi của inner stage lan tới flattened stage |
| Đợi hai kết quả bình thường rồi kết hợp | `thenCombine` | Một bên failed → combiner không chạy |
| Đợi mọi future hoàn thành | `allOf` | Một bên failed → aggregate failed, không có list lỗi |
| Nhận outcome hoàn thành đầu tiên | `anyOf` | Có thể nhận exception của nhánh sớm |
| Recover lỗi bằng fallback cùng kiểu | `exceptionally` | Đặt sớm/muộn thay đổi pipeline phía sau |
| Xử lý cả success và failure, có thể đổi kiểu | `handle` | Handler ném lỗi → stage mới failed |
| Quan sát lỗi/giá trị | `whenComplete` | Observer có thể ảnh hưởng outcome stage trả về nếu tự ném |
| Xác định failure type khi đọc blocking | `get`/`join` | Exception wrapping khác nhau |
| Tạo future đã failed bằng API Java 8 | `new CompletableFuture` + `completeExceptionally` | `failedFuture` chỉ có trên JDK mới |
| Thực thi action với explicit executor | `thenApplyAsync(...,executor)` | Chỉ thay execution context, không đổi luật lỗi |
| Hủy một dependent future | `cancel` trên child | Không tự hủy source/siblings |
| Chờ nhánh không lỗi dù sibling failed | Giữ mỗi branch future | Đừng chỉ đọc aggregate `allOf` |

## 18. Checklist kiểm thử lỗi theo chuỗi và theo nhánh

1. Source hoàn thành bình thường; stage thứ hai ném lỗi.
2. Stage phía sau stage lỗi **không chạy** lambda bình thường.
3. Source và các stage trước stage lỗi giữ kết quả ban đầu.
4. Recovery cuối chuỗi trả fallback đúng kiểu.
5. Recovery sớm tạo dữ liệu cho transform phía sau.
6. Một nhánh failed sau source success **không** phá sibling.
7. Lỗi ở **source chung** ảnh hưởng các nhánh phụ thuộc cần success.
8. Recovery một nhánh **không** sửa source hoặc sibling.
9. `thenCompose` nhận outer failure, composer failure và inner failure.
10. `thenCombine` action không chạy khi bất kỳ input failed.
11. Ghép hai nhánh có fallback **đúng nghiệp vụ**, không trả giá giả nguy hiểm.
12. `allOf` chưa completed khi còn input pending.
13. `allOf` failed nếu ít nhất một input failed.
14. `allOf` không tự cancel input còn lại.
15. Thu thập thành công/thất bại của từng input qua `handle` trước aggregation.
16. `anyOf` nhận lỗi của một input hoàn thành sớm, ngay cả khi input khác sau thành công.
17. Input list rỗng có policy riêng cho `allOf` và `anyOf`.
18. `whenComplete` observer không throw trong đường production thông thường.
19. Khi observer throw trên success, stage phụ thuộc nhận lỗi observer.
20. Khi observer throw trên failure, error gốc được ưu tiên.
21. Parent bị cancel, child phản ánh exceptional completion; không giả định child tự `isCancelled()==true`.
22. Child cancel không tự cancel parent hoặc sibling.
23. `get` và `join` được catch đúng các kiểu wrapper và interruption.
24. Thử future success bằng `null`, không suy thành failure.
25. Test retry/timeout không giả định callback/thread winner cố định.
26. Kiểm thử không để executor còn thread sống sau khi hoàn tất.
27. Nếu có I/O, xác định idempotency, transaction, cleanup riêng.
28. Nếu API target Java 8, kiểm tra compilation với `--release 8`.

### 18.1. Các ca giá trị ngắn

| Test | Kết quả chính |
| --- | --- |
| `completedFuture(3).thenApply(x->x+1)` | 4 |
| Transform lambda ném lỗi | Dependent stage exceptional |
| `failed.exceptionally(e->5)` | Stage mới trả 5 |
| Recovery sau transform lỗi | Không chạy transform bị chặn |
| Hai sibling trên nguồn 10 | Một có thể lỗi, một trả 30 |
| `thenCombine` một bên lỗi | Combiner skip |
| `thenCompose` inner failed | Stage làm phẳng failed |
| `allOf` một lỗi, một pending | Chưa hoàn thành đến khi tất cả done |
| `allOf` mọi input done, một lỗi | Aggregate exceptional |
| `anyOf` lỗi trước success | Aggregate exceptional |
| `whenComplete` success + observer lỗi | Stage observer failed |
| `whenComplete` source lỗi + observer lỗi | Stage observer giữ lỗi source |
| Parent cancel | Dependent stage exceptional |
| `join` đọc failed future | `CompletionException` theo thông lệ |
| `get` đọc failed future | `ExecutionException` |

## 19. Bài tập tự kiểm tra và đáp án

**Câu 1.** `source.thenApply(f).thenApply(g)` sẽ làm gì nếu `f` ném exception?

**Đáp án:** Stage của `f` exceptional; action `g` không chạy và stage của `g` thường hoàn thành exceptional do lỗi upstream.

**Câu 2.** Lỗi ở stage `g` có làm stage `source` trước đó thành failed không?

**Đáp án:** Không. Completion chỉ lan xuống các dependent stages, không ghi đè outcome của ancestor.

**Câu 3.** Hai sibling branches cùng xuất phát từ source success. A thất bại trong action, B có được thành công không?

**Đáp án:** Có. Lỗi của A không tự động biến B thành failed.

**Câu 4.** Nếu source chung failed, hai `thenApply` sibling có chạy callback không?

**Đáp án:** Không, vì cả hai đều cần source hoàn thành bình thường; chúng có thể hoàn thành exceptional và từng nhánh có thể recover riêng.

**Câu 5.** `exceptionally` đặt trước và sau `thenApply` có luôn cho cùng kết quả không?

**Đáp án:** Không. Nếu nguồn lỗi, recovery trước có thể cấp fallback để `thenApply` chạy; recovery sau bỏ qua transform rồi cấp fallback.

**Câu 6.** `exceptionally` có đổi state của source failed thành success không?

**Đáp án:** Không. Nó tạo dependent stage mới chứa kết quả đã phục hồi.

**Câu 7.** `thenCompose` trả về một inner failed future thì outer flattened stage ra sao?

**Đáp án:** Stage trả về từ `thenCompose` cũng exceptional do lỗi của inner stage.

**Câu 8.** Khi một input của `thenCombine` failed, biFunction combiner có chạy không?

**Đáp án:** Không. Nó chỉ chạy khi hai inputs đều thành công.

**Câu 9.** `allOf` có dừng các futures khác khi một future lỗi không?

**Đáp án:** Không. Nó đợi tất cả futures hoàn thành, và aggregate failed nếu có input lỗi; tác vụ nguồn phải được quản lý riêng.

**Câu 10.** Có thể lấy mọi nguyên nhân lỗi của tất cả branches từ duy nhất `allOf.join()` không?

**Đáp án:** Không có cam kết. Cần quan sát/thu thập từng future con bằng `handle` hoặc cơ chế tương đương.

**Câu 11.** `anyOf` có phải đợi nhánh success đầu tiên không?

**Đáp án:** Không. Một exceptional completion đến trước cũng có thể chốt lỗi cho aggregate.

**Câu 12.** `allOf()` và `anyOf()` với 0 inputs khác nhau thế nào?

**Đáp án:** `allOf()` trả future hoàn thành bình thường với null; `anyOf()` trả future còn pending.

**Câu 13.** `handle` và `whenComplete` khác nhau ở đâu?

**Đáp án:** `handle` trả một kết quả mới có thể khác kiểu, phù hợp recovery/chuyển đổi; `whenComplete` dùng để quan sát và theo quy tắc giữ original outcome nếu callback bình thường.

**Câu 14.** `whenComplete` trên source success mà observer throw thì sao?

**Đáp án:** Stage trả về bởi `whenComplete` có thể failed bởi exception observer; source success không đổi.

**Câu 15.** `whenComplete` trên source đã failed và observer cũng throw thì nguyên nhân nào ưu tiên?

**Đáp án:** Theo contract, lỗi source được ưu tiên ở dependent stage trả về.

**Câu 16.** Canceled parent thì child có nhất thiết `isCancelled()==true` không?

**Đáp án:** Không. Child có thể completed exceptionally với `CompletionException` chứa `CancellationException`, trong khi bản thân child không bị cancel trực tiếp.

**Câu 17.** Dùng `get` hoặc `join` khi cần bắt một business exception trong failed future?

**Đáp án:** Bắt wrapper tương ứng (`ExecutionException`, `CompletionException`, hoặc `CancellationException`) và xem cause theo chính sách; giữ interrupt flag khi bắt `InterruptedException`.

**Câu 18.** Có nên dùng một `exceptionally(e -> null)` duy nhất để che mọi lỗi?

**Đáp án:** Không mặc định. Nó có thể biến lỗi quan trọng thành success null, khiến caller không biết sự cố. Chỉ làm khi null là fallback hợp lệ theo contract.

**Câu 19.** Một `whenComplete` log lỗi ở mọi stage có thể gây vấn đề gì?

**Đáp án:** Log trùng một lỗi nhiều lần, tăng tải và gây khó truy dấu; chọn boundary hợp lý.

**Câu 20.** Vì sao cancel một dependent future không nhất thiết hủy tác vụ nguồn?

**Đáp án:** CompletableFuture không tự thiết kế cancellation lan ngược theo dependency, và `cancel(true)` không đảm bảo interrupt nguồn xử lý.

## 20. Tổng kết

- **Lỗi lan truyền theo các dependency edges:** ancestor failed làm các success-only descendants bỏ qua action; descendant failed không sửa ancestor hay sibling.
- **Recovery là một stage mới:** `exceptionally` và `handle` thay đổi outcome của đoạn pipeline **phía sau điểm recovery**, không làm nguồn failed thành success.
- **Vị trí recovery quan trọng:** recovery sớm cấp fallback cho transform; recovery muộn bỏ qua transform và xử lý lỗi tổng.
- **`thenCompose` làm phẳng stage bất đồng bộ** và đưa failure của inner stage ra kết quả cuối.
- **`thenCombine` yêu cầu cả hai input success**; lỗi một bên làm combiner không chạy, nhưng không tự dừng bên khác.
- **`allOf` đợi mọi input done** rồi failed nếu ít nhất một branch lỗi; không hứa gom tất cả exception hoặc tự hủy nguồn.
- **`anyOf` nhận outcome của future hoàn thành đầu tiên**, kể cả exceptional; không phải first-success combinator.
- **`handle` có thể chuyển đổi cả success/failure**, còn **`whenComplete` chủ yếu để quan sát**, cần tránh observer tự ném lỗi.
- **Cancellation** là exceptional completion, nhưng không tự chặn xử lý nguồn hay lan ngược/hủy sibling.
- **`join` và `get` khác cách wrap exception**; muốn hiểu lỗi domain nên giữ nguyên cause và unwrap có kiểm soát.
- Bài sử dụng các API Java 8 vẫn hỗ trợ trên JDK hiện hành; các method ra đời sau Java 8 được phân biệt để tránh lỗi tương thích.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — CompletableFuture](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 8 — CompletionStage](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionStage.html)
- [Oracle Java SE 8 — Future](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/Future.html)
- [Oracle Java SE 8 — CompletionException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionException.html)
- [Oracle Java SE 8 — ExecutionException](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ExecutionException.html)
- [Oracle Java SE 25 — CompletableFuture (API vẫn hỗ trợ)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Oracle Java SE 25 — CompletionStage](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionStage.html)
