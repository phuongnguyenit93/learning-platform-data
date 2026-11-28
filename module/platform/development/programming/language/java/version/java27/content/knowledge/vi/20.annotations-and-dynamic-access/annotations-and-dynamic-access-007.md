# Dynamic proxy và thiết kế điểm mở rộng có kiểm soát trong Java 27

Trong ứng dụng lớn, cùng một lời gọi phương thức có thể cần thêm những hành vi dùng chung như đo thời gian thực thi, ghi nhận chỉ số vận hành, kiểm tra quyền, kiểm soát giao dịch hoặc định tuyến đến một implementation khác. Viết lặp lại các bước này vào mọi lớp nghiệp vụ làm tăng độ phức tạp. Một lựa chọn là **dynamic proxy**: chương trình tạo một đối tượng thực thi interface tại runtime, rồi chuyển các lời gọi phương thức đến một bộ xử lý trung gian.

Trong **Java 27**, cơ chế dynamic proxy chuẩn của JDK nằm trong `java.lang.reflect` với `Proxy` và `InvocationHandler`. Đây là API ổn định, vẫn phù hợp với các thư viện, adapter, instrumentation và những điểm mở rộng có hợp đồng interface. Tuy nhiên, dynamic proxy **không tự cấp quyền**, **không tự bảo vệ tài nguyên** và **không thay thế một chính sách bảo mật**. Tính linh hoạt cần đi cùng giới hạn rõ ràng về loại interface được chấp nhận, phương thức được gọi, dữ liệu đầu vào và vòng đời đối tượng.

Bài học thuộc chương **Annotation và truy cập động**, sử dụng **chỉ các API còn hiện hành của Java 27**. Các ví dụ chú trọng giao diện có kiểu tĩnh, annotation có retention phù hợp, tránh mở quyền reflection tùy ý và không dựa vào API đã deprecated.

Tài liệu chính thức:

- [Java SE 27 — Proxy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Proxy.html).
- [Java SE 27 — InvocationHandler](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/InvocationHandler.html).
- [Java SE 27 — Method](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html).
- [Java SE 27 — ServiceLoader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ServiceLoader.html).

## 1. Dynamic proxy là gì?

**JDK dynamic proxy** là một đối tượng được tạo trong lúc chạy, có lớp được JDK sinh ra để **triển khai một hoặc nhiều interface**. Khi bên gọi thực hiện một phương thức được proxy triển khai, JVM chuyển lời gọi đó vào `InvocationHandler.invoke(...)`. Handler quyết định:

1. Có chấp nhận lời gọi không?
2. Có cần đo thời gian, kiểm tra hợp đồng hoặc ghi chỉ số không?
3. Có chuyển lời gọi đến một đối tượng đích (*target/delegate*) hay xử lý theo cách khác?
4. Trả giá trị gì hoặc ném exception nào cho bên gọi?

Sơ đồ:

~~~~text
             Biến có kiểu interface
                       |
                       v
                Proxy instance
                       |
       Method + args + proxy instance
                       |
                       v
           InvocationHandler.invoke()
                 /     |      \
           kiểm tra  đo đạc   từ chối
                 \     /
             delegate / xử lý riêng
                       |
               kết quả / exception
                       |
                       v
                  Bên gọi
~~~~

Lớp proxy do JDK tạo là **`final`**, kế thừa `java.lang.reflect.Proxy` và triển khai những interface đã chỉ định. Nó **không kế thừa lớp target**. Một proxy được tạo cho `PaymentService` có thể truyền vào nơi cần `PaymentService`, nhưng không được xem là instance của một implementation cụ thể chỉ vì đang ủy quyền đến implementation đó.

### 1.1. Khi nào nên dùng dynamic proxy?

| Tình huống | Dynamic proxy phù hợp? | Lý do |
| --- | --- | --- |
| Bổ sung phép đo và log cho nhiều method của interface | Có | Tập trung logic dùng chung trong handler |
| Thực thi một interface bằng lời gọi RPC | Có thể | Handler chuyển lời gọi thành request theo một hợp đồng rõ |
| Kiểm soát phương thức của một interface được công bố | Có thể | Handler chặn phương thức không cho phép, nhưng cần bảo vệ mọi đường truy cập khác |
| Tạo object thay thế trong kiểm thử | Có thể | Cho phép mô phỏng hành vi interface |
| Mở rộng lớp không có interface | **Không**, JDK proxy không kế thừa class tùy ý | Dùng adapter/decorator hoặc thiết kế interface |
| Triển khai `sealed interface` | **Không** | Java 27 yêu cầu interface proxy **non-sealed** |
| Chỉ bọc một implementation và vài phương thức cố định | Cân nhắc decorator viết tay | Dễ đọc, kiểm tra tĩnh và thường đơn giản hơn |
| Nạp plugin do bên thứ ba viết | Dynamic proxy không phải bộ nạp plugin | Cân nhắc `ServiceLoader` cùng chính sách tin cậy |

Dynamic proxy là kỹ thuật **định tuyến lời gọi theo interface**, không phải cách truy cập tùy ý mọi đối tượng hay cơ chế plugin hoàn chỉnh.

## 2. Ba API cốt lõi

| API | Chức năng |
| --- | --- |
| `Proxy.newProxyInstance(ClassLoader, Class<?>[], InvocationHandler)` | Tạo proxy instance triển khai các interface hợp lệ |
| `InvocationHandler.invoke(Object proxy, Method method, Object[] args)` | Xử lý mỗi lời gọi được chuyển đến proxy |
| `Method` | Mô tả phương thức được gọi: tên, tham số, kiểu trả về, annotation, exception... |

Thêm vào đó:

- `Proxy.isProxyClass(Class<?>)`: xác minh class có phải lớp proxy do cơ chế JDK tạo không.
- `Proxy.getInvocationHandler(Object)`: lấy handler của một proxy instance; chỉ thực hiện khi có chủ đích.
- `InvocationHandler.invokeDefault(...)`: gọi implementation `default` của một proxy interface.

**Không dùng `Proxy.getProxyClass(...)` để tạo proxy mới.** Phương thức này đã được đánh dấu **deprecated** trong Java 27; API khuyến nghị tạo instance trực tiếp qua `Proxy.newProxyInstance(...)`. Bỏ qua đường đi lấy constructor lớp proxy rồi cố `newInstance` thông qua reflection.

### 2.1. Tạo proxy đơn giản

~~~~java
import java.lang.reflect.Proxy;

interface Greeter {
    String greet(String name);
}

public class HelloProxyDemo {
    public static void main(String[] args) {
        Greeter greeter = (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[] { Greeter.class },
                (proxy, method, arguments) -> {
                    if (method.getName().equals("greet")) {
                        return "Xin chào " + arguments[0];
                    }
                    throw new UnsupportedOperationException(method.getName());
                });

        System.out.println(greeter.greet("Java")); // Xin chào Java
    }
}
~~~~

Ví dụ này dành cho interface chỉ có một phương thức nghiệp vụ. **Nó chưa hoàn chỉnh cho production**, vì các lời gọi `equals`, `hashCode`, `toString` cũng đến handler, còn ví dụ mới chỉ xử lý `greet`. Phần sau sẽ cung cấp cách xây dựng handler đầy đủ hơn.

### 2.2. `ClassLoader` có vai trò gì?

Tham số đầu của `newProxyInstance` là class loader được dùng để định nghĩa và liên kết lớp proxy. Một lựa chọn hợp lý khi proxy một interface cụ thể là:

~~~~java
ClassLoader loader = Greeter.class.getClassLoader();
~~~~

Lớp proxy phải nhìn thấy các interface qua class loader đó, cùng các kiểu xuất hiện trong public method signatures theo yêu cầu JDK. Không thể chọn một loader bất kỳ rồi mặc định nó nhìn thấy toàn bộ các module/class trong ứng dụng.

