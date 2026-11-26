# Ràng buộc giá trị bằng ScopedValue.where và thực thi trong phạm vi run hoặc call

`ScopedValue` cho phép một phương thức truyền dữ liệu một chiều tới các phương thức được gọi sâu bên trong mà không phải chuyển tiếp dữ liệu qua từng tham số. Caller tạo một binding bằng `ScopedValue.where(key, value)`, sau đó thực thi tác vụ trong phạm vi của binding bằng `Carrier.run()` hoặc `Carrier.call()`. Khi tác vụ kết thúc, binding tự động được khôi phục hoặc trở về trạng thái chưa bind.

Scoped Values được thử nghiệm qua nhiều phiên bản Java: incubator ở JDK 20 (JEP 429), preview ở JDK 21 (JEP 446), JDK 22 (JEP 464), JDK 23 (JEP 481) và JDK 24 (JEP 487). JEP 506 hoàn thiện API trong JDK 25. Trên JDK 25 và JDK 27, `ScopedValue`, `ScopedValue.Carrier`, `run()` và `call()` là API chính thức trong `java.base`, không cần `--enable-preview` hoặc incubator module.

## 1. Khi nào cần ScopedValue?

Thông thường, Java truyền dữ liệu qua tham số phương thức. Đây vẫn là cách rõ ràng nhất khi một phương thức trực tiếp cần một giá trị. Nhưng với một chuỗi gọi sâu, có thể chỉ phương thức đầu tiên và một callback ở cuối cần biết request ID, người dùng hiện tại hoặc thông tin tracing. Các phương thức trung gian phải nhận rồi truyền tiếp tham số dù không sử dụng chúng.

Ví dụ, luồng xử lý một request có thể đi qua controller, service, repository và cuối cùng tới một thành phần ghi log. Nếu mọi phương thức đều phải nhận `requestId`, chữ ký của nhiều lớp sẽ phụ thuộc vào cùng một chi tiết ngữ cảnh.

`ScopedValue` tạo một binding trong phạm vi thực thi động. Các phương thức được gọi trực tiếp hoặc gián tiếp bên trong phạm vi đó có thể đọc giá trị qua cùng một khóa `ScopedValue`, miễn là chúng có quyền truy cập tới khóa.

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Một phương thức cần một giá trị đầu vào rõ ràng | Truyền tham số thông thường. |
| Nhiều phương thức sâu trong cùng tác vụ cần đọc chung một context chỉ truyền từ caller xuống callee | `ScopedValue`. |
| Trạng thái mutable gắn với thread và được cập nhật trong nhiều điểm | Cân nhắc `ThreadLocal` hoặc một cơ chế trạng thái phù hợp; ScopedValue không cung cấp `set()`/`remove()`. |
| Truyền context qua một tác vụ executor không có kế thừa tự động | Bọc tác vụ bằng `Carrier.run()` hoặc `Carrier.call()`. |

## 2. Các thành phần của API

`ScopedValue<T>` là một khóa có kiểu `T`. Tạo khóa bằng `ScopedValue.newInstance()`. Khóa mới ban đầu chưa được bind trong bất kỳ thread nào.

`ScopedValue.where(key, value)` tạo một `ScopedValue.Carrier` chứa ánh xạ giữa khóa và giá trị. Carrier có thể tích lũy nhiều ánh xạ bằng cách gọi `where` liên tiếp. Binding chỉ có hiệu lực khi gọi `run()` hoặc `call()` trên carrier.

| API | Vai trò |
| --- | --- |
| `ScopedValue.newInstance()` | Tạo khóa ScopedValue mới, ban đầu chưa được bind. |
| `ScopedValue.where(key, value)` | Tạo Carrier chứa một binding. |
| `Carrier.where(key, value)` | Tạo Carrier mới có thêm hoặc thay thế binding cho khóa đó. |
| `Carrier.run(Runnable)` | Chạy tác vụ không trả về kết quả trong phạm vi binding. |
| `Carrier.call(ScopedValue.CallableOp)` | Chạy tác vụ có trả về kết quả trong phạm vi binding. |
| `ScopedValue.get()` | Đọc binding của khóa trong thread hiện tại. |
| `ScopedValue.isBound()` | Kiểm tra khóa có đang được bind trong thread hiện tại hay không. |
| `ScopedValue.orElse(value)` | Đọc giá trị nếu đã bind, nếu chưa thì trả về giá trị mặc định. |
| `ScopedValue.orElseThrow(supplier)` | Đọc giá trị nếu đã bind, nếu chưa thì ném exception do supplier tạo ra. |

