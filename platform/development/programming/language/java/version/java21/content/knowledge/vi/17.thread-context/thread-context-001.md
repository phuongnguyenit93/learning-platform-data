# ThreadLocal trên virtual thread và phạm vi dữ liệu theo task

Trong Java 21, **ThreadLocal** vẫn hoạt động khi mã chạy trên virtual thread. Giá trị được gắn với đối tượng **Thread** đại diện cho virtual thread, không gắn với platform thread đang làm carrier. Vì vậy, khi virtual thread tạm dừng rồi tiếp tục trên carrier khác, nó vẫn đọc được giá trị ThreadLocal của chính mình.

Mô hình một task một virtual thread cũng giúp dữ liệu ThreadLocal của task này tách biệt với task khác khi dùng **Executors.newVirtualThreadPerTaskExecutor()**. Tuy nhiên, ThreadLocal có phạm vi theo vòng đời thread, không tự biết ranh giới nghiệp vụ của task. Nếu một virtual thread tự xử lý nhiều công việc nối tiếp, giá trị đã đặt vẫn còn cho đến khi được thay thế, xóa hoặc thread kết thúc.

## 1. ThreadLocal lưu dữ liệu theo Thread

**ThreadLocal<T>** cung cấp một biến có giá trị riêng cho từng thread. Nhiều thread có thể truy cập cùng một đối tượng ThreadLocal, nhưng mỗi thread có giá trị độc lập.

~~~java
class RequestContext {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    static void handle(String requestId) {
        REQUEST_ID.set(requestId);
        try {
            processRequest();
        } finally {
            REQUEST_ID.remove();
        }
    }

    private static void processRequest() {
        System.out.println(REQUEST_ID.get());
    }
}
~~~

Trong ví dụ, **set()** đặt giá trị cho thread hiện tại, **get()** đọc giá trị đó và **remove()** xóa liên kết giá trị với thread hiện tại. Thread khác gọi get() trên cùng biến REQUEST_ID sẽ không đọc được giá trị vừa đặt ở thread này.

Nếu chưa gọi set() và không cấu hình giá trị khởi tạo, get() trả về null. Có thể tạo ThreadLocal với supplier:

~~~java
class BufferContext {
    private static final ThreadLocal<StringBuilder> BUFFER =
            ThreadLocal.withInitial(StringBuilder::new);
}
~~~

Supplier được gọi khi một thread lần đầu gọi get() mà chưa có giá trị. Mỗi thread nhận một StringBuilder riêng; nó không dùng chung một StringBuilder cho mọi thread.

## 2. Virtual thread giữ ThreadLocal qua các lần đổi carrier

Virtual thread được runtime lập lịch trên các platform thread gọi là carrier. Khi virtual thread thực hiện thao tác blocking được hỗ trợ, nó có thể được tháo khỏi carrier và tiếp tục sau đó trên một carrier khác.

Trạng thái ThreadLocal vẫn thuộc virtual thread:

~~~java
class VirtualThreadContext {
    private static final ThreadLocal<String> TRACE_ID =
            new ThreadLocal<>();

    static void runTask(String traceId) {
        TRACE_ID.set(traceId);
        try {
            System.out.println(TRACE_ID.get());
            performBlockingOperation();
            System.out.println(TRACE_ID.get());
        } finally {
            TRACE_ID.remove();
        }
    }

    private static void performBlockingOperation() {
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Task bị gián đoạn", e);
        }
    }
}
~~~

Sau khi virtual thread tiếp tục chạy, get() vẫn trả về traceId đã đặt trước khi blocking. Không cần lưu ThreadLocal vào carrier hoặc tự sao chép giá trị khi virtual thread đổi carrier.

Không dùng **Thread.currentThread()** để suy ra carrier. Trong mã ứng dụng chạy trên virtual thread, phương thức này trả về virtual thread đang thực thi.

## 3. Phạm vi task khi dùng executor tạo virtual thread cho mỗi task

**Executors.newVirtualThreadPerTaskExecutor()** tạo một virtual thread mới cho mỗi task được submit. Vì mỗi task có thread riêng, các giá trị ThreadLocal được đặt trong một task không tự động trở thành giá trị của task tiếp theo.

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

class TaskScopedContext {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    static void handle(String requestId) {
        REQUEST_ID.set(requestId);
        try {
            process();
        } finally {
            REQUEST_ID.remove();
        }
    }

    private static void process() {
        System.out.println(
                Thread.currentThread().isVirtual() + ": " + REQUEST_ID.get()
        );
    }

    public static void main(String[] args) {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            executor.submit(() -> handle("request-A"));
            executor.submit(() -> handle("request-B"));
        }
    }
}
~~~