Với hệ thống plugin và module lớn, class loader là một phần của **biên kiến trúc**. Thiết kế đúng yêu cầu nêu rõ interface nào có thể được proxy, do loader nào định nghĩa, và target đến từ nguồn nào.

## 3. Ví dụ hoàn chỉnh: proxy chỉ đo những phương thức được đánh dấu

Ví dụ dưới đây kết hợp **annotation** và **dynamic proxy**: một interface công bố phương thức nào được đo thời gian bằng `@Timed`. Proxy chỉ đo các lời gọi mang annotation đó và ủy quyền nghiệp vụ đến implementation thật.

Đặc biệt, ví dụ xử lý đúng **default method**, các phương thức `Object` và exception của lời gọi reflection.

Lưu thành `DynamicProxyDemo.java`:

~~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.Locale;
import java.util.Objects;

public class DynamicProxyDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface Timed {
    }

    public interface AccountLookup {
        @Timed
        String lookup(String accountId);

        default String lookupNormalized(String rawAccountId) {
            Objects.requireNonNull(rawAccountId, "rawAccountId");
            return lookup(rawAccountId.strip());
        }
    }

    public static final class AccountLookupImpl implements AccountLookup {
        @Override
        public String lookup(String accountId) {
            Objects.requireNonNull(accountId, "accountId");
            if (accountId.isBlank()) {
                throw new IllegalArgumentException("accountId is blank");
            }
            return "account:" + accountId.toUpperCase(Locale.ROOT);
        }
    }

    public static <T> T instrument(Class<T> contract, T target) {
        Objects.requireNonNull(contract, "contract");
        Objects.requireNonNull(target, "target");

        if (!contract.isInterface() || contract.isSealed()) {
            throw new IllegalArgumentException(
                    "Contract must be a non-sealed interface");
        }
        if (!contract.isInstance(target)) {
            throw new IllegalArgumentException(
                    "Target must implement the contract");
        }

        InvocationHandler handler = (proxy, method, args) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == args[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" ->
                            "Proxy<" + contract.getSimpleName() + ">";
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            boolean timed = method.isAnnotationPresent(Timed.class);
            long started = timed ? System.nanoTime() : 0L;

            try {
                if (method.isDefault()) {
                    // Gọi default body với this là chính proxy.
                    return InvocationHandler.invokeDefault(
                            proxy, method, args);
                }

                try {
                    return method.invoke(target, args);
                } catch (InvocationTargetException exception) {
                    // Trả lại exception gốc từ target.
                    throw exception.getCause();
                }
            } finally {
                if (timed) {
                    System.out.printf(
                            "Timed %s: %d ns%n",
                            method.getName(),
                            System.nanoTime() - started);
                }
            }
        };

        Object candidate = Proxy.newProxyInstance(
                contract.getClassLoader(),
                new Class<?>[] { contract },
                handler);

        return contract.cast(candidate);
    }

    public static void main(String[] args) {
        AccountLookup target = new AccountLookupImpl();
        AccountLookup client = instrument(AccountLookup.class, target);

        System.out.println(client.lookup("ab-12"));
        // Timed lookup: <thời gian> ns
        // account:AB-12

        System.out.println(client.lookupNormalized("  cd-34  "));
        // Timed lookup: <thời gian> ns
        // account:CD-34

        System.out.println(client.equals(client)); // true
        System.out.println(client.toString());      // Proxy<AccountLookup>
        System.out.println(Proxy.isProxyClass(client.getClass())); // true
    }
}
~~~~

### 3.1. Giải thích từng thành phần

1. `@Retention(RetentionPolicy.RUNTIME)` giữ metadata của `@Timed` để reflection đọc được trong quá trình chạy.
2. `@Target(ElementType.METHOD)` giới hạn vị trí sử dụng annotation vào phương thức.
3. `AccountLookup` là **interface công khai của hợp đồng**. `AccountLookupImpl` là đối tượng thực thi nghiệp vụ.
4. `instrument(Class<T>, T)` kiểm tra hợp đồng là interface không sealed và target đúng kiểu trước khi tạo proxy.
5. Handler nhận `Method` tương ứng phương thức được gọi. `method.isAnnotationPresent(Timed.class)` quyết định có đo thời gian không.
6. `method.invoke(target, args)` ủy quyền đến target. Nếu target ném exception, reflection bọc nó trong `InvocationTargetException`; handler mở bọc bằng `getCause()`.
7. `method.isDefault()` được xử lý riêng bằng `InvocationHandler.invokeDefault` để default method chạy với `this` là proxy. Khi `lookupNormalized` gọi `lookup`, lời gọi tiếp tục bị handler chặn và đo.
8. `equals`, `hashCode`, `toString` có chính sách thống nhất theo **identity** của proxy; không gọi các phương thức đó trên chính proxy từ trong handler.

### 3.2. Điều ví dụ chưa cam kết

Ví dụ đo thời gian mang mục đích **quan sát kỹ thuật**. Nó không phải hệ thống audit nghiệp vụ đáng tin cậy, không lưu bản ghi bảo đảm bền vững và không che mọi đường gọi trực tiếp vào target.

Nếu cùng một target còn được sử dụng qua một biến khác, lời gọi qua biến đó **bỏ qua proxy**. Nếu cần áp đặt chính sách bắt buộc, phải thiết kế sao cho mọi đường đi đến tài nguyên đều được kiểm soát ở chính tầng sở hữu tài nguyên, không chỉ qua wrapper.

Việc in `System.nanoTime()` trong ví dụ chỉ minh họa thời lượng. Trong hệ thống thật, nên dùng metrics/tracing theo quy ước chung, không ghi tham số nhạy cảm hoặc dữ liệu phản hồi vào log theo thói quen.

## 4. Hợp đồng chi tiết của `InvocationHandler.invoke`

Phương thức của handler có chữ ký:

~~~~java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
~~~~

| Đối số | Ý nghĩa | Trường hợp dễ sai |
| --- | --- | --- |
| `proxy` | Chính proxy instance đang được gọi | Gọi lại cùng phương thức trên `proxy` có thể tạo đệ quy vô hạn |
| `method` | Metadata của phương thức đã được dispatch | Có thể đến từ interface cha hoặc `Object`, không nhất thiết từ interface trực tiếp |
| `args` | Tham số của lời gọi, các primitive được boxed | Có thể là **`null` khi phương thức không có tham số** |

Handler trả về một `Object`, còn proxy tự chuyển về kiểu trả về đã khai báo của phương thức.

### 4.1. Tham số không có đối số: `args == null`

~~~~java
interface StatusReader {
    String currentStatus();
}

// Khi client.currentStatus() được gọi:
// method.getName() == "currentStatus"
// args có thể là null (không phải Object[0]).
~~~~

Trong handler tổng quát, nếu cần xem các tham số và muốn tránh null:

~~~~java
Object[] actualArguments =
        args == null ? new Object[0] : args;
~~~~

Đừng tự thay `args` bằng mảng mới và lưu lại nó trong trạng thái dùng chung rồi cho rằng các phần tử tham chiếu đã được sao chép sâu. Đây chỉ là mảng chứa tham chiếu đến những argument object được truyền vào.

### 4.2. Primitive được boxed và unboxed

Nếu interface có:

~~~~java
interface Counter {
    int count();
    boolean enabled();
}
~~~~

Handler phải trả `Integer` cho `count()` và `Boolean` cho `enabled()`. Java sẽ unbox chúng để giao cho caller:

~~~~java
Counter counter = (Counter) Proxy.newProxyInstance(
        Counter.class.getClassLoader(),
        new Class<?>[] { Counter.class },
        (proxy, method, args) -> switch (method.getName()) {
            case "count" -> Integer.valueOf(42);
            case "enabled" -> Boolean.TRUE;
            default -> throw new UnsupportedOperationException();
        });

System.out.println(counter.count());   // 42
System.out.println(counter.enabled()); // true
~~~~

Nếu phương thức trả primitive mà handler trả `null`, việc gọi qua proxy sẽ ném `NullPointerException`. Nếu trả object không tương thích với kiểu trả về, có thể gặp `ClassCastException`. Khi xây dựng handler chung, phải bảo toàn hợp đồng **kiểu trả về**, không chỉ tên phương thức.

### 4.3. `equals`, `hashCode` và `toString` đều đi qua handler

Một khác biệt quan trọng so với nhiều proxy tự viết: JDK dynamic proxy chuyển **ba phương thức public từ `Object`** dưới đây vào `InvocationHandler.invoke`:

- `boolean equals(Object other)`
- `int hashCode()`
- `String toString()`

`method.getDeclaringClass()` trong những lời gọi đó là `Object.class`, ngay cả khi interface proxy cũng khai báo một phương thức có signature tương ứng.

Ví dụ áp dụng **identity semantics**:

~~~~java
if (method.getDeclaringClass() == Object.class) {
    return switch (method.getName()) {
        case "equals" -> proxy == args[0];
        case "hashCode" -> System.identityHashCode(proxy);
        case "toString" -> "Proxy<" + contract.getSimpleName() + ">";
        default -> throw new UnsupportedOperationException();
    };
}
~~~~

Chính sách này bảo toàn quan hệ `equals/hashCode`: hai biến cùng chỉ một instance proxy là bằng nhau và có cùng hash. Một proxy khác được tạo riêng sẽ không bằng, dù cùng target.

**Không gọi `proxy.toString()` trong nhánh xử lý `toString`**, không gọi `proxy.equals(...)` trong nhánh `equals`, và không gọi `method.invoke(proxy, args)` để “ủy quyền” cho chính proxy. Các cách đó có thể quay lại handler lặp vô hạn.

Nếu nghiệp vụ muốn proxy bằng nhau dựa trên **identity của target** hoặc một khóa miền, cần thiết kế cả `equals` và `hashCode` nhất quán, xác định xử lý proxy khác loại và trường hợp target mutable. Không tự mặc định proxy có ngữ nghĩa bằng nhau giống đối tượng được bọc.

### 4.4. Phương thức `default` không tự động gọi thân default

Một interface có thể có phương thức `default`:

~~~~java
interface PriceFormatter {
    String formatRaw(int cents);

    default String formatForDisplay(int cents) {
        return "Giá: " + formatRaw(cents);
    }
}
~~~~

Khi gọi `formatForDisplay` trên dynamic proxy, **handler vẫn được gọi**. Để thực thi thân default thực sự, sử dụng:

~~~~java
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(proxy, method, args);
}
~~~~

`InvocationHandler.invokeDefault` mô phỏng lời gọi đến thân default trên interface tương ứng. Một lời gọi tới phương thức interface khác từ trong thân default có thể tiếp tục được dispatch qua proxy, đúng như ví dụ `lookupNormalized` ở trên.

Không nhầm với `method.invoke(proxy, args)`: gọi qua reflection lên **proxy** có thể quay lại handler của chính phương thức ấy, tạo đệ quy. Cũng không buộc mọi default method phải chạy; handler có thể từ chối hoặc cung cấp hành vi khác theo chính sách.

**Ràng buộc quan trọng:** `invokeDefault` chỉ nhận default method hợp lệ từ một proxy interface hoặc superinterface được kế thừa phù hợp. Nếu một interface con override method và không còn kế thừa phiên bản default cũ, việc cố gọi Method đại diện cho bản cũ có thể tạo `IllegalArgumentException`.

### 4.5. Các phương thức có cùng chữ ký trong nhiều interface

Nếu proxy triển khai nhiều interface đều có phương thức tên và tham số giống nhau, handler không nhất thiết được biết **bên gọi đã ép kiểu qua interface nào**:

~~~~java
interface First {
    String name();
}

interface Second {
    String name();
}

Object proxy = Proxy.newProxyInstance(
        First.class.getClassLoader(),
        new Class<?>[] { First.class, Second.class },
        (instance, method, args) -> method.getDeclaringClass().getSimpleName());

System.out.println(((First) proxy).name());  // First
System.out.println(((Second) proxy).name()); // First
~~~~

Lý do: khi các interface có phương thức **trùng tên và danh sách tham số**, JDK chọn đối tượng `Method` từ interface xuất hiện sớm nhất trong danh sách có method đó, bất kể kiểu tham chiếu dùng để gọi. Trường hợp interface kế thừa và return type covariant còn có các quy tắc tương thích bổ sung.

Thiết kế handler **không được dựa** vào việc cùng một signature sẽ gửi hai Method khác nhau tùy cách client ép kiểu. Nếu hai interface cần hành vi khác nhau, hãy đổi tên/chữ ký hợp đồng hoặc tổ chức điểm mở rộng tách biệt.

## 5. Exception và hợp đồng của proxy

Reflection tạo thêm một lớp exception dễ khiến người viết handler nhầm lẫn.

### 5.1. `InvocationTargetException` là lớp bọc, không phải lỗi nghiệp vụ gốc

Khi handler gọi:

~~~~java
Object result = method.invoke(target, args);
~~~~

Nếu chính phương thức của target ném exception, `Method.invoke` thường bọc exception đó trong `InvocationTargetException`. Nếu cứ để wrapper này đi ra, caller có thể nhận `UndeclaredThrowableException` thay vì lỗi nghiệp vụ đã công bố.

Hướng xử lý:

~~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException exception) {
    throw exception.getCause();
}
~~~~

`InvocationHandler.invoke` được phép khai báo `throws Throwable`, nên có thể ném lại cause gốc. Tuy nhiên, **proxy interface vẫn quyết định checked exception nào được phép đi qua**.

### 5.2. Checked exception không được interface khai báo

Giả sử interface không khai báo một checked exception nhưng handler cố ném `IOException`:

~~~~java
import java.io.IOException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;

interface Task {
    void run();
}

public class UndeclaredExceptionDemo {
    public static void main(String[] args) {
        Task task = (Task) Proxy.newProxyInstance(
                Task.class.getClassLoader(),
                new Class<?>[] { Task.class },
                (proxy, method, arguments) -> {
                    throw new IOException("I/O failure");
                });

        try {
            task.run();
        } catch (UndeclaredThrowableException exception) {
            System.out.println(
                    exception.getCause() instanceof IOException);
            // true
        }
    }
}
~~~~

`UndeclaredThrowableException` là unchecked exception xuất hiện khi handler ném **checked exception không tương thích với `throws` của phương thức interface**. Đó không phải là cơ chế miễn trách nhiệm về khai báo exception: client có thể khó xử lý lỗi hơn nếu hệ thống lạm dụng nó.

Với một lỗi I/O được dự kiến là một phần hợp đồng:

~~~~java
import java.io.IOException;

interface FileLookup {
    String read(String path) throws IOException;
}
~~~~

Khi target ném `IOException` và handler bỏ lớp bọc `InvocationTargetException`, caller có thể nhận `IOException` trực tiếp vì interface đã khai báo đúng checked exception.

Nếu một method signature có trong **nhiều proxy interface** nhưng các `throws` không giống nhau, loại checked exception được handler ném cần tương thích với những khai báo tương ứng của các method trùng chữ ký. Một `Method.getExceptionTypes()` đơn lẻ có thể không mô tả hết ràng buộc từ các interface còn lại.

### 5.3. Những lỗi khác cần phân biệt

