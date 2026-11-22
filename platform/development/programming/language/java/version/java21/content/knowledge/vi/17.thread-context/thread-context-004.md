# Dọn dữ liệu bằng `remove()` trong `finally` khi có nhu cầu

## Mục tiêu

`ThreadLocal` lưu một giá trị riêng cho từng thread. Cơ chế này hữu ích khi nhiều tầng xử lý cần đọc cùng một ngữ cảnh như request ID, người dùng hiện tại hoặc locale mà không phải truyền tham số qua mọi method. Tuy nhiên, một thread có thể được tái sử dụng để chạy nhiều task khác nhau. Nếu task đặt dữ liệu vào `ThreadLocal` rồi kết thúc mà không dọn, task tiếp theo trên cùng worker thread có thể đọc nhầm dữ liệu cũ.

Java cung cấp `ThreadLocal.remove()` để xóa giá trị gắn với `ThreadLocal` trên **thread hiện tại**. Khi dữ liệu chỉ có ý nghĩa trong một request hoặc task, hãy đặt giá trị và dọn trong `finally` để việc dọn diễn ra cả khi xử lý thành công lẫn khi có exception. Bài học này giải thích khi nào cần `remove()`, cách xử lý thread pool, context lồng nhau, virtual threads và các lỗi thường gặp.

## 1. `ThreadLocal` gắn dữ liệu với thread

Mỗi thread có giá trị riêng cho một đối tượng `ThreadLocal`. Hai thread gọi `get()` trên cùng một `ThreadLocal` không nhất thiết nhận cùng một giá trị:

```java
class ThreadLocalBasicExample {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        Thread first = Thread.ofPlatform().start(() -> {
            CURRENT_USER.set("alice");
            System.out.println(CURRENT_USER.get()); // alice
        });

        Thread second = Thread.ofPlatform().start(() -> {
            System.out.println(CURRENT_USER.get()); // null
        });

        first.join();
        second.join();
    }
}
```

`CURRENT_USER` là một đối tượng `ThreadLocal` dùng chung, nhưng giá trị được lưu riêng theo từng thread. Việc thread thứ nhất đặt `alice` không làm thread thứ hai nhìn thấy giá trị đó.

`ThreadLocal` không tự động truyền context từ thread gọi sang thread khác. Nếu một request đặt giá trị trên thread xử lý request rồi submit task sang executor, task chạy trên worker thread khác sẽ không tự nhận giá trị đó. Cần truyền dữ liệu tường minh hoặc thiết lập context bên trong task thực thi.

## 2. Vì sao cần dọn trong thread pool?

Thread pool tái sử dụng worker thread cho nhiều task. Nếu task A đặt một giá trị vào `ThreadLocal` nhưng không xóa, task B chạy sau đó trên cùng worker có thể đọc giá trị của task A.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

class ThreadLocalLeakExample {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            Future<?> first = executor.submit(() -> {
                CURRENT_USER.set("alice");
                System.out.println("Task A: " + CURRENT_USER.get());
                // Thiếu remove(): worker giữ lại alice sau khi task kết thúc.
            });

            first.get();

            Future<?> second = executor.submit(() ->
                    System.out.println("Task B: " + CURRENT_USER.get()));
            second.get(); // Có thể in alice vì cùng worker thread.
        }
    }
}
```

Ví dụ cố ý thể hiện lỗi: executor chỉ có một worker nên hai task được chạy lần lượt trên cùng thread. Task B có thể đọc `alice`, dù người dùng của task B không phải Alice.

Rủi ro không chỉ là dữ liệu hiển thị sai. Nếu `ThreadLocal` giữ request context, security principal, tenant ID hoặc thông tin giao dịch, dữ liệu cũ có thể ảnh hưởng đến logic xử lý task sau. Nếu value giữ một object lớn, nó còn có thể kéo dài thời gian giữ bộ nhớ.

## 3. Dùng `remove()` trong `finally`

Khi giá trị chỉ có ý nghĩa trong một task, hãy đặt nó trước phần xử lý và xóa trong `finally`:

```java
class ThreadLocalCleanupExample {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    static void handleRequest(String userId) {
        CURRENT_USER.set(userId);
        try {
            processRequest();
        } finally {
            CURRENT_USER.remove();
        }
    }

