# Mục đích và trạng thái chính thức của ScopedValue trong Java 25

## Mục tiêu học tập

Trong Java, dữ liệu thường được truyền qua **tham số phương thức**: một request đi qua controller, service, repository và nhiều lớp trung gian sẽ phải chuyển tiếp các thông tin như request ID hoặc tenant ID. Có những giá trị mà nhiều phương thức ở sâu trong chuỗi lời gọi cần đọc, nhưng không cần thay đổi. **`ScopedValue`** được thiết kế cho chính tình huống này: **truyền ngữ cảnh theo chiều từ caller đến callee, chỉ trong một phạm vi thực thi được xác định rõ**.

Trong **Java 25**, `java.lang.ScopedValue` là API **chính thức (final/permanent)** theo **JEP 506 — Scoped Values**. Không cần bật preview để dùng `ScopedValue` trong JDK 25. Điều này khác với những bản JDK trước từng thử nghiệm API ở trạng thái preview; bài học chỉ dùng tên và hành vi được chuẩn hóa trong Java 25.

Bài thuộc chương **ScopedValue** của module học **JAVA_VERSION_JAVA25**, hướng tới kiến thức Java hiện đại còn áp dụng trong thực tế. Sau bài, bạn sẽ:

1. Giải thích `ScopedValue` giải quyết bài toán gì và vì sao không phải biến toàn cục hoặc `ThreadLocal` có thể sửa tùy ý.
2. Tạo khóa `ScopedValue<T>`, bind giá trị bằng `ScopedValue.where(...).run(...)` hoặc `call(...)`, rồi đọc bằng `get()`.
3. Hiểu **dynamic scope**, rebinding, khôi phục binding sau khi scope kết thúc hoặc ném exception.
4. Phân biệt tính **immutable của binding** với tính mutable của object được tham chiếu.
5. Biết giới hạn truyền context qua thread, executor, virtual thread và sự liên quan tới structured concurrency.
6. Chọn trường hợp sử dụng phù hợp, viết kiểm thử, nhận ra lỗi và cân nhắc migration từ `ThreadLocal`.

> **Môi trường:** dùng JDK 25 trở lên có API `java.lang.ScopedValue` chính thức. Các đoạn mã minh họa là Java thuần, không cần thư viện bên thứ ba. Khi tích hợp framework web, logging hoặc tracing, cần xem cơ chế context propagation của framework đó; `ScopedValue` không tự kết nối với MDC, OpenTelemetry hay executor của framework.

## 1. Bài toán: truyền context qua nhiều tầng lời gọi

Giả sử hệ thống xử lý yêu cầu tra cứu đơn hàng. Controller nhận `requestId`, rồi gọi qua nhiều tầng:

~~~text
HTTP request
  └─ OrderController.handle(requestId, orderId)
       └─ OrderService.find(requestId, orderId)
            └─ OrderRepository.load(requestId, orderId)
                 └─ AuditLogger.record(requestId, action)
~~~

Nếu mỗi phương thức đều phải nhận `requestId`, nhiều chữ ký sẽ chứa một tham số mà các tầng trung gian **không sử dụng**, chỉ chuyển tiếp. Cách này là **truyền tường minh** và vẫn là lựa chọn dễ hiểu, thích hợp cho phần lớn dữ liệu nghiệp vụ.

Tuy nhiên, với những ngữ cảnh **chỉ đọc** dùng sâu trong call stack như request ID, locale hoặc thông tin cấu hình xử lý tạm thời, truyền từng tầng có thể làm API cồng kềnh. Trước đây, nhiều ứng dụng dùng `ThreadLocal` để đặt dữ liệu ở một thread mà không cần thêm tham số vào các phương thức.

`ScopedValue` cung cấp cách **truyền ngữ cảnh ngầm** nhưng có **phạm vi sống được giới hạn bằng cấu trúc lời gọi**. Caller tạo binding, các callee trực tiếp hoặc gián tiếp có quyền truy cập khóa có thể đọc giá trị trong scope, và khi scope kết thúc, binding tự được khôi phục.

~~~mermaid
flowchart TB
    START["Bên ngoài scope<br/>REQUEST_ID chưa bind"] --> BIND["ScopedValue.where(REQUEST_ID, req-42).run(...)"]
    BIND --> A["Controller"]
    A --> B["Service"]
    B --> C["Repository"]
    C --> D["Audit đọc REQUEST_ID.get()"]
    D --> END["Thoát run/call<br/>Binding cũ được khôi phục"]
~~~

**Điểm mấu chốt:** thông tin đi theo **dynamic scope** của việc chạy `run`/`call`, không phải một biến mutable tồn tại vô hạn trong thread pool.

## 2. Tình trạng chính thức trong Java 25