Hai task chạy trên hai virtual thread riêng. Task A đọc được request-A và task B đọc được request-B; chúng không dùng chung giá trị ThreadLocal.

Đây là hệ quả của mô hình executor tạo thread cho mỗi task, không phải cam kết rằng ThreadLocal luôn có phạm vi task. Nếu ứng dụng tự tạo một virtual thread dài hạn rồi cho nó xử lý nhiều đơn vị công việc, dữ liệu ThreadLocal vẫn thuộc thread đó qua các đơn vị công việc.

## 4. Xóa giá trị ở cuối phạm vi sử dụng

Với task-per-virtual-thread, thread thường kết thúc khi task hoàn tất, nên giá trị ThreadLocal của thread đó không bị tái sử dụng bởi task tiếp theo như worker của thread pool truyền thống. Dù vậy, vẫn nên gọi **remove()** trong finally khi giá trị chỉ có ý nghĩa trong một phạm vi xử lý.

Việc dọn dẹp rõ ràng có ích khi:

- Một virtual thread chạy nhiều công việc nối tiếp.
- Một phần mã lồng nhau có thể ghi đè context hiện tại.
- Giá trị giữ tham chiếu tới object lớn trong khi thread còn sống.
- Mã được chuyển đổi giữa executor per-task và cơ chế chạy thread dài hạn.

~~~java
class ScopedRequestId {
    private static final ThreadLocal<String> REQUEST_ID =
            new ThreadLocal<>();

    static void process(String id) {
        REQUEST_ID.set(id);
        try {
            handleRequest();
        } finally {
            REQUEST_ID.remove();
        }
    }

    private static void handleRequest() {
        System.out.println("Đang xử lý " + REQUEST_ID.get());
    }
}
~~~

**remove()** xóa giá trị hiện tại của ThreadLocal trên thread đang chạy. Nó không xóa giá trị của thread khác và cũng không đóng tài nguyên được tham chiếu bởi giá trị đó.

## 5. Không dùng ThreadLocal làm pool tài nguyên cho virtual thread

Trong ứng dụng dùng platform thread pool, một số hệ thống cũ lưu đối tượng đắt tiền trong ThreadLocal để worker tái sử dụng giữa nhiều task. Mô hình virtual thread per task không tái sử dụng thread cho task tiếp theo, nên cách cache đó thường tạo một bản sao trên mỗi virtual thread thay vì chia sẻ một pool nhỏ.

Ví dụ, không nên tạo một **ThreadLocal** mở một kết nối cơ sở dữ liệu riêng cho mỗi virtual thread. Nếu có hàng nghìn task đồng thời, cách này có thể mở ra rất nhiều kết nối, vượt khả năng của database. Hãy dùng connection pool có giới hạn và để mỗi task mượn/trả connection theo thời gian sử dụng:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

class Repository {
    private final DataSource dataSource;

    Repository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    void loadData() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Thực hiện truy vấn trong phạm vi connection.
        }
    }
}
~~~

ThreadLocal phù hợp với dữ liệu nhỏ, gắn với luồng thực thi như request ID, trace ID hoặc thông tin phục vụ logging. Nó không phải cơ chế giới hạn concurrency hoặc quản lý vòng đời kết nối, transaction hay file.

## 6. Phân biệt ThreadLocal và InheritableThreadLocal

**ThreadLocal** không truyền giá trị sang thread con. **InheritableThreadLocal** là một lớp riêng mở rộng ThreadLocal, có cơ chế kế thừa giá trị khi thread mới được tạo.

Virtual thread mặc định có thể kế thừa các giá trị InheritableThreadLocal từ thread tạo nó. Có thể tắt việc kế thừa trên builder:

~~~java
class ChildThreadContext {
    private static final ThreadLocal<String> LOCAL =
            new ThreadLocal<>();
    private static final InheritableThreadLocal<String> INHERITED =
            new InheritableThreadLocal<>();

    static void startChild() throws InterruptedException {
        LOCAL.set("local-value");
        INHERITED.set("inherited-value");

        Thread child = Thread.ofVirtual()
                .inheritInheritableThreadLocals(false)
                .start(() -> {
                    System.out.println(LOCAL.get());     // null
                    System.out.println(INHERITED.get()); // null
                });

        child.join();
    }
}
~~~

Thiết lập false chỉ ngăn việc kế thừa các giá trị InheritableThreadLocal khi tạo thread. ThreadLocal thông thường vốn không được kế thừa. Nó cũng không ngăn task truy cập dữ liệu được truyền trực tiếp qua tham số, lambda capture hoặc static field.

Nếu task cần một phần context của request cha, hãy cân nhắc truyền dữ liệu đó tường minh. Khi cần dùng cơ chế kế thừa, hãy đọc bài học về Thread.Builder và InheritableThreadLocal để kiểm soát chính sách truyền context.

