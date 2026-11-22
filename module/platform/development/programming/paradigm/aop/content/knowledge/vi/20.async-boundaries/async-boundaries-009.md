# Khi nào nên dùng cơ chế chuyên biệt của mô hình bất đồng bộ trong AOP?

## 1. Vấn đề cốt lõi: lời gọi đã kết thúc, công việc có thể vẫn đang chạy

Aspect-Oriented Programming (AOP) tách những mối quan tâm cắt ngang như ghi log, đo thời gian, tracing, metrics, bảo mật và quan sát lỗi khỏi logic nghiệp vụ chính. Advice có thể thực thi trước, sau hoặc bao quanh một join point, thường là lời gọi phương thức. Trong mã đồng bộ, thời điểm phương thức trả về hoặc ném ngoại lệ thường cũng là thời điểm phần công việc được gọi đã kết thúc.

Trong mã bất đồng bộ, **lời gọi phương thức** và **vòng đời công việc** là hai sự kiện khác nhau:

- Phương thức có thể trả về ngay một future, promise, handle, subscription hoặc kết quả đăng ký callback.
- Công việc có thể được xếp hàng, bắt đầu sau đó và chỉ thành công/thất bại khi phương thức gốc đã trả về từ lâu.
- Callback có thể được gọi nhiều lần, được gọi ngay trong bước đăng ký hoặc chạy ở luồng khác.
- Kết quả có thể thất bại, bị hủy hoặc kết thúc từng phần theo một giao thức riêng; exception không nhất thiết thoát qua call stack của lời gọi ban đầu.

Ví dụ một phương thức trả về CompletionStage<String> có thể trả đối tượng stage thành công mà stage đó vẫn đang pending. Một advice kiểu after-returning quan sát được **hành vi trả về của lời gọi**, nhưng chưa thể kết luận nghiệp vụ đã thành công. Một advice kiểu after-throwing quanh lời gọi chỉ bắt exception thoát ra ở thời điểm gọi; lỗi phát sinh khi stage hoàn tất sau đó sẽ cần một cơ chế khác.

~~~text
t0: caller --> advice --> method submit() ----> trả handle/future --> advice kết thúc
                              |
                              +--> công việc được xếp lịch / đăng ký
t1:                         runtime thực thi công việc
t2:                         callback, success, error hoặc cancel
                              |
                              +--> điểm quan sát theo mô hình bất đồng bộ
~~~

**Nguyên tắc:** dùng advice tổng quát để quan sát **invocation boundary**; dùng hook, handler hoặc decorator của mô hình bất đồng bộ khi cần quan sát **completion boundary**, **callback execution**, **subscription lifecycle** hay **task lifecycle**.

## 2. Thế nào là một cơ chế chuyên biệt?

“Cơ chế chuyên biệt” ở đây không đồng nghĩa với việc chọn một thư viện AOP khác. Đó là điểm mở rộng do chính mô hình bất đồng bộ cung cấp để phản ánh đúng trạng thái thực:

| Mô hình | Cơ chế phù hợp | Thông tin có thể quan sát |
| --- | --- | --- |
| Future/CompletionStage | Completion callback như whenComplete, handle, listener khi hoàn tất | Thành công, lỗi hoàn tất, hủy, thời điểm complete |
| Callback một lần | Bao callback nhận kết quả/lỗi, hook của dispatcher | Callback nào được gọi, thời điểm gọi, lỗi dữ liệu hoặc lỗi trong handler |
| Listener nhiều lần | Hook vòng đời đăng ký, từng sự kiện và hủy đăng ký | Sự kiện, lỗi, số lượng callback, tài nguyên còn đăng ký |
| Reactive stream / Publisher | Hook subscribe, onNext, onError, onComplete, cancel theo giao thức stream | Vòng đời từng subscription, tín hiệu lỗi, hoàn tất, hủy, backpressure |
| Executor / queue / background task | Decorator Runnable/Callable/task, completion handle hoặc task supervisor | Thời điểm thực thi, kết quả công việc, lỗi task và hủy |
| Fire-and-forget | Worker-side error handler, event/queue consumer, correlation và trạng thái riêng | Kết quả sau khi lời gọi enqueue đã thành công |
| Coroutine / continuation | Hook completion, cancellation, structured scope và context của mô hình đó | Hoàn tất tác vụ logic qua nhiều lần tạm dừng và tiếp tục |

Bảng chỉ mô tả loại cơ chế; tên API và bảo đảm thực tế tùy môi trường. Trong Java 17, CompletionStage, CompletableFuture và ExecutorService cung cấp các ví dụ cụ thể dễ kiểm chứng mà không cần thêm thư viện.

## 3. Tiêu chí quyết định: dùng cơ chế chuyên biệt khi nào?

### 3.1. Kết quả cuối cùng xuất hiện sau khi lời gọi đã trả về

