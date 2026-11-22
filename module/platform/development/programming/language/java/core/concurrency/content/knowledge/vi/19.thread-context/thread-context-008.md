# Scoped Values (preview ở Java 21) để chia sẻ context bất biến

## 1. Bài toán: truyền ngữ cảnh qua nhiều lời gọi mà không làm bẩn chữ ký hàm

Trong Java, cách rõ ràng nhất để chuyển dữ liệu là truyền tham số:

```java
void handle(RequestContext context) {
    validate(context);
}
```

Tuy nhiên, khi một hàm xử lý đi qua nhiều tầng thư viện, có thể hàng loạt phương thức trung gian phải nhận rồi chuyển tiếp một giá trị mà chính chúng không dùng: mã định danh tác vụ, thông tin người dùng đã xác thực, locale hay thông số truy vết. `ThreadLocal` giải quyết việc truyền ngầm đó nhưng mang các vấn đề về khả năng thay đổi giá trị từ bất cứ callee nào, vòng đời cần `remove()` và chi phí khi có rất nhiều virtual threads.

**`ScopedValue<T>`** cho phép hàm gọi (*caller*) ràng buộc một khóa với một value **trong phạm vi thực thi được giới hạn**, rồi các hàm được gọi trực tiếp hoặc gián tiếp có thể đọc value qua khóa đó. Khi phạm vi kết thúc, binding tự động kết thúc hoặc khôi phục binding bên ngoài. Đây là mô hình truyền ngữ cảnh **một chiều, hướng đọc**: callee chỉ đọc binding đã được caller cung cấp, trừ khi chính callee chủ động mở một scope con với binding khác.

Bài tập trung vào **Java concurrency và ngữ cảnh luồng nói chung**, đặc biệt các tác vụ dùng virtual threads. Cơ chế không phụ thuộc Spring.

### Tình trạng API theo phiên bản Java

| Phiên bản | Trạng thái `ScopedValue` | Hệ quả thực hành |
| --- | --- | --- |
| Java 21 | Preview lần đầu, JEP 446 | Cần `--enable-preview` khi biên dịch và chạy; dùng API đúng tài liệu Java 21. |
| Java 22–24 | Các vòng preview tiếp theo | API có thể thay đổi; cần đọc JavaDoc đúng phiên bản. |
| Java 25 trở lên | API chuẩn, JEP 506 | Không cần bật preview riêng cho `ScopedValue`. |
 
Trong bài, mọi ví dụ được đánh dấu **Java 21** đều áp dụng API preview của JDK 21 và dùng lệnh chạy chính xác. Những đoạn ghi **Java 25+** dùng API chính thức; không trộn tùy tiện các phiên bản trong một ví dụ.

## 2. Cơ chế: khóa, binding và dynamic scope

Giả sử khai báo:

```java
private static final ScopedValue<String> TRACE_ID = ScopedValue.newInstance();
```

`TRACE_ID` chỉ là **khóa (key)** dùng để tra giá trị. Nó không phải một biến String được cập nhật toàn cục. Khi chạy:

```java
ScopedValue.runWhere(TRACE_ID, "REQ-42", () -> handleRequest());
```

JDK 21 sẽ thực thi `handleRequest()` với `TRACE_ID` được bind thành `"REQ-42"` ở thread hiện tại. Mọi lời gọi sâu hơn trong chuỗi gọi đó có quyền truy cập khóa đều có thể gọi `TRACE_ID.get()`. Khi `runWhere` trả về hoặc ném exception, binding được gỡ và binding trước đó (nếu có) được khôi phục. Không cần `try/finally/remove` cho việc cleanup binding.

Phạm vi này là **dynamic scope**: được xác định bằng các phương thức thực sự chạy bên trong lời gọi ràng buộc, kể cả callback, chứ không đơn giản là các dấu ngoặc của một khối lexical bất kỳ.

Một minh họa đường đi:

```text
Thread hiện tại
  |
  +-- TRACE_ID chưa được bind
  |
  +-- runWhere(TRACE_ID, "REQ-42", () -> service())
  |     |
  |     +-- service()
  |           |
  |           +-- repository()  -> TRACE_ID.get() == "REQ-42"
  |           |
  |           +-- callback()    -> TRACE_ID.get() == "REQ-42"
  |
  +-- kết thúc scope: TRACE_ID trở về trạng thái trước đó
```

**Không đồng nhất binding bất biến với object bất biến.** API không cung cấp thao tác `TRACE_ID.set(...)` để sửa binding hiện có, nhưng nếu bind một `ArrayList` hay object có setter, code nhận được tham chiếu vẫn có thể thay đổi **bên trong object**. Muốn thật sự dùng “context bất biến”, hãy bind `String`, record chứa các giá trị bất biến, hoặc object được thiết kế immutable/defensive copy.

## 3. Những API chính trong Java 21

| API | Tác dụng |
| --- | --- |
| `ScopedValue.newInstance()` | Tạo key mới, ban đầu chưa bind trong mọi thread. |
| `ScopedValue.runWhere(key, value, runnable)` | Bind value và chạy `Runnable` trong phạm vi đó. |
| `ScopedValue.callWhere(key, value, callable)` | Bind value rồi trả về kết quả của `Callable`; có thể lan truyền checked exception. |
| `ScopedValue.getWhere(key, value, supplier)` | Bind value rồi trả về kết quả của `Supplier`. |
| `ScopedValue.where(key, value).run(runnable)` | Tạo `Carrier` của một hoặc nhiều binding và thực thi với chúng. |
| `ScopedValue.where(k1,v1).where(k2,v2).call(callable)` | Bind nhiều key trong một scope. |
| `key.get()` | Lấy value đang bind; ném `NoSuchElementException` nếu chưa bind. |
| `key.isBound()` | Kiểm tra key có binding trong thread hiện tại không. |
| `key.orElse(fallback)` | Lấy binding hoặc fallback nếu chưa bind. |
| `key.orElseThrow(supplier)` | Ném exception được cung cấp nếu key chưa bind. |

Trên Java 21, `ScopedValue` và `ScopedValue.Carrier` đều là **preview API**, phải bật preview cho cả compile và run. `Carrier` là tập mapping bất biến: nối `where(...)` tạo carrier mới; không làm thay đổi carrier đã có.

**Bảo mật và thiết kế API:** chỉ những đoạn code truy cập được đối tượng khóa mới có thể gọi `get()`. Vì vậy, khóa thường được giữ trong trường `private static final` và chỉ mở các helper đọc phù hợp với nhu cầu. Công khai key ra toàn ứng dụng sẽ tăng các vị trí có thể truy cập context.

## 4. Ví dụ đầy đủ Java 21: binding, gọi sâu, rebinding và khôi phục

Lưu dưới tên `ScopedValueDemo.java`:

```java
public class ScopedValueDemo {
    private static final ScopedValue<Context> CONTEXT =
            ScopedValue.newInstance();

    record Context(String traceId, String userId) {}

    static String readInDeepMethod() {
        return CONTEXT.get().traceId();
    }

    static String service() {
        return "trace=" + readInDeepMethod();
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Before: " + CONTEXT.isBound());

        String result = ScopedValue.where(
                CONTEXT, new Context("REQ-42", "an")).call(() -> {

            System.out.println("Outer: " + service());

            String nested = ScopedValue.where(
                    CONTEXT, new Context("REQ-99", "an"))
                    .call(ScopedValueDemo::service);

            System.out.println("Inner: " + nested);
            System.out.println("Restored: " + service());
            return "ok";
        });

        System.out.println("Result: " + result);
        System.out.println("After: " + CONTEXT.isBound());
    }
}
```

Dùng **JDK 21** để biên dịch và chạy:

```bash
javac --enable-preview --release 21 -encoding UTF-8 ScopedValueDemo.java
java --enable-preview ScopedValueDemo
```

Biên dịch có thể phát thông báo rằng chương trình dùng preview API; đó là thông báo dự kiến. **Stdout từ chương trình**:

```text
Before: false
Outer: trace=REQ-42
Inner: trace=REQ-99
Restored: trace=REQ-42
Result: ok
After: false
```

Giải thích:

1. Khi chưa vào scope, `CONTEXT.isBound()` là `false`.
2. `Carrier.call(...)` bind record cho thread hiện tại, các hàm `service()` và `readInDeepMethod()` đọc được `REQ-42` dù không có tham số context.
3. Scope lồng nhau **rebind** cùng key thành `REQ-99`; nó không sửa record ngoài.
4. Khi scope con kết thúc, `REQ-42` được khôi phục. Khi scope ngoài kết thúc, key lại không bind.
5. Kết quả của `Callable` được trả về từ `call`. Không có bước xóa thủ công.

Record `Context` dùng các thành phần `String` bất biến; nếu record giữ `List`, `Map` hoặc các object mutable khác, cần cân nhắc `List.copyOf`, `Map.copyOf` hay một dạng defensive copy thích hợp.

## 5. Exception cũng kết thúc scope đúng cách

Khi tác vụ bên trong scope ném exception, cơ chế ràng buộc vẫn được tháo/khôi phục. Ví dụ Java 21, lưu `ScopedValueFailureDemo.java`:

```java
public class ScopedValueFailureDemo {
    private static final ScopedValue<String> TRACE =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        System.out.println("Before: " + TRACE.isBound());

        try {
            ScopedValue.runWhere(TRACE, "REQ-error", () -> {
                System.out.println("During: " + TRACE.get());
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException e) {
            System.out.println("Caught: " + e.getMessage());
        }

        System.out.println("After: " + TRACE.isBound());
    }
}
```

```bash
javac --enable-preview --release 21 -encoding UTF-8 ScopedValueFailureDemo.java
java --enable-preview ScopedValueFailureDemo
```

```text
Before: false
During: REQ-error
Caught: boom
After: false
```

Việc khôi phục binding được thực hiện bởi cơ chế scope, kể cả lúc exception được ném. Điều đó giải quyết một lỗi thường gặp ở `ThreadLocal`: bỏ quên `remove()` sau một nhánh trả về sớm hoặc exception. Tuy nhiên, **ScopedValue không tự động đóng tài nguyên** mà value trỏ đến. Nếu value chứa kết nối, file hay tài nguyên `AutoCloseable`, cần quản lý việc đóng riêng bằng `try-with-resources` hoặc lifecycle rõ ràng.

## 6. Khả năng nhìn thấy giữa các thread và structured concurrency

Binding của `ScopedValue` theo **thread đang chạy**, không phải một global variable. Một thread khác chạy độc lập sẽ không tự nhiên thấy binding của thread hiện tại.

**Đặc điểm quan trọng:** `ScopedValue` có thể được **kế thừa có cấu trúc** bởi các thread con được tạo bằng `StructuredTaskScope.fork(...)` bên trong scope phù hợp. Cấu trúc parent-child cho phép các child threads cùng chia sẻ **tham chiếu tới context bất biến**, không cần sao chép một ThreadLocalMap đầy đủ cho mỗi child.

Trong **Java 21**, `StructuredTaskScope` cũng là **preview API** (JEP 453). Cần bật `--enable-preview`. Đoạn sau dùng chính kiểu API Java 21; lưu `ScopedValueChildrenDemo.java`:

```java
import java.util.concurrent.StructuredTaskScope;

public class ScopedValueChildrenDemo {
    private static final ScopedValue<String> TRACE =
            ScopedValue.newInstance();

    static String work(String name) {
        return name + "=" + TRACE.get();
    }

    public static void main(String[] args) throws Exception {
        String joined = ScopedValue.where(TRACE, "REQ-7").call(() -> {
            try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
                var first = scope.fork(() -> work("first"));
                var second = scope.fork(() -> work("second"));

                scope.join().throwIfFailed();
                return first.get() + ", " + second.get();
            }
        });

        System.out.println(joined);
        System.out.println("Parent bound: " + TRACE.isBound());
    }
}
```