## 7. Dữ liệu mutable trong ThreadLocal vẫn cần quản lý đúng

ThreadLocal tạo vùng lưu trữ riêng theo thread, nhưng không tự làm object được lưu trở thành immutable hoặc thread-safe. Nếu một object được truyền sang thread khác qua tham số, static field hoặc InheritableThreadLocal, nhiều thread vẫn có thể cùng tham chiếu tới object đó.

~~~java
class PerThreadBuffer {
    private static final ThreadLocal<StringBuilder> BUFFER =
            ThreadLocal.withInitial(StringBuilder::new);

    static String format(String value) {
        StringBuilder buffer = BUFFER.get();
        buffer.setLength(0);
        buffer.append("Value: ").append(value);
        return buffer.toString();
    }
}
~~~

Mỗi thread có một StringBuilder riêng. Việc đặt lại độ dài trước khi dùng lại giúp tránh giữ nội dung của lần gọi trước nếu cùng thread xử lý nhiều lần. Nếu buffer không cần tồn tại lâu, có thể gọi remove() sau khi xử lý.

Không trả trực tiếp một object mutable đang lưu trong ThreadLocal cho nơi khác giữ lâu dài nếu nơi nhận có thể tiếp tục thay đổi nó. Hãy trả về giá trị bất biến hoặc bản sao phù hợp với hợp đồng API.

## 8. Chi phí bộ nhớ khi có nhiều virtual thread

Virtual thread nhẹ hơn platform thread, nhưng không miễn phí. Mỗi virtual thread có trạng thái riêng; các giá trị ThreadLocal và object được giữ bởi chúng cũng tiêu thụ bộ nhớ.

Khi có số lượng lớn virtual thread đồng thời, hãy:

1. Chỉ lưu những giá trị thực sự cần thiết trong ThreadLocal.
2. Tránh đặt cache lớn hoặc object nặng trong mỗi ThreadLocal.
3. Xóa giá trị sau phạm vi sử dụng nếu thread còn sống.
4. Không dùng ThreadLocal để tạo một bản sao tài nguyên độc quyền cho mọi task.
5. Đo heap, số virtual thread đang sống và lượng dữ liệu context dưới tải thực tế.

Không cần xóa mọi ThreadLocal ngay sau từng lệnh I/O nếu task vẫn cần context đó ở bước tiếp theo. Hãy xác định phạm vi dữ liệu theo một thao tác nghiệp vụ rõ ràng, rồi dọn dẹp ở điểm kết thúc phù hợp.

## 9. Khi nào nên dùng ThreadLocal trên virtual thread?

| Trường hợp | Cách lựa chọn |
|---|---|
| Request ID hoặc trace ID cần đọc ở nhiều tầng gọi đồng bộ | ThreadLocal có thể phù hợp; đặt và xóa theo phạm vi xử lý |
| Cache đối tượng lớn để tái sử dụng giữa nhiều task | Không phù hợp với mô hình virtual thread per task; dùng cache có phạm vi ứng dụng |
| Connection hoặc session cần giới hạn số lượng | Dùng pool chuyên dụng, không tạo một bản cho mỗi virtual thread |
| Context cần truyền sang thread con | Xem xét InheritableThreadLocal hoặc truyền tham số tường minh |
| Dữ liệu cần dùng chung giữa nhiều thread | Dùng cơ chế chia sẻ an toàn như object immutable hoặc cấu trúc đồng bộ phù hợp |
| Một virtual thread xử lý nhiều đơn vị công việc nối tiếp | Dọn ThreadLocal giữa các đơn vị công việc để tránh rò rỉ context |

## 10. Checklist quản lý ThreadLocal theo task

- [ ] Hiểu rằng giá trị ThreadLocal thuộc virtual Thread, không thuộc carrier.
- [ ] Dùng ThreadLocal cho dữ liệu nhỏ, gắn với luồng thực thi.
- [ ] Với executor per-task, mỗi task có virtual thread riêng và giá trị riêng.
- [ ] Không suy luận rằng ThreadLocal tự có phạm vi task nếu thread có thể xử lý nhiều task.
- [ ] Đặt và xóa giá trị theo phạm vi nghiệp vụ bằng try/finally.
- [ ] Không dùng ThreadLocal để pool connection hoặc tài nguyên đắt tiền cho virtual thread.
- [ ] Phân biệt ThreadLocal với InheritableThreadLocal.
- [ ] Kiểm tra dữ liệu mutable và tránh chia sẻ object không an toàn.
- [ ] Đo chi phí bộ nhớ khi chạy nhiều virtual thread đồng thời.

## Tài liệu tham khảo

- [Java SE 21 API: ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 21 API: InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html)
- [Java SE 21 API: Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [Java SE 21: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
