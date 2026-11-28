# ClassValue và vòng đời class loader khi thiết kế cache reflection cho thư viện

## 1. Vì sao cache reflection phải quan tâm đến class loader?

Một thư viện serialization, dependency injection, object mapping hoặc routing thường lặp lại cùng thao tác reflection: tìm `Method`, duyệt `Field`, đọc annotation, tạo accessor, hoặc chuẩn bị `MethodHandle`. Cache kết quả giúp tránh lặp công việc tìm kiếm và chuẩn bị metadata trên đường xử lý nóng.

Nhưng thư viện có thể sống lâu hơn những lớp mà nó xử lý. Trong application server, hệ thống plugin, test runner, framework hot reload hoặc môi trường triển khai lại ứng dụng, một `ClassLoader` có thể tạo ra nhiều `Class<?>` rồi được kỳ vọng ngừng tồn tại khi plugin/ứng dụng bị tháo.

Một cache tĩnh kiểu `Map<Class<?>, Method>` có thể giữ lại những lớp đó vô thời hạn. Nếu thư viện được nạp bởi class loader sống lâu, tham chiếu từ cache có thể ngăn class loader của plugin trở nên thu hồi được. Hậu quả là heap và metaspace tăng sau nhiều vòng load/unload.

`java.lang.ClassValue<T>` là API được thiết kế để **gắn một giá trị được tính lười với từng đối tượng `Class`**. Nó là một lựa chọn thích hợp cho metadata reflection sống theo lớp. API đã có từ Java 7 và vẫn được hỗ trợ trên JDK hiện đại; giá trị của bài học trong phạm vi Java 18 là thiết kế cache đúng vòng đời, đồng thời hiểu bối cảnh JEP 416 đã triển khai core reflection dựa trên method handles.

Mục tiêu của bài:

- Phân biệt danh tính lớp với tên lớp, nhất là khi có nhiều class loader.
- Nhận diện cache giữ strong reference gây class-loader leak.
- Dùng `ClassValue` để tính và lưu metadata reflection theo từng `Class`.
- Hiểu `get`, `computeValue`, `remove`, lỗi và tranh chấp giữa nhiều thread.
- Quản lý invalidation, độ lớn cache, quyền truy cập reflection và vòng đời plugin.
- Thiết kế kiểm chứng vừa đo hiệu năng vừa theo dõi class unloading.

## 2. Danh tính Class gồm tên và class loader định nghĩa nó

Hai class có cùng binary name không nhất thiết là cùng kiểu. Trong Java, danh tính kiểu liên quan đến **binary name và defining class loader**. Chẳng hạn hai plugin khác nhau đều có class tên `com.example.plugin.Widget`, nhưng do hai class loader riêng định nghĩa.

```text
Thư viện dùng chung (loader sống lâu)
      |
      +-- Plugin Loader A
      |        |
      |        +-- com.example.plugin.Widget -> Class<?> A
      |
      +-- Plugin Loader B
               |
               +-- com.example.plugin.Widget -> Class<?> B

Class<?> A != Class<?> B
```

Các lớp cùng tên nhưng được định nghĩa bởi loader khác nhau có thể có method, annotation và hành vi khác nhau. Cache dùng tên String làm khóa có thể nhầm metadata từ lớp A sang lớp B.

```java
// Sai khi nhiều loader có thể định nghĩa lớp cùng tên.
Map<String, Method> byName = new ConcurrentHashMap<>();

// Khóa Class<?> phân biệt đúng hai Class, nhưng map tĩnh có thể giữ loader.
Map<Class<?>, Method> byClass = new ConcurrentHashMap<>();
```

`ClassValue` cho phép hỏi trực tiếp một giá trị theo `Class<?>`:

```java
Metadata metadata = CLASS_METADATA.get(widget.getClass());
```

Một `ClassValue` có thể nhận các `Class` thuộc nhiều loader. Giá trị được gắn theo danh tính `Class`, vì vậy không cần nối tên lớp với ID loader để tự làm khóa.

## 3. Vì sao static Map<Class<?>, ...> dễ giữ class loader?

Xem cache đặt trong thư viện dùng chung:

```java
import java.lang.reflect.Method;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

final class ReflectionCache {
    static final Map<Class<?>, Method[]> METHODS = new ConcurrentHashMap<>();

    static Method[] methodsOf(Class<?> type) {
        return METHODS.computeIfAbsent(type, Class::getDeclaredMethods);
    }
}
```

`ConcurrentHashMap` giữ tham chiếu mạnh đến key và value. `Class<?>` giữ liên hệ đến defining loader; `Method` cũng có liên hệ đến declaring class và các kiểu trong chữ ký. Nếu map tĩnh này thuộc một loader còn sống sau khi plugin bị tháo, các lớp cũ có thể tiếp tục reachable.

Đồ thị tham chiếu điển hình:

```text
GC root
   |
   v
Static field của thư viện chung
   |
   v
ConcurrentHashMap
   |
   +-- key: Class<?> của plugin
   |         |
   |         v
   |   defining ClassLoader
   |
   +-- value: Method[] / MethodHandle / metadata
             |
             v
        Class<?> và kiểu liên quan
```

