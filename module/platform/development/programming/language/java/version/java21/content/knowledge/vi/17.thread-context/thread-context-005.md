# InheritableThreadLocal và rủi ro sao chép context ngoài ý muốn

`InheritableThreadLocal<T>` cho phép một thread con nhận giá trị context từ thread cha tại thời điểm thread con được tạo. Cơ chế này hữu ích khi muốn truyền một ít thông tin theo quan hệ cha–con, nhưng có thể tạo ra lỗi khó thấy nếu giá trị là object mutable, thread sống lâu hoặc executor tái sử dụng worker.

Trong Java 21, virtual thread cũng kế thừa `InheritableThreadLocal` theo mặc định khi được tạo. Vì vậy, việc chuyển sang virtual thread không tự động loại bỏ context inheritance. Cần quyết định rõ context nào được phép truyền sang thread mới, giá trị đó có bất biến hay không và ai chịu trách nhiệm dọn dẹp.

## 1. ThreadLocal và InheritableThreadLocal

`ThreadLocal<T>` lưu một giá trị riêng cho từng thread. Thread con tạo mới không tự nhận giá trị `ThreadLocal` của thread cha.

`InheritableThreadLocal<T>` là một biến thể của `ThreadLocal<T>`. Khi một thread mới được tạo, Java có thể khởi tạo entry tương ứng trong thread con từ giá trị của thread cha.

```java
private static final ThreadLocal<String> LOCAL = new ThreadLocal<>();
private static final InheritableThreadLocal<String> INHERITED =
        new InheritableThreadLocal<>();

static void compareInheritance() throws InterruptedException {
    LOCAL.set("local-value");
    INHERITED.set("inherited-value");

    Thread child = Thread.ofPlatform().start(() -> {
        System.out.println(LOCAL.get());     // null
        System.out.println(INHERITED.get()); // inherited-value
    });

    child.join();
    LOCAL.remove();
    INHERITED.remove();
}
```

Thread con nhận giá trị `INHERITED` khi được tạo. `ThreadLocal` thông thường không truyền giá trị của thread cha sang thread con.

## 2. Giá trị được kế thừa tại thời điểm tạo thread

Việc kế thừa xảy ra khi thread con được tạo, không phải mỗi lần thread con bắt đầu một tác vụ. `InheritableThreadLocal.childValue(parentValue)` được gọi trong thread cha để xác định giá trị ban đầu của thread con.

Mặc định, `childValue()` trả lại chính `parentValue`. Điều đó có nghĩa là giá trị được kế thừa theo reference, không phải tự động sao chép object.

```java
private static final InheritableThreadLocal<String> REQUEST_ID =
        new InheritableThreadLocal<>();

static void showCreationTimeInheritance() throws InterruptedException {
    REQUEST_ID.set("request-A");

    Thread child = Thread.ofVirtual().start(() ->
            System.out.println(REQUEST_ID.get()));

    REQUEST_ID.set("request-B");
    child.join();

    REQUEST_ID.remove();
}
```

Thread con được tạo khi giá trị cha là `request-A`, nên giá trị ban đầu của nó là `request-A`. Việc thread cha đổi giá trị thành `request-B` sau đó không cập nhật entry riêng của thread con.

Với object mutable, cả hai thread có thể cùng giữ reference đến một object. Khi một bên thay đổi object đó, bên còn lại có thể nhìn thấy thay đổi.

## 3. Rủi ro shallow copy: hai thread cùng dùng một object mutable

Ví dụ sau dùng `Map` làm request context. Vì `childValue()` mặc định trả lại cùng reference, thay đổi nội dung map trong thread con cũng làm thay đổi map mà thread cha đang giữ:

```java
import java.util.HashMap;
import java.util.Map;

private static final InheritableThreadLocal<Map<String, String>> CONTEXT =
        new InheritableThreadLocal<>();

static void demonstrateSharedReference() throws InterruptedException {
    Map<String, String> parentContext = new HashMap<>();
    parentContext.put("requestId", "req-42");
    CONTEXT.set(parentContext);

    Thread child = Thread.ofVirtual().start(() -> {
        CONTEXT.get().put("worker", "catalog");
    });

    child.join();
    System.out.println(CONTEXT.get());
    // {requestId=req-42, worker=catalog}

    CONTEXT.remove();
}
```

Đây là chia sẻ object, không phải bản sao độc lập. Nếu nhiều thread cùng đọc và ghi map, ứng dụng còn phải xử lý an toàn luồng cho chính map đó. `InheritableThreadLocal` không tự thêm khóa hoặc bảo đảm thread-safety cho object được lưu.

