# Phân biệt tính bất biến của ràng buộc với khả năng thay đổi của đối tượng giá trị

## 1. Bài toán: “ScopedValue bất biến” có nghĩa là gì?

Trong một ứng dụng Java hiện đại, nhiều phương thức cùng xử lý một request cần truy cập những thông tin ngữ cảnh giống nhau: mã tương quan, locale, thông tin người gọi đã xác thực hoặc chế độ xử lý. Truyền các tham số đó qua mọi tầng API có thể khiến chữ ký phương thức dài và khó đọc. Java 25 cung cấp **`ScopedValue`** để truyền dữ liệu ngữ cảnh theo **phạm vi thực thi động** (*dynamic scope*).

Tuy nhiên, một cách hiểu sai rất nguy hiểm là:

> “Vì `ScopedValue` bất biến nên mọi đối tượng lấy ra qua `get()` cũng bất biến, có thể chia sẻ tự do giữa các thread.”

Điều này **không đúng**. `ScopedValue` giữ một **ràng buộc bất biến giữa một khóa và một tham chiếu tới giá trị** trong một phạm vi đang hoạt động; bản thân đối tượng được tham chiếu có thể là **mutable object**.

Bài **Phân biệt tính bất biến của ràng buộc với khả năng thay đổi của đối tượng giá trị** thuộc chương **ScopedValue** của module **JAVA_VERSION_JAVA25**. Đây là kiến thức còn áp dụng khi xây dựng Java 25 application, kể cả ứng dụng sử dụng virtual threads, các luồng xử lý request, các API ngữ cảnh hoặc tracing.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **khóa `ScopedValue`**, **binding**, **tham chiếu đối tượng** và **trạng thái nội tại của đối tượng**.
2. Giải thích tại sao không thể thay giá trị binding bằng một setter nhưng vẫn có thể sửa một `List`, `Map` hoặc object mutable được lấy bằng `get()`.
3. Sử dụng `ScopedValue.newInstance()`, `ScopedValue.where(...).run(...)`, `call(...)`, `get()` và `isBound()` đúng vòng đời.
4. Phân biệt **nested rebinding** với **mutating shared object**.
5. Áp dụng immutable records, defensive copies và snapshot để bảo vệ ngữ cảnh giữa các tầng và giữa các task.
6. Xác định rủi ro concurrency, visibility, race conditions và sự cố dữ liệu nếu chia sẻ một mutable value.
7. Kiểm tra ngữ nghĩa bằng JUnit và xây dựng quy tắc sử dụng `ScopedValue` cho code production.

> **Trạng thái Java 25:** `ScopedValue` được chuẩn hóa trong **JDK 25** thông qua **JEP 506 – Scoped Values**. Các ví dụ ở bài này dùng API chính thức của `java.lang.ScopedValue` và **không cần** `--enable-preview`. Không nhầm với tài liệu Java 20–24 vốn trình bày các bản incubator/preview hoặc API thay đổi qua từng giai đoạn. Những tính năng khác của Java 25 như compact source files, module imports, constructor linh hoạt, KDF, AOT cache và JFR không làm thay đổi quy tắc “immutable binding, potentially mutable object”.

## 2. Bốn khái niệm phải tách riêng

Giả sử bạn viết:

~~~java
static final ScopedValue<RequestContext> CONTEXT =
    ScopedValue.newInstance();
~~~

và chạy:

~~~java
var context = new RequestContext("req-001", "vi-VN");

ScopedValue.where(CONTEXT, context).run(() -> {
    handleRequest();
});
~~~

Cần phân biệt bốn lớp ý nghĩa:

| Thành phần | Ví dụ | Tính chất cần nhớ |
| --- | --- | --- |
| **Khóa (key)** | `CONTEXT` | Đối tượng `ScopedValue<RequestContext>` xác định chỗ tra cứu; thường khai báo `static final` |
| **Binding** | `CONTEXT → context` | Quan hệ giữa khóa và giá trị được thiết lập khi vào `where(...).run(...)`; không có API `set()` để ghi đè binding trong cùng scope |
| **Tham chiếu (reference)** | Biến `context` trỏ tới object | Bản thân reference được binding cố định trong scope đang chạy |
| **Đối tượng/giá trị (referent)** | `RequestContext` | Trạng thái bên trong object có thể bất biến hoặc thay đổi tùy cách thiết kế class |

Mấu chốt là **bất biến của mối liên hệ** chứ không mặc nhiên là **bất biến của dữ liệu**.

Có thể hình dung:

~~~mermaid
flowchart LR
    K[Khóa ScopedValue CONTEXT] -->|binding trong scope hiện tại| R[Tham chiếu tới RequestContext]
    R --> O[Object RequestContext]
    O --> F1[requestId]
    O --> F2[locale]
    O --> F3[attributes / state]
~~~

Không có thao tác `CONTEXT.set(other)` giống `ThreadLocal.set(...)`. Nhưng nếu `Object RequestContext` có setter hoặc chứa `Map` mutable, code hoàn toàn có thể gọi setter hoặc sửa map thông qua `CONTEXT.get()`.

### Hai nghĩa khác nhau của từ immutable

**Immutable binding**: một lần thực thi `where(CONTEXT, value).run(action)` thiết lập binding tương ứng trong phạm vi đó; code ở trong scope không đổi binding trực tiếp sang một reference khác. Có thể mở **scope lồng nhau** với một binding mới, nhưng binding cũ sẽ được phục hồi khi thoát scope con.

**Immutable object**: trạng thái object sau khi tạo không thể bị thay đổi qua API quan sát được, kể cả qua tham chiếu alias hoặc collection lồng bên trong. Đây là **trách nhiệm thiết kế object**, không phải điều `ScopedValue` tự cung cấp.

## 3. Tại sao scoped binding lại hữu ích?

Khi một request đi qua nhiều lớp:

~~~text
HTTP handler
    → OrderService
        → PricingService
            → AuditHelper
~~~

Bạn có hai lựa chọn phổ biến:

- Truyền `RequestContext` qua mọi method: dễ thấy dependency, nhưng có thể tạo nhiều tham số xuyên tầng chỉ để phục vụ logging/correlation.
- Dùng `ScopedValue<RequestContext>` cho ngữ cảnh **read-mostly**, chỉ bind ở boundary, rồi gọi `CONTEXT.get()` khi cần.

Sơ đồ vòng đời:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Request boundary
    participant S as ScopedValue runtime
    participant O as OrderService
    participant A as AuditHelper

    B->>S: where(CONTEXT, snapshot).run(action)
    S->>S: Thiết lập binding cho dynamic scope
    B->>O: handle()
    O->>A: audit()
    A->>S: CONTEXT.get()
    S-->>A: Cùng tham chiếu snapshot
    A-->>O: Ghi nhận ngữ cảnh
    O-->>B: Hoàn tất request
    S->>S: Rời scope, phục hồi binding trước đó
~~~

`ScopedValue` phù hợp nhất khi:

1. Dữ liệu được bind một lần tại boundary.
2. Các phương thức downstream chủ yếu **đọc**.
3. Các phương thức gọi nhau theo phạm vi rõ ràng.
4. Dữ liệu không cần mutable global store hoặc tùy ý thay đổi binding ở giữa luồng.
5. Có quy định rõ cách chuyển tiếp context nếu đưa công việc sang thread/task khác.

