# Ưu tiên tham số tường minh khi luồng dữ liệu đơn giản

## 1. Bài toán: dữ liệu ngữ cảnh đi theo tác vụ

Trong chương trình Java chạy đồng thời, một tác vụ thường cần một số dữ liệu đi kèm: `requestId`, `tenantId`, tên người dùng, ngôn ngữ, deadline hoặc thông tin định tuyến. Dữ liệu này gọi chung là **ngữ cảnh thực thi** (*execution context*). Khi chuyển công việc sang một thread khác, chương trình phải quyết định cách đưa ngữ cảnh đến nơi xử lý.

Có hai kiểu thiết kế phổ biến:

- **Tham số tường minh:** hàm cần dữ liệu nào thì nhận dữ liệu đó qua tham số; caller chịu trách nhiệm cung cấp.
- **Ngữ cảnh ngầm theo thread:** hàm gọi `ThreadLocal.get()` hoặc đọc một cơ chế context khác dù chữ ký không cho biết nó phụ thuộc vào dữ liệu gì.

**Nguyên tắc:** khi dữ liệu chỉ đi qua một vài phương thức, hãy **ưu tiên tham số tường minh**. Nó giữ phụ thuộc ở ngay chữ ký phương thức, dễ kiểm thử và không phụ thuộc tác vụ đang chạy trên platform thread, executor worker hay virtual thread.

Ví dụ cách thiết kế dễ đọc:

~~~java
int calculateFee(int amount, boolean premium) {
    return premium ? 0 : amount / 20;
}
~~~

Người gọi thấy rõ hai đầu vào. So với cách dựa vào ngữ cảnh ẩn:

~~~java
int calculateFee(int amount) {
    boolean premium = PREMIUM_CUSTOMER.get();
    return premium ? 0 : amount / 20;
}
~~~

Đây là hai **mảnh phương thức minh họa**, không phải lớp Java độc lập. `PREMIUM_CUSTOMER` ở cách sau được giả định là một `ThreadLocal<Boolean>`; nếu chưa có giá trị, `get()` có thể trả về `null` và unboxing có thể ném `NullPointerException`. Kể cả khi khắc phục null, hợp đồng rằng caller phải thiết lập thread context trước khi gọi vẫn bị che giấu.

Không có quy tắc bắt buộc phải bỏ hoàn toàn `ThreadLocal`. Lời khuyên ở đây áp dụng khi **luồng dữ liệu đơn giản**, tức các giá trị và đường truyền của chúng đủ ngắn, dễ biểu diễn trực tiếp.

## 2. Vì sao tham số rõ ràng thường tốt hơn?

Hãy xét chuỗi xử lý:

~~~text
handleRequest(context, amount)
    -> calculateTotal(amount)
    -> formatResponse(context, total)
~~~

`calculateTotal` chỉ tính số học, còn `formatResponse` dùng mã request và tenant. Mỗi phương thức nhận đúng dữ liệu nó cần, thay vì lặng lẽ đọc trạng thái của thread.

Lợi ích cụ thể:

1. **Phụ thuộc hiện rõ:** nhìn chữ ký là biết một hàm cần `requestId` hay `tenantId`.
2. **Kiểm thử độc lập:** gọi hàm với dữ liệu mẫu, không phải khởi tạo/giải phóng thread context trong các bước thiết lập test.
3. **Dễ truyền qua ranh giới bất đồng bộ:** closure giữ một giá trị và gọi `process(context)` trên thread bất kỳ.
4. **Giảm rò rỉ dữ liệu giữa các yêu cầu:** thread pool có thể tái sử dụng worker, nhưng tham số của lần gọi trước không tự tồn tại trong lần gọi sau.
5. **Dễ refactor:** di chuyển tác vụ giữa thread thường, virtual thread hoặc executor không làm mất điều kiện thiết lập ngữ cảnh ngầm.
6. **Dễ kiểm soát vòng đời:** đối tượng context sống theo tham chiếu mà tác vụ giữ; không còn một slot `ThreadLocal` cần dọn dẹp sau mỗi lần chạy.

