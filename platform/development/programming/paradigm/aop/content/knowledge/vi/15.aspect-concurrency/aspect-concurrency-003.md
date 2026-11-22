# Tách dữ liệu cấu hình bất biến khỏi trạng thái mỗi lần gọi trong Aspect

## 1. Vấn đề thực sự: cùng một aspect xử lý nhiều lần gọi

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming – AOP)**, một **aspect** đóng gói **pointcut** và **advice** cho mối quan tâm cắt ngang: audit, logging, tracing, kiểm tra chính sách, đo thời gian, retry hoặc kiểm soát truy cập. Trong nhiều mô hình, một **aspect instance được dùng chung** để xử lý nhiều join point hoặc nhiều lần xuất hiện của cùng một join point.

Điều đó không có nghĩa mọi dữ liệu mà advice sử dụng cũng nên đặt vào một **field dùng chung**.

Một advice có thể cần **hai loại dữ liệu có vòng đời hoàn toàn khác nhau**:

- **Cấu hình/chính sách (configuration/policy):** những giá trị làm nền cho hành vi, ví dụ giới hạn số lần retry, mẫu định danh method được theo dõi, nhãn metric, ngưỡng thời gian, những nhóm lỗi được phép chuyển đổi. Chúng thường được đọc bởi nhiều invocation và có thể được biểu diễn thành **bất biến (immutable)**.
- **Trạng thái của một lượt gọi (per-invocation state):** mã tương quan của lượt hiện tại, thời điểm bắt đầu, argument đã chọn, số retry đã thử, kết quả tạm, Throwable đang xử lý. Những giá trị này **phải gắn đúng lượt invocation**, không vô tình bị lượt khác ghi đè.

Một thiết kế tốt thường có dạng:

```text
                      Aspect dùng chung
                    +--------------------+
                    | ConfigStore        |
                    | Policy snapshot    |
                    | Helpers stateless  |
                    +---------+----------+
                              |
             +----------------+----------------+
             |                |                |
        Invocation A     Invocation B     Invocation C
        +------------+   +------------+   +------------+
        | config@v1  |   | config@v2  |   | config@v2  |
        | start_A    |   | start_B    |   | start_C    |
        | args_A     |   | args_B     |   | args_C     |
        | result_A   |   | result_B   |   | error_C    |
        +------------+   +------------+   +------------+
```

**Nguyên tắc trung tâm:** *Dùng cấu hình bất biến có thể chia sẻ an toàn; chọn một snapshot nhất quán cho từng lượt gọi; giữ những dữ liệu biến đổi riêng của lượt gọi trong local variables hoặc invocation context có vòng đời rõ ràng.*

> **Phạm vi:** Bài này trình bày kiến thức AOP cơ bản và nâng cao nói chung, không gắn vào một công cụ cụ thể. “Around advice”, “before/after advice”, “join point”, “proxy” và “weaving” là các khái niệm tổng quát; từng công cụ có API, instantiation policy và mức hỗ trợ khác nhau. Ví dụ Java 17+ dùng Java Dynamic Proxy để thực nghiệm **nguyên tắc tách cấu hình và trạng thái**, không giả định mọi AOP đều triển khai bằng proxy.

## 2. Phân loại dữ liệu trước khi quyết định đặt ở đâu

Một aspect có thể cần tới ít nhất bốn nhóm dữ liệu:

| Nhóm | Ví dụ | Phạm vi sở hữu hợp lý |
| --- | --- | --- |
| **Cấu hình tương đối ổn định** | `maxAttempts`, ngưỡng log, tập prefix cấm | Immutable snapshot dùng chung |
| **Metadata bất biến** | Tên method, chữ ký, quy tắc pointcut đã phân tích | Read-only metadata/cache có key chuẩn |
| **State mỗi invocation** | `startNanos`, `currentId`, `attempt`, selected argument | Biến local trong around hoặc invocation context |
| **State tổng hợp lâu dài** | Tổng số lời gọi, circuit state, cache counters | Shared component có concurrency contract |
| **State theo request/task** | Trace ID, actor/context đã xác minh | Context với propagation và cleanup riêng |
| **State theo target** | Cache riêng target, counter per-object | Per-target association nếu phù hợp |

Không nên gom tất cả thành một object lớn tên `AspectContext` rồi gắn lên singleton aspect. Khi đó các field per-invocation sẽ trở thành dữ liệu chia sẻ ngoài ý muốn.

### Một trường hợp dễ nhầm

```java
// Ví dụ sai về phạm vi state, không phải chương trình độc lập.
final class LoggingAspect {
    private final int maxLength = 120; // Cấu hình có thể dùng chung.
    private String currentUser;        // Sai nếu dùng cho từng request.
    private long startNanos;           // Sai nếu dùng cho từng invocation.
}
```

`maxLength` là một giá trị cấu hình; nếu không đổi theo thời gian thì việc dùng chung hoàn toàn hợp lý. Nhưng `currentUser` và `startNanos` có ý nghĩa với **một hoạt động cụ thể**. Nếu hai lời gọi chạy đồng thời hoặc lồng nhau, một invocation có thể đọc giá trị của invocation khác.

## 3. Immutable config không phải “mọi field đều phải final”

Một class có field `final` không tự động bất biến sâu:

```java
// Minh họa antipattern.
final class WeakPolicy {
    final java.util.Set<String> forbiddenPrefixes;

    WeakPolicy(java.util.Set<String> source) {
        this.forbiddenPrefixes = source; // Giữ alias mutable của caller.
    }
}
```

Caller tạo một `HashSet` rồi truyền vào constructor. Nếu `WeakPolicy` giữ **chính reference đó**, caller còn có thể `source.add("X")` về sau, làm “cấu hình” thay đổi **không đi qua cơ chế publish/reload**.

**`final` bảo vệ việc gán lại reference của field, không tự ngăn object được reference tới bị mutate.**

### Các điều kiện thường cần cho một snapshot bất biến

1. Field không được reassign sau khi xây dựng.
2. Những mutable collection được **defensive copy** hoặc dùng persistent immutable structure thích hợp.
3. Không để lộ mutable array/list/map bên trong qua getter.
4. Các phần tử lồng nhau cũng phải bất biến hoặc được sao chép phù hợp.
5. Constructor xác minh invariant: giới hạn không âm, tên phiên bản hợp lệ, không có element null ngoài quy tắc, policy không mâu thuẫn.
6. Không để `this` “thoát” khỏi constructor trước khi khởi tạo xong.
7. Khi reload, tạo **snapshot mới** thay vì chỉnh sửa snapshot đang có nhiều caller sử dụng.

### Java 17 record là công cụ tiện lợi, nhưng chỉ shallowly immutable

```java
// Một ví dụ độc lập về data holder.
record Policy(String version, int maxLength,
              java.util.Set<String> prefixes) {
    Policy {
        if (maxLength <= 0) {
            throw new IllegalArgumentException("maxLength");
        }
        prefixes = java.util.Set.copyOf(prefixes);
    }
}
```

Record có các component fields ngầm là `final`, và `Set.copyOf` tạo hoặc dùng một unmodifiable set theo contract. Với `Set<String>`, cả cấu trúc set lẫn `String` elements đều có semantics bất biến thích hợp.

Nhưng nếu component là `List<MutableRule>`, `List.copyOf` **chỉ copy cấu trúc ngoài**; một `MutableRule` bên trong vẫn có thể bị thay đổi. Vì vậy phải xem **toàn bộ object graph**, không chỉ keyword `record` hoặc `final`.

### Dữ liệu bất biến là lời hứa thiết kế

Một getter trả mảng `byte[]` nội bộ có thể cho caller sửa trực tiếp nội dung. Nếu cấu hình chứa array hay map lồng nhau, cần dùng defensive copies ở cả **đầu vào** và **đầu ra** khi cần thiết; với nested elements mutable, copy sâu hoặc chuyển thành immutable types phù hợp.

## 4. Tại sao phải tách config khỏi per-call state?