**Không nên biến `ScopedValue` thành một biến toàn cục có thể ghi ngầm.** Thiết kế đó đi ngược mục tiêu của scoped binding.

## 4. Ví dụ cơ bản: binding bất biến và tự phục hồi

Tạo tệp `Basics.java`:

~~~java
public class Basics {

    private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

    static void log(String step) {
        System.out.println(step + " / " + REQUEST_ID.get());
    }

    public static void main(String[] args) {
        System.out.println("Trước scope: " + REQUEST_ID.isBound());

        ScopedValue.where(REQUEST_ID, "req-001").run(() -> {
            log("handler");
            log("service");
        });

        System.out.println("Sau scope: " + REQUEST_ID.isBound());
    }
}
~~~

Chạy với JDK 25:

~~~bash
javac --release 25 -encoding UTF-8 Basics.java
java Basics
~~~

Kết quả dự kiến:

~~~text
Trước scope: false
handler / req-001
service / req-001
Sau scope: false
~~~

Giải thích:

- `ScopedValue.newInstance()` tạo một **key**, chưa bind giá trị.
- `ScopedValue.where(REQUEST_ID, "req-001")` tạo một cấu hình binding cho carrier.
- `run(...)` thực thi action với binding đang hoạt động.
- `REQUEST_ID.get()` ở helper tìm giá trị trong dynamic scope đang chạy.
- Sau khi `run` kết thúc, binding không còn hoạt động nếu trước đó key chưa được bind.
- `isBound()` là kiểm tra trạng thái binding hiện tại; không phải kiểm tra object được tham chiếu có null hay rỗng hay không.

Vì `String` bất biến, ví dụ này đồng thời có **binding bất biến** và **đối tượng giá trị bất biến**. Nhưng trường hợp đó **không chứng minh** mọi kiểu dữ liệu đều bất biến.

## 5. Ví dụ quan trọng nhất: binding không đổi, object vẫn thay đổi

Tạo tệp `MutableValueDemo.java`:

~~~java
public class MutableValueDemo {

    private static final ScopedValue<CounterBox> BOX =
        ScopedValue.newInstance();

    static final class CounterBox {
        private int count;

        CounterBox(int initial) {
            this.count = initial;
        }

        void increment() {
            count++;
        }

        int count() {
            return count;
        }
    }

    public static void main(String[] args) {
        var box = new CounterBox(0);

        ScopedValue.where(BOX, box).run(() -> {
            CounterBox first = BOX.get();

            first.increment();
            BOX.get().increment();

            System.out.println("Cùng object: " + (BOX.get() == box));
            System.out.println("Count trong scope: " + BOX.get().count());
        });

        System.out.println("Count sau scope: " + box.count());
        System.out.println("Còn binding? " + BOX.isBound());
    }
}
~~~

Kết quả:

~~~text
Cùng object: true
Count trong scope: 2
Count sau scope: 2
Còn binding? false
~~~

### Phân tích từng dòng

1. `BOX` là một khóa dùng chung để tra cứu context.
2. `box` là object có field `count` **mutable**.
3. `where(BOX, box)` bind **tham chiếu tới chính object đó**, không tự clone/copy object.
4. `BOX.get() == box` là `true` vì `get()` trả về cùng reference.
5. Gọi `increment()` sửa field của `CounterBox`; nó **không thay** ràng buộc `BOX → box`.
6. Thoát khỏi scope khiến binding biến mất, **không khôi phục trạng thái count** về 0.
7. Biến `box` vẫn còn tham chiếu tới object, nên thấy `count = 2` ngay cả ngoài scope.

### Kết luận định lượng

| Thao tác | Binding thay đổi? | Object thay đổi? |
| --- | --- | --- |
| `BOX.get()` | Không | Không |
| `BOX.get().increment()` | **Không** | **Có** |
| Thoát khỏi `run(...)` | Binding hiện tại hết hiệu lực/phục hồi binding trước đó | Object **không tự rollback** |
| Thực thi nested `where(BOX, other)` | Có **binding mới trong scope con** | Không bắt buộc |
| Thay một field mutable trong object | Không | Có |
| Tạo object mới bằng `new CounterBox(...)` | Không, cho tới khi bind vào scope khác | Tạo object khác |

Do đó: **tính bất biến của binding không bảo đảm tính bất biến của giá trị** và cũng không mang lại transaction/rollback cho object mutable.

## 6. Nested rebinding khác mutation thế nào?

Một scoped value có thể được **bind lại trong một phạm vi con**. Đây là hành vi hợp lệ, không mâu thuẫn với immutable binding: mỗi scope có binding của riêng mình.

Tạo `NestedBindings.java`:

~~~java
public class NestedBindings {

    private static final ScopedValue<String> ROLE =
        ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(ROLE, "reader").run(() -> {
            System.out.println("Ngoài: " + ROLE.get());

            ScopedValue.where(ROLE, "admin").run(() -> {
                System.out.println("Trong: " + ROLE.get());
            });

            System.out.println("Phục hồi: " + ROLE.get());
        });

        System.out.println("Hết scope: " + ROLE.isBound());
    }
}
~~~

Đầu ra:

~~~text
Ngoài: reader
Trong: admin
Phục hồi: reader
Hết scope: false
~~~

Mô hình:

~~~mermaid
flowchart TD
    A[Chưa bind ROLE] --> B[Scope ngoài ROLE = reader]
    B --> C[Scope con ROLE = admin]
    C --> D[Scope con kết thúc]
    D --> E[Scope ngoài vẫn ROLE = reader]
    E --> F[Scope ngoài kết thúc, không còn binding]
~~~

**Điểm kỹ thuật:** trong scope con, lời gọi `ROLE.get()` trả về giá trị binding **gần nhất đang hoạt động**. Khi scope con kết thúc, binding của scope ngoài trở lại. Không cần và không nên tự gọi `remove()`.

### Không nhầm “rebind” với “set”

Với `ThreadLocal`, người lập trình có thể gọi `threadLocal.set(other)` trong cùng dòng xử lý, sau đó phải quan tâm cleanup. Với `ScopedValue`, bạn **không gọi setter**; bạn biểu thị vùng cần giá trị khác bằng **nested `where(...).run(...)`**. Đây là thay đổi về **cấu trúc vòng đời**, không phải chỉ đổi tên API.

## 7. Nested binding tới object khác và nested binding tới cùng object

Với object mutable, có hai tình huống thường bị nhầm.

### 7.1. Bind object mới trong scope con

~~~java
var outer = new CounterBox(1);
var inner = new CounterBox(100);

ScopedValue.where(BOX, outer).run(() -> {
    BOX.get().increment();                  // outer = 2

    ScopedValue.where(BOX, inner).run(() -> {
        BOX.get().increment();              // inner = 101
    });

    System.out.println(BOX.get().count());  // 2
});

System.out.println(inner.count());          // 101
~~~

Ở đây:

- Scope ngoài trỏ tới `outer`.
- Scope con trỏ tới `inner`.
- Hai objects có trạng thái khác nhau.
- Sau scope con, `BOX.get()` lại trỏ tới `outer`.
- Object `inner` vẫn có `count=101` nếu còn reference bên ngoài.

### 7.2. Bind lại **chính object cũ**

~~~java
var shared = new CounterBox(1);

ScopedValue.where(BOX, shared).run(() -> {
    ScopedValue.where(BOX, shared).run(() -> {
        BOX.get().increment();
    });

    System.out.println(BOX.get().count());  // 2
});
~~~

Scope con là scope khác nhưng **vẫn trỏ tới cùng object**. Vì vậy mutation trong scope con **lộ trở lại scope ngoài**. Không có snapshot/copy tự động chỉ vì ta gọi `where` lần thứ hai.

> Câu cần ghi nhớ: **rebind thay reference được nhìn thấy; mutate thay state của referent.** Nếu hai bindings trỏ tới cùng referent mutable, thay đổi state sẽ được quan sát qua cả hai bindings.

## 8. Mối quan hệ giữa final, record và tính bất biến thực sự

Trong Java, có nhiều cơ chế thường bị hiểu nhầm là “đảm bảo object immutable”:

| Cơ chế | Bảo đảm gì? | Không bảo đảm gì? |
| --- | --- | --- |
| `final` field | Không gán lại field sang reference khác sau khởi tạo hợp lệ | Object được field tham chiếu không thể đổi |
| `static final ScopedValue<T> KEY` | Không thay reference của biến `KEY` trong class | Mọi object `T` được bind đều immutable |
| `record` | Fields là final và API record theo cấu trúc cố định | Các phần tử mutable bên trong field không bị thay đổi |
| `List.copyOf(source)` | Danh sách trả về không hỗ trợ sửa cấu trúc thông qua API List | Đối tượng **phần tử** mutable không bị khóa |
| `Collections.unmodifiableMap(map)` | Chặn sửa map qua **view** này | Backing map có thể bị sửa qua alias khác |
| `Map.copyOf(map)` | Tạo bản sao map không sửa được qua API Map | Giá trị object nằm trong map có thể mutable |
| `ScopedValue.where(key, value)` | Binding theo dynamic scope | Referential/deep immutability của `value` |

Không nên dùng thuật ngữ **deep immutable** chỉ vì một record có fields final hoặc map đã được bọc bằng unmodifiable view.

### 8.1. Record với mutable collection vẫn thay đổi được

~~~java
import java.util.ArrayList;
import java.util.List;

record TraceContext(String traceId, List<String> checkpoints) {
}

class RecordIsShallow {

    private static final ScopedValue<TraceContext> CONTEXT =
        ScopedValue.newInstance();

    public static void main(String[] args) {
        var steps = new ArrayList<String>();
        var context = new TraceContext("trace-1", steps);

        ScopedValue.where(CONTEXT, context).run(() -> {
            CONTEXT.get().checkpoints().add("order");
        });

        System.out.println(steps);  // [order]
    }
}
~~~

Ở đây:

- Record field `checkpoints` là final.
- Nhưng field chứa reference tới **`ArrayList` mutable**.
- Lời gọi `add(...)` thay đổi chính collection.
- Người giữ reference `steps` bên ngoài scope cũng nhìn thấy phần tử mới.
- `ScopedValue` không sao chép record hoặc danh sách.

### 8.2. Tạo immutable snapshot bằng defensive copy

Nếu context dùng để trao đổi giữa nhiều tầng hoặc task, nên tạo snapshot ngay tại boundary:

~~~java
import java.util.List;
import java.util.Objects;

record SafeTraceContext(String traceId, List<String> checkpoints) {

    SafeTraceContext {
        Objects.requireNonNull(traceId, "traceId");
        checkpoints = List.copyOf(
            Objects.requireNonNull(checkpoints, "checkpoints"));
    }
}
~~~

Sử dụng:

~~~java
var input = new java.util.ArrayList<String>();
input.add("received");

var snapshot = new SafeTraceContext("trace-2", input);
input.add("mutated-outside");

ScopedValue.where(CONTEXT, snapshot).run(() -> {
    System.out.println(CONTEXT.get().checkpoints());
});
~~~

Để hai đoạn trên thực sự là **một chương trình Java** thì khóa `CONTEXT` phải được khai báo dưới dạng `ScopedValue<SafeTraceContext>` trong class chứa `main`; ví dụ chỉ trình bày ý tưởng chuyển từ kiểu context mutable sang immutable.

Với `List.copyOf`:

- Danh sách được giữ trong snapshot **không còn phản chiếu việc thêm/xóa** từ input list sau đó.
- Cố gọi `snapshot.checkpoints().add("x")` sẽ ném `UnsupportedOperationException`.
- **Không** suy ra immutable sâu nếu phần tử của List là object mutable. Ở ví dụ này phần tử là `String` — một kiểu immutable — nên snapshot an toàn hơn đáng kể.

**Khi dùng `Map.copyOf`:** áp dụng nguyên tắc tương tự. Nếu value là `UserProfile` mutable, map không cho thay key nhưng `profile.setName(...)` vẫn có thể thay đổi nội dung quan sát được.

## 9. Thiết kế RequestContext an toàn cho production

Một context thông dụng có thể được biểu diễn bằng record bất biến:

~~~java
package vn.example.context;

import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public record RequestContext(
        String requestId,
        String actorId,
        Locale locale,
        Map<String, String> attributes) {

    public RequestContext {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(actorId, "actorId");
        Objects.requireNonNull(locale, "locale");
        attributes = Map.copyOf(
            Objects.requireNonNull(attributes, "attributes"));
    }
}
~~~

Lớp giữ key:

~~~java
package vn.example.context;

public final class RequestScope {

    public static final ScopedValue<RequestContext> CURRENT =
        ScopedValue.newInstance();

    private RequestScope() {
    }

    public static RequestContext current() {
        return CURRENT.get();
    }

    public static void run(RequestContext context, Runnable action) {
        ScopedValue.where(CURRENT, context).run(action);
    }
}
~~~

Lớp sử dụng:

~~~java
package vn.example.context;

public final class AuditService {

    public void record(String operation) {
        var context = RequestScope.current();

        System.out.printf(
            "request=%s actor=%s operation=%s%n",
            context.requestId(),
            context.actorId(),
            operation);
    }
}
~~~

Ở boundary:

~~~java
var context = new RequestContext(
    "request-42",
    "actor-7",
    java.util.Locale.forLanguageTag("vi-VN"),
    java.util.Map.of("source", "rest"));

RequestScope.run(context, () -> {
    new AuditService().record("submit-order");
});
~~~

Một ứng dụng thực tế sẽ lấy `requestId` và `actorId` từ **nguồn tin cậy**, validate dữ liệu và đặt giới hạn kích thước cho `attributes`. Không tùy tiện tin header của client là user identity đã được xác thực.

### Vì sao dùng static final cho khóa?

Khóa phải được các phương thức downstream truy cập **đúng cùng instance**. Tạo `ScopedValue.newInstance()` mỗi lần gọi sẽ tạo **key khác**, nên không đọc được binding được tạo bằng key trước đó. Khai báo key cố định thường là cách dễ hiểu.

