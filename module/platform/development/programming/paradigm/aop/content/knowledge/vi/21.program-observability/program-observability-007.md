# Không để lỗi ghi nhật ký làm thay đổi kết quả ngoài chính sách trong AOP

## 1. Mục tiêu: tính đúng đắn nghiệp vụ phải đi trước cơ chế quan sát

Logging advice trong AOP có thể chạy trước, sau hoặc bao quanh nhiều join point để ghi tình trạng lời gọi. Khác với các bài về chọn sự kiện hay lọc dữ liệu, ở đây câu hỏi chính là: **khi chính hệ thống ghi log thất bại, kết quả nghiệp vụ phải được bảo vệ như thế nào?**

Tuy nhiên, **ghi nhật ký cũng là một thao tác có thể thất bại**. Hệ thống ghi log có thể hết dung lượng, không truy cập được tệp, bị từ chối gửi mạng, đầy hàng đợi, serialize dữ liệu lỗi, mắc lỗi khi định dạng chuỗi hoặc chính đoạn instrumentation bị lỗi. Nếu thực hiện sơ suất, lỗi thứ cấp từ logger sẽ:

- Biến một thao tác nghiệp vụ thành công thành một lời gọi ném ngoại lệ.
- Che mất ngoại lệ nghiệp vụ ban đầu, khiến caller chỉ thấy lỗi ghi log.
- Chặn việc gọi nghiệp vụ vì lời ghi log ở advice *before* thất bại.
- Thay đổi giá trị trả về, loại ngoại lệ, thông điệp hoặc trạng thái future.
- Làm một callback/thao tác bất đồng bộ bị đánh dấu thất bại dù công việc gốc đã thành công.
- Gây chậm, tắc hàng đợi, deadlock hoặc tiêu tốn tài nguyên ngoài giới hạn dự kiến.

Vì vậy, trước khi viết advice cần có **chính sách lỗi ghi nhật ký**. Với log quan sát thông thường, chính sách phổ biến là *best effort/fail-open*: logger lỗi thì ghi nhận sự cố theo cơ chế dự phòng được kiểm soát, nhưng vẫn giữ nguyên kết quả nghiệp vụ. Với nhật ký bắt buộc vì kiểm toán, bảo mật hoặc ràng buộc pháp lý, có thể cần *fail-closed*: không cho phép thực hiện hành động khi điều kiện ghi audit chưa được đáp ứng. **Đó phải là quyết định nghiệp vụ có chủ đích**, được thực thi tại một ranh giới phù hợp, không phải tác dụng phụ ngẫu nhiên của một lệnh ghi log bị lỗi.

Mục tiêu học tập:

1. Hiểu vì sao lời gọi logger trong advice có thể phá tính minh bạch của một aspect.
2. Nhận diện các vị trí logging che khuất kết quả hoặc ngoại lệ nghiệp vụ.
3. Thiết kế ranh giới cô lập lỗi cho log best effort, cả đồng bộ lẫn bất đồng bộ.
4. Biết lúc nào cần chính sách fail-open, fail-closed, buffer hoặc cơ chế lưu audit bền vững.
5. Kiểm chứng bằng Java 17+ rằng logger thất bại nhưng caller vẫn nhận đúng giá trị hoặc ngoại lệ gốc.

## 2. Kết quả “không thay đổi” nghĩa là gì?

**Tính minh bạch quan sát (observational transparency)** ở phạm vi này có nghĩa: trừ những khác biệt đã được chính sách cho phép, thêm logging aspect không làm thay đổi các kết quả mà thành phần nghiệp vụ và caller có thể quan sát.

Với một lời gọi đồng bộ, cần bảo toàn:

- **Giá trị trả về**, gồm giá trị null nếu hợp đồng cho phép.
- **Việc ném ngoại lệ hay trả bình thường**: không đổi nhánh điều khiển chỉ vì sink log lỗi.
- **Loại và đối tượng ngoại lệ** khi hợp đồng yêu cầu; tốt nhất truyền tiếp chính ngoại lệ nghiệp vụ đã nhận, không tự thay bằng lỗi logging.
- **Nguyên nhân và stack trace** của lỗi nghiệp vụ; đừng tự đóng gói hoặc xóa mất chúng nếu không có yêu cầu.
- **Tác dụng phụ và thứ tự nghiệp vụ**: logging không được bất ngờ khiến nghiệp vụ chạy hai lần, bỏ qua hoặc rollback giả tạo.
- **Ràng buộc hiệu năng được công bố**: best effort không có nghĩa chấp nhận treo vô hạn khi ghi log.

Với bất đồng bộ, còn phải xem **kết quả cuối cùng của future, callback, task hoặc stream**. Phương thức trả về một future bình thường chưa phải công việc thành công. Nếu observer log ném lỗi vào dependent stage, caller có thể thấy lỗi logging thay cho kết quả công việc. Vì vậy, chỉ kiểm tra advice đồng bộ là chưa đủ.

Không có bảo đảm tuyệt đối rằng logging sẽ không bao giờ ảnh hưởng tới hệ thống: ghi log luôn tốn CPU, bộ nhớ và có thể gây lỗi nghiêm trọng của JVM. Mục tiêu thực tế là **quy định và kiểm soát những failure mode có thể xử lý**, nhất là RuntimeException ở tầng ghi log, chi phí blocking và chính sách quá tải. Không nên hứa rằng bắt mọi Throwable có thể khiến chương trình an toàn trước OutOfMemoryError hay lỗi nghiêm trọng của runtime.