    private static void processRequest() {
        System.out.println("Đang xử lý cho " + CURRENT_USER.get());
        // Các tầng xử lý trong cùng thread có thể đọc CURRENT_USER.
    }
}
```

`finally` chạy khi khối `try` kết thúc bình thường hoặc do exception được ném ra. Nhờ đó, giá trị được dọn ngay cả khi `processRequest()` thất bại.

Đặt `remove()` sau `try/catch` mà không có `finally` dễ bỏ sót các đường thoát bất thường. Cũng không nên chỉ dọn ở cuối nhánh thành công, vì exception có thể khiến worker giữ context cũ.

### Dọn cả khi task chạy qua executor

Nếu task chạy trên worker thread, phải đặt và xóa `ThreadLocal` ngay bên trong task đó:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

class ExecutorThreadLocalCleanup {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    public static void main(String[] args) {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            String requestId = "req-204";

            executor.submit(() -> {
                REQUEST_ID.set(requestId);
                try {
                    handle();
                } finally {
                    REQUEST_ID.remove();
                }
            });
        }
    }

    private static void handle() {
        System.out.println(REQUEST_ID.get());
    }
}
```

Gọi `REQUEST_ID.remove()` ở thread gửi task chỉ xóa giá trị của thread gửi; nó không xóa giá trị trên worker thread. Việc dọn phải diễn ra trên chính thread đã đặt giá trị.

## 4. Phân biệt `remove()` với `set(null)`

`set(null)` đặt giá trị hiện tại thành `null`; `remove()` xóa entry của thread hiện tại khỏi map nội bộ của `ThreadLocal`. Hai thao tác này có thể cho kết quả khác nhau khi `ThreadLocal` được tạo bằng `withInitial()`.

```java
class RemoveVersusSetNullExample {
    private static final ThreadLocal<String> CURRENT_USER =
            ThreadLocal.withInitial(() -> "guest");

    public static void main(String[] args) {
        CURRENT_USER.set("alice");
        CURRENT_USER.set(null);
        System.out.println(CURRENT_USER.get()); // null

        CURRENT_USER.set("bob");
        CURRENT_USER.remove();
        System.out.println(CURRENT_USER.get()); // guest
    }
}
```

Sau `set(null)`, lần `get()` tiếp theo trả về `null`; giá trị khởi tạo không được gọi lại vì entry vẫn tồn tại. Sau `remove()`, lần `get()` kế tiếp xem như chưa có giá trị và gọi lại `initialValue()` do `withInitial()` cung cấp.

Vì vậy, nếu mục tiêu là dọn giá trị task-scoped và để thread trở về trạng thái chưa có binding, hãy dùng `remove()`. `set(null)` chỉ phù hợp khi `null` thực sự là một giá trị mà hợp đồng dữ liệu cần lưu.

## 5. Khôi phục context trước đó khi có phạm vi lồng nhau

Không phải mọi lần thiết lập `ThreadLocal` đều nên kết thúc bằng `remove()`. Nếu một thao tác lồng nhau tạm thời thay context bên ngoài, việc xóa vô điều kiện sẽ làm mất context của phạm vi gọi.

Ví dụ, request ngoài có trace ID `outer`, sau đó gọi một thao tác lồng nhau dùng trace ID `inner`. Khi thao tác trong kết thúc, cần khôi phục `outer`:

```java
import java.util.Objects;
import java.util.function.Supplier;

class NestedThreadLocalContext {
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    static <T> T withTraceId(String traceId, Supplier<T> action) {
        Objects.requireNonNull(traceId, "traceId");
        Objects.requireNonNull(action, "action");

        String previous = TRACE_ID.get();
        TRACE_ID.set(traceId);
        try {
            return action.get();
        } finally {
            if (previous == null) {
                TRACE_ID.remove();
            } else {
                TRACE_ID.set(previous);
            }
        }
    }

    static String currentTraceId() {
        return TRACE_ID.get();
    }

    public static void main(String[] args) {
        withTraceId("outer", () -> {
            System.out.println(currentTraceId()); // outer

            withTraceId("inner", () -> {
                System.out.println(currentTraceId()); // inner
                return null;
            });

            System.out.println(currentTraceId()); // outer được khôi phục
            return null;
        });

        System.out.println(currentTraceId()); // null, không còn context
    }
}
```

