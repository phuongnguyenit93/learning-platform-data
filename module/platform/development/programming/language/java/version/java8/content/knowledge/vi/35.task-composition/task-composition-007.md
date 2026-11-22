# CompletableFuture.handle: biến đổi cả kết quả lẫn ngoại lệ (Java 8+)

## 1. Bài toán: một pipeline có hai khả năng hoàn tất

Trong một dịch vụ Java, tác vụ tải thông tin đơn hàng có thể trả về kết quả thành công, hoặc hoàn tất ngoại lệ do dịch vụ phụ thuộc không phản hồi. Ứng dụng cần **đổi cả hai kết cục** thành một giá trị có thể sử dụng: khi thành công thì xây DTO hiển thị, khi thất bại thì trả một trạng thái dự phòng có chủ đích.

Đó là tình huống điển hình cho **CompletableFuture.handle**. Phương thức này thuộc **CompletionStage** từ Java 8 và tiếp tục được hỗ trợ trong các phiên bản Java hiện đại.

Ví dụ ngắn:

~~~java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(21);

CompletableFuture<String> displayed =
        source.handle((value, error) ->
                error == null ? "OK:" + (value * 2) : "FALLBACK");

System.out.println(displayed.join()); // OK:42
~~~

**handle** nhận **hai tham số**: kết quả bình thường **value** và ngoại lệ **error**. Nó chạy khi stage nguồn đã hoàn tất **bình thường hoặc ngoại lệ**. Hàm callback trả ra **một giá trị U mới**; giá trị đó được dùng để hoàn tất stage phụ thuộc mới.

Điều cần phân biệt từ đầu:

- **handle có thể phục hồi lỗi**, nhưng không bắt buộc phải phục hồi.
- **handle có thể biến đổi kết quả thành công** và thay đổi kiểu dữ liệu.
- **Nếu callback handle tự ném exception**, stage mà handle tạo ra vẫn có thể hoàn tất ngoại lệ.
- **handle không sửa lại kết quả/lỗi của stage nguồn**. Nó tạo stage mới với outcome mới.
- **handle không mặc nhiên chạy trên thread khác**. Muốn có cơ chế scheduling bất đồng bộ, dùng các overload handleAsync.

Bài sẽ phân tích chữ ký, luồng giá trị/lỗi, null, exception wrapping, cancellation, cách ghép pipeline, khác biệt với exceptionally/whenComplete/thenApply, handleAsync, lựa chọn fallback và kiểm thử bằng các chương trình Java chạy được.

## 2. CompletionStage và chữ ký của handle

**CompletableFuture<T>** là một hiện thực của **CompletionStage<T>** và **Future<T>**. Nó mô tả một kết quả có thể chưa sẵn sàng, đã thành công hoặc đã hoàn tất ngoại lệ.

Chữ ký trong API, viết từ góc nhìn một stage có kết quả T:

~~~java
<U> CompletionStage<U> handle(
        BiFunction<? super T, Throwable, ? extends U> fn);
~~~

Đây là chữ ký của **CompletionStage**. Với đối tượng **CompletableFuture<T>**, implementation của method trả **CompletableFuture<U>**.

**BiFunction** thuộc **java.util.function** và nhận hai đầu vào, trả một kết quả:

~~~java
U apply(T value, Throwable error);
~~~

Đoạn này là chữ ký khái niệm: trong Java thật, callback được truyền qua một lambda hoặc BiFunction, không khai báo tự do một method U apply ngoài class.

Với lambda:

~~~java
CompletableFuture<String> outcome =
        source.handle((value, error) -> {
            if (error != null) {
                return "NOT_AVAILABLE";
            }
            return "VALUE:" + value;
        });
~~~

Trong đoạn trên, **source** được giả định có kiểu **CompletableFuture<Integer>**. Kiểu T = Integer; kiểu U = String. Cả nhánh thành công lẫn nhánh lỗi trả một String, nên stage kết quả là CompletableFuture<String>.

**Khác thenApply:** callback của thenApply chỉ nhận T và chỉ chạy sau completion bình thường. Callback của handle nhận cả kết quả và ngoại lệ, được gọi với trạng thái thích hợp ở cả hai trường hợp.

## 3. Hai tham số value và error thực sự nhận gì?

Khi stage nguồn hoàn tất:

| Outcome của nguồn | Tham số value | Tham số error | handle có được gọi? |
| --- | --- | --- | --- |
| Bình thường với giá trị T khác null | Giá trị T | null | Có |
| Bình thường với giá trị null | null | null | Có |
| Hoàn tất ngoại lệ | null | Throwable khác null | Có |
| Chưa hoàn tất | Chưa được gọi | Chưa được gọi | Chưa |

Chú ý: **value == null không có nghĩa stage lỗi**. Một CompletableFuture có thể hoàn tất bình thường với null:

~~~java
CompletableFuture<String> empty =
        CompletableFuture.completedFuture(null);

String status = empty.handle((value, error) ->
        error != null ? "FAILED"
                : value == null ? "SUCCESS_WITH_NULL" : value).join();
// SUCCESS_WITH_NULL
~~~

Quy tắc an toàn khi quyết định nhánh:

~~~java
if (error != null) {
    // Hoàn tất ngoại lệ.
} else {
    // Hoàn tất bình thường; value vẫn có thể null.
}
~~~

Nếu nghiệp vụ cấm kết quả null, hãy kiểm tra null ở nhánh bình thường và biến nó thành một trạng thái domain rõ ràng. Không sử dụng duy nhất **value != null** để kết luận rằng source thành công.

**Throwable error** không có nghĩa lúc nào cũng có cùng class với exception gốc trong callback sâu hơn của pipeline. Một lỗi có thể được bọc trong **CompletionException** bởi một stage phụ thuộc. Việc đọc nguyên nhân được trình bày ở phần sau.

## 4. So sánh thenApply, exceptionally, whenComplete và handle

| Phương thức | Khi gọi callback? | Callback nhận gì? | Có đổi kiểu T thành U? | Mục tiêu chính |
| --- | --- | --- | --- | --- |
| **thenApply(fn)** | Khi cha thành công | T | Có | Biến đổi giá trị thành công |
| **exceptionally(fn)** | Khi cha lỗi | Throwable | Không, vẫn T | Trả fallback cùng kiểu T |
| **whenComplete(action)** | Cả thành công và lỗi | T hoặc null, Throwable hoặc null | Không, cùng kiểu T | Quan sát outcome, ghi log/metric |
| **handle(fn)** | Cả thành công và lỗi | T hoặc null, Throwable hoặc null | Có | Biến đổi outcome thành U |

