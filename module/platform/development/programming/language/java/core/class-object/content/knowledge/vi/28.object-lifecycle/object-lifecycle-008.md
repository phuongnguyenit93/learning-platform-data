# `finalize()` đã bị khuyến cáo loại bỏ và không dùng để quản lý tài nguyên — Java 17

## 1. Mục tiêu và kết luận cần nhớ

Trong Java, **garbage collector (GC)** giải quyết việc thu hồi bộ nhớ của những đối tượng không còn được chương trình sử dụng theo quy tắc reachability. Nhưng các đối tượng Java còn có thể quản lý **tài nguyên ngoài heap**: file descriptor, kết nối mạng, socket, JDBC connection, native memory, luồng dữ liệu hoặc khóa nghiệp vụ. Việc một đối tượng trở nên unreachable **không** tạo ra lời hứa rằng các tài nguyên đó sẽ được giải phóng **đúng thời điểm**.

Java từng cung cấp phương thức kế thừa từ `Object`:

```java
protected void finalize() throws Throwable
```

Một class có thể override để chạy mã “dọn dẹp” sau khi GC xác định đối tượng thuộc diện finalization. Nhưng cơ chế này có các vấn đề nghiêm trọng: **không có thời hạn gọi**, **không có thứ tự gọi**, khó kiểm soát lỗi, tốn chi phí, có nguy cơ deadlock, hồi sinh đối tượng và vấn đề bảo mật. Vì vậy **không sử dụng `finalize()` để đóng file, socket, database connection hoặc bất kỳ resource nào cần được giải phóng đáng tin cậy**.

Thay thế chính trong Java 17:

- **`try-with-resources`** để bảo đảm thực hiện `close()` khi kết thúc phạm vi sử dụng, bao gồm khi có exception.
- **`AutoCloseable` / `Closeable`** để khai báo và thực thi việc giải phóng resource một cách rõ ràng, có trách nhiệm sở hữu.
- **`try/finally`** nếu phải quản lý một thao tác cleanup chưa thể biểu diễn bằng try-with-resources.
- **`Cleaner`** hoặc **`PhantomReference`** trong một số tình huống thấp tầng làm **safety net**, không thay lời gọi `close()` chủ động.
- **Lifecycle management** của ứng dụng để đóng/cancel/unregister đúng lúc.

**Thông điệp quan trọng:** *GC quản lý khả năng thu hồi bộ nhớ; chương trình quản lý thời điểm đóng tài nguyên.*

Bài này theo **Java 17** và giải thích chi tiết: lịch sử deprecation, cơ chế finalizer, giới hạn, lựa chọn thay thế, exception suppression, tài nguyên phân cấp, ownership, Cleaner, ReferenceQueue, kiểm thử, migration khỏi `finalize()`, nhiều chương trình chạy độc lập và bài tập.

## 2. Phân biệt `finalize`, `final` và `finally`

Ba từ giống nhau về chữ nhưng khác hoàn toàn về vai trò:

| Khái niệm | Vai trò | Có dùng để đóng resource không? |
| --- | --- | --- |
| `finalize()` | Hook kế thừa từ `Object`, có thể được cơ chế finalization gọi khi xử lý object | **Không dùng** làm phương án cleanup đáng tin |
| `final` | Modifier của class, method, field, local variable; giới hạn kế thừa/override/gán lại | Không tự thực hiện cleanup |
| `finally` | Khối lệnh thực thi theo control flow của `try` (với các giới hạn như JVM bị dừng đột ngột) | Có thể cleanup, nhưng thường ưu tiên `try-with-resources` |
| `close()` | Phương thức được khai báo trong `AutoCloseable`, thường thể hiện explicit release | **Có**, nếu implementation đáp ứng contract |
| `try-with-resources` | Cú pháp `try (Resource r = ...) { ... }` gọi `close()` tự động khi ra khỏi scope | **Phương án ưu tiên** |

### Ví dụ đối chiếu

```java
final class ConnectionOwner implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("closed");
    }
}

try (ConnectionOwner owner = new ConnectionOwner()) {
    // Sử dụng tài nguyên trong phạm vi đã xác định.
}
```

Đoạn trên minh họa source hợp lệ trong một method/context thích hợp; nó **không có `finalize()`**. Modifier `final` của class không làm cho `close()` chạy. Chính `try-with-resources` mới bảo đảm gọi `close()` khi thoát theo control flow bình thường hoặc qua exception.

## 3. Lịch sử deprecation: Java 9, Java 17 và JDK 18

Cần nói chính xác theo mốc phát hành:

1. **Java 9:** `Object.finalize()` được đánh dấu **deprecated** do vấn đề thiết kế.
2. **Java 17:** `Object.finalize()` vẫn tồn tại trong Java SE API và được ghi `@Deprecated(since="9")`; API docs khuyến cáo không sử dụng.
3. **JDK 18:** **JEP 421** đánh dấu cơ chế finalization và các API liên quan **deprecated for removal**; đây là mốc quan trọng khác với “deprecated” trong Java 17.
4. Các JDK sau có thể thay đổi chính sách bật/tắt/loại bỏ finalization. Khi viết phần mềm phải xét **JDK thực tế đang deploy**, không phỏng đoán behavior tương lai chỉ từ số version.

**Không viết sai:** “Java 17 đã xóa `finalize()`” hoặc “Java 17 mới bắt đầu deprecated-for-removal”. Cả hai đều không chính xác. Java 17 còn API, nhưng nó đã được khuyến cáo không dùng; mốc for-removal là JDK 18.

### Vì sao vẫn học một API đã cũ?

Khi bảo trì ứng dụng, bạn có thể gặp:
- Code legacy override `finalize()` để đóng file/socket.
- Thư viện cũ sử dụng finalizer.
- Cảnh báo `javac -Xlint:deprecation`.
- Heap/performance issues do các finalizable objects.
- Một yêu cầu migrate sang JDK mới.
- Lỗ hổng do finalizer có thể nhìn thấy partially constructed object.

Hiểu cơ chế cũ giúp bạn **loại bỏ phụ thuộc đúng cách**, không phải học để tạo finalizer mới.

## 4. `Object.finalize()` trông như thế nào?

Trong Java 17, chữ ký từ `java.lang.Object`:

```java
@Deprecated(since = "9")
protected void finalize() throws Throwable
```

Tại source level, một subclass có thể override:

```java
class LegacyResource {
    @Override
    protected void finalize() throws Throwable {
        try {
            // Ví dụ di sản: cleanup trễ và không đáng tin.
        } finally {
            super.finalize();
        }
    }
}
```

**Đây chỉ là ví dụ đọc hiểu legacy, không phải code khuyến nghị sử dụng.** Không đặt tài nguyên thật cần đóng vào finalizer mới.

Đặc điểm:
- Nó không phải destructor như trong một số ngôn ngữ quản lý memory thủ công.
- Không được tự động gọi khi biến cục bộ hết scope.
- Không chạy ngay lúc reference được gán `null`.
- Không bảo đảm chạy trước process exit.
- Có thể bị trì hoãn không xác định.
- Các exceptions từ finalizer không vận hành như exception từ một lời gọi `close()` tường minh của caller.

### Không tự gọi `finalize()` thay `close()`

Gọi trực tiếp `someObject.finalize()` từ application code (kể cả nếu accessibility cho phép) chỉ là một lời gọi method thông thường; nó **không làm object unreachable, không thay GC, không bảo đảm idempotent**. Nếu cần cleanup chủ động, khai báo **`close()`** với contract rõ.

## 5. Vòng đời: object, reference, finalization, resource

Hãy mô hình hóa một object giữ native handle:

```text
[Client / GC root] ──strong ref──▶ [ResourceWrapper]
                                       │
                                       └──native handle──▶ [OS resource]
```

Khi client không còn đường tham chiếu mạnh đến wrapper:
- JVM có thể nhận diện wrapper không còn strongly reachable.
- GC có thể xử lý memory/lifecycle của wrapper khi phù hợp.
- Một finalizer (nếu có và được runtime xử lý) **không được bảo đảm chạy đúng lúc**, hoặc có thể không chạy.
- File descriptor/socket/native handle cần giải phóng **sớm và xác định**, không dựa vào việc wrapper cuối cùng được GC.
- Khi application gọi `close()`, wrapper có thể vẫn reachable nhưng OS resource đã đóng. Đây là **kết quả mong muốn**.

### Hai vòng đời khác nhau

**Vòng đời Java object**: cấp phát → còn reachable → có thể trở thành unreachable → GC có thể reclaim.

**Vòng đời resource**: acquire → use → **release/close** theo application contract.

Không bắt resource phải chờ object chết. Ngược lại, một object có thể tiếp tục tồn tại sau khi resource đã đóng, chẳng hạn để cung cấp metadata, trạng thái `isClosed()` hoặc logging.

## 6. Vì sao không dự đoán được thời gian chạy finalizer?

Không có deadline trong API kiểu:
- “GC phải chạy trong 100 ms sau `obj = null`”.
- “Finalizer phải chạy trước khi method caller return”.
- “`System.gc()` bắt buộc hoàn tất mọi finalizers”.
- “Process kết thúc bình thường sẽ chạy hết finalizers”.

Cả bốn khẳng định đều **không phải bảo đảm Java 17**.

JVM có thể trì hoãn GC theo áp lực bộ nhớ và chính sách collector. Một process nhỏ kết thúc nhanh thường không có lý do phải chạy full GC. Hơn nữa, source scope và liveness không trùng nhau, việc một local không dùng nữa không phải event finalizer.

Với resource khan hiếm (file descriptors, DB connections), có thể hết resource **trước khi** heap pressure khiến GC quan tâm.

### Rủi ro thực tế

