# Cache metadata theo Class và chữ ký để tránh tra cứu lặp trong đường chạy thường xuyên

> **Phạm vi:** Bài thuộc chương **Reflection và hiệu năng**, module `JAVA_VERSION_JAVA18`. Trong Java 18, JEP 416 tái triển khai core reflection dựa trên method handles nhưng vẫn duy trì API `Method`, `Field` và `Constructor`. Với JDK hiện đại, khi cùng một method/field/constructor được dùng nhiều lần, có thể lưu metadata đã tìm để tránh lặp lại `Class.getMethod(...)` hay `getDeclaredMethod(...)` trên đường chạy nóng. Bài tập trung vào thiết kế key chính xác theo `Class` và chữ ký, quản lý class loader, tính an toàn luồng, phân biệt chi phí lookup với chi phí invoke và cách kiểm chứng hiệu năng có cơ sở. Không sử dụng API nội bộ hoặc kỹ thuật đã legacy.

## 1. Metadata reflection là gì và tại sao không nên tra cứu trong mỗi lần gọi?

Reflection cho phép lấy thông tin về member của một lớp tại runtime:

~~~java
Class<?> type = service.getClass();
Method method = type.getMethod("process", String.class);
Object result = method.invoke(service, "payload");
~~~

Có hai thao tác khác nhau:

1. **Metadata lookup**: `type.getMethod("process", String.class)` tìm method theo tên và kiểu tham số, trả về đối tượng `Method`.
2. **Invocation**: `method.invoke(service, "payload")` thực thi method trên đối tượng, với kiểm tra receiver/arguments/access và cách xử lý exception theo hợp đồng.

Nếu đoạn code trên nằm trong vòng lặp xử lý sự kiện, lookup có thể bị làm đi làm lại dù lớp và chữ ký hoàn toàn không đổi:

~~~text
Sự kiện A -> getMethod("process", String) -> invoke
Sự kiện B -> getMethod("process", String) -> invoke
Sự kiện C -> getMethod("process", String) -> invoke
                   ^ lặp lại cùng phép tra cứu
~~~

Cache metadata thay đổi đường đi:

~~~text
Lần đầu  -> Class + Signature -> getMethod -> lưu Method -> invoke
Lần sau  -> Class + Signature -> đọc cache -----------> invoke
Lần sau  -> Class + Signature -> đọc cache -----------> invoke
~~~

**Mục tiêu của cache:** giảm việc *tìm kiếm và tạo/lấy metadata lặp lại*, không mặc định biến `Method.invoke` thành lời gọi Java trực tiếp. Chi phí access check, đóng hộp tham số, chuyển đổi giá trị, thực thi thân method và các tối ưu JIT vẫn là những yếu tố riêng.

## 2. Vì sao key chỉ có tên method là sai?

Java hỗ trợ method overload:

~~~java
public String convert(int value) {
    return Integer.toString(value);
}

public String convert(String value) {
    return value.trim();
}
~~~

Hai method cùng tên `convert` nhưng có chữ ký khác nhau. Nếu cache chỉ dùng chuỗi `"convert"`, một lookup có thể ghi đè method của overload khác. Kết quả có thể là `IllegalArgumentException` lúc `invoke`, hoặc gọi nhầm member.

Một key phù hợp với `Class.getMethod(String, Class<?>...)` có ba yếu tố:

- **Lớp dùng để lookup**: `Class<?>` thực tế, không chỉ tên lớp dạng chuỗi.
- **Tên method**: `String` như `convert`.
- **Danh sách kiểu tham số theo đúng thứ tự**: `List<Class<?>>`, chẳng hạn `[int.class]` hoặc `[String.class]`.

| Lookup | Key hợp lý |
|---|---|
| `Calculator.class.getMethod("add", int.class, int.class)` | (`Calculator.class`, `"add"`, `[int, int]`) |
| `Calculator.class.getMethod("convert", int.class)` | (`Calculator.class`, `"convert"`, `[int]`) |
| `Calculator.class.getMethod("convert", String.class)` | (`Calculator.class`, `"convert"`, `[String]`) |
| `OtherCalculator.class.getMethod("convert", int.class)` | (`OtherCalculator.class`, `"convert"`, `[int]`) |

