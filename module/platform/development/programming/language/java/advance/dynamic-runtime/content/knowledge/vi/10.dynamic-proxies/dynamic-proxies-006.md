# 10.6 Chuẩn hóa kiểu trả về, giá trị primitive, void và null trong Java Dynamic Proxy

Một **dynamic proxy** của Java thực thi các interface ở runtime. Khi client gọi một method trên proxy, lời gọi được chuyển tới `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`. Method này **luôn khai báo trả `Object`**, trong khi method trên interface có thể trả `int`, `long`, `boolean`, `String`, `Optional<String>`, `void` hoặc một kiểu tham chiếu khác. Vì vậy, code handler cần trả **đúng dạng giá trị mà proxy-generated method có thể chuyển về kiểu đã khai báo**.

Các khác biệt quan trọng nhất:

- **Primitive:** handler phải trả một **wrapper đúng kiểu** (`int` ↔ `Integer`, `long` ↔ `Long`...). `null` gây `NullPointerException`; wrapper sai gây `ClassCastException` tại lời gọi trên proxy.
- **Reference:** handler được trả `null` hoặc object **gán được cho kiểu trả về đã khai báo**. Object không tương thích gây `ClassCastException`.
- **`void`:** proxy **bỏ qua giá trị** handler trả, dù handler có trả object khác `null`; thiết kế rõ ràng nên trả `null`.
- **Chuẩn hóa:** nếu dữ liệu từ JSON/DB/remote API có kiểu chưa chuẩn, hãy kiểm tra `method.getReturnType()`, chuyển đổi có chủ đích **trước khi trả khỏi handler**, và xác định rõ chính sách `null`/overflow/validation.

Bài học này tập trung vào **hợp đồng kiểu trả về của dynamic proxy và cách chuẩn hóa an toàn**; ví dụ Java 17+ hoàn chỉnh có cả đường đi thành công và lỗi dự kiến.

## 1. Luồng lời gọi: hai chữ ký và một điểm chuyển đổi bắt buộc

Giả sử interface định nghĩa:

~~~java
interface Counter {
    int count();
    String label();
    void reset();
}
~~~

Handler vẫn có cùng một chữ ký:

~~~java
@Override
public Object invoke(Object proxy, Method method, Object[] args) throws Throwable
~~~

Hai đoạn trên chỉ minh họa cấu trúc, chưa phải một chương trình chạy độc lập.

~~~text
Client gọi proxy.count()           -> kiểu int tại code gọi
          |
          v
Proxy-generated method             -> gọi handler.invoke(proxy, method, args)
          |
          v
InvocationHandler.invoke           -> Object: ví dụ Integer.valueOf(7)
          |
          v
Proxy-generated method             -> cast sang Integer, unbox thành int
          |
          v
Client nhận 7 (int)

Nếu handler trả null              -> unboxing null -> NullPointerException
Nếu handler trả Long.valueOf(7)   -> cast sang Integer -> ClassCastException
~~~

Điểm cần tách bạch: Java tự **boxing đối số primitive** đưa vào `args` của handler và tự **unboxing wrapper đúng kiểu** khi method proxy trả primitive. Nhưng proxy **không phải hệ thống chuyển đổi dữ liệu tổng quát**. Nó không parse chuỗi sang số và không đảm bảo widening từ mọi numeric wrapper khác nhau.

Chính xác hơn, lời gọi proxy được kiểm tra dựa trên **kiểu trả về khai báo của method được thực thi**, không phải chỉ dựa vào biến `Object` trong handler. Trả `Object` chỉ là chữ ký Java của `InvocationHandler.invoke`; nó không cho phép trả tùy ý mọi object.

## 2. Bảng hợp đồng trả về

| Kiểu trả về của interface | Handler trả đúng | Handler trả `null` | Handler trả sai |
| --- | --- | --- | --- |
| `int` | `Integer` | `NullPointerException` | `Long`, `String` → `ClassCastException` |
| `long` | `Long` | `NullPointerException` | `Integer` → `ClassCastException` |
| `boolean` | `Boolean` | `NullPointerException` | `String("true")` → `ClassCastException` |
| `char` | `Character` | `NullPointerException` | `String("A")` → `ClassCastException` |
| `double` | `Double` | `NullPointerException` | `Float` → `ClassCastException` |
| `String` | `String` hoặc subtype (String là final) | Hợp lệ | `StringBuilder` → `ClassCastException` |
| `Number` | `Integer`/`Long`/`BigDecimal`... | Hợp lệ | `String` → `ClassCastException` |
| `Optional<String>` | `Optional` (nên đúng generic contract) | Runtime cho phép vì reference; thường **không nên** theo API contract | Không phải `Optional` → `ClassCastException` |
| `void` | `null` là quy ước rõ nhất | Hợp lệ | Giá trị khác `null` **bị bỏ qua**, không dùng làm kết quả |

Quy tắc của JDK `InvocationHandler.invoke`: nếu interface method trả primitive, handler phải trả **instance của lớp wrapper tương ứng**. Không phải mọi numeric wrapper “có cùng số” đều hợp lệ. Ví dụ `Long.valueOf(5)` cho `int` không hợp lệ; `Integer.valueOf(5)` cho `long` cũng không hợp lệ **nếu bạn chưa chuyển sang `Long`**.