Một application có heap còn dư nhưng mở rất nhiều sockets/file descriptors. Nó có thể gặp “too many open files” hoặc pool starvation vì phụ thuộc GC để gọi finalizer. Tăng heap đôi khi làm finalization bị trì hoãn lâu hơn, không giải quyết gốc rễ.

## 7. Runnable: resource có `close()` xác định

Lưu **`ExplicitCloseDemo.java`**:

```java
final class DemoResource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("resource closed");
        }
        System.out.println("using");
    }

    boolean isClosed() {
        return closed;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("closed");
        }
    }
}

public class ExplicitCloseDemo {
    public static void main(String[] args) {
        DemoResource resource = new DemoResource();

        resource.use();
        resource.close();

        System.out.println(resource.isClosed());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 ExplicitCloseDemo.java
java ExplicitCloseDemo
```

Stdout **chính xác**:

```text
using
closed
true
```

Ví dụ tự viết `close()` idempotent: gọi nhiều lần không giải phóng hai lần. `AutoCloseable` nói chung **không bắt mọi implementation idempotent**, nên nếu API cho phép đóng nhiều lần, hãy document/implement hành vi đó rõ.

## 8. Ưu tiên `try-with-resources`

`try-with-resources` được Java hỗ trợ từ Java 7. Khi resource implement `AutoCloseable`, cấu trúc:

```java
try (DemoResource resource = new DemoResource()) {
    resource.use();
}
```

tự gọi `resource.close()` khi rời try statement theo quy tắc ngôn ngữ.

Lợi ích:
- Nhìn thấy **phạm vi sở hữu** resource.
- Không quên close trên các nhánh `return` hoặc exception thông thường.
- Nhiều resources được đóng theo thứ tự ngược khai báo.
- Exception từ `close` được xử lý qua **suppressed exceptions** nếu try body đã có primary exception.
- Code thường ngắn và nhất quán hơn manual `try/finally`.

### Không đồng nghĩa đóng mọi object trong block

Chỉ các resource variables liệt kê trong `try (...)` có `close()` được auto-invoke. Một `StringBuilder` được tạo bên trong block không tự có `close()`; nó chỉ là Java object thông thường.

## 9. Runnable: try-with-resources luôn gọi `close()`

Lưu **`TryWithResourcesDemo.java`**:

```java
final class AuditResource implements AutoCloseable {
    AuditResource() {
        System.out.println("open");
    }

    void use() {
        System.out.println("use");
    }

    @Override
    public void close() {
        System.out.println("close");
    }
}

public class TryWithResourcesDemo {
    public static void main(String[] args) {
        try (AuditResource resource = new AuditResource()) {
            resource.use();
        }

        System.out.println("after");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 TryWithResourcesDemo.java
java TryWithResourcesDemo
```

Stdout:

```text
open
use
close
after
```

`close` xảy ra **trước** câu lệnh after. Không cần dự đoán GC, không cần `System.gc()` hoặc legacy finalizer.

## 10. Nếu code trong try ném exception?

`try-with-resources` vẫn đóng resource nếu việc tạo resource đã thành công. Exception từ thân try được truyền đi sau khi Java thực hiện cleanup theo quy tắc.

```java
try (AuditResource resource = new AuditResource()) {
    throw new IllegalStateException("problem");
}
```

Đây là snippet, không thể nhầm với full program. Lưu ý Java có các quy tắc đặc biệt nếu resource acquisition hoặc close cũng ném lỗi; phần suppression sẽ được giải thích riêng.

**Không dựa vào `finally`/`close` khi process bị kill đột ngột, JVM bị halt hoặc hardware failure.** Deterministic theo Java control flow không đồng nghĩa bảo đảm chống mọi sự cố ngoài hệ thống.

## 11. Runnable: cleanup cả khi exception

Lưu **`ExceptionCloseDemo.java`**:

```java
final class Resource implements AutoCloseable {
    @Override
    public void close() {
        System.out.println("close");
    }
}

public class ExceptionCloseDemo {
    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("work");
            throw new IllegalStateException("failed");
        } catch (IllegalStateException error) {
            System.out.println("caught:" + error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ExceptionCloseDemo.java
java ExceptionCloseDemo
```

Stdout:

```text
work
close
caught:failed
```

Không có dòng “finalize ran”. Cleanup chạy do **language construct**, không do collector.

## 12. Nhiều resources được đóng theo thứ tự ngược

Khi khai báo:

```java
try (Resource a = new Resource("A");
     Resource b = new Resource("B")) {
    // ...
}
```

Java đóng **B trước A**. Điều này phù hợp với các dependency stacks: đối tượng được tạo sau cùng thường nên release trước đối tượng gốc.

### Điều cần phân biệt

**Thứ tự close do try-with-resources** có quy tắc ngôn ngữ rõ.

**Thứ tự finalizers cho nhiều objects** không được chỉ định. Vì thế nếu Child resource cần dùng Parent resource lúc cleanup, finalizers không cung cấp một cơ chế dependency-order đáng tin.

## 13. Runnable: reverse-order close

Lưu **`CloseOrderDemo.java`**:

```java
final class NamedResource implements AutoCloseable {
    private final String name;

    NamedResource(String name) {
        this.name = name;
        System.out.println("open:" + name);
    }

    @Override
    public void close() {
        System.out.println("close:" + name);
    }
}

public class CloseOrderDemo {
    public static void main(String[] args) {
        try (NamedResource a = new NamedResource("A");
             NamedResource b = new NamedResource("B")) {
            System.out.println("work");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CloseOrderDemo.java
java CloseOrderDemo
```

Stdout:

```text
open:A
open:B
work
close:B
close:A
```

Nếu cleanup order quan trọng, kiến trúc cần thể hiện nó bằng explicit scopes/dependency management như ví dụ, không bằng thứ tự GC chọn xử lý objects.

## 14. Suppressed exceptions: bảo toàn lỗi gốc

Nếu code trong try body ném exception **và** `close()` cũng ném exception:
- Exception từ try body thường là **primary exception**.
- Exception từ `close()` thường là **suppressed exception**, truy cập qua `getSuppressed()`.
- Nhờ vậy lỗi “thực hiện công việc thất bại” không bị ghi đè một cách âm thầm bởi lỗi thứ hai trong cleanup.

Đây là khác biệt hữu ích giữa `try-with-resources` với một số cách viết manual `finally` thiếu cẩn thận.

### Phương thức `AutoCloseable.close()`

API `AutoCloseable` khai báo `void close() throws Exception`. Implementation có thể chọn ném một loại checked exception hẹp hơn, hoặc không ném checked exception. `java.io.Closeable.close()` khai báo `IOException` và có contract cụ thể dành cho I/O resources.

## 15. Runnable: quan sát suppressed exception

Lưu **`SuppressedExceptionDemo.java`**:

```java
import java.io.IOException;

final class FailingResource implements AutoCloseable {
    @Override
    public void close() throws IOException {
        throw new IOException("close-failed");
    }
}

public class SuppressedExceptionDemo {
    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("work-failed");
        } catch (IOException error) {
            System.out.println(error.getMessage());
            System.out.println(error.getSuppressed().length);
            System.out.println(error.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

Stdout:

```text
work-failed
1
close-failed
```

Thông báo lỗi gốc vẫn được bảo toàn. Nếu dùng manual `finally` và ném một exception mới không quản lý rõ, bạn có thể vô tình che mất exception ban đầu.

## 16. Khi constructor acquire resource thất bại

Một điểm dễ bị bỏ sót: **constructor cũng có thể ném exception** giữa chừng. Nếu acquisition diễn ra nhiều bước:

```java
ResourceA a = acquireA();
ResourceB b = acquireB(); // Có thể fail.
```

khi B fail, A cần được release. `try-with-resources` cho phép Java đóng các resources **đã tạo thành công trước đó** trong resource specification.

```java
try (ResourceA a = acquireA();
     ResourceB b = acquireB()) {
    use(a, b);
}
```

Đây là snippet thiết kế, giả định `ResourceA` và `ResourceB` implement `AutoCloseable`.

**Nếu constructor của một resource tự acquire một phần rồi ném exception trước khi object được đăng ký thành công trong try-with-resources**, chính constructor/factory phải tự dọn tài nguyên đã acquire trong quá trình thất bại. Try-with-resources **không thể đóng một resource variable chưa khởi tạo thành công**.

## 17. Runnable: resource thứ hai lỗi khi khởi tạo

Lưu **`ResourceAcquisitionFailureDemo.java`**:

```java
final class AResource implements AutoCloseable {
    AResource() {
        System.out.println("A-open");
    }

    @Override
    public void close() {
        System.out.println("A-close");
    }
}

final class BResource implements AutoCloseable {
    BResource() {
        System.out.println("B-start");
        throw new IllegalStateException("B-failed");
    }

    @Override
    public void close() {
        System.out.println("B-close");
    }
}