| Nội dung | Trạng thái trong Java 25 | Điều người học cần làm |
|---|---|---|
| `java.lang.ScopedValue` | **API chính thức**, JEP 506 | Có thể dùng với JDK 25, không cần preview |
| `ScopedValue.where(...)` và `ScopedValue.Carrier` | API chính thức | Dùng để tạo binding tạm thời |
| `run`, `call`, `get`, `isBound`, `orElse`, `orElseThrow` | API chính thức | Dùng đúng hành vi theo Java SE 25 |
| Virtual threads | Tính năng chính thức của Java | Có thể phối hợp với `ScopedValue`, nhưng không giả định tự kế thừa binding khi tạo thread tùy ý |
| `StructuredTaskScope` | **Preview trong Java 25** theo JEP 505 | Biết đây là cơ chế structured inheritance, nhưng không dạy code preview như API production ổn định |
| `ThreadLocal` | Vẫn là API Java hợp lệ | Tiếp tục dùng khi cần mô hình dữ liệu thay đổi được hoặc tương thích thư viện cũ; không coi nó bị xóa |

**Cần phân biệt hai JEP:** **JEP 506** là `ScopedValue` đã hoàn thiện, trong khi **JEP 505** là `Structured Concurrency` ở lần preview thứ năm của Java 25. Không thể suy ra rằng `ScopedValue` vẫn là preview chỉ vì ví dụ trong JavaDoc đề cập `StructuredTaskScope`.

Một số bài viết cũ sử dụng các cách gọi API ở giai đoạn preview. Khi học Java 25, hãy ưu tiên chính dạng:

~~~java
ScopedValue.where(KEY, value).run(() -> work());
~~~

Hoặc:

~~~java
Result result = ScopedValue.where(KEY, value).call(() -> calculate());
~~~

Dùng đúng kiểu và chữ ký hiện hành trong [Java SE 25 ScopedValue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html), thay vì sao chép các mẫu thử nghiệm chưa được kiểm chứng.

## 3. Thành phần của API

`ScopedValue<T>` là một **key** để truy cập giá trị kiểu `T` đang được bind trong phạm vi hiện hành. Lớp này nằm trong `java.lang`, nên không bắt buộc viết `import java.lang.ScopedValue;`.

| API | Ý nghĩa | Lưu ý |
|---|---|---|
| `ScopedValue.newInstance()` | Tạo một key `ScopedValue<T>` chưa có binding | Key thường đặt ở `private static final` |
| `ScopedValue.where(KEY, value)` | Tạo `Carrier` chứa ánh xạ key → value | Chưa chạy code và chưa bind vào thread tại thời điểm chỉ tạo Carrier |
| `carrier.run(Runnable)` | Chạy một thao tác không trả kết quả với các binding có hiệu lực | Binding được khôi phục khi chạy xong, kể cả nếu có exception |
| `carrier.call(CallableOp)` | Chạy thao tác trả kết quả, có thể ném exception | Phù hợp thao tác tính toán hoặc truy vấn |
| `KEY.get()` | Đọc binding hiện hành | Ném `NoSuchElementException` nếu chưa bind |
| `KEY.isBound()` | Kiểm tra key có binding trong thread hiện tại không | Không yêu cầu xử lý exception |
| `KEY.orElse(fallback)` | Đọc giá trị hoặc fallback nếu unbound | Không thay đổi binding |
| `KEY.orElseThrow(supplier)` | Đọc hoặc ném exception do supplier tạo | Hữu ích khi context là bắt buộc |
| `carrier.where(OTHER_KEY, value)` | Trả về Carrier mới có thêm/thay mapping | Carrier có thể tập hợp nhiều key |

Không tồn tại `KEY.set(value)` hay `KEY.remove()` theo kiểu `ThreadLocal`. Muốn thay đổi **binding đang được đọc**, hãy mở một **scope lồng nhau** với binding mới. Khi scope trong kết thúc, binding trước đó lại có hiệu lực.

### 3.1. Key khác với value

~~~java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();
~~~

`REQUEST_ID` là **đối tượng khóa** có thể dùng cho nhiều request. Không nên tạo một key mới mỗi lần đọc dữ liệu hoặc để value ở một trường static mutable.

Ví dụ hai request độc lập có thể dùng cùng key `REQUEST_ID`:

~~~java
ScopedValue.where(REQUEST_ID, "req-A").run(() -> process());
ScopedValue.where(REQUEST_ID, "req-B").run(() -> process());
~~~

`process()` đọc giá trị theo binding đang có ở dynamic scope, không phải theo một trường static được cập nhật toàn cục.

## 4. Ví dụ hoàn chỉnh: `run`, `get`, `isBound`

Tạo tệp `ScopedValueIntro.java`:

~~~java
public final class ScopedValueIntro {

    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        System.out.println("Trước scope: " + REQUEST_ID.isBound());

        ScopedValue.where(REQUEST_ID, "req-42")
                .run(ScopedValueIntro::handleRequest);