Bảng trên là **hợp đồng khi giá trị rời handler và được trả cho caller qua proxy**, khác với những quy tắc *method invocation conversion* khi compiler thực hiện lời gọi Java thông thường.

## 3. Bảng đủ tám primitive và lớp wrapper bắt buộc

| Primitive | Wrapper phải trả từ `invoke` | Ví dụ |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.TRUE` |
| `byte` | `Byte` | `Byte.valueOf((byte) 1)` |
| `short` | `Short` | `Short.valueOf((short) 2)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(7)` |
| `long` | `Long` | `Long.valueOf(7L)` |
| `float` | `Float` | `Float.valueOf(1.5f)` |
| `double` | `Double` | `Double.valueOf(1.5d)` |

Đừng viết kiểu trả về là `Number` cho interface nếu contract yêu cầu `int` rồi hy vọng `Long` hoặc `BigDecimal` được tự đổi. Khi method là `int count()`, handler phải trả `Integer`; khi method là `long total()`, handler phải trả `Long`. `void` **không** nằm trong tám primitive dữ liệu và không có wrapper để unbox. `Void.class` là một **kiểu reference** riêng, khác với primitive return type `void.class`.

### Ví dụ sai và đúng

~~~java
// Interface: long total();

return Integer.valueOf(5);                  // Sai: proxy cần Long, gây ClassCastException.
return Long.valueOf(5L);                    // Đúng: wrapper Long.
return Long.valueOf(Integer.valueOf(5));    // Đúng: Integer được unbox thành int, widen sang long và tạo Long.
return Long.valueOf(((Integer) raw).longValue()); // Đúng nếu raw thực sự là Integer.
~~~

Đây là các **dòng minh họa trong handler**, không phải cùng một block method chạy độc lập. Ở dòng cuối, `raw` được giả định có giá trị `Integer` và việc chuyển sang `long` là chủ đích của tác giả.

### Chuyển đổi số cần chính sách chính xác

- `BigDecimal.intValue()` có thể **cắt phần thập phân** hoặc làm mất thông tin khi ngoài phạm vi; nếu chỉ cho phép số nguyên chính xác, dùng `intValueExact()`.
- `Number.longValue()` có thể làm mất dữ liệu ở nhiều subtype; chỉ convert khi bạn biết nguồn dữ liệu, đơn vị và phạm vi hợp lệ.
- `float`/`double` có vấn đề độ chính xác và `NaN`/`Infinity`; nếu contract không cho phép, hãy validate trước khi trả wrapper.
- `byte`/`short`/`char` không nên bị narrow bằng cast âm thầm trong hệ thống xử lý dữ liệu bên ngoài.
- `Boolean.valueOf("maybe")` **trả false**, không tự ném lỗi; nếu input phải là literal boolean, validate chính xác `"true"`/`"false"` trước khi parse.

Một normalizer tốt phân biệt **đúng kiểu sẵn có**, **chuyển đổi có phép**, **thiếu giá trị** và **dữ liệu sai**. Không nên dùng một `(T) raw` không kiểm tra để che giấu vấn đề.

## 4. `void`: giá trị handler được bỏ qua, nhưng side effect và exception thì không

Ví dụ:

~~~java
interface Audit {
    void log(String message);
}
~~~

Nếu `InvocationHandler.invoke` trả `"ok"` sau khi xử lý `log(...)`, generated proxy method có return type `void` nên **không có giá trị để chuyển cho caller**. Giá trị `"ok"` bị bỏ qua, không thành `String` hay exception do sai return type.

~~~java
if (method.getReturnType() == void.class) {
    // Thực hiện side effect thích hợp.
    return null; // Chỉ là quy ước rõ nghĩa; proxy cũng bỏ qua Object khác null.
}
~~~

Lưu ý:

1. **Không có giá trị trả** không đồng nghĩa **không thực hiện gì**: handler vẫn chạy, vẫn có thể ghi log, gọi delegate, thay đổi trạng thái hoặc ném exception.
2. `void.class` khác `Void.class`. Nếu method khai báo `Void apply()` thì đây là **reference-returning method**. `null` hợp lệ; object trả về nếu không null phải gán được cho `Void`. `java.lang.Void` không có public constructor để tạo instance hữu ích.
3. `method.invoke(target, args)` của reflection khi target trả `void` sẽ trả `null`; nhưng đó là semantics của reflection API, **không phải** điều kiện bắt buộc để dynamic proxy chấp nhận method `void`.
4. Nếu async operation cần kết quả, đừng cố nhét nó vào return value của method `void`; cân nhắc công khai contract `CompletionStage<Void>`, `Future<Void>` hoặc kết quả khác ở API interface.
5. Đừng bỏ qua exception từ logic xử lý chỉ vì method là `void`. Exception được truyền theo quy tắc exception của proxy.

## 5. `null`: hợp lệ với reference, nhưng không với primitive

`null` có ba ý nghĩa khác nhau tùy signature:

| Return type | `return null` từ handler có nghĩa gì? |
| --- | --- |
| `int` / `long` / `boolean` / primitive khác | **Sai**: proxy cần unbox wrapper; người gọi nhận `NullPointerException` |
| `String`, `User`, `List<?>`, array, `Optional<?>`, `Void` | **Đúng về type**: reference có thể null; application contract có thể cấm |
| `void` | Rõ ràng, thường dùng; proxy bỏ qua return value |

Vì vậy, “không có dữ liệu” không có một chính sách toàn cục áp dụng cho mọi method:

- Với `int count()`, chọn **trả 0 nếu contract quy định giá trị mặc định**, hoặc ném exception rõ nghĩa; không tự cho 0 thay mọi tình huống thiếu dữ liệu vì dễ che lỗi.
- Với `String nickname()`, có thể trả `null` nếu API đã chấp thuận nullable, nhưng phải tài liệu hóa.
- Với `Optional<User> find(...)`, tốt nhất trả `Optional.empty()` thay vì `null` để giữ contract “không null” mà caller thường mong đợi. Về mặt proxy runtime, `null` vẫn có thể qua được vì `Optional` là reference.
- Với `void`, trả `null` làm handler dễ hiểu; không cần tạo `Void`.

Đừng kết luận `@NotNull` hay `@NonNull` trên method return type làm JVM tự kiểm tra null của proxy. Annotation chỉ có tác dụng nếu checker/framework hoặc code kiểm tra theo contract. Proxy core không tự thực thi Bean Validation.

### Thứ tự lỗi quan trọng

Khi handler trả `null` cho primitive, lỗi ném **khi proxy method cố unbox**, chứ không nhất thiết ném ngay tại câu `return null;`. Tương tự, trả `Integer` cho method trả `String` sẽ bị phát hiện khi generated proxy method cast kết quả. Lỗi vì input dữ liệu nên được nhận diện sớm ở bước normalizer để tạo thông báo cụ thể hơn thay vì đợi một `ClassCastException` khó gỡ.

## 6. Thiết kế bước chuẩn hóa kết quả theo `Method.getReturnType()`

Hướng thiết kế gợi ý:

~~~text
1. Method method từ InvocationHandler.invoke
          |
          v
2. Xác định Class<?> returnType = method.getReturnType()
          |
          +-- void.class        -> thực thi logic -> trả null
          |
          +-- primitive         -> kiểm tra raw != null
          |                       convert có chủ đích sang đúng wrapper
          |                       reject kiểu sai / overflow
          |
          +-- reference         -> raw == null? áp dụng nullable policy
                                  type.isInstance(raw)? chấp nhận
                                  convert có chủ đích? xử lý
                                  không đúng? reject
          |
          v
3. Trả Object đã chuẩn hóa từ handler
          |
          v
4. Proxy-generated method cast/unbox thành return type của interface
~~~

Chữ ký gợi ý của utility:

~~~java
static Object normalize(Class<?> returnType, Object raw)
~~~

Từng bước:

- `returnType == void.class` phải được kiểm tra **trước** `isPrimitive()`, vì `void.class.isPrimitive()` là `true` nhưng `void` không có primitive wrapper/unboxing như tám kiểu dữ liệu.
- Với primitive, dùng một mapping từ primitive type sang wrapper class tương ứng; nếu raw đã có đúng wrapper, giữ nguyên. Nếu cho phép convert, chỉ chuyển khi điều kiện rõ ràng, ví dụ `BigDecimal.intValueExact()` hay `Integer.longValue()`.
- Với reference, dùng `returnType.isInstance(raw)`; `Class.isInstance(null)` là `false` nên cần xử lý null riêng. `isAssignableFrom` cũng có thể dùng khi đã lấy được runtime `raw.getClass()` (phải guard null).
- Nếu raw không hợp lệ, **ném lỗi có chủ đích** ngay trong normalizer để báo dữ liệu không phù hợp. Không tạo wrapper bằng ép kiểu mù.
- `Method.getGenericReturnType()` có thể trả `ParameterizedType` khi interface dùng generic, nhưng **không thay thế** `getReturnType()` trong việc kiểm tra kiểu runtime. Kiểu generic phần tử thường bị erasure.

### Giới hạn của normalizer

Không có giải pháp mặc định nào đúng cho mọi API. Ví dụ `"10"` có được chuyển thành `int 10` không? `null` trong `Integer` có nên đổi thành 0 không? `BigDecimal("1.5")` có được làm tròn không? `Instant` có chuyển thành `String` theo múi giờ nào? Tất cả là **quy tắc nghiệp vụ** cần quyết định công khai.

Ví dụ bên dưới cố ý hỗ trợ đúng một vài conversion, và **từ chối** những conversion còn lại. Nó không phải bộ mapper JSON đa năng.

## 7. Chương trình Java 17+ hoàn chỉnh: chuẩn hóa và quan sát lỗi

Lưu file `ProxyReturnTypesDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.math.BigDecimal;
import java.util.Optional;

