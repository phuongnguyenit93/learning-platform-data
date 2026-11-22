# get ném ExecutionException, join thường ném CompletionException

## 1. Vấn đề: cùng một CompletableFuture nhưng có nhiều cách nhận lỗi

**CompletableFuture<T>** có thể hoàn tất theo một trong các kết quả chính: thành công với một giá trị, hoàn tất bất thường với exception, hoặc bị hủy. Hai phương thức phổ biến để chờ và lấy kết quả là **get()** và **join()**. Khi CompletableFuture hoàn tất thành công, chúng đều trả về giá trị kiểu T. Khi CompletableFuture hoàn tất bất thường, **cách chúng báo lỗi khác nhau**.

- **get()** kế thừa hợp đồng của **Future**: đối với lỗi tác vụ thông thường, nó ném **ExecutionException**, một **checked exception**, và đặt lỗi gốc vào **getCause()**.
- **join()** có hợp đồng thuận tiện hơn cho pipeline: đối với lỗi tác vụ thông thường, nó ném **CompletionException**, một **unchecked exception**, với nguyên nhân trong **getCause()**.
- Hai câu trên là **quy tắc thường gặp**, không phải quy tắc áp dụng bất kể trạng thái. Với một CompletableFuture **đã hủy**, **get()** và **join()** đều có thể ném trực tiếp **CancellationException**. **get()** còn có thể ném **InterruptedException** nếu thread đang chờ bị ngắt; **get(timeout, unit)** có thể ném trực tiếp **TimeoutException** khi quá hạn chờ.

Điều thiết yếu là phân biệt **lỗi gốc của công việc** với **lớp exception dùng để truyền kết quả lỗi tới consumer**. Nếu tác vụ bất đồng bộ thất bại vì **IllegalStateException("storage unavailable")**, consumer gọi get thường bắt ExecutionException nhưng nguyên nhân cần xử lý là IllegalStateException trong cause. Cùng tác vụ đó, consumer gọi join thường bắt CompletionException, và cause vẫn là IllegalStateException.

Chọn get hay join là lựa chọn về **hợp đồng API và kiểm soát việc chờ**, không làm thay đổi bản chất tác vụ đã thất bại. Khi lập trình Java Core, hiểu cách wrap và unwrap exception giúp không mất nguyên nhân lỗi, không retry nhầm cancellation và không nuốt tín hiệu ngắt.

## 2. Các class exception và hợp đồng API

Trong Java 17, các kiểu liên quan đều thuộc package **java.util.concurrent**:

| Kiểu exception | Checked hay unchecked? | Vai trò điển hình |
| --- | --- | --- |
| **ExecutionException** | Checked; kế thừa **Exception** | Lỗi thực thi được báo qua **Future.get()**; lỗi thực sự thường ở cause |
| **CompletionException** | Unchecked; kế thừa **RuntimeException** | Lỗi hoàn tất bất thường được báo qua **CompletableFuture.join()** hoặc pipeline CompletionStage |
| **CancellationException** | Unchecked; kế thừa **IllegalStateException** | Future đã bị hủy; không phải mọi đường đều bọc qua ExecutionException/CompletionException |
| **InterruptedException** | Checked; thuộc **java.lang** | Thread caller bị interrupt trong khi chờ bằng API interruptible, như get() |
| **TimeoutException** | Checked | **get(timeout, unit)** không lấy được kết quả trong thời gian đã cho |

Chữ ký thường dùng, viết dưới dạng mô tả API:

~~~java
// Chữ ký minh họa; đây là các phương thức của CompletableFuture<T>.
T get() throws InterruptedException, ExecutionException;

T get(long timeout, TimeUnit unit)
    throws InterruptedException, ExecutionException, TimeoutException;

T join();
~~~

Dù chữ ký **join()** không khai báo checked exceptions, phương thức vẫn có thể ném **CompletionException** hoặc **CancellationException** lúc runtime. Không thấy **throws** trên chữ ký không đồng nghĩa tác vụ không thể thất bại.

**ExecutionException** và **CompletionException** là *wrapper* thường dùng để phân biệt tầng lấy kết quả với lỗi xảy ra bên trong task. Chúng không có nghĩa rằng lỗi gốc đã biến mất; caller cần truy xuất và bảo tồn cause.

## 3. Hai phương thức nhận một kết quả thành công giống nhau

Với CompletableFuture đã thành công:

~~~java
// Minh họa độc lập về biểu thức, đặt trong phương thức Java.
CompletableFuture<String> future =
        CompletableFuture.completedFuture("ready");

String fromGet = future.get();
String fromJoin = future.join();
~~~

Cả **fromGet** và **fromJoin** đều bằng **"ready"**. Khác biệt biểu lộ rõ khi kết quả chưa sẵn sàng hoặc hoàn tất bất thường:

- **get()** có thể bị ngắt trong khi chờ, nên caller phải xử lý hoặc khai báo InterruptedException.
- **join()** không khai báo InterruptedException như get; nó không trở về theo một nhánh checked-interruption tương đương.
- **get()** yêu cầu xử lý ExecutionException theo cơ chế checked exception.
- **join()** để CompletionException lan qua cơ chế unchecked exception; cách này thuận tiện trong method/lambda không khai báo checked exception, nhưng vẫn phải có chiến lược báo lỗi ở ranh giới phù hợp.