| Exception hoặc tình huống | Nguyên nhân có thể |
| --- | --- |
| `IllegalArgumentException` từ `newProxyInstance` | Interface không hợp lệ, interface sealed/hidden, trùng interface, class loader không nhìn thấy hoặc return type xung đột |
| `NullPointerException` từ `newProxyInstance` | Mảng interface, phần tử interface hoặc handler null |
| `IllegalAccessException` từ `Method.invoke` | Vi phạm quy tắc truy cập đến member/target |
| `InvocationTargetException` từ `Method.invoke` | Method của target ném exception, đã được reflection bọc |
| `UndeclaredThrowableException` qua proxy | Handler ném checked exception không nằm trong hợp đồng `throws` |
| `ClassCastException` ở caller | Handler trả giá trị không tương thích với kiểu trả về |
| `NullPointerException` khi return primitive | Handler trả null cho phương thức trả primitive |
| `StackOverflowError` | Handler vô tình gọi lại phương thức trên chính proxy |

Không dùng `catch (Exception)` bao trùm mọi lỗi rồi trả một giá trị thành công giả. Với một điểm mở rộng động, cần thông báo lỗi đủ rõ để caller xử lý và không che dấu lỗi truy cập hoặc sai hợp đồng.

## 6. Annotation nên mô tả chính sách, không thay thế chính sách

Annotation là **metadata**, không tự thực thi kiểm tra quyền hay thực hiện phép đo. Handler hoặc framework phải chủ động đọc và áp dụng chúng.

Ví dụ:

~~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Measured {
}

interface CatalogService {
    @Measured
    String lookup(String sku);

    void refresh();
}
~~~~

Handler có thể dùng:

~~~~java
boolean shouldMeasure =
        method.isAnnotationPresent(Measured.class);
~~~~

Chính sách được thực thi là: **chỉ đo các phương thức của interface có `@Measured` tại runtime**. Điều này giảm phụ thuộc vào tên method và cho phép compiler kiểm tra vị trí dùng annotation.

### 6.1. Vì sao cần `RUNTIME` retention?

| Retention | Có thể đọc bằng reflection ở runtime? | Tình huống |
| --- | --- | --- |
| `SOURCE` | Không | Gợi ý cho compiler, công cụ phân tích mã nguồn |
| `CLASS` | Không được bảo đảm để đọc qua reflection ở runtime | Metadata giữ trong file class, không mặc định runtime-visible |
| `RUNTIME` | Có | Handler cần `getAnnotation` / `isAnnotationPresent` |

Nếu bỏ `@Retention`, annotation mặc định là `RetentionPolicy.CLASS`. Với bộ xử lý dựa trên `Method.isAnnotationPresent(...)`, điều này có thể khiến mọi lời gọi trông như “không có annotation”.

### 6.2. Annotation đặt trên interface hay implementation?

Trong proxy JDK, `Method` được chuyển đến handler thường đại diện cho phương thức của **proxy interface hoặc superinterface**, chứ không phải Method trực tiếp của class target.

~~~~java
interface PaymentPort {
    void pay();
}

final class PaymentPortImpl implements PaymentPort {
    @Measured
    @Override
    public void pay() {
    }
}
~~~~

Handler gọi:

~~~~java
method.isAnnotationPresent(Measured.class)
~~~~

với Method từ `PaymentPort` có thể trả **false** vì annotation chỉ đặt trên `PaymentPortImpl.pay`. Annotation ở method của implementation **không tự động được truyền sang method tương ứng của interface**.

Chọn một quy ước thiết kế rõ ràng:

- **Hợp đồng do interface quản lý:** đặt annotation trên interface method và chỉ đọc từ `Method` do proxy cung cấp.
- **Hợp đồng do implementation quản lý:** tra cứu method tương ứng trên target theo **tên cùng kiểu tham số**, rồi đọc annotation ở implementation, nhưng phải xử lý overload, bridge method, quyền truy cập và metadata.

Đối với điểm mở rộng dùng chung, annotation trên **interface** thường đơn giản và minh bạch hơn vì chính interface là hợp đồng mà client nhìn thấy.

**Lưu ý:** `@Inherited` chỉ có quy tắc kế thừa đặc biệt cho annotation trên **class**, không khiến annotation của một method trên interface tự động “chảy” tới method cùng tên trên implementation.

### 6.3. Chọn metadata ổn định

Đừng dùng `method.getName().startsWith("read")` làm chính sách phân quyền. Một phương thức như `readAndDelete` có thể lọt qua kiểm tra tên bắt đầu bằng `read`. Khi dùng metadata để điều khiển hành vi quan trọng, hãy biểu diễn quyền bằng annotation có định nghĩa chính xác hoặc một whitelist các đối tượng `Method` được phê duyệt.

Annotation cũng không tự ràng buộc giá trị được truyền vào phương thức. Với `@Allowed` hoặc `@ReadOnly`, handler vẫn cần validation đầu vào và bảo vệ **mọi đường truy cập tới tài nguyên** nếu mục tiêu là phân quyền.

## 7. Thiết kế điểm mở rộng có kiểm soát bằng allowlist

Một interface có thể công bố cả thao tác đọc và ghi, nhưng một khu vực của hệ thống chỉ muốn cho phép thao tác đọc. Một dynamic proxy có thể đóng vai trò **adapter giới hạn phương thức** trên một đường gọi đã xác định.

Hãy bắt đầu bằng nguyên tắc **deny by default**: chỉ những method được liệt kê tường minh mới được ủy quyền tới target.

### 7.1. Ví dụ đầy đủ: wrapper chỉ cho phép đọc

Chương trình `ReadOnlyProxyDemo.java`:

~~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ReadOnlyProxyDemo {
    public interface DocumentPort {
        String read(String documentId);
        void delete(String documentId);
    }

    public static final class DocumentStore implements DocumentPort {
        private final Map<String, String> documents = new HashMap<>(
                Map.of("DOC-1", "Nội dung tài liệu"));

        @Override
        public String read(String documentId) {
            return documents.get(documentId);
        }

        @Override
        public void delete(String documentId) {
            documents.remove(documentId);
        }
    }

    public static DocumentPort readOnly(DocumentPort target)
            throws NoSuchMethodException {
        Objects.requireNonNull(target, "target");

        // Chọn theo toàn bộ chữ ký, không chỉ theo tên "read".
        Set<Method> allowedMethods = Set.of(
                DocumentPort.class.getMethod("read", String.class));

        InvocationHandler handler = (proxy, method, arguments) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == arguments[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "ReadOnlyDocumentPort";
                    default -> throw new UnsupportedOperationException();
                };
            }

            if (!allowedMethods.contains(method)) {
                throw new UnsupportedOperationException(
                        "Operation not exposed: " + method.getName());
            }

            // Kiểm tra đầu vào ở ranh giới proxy theo hợp đồng.
            String documentId = (String) arguments[0];
            if (documentId == null || documentId.isBlank()) {
                throw new IllegalArgumentException(
                        "documentId is required");
            }

            try {
                return method.invoke(target, arguments);
            } catch (InvocationTargetException exception) {
                throw exception.getCause();
            }
        };

        return (DocumentPort) Proxy.newProxyInstance(
                DocumentPort.class.getClassLoader(),
                new Class<?>[] { DocumentPort.class },
                handler);
    }

    public static void main(String[] args) throws NoSuchMethodException {
        DocumentPort port = readOnly(new DocumentStore());

        System.out.println(port.read("DOC-1"));
        // Nội dung tài liệu

        try {
            port.delete("DOC-1");
        } catch (UnsupportedOperationException exception) {
            System.out.println("Blocked: " + exception.getMessage());
            // Blocked: Operation not exposed: delete
        }

        System.out.println(port.read("DOC-1"));
        // Nội dung tài liệu vẫn tồn tại.
    }
}
~~~~