Đóng `URLClassLoader` hoặc xóa plugin khỏi danh sách active **không đủ** nếu những strong reference này còn tồn tại. `URLClassLoader.close()` giải phóng tài nguyên mà loader đang quản lý, nhưng không có nghĩa JVM sẽ unload các class ngay lập tức.

Theo JLS §12.7, JVM chỉ có thể unload một lớp nếu defining class loader của lớp đó có thể được GC thu hồi; việc unload thực tế là tối ưu hóa, không phải hành vi được bảo đảm tại một thời điểm cố định.

## 4. ClassValue gắn cache với từng Class

`ClassValue<T>` khai báo cách tính một giá trị kiểu `T` cho mỗi `Class<?>`:

```java
import java.lang.ClassValue;

public final class Example {
    private static final ClassValue<Integer> DECLARED_METHOD_COUNT =
            new ClassValue<>() {
                @Override
                protected Integer computeValue(Class<?> type) {
                    return type.getDeclaredMethods().length;
                }
            };

    public static int methodCount(Class<?> type) {
        return DECLARED_METHOD_COUNT.get(type);
    }
}
```

Lần `get(type)` đầu tiên khi chưa có association sẽ kích hoạt `computeValue(type)`. Những lần truy cập sau sử dụng giá trị đã được gắn với class, miễn là association chưa bị `remove`.

Đây là API hiện hành theo Javadoc Java SE 26:

| Phương thức | Ý nghĩa |
| --- | --- |
| `computeValue(Class<?>)` | Tính giá trị khi association chưa tồn tại; do subclass triển khai |
| `get(Class<?>)` | Lấy giá trị đã gắn hoặc thử tính và gắn giá trị |
| `remove(Class<?>)` | Xóa association của một `Class` và vô hiệu hóa phép tính quá cũ theo quy tắc concurrency |

Không có thao tác `put` công khai, không có `keySet()` hoặc API liệt kê toàn bộ `Class` đã từng được truy cập. Đây là cách nhìn theo association với class, không phải một map toàn cục để duyệt và quản lý thủ công.

## 5. Thiết kế cache cho một accessor reflection cụ thể

Giả sử thư viện muốn đọc method công khai `String name()` từ nhiều loại đối tượng. Ta có thể cache `Optional<Method>` theo runtime class.

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Objects;
import java.util.Optional;

public final class NameReader {
    private NameReader() {
    }

    private static final ClassValue<Optional<Method>> NAME_METHOD =
            new ClassValue<>() {
                @Override
                protected Optional<Method> computeValue(Class<?> type) {
                    try {
                        Method method = type.getMethod("name");

                        if (Modifier.isStatic(method.getModifiers())
                                || method.getParameterCount() != 0
                                || method.getReturnType() != String.class) {
                            return Optional.empty();
                        }
                        return Optional.of(method);
                    } catch (NoSuchMethodException notFound) {
                        return Optional.empty();
                    }
                }
            };

    public static Optional<String> readName(Object target)
            throws ReflectiveOperationException {
        Objects.requireNonNull(target, "target");

        Optional<Method> method = NAME_METHOD.get(target.getClass());
        if (method.isEmpty()) {
            return Optional.empty();
        }

        Object result = method.orElseThrow().invoke(target);
        return Optional.ofNullable((String) result);
    }

    public static void invalidate(Class<?> type) {
        NAME_METHOD.remove(Objects.requireNonNull(type, "type"));
    }
}
```

Ví dụ sử dụng:

```java
public class Customer {
    public String name() {
        return "Lan";
    }
}