public class ResourceAcquisitionFailureDemo {
    public static void main(String[] args) {
        try (AResource a = new AResource();
             BResource b = new BResource()) {
            System.out.println("body");
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ResourceAcquisitionFailureDemo.java
java ResourceAcquisitionFailureDemo
```

Stdout:

```text
A-open
B-start
A-close
B-failed
```

A được tạo thành công nên được auto-close. B constructor ném exception nên `B-close` **không** được gọi bởi try-with-resources; nếu B đã mở tài nguyên OS trước khi throw, B constructor/factory phải tự dọn phần đã mở.

## 18. Resource ownership: ai chịu trách nhiệm `close()`?

Muốn dùng `AutoCloseable` đúng, phải xác định **owner**:
- Code nào gọi acquire/open?
- Ai được phép dùng resource?
- Scope kết thúc khi nào?
- Ai chịu trách nhiệm close?
- Có những borrowers chỉ mượn resource, không được close không?
- Nếu resource được return từ factory, quyền sở hữu được chuyển như thế nào?

Ví dụ method trả một `InputStream` mà caller phải đóng:

```java
InputStream openData() throws IOException {
    return Files.newInputStream(path);
}
```

**Snippet:** `path` cần tồn tại ở context phù hợp. Nếu factory trả một stream đang mở, hãy document “caller owns and must close”.

Một method chỉ **nhận resource để sử dụng** không nên tùy ý close resource do caller sở hữu nếu contract không quy định việc chuyển ownership.

### Ownership giúp ngăn hai nhóm lỗi

1. **Resource leak**: chẳng ai close.
2. **Use-after-close/double-close**: nhiều bên nghĩ mình là owner, dẫn đến đóng sớm hoặc đóng lặp.

Hãy chọn một owner rõ và một cleanup point đúng.

## 19. `Closeable` và `AutoCloseable`

`AutoCloseable`:
- Tổng quát, có phương thức `close() throws Exception`.
- Dùng trong try-with-resources.
- Hợp với nhiều loại resources: database connection, custom handle, subscriptions.

`Closeable`:
- Thuộc `java.io`, extends `AutoCloseable`.
- `close() throws IOException`.
- Có contract cụ thể cho các closeable I/O objects và yêu cầu close nhiều lần không tạo hiệu ứng khi đã đóng theo API.

Không phải mọi object Java cần implement `AutoCloseable`. Một immutable value object như `record Point(int x,int y)` không giữ resource ngoài heap thì không cần `close()`.

### Tránh `AutoCloseable` chỉ để lấy `try` syntax

Nếu một object không thực sự có resource lifetime, thêm `AutoCloseable` với `close()` rỗng làm API khó hiểu và tạo kỳ vọng giả về ownership.

## 20. Runnable: tự viết một `Closeable` có trạng thái

Lưu **`CustomCloseableDemo.java`**:

```java
import java.io.Closeable;
import java.io.IOException;

final class TextHandle implements Closeable {
    private boolean closed;

    String read() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
        return "data";
    }

    @Override
    public void close() throws IOException {
        if (!closed) {
            closed = true;
            System.out.println("release");
        }
    }
}

public class CustomCloseableDemo {
    public static void main(String[] args) throws IOException {
        TextHandle handle = new TextHandle();

        try (handle) {
            System.out.println(handle.read());
        }

        System.out.println("done");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CustomCloseableDemo.java
java CustomCloseableDemo
```

Stdout:

```text
data
release
done
```

Java 9 trở đi hỗ trợ biến resource **final hoặc effectively final** đã khai báo trước `try` trong `try (handle)`. Trong Java 17 đây là cú pháp ổn định. Không cần gọi `finalize()`.

## 21. `finally` dùng khi không thể try-with-resources

Nếu API chưa implement `AutoCloseable`, bạn có thể cần:

```java
Resource resource = acquire();
try {
    use(resource);
} finally {
    release(resource);
}
```

Đây là **snippet** tùy API, không phải ví dụ có thể chạy độc lập. Nếu bạn kiểm soát interface, cân nhắc bọc resource trong adapter implement `AutoCloseable` để gọi:

```java
try (ResourceAdapter adapter = new ResourceAdapter(...)) {
    adapter.use();
}
```

### Cẩn thận thứ tự exception trong finally

Nếu body đã throw mà `finally` cũng throw, exception thứ hai có thể che mất exception thứ nhất. Với `AutoCloseable`, try-with-resources quản lý suppressed exceptions giúp giữ thông tin chẩn đoán tốt hơn.

### Không tự viết cleanup khi không có tài nguyên cần dọn

`finally` còn dùng cho restore state/unlock trong một số APIs. Nhưng không phải mọi method cần một `finally`; dùng khi có side effect/acquire cần guaranteed balancing action.

## 22. Runnable: `finally` cleanup theo control flow

Lưu **`ManualFinallyDemo.java`**:

```java
public class ManualFinallyDemo {
    static void process() {
        boolean acquired = false;

        try {
            acquired = true;
            System.out.println("work");
            throw new IllegalStateException("failure");
        } finally {
            if (acquired) {
                System.out.println("cleanup");
            }
        }
    }

    public static void main(String[] args) {
        try {
            process();
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ManualFinallyDemo.java
java ManualFinallyDemo
```

Stdout:

```text
work
cleanup
failure
```

Cơ chế điều khiển là exception unwinding, không phải GC. Với tài nguyên `AutoCloseable` thật, ưu tiên try-with-resources vì diễn đạt ownership rõ hơn.

## 23. File và stream: thay finalizer bằng scope rõ ràng

Một lớp cũ dùng `finalize()` để đóng file stream thường đang che giấu **ai sở hữu stream**. Khi refactor, làm rõ owner, trả resource cho caller có trách nhiệm hoặc bọc cả thao tác I/O trong `try-with-resources`. Chẳng hạn, `Files.lines(path)` trả stream có thể giữ file handle nên caller phải close theo contract, còn stream trong bộ nhớ như `Stream.of(...)` không có file handle tương đương.

Nếu API trả một `InputStream` từ factory, phải document rõ bên gọi chịu trách nhiệm đóng. Nếu một method chỉ mượn stream, không tự đóng resource của caller trừ khi contract cho phép chuyển quyền sở hữu. Đây là nguyên tắc sửa lỗi finalizer; chi tiết ví dụ `BufferedReader`, `Files.lines` và lỗi close thuộc bài AutoCloseable/TWR.

## 24. JDBC: đóng logical resources, không chờ finalization

`Connection`, `Statement`/`PreparedStatement` và `ResultSet` có lifecycle xác định trong JDBC. Không đặt `finalize()` trên DAO/entity để mong connection được trả về pool khi JVM dọn object. Thay vào đó, đặt explicit `close()` theo scope; trong connection pool, `Connection.close()` thường trả **logical connection** về pool, không nhất thiết đóng physical socket.

Một migration review phải xác định: ai lấy connection, ai commit/rollback transaction, ai sở hữu statements và result sets, có giữ connection trong singleton không, và các code paths khi exception xảy ra có close đúng không. `try-with-resources` giúp đóng resources nhưng **không tự commit hay rollback đúng nghiệp vụ** thay transaction management. Ví dụ nhiều JDBC resources và thứ tự đóng được triển khai trong bài chuyên AutoCloseable/TWR.

## 25. Socket và network resources: tách vòng đời kết nối khỏi GC

Socket có tài nguyên OS/protocol riêng và implements `Closeable`. Khi một operation sở hữu `Socket`, đóng đúng lúc bằng `close()` (thường trong `try-with-resources`), không viết finalizer hoặc gọi `System.gc()` để “cứu” việc hết file descriptors. Nếu helper chỉ mượn input/output stream từ socket, phải hiểu API ownership: đóng một stream có thể ảnh hưởng tới socket đang dùng chung.

Trong migration từ finalizer, điều cần kiểm tra là **vòng đời kết nối và người chịu trách nhiệm đóng**, kể cả khi handshake, I/O, timeout hoặc exception xảy ra. Cơ chế Java để close nhiều resources và xử lý suppressed errors được giải thích ở bài AutoCloseable/TWR; ở đây trọng tâm là vì sao finalization không thể thay contract đó.

## 26. Vì sao `System.gc()` không giải quyết resource leak?

Nhiều code legacy cố:

```java
resource = null;
System.gc();
System.runFinalization();
```

Đây là **anti-pattern**, không phải giải pháp.

- `resource = null` chỉ thay một reference; object có thể còn những references khác.
- `System.gc()` là một yêu cầu GC, không được dùng như deadline reclaim.
- `System.runFinalization()` không làm mô hình cleanup trở nên deterministic; đây cũng là API legacy liên quan finalization.
- Chờ finalizer không thể cam kết release trước khi pool/file descriptors hết.
- Phụ thuộc explicit GC thường gây áp lực lên hiệu năng và không giải quyết ownership bug.

**Sửa đúng:** close resource khi xong và giảm/tách references giữ nó, không yêu cầu collector sửa hộ lỗi lifecycle.

## 27. Vì sao finalizer gây vấn đề hiệu năng?

Một đối tượng cần finalization thường tham gia thêm đường xử lý của GC/runtime so với object thông thường. Điều này có thể dẫn tới:
- Chi phí theo dõi và xử lý finalizable objects.
- Object/resource tồn tại lâu hơn kỳ vọng.
- Backlog các finalizers chờ được xử lý.
- Áp lực memory hoặc tài nguyên ngoài heap tăng.
- Latency khó dự đoán.

Không khẳng định chi phí hoặc số chu kỳ GC **cố định** cho mọi JVM/collector/version. Đo lường thực tế có thể khác, nhưng JDK docs đều cảnh báo performance issues.

### Khi dọn resource chậm

Một finalizer chờ I/O/lock hoặc chạy blocking operation có thể làm các finalization tasks khác chậm theo runtime implementation. Khi backlog tăng, resource leaks trông như “GC không chịu thu gom”, trong khi gốc là cleanup được gắn vào luồng không có timing guarantee.

## 28. Vì sao finalizer có thể deadlock hoặc hang?

Một finalizer chạy không theo thread/ordering mà application chủ động sắp xếp. Nếu nó:
- Chờ một lock đang được thread khác giữ;
- Chờ event từ thread phụ thuộc resource cần release;
- Thực hiện blocking I/O vô hạn;
- Chờ một monitor trong lúc application shutdown;

thì có thể tạo deadlock/hang hoặc backlog.

**Không xây thiết kế kiểu “finalizer A phải chạy trước finalizer B”**: không có thứ tự finalizers được bảo đảm. Một resource graph có dependencies càng cần `close()` explicit với owner rõ và reverse-order scopes.

### Ví dụ phân tích, không chạy

```java
@Override
protected void finalize() throws Throwable {
    waitForOtherComponent(); // Có thể chờ mãi.
}
```

Đây là **legacy anti-pattern snippet**, không phải chương trình runnable. Finalizer không phải chỗ an toàn để đồng bộ/đợi service khác.

## 29. Exception trong `finalize()` không giống exception của `close()`

Trong API finalization:
- Exceptions xảy ra từ finalizer không được báo như exception của một cuộc gọi `close()` từ application method tương ứng.
- Chúng có thể bị bỏ qua theo cơ chế finalization; ứng dụng không có try/catch tại đúng call site để xử lý theo business semantics.
- Lỗi đóng OS resource có thể bị che, khiến vấn đề xuất hiện muộn dưới dạng resource starvation.

Với `close()` explicit:
- Caller có điểm để catch `IOException` hoặc checked exceptions phù hợp.
- Có thể log context, retry nếu hợp lệ, báo lỗi nghiệp vụ hoặc thực hiện recovery.
- Try-with-resources có cơ chế suppressed exceptions để giữ lỗi chính.

**Nếu lỗi giải phóng resource quan trọng**, không đặt nó ở một hook mà caller không có cơ hội xử lý đúng lúc.

## 30. Có thể finalizer bị bỏ qua hoàn toàn

Với những tình huống như:
- Process kết thúc trước khi GC/finalization xử lý object;
- JVM bị terminate/halt;
- GC không cần chạy trong thời gian chương trình tồn tại;
- Runtime policy với finalization bị vô hiệu hóa ở những JDK hỗ trợ;
- Các điều kiện implementation-specific;

application không được kỳ vọng mọi object có finalizer đều được finalizer xử lý.

Điều cần nhớ không phải “finalizer hiếm khi chạy” hay “nó luôn chạy” mà là **API không cung cấp bảo đảm cần thiết** để làm một resource manager đúng đắn.

### Không viết unit test chờ finalizer

Một test `Thread.sleep(1000)` rồi assert counter finalizer tăng không đáng tin. Nó phụ thuộc scheduler/GC/timing và có thể flaky. Kiểm thử `close()` thay vì chờ một cơ chế ngoài control flow của test.

## 31. Object resurrection: finalizer có thể hồi sinh object

Một finalizer có thể vô tình hoặc cố ý công bố `this` vào một long-lived reference, chẳng hạn static field hoặc registry. Khi đó object có thể trở lại trạng thái reachable sau khi finalization bắt đầu.

Sơ đồ:

```text
Trước:
no strong roots ──X──▶ LegacyObject

Trong finalizer:
static Registry.saved = this;

Sau:
GC root → Registry.saved → LegacyObject
```

Đây gọi là **object resurrection**.

### Rủi ro

- Không thể coi “đã có finalization” nghĩa là object vĩnh viễn không được truy cập nữa.
- State của object có thể không đáp ứng invariant đã mong muốn.
- Việc finalizer gọi một lần không giải quyết cleanup ở các lần object lại mất reachability sau resurrection.
- Khó bảo đảm resource đã ở trạng thái mở/đóng hợp lệ.

Theo mô hình finalization truyền thống, finalizer của một instance **không được JVM tự gọi lần hai** chỉ vì instance được resurrect rồi lại trở nên unreachable. Đừng dùng resurrection để quản lý lifecycle.

## 32. Đọc hiểu legacy resurrection — không thực hành như cleanup

```java
class DangerousLegacy {
    static DangerousLegacy saved;

    @Override
    protected void finalize() throws Throwable {
        try {
            saved = this;
        } finally {
            super.finalize();
        }
    }
}
```

**Đây là snippet legacy anti-pattern; không có lệnh chạy hay stdout.** Việc override này có thể khiến `saved` được gán trong hoàn cảnh finalizer chạy, nhưng không thể dự đoán GC/finalization xảy ra khi nào. Không hướng dẫn lập trình viên gọi `System.gc()` để “thử hồi sinh” rồi dựa vào timing.

### Hệ quả thiết kế

Không ghi cleanup logic quan trọng vào phương thức mà bản thân nó có thể làm đối tượng reachable trở lại. Hãy thiết kế `close()` idempotent, kiểm soát state và tránh rò rỉ reference tới partially destroyed resources.

## 33. Finalizer attack và đối tượng xây dựng thất bại

Một vấn đề bảo mật nổi tiếng của finalization là **finalizer attack**: nếu một superclass constructor kiểm tra quyền/validation rồi ném exception, một subclass không đáng tin có thể kế thừa/ghi finalizer theo cách khiến object chưa được khởi tạo thành công vẫn có cơ hội tạo reference ra ngoài.

Đây là lớp vấn đề về **partially initialized objects**, inheritance và khả năng finalizer chạy độc lập với application construction success.

Các bài học:
- Không nghĩ “constructor ném exception” tự ngăn mọi code của object/subclass được chạy sau đó theo cơ chế finalization legacy.
- Không để đối tượng chưa qua validation lọt vào global registry.
- Với security-sensitive class, cân nhắc class final, constructor visibility, factory APIs, invariants và loại bỏ finalization trong hierarchy.
- Khi audit code legacy, tìm override `finalize()` cả ở subclasses và external libraries.

**Không dùng ví dụ khai thác** để quản lý tài nguyên; mục tiêu là nhận diện vì sao một API có tác động bảo mật khó kiểm soát bị khuyến cáo loại bỏ.

## 34. `Cleaner` là gì?

Java cung cấp `java.lang.ref.Cleaner`, dùng các cơ chế phantom reachability/ReferenceQueue để quản lý cleaning actions đã đăng ký.

Một pattern:

```java
private static final Cleaner CLEANER = Cleaner.create();

private final Cleaner.Cleanable cleanable;

// Khi cần explicit release:
cleanable.clean();
```

Điểm thiết yếu:
- Khi gọi `cleanable.clean()` rõ ràng, action có thể chạy **chủ động**, không chờ GC.
- Nếu application quên close, Cleaner **có thể** chạy action sau khi referent đạt trạng thái phantom reachable theo luật của runtime.
- **Không có bảo đảm Cleaner tự chạy trước process exit**, cũng không có deadline.
- Cleaning action nên nhanh, không blocking, có khả năng xử lý đồng thời và không phụ thuộc object state đã inaccessible.
- Cleaning action **không được giữ strong reference tới object đã đăng ký**. Nếu action capture chính referent, nó có thể ngăn object trở thành phantom reachable và không được Cleaner tự động gọi.

**Kết luận:** Cleaner là **safety net**, còn `close()` chủ động vẫn là đường xử lý chính.

## 35. Runnable: Cleaner với explicit close, output xác định

Lưu **`CleanerBackstopDemo.java`**:

```java
import java.lang.ref.Cleaner;
import java.util.concurrent.atomic.AtomicBoolean;

final class NativeLikeHandle implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();

    private static final class State implements Runnable {
        private final int id;
        private final AtomicBoolean released = new AtomicBoolean();

        State(int id) {
            this.id = id;
        }

        @Override
        public void run() {
            if (released.compareAndSet(false, true)) {
                System.out.println("release:" + id);
            }
        }

        boolean isReleased() {
            return released.get();
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    NativeLikeHandle(int id) {
        this.state = new State(id);
        this.cleanable = CLEANER.register(this, state);
    }

    boolean isReleased() {
        return state.isReleased();
    }

    @Override
    public void close() {
        cleanable.clean();
    }
}

public class CleanerBackstopDemo {
    public static void main(String[] args) {
        NativeLikeHandle handle = new NativeLikeHandle(42);

        handle.close();
        handle.close();

        System.out.println(handle.isReleased());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CleanerBackstopDemo.java
java CleanerBackstopDemo
```

Stdout:

```text
release:42
true
```

- `State` là **static nested class**, không capture `NativeLikeHandle`.
- `CLEANER.register(this, state)` theo dõi referent là handle, action là State.
- `close()` gọi `cleanable.clean()`; action được thực thi **nhiều nhất một lần** theo Cleaner contract.
- `AtomicBoolean` tăng rõ idempotency tại resource state layer.
- Output deterministic vì ứng dụng **gọi close trực tiếp**, không đợi GC.
- Đoạn này mô phỏng native handle ID và release log; production cần gọi API release thật, xử lý concurrent close/use và lỗi phù hợp.

### Đừng bắt chước pattern này cho mọi object

`Cleaner` có chi phí và độ phức tạp. Nếu object không giữ resource đặc biệt, chỉ cần GC cho heap memory. Nếu object giữ resource, giải pháp mặc định là `AutoCloseable`/try-with-resources; Cleaner chỉ là lớp phòng vệ bổ sung có chủ đích.

## 36. Anti-pattern: cleaning action capture chính referent

Sai:

```java
final class BrokenHandle {
    private static final java.lang.ref.Cleaner CLEANER =
            java.lang.ref.Cleaner.create();

    private final java.lang.ref.Cleaner.Cleanable cleanable;

    BrokenHandle() {
        cleanable = CLEANER.register(
                this,
                () -> System.out.println(this.toString()));
    }
}
```

Đoạn này **có thể biên dịch** nhưng bị lỗi về lifecycle: lambda giữ reference tới `this`, khiến action giữ referent strong-reachable. Vì referent không đạt phantom reachability như mong muốn, **automatic cleaner action có thể không bao giờ được gọi**.

Sửa:
- Tách state cần cleanup vào một **static nested State** độc lập.
- Đăng ký `CLEANER.register(this, state)`.
- State chỉ giữ native handle/metadata cần giải phóng, **không** trỏ lại referent.
- Bảo đảm action idempotent và không block lâu.
- Luôn có `close()` explicit.

### Không dùng non-static inner class làm State

Một non-static inner class thường mang enclosing-instance association, có thể giữ chính resource owner. JDK Cleaner API khuyến nghị static state để tránh vô tình giữ object tham chiếu ngược.

## 37. `Cleaner` vẫn không giải quyết mọi tình huống

Cleaner **không** cam kết:
- Đóng resource trong thời gian xác định sau last reference.
- Chạy khi process bị kill hoặc application gọi halt.
- Chạy theo thứ tự giữa những objects khác nhau.
- Chạy trước khi external system timeout.
- Hoàn tất mọi queued cleaning actions khi exit.
- Hỗ trợ retry nghiệp vụ hay chuyển lỗi release tới đúng caller như `close()` explicit.

Cleaner action nên tránh ném exception (những exceptions trong asynchronous cleaner action thường bị bỏ qua theo API behavior), tránh giữ lock lâu, tránh phụ thuộc resource khác có thể đã được đóng.

### Khi nào cân nhắc Cleaner?

- Wrapper native/off-heap resource có explicit close làm đường chính.
- Cần safety net cho programmer error quên close.
- Có small cleanup state tách được khỏi referent.
- Chấp nhận cleanup dự phòng không có deadline.
- Có metrics và tests chứng minh explicit close chạy đúng.

Đừng dùng Cleaner để thực hiện transaction commit/rollback, gửi network business event hoặc release resource có SLA time-bound.

## 38. `PhantomReference` và `ReferenceQueue`

Một lựa chọn thấp tầng hơn Cleaner là kết hợp:
- `PhantomReference<T>`;
- `ReferenceQueue<T>`;
- Một bộ theo dõi references/states;
- Một cleanup worker/logic xử lý khi reference được enqueue.

`PhantomReference.get()` **luôn trả null**, không cho truy cập referent thông qua phantom reference. Nó dùng cho post-mortem reachability tracking và cleanup coordination, không phải “weak reference nhưng vẫn get() được”.

So với Cleaner:
- Cần code quản lý queue, strong retention của reference objects và cleanup bookkeeping.
- Cần xử lý thread lifecycle/errors/race conditions.
- Rất dễ tạo leak nếu cleanup state nắm referent.
- Không có timing guarantee.
- Thường chỉ phù hợp cho library/platform code.

**Ở cấp ứng dụng thông thường, hãy dùng `AutoCloseable` trước.**

## 39. Runnable: phantom reference không trả object

Lưu **`PhantomReferenceDemo.java`**:

```java
import java.lang.ref.PhantomReference;
import java.lang.ref.Reference;
import java.lang.ref.ReferenceQueue;

public class PhantomReferenceDemo {
    public static void main(String[] args) {
        Object object = new Object();
        ReferenceQueue<Object> queue = new ReferenceQueue<>();

        PhantomReference<Object> phantom =
                new PhantomReference<>(object, queue);

        System.out.println(phantom.get() == null);

        Reference.reachabilityFence(object);
        System.out.println("no-gc-assumption");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 PhantomReferenceDemo.java
java PhantomReferenceDemo
```

Stdout:

```text
true
no-gc-assumption
```

Không assert rằng queue đã có một phần tử. Enqueue timing tùy GC. `Reference.reachabilityFence(object)` giữ object reachable tới điểm gọi fence trong chương trình, **không** làm object được thu gom sau đó.

## 40. `Reference.reachabilityFence` dùng làm gì?

Một số native-resource wrappers có tình huống tối ưu hóa liveness khiến Java wrapper không còn cần thiết cho Java statements trong khi native work đang diễn ra.

Mốc:

```java
Reference.reachabilityFence(wrapper);
```

giúp đảm bảo wrapper được xem là **strongly reachable đến điểm fence** theo API. Nó **không phải**:
- Lệnh GC;
- Thay thế `close()`;
- Bảo đảm cleanup xảy ra sau fence;
- Cách giữ object mãi mãi.

Nếu resource code đã dùng try-with-resources/close đúng, thường không cần reachabilityFence. Nó là công cụ chuyên biệt cho người viết libraries/native integrations hiểu rõ object/native handle relationship.

## 41. Cách xử lý lỗi cleanup chủ động

Khi `close()` ném `IOException` hoặc exception domain:
- Bảo tồn exception gốc/suppressed exceptions.
- Không swallow các errors làm mất trạng thái transaction quan trọng.
- Gắn context vào log phù hợp và tránh tiết lộ secrets.
- Chỉ retry release nếu API cho phép và operation idempotent/an toàn.
- Đặt resource state `CLOSING`/`CLOSED` nếu cần thread safety.
- Không giữ lock rộng trong lúc cleanup blocking.
- Đừng đưa tất cả lỗi vào một asynchronous finalizer nơi caller không thể xử lý.

### Một lưu ý về idempotency

Nhiều `close()` operations nên idempotent, nhưng `AutoCloseable` không bắt buộc điều đó tuyệt đối. Nếu resource của bạn có thể được đóng ở nhiều code paths, hãy **thiết kế và document rõ** hành vi repeat close, thay vì giả định tất cả libraries giống nhau.

## 42. Runnable: idempotent close có thể test mà không cần GC

Lưu **`IdempotentCloseDemo.java`**:

```java
final class SafeHandle implements AutoCloseable {
    private int releaseCount;
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("closed");
        }
    }

    int releaseCount() {
        return releaseCount;
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            releaseCount++;
        }
    }
}

public class IdempotentCloseDemo {
    public static void main(String[] args) {
        SafeHandle handle = new SafeHandle();

        handle.use();
        handle.close();
        handle.close();

        System.out.println(handle.releaseCount());

        try {
            handle.use();
        } catch (IllegalStateException error) {
            System.out.println(error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 IdempotentCloseDemo.java
java IdempotentCloseDemo
```

Stdout:

```text
1
closed
```

Test xác minh contract **do code chủ động thực hiện**: release một lần và từ chối use-after-close. Không có `System.gc()` hoặc sleep chờ finalizer.

## 43. Resource wrapper có state và ownership rõ

Một wrapper tốt:
- Biết đã mở/đóng.
- Đưa `close()` thành public API rõ.
- Tách ownership khỏi references mượn tạm.
- Ngăn thao tác sau khi close nếu không hợp lệ.
- Đóng các child resources theo thứ tự tương thích dependencies.
- Có strategy khi acquire thất bại giữa chừng.
- Có thể bổ sung Cleaner safety net cho native handle nếu cần.
- Không sử dụng finalizer.

Một wrapper xấu:
- Không thể xác định khi nào resource release.
- Có `finalize()` in log mà không có `close()`.
- Dựa vào việc caller đặt null.
- Bỏ qua exceptions lúc cleanup.
- Giữ references tới global registry nhưng không unregister.

## 44. Runnable: manager quản lý hai child resources

Lưu **`CompositeCloseDemo.java`**:

```java
final class Child implements AutoCloseable {
    private final String name;

    Child(String name) {
        this.name = name;
        System.out.println("open:" + name);
    }

    @Override
    public void close() {
        System.out.println("close:" + name);
    }
}

final class Composite implements AutoCloseable {
    private final Child first;
    private final Child second;

    Composite() {
        first = new Child("first");
        second = new Child("second");
    }

    @Override
    public void close() {
        second.close();
        first.close();
    }
}

public class CompositeCloseDemo {
    public static void main(String[] args) {
        try (Composite composite = new Composite()) {
            System.out.println("using-composite");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CompositeCloseDemo.java
java CompositeCloseDemo
```

Stdout:

```text
open:first
open:second
using-composite
close:second
close:first
```

Ví dụ giới thiệu ý tưởng reverse-order cleanup. Trong production, nếu second.close() ném exception, code cần bảo đảm first.close() vẫn được thử và bảo toàn error details, chẳng hạn sử dụng nested try/finally hoặc một abstraction phù hợp. Đây là điểm rất quan trọng khi viết composite resources.

## 45. Resource acquisition nên dùng scope ngắn nhất có thể

Nếu một DB connection chỉ cần trong một query, đừng giữ nó ở một singleton field rồi chờ GC dọn vào cuối process. Scope càng dài:
- Càng dễ giữ resource khan hiếm không cần thiết.
- Càng khó xác định owner.
- Càng nhiều code paths dẫn đến quên close.
- Càng dễ gặp contention/pool exhaustion.

**Thiết kế tốt:**

```java
try (Connection connection = dataSource.getConnection()) {
    // Một đơn vị công việc ngắn.
}
```

Snippet cần JDBC context thực. Nếu transaction nhiều bước bắt buộc dùng chung connection thì ownership scope dài hơn **có chủ đích**, không phải luôn đóng sau một statement bất chấp transaction boundaries.

## 46. `ShutdownHook` có thay finalizer không?

Java có `Runtime.addShutdownHook(Thread)` cho một số process-wide cleanup scenarios. Nhưng shutdown hook **không phải** giải pháp per-resource/per-request:
- Nó chạy ở lifecycle process shutdown, không phải khi một request xong.
- Không được bảo đảm chạy nếu JVM bị halt hoặc process kill không hợp tác.
- Shutdown sequencing/timeout/threads có thể gây phức tạp.
- Không thay `close()` cho hàng nghìn connections/sessions trong lúc process đang chạy.

Dùng shutdown hook cho những resources **thuộc toàn process** khi phù hợp; per-operation resources vẫn dùng scopes và close chủ động.

### Cẩn thận với `System.exit`

Đừng viết demo finalizer gọi `System.exit()` rồi cố in trước/sau: sẽ có nhiều hành vi implementation-specific. Các bài runnable trong README này chỉ minh họa cleanup do Java control flow điều khiển.

## 47. Vì sao finalize không phù hợp với business logic?

Không đặt trong `finalize()`:
- Commit hoặc rollback transaction.
- Gửi email xác nhận.
- Đổi trạng thái đơn hàng.
- Bắn event nghiệp vụ bắt buộc được gửi.
- Ghi audit record không được mất.
- Release distributed lock có deadline.
- Thực thi payment reversal.
- Gọi remote service để dọn một workflow.

Những hành động này cần **ordering, ownership, retries, idempotency, observability và SLA**; finalization không cung cấp các bảo đảm đó.

Nếu nghiệp vụ cần cleanup dù process chết, phải thiết kế **durable job/outbox/lease/timeout và recovery** phù hợp, không thể chỉ dùng một Java object finalizer.

## 48. Phân biệt heap memory leak với resource leak

Một **heap retention leak**: references còn giữ objects không cần thiết, chẳng hạn static map/listener giữ một graph lớn.

Một **resource leak**: file/socket/native handle/connection không được đóng, ngay cả khi Java object có thể sớm unreachable.

Hai lỗi có thể cùng xảy ra hoặc độc lập:
- Không giữ reference nhưng quên close: OS resource có thể leak cho đến khi runtime/OS cleanup, không có timing an toàn.
- Giữ static reference nhưng resource đã close: heap retention vẫn có thể lớn dù OS handle đã được release.
- Đóng đúng và bỏ reference đúng: giải quyết cả hai lifecycle.

**GC chỉ biết object reachability**, không suy ra deadline nghiệp vụ cần giải phóng file descriptor.

## 49. Điều tra ứng dụng legacy còn `finalize()`

Một quy trình có kiểm soát:

1. Tìm override `finalize()` trong code và dependencies.
2. Ghi lại resource mà mỗi finalizer dự định giải phóng.
3. Kiểm tra nơi acquire, nơi return/truyền reference, owner và exit paths.
4. Xác định có `close()/dispose()/release()` hay chưa.
5. Đánh giá exception behavior và thứ tự cleanup dependencies.
6. Thiết kế explicit lifecycle bằng `AutoCloseable`/try-with-resources hoặc `finally`.
7. Viết regression tests xác minh close đúng cả thành công và lỗi.
8. Nếu resource thấp tầng cần safety net, đánh giá Cleaner với state tách khỏi referent.
9. Xóa override `finalize()` và cập nhật docs/call sites.
10. Kiểm thử dưới JDK mục tiêu và so sánh resource metrics/performance.

### Không chỉ xóa finalizer

Nếu trước đây finalizer là **đường cleanup duy nhất**, xóa nó mà không thêm close/ownership mới có thể khiến leak nghiêm trọng hơn. Migration phải đưa trách nhiệm đóng resource về các code paths có thể kiểm chứng.

## 50. Compiler warning và deprecation annotation

Trong Java 17, khi một class override method deprecated, tùy compiler flags/cách sử dụng, bạn có thể nhận diagnostics về deprecation. Có thể bật:

```bash
javac --release 17 -Xlint:deprecation Example.java
```

Không cung cấp một dòng diagnostic “stdout” cố định bởi warning format và line number tùy compiler/source.

### Đừng coi suppression là remediation

`@SuppressWarnings("deprecation")` chỉ **ẩn cảnh báo** tại phạm vi hiệu lực, không thay đổi:
- Finalizer timing;
- GC behavior;
- Exception handling;
- Các vấn đề bảo mật;
- Khả năng API bị loại bỏ trong tương lai.

Hãy sửa vòng đời resource. Chỉ suppress khi có lý do đặc biệt trong migration code và được code review có giới hạn.

## 51. Code review: phát hiện finalizer với grep

Trong source code, từ khóa có thể xuất hiện dưới những dạng:

```java
@Override
protected void finalize() throws Throwable {
    // ...
}
```

hoặc:

```java
protected void finalize() {
    // ...
}
```

Cần review cả:
- Các method `finalize()` overrides thật.
- Calls tới `System.runFinalization()`/`Runtime.runFinalization()`.
- Các comments hướng dẫn “GC tự đóng resource”.
- Resources acquire mà không được close.
- Cleaners capture referent.
- Inheritance chain có finalization logic ở superclass/subclass.

Một số code có method tên giống `finalize` nhưng signature khác (`finalize(int)`) sẽ không override `Object.finalize()`; không kết luận chỉ theo text search mà không đọc chữ ký.

## 52. Unit test đúng: đếm `close()`

Một test đáng tin có thể dùng fake resource với counter:

- Khi đi hết try body → close count = 1.
- Khi exception trong body → close count = 1.
- Khi có hai resources → close order reverse.
- Nếu close cũng throw → primary/suppressed exceptions đúng.
- Khi constructor thứ hai ném → resource thứ nhất vẫn close.
- Khi client mượn resource → không tự ý close trừ contract.
- Nếu API idempotent → close lặp không release lặp.

**Không** assert “finalize chạy trong 100 ms”, “System.gc khiến reference cleared” hay “after test heap giảm đúng N bytes”. Những điều này không phải contract cần bảo vệ.

## 53. Runnable: đo cleanup theo exception path

Lưu **`CloseContractTestDemo.java`**:

```java
final class CountingHandle implements AutoCloseable {
    private int closes;

    int closes() {
        return closes;
    }

    @Override
    public void close() {
        closes++;
    }
}

public class CloseContractTestDemo {
    public static void main(String[] args) {
        CountingHandle handle = new CountingHandle();

        try (handle) {
            throw new IllegalArgumentException("error");
        } catch (IllegalArgumentException ignored) {
            // Đường cleanup của try-with-resources vẫn xảy ra.
        }

        if (handle.closes() != 1) {
            throw new AssertionError("close count");
        }

        System.out.println("CLOSE_CONTRACT_PASS");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 CloseContractTestDemo.java
java CloseContractTestDemo
```

Stdout:

```text
CLOSE_CONTRACT_PASS
```

Ví dụ Java 17 dùng `try (handle)`, hợp lệ vì variable `handle` effectively final. `close` chạy trước catch block và test assertion.

## 54. Tại sao Cleaner không bằng explicit `try-with-resources`?

| Tiêu chí | `try-with-resources` + `close()` | `Cleaner` khi không close |
| --- | --- | --- |
| Thời điểm cleanup | Gắn với cấu trúc chương trình, khi scope kết thúc | Phụ thuộc reachability/GC/background processing |
| Caller biết cleanup xảy ra? | Có, control flow rõ | Không thể dự đoán deadline |
| Thứ tự nhiều resources | Reverse declaration order theo ngôn ngữ | Không thể cam kết thứ tự GC callbacks |
| Lỗi cleanup | Có thể được catch/suppressed | Asynchronous errors khó truyền tới caller |
| Chạy trước shutdown? | Khi chương trình đi qua scope bình thường | Không bảo đảm |
| Dùng cho transaction | Có thể dùng để release sau commit/rollback flow rõ | Không phù hợp |
| Là fallback quên close? | Không phải GC fallback | Có thể giúp trong một số wrappers |
| Complexity | Thường thấp | Cao hơn, cần state không capture referent |

**Cleaner không bị cấm**, nhưng cách sử dụng tốt thường là **`AutoCloseable` là cơ chế chính, Cleaner hỗ trợ phòng vệ**.

## 55. Cách giữ cleanup state độc lập với object

Khi dùng Cleaner, cần phân biệt:

```text
Cleaner ──▶ Cleanable registration ──▶ State ──▶ Native handle
                   │
                   └──phantom tracking──▶ Resource owner
```

State không được:
- Giữ reference tới chính Resource owner.
- Là non-static inner class tự capture owner.
- Là lambda truy cập `this`/instance methods của owner.
- Giữ một child object có reference ngược về owner làm hidden cycle strong.

State **được phép** giữ các thông tin đủ để release tài nguyên: ID/descriptor/native pointer và synchronization state. Object owner thường giữ `Cleanable` để gọi `clean()` trong explicit `close()`.

### Tách metadata và ownership

Nếu State chứa một `Logger` là singleton, hoặc utility object khác, xét liệu graph đi ngược về owner không. Khi nghi ngờ, dùng heap graph analysis thay vì tin rằng một lambda “trông ngắn” không capture this.

## 56. Concurrent close và Cleaner action

Một resource wrapper có thể bị sử dụng bởi nhiều threads, trong khi một thread gọi `close()` và một Cleaner background task dự định release. Thiết kế cần xem:
- Trạng thái release chỉ chuyển **một lần** (`AtomicBoolean`, CAS hoặc locking phù hợp).
- Không use native handle sau release.
- Race giữa close và in-flight operations.
- Memory visibility và thread safety.
- Lỗi release có được report/record ở explicit close path không?
- Cleanup action có bị blocking không?
- Có cần `reachabilityFence` để giữ wrapper sống hết native operation không?

Không thể chỉ dựa vào `final` field hoặc `volatile boolean` như một giải pháp đầy đủ cho concurrent resource safety. Các operations phải theo invariant và API contract cụ thể.

## 57. Finalization và object graph

Đừng dự đoán thứ tự cleanup dựa trên cấu trúc:

```text
Parent ──field──▶ Child
```

Việc Parent giữ Child không tạo quy tắc “Child.finalize trước Parent.finalize” hay ngược lại. Một finalizer có thể truy cập objects khác đang ở trạng thái lifecycle khó đoán.

Đây là lý do:
- Có ownership explicit thì Parent.close có thể gọi Child.close.
- Dùng try-with-resources có reverse-order close cho resources trực tiếp.
- Không cần graph finalization traversal custom.
- Tránh phụ thuộc vào finalizers để đóng các resources có dependency order.

## 58. Phân biệt `Cleaner` với `WeakReference`

`WeakReference<T>` chủ yếu giúp không giữ referent mạnh chỉ vì cache/reference đó tồn tại. `weak.get()` có thể trả null khi referent được collector xử lý.

`Cleaner` quản lý registered cleanup actions khi reachability đổi. Nếu muốn giải phóng native handle, hành động dọn dẹp cần có independent state và rõ ràng về release semantics.

Không dùng `WeakReference` như một “callback đóng resource” tự động: một weak reference đơn thuần không có logic release. Nếu triển khai riêng với `ReferenceQueue`, bạn phải quản lý queue/references/cleanup lifecycle và vẫn không có deadline.

**Không phải mọi ứng dụng cần weak/phantom refs.** Explicit ownership/close là lựa chọn dễ hiểu và an toàn hơn cho phần lớn resource use cases.

## 59. Sai lầm: tin Java “có GC nên không cần close”

GC tự quản lý **heap memory** của unreachable objects. Nó không có hiểu biết nghiệp vụ:
- “Kết thúc request thì trả DB connection về pool”.
- “Upload đã xong thì đóng file ngay”.
- “Timeout thì release distributed lock”.
- “Transaction thất bại thì rollback”.
- “Thay user thì gỡ listener cũ”.

Những sự kiện đó do code application biết. Nếu bỏ trách nhiệm cleanup cho GC, resource có thể giữ lâu không cần thiết và gây sự cố dù heap không hề đầy.

### Câu hỏi cần hỏi

Thay vì “object này khi nào bị GC?”, hỏi:
1. Resource được acquire ở đâu?
2. Đơn vị công việc nào sở hữu nó?
3. Kết thúc đơn vị đó lúc nào?
4. Tại điểm nào `close/release` phải chạy?
5. Các nhánh lỗi/return/cancel có cùng cleanup contract không?

## 60. Anti-pattern: finalizer chỉ in log “đã đóng”

Một demo sai thường tạo object với `finalize() { println("closed"); }`, gọi `System.gc()`, rồi kết luận:
- Finalizer luôn chạy;
- Đó là dấu hiệu resource đã giải phóng;
- Có thể dùng để close thực tế;
- Lúc JVM exit thì chắc chắn gọi.

Tất cả kết luận ấy đều không đáng tin.

Nếu muốn dạy vòng đời resource, hãy dùng **program với `close()` deterministic**, in `open/use/close` bằng try-with-resources. Không đưa output timing của finalizer thành “stdout chính xác”.

## 61. Những warning khi migration JDK

Khi chuyển từ Java 17 sang JDK khác:
- Xem JEP 421 và release notes của JDK đích.
- Tìm usages trong code tự viết và thư viện cũ.
- Đảm bảo không có business logic phụ thuộc finalization.
- Chạy static analysis/lint cho deprecated APIs.
- Dùng memory/file descriptor/connection metrics để xác nhận migration.
- Nếu JDK hỗ trợ disable finalization, thử trong test/staging để tìm dependencies (theo hướng dẫn **đúng version**; không sao chép option của JDK 18 vào lời khuyên chạy Java 17 nếu option không được hỗ trợ).
- Document resource ownership trong APIs được phát hành.

**Rất quan trọng:** command-line flag `--finalization=disabled` được giới thiệu cùng thay đổi ở JDK 18; **không tuyên bố đây là flag tương thích Java 17**.

## 62. Bài tập 1 — Đúng mốc deprecation

Hỏi: Java 17 đã loại bỏ `Object.finalize()` chưa?

**Đáp án:** Chưa. Trong Java 17 API này đã deprecated từ Java 9. Deprecation **for removal** của finalization được đưa vào JDK 18 theo JEP 421.

## 63. Bài tập 2 — Gán `null`

Hỏi: `resource = null;` có làm resource được close ngay không?

**Đáp án:** Không. Đó chỉ là reassignment một reference; còn aliases/GC timing và không có lời gọi close nào.

## 64. Bài tập 3 — Cuối block

Hỏi: biến object ra khỏi lexical scope có bảo đảm `finalize()` được chạy ngay không?

**Đáp án:** Không. Scope khác liveness/reachability và GC không có deadline này.

## 65. Bài tập 4 — `System.gc()`

Hỏi: Sau `System.gc()`, có thể assert finalizer chắc chắn in một dòng không?

**Đáp án:** Không. GC/finalization scheduling không có bảo đảm thời gian hoặc chắc chắn thực hiện theo ý test.

## 66. Bài tập 5 — File descriptor

Một method mở file để đọc vài dòng rồi trả về. Nên dùng `finalize()` hay try-with-resources?

**Đáp án:** Try-with-resources với BufferedReader/InputStream/Stream có close contract. Đóng khi công việc đọc hoàn thành.

## 67. Bài tập 6 — DB connection pool

Hỏi: JDBC Connection trong pool nên chờ JVM GC để trả về pool không?

**Đáp án:** Không. Dùng connection.close theo pool/library contract và try-with-resources đúng unit-of-work.

## 68. Bài tập 7 — Exception trong body

Nếu body throw exception, try-with-resources có đóng resource đã acquire thành công không?

**Đáp án:** Có theo Java control-flow rules. Exceptions từ close có thể bị suppress nếu body có primary exception.

## 69. Bài tập 8 — Thứ tự hai close

`try (A a = ...; B b = ...) { ... }`. Resource nào được close trước?

**Đáp án:** B trước A theo reverse declaration order.

## 70. Bài tập 9 — Lỗi close

Body throw `IOException("work")` và close throw `IOException("close")`. Caller nhận lỗi nào là primary?

**Đáp án:** Thường lỗi “work” là primary; lỗi “close” ở `getSuppressed()`, theo try-with-resources rules.

## 71. Bài tập 10 — Constructor acquisition failure

Tạo A thành công, constructor B throw, body không chạy. A có được close không?

**Đáp án:** Có nếu A nằm trong try-with-resources resource spec. Riêng B constructor chịu trách nhiệm cleanup phần acquisition bên trong nó khi construction thất bại.

## 72. Bài tập 11 — `AutoCloseable`

Hỏi: mọi `AutoCloseable.close()` đều mặc nhiên idempotent không?

**Đáp án:** Không phải contract bắt buộc chung. Nên đọc API/thiết kế implementation; nhiều resources thực tế hỗ trợ repeated close nhưng không được tự suy ra.

## 73. Bài tập 12 — `Closeable`

Hỏi: `Closeable` liên quan `AutoCloseable` thế nào?

**Đáp án:** Closeable extends AutoCloseable, đặc biệt cho I/O và dùng IOException/close behavior của API. Cả hai đều hoạt động trong try-with-resources.

## 74. Bài tập 13 — Mã di sản

Một class có override `finalize()` gọi `socket.close()`. Có nên chỉ xóa override không?

**Đáp án:** Không. Trước hết thêm explicit ownership/close paths; sau đó mới bỏ finalizer. Xóa không thay thế có thể làm leak nặng hơn.

## 75. Bài tập 14 — `Cleaner`

Cleaner có tự tạo deadline cleanup khi object không còn reachable không?

**Đáp án:** Không. Automatic cleaning phụ thuộc GC/reachability; nên coi là safety net.

## 76. Bài tập 15 — Explicit Cleaner

`Cleanable.clean()` được gọi trong `close()`. Có phải chờ GC không?

**Đáp án:** Không, lời gọi explicit có thể chạy action chủ động, theo Cleaner contract; action không được chạy lặp cho cùng registration.

## 77. Bài tập 16 — Capture this

Cleaner action viết `() -> release(this.handle)`. Có nguy cơ gì?

**Đáp án:** Lambda capture owner `this`, giữ referent reachable và ngăn automatic cleaning. Tách static State giữ handle độc lập.

## 78. Bài tập 17 — Non-static inner State

Có nên dùng non-static inner class làm Cleaner State nếu nó implicitly giữ outer instance?

**Đáp án:** Không. Nguy cơ giữ referent và khiến cleaner không tự chạy. Dùng static nested State.

## 79. Bài tập 18 — PhantomReference.get()

Hỏi: `phantom.get()` trả được object gốc sau GC không?

**Đáp án:** Không, trả null theo API; không dùng như getter để cleanup.

## 80. Bài tập 19 — `reachabilityFence`

Có phải `Reference.reachabilityFence` gọi GC hoặc close?

**Đáp án:** Không. Nó giữ referent strong-reachable tới điểm fence, không phải resource release.

## 81. Bài tập 20 — Object resurrection

Finalizer lưu `this` vào static field. Điều gì có thể xảy ra?

**Đáp án:** Object có thể trở lại reachable nếu finalizer chạy; làm phức tạp lifecycle và bảo mật. Không dùng để quản lý resources.

## 82. Bài tập 21 — Finalizer exceptions

Lỗi trong finalizer có thể được xử lý chắc chắn tại caller như `close()` throws IOException không?

**Đáp án:** Không. Finalization diễn ra ngoài caller control flow; errors có thể bị bỏ qua theo API semantics.

## 83. Bài tập 22 — `final` class

Hỏi: `final class Resource` có tự close khi local variable hết scope không?

**Đáp án:** Không. `final` hạn chế subclassing, không liên quan automatic resource release.

## 84. Bài tập 23 — `finally`

Nếu không thể dùng AutoCloseable ngay, `finally` có thể làm cleanup không?

**Đáp án:** Có, trong phạm vi control flow thích hợp; cần cẩn thận khi cleanup tự throw và bảo tồn exception gốc.

## 85. Bài tập 24 — Resource ownership

Callee nhận InputStream do caller sở hữu, chỉ dùng để parse. Callee có được tự close không?

**Đáp án:** Chỉ khi contract chuyển ownership/quy định rõ. Nếu chỉ borrow stream, callee thường không close resource của caller.

## 86. Bài tập 25 — Cleaner ở shutdown

Cleaner có bảo đảm chạy toàn bộ actions trước process exit không?

**Đáp án:** Không. API nói behavior ở `System.exit` implementation-specific và không bảo đảm mọi action chạy.

## 87. Bài tập 26 — Performance

Một finalizer block vô hạn có thể gây vấn đề gì?

**Đáp án:** Có thể gây chậm backlog, hang/deadlock hoặc giữ resources. Không đặt blocking business work trong finalizers/cleaning actions.

## 88. Bài tập 27 — Heap leak và resource leak

Một object đã close socket nhưng còn trong static cache, liệu đã hết mọi vấn đề chưa?

**Đáp án:** Socket resource có thể đã release, nhưng heap graph còn giữ trong cache, có thể là heap retention leak riêng.

## 89. Bài tập 28 — Resource vẫn mở, object unreachable

Nếu application làm mất references tới file handle nhưng chưa close, có bảo đảm file sẽ được đóng tức thì không?

**Đáp án:** Không. Mất strong path không thay explicit close contract, GC/finalization không có deadline.

## 90. Bài tập 29 — Exception test

Một unit test muốn kiểm tra cleanup khi failure. Nên quan sát finalizer count hay close count?

**Đáp án:** Close count/state theo deterministic control flow, gồm suppression và thứ tự nếu cần. Không test GC timing.

## 91. Bài tập 30 — Migration hoàn chỉnh

Bạn tìm thấy `finalize()` trong wrapper native handle, cần làm gì?

**Đáp án:** Thiết kế explicit AutoCloseable/ownership; bảo đảm constructor thất bại có cleanup, idempotency/thread safety, tests; cân nhắc Cleaner State độc lập làm backup nếu cần; loại bỏ override finalizer và xác nhận runtime metrics.

## 92. Trắc nghiệm Đúng/Sai tổng hợp

1. Java 17 đã xóa `Object.finalize()`.
2. `Object.finalize()` deprecated từ Java 9.
3. JDK 18 đánh dấu finalization deprecated for removal.
4. Khi local ra khỏi scope, `finalize()` luôn chạy lập tức.
5. `System.gc()` bảo đảm close tất cả resource wrappers.
6. `try-with-resources` gọi `close()` khi rời scope theo Java control flow.
7. `AutoCloseable` có thể được dùng với custom class.
8. Nếu hai resources nằm trong một try, close theo thứ tự đảo ngược khai báo.
9. Cleaner action được phép capture referent mà không có hậu quả.
10. Cleaner có deadline tự động release file descriptor.
11. `PhantomReference.get()` trả referent object.
12. Finalizer có nguy cơ object resurrection.
13. `final` reference và `finalize()` là cùng một cơ chế.
14. `Closeable` extends `AutoCloseable`.
15. Đóng resource chủ động có thể xảy ra khi Java wrapper object vẫn reachable.

**Đáp án:** 1 sai; 2 đúng; 3 đúng; 4 sai; 5 sai; 6 đúng; 7 đúng; 8 đúng; 9 sai; 10 sai; 11 sai; 12 đúng; 13 sai; 14 đúng; 15 đúng.

## 93. Bảng lỗi thường gặp

| Lỗi/nhận định sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “GC tự quản lý mọi tài nguyên” | GC chủ yếu reclaim memory, không biết deadline OS resource | `close()` explicit theo ownership |
| “`finalize()` chạy ngay khi null” | Không có GC/finalization deadline | Try-with-resources |
| “`System.gc()` là cleanup API” | Chỉ request/hint, không phải đảm bảo | Đóng resource chủ động |
| “Java 17 đã remove finalize” | Java 17 còn deprecated API | Phân biệt Java 9/17 và JDK18 JEP421 |
| “`final` tương đương finalizer” | Modifier không gọi cleanup | Dùng AutoCloseable |
| “`finally` là GC callback” | Finally thuộc control flow | Hiểu exception unwinding |
| “Nhớ gọi finalize thủ công là đủ” | Không phải release contract, dễ double cleanup | API `close()` |
| “Close sau cùng cũng được” | File descriptors/DB slots có deadline/giới hạn riêng | Scope resource ngắn, rõ owner |
| “Cleaner thay try-with-resources” | Automatic Cleaner nondeterministic | Cleaner chỉ backup nếu cần |
| “Cleaner lambda capture this an toàn” | Có thể giữ referent strong reachable | Static State độc lập |
| “Một lỗi cleanup không quan trọng” | Có thể giấu resource leak/transaction state | Catch/report, suppressed exceptions |
| “Hai resources close theo thứ tự khai báo” | Java close đảo thứ tự | Thiết kế dependencies đúng |
| “AutoCloseable luôn idempotent” | Không bắt buộc chung | Document và implement phù hợp |
| “Resource mới fail thì mọi resource đã mở không được dọn” | Try-with-resources đóng resources đã khởi tạo | Bọc acquisitions trong resource list |
| “Constructor fail mà try-with-resources tự đóng object chưa tạo” | Không có resource variable hoàn tất | Cleanup partial acquisition trong constructor/factory |
| “Process exit gọi hết cleaners” | Không có guarantee | Đừng giao nghiệp vụ cho GC |
| “Không cần kiểm thử close, JVM sẽ lo” | GC không xác định | Test explicit close count/state |
| “Xóa finalizer là sửa xong leak” | Có thể bỏ đường cleanup duy nhất | Chuyển cleanup sang explicit path trước |
| “Shutdown hook thay per-request close” | Chạy quá muộn, không chắc mọi kiểu shutdown | Mỗi owner close theo scope |

## 94. Checklist thay `finalize()` bằng thiết kế an toàn

- [ ] Đã tìm mọi override `finalize()` trong code/thư viện liên quan.
- [ ] Biết JDK 17 deprecated từ 9; JDK 18 JEP421 for removal.
- [ ] Không xây functionality mới phụ thuộc finalizer.
- [ ] Đã xác định tài nguyên ngoài heap mà object giữ.
- [ ] Đã phân biệt resource lifetime và Java object reachability.
- [ ] Có rõ owner cho mỗi resource không?
- [ ] Resource có thể implement `AutoCloseable`/`Closeable`?
- [ ] Nếu có, ưu tiên `try-with-resources` tại phạm vi nhỏ phù hợp?
- [ ] Nếu không, có `try/finally` hoặc adapter giải phóng rõ?
- [ ] Đã kiểm thử cleanup trên success path?
- [ ] Đã kiểm thử cleanup trên exception path?
- [ ] Đã kiểm thử reverse-order close cho nhiều resources?
- [ ] Đã kiểm tra suppressed exception behavior?
- [ ] Đã xử lý partial acquisition failure?
- [ ] Đã tránh double close/use-after-close không hợp lệ?
- [ ] Có contract idempotency và thread safety rõ nếu cần?
- [ ] Mọi borrower/owner biết ai có quyền close?
- [ ] Không gọi `System.gc()`/`runFinalization()` để sửa leak?
- [ ] Không dùng `@SuppressWarnings("deprecation")` như giải pháp chính?
- [ ] Nếu dùng Cleaner, đó chỉ là backstop?
- [ ] Cleaner State là static/độc lập, không capture referent?
- [ ] Cleaning action đủ nhanh, ít blocking và không phụ thuộc thứ tự?
- [ ] Không giả định Cleaner sẽ chạy trước JVM exit?
- [ ] Nếu dùng `PhantomReference`, đã quản lý queue và bookkeeping đúng?
- [ ] Nếu dùng `reachabilityFence`, hiểu nó không phải cleanup call?
- [ ] Không đưa business-critical event/transaction vào finalizer?
- [ ] Có metrics cho file handles/connections/native allocations?
- [ ] Đã xem xét resource leaks khác với heap retention leaks?
- [ ] Có test không phụ thuộc GC timing?
- [ ] Có đánh giá behavior của JDK thực tế khi nâng phiên bản?
- [ ] Đã gỡ đường `finalize()` sau khi explicit lifecycle hoạt động?
- [ ] Có tài liệu ownership/cleanup lifecycle dành cho caller?
- [ ] Có review security/constructor failure/resurrection ở legacy classes?

## 95. Tổng kết

Trong **Java 17**, `Object.finalize()` vẫn xuất hiện trong API nhưng đã **deprecated từ Java 9**. **JDK 18 / JEP 421** tiếp tục đánh dấu finalization **deprecated for removal**. Cơ chế finalizer không cung cấp các bảo đảm mà một resource manager cần: không có thời điểm gọi xác định, không có thứ tự, khó quan sát lỗi, có thể tăng overhead và có nguy cơ deadlock, hồi sinh đối tượng hoặc lỗi bảo mật.

Để quản lý tài nguyên:
1. Xác định rõ **ai sở hữu resource**.
2. **Đóng chủ động** bằng `AutoCloseable.close()`.
3. Ưu tiên `try-with-resources` để cleanup ngay cả khi có exception.
4. Xử lý exception suppression, constructor failure và repeated close đúng contract.
5. Với wrapper native/off-heap hiếm gặp, **Cleaner** có thể làm safety net với State không capture referent — **không thay explicit close**.
6. Kiểm thử close count/state và resource metrics, **không** dựa vào `System.gc()` hay finalizer timing.

**Câu nhớ:** *Đừng chờ garbage collector biết công việc của bạn đã xong. Chính code sở hữu tài nguyên phải đóng nó khi không còn cần nữa.*

## 96. Tài liệu chính thức

- **Java SE 17 `Object.finalize()`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#finalize()
- **Java SE 17 `AutoCloseable`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html
- **Java SE 17 `Closeable`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html
- **Java SE 17 `Cleaner`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html
- **Java SE 17 `PhantomReference`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/PhantomReference.html
- **Java SE 17 `Reference.reachabilityFence()`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html#reachabilityFence(java.lang.Object)
- **JLS §14.20.3 — try-with-resources**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3
- **JLS §12.6 — Finalization of Class Instances**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.6
- **JEP 421 — Deprecate Finalization for Removal (JDK 18)**: https://openjdk.org/jeps/421
