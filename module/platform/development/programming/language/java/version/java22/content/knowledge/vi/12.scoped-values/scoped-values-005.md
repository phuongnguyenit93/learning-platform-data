# Đọc giá trị, kiểm tra ràng buộc và xử lý khi khóa chưa có giá trị

`ScopedValue` cho phép truyền một giá trị theo ngữ cảnh gọi hàm mà không phải thêm tham số vào mọi phương thức trung gian. Một khóa `ScopedValue<T>` được tạo ở trạng thái chưa gắn giá trị (*unbound*). Khi cần thực hiện một công việc, chương trình gắn khóa với một giá trị trong một phạm vi thực thi bằng `ScopedValue.where(key, value).run(...)` hoặc `.call(...)`. Các phương thức được gọi trực tiếp hay gián tiếp trong phạm vi đó có thể đọc giá trị bằng `get()`.

Khi đọc một khóa, cần phân biệt rõ ba tình huống: khóa đang được gắn giá trị; khóa chưa được gắn trong luồng thực thi hiện tại; và khóa được gắn nhưng giá trị là `null`. Các API `isBound()`, `get()`, `orElse(...)` và `orElseThrow(...)` hỗ trợ những cách xử lý khác nhau cho các trường hợp này.

`ScopedValue` được chuẩn hóa trong JDK 25 qua JEP 506 và tiếp tục là API stable trên JDK 27. JDK 27 là feature release mới nhất tại ngày 25-11-2026; JDK 25 là LTS mới nhất. Các ví dụ trong bài dùng API stable, không cần `--enable-preview`.

## 1. Tạo khóa và gắn giá trị trong một phạm vi

Một khóa thường được khai báo là `private static final` để những phần mã được phép truy cập mới có thể đọc giá trị:

```java
import java.lang.ScopedValue;

public class RequestContext {
    private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

    static void handle(String requestId) {
        ScopedValue.where(REQUEST_ID, requestId).run(() -> {
            processRequest();
        });
    }

    private static void processRequest() {
        System.out.println("Processing request " + REQUEST_ID.get());
    }
}
```

`ScopedValue.newInstance()` tạo một khóa ban đầu chưa được gắn giá trị. `where(REQUEST_ID, requestId)` tạo một `Carrier` chứa ánh xạ khóa với giá trị. `run(...)` thực thi `Runnable` trong khi ánh xạ đó đang có hiệu lực.

Trong lúc `processRequest()` chạy, `REQUEST_ID.get()` đọc được giá trị đã gắn. Khi `run(...)` kết thúc, khóa trở lại trạng thái trước đó. Nếu trước khi gọi `run(...)` khóa chưa được gắn, sau khi `run(...)` kết thúc nó lại là unbound. Không cần gọi `remove()` hoặc tự khôi phục giá trị như khi quản lý `ThreadLocal`.

## 2. Đọc bằng `get()` và kiểm tra bằng `isBound()`

`get()` trả về giá trị đang gắn với khóa trong thread hiện tại. Nếu khóa chưa được gắn, `get()` ném `NoSuchElementException`.

```java
import java.lang.ScopedValue;
import java.util.NoSuchElementException;

public class ReadScopedValue {
    private static final ScopedValue<String> USER = ScopedValue.newInstance();

    static void printUser() {
        if (USER.isBound()) {
            System.out.println("User: " + USER.get());
        } else {
            System.out.println("No user context is bound");
        }
    }

    public static void main(String[] args) {
        printUser(); // No user context is bound

        ScopedValue.where(USER, "duke").run(() -> printUser());
        // User: duke

        printUser(); // No user context is bound
    }
}
```

`isBound()` trả về `true` khi khóa có binding trong thread hiện tại, không phụ thuộc giá trị được gắn là gì. Nó không kiểm tra xem giá trị có khác `null` hay không.

Nên dùng `isBound()` khi chương trình cần chọn nhánh xử lý theo trạng thái binding. Nếu theo hợp đồng nghiệp vụ, giá trị bắt buộc phải tồn tại, có thể gọi `get()` trực tiếp hoặc dùng `orElseThrow(...)` để báo lỗi rõ nghĩa.

## 3. Dùng `orElse(...)` khi cần giá trị mặc định

`orElse(other)` trả về giá trị đang gắn nếu khóa có binding; nếu khóa unbound thì trả về `other`.