Hãy dùng hook completion nếu yêu cầu là:

- Đo thời gian **đến khi tác vụ kết thúc**, không chỉ thời gian tạo future.
- Ghi “thành công” sau khi kết quả đã sẵn sàng.
- Ghi nguyên nhân thất bại nếu kết quả chuyển sang trạng thái exceptional.
- Phân loại trạng thái canceled riêng theo hợp đồng.
- Tính metrics như số tác vụ hoàn thành, tỉ lệ lỗi hay latency thực.

Nếu chỉ cần đo chi phí chuẩn bị request, validate input, enqueue task hoặc tạo handle, một advice đồng bộ là đủ và thường đơn giản hơn. Không nên gắn completion observer vào mọi phương thức chỉ vì chữ “async” xuất hiện trong tên.

### 3.2. Lỗi không đi qua call stack ban đầu

Nếu target có thể trả về bình thường nhưng lỗi nghiệp vụ được chuyển qua future, error callback, stream signal hoặc task supervisor, quanh target bằng try/catch chỉ quan sát được lỗi đồng bộ lúc gọi. Khi mục đích là lỗi cuối cùng của công việc, phải theo dõi **error channel thực sự**.

Ngược lại, một callback được gọi ngay trong thao tác đăng ký, không bị dispatcher bắt lỗi, có thể ném exception qua chính lời gọi đăng ký. Không được đồng nhất “callback” với “chạy ở luồng khác”. Chọn điểm quan sát theo **cơ chế gọi callback và hợp đồng truyền lỗi**, không theo tên hàm.

### 3.3. Có nhiều mốc vòng đời hoặc nhiều lần phát dữ liệu

Một stream thường có onSubscribe, zero hoặc nhiều onNext, và một tín hiệu kết thúc onError/onComplete; cancellation có thể do subscriber khởi xướng. Với mô hình như vậy:

- After-returning từ hàm tạo Publisher không tương ứng với subscription hay dữ liệu đã được xử lý.
- Một Publisher có thể được subscribe nhiều lần; mỗi lần đăng ký tạo vòng đời quan sát riêng.
- “Nhận phần tử đầu tiên” không phải là “stream hoàn tất”.
- Lỗi stream phải được quan sát tại error signal; lỗi do observer tự gây ra là một vấn đề khác.
- Cancellation không đồng nghĩa onComplete; phải đọc đúng hợp đồng stream.

Đây là tình huống điển hình cần cơ chế theo stream thay vì một advice chỉ bao quanh hàm trả về Publisher.

### 3.4. Cần truyền ngữ cảnh xuyên ranh giới lịch thực thi

Một aspect có thể đặt correlation ID, trace ID hay ngữ cảnh người gọi vào ThreadLocal ở luồng ban đầu. Khi tác vụ chạy trên executor khác, ThreadLocal này không tự động xuất hiện ở luồng thực thi. Nếu muốn tracing xuyên các callback, cần cơ chế **capture, propagation, restore và cleanup** ở ranh giới thích hợp.

Hook gắn task, callback, completion hoặc subscription cho phép thiết lập lại context khi callback thật sự chạy. Không giữ context vĩnh viễn trên luồng dùng chung, vì thread pool có thể tái sử dụng luồng cho request khác.

### 3.5. Cần xử lý hủy, timeout, retry hoặc tài nguyên theo vòng đời

Một thao tác có thể tạo future rồi bị hủy; kết quả cũng có thể đến muộn sau khi caller đã bỏ cuộc. Nếu advice giải phóng tài nguyên khi phương thức trả về, trong khi callback còn sử dụng tài nguyên, sẽ có lỗi lifecycle. Dùng callback hoàn tất hoặc cơ chế quản lý phạm vi tác vụ khi cleanup thực sự phụ thuộc việc hoàn tất/hủy.

Retry và timeout cũng phải được thiết kế dựa trên **kết quả thực**: retry một lỗi xảy ra sau return không thể đạt được chỉ bằng cách thử gọi lại quanh lời gọi đầu tiên nếu code không chờ hoặc quan sát kết quả. Tuy nhiên không tự động retry chỉ vì một completion callback thấy lỗi; có thể nhân đôi side effect và vi phạm tính idempotent của nghiệp vụ.

## 4. Khi nào advice AOP tổng quát đã đủ?

Cơ chế chuyên biệt không phải lựa chọn mặc định cho mọi join point. Dùng advice đồng bộ nếu mục tiêu là quan sát hoặc can thiệp tại chính lời gọi:

1. Kiểm tra đầu vào hoặc điều kiện truy cập **trước khi** bắt đầu đăng ký công việc.
2. Ghi thời điểm enqueue, loại công việc và request ID ban đầu.
3. Đo latency của việc khởi tạo/schedule.
4. Bắt lỗi phát sinh ngay khi xây dựng future, tạo handler hoặc gửi tác vụ vào queue.
5. Kiểm soát số lượng thao tác đang được đăng ký theo chính sách thực thi phù hợp.
6. Chuẩn hóa metadata đầu vào của lời gọi mà không cần biết công việc kết thúc ra sao.

Nếu nghiệp vụ trả giá trị bình thường và không tạo vòng đời bất đồng bộ riêng, càng không cần một hook theo future hay callback.

Điểm quyết định là **câu hỏi cần trả lời**:

- “Method này có gọi được không?” → advice quanh lời gọi.
- “Việc đăng ký công việc có thành công không?” → advice quanh thao tác đăng ký.
- “Công việc có hoàn tất thành công không?” → completion/error hook.
- “Callback có ném lỗi khi xử lý dữ liệu không?” → bao quanh chính callback hoặc theo dõi dependent stage.
- “Một subscription đã nhận gì và chấm dứt bằng cách nào?” → lifecycle hooks của stream.
- “Tác vụ có thực sự chạy trên executor không?” → execution-side wrapper/hook.

## 5. CompletionStage: một ví dụ điển hình

Giả sử một phương thức trả về CompletionStage<T>. Khi trả về bình thường, advice chỉ biết phương thức đã tạo và trả stage. Để đo kết quả hoàn tất, cần gắn observer:

~~~java
// Đoạn minh họa trong một phương thức generic; không phải chương trình độc lập.
CompletionStage<T> stage = invokeTarget(); // Có thể ném lỗi đồng bộ.
return stage.whenComplete((value, failure) -> {
    if (failure == null) {
        recordCompletedSuccessfully();
    } else {
        recordCompletedExceptionally(failure);
    }
});
~~~

**whenComplete** trả về **một CompletionStage mới**, không phải luôn chính đối tượng ban đầu. Callback quan sát có thể chạy ngay trong thread gọi khi stage đã hoàn tất, hoặc trên thread làm stage hoàn tất. Không giả định luôn dùng một worker thread riêng. Để giữ đúng ngữ nghĩa thành công/thất bại:

- Logic quan sát nên tránh ném exception, vì exception trong observer có thể làm dependent stage thất bại khi stage gốc thành công.
- Không dùng exceptionally để tạo fallback nếu yêu cầu chỉ là metrics: nó có thể biến lỗi thành giá trị thành công.
- Không gọi join/get ngay trong advice để “đợi cho chắc”, vì sẽ làm mất ưu điểm không chặn của pipeline và có thể gây deadlock trong môi trường thiếu worker.
- Không khẳng định stage mới và stage gốc có cùng identity, cancellation propagation, callback timing hoặc cách xử lý completion của tất cả implementation.
- Nếu giao thức bắt buộc giữ nguyên đối tượng trả về, có thể đăng ký observer phụ rồi trả stage gốc, nhưng cần thiết kế rõ cách ghi nhận lỗi của **dependent stage** do observer tạo ra.

Các hàm có tên giống nhau không thay thế được nhau:

| API | Ngữ nghĩa tiêu biểu | Mục đích AOP cần cân nhắc |
| --- | --- | --- |
| whenComplete | Quan sát result/error, tạo dependent stage | Telemetry completion; observer nên không thất bại |
| handle | Biến đổi cả nhánh success/error thành một kết quả mới | Dùng khi chủ ý chuyển đổi kết quả |
| exceptionally | Phục hồi hoặc biến đổi nhánh error | Không dùng để vô tình nuốt lỗi |
| thenApply / thenAccept | Xử lý khi stage trước thành công | Lỗi trong callback làm dependent stage thất bại |
| join / get | Tiêu thụ kết quả, có thể block; báo lỗi khi tiêu thụ | Thích hợp ở ranh giới chờ kết quả có chủ đích, không làm default observer |

Trong CompletableFuture, completion exceptional và callback failure có thể xuất hiện thông qua CompletionException hoặc ExecutionException khi caller đọc kết quả. Cần xem cause để ghi nhận lỗi gốc nhưng vẫn bảo toàn hợp đồng của API.

### 5.1. Bài thực hành Java 17+: invocation so với completion

Tạo file **AsyncAdviceSelectionDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Supplier;

public class AsyncAdviceSelectionDemo {
    static <T> CompletionStage<T> observe(
            String operation,
            Supplier<? extends CompletionStage<T>> action) {
        System.out.println("CALL " + operation);

        CompletionStage<T> stage;
        try {
            stage = action.get();
        } catch (RuntimeException failure) {
            System.out.println("INVOCATION ERROR " + operation
                    + ": " + failure.getMessage());
            throw failure;
        }

        System.out.println("RETURN " + operation);

        return stage.whenComplete((value, failure) -> {
            if (failure == null) {
                System.out.println("COMPLETE SUCCESS " + operation);
            } else {
                System.out.println("COMPLETE ERROR " + operation
                        + ": " + rootMessage(failure));
            }
        });
    }