        System.out.println("Sau scope: " + REQUEST_ID.isBound());
    }

    private static void handleRequest() {
        service();
    }

    private static void service() {
        audit();
    }

    private static void audit() {
        System.out.println("Trong scope: " + REQUEST_ID.get());
    }
}
~~~

Biên dịch và chạy bằng JDK 25:

~~~bash
java -version
javac -version
javac ScopedValueIntro.java
java ScopedValueIntro
~~~

Kết quả:

~~~text
Trước scope: false
Trong scope: req-42
Sau scope: false
~~~

Ở ví dụ trên, `handleRequest` và `service` **không nhận** `requestId` qua tham số. Chúng cũng không cần biết đến key `REQUEST_ID`; chỉ có `audit` sử dụng key khi thực sự cần dữ liệu.

`run` không tạo thread mới: thao tác chạy trên **thread gọi `run`**. Khi lambda/method reference trở về, binding được khôi phục về trạng thái trước đó.

## 5. `call` và context dữ liệu bất biến

Nếu bước xử lý cần trả kết quả, sử dụng `call`. Nên đóng gói nhiều thông tin liên quan trong **một record bất biến** thay vì tạo rất nhiều key:

~~~java
public final class RequestContextExample {

    private record RequestContext(
            String requestId,
            String tenantId,
            String locale
    ) {}

    private static final ScopedValue<RequestContext> CONTEXT =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        RequestContext context =
                new RequestContext("req-99", "tenant-blue", "vi-VN");

        String result = ScopedValue.where(CONTEXT, context)
                .call(RequestContextExample::renderResponse);

        System.out.println(result);
    }

    private static String renderResponse() {
        RequestContext context = CONTEXT.get();
        return "request=" + context.requestId()
                + ", tenant=" + context.tenantId()
                + ", locale=" + context.locale();
    }
}
~~~

Kết quả:

~~~text
request=req-99, tenant=tenant-blue, locale=vi-VN
~~~

`call` trả về kết quả của thao tác. Lớp `ScopedValue.Carrier` hỗ trợ `ScopedValue.CallableOp` để callback có thể trả về dữ liệu hoặc ném exception phù hợp chữ ký.

**Tại sao dùng record?** `RequestContext` gom các giá trị tương quan thành một object có tham chiếu ổn định. Với các thành phần `String` bất biến, việc chia sẻ context dễ suy luận hơn. Trong ứng dụng thật, hãy xác thực dữ liệu đầu vào tại boundary trước khi tạo context; bản thân record không thực hiện authentication hay authorization.

### 5.1. Bind nhiều key khi cần

Khi những thông tin có vòng đời hoặc quyền đọc khác nhau, có thể dùng nhiều key:

~~~java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

private static final ScopedValue<String> REGION =
        ScopedValue.newInstance();

static void work() {
    ScopedValue.where(REQUEST_ID, "req-100")
            .where(REGION, "ap-southeast")
            .run(() -> {
                System.out.println(REQUEST_ID.get());
                System.out.println(REGION.get());
            });
}
~~~

`Carrier.where(...)` tạo **Carrier mới** với thêm một mapping; nó không cập nhật biến global và cũng không tự bind cho thread trước khi `run` hoặc `call` bắt đầu.

Trong nhiều trường hợp, một `ScopedValue<RequestContext>` là đủ và tránh chi phí/quản lý của quá nhiều key riêng lẻ.

## 6. Dynamic scope và rebinding

`ScopedValue` gắn giá trị với **thời gian thực thi của một phạm vi động**. Khi scope lồng nhau bind lại cùng key, code ở scope trong thấy giá trị mới; khi thoát scope trong, code trở lại thấy giá trị cũ.

~~~java
public final class RebindingDemo {
    private static final ScopedValue<String> LANGUAGE =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        System.out.println(LANGUAGE.isBound()); // false

        ScopedValue.where(LANGUAGE, "vi-VN").run(() -> {
            show("outer");

            ScopedValue.where(LANGUAGE, "en-US").run(() -> {
                show("inner");
            });

            show("outer again");
        });

        System.out.println(LANGUAGE.isBound()); // false
    }

    private static void show(String label) {
        System.out.println(label + ": " + LANGUAGE.get());
    }
}
~~~

Kết quả:

~~~text
false
outer: vi-VN
inner: en-US
outer again: vi-VN
false
~~~

Một sơ đồ thời gian:

~~~text
Unbound
  └── where(LANGUAGE, "vi-VN").run(...)
        LANGUAGE.get() => vi-VN
        └── where(LANGUAGE, "en-US").run(...)
              LANGUAGE.get() => en-US
        LANGUAGE.get() => vi-VN
Unbound
~~~

Đây là **rebinding**, không phải việc gọi `set` làm thay đổi binding cũ. Một callee có quyền truy cập key có thể tạo scope lồng nhau với value mới, nhưng không thể âm thầm thay đổi binding của caller sau khi scope trong kết thúc.