**Không dùng `clazz.getName()` làm định danh duy nhất.** Hai class loader khác nhau có thể nạp hai `Class` riêng biệt nhưng cùng tên fully-qualified. `Class<?>` giữ đúng danh tính runtime của kiểu.

### Có cần return type trong key không?

Đối với API `getMethod(name, parameterTypes)`, caller truyền **tên và các kiểu tham số**, không truyền kiểu kết quả. Java bytecode có thể có các method trùng tên/parameter types nhưng khác return type (ví dụ bridge methods). Javadoc quy định cách `getMethod` chọn method phù hợp trong trường hợp này.

Vì vậy, một cache **chỉ phục vụ đúng `getMethod`** nên dùng cùng khóa với API: tên + danh sách parameter types (và lớp). Nếu hệ thống tự phân tích toàn bộ `getDeclaredMethods()` để chọn method theo return type/bridge/synthetic status, đó là một **quy tắc lookup khác** và cần key/cơ chế chọn khác. Không áp đặt kết luận “mỗi tên + tham số luôn chỉ có một method ở bytecode”.

## 3. Chọn đúng API reflection trước khi nghĩ đến cache

| API | Tìm gì? | Ý nghĩa đối với cache |
|---|---|---|
| `getMethod(name, parameterTypes)` | Public member method, kể cả thừa kế theo hợp đồng của `Class`. | Cache các lookup public, phù hợp ví dụ chính. |
| `getDeclaredMethod(name, parameterTypes)` | Member do chính `Class` khai báo, có thể không public; không tìm member thừa kế. | Cần quy tắc cache khác và kiểm soát access. |
| `getMethods()` | Mảng public methods, có cả thừa kế. | Nếu cần duyệt nhiều method, có thể lập chỉ mục một lần, nhưng đừng phụ thuộc thứ tự mảng. |
| `getDeclaredMethods()` | Mảng methods khai báo trong lớp, không bao gồm inherited methods. | Cần lọc và xử lý bridge/synthetic method khi phù hợp. |
| `getField/getDeclaredField` | Public/inherited field hoặc field khai báo trực tiếp. | Key thường là tên field + kiểu lookup + class. |
| `getConstructor/getDeclaredConstructor` | Public hoặc constructor được khai báo với ordered parameter types. | Key thường là lớp + ordered parameter types. |

Không nên dùng chung một cache giữa `getMethod` và `getDeclaredMethod` mà chỉ dùng tên/chữ ký làm key: cùng tên và tham số nhưng **quy tắc tìm kiếm khác nhau**.

Ví dụ:

~~~java
class Parent {
    public void ping() {
    }
}

class Child extends Parent {
}

Child.class.getMethod("ping");         // Tìm thấy method public thừa kế.
Child.class.getDeclaredMethod("ping"); // NoSuchMethodException.
~~~

Dù cache làm lookup nhanh hơn, nó không được phép thay đổi hợp đồng truy cập và tìm kiếm.

## 4. Hai chiến lược cache phổ biến

### 4.1. Trường static final khi type và chữ ký biết trước

Nếu ứng dụng chỉ gọi một method cố định, cách đơn giản nhất là lưu `Method` vào trường `static final`:

~~~java
private static final Method ADD_METHOD = findAddMethod();

private static Method findAddMethod() {
    try {
        return Calculator.class.getMethod("add", int.class, int.class);
    } catch (NoSuchMethodException e) {
        throw new ExceptionInInitializerError(e);
    }
}
~~~

Lúc sử dụng:

~~~java
int sum = (int) ADD_METHOD.invoke(calculator, 3, 4);
~~~