System.out.println(NameReader.readName(new Customer()));
// Optional[Lan]
```

Những quyết định ở đây có chủ đích:

- `target.getClass()` là khóa thực tế, phân biệt các class cùng tên do loader khác nhau định nghĩa.
- `getMethod("name")` tìm method public, kể cả method public được kế thừa.
- `Optional.empty()` thể hiện method không tồn tại hoặc sai signature; tránh lookup lại liên tục.
- Cache không giữ một map tĩnh có key `Class<?>`.
- Không gọi `setAccessible(true)` và không cố vượt qua ranh giới module.
- `Method.invoke` vẫn có thể ném `IllegalAccessException` hoặc `InvocationTargetException`; caller cần xử lý theo hợp đồng nghiệp vụ.

`getMethod` tìm method công khai nhưng khả năng invoke còn phụ thuộc quyền truy cập của declaring class, module và runtime context. Khi method không thể được truy cập, không nên tự chuyển quyền truy cập hoặc nuốt lỗi để cho cache “hoạt động”.

### 5.1. Vì sao cache negative lookup bằng Optional?

Thư viện có thể xử lý hàng triệu đối tượng của một lớp không có `name()`. Nếu lần nào cũng phản chiếu để kiểm tra rồi bắt `NoSuchMethodException`, chi phí phát sinh liên tục.

`Optional.empty()` là một giá trị ổn định cho kết quả “không có member theo hợp đồng tìm kiếm” và được cache theo class. Tuy nhiên, nếu lớp được thay đổi bởi instrumentation hoặc cấu hình khác khiến lookup cần làm lại, ứng dụng phải có chính sách invalidation rõ ràng.

Không nên đồng nhất mọi exception với “không có method”. Lỗi truy cập module, lỗi security hoặc lỗi khởi tạo metadata cần được báo rõ, không chuyển thành `Optional.empty()`.

## 6. Hiệu năng: cache chi phí lookup, không bảo đảm invoke nhanh nhất

Cache reflection giúp tránh các thao tác lặp lại như:

- `getDeclaredMethods()`, `getMethod()`, `getDeclaredFields()`.
- Duyệt annotation và dựng metadata/schema.
- Chuẩn bị `MethodHandle`, `MethodType` hoặc accessor.
- Tạo bảng dispatch theo type.

Tuy nhiên, cache một `Method` không đồng nghĩa mọi lần `Method.invoke` sẽ nhanh ngang lời gọi Java trực tiếp. JEP 416 từ Java 18 đã triển khai `Method`, `Constructor` và `Field` trên nền method handles, nhưng hiệu năng phụ thuộc call site, JIT, khả năng coi metadata là hằng và workload thực tế.

Vì vậy, hãy đo **hai loại chi phí riêng**:

| Chi phí | Câu hỏi đo |
| --- | --- |
| Lookup và chuẩn bị metadata | Không cache phải làm lại những gì? |
| Truy cập cache | `ClassValue.get` tốn bao nhiêu trong workload thật? |
| Invocation | `Method.invoke`, `MethodHandle.invokeExact` hay direct call có khác biệt sau warmup? |
| Vòng đời | Cache giữ bao nhiêu class/loader sau nhiều lần nạp plugin? |

Có trường hợp một cấu trúc không cache đủ nhanh vì số class nhỏ và lookup hiếm. Có trường hợp dữ liệu truy cập động liên tục thì cache rất hữu ích. Tối ưu hóa dựa trên profiling và benchmark đại diện, tránh suy từ tên API.

## 7. Concurrency: computeValue có thể chạy nhiều lần

Một hiểu nhầm phổ biến là `computeValue` luôn chạy đúng một lần cho mỗi `Class`. Javadoc hiện hành nói rõ: khi nhiều thread tranh chấp, **có thể có nhiều lần `computeValue`**, nhưng chỉ một giá trị được gắn cho association ở một thời điểm và được `get` trả về theo quy tắc của API.

```text
Thread A                         Thread B
   |                                |
get(MyClass.class)             get(MyClass.class)
   |                                |
computeValue(A)                computeValue(B)
   |                                |
   +--------- race to associate ----+
                         |
                         v
              Một giá trị được gắn
                         |
                         v
           Các get nhận association
```

Do đó `computeValue` nên:

- Không có side effect không thể lặp lại.
- Không gửi email, thực hiện thanh toán hoặc đăng ký tài nguyên ngoài JVM.
- Không tạo worker thread, socket hoặc file handle cần lifecycle riêng nếu không có cách dọn kết quả thua cuộc.
- Ưu tiên tính metadata thuần, immutable và an toàn khi thực hiện lại.
- Tránh dựa vào bộ đếm chính xác “mỗi lớp đúng một lần”.

`ClassValue` đồng bộ việc **gắn association**, không bảo đảm `computeValue` của bạn là một critical section chạy duy nhất.

### 7.1. Ví dụ test điều đúng, tránh đếm sai

```java
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ClassValueTest {
    @Test
    void reusesValueAndCanRecomputeAfterRemoval() {
        AtomicInteger attempts = new AtomicInteger();

        ClassValue<Object> cache = new ClassValue<>() {
            @Override
            protected Object computeValue(Class<?> type) {
                attempts.incrementAndGet();
                return new Object();
            }
        };

        Object first = cache.get(String.class);
        Object second = cache.get(String.class);
        assertSame(first, second);

        cache.remove(String.class);

        Object third = cache.get(String.class);
        assertNotSame(first, third);
    }
}
```

Test này chạy tuần tự để xác minh cached identity và invalidation. Nếu kiểm tra dưới concurrency, không assert `attempts == 1`: nhiều thread có thể cùng gọi `computeValue`. Hãy assert kết quả được trả tương thích với association và không có lỗi logic khi `remove` xen vào.

## 8. Ngoại lệ trong computeValue không được cache

Nếu `computeValue` ném exception, lần `get` khởi phát có thể ném exception đó; không có giá trị thành công nào được gắn chỉ nhờ invocation bị lỗi. Lần `get` sau có thể thử tính lại.

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger attempts = new AtomicInteger();

ClassValue<String> cache = new ClassValue<>() {
    @Override
    protected String computeValue(Class<?> type) {
        if (attempts.incrementAndGet() == 1) {
            throw new IllegalStateException("Temporary failure");
        }
        return type.getName();
    }
};
```

Nếu chạy tuần tự: lần gọi đầu tiên có thể nhận `IllegalStateException`, lần sau tính và gắn tên class. Khi có race hoặc remove, hãy theo quy tắc chi tiết của Javadoc thay vì giả định thứ tự tuyến tính đơn giản giữa mọi lời gọi.