Một cấu hình có thể được dùng bởi nhiều caller và tồn tại hàng giờ, trong khi state của một invocation thường sống vài microseconds đến seconds.

```text
Shared configuration lifetime:
|-------------------v1-------------------|-----v2------|

Invocation A:
           |------- state A -------|

Invocation B:
                |---state B---|

Invocation C:
                                          |---state C---|
```

Nếu trộn hai loại này:

- Reload cấu hình có thể ghi đè dữ liệu một invocation đang chạy.
- Invocation B có thể ghi đè `startNanos` hoặc `currentId` của A.
- Một request object được giữ trong field shared có thể sống lâu hơn request, gây retention và rò dữ liệu.
- Khó phân biệt “version policy của lượt gọi A” với “policy hiện hành khi A kết thúc”.
- Một aspect shared trở thành tập hợp mutable field đòi synchronized phức tạp.
- Test không xác định được lỗi do visibility/race, do policy update hay do join point không được can thiệp.

Tách scope giúp **cấu hình chia sẻ an toàn** và **dữ liệu của từng invocation cô lập** mà không nhất thiết phải tạo aspect object mới cho mỗi call.

## 5. Sai lầm cổ điển: field `currentRequestId` trên aspect dùng chung

```java
// KHÔNG an toàn nếu một instance được nhiều invocation dùng.
final class UnsafeAdvice {
    String currentRequestId;

    void before(String id) {
        currentRequestId = id;
    }

    void after() {
        System.out.println(currentRequestId);
    }
}
```

Hai thread có thể xen kẽ:

```text
Thread A: before("A") -> currentRequestId = "A"
Thread B: before("B") -> currentRequestId = "B"
Thread A: after()     -> đọc "B" (sai)
```

Ngay cả **một thread duy nhất**, lời gọi lồng nhau cũng có thể gây lỗi:

```text
before(outer) -> currentRequestId = "outer"
   target.outer()
      before(inner) -> currentRequestId = "inner"
      after(inner)
after(outer) -> vẫn đọc "inner" (sai)
```

Đây là **reentrancy**, không chỉ là multi-thread race.

Thêm `volatile` hay `AtomicReference<String>` chỉ làm một số thao tác đọc/ghi có semantics đồng bộ phù hợp; nó **không biến một slot dùng chung thành nhiều slot theo invocation**. Tương tự, chỉ synchronized các setter/getter không tạo ra correlation identity.

**Giải pháp cốt lõi là thay đổi nơi lưu state**, không chỉ thêm khóa.

## 6. Dùng local variables cho around advice

Một around advice thường có thể bao trọn invocation và gọi `proceed`:

```java
// Pseudocode của around advice; proceed() phụ thuộc API AOP cụ thể.
Object around(Operation joinPoint, PolicyStore policies)
        throws Throwable {
    Policy policy = policies.snapshot(); // Chọn một phiên bản ở đầu lời gọi.
    String invocationId = joinPoint.id(); // Local của riêng lời gọi.
    long startedAt = System.nanoTime();   // Local của riêng lời gọi.

    try {
        validate(joinPoint, policy);
        return joinPoint.proceed();
    } finally {
        record(invocationId, policy.version(),
                System.nanoTime() - startedAt);
    }
}
```

`Operation` và `PolicyStore` trong đoạn pseudocode thể hiện ý tưởng, không phải các API chuẩn AOP của Java SE. Điểm cần học là:

- `policy` được **lấy một lần** từ provider ở entry.
- `invocationId` và `startedAt` là local variables của stack frame hiện tại.
- Invocation lồng nhau tạo **stack frame khác** nên không ghi đè local của outer.
- `finally` chạy trên đường return và throw theo Java semantics.
- Snapshot được dùng trong cả validation và ghi nhận outcome của **cùng invocation**.

Một aspect singleton hoàn toàn có thể là **stateless về dữ liệu mỗi lời gọi** mặc dù method advice sử dụng nhiều local variables.

### `System.nanoTime` là mốc duration

`System.nanoTime()` phù hợp đo **elapsed time** trong cùng JVM, không phải timestamp lịch/UNIX. Nếu ghi elapsed ở `finally`, phải đảm bảo hiểu duration đo phạm vi around (có thể bao gồm advice khác, retry hoặc thời gian chờ) chứ không nhất thiết riêng business method body.

## 7. Cấu hình bất biến vẫn cần công bố an toàn

Giả sử chương trình muốn đổi policy từ `v1` sang `v2` khi đang có nhiều thread gọi advice. Có hai yêu cầu:

1. **Snapshot mới phải được tạo hoàn chỉnh, hợp lệ trước khi công bố.**
2. **Caller phải lấy snapshot có semantics visibility/atomicity phù hợp.**

Một pattern thường gặp trong Java:

```java
final class PolicyStore {
    private final java.util.concurrent.atomic.AtomicReference<Policy>
            active;

    PolicyStore(Policy initial) {
        active = new java.util.concurrent.atomic.AtomicReference<>(
                java.util.Objects.requireNonNull(initial));
    }

    Policy snapshot() {
        return active.get();
    }

    void reload(Policy next) {
        active.set(java.util.Objects.requireNonNull(next));
    }
}
```

`AtomicReference.set` có semantics volatile write; `get` có semantics volatile read. Kết hợp với **snapshot immutable, constructed đúng**, một invocation sẽ nhận một reference tới object đã được công bố an toàn. Thay `active` bằng `volatile Policy active` và gán atomic một reference cũng có thể đáp ứng bài toán **đổi cả snapshot** nếu không cần compare-and-set.

**Tính atomic của reference không làm nội dung object mutable tự an toàn.** Nếu code giữ cùng `Policy` rồi sửa `HashMap` bên trong từ thread khác, vấn đề race/inconsistency vẫn còn.

### Safe publication khác atomic update của từng field

Nếu dùng các field cấu hình riêng:

```java
// Ví dụ CÓ THỂ TẠO TRẠNG THÁI LỆCH khi reload từng field.
volatile int maxLength;
volatile String policyVersion;
volatile java.util.Set<String> forbiddenPrefixes;
```

Updater lần lượt thay ba field; caller có thể thấy `maxLength` mới nhưng `policyVersion` cũ. Volatile cho từng field **không tạo giao dịch atomic giữa nhiều field**.

Một snapshot immutable gom các field liên quan cho phép **thay thế một reference duy nhất**, giúp các giá trị đi cùng một version.

## 8. Snapshot một lần cho mỗi invocation: quy tắc quan trọng nhất

Một anti-pattern:

```java
// Mã minh họa sai về tính nhất quán xuyên thời điểm.
if (store.snapshot().maxLength() >= text.length()) {
    log("allow@" + store.snapshot().version());
}
```

Nếu config reload **giữa hai lần `snapshot()`**, quyết định được đưa ra theo `v1` nhưng log lại gắn nhãn `v2`. Đó là lỗi **mixed-version decision**.

Giải pháp:

```java
Policy policy = store.snapshot();

if (text.length() <= policy.maxLength()) {
    log("allow@" + policy.version());
}
```

Lưu `policy` vào local **một lần** rồi dùng xuyên suốt lần gọi. Nếu provider chỉ publish immutable snapshots, invocation giữ được consistency nội bộ ngay cả khi một thread khác đã reload.

### Hệ quả thời gian

- Invocation A bắt đầu dưới `v1`, chọn snapshot v1.
- Configuration được reload sang `v2` khi A còn đang chạy.
- Invocation B bắt đầu sau reload, có thể chọn v2.
- A hoàn tất dựa trên v1; B dùng v2.
- Log/metric nên ghi **policy version thực sự đã được A/B sử dụng**, không luôn lấy current version ở thời điểm kết thúc.

**Đây là snapshot consistency theo lời gọi**, không phải yêu cầu mọi invocation cùng thấy một phiên bản.

## 9. Ví dụ Java 17+ thực thi được: immutable snapshot và state theo lời gọi