**Tuy nhiên:** `static final` bảo vệ biến `CURRENT` không bị gán lại, chứ không bảo vệ `RequestContext` khỏi mọi mutation nếu bạn cho phép nội dung mutable. Cần thiết kế cả hai lớp bảo đảm.

## 10. Sử dụng nhiều scoped keys cùng lúc

Trong một request, có thể cần nhiều giá trị độc lập: request ID, locale và chế độ xử lý.

~~~java
import java.util.Locale;

public class MultipleKeys {

    private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

    private static final ScopedValue<Locale> LOCALE =
        ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-25")
            .where(LOCALE, Locale.forLanguageTag("vi-VN"))
            .run(() -> {
                System.out.println(REQUEST_ID.get());
                System.out.println(LOCALE.get());
            });
    }
}
~~~

`ScopedValue.where(...).where(...).run(...)` là cách tạo carrier có nhiều bindings trong một dynamic scope, theo API Java 25.

Các keys độc lập giúp tránh tạo một object tổng hợp quá lớn, nhưng cũng có nhược điểm:

- Nếu có hàng chục keys, code khó biết request đã bind đủ những gì.
- Nếu một thao tác cần trạng thái nhất quán giữa nhiều keys, thiết lập chúng **trong một carrier** hoặc dùng một immutable context record.
- Nếu hai giá trị phải cập nhật như một transaction nghiệp vụ, `ScopedValue` **không** cung cấp transactional update; hãy dùng mô hình dữ liệu/business transaction phù hợp.

## 11. `get()`, `isBound()` và xử lý khi không có binding

Đọc ngoài scope:

~~~java
private static final ScopedValue<String> ID =
    ScopedValue.newInstance();

static void unsafe() {
    String requestId = ID.get();
}
~~~

Nếu key chưa có binding đang hoạt động, `get()` ném **`NoSuchElementException`**. Lỗi này là tín hiệu rằng helper được gọi ngoài phạm vi dự kiến.

Có hai cách tiếp cận:

### 11.1. Context là điều kiện bắt buộc

~~~java
static String requiredRequestId() {
    return ID.get();
}
~~~

Khi toàn bộ luồng nghiệp vụ yêu cầu context, **fail fast** giúp phát hiện thiếu boundary setup, thay vì âm thầm dùng một ID giả khiến log khó liên kết.

### 11.2. Context là tùy chọn

~~~java
static String optionalRequestId() {
    return ID.isBound() ? ID.get() : "no-request";
}
~~~

Chỉ dùng fallback nếu nghiệp vụ thực sự cho phép. Với authorization/security principal, **không được** coi thiếu context là một user có quyền mặc định.

Ngoài `get()` và `isBound()`, Java 25 còn cung cấp API như `orElse(...)`; cách chọn phụ thuộc vào việc thiếu binding có được xem là trường hợp bình thường hay lỗi thiết kế.

## 12. Scope kết thúc khi thành công hoặc ném exception

Một điểm mạnh của scoped binding là vòng đời được giới hạn bằng cấu trúc lời gọi. Không cần nhớ cleanup thủ công.

~~~java
public class ScopeExceptionDemo {

    private static final ScopedValue<String> ID =
        ScopedValue.newInstance();

    public static void main(String[] args) {
        try {
            ScopedValue.where(ID, "req-failed").run(() -> {
                System.out.println(ID.get());
                throw new IllegalStateException("demo failure");
            });
        } catch (IllegalStateException expected) {
            System.out.println("caught: " + expected.getMessage());
        }

        System.out.println(ID.isBound());  // false
    }
}
~~~

Kết thúc scope do exception vẫn phục hồi binding trước đó. **Nhưng** object mutable đã bị thay đổi trước khi exception xuất hiện không tự phục hồi.

Ví dụ nếu `BOX.get().increment()` chạy rồi action ném exception, `CounterBox.count` vẫn tăng. Nếu cần rollback state, phải dùng transaction, copy-on-write hoặc thiết kế thao tác có khả năng hoàn tác.

| Tình huống | Binding sau khi thoát action | Đối tượng mutable |
| --- | --- | --- |
| Action thành công | Phục hồi binding cũ / unbound | Giữ mutation đã xảy ra |
| Action ném exception | Phục hồi binding cũ / unbound | Giữ mutation, trừ khi logic riêng rollback |
| Nested action thành công | Trở lại binding scope ngoài | Giữ mutation trên object nào đã bị sửa |
| Nested action ném exception | Trở lại binding scope ngoài khi unwind | Không có rollback tự động |

## 13. Tại sao ScopedValue không phải một ThreadLocal mới có setter?

Một đoạn mã với `ThreadLocal`:

~~~java
private static final ThreadLocal<String> REQUEST_ID =
    new ThreadLocal<>();

static void process(String id) {
    REQUEST_ID.set(id);
    try {
        service();
    } finally {
        REQUEST_ID.remove();
    }
}
~~~

`ThreadLocal` là API còn được Java hỗ trợ và vẫn có use case phù hợp, nhưng được thiết kế cho **giá trị có thể gán lại theo thread**. Nếu quên cleanup trong thread pool, giá trị có thể tồn tại lâu ngoài request, gây rò thông tin hoặc làm request sau nhận context sai.

Với `ScopedValue`:

~~~java
private static final ScopedValue<String> REQUEST_ID =
    ScopedValue.newInstance();

static void process(String id) {
    ScopedValue.where(REQUEST_ID, id).run(() -> service());
}
~~~

### So sánh chính xác

| Tiêu chí | ThreadLocal | ScopedValue |
| --- | --- | --- |
| Cách thiết lập | `set(value)` | `where(key, value).run/call(action)` |
| Có setter thay giá trị trong cùng scope? | Có | Không |
| Cách kết thúc | Thường dùng `remove()` trong `finally` | Tự phục hồi khi action kết thúc |
| Nested override | Lập trình viên phải tự quản lý giá trị cũ | Nested `where` tạo binding scope con |
| Phù hợp dữ liệu mutable theo thời gian | Có thể, với cleanup và kiểm soát | Không phải mục tiêu ưu tiên |
| Phù hợp context read-mostly | Có nhưng yêu cầu quản lý vòng đời | Rất phù hợp |
| Coi object mutable thành immutable? | Không | **Không** |
| Thay thế hoàn toàn mọi tình huống? | Không | Không |

Cần phân biệt hai câu hỏi:

1. **Binding thay đổi như thế nào?** `ScopedValue` có ngữ nghĩa một chiều theo scope.
2. **Referent có thể được sửa không?** Vẫn tùy kiểu dữ liệu và cách chia sẻ reference.

Nếu yêu cầu công việc là một accumulator thay đổi liên tục xuyên các tầng, hãy cân nhắc truyền state rõ ràng, trả về kết quả, hoặc dùng một thiết kế có synchronization cụ thể; đừng lạm dụng `ScopedValue` để giấu một shared mutable object.

## 14. ScopedValue, thread và virtual threads: điều gì được chia sẻ?

Đặc điểm quan trọng của scoped binding là **ngữ cảnh thực thi có phạm vi**, không phải một biến global tồn tại đồng nhất trong mọi thread.