### 6.1. Nếu trong scope phát sinh exception?

Một ưu điểm quan trọng là binding được khôi phục theo cấu trúc khi callback kết thúc, **kể cả kết thúc bằng exception**.

~~~java
public final class ExceptionDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "outer").run(() -> {
            try {
                ScopedValue.where(REQUEST_ID, "inner").run(() -> {
                    System.out.println(REQUEST_ID.get()); // inner
                    throw new IllegalStateException("Giả lập lỗi");
                });
            } catch (IllegalStateException ex) {
                System.out.println(REQUEST_ID.get()); // outer
            }
        });

        System.out.println(REQUEST_ID.isBound()); // false
    }
}
~~~

Không cần gọi `remove()` trong `finally` như cách quản lý `ThreadLocal` thông thường. Tuy nhiên, **tài nguyên khác** như file handle, socket, database transaction vẫn cần được giải phóng theo cơ chế thích hợp; binding tự được khôi phục không phải cơ chế đóng tài nguyên.

## 7. Đọc giá trị khi chưa bind

`ScopedValue` được tạo bởi `newInstance()` **chưa có binding**. Nếu gọi `get()` ngoài scope, Java 25 ném `NoSuchElementException`.

~~~java
import java.util.NoSuchElementException;

public final class MissingBindingDemo {
    private static final ScopedValue<String> USER =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        System.out.println(USER.isBound());    // false
        System.out.println(USER.orElse("guest")); // guest

        try {
            USER.get();
        } catch (NoSuchElementException ex) {
            System.out.println("Chưa có binding");
        }

        String value = ScopedValue.where(USER, "alice")
                .call(() -> USER.orElseThrow(
                    () -> new IllegalStateException("Thiếu user")));

        System.out.println(value); // alice
    }
}
~~~

Quy tắc thực tế:

- **`get()`** khi bạn chắc chắn đang ở trong scope có binding và muốn phát hiện lỗi lập trình nếu thiếu.
- **`isBound()`** khi logic cho phép có hoặc không có context.
- **`orElse(defaultValue)`** khi có giá trị thay thế hợp lý.
- **`orElseThrow(supplier)`** khi context là điều kiện bắt buộc và bạn muốn ném một exception có ý nghĩa nghiệp vụ hoặc chẩn đoán rõ hơn.

Mỗi phương thức chỉ **đọc** binding trong thread hiện tại. Không phương thức nào tự tạo binding mới hoặc sửa value ở bên ngoài.

## 8. ScopedValue và ThreadLocal khác nhau như thế nào?

`ThreadLocal<T>` vẫn là API Java được hỗ trợ và có trường hợp dùng hợp lý. Khác biệt nằm ở **mục đích và vòng đời dữ liệu**.

| Khía cạnh | `ScopedValue<T>` | `ThreadLocal<T>` |
|---|---|---|
| Mục tiêu chính | Truyền context **chỉ đọc theo một chiều** caller → callee | Lưu dữ liệu riêng từng thread có thể đọc/sửa |
| Tạo giá trị | Bind trong `where(...).run/call` | `set(value)`, hoặc `initialValue` |
| Sửa binding từ callee | Không có `set`; có thể rebinding trong scope lồng | Callee có key có thể `set` trên thread |
| Vòng đời | Giới hạn bởi dynamic scope; tự khôi phục | Có thể tồn tại suốt thời gian sống thread nếu không `remove` |
| Sử dụng trong thread pool | Không giả định tự propagate khi chuyển task | Cũng không tự propagate khi chuyển task; phải quản lý cleanup |
| Kế thừa theo structured task scope | Có cơ chế hỗ trợ riêng khi dùng structured concurrency | Không cùng mô hình kế thừa phạm vi |
| Dữ liệu có thể mutable? | Tham chiếu binding ổn định, **object được tham chiếu có thể mutable** | Giá trị tham chiếu và object đều có thể thay đổi |
| Khi phù hợp | Request ID, locale, immutable request context, cấu hình truy vấn tạm thời | Legacy integration hoặc dữ liệu per-thread cần cập nhật có chủ đích |

Ví dụ `ThreadLocal` trong một thread pool:

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

static void process(String id) {
    REQUEST_ID.set(id);
    try {
        // Gọi logic cần request ID
    } finally {
        REQUEST_ID.remove();
    }
}
~~~

Nếu quên `remove()`, task sau trên cùng worker thread có thể đọc nhầm dữ liệu. `ScopedValue` tạo binding trong scope và tự khôi phục khi thoát nên giảm nguy cơ **context leak qua các request dùng lại thread**.

**Không nên thay toàn bộ `ThreadLocal` bằng `ScopedValue` một cách cơ học.** Nếu thuật toán thực sự cần cập nhật state riêng theo thread, mô hình truyền context bất biến không đáp ứng đầy đủ. Nếu framework sử dụng `ThreadLocal`/MDC, bạn còn phải xem cơ chế tích hợp và migration được hỗ trợ, không phải chỉ đổi tên class.