Ví dụ tiếp theo dùng **Java Dynamic Proxy** để mô phỏng một aspect shared. Mục tiêu là **nhìn thấy trực tiếp**:

1. `Policy` chứa cấu hình bất biến có defensive copy.
2. `PolicyStore` dùng `AtomicReference` để publish nguyên snapshot.
3. Handler dùng một `Policy` local và một `String text` local **cho từng lần `invoke`**.
4. Target cố ý reload `v1 → v2` giữa một outer invocation.
5. Target gọi qua proxy một lần nữa để tạo nested invocation mới.
6. **Outer advice tiếp tục dùng v1**, inner advice nhận v2.
7. Policy v2 chặn dữ liệu không hợp lệ mà không làm nhiễm state của invocation khác.

Đây là demo **kiểm chứng ngữ nghĩa**, không phải cú pháp pointcut của một engine AOP nhất định. Lời gọi qua wrapper proxy là điều kiện để handler chạy; các đường gọi raw khác không tự được intercept.

### 9.1. Tệp `AspectConfigStateDemo.java`

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public class AspectConfigStateDemo {
    interface Service {
        String execute(String text);
    }

    record Policy(String version, int maxLength,
                  Set<String> forbiddenPrefixes) {
        Policy {
            Objects.requireNonNull(version);
            Objects.requireNonNull(forbiddenPrefixes);
            if (maxLength < 1) {
                throw new IllegalArgumentException("maxLength");
            }
            forbiddenPrefixes = Set.copyOf(forbiddenPrefixes);
        }
    }

    static final class PolicyStore {
        private final AtomicReference<Policy> active;

        PolicyStore(Policy initial) {
            active = new AtomicReference<>(initial);
        }

        Policy snapshot() {
            return active.get();
        }

        void reload(Policy next) {
            active.set(Objects.requireNonNull(next));
        }
    }

    static final class Target implements Service {
        private final PolicyStore store;
        private Service self;

        Target(PolicyStore store) {
            this.store = store;
        }

        void bind(Service proxy) {
            self = proxy;
        }

        @Override
        public String execute(String text) {
            System.out.println("target " + text);

            if ("outer".equals(text)) {
                store.reload(new Policy("v2", 3, Set.of("X")));
                System.out.println("config.reload v2");
                return "O:" + self.execute("in");
            }

            return "ok:" + text;
        }
    }

    static final class Advice implements InvocationHandler {
        private final Service target;
        private final PolicyStore store;

        Advice(Service target, PolicyStore store) {
            this.target = target;
            this.store = store;
        }

        @Override
        public Object invoke(Object proxy, Method method,
                             Object[] args) throws Throwable {
            Policy policy = store.snapshot(); // Một snapshot/call.
            String text = (String) args[0];   // State local/call.

            System.out.println("advice.before " + text
                    + "@" + policy.version());
            try {
                boolean forbidden =
                        policy.forbiddenPrefixes().stream()
                                .anyMatch(text::startsWith);

                if (text.length() > policy.maxLength() || forbidden) {
                    throw new IllegalArgumentException(
                            "blocked " + text);
                }

                Object result;
                try {
                    result = method.invoke(target, args);
                } catch (InvocationTargetException wrapped) {
                    throw wrapped.getCause();
                }

                System.out.println("advice.after " + text
                        + "@" + policy.version());
                return result;
            } finally {
                System.out.println("advice.finally " + text
                        + "@" + policy.version());
            }
        }
    }

    static Service proxy(Service target, PolicyStore store) {
        return (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[]{Service.class},
                new Advice(target, store));
    }

    public static void main(String[] args) {
        Set<String> original = new HashSet<>(Set.of("X"));
        PolicyStore store = new PolicyStore(
                new Policy("v1", 8, original));

        original.add("B");
        System.out.println("config.copied "
                + !store.snapshot()
                        .forbiddenPrefixes().contains("B"));

        Target target = new Target(store);
        Service intercepted = proxy(target, store);
        target.bind(intercepted);

        System.out.println("caller "
                + intercepted.execute("outer"));
        System.out.println("caller "
                + intercepted.execute("OK"));

        for (String value : new String[]{"abcd", "X"}) {
            try {
                intercepted.execute(value);
            } catch (IllegalArgumentException error) {
                System.out.println("caller.error "
                        + error.getMessage());
            }
        }
    }
}
```

### 9.2. Biên dịch và chạy

Yêu cầu **JDK 17 trở lên**. Đặt tệp `AspectConfigStateDemo.java` trong thư mục hiện hành:

```bash
javac --release 17 -encoding UTF-8 AspectConfigStateDemo.java
java AspectConfigStateDemo
```

**Standard output đã được đối chiếu khi biên dịch và chạy thực tế:**

```text
config.copied true
advice.before outer@v1
target outer
config.reload v2
advice.before in@v2
target in
advice.after in@v2
advice.finally in@v2
advice.after outer@v1
advice.finally outer@v1
caller O:ok:in
advice.before OK@v2
target OK
advice.after OK@v2
advice.finally OK@v2
caller ok:OK
advice.before abcd@v2
advice.finally abcd@v2
caller.error blocked abcd
advice.before X@v2
advice.finally X@v2
caller.error blocked X
```

Ví dụ sử dụng một thread để **thứ tự output xác định**; nó minh họa nested/reentrant invocation và thay snapshot trong khi outer chưa kết thúc. Mô hình tương tự cũng hỗ trợ concurrent invocations nếu các thành phần chia sẻ tuân thủ concurrency contract, nhưng demo không hứa thứ tự stdout khi chạy nhiều thread.

### 9.3. Giải thích `config.copied true`

`original` là một `HashSet` có thể sửa. Constructor `Policy` dùng `Set.copyOf` để lấy một cấu trúc không cho sửa. Khi code gọi `original.add("B")`, policy v1 **không** thấy prefix B. Đây là ví dụ về **defensive copy lúc tạo snapshot**.

Nó không có nghĩa mọi `Set.copyOf` thực hiện deep copy các elements. Ở đây element là `String` nên không có mutable fields bị lộ qua element.

### 9.4. Tại sao outer có `v1` nhưng inner có `v2`?

Outer gọi `intercepted.execute("outer")`:

1. Handler lấy một `Policy` snapshot **v1** vào local `policy`.
2. Handler xác minh `outer` (5 ký tự) trong ngưỡng v1 = 8.
3. Target in `target outer`.
4. Target gọi `store.reload(new Policy("v2", 3, ...))`.
5. Target dùng `self.execute("in")`; `self` được bind tới **proxy**.
6. Nested handler invocation lấy snapshot **v2** mới, kiểm `"in"` và hoàn tất.
7. Quay về outer handler, local `policy` vẫn trỏ v1; phần after/finally in `@v1`.

Kết quả:

```text
advice.before outer@v1
...
advice.before in@v2
...
advice.after outer@v1
advice.finally outer@v1
```

**Không có data race trong ví dụ**, nhưng vẫn tồn tại tình huống đổi phiên bản trong khi một call đang chạy. Chính local snapshot đã giữ vững nhất quán theo invocation. Nếu handler liên tục gọi `store.snapshot()` ở before/after, log outer rất dễ gắn nhãn v2 dù quyết định allow ban đầu dựa trên v1.

### 9.5. Dùng snapshot v2 với các lời gọi sau

Sau khi outer kết thúc, `PolicyStore` giữ v2:

- `"OK"` có 2 ký tự, không bắt đầu bằng prefix `X` nên được chấp nhận.
- `"abcd"` có 4 ký tự, vượt maxLength 3 nên bị chặn.
- `"X"` bị chặn bởi `forbiddenPrefixes` dù độ dài hợp lệ.

Mỗi invocation có local `text` và `policy` riêng. Handler ghi `finally` đúng version ngay cả khi ném `IllegalArgumentException`.

### 9.6. Demo này có thực sự dùng immutable config?

Có, trong phạm vi dữ liệu đã biểu diễn:

- `Policy` là record có version, int và unmodifiable `Set<String>`.
- `Policy` không cung cấp setter.
- Caller sửa `original` không đổi nội dung policy.
- Reload tạo **Policy object mới**, thay vì sửa set/fields của object cũ.
- `AtomicReference` công bố reference mới.
- Handler đọc reference **một lần mỗi invocation**.

Nếu policy trong thực tế chứa mutable rule object, map lồng nhau hoặc byte arrays, phải củng cố defensive copy tương ứng. **Không suy rộng rằng mọi record đều deep immutable.**

### 9.7. Vì sao target phải bind lại proxy?

Để cố ý tạo **nested intercepted call**, ví dụ gán `self` trỏ tới proxy và target gọi `self.execute("in")`. Nếu target gọi `this.execute("in")` với wrapper proxy đứng ngoài, lời gọi nội bộ có thể bỏ qua handler. Đây là vấn đề **interception coverage**, khác với việc cấu hình có immutable hay không.

Không nên dùng self-proxy trong business code chỉ để giải quyết mọi trường hợp; đây là dụng cụ minh họa reentrancy. Một cơ chế bytecode weaving execution có thể quan sát các đường gọi khác nếu join point được dệt.

### 9.8. Giới hạn cần hiểu

Ví dụ chưa triển khai đầy đủ pointcut DSL, around advice tiêu chuẩn, cấu hình từ file, async completion hay distributed reload. Nó dùng một `PolicyStore` duy nhất và policy được thay **giữa lúc target đang chạy** chỉ để kiểm chứng snapshot consistency. Trong ứng dụng thực, reload thường do component cấu hình bên ngoài điều khiển.

Lỗi `IllegalArgumentException` do handler ném chỉ chứng minh policy ở ranh giới proxy. Một caller có reference target gốc có thể gọi thẳng mà không qua kiểm tra này; **proxy không tự tạo security boundary không thể bypass**.

## 10. Dùng immutable snapshot không có nghĩa mọi caller thấy bản mới ngay tức khắc

Sau khi `active.set(v2)` hoàn tất, các invocation **đọc snapshot về sau** qua cơ chế phù hợp có thể thấy v2. Nhưng invocation **đã lấy v1 trước đó** vẫn có thể tiếp tục dùng v1.

Đây là **snapshot-at-entry semantics**. Nó rất hữu ích cho logging, metric policy và nhiều loại validation, vì một method không đổi tiêu chí giữa chừng. Tuy nhiên, không phải chính sách nào cũng được phép chấp nhận “dùng cấu hình cũ đến hết lời gọi”.

### Trường hợp yêu cầu policy luôn mới nhất

Ví dụ:

- Token vừa bị thu hồi.
- Một permission thay đổi giữa lúc xử lý tác vụ dài.
- Một circuit breaker cần phản ứng tức thời với trạng thái runtime.
- Một global shutdown flag.

Nếu yêu cầu bắt buộc là **kiểm tra quyền ngay tại thời điểm hành động nhạy cảm**, một snapshot lấy quá sớm có thể không đủ. Có thể cần revalidation tại đúng boundary, deadline/cancellation hoặc cơ chế khác được thiết kế riêng.

**Snapshot consistency và policy freshness là hai thuộc tính khác nhau.** Đừng chọn “mỗi invocation luôn dùng snapshot ban đầu” cho chính sách bảo mật nếu business/security contract yêu cầu quyết định khác.

### Phân biệt config với live state

Một `Policy` immutable có thể nói `allowedRoles` hoặc `limit`. Nhưng **số request đang hoạt động, trạng thái circuit breaker, token revocation list động** có thể là live state cần cơ chế concurrency và consistency khác, không nhất thiết nên đóng cứng chung một snapshot vĩnh viễn.

## 11. Cấu hình theo phiên bản và quan sát có thể kiểm chứng

Khi có reload, một trường `version` hoặc `revision` là dữ liệu hữu ích:

```text
policy.version = "2026-10-19T08:00Z#42"
invocation A -> selectedVersion = #42
reload
invocation B -> selectedVersion = #43
```

Version giúp trả lời:

- Invocation A bị từ chối bởi rule phiên bản nào?
- Log before/after có cùng policy không?
- Lỗi có xuất hiện sau một lần reload cụ thể?
- Rollback có tác động tới những invocation bắt đầu sau đó không?
- Cache metadata/predicate có được invalidated theo policy version không?

**Version phải đi cùng chính snapshot được dùng để đưa ra quyết định**, không lấy lại “current version” chỉ lúc ghi log.

### Không dùng version để che nội dung config thiếu chính xác

Hai snapshot có cùng version nhưng khác nội dung là lỗi quản lý configuration identity. Có thể dùng monotonic revision hoặc fingerprint phù hợp. Nếu một component đọc nhiều nguồn config, phải xác định lúc nào các nguồn tạo thành **một phiên bản policy hợp lệ** và chỉ publish sau khi validate đầy đủ.

## 12. Reload: xây dựng mới, xác thực rồi swap

Một chuỗi reload phù hợp:

```text
Source config (file/env/remote/CLI)
            |
         Parse
            |
      Validate rules
            |
    Build immutable Policy
            |
   Publish atomic reference
            |
   Subsequent invocations read new snapshot
