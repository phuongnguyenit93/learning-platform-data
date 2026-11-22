# Ngoại lệ phát sinh đồng bộ so với lỗi trong callback: ranh giới bất đồng bộ trong AOP

## Mục tiêu học tập

Khi áp dụng **Aspect-Oriented Programming (AOP)** để ghi log, đo thời gian, giám sát lỗi hoặc quản lý ngữ cảnh, cần phân biệt hai thời điểm: **lời gọi phương thức kết thúc** và **công việc do lời gọi đó khởi phát kết thúc**. Hai thời điểm thường trùng nhau trong mã đồng bộ nhưng có thể khác nhau khi phương thức trả về một đối tượng đại diện cho kết quả tương lai, đăng ký callback hoặc phát sự kiện.

Sau bài này, bạn có thể:

- Phân biệt ngoại lệ thoát khỏi lời gọi đồng bộ với lỗi phát sinh trong callback, kể cả callback chạy ngay lập tức.
- Xác định chính xác một advice bao quanh lời gọi có thể quan sát lỗi nào và không thể quan sát lỗi nào.
- Thiết kế điểm quan sát bổ sung ở ranh giới callback hoặc kết quả bất đồng bộ, giữ nguyên ngữ nghĩa thành công, lỗi và hủy.
- Dùng Java 17+ kiểm chứng bằng chương trình có kết quả đầu ra xác định.

## 1. Ba khái niệm cần tách bạch

**Aspect** đóng gói một mối quan tâm cắt ngang (cross-cutting concern), ví dụ logging, tracing hoặc đo latency. **Join point** là điểm thực thi được quan sát/can thiệp; **advice** là logic chạy trước, sau hoặc bao quanh join point. Trong bài này, join point được xét chủ yếu là **lời gọi phương thức**. Cơ chế áp dụng advice có thể là weaving, interceptor hay proxy; các cơ chế đó không tự làm thay đổi quy tắc lan truyền ngoại lệ của Java.

**Ngoại lệ đồng bộ** là một ngoại lệ thoát ra theo call stack của lời gọi hiện tại. Chẳng hạn phương thức đích ném IllegalArgumentException trước khi trả về; advice bao quanh gọi phương thức đó có thể dùng try/catch để ghi nhận và ném lại.

**Callback** là hàm được truyền/đăng ký để gọi khi một hoạt động, sự kiện hoặc kết quả xảy ra. Tên gọi “callback” **không bảo đảm bất đồng bộ**: thư viện có thể gọi callback ngay trong cùng call stack, trên một luồng khác, trên event loop, hoặc khi một CompletableFuture đã hoàn thành. Để xác định ai bắt được lỗi, phải xem **callback thực sự được gọi lúc nào, do thành phần nào gọi và hợp đồng xử lý lỗi của thành phần đó**.

Ví dụ minh họa hai dòng thời gian:

~~~text
A. Ngoại lệ đồng bộ
caller -> around advice -> target() -> throw E
                    <- E qua cùng call stack <- caller catch E

B. Callback được kích hoạt sau khi lời gọi đăng ký đã trở về
caller -> around advice -> register(callback) -> return
                    <- advice kết thúc
... sự kiện/kết quả xảy ra ...
dispatcher / completion engine -> callback() -> throw E
                                 -> cơ chế xử lý lỗi riêng
~~~

**Ranh giới bất đồng bộ (asynchronous boundary)** là nơi quyền điều khiển rời khỏi lời gọi hiện tại và công việc tiếp tục thông qua lịch thực thi, callback, hàng đợi, future hoặc completion handler. “Khác call stack” mới là điểm then chốt; “khác thread” là khả năng thường gặp, nhưng không phải điều kiện bắt buộc.

## 2. Ngoại lệ đồng bộ: advice bao quanh nhìn thấy gì?

Giả sử target có dạng:

~~~java
static String parse(String text) {
    if (text == null) {
        throw new IllegalArgumentException("text must not be null");
    }
    return text.trim();
}
~~~

Một around advice về mặt ý tưởng hoạt động như sau:

~~~java
try {
    before();
    String value = parse(input);
    onNormalReturn(value);
    return value;
} catch (RuntimeException failure) {
    onSynchronousFailure(failure);
    throw failure;
} finally {
    onInvocationFinished();
}
~~~

Nếu parse ném lỗi trước khi trả về, lỗi đi trực tiếp qua phần try/catch của advice. Advice có thể quan sát kiểu lỗi, thông điệp, stack trace, nguyên nhân, thời điểm xảy ra và tiếp tục truyền chính ngoại lệ đó cho caller.