```java
import java.lang.ScopedValue;

public class ScopedValueFallback {
    private static final ScopedValue<String> LOCALE = ScopedValue.newInstance();

    static String currentLocale() {
        return LOCALE.orElse("vi-VN");
    }

    public static void main(String[] args) {
        System.out.println(currentLocale()); // vi-VN

        ScopedValue.where(LOCALE, "en-US").run(() ->
            System.out.println(currentLocale()) // en-US
        );

        System.out.println(currentLocale()); // vi-VN
    }
}
```

Trong ví dụ, `vi-VN` là giá trị mặc định khi không có ngữ cảnh locale. Khi có binding `en-US`, giá trị đó được ưu tiên. Sau khi phạm vi kết thúc, mặc định lại được dùng.

Đối số `other` của `orElse(...)` phải khác `null`. Từ JDK 25, truyền `null` cho `orElse(...)` sẽ gây `NullPointerException`. Nếu cần biểu diễn một giá trị có thể null, hãy thiết kế rõ trạng thái đó và dùng `isBound()` cùng `get()` thay vì dùng `orElse(null)`.

## 4. Dùng `orElseThrow(...)` khi binding là bắt buộc

Nếu một phương thức chỉ có thể hoạt động khi đã có request context, user context hoặc transaction context, nên ném ngoại lệ có thông điệp cụ thể khi khóa chưa được gắn:

```java
import java.lang.ScopedValue;

public class RequiredContext {
    private static final ScopedValue<String> TENANT = ScopedValue.newInstance();

    static String currentTenant() {
        return TENANT.orElseThrow(() ->
            new IllegalStateException("Tenant context is not bound")
        );
    }

    static void queryDatabase() {
        String tenant = currentTenant();
        System.out.println("Query database for tenant " + tenant);
    }

    public static void main(String[] args) {
        ScopedValue.where(TENANT, "tenant-42").run(RequiredContext::queryDatabase);

        // Gọi queryDatabase() ở ngoài phạm vi binding sẽ ném IllegalStateException.
    }
}
```

`orElseThrow(...)` chỉ gọi exception supplier khi khóa chưa được gắn. Khi có binding, nó trả về giá trị đã gắn mà không tạo ngoại lệ. Cách này phù hợp khi thiếu ngữ cảnh là lỗi lập trình hoặc vi phạm luồng xử lý, thay vì một tình huống cần fallback.

## 5. Phân biệt khóa unbound với khóa được gắn giá trị null

API `ScopedValue.where(key, value)` cho phép `value` là `null`. Vì vậy, trạng thái binding và nội dung giá trị là hai khái niệm riêng:

```java
import java.lang.ScopedValue;

public class NullScopedValue {
    private static final ScopedValue<String> OPTIONAL_NAME = ScopedValue.newInstance();

    public static void main(String[] args) {
        System.out.println(OPTIONAL_NAME.isBound()); // false

        ScopedValue.where(OPTIONAL_NAME, null).run(() -> {
            System.out.println(OPTIONAL_NAME.isBound()); // true
            System.out.println(OPTIONAL_NAME.get());    // null
            System.out.println(OPTIONAL_NAME.orElse("fallback")); // null
        });

        System.out.println(OPTIONAL_NAME.isBound()); // false
    }
}
```

Khi khóa đã được gắn `null`, `isBound()` vẫn trả về `true`, `get()` trả về `null`, và `orElse("fallback")` cũng trả về `null` vì binding tồn tại. `orElse(...)` chỉ dùng giá trị thay thế khi khóa unbound.

Trong thiết kế ứng dụng, thường nên tránh gắn `null` cho context bắt buộc. Hãy xác thực dữ liệu trước khi bind bằng `Objects.requireNonNull(...)` hoặc bằng constructor của kiểu context. Nếu null thực sự là một trạng thái hợp lệ, phải quy định rõ cách đọc và kiểm tra trạng thái đó.

## 6. Xác thực dữ liệu trước khi bind

Không nên gắn một context chưa hợp lệ rồi để các phương thức sâu trong call chain tự phát hiện lỗi. Hãy tạo một đối tượng context hợp lệ trước, sau đó mới bind đối tượng đó vào `ScopedValue`.

Ví dụ sau dùng record để gom request ID, tenant và user thành một giá trị bất biến:

```java
import java.lang.ScopedValue;
import java.util.Objects;

public class RequestContextDemo {
    private static final ScopedValue<RequestContext> CURRENT_REQUEST =
        ScopedValue.newInstance();

    record User(String id, String role) {
        User {
            id = requireText(id, "user id");
            role = requireText(role, "user role");
        }
    }

    record RequestContext(String requestId, String tenantId, User user) {
        RequestContext {
            requestId = requireText(requestId, "request id");
            tenantId = requireText(tenantId, "tenant id");
            user = Objects.requireNonNull(user, "user");
        }
    }

    private static String requireText(String value, String field) {
        String normalized = Objects.requireNonNull(value, field).strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return normalized;
    }

    static void handle(RequestContext request) {
        Objects.requireNonNull(request, "request");

        ScopedValue.where(CURRENT_REQUEST, request).run(() -> {
            authorize();
            loadOrder();
        });
    }

    private static RequestContext currentRequest() {
        return CURRENT_REQUEST.orElseThrow(() ->
            new IllegalStateException("Request context is not bound")
        );
    }

    private static void authorize() {
        RequestContext request = currentRequest();
        if (!request.user().role().equals("ADMIN")) {
            throw new SecurityException("User is not allowed to access this operation");
        }
    }

    private static void loadOrder() {
        RequestContext request = currentRequest();
        System.out.printf(
            "Loading orders for tenant %s, request %s%n",
            request.tenantId(), request.requestId()
        );
    }

    public static void main(String[] args) {
        User user = new User("u-17", "ADMIN");
        RequestContext request = new RequestContext("req-900", "tenant-42", user);

        handle(request);

        System.out.println(CURRENT_REQUEST.isBound()); // false
    }
}
```

Các ràng buộc được kiểm tra ở constructor của `User` và `RequestContext`. Nếu request ID hoặc tenant ID rỗng, hoặc user là null, việc tạo context thất bại trước khi gọi `ScopedValue.where(...)`. Do đó, mọi phương thức trong phạm vi binding có thể giả định rằng `CURRENT_REQUEST.get()` trả về một context đã qua xác thực.

Record cung cấp tính bất biến nông (*shallow immutability*). Nếu một record chứa collection hoặc đối tượng mutable, cần sao chép phòng vệ hoặc bảo đảm các thành phần đó không bị thay đổi ngoài dự kiến. Khi chia sẻ context qua nhiều thread, giá trị nên bất biến hoặc mọi truy cập mutable phải được đồng bộ hóa phù hợp.

## 7. Kết hợp nhiều khóa trong một phạm vi

Khi cần truyền một số giá trị độc lập, có thể nối nhiều lời gọi `where(...)` trên cùng `Carrier`:

```java
import java.lang.ScopedValue;

public class MultipleScopedValues {
    private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();
    private static final ScopedValue<String> USER_ID = ScopedValue.newInstance();

    static void handle(String requestId, String userId) {
        ScopedValue.where(REQUEST_ID, requestId)
            .where(USER_ID, userId)
            .run(() -> {
                System.out.println("Request: " + REQUEST_ID.get());
                System.out.println("User: " + USER_ID.get());
            });
    }
}
```

Tất cả các binding trong carrier có hiệu lực trong cùng phạm vi `run(...)`. Với nhiều giá trị có quan hệ chặt chẽ như request ID, tenant, user và locale, thường dễ quản lý hơn nếu gom chúng vào một record `RequestContext` rồi bind một khóa duy nhất. JDK cũng khuyến nghị dùng số lượng scoped value tương đối nhỏ.

## 8. Rebinding trong phạm vi lồng nhau

Một khóa có thể được bind lại trong phạm vi con. Binding bên trong che khuất binding bên ngoài trong thời gian phạm vi con chạy; khi phạm vi con kết thúc, giá trị trước đó được khôi phục.

```java
import java.lang.ScopedValue;

public class ScopedValueRebinding {
    private static final ScopedValue<String> USER = ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(USER, "alice").run(() -> {
            System.out.println(USER.get()); // alice

            ScopedValue.where(USER, "support-agent").run(() ->
                System.out.println(USER.get()) // support-agent
            );

            System.out.println(USER.get()); // alice
        });

        System.out.println(USER.isBound()); // false
    }
}
```

Rebinding hữu ích khi một phần xử lý cần thay thế ngữ cảnh tạm thời, chẳng hạn chạy một thao tác dưới danh tính dịch vụ hoặc locale khác. Không cần lưu và khôi phục giá trị bằng biến mutable; cơ chế phạm vi thực thi đảm nhiệm việc đó.