**Vì sao allowlist dùng `Set<Method>`?** Nếu chỉ so tên `read`, một overload `read(String, boolean)` hoặc method mới `read(String, String)` có thể lọt qua một logic kiểm tra quá rộng. So `Method` theo chữ ký cụ thể giúp danh sách cấp phép khớp chính xác với hợp đồng được dự kiến.

**Giới hạn của ví dụ:**

- Caller nhận proxy qua `readOnly` không thể gọi `delete` thành công **qua proxy này**.
- Nếu caller giữ tham chiếu đến `DocumentStore` thật, họ vẫn có thể gọi `delete` trực tiếp.
- `DocumentStore` sử dụng `HashMap` và không được thiết kế cho truy cập đồng thời; proxy không tự sửa được điều đó.
- Dùng `UnsupportedOperationException` ở đây để minh họa thao tác không được công bố. Trong API có phân quyền thật, có thể chọn exception miền phù hợp và chuyển thành mã lỗi chính sách nhất quán.

Vì thế, dynamic proxy hỗ trợ giới hạn **bề mặt API mà một client cụ thể nhìn thấy**, nhưng không trở thành một **security boundary** chỉ nhờ chặn method. Quyền truy cập phải được thực thi tại tầng sở hữu tài nguyên hoặc dịch vụ đáng tin.

### 7.2. Thiết kế interface nhỏ thường tốt hơn một proxy “chặn bớt”

Một phương án mang tính kiểu tĩnh rõ hơn là **tách quyền đọc và quyền ghi thành hai interface**:

~~~~java
interface DocumentReader {
    String read(String documentId);
}

interface DocumentWriter {
    void delete(String documentId);
}

final class DocumentRepository
        implements DocumentReader, DocumentWriter {
    @Override
    public String read(String documentId) {
        return "content for " + documentId;
    }

    @Override
    public void delete(String documentId) {
        // Thao tác ghi do implementation thực thi.
    }
}
~~~~

Client chỉ nhận `DocumentReader` không có phương thức `delete` trong hợp đồng **biên dịch**. Việc tách interface thường đơn giản và chắc chắn hơn việc tạo proxy để từ chối phần lớn API của một interface quá rộng.

Tuy nhiên, nếu client không đáng tin, việc giới hạn kiểu tham chiếu vẫn **không tự bảo vệ quyền** ở runtime; code có thể giữ hoặc lấy được tham chiếu đến object khác. Mô hình quyền thực sự phải có xác thực, kiểm tra quyền và bảo vệ tài nguyên ở phía được tin cậy.

### 7.3. Không mở điểm mở rộng bằng tên class nhập từ người dùng

Phản ví dụ thiết kế:

~~~~java
// KHÔNG nên dùng một class name không tin cậy làm lựa chọn plugin.
// String className = request.getParameter("plugin");
// Class<?> type = Class.forName(className);
// Object plugin = type.getDeclaredConstructor().newInstance();
~~~~

Điều này biến dữ liệu bên ngoài thành quyết định nạp và khởi tạo class tùy ý trong quá trình ứng dụng. Một lớp được nạp có thể chạy static initializer hoặc code khác với quyền của process.

Thay vào đó, ứng dụng có thể:

1. Định nghĩa **interface dịch vụ** công khai và ổn định.
2. Lựa chọn nhà cung cấp từ **danh sách đã triển khai, được tin cậy và được quản trị**.
3. Công bố các capability hoặc ID nghiệp vụ trong một whitelist.
4. Bọc implementation bằng proxy khi cần đo đạc hoặc một chính sách adapter.
5. Đặt kiểm tra xác thực/phân quyền ở nơi tài nguyên thực sự được thực thi.

Không cho input bên ngoài kiểm soát class loader, tên class, module, đường dẫn file JAR hay tập interface tùy ý, trừ khi đó là chức năng đặc biệt của một hệ thống plugin được cách ly và đã đánh giá rủi ro.

## 8. Giới hạn Java 27 đối với interface được proxy

Theo hợp đồng của `Proxy.newProxyInstance` trong Java SE 27:

| Điều kiện | Giải thích |
| --- | --- |
| Phải là **interface** | Không truyền class thường, enum, record hay kiểu nguyên thủy |
| Interface **không sealed** | Dynamic proxy không thể trực tiếp triển khai một sealed interface |
| Interface **không hidden** | Hidden interface không hợp lệ trong danh sách |
| Không lặp `Class<?>` trong mảng | Không được đưa cùng một interface class hai lần |
| Interface phải nhìn thấy được bởi class loader | `Class.forName(interfaceName, false, loader) == interfaceClass` theo yêu cầu đặc tả |
| Các kiểu trong public method signatures phải nhìn thấy được | Nếu không proxy class không thể định nghĩa hợp lệ |
| Interface không public có ràng buộc package và module | Các interface non-public phải thuộc cùng package và module hợp lệ |
| Các method trùng signature cần kiểu trả về tương thích | Primitive/void phải trùng; reference return type có quy tắc covariant |

Nếu vi phạm, `newProxyInstance` có thể ném `IllegalArgumentException`. Đừng bỏ qua exception này hoặc tự sửa cấu trúc module bằng cách mở toàn bộ quyền reflection.

### 8.1. Đặc biệt: `sealed interface` và dynamic proxy

~~~~java
sealed interface WorkflowResult permits Succeeded, Failed {
}

record Succeeded(String id) implements WorkflowResult {
}

record Failed(String reason) implements WorkflowResult {
}

// SAI ở runtime nếu truyền WorkflowResult.class:
// Proxy.newProxyInstance(
//     WorkflowResult.class.getClassLoader(),
//     new Class<?>[] { WorkflowResult.class },
//     handler);
// -> IllegalArgumentException.
~~~~

Lý do: sealed interface chủ động giới hạn **những subtype trực tiếp**, trong khi một proxy class sinh động không nằm trong danh sách đó. Hợp đồng Java 27 **cấm interface sealed xuất hiện trong danh sách interface dùng tạo proxy**.

Thiết kế hợp lý tùy mục tiêu:

- Nếu chỉ cần mô hình dữ liệu có tập biến thể đóng, dùng **sealed interface/record** và không tạo proxy cho kiểu sealed.
- Nếu cần **điểm mở rộng động**, dùng một interface **không sealed** làm hợp đồng proxy.
- Nếu một hệ phân cấp sealed có nhánh `non-sealed` được công bố có chủ đích, có thể proxy interface **non-sealed** đó. Nó là subtype **gián tiếp** của sealed parent, nhưng không trực tiếp triển khai sealed parent trong danh sách interface cấp cho `newProxyInstance`.

Không gỡ bỏ `sealed` một cách máy móc chỉ để “làm proxy chạy được” nếu điều đó phá vỡ ranh giới mô hình dữ liệu. Có thể tách một interface cho **dịch vụ/hành vi cần proxy** khỏi một sealed interface cho **kết quả dữ liệu**.

### 8.2. Java modules (JPMS) và truy cập reflection

Từ mô hình module Java, proxy class có thể được định nghĩa trong module/package được JDK chọn theo tính truy cập của các proxy interface. Nếu tất cả interface public nằm trong package export/open phù hợp, proxy class được bố trí tương ứng. Với interface trong package không export và không open, JDK có thể tạo proxy trong một **dynamic module** có tính đóng gói.

Hệ quả thực tế:

- Dùng `Proxy.newProxyInstance`, **không** cố tạo proxy class bằng constructor reflection.
- Kiểm tra `exports`, `requires` và `uses`/`provides` theo API module thực sự sử dụng.
- Đặt interface công khai của điểm mở rộng trong một package được module API **export** đúng đối tượng dùng nó.
- Không mặc định một proxy class sinh ra phải nằm trong package hoặc module của target.
- Không dùng `setAccessible(true)` hoặc `--add-opens` hàng loạt như một cách bỏ qua kiểm tra kiến trúc.