Đây là lựa chọn tốt khi số call site và chữ ký cố định. Nó tránh map lookup và tạo key trên hot path. Trong bối cảnh JEP 416, vị trí lưu metadata mà JIT nhận ra là hằng số (như `static final`) có thể thuận lợi cho tối ưu hóa. Tuy nhiên, **không có bảo đảm tốc độ cố định** giữa mọi workload/JDK, nên vẫn cần benchmark nếu hiệu năng là yêu cầu trọng yếu.

### 4.2. ClassValue + cache theo chữ ký khi type động

Nếu một framework xử lý nhiều `Class<?>` runtime (serializer, router, mapper, plugin dispatcher), cần cache nhiều chữ ký cho từng lớp.

Một `ConcurrentHashMap<Class<?>, Map<Signature, Method>>` toàn cục dễ sử dụng nhưng có thể **giữ tham chiếu mạnh** đến các `Class` và class loader của plugin ngay cả khi plugin đã ngừng hoạt động.

`ClassValue<T>` là API công khai cho phép **gắn giá trị lazily với từng `Class`**. Dùng `ClassValue<ConcurrentHashMap<Signature, Method>>` để nhóm cache theo lớp:

~~~text
ClassValue
   │
   ├── Class A
   │     ├── ("add", [int, int]) -> Method
   │     └── ("convert", [String]) -> Method
   │
   └── Class B
         └── ("add", [int, int]) -> Method
~~~

Thiết kế này tránh một map toàn cục trực tiếp dùng `Class<?>` làm key mạnh. Nó phù hợp hơn với hệ thống có class loader động, **nhưng không tự giải quyết mọi rò rỉ tài nguyên**: nếu code khác còn giữ `Class`, `Method`, object plugin hoặc key chứa `Class` từ loader khác, class loader vẫn có thể bị giữ sống.

## 5. Ví dụ Java 18+: cache public Method bằng ClassValue và record

Ví dụ hoàn chỉnh sau:

- Dùng `record Signature` làm key bất biến gồm tên + danh sách parameter types theo thứ tự.
- Dùng `ClassValue<ConcurrentMap<Signature, Method>>` để cô lập cache theo `Class`.
- Dùng `ConcurrentHashMap` cho các lookup đồng thời.
- Chỉ cache **lookup thành công**; không lưu `NoSuchMethodException`.
- Dùng `get` + `putIfAbsent` để xử lý phương thức checked `NoSuchMethodException` mà không ép nó thành unchecked trong `computeIfAbsent`.
- Đếm số lần thực hiện lookup thật nhằm **kiểm chứng cache về chức năng**, không dùng counter làm benchmark tốc độ.