## 9. “Binding bất biến” không có nghĩa “object bất biến”

Một `ScopedValue<List<String>>` có thể giữ tham chiếu tới một `ArrayList`. Dù không ai có thể thay đổi **binding** ngoài scope con, code nhận được list vẫn có thể gọi `add`, `remove`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class MutableValueExample {
    private static final ScopedValue<List<String>> ITEMS =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        List<String> items = new ArrayList<>();

        ScopedValue.where(ITEMS, items).run(() -> {
            ITEMS.get().add("A");
        });

        System.out.println(items); // [A]
    }
}
~~~

Ví dụ này **hợp lệ về cú pháp**, nhưng nó minh họa **anti-pattern** nếu chủ đích là truyền context chỉ đọc. Không nên khẳng định `ScopedValue` khiến mọi dữ liệu bên trong an toàn trước mutation hoặc race condition.

Ưu tiên:

~~~java
record RequestContext(String requestId, String tenantId) {}
~~~

Với dữ liệu collection, sử dụng immutable copy (`List.copyOf`, `Map.copyOf`) khi phù hợp. Nếu nhiều thread cùng đọc/ghi một object mutable, phải có cơ chế đồng bộ thích hợp như với mọi chia sẻ dữ liệu Java thông thường.

**Thiết kế tốt:** tạo context bất biến tại boundary, xác nhận dữ liệu, bind một lần cho luồng xử lý, và chỉ dùng `get()` để đọc. Đừng dùng object mutable như một cách lách việc ScopedValue không có `set()`.

## 10. Phạm vi theo thread và giới hạn propagation

Binding của `ScopedValue` **gắn với thread** đang chạy `run/call`. Việc lời gọi đi sâu qua nhiều phương thức trên cùng thread không làm mất binding, nhưng không có nghĩa mọi thread mới, `ExecutorService`, callback bất đồng bộ hoặc scheduler đều được kế thừa binding tự động.

### 10.1. Minh họa với virtual thread tự tạo

Virtual threads là tính năng chính thức của Java hiện đại. Nhưng một virtual thread **tự tạo trực tiếp** không mặc nhiên được kế thừa binding `ScopedValue` từ caller:

~~~java
public final class ThreadBoundaryDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-parent").run(() -> {
            System.out.println("parent: " + REQUEST_ID.get());

            Thread child = Thread.ofVirtual().start(() -> {
                System.out.println("child bound: "
                        + REQUEST_ID.isBound());
            });

            try {
                child.join();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });
    }
}
~~~

Kết quả điển hình:

~~~text
parent: req-parent
child bound: false
~~~

**Điểm cần nhớ:** không tự ý coi context trong parent là đã được truyền sang mọi task chạy đồng thời. Nếu cần context ở một thread tự quản lý, bạn phải truyền hoặc bind rõ ràng theo thiết kế, đồng thời bảo đảm vòng đời và tính an toàn của dữ liệu.

### 10.2. Structured concurrency là trường hợp đặc biệt

Java SE 25 hỗ trợ kế thừa binding `ScopedValue` trong **structured child threads** do `StructuredTaskScope` tạo qua `fork`, theo nguyên tắc các task con hoàn tất trước khi parent rời scope tương ứng.

Tuy nhiên, **`StructuredTaskScope` vẫn là API preview trong Java 25** (JEP 505). Vì yêu cầu bài học ưu tiên kiến thức đã ổn định, bài không dùng `StructuredTaskScope` làm ví dụ lập trình production không cần preview flag. Khi dự án chủ động thử nghiệm structured concurrency, phải bật preview theo hướng dẫn JDK đang dùng và chấp nhận thay đổi API trong các bản phát hành tiếp theo.

Sự khác nhau này rất quan trọng:

| Cách tạo công việc | Có thể dựa vào kế thừa ScopedValue tự động không? |
|---|---|
| Gọi phương thức đồng bộ trên cùng thread | **Có**, trong dynamic scope đang bind |
| Lồng `ScopedValue.where(...).run(...)` trên cùng thread | **Có**, với rebinding rồi khôi phục |
| Tạo `Thread` hoặc `Thread.ofVirtual()` riêng | **Không nên giả định có** |
| Submit task vào `ExecutorService` thông thường | **Không nên giả định có** |
| Fork child qua `StructuredTaskScope` theo quy tắc API | **Có hỗ trợ kế thừa có cấu trúc**, nhưng StructuredTaskScope là preview ở Java 25 |
| Gửi message qua Kafka/HTTP tới process khác | **Không**, cần cơ chế truyền context của giao thức/framework |

### 10.3. ScopedValue không thay thế distributed tracing

`ScopedValue` là phương tiện quản lý ngữ cảnh trong phạm vi chạy của JVM. Nó **không** tự tạo trace/span, không tự inject W3C Trace Context qua HTTP, không ghi MDC và không truyền dữ liệu sang broker.