## 3. Các lỗi cơ bản khi viết advice

### 3.1. Ghi log trong finally có thể che ngoại lệ hoặc làm mất kết quả

Đoạn minh họa sau có lỗi thiết kế:

~~~java
// Minh họa anti-pattern; target và sink là thành phần đã được khai báo.
try {
    return target.call();
} finally {
    sink.write("finished");
}
~~~

Nếu target trả về “OK” nhưng sink.write ném IllegalStateException, caller sẽ nhận **IllegalStateException từ sink**, không nhận “OK”. Nếu target đã ném IllegalArgumentException và sink.write ném lỗi khi finally chạy, lỗi từ sink có thể thay thế ngoại lệ nghiệp vụ trên đường thoát. Finally bảo đảm có cơ hội thực thi cleanup; nó **không bảo đảm thao tác trong finally là vô hại**.

Cách sử dụng đúng cho log best effort là bọc riêng thao tác logger trong một vùng xử lý lỗi:

~~~java
// Mã minh họa một đoạn advice; safeLog có hợp đồng không ném
// những lỗi logger thông thường thuộc chính sách best effort.
try {
    return target.call();
} finally {
    safeLog("finished");
}
~~~

Bản chất của safeLog quan trọng hơn tên gọi: nó phải xử lý được **toàn bộ thao tác thuộc logging**, kể cả tạo dữ liệu log nếu dữ liệu đó có thể ném RuntimeException.

### 3.2. Ghi log ngay trong catch có thể che ngoại lệ gốc

~~~java
// Anti-pattern
try {
    return target.call();
} catch (RuntimeException businessError) {
    sink.write("business failed: " + businessError.getMessage());
    throw businessError;
}
~~~

Nếu sink.write lỗi, lệnh throw businessError không chạy đến. Caller nhận lỗi logging. Đây là tình huống che giấu nguyên nhân phổ biến trong xử lý ngoại lệ.

Phiên bản phù hợp với chính sách best effort:

~~~java
try {
    return target.call();
} catch (RuntimeException businessError) {
    safeLogBusinessFailure(businessError);
    throw businessError;
}
~~~

**Điểm then chốt:** giữ lại đối tượng businessError và ném lại chính nó sau khi thử ghi log. Không dùng một catch tổng quát rồi vô tình trả giá trị mặc định hoặc đổi thành ngoại lệ “Logging failed” nếu chính sách không cho phép.

### 3.3. Advice trước lời gọi có thể ngăn nghiệp vụ chạy

~~~java
// Anti-pattern trong chính sách fail-open
sink.write("starting work");
return target.call();
~~~

Nếu sink.write ném lỗi, target.call không được thực thi. Có thể sửa bằng helper ghi log an toàn, rồi tiếp tục gọi target. Với chính sách audit bắt buộc, chặn trước khi hành động diễn ra có thể đúng, nhưng phải nêu tường minh rằng *thiếu audit thì từ chối hành động*, thay vì xem đó là bug logging tình cờ.

### 3.4. Ghi log sau return có thể biến thành công thành lỗi

~~~java
// Anti-pattern
Result result = target.call();
sink.write("success");
return result;
~~~

Một lỗi từ sink sau khi target đã gây side effect sẽ làm caller thấy lời gọi thất bại. Nếu caller retry dựa trên ngoại lệ đó, side effect nghiệp vụ có thể **bị lặp**. Đây là lý do cần tách lỗi logging khỏi kết quả trước khi trả về.

### 3.5. Gom mọi thao tác vào một catch có thể nuốt nhầm lỗi nghiệp vụ

~~~java
// Anti-pattern: kết quả fallback không hề có trong contract
try {
    sink.write("start");
    return target.call();
} catch (RuntimeException error) {
    return fallback;
}
~~~

Catch này không phân biệt lỗi logging với lỗi target. Nếu target lỗi thật, nó cũng bị chuyển thành fallback. Hãy dùng **ranh giới try/catch riêng** cho logger; nếu cần catch lỗi nghiệp vụ, catch để ghi nhận và ném lại theo hợp đồng nghiệp vụ.

## 4. Thiết kế helper logging best effort đúng trách nhiệm

Một wrapper nhỏ giúp các advice tái sử dụng cùng một chính sách:

~~~java
@FunctionalInterface
interface LogSink {
    void append(String event);
}

static void safeLog(LogSink sink, String event) {
    try {
        sink.append(event);
    } catch (RuntimeException loggingFailure) {
        // Chính sách best effort:
        // không để lỗi logger thay thế outcome của target.
        // Ghi nhận degradation ở cơ chế riêng nếu có,
        // nhưng cơ chế dự phòng cũng phải được kiểm soát.
    }
}
~~~

Đây là đoạn minh họa, chưa phải chương trình độc lập. Những điều cần xác định rõ khi triển khai thực tế:

1. **Phạm vi lỗi được chấp nhận:** helper bắt RuntimeException đến từ thao tác ghi log. Không bọc cả target.call trong helper này. Không vô điều kiện bắt Throwable rồi nuốt cả Error của JVM.
2. **Tạo event thuộc vùng được bảo vệ:** nếu message serialization, gọi toString, truy cập dữ liệu hoặc thêm trường ngữ cảnh có thể lỗi, thực hiện chúng **bên trong** ranh giới best effort.
3. **Phản ứng của hệ thống khi log lỗi:** có thể tăng bộ đếm trong bộ nhớ, cảnh báo qua health status, dùng kênh sự cố độc lập hoặc sampling; không gọi ngược cùng sink đang hỏng vô hạn.
4. **Giới hạn thời gian và tài nguyên:** catch exception không giải quyết logger bị treo hay ghi log chặn luồng quá lâu. Cần timeout, queue hữu hạn hoặc phương án non-blocking tùy độ quan trọng của log.
5. **Bảo toàn ngoại lệ đang truyền:** helper không được ném exception riêng, thay đổi cause chain, sửa return value hoặc gọi lại target để “bù” sự cố logging.
6. **Tránh nuốt âm thầm ở mọi trường hợp:** best effort là quyết định có chủ đích; hệ thống vẫn cần chỉ báo đang mất khả năng quan sát ở kênh độc lập nếu yêu cầu vận hành cần biết.

Khi event được xây dựng từ đầu vào có thể lỗi, có thể dùng callback trì hoãn định dạng để đưa toàn bộ thao tác vào catch:

~~~java
// Đoạn minh họa; Supplier lấy từ java.util.function.
static void safeLog(
        LogSink sink,
        java.util.function.Supplier<String> eventSupplier) {
    try {
        sink.append(eventSupplier.get());
    } catch (RuntimeException loggingFailure) {
        // Ghi nhận logger degraded theo kênh độc lập (nếu khả thi).
    }
}
~~~

Thời điểm đánh giá supplier vẫn nằm trong luồng gọi, do đó tránh xây dựng log quá tốn kém hoặc chứa dữ liệu nhạy cảm. Helper này không bảo đảm cô lập tác vụ blocking; cần cấu hình vận chuyển log riêng cho trường hợp đó.

## 5. Một chương trình Java 17+ kiểm chứng trực tiếp

Ví dụ dưới mô phỏng sink luôn ném IllegalStateException. Aspect được biểu diễn bằng các hàm bao quanh lời gọi và completion observer để tập trung vào **ngữ nghĩa lỗi**; đây không phải một runtime weaving đầy đủ.