Đối với lỗi thiếu member mang tính ổn định, dùng giá trị như `Optional.empty()` hoặc record kết quả. Đối với lỗi tạm thời, cân nhắc để nó lan ra caller hoặc lập chính sách retry ở tầng bên ngoài.

Không cache vĩnh viễn một exception chứa context plugin nếu hệ thống cần đổi cấu hình rồi chạy lại; đó có thể trở thành lỗi stale metadata và giữ thêm object không cần thiết.

## 9. remove(Class) và ý nghĩa invalidation

`remove(type)` loại bỏ association của một `Class` đối với đúng instance `ClassValue` đó.

```java
Class<?> type = Customer.class;

NameReader.readName(new Customer()); // Tạo hoặc dùng metadata
NameReader.invalidate(type);          // Xóa association hiện hành
NameReader.readName(new Customer()); // Có thể tính lại metadata
```

Theo Javadoc, `remove` còn vô hiệu hóa những tính toán không còn hợp lệ theo thứ tự concurrency của `get` và `computeValue`. Nhưng lưu ý:

- `remove` không xóa mọi class trong cache.
- Không có API mặc định `clearAll()` để duyệt từng class.
- `remove` không đóng tài nguyên mà value từng giữ.
- `remove` không buộc JVM unload class.
- Thread đã nhận `Method` hoặc metadata cũ vẫn có thể giữ và sử dụng chúng; `remove` chỉ tác động association trong ClassValue.

Thiết kế cache nên có một chính sách invalidation đơn giản: khi schema/config/version liên quan đến class thật sự đổi, gọi `remove(type)` hoặc thay instance cache do component sở hữu. Đối với metadata bất biến theo class, có thể không cần invalidation trong hoạt động thông thường.

### 9.1. Không gọi remove() để “xả” mọi class khi plugin đóng

Nếu thư viện không giữ registry mạnh các class plugin, không cần giữ một danh sách `Class<?>` chỉ để gọi `remove()` khi unload; danh sách đó tự nó có thể giữ class loader.

Khi plugin bị tháo, giải phóng các reference do ứng dụng/plugin sở hữu. ClassValue cho phép metadata gắn với class đi theo vòng đời của class, trong khi các reference bên ngoài vẫn cần được xử lý đúng.

## 10. Tại sao ClassValue giúp quản lý vòng đời class loader?

Điểm khác biệt kiến trúc là nơi một association được quản lý. Với map tĩnh, thư viện tạo một tập strong keys cần tự thu gom. Với `ClassValue`, association được gắn theo `Class` bởi runtime.

```text
Cách dễ giữ loader:
  Static map -> Class plugin -> defining loader
             -> Method plugin -> Class plugin

Cách dùng ClassValue:
  Static ClassValue (một instance dùng chung)
       |
       +-- get(Class plugin) -> giá trị gắn với Class plugin

Thư viện không giữ một Map<Class plugin, ...> mạnh để liệt kê class.
```

Điều này làm `ClassValue` phù hợp để cache metadata theo class trong thư viện có tuổi thọ dài. Tuy nhiên, nó **không phải bảo đảm tuyệt đối chống mọi leak**:

- Nếu code đưa `Method`, `Class<?>`, `MethodHandle`, metadata hoặc instance plugin vào một global collection khác, loader vẫn có thể bị giữ.
- Nếu plugin đăng ký listener, shutdown hook, thread, executor, `ThreadLocal` hoặc context class loader nhưng không giải phóng, vẫn có đường tham chiếu khác.
- Nếu metadata của một class giữ các đối tượng cần close, cơ chế association không tự gọi close khi class trở nên unreachable.
- Nếu callback từ thư viện sang plugin vẫn được giữ sau unload, cache reflection đúng cũng không cứu được vòng đời.

ClassValue giải quyết lớp vấn đề *strong-key registry theo Class*; ứng dụng vẫn phải đánh giá toàn bộ đồ thị tham chiếu.

## 11. So sánh các cấu trúc cache khi thư viện hỗ trợ plugin

| Cấu trúc | Lợi ích | Cần chú ý về vòng đời |
| --- | --- | --- |
| `ConcurrentHashMap<Class<?>, Metadata>` tĩnh | Dễ enumerate và quản lý bằng tay | Strong key/value có thể pin class loader |
| `WeakHashMap<Class<?>, Metadata>` | Key yếu | Value có thể giữ lại key gián tiếp; đồng bộ/concurrency do caller |
| `ClassValue<Metadata>` | Lazy per-Class, concurrency của association do JDK xử lý | Không có enumerate/clear-all; value không tự close tài nguyên |
| Map thuộc từng plugin/loader | Rõ owner và lifecycle | Phải xóa/dọn map khi plugin stop; tránh owner rò vào toàn cục |
| Không cache | Đơn giản và ít trạng thái | Chi phí lookup lặp lại nếu dùng nhiều |