```

**Không cập nhật dần snapshot đang được dùng**:

```java
// Thiết kế không phù hợp khi mutable state được nhiều caller đọc.
policy.allowedSet.clear();
policy.allowedSet.addAll(newAllowed);
policy.maxAttempts = newLimit;
```

Trong khoảng giữa các thao tác, advice có thể thấy một policy thiếu rules hoặc gồm nửa cũ/nửa mới.

### Publish thất bại thì sao?

Nếu parse/validate config mới thất bại, thường nên **giữ lại snapshot hợp lệ hiện tại**, ghi diagnostic an toàn, rồi báo trạng thái reload thất bại. Không tự publish một snapshot nửa chừng hoặc null nếu runtime không chấp nhận.

Đối với hệ thống yêu cầu fail-closed, chính sách khi reload lỗi có thể nghiêm ngặt hơn. Quan trọng là decision ấy được xác định trước, không vô tình do `NullPointerException` hoặc shared map bị xóa.

## 13. Nhiều updater cần quy tắc tranh chấp

`AtomicReference.set` thay thế cả snapshot an toàn, nhưng khi có **hai thread reload đồng thời**:

```text
Updater A: đọc revision 10, xây v11A
Updater B: đọc revision 10, xây v11B
Updater B: set(v11B)
Updater A: set(v11A)
```

A có thể ghi đè B dù quyết định của B mới hơn theo một tiêu chí bên ngoài. Đây là vấn đề **ordering/version policy**, không phải atomicity của một reference.

Nếu yêu cầu **optimistic concurrency**, có thể cần `compareAndSet`, expected revision, monotonic version hoặc một writer/queue duy nhất. Nhưng **CAS loop** cũng phải xét việc build lại snapshot, validate điều kiện mới và cách xử lý thất bại. Đừng dùng `set` rồi tuyên bố hệ thống có tính nhất quán giao dịch ở mức nhiều tác giả.

## 14. Trạng thái của before/after tách rời: một vấn đề khác

Nếu một AOP engine tách **before advice** và **after advice** thành hai method khác nhau:

```text
before -> nhận snapshot và mốc thời gian
target -> chạy
after  -> cần dùng đúng snapshot/mốc của before
```

Local variable của `before` không tự tồn tại trong stack frame của `after`.

Giải pháp tùy API:

- **Around advice** bao trọn target, dùng local variables.
- **Invocation context object** được engine cung cấp để liên hệ các phase.
- Một wrapper/interceptor pipeline tự tạo state rồi chuyển cho các phase.
- Một **stack state theo flow** chỉ khi before/after cùng thread, có LIFO semantics và cleanup đúng.
- Context correlation riêng nếu hoàn tất async xảy ra sau khi method đã return.

**Không dùng field `lastStartNanos` hoặc `lastPolicy` trên singleton aspect** để nối hai method advice; sẽ hỏng khi có concurrency/reentrancy.

### Correlation key

Hai lượt gọi cùng method, cùng target, cùng thread hoặc cùng request vẫn có thể là **hai invocation riêng**. Method name, target ID và thread ID không phải invocation ID duy nhất. Nếu một engine không hỗ trợ context per-invocation trực tiếp, cần một cơ chế correlation có ràng buộc rõ và có cleanup.

## 15. `ThreadLocal` không phải mặc định per-invocation

`ThreadLocal` lưu giá trị theo **thread**, không theo lời gọi:

```java
// Minh họa dữ liệu theo thread.
static final ThreadLocal<CallContext> CURRENT =
        new ThreadLocal<>();