Binding cũng được khôi phục khi thao tác kết thúc bằng ngoại lệ. Vì vậy, nên dùng `run(...)` hoặc `call(...)` làm ranh giới rõ ràng cho công việc cần context, thay vì cố giữ binding sau khi phương thức đã trả về.

## 9. Dùng `call(...)` khi cần trả kết quả

`run(...)` phù hợp với thao tác không trả kết quả. Nếu công việc cần trả về một giá trị, dùng `call(...)`:

```java
import java.lang.ScopedValue;

public class ScopedValueCall {
    private static final ScopedValue<String> USER = ScopedValue.newInstance();

    static String greeting(String user) {
        return ScopedValue.where(USER, user).call(() ->
            "Hello, " + USER.get()
        );
    }

    public static void main(String[] args) {
        System.out.println(greeting("duke")); // Hello, duke
        System.out.println(USER.isBound());    // false
    }
}
```

`call(...)` trả lại kết quả từ `CallableOp` và vẫn giới hạn binding trong thời gian thực thi thao tác. Nếu callback ném ngoại lệ, ngoại lệ được truyền ra caller và binding được khôi phục khi phạm vi kết thúc.

## 10. Phạm vi thread và giới hạn với Structured Concurrency

Binding của `ScopedValue` là **per-thread**: `get()` đọc binding của thread hiện tại. Các phương thức được gọi trong cùng call chain của thread đó có thể đọc giá trị. Không nên giả định binding tự động được truyền sang mọi thread được tạo bằng `new Thread`, executor hoặc thread pool.

JDK hỗ trợ kế thừa scoped value trong các trường hợp concurrency có cấu trúc. Cụ thể, khi dùng `StructuredTaskScope`, binding hiện tại được chụp lúc mở scope và kế thừa vào các thread thực thi subtask được fork trong scope. Giá trị dùng chung giữa các thread cần bất biến hoặc phải được đồng bộ hóa đúng cách.

**Giới hạn phiên bản cần lưu ý:** `ScopedValue` là API stable từ JDK 25, nhưng `StructuredTaskScope` vẫn là preview API trong JDK 27 (JEP 533, Seventh Preview). Nếu thử nghiệm tích hợp này, phải bật preview ở cả lúc biên dịch và chạy:

```bash
javac --enable-preview --release 27 -d out src/PreviewStructuredTaskDemo.java
java --enable-preview -cp out PreviewStructuredTaskDemo
```

Không cần preview flag để dùng riêng `ScopedValue`. Các ví dụ trong bài chỉ sử dụng API stable của `ScopedValue` và không phụ thuộc vào `StructuredTaskScope`.

## 11. ScopedValue và ThreadLocal khác nhau ở đâu?

`ScopedValue` phù hợp với truyền dữ liệu một chiều từ caller tới các phương thức được gọi trong một phạm vi. `ThreadLocal` vẫn hữu ích khi mỗi thread thực sự cần trạng thái mutable riêng hoặc cần một giá trị tồn tại qua nhiều tác vụ trên cùng thread.

| Tiêu chí | `ScopedValue` | `ThreadLocal` |
|---|---|---|
| Mục đích chính | Truyền context từ caller xuống callee trong phạm vi có giới hạn. | Lưu trạng thái gắn với từng thread. |
| Thay đổi giá trị | Caller tạo binding; callee đọc giá trị, có thể tạo scope lồng nhau để rebind. | Code có quyền truy cập có thể gọi `set()` để thay đổi giá trị. |
| Vòng đời | Binding tự hết hiệu lực khi `run(...)`/`call(...)` kết thúc. | Giá trị tồn tại cho tới khi bị thay thế hoặc `remove()`; trong thread pool cần quản lý dọn dẹp. |
| Khi nào phù hợp | Request context, security identity, locale, transaction metadata được truyền một chiều. | Trạng thái mutable thật sự riêng cho thread hoặc tích hợp API yêu cầu ThreadLocal. |

Không nên thay mọi `ThreadLocal` bằng `ScopedValue` một cách máy móc. Hãy chọn theo vòng đời và quyền thay đổi dữ liệu. Với context chỉ cần truyền xuống trong một thao tác, `ScopedValue` giúp phạm vi và thời điểm kết thúc rõ ràng hơn.