Phân biệt các mốc quan sát:

- **Before**: trước khi target được gọi; chưa biết kết quả.
- **After returning**: target đã **trả về bình thường**. Với phương thức trả về CompletionStage, điều này chỉ nói đối tượng stage đã được trả về, chưa khẳng định công việc đã thành công.
- **After throwing**: target **ném ngoại lệ thoát ra khỏi chính lời gọi được bao quanh**. Không mặc nhiên bao gồm lỗi xảy ra sau đó trong callback.
- **After/finally**: lời gọi được bao quanh đã rời khỏi call stack, bất kể cách kết thúc; không mặc nhiên là tác vụ bất đồng bộ đã xong.
- **Around**: có thể quyết định tiếp tục gọi target, quan sát kết quả trả về và, nếu hợp đồng cho phép, gắn thêm completion observer.

Cần xác định rõ phạm vi đo: “thời gian lời gọi phương thức” kết thúc ở return/throw; “thời gian nghiệp vụ hoàn thành” kết thúc ở kết quả cuối cùng của công việc bất đồng bộ.

## 3. Lỗi trong callback: vì sao try/catch bên ngoài không đủ?

Xét lời gọi register(onResult): nếu nó lưu callback rồi trả về, catch bao quanh register chỉ bắt được lỗi của quá trình **đăng ký**. Khi sự kiện phát sinh sau đó, callback được gọi từ một stack khác; một throw tại đây không thể tự động “quay ngược thời gian” để đi vào catch của register đã kết thúc.

Cách lỗi callback được xử lý phụ thuộc vào API:

| Cách thực thi callback | Kết quả khi callback ném ngoại lệ | Advice quanh lời gọi đăng ký có bắt được không? |
| --- | --- | --- |
| Gọi trực tiếp callback.run() ngay trong register và không chặn lỗi | Throw lan qua stack của register | Có |
| Gọi callback sau khi register trả về, trên executor/event loop | Lỗi đi vào nơi gọi callback, uncaught handler, cơ chế báo lỗi hoặc log tùy API | Không |
| Gọi callback trong thenApply/thenAccept của CompletableFuture | Lỗi thường làm **stage phụ thuộc** hoàn thành exceptional | Không, nếu lời gọi đăng ký đã trở về |
| CompletionStage được trả về đã/thêm lúc sau hoàn thành exceptional | Lỗi được lưu trong trạng thái hoàn thành của stage | Catch quanh thao tác trả về stage chỉ thấy lỗi nếu chính thao tác đó throw |
| Callback có tham số error hoặc error channel riêng | Lỗi được chuyển qua giao thức callback; có thể không hề có throw | Phải quan sát error channel đó |

**Ngoại lệ xảy ra trong callback** và **kết quả bất đồng bộ báo thất bại** có quan hệ nhưng không đồng nhất:

1. Công việc phía dưới có thể thất bại và báo qua error callback/failed stage mà không ném lỗi trên luồng của người đăng ký.
2. Công việc có thể thành công nhưng chính callback xử lý kết quả ném lỗi; stage do callback tạo ra có thể thất bại.
3. Thư viện có thể chặn và ghi log exception trong callback, hoặc để exception thoát tới bộ điều phối. Không thể giả định mọi exception đều được đưa vào future.
4. Callback có thể chạy đồng bộ ngay trong lời gọi API. Vì vậy, phải xét **thực tế lời gọi callback**, không chỉ tên “callback”.

Đặc biệt, try/catch đặt quanh một biểu thức trả về future không bắt lỗi hoàn tất future **sau khi** biểu thức đó đã trả về. Dùng cơ chế completion/error của API tương ứng mới quan sát được trạng thái muộn.

## 4. Quan sát hai tầng trong AOP

Một aspect theo dõi tác vụ bất đồng bộ thường cần **hai tầng quan sát có ngữ nghĩa khác nhau**.

**Tầng 1 — invocation boundary:** ghi nhận điểm bắt đầu, dữ liệu vào đã lọc, lỗi ném trước khi trả về, thời điểm phương thức trả về, và đối tượng bất đồng bộ được trả về nếu có. Đây là những gì một advice đồng bộ có thể biết chắc chắn.