Tạo file **LoggingIsolationDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public class LoggingIsolationDemo {
    @FunctionalInterface
    interface LogSink {
        void append(String event);
    }

    static void safeLog(LogSink sink, String event) {
        try {
            sink.append(event);
        } catch (RuntimeException loggingFailure) {
            System.out.println("LOGGER DOWN: " + loggingFailure.getMessage());
        }
    }

    static <T> T around(String operation, Supplier<T> business, LogSink sink) {
        safeLog(sink, "begin " + operation);
        try {
            T result = business.get();
            safeLog(sink, "success " + operation);
            return result;
        } catch (RuntimeException businessError) {
            safeLog(sink, "failure " + operation);
            throw businessError;
        }
    }

    static <T> CompletionStage<T> observeCompletion(
            String operation, CompletionStage<T> source, LogSink sink) {
        return source.whenComplete((value, failure) -> {
            safeLog(sink, failure == null
                    ? "completed " + operation
                    : "failed " + operation);
        });
    }

    public static void main(String[] args) {
        LogSink broken = event -> {
            throw new IllegalStateException("storage unavailable");
        };

        String result = around("read", () -> "DATA", broken);
        System.out.println("RESULT: " + result);

        RuntimeException original =
                new IllegalArgumentException("invalid input");
        try {
            around("parse", () -> {
                throw original;
            }, broken);
        } catch (RuntimeException observed) {
            System.out.println("SAME ERROR: " + (observed == original));
        }

        CompletionStage<Integer> success = observeCompletion(
                "calculate", CompletableFuture.completedFuture(42), broken);
        System.out.println("ASYNC VALUE: " + success.toCompletableFuture().join());

        CompletableFuture<Integer> pending = new CompletableFuture<>();
        CompletionStage<Integer> failed = observeCompletion(
                "remote", pending, broken);
        pending.completeExceptionally(new IllegalArgumentException("timeout"));
        try {
            failed.toCompletableFuture().join();
        } catch (CompletionException error) {
            System.out.println("ASYNC ERROR: " + error.getCause().getMessage());
        }
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac LoggingIsolationDemo.java
java LoggingIsolationDemo
~~~

Kết quả stdout xác định:

~~~text
LOGGER DOWN: storage unavailable
LOGGER DOWN: storage unavailable
RESULT: DATA
LOGGER DOWN: storage unavailable
LOGGER DOWN: storage unavailable
SAME ERROR: true
LOGGER DOWN: storage unavailable
ASYNC VALUE: 42
LOGGER DOWN: storage unavailable
ASYNC ERROR: timeout
~~~

### Phân tích kết quả

**Trường hợp read:** logging ở đầu và cuối đều hỏng nhưng around vẫn trả “DATA”. Advice giữ đúng đường return.

**Trường hợp parse:** target ném một đối tượng IllegalArgumentException đã tạo sẵn. Logging lúc bắt đầu và lúc xử lý thất bại đều hỏng nhưng advice ném lại **chính đối tượng ngoại lệ gốc**. Biểu thức so sánh tham chiếu trả true.

**Trường hợp calculate:** source là completedFuture(42), nên observer có thể chạy ngay khi đăng ký. Lỗi logger bị cô lập; stage phụ thuộc vẫn hoàn thành với 42.

**Trường hợp remote:** source future đang pending được gắn observer. Khi completeExceptionally được gọi, callback logging chạy và xử lý lỗi sink. Stage quan sát vẫn hoàn tất exceptional bằng lỗi nghiệp vụ; khi join, caller nhận CompletionException chứa IllegalArgumentException("timeout").

Cách tạo future trong ví dụ tránh yếu tố nondeterministic của lịch chạy nhiều thread, nhờ đó thứ tự stdout ổn định. Trong code sản xuất, completion callback có thể chạy trên nhiều luồng tùy API và thời điểm hoàn tất. Vì vậy không được dựa vào thứ tự dòng log giữa các luồng để kết luận thứ tự nghiệp vụ.

**Giới hạn chủ ý của ví dụ:** safeLog in ra console khi log lỗi để dễ học và kiểm chứng. Console ở ví dụ là **kênh minh họa**, không phải lời hứa rằng kênh dự phòng luôn hoạt động. Nếu chính System.out cũng lỗi, đoạn này chưa cô lập lỗi đó. Trong hệ thống thực, hãy thiết kế một kênh báo degradation phù hợp hoặc chấp nhận best effort hoàn toàn và xác định phạm vi lỗi được cô lập. around chỉ xử lý RuntimeException từ supplier; checked exception cần một giao diện có throws và chính sách tương ứng.

## 6. Phân biệt ba chính sách khi hệ thống ghi log hỏng

Không có một chính sách đúng cho tất cả kiểu nhật ký. Hãy phân loại **mục đích của dữ liệu** trước:

| Loại ghi nhận | Ví dụ | Chính sách thường phù hợp | Điều cần bảo toàn |
| --- | --- | --- | --- |
| Log chẩn đoán best effort | Thời gian gọi, dòng debug, thông tin xử lý | Fail-open, có giới hạn hao phí | Kết quả nghiệp vụ không phụ thuộc sink |
| Metrics/tracing quan sát | Số lời gọi, latency, span, sự kiện tracing | Thường fail-open; có sampling/backpressure | Không thay return, exception hay completion |
| Audit bắt buộc | Sự kiện nghiệp vụ cần chứng minh, yêu cầu tuân thủ | Theo yêu cầu nghiệp vụ: lưu bền vững hoặc fail-closed | Không thực thi thay đổi bị cấm nếu thiếu bảo đảm audit |
| Log vận hành quan trọng | Lỗi cần điều tra, cảnh báo an toàn | Buffer, retry hữu hạn, báo health degraded; có thể nâng mức cảnh báo | Không gây nghẽn vô hạn hoặc vòng lặp lỗi |
| Nhật ký quyết định nghiệp vụ | Bản ghi làm căn cứ thanh toán/đối soát | Coi là dữ liệu nghiệp vụ với transaction/reconciliation rõ ràng | Tính nhất quán và khôi phục theo hợp đồng |

**Fail-open**: khi kênh quan sát thất bại, nghiệp vụ vẫn chạy và trả kết quả theo chính hợp đồng của nó. Cần quy định hệ thống chấp nhận mất log bao nhiêu, cách báo hệ thống mất quan sát, giới hạn queue và tỷ lệ drop.

**Fail-closed**: nếu điều kiện audit là bắt buộc **trước khi thực hiện** một hành động nhạy cảm, có thể từ chối bắt đầu hành động khi chưa thể đảm bảo ghi nhận audit. Đây là một phần của contract nghiệp vụ và có thể phát sinh lỗi rõ ràng như “audit unavailable” theo chính sách được chấp thuận. Không sử dụng fail-closed một cách ngẫu nhiên chỉ vì logger throw sau khi tác dụng phụ đã xảy ra.

**Lưu bền vững/audit transaction**: khi nghiệp vụ và audit phải nhất quán, cần thiết kế commit chung trong phạm vi transaction phù hợp hoặc mẫu transactional outbox. Ví dụ cùng lưu thay đổi nghiệp vụ và một sự kiện audit/outbox trong một transaction của cùng kho dữ liệu; sender gửi tiếp sau commit và có cơ chế retry, idempotency, giám sát tồn đọng. Không tự suy diễn rằng hai hệ thống lưu trữ độc lập có thể atomic chỉ nhờ đặt chúng trong around advice.

### Vì sao một lời gọi ghi log sau khi nghiệp vụ chạy không tạo được audit atomic?

Giả sử chuyển tiền thành công rồi ghi audit bị lỗi. Nếu advice ném “audit unavailable” ra caller, tiền vẫn có thể đã chuyển; caller tưởng thao tác thất bại và có thể thực hiện lại. Ngược lại nếu âm thầm bỏ qua audit, yêu cầu tuân thủ có thể bị vi phạm. Giải pháp là ràng buộc đúng tính nguyên tử hoặc khả năng phục hồi của **thao tác ghi sự kiện audit** với **thao tác nghiệp vụ**, không chỉ đổi catch behavior.

Một quyết định chính sách hoàn chỉnh cần trả lời:

1. Loại log nào được phép mất?
2. Trạng thái logger degraded có làm từ chối thao tác mới không?
3. Ai được phép retry và có cơ chế idempotency nào?
4. Nếu lỗi xảy ra *sau commit*, caller sẽ nhận thông tin gì để tránh thực thi lại không an toàn?
5. Có replay, reconcile hay kiểm tra tồn đọng audit được không?
6. Các giá trị nào là dữ liệu nhạy cảm và phải được loại bỏ/che khi ghi nhận?

## 7. Lỗi logger phát sinh ngoài lời gọi đồng bộ

### 7.1. CompletionStage và future

Một advice quanh phương thức trả CompletionStage có thể kết thúc trước khi future hoàn tất. Nếu cần ghi log tại lúc hoàn tất, callback của stage cũng có khả năng ném lỗi. Trong Java, whenComplete tạo một **stage phụ thuộc**: lỗi do action của observer ném có thể khiến stage mới thất bại nếu stage gốc thành công.

Mã nguy hiểm:

~~~java
// Đoạn minh họa; stage và sink đã có sẵn.
return stage.whenComplete((value, error) -> {
    sink.append("operation ended"); // có thể throw
});
~~~

Mã phù hợp với chính sách best effort:

~~~java
return stage.whenComplete((value, error) -> {
    safeLog(sink, "operation ended");
});
~~~

Cần hiểu các ràng buộc bổ sung:

- Nếu callback thành công hoặc lỗi đã được helper cô lập, observer không cố tình thay đổi kết quả nguồn.
- Nếu callback observer ném lỗi nghiêm trọng ngoài phạm vi helper, dependent stage có thể chịu ảnh hưởng; không tuyên bố bất biến tuyệt đối.
- whenComplete trả stage mới; nếu giữ nguyên identity object là một phần của contract, có thể attach observer bên cạnh rồi trả source gốc, nhưng phải có chính sách riêng với dependent stage tạo ra.
- Cancellation propagation giữa dependent stage và upstream không nên suy đoán. Cần kiểm tra hành vi theo implementation và contract.
- Logger có thể chặn thread hoàn tất future. Bảo vệ chống throw chưa giải quyết độ trễ; có thể cần kênh gửi log không chặn với queue hữu hạn.

Đặc biệt, một callback thenApply/thenAccept do nghiệp vụ định nghĩa có thể throw; đó là lỗi của nhánh xử lý, không nhất thiết là lỗi của stage trước. Instrumentation phải ghi nhận đúng stage được định nghĩa là outcome chính.

### 7.2. Callback API và dispatcher

Nếu một API đăng ký callback rồi trả về, advice quanh register không thể thấy lỗi logging phát sinh sau đó khi callback chạy. Để cô lập lỗi logger ở callback, cần đặt helper **bên trong chính callback hoặc wrapper thực thi callback**.

~~~java
// Đoạn minh họa; delegate và sink là các thành phần đã khai báo.
void onResult(String value) {
    safeLog(sink, "result delivered");
    delegate.onResult(value); // lỗi của delegate là lỗi riêng của delegate
}
~~~

Không được viết catch RuntimeException quanh cả safeLog và delegate rồi nuốt mọi lỗi, vì như vậy có thể nuốt lỗi nghiệp vụ do delegate phát sinh. Nếu callback có phương thức removeListener hoặc sử dụng identity để unsubscribe, cần bảo toàn mapping từ callback gốc sang wrapper. Không gọi callback thêm lần nào chỉ để retry logging.

### 7.3. Executor và tác vụ chạy nền

Nếu target chỉ gọi execute/submit để đưa một task vào hàng đợi, lời gọi đó có thể thành công dù task sau đó thất bại. Nếu logging được thực thi trong Runnable wrapper, helper bảo vệ logging tại **task execution boundary**:

~~~java
// Đoạn minh họa; delegate và sink đã được khai báo.
Runnable wrapped = () -> {
    safeLog(sink, "task started");
    try {
        delegate.run();
        safeLog(sink, "task finished");
    } catch (RuntimeException businessError) {
        safeLog(sink, "task failed");
        throw businessError;
    }
};
~~~

Nếu một task chưa bao giờ chạy vì bị hủy trước lúc thực thi, wrapper không quan sát được thời điểm hủy. Nếu cần metrics đầy đủ, gắn thêm hook ở future/task lifecycle. Tránh gọi logging đồng bộ tốn thời gian trên thread quan trọng; nếu logger hết dung lượng queue, quy định rõ drop, backpressure hoặc blocking trong giới hạn.

### 7.4. Reactive stream hoặc nguồn sự kiện liên tục

Với mô hình phát nhiều sự kiện, logging có thể thực hiện tại các tín hiệu subscribe, onNext, onError, onComplete và cancel. Observer log ném exception trong xử lý một phần tử có thể làm pipeline bị dừng hoặc tạo error signal mới tùy mô hình. Phải dùng hook “do/observe” đúng theo hợp đồng của stream và cô lập lỗi logger trong callback quan sát.

Không tự subscribe lần nữa chỉ để ghi log, vì có thể kích hoạt thêm công việc hoặc nhân đôi side effect. Với stream có nhiều subscriber, xác định rõ một dòng log đại diện cho **mỗi sự kiện**, **mỗi subscription** hay **toàn bộ nguồn**, tránh nhân đôi hoặc sai metric.

## 8. Xử lý chính exception của nghiệp vụ mà không làm méo thông tin lỗi

Nếu advice bắt được lỗi nghiệp vụ, mục tiêu logging thường là thêm ngữ cảnh chẩn đoán mà vẫn cho caller nhận lại lỗi gốc:

~~~java
// Minh họa: chỉ log; không thay businessError.
try {
    return target.call();
} catch (RuntimeException businessError) {
    safeLog(sink, "business failed");
    throw businessError;
}
~~~

Một số quyết định cần cân nhắc:

**Giữ object identity:** Ném lại chính businessError cho phép code caller đang kiểm tra ngoại lệ tham chiếu gốc hoặc đặc tính bổ sung tiếp tục hoạt động. Tạo một ngoại lệ mới chỉ vì logger thất bại sẽ thay contract.

**Giữ cause chain:** Nếu cần phân loại lỗi và log cause, hãy đọc có kiểm soát. Lỗi logging không nên trở thành cause của lỗi nghiệp vụ. Không thay stack trace để “đẹp log”.

**Suppressed exception:** Có thể bổ sung lỗi logging bằng addSuppressed trên businessError khi chính sách cho phép; tuy nhiên hành động này **thay đổi dữ liệu ngoại lệ** và có thể tăng bộ nhớ hay lộ chi tiết vận hành. Với log best effort yêu cầu không đổi kết quả có thể quan sát, không tự động đính loggingFailure vào businessError.

**Checked exception:** Java cho phép phương thức ném checked exception theo khai báo. Around advice phải có chữ ký/giao diện phù hợp và truyền lại chính exception đó. Đừng bọc mọi Exception thành RuntimeException chỉ để viết interceptor gọn hơn.

**Error nghiêm trọng:** Một helper chỉ catch RuntimeException không che VirtualMachineError, ThreadDeath hoặc lỗi JVM khác. Việc cố “bảo đảm không có lỗi ghi log nào thoát ra” bằng catch Throwable không tự làm chương trình an toàn; các lỗi fatal có thể là dấu hiệu runtime không còn khả năng phục hồi. Phạm vi chống lỗi cần được công bố chính xác.

**Độ nhạy dữ liệu:** Một dòng stack trace hoặc toString có thể chứa thông tin cá nhân, mã thông báo hay bí mật. Aspect nên log theo trường đã lọc, tuân theo chính sách ẩn danh/che dữ liệu. Log hỏng không phải lý do dùng fallback kém bảo mật hơn.

## 9. Khi bản thân hệ thống báo lỗi logger lại bị lỗi

Một anti-pattern nguy hiểm là gọi lại chính logger từ catch loggingFailure:

~~~java
// Anti-pattern
try {
    sink.append("business event");
} catch (RuntimeException loggingFailure) {
    sink.append("logging failed: " + loggingFailure);
}
~~~

Nếu sink vẫn hỏng, exception thứ hai lại thoát và có thể che kết quả nghiệp vụ. Nếu logger nội bộ cũng ghi thông qua chính aspect đang áp dụng, vòng gọi lồng nhau có thể dẫn đến đệ quy vô hạn.

Chiến lược thay thế:

- Ghi nhận trạng thái “logging degraded” bằng một thành phần độc lập, giới hạn tần suất và tránh route qua cùng sink lỗi.
- Có thể dùng counter trong bộ nhớ cho số lần ghi thất bại, kết hợp health check hoặc cảnh báo nội bộ; xác định rõ xử lý khi bộ đếm/health reporter cũng gặp lỗi.
- Nếu cần fallback, dùng **kênh khác thật sự** và đảm bảo đường fallback không kích hoạt chính aspect gây sự cố.
- Dùng cơ chế chống reentrancy có vòng đời rõ, ví dụ trạng thái theo scope của invocation và cleanup đúng ở finally; không sử dụng một cờ global đơn nhất cho nhiều task đồng thời.
- Giới hạn dung lượng lưu sự cố, tần suất gửi, số lần retry, mức độ backpressure để lỗi logger không khuếch đại thành quá tải hệ thống.

Không nên dùng một logger hỏng để liên tục thông báo chính lỗi hỏng của nó. Mất vài bản ghi chẩn đoán ít nguy hiểm hơn tạo một failure cascade ảnh hưởng trực tiếp nghiệp vụ.

## 10. Đồng bộ, bất đồng bộ và điểm đo chính xác

AOP cho quan sát chương trình phải xác định **ranh giới** của từng sự kiện:

| Sự kiện | Có thể ghi ở đâu? | Logger hỏng có thể ảnh hưởng gì nếu không cô lập? |
| --- | --- | --- |
| Enter invocation | Before/around advice | Chặn target chưa được gọi |
| Normal return | After-returning/around | Đổi success thành throw |
| Business throw | After-throwing/around catch | Che business exception |
| Invocation finally | Finally của advice | Che cả return lẫn throw |
| Future completion | Completion observer | Làm dependent stage exceptional |
| Callback execution | Callback wrapper | Làm dispatcher/callback thất bại |
| Task execution | Runnable/Callable wrapper | Làm task lỗi hoặc thay exception |
| Stream signal | Subscriber/operator observer | Đổi tiến trình hoặc terminal signal |

**Một thao tác return thành công không tương đương một công việc async thành công.** Nếu aspect ghi “operation success” ngay khi trả future, log có thể sai ngay cả khi logger hoàn toàn khỏe mạnh. Phân biệt log “invocation returned” với “operation completed successfully”; hook completion được dùng cho trạng thái thứ hai.

Cũng cần phân biệt **lỗi business**, **lỗi callback xử lý business** và **lỗi logger**. Nếu callback nghiệp vụ throw sau khi xử lý một stage thành công, dependent stage có thể thất bại trong khi stage upstream vẫn thành công. Hãy quan sát outcome của đúng stage mà contract coi là kết quả cuối cùng.

## 11. Logging bất đồng bộ không tự động an toàn

Ghi log vào hàng đợi rồi trả nhanh thường giúp giảm chi phí trên đường xử lý nghiệp vụ, nhưng chỉ chuyển lỗi sang một tầng khác:

- Queue có thể đầy; producer bị block, bị reject hoặc log bị drop tùy chính sách.
- Worker gửi log có thể bị lỗi I/O, lỗi serialization hoặc chết.
- Khi tiến trình dừng, phần log chưa flush có thể bị mất.
- Retry quá mạnh khi sink chậm có thể chiếm CPU, bộ nhớ và băng thông.
- Mỗi event log có thể chứa dữ liệu mutable, bị thay đổi trước khi worker serialize.

Với log best effort, nên quy định một ngân sách rõ ràng: queue hữu hạn, chính sách drop/sampling hoặc phương án không chặn, số retry tối đa, cách quan sát tỉ lệ drop và shutdown flush trong giới hạn. Nếu nghiệp vụ không được phép mất audit, thiết kế queue volatile đơn thuần không đáp ứng yêu cầu durability.

Không đảm bảo “logger không ảnh hưởng business” chỉ bằng try/catch nếu sink có thể block vô thời hạn. Cần cả chính sách latency và backpressure.

## 12. Testing: xác minh cả logger hỏng và nghiệp vụ hỏng

Một bài kiểm thử tốt phải tiêm lỗi tại từng điểm logging và kiểm tra **outcome quan sát từ caller**, không chỉ kiểm tra rằng chương trình “không crash”:

| Tình huống | Kỳ vọng với log best effort |
| --- | --- |
| Logger hỏng ở before; target trả giá trị | Target vẫn chạy đúng một lần, caller nhận nguyên giá trị |
| Logger hỏng sau khi target trả | Caller vẫn nhận giá trị, không bị throw từ logger |
| Target throw; logger hỏng trong catch | Caller nhận chính lỗi target, cause/identity không bị thay |
| Target throw; logger hỏng trong finally | Không che lỗi gốc |
| Target trả null; logger hỏng | Trả đúng null |
| Future thành công; observer log throw | Stage được trả vẫn có kết quả thành công theo contract |
| Future exceptional; observer log throw | Lỗi nghiệp vụ không bị che hoặc chuyển thành success |
| Callback/stream phát nhiều tín hiệu; logger lỗi | Không thêm callback, không chuyển sai terminal signal |
| Logger bị block/queue đầy | Hành vi phù hợp time budget và overflow policy |
| Fallback reporter cũng lỗi | Không tạo recursion hoặc failure cascade |
| Logging yêu cầu audit bắt buộc không sẵn sàng | Hành vi từ chối/hoãn hoặc transaction recovery đúng chính sách đã công bố |

### 12.1. Kiểm tra giá trị và tham chiếu ngoại lệ

Trong Java có thể kiểm tra:

~~~java
// Minh họa kiểm thử với target và around được thiết lập sẵn.
RuntimeException original = new IllegalArgumentException("bad input");

try {
    around("check", () -> {
        throw original;
    }, brokenLogger);
    throw new AssertionError("Expected business failure");
} catch (RuntimeException actual) {
    if (actual != original) {
        throw new AssertionError("Logging changed business exception", actual);
    }
}
~~~

Đoạn này là **mảnh kiểm thử minh họa**, cần các biến/method tương ứng từ ứng dụng hoặc từ chương trình ở phần 5. Để test đầy đủ, cũng cần bảo đảm target được gọi đúng một lần và mọi side effect của nó không bị lặp.

### 12.2. Kiểm tra lỗi completion và logging callback

Với CompletableFuture, hoàn tất source bằng một exception đã tạo trước; quan sát dependent stage và kiểm tra exception có cause là lỗi gốc, thay vì thông điệp lỗi logger. Đừng chỉ assert advice đồng bộ trả stage thành công; phải quan sát **terminal state**.

Với callback/error channel của một API khác, cần tiêm lỗi vào từng callback và kiểm tra dispatch contract cụ thể. Với stream, kiểm tra cả onError/onComplete/cancel và việc không phát thêm tín hiệu. Trường hợp callback thực thi ngay khi đăng ký cũng cần được kiểm chứng.

### 12.3. Kiểm tra overload và khả năng quan sát sự cố logger

Dùng fake sink có thể chặn, từ chối hoặc ném lỗi theo kịch bản để đo overhead, số event được drop và trạng thái degraded. Không mặc định best effort nghĩa là mọi thất bại đều phải có thêm một dòng log mới; nếu toàn bộ pipeline ghi log đang sập, health signal hoặc counter riêng có thể thực tế hơn.

## 13. Quy trình áp dụng tại join point

Khi thêm một logging aspect vào hệ thống, có thể làm theo trình tự:

1. **Phân loại bản ghi:** debug, telemetry, operational, audit bắt buộc hay event dữ liệu nghiệp vụ? Nếu khác độ tin cậy, không gom vào chung một chính sách.
2. **Xác định join point:** invocation return/throw, completion stage, callback, task execution, subscription lifecycle. Gắn đúng nơi có tín hiệu thực.
3. **Viết contract bảo toàn outcome:** nêu rõ return value, exception, future completion, cancellation, side effects và time budget phải giữ thế nào.
4. **Đặt logging trong vùng xử lý lỗi riêng:** khoanh thao tác sink và chuẩn bị dữ liệu event. Không nuốt nhầm lỗi target.
5. **Thiết kế failure policy:** fail-open, fail-closed ở trước điểm commit, buffered/durable, fallback hoặc degraded mode; ghi rõ quyết định và giới hạn.
6. **Xem xét reentrancy, context và redaction:** tránh aspect gọi chính mình, quản lý trace context qua callback, lọc thông tin nhạy cảm.
7. **Tiêm lỗi để kiểm tra:** before, after, catch, finally, completion callback, task wrapper, sink block, queue full, audit store unavailable và khôi phục sau lỗi.
8. **Theo dõi vận hành:** tỷ lệ mất log, queue depth, thời gian ghi, logger degraded và đối soát audit nếu liên quan.

### Quy tắc lựa chọn nhanh

- **Chỉ ghi log chẩn đoán** → ưu tiên best effort, không làm đổi outcome nghiệp vụ khi sink ném lỗi thuộc phạm vi đã định.
- **Log gắn với kết quả bất đồng bộ** → bổ sung hook completion/callback/task/stream phù hợp và cô lập lỗi log tại chính hook đó.
- **Audit là điều kiện bắt buộc để thao tác được phép diễn ra** → thiết kế bước bảo đảm audit trước hành động hoặc transaction/outbox có bảo đảm; từ chối minh bạch nếu chưa đạt điều kiện.
- **Không chấp nhận mất dữ liệu nghiệp vụ** → coi record đó là phần của luồng giao dịch nghiệp vụ, không dựa vào một logger best effort.
- **Yêu cầu latency nghiêm ngặt** → ngoài catch exception còn phải giới hạn thời gian, kích thước queue và backpressure.

## 14. Câu hỏi tự đánh giá

**1. Một phương thức đã ghi dữ liệu thành công, nhưng lệnh ghi log ở finally ném exception. Caller sẽ thấy gì nếu không cô lập lỗi logger?**

Caller có thể thấy exception từ logger, trong khi side effect nghiệp vụ đã xảy ra. Điều này dễ khiến caller retry nhầm và sinh thay đổi trùng lặp. Với best effort, bọc riêng logging để return hoặc business exception được giữ nguyên.

**2. Một target ném IllegalArgumentException, advice cố log lỗi nhưng logger cũng ném IllegalStateException. Ngoại lệ nào phải đến caller trong chính sách best effort?**

IllegalArgumentException từ target. Advice phải catch lỗi logger ở vùng riêng rồi ném lại **chính business exception**, không thay bằng lỗi logger hoặc fallback.

**3. Future hoàn tất thành công nhưng whenComplete observer ném lỗi logging. Hệ quả có thể là gì?**

Stage phụ thuộc do whenComplete tạo ra có thể hoàn tất exceptional dù source thành công. Cần cô lập lỗi logger trong callback observer, đồng thời hiểu rằng attach observer có thể thay đổi identity và một số đặc tính của stage được trả.

**4. Một thao tác chuyển tiền yêu cầu lưu audit bắt buộc. Có nên cứ bỏ qua khi audit store hỏng không?**

Không nếu hợp đồng bắt buộc lưu audit để thao tác hợp lệ. Cần cơ chế bền vững/transactional hoặc điều kiện từ chối trước hành động với thông báo rõ ràng; không để một log sau side effect ném lỗi tùy tiện vì như vậy có thể khiến caller hiểu nhầm rằng chuyển tiền chưa diễn ra.

**5. Bắt RuntimeException quanh cả target và logger rồi trả fallback có giúp cô lập lỗi logging không?**

Không. Catch đó nuốt cả lỗi target và đổi kết quả nghiệp vụ. Ranh giới bắt lỗi logger phải tách biệt với ranh giới bắt lỗi nghiệp vụ.

**6. Đã catch exception logger, vì sao vẫn có thể gây sự cố?**

Logger có thể block, queue đầy, phát sinh recursion ở fallback, dùng quá nhiều bộ nhớ hoặc làm rò dữ liệu. Chỉ bắt exception chưa đủ; cần chính sách về thời gian, dung lượng, retry, fallback, context và dữ liệu.

## Kết luận kiến thức

Logging aspect tốt giúp quan sát rõ hệ thống mà **không vô tình quyết định kết quả nghiệp vụ**. Với log best effort, hãy cô lập những lỗi ghi log có thể xử lý tại chính nơi phát sinh, kể cả before, after, catch, finally và completion/callback; giữ nguyên giá trị trả về, ngoại lệ gốc, trạng thái tương lai và số lần thực hiện tác dụng phụ. Với audit bắt buộc, hãy diễn đạt rõ quy tắc từ chối hoặc lưu bền vững và triển khai ở ranh giới nghiệp vụ phù hợp. Nguyên tắc xuyên suốt là: **mỗi loại bản ghi có một chính sách đáng tin cậy, và lỗi của cơ chế quan sát chỉ được phép ảnh hưởng nghiệp vụ theo chính sách đó**.