`Carrier` là immutable và thread-safe. Mỗi lời gọi `where` trả về một Carrier mới; nó không sửa Carrier ban đầu. Nếu Carrier đã có ánh xạ cho cùng một khóa, lời gọi `where` tiếp theo thay giá trị trong Carrier mới đó.

## 3. Dùng run để thực thi tác vụ không trả kết quả

`run()` nhận một `Runnable`. Trong thời gian `Runnable.run()` và toàn bộ chuỗi phương thức mà nó gọi còn đang thực thi, các khóa trong Carrier được bind với giá trị tương ứng trên thread hiện tại.

Ví dụ sau dùng một `record` bất biến để gom thông tin request:

```java
public final class ScopedValueRunExample {
    private static final ScopedValue<RequestContext> CURRENT_REQUEST =
            ScopedValue.newInstance();

    record RequestContext(String requestId, String userId) {}

    public static void main(String[] args) {
        RequestContext context = new RequestContext("req-42", "user-17");

        ScopedValue.where(CURRENT_REQUEST, context)
                .run(ScopedValueRunExample::handleRequest);
    }

    private static void handleRequest() {
        loadOrder();
    }

    private static void loadOrder() {
        RequestContext context = CURRENT_REQUEST.get();
        System.out.printf("request=%s, user=%s%n",
                context.requestId(), context.userId());
    }
}
```

`main` tạo context và bind nó vào `CURRENT_REQUEST`. `handleRequest()` và `loadOrder()` không cần nhận thêm tham số, nhưng `loadOrder()` vẫn đọc được context bằng `CURRENT_REQUEST.get()`.

`ScopedValue` thuộc package `java.lang`, nên không cần import riêng. Ví dụ có thể biên dịch và chạy trên JDK 25 trở lên, bao gồm JDK 27, mà không cần bật preview:

```bash
javac --release 25 ScopedValueRunExample.java
java ScopedValueRunExample
```

## 4. Dùng call để thực thi tác vụ có kết quả

Khi tác vụ cần trả về kết quả, dùng `Carrier.call()`. `call()` nhận `ScopedValue.CallableOp`, trả lại giá trị do tác vụ tạo ra và cho phép exception của tác vụ được truyền về caller.

```java
public final class ScopedValueCallExample {
    private static final ScopedValue<RequestContext> CURRENT_REQUEST =
            ScopedValue.newInstance();

    record RequestContext(String requestId, String userId) {}

    public static void main(String[] args) {
        RequestContext context = new RequestContext("req-73", "user-21");

        String auditLine = ScopedValue.where(CURRENT_REQUEST, context)
                .call(ScopedValueCallExample::createAuditLine);

        System.out.println(auditLine);
    }

    private static String createAuditLine() {
        RequestContext context = CURRENT_REQUEST.get();
        return "request=" + context.requestId()
                + ", user=" + context.userId();
    }
}
```

`call()` trả về `String` do `createAuditLine()` tạo ra. Nếu tác vụ có thể ném checked exception, `CallableOp` cho phép khai báo và truyền exception đó về caller; phương thức gọi `call()` phải xử lý hoặc khai báo exception tương ứng.

Chọn theo kết quả của tác vụ:

- Dùng `run()` khi chỉ cần thực hiện hành động, ví dụ xử lý request hoặc ghi log.
- Dùng `call()` khi cần nhận một kết quả, ví dụ tạo response, tính tổng hoặc truy vấn dữ liệu.

## 5. Bind nhiều giá trị bằng cách nối where

Một Carrier có thể chứa nhiều binding. Gọi `where` tiếp theo trên Carrier để bổ sung khóa khác:

```java
import java.util.Locale;

public final class MultipleBindingsExample {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();
    private static final ScopedValue<Locale> CURRENT_LOCALE =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-88")
                .where(CURRENT_LOCALE, Locale.forLanguageTag("vi-VN"))
                .run(MultipleBindingsExample::handleRequest);
    }

    private static void handleRequest() {
        System.out.println("request=" + REQUEST_ID.get());
        System.out.println("locale=" + CURRENT_LOCALE.get());
    }
}
```