**Tầng 2 — completion/callback boundary:** theo dõi callback thực sự chạy hoặc kết quả của future/promise/stream; ghi nhận thành công, thất bại hoặc hủy, thời điểm hoàn thành và ngữ cảnh tương quan. Tầng này cần một hook thực sự đại diện cho sự hoàn tất: callback error/result, completion stage, handler của nguồn phát sự kiện, hoặc bộ giám sát luồng thực thi.

~~~text
                       +--------------------+
request / caller ----> | around invocation  | ----> target()
                       +--------------------+            |
                         | sync throw                     +--> throw ngay -> sync failure
                         | normal return                  |
                         v                                +--> trả CompletionStage
                    invocation ended                                  |
                                                                       v
                                                      completion observer/callback
                                                        | success | error | cancelled
                                                        v
                                                   async outcome recorded
~~~

Nếu target trả về stage, một cách thực hiện chung là quan sát stage đó:

~~~java
CompletionStage<T> stage = invokeTarget(); // vẫn có thể throw ngay tại đây
return stage.whenComplete((value, error) -> {
    // Quan sát sự hoàn thành của stage.
    // Callback quan sát cần hạn chế lỗi phát sinh từ chính nó.
});
~~~

Lưu ý: whenComplete **trả về một stage mới**; lời gọi trên là một lựa chọn thiết kế tác động đến stage trả cho caller. Nếu callback quan sát tự throw, stage mới có thể thất bại dù stage gốc thành công. Nếu stage gốc đã thất bại, lỗi gốc thông thường vẫn được ưu tiên theo hợp đồng của CompletionStage. Vì thế, hãy giữ logic quan sát không ném lỗi, hoặc xử lý nội bộ lỗi của logger/metrics, và kiểm tra hợp đồng của API trước khi decorates kết quả.

Nếu chỉ gọi stage.whenComplete(...) nhưng bỏ qua stage trả về, mọi exception do observer tự ném có thể nằm trong một dependent stage không được ai kiểm tra. Nếu trả stage đã decorate, cần chủ động giữ ngữ nghĩa completion và hiểu sự khác biệt về định danh đối tượng stage. Trong hệ thống có yêu cầu **giữ nguyên chính đối tượng trả về**, có thể gắn observer không thay kết quả trả về, với chính sách giám sát lỗi observer rõ ràng.

## 5. Ví dụ Java 17+ chạy được: so sánh ba đường lỗi

