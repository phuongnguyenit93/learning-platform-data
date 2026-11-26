# Chuyển ví dụ preview hoặc ngữ cảnh ThreadLocal phù hợp sang API ScopedValue chính thức

## 1. Mục tiêu và phiên bản áp dụng

Trong chương Scoped Value của module Java 22, mục tiêu của bài này là hiện đại hóa mã đang truyền ngữ cảnh bằng API preview hoặc bằng `ThreadLocal`. Kết quả cần đạt là một luồng truyền dữ liệu từ nơi tiếp nhận yêu cầu xuống các tầng xử lý, có phạm vi thực thi rõ ràng và dùng API chính thức.

`ScopedValue` còn là preview trong Java 22; API chính thức có từ Java 25. Bài sử dụng **Java 25 làm mức nền** cho mã đích. Tên API cũ chỉ xuất hiện để nhận diện điểm cần sửa, không phải mẫu triển khai mới. Trạng thái phiên bản có thể đối chiếu trong [API Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/ScopedValue.html) và [API Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html).

Sau bài học, người học có thể:

- Phân loại một ngữ cảnh `ThreadLocal` trước khi quyết định chuyển đổi.
- Thay lời gọi preview bằng `ScopedValue.where(...).run(...)` hoặc `call(...)`.
- Chuyển adapter `Supplier`, `Callable` và giữ đúng hợp đồng ngoại lệ.
- Xác định nơi bắt đầu, kết thúc, lồng phạm vi và chuyển luồng thực thi.
- Tách việc truyền ngữ cảnh khỏi quản lý tài nguyên, cập nhật trạng thái và tích hợp framework.

Kiến thức cần có: lambda, method reference, `try/finally`, checked exception và khái niệm thread/executor.

## 2. Chọn đúng ngữ cảnh để chuyển

Hãy mô tả dữ liệu theo hướng: **ai tạo dữ liệu, ai đọc dữ liệu, ai được thay đổi dữ liệu, và tác vụ nào quyết định vòng đời của nó**. Ví dụ: một tenant ID được xác định ở đầu yêu cầu, sau đó dịch vụ và repository chỉ đọc trong lúc xử lý yêu cầu.

Bảng dưới đây là hướng dẫn thiết kế cho quá trình chuyển đổi:

| Cách sử dụng hiện tại | Hướng xử lý đề xuất | Lý do |
|---|---|---|
| Tenant ID, request ID, locale dùng nhất quán trong một yêu cầu | Cân nhắc `ScopedValue` | Dữ liệu có chủ sở hữu và thời điểm kết thúc rõ ràng |
| Snapshot quyền truy cập đã được xác thực ở đầu tác vụ | Có thể dùng context bất biến | Các tầng dưới đọc cùng một snapshot |
| Các tầng dưới ghi kết quả vào `ThreadLocal` để tầng trên đọc lại | Trả kết quả qua kiểu dữ liệu hoặc đối tượng nghiệp vụ | Cần thiết kế lại chiều truyền dữ liệu |
| Cache hoặc bộ đệm được tái sử dụng theo tuổi thọ thread | Đánh giá riêng | Vòng đời cache có thể không trùng vòng đời tác vụ |
| `Connection`, transaction hoặc đối tượng có trạng thái thay đổi | Phân tích quyền sở hữu tài nguyên trước | Chỉ thay cách lưu tham chiếu không giải quyết commit, rollback hay close |
| Đối số nghiệp vụ cần cho một vài lời gọi | Ưu tiên tham số phương thức | Phụ thuộc được nhìn thấy trực tiếp trong chữ ký |
| Context do thư viện bên ngoài đọc qua `ThreadLocal` | Kiểm tra điểm tích hợp được thư viện hỗ trợ | Đổi context của ứng dụng chưa làm thư viện đọc nguồn mới |

Đây không phải kế hoạch loại bỏ mọi `ThreadLocal`. API này vẫn cung cấp biến có giá trị riêng cho từng thread, với các thao tác `get`, `set`, `remove` và khởi tạo giá trị. [Đặc tả ThreadLocal Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html).

Một ứng viên chuyển đổi tốt thường có ba đặc điểm:

1. Đầu tác vụ tạo hoặc nhận một context hoàn chỉnh.
2. Các tầng được gọi chỉ cần đọc context đó.
3. Có thể bao toàn bộ phần sử dụng context trong một lời gọi `run` hoặc `call`.

Nếu bước thứ ba chưa xác định được, hãy vẽ lại vòng đời tác vụ trước khi sửa API.

## 3. Phân biệt khóa, dữ liệu và phạm vi thực thi

Trong bài, **binding** nghĩa là việc gắn một giá trị với một khóa `ScopedValue` trong một phạm vi thực thi.

~~~java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();
~~~

`REQUEST_ID` là khóa dùng chung trong lớp, không phải một ô chứa request ID toàn cục. Khi đọc `REQUEST_ID.get()`, kết quả phụ thuộc binding đang có hiệu lực trên thread hiện tại. [Quy tắc binding của ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html#class-description).

Ví dụ khung:

~~~java
ScopedValue.where(REQUEST_ID, "req-101").run(() -> {
    // Các lời gọi đồng bộ bên dưới được thực hiện trong phạm vi này.
    System.out.println(REQUEST_ID.get());
});
~~~

Dùng mô hình sau khi rà soát một điểm chuyển đổi:

~~~text
Điểm tiếp nhận yêu cầu
  tạo RequestContext
  vào run/call
    controller -> service -> repository
                  đọc context hiện hành
  thoát run/call
Tiếp tục phần việc ngoài yêu cầu
~~~

Có hai cách đọc ví dụ cần tránh:

- Dấu ngoặc trong lambda không phải cơ chế truyền ngữ cảnh sang mọi công việc được tạo từ bên trong lambda.
- `static final` trên khóa không khiến mọi thread dùng chung một context.

Phạm vi cần chứa **việc thực thi phần xử lý**, không chỉ chứa việc tạo một callback để chạy sau.

## 4. Nhận diện và thay các lời gọi preview

### 4.1. Bảng chuyển API

Khi gặp mã Java 22, đối chiếu theo bảng sau. `K` là khóa, `v` là giá trị; các operation có chữ ký phù hợp với cột đích.

| Dấu vết trong mã preview | Dạng sử dụng API chính thức |
|---|---|
| `ScopedValue.runWhere(K, v, runnable)` | `ScopedValue.where(K, v).run(runnable)` |
| `ScopedValue.callWhere(K, v, () -> compute())` | `ScopedValue.where(K, v).call(() -> compute())` |
| `ScopedValue.getWhere(K, v, supplier)` | `ScopedValue.where(K, v).call(supplier::get)` |
| `ScopedValue.where(K, v).get(supplier)` | `ScopedValue.where(K, v).call(supplier::get)` |
| `ScopedValue.where(K, v).call(callable)` với biến kiểu `Callable` | `ScopedValue.where(K, v).call(callable::call)` |
| `ScopedValue.where(K, v).run(runnable)` | Giữ dạng lời gọi; vẫn phải kiểm tra vòng đời tác vụ |

Đối chiếu chữ ký lịch sử tại [ScopedValue Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/ScopedValue.html) và [Carrier Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/ScopedValue.Carrier.html); chữ ký đích nằm trong [Carrier Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html).

Tên `get` cần được phân biệt theo đối tượng nhận và kiểu đối số:

| Lời gọi | Vai trò |
|---|---|
| `REQUEST_ID.get()` | Đọc binding hiện hành |
| `carrier.get(REQUEST_ID)` | Đọc ánh xạ được lưu trong carrier |
| `carrier.get(supplier)` trong ví dụ preview | Chạy supplier trong phạm vi binding; cần chuyển sang `call(supplier::get)` |

`Carrier.get(ScopedValue)` vẫn có trong API chính thức. Không thay toàn bộ mọi lời gọi mang tên `get` chỉ dựa trên tên phương thức. [Các phương thức Carrier Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html#method-summary).

### 4.2. Supplier, Callable và CallableOp

Mẫu sau giả định đã có khóa `REQUEST_ID`:

~~~java
java.util.function.Supplier<String> supplier =
        () -> "request=" + REQUEST_ID.get();

String first = ScopedValue.where(REQUEST_ID, "req-101")
        .call(supplier::get);

java.util.concurrent.Callable<String> callable =
        () -> "request=" + REQUEST_ID.get();

String second = ScopedValue.where(REQUEST_ID, "req-102")
        .call(callable::call);
~~~

`call` nhận operation kiểu `ScopedValue.CallableOp<T, X>`. Lambda và method reference có thể được định kiểu theo interface đó; một biến đã có kiểu `Supplier` hay `Callable` cần được thích nghi bằng method reference như trên. Hợp đồng của `CallableOp.call()` trả về `T` và có thể ném `X`. [Đặc tả CallableOp](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.CallableOp.html).

Trong ví dụ, đoạn gọi `callable::call` phải khai báo hoặc xử lý `Exception` theo chữ ký của `Callable.call()`, dù thân lambda cụ thể không ném checked exception. [Hợp đồng Callable.call()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Callable.html#call()).

Với mã mới cần đọc tệp, có thể giữ loại ngoại lệ cụ thể:

~~~java
// Phương thức này nằm trong lớp đã khai báo REQUEST_ID.
static String loadTemplate(String requestId, java.nio.file.Path path)
        throws java.io.IOException {
    return ScopedValue.where(REQUEST_ID, requestId)
            .call(() -> java.nio.file.Files.readString(path));
}
~~~

Ở đây, compiler suy luận hợp đồng operation từ lambda gọi `Files.readString`. Chữ ký phương thức có thể giữ `IOException`; không cần đổi thành `throws Exception` chỉ vì chuyển sang `ScopedValue`. Đây là cách áp dụng tham số ngoại lệ `X` của [CallableOp](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.CallableOp.html).

## 5. Chuyển một request context từ ThreadLocal

### 5.1. Xác định hợp đồng đang có

Giả sử ứng dụng có record `RequestContext`, một phương thức `service()` và mã tại ranh giới ngoài cùng của yêu cầu:

~~~java
private static final ThreadLocal<RequestContext> CURRENT =
        new ThreadLocal<>();

static String handle(RequestContext context) {
    CURRENT.set(context);
    try {
        return service();
    } finally {
        CURRENT.remove();
    }
}
~~~

Trong trường hợp này, `handle` thiết lập context và `service` chỉ đọc. Chọn chuyển đổi dựa trên hợp đồng đó.

Mẫu trên giả định trước khi vào `handle` không có context cần giữ lại. Nếu ứng dụng cho phép lồng lời gọi, phải tìm hiểu mã cũ có khôi phục giá trị trước đó hay không. Một lỗi bị che giấu ở cơ chế cũ không nên trở thành yêu cầu cần sao chép sang cơ chế mới.

### 5.2. Mã đích hoàn chỉnh

Ví dụ dưới đây dùng context bất biến, giữ khóa trong lớp và cung cấp một điểm đọc có thông báo lỗi rõ ràng. Các permission chỉ là dữ liệu minh họa; trong ứng dụng thật, context phải được tạo từ kết quả xác thực và phân quyền đáng tin cậy tại điểm vào.

Lưu ví dụ thành `RequestContextDemo.java` khi thực hành:

~~~java
import java.util.Objects;
import java.util.Set;

public class RequestContextDemo {
    private static final ScopedValue<RequestContext> CURRENT =
            ScopedValue.newInstance();

    record RequestContext(
            String tenantId,
            String requestId,
            Set<String> permissions) {
        RequestContext {
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(requestId, "requestId");
            permissions = Set.copyOf(permissions);
        }
    }

    static RequestContext current() {
        return CURRENT.orElseThrow(() ->
                new IllegalStateException("Thiếu request context"));
    }

    static String handle(RequestContext context) {
        Objects.requireNonNull(context, "context");
        return ScopedValue.where(CURRENT, context)
                .call(RequestContextDemo::service);
    }

    static String service() {
        return repository();
    }

    static String repository() {
        RequestContext context = current();
        return context.tenantId() + ":" + context.requestId();
    }

    public static void main(String[] args) {
        var outer = new RequestContext(
                "tenant-a", "req-101", Set.of("invoice:read"));

        System.out.println(handle(outer));
        System.out.println("bound-after-handle=" + CURRENT.isBound());

        ScopedValue.where(CURRENT, outer).run(() -> {
            System.out.println("outer=" + current().requestId());

            var inner = new RequestContext(
                    outer.tenantId(),
                    "req-101/internal",
                    outer.permissions());

            try {
                ScopedValue.where(CURRENT, inner).run(() -> {
                    System.out.println("inner=" + current().requestId());
                    throw new IllegalStateException("Lỗi minh họa");
                });
            } catch (IllegalStateException expected) {
                System.out.println(
                        "restored=" + current().requestId());
            }
        });

        System.out.println("bound-after-all=" + CURRENT.isBound());
    }
}
~~~

Kết quả mong đợi:

~~~text
tenant-a:req-101
bound-after-handle=false
outer=req-101
inner=req-101/internal
restored=req-101
bound-after-all=false
~~~

Ví dụ cho phép quan sát hai ranh giới: `handle` cho một yêu cầu bình thường và một phạm vi lồng có lỗi. Khi operation kết thúc, binding được khôi phục về binding trước đó hoặc trở về trạng thái chưa bind; ngoại lệ từ operation được truyền ra ngoài. [Hợp đồng run và call](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html#call(java.lang.ScopedValue.CallableOp)).

Nhìn từ thiết kế ứng dụng:

- `handle` sở hữu quyết định chọn context cho luồng xử lý.
- `service` không cần nhận một tham số chỉ để chuyển tiếp xuống `repository`.
- `repository` vẫn thể hiện nhu cầu đọc context qua `current()`.
- Scope bên trong có context riêng cho thao tác nội bộ; mã sau đó tiếp tục dùng context ngoài.
- Ngoại lệ minh họa được bắt để in kết quả, không phải mẫu xử lý lỗi nghiệp vụ.

Khi chuyển mã thật, nên giữ facade đọc context ổn định nếu ứng dụng đã có. Như vậy, mỗi nhóm lời gọi có thể được chuyển theo một ranh giới tác vụ cụ thể, thay vì sửa mọi lớp cùng lúc.

### 5.3. Chọn dữ liệu bất biến ngay từ đầu

Record trong ví dụ có `String` và một tập hợp được sao chép bằng `Set.copyOf`. Việc sao chép giúp các thay đổi sau đó trên tập hợp đầu vào không làm thay đổi snapshot permission của yêu cầu.

Không nên suy luận rằng một record bất kỳ luôn bất biến sâu. Ví dụ, record chứa một `ArrayList` vẫn có thể cho phép thay đổi các phần tử thông qua tham chiếu danh sách.

Khi thiết kế context, hãy rà từng thành phần:

| Thành phần đề xuất | Cách xử lý |
|---|---|
| ID, tên, locale hoặc dữ liệu giá trị | Chọn kiểu bất biến phù hợp |
| Danh sách, tập hợp hoặc map đầu vào | Tạo snapshot; xét cả tính thay đổi của phần tử |
| Đối tượng dịch vụ lớn | Ưu tiên truyền ID hoặc dữ liệu cần thiết |
| Tài nguyên cần đóng | Đặt quyền sở hữu và việc đóng tại nơi quản lý tài nguyên |
| Dữ liệu cần được cập nhật trong quá trình xử lý | Thiết kế API nghiệp vụ hoặc kiểu kết quả riêng |

Những lựa chọn này giúp context biểu diễn đầu vào của tác vụ, thay vì trở thành một nơi cất mọi trạng thái thuận tiện.

## 6. Giữ đúng hành vi khi thiếu context và khi có lỗi

### 6.1. Context bắt buộc và context tùy chọn

Đối với một repository bắt buộc có tenant context, việc thiếu context nên là lỗi rõ ràng như `current()` ở ví dụ trên. Một giá trị tenant mặc định có thể khiến lỗi tích hợp bị biến thành thao tác trên dữ liệu sai tenant.

Đối với metadata tùy chọn, chẳng hạn request ID dùng trong chẩn đoán, có thể chọn fallback có ý nghĩa:

~~~java
// Đoạn độc lập, dùng khóa riêng cho metadata tùy chọn.
private static final ScopedValue<String> OPTIONAL_REQUEST_ID =
        ScopedValue.newInstance();

static String requestIdForLog() {
    return OPTIONAL_REQUEST_ID.orElse("untracked");
}
~~~

`get()` ném `NoSuchElementException` nếu khóa chưa được bind. `orElse` chọn fallback khi chưa bind; `orElseThrow` cho phép tạo ngoại lệ theo hợp đồng ứng dụng. [Các cách đọc ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html#method-summary).

Trong API Java 25, không dùng `orElse(null)`: quy tắc đối số `null` của lớp áp dụng cho phương thức này. Việc `where(key, null)` được cho phép là trường hợp riêng; bind `null` vẫn là đã bind. Để đơn giản hóa hợp đồng của request context, ví dụ trong bài chủ động từ chối context `null`. [Quy tắc null và where](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html#where(java.lang.ScopedValue,T)).

### 6.2. Bỏ cleanup binding, giữ cleanup tài nguyên

Khi đã đặt việc thực thi trong scope, không thêm một khối `finally` chỉ để tìm cách “remove ScopedValue”. Tuy nhiên, việc dọn binding và việc đóng tài nguyên là hai trách nhiệm riêng.

Nếu service mở một stream, connection hoặc tài nguyên `AutoCloseable`, nơi sở hữu tài nguyên vẫn cần `try-with-resources` hay cơ chế đóng tương ứng. Đừng xóa phần đó chỉ vì khối `finally` của `ThreadLocal.remove()` đã được loại bỏ.

Tương tự, nếu mã cũ phục hồi một context ngoài sau lời gọi nội bộ, ví dụ ở mục 5 cho thấy cách biểu diễn yêu cầu đó bằng scope lồng. Hãy kiểm tra tại vị trí sau scope trong, vì đó là nơi lỗi khôi phục thường ảnh hưởng phần còn lại của yêu cầu.

## 7. Rà lại callback, executor và công việc chạy sau

### 7.1. Tạo callback trong scope chưa đủ

Đoạn dưới đây minh họa lỗi đặt ranh giới; giả định đã có `REQUEST_ID`:

~~~java
static Runnable makeTask() {
    return ScopedValue.where(REQUEST_ID, "req-101")
            .call(() -> (Runnable) () ->
                    System.out.println(REQUEST_ID.get()));
}
~~~

Operation bên ngoài chỉ tạo và trả về một `Runnable`. Khi gọi `makeTask().run()` ở ngoài mọi binding của `REQUEST_ID`, callback không còn ở trong phạm vi vừa tạo.

Nếu API cho phép, hãy chuyển dữ liệu cần thiết thành đầu vào của callback:

~~~java
static Runnable makeTask(String requestId) {
    return () -> System.out.println(requestId);
}
~~~

Nếu callback cần gọi nhiều tầng đang đọc qua `ScopedValue`, nơi thực thi callback phải thiết lập phạm vi phù hợp. Đây là một quyết định về hợp đồng và vòng đời, không chỉ là sửa cú pháp lambda.

### 7.2. Executor thông thường: truyền dữ liệu rồi bind tại nơi chạy

Hãy xem `ExecutorService`, `CompletableFuture` và callback của framework là các ranh giới cần kiểm tra việc truyền context. Không dựa vào giả định “tạo task trong scope thì task tự có binding”.

Java 25 có cơ chế kế thừa binding gắn với `StructuredTaskScope`. API structured concurrency đó **vẫn là preview trong Java 25**, tách biệt với trạng thái chính thức của `ScopedValue`. Bài không dùng nó làm điều kiện để chạy các ví dụ. [ScopedValue inheritance](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html#inheritance), [trạng thái StructuredTaskScope Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

Ví dụ sau chỉ sử dụng API chính thức và truyền một tenant ID tường minh sang task. Một executor đơn luồng giúp quan sát trạng thái của cùng worker sau khi task hoàn tất.

Lưu thành `ExecutorContextDemo.java` khi thực hành:

~~~java
import java.util.concurrent.Executors;

public class ExecutorContextDemo {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();

    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newSingleThreadExecutor()) {
            String result = ScopedValue.where(TENANT, "tenant-a")
                    .call(() -> {
                        boolean inherited = executor.submit(() -> {
                            return TENANT.isBound();
                        }).get();
                        System.out.println("inherited=" + inherited);

                        String tenantSnapshot = TENANT.get();

                        return executor.submit(() -> {
                            return ScopedValue
                                    .where(TENANT, tenantSnapshot)
                                    .call(TENANT::get);
                        }).get();
                    });

            System.out.println("task=" + result);

            boolean workerStillBound = executor.submit(() -> {
                return TENANT.isBound();
            }).get();

            System.out.println("worker-after=" + workerStillBound);
        }
    }
}
~~~

Kết quả mong đợi:

~~~text
inherited=false
task=tenant-a
worker-after=false
~~~

Điểm cần đọc trong ví dụ:

1. Task đầu tiên chỉ quan sát worker; nó chưa thiết lập scope nào.
2. Thread gửi task lấy `tenantSnapshot` khi vẫn đang ở trong context hợp lệ.
3. Task thứ hai nhận giá trị qua lambda và tự vào `where(...).call(...)` trên worker.
4. Sau task thứ hai, worker tiếp tục xử lý task khác mà không còn binding đó.
5. `get()` trong ví dụ làm thread gửi chờ kết quả; ví dụ này không mô tả tác vụ nền tách khỏi vòng đời yêu cầu.

Đây là **bind tường minh tại nơi thực thi**, không phải khả năng kế thừa context của executor.

Với email, export hoặc tác vụ nền chạy lâu hơn yêu cầu, nên thiết kế payload gồm các ID và dữ liệu cần thiết cho chính công việc đó. Tránh giữ nguyên cả request context chỉ để có thể đọc lại về sau: dữ liệu quyền truy cập, thời hạn và vòng đời tài nguyên cần được đánh giá theo hợp đồng của tác vụ nền.

### 7.3. Thư viện đọc ThreadLocal cần điểm tích hợp riêng

Sau khi chuyển `CURRENT` của ứng dụng, một logger, framework giao dịch hoặc thư viện bảo mật vẫn có thể đọc context riêng của nó.

Chọn một trong các hướng theo khả năng được thư viện hỗ trợ:

- Để tích hợp chính thức của thư viện cung cấp context.
- Dùng điểm mở rộng để ánh xạ dữ liệu tại ranh giới đã xác định.
- Giữ phần chưa chuyển và ghi rõ chủ sở hữu cùng vòng đời của nó.

Nếu cần adapter ghi tạm vào một `ThreadLocal` của thư viện, adapter phải khôi phục trạng thái trước đó khi hoàn tất. Không duy trì hai nguồn context có thể thay đổi độc lập tại nhiều tầng ứng dụng.

## 8. Những thay đổi thiết kế cần kiểm tra cùng API

### 8.1. Đừng dùng rebinding để gửi kết quả ngược lên

Nếu tầng dưới trước đây cập nhật một giá trị rồi mong tầng trên nhìn thấy, hãy đổi sang kiểu kết quả rõ ràng:

~~~java
record PricingResult(long total, String appliedPolicy) {}

static PricingResult calculatePrice() {
    return new PricingResult(250_000L, "STANDARD");
}
~~~

Tầng trên nhận cả tổng tiền và chính sách từ kết quả. Việc trả kết quả diễn đạt chính xác nhu cầu của bài toán hơn một cập nhật ngầm vào context.

### 8.2. Đặt khóa sau một API nhỏ

Giữ khóa trong phạm vi truy cập hẹp giúp ứng dụng kiểm soát nơi bắt đầu scope. Các lớp nghiệp vụ nên lấy dữ liệu qua một facade như `current()` hoặc một phương thức chuyên biệt như `currentTenantId()`, thay vì được cung cấp khóa để tùy ý tạo context mới.

Nếu chỉ có một vài hàm cần tenant ID và các hàm được gọi trực tiếp, truyền tenant ID qua tham số có thể dễ hiểu hơn. Hãy dùng context ẩn khi nó giúp một chuỗi gọi trung gian không phải nhận dữ liệu chỉ để chuyển tiếp.

### 8.3. Carrier không phải handle đóng scope

`where` tạo một carrier, chưa thực thi operation. Carrier lưu ánh xạ và có thể được dùng để gọi `run` hoặc `call`; nó không phải đối tượng `AutoCloseable` cần đóng để kết thúc binding. [Đặc tả Carrier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html).

Khi đọc mã, hãy tìm operation được thực thi ở đâu. Chỉ nhìn thấy một biến `carrier` được tạo ở đầu yêu cầu chưa chứng minh các lời gọi nghiệp vụ được chạy trong context đó.

Ngoài ra, nếu giữ carrier trong hàng đợi hoặc field lâu dài, ứng dụng cũng giữ các giá trị mà carrier tham chiếu. Hạn chế vòng đời carrier theo nhu cầu công việc thay vì xem nó như một context toàn cục có thể dùng bất cứ lúc nào.

## 9. Chạy ví dụ với mức nền Java 25

Trong môi trường thực hành, lưu từng lớp hoàn chỉnh ở file cùng tên rồi dùng JDK 25:

~~~shell
javac --release 25 -encoding UTF-8 RequestContextDemo.java
java RequestContextDemo
~~~

~~~shell
javac --release 25 -encoding UTF-8 ExecutorContextDemo.java
java ExecutorContextDemo
~~~

Hai ví dụ không dùng API preview nên không cần `--enable-preview`. `--release 25` giúp giữ mã nguồn và API nền ở Java 25; runtime chạy các class cũng cần đáp ứng mức phiên bản tương ứng. [Tài liệu javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html), [tài liệu java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

Khi chuyển một dự án:

1. Cập nhật toolchain biên dịch, mức API đích và runtime triển khai nhất quán.
2. Biên dịch lại mã đã sử dụng preview, cùng các thư viện liên quan mà ứng dụng tự quản lý.
3. Chỉ gỡ cấu hình preview khi đã xác nhận dự án không còn phụ thuộc tính năng preview khác.
4. Chuyển từng ranh giới tác vụ; đối chiếu kết quả nghiệp vụ trước và sau chuyển đổi.

Việc nâng runtime đơn lẻ chưa phải bằng chứng rằng mọi ví dụ preview hoặc adapter đã được chuyển đúng.

## 10. Tiêu chí nghiệm thu một lần chuyển đổi

Bảng sau dùng để xây dựng ca kiểm chứng cho ứng dụng thực tế:

| Tình huống | Hành vi cần quan sát |
|---|---|
| Yêu cầu có context hợp lệ | Các tầng xử lý đọc đúng dữ liệu đầu vào |
| Operation kết thúc bình thường | Scope không còn binding của yêu cầu vừa xử lý |
| Operation ném ngoại lệ | Ngoại lệ giữ đúng hợp đồng; context ngoài được khôi phục |
| Scope lồng | Bên trong đọc context trong; sau đó đọc lại context ngoài |
| Thiếu context bắt buộc | Có lỗi rõ ràng, không tự chọn tenant mặc định |
| Hai yêu cầu trên các thread khác nhau | Mỗi yêu cầu đọc đúng context của mình |
| Worker được tái sử dụng | Task sau không đọc được binding đã kết thúc của task trước |
| Callback chạy sau khi tạo | Context được truyền thành dữ liệu hoặc bind tại nơi chạy |
| Đầu vào có collection thay đổi được | Snapshot không thay đổi theo collection đầu vào |
| Thành phần thư viện còn dùng ThreadLocal | Điểm tích hợp được kiểm tra theo hợp đồng của thành phần đó |

Một lần chuyển đổi hoàn tất cần trả lời được: context được tạo ở đâu, việc xử lý được bao bởi operation nào, nơi nào đổi thread, và ai sở hữu dữ liệu/tài nguyên được tham chiếu. Khi các ranh giới đó rõ ràng, việc thay API preview hoặc một request context phù hợp bằng `ScopedValue` mới có ý nghĩa đối với hành vi của ứng dụng.