Ví dụ minh họa phần khai báo của một module API:

~~~~java
// module-info.java của module API (mã minh họa, không thuộc bài thực thi).
module com.example.api {
    exports com.example.api;
}
~~~~

Trong một module client:

~~~~java
module com.example.client {
    requires com.example.api;
}
~~~~

Các file `module-info.java` này chỉ để minh họa hợp đồng; bài học không yêu cầu tạo hoặc chỉnh bất cứ file module nào của dự án. Nếu interface không public, không được giả định rằng một module khác có thể truy cập nó chỉ vì nó tồn tại ở runtime.

## 9. `ServiceLoader` cho hệ thống plugin, proxy cho lớp bọc hành vi

Nếu mục tiêu là **phát hiện implementation** do module/JAR khác cung cấp, API chuẩn của JDK là `java.util.ServiceLoader`. Nó khác với dynamic proxy:

| Cơ chế | Chức năng |
| --- | --- |
| `ServiceLoader` | Tìm và khởi tạo provider của một service interface |
| `Proxy.newProxyInstance` | Tạo một implementation trung gian để chặn/xử lý lời gọi đến interface |
| `InvocationHandler` | Quyết định hành vi của lời gọi qua proxy |
| `MethodHandles` / reflection | Tìm kiếm và gọi member một cách động theo quyền truy cập |

Một điểm mở rộng điển hình có thể kết hợp hai cơ chế:

~~~~text
Ứng dụng host
      |
      v
ServiceLoader<FormatterPlugin>
      |
      v
Provider đã được triển khai / kiểm soát
      |
      v
Proxy bọc để ghi metrics và kiểm tra hợp đồng adapter
      |
      v
Plugin implementation
~~~~

### 9.1. Hợp đồng service có kiểu rõ ràng

~~~~java
package com.example.api;

public interface FormatterPlugin {
    String id();
    String format(String input);
}
~~~~

Phía provider tạo một implementation đáp ứng interface. Trong **named module**, module chủ quản service được export còn module provider khai báo `provides ... with ...`:

~~~~java
// module-info.java của module API
module com.example.api {
    exports com.example.api;
}
~~~~

~~~~java
// module-info.java của module host
module com.example.host {
    requires com.example.api;
    uses com.example.api.FormatterPlugin;
}
~~~~

~~~~java
// module-info.java của một module provider
module com.example.plugin {
    requires com.example.api;
    provides com.example.api.FormatterPlugin
        with com.example.plugin.PlainTextFormatter;
}
~~~~

Đây là **các đoạn minh họa riêng**, không phải một tệp Java duy nhất. Module provider phải có implementation `PlainTextFormatter` phù hợp và được triển khai bằng cách để runtime tìm được module theo cấu hình của ứng dụng.

### 9.2. Khám phá provider và kiểm soát quyền mở rộng

~~~~java
import com.example.api.FormatterPlugin;
import java.util.ServiceLoader;
import java.util.Set;

Set<String> approvedProviderTypes = Set.of(
        "com.example.plugin.PlainTextFormatter");

ServiceLoader<FormatterPlugin> loader =
        ServiceLoader.load(FormatterPlugin.class);

var selectedProviders = loader.stream()
        .filter(provider -> approvedProviderTypes.contains(
                provider.type().getName()))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~~

Đây là **ví dụ lọc từ danh sách provider đã được cấu hình trong runtime**. `Provider.type()` cho biết provider type và `Provider.get()` lấy instance; kiểm tra trước `get` giúp không chủ động khởi tạo provider không nằm trong danh sách cho phép qua pipeline này.

Tuy nhiên, **allowlist tên class không phải sandbox**: việc phân giải hoặc nạp class, chạy module được triển khai và khởi tạo provider đều có các yêu cầu tin cậy riêng. Ứng dụng phải kiểm soát **nguồn artifact, cấu hình runtime, cấp quyền process và quy trình phê duyệt**. Đừng biến một `ServiceLoader` có sẵn thành lời hứa rằng plugin không đáng tin sẽ không thể tác động hệ thống.

Service interface trong ví dụ **không sealed**, nên về mặt hợp đồng có thể được proxy khi các điều kiện khác của `Proxy.newProxyInstance` được đáp ứng. Để thêm metrics, host có thể dùng factory như `instrument(FormatterPlugin.class, provider)` đã giới thiệu; cách ghi logging, exception và identity cần được thống nhất trên toàn bộ điểm mở rộng.

### 9.3. Tại sao cần tách API, provider và chính sách host?

- **Module API** chỉ công bố hợp đồng và dữ liệu chia sẻ; nên có số lượng method ít và versioning rõ.
- **Provider** triển khai một hoặc nhiều chức năng đã được phép, không được biết tùy ý nội bộ host.
- **Host** quyết định provider nào được nạp, thứ tự ưu tiên, định dạng input/output, mức timeout, giới hạn kích thước và cách xử lý lỗi.
- **Proxy/decorator** có thể thêm chính sách liên quan lời gọi, nhưng phải đặt bên đúng với tài nguyên mà nó kiểm soát.

Đây là ý nghĩa của **điểm mở rộng có kiểm soát**: có khả năng cắm hành vi mới nhưng không đánh đổi hợp đồng, tính quan sát được và quyền sở hữu tài nguyên.

## 10. An toàn đa luồng và vòng đời của handler

Một proxy instance có thể được nhiều thread gọi đồng thời. JDK **không tự đặt khóa** quanh `InvocationHandler.invoke` hoặc quanh target. Nếu handler ghi vào trạng thái mutable hoặc target không thread-safe, proxy không biến chúng thành thread-safe.

### 10.1. Bộ đếm lời gọi an toàn giữa các thread

~~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.LongAdder;

interface HealthCheck {
    boolean healthy();
}

public class ProxyCounterDemo {
    public static void main(String[] args) {
        LongAdder callCount = new LongAdder();

        InvocationHandler handler = (proxy, method, arguments) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == arguments[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "HealthCheckProxy";
                    default -> throw new UnsupportedOperationException();
                };
            }

            if (!method.getName().equals("healthy")) {
                throw new UnsupportedOperationException(method.getName());
            }

            callCount.increment();
            return Boolean.TRUE;
        };

        HealthCheck service = (HealthCheck) Proxy.newProxyInstance(
                HealthCheck.class.getClassLoader(),
                new Class<?>[] { HealthCheck.class },
                handler);

        System.out.println(service.healthy()); // true
        System.out.println(callCount.sum());    // 1
    }
}
~~~~

`LongAdder` hỗ trợ tích lũy nhiều luồng với mức tranh chấp thấp. Nhưng `sum()` **không phải snapshot nguyên tử** nếu vẫn có thread đang tăng đếm. Nếu nghiệp vụ yêu cầu đồng bộ nhiều biến hoặc cần số đếm chính xác tại một mốc giao dịch, phải chọn chiến lược khác.

Trong thực tế, handler có thể nắm một target là singleton hoặc service có trạng thái. Tính an toàn đa luồng của target vẫn phải được đánh giá riêng. Một proxy chỉ dùng metadata `Method` và các cấu hình bất biến thường dễ chia sẻ hơn proxy tích lũy trực tiếp vào `HashMap` mutable.

### 10.2. Tránh giữ dữ liệu của từng request trong trường dùng chung

Phản ví dụ:

~~~~java
// KHÔNG nên dùng một biến chung cho tham số của mọi request.
// Object[] lastArgs;  // mutable shared state
//
// invoke(..., Object[] args) {
//     lastArgs = args;
//     ...
// }
~~~~