Cũng có đánh đổi: khi cùng một thông tin phải truyền qua hàng chục tầng không sử dụng nó, chữ ký có thể trở nên rườm rà. Khi đó mới cân nhắc thiết kế đối tượng ngữ cảnh hoặc cơ chế ngữ cảnh có phạm vi rõ ràng. Việc tránh thêm hai tham số vào hai phương thức không đủ lý do để đưa vào thread-local.

## 3. Ví dụ hoàn chỉnh với Java 17+: ngữ cảnh bất biến

Dùng `record` để biểu diễn giá trị ngữ cảnh gồm các `String` bất biến. Các hàm truyền dữ liệu cần thiết theo tuyến xử lý, không đọc trạng thái của thread.

Lưu vào **`ExplicitContextDemo.java`**:

~~~java
import java.util.Objects;

public class ExplicitContextDemo {
    record RequestContext(String requestId, String tenantId) {
        RequestContext {
            Objects.requireNonNull(requestId, "requestId");
            Objects.requireNonNull(tenantId, "tenantId");
        }
    }

    static int calculateTotal(int amount, int shippingFee) {
        return amount + shippingFee;
    }

    static String formatResult(RequestContext context, int total) {
        return context.requestId() + " / "
                + context.tenantId() + " -> " + total;
    }

    static String handleOrder(
            RequestContext context, int amount, int shippingFee) {
        int total = calculateTotal(amount, shippingFee);
        return formatResult(context, total);
    }