Không có một lựa chọn đúng cho mọi workload. Với metadata bất biến và xác định hoàn toàn từ `Class<?>`, `ClassValue` thường là lựa chọn phù hợp để xem xét trước. Nếu cache có policy LRU, TTL, quota hoặc cần enumerate, có thể dùng một cơ chế khác nhưng phải thiết kế ownership/cleanup rõ ràng.

### 11.1. WeakHashMap không tự động giải quyết mọi vòng tham chiếu

Một bẫy điển hình:

```java
Map<Class<?>, Method> weakMap = new WeakHashMap<>();
```

Key là weak reference nhưng value là strong reference. Một `Method` có thể trỏ đến declaring class (và các kiểu trong signature), khiến key vẫn reachable qua value trong map. Vì vậy, chỉ chuyển key từ strong sang weak không nhất thiết phá chu trình giữ loader.

`WeakHashMap` cũng không tự đồng bộ; không dùng trực tiếp làm cache concurrent khi có nhiều thread mà không thiết kế đồng bộ hoặc cấu trúc thích hợp.

## 12. Độ lớn của metadata theo Class vẫn cần được kiểm soát

`ClassValue` tránh global strong map keys, nhưng không giải quyết mọi vấn đề về kích thước value.

Ví dụ một value chứa:

```java
import java.lang.reflect.Method;
import java.util.List;

ClassValue<List<Method>> ALL_DECLARED = new ClassValue<>() {
    @Override
    protected List<Method> computeValue(Class<?> type) {
        return List.of(type.getDeclaredMethods());
    }
};
```

Đây là minh họa cho một **cache rộng**; nó giữ tất cả method được khai báo ở từng class đã truy cập. Trong thư viện chỉ gọi một vài accessor, cache theo method cần dùng (như `NameReader`) thường tiết kiệm hơn.

Nếu thư viện tạo nhiều signature key động hoặc giữ toàn bộ metadata không cần thiết cho mỗi class, heap vẫn tăng theo số class đang sống. Đó có thể là tiêu thụ bộ nhớ hợp lệ nhưng cao; nếu class loader không unload, cache cũng tiếp tục sống cùng class.

Những nguyên tắc hợp lý:

- Chỉ cache member đang được dùng thật.
- Cân nhắc metadata immutable khi compute một lần.
- Dùng key thể hiện **signature đầy đủ** nếu có overload; chỉ tên method không đủ.
- Không cache object instance của plugin khi cache chỉ cần `Method`/schema.
- Nếu value chứa map mutable, dùng cấu trúc concurrent phù hợp hoặc đồng bộ.
- Không chạy công việc nặng không cần thiết trong `computeValue`.
- Không quên invalidation khi metadata phụ thuộc cấu hình ngoài class.

## 13. Cache MethodHandle theo ClassValue

Nếu thư viện chủ động dùng `MethodHandle`, vẫn có thể cache theo class. Ví dụ công khai `String name()`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;
import java.util.Optional;

public final class FastNameReader {
    private FastNameReader() {
    }

    private static final ClassValue<Optional<MethodHandle>> NAME_HANDLES =
            new ClassValue<>() {
                @Override
                protected Optional<MethodHandle> computeValue(Class<?> type) {
                    try {
                        MethodHandle raw = MethodHandles.publicLookup()
                                .findVirtual(type, "name",
                                        MethodType.methodType(String.class));

                        MethodHandle adapted = raw.asType(
                                MethodType.methodType(String.class, Object.class));
                        return Optional.of(adapted);
                    } catch (NoSuchMethodException missing) {
                        return Optional.empty();
                    } catch (IllegalAccessException denied) {
                        throw new IllegalStateException(
                                "Public method is not accessible: " + type,
                                denied);
                    }
                }
            };