```

Nếu outer advice đặt context A, inner advice cùng thread đặt context B, sau khi inner trả về outer có thể đọc nhầm B nếu không restore.

Trong thread pool, worker có thể phục vụ request R1 rồi R2; nếu quên `remove()` hoặc restore, R2 có nguy cơ thấy dữ liệu của R1.

### Pattern restore scope

```java
// Pseudocode trong method có work được truyền vào.
CallContext previous = CURRENT.get();
try {
    CURRENT.set(new CallContext(...));
    work.run();
} finally {
    if (previous == null) {
        CURRENT.remove();
    } else {
        CURRENT.set(previous);
    }
}
```

`CallContext` và `work` trong snippet là thành phần do ứng dụng định nghĩa, không phải chương trình chạy độc lập. Pattern này minh họa cách restore trên **cùng thread**; nó chưa tự xử lý context đi qua executor hoặc các nested flow phi-LIFO.

**Với một around advice đồng bộ, local variables thường đơn giản, dễ đúng hơn ThreadLocal.**

## 16. Bất đồng bộ: local state có thể cần được capture

Một method trả `CompletableFuture<T>` có thể return trước khi computation hoàn tất. Nếu around advice đo tới **method return**, nó không nhất thiết đo end-to-end latency đến khi future complete.

```text
method call
   |
   +-- return CompletableFuture<T> --- around synchronous exits
                    |
                    +-- worker computes
                    |
                    +-- Complete(value) / error / cancel
```

Nếu mục tiêu là quan sát completion, có thể tạo immutable per-operation context và capture nó trong callback:

```java
// Minh họa: original là CompletableFuture<String> đã có sẵn.
long startedAt = System.nanoTime();
Policy policy = store.snapshot();

java.util.concurrent.CompletableFuture<String> observed =
        original.whenComplete((value, error) -> {
            recordCompletion(
                    policy.version(),
                    System.nanoTime() - startedAt,
                    error);
        });
```

`recordCompletion` là hàm quan sát do ứng dụng định nghĩa. Lưu ý:

- `whenComplete` tạo một stage phụ, với semantics exception riêng.
- Nếu callback ném lỗi, stage trả về có thể bị ảnh hưởng theo API.
- Captured policy là snapshot per-operation, không tự chuyển mọi ThreadLocal context sang worker.
- Nếu callback sống lâu, closure có thể giữ reference tới dữ liệu/target hơn dự kiến.
- Cần xử lý cancellation/retry/timeouts và phân biệt *method-return* với *future-completion*.

### Context propagation và security

Trace ID của request có thể cần truyền qua worker; đó là **request context**, không đồng nghĩa state timer của một method. Dữ liệu được propagate có thể bị giả mạo nếu không có boundary xác thực. Có cùng context object không tự chứng minh tác vụ được cấp quyền.

## 17. Trạng thái mỗi invocation không có nghĩa phải tạo aspect mới

Một shared aspect có thể hoàn toàn stateless về per-call state:

```text
Shared Advice instance
  |
  +-- call 1 -> local Policy v1, local start 1
  +-- call 2 -> local Policy v2, local start 2
  +-- call 3 -> local Policy v2, local start 3
```

Việc Java tạo **stack frame riêng cho từng method invocation** giúp local variables tách biệt kể cả cùng một object advice.

Tạo aspect instance mới mỗi lần cũng có thể hoạt động, nhưng tăng chi phí khởi tạo và không giải quyết shared dependency/static mutable state bên ngoài.

**Trục lifecycle aspect khác trục lifecycle invocation state.**

### Per-target aspect cũng có thể bị race

Nếu hai thread cùng gọi target X, một aspect per-target gắn với X vẫn có thể phục vụ cả hai. Vì thế field `currentOperation` trên per-target aspect cũng sai nếu state cần per-call. Cô lập **theo target** không tự cô lập **theo invocation**.

## 18. Immutable policy khác state máy trạng thái dùng chung

Có những concern AOP cần state dùng chung **thực sự biến đổi theo thời gian**, ví dụ:

- Circuit breaker lưu open/half-open/closed.
- Rate limiter giữ quota/token counters.
- Bulkhead theo dõi số request đang chạy.
- Audit sink có queue/hạn mức.
- Global metric counters.
- Cache chứa entry được thêm/xóa.

Các thành phần này không phải “config immutable”; chúng cần **concurrency contract** riêng: atomic fields, locks, concurrent data structures hoặc state machine có giới hạn.

Một cấu trúc tốt có thể là:

```text
Immutable Policy snapshot:
   maxConcurrent = 20
   timeoutMillis = 500

Shared mutable runtime limiter:
   activeCalls = 7
   atomic acquire/release

Per-invocation:
   permitAcquired = true
   startedAtNanos = ...
```

**Không để đồng nhất “mọi thứ shared đều immutable”** làm mất chức năng của shared runtime counters. Thay vào đó tách ba loại có mục đích rõ.

## 19. Concurrency: `volatile`, `AtomicReference` và khóa dùng cho việc gì?

| Công cụ Java | Hữu ích cho | Không tự giải quyết |
| --- | --- | --- |
| `final` + object immutable | Xây dựng snapshot không đổi | Deep immutability nếu giữ mutable references |
| `volatile Policy` | Công bố/đọc reference snapshot | Atomic multi-object transaction, mutable policy internals |
| `AtomicReference<Policy>` | Atomic get/set/CAS của reference | Đúng ordering giữa nhiều updater nếu không có policy revision |
| `AtomicLong`, `LongAdder` | Bộ đếm dùng chung | Correlation của nhiều field per-invocation |
| `synchronized` | Bảo vệ invariant trong vùng khóa | Chọn đúng scope cho một invocation |
| `ConcurrentHashMap` | Concurrent map operations | Tính đúng của key, lifecycle và multi-step invariant |
| Local variables | State tách theo stack frame | Kéo dài ngữ cảnh qua async không có carrier |

Một solution đúng thường kết hợp **immutable config + AtomicReference for publication + local state + shared counter chuyên dụng**. Không ép mọi vấn đề vào một primitive duy nhất.

### Không nhầm visibility với semantic consistency

Một `volatile currentId` luôn có thể được đọc dưới memory visibility phù hợp, nhưng vẫn **có thể là ID của request khác**. Đọc được giá trị mới nhất không đồng nghĩa đọc được giá trị đúng của invocation mình.

## 20. Config metadata cache và invocation cache khác nhau

Một shared aspect có thể cache những thứ tương đối ổn định:

- `Method` metadata.
- Resolved annotation policy.
- Precompiled expression hoặc regex.
- Join point signature.
- Type hierarchy resolution.
- Config snapshot revision.

Nhưng `startNanos`, input cụ thể hoặc kết quả hiện tại **không phải metadata cache chung**.

### Cache key khi có reload

Giả sử một method được cho phép ở policy v1 nhưng bị từ chối ở v2. Nếu cache decision chỉ theo `methodName`, kết quả cũ có thể được dùng lại sau reload.

Một key hợp lý có thể gồm:

```text
(method identity, policyRevision, targetType, relevant static metadata)
```

Nếu quyết định còn phụ thuộc runtime args, tenant hoặc caller identity, không được bỏ những yếu tố ấy khỏi semantics. Không phải lúc nào cũng nên cache kết quả dynamic predicate.

### Class loader và module scope

Trong ứng dụng modular/plugin, cùng tên class có thể được định nghĩa bởi class loaders khác nhau, tạo type identity khác nhau. Cache theo chuỗi class name đơn thuần có thể trộn metadata từ các loader khác. Chọn key phù hợp và có eviction/invalidation khi loader/plugin reload.

## 21. Tránh rò dữ liệu qua cấu hình

Một policy object đôi khi chứa:

- Secret/token.
- Địa chỉ endpoint.
- Danh sách quyền.
- Identifier tenant.
- Chính sách mask log.
- Retry/backoff settings.

Immutable không đồng nghĩa **được phép log công khai**. Nếu in `policy.toString()` trực tiếp, record có thể để lộ dữ liệu nhạy cảm qua generated `toString`.

Nên chỉ log những trường cần thiết như **revision**, một vài nhãn an toàn, kết quả policy không nhạy cảm. Không đưa raw secrets vào shared aspect fields hoặc invocation context nếu không cần. Với key material, lifecycle zeroization có vấn đề riêng mà immutable Java String/record không tự giải quyết.

## 22. Cấu hình cho nhiều tenant hoặc nhiều request

Một snapshot **toàn cục duy nhất** có thể không đúng nếu tenant A và B dùng chính sách khác nhau. Có thể xây:

```text
Immutable registry snapshot:
    tenant A -> PolicyA@revision 3
    tenant B -> PolicyB@revision 7