Một key `static final` có thể được nhiều thread dùng chung, nhưng **binding được quan sát bởi `get()` tùy ngữ cảnh thực thi của thread hiện tại**. Hai request xử lý trong hai thread khác nhau có thể bind cùng một key với các giá trị khác nhau mà không ghi đè binding lẫn nhau.

~~~text
Key chung: REQUEST_CONTEXT

Thread A / request A:
  where(REQUEST_CONTEXT, contextA).run(...)

Thread B / request B:
  where(REQUEST_CONTEXT, contextB).run(...)
~~~

Trong phạm vi tương ứng, A thấy `contextA` và B thấy `contextB`. Đây là lợi ích cho request-scoped context.

### 14.1. Thread mới không tự động “nhìn thấy” binding

Đừng giả định một thread mới bất kỳ — kể cả **virtual thread** — tự nhận mọi `ScopedValue` binding đang hoạt động ở thread tạo ra nó.

Ví dụ `ThreadBoundary.java`:

~~~java
public class ThreadBoundary {

    private static final ScopedValue<String> ID =
        ScopedValue.newInstance();

    public static void main(String[] args)
            throws InterruptedException {

        ScopedValue.where(ID, "request-parent").run(() -> {
            Thread worker = Thread.ofVirtual().start(() -> {
                System.out.println(
                    "Worker isBound: " + ID.isBound());
            });

            try {
                worker.join();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        });
    }
}
~~~

Với thread được tạo **không qua cơ chế thừa kế scope có cấu trúc**, worker không có binding đang hoạt động như parent chỉ vì được tạo trong body `run`. Ví dụ trên minh họa một **unstructured virtual thread**, không phải task được fork bởi một structured task scope.

Điểm cần phân biệt:

- **Virtual threads** là tính năng chính thức và phù hợp trong Java 25.
- **ScopedValue** cũng là tính năng chính thức ở Java 25.
- **Structured concurrency** tại JDK 25 vẫn có trạng thái preview (JEP 505). Các cấu trúc task scope của API preview có thể hỗ trợ thừa kế scoped bindings xuống subtasks theo quy tắc riêng; bài này **không yêu cầu bật preview**, cũng không coi API preview là phần ổn định của Java 25.
- Với executor hoặc thread tự quản lý, cần thiết kế context propagation rõ ràng, không tự suy ra propagation chỉ vì các API đều liên quan concurrency.

### 14.2. Truyền snapshot khi cần chuyển công việc sang executor

Có thể chuyển một **snapshot bất biến** sang task khác, rồi bind lại cho phạm vi của task đó:

~~~java
record RequestInfo(String requestId, String actorId) {
}

static final ScopedValue<RequestInfo> CURRENT =
    ScopedValue.newInstance();

static void handleInWorker(
        java.util.concurrent.ExecutorService executor)
        throws Exception {

    var snapshot = new RequestInfo("req-42", "actor-7");

    var future = executor.submit(() ->
        ScopedValue.where(CURRENT, snapshot).call(() -> {
            return CURRENT.get().requestId();
        }));

    System.out.println(future.get());
}
~~~

Đoạn trên là **một method minh họa** cần đặt bên trong class, truyền executor đã tạo và bảo đảm shutdown executor ở tầng gọi. Nó dùng cùng object `snapshot` ở hai phạm vi thực thi nếu bạn cũng bind snapshot ở parent. Vì `RequestInfo` chỉ chứa hai `String` immutable, sharing lành mạnh hơn so với một object có `HashMap` được nhiều worker sửa đồng thời.

Lưu ý: đây là **truyền và bind tường minh**, không phải inheritance tự động. Nếu worker phải tiếp tục thực thi sau khi request gốc đã kết thúc, hãy xác định policy về quyền truy cập, hết hạn dữ liệu, audit và tính hợp lệ của context — không tự coi object snapshot là một phiên đăng nhập có quyền không thời hạn.

## 15. Đối tượng mutable chia sẻ giữa các thread: bất biến binding không cứu race condition

Xét:

~~~java
static final ScopedValue<MutableCounter> COUNTER =
    ScopedValue.newInstance();

static final class MutableCounter {
    int value;

    void increment() {
        value++; // Đọc, cộng, ghi: không atomic
    }
}
~~~

Nếu nhiều threads được bind tới **cùng một instance `MutableCounter`**, hai thao tác `increment()` có thể xảy ra đồng thời. `value++` không atomic và không tạo bảo đảm memory visibility thích hợp. Kết quả có thể bị **lost update**.

**Không có bảo đảm đồng bộ hóa nào được bổ sung chỉ vì reference được truy cập qua `ScopedValue.get()`.**

### Ba chiến lược an toàn hơn

**Chiến lược A — immutable snapshot, không mutation:** context chứa `requestId`, `Locale`, danh mục permission và các record bất biến. Các tasks chỉ đọc dữ liệu.

**Chiến lược B — thread confinement:** mỗi task sở hữu riêng mutable object; không truyền cùng reference cho hai tasks đồng thời. Trạng thái tích lũy được trả về bằng result rồi hợp nhất ở owner.

**Chiến lược C — mutation có synchronization rõ ràng:** nếu thật sự cần bộ đếm dùng chung, cân nhắc `AtomicInteger` hoặc cơ chế bảo vệ state phù hợp, nhưng chỉ áp dụng sau khi kiểm tra yêu cầu toàn vẹn nghiệp vụ. Thread-safe mutation vẫn **không đồng nghĩa immutable**.

Ví dụ với `AtomicInteger`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class SharedCounter {

    static final ScopedValue<AtomicInteger> TOTAL =
        ScopedValue.newInstance();

    static void increment() {
        TOTAL.get().incrementAndGet();
    }
}
~~~

Nếu nhiều tasks bind tới cùng một `AtomicInteger`, `incrementAndGet()` hỗ trợ cập nhật nguyên tử cho **một biến đếm**. Nhưng giá trị vẫn thay đổi, được nhìn thấy bởi các phạm vi cùng trỏ tới object. Với state gồm nhiều field, một atomic counter không thay thế transaction/synchronization cho toàn bộ invariant.

### Câu hỏi cần hỏi khi review

1. Object được bind có immutable thật không?
2. Có reference alias ở ngoài scope không?
3. Có nested binding tới cùng object không?
4. Có executor/virtual thread nhận chung object không?
5. Có mutation sau khi scope parent kết thúc không?
6. Nếu nhiều thread đọc/ghi, cơ chế *happens-before* và concurrency control là gì?
7. Nếu lỗi, có cần rollback business state không?

Nếu chưa trả lời được, **chưa thể kết luận an toàn** chỉ vì code sử dụng `ScopedValue`.

## 16. Context có thể “thoát scope” qua reference alias

Một hiểu lầm khác: “ScopedValue chỉ sống trong `run` nên object tự bị hủy sau `run`.”

**Sai.** Khi scope kết thúc, **binding** bị gỡ/phục hồi. Object vẫn tồn tại nếu còn reference khác.

~~~java
public class EscapingReference {

    private static final ScopedValue<StringBuilder> BUFFER =
        ScopedValue.newInstance();