```bash
javac --enable-preview --release 21 -encoding UTF-8 ScopedValueChildrenDemo.java
java --enable-preview ScopedValueChildrenDemo
```

```text
first=REQ-7, second=REQ-7
Parent bound: false
```

Mặc dù hai child có thể hoàn thành theo thứ tự bất kỳ, kết quả cuối ghép `first.get()` trước `second.get()` nên stdout xác định. `scope.join()` chờ các child hoàn tất và `throwIfFailed()` báo lỗi khi có task thất bại. Khi `try-with-resources` kết thúc, phạm vi task được đóng. Hai child đọc được cùng giá trị `REQ-7` từ binding mà scope đã nhận tại thời điểm tạo; key không bị set lại ở từng child.

**Giới hạn cần hiểu:** đây là cơ chế inheritance gắn với *structured task scope*, không có nghĩa mọi cách khởi chạy thread đều được truyền binding. Cụ thể, đừng mặc định `Thread.ofVirtual().start(...)` hoặc một executor bất kỳ tự nhận context từ thread submit task. Nếu cần context trong tác vụ độc lập, bind trực tiếp trong tác vụ đó hoặc tổ chức tác vụ bằng phạm vi có cấu trúc phù hợp.

Khi value là immutable, nhiều child có thể cùng tham chiếu tới nó an toàn theo cách đọc. Nếu value là mutable, việc kế thừa binding **không biến object thành thread-safe**; cần đồng bộ truy cập hoặc chọn object bất biến.

### Vì sao tính có cấu trúc quan trọng?

Nếu thread con tiếp tục chạy sau khi scope của cha kết thúc, ý nghĩa của context trở nên khó xác định. `StructuredTaskScope` ràng buộc vòng đời các task con với block cha, giúp việc truyền ngữ cảnh và dọn binding có điểm bắt đầu/kết thúc rõ ràng. Đừng tách việc truyền binding khỏi thiết kế lifetime và xử lý lỗi của các child tasks.

Lưu ý phiên bản: API `StructuredTaskScope` tiếp tục thay đổi trong những bản Java sau; đoạn trên là **Java 21 preview**, không phải mã bảo đảm biên dịch nguyên xi trên mọi JDK mới hơn.

## 7. So sánh ScopedValue và ThreadLocal

| Tiêu chí | `ScopedValue` | `ThreadLocal` |
| --- | --- | --- |
| Mục đích tốt nhất | Truyền context **hướng đọc**, trong phạm vi rõ ràng | State theo thread cần `get/set/remove` linh hoạt |
| Thiết lập giá trị | Caller bind trong `run/call` | Bất kỳ mã có key có thể `set` |
| Sửa binding tại callee | Không có setter thay binding đang dùng; có thể mở scope con để rebind tạm thời | Có thể `set` rồi ảnh hưởng các lời gọi tiếp theo trong thread |
| Vòng đời | Tự khôi phục khi scope kết thúc | Tiếp tục gắn với thread cho tới khi `remove` hoặc thread kết thúc |
| Đọc ngoài scope | `get` ném `NoSuchElementException`; `isBound/orElse` an toàn | `get` trả `null` hoặc giá trị initial |
| Truyền sang child | Có cơ chế inheritance qua structured task scope | `ThreadLocal` thường không kế thừa; `InheritableThreadLocal` có quy tắc khác |
| Nhiều virtual threads | Phù hợp để đọc context immutable chia sẻ theo scope | Có thể tốn bộ nhớ nếu mỗi virtual thread giữ dữ liệu riêng lớn |
| Tính bất biến của value | **Không tự cưỡng chế deep immutability** | Không cưỡng chế bất biến |
| Mức độ sẵn có | Preview Java 21–24, chính thức từ Java 25 | API ổn định lâu đời |

Đánh giá hiệu năng phải dựa trên workload thật. `ScopedValue` thường ít chi phí hơn trong tình huống truyền context chỉ đọc tới nhiều virtual threads có cấu trúc, nhưng **không nên coi nó là giải pháp tăng tốc tự động** cho mọi thuật toán.