Rủi ro tương tự xuất hiện với `Map`, `List`, mutable DTO, đối tượng chứa session hoặc một context có các trường lồng nhau. Ngay cả khi sao chép container bên ngoài, các object mutable bên trong vẫn có thể dùng chung reference.

## 4. Tùy chỉnh childValue để tạo bản sao

Có thể override `childValue()` để tạo giá trị riêng cho thread con:

```java
import java.util.HashMap;
import java.util.Map;

private static final InheritableThreadLocal<Map<String, String>> CONTEXT =
        new InheritableThreadLocal<>() {
            @Override
            protected Map<String, String> childValue(
                    Map<String, String> parentValue) {
                return parentValue == null
                        ? null
                        : new HashMap<>(parentValue);
            }
        };
```

`new HashMap<>(parentValue)` tạo map mới cho thread con. Thay đổi cấu trúc map ở thread con không làm thay đổi map của thread cha.

Đây chỉ là shallow copy. Nếu value của map là object mutable, các value đó vẫn được chia sẻ. Khi cần cách ly sâu hơn, hãy tạo bản sao phù hợp với mô hình dữ liệu hoặc dùng một context object bất biến. Không nên viết deep-copy tổng quát nếu không hiểu đầy đủ vòng đời và quan hệ giữa các object.

## 5. Rủi ro với thread pool: context gắn với worker, không gắn với từng task

Thread pool tái sử dụng worker thread cho nhiều tác vụ. Khi executor tạo một worker, worker kế thừa `InheritableThreadLocal` từ thread thực hiện việc tạo worker. Giá trị đó gắn với worker; nó không tự được thay bằng context của từng thread gửi task sau này.

Ví dụ tình huống:

1. Request A gửi task đầu tiên và khiến executor tạo worker W1.
2. W1 được tạo trong lúc thread xử lý Request A có `InheritableThreadLocal` chứa `request-A`.
3. Sau khi task A kết thúc, executor giữ W1 để tái sử dụng.
4. Request B gửi task lên W1; nếu context chưa được dọn hoặc thay thế, task B có thể nhìn thấy `request-A`.

Vì vậy, `InheritableThreadLocal` không phải cơ chế truyền context đáng tin cậy cho từng task trong executor dùng lại worker. Việc kế thừa chỉ xảy ra lúc worker được tạo, còn việc gửi task không tạo một thread con mới.

Khi task chạy trên virtual thread-per-task executor, mỗi task thường có virtual thread mới. Virtual thread đó kế thừa context từ thread gửi task tại thời điểm tạo theo mặc định. Điều này có thể hữu ích, nhưng cũng có thể truyền nhầm thông tin nhạy cảm hoặc context không cần thiết sang task mới.

## 6. Tắt kế thừa khi tạo thread

Java 21 cho phép tắt kế thừa `InheritableThreadLocal` bằng `Thread.Builder.inheritInheritableThreadLocals(false)`. Có thể dùng với virtual thread hoặc platform thread:

```java
Thread worker = Thread.ofVirtual()
        .inheritInheritableThreadLocals(false)
        .name("isolated-worker")
        .start(() -> {
            // Không nhận các giá trị InheritableThreadLocal từ thread tạo nó.
            processJob();
        });

worker.join();
```

Để tạo executor chạy mỗi task bằng virtual thread nhưng không kế thừa context:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = Thread.ofVirtual()
        .inheritInheritableThreadLocals(false)
        .factory();

try (ExecutorService executor = Executors.newThreadPerTaskExecutor(factory)) {
    executor.submit(() -> processJob());
}
```

Khi tắt inheritance, task không tự nhận các giá trị từ thread gửi task. Nếu task cần một phần context, hãy truyền rõ dữ liệu cần thiết qua tham số hoặc wrapper của task.

Phương thức tiện ích `Thread.startVirtualThread(task)` dùng cấu hình mặc định và không cung cấp tham số để tắt inheritance. Khi cần kiểm soát việc kế thừa, dùng `Thread.ofVirtual()` builder.

## 7. Truyền context tường minh cho từng task

Với executor tái sử dụng worker, cách dễ kiểm soát là chụp context cần thiết tại nơi gửi task, đặt context đó trong lúc task chạy và dọn dẹp trong `finally`.

```java
record RequestContext(String requestId, String tenantId) {}

private static final ThreadLocal<RequestContext> CURRENT =
        new ThreadLocal<>();