Ví dụ một framework web đặt request context vào `ScopedValue` là một lựa chọn triển khai của framework. Với các API callback, executor, Reactor, CompletableFuture hoặc messaging, cần kiểm tra cơ chế context propagation phù hợp. **Không kết luận rằng một trace sẽ liên tục chỉ vì phần code đã dùng ScopedValue**.

## 11. Hướng dẫn thiết kế context cho ứng dụng thực tế

Một ví dụ thiết kế request context có thể định nghĩa một public API nhỏ, giữ key riêng trong lớp quản lý:

~~~java
public final class RequestContextScope {

    public record Context(
            String requestId,
            String tenantId
    ) {}

    private static final ScopedValue<Context> CURRENT =
            ScopedValue.newInstance();

    private RequestContextScope() {}

    public static void runWith(Context context, Runnable action) {
        ScopedValue.where(CURRENT, context).run(action);
    }

    public static Context current() {
        return CURRENT.orElseThrow(
                () -> new IllegalStateException(
                        "Không có request context trong scope hiện tại"));
    }
}
~~~

Ví dụ sử dụng:

~~~java
public final class ServiceExample {

    public static void main(String[] args) {
        var context = new RequestContextScope.Context(
                "req-123", "tenant-blue");

        RequestContextScope.runWith(context,
                ServiceExample::handleRequest);
    }

    private static void handleRequest() {
        String tenantId = RequestContextScope.current().tenantId();
        System.out.println("Đang xử lý tenant: " + tenantId);
    }
}
~~~

Ở đây các lớp dùng ngữ cảnh chỉ có thể đọc qua `current()`; key `CURRENT` được đóng gói trong `RequestContextScope`. Điều này giúp kiểm soát nơi binding được tạo, giới hạn việc các lớp khác tự bind lại key và làm lỗi thiếu context rõ ràng hơn.

**Ranh giới bảo mật:** không sử dụng riêng `ScopedValue` như cơ chế xác thực hay phân quyền. Context phải được tạo từ thông tin đã kiểm tra; tầng cấp quyền vẫn phải xác thực hành động theo chính sách. Không coi request ID hoặc tenant ID trong context là bằng chứng an toàn tuyệt đối nếu chưa được xác thực.

### 11.1. Một sơ đồ lựa chọn công cụ

~~~mermaid
flowchart TD
    A["Có cần truyền dữ liệu qua lời gọi?"] --> B{"Thông tin có thuộc hợp đồng nghiệp vụ rõ ràng?"}
    B -->|Có| P["Ưu tiên tham số tường minh"]
    B -->|Không| C{"Chỉ đọc trong một dynamic scope?"}
    C -->|Có| S["Cân nhắc ScopedValue"]
    C -->|Không| D{"Cần state riêng theo thread có thể cập nhật?"}
    D -->|Có| T["Xem xét ThreadLocal / cấu trúc state khác"]
    D -->|Không| E["Thiết kế lại lifetime / ownership của dữ liệu"]
    S --> F{"Qua thread / process khác?"}
    F -->|Có| G["Thiết kế propagation riêng, kiểm tra concurrency API"]
    F -->|Không| H["Bind một scope, đọc trong call chain"]
~~~

Không phải toàn bộ context nên đưa vào `ScopedValue`. Với tham số liên quan trực tiếp đến kết quả nghiệp vụ như `orderId`, `amount`, `currency`, cách truyền tường minh vẫn giúp method contract rõ ràng và dễ test. `ScopedValue` phù hợp nhất với **ngữ cảnh phụ trợ cần đọc nhiều nơi**.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `cannot find symbol: ScopedValue` | JDK/toolchain chưa phải 25 hoặc compile `--release` quá thấp | Kiểm tra `java -version`, `javac -version`, `--release 25` |
| Ví dụ yêu cầu bật preview cho `ScopedValue` | Tài liệu đang nói về bản preview cũ | Dùng tài liệu Java SE 25/JEP 506 final |
| Gọi `KEY.get()` ném `NoSuchElementException` | Chưa có binding trong current thread | Tạo scope với `where` hoặc xử lý `isBound/orElse` |
| Đã tạo `Carrier` nhưng `isBound()` vẫn false | `where` chỉ chuẩn bị mapping, chưa chạy `run/call` | Chạy callback trong scope |
| Context mất khi chuyển qua executor | Scope không tự propagate qua task tùy ý | Truyền/bind context rõ ràng hoặc dùng tích hợp concurrency phù hợp |
| Context giữ giá trị lạ sau lần gọi bên trong | Đang ở nested rebinding scope | Kiểm tra cấu trúc `where` lồng nhau và thứ tự đọc |
| Dữ liệu bên trong vẫn bị sửa | Object được bind là mutable | Dùng immutable context hoặc đồng bộ khi cần |
| Tưởng `ScopedValue` tự tạo traceId/MDC | Nhầm cơ chế lưu context với instrumentation | Cấu hình tracing/logging framework riêng |
| Đọc giá trị của request khác | Context được tạo/bind sai ở boundary hoặc tự truyền sai giữa task | Kiểm tra ownership, input validation và lifetime |
| Lạm dụng nhiều key gây khó quản lý | Phân tán context thành rất nhiều ScopedValue | Gom những giá trị liên quan trong record bất biến |
| Dùng `ScopedValue` để chia sẻ state mutable giữa threads | Sai mục tiêu API, nguy cơ race condition | Dùng state management và synchronization thích hợp |