Trong `handleRequest()`, cả hai khóa đều đã được bind. Một Carrier cũng có thể được tạo trước rồi gọi `run()` hoặc `call()` sau:

```java
var requestBindings = ScopedValue.where(REQUEST_ID, "req-88")
        .where(CURRENT_LOCALE, Locale.forLanguageTag("vi-VN"));

requestBindings.run(MultipleBindingsExample::handleRequest);
```

Carrier chỉ là tập ánh xạ bất biến. Tạo Carrier chưa làm binding có hiệu lực; binding bắt đầu khi gọi `run()` hoặc `call()`.

Nếu nhiều trường luôn thuộc cùng một context, nên gom chúng vào một `record` hoặc kiểu dữ liệu bất biến tương đương rồi bind một ScopedValue. Scoped Values được thiết kế để dùng với số lượng khóa tương đối nhỏ; gom context giúp API dễ đọc và tránh tạo quá nhiều khóa độc lập.

## 6. Phạm vi lồng nhau và rebinding

Một khóa đang được bind có thể được bind lại trong phạm vi động lồng nhau. Giá trị mới chỉ có hiệu lực trong thời gian `run()` hoặc `call()` bên trong. Khi phạm vi bên trong kết thúc, giá trị của phạm vi ngoài được khôi phục.

```java
public final class RebindingExample {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(TENANT, "tenant-A").run(() -> {
            printTenant(); // tenant-A

            ScopedValue.where(TENANT, "tenant-B")
                    .run(RebindingExample::printTenant); // tenant-B

            printTenant(); // tenant-A được khôi phục
        });
    }

    private static void printTenant() {
        System.out.println(TENANT.get());
    }
}
```

Có thể hiểu quá trình như sau:

```text
Không có binding
    |
    +-- run(TENANT = tenant-A)
            |
            |-- get() -> tenant-A
            |
            +-- run(TENANT = tenant-B)
            |       |
            |       +-- get() -> tenant-B
            |       |
            |       +-- kết thúc phạm vi trong
            |
            +-- get() -> tenant-A
            |
            +-- kết thúc phạm vi ngoài
    |
    +-- trở về chưa bind
```

Rebinding hữu ích khi một request đi qua một phần xử lý cần tạm thời đổi tenant, locale hoặc security context. Phần xử lý bên trong thấy giá trị mới; sau đó caller tiếp tục với giá trị cũ.

## 7. Binding được khôi phục kể cả khi có exception

Khi tác vụ của `run()` hoặc `call()` kết thúc bình thường hoặc ném exception, mọi binding do phạm vi đó thiết lập sẽ được khôi phục. Nếu có binding trước đó cho cùng khóa, giá trị trước đó được phục hồi; nếu chưa có binding, khóa trở về trạng thái unbound.

```java
public final class ExceptionScopeExample {
    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(TENANT, "tenant-A").run(() -> {
            try {
                ScopedValue.where(TENANT, "tenant-B").run(() -> {
                    System.out.println(TENANT.get()); // tenant-B
                    throw new IllegalStateException("request failed");
                });
            } catch (IllegalStateException ex) {
                System.out.println(ex.getMessage());
            }

            System.out.println(TENANT.get()); // tenant-A
        });
    }
}
```

Không cần gọi `remove()` trong `finally`. Việc khôi phục binding là một phần ngữ nghĩa của `run()` và `call()`. Exception vẫn được truyền về caller theo quy tắc Java thông thường; ScopedValue không nuốt hoặc tự xử lý lỗi của tác vụ.

## 8. Đọc khóa khi chưa được bind

`get()` chỉ hợp lệ khi khóa đang được bind trong thread hiện tại. Nếu chưa bind, `get()` ném `NoSuchElementException`.

```java
private static final ScopedValue<String> CURRENT_USER =
        ScopedValue.newInstance();

static void printCurrentUser() {
    if (CURRENT_USER.isBound()) {
        System.out.println(CURRENT_USER.get());
    } else {
        System.out.println("Không có user context");
    }
}
```

Nếu trường hợp chưa bind có giá trị mặc định hợp lệ, có thể dùng `orElse()`:

```java
String user = CURRENT_USER.orElse("anonymous");
```