    public static Optional<String> readName(Object target) throws Throwable {
        Objects.requireNonNull(target, "target");

        Optional<MethodHandle> found = NAME_HANDLES.get(target.getClass());
        if (found.isEmpty()) {
            return Optional.empty();
        }

        String name = (String) found.orElseThrow().invokeExact((Object) target);
        return Optional.ofNullable(name);
    }
}
```

`publicLookup()` tuân theo khả năng truy cập public và quy tắc module. `findVirtual` tìm method instance có đúng `MethodType` yêu cầu. Đoạn code chuyển handle từ receiver type cụ thể thành `(Object)String` bằng `asType`, sau đó `invokeExact` với kiểu đã thống nhất.

Với method có chữ ký khác hoặc generic adapter phức tạp, cần điều chỉnh `MethodType`. Sai signature ở điểm invoke có thể gây `WrongMethodTypeException`.

Quan trọng: method handle được tạo từ một lookup có quyền phù hợp là một capability. Nếu cache handle tới member non-public, không xuất handle đó cho code không đáng tin. Một cache nội bộ nên giữ metadata và handle theo phạm vi truy cập của thư viện.

### 13.1. Phân biệt API và chiến lược tối ưu hóa

`MethodHandle` có thể có đường invocation tối ưu khi JIT thấy handle và kiểu ổn định. Một handle lấy từ cache động qua `ClassValue.get` không mặc nhiên được JIT xem là hằng tại mọi call site.

Do đó, không khẳng định MethodHandle luôn nhanh hơn Method.invoke, hoặc ClassValue luôn nhanh hơn ConcurrentHashMap trong mọi workload. Hãy benchmark sau warmup với chuỗi class, tỷ lệ hit/miss và cách dispatch thực tế.

## 14. Reflection và ranh giới truy cập của module

Cache không được phép làm thay đổi hợp đồng truy cập. Trên JDK hiện đại, strong encapsulation của JPMS có ý nghĩa đối với thư viện reflection:

- `getMethod` thường dùng để tìm method public; việc invoke còn phải thỏa điều kiện truy cập của declaring type và module.
- `getDeclaredMethod` có thể tìm method private nhưng không tự cấp quyền invoke.
- `setAccessible(true)` không luôn thành công khi module chứa class không mở package phù hợp.
- `trySetAccessible()` trả kết quả cho biết có thể bật suppression theo quy tắc API.
- `MethodHandles.privateLookupIn` cũng phải đáp ứng các điều kiện module và quyền lookup được quy định.

Nếu muốn đọc private member để serialization hoặc dependency injection, hãy công bố yêu cầu `opens` một cách rõ ràng trong module của ứng dụng:

```java
module com.example.domain {
    opens com.example.domain.model to com.example.framework;
}
```

Ví dụ này giả định framework là một named module được nhận diện đúng. Không dùng `--add-opens` như mặc định cho thư viện chỉ vì cache không tìm được private member; quyền truy cập phải là quyết định tích hợp có chủ đích.

Một cache nên phân biệt “member không tồn tại” với “member tồn tại nhưng không được phép truy cập”. Cố gắng dùng cache để giữ handle không hợp lệ không giải quyết được vấn đề module.

## 15. Vòng đời plugin và trách nhiệm dọn tài nguyên

Một chu kỳ plugin thường có dạng:

```text
LOAD
  |
  +-- tạo loader mới
  +-- nạp class
  +-- phản chiếu metadata -> ClassValue
  +-- xử lý request
  |
STOP / UNDEPLOY
  |
  +-- dừng task, scheduler, thread và executor của plugin
  +-- hủy đăng ký callback/listener/provider
  +-- xóa reference từ registry toàn cục
  +-- dọn ThreadLocal, TCCL và tài nguyên
  +-- close URLClassLoader nếu framework sở hữu loader đó
  |
  v
Loader có thể trở nên unreachable
  |
  v
GC có thể thu hồi loader và class tương ứng
```

TCCL ở đây là **thread context class loader**. Một worker thread sống lâu giữ TCCL trỏ tới plugin loader cũng có thể giữ toàn bộ plugin. Khi thiết kế executor dùng chung, cần khôi phục TCCL sau khi chạy nhiệm vụ hoặc bảo đảm thread không giữ loader đã dừng.

Không gọi `System.gc()` làm bước cleanup chính. GC là quyết định của JVM; tính đúng đắn của plugin lifecycle cần đến từ việc dọn reference và resource.

Nếu metadata ClassValue chứa dữ liệu native, file handle hoặc callback, đặt chúng trong component có lifecycle cụ thể để đóng khi plugin stop. `ClassValue.remove` không phải công cụ quản lý tài nguyên tổng quát.

## 16. Kiểm thử danh tính với hai class loader

Một test quan trọng là nạp **cùng một binary name** qua hai loader thực sự khác nhau rồi kiểm tra ClassValue không trộn metadata.

Giả sử `pluginJar` là đường dẫn tới JAR chứa `com.example.plugin.Widget`, và class đó không được parent loader nạp trước. Mỗi `URLClassLoader` mới có parent là platform class loader:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;

import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class ClassLoaderIdentityTest {
    @Test
    void isolatesClassValuesAcrossDefiningLoaders() throws Exception {
        Path pluginJar = Path.of("build/fixtures/plugin.jar");
        URL[] urls = {pluginJar.toUri().toURL()};

        ClassValue<Object> cache = new ClassValue<>() {
            @Override
            protected Object computeValue(Class<?> type) {
                return new Object();
            }
        };

        try (URLClassLoader loaderA = new URLClassLoader(
                     urls, ClassLoader.getPlatformClassLoader());
             URLClassLoader loaderB = new URLClassLoader(
                     urls, ClassLoader.getPlatformClassLoader())) {

            Class<?> typeA = Class.forName(
                    "com.example.plugin.Widget", false, loaderA);
            Class<?> typeB = Class.forName(
                    "com.example.plugin.Widget", false, loaderB);

            assertEquals(typeA.getName(), typeB.getName());
            assertNotSame(typeA, typeB);
            assertSame(cache.get(typeA), cache.get(typeA));
            assertNotSame(cache.get(typeA), cache.get(typeB));
        }
    }
}
```

Test này **xác minh isolation giữa loader**, không xác minh rằng GC đã unload lớp. Với test tự động, chuẩn bị JAR fixture trước bằng build test; không để test phụ thuộc JAR ngẫu nhiên trong máy developer.