static Runnable withContext(Runnable task, RequestContext snapshot) {
    return () -> {
        CURRENT.set(snapshot);
        try {
            task.run();
        } finally {
            CURRENT.remove();
        }
    };
}

// Tại nơi gửi task:
RequestContext snapshot = new RequestContext("req-42", "tenant-a");
executor.submit(withContext(() -> processJob(), snapshot));
```

Wrapper này làm rõ context nào được truyền vào task và bảo đảm worker được dọn context sau khi task kết thúc, kể cả khi task ném exception. Với hệ thống có context lồng nhau, wrapper cần lưu và khôi phục giá trị trước đó thay vì luôn remove; chọn chính sách nhất quán với cách executor và framework quản lý task.

Context record ở ví dụ chỉ bất biến ở mức nông. Hãy dùng component bất biến như `String`, primitive hoặc value object bất biến; nếu record chứa `Map` hay object mutable, cần sao chép hoặc bảo vệ chúng riêng.

## 8. Dọn dẹp context và tránh rò rỉ dữ liệu

`remove()` chỉ xóa entry trên thread đang gọi. Gọi `CONTEXT.remove()` ở thread cha không xóa entry đã được kế thừa trong thread con. Mỗi thread cần tự dọn giá trị của mình khi vòng đời công việc kết thúc.

Với worker được tái sử dụng, nên đặt và xóa context quanh từng task trong `try/finally`. Nếu không, dữ liệu của task trước có thể tồn tại và bị task sau đọc nhầm.

Không truyền tự động các giá trị nhạy cảm như access token, thông tin xác thực, session object hoặc quyền người dùng sang mọi thread con. Chỉ truyền các trường thực sự cần cho tác vụ và cân nhắc thời gian sống của thread so với request đã tạo ra nó.

## 9. Khi nào nên dùng InheritableThreadLocal?

| Tình huống | Khuyến nghị |
|---|---|
| Thread con được tạo trực tiếp và cần nhận context nhỏ, bất biến | `InheritableThreadLocal` có thể phù hợp |
| Context chứa object mutable | Dùng `childValue()` để sao chép phù hợp hoặc truyền immutable context |
| Task chạy trên executor dùng lại worker | Truyền context theo từng task bằng wrapper/task decorator; không dựa vào inheritance lúc tạo worker |
| Task chạy trên virtual thread-per-task | Xác định rõ có cần inheritance; tắt bằng builder nếu không cần |
| Context có dữ liệu nhạy cảm hoặc quyền truy cập | Truyền tối thiểu dữ liệu cần thiết và kiểm soát vòng đời/cleanup |
| Không cần context trong thread con | Tắt inheritance bằng `inheritInheritableThreadLocals(false)` |

Không dùng `InheritableThreadLocal` như một kho lưu trạng thái toàn cục hoặc cơ chế tự động đồng bộ dữ liệu giữa các thread. Nó chỉ xác định giá trị ban đầu cho thread mới; nó không quản lý vòng đời request, không truyền context cho mỗi task và không làm object trở nên thread-safe.

## 10. API Java 21 cần nhớ

| API | Vai trò |
|---|---|
| `InheritableThreadLocal<T>` | Lưu giá trị có thể được kế thừa khi tạo thread con |
| `childValue(T parentValue)` | Xác định giá trị ban đầu của thread con; mặc định trả cùng reference |
| `ThreadLocal.remove()` | Xóa entry của thread hiện tại |
| `Thread.ofVirtual()` | Tạo virtual thread builder |
| `Thread.ofPlatform()` | Tạo platform thread builder |
| `Thread.Builder.inheritInheritableThreadLocals(false)` | Tắt kế thừa inheritable thread-local khi tạo thread |
| `Thread.Builder.factory()` | Tạo `ThreadFactory` với cấu hình builder |
| `Executors.newThreadPerTaskExecutor(ThreadFactory)` | Tạo executor tạo một thread cho mỗi task bằng factory đã cấu hình |

## 11. Biên dịch với Java 21

`InheritableThreadLocal`, `Thread.Builder` và các API executor trong bài đều có thể sử dụng với Java 21 mà không cần bật Preview.

```bash
javac --release 21 -d out src/InheritableContextDemo.java
java -cp out InheritableContextDemo
```

Đặt compiler release hoặc toolchain về 21 để kiểm tra cú pháp và API theo đúng phiên bản mục tiêu. Không thêm `--enable-preview` cho các ví dụ trong bài.

## 12. Tài liệu tham khảo

- [Java SE 21 API — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html)
- [Java SE 21 API — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 21 API — Thread.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html)
- [Java SE 21 API — Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html)
- [Java SE 21 API — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