Invocation A:
    tenantId verified -> select PolicyA@3

Invocation B:
    tenantId verified -> select PolicyB@7
```

Tuy nhiên việc lấy `tenantId` phải dựa vào context đã được xác thực; không cho phép người gọi tự chọn policy “dễ hơn” bằng cách gửi một key tùy ý.

Nếu policy per-tenant được reload độc lập, cần định nghĩa semantics revision theo tenant và phạm vi atomic update: thay từng policy hay thay cả registry snapshot. Tránh map mutable bị thay từng entry mà caller thấy trạng thái trung gian ngoài hợp đồng.

### Policy hierarchy

Khi config kết hợp default, environment, tenant override và request override, nên:

1. Xác định precedence.
2. Validate toàn bộ kết quả.
3. Tạo **effective immutable policy**.
4. Dùng effective policy snapshot cho invocation.
5. Giữ metadata về nguồn/revision nếu cần debug.

Không viết advice theo kiểu đọc mỗi key từ nhiều nguồn mutable khác nhau **giữa lúc xử lý** rồi giả định tất cả cùng một cấu hình nhất quán.

## 23. Version snapshot trong log, metric và error policy

Một invocation thất bại nên có thể trả lời:

- Nó đã chọn phiên bản policy nào?
- Nếu retry, mỗi attempt dùng cùng policy hay refresh?
- Nếu reject vì rule, rule/code nào quyết định?
- Nếu reload giữa lúc chạy, đã sử dụng cấu hình cũ hay mới?
- Lỗi được chuyển đổi theo exception mapping policy version nào?
- Metric bucket và log line có tương quan cùng invocation ID không?

**Nên ghi config version đã chọn trong per-invocation context.** Đừng gọi `store.snapshot().version()` ở đoạn after/finally chỉ để tạo nhãn bởi có thể lúc ấy đã reload.

### Version và metric cardinality

Gắn revision duy nhất cho từng micro-update vào metric labels có thể làm cardinality tăng mạnh. Có thể dùng revision trong log/trace debug và nhãn metric tổng quát hơn tùy kiến trúc quan sát. Không chọn key high cardinality như full request ID cho mọi metric time-series.

## 24. Lỗi trong validation, reload và advice

Tách config và per-call state giúp xác định ranh giới lỗi:

**Reload error:** không parse/validate được policy mới → không publish snapshot nửa hoàn chỉnh, xử lý theo policy.

**Invocation validation error:** snapshot đã hợp lệ nhưng input không hợp lệ → advice có thể từ chối theo contract, không làm đổi global policy.

**Advice infrastructure error:** logger, reflection, interceptor helper gặp lỗi → không nhầm là policy deny/allow.

**Target error:** target ném exception → có thể preserve/map theo rule đã snapshot.

Nếu advice dùng `finally` để log duration/outcome, lỗi logger có thể thay outcome. Cần chính sách ưu tiên lỗi target và audit theo tính bắt buộc của concern.

### Không để một request sửa config toàn cục

Một request input không hợp lệ không nên có quyền gọi `store.reload(...)` chỉ vì advice có thể truy cập provider. Trong demo, target reload để phơi bày snapshot semantics; trong kiến trúc thực, **config ownership** nên thuộc thành phần quản trị riêng.

## 25. Sự khác biệt giữa proxy và bytecode weaving

Một Java Dynamic Proxy chỉ chạy interceptor khi caller gọi **proxy object** trên method được proxy công bố. Nếu caller gọi raw target trực tiếp, interceptor không chạy; cấu hình dù bất biến và state dù tách đúng cũng không làm proxy bao phủ mọi đường gọi.

```text
caller -> proxy -> advice(store.snapshot) -> target
caller -------------------------------> raw target  [bypass]
```

Một engine AOP dệt **execution join point** vào bytecode target có thể bao phủ các đường khác, nếu class/method thuộc weaving scope, pointcut khớp và engine hỗ trợ.

**Thiết kế state tốt không thay thế yêu cầu kiểm chứng interception coverage.**

### Call vs execution

- Một **call join point** tại caller có thể quan sát vị trí phát lời gọi.
- Một **execution join point** tại callee có thể quan sát lúc method body chạy.
- Trạng thái per-invocation phải gắn đúng loại sự kiện mà advice thực sự xử lý.
- Nếu quanh cùng một thao tác có nhiều advice call/execution, có thể có **nhiều invocation contexts**, không tự đồng nhất chúng thành một.

## 26. Aspect instance dùng chung không tự làm target thread-safe

Giả sử aspect đã tách local state chính xác, nhưng target có field:

```java
// Ví dụ business target không an toàn đa luồng.
class CounterService {
    private int count;