Một số ví dụ cũ có thể dùng các tên phương thức khác trong giai đoạn preview. Với Java 25, sử dụng **`ScopedValue.where(KEY, value).run(...)`**, **`call(...)`** và các getter được Java SE 25 công bố, không tự chuyển mã theo tên API cũ mà chưa kiểm chứng.

## 13. Kiểm thử hành vi thay vì chỉ nhìn output

Các test quan trọng cần kiểm tra **binding lifetime** và **không rò rỉ giữa các lần chạy**. Một ma trận kiểm thử:

| Mã | Thiết lập | Kết quả mong đợi |
|---|---|---|
| S1 | Tạo key bằng `newInstance()` | `isBound() == false` |
| S2 | Bind trong `run`, gọi qua 3 phương thức đồng bộ | `get()` đọc cùng giá trị |
| S3 | Rời `run` | Binding trở về trạng thái cũ/unbound |
| S4 | Bind ngoài `vi-VN`, bind lồng `en-US` | Trong scope con đọc `en-US`; sau đó khôi phục `vi-VN` |
| S5 | Throw exception trong scope con | Binding ngoài vẫn được khôi phục |
| S6 | `call` trả về dữ liệu | Giá trị trả về đúng, binding không còn sau call |
| S7 | `get()` khi unbound | Ném `NoSuchElementException` |
| S8 | `orElse` khi unbound | Trả về fallback, không tự tạo binding |
| S9 | Dùng cùng key trong hai thread độc lập, bind giá trị khác nhau | Mỗi thread đọc binding của mình |
| S10 | Tạo virtual thread riêng khi parent đang bind | Không mặc định đọc được binding của parent |
| S11 | Bind tham chiếu tới list mutable rồi sửa list | Thấy mutation, chứng minh binding không làm object bất biến |
| S12 | Xử lý hai request liên tiếp trong cùng thread pool | Khi scope chuẩn kết thúc, không còn binding của request trước |

### 13.1. Ví dụ kiểm tra bằng assertion Java thuần

~~~java
import java.util.NoSuchElementException;

public final class ScopedValueChecks {
    private static final ScopedValue<String> KEY =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        assert !KEY.isBound();

        ScopedValue.where(KEY, "outer").run(() -> {
            assert KEY.get().equals("outer");

            ScopedValue.where(KEY, "inner").run(() -> {
                assert KEY.get().equals("inner");
            });

            assert KEY.get().equals("outer");
        });

        assert !KEY.isBound();

        try {
            KEY.get();
            throw new AssertionError("get() phải ném exception");
        } catch (NoSuchElementException expected) {
            System.out.println("PASS: unbound");
        }
    }
}
~~~

Chạy với assertions bật:

~~~bash
javac ScopedValueChecks.java
java -ea ScopedValueChecks
~~~

Trong dự án thật, có thể chuyển các trường hợp S1–S12 thành test JUnit 5. Quan trọng nhất là kiểm tra isolation, restoration và exception paths; đừng chỉ so sánh log có in đúng request ID trong happy path.

## 14. Những hiểu nhầm cần loại bỏ khi học Java 25

| Khẳng định | Đánh giá |
|---|---|
| “`ScopedValue` vẫn là preview trong Java 25” | **Sai**: JEP 506 đã final |
| “Java 25 cần `--enable-preview` để chạy `ScopedValue`” | **Sai** nếu chỉ dùng API ScopedValue chính thức |
| “Mọi công cụ Structured Concurrency cũng final trong Java 25” | **Sai**: `StructuredTaskScope` còn preview |
| “`ScopedValue` cho phép callee gọi `set` như ThreadLocal” | **Sai**: không có `set`, chỉ có rebinding có phạm vi |
| “Khi hết scope, binding không thể rò rỉ vì tự khôi phục” | **Đúng đối với binding**, nhưng object/context được truyền sai qua cơ chế khác vẫn có rủi ro |
| “Value được bind tự động trở thành immutable” | **Sai**: object có thể mutable |
| “Một virtual thread tùy ý luôn kế thừa context của parent” | **Sai** |
| “`ScopedValue` tự động truyền tracing headers cho HTTP/Kafka” | **Sai** |
| “`ThreadLocal` bị xóa hoặc không còn hợp lệ trong Java 25” | **Sai**: vẫn được hỗ trợ, chỉ có trade-off khác |
| “Dùng ScopedValue là cách duy nhất để truyền context” | **Sai**: truyền tham số tường minh thường rõ ràng và hợp lý hơn |