## 8. Thiết kế context bất biến và ranh giới truy cập

Một thiết kế thuận tiện là gom những dữ liệu cùng vòng đời vào record:

```java
import java.util.Map;

record RequestContext(String traceId, String principal,
                      Map<String, String> tags) {
    RequestContext {
        tags = Map.copyOf(tags);
    }
}
```

Đây là **đoạn minh họa kiểu dữ liệu**, không phải chương trình Java độc lập. Việc `Map.copyOf` tạo một map không cho phép sửa thông qua API map; ở đây cả khóa và giá trị đều là `String` nên không có object mutable nằm sâu bên trong. Nếu trường là object mutable khác, record chỉ làm bất biến **tham chiếu**, không làm bất biến object.

Một số nguyên tắc:

- Dữ liệu trong context nên **nhỏ, cần thiết, bất biến**: trace ID, correlation ID, locale, tham số truy vấn đọc-only đã chuẩn hóa.
- Không đưa cả request body, buffer lớn, cache hay kết nối mở vào context nếu không có lý do và vòng đời chính xác.
- Trường khóa `ScopedValue` nên càng ít nơi truy cập càng tốt (thường `private static final`), cung cấp helper đọc nếu cần để giảm sự phụ thuộc ngầm.
- Nếu xử lý chỉ đi qua một hoặc hai hàm, **truyền tham số tường minh** thường dễ hiểu, dễ test hơn.
- Không nhầm việc “không thể set lại binding tại callee” với cơ chế sandbox hay quyền truy cập bảo mật hoàn chỉnh; code có key vẫn có thể đọc value đang bind.

## 9. Các lỗi thường gặp

### Lỗi 1: gọi get ngoài binding

`TRACE.get()` khi key chưa bind sẽ ném `NoSuchElementException`. Hãy tạo scope trước khi gọi hoặc dùng `TRACE.isBound()`, `TRACE.orElse(fallback)` hay `TRACE.orElseThrow(...)` tùy hợp đồng API.

### Lỗi 2: tưởng rằng rebind làm thay đổi giá trị cha

Trong scope lồng nhau, rebind chỉ hiệu lực **cho phạm vi con**. Khi con kết thúc, cha đọc được value cũ. Không dùng rebind để truyền giá trị trả ngược từ callee lên caller; nên return giá trị hoặc dùng kênh kết quả rõ ràng.

### Lỗi 3: bind object mutable rồi coi là bất biến

Hai child threads có thể cùng thấy tham chiếu `ArrayList` hay `HashMap` và sửa đồng thời, dẫn tới data race. Dùng immutable value/defensive copy hoặc đồng bộ nếu thực sự cần chia sẻ mutable state.

### Lỗi 4: giả định thread nào cũng kế thừa context

Binding là per-thread. Cơ chế kế thừa có cấu trúc có các giới hạn cụ thể; một task qua executor độc lập có thể không nhận giá trị. Đừng phụ thuộc context ngầm khi mô hình concurrency không cam kết propagation đó.

### Lỗi 5: dùng cú pháp Java 25 khi đang chạy JDK 21

Java 21 có API preview riêng và cần cờ preview:

```bash
javac --enable-preview --release 21 ScopedValueDemo.java
java --enable-preview ScopedValueDemo
```

Nếu máy chạy JDK 25, không dùng `--release 21` để “giả lập Java 21 preview” từ compiler JDK 25: preview được gắn với phiên bản trình biên dịch đang chạy. Để xác minh API Java 21 phải chạy **JDK 21** thực sự.

### Lỗi 6: lạm dụng context ẩn

Nếu mọi logic dựa vào nhiều khóa bí mật, dữ liệu trở nên khó truy vết và test. Gom các trường liên quan thành một record rõ nghĩa và dành `ScopedValue` cho thông tin thực sự xuyên nhiều tầng gọi.

## 10. Chuyển từ ThreadLocal sang ScopedValue khi phù hợp

Một API kiểu `ThreadLocal` thường xuất hiện như sau:

```java
private static final ThreadLocal<String> TRACE = new ThreadLocal<>();

static void handle(String id) {
    TRACE.set(id);
    try {
        process();
    } finally {
        TRACE.remove();
    }
}
```

Các đoạn trong phần này **là minh họa phương thức**; `process()` do ứng dụng cung cấp. Nếu dữ liệu chỉ để đọc và không có nhánh nào thực sự cần `TRACE.set()` giữa đường, với Java 21 preview có thể viết:

```java
private static final ScopedValue<String> TRACE = ScopedValue.newInstance();

static void handle(String id) {
    ScopedValue.runWhere(TRACE, id, () -> process());
}
```

Lợi ích là caller quyết định binding trong một scope rõ ràng; callee `process()` chỉ đọc `TRACE.get()` và cơ chế tự khôi phục khi khối chạy kết thúc.

**Không thay thế máy móc** nếu code cũ chủ động cập nhật state trong suốt vòng đời thread, dựa vào giá trị sống ngoài scope, có tương tác với thư viện không hỗ trợ, hoặc yêu cầu truyền context qua task bất đồng bộ không có cấu trúc. Cần xác định phạm vi xử lý, ownership và lifecycle trước khi chuyển.

Khi dùng Java 25+, API `ScopedValue.where(KEY, value).run(...)` vẫn sẵn có mà không cần bật preview. Các phương thức tiện ích preview như `runWhere` trong tài liệu Java 21 không nên được coi là API chung ổn định cho mọi JDK.

## 11. Câu hỏi tự kiểm tra

**Hỏi:** `ScopedValue` có khác một biến `static final String` như thế nào?  
**Đáp:** `static final String` là một giá trị dùng chung cố định; `ScopedValue` là một **khóa** có thể nhận binding khác nhau theo thread và scope, tự khôi phục khi kết thúc scope.

**Hỏi:** Scope bên ngoài bind `A`, scope con bind `B`, sau khi scope con kết thúc đọc được gì?  
**Đáp:** `A`; binding con `B` chỉ tồn tại trong scope con.

**Hỏi:** Nếu task ném exception trước khi kết thúc, có cần gọi `remove()` không?  
**Đáp:** Không; scope tự khôi phục binding. Resource chứa trong value vẫn cần được đóng riêng.

**Hỏi:** Vì sao một record không nhất thiết có deep immutability?  
**Đáp:** Record chỉ ngăn gán lại field; field có thể trỏ đến object mutable. Muốn chia sẻ an toàn cần chọn immutable types hoặc defensive copy phù hợp.

**Hỏi:** Dùng `Thread.ofVirtual().start(...)` trong scope cha có tự truyền `ScopedValue` không?  
**Đáp:** Không được mặc định như vậy. Inheritance của scoped values gắn với mô hình structured task scope, không phải mọi API tạo virtual threads.

**Hỏi:** Java 21 phải chạy lệnh gì với đoạn code sử dụng `ScopedValue`?  
**Đáp:** `javac --enable-preview --release 21 ...` và `java --enable-preview ...`, trên **JDK 21**.

**Ghi nhớ:** `ScopedValue` truyền **ngữ cảnh hướng đọc** trong phạm vi thực thi có điểm kết thúc rõ ràng; binding có thể lồng nhau, tự khôi phục và truyền cho thread con khi dùng cấu trúc phù hợp. Để việc chia sẻ thực sự an toàn, bind **context nhỏ và bất biến**, hiểu rõ phiên bản Java cũng như vòng đời tác vụ.

## Tài liệu chính thức

- [OpenJDK JEP 446 — Scoped Values (Preview), Java 21](https://openjdk.org/jeps/446)
- [Oracle Java 21 — ScopedValue API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ScopedValue.html)
- [Oracle Java 21 — ScopedValue.Carrier API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ScopedValue.Carrier.html)
- [OpenJDK JEP 453 — Structured Concurrency (Preview), Java 21](https://openjdk.org/jeps/453)
- [OpenJDK JEP 506 — Scoped Values, Java 25](https://openjdk.org/jeps/506)
- [Oracle Java 25 — ScopedValue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html)