    int next() {
        return ++count;
    }
}
```

Hai thread vẫn có thể lost updates trong target. **Thread safety của aspect và thread safety của target là hai vấn đề riêng**.

Ngược lại, một target bất biến không làm advice an toàn nếu advice giữ một shared `currentId`. Phải kiểm tra cả hai bên của interception boundary.

## 27. Per-call state và quanh exception/retry

Với retry advice, bộ đếm `attempt` nên là local của **caller invocation đang retry**:

```java
// Pseudocode around; loại lỗi và API proceed do ứng dụng xác định.
int attempt = 0;
Policy policy = store.snapshot();
for (;;) {
    attempt++;
    try {
        return proceed();
    } catch (TransientFailure error) {
        if (attempt >= policy.maxAttempts()) {
            throw error;
        }
        backoff(attempt);
    }
}
```

Nếu `attempt` là một field singleton, invocation B có thể tăng nó khiến A dừng sai số lần retry. Nếu config được reload trong lúc A đang retry, policy “snapshot once” khiến A giữ một giới hạn nhất quán giữa các attempt. **Điều đó phải là contract có chủ đích**, không phải kết quả ngẫu nhiên.

Không retry mù quáng nếu target có side effect không idempotent, nếu thao tác bị hủy hoặc lỗi thuộc nhóm không thể phục hồi.

## 28. Trạng thái có thể là một object riêng, không nhất thiết nhiều biến local

Một invocation phức tạp có thể giữ:

```java
// Java 17 minh họa data holder bất biến.
record CallContext(
        String operationId,
        String configRevision,
        long startedAtNanos
) { }
```

Một context object tạo **mới cho từng lượt gọi** và giữ ở local/closure tương ứng vẫn là per-invocation. Nhưng nếu một aspect singleton tạo `new CallContext(...)` rồi lưu vào field `currentContext` dùng chung, lỗi state mixing quay trở lại.

**Tên class “InvocationContext” không tự tạo scope per-invocation.** Ownership, cách phân phối reference và lifetime mới quyết định.

### Mutable per-call object

Một mutable state object dùng riêng cho một invocation có thể hợp lệ (ví dụ chứa số attempt và accumulated errors) nếu nó không được chia sẻ sai. Khi truyền vào nhiều thread, phải xác định thread confinement hoặc synchronization. Bất biến vẫn hữu ích cho config, nhưng không bắt buộc mọi per-call working state đều bất biến.

## 29. Không ghép before và after bằng một shared field

Một cặp advice tách rời:

```text
before(call A) -> start_A
before(call B) -> start_B
after(call A)  -> cần start_A
after(call B)  -> cần start_B
```

Nếu dùng `Aspect.start`, B ghi đè A. Nếu dùng `ThreadLocal<Long>` đơn lẻ, nested calls trên cùng thread có thể ghi đè. Cần một trong các cơ chế:

- Around advice với local start.
- Join-point invocation context được engine hỗ trợ.
- Stack theo flow đúng LIFO và cleanup.
- Per-invocation map có key thực sự duy nhất, bộ nhớ có giới hạn và cleanup mọi đường.
- Explicit carrier/context qua async callback.

Không dùng method name, target identity hoặc thread ID đơn thuần để giả làm invocation key nếu recursion hoặc concurrent calls có thể xảy ra.

## 30. Kiểm thử deterministically, không chỉ hy vọng race xuất hiện

Ví dụ chạy nhiều thread ngẫu nhiên có thể không lộ lỗi field chung ngay. Có thể dùng `CountDownLatch` hoặc `CyclicBarrier` để ép interleaving:

```text
A: capture snapshot v1, pause before target
Reload: publish v2
B: capture snapshot v2, execute
A: resume, finish after/finally using v1
```

Test cần assert:

- A log policy version v1 ở before và after.
- B log v2.
- A không đọc per-call ID của B.
- Reload không mutate v1 đã được A giữ.
- Target return/exception đúng contract.
- Nếu validation rule thay giữa chừng, hành vi theo snapshot semantics đã định.

**Reentrancy test một thread** như trong demo đã đủ bắt một số lỗi, còn multi-thread tests giúp phát hiện data races và publication bugs.

## 31. Ma trận kiểm thử

| Trường hợp | Điều phải xác minh |
| --- | --- |
| Snapshot chứa immutable scalars | Không đổi sau khi khởi tạo |
| Caller sửa Set đã đưa vào constructor | Policy không thay vì đã defensive copy |
| Snapshot có nested mutable element | Được chuyển thành immutable hoặc copy đúng |
| Getter trả array/list | Không để lộ mutable internal state |
| Reload hợp lệ | Publish nguyên snapshot đúng một lần |
| Reload cấu hình lỗi | Snapshot cũ vẫn hợp lệ theo policy |
| Hai updater chạy đồng thời | Có quy tắc revision/order rõ |
| A lấy v1, reload, A hoàn tất | A vẫn dùng v1 nội bộ |
| B bắt đầu sau reload | B chọn v2 theo policy |
| Nested invocation trong cùng thread | Local state outer không bị inner ghi đè |
| Hai invocation concurrent | Mỗi call giữ đúng args/timer/config |
| Shared aspect singleton | Local state cô lập dù một aspect instance |
| Per-target aspect | Hai calls cùng target vẫn có state riêng |
| Before/after riêng | Context mapping đúng invocation, cleanup đủ |
| Thread pool reuse | Không giữ context request trước |
| Future hoàn tất muộn | Phân biệt method return và async completion |
| Retry và config reload | Số lần thử/phiên bản theo contract |
| Cấu hình đa tenant | Không lẫn policy khác tenant, key xác thực |
| Cache metadata sau reload | Key/invalidation tính tới revision |
| Logging/metric sink lỗi | Không vô tình che target error |
| Raw target bypass proxy | Nhận diện thiếu interception, không gán lỗi cho state |
| Class loader/plugin reload | Cache không trộn type identity, không leak loader |
| Permission revocation khẩn cấp | Freshness policy đáp ứng yêu cầu bảo mật |

### Đo những thứ độc lập

Một test tốt phân biệt:

1. **Aspect invocation count** (lần advice thực sự chạy).
2. **Target execution count** (lần business logic chạy).
3. **Config snapshot selected** (version/identity tại entry).
4. **Per-call state** (argument, ID, timestamp, attempt).
5. **Final caller outcome** (return/exception/async completion).

Nhìn duy nhất một dòng log có thể không biết lỗi do thiếu advice, sai policy hay log sink bị tắt.

## 32. Chẩn đoán khi dữ liệu cấu hình hoặc state bị sai

**Triệu chứng: cùng một lời gọi in v1 ở before, v2 ở after.**

- Có gọi `store.snapshot()` nhiều lần trong cùng invocation không?
- Có mutate object policy cũ không?
- `version` có thuộc cùng object snapshot với rules không?

**Triệu chứng: request A có trace ID của B.**

- Có field `currentRequestId` dùng chung không?
- Có nested advice/reentrancy không?
- Có `ThreadLocal` không restore/remove?
- Có callback giữ/copy sai context không?

**Triệu chứng: reload thỉnh thoảng gây giá trị policy lộn xộn.**

- Có update nhiều mutable fields từng cái?
- Có publish trước khi validate/build xong?
- Có nhiều updater làm overwrite stale revision?
- Có mutable nested list/map bị share từ bên ngoài?

**Triệu chứng: policy đúng nhưng một số method không được kiểm tra.**

- Lời gọi có đi qua proxy/weaving boundary?
- Pointcut có khớp method thực tế?
- Có self-invocation hoặc raw target bypass?
- Có module/class loader/plugin khác ngoài scope?

**Triệu chứng: memory tăng sau nhiều request.**

- Aspect singleton có field giữ request/argument/result không?
- Callback có capture object graph lớn?
- Cache có eviction/bounds?
- Registry per-target có giữ strong references?
- ThreadLocal có remove/restore sau task không?

Phân loại đúng **config consistency**, **invocation isolation**, **interception coverage** và **lifetime management** trước khi sửa.

## 33. Các anti-pattern cần tránh

1. **`final Map` là đủ bất biến.** Reference final nhưng nội dung map vẫn có thể sửa.
2. **Record bảo đảm deep immutable.** Record chỉ bảo đảm component fields final; elements có thể mutable.
3. **Cứ dùng `Collections.unmodifiableMap(source)` là đã copy.** Wrapper read-only có thể vẫn phản ánh mutation của source bên dưới.
4. **Cấu hình reload bằng `clear` rồi `addAll` vào set đang dùng.** Caller có thể quan sát trạng thái giữa chừng.
5. **Mỗi field config có volatile thì cả config atomic.** Không tạo transaction nhiều field.
6. **Lấy config mỗi lần cần để luôn mới.** Có thể tạo mixed-version trong một invocation.
7. **Lấy config một lần luôn an toàn cho mọi security decision.** Freshness/revocation policy có thể đòi revalidation.
8. **Lưu `currentId` trong aspect singleton.** Concurrency/reentrancy làm state bị ghi đè.
9. **Dùng `AtomicReference<CurrentCall>` cho mọi request.** Vẫn chỉ có một slot shared.
10. **`synchronized` getter/setter bảo đảm correlation.** Scope vẫn sai.
11. **Một ThreadLocal mặc định đại diện invocation.** Nested call/thread pool có thể lẫn state.
12. **Shared aspect không thể dùng local state.** Java method frame vẫn là per-call.
13. **Per-target aspect tự thread-safe.** Một target vẫn phục vụ nhiều threads.
14. **Per-call aspect tự cô lập static field.** Static thuộc class identity.
15. **Lấy policy revision ở after bằng current snapshot.** Có thể sai revision đã dùng khi decision.
16. **Metadata cache chỉ cần method name.** Overload/type/loader/revision có thể làm cache sai.
17. **Capturing cả request vào callback không tốn lifetime.** Có thể giữ dữ liệu lâu.
18. **Proxy tồn tại nghĩa là mọi direct/self call đều chạy advice.** Phải kiểm chứng đường interception.
19. **Cứ dùng immutable snapshot là hệ thống thread-safe.** Shared runtime state và target có thể còn race.
20. **Mỗi invocation phải tạo một policy object mới.** Immutable snapshot có thể share; chỉ per-call working state cần cô lập.
21. **Không cần policy version trong log.** Khó chẩn đoán khi reload giữa các calls.
22. **Dùng một bộ đếm request trong local, sau đó coi là metric tổng.** Local không tự aggregate.
23. **Reload lỗi vẫn publish policy nửa hợp lệ.** Caller có thể đưa ra quyết định sai.
24. **Set.copyOf luôn deep-copy object bên trong.** Chỉ là unmodifiable snapshot của cấu trúc set; mutable elements vẫn cần xử lý.
25. **Cấu hình bất biến mặc nhiên không chứa bí mật.** Generated `toString` hoặc log vẫn có thể lộ secret.
26. **Nếu config mới publish, mọi in-flight operation tức khắc chuyển sang v2.** Snapshot-at-entry cố ý giữ policy đã chọn.
27. **Hai reload đồng thời dùng set là có ordering đúng ý nghiệp vụ.** Atomic swap không giải quyết stale overwrite.
28. **Scope request bằng ThreadLocal tự truyền qua executor.** Thread khác có context riêng.
29. **Dùng chung một `InvocationContext` rồi ghi đè fields.** Tên context không tạo ownership.
30. **Bài test không ném exception là đủ.** Phải test error/finally/async/cancel/reload.

## 34. Checklist triển khai một aspect có cấu hình có thể reload

1. **Phân loại mọi field:** immutable config, shared runtime counter, target state, invocation state hay request context?
2. **Định nghĩa policy type:** field nào được yêu cầu, invariant nào cần validate?
3. **Loại bỏ mutable aliases:** copy input collection, nested mutable components và bảo vệ getter.
4. **Dùng snapshot immutable:** không mutate snapshot đang được chia sẻ.
5. **Công bố an toàn:** dùng `AtomicReference` hoặc `volatile` reference phù hợp.
6. **Xác định concurrency của reload:** một writer, CAS hay monotonic revision?
7. **Chọn snapshot một lần trong invocation** nếu yêu cầu policy consistency theo entry.
8. **Gắn policy version vào context/log** của invocation ấy.
9. **Giữ state per-call ở local/appropriate scope:** timer, arguments, retry attempts, Throwable.
10. **Nếu before/after tách:** có invocation correlation đúng hoặc dùng around.
11. **Nếu async:** chọn nghĩa của completion, carrier, cleanup, cancellation.
12. **Nếu có live security state:** nêu rõ freshness requirements, không dựa mù quáng vào snapshot cũ.
13. **Thiết kế advice ordering:** mapping/retry/authorization/log dùng snapshot thế nào?
14. **Kiểm chứng proxy/weaving coverage:** mọi đường bắt buộc có đi qua advice không?
15. **Test race/reentrancy/reload:** dùng latches, nested calls và deterministic asserts.
16. **Quan sát memory/caches:** eviction, loader lifetime, sensitive-data retention.

Đừng chọn `AtomicReference` hoặc `ThreadLocal` như một quy tắc áp dụng vô điều kiện. Chọn chúng sau khi đã xác định rõ **ai sở hữu state và cần nhìn thấy state tại thời điểm nào**.

## 35. Bài tập thực hành

1. Biên dịch và chạy `AspectConfigStateDemo.java`, đối chiếu từng dòng stdout.
2. Vì sao `config.copied true`? Nếu bỏ `Set.copyOf`, giá trị có thể thay thế nào?
3. Thêm `"B"` vào `forbiddenPrefixes` của config mới và dự đoán kết quả lời gọi `execute("B")`.
4. Đổi handler để gọi `store.snapshot().version()` ở `finally` thay cho `policy.version()`. Dự đoán dòng log của outer khi reload.
5. Thêm field `String currentText` trên `Advice`, dùng field này ở finally. Vì sao nested call tạo output sai?
6. Đổi `Target.self.execute("in")` thành `this.execute("in")`. Vì sao không còn nested proxy advice trong mô hình wrapper?
7. Dùng hai thread với `CountDownLatch`: A đọc v1 rồi chờ, updater set v2, A tiếp tục. Kiểm tra A vẫn dùng v1.
8. Tạo 1000 invocations concurrent qua một shared advice; ghi số lời gọi vào `LongAdder` và per-call ID trong local, không dùng shared `currentId`.
9. Thêm `int attempts` vào immutable policy, và retry attempt count local trong advice; reload giữa retry, mô tả policy áp dụng.
10. Thêm hai updater cùng tạo version từ một revision cũ, rồi đề xuất `compareAndSet` để tránh stale overwrite.
11. Tạo record chứa `List<MutableRule>`; chứng minh `List.copyOf` không ngăn sửa một `MutableRule` bên trong.
12. Tạo defensive-copy getter cho `byte[]` trong một policy; test sửa array trả về không đổi policy.
13. Tạo một policy đa tenant có mapping tenant → immutable policy; cách nào ngăn tenant A chọn policy B?
14. Tạo một before/after advice tách rời, dùng invocation scope/stack để giữ đúng start time khi có recursion.
15. Dùng một executor một thread phục vụ hai request nối tiếp; cho ThreadLocal tồn tại giữa hai task rồi sửa bằng restore/remove.
16. Tạo `CompletableFuture` hoàn tất sau return; so sánh timer tới method return và timer tới completion.
17. Tạo metric cache key theo method + revision; reload rule rồi đảm bảo cache không dùng result cũ.
18. Thiết kế chính sách token revocation: điều kiện nào đòi revalidation giữa một invocation dài thay vì snapshot-at-entry?
19. Thêm logging policy version vào error path của demo; đảm bảo validation error vẫn in version của invocation đã chọn.
20. Viết ma trận QA có ít nhất một case cho defensive copy, multi-field update, nested invocation, concurrent reload, async completion, direct target bypass và sensitive-data logging.

**Tự kiểm tra:** Vì sao `final` không đủ để tạo immutable object graph? Tại sao một `AtomicReference<Policy>` có thể publish snapshot nguyên vẹn nhưng không giải quyết mọi stale update? Nếu A bắt đầu ở v1 và reload sang v2 trong lúc A chạy, before/after của A nên in gì? Per-invocation local state giải quyết lỗi nào mà volatile field không giải quyết được? Per-target aspect có chắc tách state của hai lượt gọi cùng target không? Vì sao request context qua executor phải propagate riêng? Khi nào snapshot-at-entry không đủ cho policy bảo mật?

## Kết luận

**Tách cấu hình bất biến khỏi trạng thái mỗi lần gọi** giúp AOP vừa **chia sẻ policy an toàn** vừa **cô lập dữ liệu động của từng invocation**. Cấu hình cần được xây dựng đầy đủ, defensive-copy các thành phần mutable, validate rồi **publish nguyên snapshot**; mỗi advice invocation thường nên **đọc một snapshot tại entry** và gắn version vào local/context của mình. Mốc thời gian, input, attempt, kết quả và lỗi nên thuộc đúng invocation thay vì nằm trong shared mutable fields.

Trong những hệ thống có reload, nhiều thread, nested calls hoặc callback bất đồng bộ, cần phân biệt **snapshot consistency**, **config freshness**, **request/task context**, **state dùng chung thực sự** và **interception coverage**. Không có một primitive Java hay một scope aspect đơn lẻ giải quyết tất cả. Thiết kế đúng luôn bắt đầu từ câu hỏi: **dữ liệu này thuộc về ai, sống bao lâu, được cập nhật bởi ai, và người đọc phải thấy phiên bản nào?**