## 15. Bài thực hành tổng hợp

**Bài A — Request context.** Tạo một record `RequestContext(requestId, tenantId)` và một `ScopedValue<RequestContext>` private static final. Viết phương thức `handle` bind context, `service` gọi `audit`, và `audit` chỉ đọc context. In `isBound()` trước/trong/sau scope và xác minh kết quả.

**Bài B — Rebinding.** Trong một scope có `tenantId="tenant-blue"`, tạo scope lồng `tenantId="tenant-green"` để thử một callback khác. Sau khi callback kết thúc (kể cả khi ném exception), xác nhận scope ngoài vẫn đọc tenant ban đầu.

**Bài C — Context giữa threads.** Tạo một virtual thread tự quản lý trong scope và chứng minh `isBound()` của key có thể false. Sau đó thử truyền một immutable `RequestContext` như tham số cho task và bind nó **bên trong task** một cách tường minh. Giải thích tại sao đây là một cơ chế propagation do bạn thiết kế, không phải kế thừa tự động.

**Bài D — So sánh với ThreadLocal.** Viết hai request chạy liên tiếp trên một thread cố định. Với ThreadLocal, thử bỏ `remove` trong bản thử nghiệm để quan sát nguy cơ stale context; khôi phục bằng `try/finally`. Với ScopedValue, dùng scope để không phải dọn binding thủ công. Không triển khai thí nghiệm cố ý rò rỉ trong code production.

**Bài E — Đánh giá công nghệ.** Liệt kê ba tình huống thật: truyền `orderId` tới repository, truyền request ID cho audit log, lưu state mutable riêng mỗi thread. Chọn cách truyền tham số, ScopedValue hoặc ThreadLocal, giải thích về độ rõ của API, lifetime, khả năng kiểm thử và propagation khi có async.

**Yêu cầu nghiệm thu:** code chạy với `javac`/JDK 25 không cần preview; trình bày được sự khác nhau giữa **binding**, **value**, **dynamic scope** và **thread boundary**; có ít nhất một test chứng minh restoration sau exception.

## 16. Checklist áp dụng trong dự án hiện đại

Trước khi dùng `ScopedValue` trong một hệ thống thực tế:

- **Phiên bản:** xác nhận project thật sự dùng JDK 25+ và không sao chép API preview từ JDK 21–24.
- **Mục đích:** value là context phụ trợ, cần truyền từ caller xuống các callee theo một chiều.
- **Ownership:** key đặt `private static final` hoặc đóng gói qua API có kiểm soát.
- **Dữ liệu:** ưu tiên record bất biến; không đặt mutable shared state vào context mà thiếu đồng bộ.
- **Lifetime:** bind tại boundary rõ ràng; tránh giữ Carrier như một “session global” hoặc kéo dài scope không cần thiết.
- **Đọc:** dùng `get`, `isBound`, `orElse`, `orElseThrow` theo tính bắt buộc của context.
- **Nested scope:** kiểm chứng rebinding và restoration, kể cả exception.
- **Concurrency:** không giả định tự động truyền qua executor, Thread.ofVirtual hay message broker.
- **Structured concurrency:** nhận diện `StructuredTaskScope` vẫn là preview trong Java 25 khi cân nhắc inheritance.
- **Security:** xác thực context tại đầu vào; không thay thế kiểm tra quyền bằng việc context đã được bind.
- **Testing:** kiểm tra nhiều request, thread, exception, absence và context isolation.
- **Performance:** đo trên workload thật, không khẳng định luôn nhanh hơn ThreadLocal trong mọi trường hợp.
- **Tài liệu:** liên kết trực tiếp tới JEP 506 và Java SE 25 API thay vì dựa vào blog preview cũ.

## Tài liệu tham khảo chính thức

- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): mô tả tính năng đã được chính thức hóa trong Java 25 và mục tiêu của ScopedValue.
- [Java SE 25 API — java.lang.ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): định nghĩa API, binding, rebinding, inheritance và lưu ý so sánh với ThreadLocal.
- [Java SE 25 API — ScopedValue.Carrier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html): `where`, `run`, `call` và vòng đời của các mapping.
- [Oracle Java SE 25 Core Libraries — Scoped Values](https://docs.oracle.com/en/java/javase/25/core/scoped-values.html): hướng dẫn tổng quan ScopedValue trong core libraries.
- [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): trạng thái preview của StructuredTaskScope trong Java 25.
- [Java SE 25 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): inheritance có cấu trúc, cần lưu ý API còn preview.
- [Oracle JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): trạng thái tính năng Scoped Values và Structured Concurrency khi phát hành Java 25.