Ví dụ quy ước không dùng `null` làm một context hợp lệ: `null` có nghĩa là trước khi vào phạm vi hiện tại không có trace ID. Vì thế, `finally` gọi `remove()` khi không có context cũ, còn nếu có thì khôi phục giá trị trước đó.

Nếu code luôn gọi `remove()` khi thoát khỏi phạm vi lồng nhau, context của caller sẽ bị mất. Với API hỗ trợ phạm vi lồng nhau, hãy thiết kế rõ quy tắc restore trước đó thay vì chỉ xóa.

## 6. Kiểm thử không rò rỉ giá trị giữa các task

Có thể dùng một executor chỉ có một worker để chứng minh hai task dùng lại cùng thread và kiểm tra task thứ hai không đọc được dữ liệu của task thứ nhất:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;

class ThreadLocalCleanupTest {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    @Test
    void valueIsRemovedBeforeWorkerRunsNextTask() throws Exception {
        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            Future<String> first = executor.submit(() -> {
                CURRENT_USER.set("alice");
                try {
                    return CURRENT_USER.get();
                } finally {
                    CURRENT_USER.remove();
                }
            });

            Future<String> second = executor.submit(CURRENT_USER::get);

            assertEquals("alice", first.get());
            assertNull(second.get());
        }
    }
}
```

Test này kiểm tra kết quả quan sát được từ task thứ hai, không chỉ kiểm tra rằng `remove()` đã được gọi. Vì executor dùng một worker, task thứ hai được thực thi trên cùng thread sau task thứ nhất; nếu bỏ `remove()`, assertion `assertNull` sẽ thất bại.

Nên bổ sung test cho đường exception: đặt giá trị, ném exception trong phần xử lý, rồi submit task kế tiếp để xác nhận giá trị vẫn đã được dọn. Cách đó kiểm tra rằng cleanup thực sự nằm trong `finally`.

## 7. `ThreadLocal` và virtual threads

Virtual thread cũng hỗ trợ `ThreadLocal`. Tuy nhiên, cần phân biệt vòng đời của chúng với worker thread trong pool:

- Platform thread trong pool thường được tái sử dụng cho nhiều task. Giá trị task-scoped phải được dọn trước khi worker nhận task tiếp theo.
- Virtual thread thường được tạo riêng cho một task và kết thúc khi task hoàn tất, nên không có việc tái sử dụng cùng virtual thread cho task tiếp theo theo mô hình này.
- Trong một virtual thread còn sống lâu, `ThreadLocal` vẫn giữ giá trị cho đến khi được thay thế, xóa hoặc thread kết thúc. `remove()` hữu ích nếu context không còn cần thiết trước khi thread kết thúc.
- Tạo rất nhiều virtual thread với nhiều `ThreadLocal` chứa object lớn có thể làm tăng đáng kể bộ nhớ sử dụng.

Không nên dùng `ThreadLocal` để giả định dữ liệu sẽ tự truyền sang mọi virtual thread hoặc task con. Khi tạo task mới, hãy xác định rõ context cần được truyền qua tham số, cơ chế context propagation của framework hoặc một API phù hợp với phạm vi chia sẻ.

## 8. Khi nào nên dùng cơ chế context khác?

`ThreadLocal` phù hợp khi dữ liệu thực sự gắn với thread hiện tại và có quy tắc cleanup rõ ràng. Nếu mục tiêu chỉ là truyền dữ liệu bất biến trong một phạm vi gọi có giới hạn, `ScopedValue` là một lựa chọn hiện đại hơn ở các JDK đã hỗ trợ API ổn định.

Lưu ý theo phiên bản: trong Java 21, `ScopedValue` là preview API, cần bật preview khi biên dịch và chạy. API này được hoàn thiện ở Java 25. Vì vậy, với code phải chạy đúng trên Java 21, không được dùng `ScopedValue` như API Java 21 ổn định; khi nâng JDK lên phiên bản đã final, có thể đánh giá lại việc thay context chỉ đọc bằng scoped values.

Việc chọn cơ chế nên dựa trên đặc tính dữ liệu:

| Nhu cầu | Cách phù hợp |
|---|---|
| Giá trị mutable gắn với thread hiện tại, cần cập nhật trong quá trình xử lý | `ThreadLocal`, kèm cleanup hoặc restore rõ ràng |
| Context chỉ đọc, có phạm vi lồng nhau và cần chia sẻ có kiểm soát | `ScopedValue` trên JDK có API final; Java 21 chỉ có bản preview |
| Truyền dữ liệu qua executor hoặc ranh giới bất đồng bộ | Truyền context tường minh hoặc dùng cơ chế propagation được framework hỗ trợ |
| Giữ dữ liệu nghiệp vụ lâu dài | Đối tượng hoặc kho lưu trữ có vòng đời rõ ràng, không dùng `ThreadLocal` làm nơi lưu trữ lâu dài |

## 9. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Không gọi `remove()` trên worker thread dùng lại | Task sau có thể đọc context của task trước | Đặt `remove()` trong `finally` của task sở hữu giá trị |
| Gọi `remove()` trên thread gửi task | Không xóa được giá trị ở worker thread | Cleanup trên đúng thread đã gọi `set()` |
| Chỉ cleanup khi xử lý thành công | Exception để lại giá trị cũ | Dùng `try/finally` |
| Dùng `set(null)` với mục đích xóa entry | Entry vẫn tồn tại và `withInitial()` không chạy lại | Dùng `remove()` khi cần xóa binding |
| Xóa vô điều kiện trong phạm vi lồng nhau | Làm mất context của caller | Lưu và khôi phục giá trị trước đó |
| Nghĩ `ThreadLocal` tự truyền qua executor | Worker có thể không nhận context của request | Truyền tường minh hoặc thiết lập context trong task |
| Giữ object lớn trong `ThreadLocal` lâu hơn cần thiết | Tăng thời gian giữ bộ nhớ | Dọn ngay khi kết thúc phạm vi sử dụng |

## 10. Checklist cleanup `ThreadLocal`

Khi review một `ThreadLocal`, hãy kiểm tra:

1. Giá trị là thread-scoped hay chỉ có ý nghĩa trong một task/request?
2. Thread có được tái sử dụng bởi executor hoặc server worker không?
3. Mọi đường thoát khỏi phần xử lý có chạy cleanup không?
4. `remove()` được gọi trên đúng thread đã đặt giá trị chưa?
5. Có phạm vi lồng nhau cần khôi phục giá trị trước đó không?
6. Có nhầm `set(null)` với việc xóa entry không?
7. Context có đi qua executor hoặc callback bất đồng bộ không, và cơ chế truyền context đã rõ chưa?
8. Với virtual threads, có đang giữ object lớn trong `ThreadLocal` lâu hơn cần thiết không?
9. Dữ liệu chỉ đọc có phù hợp hơn với `ScopedValue` trên JDK đã hỗ trợ API final không?

## Kết luận

`ThreadLocal.remove()` cần được dùng khi giá trị chỉ có ý nghĩa trong một phạm vi task hoặc request và thread có thể tiếp tục được sử dụng cho công việc khác. Đặt cleanup trong `finally` để xử lý cả đường thành công lẫn exception, và luôn gọi trên chính thread đã lưu giá trị. Với context lồng nhau, khôi phục giá trị trước đó thay vì xóa vô điều kiện. Virtual threads cũng hỗ trợ `ThreadLocal`, nhưng không tự truyền context qua ranh giới task và vẫn có thể giữ dữ liệu trong suốt vòng đời thread. Khi cần context chỉ đọc với phạm vi rõ ràng, hãy cân nhắc `ScopedValue` trên JDK có API final; riêng Java 21, API này vẫn ở trạng thái preview.