**thenApply** phù hợp khi chỉ cần biến một giá trị hợp lệ thành giá trị khác, không thay đổi nhánh lỗi. **exceptionally** phù hợp khi chỉ cần giá trị dự phòng cùng kiểu, và không cần biến đổi nhánh thành công.

**whenComplete** thích hợp cho quan sát và side effect, không được thiết kế để đổi kết quả/lỗi thành một giá trị khác. **handle** dùng khi bạn cần quyền chủ động lựa chọn kết quả mới trên **cả hai nhánh**.

Ví dụ với callback trả String:

~~~java
CompletableFuture<Integer> source =
        CompletableFuture.completedFuture(7);

CompletableFuture<String> translated =
        source.handle((value, error) ->
                error == null ? "SEVEN:" + value : "UNAVAILABLE");
~~~

**Không thể thay thế trực tiếp bằng exceptionally**, vì exceptionally của CompletableFuture<Integer> phải cung cấp giá trị Integer, không phải String.

**Lựa chọn dựa theo ngữ nghĩa:** thay vì cứ thấy exception là dùng handle, hãy chọn API nào biểu diễn rõ mục đích nhất.

## 5. handle chuyển kết quả thành công sang kiểu khác

Một ví dụ ứng dụng có giá trị số từ service nhưng giao diện cần chuỗi hiển thị:

~~~java
CompletableFuture<Integer> amount =
        CompletableFuture.completedFuture(500);

CompletableFuture<String> text =
        amount.handle((value, error) -> {
            if (error != null) {
                return "Không thể lấy số tiền";
            }
            return "Số tiền: " + value;
        });

System.out.println(text.join());
// Số tiền: 500
~~~

Từ **CompletableFuture<Integer>** chuyển thành **CompletableFuture<String>**. Thành công được ánh xạ thành chuỗi; thất bại được ánh xạ thành thông điệp dự phòng. Đây là hai phép biến đổi rõ ràng trong cùng một callback.

Một thiết kế mạnh hơn có thể trả về một kiểu **Outcome<T>** hoặc một DTO có trường status/value thay vì chuỗi hiển thị. Quan trọng là **không nhầm String "Không thể lấy số tiền" với một kết quả kinh doanh thành công thật**; consumer của stage sau cần biết đây là trạng thái dự phòng.

**handle thực hiện công việc sau khi stage cha hoàn tất**, không tạo lại request hay gọi lại tác vụ nguồn. Nếu bạn muốn retry, phải có một chính sách và thao tác riêng, không chỉ dùng handle rồi mặc nhiên hiểu là sẽ có retry.

## 6. handle phục hồi lỗi thành kết quả bình thường

Một source được hoàn tất ngoại lệ:

~~~java
CompletableFuture<Integer> source = new CompletableFuture<>();

CompletableFuture<Integer> safe =
        source.handle((value, error) ->
                error == null ? value : -1);

source.completeExceptionally(
        new IllegalStateException("service-down"));

System.out.println(safe.join()); // -1
~~~

Khi nguồn lỗi, callback của handle được gọi với **error != null**. Vì callback **trả -1 bình thường**, stage **safe** hoàn tất bình thường với -1.

**Nhưng source vẫn hoàn tất ngoại lệ.**

~~~java
System.out.println(source.isCompletedExceptionally());
// true
~~~

Điều này rất quan trọng khi ghép tác vụ: phục hồi ở một nhánh không thay đổi outcome của nhánh khác đã đăng ký vào source.

**Fallback phải có ý nghĩa:** nếu -1 có thể là dữ liệu hợp lệ, người dùng stage sau không thể phân biệt kết quả thật và dự phòng. Với nghiệp vụ nghiêm túc, nên dùng một kiểu chứa status, một giá trị default đã công bố hoặc tiếp tục truyền lỗi.

## 7. handle không tự thay đổi nhánh khác của pipeline

Giả sử một future bị lỗi và có hai stage phụ thuộc:

~~~java
CompletableFuture<Integer> source = new CompletableFuture<>();

CompletableFuture<Integer> recovered =
        source.handle((value, error) ->
                error == null ? value : -1);

CompletableFuture<Integer> skipped =
        source.thenApply(value -> value + 1);

source.completeExceptionally(
        new IllegalArgumentException("bad-input"));
~~~

Kết quả:

- **recovered** hoàn tất bình thường với **-1** vì handle phục hồi lỗi.
- **skipped** hoàn tất ngoại lệ: callback thenApply **không chạy** do source không hoàn tất bình thường.
- **source** vẫn hoàn tất ngoại lệ.

Nếu muốn bước thenApply được chạy sau khi đã phục hồi, phải nối từ **recovered**:

~~~java
CompletableFuture<Integer> continued =
        recovered.thenApply(value -> value + 10);

// continued.join() = 9
~~~

**Một stage được trả về chính là node tiếp theo trong đồ thị phụ thuộc.** Việc bạn giữ reference tới source và gọi các method khác trên source tạo các nhánh riêng. Không có "ghi đè exception toàn cục" bằng một câu lệnh handle.

## 8. Xử lý null đúng cách

**CompletableFuture.completedFuture(null)** là một completion bình thường. Vì thế:

~~~java
CompletableFuture<String> nullable =
        CompletableFuture.completedFuture(null);

CompletableFuture<String> checked =
        nullable.handle((value, error) -> {
            if (error != null) {
                return "ERROR";
            }
            if (value == null) {
                return "EMPTY_RESULT";
            }
            return value;
        });
~~~

Khi nguồn thành công với null, callback thấy **(value=null, error=null)**. Stage trả "EMPTY_RESULT", không phải "ERROR".

Nhiều lỗi thực tế đến từ biểu thức:

~~~java
// Sai nếu kết quả null được phép:
source.handle((value, error) ->
        value != null ? value : fallback);
~~~

Nếu source thành công với null, biểu thức trên vẫn chọn fallback; có thể làm mất sự khác biệt giữa **không tìm thấy dữ liệu** và **lỗi hệ thống**.

Nên quyết định từng trường hợp:

1. Source hoàn tất lỗi.
2. Source thành công với một giá trị hợp lệ.
3. Source thành công với null (nếu contract cho phép).

Nếu muốn phân biệt cả ba, một kiểu kết quả có trạng thái rõ có thể tốt hơn giá trị sentinel như -1, null hay chuỗi "UNKNOWN".

## 9. Callback handle tự ném exception

**handle không phải một vùng an toàn không thể lỗi.** Callback có thể ném exception do logic, dữ liệu không hợp lệ hoặc một thao tác phụ thất bại.