Nếu binding bắt buộc phải tồn tại, dùng `orElseThrow()` để báo lỗi có ý nghĩa:

```java
String user = CURRENT_USER.orElseThrow(
        () -> new IllegalStateException("Thiếu user context"));
```

`isBound()` phân biệt rõ hai trường hợp: khóa chưa được bind và khóa đã được bind với một giá trị. Trong thiết kế context, nên tránh bind `null` để việc kiểm tra và đọc giá trị dễ hiểu hơn.

## 9. ScopedValue gắn với thread như thế nào?

Binding của ScopedValue là theo từng thread. Nếu hai thread thực thi hai Carrier khác nhau với cùng một khóa, mỗi thread đọc được giá trị mà nó đã bind trong phạm vi của mình.

Không nên giả định một binding tự động xuất hiện trong mọi thread mới, executor hoặc callback bất đồng bộ. Tài liệu Java mô tả việc chia sẻ binding sang thread con trong những trường hợp có cấu trúc, cụ thể là `StructuredTaskScope`. Tuy nhiên, `StructuredTaskScope` vẫn là preview trên JDK 27 theo JEP 533 (preview lần thứ bảy). Vì vậy, không dùng nó như API stable hoặc đưa mã `StructuredTaskScope` vào ví dụ chạy mặc định trong bài này.

### Truyền binding tường minh tới Executor

Với executor thông thường, có thể giữ Carrier và bọc tác vụ bằng `run()` hoặc `call()` khi tác vụ thực sự chạy trên worker thread. Đây là cách dùng API ScopedValue stable, không cần dựa vào cơ chế kế thừa preview:

```java
import java.util.concurrent.Executors;

public final class ExecutorPropagationExample {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    public static void main(String[] args) throws Exception {
        var bindings = ScopedValue.where(REQUEST_ID, "req-91");

        try (var executor = Executors.newFixedThreadPool(2)) {
            var future = executor.submit(
                    () -> bindings.run(ExecutorPropagationExample::handle));
            future.get();
        }
    }

    private static void handle() {
        System.out.println("request=" + REQUEST_ID.get());
    }
}
```

Ở đây Carrier được tạo ở thread gọi, nhưng `bindings.run(...)` được thực thi trên worker thread. Binding được thiết lập cho worker trong lúc `handle()` chạy rồi được khôi phục sau đó. Nếu bỏ lớp bọc `bindings.run(...)` và chỉ submit `ExecutorPropagationExample::handle`, không nên kỳ vọng worker đọc được `REQUEST_ID`.

## 10. So sánh ScopedValue với ThreadLocal

| Khía cạnh | `ScopedValue` | `ThreadLocal` |
| --- | --- | --- |
| Mục tiêu | Truyền dữ liệu một chiều từ caller tới callee. | Lưu trạng thái gắn với thread. |
| Vòng đời | Binding bị giới hạn bởi `run()` hoặc `call()`. | Giá trị tồn tại theo thread cho tới khi được thay đổi hoặc xóa. |
| Thay đổi giá trị | Không có `set()`; tạo binding mới bằng Carrier trong phạm vi mới. | Có thể gọi `set()` từ bất kỳ nơi nào có khóa. |
| Dọn dẹp | Tự động khôi phục khi phạm vi kết thúc. | Thường phải gọi `remove()` đúng lúc, đặc biệt khi dùng thread pool. |
| Phạm vi đọc | Mã có tham chiếu tới khóa và chạy trong phạm vi binding. | Mã có tham chiếu tới ThreadLocal trên thread hiện tại. |
| Trường hợp phù hợp | Request context, principal, tenant, locale hoặc tracing context chỉ truyền xuống. | Trạng thái mutable thực sự thuộc về thread. |

ScopedValue không tự làm cho object được bind trở thành immutable. Nếu value là object mutable và được chia sẻ giữa nhiều thread, ứng dụng vẫn phải bảo đảm đồng bộ truy cập. Dùng `record` với các thành phần bất biến là lựa chọn phù hợp cho nhiều loại request context.

## 11. Nguyên tắc thiết kế và lỗi thường gặp