    public static void main(String[] args) {
        RequestContext context = new RequestContext("req-42", "tenant-A");
        System.out.println(handleOrder(context, 150, 15));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ExplicitContextDemo.java
java ExplicitContextDemo
~~~

Stdout chính xác:

~~~text
req-42 / tenant-A -> 165
~~~

Phân tích:

- `handleOrder` và `formatResult` cần ngữ cảnh, vì vậy chữ ký thể hiện nó.
- `calculateTotal` không cần ngữ cảnh, nên **không** nhận tham số context chỉ để chuyển tiếp.
- `RequestContext` có thể được chia sẻ an toàn trong ví dụ vì các trường `String` là bất biến. **Record không bảo đảm bất biến sâu**: nếu thêm `List` hoặc `Map` mutable, nên tạo snapshot hoặc defensive copy.
- Không cần giả định về thread đang chạy; kết quả chỉ phụ thuộc dữ liệu đầu vào và logic của hàm.
- Đối với các giá trị chỉ dùng riêng lẻ, có thể truyền `requestId` hoặc `tenantId` trực tiếp, thay vì luôn gói cả context.

Một test đơn giản có thể gọi `handleOrder(new RequestContext(...), 150, 15)`, so sánh chuỗi trả về và kết thúc. Không cần biết test runner dùng thread nào hoặc có chạy các test song song.

## 4. `ThreadLocal` giải quyết vấn đề khác và có rủi ro riêng

**ThreadLocal** là lựa chọn khi một API legacy cần đọc trạng thái của **thread đang chạy** từ nhiều tầng gọi hàm; nó không tự biến state này thành dữ liệu của một request. Trong worker pool, task A có thể đặt context rồi kết thúc, còn task B chạy trên cùng worker đọc lại dữ liệu cũ nếu không cleanup.

~~~java
// Snippet có ThreadLocal<String> CURRENT và method handle():
CURRENT.set(requestId);
try {
    handle();
} finally {
    CURRENT.remove();
}
~~~

Đoạn trên cần được đặt tại **điểm sở hữu context của tác vụ**, sau đó cần xem có scope lồng nhau phải **restore previous** hay không. Nếu lời gọi logic chuyển qua executor/thread khác, ThreadLocal không tự propagate theo việc submit; vẫn phải capture và bind bên worker hoặc truyền tham số tường minh.

Bài này ưu tiên **truyền trực tiếp biến/record bất biến** vì dependency dễ kiểm tra và không cần cleanup ngầm. Quy tắc set/get/remove, lỗi rò rỉ trên pooled worker và các wrapper propagation đã có bài chuyên sâu riêng.

## 5. Chuyển context sang executor bằng closure

Khi một hàm giao việc sang executor, hãy lấy snapshot ngữ cảnh **tại ranh giới giao việc**, rồi capture nó trong `Runnable` hoặc `Callable`. Tác vụ nhận dữ liệu qua tham số:

~~~text
caller: contextA, contextB
    |
    +-- submit(() -> process(contextA))
    |                    |
    |                    +-- worker bất kỳ
    |
    +-- submit(() -> process(contextB))
                         |
                         +-- worker bất kỳ
~~~

Lưu **`ExplicitExecutorDemo.java`** (Java 17+):

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExplicitExecutorDemo {
    record RequestContext(String requestId, String tenantId) {}

    static String process(RequestContext context, int amount) {
        return context.requestId()
                + " [" + context.tenantId() + "]: " + amount;
    }

    public static void main(String[] args) throws Exception {
        RequestContext first = new RequestContext("req-A", "tenant-X");
        RequestContext second = new RequestContext("req-B", "tenant-Y");

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> f1 =
                    executor.submit(() -> process(first, 100));
            Future<String> f2 =
                    executor.submit(() -> process(second, 200));

            System.out.println(f1.get());
            System.out.println(f2.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExplicitExecutorDemo.java
java ExplicitExecutorDemo
~~~

Stdout chính xác:

~~~text
req-A [tenant-X]: 100
req-B [tenant-Y]: 200
~~~

Các task có thể kết thúc ở thứ tự bất kỳ, nhưng chương trình gọi `f1.get()` rồi `f2.get()` nên thứ tự hai dòng in ra được xác định. `Future.get()` cũng giúp caller nhận lỗi task thông qua `ExecutionException`.

`first` và `second` là biến local effectively final, nên lambda được phép capture. Hai record này chứa `String` bất biến. Nếu thay bằng object mutable và sửa nó sau `submit`, các thread có thể thấy thay đổi bất ngờ hoặc xuất hiện data race. **Tham số tường minh giải quyết đường truyền dữ liệu; tính bất biến/đồng bộ giải quyết vấn đề chia sẻ mutable state.**

## 6. Virtual threads (Java 21+) không làm thay đổi quy tắc

Virtual threads do JVM lập lịch trên các carrier threads. Một virtual thread có thể được tạm unmount khi chờ I/O và tiếp tục trên carrier khác. Tham số hàm và các biến của tác vụ đi theo quá trình thực thi bình thường, nên không cần ràng buộc request context với danh tính carrier.

Lưu **`ExplicitVirtualThreadDemo.java`** (JDK 21+):

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExplicitVirtualThreadDemo {
    record RequestContext(String requestId, String tenantId) {}

    static String process(RequestContext context) {
        return context.requestId()
                + "/" + context.tenantId()
                + ": virtual=" + Thread.currentThread().isVirtual();
    }

    public static void main(String[] args) throws Exception {
        RequestContext a = new RequestContext("req-01", "tenant-A");
        RequestContext b = new RequestContext("req-02", "tenant-B");

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> first =
                    executor.submit(() -> process(a));
            Future<String> second =
                    executor.submit(() -> process(b));

            System.out.println(first.get());
            System.out.println(second.get());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExplicitVirtualThreadDemo.java
java ExplicitVirtualThreadDemo
~~~

Stdout chính xác:

~~~text
req-01/tenant-A: virtual=true
req-02/tenant-B: virtual=true
~~~

`Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread mới cho mỗi task. `try-with-resources` đóng executor và hoàn tất quản lý vòng đời. Không có thao tác thiết lập “thread context” ngầm; hàm `process(context)` không quan tâm được thực thi trên virtual thread hay platform thread.

Nếu chỉ có một tác vụ và không cần thu giá trị trả về, có thể dùng API trực tiếp:

~~~java
RequestContext context = new RequestContext("req-03", "tenant-A");
Thread worker = Thread.startVirtualThread(() -> process(context));
worker.join();
~~~

Đây là **mảnh mã** trong phương thức có kiểu `RequestContext` và `process` tương ứng, đồng thời xử lý hoặc khai báo `InterruptedException`. `Thread.join()` chỉ đợi kết thúc; nó không trả về kết quả hay ném lại ngoại lệ không bắt được trong worker. Cần kết quả và lỗi có cấu trúc thì dùng `Callable`/`Future` như ví dụ phía trên.

**Chú ý:** virtual thread vẫn có `ThreadLocal` của chính nó; nó không “đọc ThreadLocal của carrier” theo cách diễn giải tùy tiện. Vấn đề của ngữ cảnh ngầm là nó bám vào một thread hoặc scope riêng và cần quy tắc truyền/ràng buộc đúng khi tác vụ tách nhánh. Tham số tường minh tránh yêu cầu người đọc phải suy đoán quy tắc đó.

## 7. Thiết kế chữ ký: truyền riêng hay gom context?

### 7.1. Dữ liệu ít, sử dụng ở một hàm

Khi phương thức chỉ cần hai giá trị, dùng hai tham số:

~~~java
String formatMessage(String requestId, String localeTag) {
    return "[" + requestId + "] " + localeTag;
}
~~~

Không cần tạo `RequestContext` 20 trường cho thao tác này.

### 7.2. Có một nhóm dữ liệu đi chung và có nghĩa

Khi một nhóm trường cùng mô tả yêu cầu, có thể gom trong object bất biến:

~~~java
record RequestContext(
        String requestId,
        String tenantId,
        java.util.Locale locale) {}
~~~

Không biến object thành **“túi các service và trạng thái”** chứa database connection, HTTP response, logger, config toàn cục và nhiều đối tượng mutable. Như vậy nó chỉ thay một sự phụ thuộc ngầm bằng một sự phụ thuộc rộng khó đánh giá.

### 7.3. Hàm không dùng context

Không nên nhận tham số context chỉ để giữ quy ước nếu hàm thực sự không cần. Cho hàm nhận `amount` và `taxRate` nếu nó chỉ tính thuế. Cách này giữ chữ ký có ý nghĩa, hỗ trợ test và tránh coupling.

### 7.4. Context có dữ liệu mutable

Record `record RequestContext(List<String> roles) {}` không tạo tính bất biến sâu. Nếu các tác vụ cùng nhìn vào list đó và một tác vụ sửa, vẫn có race. Chụp snapshot trước khi submit:

~~~java
List<String> rolesSnapshot = List.copyOf(roles);
executor.submit(() -> checkRoles(rolesSnapshot));
~~~

Đây là **mảnh mã** có `roles`, `executor` và `checkRoles` được định nghĩa. `List.copyOf` tạo danh sách không sửa được; các phần tử bên trong vẫn có thể mutable nếu kiểu dữ liệu cho phép. Khi cần shared mutable state thật, dùng owner rõ ràng, lock, atomic hoặc concurrent collection phù hợp, không giả định “truyền param” tự làm mọi thao tác thread-safe.

## 8. Khi nào mới cân nhắc context ngầm?

Một số nhu cầu xuyên nhiều tầng có thể khiến truyền thủ công trở nên bất tiện: tracing/correlation ID qua thư viện chung, metadata gắn với một scope, hoặc API bên thứ ba chỉ đọc context ngầm. Lúc đó cần đánh giá:

- Ai **thiết lập** và **đóng** context?
- Scope của context là một lời gọi, một task, một request, hay toàn bộ thread?
- Nó có vượt ranh giới executor/child thread không, và cần truyền theo quy tắc nào?
- Có thể lẫn dữ liệu giữa các request không?
- Dữ liệu có bất biến và có thể được chia sẻ giữa các task con không?
- Nếu bị lỗi hoặc cancel giữa chừng, `finally`/đóng scope có được chạy đầy đủ?

Java 25 chuẩn hóa **`ScopedValue`** (JEP 506) cho ngữ cảnh đọc ngầm có phạm vi ràng buộc, phù hợp một số bài toán nhiều tầng. Đây là cơ chế khác `ThreadLocal`: việc thiết lập có phạm vi ràng buộc, và quy tắc truyền sang tác vụ con phụ thuộc cách tạo/quản lý task. Với Java 17/21 hoặc tình huống chỉ qua vài lời gọi, truyền tham số vẫn là lựa chọn đơn giản hơn.

**Lưu ý về bảo mật:** truyền `userId` hoặc `tenantId` đúng cách không tự thực hiện authorization. Các lớp kiểm tra quyền vẫn phải xác thực đầu vào và ràng buộc truy cập tài nguyên theo yêu cầu.

## 9. Tình huống thường gặp và quyết định

| Tình huống | Nên ưu tiên | Vì sao |
| --- | --- | --- |
| Hàm tính phí cần `amount` và `premium` | Hai tham số | Phụ thuộc nhỏ, rõ ràng |
| Hàm format log của một request chỉ cần `requestId` | Truyền `requestId` | Không cần setup/cleanup thread context |
| Vài hàm dùng chung `requestId`, `tenantId`, `locale` | `RequestContext` bất biến | Nhóm dữ liệu có ý nghĩa, không gây chữ ký quá dài |
| Submit hai tác vụ lên executor | Capture context rồi gọi `process(context)` | Không phụ thuộc worker tái sử dụng |
| Một virtual thread xử lý một yêu cầu | Truyền/capture context | Không phụ thuộc carrier, dễ test |
| Framework/library đòi context ngầm nhiều tầng | Cân nhắc cơ chế scoped/thread context | Cần scope, cleanup và propagation rõ ràng |
| Nhiều task cần cùng mutable counter | Atomic/lock hoặc owner riêng | Context propagation không thay concurrency control |
| Công việc có deadline | Truyền deadline và thiết kế timeout/cancel | Chuyển dữ liệu không tự dừng task |

Ở ví dụ thứ hai, đôi khi logger thật sự có cơ chế tự gắn correlation ID; đó là quyết định hạ tầng khác. Bảng trên dành cho **đường truyền dữ liệu đơn giản trong code Java của chính chương trình**.

## 10. Lỗi phổ biến

1. **Ẩn đầu vào của hàm trong `ThreadLocal`** dù caller có thể truyền trực tiếp: tăng độ khó khi test, debug và review.
2. **Quên `remove()` trong executor**: dữ liệu của yêu cầu trước có thể xuất hiện trong tác vụ khác trên cùng worker.
3. **Cho rằng `InheritableThreadLocal` tự truyền qua mọi executor**: worker pool có thể đã được tạo trước khi có request.
4. **Capture đối tượng mutable và sửa sau `submit`**: lambda vẫn giữ cùng tham chiếu, không phải một bản sao bất biến.
5. **Truyền context cho mọi hàm bất kể nó có dùng hay không**: tạo coupling và che phụ thuộc thực tế.
6. **Đưa nhiều service và object lớn vào “Context”**: khiến object thành service locator khó kiểm soát.
7. **Nghĩ `Future.get()` mang thread-local trở lại caller**: `get()` chỉ trả kết quả hoặc báo ngoại lệ task.
8. **Nhầm thread identity với logical request identity**: một request có thể tách thành nhiều task/thread.
9. **Giả định tham số tường minh loại bỏ mọi race**: mutable data vẫn phải được bảo vệ.
10. **Đánh đồng propagation với cancellation**: có deadline trong context không khiến thread tự bị interrupt khi đến hạn.

## 11. Checklist khi review

- [ ] Với đường truyền chỉ vài hàm, đã thử truyền tham số thay cho `ThreadLocal`?
- [ ] Mỗi phương thức có nhận **đúng trường dữ liệu nó sử dụng**?
- [ ] Nếu nhiều trường luôn đi cùng nhau, đã cân nhắc một object context bất biến, vừa đủ?
- [ ] Tại `executor.submit`, `Thread.startVirtualThread` hoặc callback, context có được đưa vào task tường minh?
- [ ] Có object mutable nào bị share giữa task mà chưa có chiến lược đồng bộ?
- [ ] Nếu vẫn dùng `ThreadLocal`, đã có `try/finally` cleanup/restore và test tái sử dụng worker?
- [ ] Có assumption sai rằng các task của một request chạy trên cùng một thread?
- [ ] Output, errors và timeout có đường truyền/vòng đời riêng, thay vì phụ thuộc trạng thái ẩn?
- [ ] Dữ liệu nhận từ context có được kiểm tra quyền khi dùng vào thao tác nhạy cảm?

## 12. Tài liệu chính thức

- [Java SE 17 — `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): `get`, `set`, `remove`.
- [Java SE 17 — `InheritableThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html): ngữ nghĩa kế thừa giá trị.
- [Java SE 21 — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `startVirtualThread`, `join` và `isVirtual`.
- [Java SE 21 — `Executors`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor`.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): mô hình concurrency của virtual thread.
- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): ngữ cảnh có phạm vi ràng buộc từ JDK 25.