Lưu ý parent-first delegation: nếu parent đã định nghĩa chính lớp plugin, hai `loadClass` có thể trả về cùng Class từ parent. Test phải cấu hình hierarchy rõ ràng và xác nhận class thực tế được định nghĩa bởi loader mong đợi.

## 17. Kiểm thử cạnh tranh get/computeValue

Đối với thư viện có nhiều thread, tạo test race để khẳng định cache trả association nhất quán nhưng không áp đặt số lần `computeValue`.

Ý tưởng test:

1. Khởi tạo `ClassValue<Object>` có `computeValue` tăng `AtomicInteger`.
2. Dùng nhiều thread đồng thời gọi `get(Sample.class)` sau cùng một barrier.
3. Thu các object được trả về; xác nhận chúng là cùng giá trị đã gắn nếu không có `remove`.
4. Xác nhận `computeValue` được gọi ít nhất một lần; không assert đúng một lần.
5. Chạy test riêng để xen `remove` với `get` và chỉ assert các hợp đồng mà Javadoc bảo đảm.

Không đặt side effect ngoài JVM trong `computeValue` chỉ để đếm lần gọi. Test nên sử dụng đối tượng thuần được tạo mới.

`ClassValue` cũng cho phép `computeValue` gián tiếp gây class loading; cần tránh recursion vô hạn khi cache A trong quá trình tính lại gọi A trên cùng class. Javadoc mô tả tương tác reentrant `get`/`remove`, nhưng application code vẫn phải thiết kế tránh vòng lặp không kết thúc.

## 18. Kiểm tra class unloading mà không dựa vào GC đúng thời điểm

Class unloading không phải API đồng bộ kiểu `close()`. Vì vậy test dạng “gọi `System.gc()` một lần rồi assert loader đã bị thu hồi ngay” dễ flaky.

Một chiến lược kiểm chứng tốt hơn:

- **Unit test quyết định:** xác nhận cache phân biệt Class theo loader, trả giá trị đúng, invalidation chính xác.
- **Integration test lifecycle:** tạo plugin loader, khởi tạo cache, stop plugin, xóa toàn bộ strong references mà ứng dụng sở hữu.
- **Diagnostic test dài hơn:** dùng `WeakReference<ClassLoader>` và `ReferenceQueue<ClassLoader>` để quan sát khả năng thu hồi, nhưng không coi thời hạn GC là hợp đồng Java SE.
- **Theo dõi production/test soak:** quan sát class-loader count, class unload và metaspace sau nhiều vòng redeploy.

Ví dụ helper chỉ giữ weak reference sau khi đóng loader:

```java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;

static WeakReference<ClassLoader> loadOnce(
        URL pluginUrl, ClassValue<?> cache) throws Exception {
    try (URLClassLoader loader = new URLClassLoader(
            new URL[] {pluginUrl}, ClassLoader.getPlatformClassLoader())) {
        Class<?> type = Class.forName(
                "com.example.plugin.Widget", false, loader);

        cache.get(type); // Thực sự khởi tạo association của cache được kiểm tra.
        return new WeakReference<>(loader);
    }
}
```

Caller truyền vào một `ClassValue<?>` có `computeValue` tính metadata reflection thực tế; helper gọi `get(type)` để khởi tạo cache trước khi kết thúc vòng load. Sau khi helper trả về, tránh lưu `type`, `Method`, object plugin hoặc loader vào biến/static khác.

`weakReference.get() == null` nếu xảy ra là một quan sát; `weakReference.get() != null` tại một thời điểm không tự chứng minh leak. Cần kết hợp heap dump và reference path để xác định ai đang giữ object.

## 19. Công cụ quan sát class loader và metaspace