1. **Giữ khóa ở phạm vi truy cập hẹp.** Khai báo `private static final ScopedValue<Context>` khi có thể. ScopedValue đóng vai trò như capability: chỉ mã có quyền truy cập khóa mới đọc được giá trị.
2. **Bind tại ranh giới tác vụ.** Thiết lập context khi bắt đầu xử lý request hoặc công việc; để các phương thức bên trong đọc khi cần.
3. **Ưu tiên giá trị bất biến.** Binding không thể bị thay đổi trong phạm vi hiện tại, nhưng object được bind vẫn có thể mutable.
4. **Gom context hợp lý.** Nếu nhiều trường luôn đi cùng nhau, gom vào một `record` và bind một khóa thay vì tạo quá nhiều ScopedValue.
5. **Dùng đúng run hoặc call.** `run()` cho tác vụ không trả kết quả; `call()` cho tác vụ có kết quả.
6. **Không đọc ngoài phạm vi.** Dùng `get()` khi binding là điều kiện bắt buộc; dùng `isBound()`, `orElse()` hoặc `orElseThrow()` khi phù hợp.
7. **Truyền tường minh qua executor.** Bọc tác vụ bằng `Carrier.run()` hoặc `Carrier.call()` nếu worker thread cần context.
8. **Không nhầm với StructuredTaskScope.** Trên JDK 27, StructuredTaskScope vẫn preview; muốn dùng phải bật preview đúng JDK và chấp nhận API có thể thay đổi. Ví dụ stable nên dùng ScopedValue riêng hoặc truyền context tường minh.

## 12. Lịch sử API và lưu ý migration

| JDK | JEP | Trạng thái |
| --- | --- | --- |
| JDK 20 | JEP 429 | Incubator. |
| JDK 21 | JEP 446 | Preview lần đầu. |
| JDK 22 | JEP 464 | Preview lần thứ hai. |
| JDK 23 | JEP 481 | Preview lần thứ ba. |
| JDK 24 | JEP 487 | Preview lần thứ tư; API chuyển sang phong cách fluent. |
| JDK 25 | JEP 506 | API chính thức. |
| JDK 27 | — | API stable, không cần preview flag. |

Một thay đổi quan trọng trong quá trình preview là bỏ `ScopedValue.runWhere()` và `ScopedValue.callWhere()`. API hiện hành dùng `ScopedValue.where(key, value)` để tạo Carrier, sau đó gọi `Carrier.run()` hoặc `Carrier.call()`. Khi đọc ví dụ từ JDK 20–23, không sao chép các phương thức preview cũ vào ứng dụng hiện đại.

Structured Concurrency là tính năng riêng. Trên JDK 27, `StructuredTaskScope` vẫn ở preview thứ bảy theo JEP 533. ScopedValue đã stable không làm cho StructuredTaskScope trở thành stable; nếu dùng StructuredTaskScope trong dự án JDK 27 thì vẫn phải bật preview theo đúng phiên bản JDK. Javadoc JDK 27 của `Carrier.run()` và `Carrier.call()` cũng ghi nhận `StructureViolationException` (preview) trong trường hợp tác vụ tạo một `StructuredTaskScope` nhưng không đóng scope trước khi kết thúc. Khi dùng ScopedValue mà không tạo StructuredTaskScope, các ví dụ stable trong bài không cần preview.

## Tài liệu tham khảo

- [JEP 429: Scoped Values (Incubator)](https://openjdk.org/jeps/429) — giai đoạn incubator trong JDK 20.
- [JEP 446: Scoped Values (Preview)](https://openjdk.org/jeps/446) — preview đầu tiên trong JDK 21.
- [JEP 464: Scoped Values (Second Preview)](https://openjdk.org/jeps/464) — preview trong JDK 22.
- [JEP 481: Scoped Values (Third Preview)](https://openjdk.org/jeps/481) — preview trong JDK 23.
- [JEP 487: Scoped Values (Fourth Preview)](https://openjdk.org/jeps/487) — preview trong JDK 24 và thay đổi sang API fluent.
- [JEP 506: Scoped Values](https://openjdk.org/jeps/506) — hoàn thiện API trong JDK 25.
- [ScopedValue, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html) — binding, rebinding, per-thread behavior và trạng thái API hiện hành.
- [ScopedValue.Carrier, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.Carrier.html) — `where`, `run` và `call`.
- [JEP 533: Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533) — trạng thái preview của Structured Concurrency trong JDK 27.
- [Preview Features, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/preview-list.html) — danh sách preview API của JDK 27.