Đừng lựa chọn join chỉ để “tránh viết catch” nếu ứng dụng thực sự cần chính sách hủy, deadline hoặc xử lý nguyên nhân lỗi. Ngược lại, không nhất thiết catch ExecutionException ở mọi tầng khi có thể để hợp đồng get được chuyển đến nơi có trách nhiệm.

## 4. Ví dụ Java 17+ hoàn chỉnh: kiểm chứng lớp wrapper và cause

Chương trình dưới đây tạo bốn tình huống **không phụ thuộc scheduler**: Future thành công, Future hoàn tất bất thường bằng một instance IllegalStateException có sẵn, Future bị hủy, và một lần gọi get có timeout trên Future chưa hoàn tất.

Lưu nội dung sau thành tệp **GetJoinExceptionsDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class GetJoinExceptionsDemo {
    static void describe(Throwable failure) {
        Throwable cause = failure.getCause();
        System.out.println(failure.getClass().getSimpleName()
                + " | cause=" + (cause == null ? "none"
                        : cause.getClass().getSimpleName() + ": " + cause.getMessage()));
    }

    public static void main(String[] args) throws InterruptedException {
        CompletableFuture<String> success =
                CompletableFuture.completedFuture("ready");
        System.out.println("success get=" + readGet(success));
        System.out.println("success join=" + success.join());

        IllegalStateException original =
                new IllegalStateException("storage unavailable");
        CompletableFuture<String> failed = new CompletableFuture<>();
        failed.completeExceptionally(original);

        try {
            failed.get();
        } catch (ExecutionException failure) {
            describe(failure);
            System.out.println("get keeps original cause=" + (failure.getCause() == original));
        }
        try {
            failed.join();
        } catch (CompletionException failure) {
            describe(failure);
            System.out.println("join keeps original cause=" + (failure.getCause() == original));
        }

        CompletableFuture<String> canceled = new CompletableFuture<>();
        canceled.cancel(false);
        try {
            canceled.get();
        } catch (ExecutionException failure) {
            describe(failure);
        } catch (CancellationException failure) {
            System.out.println("canceled get=" + failure.getClass().getSimpleName());
        }
        try {
            canceled.join();
        } catch (CancellationException failure) {
            System.out.println("canceled join=" + failure.getClass().getSimpleName());
        }

        CompletableFuture<String> waiting = new CompletableFuture<>();
        try {
            waiting.get(1, TimeUnit.MILLISECONDS);
        } catch (ExecutionException failure) {
            describe(failure);
        } catch (TimeoutException failure) {
            System.out.println("timed get=" + failure.getClass().getSimpleName());
        }
        waiting.complete("later");
        System.out.println("later join=" + waiting.join());

        CompletableFuture<String> downstream =
                failed.exceptionally(failure -> "fallback");
        System.out.println("recovered=" + downstream.join());
        System.out.println("original failed=" + failed.isCompletedExceptionally());
    }

    static String readGet(CompletableFuture<String> future)
            throws InterruptedException {
        try {
            return future.get();
        } catch (ExecutionException failure) {
            throw new AssertionError("Unexpected failure", failure);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 GetJoinExceptionsDemo.java
java GetJoinExceptionsDemo
~~~

Stdout đã kiểm tra trực tiếp khi chạy chương trình:

~~~text
success get=ready
success join=ready
ExecutionException | cause=IllegalStateException: storage unavailable
get keeps original cause=true
CompletionException | cause=IllegalStateException: storage unavailable
join keeps original cause=true
canceled get=CancellationException
canceled join=CancellationException
timed get=TimeoutException
later join=later
recovered=fallback
original failed=true
~~~

### Vì sao output như vậy?

**Lỗi gốc** được tạo đúng một lần:

~~~java
IllegalStateException original =
        new IllegalStateException("storage unavailable");
CompletableFuture<String> failed = new CompletableFuture<>();
failed.completeExceptionally(original);
~~~

Đây là đoạn trích từ chương trình đầy đủ. **completeExceptionally(original)** chuyển trạng thái Future sang hoàn tất bất thường với Throwable đã cung cấp. Nó không có nghĩa thân một Callable vừa ném lỗi; nó là cách chủ động hoàn tất một CompletableFuture bằng exception.

Khi consumer gọi **failed.get()**, wrapper được quan sát là ExecutionException và **getCause() == original** bằng true. Gọi **failed.join()** trên chính Future đó tạo đường báo lỗi qua CompletionException, nhưng **getCause() == original** vẫn bằng true. Lỗi gốc không bị đổi loại hoặc thay message chỉ vì consumer chọn API khác.

Khi **cancel(false)** được gọi thành công trên Future chưa hoàn tất, cả get và join đều ném CancellationException trực tiếp. Đoạn code không khẳng định cancellation luôn có cùng dạng trên mọi dependent stage; một stage phụ thuộc có thể được hoàn tất bất thường với wrapper có cause là CancellationException.

Ở phần timeout, **waiting.get(1, MILLISECONDS)** hết hạn chờ vì không có thread hoặc code nào hoàn tất waiting trước đó. Sau khi bắt TimeoutException, chương trình gọi **waiting.complete("later")**, nên **waiting.join()** trả **later**. Timeout của lần chờ không tự cancel Future.

Cuối cùng, **failed.exceptionally(failure -> "fallback")** tạo một stage downstream hoàn tất bình thường bằng **fallback**, trong khi **failed.isCompletedExceptionally()** vẫn true. Recovery stage không biến trạng thái của upstream Future thành thành công.

## 5. ExecutionException: lỗi của tác vụ nằm trong cause

Khi **Future.get()** lấy kết quả từ một tác vụ hoàn tất bất thường vì lỗi thực thi thông thường, caller nhận **ExecutionException**. Ví dụ:

~~~java
// Mã minh họa theo ngữ cảnh; failed là CompletableFuture<String>.
try {
    String result = failed.get();
    use(result);
} catch (ExecutionException e) {
    Throwable original = e.getCause();
    handleTaskFailure(original);
}
~~~

Đoạn này là phần thân phương thức, cần khai báo thêm **InterruptedException** hoặc bắt nó, và **use/handleTaskFailure** là các hàm của ứng dụng; nó chưa phải chương trình chạy độc lập.

Những điều cần phân biệt:

1. **ExecutionException** mô tả việc không lấy được kết quả vì tác vụ đã hoàn tất bất thường.
2. **Cause** mô tả lỗi đã làm tác vụ thất bại, ví dụ IllegalArgumentException, IOException hoặc IllegalStateException.
3. **Stack trace** của wrapper thường liên quan đến điểm nhận kết quả, còn stack trace của cause cho biết nơi lỗi gốc phát sinh.
4. **isCompletedExceptionally()** cho biết Future hoàn tất bất thường, nhưng không thay thế việc phân loại nguyên nhân.
5. Nếu code wrap lại exception để đổi tầng trừu tượng, cần giữ cause để không làm mất lịch sử lỗi.

Ví dụ, một tầng service muốn báo lỗi với ngữ cảnh nghiệp vụ:

~~~java
// Minh họa phương thức có thể khai báo InterruptedException.
try {
    return future.get();
} catch (ExecutionException e) {
    throw new IllegalStateException("Could not load profile", e.getCause());
}
~~~

Ở đây wrapper nghiệp vụ giữ cause gốc, nhưng việc chọn **e.getCause()** hay **e** làm cause cần được cân nhắc theo nhu cầu chẩn đoán. Giữ **e** sẽ bảo toàn cả wrapper của Future và original bên dưới; dùng **e.getCause()** giúp wrapper nghiệp vụ trực tiếp trỏ đến lỗi tác vụ. Cả hai có thể hợp lý nếu không làm mất thông tin. Tuyệt đối tránh chỉ ném **new IllegalStateException(e.getMessage())** rồi bỏ cause.

## 6. CompletionException: cách báo lỗi unchecked của join

**CompletableFuture.join()** không bắt caller phải khai báo checked ExecutionException hoặc InterruptedException. Nếu Future hoàn tất bất thường vì một lỗi tác vụ thông thường, join ném **CompletionException** với lỗi gốc là cause.

~~~java
// Mã minh họa theo ngữ cảnh.
try {
    String result = future.join();
    use(result);
} catch (CompletionException e) {
    Throwable original = e.getCause();
    handleTaskFailure(original);
}
~~~

Đây là nhánh xử lý thích hợp khi thành phần gọi được phép làm việc với unchecked exception và không cần hợp đồng get có kiểm soát interruption. Nhưng không nên cho rằng **catch(CompletionException)** bao trùm mọi thất bại của join: khi Future bị canceled, **CancellationException** có thể được ném trực tiếp.

**CompletionException** thường xuất hiện trong pipeline **thenApply**, **thenCompose**, **thenCombine**, **handle** và những CompletionStage phụ thuộc. Một lambda trong thenApply có thể ném IllegalArgumentException; stage hoàn tất bất thường và khi join ở cuối pipeline, consumer nhận CompletionException có cause là lỗi từ lambda.

Ví dụ:

~~~java
// Đoạn minh họa có thể đặt trong một phương thức.
CompletableFuture<Integer> pipeline =
    CompletableFuture.completedFuture("not-a-number")
        .thenApply(Integer::parseInt);

try {
    pipeline.join();
} catch (CompletionException failure) {
    System.out.println(failure.getCause().getClass().getSimpleName());
}
~~~

Đoạn này in **NumberFormatException** khi chạy bình thường với Java 17, vì Integer.parseInt không chuyển được chuỗi đã cho. Điều cần rút ra là lỗi parse vẫn có thể được truy xuất qua **getCause()**, dù nó xuất hiện trong một stage rồi được nhận qua join.

Không dùng **CompletionException** như synonym của “lỗi task”; đó là kiểu wrapper do cơ chế completion truyền đi. Ứng dụng cần tìm đến cause thật sự và xem liệu stage trước đã wrap một exception khác hay chưa.

## 7. Khi Throwable vốn đã là CompletionException

Không phải mọi Future thất bại đều chứa exception gốc trực tiếp. Một phương thức có thể **completeExceptionally(new CompletionException(original))**, hoặc một stage phụ thuộc có thể nhận lại trạng thái lỗi đã được wrap.

Theo ngữ nghĩa của CompletableFuture, khi nhận kết quả từ một completion chứa **CompletionException** có cause, **get()** thường biểu diễn lỗi bằng **ExecutionException** với **cause là nguyên nhân được bọc**. **join()** thường truyền **CompletionException** đã có. Điều này giúp hai API duy trì hợp đồng báo lỗi của mình mà không bắt buộc tạo thêm lớp wrapper mới cho mỗi lần nhận kết quả.

Vì vậy, đường chẩn đoán có thể có nhiều tầng:

~~~text
Future thất bại
    |
    +-- get()  -> ExecutionException
    |              └── cause -> IllegalArgumentException
    |
    +-- join() -> CompletionException
                   └── cause -> IllegalArgumentException
~~~

Sơ đồ trên mô tả trường hợp điển hình. Với logic ứng dụng tự wrap nhiều tầng, chuỗi cause có thể sâu hơn. Không nên viết code mù quáng gọi **e.getCause().getCause()** và mặc định tầng thứ hai luôn tồn tại; **getCause()** có thể trả null ở một exception tự tạo không có cause.

Nếu cần tìm nguyên nhân cuối trong hệ thống của mình, có thể viết một hàm unwrap có giới hạn cho những wrapper được biết trước. Đừng xóa mọi wrapper bất kể loại, vì mỗi wrapper có thể mang ngữ cảnh, suppressed exceptions hoặc stack trace hữu ích.

## 8. Ngoại lệ quan trọng: CancellationException

**CancellationException** là unchecked exception. Với một **CompletableFuture bị hủy trực tiếp** bằng **cancel(...)**, cả **get()** lẫn **join()** đều có thể ném trực tiếp CancellationException. Nếu chỉ catch ExecutionException hoặc CompletionException, ứng dụng sẽ bỏ sót đường cancellation.

~~~java
// Mã minh họa:
CompletableFuture<String> canceled = new CompletableFuture<>();
boolean accepted = canceled.cancel(true);
System.out.println(accepted);
System.out.println(canceled.isCancelled());
~~~

Nếu cancel thắng cuộc đua trước khi Future hoàn tất, **accepted** và **isCancelled()** đều true. Sau đó **get()** và **join()** ném CancellationException.

Phải phân biệt cancellation của Future với việc worker đã ngừng thực thi. Với CompletableFuture, tham số **mayInterruptIfRunning** của **cancel(boolean)** không được sử dụng để điều khiển interruption của computation tương tự FutureTask. Nếu computation chạy qua **supplyAsync**, việc Future bị canceled không bảo đảm supplier đang chạy đã bị interrupt hoặc ngừng side effect.

Một stage **phụ thuộc** vào Future bị hủy có thể có dạng lỗi khác:

~~~java
// Minh họa; không cần chạy độc lập.
CompletableFuture<String> root = new CompletableFuture<>();
CompletableFuture<Integer> dependent = root.thenApply(String::length);
root.cancel(false);
// dependent có thể hoàn tất bất thường với CompletionException
// có cause là CancellationException, thay vì chính dependent bị canceled.
~~~

Do đó, khi muốn xác định policy cancellation, hãy kiểm tra **isCancelled()** của đúng Future và phân tích chuỗi cause ở stage phụ thuộc. Không sử dụng một catch CancellationException duy nhất như bảo đảm mọi dạng lan truyền hủy đều đã được xử lý.

Nếu task đã có side effect trước khi bị canceled, không được suy ra mọi tác dụng phụ đã rollback. Đây là lý do quan trọng để gắn chính sách cancellation với quyền sở hữu task và trạng thái nghiệp vụ.

## 9. Ngoại lệ riêng của get: InterruptedException

**CompletableFuture.get()** có thể ném InterruptedException khi **thread gọi get** bị interrupt trong lúc chờ. Đây là tín hiệu dành cho caller đang chờ, **không tự chứng minh** supplier hoặc worker chạy Future đó đã bị hủy.

Ví dụ chính sách lan truyền khi chữ ký cho phép:

~~~java
// Minh họa phương thức.
static String waitFor(CompletableFuture<String> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
~~~

Ở đây hợp đồng method đã cho phép đưa InterruptedException lên tầng gọi. Không cần catch nó ở tầng trung gian rồi bỏ qua, vì như vậy yêu cầu ngắt có thể bị mất.

Nếu không thể khai báo checked exception, ví dụ trong **Runnable.run()**, một chính sách thường dùng là khôi phục cờ interrupt và kết thúc:

~~~java
// Minh họa trong Runnable hoặc callback không khai báo throws.
try {
    future.get();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException failure) {
    handleTaskFailure(failure.getCause());
}
~~~

Đoạn code này theo ngữ cảnh; **handleTaskFailure** do ứng dụng định nghĩa và **return** giả định đang ở trong một phương thức void phù hợp. Không nên nuốt InterruptedException và tiếp tục chờ vô hạn.

**join()** không khai báo InterruptedException. Khi chờ, join không dùng đường ném checked InterruptedException giống get; tình trạng interrupt của thread cần được xử lý theo hợp đồng JDK và chính sách ứng dụng. Nếu ứng dụng cần đáp ứng cancellation của *caller* một cách rõ ràng, get hoặc một API chờ interruptible là lựa chọn phù hợp hơn.

Ngoài ra, khi **Callable** của worker tự ném InterruptedException và Future hoàn tất bất thường với lỗi đó, **get()** của caller thường nhận ExecutionException **có cause là InterruptedException**. Đừng nhầm trường hợp này với việc chính caller bị interrupt và get ném InterruptedException trực tiếp.

## 10. Ngoại lệ riêng của get(timeout): TimeoutException

**get(timeout, unit)** thêm đường thất bại khi **lần chờ** vượt thời lượng:

~~~java
// Ví dụ minh họa theo ngữ cảnh.
try {
    return future.get(200, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    // Chưa nhận kết quả trong deadline chờ này.
    throw e;
}
~~~

Khi hết thời gian, **TimeoutException** được ném trực tiếp; nó không được bọc trong ExecutionException, vì đó không phải lỗi của task đã hoàn tất bất thường. Đây là lỗi/điều kiện của **lượt chờ**.

Timeout không tự chuyển CompletableFuture sang canceled. Trong ví dụ chạy được, sau khi **waiting.get(1, MILLISECONDS)** timeout, lời gọi **waiting.complete("later")** vẫn thành công và **waiting.join()** trả kết quả.

Cần phân biệt với **CompletableFuture.orTimeout(timeout, unit)**:

- **future.get(timeout, unit)**: caller ngừng chờ khi hết thời gian; Future có thể còn chưa hoàn tất.
- **future.orTimeout(timeout, unit)**: nếu Future chưa hoàn tất khi hết hạn, phương thức làm **chính Future đó** hoàn tất bất thường với một TimeoutException.
- Sau **orTimeout** thực sự kích hoạt, **future.get()** thường ném ExecutionException **có cause là TimeoutException**, còn **future.join()** thường ném CompletionException **có cause là TimeoutException**.
- **future.completeOnTimeout(fallback, timeout, unit)** có thể hoàn tất Future bình thường với fallback nếu đến hạn mà Future vẫn chưa xong.

Nói cách khác, TimeoutException có thể là **exception trực tiếp của get(timeout)** hoặc là **nguyên nhân của một exceptional completion** được quan sát bằng get/join. Nếu dùng chung một catch TimeoutException cho mọi trường hợp, code có thể bỏ sót đường bọc ở cause.

Không mặc định rằng orTimeout hoặc completeOnTimeout ngắt supplier hoặc rollback tác vụ đang chạy. Chúng quyết định trạng thái completion của CompletableFuture; phần thực thi bên dưới có thể tiếp tục làm việc.

## 11. isDone và isCompletedExceptionally không xác định được nguyên nhân

Các phương thức trạng thái giúp quan sát, nhưng không thay thế việc đọc kết quả và phân loại Throwable:

- **isDone()** true khi Future đã hoàn tất, kể cả hoàn tất bất thường hoặc canceled.
- **isCompletedExceptionally()** true nếu CompletableFuture đã hoàn tất bất thường, bao gồm cancellation.
- **isCancelled()** true nếu Future đó bị canceled theo trạng thái hủy của nó.
- **get()** hoặc **join()** cho biết kết quả thành công hoặc truyền lỗi để consumer xử lý.

Một phương thức chỉ kiểm tra:

~~~java
// Phản mẫu minh họa.
if (future.isDone()) {
    markSuccess();
}
~~~

là sai nếu **markSuccess** có nghĩa tác vụ chắc chắn thành công. Future có thể isDone sau khi completeExceptionally hoặc cancel.

Cũng không được kết luận **isCompletedExceptionally()** true nghĩa là một task đã ném exception trong body. Code có thể chủ động gọi **completeExceptionally(...)**, **obtrudeException(...)**, hoặc một timeout policy hoàn tất Future bất thường.

Nếu cần kiểm tra kết quả không blocking, có thể xem các API khác như **getNow(valueIfAbsent)**, nhưng getNow cũng có thể ném khi Future đã hoàn tất bất thường. Chọn phương pháp quan sát dựa trên trạng thái và hợp đồng yêu cầu, không chỉ dựa vào tên phương thức.

## 12. Chuỗi CompletionStage: lỗi từ đâu đến?

Xét một pipeline xử lý:

~~~java
// Mã minh họa có thể đặt trong một phương thức.
CompletableFuture<Integer> pipeline =
    CompletableFuture.completedFuture("42")
        .thenApply(String::trim)
        .thenApply(Integer::parseInt)
        .thenApply(value -> value * 2);
int result = pipeline.join(); // 84
~~~

Khi mọi stage thành công, join trả 84. Nếu chuỗi đầu vào không thể parse, stage **Integer::parseInt** làm pipeline hoàn tất bất thường. Stage ở sau bình thường không chạy biến đổi giá trị nữa, và consumer ở cuối nhận một CompletionException. Cause sẽ giúp tìm lỗi parse thật.

Lỗi có thể phát sinh ở:

1. Nhà cung cấp dữ liệu ban đầu, ví dụ supplier của **supplyAsync**.
2. Hàm biến đổi **thenApply**.
3. Hàm phụ thuộc bất đồng bộ như **thenCompose**.
4. Callback quan sát **whenComplete** tự ném exception.
5. Chính sách thời hạn **orTimeout**.
6. Hủy stage/root Future.
7. Code chủ động gọi **completeExceptionally(...)**.

Do đó, khi thấy CompletionException tại **join()**, không nên kết luận chính phương thức join có bug hay stage cuối cùng là nguồn lỗi. Hãy đi theo cause và ngữ cảnh của pipeline để xác định stage nào thực sự thất bại.

### Nhánh phục hồi exceptionally

**exceptionally(Function<Throwable, ? extends T>)** tạo một stage có thể chuyển kết quả bất thường của upstream thành giá trị fallback. Ví dụ:

~~~java
CompletableFuture<String> source =
        CompletableFuture.failedFuture(
                new IllegalStateException("remote unavailable"));
CompletableFuture<String> recovered =
        source.exceptionally(failure -> "cached value");
System.out.println(recovered.join());
~~~

Đoạn này in **cached value**. **recovered** hoàn tất bình thường nếu hàm recovery trả về fallback; **source** vẫn hoàn tất bất thường. Recovery trên downstream không làm thay đổi ngược trạng thái upstream.

Nếu lambda của exceptionally ném exception mới, recovered cũng có thể hoàn tất bất thường. Không nên nuốt mọi exception bằng một fallback mặc định nếu lỗi có ý nghĩa bảo mật, tính toàn vẹn dữ liệu hay yêu cầu nghiệp vụ không cho phép tiếp tục.

### Nhánh handle

**handle((value, failure) -> ...)** được gọi khi upstream thành công hoặc thất bại và có thể chuyển đổi kết quả thành một giá trị mới. Khi **failure** khác null, ứng dụng cần phân biệt lỗi có thể recovery với cancellation hoặc lỗi nghiêm trọng. Việc có callback handle không có nghĩa mọi lỗi phải được chuyển thành thành công.

### Nhánh whenComplete

**whenComplete((value, failure) -> ...)** thường dùng để quan sát side effect như metrics/logging. Nó không tự chuyển kết quả lỗi thành giá trị bình thường. Nếu callback tự ném lỗi, cần hiểu cách exception của callback ảnh hưởng stage trả về; tránh để logging/cleanup tạo một kết quả lỗi mới ngoài ý muốn.

## 13. Cách viết xử lý kết quả bằng get()

Với tầng service được phép khai báo checked exceptions, có thể dùng get và để caller quyết định:

~~~java
// Mã minh họa trong một class.
static <T> T await(CompletableFuture<T> future)
        throws InterruptedException, ExecutionException {
    return future.get();
}
~~~

Lợi ích: chữ ký thể hiện rõ rằng caller có thể bị ngắt hoặc nhận lỗi task qua ExecutionException. Nếu caller cần deadline, thêm biến thể dùng **get(timeout, unit)** và khai báo TimeoutException.

Khi thật sự cần chuyển lỗi sang domain exception, hãy đọc cause cẩn thận:

~~~java
// Mã minh họa theo ngữ cảnh.
try {
    return future.get();
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    throw new IllegalStateException("Async operation failed",
                                    cause == null ? e : cause);
}
~~~

Cần xử lý **InterruptedException** theo hợp đồng của method chứa đoạn code. Nếu có thể lan truyền checked exception, để nó đi lên thường tốt hơn là nuốt rồi tiếp tục. Nếu không thể, khôi phục interrupt flag và áp dụng chính sách dừng.

Đừng bắt **Exception** chung rồi coi mọi nhánh là lỗi của task: điều đó trộn **InterruptedException**, **ExecutionException** và có thể cả **CancellationException** vào cùng một loại lỗi nghiệp vụ.

## 14. Cách viết xử lý kết quả bằng join()

**join()** phù hợp khi code dùng pipeline đồng bộ ở điểm kết thúc, khi giao diện không khai báo checked exceptions, hoặc khi caller đã có ranh giới chung xử lý lỗi unchecked.

~~~java
// Mã minh họa trong một class.
static <T> T joinResult(CompletableFuture<T> future) {
    try {
        return future.join();
    } catch (CancellationException canceled) {
        throw canceled;
    } catch (CompletionException failed) {
        throw failed;
    }
}
~~~

Đoạn này chỉ cho thấy hai loại lỗi cần phân biệt; trong thực tế nếu chỉ ném lại cả hai như vậy, các catch đều có thể bỏ đi. Khi cần thêm ngữ cảnh nghiệp vụ, có thể wrap nhưng giữ **failed** hoặc **failed.getCause()** đúng theo hợp đồng API.

Ví dụ thiết kế handling:

~~~java
// Mã minh họa theo ngữ cảnh.
try {
    return future.join();
} catch (CancellationException canceled) {
    recordCancellation(canceled);
    throw canceled;
} catch (CompletionException failed) {
    Throwable cause = failed.getCause();
    recordFailure(cause == null ? failed : cause);
    throw failed;
}
~~~

**recordCancellation** và **recordFailure** là các hàm ứng dụng; đoạn trên không chạy độc lập. Điểm quan trọng: cancellation có thể cần chính sách riêng thay vì bị ghi nhận như lỗi tác vụ bình thường.

Một lỗi khác là viết **catch (CompletionException e) { return null; }** để làm im lặng mọi exception. Nếu null không biểu diễn kết quả hợp lệ, code phía sau có thể ném NullPointerException và che mất nguồn lỗi thực sự. Nếu cần fallback, hãy xác định rõ nó có thể được dùng cho loại exception nào, cân nhắc **exceptionally** hoặc **handle** với ý nghĩa nhất quán.

## 15. Khi nào dùng get và khi nào dùng join?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| API đã khai báo **InterruptedException/ExecutionException** | **get()** | Giữ hợp đồng checked và khả năng phản ứng khi caller bị ngắt |
| Cần giới hạn thời gian đợi một kết quả | **get(timeout, unit)** | TimeoutException trực tiếp theo lượt chờ |
| Điểm kết thúc của CompletionStage pipeline không muốn khai báo checked exceptions | **join()** | CompletionException là unchecked; tiện tích hợp nhưng vẫn phải xử lý lỗi |
| Muốn nhận một fallback khi pipeline thất bại | **exceptionally/handle** rồi get/join | Recovery ở stage riêng với chính sách rõ |
| Nhiều kết quả cần chờ sau allOf | **allOf(...).join()** thường được dùng | Chờ tất cả rồi xem trạng thái từng phần; lỗi vẫn cần phân loại |
| Hỗ trợ cancellation từ thread caller theo hợp đồng interruptible | **get()** hoặc API interruptible phù hợp | join không cung cấp cùng đường checked InterruptedException |
| Không muốn blocking trên request thread | Sử dụng pipeline bất đồng bộ | Cả get và join đều có thể block; cân nhắc kiến trúc async |

Không có quy tắc rằng **join() luôn tốt hơn get()** hay ngược lại. Chọn API theo boundary, cách báo lỗi, khả năng hủy/chờ và loại đối tượng caller phải phục vụ.

Đặc biệt, **get()** là cách chờ có khả năng báo interrupted caller trực tiếp; **join()** không phải phép chờ với timeout tích hợp. Nếu muốn timeout ở CompletableFuture mà không thay trạng thái Future, dùng **get(timeout)** chứ không gọi **orTimeout** một cách vô thức.

## 16. Tính chất blocking và nguy cơ deadlock

**get()** và **join()** đều có thể chặn thread gọi khi Future chưa hoàn tất. Trong thread pool nhỏ, một task đang chạy ở executor mà lại gọi **join()** để đợi một task khác đã được submit vào **cùng executor** có thể tạo tình huống thiếu worker hoặc deadlock.

Ví dụ tư duy: executor chỉ có một worker; task A đang chạy chiếm worker, task A đợi Future của task B bằng join, nhưng B đang nằm trong hàng đợi của chính executor. Nếu không có thread khác xử lý B, A có thể chờ mãi.

Lựa chọn get hay join không tự giải quyết thiết kế này. Nên:

- Ghép các bước phụ thuộc bằng **thenCompose**, **thenApply**, **thenCombine** thay vì block bên trong worker khi có thể.
- Dùng executor phù hợp với số lượng tác vụ đồng thời và loại I/O.
- Không chờ vô hạn ở ranh giới có deadline.
- Theo dõi luồng, queue, thread dump và chẩn đoán độ trễ nếu có dấu hiệu starvation.

Một CompletionException phát sinh sau timeout hoặc lỗi task không chứng minh lỗi đến từ get/join; nguyên nhân có thể là deadlock, timeout policy hoặc stage xử lý trước.

## 17. Logging và bảo toàn thông tin lỗi gốc

Khi báo lỗi bất đồng bộ, logging nên giữ được Throwable đầy đủ:

~~~java
// Minh họa với một logger có API logger.error(String, Throwable).
try {
    future.join();
} catch (CompletionException failed) {
    logger.error("Asynchronous operation failed", failed);
    throw failed;
}
~~~

Nếu chỉ in **failed.getMessage()**, có thể không đủ ngữ cảnh của nguyên nhân. Một exception tree đầy đủ thể hiện cả wrapper, cause, stack trace và suppressed exceptions. Nếu tầng service wrap lại exception, cần truyền cause phù hợp.

Cũng tránh log trùng ở mỗi stage của pipeline và mỗi consumer. Có thể để tầng gần nguồn bổ sung context, còn ranh giới quan sát cuối ghi một log phù hợp. Với hệ thống dùng structured logging, xác nhận pipeline log có giữ dữ liệu **cause** và **suppressed** hay không.

Không nên đưa thông tin nhạy cảm từ exception trực tiếp ra API công khai. Có thể trả response mã lỗi chung cho client nhưng vẫn giữ đầy đủ chain lỗi trong logging nội bộ.

## 18. Kiểm thử chính xác kiểu exception và cause

Một bài test tốt không chỉ kiểm tra “có exception”, mà còn kiểm tra **đúng lớp wrapper và đúng nguyên nhân**.

Với một CompletableFuture đã completeExceptionally bằng một instance lỗi xác định:

1. Gọi **get()** và assert **ExecutionException**.
2. So sánh **getCause()** với đúng instance lỗi gốc; chỉ so message có thể bỏ sót việc tạo exception mới.
3. Gọi **join()** trên cùng Future và assert **CompletionException**.
4. Kiểm tra cause của join cũng là lỗi gốc.
5. Với Future canceled trực tiếp, xác minh cả get và join ném **CancellationException**.
6. Với Future chưa hoàn tất, **get(timeout)** ném **TimeoutException** và Future vẫn chưa bị cancel.
7. Cho Future hoàn tất sau timeout rồi assert **join()** trả kết quả.
8. Tạo stage **exceptionally** và xác minh fallback thành công không sửa trạng thái lỗi upstream.

Chương trình Java ở mục 4 đã minh họa những điểm này mà không dựa vào background scheduling; riêng **get(1, MILLISECONDS)** đợi trên Future chưa được hoàn tất nên nhánh timeout xác định được.

Bảng đối chiếu:

| Tình huống | get() | join() |
| --- | --- | --- |
| Future hoàn tất bình thường | Giá trị T | Giá trị T |
| Future hoàn tất bất thường với IllegalStateException | ExecutionException, cause IllegalStateException | CompletionException, cause IllegalStateException |
| Future bị canceled trực tiếp | CancellationException | CancellationException |
| Caller bị interrupt trong lúc chờ | InterruptedException trực tiếp | Không ném checked InterruptedException |
| Chờ quá hạn | **get(timeout)** ném TimeoutException | join không có overload timeout |
| Future được **orTimeout** hoàn tất bất thường | ExecutionException, cause TimeoutException | CompletionException, cause TimeoutException |

Với stage phụ thuộc của CompletableFuture đã bị hủy, lớp wrapper có thể khác việc gọi get/join trên Future gốc; cần kiểm tra đúng stage ở từng assertion.

### Kiểm thử với supplyAsync

Nếu dùng **supplyAsync**, bất đồng bộ thực sự có thể khiến test gặp race. Để ổn định:

- Dùng latch hoặc CompletableFuture đã complete để điều khiển thời điểm.
- Nếu muốn kiểm tra exception của stage, chủ động dùng **completeExceptionally** hoặc **failedFuture** với instance lỗi xác định.
- Với test integration, xác minh task thực sự kết thúc, executor được đóng khi thuộc quyền sở hữu của test.
- Không dùng sleep với thời lượng tùy ý như cơ chế đồng bộ duy nhất.

## 19. Những lỗi thường gặp

**Bắt CompletionException để xử lý get().** get thông thường ném **ExecutionException** cho exceptional completion; không nên viết handler sai lớp wrapper rồi mong bắt được mọi lỗi.

**Bắt ExecutionException để xử lý join().** join thường ném CompletionException, là unchecked. Chọn loại catch theo API thật sự gọi.

**Quên CancellationException.** Future bị canceled có thể khiến cả get và join ném CancellationException trực tiếp, bỏ qua catch ExecutionException/CompletionException.

**Nghĩ get và join tạo ra hai lỗi gốc khác nhau.** Lỗi task có thể là cùng một Throwable, được truyền qua các wrapper khác nhau. Đọc cause để phân loại.

**Catch Exception chung rồi nuốt InterruptedException.** Caller get có thể đang được yêu cầu dừng. Cần truyền lên hoặc khôi phục flag và kết thúc theo hợp đồng.

**Hiểu timeout là lỗi task.** get(timeout) hết hạn trực tiếp do caller chờ quá lâu, trong khi task vẫn có thể hoàn tất sau đó. Phân biệt với exceptional completion do orTimeout.

**Dùng isDone() làm cờ thành công.** isDone cũng đúng với canceled và exceptional completion.

**Unwrap cố định hai cấp getCause().** Cây exception có thể có số tầng khác nhau, hoặc cause null. Chỉ unwrap những wrapper đã biết và giữ đủ context.

**Cho rằng cancel CompletableFuture ngắt computation ngay.** Cancellation của future không tự bảo đảm supplier dừng hoặc hoàn tác side effect.

**Dùng join trong worker để đợi công việc cần chính worker ấy chạy.** Dễ tạo starvation/deadlock; cần thiết kế pipeline và executor phù hợp.

**Biến mọi lỗi thành fallback không phân loại.** Một giá trị mặc định có thể che khuất vi phạm bất biến, lỗi bảo mật hoặc kết quả chưa xác nhận. Recovery phải có chính sách cụ thể.

## 20. Bảng kiểm trước khi đưa vào ứng dụng

1. Future có thể hoàn tất theo những trạng thái nào: thành công, lỗi, canceled?
2. Ranh giới gọi muốn checked exception của get hay unchecked exception của join?
3. Caller cần phản ứng với interrupt và timeout theo hợp đồng riêng không?
4. Khi get thất bại, code có bắt ExecutionException và truy xuất cause?
5. Khi join thất bại, code có bắt CompletionException và phân biệt CancellationException?
6. Nếu API đã chuyển sang exceptional completion bằng orTimeout, có biết lỗi timeout nằm trong cause của wrapper không?
7. Có nơi nào xem isDone() đồng nghĩa thành công hoặc xem canceled đồng nghĩa worker đã dừng?
8. Pipeline có callback exceptionally/handle chuyển lỗi thành fallback một cách có chủ đích không?
9. Khi wrap exception, stack trace, cause và suppressed có còn được ghi nhận không?
10. Các test có xác minh đúng exception class, nguyên nhân gốc và đường timeout/cancellation không?

**Điểm cần nhớ:** **CompletableFuture.get()** thường báo exceptional completion bằng **ExecutionException** (checked), còn **CompletableFuture.join()** thường báo cùng lỗi bằng **CompletionException** (unchecked). Cả hai đều phải được đọc qua **getCause()** để hiểu nguyên nhân tác vụ. Hãy xử lý riêng **CancellationException**, **InterruptedException** và **TimeoutException**, vì chúng mô tả các điều kiện khác nhau và không tuân theo một quy tắc wrap duy nhất.