~~~java
CompletableFuture<Integer> stage =
        CompletableFuture.completedFuture(5)
                .handle((value, error) -> {
                    throw new IllegalArgumentException("handler-bug");
                });

System.out.println(stage.isCompletedExceptionally());
// true
~~~

Ở đây **stage nguồn thành công**, nhưng callback **handle** ném lỗi nên stage trả ra **hoàn tất ngoại lệ**.

Có thể gắn xử lý ở bước sau:

~~~java
CompletableFuture<Integer> safe =
        stage.exceptionally(error -> -9);

// safe.join() = -9
~~~

Không nên bắt mọi Throwable rồi mặc định chuyển thành một giá trị 0. Một số lỗi có thể là lỗi lập trình, vi phạm invariant, thiếu tài nguyên hoặc sự cố cần được quan sát và truyền tiếp. **Phục hồi lỗi phải có chính sách**; khi không thể phục hồi an toàn, hãy giữ nhánh lỗi.

Nếu callback phải làm I/O nặng, việc ném lỗi ở đây không phải lý do duy nhất cần cân nhắc Executor; tính chất blocking cũng quan trọng.

## 10. CompletionException, nguyên nhân gốc và tránh unwrap bừa bãi

Trong CompletableFuture, lỗi của callback trước có thể đi qua các stage phụ thuộc dưới dạng **CompletionException** chứa một cause. Khi dùng **join()** trên một future hoàn tất ngoại lệ, thường có thể gặp CompletionException (trừ một số dạng như cancellation theo hợp đồng).

Ví dụ:

~~~java
CompletableFuture<Integer> parsed =
        CompletableFuture.completedFuture("not-a-number")
                .thenApply(Integer::parseInt);
~~~

**NumberFormatException** phát sinh khi parse số; stage phụ thuộc hoàn tất ngoại lệ. Một handler gắn sau có thể nhận một Throwable bọc nguyên nhân.

Nếu thật sự cần phân loại lỗi gốc, có thể unwrap có kiểm soát:

~~~java
static Throwable root(Throwable error) {
    while ((error instanceof CompletionException
            || error instanceof ExecutionException)
            && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}
~~~

Đoạn này là **method của class** cần import java.util.concurrent.*. Nó chỉ đi qua một số wrapper thường gặp và dừng khi không còn cause; không phải quy tắc bắt buộc cho mọi ứng dụng.

**Không phải mọi Throwable đều cần unwrap.** Nếu contract của service đã định nghĩa exception type, hãy dùng hợp đồng đó. Trong logging hoặc thông báo cho client, không gửi nguyên stack trace hay message nội bộ nếu có thể chứa dữ liệu nhạy cảm.

**Không nuốt sự khác biệt giữa lỗi tạm thời và lỗi vĩnh viễn.** Một timeout có thể cho phép một fallback đọc cache; một lỗi xác thực/ủy quyền thường không nên âm thầm biến thành dữ liệu "thành công".

## 11. Cancellation cũng là một dạng exceptional completion

**CompletableFuture.cancel(...)** khiến future chưa hoàn tất chuyển sang trạng thái hủy với CancellationException. Với CompletableFuture, cancellation được xử lý như một dạng hoàn tất ngoại lệ.

~~~java
CompletableFuture<Integer> source = new CompletableFuture<>();

CompletableFuture<String> observed =
        source.handle((value, error) ->
                error == null ? "OK" : "CANCELLED_OR_FAILED");

source.cancel(false);

System.out.println(observed.join());
// CANCELLED_OR_FAILED
System.out.println(source.isCancelled());
// true
~~~

**handle vẫn có thể chạy** sau cancellation của source, vì callback được kích hoạt cho completion ngoại lệ. Nhưng nếu handler trả giá trị fallback bình thường, **stage mới có thể hoàn tất bình thường**, dù source đã bị hủy.

Vì thế không nên biến mọi hủy thành "thành công" nếu user/service thật sự cần phân biệt **đã hủy** với **lỗi tạm thời**.

**Lưu ý cơ chế hủy:** hủy một CompletableFuture không tự đảm bảo dừng tác vụ upstream đang chạy, không tự hoàn tác side effect và không chắc tạo interrupt ở worker. Ứng dụng cần một giao thức hủy tài nguyên riêng nếu yêu cầu thực thi có thể dừng.

Trong code production, muốn xử lý cancellation khác lỗi khác, hãy kiểm tra loại exception theo đúng contract sau khi cân nhắc wrapper, thay vì suy từ error != null rằng luôn cùng nguyên nhân.

## 12. handle, exceptionally và whenComplete khác nhau ở chuyện biến đổi outcome

Ba phương thức xử lý lỗi phổ biến:

**exceptionally** chỉ được gọi khi lỗi, trả fallback **cùng kiểu T**:

~~~java
CompletableFuture<Integer> safe =
        CompletableFuture.completedFuture("invalid")
                .thenApply(Integer::parseInt)
                .exceptionally(error -> -1);
~~~

**handle** chạy ở cả hai outcome, có thể trả **U khác T**:

~~~java
CompletableFuture<String> outcome =
        CompletableFuture.completedFuture("invalid")
                .thenApply(Integer::parseInt)
                .handle((value, error) ->
                        error == null ? "NUMBER:" + value : "INVALID_NUMBER");
~~~

**whenComplete** chạy ở cả hai outcome, nhưng được thiết kế để **quan sát**, không phải thay outcome:

~~~java
CompletableFuture<Integer> observed =
        CompletableFuture.completedFuture(4)
                .whenComplete((value, error) ->
                        System.out.println("observed: " + value));
~~~

Nếu nguồn hoàn tất ngoại lệ, whenComplete thường trả stage giữ outcome lỗi của nguồn (trừ các chi tiết kết hợp ngoại lệ theo hợp đồng nếu chính observer ném lỗi).

| Đặc điểm | exceptionally | whenComplete | handle |
| --- | --- | --- | --- |
| Chỉ đường lỗi | Có | Không | Không |
| Chạy cả success và error | Không | Có | Có |
| Trả giá trị khác kiểu T | Không | Không | Có |
| Dùng chủ yếu cho log/metric | Không | Có | Không |
| Thiết kế để phục hồi/đổi outcome | Có, nhánh lỗi | Không | Có, cả hai |
| Nếu callback ném lỗi | Stage trả ra lỗi | Phụ thuộc nguồn và quy tắc ưu tiên lỗi | Stage trả ra lỗi |

**whenComplete không giống finally của lệnh try** trong mọi trường hợp. Nó quan sát completion nhưng vẫn có thể tạo stage lỗi nếu observer ném exception; và không tự quản lý tài nguyên hoặc rollback side effect.

## 13. Vị trí của handle trong chuỗi thay đổi ngữ nghĩa

Cùng một phép toán có thể xử lý lỗi khác nhau tùy vị trí đặt handle.

**Handle trước một bước tiếp theo:**

~~~java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture("bad")
                .thenApply(Integer::parseInt)
                .handle((value, error) ->
                        error == null ? value : -1)
                .thenApply(value -> value + 10);

// result.join() = 9
~~~

Ở đây parse lỗi được đổi thành -1; thenApply sau đó **chạy bình thường** với fallback -1.

**Handle trước bước có thể ném lỗi:**

~~~java
CompletableFuture<Integer> result =
        CompletableFuture.completedFuture("bad")
                .handle((value, error) ->
                        error == null ? value : "0")
                .thenApply(Integer::parseInt);

// result.join() phát sinh lỗi do "bad" không phải số.
~~~

Ở ví dụ thứ hai, handle không sửa chuỗi "bad" vì source đầu tiên hoàn tất bình thường, nên lỗi parse phát sinh **sau handle** và không được handler trước đó bắt.

**Bài học:** handle chỉ quan sát outcome của **stage nó gắn trực tiếp**, không tự giám sát mọi stage được tạo trong tương lai. Muốn xử lý lỗi của một phép parse, hãy gắn handler **sau** phép parse hoặc điều chỉnh cấu trúc pipeline.

## 14. Chương trình Java 17 đầy đủ: success, error, null, cancellation

Tạo tệp **HandleOutcomesDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

public class HandleOutcomesDemo {
    static Throwable root(Throwable error) {
        while ((error instanceof CompletionException
                || error instanceof ExecutionException)
                && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    public static void main(String[] args) {
        CompletableFuture<Integer> success =
                CompletableFuture.completedFuture(21);
        CompletableFuture<String> mapped =
                success.handle((value, error) ->
                        error == null ? "OK:" + (value * 2) : "FALLBACK");
        System.out.println("success mapped: " + mapped.join());

        CompletableFuture<Integer> failure = new CompletableFuture<>();
        CompletableFuture<String> recovered =
                failure.handle((value, error) ->
                        error == null ? "OK:" + value : "FALLBACK:0");
        CompletableFuture<Integer> skipped =
                failure.thenApply(value -> value + 1);
        failure.completeExceptionally(
                new IllegalStateException("service-down"));
        System.out.println("failed recovered: " + recovered.join());
        System.out.println("source still failed: "
                + failure.isCompletedExceptionally());
        System.out.println("thenApply skipped: "
                + skipped.isCompletedExceptionally());

        CompletableFuture<String> nullValue =
                CompletableFuture.<String>completedFuture(null)
                        .handle((value, error) ->
                                error == null && value == null
                                        ? "SUCCESS_NULL" : "OTHER");
        System.out.println("normal null: " + nullValue.join());

        CompletableFuture<String> parsed =
                CompletableFuture.completedFuture("not-a-number")
                        .thenApply(Integer::parseInt)
                        .handle((value, error) ->
                                error == null ? "PARSED:" + value
                                        : "ERROR:" + root(error)
                                                .getClass().getSimpleName());
        System.out.println("parse failure: " + parsed.join());

        AtomicInteger calls = new AtomicInteger();
        CompletableFuture<Integer> handlerFailed =
                CompletableFuture.completedFuture(5)
                        .handle((value, error) -> {
                            calls.incrementAndGet();
                            throw new IllegalArgumentException("handler-bug");
                        });
        System.out.println("handler ran: " + calls.get());
        System.out.println("handler failed: "
                + handlerFailed.isCompletedExceptionally());
        System.out.println("handler recovery: "
                + handlerFailed.exceptionally(error -> -9).join());

        CompletableFuture<Integer> next =
                failure.handle((value, error) ->
                        error == null ? value : -1)
                        .thenApply(value -> value + 10);
        System.out.println("continued after recovery: " + next.join());

        CompletableFuture<Integer> cancelled = new CompletableFuture<>();
        CompletableFuture<String> afterCancel =
                cancelled.handle((value, error) ->
                        error == null ? "OK" : "CANCELLED");
        cancelled.cancel(false);
        System.out.println("cancellation handled: " + afterCancel.join());
        System.out.println("original cancelled: " + cancelled.isCancelled());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac HandleOutcomesDemo.java
java HandleOutcomesDemo
~~~

**Stdout đã biên dịch và chạy thành công:**

~~~text
success mapped: OK:42
failed recovered: FALLBACK:0
source still failed: true
thenApply skipped: true
normal null: SUCCESS_NULL
parse failure: ERROR:NumberFormatException
handler ran: 1
handler failed: true
handler recovery: -9
continued after recovery: 9
cancellation handled: CANCELLED
original cancelled: true
~~~

### Vì sao kết quả đáng tin?

- **completedFuture** tạo kết quả cố định, không có network.
- **completeExceptionally** được gọi chủ động sau khi đăng ký dependent, bảo đảm nhánh lỗi được kiểm tra.
- **thenApply trên source lỗi không chạy**, nên stage skipped được đánh dấu hoàn tất ngoại lệ.
- **handle trên source lỗi vẫn chạy**, và có thể trả fallback.
- **nullValue** minh họa **kết quả null không đồng nghĩa lỗi**.
- **parse failure** minh họa cách nhận nguyên nhân từ một callback có lỗi.
- **handlerFailed** chứng minh handler có thể tự ném exception; callback đã chạy 1 lần nhưng stage sau vẫn lỗi.
- **continued after recovery** chứng minh thenApply đặt sau handler nhận giá trị phục hồi.
- **cancelled** chứng minh handler có thể đổi kết cục cancellation thành stage mới thành công; source vẫn bị hủy.

**Không nên sao chép các giá trị fallback tùy ý -1/-9 vào production nếu domain không chấp nhận sentinel.** Chúng được chọn để cho thấy dòng dữ liệu trên console và dễ kiểm thử.

## 15. Khi nào cần handleAsync và Executor?

**handle** không có hậu tố Async và không bảo đảm callback chạy trên một worker thread riêng. Chính sách của CompletableFuture cho callback non-async cho phép thread hoàn tất stage trước hoặc một thread gọi completion thực thi callback; với stage đã hoàn tất, callback có thể thực thi gần thời điểm đăng ký.

Những biến thể:

~~~java
source.handle(fn);
source.handleAsync(fn);
source.handleAsync(fn, executor);
~~~

Đây là **mã chữ ký minh họa** với source, fn và executor được định nghĩa trong ứng dụng.

- **handle(fn):** callback theo cơ chế non-async; không hứa một thread cụ thể.
- **handleAsync(fn):** dùng cơ chế thực thi bất đồng bộ mặc định của CompletableFuture.
- **handleAsync(fn, executor):** sắp lịch callback bằng Executor bạn cung cấp.

Với CompletableFuture thông thường, các phương thức Async mặc định thường sử dụng **ForkJoinPool.commonPool()**, hoặc fallback được tài liệu JDK nêu khi common pool không có đủ parallelism. Ở implementation subclass, defaultExecutor có thể được thay đổi.

**Async không có nghĩa mỗi callback được cấp một thread mới**, và không bảo đảm thứ tự các callback ở nhánh độc lập. Executor có thể dùng thread pool, queue hoặc cơ chế scheduling khác. Nếu callback blocking I/O, không mặc nhiên cho nó chạy trên common pool dùng chung của JVM.

**Đối với side effect có chi phí cao:** chọn Executor được quản lý, giới hạn tải, quan sát backlog, thiết kế timeout và chống retry trùng; chỉ thêm hậu tố Async không tự tạo backpressure.

## 16. Chương trình Java 17: handleAsync, whenComplete và exceptionally

Tạo tệp **HandleAsyncDemo.java**:

~~~java
import java.util.concurrent.*;

public class HandleAsyncDemo {
    public static void main(String[] args) {
        ExecutorService executor =
                Executors.newSingleThreadExecutor(task ->
                        new Thread(task, "recovery-worker"));
        try {
            CompletableFuture<Integer> source = new CompletableFuture<>();
            CompletableFuture<String> recovered =
                    source.handleAsync((value, error) -> {
                        System.out.println("handle thread: "
                                + Thread.currentThread().getName());
                        return error == null ? "OK:" + value : "FALLBACK";
                    }, executor);
            source.completeExceptionally(
                    new IllegalStateException("offline"));
            System.out.println("async result: " + recovered.join());

            CompletableFuture<String> success =
                    CompletableFuture.completedFuture(8)
                            .handleAsync((value, error) ->
                                    error == null ? "DOUBLE:" + (value * 2)
                                            : "ERROR", executor);
            System.out.println("async success: " + success.join());

            CompletableFuture<Integer> triggered =
                    CompletableFuture.completedFuture("17")
                            .thenApply(Integer::parseInt);
            CompletableFuture<String> observed =
                    triggered.whenComplete((value, error) ->
                            System.out.println("observer value: " + value
                                    + " error: " + (error != null)))
                            .handle((value, error) ->
                                    error == null ? "RESULT:" + value
                                            : "ERROR");
            System.out.println("observed result: " + observed.join());

            CompletableFuture<Integer> broken = new CompletableFuture<>();
            CompletableFuture<Integer> stillBroken =
                    broken.whenComplete((value, error) ->
                            System.out.println("failure observed: "
                                    + (error != null)));
            CompletableFuture<Integer> fallback =
                    stillBroken.exceptionally(error -> 11);
            broken.completeExceptionally(new IllegalArgumentException("bad"));
            System.out.println("observer preserves failure: "
                    + stillBroken.isCompletedExceptionally());
            System.out.println("exceptionally fallback: " + fallback.join());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac HandleAsyncDemo.java
java HandleAsyncDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
handle thread: recovery-worker
async result: FALLBACK
async success: DOUBLE:16
observer value: 17 error: false
observed result: RESULT:17
failure observed: true
observer preserves failure: true
exceptionally fallback: 11
~~~

**Phân tích:**

- Executor một thread tự đặt tên **recovery-worker**, vì thế có thể kiểm chứng nơi callback handleAsync chạy trong mẫu này.
- Handler xử lý một stage lỗi và trả "FALLBACK", nhưng source vẫn là stage lỗi.
- Handler trên stage thành công trả **DOUBLE:16**, minh họa handle biến đổi cả nhánh thành công.
- whenComplete thấy kết quả thành công của parse 17 và quan sát nó, không tự thay giá trị.
- whenComplete của stage lỗi nhìn thấy error != null, nhưng **stillBroken vẫn hoàn tất ngoại lệ**.
- exceptionally trên stillBroken đổi lỗi thành số 11; nó không làm thay đổi trạng thái của stillBroken.

Chương trình gọi **executor.shutdown()** trong finally để quản lý vòng đời executor. **join** được đặt tại điểm kiểm thử cần đợi, không bên trong callback để chặn pool một cách vô thức.

## 17. Một handler trả CompletionStage khác: dùng thenCompose

**handle** là một phép **biến đổi giá trị**. Nếu callback trả **CompletableFuture<U>**, giá trị U của handle có thể trở thành **một future khác**, tạo future lồng nhau:

~~~java
CompletableFuture<CompletableFuture<String>> nested =
        source.handle((value, error) ->
                lookupAsync(error == null ? value : "backup"));
~~~

Đoạn này là **mã minh họa**, với source là CompletableFuture<String> và lookupAsync(String) trả CompletableFuture<String> do ứng dụng định nghĩa.

Để nhận một stage kết quả phẳng, dùng **thenCompose**:

~~~java
CompletableFuture<String> flattened =
        source.handle((value, error) ->
                lookupAsync(error == null ? value : "backup"))
                .thenCompose(Function.identity());
~~~

**Vì sao hữu ích?** Nếu một request lỗi và bạn muốn thử đọc từ cache bất đồng bộ, callback handle có thể quyết định dùng một **CompletionStage của tác vụ phụ**. Khi ấy cần flatten thay vì gọi join trong handle.

**Không gọi lookupAsync(...).join() ngay trong handler** chỉ để bỏ một lớp future, vì nó có thể chặn thread callback và làm pipeline kém an toàn khi dùng pool nhỏ.

Với Java hiện đại còn có **exceptionallyCompose** (từ Java 12) chuyên phục hồi nhánh lỗi bằng một CompletionStage, nhưng nó không tự biến đổi nhánh thành công sang U như handle. Bài vẫn minh họa cách kết hợp **handle + thenCompose** tương thích Java 8.

## 18. Chương trình Java 8 chạy được: handle và thenCompose

Tạo tệp **HandleComposeJava8Demo.java**:

~~~java
import java.util.concurrent.*;
import java.util.function.Function;

public class HandleComposeJava8Demo {
    static CompletableFuture<String> lookupAsync(String key) {
        return CompletableFuture.completedFuture("lookup:" + key);
    }

    public static void main(String[] args) {
        CompletableFuture<String> first =
                CompletableFuture.completedFuture("order-7");
        CompletableFuture<CompletableFuture<String>> nested =
                first.handle((value, error) ->
                        lookupAsync(error == null ? value : "backup"));
        CompletableFuture<String> flat =
                first.handle((value, error) ->
                        lookupAsync(error == null ? value : "backup"))
                        .thenCompose(Function.identity());
        System.out.println("nested: " + nested.join().join());
        System.out.println("flattened: " + flat.join());

        CompletableFuture<String> failed = new CompletableFuture<String>();
        CompletableFuture<String> recovered =
                failed.handle((value, error) ->
                        lookupAsync(error == null ? value : "backup"))
                        .thenCompose(Function.identity());
        failed.completeExceptionally(new IllegalArgumentException("bad"));
        System.out.println("async fallback: " + recovered.join());
        System.out.println("source failed: "
                + failed.isCompletedExceptionally());
    }
}
~~~

Biên dịch và chạy với JDK 8+:

~~~bash
javac HandleComposeJava8Demo.java
java HandleComposeJava8Demo
~~~

**Stdout đã kiểm thử bằng javac --release 8:**

~~~text
nested: lookup:order-7
flattened: lookup:order-7
async fallback: lookup:backup
source failed: true
~~~

Đây là cách kết hợp **handle để chọn nhánh** và **thenCompose để làm phẳng**. Method lookupAsync ở ví dụ này trả một future đã hoàn tất để giữ output deterministic; trong dự án thật, nó có thể là một API bất đồng bộ của cache hoặc service.

**Lưu ý version:** cú pháp Java và các API trong chương trình có từ Java 8; nếu muốn dùng exceptionallyCompose thì đó là API được thêm sau Java 8, cần ghi yêu cầu tối thiểu Java 12+.

## 19. Phân biệt fallback có chủ đích với việc nuốt lỗi

Một lời gọi bên ngoài thất bại có thể thuộc nhiều loại:

| Loại kết cục | Ví dụ | Chính sách có thể phù hợp |
| --- | --- | --- |
| Thành công | Tải được 20 dòng dữ liệu | Biến thành DTO, tính toán, tiếp tục |
| Không tìm thấy theo nghiệp vụ | Danh sách rỗng hợp lệ | Giữ kết quả bình thường, không đổi thành lỗi hạ tầng |
| Lỗi tạm thời | Cache offline | Có thể trả dữ liệu backup nếu đủ điều kiện |
| Lỗi input | ID sai quy tắc | Trả lỗi kiểm tra input, không ngầm dùng dữ liệu giả |
| Lỗi phân quyền | Không có quyền truy cập | Không chuyển thành "tải thành công" chỉ vì có default |
| Cancellation | User hủy tác vụ | Thường cần giữ trạng thái đã hủy |
| Lỗi lập trình | NullPointerException do bug | Quan sát, sửa bug; không mặc nhiên nuốt lỗi |

**handle cho phép bạn lựa chọn**, nhưng không quyết định hộ nghiệp vụ. Các giá trị fallback như -1, 0, "UNKNOWN" hoặc List.of() có thể làm downstream không phân biệt được thành công thật với dữ liệu dự phòng.

Một cách thiết kế rõ là trả kiểu kết quả mang **status**:

~~~java
record ViewResult(String status, String payload) {}

CompletableFuture<ViewResult> displayed =
        serviceResult.handle((value, error) ->
                error == null
                    ? new ViewResult("OK", String.valueOf(value))
                    : new ViewResult("DEGRADED", "Temporarily unavailable"));
~~~

Đây là **đoạn minh họa thuộc method Java 17+**: ViewResult là record ở cấp class; serviceResult là CompletableFuture do ứng dụng cung cấp. Nó không phải toàn bộ chương trình runnable. Với một hợp đồng production, status có thể là enum và được kiểm soát kiểu mạnh hơn chuỗi.

**Đừng lộ exception message nhạy cảm cho client**. Có thể ghi metric/log ở hệ thống nội bộ được bảo vệ, và trả một mã lỗi/fallback ổn định cho phía người dùng.

## 20. Khi nào nên truyền lại lỗi thay vì trả fallback?

Không phải lỗi nào cũng phục hồi hợp lệ. Nếu handler cần duy trì nhánh lỗi, có thể ném một exception phù hợp từ callback:

~~~java
CompletableFuture<String> processed =
        source.handle((value, error) -> {
            if (error != null) {
                throw new CompletionException(error);
            }
            return "OK:" + value;
        });
~~~

Đây là **mã minh họa** với source có giá trị phù hợp. Dùng CompletionException để biểu diễn lỗi trong pipeline có thể có ý nghĩa, nhưng **không nên bọc lặp CompletionException vô ích**. Một pattern thường dùng là:

~~~java
if (error instanceof CompletionException) {
    throw (CompletionException) error;
}
throw new CompletionException(error);
~~~

Đoạn cuối thuộc nhánh đã biết **error != null**. Khi chọn rethrow, cần kiểm tra liệu exception đã là wrapper hay chưa và liệu bạn có muốn giữ nguyên loại lỗi/cause cho tầng gọi.

**Khi handler tự ném exception**, stage trả ra của handle lỗi. Đây là cách giữ pipeline ở trạng thái lỗi, thay vì trả một dữ liệu default có thể gây hiểu nhầm.

**Không dùng catch(Throwable) tràn lan để biến cả lỗi nghiêm trọng thành thành công**. Chính sách xử lý cần phân biệt lỗi đáng phục hồi với lỗi cần cảnh báo/không tiếp tục.

## 21. Timeout, retry và idempotency không được handle tự giải quyết

**handle chỉ quan sát outcome của stage nguồn.** Nó không tự đặt deadline, dừng I/O, retry network request hay rollback side effect.

Ở Java 9+ có các API như **orTimeout** và **completeOnTimeout** trên CompletableFuture. Cần hiểu chúng tác động đến completion của future được gọi và dùng chính sách phù hợp:

- **orTimeout** hoàn tất future ngoại lệ với TimeoutException nếu chưa hoàn tất trước deadline.
- **completeOnTimeout** hoàn tất future bình thường với giá trị fallback khi quá thời gian, nếu chưa hoàn tất.
- **handle** có thể quyết định cách trình bày outcome timeout sau khi stage đã hoàn tất, nhưng không tự ngắt tác vụ nền.
- Nếu một tác vụ ngoài đang xử lý có side effect, timeout ở future không đảm bảo hệ thống ngoài dừng đúng lúc.

Ví dụ minh họa Java 9+:

~~~java
CompletableFuture<String> timed =
        serviceFuture.orTimeout(2, TimeUnit.SECONDS);

CompletableFuture<String> outcome =
        timed.handle((value, error) ->
                error == null ? value : "UNAVAILABLE");
~~~

Đây là **đoạn minh họa trong method**: serviceFuture là CompletableFuture<String> do ứng dụng cấp và có import java.util.concurrent.*. **orTimeout trả chính CompletableFuture được gọi**, không tự tạo một bản sao cô lập. Nếu các nhánh khác đang dựa vào cùng source, cần hiểu tác động khi orTimeout hoàn tất source.

**Retry** là thao tác khác: tạo một request mới khi được phép, chọn số lần, backoff, deadline tổng và idempotency. Không viết một thenApply/handle gọi join lên future từ cùng một executor nhỏ trong tình huống có thể dẫn tới deadlock.

## 22. Lỗi đồng thời, race và tính xác định

Một source CompletableFuture có thể được hoàn tất bởi thread khác. Một callback handle sẽ được kích hoạt theo chính sách completion, nhưng không nên dựa vào timing may rủi:

- Nếu source chưa hoàn tất, callback được đăng ký và chờ outcome.
- Nếu source đã hoàn tất, callback có thể được thực thi rất gần thao tác đăng ký.
- Với method non-async, thread thực thi callback không phải một thread được bảo đảm cố định.
- Với handleAsync, callback được đưa tới executor tương ứng; nếu executor từ chối công việc, quá trình scheduling có thể gây lỗi completion.
- Nếu nhiều thread cố complete/completeExceptionally/cancel cùng một future, theo hợp đồng CompletableFuture **chỉ một completion đầu tiên thành công**.

**Khuyến nghị kiểm thử:** dùng completedFuture, new CompletableFuture rồi gọi completeExceptionally/cancel một cách chủ động; không dùng Thread.sleep với những khoảng thời gian phỏng đoán để "chờ handler chạy". Khi cần chờ kết thúc, dùng chính stage trả về, join hoặc các công cụ đồng bộ thích hợp.

Các stage phụ thuộc độc lập không có thứ tự được bảo đảm chỉ vì đăng ký theo thứ tự dòng code. Muốn bước B chờ bước A, nối **A.handle(...).thenApply(...)** hoặc dùng các phương thức ghép phù hợp.

## 23. Test matrix cho handle và các biến thể

| Ca kiểm thử | Source | Kỳ vọng |
| --- | --- | --- |
| Thành công có giá trị | complete(21) | handle được gọi, trả chuỗi OK:42 |
| Lỗi | completeExceptionally(...) | handle được gọi, trả FALLBACK:0 |
| Source sau recovery | Source lỗi gốc | Vẫn isCompletedExceptionally = true |
| Nhánh thenApply khác | Cùng source lỗi | Callback thenApply bị bỏ qua |
| Thành công với null | completedFuture(null) | error null và value null |
| Callback của stage trước ném | Integer.parseInt sai | Handler nhận lỗi, có thể map thành giá trị |
| Callback handle tự ném | Handler throw IllegalArgumentException | Stage handle trả ra bị lỗi |
| Handler nối thenApply | Lỗi được phục hồi về -1 | thenApply sau đó nhận -1 và trả 9 |
| Source bị cancel | cancel(false) | Handler có thể đổi outcome; source vẫn cancelled |
| handleAsync với executor | Source lỗi | Callback chạy theo executor đã cấp |
| whenComplete quan sát lỗi | Source lỗi | Stage quan sát vẫn lỗi nếu action không tự thay outcome |
| exceptionally phía sau | Source lỗi | Trả fallback cùng kiểu |
| handle trả Future | Callback chọn lookupAsync | Cần thenCompose để flatten |
| Giá trị fallback sai domain | Lỗi phân quyền | Không được ngầm tạo "thành công" giả |
| Nhiều callback trên cùng source | Source hoàn tất | Không dựa vào thứ tự đăng ký |
| Rethrow | Handler không phục hồi | Stage trả ra tiếp tục hoàn tất ngoại lệ |

**Test cả giá trị và loại lỗi**. Không đủ chỉ assert rằng join không throw; một fallback bất hợp lý cũng làm join trả bình thường nhưng khiến hệ thống mất tín hiệu lỗi.

Với JUnit hoặc framework test, có thể kiểm tra **isCompletedExceptionally**, Throwable/cause của stage mới, số lần callback được gọi qua AtomicInteger, cũng như status domain trả về.

## 24. Những lỗi phổ biến khi dùng handle

1. **Coi handle chỉ chạy khi thất bại** — thực tế callback cũng được gọi khi source thành công.
2. **Coi value == null đồng nghĩa lỗi** — source có thể thành công với null.
3. **Coi handle sửa stage nguồn** — nó tạo stage mới, source giữ outcome cũ.
4. **Dùng handle trả fallback cho mọi lỗi** — có thể che lỗi phân quyền, bug, cancellation.
5. **Trả default làm dữ liệu thật bị hiểu sai** — nên dùng result/status rõ ràng.
6. **Đặt handle trước phép toán dễ lỗi rồi mong nó bắt lỗi về sau** — handler chỉ xử lý outcome của stage mà nó gắn.
7. **Dùng whenComplete để đổi result** — whenComplete được thiết kế để quan sát, không để translate outcome.
8. **Nhầm exceptionally cho phép đổi T sang U khác** — exceptionally vẫn giữ cùng kiểu T.
9. **Nhầm handle với thenApply** — thenApply chỉ chạy ở đường thành công.
10. **Gọi join trong callback để chờ một task khác** — có thể chặn pool hoặc deadlock.
11. **Dùng handleAsync nhưng không để ý executor mặc định** — common pool có thể đang phục vụ workload khác.
12. **Tin rằng handleAsync luôn tạo thread mới** — executor quyết định scheduling.
13. **Quên shutdown ExecutorService riêng** — có thể giữ tài nguyên hoặc JVM chạy dai.
14. **Không quan sát lỗi do chính handler ném** — stage cuối có thể hoàn tất ngoại lệ.
15. **Unwrap throwable tùy tiện tới tận cùng không xét contract** — có thể mất thông tin lỗi hoặc xử lý sai lớp exception.
16. **Dùng handle trả CompletionStage nhưng không flatten** — dẫn tới future lồng nhau hoặc join blocking.
17. **Coi cancel một future là hủy ngay mọi tác vụ nền** — CompletableFuture không tự quản lý toàn bộ cancellation của công việc.
18. **Coi timeout là rollback** — tác vụ ngoài có thể vẫn chạy và gây side effect.
19. **Dựa vào số lần in log để chứng minh nhánh chạy theo thứ tự** — test nên đồng bộ qua completion, không sleep.
20. **Lấy exception message raw để trả client** — có thể làm lộ thông tin vận hành hoặc dữ liệu nhạy cảm.

## 25. Bài tập và lời giải

### Bài 1 — Chọn handle hay thenApply?

**Đề:** Từ CompletableFuture<Integer>, nhân đôi số khi thành công, còn khi lỗi trả String "ERROR".

**Đáp án:** **handle** vì cần xử lý cả hai outcome và trả String:

~~~java
CompletableFuture<String> status =
        future.handle((value, error) ->
                error == null ? "OK:" + (value * 2) : "ERROR");
~~~

Trong đoạn minh họa, future là CompletableFuture<Integer>.

### Bài 2 — Result null

**Đề:** source thành công với null; callback handle nhận những gì?

**Đáp án:** **(value=null, error=null)**. Không dựa vào value null để kết luận source lỗi.

### Bài 3 — Lỗi được phục hồi có sửa source?

**Đề:** source lỗi, source.handle(...) trả -1, vậy source.isCompletedExceptionally() có còn true?

**Đáp án:** **Có**. Stage mới bình thường với -1, nhưng source không đổi.

### Bài 4 — thenApply sau recovery

**Đề:** source lỗi; handle trả -1; thenApply n -> n + 10 nối sau handle trả gì?

**Đáp án:** **9**, bởi handler đã biến lỗi thành completion bình thường ở stage trung gian.

### Bài 5 — thenApply khác handle

**Đề:** source lỗi và cả hai method đăng ký trực tiếp vào source. Callback nào chạy?

**Đáp án:** Callback **handle** có thể chạy để xử lý lỗi; callback **thenApply** không chạy vì stage nguồn không thành công.

### Bài 6 — whenComplete thay outcome?

**Đề:** source lỗi, observer whenComplete in log mà không throw. Stage được trả về thành công không?

**Đáp án:** **Không**. Khi không có hành vi đặc biệt khác, stage được trả về tiếp tục mang lỗi từ source.

### Bài 7 — Handler tự throw?

**Đáp án:** Stage do handle trả ra **hoàn tất ngoại lệ**, dù source ban đầu có thể đã thành công.

### Bài 8 — Fallback bất đồng bộ

**Đề:** handle callback phải gọi cacheAsync và nhận CompletionStage từ cache.

**Đáp án:** Có thể dùng **handle(...).thenCompose(Function.identity())**; nếu chỉ cần nhánh lỗi và Java 12+ cho phép, cân nhắc exceptionallyCompose.

### Bài 9 — Chọn Executor

**Đề:** Handler cần I/O chặn, có nên để handleAsync() mặc định trên common pool?

**Đáp án:** Không mặc định. Cần cân nhắc API bất đồng bộ hoặc Executor chuyên dụng, giới hạn tải và timeout; Async không tự làm I/O trở thành non-blocking.

### Bài 10 — Cancellation

**Đề:** source.cancel(false), handle trả "CANCELLED" bình thường. Stage nguồn có còn isCancelled() true?

**Đáp án:** **Có**, vì handler không thay đổi completion của source.

### Bài 11 — Phân biệt lỗi parse và lỗi service

**Đề:** Một callback Integer.parseInt ném NumberFormatException, một request khác trả lỗi mạng. Có nên trả cùng fallback 0?

**Đáp án:** Không tự động. Kiểm tra loại lỗi và contract. Parse sai input thường cần báo lỗi; lỗi mạng có thể có phương án dự phòng được phép.

### Bài 12 — Chờ ở đâu?

**Đề:** Có nên gọi join ngay bên trong handle để chờ một task khác trên cùng pool nhỏ?

**Đáp án:** Thường không. Dùng composition bất đồng bộ (thenCompose, các stage phụ thuộc) và chỉ chờ tại ranh giới thật sự cần, tránh blocking/deadlock.

## 26. Tổng kết và tài liệu chính thức

**Ghi nhớ 12 ý:**

1. **handle(BiFunction<T,Throwable,U>)** chạy khi stage cha hoàn tất bình thường **hoặc ngoại lệ**.
2. Nhánh thành công: **error == null**, nhưng value vẫn có thể null.
3. Nhánh lỗi: **error != null**, value thường null.
4. **Callback trả U bình thường** sẽ hoàn tất stage mới bình thường — có thể biến lỗi thành fallback.
5. **handle không sửa source**; những nhánh khác từ source vẫn nhận outcome gốc.
6. **Callback handle tự throw** khiến stage do handle trả về hoàn tất ngoại lệ.
7. **thenApply** chỉ đường thành công; **exceptionally** chỉ đường lỗi, cùng kiểu T.
8. **whenComplete** quan sát cả hai outcome nhưng không thiết kế để đổi result.
9. **Vị trí handle trong pipeline** quyết định nó bắt và xử lý lỗi của bước nào.
10. **handleAsync** dùng executor mặc định hoặc executor cấp rõ; không có bảo đảm tạo thread mới.
11. **handle + thenCompose** thích hợp khi cần chuyển outcome sang một tác vụ bất đồng bộ và flatten.
12. **Fallback phải có hợp đồng nghiệp vụ**: không nuốt lỗi nghiêm trọng, lỗi phân quyền, cancellation hoặc lỗi lập trình một cách máy móc.

**Tài liệu Oracle Java SE 25 (đang được hỗ trợ):**

- **CompletionStage** — ngữ nghĩa handle, handleAsync, whenComplete, exceptionally: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionStage.html
- **CompletableFuture** — implementation, completion, cancellation, executor và join/get: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **BiFunction** — callback hai tham số và một kết quả: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/BiFunction.html
- **CompletionException** — wrapper cho lỗi bất đồng bộ: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletionException.html
- **Executor** và **ExecutorService** — chính sách thực thi và vòng đời: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executor.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html
- **ForkJoinPool** — common pool dùng chung trong nhiều Async overload: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ForkJoinPool.html

**Phiên bản:** handle, handleAsync, exceptionally, whenComplete và thenCompose đã có từ Java 8, vẫn còn áp dụng trong Java hiện đại. Các demo chính dùng JDK 17+; demo handle + thenCompose đã được biên dịch ở mục tiêu Java 8. Các API được thêm sau Java 8 nếu được nhắc tới đều được đánh dấu phiên bản để tránh nhầm lẫn.