Có thể dùng `jcmd` để kiểm tra JVM đang chạy:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.classloaders
jcmd <pid> GC.class_histogram
```

`VM.classloader_stats` in thống kê các class loader và số lớp đang nạp. `VM.classloaders` hiển thị hierarchy. Class histogram giúp xem các đối tượng còn tồn tại; tùy JVM và tham số, việc thu thập có thể tốn thời gian hoặc gây ảnh hưởng nên chạy ở môi trường phù hợp.

Java Flight Recorder (JFR) hỗ trợ quan sát sự kiện class loading/unloading khi các event tương ứng được bật. Kết hợp JFR, JDK Mission Control và heap dump để nhìn xu hướng thay vì suy từ một snapshot.

Các dấu hiệu cần điều tra:

- Số plugin loader tăng sau mỗi lần redeploy.
- Metaspace tăng theo thời gian và không giảm dù plugin đã stop.
- Heap dump cho thấy strong path từ static cache của thư viện đến Class/Method/MethodHandle plugin.
- Thread giữ TCCL trỏ về loader đã stop.
- Thư viện đang giữ callback, annotation proxy hoặc instance plugin trong global registry.

`ClassValue` có thể loại bỏ một đường giữ loader nhưng không chữa được các đường giữ khác.

## 20. Benchmark cache reflection đúng cách

Đối với hiệu năng, tránh dùng `System.nanoTime()` trong một vòng lặp ngắn làm kết luận về cache. Dùng JMH hoặc harness phù hợp, tách các pha:

- Lookup cold cache, tính metadata lần đầu.
- Cache hit sau warmup.
- Repeated `Method.invoke` với handle đã chuẩn bị.
- Repeated `MethodHandle.invokeExact` với signature ổn định.
- Workload nhiều class/loader, bao gồm class churn.
- Memory và tỷ lệ thu hồi sau chu kỳ load/unload.

Ghi rõ JDK vendor/version, JVM arguments, số thread, fork, warmup, GC và tỷ lệ cache hit/miss. Đừng để benchmark vô tình đo việc tạo class, disk I/O hoặc log thay vì đo cache.

JEP 416 cho phép phần triển khai reflection hưởng lợi từ cơ chế method handles, nhưng không tạo cam kết rằng mọi trường hợp sẽ nhanh hơn theo cùng một hệ số. Quyết định giữ cache nên dựa vào kết quả trên JDK và workload mục tiêu.

## 21. Checklist thiết kế cache reflection cho thư viện

- [ ] Khóa cache phân biệt danh tính `Class`, không chỉ dựa vào `getName()`.
- [ ] Cache dùng chung không giữ `Map<Class<?>, ...>` tĩnh nếu không có kế hoạch cleanup.
- [ ] Xem xét `ClassValue` cho metadata xác định theo `Class`.
- [ ] `computeValue` thuần/idempotent, chịu được việc chạy nhiều lần khi race.
- [ ] Negative lookup chỉ cache các trường hợp thực sự ổn định.
- [ ] Exception về quyền truy cập được phân biệt với “không tìm thấy member”.
- [ ] Không tự bật `setAccessible(true)` nếu chưa có yêu cầu và quyền truy cập hợp lệ.
- [ ] Kiểm tra public/exported module hoặc thiết kế `opens` rõ ràng khi cần private access.
- [ ] Có chính sách `remove(type)` khi metadata phụ thuộc trạng thái thay đổi.
- [ ] Value không giữ file handle, thread hoặc callback không có lifecycle rõ ràng.
- [ ] Tránh global registry giữ Method/MethodHandle/Class của plugin.
- [ ] Khi plugin stop, dọn listener, thread, executor, TCCL và resource.
- [ ] Test hai loader khác nhau nạp cùng binary name.
- [ ] Test concurrent `get` không giả định `computeValue` đúng một lần.
- [ ] Không assert class unloading diễn ra ngay sau `System.gc()`.
- [ ] Đo hiệu năng và memory trên workload thực tế.

## 22. Những nhận định dễ nhầm

- **“Hai class cùng tên luôn dùng chung metadata.”** Sai. Defining loader là một phần danh tính type; mỗi Class phải được xử lý riêng.
- **“ConcurrentHashMap<Class, Method> tĩnh là an toàn vì thread-safe.”** Thread-safe không đồng nghĩa lifecycle-safe; strong keys có thể giữ loader.
- **“WeakHashMap<Class, Method> luôn tránh leak.”** Không chắc. Value có thể tham chiếu ngược đến Class và giữ key reachable.
- **“ClassValue đảm bảo computeValue đúng một lần.”** Sai. Dưới race, compute có thể được gọi nhiều lần.
- **“ClassValue.remove() unload class.”** Sai. Nó xóa association của ClassValue, không ép JVM unload hoặc thu hồi loader.
- **“ClassValue tự đóng tài nguyên trong value.”** Sai. Cần quản lý lifecycle tài nguyên riêng.
- **“Nếu dùng ClassValue thì loader không thể leak.”** Sai. Leak vẫn có thể đến từ thread, TCCL, callback hoặc map khác.
- **“ClassValue có clear-all để xóa mọi lớp.”** Sai. API không cung cấp enumerate/clear-all công khai.
- **“MethodHandle luôn nhanh hơn reflection.”** Không được bảo đảm. JIT, call site và workload quyết định; JEP 416 cũng thay đổi implementation của core reflection.
- **“Đổi từ map sang ClassValue là đủ để cache private member.”** Sai. Cache không thay quyền truy cập hoặc ranh giới module.
- **“Gọi URLClassLoader.close() là unload ngay.”** Sai. Close không bảo đảm loader hay class được GC tức thời.
- **“Không thấy loader GC sau một lần System.gc() chứng minh leak.”** Sai. GC và class unloading không có deadline do ứng dụng quyết định.

## 23. Tài liệu tham khảo chính thức

- [ClassValue — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassValue.html): contract của `get`, `computeValue`, `remove`, race và reentrant access.
- [ClassLoader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): class loader, delegation và quan hệ với Class.
- [Java Language Specification §12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.7): điều kiện class unloading liên quan defining loader.
- [MethodHandles.Lookup — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access checks và tạo method handles.
- [Method — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Method.html): lookup, invoke và xử lý ngoại lệ reflection.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai core reflection từ Java 18.
- [The jcmd Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): `VM.classloader_stats`, `VM.classloaders` và diagnostic commands.
- [JDK 18 Release Notes — JEP 416](https://www.oracle.com/java/technologies/javase/18-relnote-issues.html): thay đổi implementation reflection ở Java 18 và phạm vi tương thích.