Các lời gọi từ nhiều thread có thể ghi đè biến này, còn mảng `args` chứa tham chiếu đến dữ liệu caller. Nếu cần logging, hãy thiết kế một record log đã **lọc dữ liệu nhạy cảm**, có kích thước giới hạn và không giữ alias đến input mutable. Nếu cần correlation ID theo request, sử dụng cơ chế context mà hệ thống đã quy định thay vì một field dùng chung trong handler.

### 10.3. Không mặc định proxy tự động có thể serialize an toàn

JDK proxy class có thể tham gia Java serialization theo giao diện `Serializable` của `Proxy`, nhưng khả năng serialize thành công còn phụ thuộc **handler và trạng thái được handler giữ**, cùng các yêu cầu môi trường. Không lưu trữ proxy instance hoặc truyền qua mạng dưới dạng Java serialized object chỉ vì class proxy mang interface `Serializable`.

Đối với trao đổi dữ liệu, nên dùng DTO/record có hợp đồng rõ ràng và định dạng giao thức đã được kiểm soát. Không dùng Java native deserialization trên dữ liệu không tin cậy như một cơ chế nạp plugin hay khôi phục proxy.

## 11. Hiệu năng và lựa chọn thay thế

Dynamic proxy thêm một bước dispatch qua `InvocationHandler`; việc gọi `Method.invoke` lên target còn là một phép gọi reflection. Điều này có thể hợp lý khi phần nghiệp vụ chính là I/O hoặc chi phí xử lý lớn, nhưng nếu một hàm cực nhỏ được gọi hàng triệu lần trong vòng lặp nóng, overhead của proxy có thể đáng kể.

Đừng khẳng định dynamic proxy “chậm hơn đúng N lần” hoặc “MethodHandle luôn nhanh hơn” nếu chưa đo. Hiệu năng phụ thuộc JIT, tính đa hình của call site, cách tổ chức handler, workload và JVM.

| Cách tiếp cận | Ưu điểm | Giới hạn |
| --- | --- | --- |
| Gọi trực tiếp interface | Đơn giản, an toàn kiểu tĩnh, dễ debug | Không tự chèn logic ngang trên nhiều implementation |
| **Decorator viết tay** | Kiểm tra tĩnh, xử lý rõ từng method | Tốn code nếu nhiều interface/method |
| **JDK dynamic proxy** | Tạo wrapper lúc chạy, tái sử dụng interceptor | Chỉ hỗ trợ interface hợp lệ, thêm dispatch và reflection |
| `MethodHandles.Lookup` / `MethodHandle` | Hỗ trợ gọi động có ràng buộc kiểu và quyền truy cập | API nâng cao, không tự tạo wrapper interface như `Proxy` |
| `ServiceLoader` | Tìm provider đã triển khai cho service interface | Không tự intercept lời gọi hoặc sandbox plugin |

### 11.1. Khi nào decorator viết tay hợp lý hơn?

Một interface nhỏ:

~~~~java
interface PriceService {
    long getPriceInCents(String sku);
}

final class TimedPriceService implements PriceService {
    private final PriceService target;

    TimedPriceService(PriceService target) {
        this.target = java.util.Objects.requireNonNull(target);
    }

    @Override
    public long getPriceInCents(String sku) {
        long started = System.nanoTime();
        try {
            return target.getPriceInCents(sku);
        } finally {
            System.out.println(
                    "getPriceInCents took " + (System.nanoTime() - started));
        }
    }
}
~~~~

Đây là cách **tĩnh, minh bạch** và được compiler kiểm tra, không cần reflection. Với chỉ vài interface và một số method ổn định, nó có thể dễ bảo trì và dễ kiểm thử hơn factory proxy chung.

### 11.2. Khi nào dùng `MethodHandle`?

`MethodHandle` và `MethodHandles.Lookup` hữu ích khi cần tìm và gọi một member động theo quyền truy cập đã có, có thể tái sử dụng handle và áp dụng biến đổi kiểu invocation. Tuy nhiên:

- Chúng **không tự tạo instance triển khai một interface** như `Proxy.newProxyInstance`.
- Quyền truy cập vẫn áp dụng; không nên mở private member tùy ý chỉ để “chạy được”.
- Nếu chỉ cần gọi một method đã biết ở compile time, gọi thông thường đơn giản hơn.

Phân biệt **dynamic invocation** (gọi method) với **dynamic proxy** (tạo object triển khai interface để chặn lời gọi): đây là hai vấn đề có thể phối hợp nhưng không tương đương.

## 12. Kiểm thử dynamic proxy và policy

Một test tốt không chỉ gọi được phương thức thành công. Nó cần xác nhận cả đường được phép, đường bị từ chối, default methods, exception và điều kiện concurrency.

### 12.1. Ma trận hành vi

| Tình huống | Kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Tạo proxy cho interface public không sealed | `Proxy.newProxyInstance` | Thành công nếu class loader và signature hợp lệ |
| Tạo proxy cho sealed interface | `Proxy.newProxyInstance` | `IllegalArgumentException` |
| Tạo proxy cho class thường | `Proxy.newProxyInstance` | `IllegalArgumentException` |
| Truyền cùng interface hai lần | Mảng `new Class<?>[]{A.class, A.class}` | `IllegalArgumentException` |
| Gọi method không tham số | `args` trong handler | Có thể là null |
| Method trả primitive, handler trả wrapper đúng | `int`/`Integer` | Caller nhận giá trị primitive |
| Method trả primitive, handler trả null | `int` | `NullPointerException` |
| Method trả reference type, handler trả sai kiểu | Kiểu trả về | `ClassCastException` |
| `equals`/`hashCode`/`toString` | `getDeclaringClass()` | Nhận `Object.class` |
| Gọi default method | Handler dùng `invokeDefault` | Thân default chạy và có thể gọi lại method qua proxy |
| Target ném checked exception đã khai báo | Unwrap `InvocationTargetException` | Caller nhận exception phù hợp với hợp đồng |
| Handler ném checked exception chưa khai báo | Lời gọi qua proxy | `UndeclaredThrowableException` |
| Annotation runtime trên interface method | `isAnnotationPresent` | Handler đọc được |
| Annotation chỉ trên implementation method | `Method` từ interface | Không tự được nhìn thấy |
| Method nằm ngoài allowlist | Handler chặn trước delegate | Target không được gọi |
| Dùng cùng proxy từ nhiều thread | Handler/target chia sẻ | Cần bảo đảm thread safety theo thiết kế |

### 12.2. Kiểm thử allowlist không bị bỏ qua qua proxy

Trong ví dụ `ReadOnlyProxyDemo`, nên kiểm tra:

~~~~java
DocumentPort port = ReadOnlyProxyDemo.readOnly(
        new ReadOnlyProxyDemo.DocumentStore());

System.out.println(port.read("DOC-1") != null); // true

try {
    port.delete("DOC-1");
    throw new AssertionError("delete should be blocked");
} catch (UnsupportedOperationException expected) {
    System.out.println("Policy worked");
}

System.out.println(port.read("DOC-1") != null); // true
~~~~

Đoạn kiểm thử minh họa này giả định đang ở môi trường có quyền truy cập `ReadOnlyProxyDemo` và `DocumentPort`, cùng xử lý `NoSuchMethodException` theo chữ ký `readOnly`. Đừng chạy nó như một đoạn mã độc lập không có các class của ví dụ trước.

### 12.3. Kiểm thử không đệ quy qua `Object`

~~~~java
AccountLookup proxy = DynamicProxyDemo.instrument(
        DynamicProxyDemo.AccountLookup.class,
        new DynamicProxyDemo.AccountLookupImpl());