## 12. Các lỗi thường gặp khi đọc và kiểm tra binding

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi `get()` khi khóa chưa được bind | Ném `NoSuchElementException`. | Dùng `isBound()`, `orElse(...)` hoặc `orElseThrow(...)` theo hợp đồng. |
| Coi unbound đồng nghĩa với giá trị null | Không phân biệt được chưa có binding với binding có giá trị null. | Kiểm tra `isBound()` trước khi đọc nếu null là trạng thái hợp lệ. |
| Dùng `orElse(null)` | Ném `NullPointerException` trên JDK 25+. | Dùng fallback khác null hoặc kiểm tra `isBound()` và `get()`. |
| Bind context trước khi xác thực | Phương thức sâu trong call chain có thể nhận dữ liệu sai. | Tạo và xác thực object context trước `where(...)`. |
| Cho nhiều thành phần giữ quyền truy cập key không cần thiết | Mở rộng khả năng đọc context ngoài phạm vi dự định. | Giữ key `private static final` và chỉ cung cấp phương thức đọc có kiểm soát. |
| Giả định binding tự truyền sang mọi thread | Thread khác có thể thấy khóa unbound. | Truyền dữ liệu tường minh hoặc dùng cơ chế concurrency có cấu trúc; lưu ý `StructuredTaskScope` vẫn preview trên JDK 27. |
| Gắn object mutable rồi chia sẻ cho nhiều thread | Có thể phát sinh race condition. | Ưu tiên giá trị bất biến hoặc đồng bộ hóa truy cập mutable. |
| Tạo quá nhiều khóa cho các trường context nhỏ | Tăng chi phí tìm binding và gây khó quản lý. | Gom các giá trị liên quan vào một record và bind một khóa. |

## 13. Biên dịch và chạy trên JDK hiện hành

Các ví dụ `ScopedValue` trong bài có thể biên dịch bằng JDK 25 hoặc JDK 27 mà không cần preview:

```bash
javac --release 25 -d out src/RequestContextDemo.java
java -cp out RequestContextDemo
```

Nếu dự án dùng JDK 27:

```bash
javac --release 27 -d out src/RequestContextDemo.java
java -cp out RequestContextDemo
```

Chỉ khi chương trình có dùng thêm API preview như `StructuredTaskScope` trên JDK 27 mới thêm `--enable-preview` ở cả hai lệnh. Không bật preview chỉ để sử dụng `ScopedValue`.

## 14. Checklist lựa chọn API đọc giá trị

- Dùng `get()` khi binding chắc chắn tồn tại theo hợp đồng của phương thức.
- Dùng `isBound()` khi cần rẽ nhánh theo trạng thái binding, nhất là khi giá trị null được cho phép.
- Dùng `orElse(nonNullDefault)` khi unbound là tình huống bình thường và có giá trị thay thế hợp lệ.
- Dùng `orElseThrow(...)` khi thiếu context là lỗi cần báo rõ.
- Xác thực giá trị trước khi bind; ưu tiên record hoặc kiểu bất biến cho context.
- Dùng `run(...)` cho thao tác không trả kết quả và `call(...)` khi cần kết quả.
- Giữ key trong phạm vi truy cập cần thiết và không giả định binding được truyền sang mọi thread.
- Dùng API stable của `ScopedValue` từ JDK 25; nhận diện `StructuredTaskScope` là preview trên JDK 27.

## 15. Kết luận

Để đọc và xử lý `ScopedValue` đúng cách, trước hết hãy xác định khóa có binding trong thread hiện tại hay không. `get()` đọc giá trị và ném `NoSuchElementException` khi unbound; `isBound()` kiểm tra sự tồn tại của binding; `orElse(...)` cung cấp fallback khác null; `orElseThrow(...)` báo lỗi khi context bắt buộc bị thiếu.

Hãy phân biệt unbound với binding chứa null, xác thực context trước khi bind và giữ giá trị bất biến nếu có chia sẻ qua thread. Binding chỉ tồn tại trong phạm vi `run(...)` hoặc `call(...)`, có thể được rebind trong scope lồng nhau và tự khôi phục khi scope kết thúc. `ScopedValue` là API stable từ JDK 25; `StructuredTaskScope` vẫn preview trên JDK 27 và phải được xử lý như một giới hạn riêng.

## Tài liệu tham khảo

- [JEP 506 – Scoped Values (JDK 25)](https://openjdk.org/jeps/506)
- [ScopedValue – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html)
- [JEP 533 – Structured Concurrency (Seventh Preview, JDK 27)](https://openjdk.org/jeps/533)
- [StructuredTaskScope – Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27.html)
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html)