Lưu toàn bộ vào `ReflectionCacheDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

public final class ReflectionCacheDemo {
    public static final class Calculator {
        public int add(int a, int b) {
            return a + b;
        }

        public String convert(int value) {
            return "number=" + value;
        }

        public String convert(String value) {
            return "text=" + value;
        }
    }

    // Record (Java 16+) có equals/hashCode theo tất cả components.
    private record Signature(String name, List<Class<?>> parameters) {
        private Signature {
            Objects.requireNonNull(name, "name");
            parameters = List.copyOf(parameters);
        }
    }

    // Cache theo Class thực tế; không dùng tên class làm key.
    private static final ClassValue<ConcurrentMap<Signature, Method>> CACHE =
            new ClassValue<>() {
                @Override
                protected ConcurrentMap<Signature, Method> computeValue(
                        Class<?> type) {
                    return new ConcurrentHashMap<>();
                }
            };

    private static final AtomicInteger REAL_LOOKUPS =
            new AtomicInteger();

    public static Method publicMethod(
            Class<?> owner, String name, Class<?>... parameterTypes)
            throws NoSuchMethodException {
        Objects.requireNonNull(owner, "owner");
        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(parameterTypes, "parameterTypes");

        // Sao chép varargs để caller không thể làm thay đổi key sau đó.
        Class<?>[] types = parameterTypes.clone();
        for (Class<?> type : types) {
            Objects.requireNonNull(type, "parameter type");
        }

        Signature signature = new Signature(name, List.of(types));
        ConcurrentMap<Signature, Method> methods = CACHE.get(owner);

        Method hit = methods.get(signature);
        if (hit != null) {
            return hit;
        }

        // Đường miss: vẫn giữ NoSuchMethodException là checked exception.
        REAL_LOOKUPS.incrementAndGet();
        Method found = owner.getMethod(name, types);

        // Nếu luồng khác đã thêm cùng key, dùng giá trị đã có.
        Method previous = methods.putIfAbsent(signature, found);
        return previous != null ? previous : found;
    }

    // API minh họa cách cache method với target có kiểu động.
    public static Object invokePublic(
            Object target, String name, Class<?>[] parameterTypes,
            Object... args)
            throws NoSuchMethodException,
                   IllegalAccessException,
                   InvocationTargetException {
        Objects.requireNonNull(target, "target");
        Method method = publicMethod(
                target.getClass(), name, parameterTypes);
        return method.invoke(target, args);
    }

    public static void invalidate(Class<?> owner) {
        Objects.requireNonNull(owner, "owner");
        CACHE.remove(owner);
    }

    public static void main(String[] args) throws Exception {
        Calculator calculator = new Calculator();

        // Hai lần tìm cùng class + chữ ký chỉ lookup thật lần đầu
        // trong thử nghiệm đơn luồng.
        Method first = publicMethod(
                Calculator.class, "add", int.class, int.class);
        Method again = publicMethod(
                Calculator.class, "add", int.class, int.class);

        if (first != again) {
            throw new AssertionError("Cache did not reuse Method");
        }
        if (REAL_LOOKUPS.get() != 1) {
            throw new AssertionError("Expected exactly one lookup");
        }

        int sum = (int) again.invoke(calculator, 3, 4);
        System.out.println("ADD=" + sum);

        // Hai overload có key khác nhau.
        String fromInt = (String) invokePublic(
                calculator, "convert",
                new Class<?>[]{int.class}, 12);

        String fromString = (String) invokePublic(
                calculator, "convert",
                new Class<?>[]{String.class}, "hello");

        System.out.println("INT=" + fromInt);
        System.out.println("STRING=" + fromString);
        System.out.println("LOOKUPS=" + REAL_LOOKUPS.get());

        // Invalidate và truy cập lại: lookup được thực hiện lại.
        invalidate(Calculator.class);
        publicMethod(Calculator.class, "add", int.class, int.class);
        System.out.println("AFTER_INVALIDATE=" + REAL_LOOKUPS.get());
    }
}
~~~

Biên dịch/chạy với JDK 18 trở lên:

~~~shell
javac ReflectionCacheDemo.java
java ReflectionCacheDemo
~~~

Kết quả dự kiến khi chạy tuần tự:

~~~text
ADD=7
INT=number=12
STRING=text=hello
LOOKUPS=3
AFTER_INVALIDATE=4
~~~

Diễn giải:

- Lookup đầu tiên cho `add(int, int)` tìm method; lookup thứ hai cùng key lấy trực tiếp từ cache.
- Hai overload `convert(int)` và `convert(String)` tạo thêm hai entry vì parameter types khác nhau.
- `invalidate(Calculator.class)` gọi `ClassValue.remove`, nên lần truy cập sau phải tạo cache mới cho lớp này và tra lại `add`.
- Đây là **kiểm chứng tính đúng của cache**, không chứng minh giảm thời gian ở một JDK cụ thể.

## 6. Chi tiết cần hiểu về tính đồng thời

Ví dụ dùng `ConcurrentHashMap` để nhiều thread có thể cùng đọc/thêm entry mà không làm hỏng map. Tuy nhiên, với đoạn:

~~~java
Method hit = methods.get(key);
if (hit == null) {
    Method found = owner.getMethod(name, types);
    Method existing = methods.putIfAbsent(key, found);
    return existing != null ? existing : found;
}
~~~

Hai thread đến **lần đầu** cùng lúc có thể đều chạy `getMethod(...)`, rồi chỉ một `Method` được giữ lại trong map. Tình huống này **đúng về kết quả**, nhưng không đạt “chính xác một lần lookup” trong mọi trường hợp đồng thời.

Nếu bắt buộc tính toán một lần cho mỗi key ở thời điểm cold cache, cần thiết kế đồng bộ chặt hơn, hoặc dùng `computeIfAbsent` kèm chiến lược xử lý checked exception. Tuy nhiên, khóa chặt quanh reflection có thể gây contention và rủi ro tái nhập: chỉ thêm phức tạp khi đo đạc cho thấy cần thiết.

`ClassValue.computeValue(Class<?>)` cũng **có thể được gọi nhiều lần khi các thread đua nhau**; Javadoc chỉ bảo đảm kết quả liên kết được chọn và trả về phù hợp. Do đó `computeValue` nên nhanh, không có side effect quan trọng, không mở network connection hoặc tạo tài nguyên cần đóng.

### Ranh giới invalidate

`CACHE.remove(owner)` loại bỏ giá trị đang liên kết cho `Class`, nhưng:

- Thread đã lấy `Method` trước đó vẫn có thể dùng nó.
- Thread đang giữ map cũ có thể tiếp tục làm việc với map đó.
- Invalidate không phải cơ chế hủy các `Method`/`Class` đã được caller giữ.
- `ClassValue` quản lý giá trị theo từng lớp, không thay thế một chiến lược quản trị version/config của ứng dụng.

Với metadata Java thông thường, việc invalidate thường không cần thiết vì cấu trúc member của một `Class` ổn định trong một class loader. Dùng invalidate khi cache còn chứa thông tin phụ thuộc cấu hình hoặc vòng đời cụ thể.

## 7. Đừng làm thay đổi hợp đồng truy cập bằng cache

Cache `Method` giúp tái sử dụng đối tượng metadata, **không cấp thêm quyền** cho caller.

- `Class.getMethod` có thể tìm public member được kế thừa, nhưng invoking method vẫn phải hợp lệ theo accessibility của class/member từ vị trí caller.
- Với private members, `getDeclaredMethod` có thể tìm thấy metadata nhưng `invoke` vẫn có thể ném `IllegalAccessException`.
- `trySetAccessible()` chỉ thành công khi quy tắc Java/JPMS cho phép; `setAccessible(true)` có thể ném `InaccessibleObjectException` đối với package không được mở.
- Trạng thái accessible là trạng thái mutable của `AccessibleObject`. Chia sẻ một `Method` đã được bật suppress access check giữa các thành phần với policy truy cập khác nhau có thể làm mờ ranh giới bảo mật mà ứng dụng tự đặt.

Vì vậy ví dụ trên **chỉ** dùng `getMethod` và không gọi `setAccessible(true)`. Nếu muốn cache private members trong framework, cần xác định rõ caller, module, package, permission và phạm vi mà member được phép truy cập. Không dùng cache để vượt qua tính đóng gói của JDK.

Nếu dùng `MethodHandles.Lookup` hoặc `privateLookupIn` để tạo method handle, các quy tắc access của chúng cũng phải được tuân thủ. MethodHandle là một lựa chọn API cho call site cần tối ưu, không phải lối tắt bỏ kiểm tra quyền.

## 8. Tránh giữ class loader quá lâu

Một lỗi dễ xảy ra trong các hệ thống hot reload/plugin:

~~~java
// Cẩn trọng: map static này giữ Class key bằng tham chiếu mạnh.
static final ConcurrentMap<Class<?>, Method> CACHE =
        new ConcurrentHashMap<>();
~~~

Một `Class<?>` tham chiếu tới class loader của nó. Nếu map static sống suốt JVM giữ key `Class<?>`, plugin class loader có thể không được thu hồi dù ứng dụng đã loại plugin.

Các lựa chọn:

| Cách cache | Khi nào phù hợp | Lưu ý |
|---|---|---|
| `static final Method` | Một lớp và một chữ ký cố định suốt vòng đời ứng dụng. | Cố ý giữ member trong vòng đời class chứa cache. |
| `ClassValue<Map<Signature, Method>>` | Nhiều loại lớp động, cần giá trị gắn theo từng `Class`. | Phù hợp với quản lý theo lớp, tránh map global giữ Class key trực tiếp. |
| Map theo lifecycle component/plugin | Có bộ quản lý plugin và giai đoạn unload rõ ràng. | Chủ động `clear` khi plugin dừng; phải chắc chắn mọi tham chiếu được thả. |
| Cache theo tên lớp đơn thuần | Không khuyến nghị khi có nhiều class loader. | Tên bằng nhau không đồng nghĩa cùng `Class`. |

`ClassValue` không làm mọi cache “tự động an toàn bộ nhớ”. Ví dụ key có `Class<?>` tham số của class loader khác, giá trị lưu metadata của lớp khác, hoặc một cache ngoài vòng đời ứng dụng giữ tham chiếu lại thì vẫn có thể phát sinh retention. Với hệ thống plugin, theo dõi class unloading và tài nguyên trên workload thực tế.

## 9. Chi phí nào được giảm, chi phí nào vẫn còn?

| Chi phí | Cache metadata giúp gì? |
|---|---|
| Tra cứu member theo tên/chữ ký | Giảm hoặc loại bỏ trên cache hit. |
| Tạo key và hash map lookup | **Vẫn có** nếu dùng cache động theo chữ ký. |
| Kiểm tra quyền của `Method.invoke` | Không mặc định loại bỏ. |
| Chuẩn bị varargs/`Object[]` | Có thể vẫn cần cấp phát tùy call site và tối ưu JIT. |
| Boxing/unboxing primitive | Có thể vẫn xảy ra; đo bằng profiler/benchmark. |
| Chạy code mục tiêu | Vẫn phải chạy đầy đủ. |
| Khởi tạo class lần đầu | Không bị triệt tiêu bằng việc cache method metadata. |
| Xử lý exception của target | Vẫn tuân hợp đồng `InvocationTargetException`. |

**Không khẳng định “cache reflection giúp nhanh hơn X lần”** nếu chưa có benchmark đáng tin cho workload đang xét. Nếu ứng dụng chỉ lookup một lần trước khi chạy hàng triệu invocation, cache lookup sẽ giúp rất ít phần tổng thời gian so với tốc độ gọi target. Ngược lại, nếu mỗi sự kiện lại gọi `getMethod`, phần lookup có thể đáng kể.

Trong một số tình huống, direct Java method call hoặc interface thông thường còn đơn giản, dễ kiểm thử và được JIT tối ưu tốt hơn. Đừng thêm reflection chỉ để dùng cache.

## 10. Java 18 / JEP 416: vì sao vị trí giữ Method quan trọng?

JEP 416, được triển khai trong Java 18, tái triển khai core reflection dựa trên method handles. Các API `Method.invoke`, `Constructor.newInstance` và field access tiếp tục có hợp đồng Java công khai.

Thiết kế mới cho phép JIT tận dụng tốt hơn các trường hợp metadata phản chiếu được giữ dưới dạng **constant-like reference**, ví dụ trường `static final`. Vì thế:

- Nếu biết class/member từ trước, ưu tiên lưu `Method` trong `static final` và tái sử dụng.
- Nếu member chỉ được biết ở runtime, `ClassValue`/map có ích để giảm lookup nhưng `Method` đọc từ map không mặc nhiên là hằng số đối với JIT.
- Hiệu năng giữa các trường hợp này có thể khác nhau tùy JDK, compilation profile và tính đa hình của call site.
- Không dựa vào các lớp triển khai nội bộ reflection trước JEP 416 như `MagicAccessorImpl` hoặc giả định cấu trúc private field của `Method`.

JEP 416 là thay đổi implementation, **không** có nghĩa phải thay mọi `Method.invoke` bằng method handle. Cần đo cả lookup overhead, invocation overhead và chi phí duy trì cache trước khi quyết định.

## 11. Đo hiệu năng đúng cách: dùng JMH, không dựa vào một vòng nanoTime

Một phép đo vội:

~~~java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    // lookup + invoke hoặc cache + invoke
}
System.out.println(System.nanoTime() - start);
~~~

không đủ để rút ra kết luận ổn định vì:

- JVM cần warmup và biên dịch JIT; kết quả có thể chứa thời gian khởi tạo.
- Tối ưu escape analysis, inlining, constant folding và dead-code elimination có thể làm biến dạng bài đo.
- GC, CPU frequency, thermal throttling, contention và background load gây nhiễu.
- Đường cold lookup và warm cache có tỉ lệ khác hẳn ứng dụng thật.
- Cache dynamic tạo object `Signature`, hash và map access; cần đo cả chi phí này.
- Nếu không tiêu thụ kết quả, JVM có thể loại bỏ một phần công việc.

OpenJDK có **JMH (Java Microbenchmark Harness)** để tổ chức warmup, forks, measurement và xử lý kết quả benchmark. Nên so sánh ít nhất ba trường hợp:

1. **Uncached**: `Class.getMethod` mỗi invocation, sau đó `invoke`.
2. **Dynamic cached**: `ClassValue` + `Signature` + `ConcurrentHashMap` + `invoke`.
3. **Known static final**: `static final Method` + `invoke`.

Nếu thích hợp, thêm **direct call** làm baseline. Đảm bảo cùng method, cùng input, cùng policy và tiêu thụ output qua `Blackhole` hoặc cơ chế chống tối ưu hợp lệ.

Đây là **khung minh họa** cho JMH; cần một dự án JMH đúng cấu hình, có `jmh-core` và annotation processor `jmh-generator-annprocess` theo hướng dẫn OpenJDK. Không chỉ copy một class rồi chạy bằng `javac` thuần khi chưa bổ sung dependency:

~~~java
@State(Scope.Thread)
public class LookupBench {
    private ReflectionCacheDemo.Calculator calculator;
    private static final Method KNOWN_ADD = findKnownAdd();

    private static Method findKnownAdd() {
        try {
            return ReflectionCacheDemo.Calculator.class
                    .getMethod("add", int.class, int.class);
        } catch (NoSuchMethodException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    @Setup(Level.Trial)
    public void setup() {
        calculator = new ReflectionCacheDemo.Calculator();
    }

    @Benchmark
    public void repeatedLookup(Blackhole blackhole) throws Exception {
        Method method = calculator.getClass()
                .getMethod("add", int.class, int.class);
        blackhole.consume(method.invoke(calculator, 3, 4));
    }

    @Benchmark
    public void cachedLookup(Blackhole blackhole) throws Exception {
        Method method = ReflectionCacheDemo.publicMethod(
                calculator.getClass(), "add", int.class, int.class);
        blackhole.consume(method.invoke(calculator, 3, 4));
    }

    @Benchmark
    public void preResolved(Blackhole blackhole) throws Exception {
        blackhole.consume(KNOWN_ADD.invoke(calculator, 3, 4));
    }

    @Benchmark
    public void direct(Blackhole blackhole) {
        blackhole.consume(calculator.add(3, 4));
    }
}
~~~

Trong benchmark thực tế, đặt lớp trong package phù hợp, thêm imports của `org.openjdk.jmh.annotations.*`, `org.openjdk.jmh.infra.Blackhole`, `java.lang.reflect.Method` và thiết lập annotation processing bằng archetype/dự án JMH. Khung không được coi là benchmark đã chạy hoặc đã cho ra con số.

Khi báo cáo, ghi rõ JDK/vendor/version, hệ điều hành, CPU, flags JVM, số forks/warmups, tỉ lệ cache hit/miss, số type và số chữ ký, throughput hoặc time/op, độ phân tán, thay vì một con số tốc độ tuyệt đối không có ngữ cảnh.

## 12. Checklist đưa cache metadata vào production

| Kiểm tra | Điều cần bảo đảm |
|---|---|
| Scope | Chỉ cache những member thực sự được lookup lặp lại trong đường chạy nóng. |
| Correctness | Cache theo đúng `Class<?>`, tên và parameter types có thứ tự. |
| Public/declared | Không trộn `getMethod` với `getDeclaredMethod` nếu key không chứa lookup mode. |
| Null & overload | Kiểm tra key khi có overload, array, primitives và null tham số. |
| Thread safety | Dùng cấu trúc concurrency phù hợp; không nhầm cache atomic với lookup đúng một lần. |
| Class loaders | Không dùng tên class làm identity và tránh map static giữ Class key vĩnh viễn. |
| Access | Cache metadata không làm tăng quyền; tôn trọng JPMS và access check. |
| Failures | Giữ `NoSuchMethodException` đúng hợp đồng; có chủ đích nếu muốn cache misses. |
| Invalidation | Có chiến lược clear/remove nếu vòng đời dữ liệu thực sự yêu cầu. |
| Test | Xác minh kết quả invocation, overload và việc cache hit không tra lại. |
| Benchmark | Dùng JMH hoặc đo workload đại diện có warmup, forks, GC và noise control. |
| Tradeoff | Nếu chữ ký cố định, cân nhắc `static final Method`; nếu không cần reflection, cân nhắc direct call. |

## 13. Câu hỏi tự đánh giá

1. Vì sao key chỉ có tên method `"convert"` là sai khi có overload?
2. Tại sao `Class<?>` tốt hơn tên fully-qualified nếu ứng dụng dùng nhiều class loader?
3. Vì sao các parameter types phải được lưu **theo thứ tự** và không được giữ mảng mutable của caller?
4. `getMethod` và `getDeclaredMethod` khác nhau như thế nào khi method được thừa kế?
5. `ClassValue.computeValue` có bảo đảm chỉ chạy đúng một lần dưới concurrency không?
6. Vì sao `get` + `putIfAbsent` có thể thực hiện lookup thừa ở lần truy cập đồng thời đầu tiên nhưng vẫn đúng kết quả?
7. Vì sao không nên lưu `Class<?>` của plugin trong map static toàn cục mà không có chiến lược dọn dẹp?
8. Cache một `Method` có loại bỏ `IllegalAccessException` hay `InvocationTargetException` không?
9. Trong trường hợp nào `static final Method` có lợi hơn map cache theo chữ ký?
10. Tại sao cần JMH thay vì một phép đo đơn giản bằng `System.nanoTime()`?
11. Khi `CACHE.remove(clazz)`, điều đó có vô hiệu hóa `Method` mà caller khác đang giữ không?
12. Liên hệ JEP 416 với nhận định “metadata trong `static final` có thể thuận lợi hơn cho JIT” là gì?

**Ghi nhớ:** Cache reflection metadata theo **đúng `Class<?>` và chữ ký** giúp tránh `getMethod` lặp lại trên hot path. Với method cố định, dùng `static final Method`; với nhiều type động, `ClassValue<ConcurrentMap<Signature, Method>>` là mô hình có thể kiểm soát concurrency và lifecycle tốt hơn map static giữ `Class` key. Cache không thay đổi access checks, không bảo đảm invocation nhanh hơn, và không thay thế benchmark dựa trên workload thực tế.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 416 – Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
- [Java SE 26: `Class` – `getMethod`, `getDeclaredMethod`, chữ ký và phương thức inherited](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html).
- [Java SE 26: `ClassValue` – liên kết cache theo `Class` và `remove`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassValue.html).
- [Java SE 26: `Method` – `invoke` và hợp đồng truy cập](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Method.html).
- [Java SE 26: `AccessibleObject` – `trySetAccessible`, giới hạn JPMS](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [OpenJDK JMH – Java Microbenchmark Harness và hướng dẫn sử dụng](https://github.com/openjdk/jmh).