System.out.println(proxy.equals(proxy)); // true
System.out.println(proxy.hashCode() == proxy.hashCode()); // true
System.out.println(proxy.toString()); // Proxy<AccountLookup>
~~~~

Một bộ test nên gọi ba method này **trước khi** đưa proxy vào `HashMap`, `HashSet` hoặc logger, vì nhiều framework sẽ gọi chúng dù nghiệp vụ không gọi trực tiếp.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đưa một class hoặc sealed interface vào `newProxyInstance` | `IllegalArgumentException` | Dùng interface không sealed, hoặc thiết kế decorator |
| Dùng `Proxy.getProxyClass` để tạo instance | API deprecated, dễ vướng đóng gói module | Dùng `Proxy.newProxyInstance` |
| Handler chỉ xử lý method nghiệp vụ | `equals`/`hashCode`/`toString` hoạt động sai hoặc ném lỗi | Có nhánh xử lý `Object` tường minh |
| Handler gọi lại `method.invoke(proxy, args)` | Đệ quy vô hạn qua proxy | Gọi target, hoặc dùng `invokeDefault` cho thân default |
| Không kiểm tra `args == null` | `NullPointerException` khi method không có tham số | Quy ước mảng rỗng hoặc kiểm tra trước |
| Trả null cho method trả primitive | `NullPointerException` ở đường gọi | Trả boxed value đúng loại |
| Trả giá trị sai kiểu | `ClassCastException` | Tôn trọng return type đã khai báo |
| Không unwrap `InvocationTargetException` | Lỗi target bị bọc thêm, thậm chí thành `UndeclaredThrowableException` | Ném lại `getCause()` phù hợp với contract |
| Dùng `method.getName()` để phân quyền | Không xét overload, có thể chặn/cho phép sai | Dùng `Method` hoặc annotation/metadata chính xác |
| Không đặt `@Retention(RUNTIME)` | Handler không thấy annotation qua reflection | Thiết kế retention đúng |
| Chỉ gắn annotation lên implementation nhưng handler đọc Method từ interface | Policy không được kích hoạt | Đặt trên interface hoặc tra cứu implementation tường minh |
| Cho rằng `@Inherited` có tác dụng với method | Hiểu sai kế thừa annotation | Áp dụng đúng quy tắc cho class annotation |
| Mở toàn bộ quyền reflection để “sửa” vấn đề JPMS | Làm mất ranh giới module | Export API cần thiết; không mở tràn lan |
| Coi proxy là tường bảo vệ trước code không tin cậy | Caller vẫn có thể truy cập target hoặc handler theo đường khác | Thực thi quyền ở tầng tài nguyên đáng tin |
| Nạp class từ tên nhận từ HTTP để làm plugin | Tạo đường chạy code ngoài ý muốn | Chỉ nạp provider được triển khai/kiểm soát |
| Giữ trạng thái request trong handler dùng chung | Data race và rò rỉ dữ liệu | Dùng state cục bộ hoặc cấu trúc concurrency phù hợp |
| Cho rằng mọi proxy phù hợp để serialize | Handler/target có thể không serializable | Dùng hợp đồng DTO, tránh native serialization không tin cậy |

## 14. Quy trình ra quyết định khi thiết kế điểm mở rộng

1. **Xác định điểm thay đổi:** cần đổi implementation, chặn lời gọi, bổ sung metrics hay kiểm soát tài nguyên?
2. **Định nghĩa interface nhỏ, có kiểu rõ ràng:** làm hợp đồng cho client; không vội dùng reflection cho mọi việc.
3. **Chọn cơ chế:** decorator nếu ít method; JDK dynamic proxy nếu có nhiều interface cùng logic interception; `ServiceLoader` nếu cần phát hiện provider.
4. **Kiểm soát nguồn thực thi:** chọn provider từ artifact đã quản trị, không từ class name nhập tùy ý.
5. **Kiểm tra hợp đồng trước khi tạo proxy:** interface non-sealed, target `isInstance`, class loader và module truy cập được.
6. **Thiết kế handler theo deny-by-default:** xử lý `Object`, default method, checked exception, các method thực sự được phép và kiểm tra input.
7. **Không nhầm proxy với bảo mật:** xác thực và phân quyền phải nằm ở biên tin cậy của tài nguyên.
8. **Tách dữ liệu và logic:** record/DTO dùng để trao đổi dữ liệu; interface/handler dùng để định tuyến hành vi.
9. **Kiểm tra concurrency và lifecycle:** handler hoặc target dùng chung phải có chính sách thread safety.
10. **Kiểm thử bằng hành vi:** không phụ thuộc tên lớp proxy sinh ra, không giả định proxy class ở package cụ thể.

### Checklist trước khi phát hành

- [ ] Hợp đồng interface có giới hạn rõ, không sealed và nhìn thấy được qua class loader phù hợp.
- [ ] Không dùng API `Proxy.getProxyClass` deprecated.
- [ ] Handler không gọi lại `Method.invoke(proxy, ...)` gây đệ quy.
- [ ] Ba method `equals`/`hashCode`/`toString` được xử lý nhất quán.
- [ ] Method không tham số và method trả primitive có xử lý đúng.
- [ ] Default method được xử lý đúng, không tự động được gọi ngoài ý muốn.
- [ ] Exception của target được unwrap từ `InvocationTargetException` nếu delegate dùng reflection.
- [ ] Checked exception tương thích với `throws` của interface.
- [ ] Annotation policy được định nghĩa với `RUNTIME` retention và đặt đúng vị trí.
- [ ] Danh sách thao tác được phép không chỉ so tên method bỏ qua overload.
- [ ] Target/handler có quy tắc an toàn đa luồng và không rò dữ liệu nhạy cảm.
- [ ] Các interface và kiểu trong signature đáp ứng quy tắc module/class loader.
- [ ] Provider/plugin chỉ đến từ nguồn đã được phê duyệt và kiểm soát.
- [ ] Các đường gọi **ngoài proxy** tới cùng tài nguyên cũng được bảo vệ nếu có yêu cầu phân quyền.
- [ ] Có test cho phương thức được phép, từ chối, ngoại lệ, default, metadata và concurrency.

## Tài liệu tham khảo chính thức

- [Java SE 27 — Proxy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Proxy.html): hạn chế interface, `newProxyInstance`, tính truy cập qua module, duplicate signatures, `Object` methods.
- [Java SE 27 — InvocationHandler](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/InvocationHandler.html): `invoke`, `invokeDefault`, hợp đồng đối số/kiểu trả về/exception.
- [Java SE 27 — Method](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html): phản chiếu thông tin method, invocation và annotation.
- [Java SE 27 — InvocationTargetException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): exception bọc lỗi do target ném.
- [Java SE 27 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): checked exception không nằm trong hợp đồng method.
- [Java SE 27 — RetentionPolicy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/annotation/RetentionPolicy.html): SOURCE/CLASS/RUNTIME.
- [Java SE 27 — ServiceLoader](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ServiceLoader.html): phát hiện provider, named modules và lifecycle.
- [Java SE 27 — MethodHandles](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.html): phương án tra cứu và gọi member động bằng lookup.

**Kết luận:** JDK dynamic proxy giúp áp dụng hành vi dùng chung lên **những interface cụ thể** tại runtime mà không sửa implementation. Trên Java 27, dùng `Proxy.newProxyInstance` và `InvocationHandler`, xử lý rõ lời gọi `Object`, default methods, metadata annotation và exception. Một điểm mở rộng tốt cần thêm **interface nhỏ, allowlist chính xác, quản lý provider, giới hạn class loader/module và kiểm tra quyền tại tài nguyên thực**. Proxy là công cụ để tổ chức kiến trúc và định tuyến lời gọi — không phải đặc quyền vượt qua hệ thống kiểu hay cơ chế sandbox cho code không tin cậy.