public class ProxyReturnTypesDemo {
    public interface ReportApi {
        int count();
        long total();
        boolean enabled();
        char grade();
        String title();
        String absent();
        Optional<String> optional();
        void notifyEvent(String event);
    }

    public interface UnsafeApi {
        int missingPrimitive();
        long wrongWrapper();
        String wrongReference();
        void ignored();
    }

    static final class NormalizingHandler implements InvocationHandler {
        @Override
        public Object invoke(Object proxy, Method method, Object[] args) {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "ReportProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == args[0];
                    default -> throw new UnsupportedOperationException(method.getName());
                };
            }

            // Tuong trung cho du lieu chua chuan hoa den tu mot provider.
            Object raw = switch (method.getName()) {
                case "count" -> new BigDecimal("7");
                case "total" -> Integer.valueOf(5);
                case "enabled" -> "true";
                case "grade" -> "A";
                case "title" -> new StringBuilder("daily");
                case "absent" -> null;
                case "optional" -> Optional.empty();
                case "notifyEvent" -> {
                    System.out.println("event = " + args[0]);
                    yield "ignored by void";
                }
                default -> throw new UnsupportedOperationException(method.getName());
            };
            return normalize(method.getReturnType(), raw);
        }
    }

    static Object normalize(Class<?> type, Object raw) {
        if (type == void.class) return null;

        if (type.isPrimitive()) {
            if (raw == null) {
                throw new IllegalStateException("null for " + type.getName());
            }

            // Chi chuyen doi du lieu da duoc cho phep ro rang.
            if (type == int.class && raw instanceof BigDecimal value) {
                return Integer.valueOf(value.intValueExact());
            }
            if (type == long.class && raw instanceof Integer value) {
                return Long.valueOf(value.longValue());
            }
            if (type == boolean.class && raw instanceof String value
                    && (value.equals("true") || value.equals("false"))) {
                return Boolean.valueOf(value);
            }
            if (type == char.class && raw instanceof String value && value.length() == 1) {
                return Character.valueOf(value.charAt(0));
            }

            Class<?> wrapper = switch (type.getName()) {
                case "boolean" -> Boolean.class;
                case "byte" -> Byte.class;
                case "short" -> Short.class;
                case "char" -> Character.class;
                case "int" -> Integer.class;
                case "long" -> Long.class;
                case "float" -> Float.class;
                case "double" -> Double.class;
                default -> throw new IllegalArgumentException("unknown primitive " + type);
            };

            if (wrapper.isInstance(raw)) return raw;
            throw new IllegalArgumentException("expected " + wrapper.getSimpleName());
        }

        if (raw == null || type.isInstance(raw)) return raw;
        if (type == String.class && raw instanceof CharSequence value) {
            return value.toString();
        }
        throw new IllegalArgumentException("expected " + type.getTypeName());
    }

    public static void main(String[] args) {
        ReportApi report = (ReportApi) Proxy.newProxyInstance(
                ReportApi.class.getClassLoader(),
                new Class<?>[] { ReportApi.class },
                new NormalizingHandler());

        System.out.println("count = " + report.count());
        System.out.println("total = " + report.total());
        System.out.println("enabled = " + report.enabled());
        System.out.println("grade = " + report.grade());
        System.out.println("title = " + report.title());
        System.out.println("absent = " + report.absent());
        System.out.println("optional = " + report.optional());
        report.notifyEvent("ping");
        System.out.println("toString = " + report.toString());
        System.out.println("equals self = " + report.equals(report));
        System.out.println("hashCode identity = " +
                (report.hashCode() == System.identityHashCode(report)));

        UnsafeApi bad = (UnsafeApi) Proxy.newProxyInstance(
                UnsafeApi.class.getClassLoader(),
                new Class<?>[] { UnsafeApi.class },
                (proxy, method, values) -> switch (method.getName()) {
                    case "missingPrimitive" -> null;
                    case "wrongWrapper" -> Integer.valueOf(3);
                    case "wrongReference" -> Integer.valueOf(123);
                    case "ignored" -> "unused";
                    default -> throw new UnsupportedOperationException(method.getName());
                });

        try {
            bad.missingPrimitive();
        } catch (NullPointerException ex) {
            System.out.println("primitive null -> " + ex.getClass().getSimpleName());
        }

        try {
            bad.wrongWrapper();
        } catch (ClassCastException ex) {
            System.out.println("wrong primitive wrapper -> " + ex.getClass().getSimpleName());
        }

        try {
            bad.wrongReference();
        } catch (ClassCastException ex) {
            System.out.println("wrong reference -> " + ex.getClass().getSimpleName());
        }

        bad.ignored();
        System.out.println("void ignores raw result = true");
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file, dùng **JDK 17 trở lên**:

~~~bash
javac --release 17 ProxyReturnTypesDemo.java
java ProxyReturnTypesDemo
~~~

**`stdout` đã kiểm tra khi biên dịch/chạy bằng JDK:**

~~~text
count = 7
total = 5
enabled = true
grade = A
title = daily
absent = null
optional = Optional.empty
event = ping
toString = ReportProxy
equals self = true
hashCode identity = true
primitive null -> NullPointerException
wrong primitive wrapper -> ClassCastException
wrong reference -> ClassCastException
void ignores raw result = true
~~~

### 7.1. Điều gì diễn ra trong normalizer?

- `count()` trả primitive `int`. Source raw là `BigDecimal("7")`; `intValueExact()` cho 7 và utility đóng gói trong `Integer`. Proxy unbox thành `int`.
- `total()` trả primitive `long`. Raw là `Integer.valueOf(5)`; utility chủ động tạo `Long.valueOf(5L)`. Nếu trả nguyên `Integer` khỏi handler, proxy **không tự widen** và sẽ lỗi.
- `enabled()` trả `boolean`. Utility chấp nhận chính xác chuỗi `"true"` hoặc `"false"`, sau đó tạo `Boolean`. Chuỗi khác không bị ép âm thầm thành `false`.
- `grade()` trả `char`. Utility yêu cầu chuỗi dài đúng một `char` rồi tạo `Character`. Nếu cần hỗ trợ Unicode code point ngoài BMP, thiết kế phải xét surrogate pair thay vì coi mọi ký tự hình ảnh là một `char`.
- `title()` yêu cầu `String` nhưng raw là `StringBuilder`, vốn **không phải subtype của String**; utility chuyển bằng `toString()` trước khi trả.
- `absent()` trả `String` nên `null` hợp lệ ở runtime; `optional()` trả một `Optional.empty()` để diễn đạt thiếu dữ liệu theo kiểu `Optional`.
- `notifyEvent(...)` khai báo `void`. Handler thực hiện side effect rồi có raw `"ignored by void"`, nhưng normalizer trả `null`. Trong phần `UnsafeApi.ignored()`, handler trực tiếp trả chuỗi `"unused"` **không qua chuẩn hóa**, và proxy vẫn bỏ qua vì method trả `void`.

### 7.2. Vì sao có đúng ba lỗi trong `UnsafeApi`?

1. `missingPrimitive():int` — handler trả `null`; proxy cố unbox một `Integer` từ null, nên `NullPointerException`.
2. `wrongWrapper():long` — handler trả `Integer` thay vì `Long`, nên generated proxy method cố cast sang `Long` và ném `ClassCastException`.
3. `wrongReference():String` — handler trả `Integer`; không gán được cho `String`, nên `ClassCastException`.

Code chỉ bắt ba exception **cố ý tạo** ở đúng vị trí; không catch `Throwable` bừa bãi. Điều này giữ những lỗi bất ngờ khác có thể xuất hiện dưới dạng lỗi thật để dễ debug.

### 7.3. `equals`, `hashCode` và `toString` cũng được dispatch

Dynamic proxy còn chuyển các lời gọi `Object.equals(Object)`, `Object.hashCode()` và `Object.toString()` vào handler. `method.getDeclaringClass() == Object.class` giúp nhận diện chúng. Demo trả:

- `toString()` → `"ReportProxy"`, là `String` hợp lệ.
- `hashCode()` → một `Integer` từ `System.identityHashCode(proxy)`, hợp lệ với return type `int`.
- `equals(...)` → `Boolean` từ phép so sánh identity `proxy == args[0]`, hợp lệ với return type `boolean`.

Không nên vô tình return `null` ở `hashCode` hoặc `equals`: cả hai trả primitive. Đừng dùng `proxy.toString()` bên trong handler của `toString()` để tự tạo chuỗi, vì nó lại gọi handler và có thể gây đệ quy vô hạn.

## 8. Chuyển tiếp tới một object thật bằng `Method.invoke`

Một handler thường không tự tính tất cả giá trị, mà **forward** lời gọi đến delegate. Hãy phân biệt **kết quả trả về** và **exception**.

~~~java
Object raw;
try {
    raw = method.invoke(delegate, args);
} catch (java.lang.reflect.InvocationTargetException ex) {
    throw ex.getCause();
}
return normalize(method.getReturnType(), raw);
~~~

Đây là **đoạn minh họa nằm bên trong `InvocationHandler.invoke`**: giả sử `delegate` là object phù hợp với declaring interface, `method`/`args` là tham số của handler, `normalize` đã được định nghĩa trong class phù hợp, và method có thể `throws Throwable`.

- Khi delegate method trả primitive, `Method.invoke` **boxing** giá trị sang đúng wrapper (`int` → `Integer`), phù hợp để return qua proxy nếu contract nguyên vẹn.
- Khi delegate method trả `void`, `Method.invoke` trả `null`; handler forward giá trị này là hợp lệ.
- Khi delegate trả reference `null`, `Method.invoke` trả `null`; handler phải quyết định xem API cho phép nullable không.
- Khi delegate method **ném exception**, reflection bọc nó trong `InvocationTargetException`. Nếu handler ném nguyên wrapper, bạn có thể gặp `UndeclaredThrowableException` ngoài ý muốn; thay vào đó, thường phải `throw ex.getCause()` để trả đúng exception đích theo hợp đồng của interface.
- Nếu delegate không triển khai đúng interface/Method được dùng để gọi, `method.invoke(delegate,args)` có thể ném `IllegalArgumentException`; đừng coi đó là lỗi normalize return value.
- Đừng bao giờ dùng `method.invoke(proxy,args)` nếu `proxy` chính là object dynamic proxy đang dispatch vào handler: bạn sẽ gọi lại handler, dẫn đến vòng đệ quy thay vì gọi delegate thật.

Thực tế có thể cần `method.getDeclaringClass()` và metadata của interface để chọn implementation phù hợp. Khi forward giữa interface versions, không nên resolve method đơn thuần chỉ bằng tên nếu có overload; cần kiểm tra cả parameter signature.

## 9. Argument đầu vào khác với giá trị trả về

`InvocationHandler.invoke` nhận:

~~~java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable
~~~

`args` có thể là **`null` khi method không có tham số**, không phải lúc nào cũng là `new Object[0]`. Một argument có kiểu primitive sẽ được boxing thành wrapper trước khi truyền vào handler. Nếu method khai báo `int add(int x, int y)`, handler thường nhìn thấy `Integer` ở `args[0]` và `args[1]`.

Ví dụ:

~~~java
Object[] actualArgs = args == null ? new Object[0] : args;
int numberOfArguments = actualArgs.length;
~~~

Đoạn minh họa này an toàn cho method không tham số. Tuy nhiên, **không trộn xử lý argument và xử lý return**: `args==null` chỉ cho biết method không có argument, không có nghĩa handler phải return `null`. Một `int count()` không có argument vẫn phải trả `Integer`.

Với varargs interface method, ví dụ `void log(String... messages)`, `args` thường chứa **một phần tử mảng `String[]`** ở vị trí argument cuối, không nhất thiết mỗi chuỗi thành một phần tử riêng trong `args`. Reflection forwarding qua `Method.invoke` có tầng varargs riêng; không tự trải mảng thành nhiều tham số khác với chữ ký method đích.

## 10. Lỗi của handler, lỗi của proxy và `UndeclaredThrowableException`

Đừng nhầm các lớp lỗi:

| Lỗi | Phát sinh ở đâu? | Nguyên nhân | Cách sửa |
| --- | --- | --- | --- |
| `NullPointerException` | Proxy method, khi return primitive | Handler return `null` | Không return null cho primitive; validate hoặc báo thiếu dữ liệu rõ ràng |
| `ClassCastException` | Proxy method, khi cast/unbox return | Wrapper primitive sai hoặc reference không tương thích | Chuẩn hóa đúng wrapper hoặc đúng kiểu reference trước khi return |
| `IllegalArgumentException` / `IllegalStateException` | Code normalizer (nếu bạn chọn ném) | Dữ liệu không đáp ứng policy conversion | Thông báo kiểu mong đợi, giá trị nguồn, ngữ cảnh method |
| `ArithmeticException` | `BigDecimal.intValueExact()` v.v. | Số không thể đổi chính xác | Chặn overflow/fraction, điều chỉnh contract |
| `InvocationTargetException` | `Method.invoke` dùng trong handler | Delegate method thực sự ném exception | Lấy `getCause()` và quyết định ném lại exception đích |
| `UndeclaredThrowableException` | Proxy method | Handler ném **checked exception** mà interface không khai báo `throws` tương thích | Khai báo checked exception, convert theo policy, hoặc unwrap đúng cause |
| `StackOverflowError` | Handler tự gọi lại proxy | Handler vô tình invoke method trên chính `proxy` | Gọi delegate thật, không gọi proxy từ handler |
| `ClassCastException` lúc caller xử lý generic data | Phía caller hoặc code đọc generic value | Generic element sai sau erasure | Validate sâu theo generic schema/`Type` nếu contract yêu cầu |

`InvocationHandler.invoke` có thể ném `Throwable`, nhưng khi client gọi interface method, checked exception hợp lệ phải thuộc những exception được khai báo (theo rules của proxy), còn unchecked `RuntimeException`/`Error` có thể truyền trực tiếp. Nếu handler ném checked exception chưa được khai báo, proxy bọc trong `UndeclaredThrowableException`. Do đó, thiết kế handler không chỉ chuẩn hóa **return values** mà còn chuẩn hóa **exception contract**.

Ví dụ nếu interface khai báo `String load() throws IOException` thì handler có thể ném `IOException` hợp lệ; với `String load()` không khai báo checked exception, ném `IOException` có thể dẫn đến `UndeclaredThrowableException`. Với proxy implements nhiều interface có method trùng signature, các `throws` phải tương thích với **tất cả** bản khai báo tương ứng, không chỉ method mà handler nhận ở runtime.

## 11. Return type của method trùng nhau, covariant return và generic erasure

Dynamic proxy có các ràng buộc ngay từ **lúc tạo proxy class**:

- Nếu nhiều proxy interface khai báo **cùng tên và cùng parameter signature**, và có một return type là primitive hoặc `void`, **tất cả** method trùng chữ ký phải có **cùng return type** đó. Không thể tạo một proxy thống nhất cho `int size()` và `long size()` với cùng params.
- Nếu mọi return type đều là reference, phải có **ít nhất một** return type gán được cho tất cả những return type còn lại (một kiểu covariant phù hợp). Ví dụ hai interface trả `Number` và `Integer` có thể được phối hợp vì `Integer` là subtype của `Number`.
- Khi trùng method từ nhiều interface, `Method` được đưa tới handler có thể là method từ **interface xuất hiện sớm hơn** trong danh sách interfaces khi tạo proxy; nó không nhất thiết tương ứng với static reference type mà caller dùng. Đừng phụ thuộc duy nhất vào `method.getDeclaringClass()` để suy luận mọi ngữ cảnh của method trùng.
- Dù proxy cho phép covariant reference returns, handler nên trả object **tương thích với tất cả nhánh API có thể gọi**, không chỉ một return type rộng hơn được chọn làm Method metadata.

### Generic không được kiểm tra sâu tự động

Ví dụ `List<String> names()`: return type ở JVM là `List.class`; proxy có thể xác minh object trả ra là một `List` nhưng **không kiểm tra mọi phần tử là String** theo generic source contract. Nếu handler trả `List.of(123)` cho contract `List<String>`, một code đọc phần tử kiểu `String` có thể gặp `ClassCastException` sau đó. Đừng coi `method.getReturnType().isInstance(list)` là đủ nếu API của bạn đòi kiểm tra generic contents.

Khi thực sự cần, có thể đọc `Method.getGenericReturnType()`, xử lý `ParameterizedType` và xác thực nội dung theo schema riêng; đó là vấn đề validation **ngoài** return-type checks tối thiểu của dynamic proxy.

### Default methods

Interface có thể định nghĩa `default String label() { ... }`. Trên dynamic proxy, lời gọi method đó vẫn đi qua `InvocationHandler`; default body không tự chạy chỉ vì method có modifier `default`. Từ Java 16, handler có thể gọi `InvocationHandler.invokeDefault(proxy, method, args)` (với điều kiện method hợp lệ) nếu muốn dùng default implementation. Kết quả trả từ default method vẫn phải tuân thủ contract return type khi đi qua handler.

~~~java
if (method.isDefault()) {
    Object[] callArgs = args == null ? new Object[0] : args;
    return InvocationHandler.invokeDefault(proxy, method, callArgs);
}
~~~

Đây là đoạn **minh họa trong handler** với `import java.lang.reflect.InvocationHandler;` và `throws Throwable`. Không phải mọi default method đều có thể được gọi theo mọi cấu hình interfaces khi chúng bị override hoặc có xung đột; Javadoc có điều kiện resolution rõ ràng.

## 12. Thiết kế policy cho null và conversion trong hệ thống thật

Một ứng dụng lớn nên viết rõ **normalization contract**, không để mỗi handler tự suy luận:

| Câu hỏi thiết kế | Ví dụ policy |
| --- | --- |
| Missing value của primitive được xử lý thế nào? | Ném `IllegalStateException` thay vì tùy tiện đổi sang 0 |
| Có cho phép numeric widening không? | `Integer` → `Long` cho `long`, có điều kiện rõ; **không** để proxy tự làm |
| Có cho phép rounding/truncation không? | Không; `BigDecimal.intValueExact()` cho `int`; reject phần lẻ/overflow |
| `boolean` từ chuỗi chấp nhận literal gì? | Chỉ `"true"` và `"false"`, có hoặc không phân biệt hoa-thường theo contract |
| `String` có tự nhận `CharSequence` không? | Nếu được phép, gọi `toString()`; còn lại reject |
| Nullable reference có được return null? | Theo đặc tả method; nếu `Optional`, nên dùng `Optional.empty()` |
| `void` trả gì? | `null` từ handler để dễ đọc, dù proxy sẽ bỏ qua mọi Object return |
| Runtime validation có cần áp dụng cho collection generic? | Nếu contract yêu cầu, duyệt và validate các element riêng, không trông đợi proxy |
| Lỗi conversion đi đâu? | Ném exception đủ thông tin, gắn method name, expected type, actual class; không ghi dữ liệu nhạy cảm vào log |

Đối với framework, có thể thêm một `ReturnPolicy`/`ResultAdapter` gắn với metadata method, cache `Method.getReturnType()` nếu cần tối ưu khi gọi nhiều, và tách ba khối: **delegate invocation → normalize result → return to proxy**. Nếu dùng JSON mapper, hãy phân biệt validation tại biên với conversion sau deserialization; object đã có runtime type đúng vẫn có thể mang giá trị nghiệp vụ sai.

**Lưu ý về bảo mật:** đừng cho input không tin cậy tự chọn method name và result adapter bất kỳ rồi thực thi qua proxy; xác thực interface/member được phép và không log raw secret values khi báo lỗi conversion. Normalizer nên đo kiểu và đưa thông báo tối thiểu hữu ích thay vì rò rỉ payload.

## 13. Kiểm thử bắt buộc cho handler có nhiều return types

Một test suite nên có ít nhất các nhóm:

1. **Mọi primitive:** kiểm tra từng wrapper chính xác (`Boolean`, `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`), rồi kiểm tra kết quả unboxing tại caller.
2. **Sai wrapper có cùng giá trị số:** `Integer` trả cho `long`, `Long` trả cho `int`; phải reject, không tự widen.
3. **Primitive null:** xác minh exception theo policy; nếu không có normalizer, kỳ vọng `NullPointerException` từ proxy.
4. **Reference đúng/sai:** `String`, subtype của interface, object không gán được; null reference hợp lệ nếu contract cho phép.
5. **Void:** handler thực thi side effect và return arbitrary object; proxy không trả giá trị. Handler không nuốt exception.
6. **Missing data:** thử null, chuỗi rỗng, `Optional.empty()`, trường hợp phải ném exception riêng.
7. **Numeric boundaries:** số âm, 0, max/min của primitive, phần thập phân khi chuyển sang integer, overflow, `NaN` và infinity khi policy có liên quan.
8. **Object methods:** `equals` trả Boolean, `hashCode` trả Integer, `toString` trả String; tránh recursion.
9. **Delegate exceptions:** thử runtime exception, checked exception hợp lệ và không khai báo, `InvocationTargetException` được unwrap đúng.
10. **Generic/covariant returns:** proxy interfaces trùng signature, reference result gán được cho mọi đường gọi; validate collection elements nếu contract cần.

Tránh test chỉ gọi `handler.invoke(...)` trực tiếp. Việc gọi trực tiếp handler **bỏ qua** generated proxy method, nên bạn sẽ không quan sát lỗi unboxing/casting của proxy. Các test quan trọng phải **gọi thông qua object proxy thật** như `api.count()`, `api.total()`, `api.title()` để bắt đúng semantics production.

## 14. Các tình huống hay nhầm

### “Handler trả Long cho int, nhưng Java tự chuyển kiểu số được mà?”

Không. Việc Java có thể widen `int` sang `long` trong lời gọi Java bình thường **không** có nghĩa generated proxy method sẽ chuyển mọi wrapper số. `long total()` yêu cầu handler trả `Long`; nếu raw là `Integer`, conversion phải được làm trước khi return từ handler.

### “Cứ return null cho mọi method không biết xử lý có được không?”

Không. `null` gây `NullPointerException` cho primitive returns. Với references, null có thể hợp kiểu nhưng vi phạm contract của ứng dụng. Với `void` null là lựa chọn rõ ràng. Handler nên ném `UnsupportedOperationException` cho method chưa hỗ trợ, hoặc dùng policy được ghi rõ, không silently return null cho toàn bộ API.

### “Method.getReturnType() là Object vì handler.invoke trả Object?”

Không. `method` đại diện cho method **trên interface**, nên `method.getReturnType()` là kiểu khai báo, ví dụ `int.class`, `String.class` hoặc `void.class`. `Object.class` chỉ là return type của **chính** `InvocationHandler.invoke`, không thay thế return type của method được proxy gọi.

### “Nếu method trả Optional thì null bị proxy từ chối?”

Không. `Optional` là reference type nên runtime proxy chấp nhận `null` về mặt type. Nhưng `Optional.empty()` thường là policy API tốt hơn; caller có thể gọi `optional.isPresent()` và bị `NullPointerException` nếu handler vi phạm contract.

### “Trả object khác null từ handler cho void có gây ClassCastException?”

Không. Generated proxy method khai báo `void` bỏ qua return value của handler. Dù vậy return `null` giữ code dễ hiểu hơn.

### “Mọi exception từ delegate đều bị proxy tự unwrap?”

Không. `Method.invoke` bọc exception trong `InvocationTargetException`; handler phải quyết định `throw ex.getCause()` khi forward. Proxy lại có quy tắc riêng về checked exception không được khai báo, có thể xuất hiện `UndeclaredThrowableException`.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Interface có `int getCount()`, handler return `Long.valueOf(3)`. Caller nhận gì?

**Đáp án:** `ClassCastException`, vì proxy cần `Integer` để unbox `int`. Dữ liệu numeric cần được chuyển thành `Integer` trong handler theo policy hợp lệ.

**Câu 2.** Interface có `long getTotal()`, handler return `Integer.valueOf(3)`. Giá trị số có đúng nhưng handler có hợp đồng đúng không?

**Đáp án:** Không. Proxy cần `Long`. Có thể chủ động `Long.valueOf(integer.longValue())` trong normalizer.

**Câu 3.** Method trả `void`, handler return `"done"`. Proxy có ném `ClassCastException` không?

**Đáp án:** Không chỉ vì giá trị đó. Proxy bỏ qua Object return của handler cho `void`; side effect hoặc exception của handler vẫn xảy ra.

**Câu 4.** Method trả `String`, handler return `null`. Có hợp lệ không?

**Đáp án:** Hợp lệ ở tầng kiểu của dynamic proxy; có thể bị cấm bởi contract ứng dụng.

**Câu 5.** Method trả `boolean`, handler return `null`. Kết quả?

**Đáp án:** `NullPointerException` khi proxy cố unbox `Boolean`.

**Câu 6.** `method.getReturnType() == void.class` và `method.getReturnType() == Void.class` khác gì?

**Đáp án:** `void.class` mô tả method không trả giá trị; `Void.class` mô tả return type là một reference class, nên có thể trả `null` như reference.

**Câu 7.** Trực tiếp gọi `handler.invoke(...)` để test có đủ xác minh conversion return của proxy không?

**Đáp án:** Không. Khi gọi trực tiếp bạn nhận `Object` từ handler, bỏ qua proxy-generated method thực hiện cast/unbox.

**Câu 8.** Vì sao `List<String>` trả `List<Integer>` có thể vượt qua kiểm tra return type của proxy?

**Đáp án:** Vì erasure khiến runtime check ở proxy chỉ thấy `List`; kiểm tra nội dung phần tử cần validation riêng.

**Câu 9.** Handler forward đến delegate bằng `method.invoke(...)` nhưng delegate ném `IOException`. Cần xem xét gì?

**Đáp án:** Reflection ném `InvocationTargetException`, nên handler cần unwrap cause; `IOException` chỉ có thể đi qua proxy như checked exception nếu interface method khai báo `throws` tương thích. Nếu không, proxy có thể bọc trong `UndeclaredThrowableException`.

## Tài liệu chính thức

- [Java SE 21 — InvocationHandler.invoke và hợp đồng primitive, reference, null, exception](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 21 — Proxy: Object methods, return type giữa nhiều interface, duplicate method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 21 — Method.getReturnType và getGenericReturnType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 21 — InvocationTargetException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Java SE 21 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html)