    public static void main(String[] args) {
        StringBuilder shared = new StringBuilder("start");

        ScopedValue.where(BUFFER, shared).run(() -> {
            BUFFER.get().append("-inside");
        });

        // Không còn binding, nhưng shared vẫn tồn tại.
        System.out.println(BUFFER.isBound()); // false
        System.out.println(shared);           // start-inside
    }
}
~~~

Với đối tượng yêu cầu quản lý vòng đời — socket, stream, kết nối database, session — `ScopedValue` **không thay thế** `try-with-resources` hoặc quy tắc cleanup tài nguyên. Nếu bạn bind một mutable connection và code lưu lại reference để dùng ngoài scope, hệ thống vẫn có rủi ro lifecycle.

Đối với audit/security context, không bao giờ giả định “thoát scope sẽ xóa mọi bản sao dữ liệu nhạy cảm”. Dữ liệu có thể đã bị copy vào log, cache, static field hoặc executor task.

## 17. Có nên bind một mutable Map để truyền thông tin giữa middleware?

Một mẫu dễ gặp:

~~~java
static final ScopedValue<java.util.Map<String, Object>> BAG =
    ScopedValue.newInstance();

static void stepA() {
    BAG.get().put("requestId", "req-25");
}

static void stepB() {
    Object id = BAG.get().get("requestId");
}
~~~

Về mặt kỹ thuật, `BAG.get().put(...)` có thể chạy nếu map mutable. Nhưng các vấn đề thiết kế là:

- **Data flow ẩn:** `stepB` phụ thuộc việc `stepA` đã ghi đúng key trước đó.
- **Thời điểm đọc:** chạy step khác thứ tự có thể cho null hoặc dữ liệu cũ.
- **Không có type safety:** cast sai có thể gây `ClassCastException`.
- **Concurrency:** chia sẻ map giữa tasks có thể tạo race/corruption nếu dùng implementation không thread-safe.
- **Test isolation:** unit test từng method khó biết cần chuẩn bị những key nào.
- **Khó audit:** một helper bất kỳ có thể sửa context của phần còn lại.

### Thiết kế đề xuất: chuyển đổi dữ liệu thành snapshot

Thay vì sửa một map dùng chung, hãy:

1. Thu thập request metadata tại boundary.
2. Validate và normalize dữ liệu đầu vào.
3. Tạo `RequestContext` immutable.
4. Bind một lần trong scope.
5. Truyền kết quả nghiệp vụ bằng return value, event hoặc repository thay vì “đẩy state vào context map”.
6. Khi cần thay đổi ngữ cảnh chính đáng, tạo **record mới** và nested bind ở vùng cụ thể.

Ví dụ cập nhật immutable context theo phong cách copy-on-write:

~~~java
record Context(String requestId, String mode) {
    Context withMode(String newMode) {
        return new Context(requestId, newMode);
    }
}

static final ScopedValue<Context> CTX =
    ScopedValue.newInstance();

static void execute() {
    var initial = new Context("req-8", "normal");

    ScopedValue.where(CTX, initial).run(() -> {
        process();

        var privileged = CTX.get().withMode("review");
        ScopedValue.where(CTX, privileged).run(() -> {
            process();
        });

        process(); // Quay về mode "normal".
    });
}
~~~

`process()` ở đây là helper nghiệp vụ giả định. **Đừng dùng ví dụ này để thực hiện nâng quyền truy cập bảo mật một cách tùy tiện**; giá trị `mode` chỉ mô tả cấu hình xử lý, còn authorization phải được quyết định bởi policy tin cậy riêng.

## 18. ScopedValue không phải kho dữ liệu giao dịch hay message bus

Giới hạn rất quan trọng trong hệ thống lớn:

| Nhu cầu | ScopedValue có phù hợp? | Vì sao |
| --- | --- | --- |
| Request ID, locale, tracing baggage đã kiểm soát | Thường phù hợp | Đọc nhiều, thiết lập trong scope |
| Actor identity đã xác thực | Có thể phù hợp, với boundary tin cậy | Context không thay security enforcement |
| Thay đổi số dư, tồn kho | Không nên dùng làm nơi lưu state chính | Cần transaction/database và invariants |
| Bộ đếm global | Không | Cần counter/storage có concurrency semantics |
| Chia sẻ mutable cache cho mọi request | Không nên | Là shared state ngoài trách nhiệm ScopedValue |
| Truyền message qua process/network | Không | Scope của một Java execution không tự serialize đi xa |
| Rollback object mutable sau exception | Không | Binding restoration khác data rollback |
| Correlation metadata trong lời gọi lồng nhau | Phù hợp | Dynamic scope giúp giảm parameter plumbing |
| Context propagation qua executor bất kỳ | Không tự động | Cần API/cơ chế propagation rõ ràng |

Một thực hành tốt là **không đưa `ScopedValue` vào domain model như một dependency ngầm** nếu domain logic có thể nhận rõ dữ liệu đầu vào. Dùng nó tại infrastructure boundary hoặc cross-cutting concerns (logging, correlation, locale) khi lợi ích đủ rõ.

## 19. Tích hợp với logging, observability và JFR

Ví dụ đọc request context để ghi log:

~~~java
static final ScopedValue<RequestContext> CURRENT =
    ScopedValue.newInstance();

static void logStep(String message) {
    var ctx = CURRENT.get();
    System.out.printf(
        "requestId=%s actorId=%s message=%s%n",
        ctx.requestId(),
        ctx.actorId(),
        message);
}
~~~

**Lưu ý:** bản thân `ScopedValue` **không phải hệ thống tracing** và không tự sinh span. Khi ứng dụng dùng Micrometer/OpenTelemetry/JFR:

- Trace context/span lifecycle phải do công cụ tracing quản lý đúng quy tắc của nó.
- Nếu muốn đặt `requestId` vào logs, phải quyết định cách tương tác với logger/structured logging của framework.
- Với JFR, các sự kiện JVM/ứng dụng được ghi theo cơ chế recording; không được giả định `ScopedValue` tự động đưa toàn bộ object context vào JFR events.
- Nếu đưa metadata vào custom JFR event hoặc span attribute, cần kiểm soát dữ liệu nhạy cảm và cardinality.
- `ScopedValue` không tự thay thế context propagation của tracing khi công việc đi qua queue, HTTP hoặc thread không có inherited binding.

Trong Java 25, **JFR** vẫn là công cụ hiện đại để quan sát runtime, nhưng không làm cho việc bind mutable object trở nên an toàn hơn. Chọn immutable context trước; instrumentation chỉ giúp phát hiện/chẩn đoán hành vi.

## 20. Viết test cho tính bất biến của binding

Dùng JUnit 5 trong một dự án Java 25 có dependency test phù hợp. Đoạn dưới là **một class test độc lập** nếu có JUnit Jupiter.

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ScopedBindingTest {

    private static final ScopedValue<String> KEY =
        ScopedValue.newInstance();

    @Test
    void nestedBindingRestoresOuterValue() {
        assertFalse(KEY.isBound());

        ScopedValue.where(KEY, "outer").run(() -> {
            assertEquals("outer", KEY.get());

            ScopedValue.where(KEY, "inner").run(() -> {
                assertEquals("inner", KEY.get());
            });

            assertEquals("outer", KEY.get());
        });

        assertFalse(KEY.isBound());
    }

    @Test
    void missingBindingDoesNotReturnAValue() {
        assertFalse(KEY.isBound());
        assertThrows(
            java.util.NoSuchElementException.class,
            KEY::get);
    }

    @Test
    void exceptionDoesNotLeaveBindingBehind() {
        assertThrows(IllegalStateException.class, () ->
            ScopedValue.where(KEY, "request").run(() -> {
                throw new IllegalStateException("failed");
            }));

        assertFalse(KEY.isBound());
    }
}
~~~

**Ý nghĩa của bộ test:**

- Nested scope phục hồi value của scope ngoài.
- `get()` ngoài scope gây lỗi đúng contract.
- Exception không làm binding bị rò sang test tiếp theo qua cùng thread.

Các tests này **chưa kiểm chứng object được bind có bất biến hay không**; muốn kiểm tra thuộc tính đó cần một test riêng.

## 21. Viết test chứng minh object vẫn mutable

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MutableReferentTest {

    private static final ScopedValue<StringBuilder> TEXT =
        ScopedValue.newInstance();

    @Test
    void bindingIsStableButReferentIsMutable() {
        var buffer = new StringBuilder("A");

        ScopedValue.where(TEXT, buffer).run(() -> {
            assertSame(buffer, TEXT.get());

            TEXT.get().append("B");

            assertSame(buffer, TEXT.get());
            assertEquals("AB", TEXT.get().toString());
        });

        assertFalse(TEXT.isBound());
        assertEquals("AB", buffer.toString());
    }

    @Test
    void nestedBindingToAnotherObjectRestoresReference() {
        var outer = new StringBuilder("outer");
        var inner = new StringBuilder("inner");

        ScopedValue.where(TEXT, outer).run(() -> {
            ScopedValue.where(TEXT, inner).run(() -> {
                TEXT.get().append("-changed");
                assertSame(inner, TEXT.get());
            });

            assertSame(outer, TEXT.get());
            assertEquals("outer", TEXT.get().toString());
        });

        assertEquals("inner-changed", inner.toString());
    }

    @Test
    void nestedBindingToSameObjectDoesNotIsolateMutation() {
        var shared = new StringBuilder("start");

        ScopedValue.where(TEXT, shared).run(() -> {
            ScopedValue.where(TEXT, shared).run(() ->
                TEXT.get().append("-child"));

            assertEquals("start-child", TEXT.get().toString());
        });
    }
}
~~~

Các assertion này trả lời đúng đề bài:

1. Reference từ `get()` ổn định trong binding.
2. Mutating method vẫn sửa được object.
3. Nested binding tới **object khác** làm scope ngoài quan sát lại reference trước đó.
4. Nested binding tới **cùng object** không tạo bản sao và không chống mutation.

Trong code thực tế, đừng dùng `StringBuilder` chia sẻ giữa nhiều threads như một mutable context vì nó không được đồng bộ hóa cho kiểu sharing đó.

## 22. Test immutable snapshot và defensive copy

~~~java
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SnapshotTest {

    record Context(String id, List<String> tags) {
        Context {
            tags = List.copyOf(tags);
        }
    }

    private static final ScopedValue<Context> CURRENT =
        ScopedValue.newInstance();

    @Test
    void changingSourceListDoesNotChangeSnapshot() {
        var input = new ArrayList<String>();
        input.add("initial");

        var snapshot = new Context("req-1", input);
        input.add("later");

        ScopedValue.where(CURRENT, snapshot).run(() -> {
            assertEquals(
                List.of("initial"),
                CURRENT.get().tags());

            assertThrows(
                UnsupportedOperationException.class,
                () -> CURRENT.get().tags().add("wrong"));
        });
    }
}
~~~

Test này xác nhận:

- Constructor đã chụp bản sao của danh sách đầu vào.
- Thay đổi input list sau đó không ảnh hưởng snapshot.
- API của list trong record không cho phép thêm phần tử.
- Binding cho cùng snapshot vẫn tự phục hồi khi scope kết thúc.

Nó **không chứng minh deep immutability của mọi object tùy ý**. Muốn bảo đảm sâu, phải kiểm tra cả kiểu phần tử và tất cả object mutable được tham chiếu bên trong.

## 23. Những sai lầm dễ mắc khi review

### 23.1. “Không có `set()` nghĩa là dữ liệu không thể thay đổi”

**Sai.** Không có setter cho **binding**, nhưng `KEY.get().mutate()` có thể sửa object.

### 23.2. “Nested `where` tạo bản sao của object”

**Sai.** `where(KEY, object)` bind reference; nếu scope con và scope ngoài bind cùng object, chúng cùng thấy mutation.

### 23.3. “Thoát scope sẽ hoàn tác tất cả thay đổi”

**Sai.** Binding được phục hồi/unbound; database transaction, field mutations hoặc collection changes không tự rollback.

### 23.4. “`record` có nghĩa tất cả field bên trong immutable sâu”

**Sai.** Record components là final fields, nhưng một `List<User>` vẫn có thể chứa `User` mutable và một getter vẫn có thể trả reference tới mutable collection nếu không defensive-copy.

### 23.5. “`Map.copyOf` làm mọi value trong map thành immutable”

**Sai.** Bản thân map không hỗ trợ sửa cấu trúc thông qua API Map, nhưng object value có thể mutable.

### 23.6. “Có thể dùng mutable context đồng thời mà không cần synchronization”

**Sai.** `ScopedValue` không cung cấp atomicity, memory visibility hoặc happens-before cho mọi mutation của referent. Mọi shared mutable state cần concurrency design riêng.

### 23.7. “Một virtual thread mới luôn kế thừa ScopedValue của parent”

**Sai nếu nói như một quy tắc chung.** Context inheritance có điều kiện theo cơ chế task/structured concurrency, không tự xảy ra cho mọi cách khởi tạo thread hay executor.

### 23.8. “ScopedValue thay thế hoàn toàn ThreadLocal”

**Không chính xác.** Cả hai API còn được hỗ trợ. `ScopedValue` tối ưu mô hình context read-mostly và dynamic scope; `ThreadLocal` có ngữ nghĩa cho giá trị per-thread có thể gán lại, khi thật sự cần và có cleanup phù hợp.

### 23.9. “Dùng ScopedValue thì traceId tự truyền qua HTTP”

**Sai.** Context qua network cần giao thức propagation riêng, ví dụ tracing headers được xác thực/xử lý bởi instrumentation. `ScopedValue` không tự serialize hay gửi context.

### 23.10. “ScopedValue vẫn là preview trong Java 25”

**Lỗi thời.** `ScopedValue` đã được chuẩn hóa trong Java 25 (JEP 506). Không thêm preview flags cho những ví dụ chỉ dùng `java.lang.ScopedValue`.

## 24. Ma trận lựa chọn thiết kế

| Tình huống | Giải pháp khuyến nghị | Rủi ro nếu làm khác |
| --- | --- | --- |
| Request ID là String | Bind trực tiếp `ScopedValue<String>` | Thường không có mutation risk vì String immutable |
| Locale của request | Bind `Locale` hoặc immutable record | Có thể thiếu context ở thread ngoài scope |
| Read-only request metadata | Record + `Map.copyOf` với values immutable | Mutable map lộ state giữa tầng |
| Cần override tạm thời chế độ xử lý | Tạo snapshot mới + nested `where` | Sửa field của object cũ làm ảnh hưởng outer scope |
| Accumulator chỉ một task sở hữu | Truyền object/result rõ ràng; thread-confined | Giấu state trong `ScopedValue` khiến data flow khó hiểu |
| Shared counter giữa tasks | `AtomicInteger`/cơ chế đồng bộ và explicit design | `count++` lost updates |
| Data cần rollback | Database transaction hoặc snapshot/restore rõ ràng | Tưởng binding cleanup rollback object |
| Async task từ thread không có scope thừa kế | Truyền immutable snapshot và bind lại | Worker bị unbound, context sai |
| User identity/security | Immutable verified principal + authorization ở boundary | Lạm dụng rebind để nâng quyền |
| Tracing cross-service | Tracing propagation theo chuẩn của framework | Tưởng ScopedValue tự động mang trace qua network |

## 25. Bài tập tổng hợp

### Bài tập A — dự đoán trước khi chạy

Cho đoạn code:

~~~java
var state = new CounterBox(5);

ScopedValue.where(BOX, state).run(() -> {
    BOX.get().increment();

    ScopedValue.where(BOX, state).run(() -> {
        BOX.get().increment();
    });
});

System.out.println(state.count());
~~~

**Câu hỏi:** giá trị in ra là bao nhiêu? Có bao nhiêu bindings đã được tạo? Vì sao object vẫn thay đổi dù không có `BOX.set(...)`?

**Đáp án định hướng:** `state.count()` thành **7**. Có binding ở scope ngoài và binding scope con, nhưng cả hai trỏ tới **cùng một object**. Increment thay state của object chứ không thay binding.

### Bài tập B — so sánh hai nhánh nested binding

Tạo hai `CounterBox` khác nhau. Bind object A ở scope ngoài, object B ở scope con, tăng B và kiểm tra A không đổi. Sau khi ra scope con, xác minh `BOX.get() == A`.

**Đạt khi:** nêu được sự khác nhau giữa **reference rebinding** và **mutation**.

### Bài tập C — sửa record chứa mutable list

Một record khai báo:

~~~java
record RequestData(String id, List<String> roles) {
}
~~~

Hãy bổ sung compact canonical constructor với `List.copyOf(roles)`, test rằng sửa input list không làm thay đổi record và caller không sửa được list trả ra. Nếu `roles` là danh sách object mutable, giải thích vì sao cần một chiến lược copy sâu hơn hoặc immutable element type.

**Đạt khi:** phân biệt final field, unmodifiable collection và deep immutable graph.

### Bài tập D — thay ThreadLocal ở request boundary

Cho một middleware sử dụng `ThreadLocal<RequestContext>` chỉ để set một lần rồi đọc nhiều nơi. Chuyển sang `ScopedValue`, dùng `where(...).run(...)` và thêm test exception để xác minh không rò binding.

**Đạt khi:** không gọi setter/remove, không dùng context thiếu binding để bypass authorization và không tự kéo mutable state sang flow mới.

### Bài tập E — phân tích concurrent tasks

Cho hai worker cùng xử lý một `AtomicInteger` hoặc `HashMap` trong context. Xác định:

1. Hai tasks có đang dùng **cùng object** hay không?
2. Ai sở hữu lifecycle và quy tắc update của object?
3. Kiểu dữ liệu có thread-safe cho hoạt động cần thiết không?
4. Có thể thay bằng immutable snapshots + results riêng không?
5. Có cần đảm bảo order, atomicity hoặc consistency giữa nhiều field không?

**Đạt khi:** hiểu rằng một binding bất biến **không** thay thế synchronization cho referent mutable.

### Bài tập F — JUnit regression suite

Viết test cho:

- Binding chưa có: `isBound() == false`, `get()` ném `NoSuchElementException`.
- Bind một `String`: value đúng trong scope và hết binding sau scope.
- Nested rebind tới giá trị khác: outer value được phục hồi.
- Bind `StringBuilder`: reference không đổi, nội dung được append.
- Nested bind tới cùng `StringBuilder`: mutation vẫn nhìn thấy ở scope ngoài.
- Exception: binding cleanup nhưng referent mutation không rollback.
- Record + `List.copyOf`: input mutation không làm thay đổi snapshot.
- Worker chạy ngoài cơ chế inheritance có cấu trúc: context không tự nhiên có mặt; cần snapshot/binding ở boundary rõ ràng.

**Đạt khi:** test phân biệt được **binding lifecycle**, **object lifecycle** và **thread lifecycle**.

### Checklist tự đánh giá

- [ ] Biết `ScopedValue` Java 25 đã là final API, không cần preview.
- [ ] Giải thích được key, binding, reference và referent khác nhau thế nào.
- [ ] Không đánh đồng immutable binding với immutable object.
- [ ] Biết `get()` chỉ đọc binding hiện hành, không clone object.
- [ ] Biết nested `where` tạo binding trong scope con và phục hồi binding ngoài.
- [ ] Hiểu nested binding tới cùng object không chặn mutation.
- [ ] Biết exception unwind phục hồi binding nhưng không rollback state.
- [ ] Biết `final`/`record`/`List.copyOf`/`Map.copyOf` bảo vệ những gì.
- [ ] Ưu tiên immutable snapshots khi truyền metadata qua các tầng hoặc task.
- [ ] Không giả định virtual threads hoặc executor bất kỳ tự nhận scoped binding.
- [ ] Phân biệt ScopedValue với ThreadLocal, transaction và tracing propagation.
- [ ] Có bộ test khẳng định binding và referent là hai thuộc tính khác nhau.

## 26. Tài liệu tham khảo chính thức

Đối với Java 25, ưu tiên tài liệu cho **đúng release** và tránh ví dụ dùng API preview cũ:

1. [JEP 506 — Scoped Values (final in JDK 25)](https://openjdk.org/jeps/506): mục tiêu, mô hình immutable bindings, rebind và thừa kế trong structured concurrency.
2. [Java SE 25 API — java.lang.ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): contract của `newInstance`, `where`, `get`, `isBound` và các API scope.
3. [Oracle Java 25 — Scoped Values](https://docs.oracle.com/en/java/javase/25/core/scoped-values.html): hướng dẫn sử dụng context theo dynamic scope.
4. [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): tham khảo riêng để hiểu propagation theo task scope; **vẫn preview trong Java 25**, không phải dependency bắt buộc của bài này.
5. [Java SE 25 API — java.util.List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): defensive copying và giới hạn bất biến nông của phần tử.

**Kết quả mong đợi:** người học hiểu `ScopedValue` cố định **ràng buộc key → value reference trong một phạm vi thực thi**, nhưng không khóa **trạng thái của object được tham chiếu**. Vì thế, dùng immutable request context và snapshot là thực hành tốt cho ứng dụng Java 25; khi cần shared mutable state vẫn phải thiết kế ownership, concurrency và transaction tường minh.