Tạo tệp **AspectBoundaryExample.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public class AspectBoundaryExample {
    static <T> T aroundInvocation(String name, Supplier<T> target) {
        System.out.println("BEFORE " + name);
        try {
            T result = target.get();
            System.out.println("RETURN " + name);
            return result;
        } catch (RuntimeException error) {
            System.out.println("SYNC FAIL " + name + ": " + error.getMessage());
            throw error;
        }
    }

    static <T> CompletionStage<T> aroundCompletion(
            String name, Supplier<CompletionStage<T>> target) {
        CompletionStage<T> stage = aroundInvocation(name, target);
        return stage.whenComplete((value, error) -> {
            if (error == null) {
                System.out.println("ASYNC SUCCESS " + name);
            } else {
                System.out.println("ASYNC FAIL " + name + ": " + message(error));
            }
        });
    }

    static String message(Throwable error) {
        while (error instanceof CompletionException && error.getCause() != null) {
            error = error.getCause();
        }
        return error.getMessage();
    }

    public static void main(String[] args) {
        // (1) Lỗi thoát ngay qua lời gọi được bao quanh.
        try {
            aroundInvocation("parse", () -> {
                throw new IllegalArgumentException("invalid input");
            });
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER SYNC: " + error.getMessage());
        }

        // (2) Lời gọi trả về stage bình thường, nhưng stage thất bại sau đó.
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletionStage<String> observed = aroundCompletion("fetch", () -> pending);
        pending.completeExceptionally(new IllegalStateException("timeout"));
        try {
            observed.toCompletableFuture().join();
        } catch (CompletionException error) {
            System.out.println("CALLER ASYNC: " + message(error));
        }

        // (3) Dữ liệu đầu vào thành công, nhưng callback xử lý dữ liệu ném lỗi.
        CompletableFuture<String> event = new CompletableFuture<>();
        CompletableFuture<Void> callbackStage = event.thenAccept(value -> {
            throw new IllegalArgumentException("invalid callback");
        });
        event.complete("event");
        System.out.println("EVENT COMPLETE RETURNED");
        try {
            callbackStage.join();
        } catch (CompletionException error) {
            System.out.println("CALLBACK FAIL: " + message(error));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AspectBoundaryExample.java
java AspectBoundaryExample
~~~

Đầu ra xác định:

~~~text
BEFORE parse
SYNC FAIL parse: invalid input
CALLER SYNC: invalid input
BEFORE fetch
RETURN fetch
ASYNC FAIL fetch: timeout
CALLER ASYNC: timeout
EVENT COMPLETE RETURNED
CALLBACK FAIL: invalid callback
~~~

**Giải thích từng trường hợp:**

1. parse ném IllegalArgumentException trước khi aroundInvocation trả về, vì vậy advice nhìn thấy **SYNC FAIL** và caller cũng bắt được lỗi khi gọi phương thức.
2. fetch trả một CompletableFuture đang pending. Advice đồng bộ in **RETURN fetch**, tức chỉ lời gọi đã kết thúc. Sau đó completeExceptionally làm stage thất bại và completion observer in **ASYNC FAIL fetch**. Khi caller chủ động gọi join, CompletionException mới xuất hiện tại vị trí join.
3. thenAccept đăng ký callback và trả một **dependent stage**. Khi event.complete("event") được gọi, callback throw nhưng CompletableFuture ghi nhận lỗi vào dependent stage. complete trả về bình thường; callbackStage.join() mới ném CompletionException.

Ví dụ cố tình dùng complete/completeExceptionally từ cùng luồng main để thứ tự in luôn xác định. Điều đó chứng minh rằng **lỗi hoàn tất bất đồng bộ là một ranh giới kết quả và quyền điều khiển**, không nhất thiết đòi hỏi hai luồng. Trong hệ thống thực tế, observer có thể chạy trên luồng hoàn tất stage; phiên bản callback “async” có thể chạy với executor riêng. Không dựa vào thứ tự log giữa các luồng nếu chưa có quan hệ đồng bộ hóa.

**Giới hạn minh họa:** aroundInvocation và aroundCompletion là các hàm bao quanh lời gọi để giải thích ngữ nghĩa advice. Chúng không phải bộ weaving AOP đầy đủ. Hàm message chỉ gỡ CompletionException phục vụ in thông điệp; mã sản xuất nên giữ nguyên nguyên nhân, stack trace và thông tin lỗi khi cần.

## 6. Ba cách quản lý lỗi callback

### 6.1 Callback API thuần: chịu trách nhiệm ở nơi thực sự gọi callback

~~~java
static void dispatch(Runnable callback) {
    try {
        callback.run();
    } catch (RuntimeException failure) {
        // Ghi nhận tại callback execution boundary.
        System.err.println("Callback failed: " + failure);
        // Chính sách tiếp theo tùy giao thức: báo lỗi, retry, hoặc chuyển lỗi.
    }
}
~~~

Nếu dispatch chạy sau một lời gọi đăng ký, advice quanh **lời gọi đăng ký** không sở hữu catch này. Với callback do thư viện gọi, người dùng API cần đọc rõ giao thức về exception handler, completion/error callback và cách gắn ngữ cảnh theo sự kiện.

### 6.2 CompletionStage: quan sát chuỗi phụ thuộc

- **whenComplete**: quan sát cả value/error; thông thường giữ kết quả trước đó nếu observer không throw. Thích hợp telemetry nhưng tránh tác dụng phụ có thể thất bại.
- **handle**: nhận cả value/error và **biến đổi** chúng thành kết quả mới; thích hợp khi có chính sách phục hồi hoặc chuyển đổi lỗi rõ ràng.
- **exceptionally**: xử lý riêng nhánh thất bại, thường cung cấp giá trị thay thế; nếu dùng trong aspect chỉ để ghi log mà vô tình trả fallback, nó sẽ **thay đổi ngữ nghĩa lỗi**.
- **thenApply/thenAccept**: chạy xử lý khi stage trước thành công; lỗi ném trong hàm xử lý sẽ làm dependent stage thất bại.
- **join/get**: lấy kết quả theo cách có thể chặn luồng nếu chưa hoàn tất; join có thể ném CompletionException, get có thể ném ExecutionException (và InterruptedException). Đây là điểm quan sát của caller, **không nên chặn luồng chỉ để aspect lấy kết quả**.

Ví dụ về việc **quan sát** khác **phục hồi**:

~~~java
CompletionStage<String> observed = work.whenComplete((value, error) -> {
    recordOutcome(error); // observer cần không ném lỗi
});

CompletionStage<String> recovered = work.exceptionally(error -> {
    return "fallback"; // cố ý đổi kết quả thất bại thành thành công
});
~~~

Hai dòng này có mục đích khác nhau. Việc chuyển lỗi thành fallback phải là quyết định nghiệp vụ, không phải tác dụng phụ của một advice giám sát.

### 6.3 Sự kiện, stream, tác vụ nền và fire-and-forget

Một phương thức trả void sau khi enqueue công việc không có “future kết quả” để aspect suy luận. Cần chủ động gắn điểm quan sát nơi thực thi thật: callback lỗi, subscriber error, task supervisor, queue consumer hay executor hook thích hợp. Nếu callback có thể chạy nhiều lần, không thể xem **lần callback đầu** là tác vụ hoàn thành; phải định nghĩa hợp đồng complete/error/cancel cụ thể. Các callback có thể đồng thời chạy, vì thế số đếm và trạng thái theo dõi phải an toàn khi truy cập đồng thời.

## 7. Các góc cạnh nâng cao dễ bị hiểu sai

**Callback có thể chạy ngay trong thao tác đăng ký.** Một stage đã hoàn thành trước khi gọi whenComplete có thể kích hoạt callback ngay khi đăng ký. Vì thế, không suy luận “callback luôn chạy sau dòng lệnh kế tiếp”. Nếu callback ném lỗi, CompletionStage vẫn có thể chuyển lỗi đó vào dependent stage thay vì ném qua lời gọi đăng ký; hành vi tùy hợp đồng.

**Lỗi của callback không luôn đồng nghĩa lỗi của công việc gốc.** Nếu work đã thành công nhưng thenAccept throw, work vẫn có thể ở trạng thái success trong khi dependent stage thất bại. Aspect phải xác định rõ đang theo dõi **stage gốc, stage trung gian hay toàn bộ pipeline** để tránh ghi nhãn kết quả sai.

**Lỗi trong instrumentation cũng là lỗi.** Logic ghi log, tracing hoặc metrics có thể ném RuntimeException. Với advice đồng bộ, exception đó có thể thay thế lỗi/ngữ nghĩa của target; với observer bất đồng bộ, nó có thể làm dependent stage thất bại. Xử lý lỗi nội bộ phù hợp với chính sách giám sát, hạn chế side effect và không vô ý nuốt lỗi nghiệp vụ.

**Không làm mất loại lỗi ban đầu.** CompletionException và ExecutionException thường là wrapper. Khi cần phân loại/ghi nhận, xem cause; khi truyền cho caller, ưu tiên giữ contract của API và chuỗi nguyên nhân. Với các cơ chế proxy/reflective invocation, lỗi còn có thể bị wrapper bởi cơ chế gọi phản xạ; cần xác định tầng nào đang bắt và unwrapping có chủ đích.

**Cancellation có thể là một trạng thái riêng.** Future hủy có thể biểu diễn bằng CancellationException hoặc kết quả “cancelled”; đừng tự động đếm mọi cancellation là lỗi nghiệp vụ. Nếu hệ thống hỗ trợ hủy, ghi nhận riêng cả lý do, thời điểm và ngữ nghĩa hủy.

**Không đồng nhất context giữa các luồng.** Những thông tin lưu trong ThreadLocal của advice gọi ban đầu không được bảo đảm hiện diện ở executor/callback khác. Hãy chuyển correlation ID/trace context bằng cơ chế propagation phù hợp, thiết lập và dọn dẹp context quanh phần thực thi callback, tránh rò dữ liệu sang tác vụ tiếp theo.

**Độ trễ của lời gọi và độ trễ hoàn tất khác nhau.** Lấy timestamp trước invocation, sau khi trả stage, và khi stage hoàn tất. Ghi hai chỉ số riêng: invocation latency và end-to-end completion latency. Nếu chỉ đo đến return, tác vụ chậm hoặc thất bại sau đó có thể vẫn bị báo “thành công nhanh”.

**Có thể xảy ra race.** Một tác vụ có thể hoàn tất trước khi caller kịp nhận stage. Khi attach observer trên stage đã hoàn tất, observer có thể chạy ngay; trong code đa luồng, thứ tự BEFORE/RETURN/completion logs phải được phân tích theo quan hệ thực thi thật và bảo đảm đồng bộ của API, không dựa vào suy đoán về lịch CPU.

## 8. Cách thiết kế aspect xử lý lỗi đúng ranh giới

1. **Định nghĩa join point và kết quả mong đợi.** Advice đang theo dõi phương thức, callback invocation, một stage hay toàn bộ lifecycle? Khai báo rõ event nào được xem là success, failure, cancellation.
2. **Quan sát lỗi ném ngay.** Dùng catch ở tầng gọi target để ghi nhận ngoại lệ trước khi return, đồng thời bảo toàn hành vi ném lại.
3. **Xem kiểu và hợp đồng kết quả trả về.** Nếu trả CompletionStage, có thể gắn completion observer; nếu đăng ký callback hoặc fire-and-forget, cần hook xử lý tại nơi callback/task được gọi. Không dùng phương thức tên “async” làm bằng chứng duy nhất.
4. **Không đánh tráo trạng thái.** Return thành công của một stage chưa hoàn tất khác với tác vụ thành công; stage gốc thành công nhưng callback thất bại khác với công việc gốc thất bại.
5. **Bảo vệ logic quan sát.** Không để lỗi telemetry thay đổi kết quả nghiệp vụ; không blocking join/get trong advice chỉ để lấy outcome; giữ cancellation và cause chain khi cần.
6. **Truyền ngữ cảnh xuyên ranh giới.** Gắn correlation ID ở entry và khôi phục nó tại callback/completion để kết nối hai tầng log.
7. **Thử các trường hợp độc lập.** Target throw đồng bộ; target trả pending stage rồi fail; callback throw khi xử lý kết quả; callback được gọi ngay; observer tự fail; cancel; hai completion xảy ra gần nhau.

Bảng quyết định nhanh:

| Điều cần quan sát | Điểm gắn advice/hook phù hợp | Sai lầm cần tránh |
| --- | --- | --- |
| Lời gọi ném lỗi trước khi return | Around/after-throwing của lời gọi | Coi mọi exception sau đó là lỗi đồng bộ |
| Lời gọi trả future bình thường | After-returning của lời gọi | Ghi “nghiệp vụ thành công” ngay lúc return |
| Future thất bại/hoàn tất/hủy | Completion observer của future | Blocking toàn bộ pipeline để chờ kết quả |
| Callback ném lỗi khi được gọi | Callback execution boundary hoặc dependent stage | Chỉ catch quanh thao tác register |
| Lỗi callback do framework/runtime xử lý | Error channel/handler theo hợp đồng API | Giả định exception luôn đi tới caller ban đầu |

## 9. Tự kiểm tra

**Câu 1.** Một advice in “RETURN” khi nhận CompletableFuture, 200 ms sau future hoàn thành exceptional. Advice có sai không?

**Đáp án:** “RETURN” đúng nếu nó mô tả **lời gọi đã trả về**; sai nếu nó được diễn giải là **nghiệp vụ đã hoàn tất thành công**. Cần thêm hook completion để ghi lỗi muộn.

**Câu 2.** Đăng ký callback trong try/catch, vì sao lỗi trong callback vẫn có thể không vào catch?

**Đáp án:** Try/catch chỉ có hiệu lực với exception lan qua stack đang thực thi. Nếu callback được gọi sau khi thao tác đăng ký trả về, stack ban đầu đã kết thúc; lỗi thuộc stack và cơ chế xử lý mới. Nếu callback chạy trực tiếp ngay trong stack đăng ký và lỗi không bị chặn, catch vẫn có thể bắt được.

**Câu 3.** CompletableFuture gốc hoàn thành thành công, nhưng thenAccept ném lỗi. Lỗi thuộc đâu?

**Đáp án:** Lỗi thuộc **dependent stage** được tạo bởi thenAccept. Nó không nhất thiết biến stage gốc thành failed. Cần theo dõi đúng stage mà caller dùng làm kết quả cuối cùng.

**Câu 4.** Vì sao không dùng exceptionally với giá trị fallback chỉ để aspect ghi lỗi?

**Đáp án:** Vì exceptionally có thể biến thất bại thành thành công, vô tình đổi hợp đồng. Dùng observer phù hợp, xử lý lỗi của observer riêng và để nguyên kết quả nghiệp vụ.

## Kết luận kiến thức

Một **ngoại lệ đồng bộ** có thể thoát qua cùng call stack mà advice đang bao quanh. **Lỗi trong callback** đi theo thời điểm và cơ chế thực thi của callback; nó có thể lan đồng bộ nếu callback được gọi ngay, được lưu trong một dependent future, hoặc được xử lý bởi một error channel khác. Khi thiết kế AOP, luôn tách **kết thúc lời gọi** khỏi **hoàn tất hoạt động**, rồi đặt điểm giám sát tại đúng ranh giới sở hữu kết quả và lỗi.