    static String rootMessage(Throwable failure) {
        while (failure instanceof CompletionException
                && failure.getCause() != null) {
            failure = failure.getCause();
        }
        return failure.getMessage();
    }

    public static void main(String[] args) {
        CompletableFuture<String> pending = new CompletableFuture<>();
        CompletionStage<String> monitored = observe("fetch", () -> pending);

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            executor.execute(() -> pending.completeExceptionally(
                    new IllegalStateException("upstream unavailable")));

            try {
                monitored.toCompletableFuture().join();
            } catch (CompletionException failure) {
                System.out.println("CALLER ERROR: " + rootMessage(failure));
            }
        } finally {
            executor.shutdown();
        }

        CompletableFuture<String> source =
                CompletableFuture.completedFuture("input");
        CompletableFuture<Integer> dependent = source.thenApply(value -> {
            throw new IllegalArgumentException("invalid mapping");
        });

        System.out.println("SOURCE VALUE: " + source.join());

        try {
            dependent.join();
        } catch (CompletionException failure) {
            System.out.println("CALLBACK ERROR: " + rootMessage(failure));
        }
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac AsyncAdviceSelectionDemo.java
java AsyncAdviceSelectionDemo
~~~

Đầu ra:

~~~text
CALL fetch
RETURN fetch
COMPLETE ERROR fetch: upstream unavailable
CALLER ERROR: upstream unavailable
SOURCE VALUE: input
CALLBACK ERROR: invalid mapping
~~~

**Vì sao thứ tự này xác định?** Hàm observe ghi CALL và RETURN trước khi submit thao tác hoàn tất future vào executor. Lời gọi join trên dependent stage chỉ trả lỗi sau khi completion callback của observer xử lý xong. Sau khi khối đầu tiên kết thúc, main mới chuyển sang ví dụ stage thứ hai. Ví dụ dùng một thread executor riêng để minh họa ranh giới thực thi, nhưng chính trạng thái stage và cơ chế callback mới quyết định ranh giới hoàn tất.

**Ý nghĩa:**

- RETURN fetch là việc **lời gọi tạo/nhận future** đã trả về, không phải fetch thành công.
- COMPLETE ERROR fetch ghi nhận lỗi tại completion boundary.
- CALLER ERROR xuất hiện khi caller tiêu thụ stage bằng join, nơi CompletionException được ném.
- source đã thành công, nhưng callback thenApply ném IllegalArgumentException. Lỗi thuộc **dependent**, không làm source đổi sang trạng thái failed.
- Callback thenApply có thể chạy ngay khi đăng ký, vì source đã hoàn thành. Callback không nhất thiết chạy bất đồng bộ chỉ vì dùng CompletionStage.

Mẫu observe chỉ minh họa một điểm mở rộng tương đương advice. Nó không tự weaving join point. Trong ứng dụng thực, gắn hook thông qua cơ chế interception/weaving hoặc wrapper thích hợp của hệ thống đang dùng.

## 6. Callback API: theo dõi đúng cả kết quả và handler

Với API nhận callback như onSuccess(value) và onFailure(error), lời gọi đăng ký có thể kết thúc trước khi callback được gọi. Một aspect quanh việc đăng ký nên ghi “registered”, còn wrapper tại callback mới biết tác vụ thành công hay thất bại. Đồng thời, cần phân biệt **lỗi của tác vụ** với **lỗi do chính handler của người dùng ném ra**.

Đoạn sau là mã minh họa có thể đặt trong một chương trình Java với giao diện tương ứng:

~~~java
interface ResultCallback<T> {
    void onSuccess(T value);
    void onFailure(Throwable failure);
}

static <T> ResultCallback<T> instrument(
        ResultCallback<T> delegate) {
    return new ResultCallback<>() {
        @Override
        public void onSuccess(T value) {
            recordTaskSuccess();
            try {
                delegate.onSuccess(value);
            } catch (RuntimeException handlerFailure) {
                recordCallbackFailure(handlerFailure);
                throw handlerFailure;
            }
        }

        @Override
        public void onFailure(Throwable failure) {
            recordTaskFailure(failure);
            try {
                delegate.onFailure(failure);
            } catch (RuntimeException handlerFailure) {
                recordCallbackFailure(handlerFailure);
                throw handlerFailure;
            }
        }
    };
}
~~~

Ở đây, recordTaskSuccess và recordTaskFailure ghi **tín hiệu kết quả công việc**; recordCallbackFailure ghi **lỗi thực thi callback delegate**. Các phương thức record... là những hook minh họa, không có định nghĩa độc lập trong đoạn trích. Wrapper ném lại lỗi handler để tôn trọng cơ chế xử lý ngoại lệ sẵn có của dispatcher. Nếu thư viện yêu cầu handler không được throw, cần tuân theo chính sách lỗi của thư viện.

Các điểm cần kiểm tra trước khi bọc callback:

1. Callback có thể gọi không, một hay nhiều lần? Có cả callback terminal riêng không?
2. Có thể gọi callback đồng thời hay tái nhập (reentrant) không?
3. Có error callback riêng không? Exception handler có bị runtime nuốt/log không?
4. API có yêu cầu callback identity để removeListener/unsubscribe không? Nếu có, phải giữ mapping wrapper ↔ callback gốc.
5. Việc gắn wrapper có làm thay đổi ordering, chính sách retry hoặc luồng callback không?
6. Khi callback delegate thất bại, có nên để exception truyền tiếp hay API yêu cầu chuyển thành error signal? Hợp đồng API quyết định.

Nếu callback chỉ đăng ký rồi người gọi không có đối tượng kết quả, không thể tự suy diễn kết quả từ return của register. Nếu callback báo nhiều event, không đếm mỗi onSuccess là “toàn bộ công việc hoàn thành” trừ khi giao thức quy định như vậy.

## 7. Executor và fire-and-forget: quan sát ở nơi task chạy

Giả sử phương thức submitTask chỉ đặt Runnable vào executor:

~~~java
// Ví dụ minh họa; executor và runnable đã được khai báo.
executor.execute(runnable);
return;
~~~

Advice quanh submitTask chỉ thấy thao tác gửi task. Để đo thời gian thực thi, truy ngữ cảnh hay bắt lỗi trong Runnable, cần **decorator của task**:

~~~java
static Runnable observedTask(Runnable delegate) {
    return () -> {
        long startedAt = System.nanoTime();
        try {
            delegate.run();
            recordSuccess(System.nanoTime() - startedAt);
        } catch (RuntimeException failure) {
            recordFailure(failure, System.nanoTime() - startedAt);
            throw failure;
        }
    };
}
~~~

Đây là đoạn minh họa sử dụng các hook recordSuccess/recordFailure do người triển khai cung cấp. Nó đo từ lúc Runnable thực sự được chạy, không tính thời gian task nằm trong queue. Nếu cần end-to-end latency, lưu thêm timestamp tại thời điểm submit rồi kết hợp với timestamp lúc bắt đầu và hoàn tất thực thi.

**Khác biệt giữa execute và submit rất quan trọng:** Với nhiều implementation dựa trên ExecutorService, submit tạo Future ghi nhận exception của task; lỗi đó thường hiển thị khi gọi Future.get. Với execute, exception không bị Future của submit bao lại vì không có Future đó, và cách uncaught exception được xử lý tùy executor/runtime. Không suy ra một chính sách báo lỗi thống nhất cho mọi executor.

Nếu công việc bị từ chối ngay khi submit do executor đã shutdown hoặc quá tải, ngoại lệ có thể phát sinh **đồng bộ tại thao tác submit**; đây là một kết quả riêng, không có nghĩa task đã được chạy hay đã thất bại trong khi chạy. Với task bị hủy trước khi thực thi, wrapper Runnable có thể không bao giờ chạy: phải theo dõi cả cancellation/queue lifecycle nếu yêu cầu đo mọi submission.

## 8. Reactive Publisher: quan sát mỗi subscription thay vì phương thức tạo Publisher

Một phương thức có thể trả Publisher mà chưa thực thi công việc. Với nhiều Publisher, việc thực thi bắt đầu khi subscriber đăng ký. Mỗi subscription có thể có vòng đời riêng, và một Publisher có thể được đăng ký nhiều lần.

~~~text
buildPublisher() -> trả Publisher            (chỉ dựng mô tả pipeline)
                         |
subscriber A --------> subscribe ----> onNext* ----> onComplete/onError
                         |
subscriber B --------> subscribe ----> onNext* ----> onComplete/onError
                         |
cancel signal --------> kết thúc theo chính sách hủy của subscription
~~~

Cơ chế phù hợp ở đây là hook/decorator có hiểu giao thức tín hiệu:

- **onSubscribe:** bắt đầu vòng đời subscription và nhận subscription handle.
- **onNext:** quan sát từng phần tử; ghi số lượng và thời gian xử lý nếu cần, nhưng không biến onNext đầu tiên thành completion.
- **onError:** ghi lỗi terminal của subscription.
- **onComplete:** ghi hoàn tất bình thường.
- **cancel:** ghi việc subscriber chủ động hủy; không tự đồng nhất với success hay failure.
- **request/backpressure:** nếu instrumentation chuyển tiếp các tín hiệu, phải giữ nguyên số lượng/yêu cầu và thứ tự theo hợp đồng, không phát phần tử ngoài nhu cầu.

Không nên quan sát Publisher bằng cách tự subscribe trong advice chỉ để lấy log: thao tác này có thể kích hoạt công việc thêm một lần, tạo side effect, thay đổi tài nguyên hoặc làm sai số lượng subscriber. Hãy dùng operator/hook quan sát được cung cấp bởi mô hình hoặc decorator bảo toàn giao thức. Không blocking để chờ stream kết thúc trong lời gọi xây dựng Publisher.

Nếu Publisher phát nhiều phần tử, completion latency là từ **mốc định nghĩa của subscription** đến terminal signal, không phải từ lúc tạo đối tượng Publisher. Cần phân biệt một stream tồn tại lâu dài không bao giờ tự complete với một tác vụ một lần kết thúc hữu hạn.

## 9. Lỗi và hủy: thiết kế observation contract trước khi triển khai

Một hệ thống giám sát nên định nghĩa chính xác các trạng thái ở từng tầng:

| Tầng | Ví dụ trạng thái | Ý nghĩa |
| --- | --- | --- |
| Invocation | entered, returned, threw | Lời gọi đi vào và thoát ra thế nào |
| Registration/submit | accepted, rejected | Runtime có nhận đăng ký/task không |
| Execution | started, finished | Task thật sự bắt đầu và kết thúc khi nào |
| Completion | succeeded, failed, canceled | Kết quả cuối của operation theo giao thức |
| Callback execution | handler succeeded, handler failed | Chính code xử lý kết quả có chạy an toàn không |
| Subscription | active, completed, errored, canceled | Một subscription riêng đã kết thúc thế nào |

Sự phân tầng tránh các lỗi thống kê như: “Tất cả lời gọi submit đều success” dù phần lớn task bị fail sau đó; hoặc “task thất bại” khi chỉ handler ghi log ném exception.

**Phân loại failure không đơn giản là catch Throwable ở mọi nơi.** Trong Java, Error khác RuntimeException; quyết định quan sát Throwable, có log hay ném lại phải dựa trên contract và tính ổn định của runtime. Không nên tự ý nuốt VirtualMachineError hay biến cancellation thành success. Nếu error được bọc trong CompletionException/ExecutionException, giữ nguyên nguyên nhân và ghi nhận cause chính xác.

**Đo thời gian cần nhiều timestamp nếu nhiều tầng:** submission timestamp, execution start, invocation return, first result, terminal event. Queue latency = execution start − submit; task runtime = terminal − execution start; end-to-end latency = terminal − submit. Không đưa các đại lượng này vào cùng một metric khi chúng đo những hiện tượng khác nhau.

**Đếm event phải tránh đếm hai lần:** Nếu completion observer được gắn nhiều lần, mỗi observer có thể ghi một completion log. Nếu cùng một stage đã được quan sát ở nhiều tầng, phải định nghĩa ranh giới sở hữu metric và dùng operation ID/correlation key để phân biệt.

## 10. Tracing và context propagation trong AOP nâng cao

Trong mô hình đồng bộ, có thể mở và đóng scope tracing quanh một lời gọi. Ở mô hình bất đồng bộ, task có thể thực thi trên luồng khác hoặc callback tiếp tục khi scope ban đầu đã đóng.

Một pipeline thường cần:

1. Tạo/capture một correlation context khi operation được đăng ký.
2. Đính kèm context vào task, callback hoặc metadata được mô hình hỗ trợ.
3. Khi xử lý callback/task, restore context tạm thời.
4. Thực thi logic nghiệp vụ và instrumentation trong context đúng.
5. Cleanup/restore context trước đó trong finally, tránh rò trên thread pool.
6. Ghi event hoàn tất/hủy vào cùng operation ID.

~~~text
thread caller:
  begin trace A -> submit task (capture A) -> return -> close caller scope

thread worker:
  restore A -> run task -> signal completion -> cleanup A

completion observer:
  use captured A / native context -> record outcome -> cleanup
~~~

Đây là ví dụ ý tưởng; trong hệ thống cụ thể, model có thể hỗ trợ propagation sẵn, hoặc cần truyền context tường minh. Không giả định ThreadLocal tự theo một CompletableFuture qua mọi callback. Không để đồng thời nhiều callback dùng chung mutable context không an toàn, và không dùng global variable duy nhất cho nhiều tác vụ.

Khi completion callback được kích hoạt ngay lúc attach observer vì stage đã hoàn tất, xử lý context vẫn phải đúng. Thiết kế không nên phụ thuộc vào giả định callback luôn xảy ra trong một luồng hoặc một thời điểm định trước.

## 11. Những thay đổi hành vi do instrumentation có thể gây ra

Aspect theo dõi là code chạy thật, nên nó cũng có thể làm thay đổi hệ thống:

**Lỗi observer:** Một callback metrics có thể throw. Với CompletionStage, lỗi đó có thể ảnh hưởng dependent stage; với Runnable wrapper, lỗi đó có thể che lỗi ban đầu. Giảm tối đa side effect, áp dụng chính sách xử lý lỗi instrumentation riêng, tránh làm mất stack trace hoặc thay đổi completion contract.

**Identity và kiểu kết quả:** Decorator tạo object mới có thể phá so sánh reference, quy tắc hủy hoặc giao kèo về kiểu cụ thể. CompletionStage.whenComplete không cam kết trả chính stage ban đầu. Khi API consumer cần chính đối tượng gốc, phải kiểm tra cách attach observer mà vẫn trả đúng object và theo dõi lỗi observer tách biệt.

**Cancellation propagation:** Hủy dependent future không luôn có nghĩa hủy tác vụ upstream. Hủy một subscription có ý nghĩa khác với kết thúc nguồn. Không bổ sung propagate cancellation theo trực giác nếu mô hình không cam kết.

**Timing và scheduling:** Callback quan sát có thể thực thi inline và làm chậm thread hoàn tất stage. Chuyển observer sang executor khác có thể giảm blocking nhưng thay đổi thứ tự, điểm hoàn tất và nhu cầu quản lý shutdown. Tránh tác vụ logging nặng trong callback chạy trên event loop.

**Cardinality:** Một callback có thể được gọi nhiều lần, một Publisher có nhiều subscriber, một task có thể retry. Cần metric theo **operation**, **attempt**, **subscription**, hoặc **event** đúng yêu cầu; không gom các đơn vị này một cách tùy tiện.

**Lifecycle resources:** Đóng stream, file, buffer hay connection ở finally của lời gọi tạo tác vụ có thể quá sớm. Nếu tài nguyên thuộc về hoạt động bất đồng bộ, cleanup nên nằm tại completion/error/cancel tương ứng, với bảo đảm idempotent trong race condition.

**AOP join point coverage:** Proxy/interceptor quanh lời gọi không mặc nhiên quan sát mọi callback, task, hoặc lệnh nội bộ. Weaving có thể mở rộng loại join point quan sát được, nhưng cũng không tự hiểu completion semantics của một protocol. Độ sâu instrumentation phải tương ứng hợp đồng runtime.

## 12. Quy trình lựa chọn trong dự án

Dùng checklist dưới đây khi quyết định giữa advice tổng quát và hook chuyên biệt:

| Câu hỏi | Nếu câu trả lời là “có” | Hành động |
| --- | --- | --- |
| Lời gọi kết thúc là đủ để hoàn thành yêu cầu đo/ghi log? | Có | Dùng advice quanh lời gọi, không thêm hook |
| Có future/promise thể hiện outcome đến sau return? | Có | Theo dõi completion/error/cancel của stage |
| API trả void/handle và báo kết quả qua callback? | Có | Bọc callback hoặc dùng dispatcher hook |
| Có nhiều sự kiện, nhiều subscription hoặc stream không kết thúc ngay? | Có | Dùng lifecycle hook theo từng subscription |
| Task đi qua queue/executor? | Có | Instrument submission lẫn execution khi cần |
| Cần tracing qua nhiều luồng/continuation? | Có | Propagate context theo task/callback/continuation |
| Có retry, timeout, cancel hoặc cleanup phức tạp? | Có | Quan sát đúng trạng thái lifecycle và side effect |
| Hook quan sát có thể thay đổi lỗi, object identity hoặc scheduling? | Có | Xem xét contract và lựa chọn decorator an toàn hơn |

Sau đó thực hiện các bước:

1. **Định nghĩa đại lượng:** invocation latency, queue time, execution time, completion latency, error rate hay callback failure? Mỗi đại lượng có mốc bắt đầu/kết thúc rõ ràng.
2. **Xác định đối tượng đang đo:** một lời gọi, một submission, một task, một future, một subscriber hay một toàn bộ pipeline.
3. **Tìm chủ sở hữu tín hiệu kết thúc:** target stack, completion stage, callback, dispatcher, consumer hay subscription.
4. **Xác định nhánh terminal:** success, failure, cancellation, timeout và các tình huống callback tự throw. Không tự suy luận terminal từ “returned”.
5. **Đặt instrumentation ít xâm lấn nhất:** chỉ một hook đủ tin cậy để quan sát kết quả; bổ sung invocation advice nếu thật sự cần đo cả bước đăng ký.
6. **Bảo toàn contract:** không nuốt lỗi, không phát thêm subscription, không chặn event loop, không thay thứ tự callback, không làm sai propagation/hủy.
7. **Xác minh với race thực tế:** hoàn tất trước lúc gắn callback, callback gọi đồng bộ, hoàn tất ngay sau return, hủy trước thực thi, cùng operation có nhiều listener, callback metrics tự throw.

## 13. Những ngộ nhận thường gặp

**“After-returning nghĩa là operation success.”** Chỉ đúng nếu outcome thuộc về chính lời gọi. Future trả về bình thường có thể thất bại sau.

**“Callback luôn chạy ở thread khác.”** Sai. Callback có thể chạy trong thread hiện tại, kể cả khi đăng ký vào stage đã hoàn tất.

**“Around advice với try/catch bắt tất cả lỗi tương lai.”** Sai. Catch chỉ bắt exception lan qua call stack đang được thực thi; future/error signal cần hook đúng kênh.

**“Thêm whenComplete là hoàn toàn không đổi hành vi.”** Không luôn đúng. Nó tạo dependent stage và callback có thể throw, có chi phí thực thi, và có thể chạy trên luồng nhạy cảm về latency.

**“Một stream chỉ cần quan sát lần onNext đầu tiên.”** Sai nếu mục tiêu là outcome cuối. Một stream có thể tiếp tục nhiều phần tử, kết thúc bằng error hoặc bị hủy.

**“Có thể log bằng cách tự subscribe.”** Có thể kích hoạt nguồn thêm lần nữa, làm thay đổi semantics, phụ tải và side effect.

**“Chỉ bọc lời gọi submit là sẽ thấy lỗi khi task chạy.”** Không. Phải theo dõi task execution hoặc future/error channel của task.

**“Cancellation giống lỗi nghiệp vụ.”** Không mặc định. Cancellation có thể là quyết định bình thường của caller hoặc timeout; chính sách phân loại cần ghi rõ.

**“ThreadLocal đi theo lời gọi bất đồng bộ.”** Không được bảo đảm. Context phải được truyền hoặc restore bằng cơ chế phù hợp.

## 14. Bài tập tự đánh giá

**Tình huống 1:** Advice đo 2 ms quanh phương thức tạo CompletionStage; tác vụ mất 700 ms và thất bại. Muốn báo cáo latency thực và lỗi của tác vụ nên làm gì?

**Hướng giải:** Giữ 2 ms cho invocation latency nếu cần, đồng thời gắn completion observer vào stage để đo từ thời điểm khởi phát nghiệp vụ đến terminal event. Quan sát exceptional completion; không coi normal return là thành công của tác vụ.

**Tình huống 2:** API nhận callback mỗi khi sensor phát dữ liệu, có removeListener và không có “hoàn tất” tự động. Có nên ghi success khi callback đầu tiên chạy không?

**Hướng giải:** Không nếu metric biểu diễn thành công toàn bộ subscription. Theo dõi event count, error signal và sự kiện unregister/cancel theo giao thức. Nếu bọc listener, giữ mapping để removeListener vẫn hoạt động.

**Tình huống 3:** Một stage gốc completedFuture("ok"), còn thenApply xử lý nó ném IllegalArgumentException. Stage gốc thất bại không?

**Hướng giải:** Không. Stage phụ thuộc từ thenApply hoàn thành exceptional; stage gốc giữ kết quả "ok". Hook phải gắn đúng stage đại diện cho phạm vi kết quả cần đo.

**Tình huống 4:** Có một advice ghi log kết thúc rồi đóng tài nguyên trước khi task trong executor thực sự chạy. Nên thay đổi ở đâu?

**Hướng giải:** Nếu tài nguyên thuộc vòng đời task, dùng completion/task lifecycle hook để giải phóng sau khi thực thi, lỗi hay hủy theo contract. Đảm bảo cleanup idempotent và không đóng khi operation vẫn dùng tài nguyên.

**Tình huống 5:** Muốn tracing xuyên executor dùng chung nhưng đang ghi correlation ID bằng ThreadLocal. Điều gì còn thiếu?

**Hướng giải:** Capture context tại submit, truyền sang Runnable/Callable hoặc hook của mô hình, restore khi thực thi và cleanup trong finally, đồng thời bảo vệ trước việc worker thread tái sử dụng.

## Kết luận

Hãy chọn **cơ chế chuyên biệt của mô hình bất đồng bộ** khi mục tiêu AOP phụ thuộc vào kết quả hoặc vòng đời diễn ra **sau khi lời gọi phương thức đã trả về**, hoặc khi mô hình có ngữ nghĩa riêng về error, cancellation, subscription, callback và context. Một advice tổng quát vẫn hữu ích để ghi nhận mốc invocation/registration; completion hook, callback wrapper, task decorator hay stream lifecycle hook sẽ bổ sung góc nhìn mà call stack ban đầu không cung cấp. Chất lượng instrumentation được quyết định bởi việc gắn đúng **điểm phát tín hiệu thật**, hiểu rõ hợp đồng API và bảo toàn hành vi nghiệp vụ.