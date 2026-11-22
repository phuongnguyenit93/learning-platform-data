# `Proxy.isProxyClass`, `Proxy.getInvocationHandler` và giới hạn của tên lớp proxy trong Java

## 1. Bài toán: nhận diện một JDK dynamic proxy đúng cách

Trong Java Reflection, `java.lang.reflect.Proxy` tạo **dynamic proxy** tại runtime: JVM sinh một lớp thực thi một hoặc nhiều interface và chuyển các lời gọi phương thức qua một đối tượng `InvocationHandler`. Cơ chế này thường xuất hiện ở adapter, logging, kiểm tra quyền, giao dịch, AOP hoặc client gọi dịch vụ.

Khi đang cầm một biến kiểu `Object`, có ba câu hỏi khác nhau:

1. **Đối tượng có thực sự thuộc lớp JDK dynamic proxy?** Dùng `Proxy.isProxyClass(candidate.getClass())` sau khi kiểm tra `candidate != null`.
2. **Đối tượng proxy đang sử dụng handler nào?** Dùng `Proxy.getInvocationHandler(candidate)`, với điều kiện đây là instance của lớp proxy do API JDK tạo.
3. **Đối tượng có cung cấp nghiệp vụ qua interface nào?** Kiểm tra `instanceof`, `Class.isInstance` hoặc ép về interface đã biết. Đây là kiểm tra hợp đồng nghiệp vụ, không đồng nghĩa với hai câu hỏi trên.

**Điểm mấu chốt:** đừng nhận diện proxy bằng chuỗi do `getClass().getName()` trả về. Tên lớp phát sinh là chi tiết triển khai, không phải giao diện API ổn định.

## 2. Hai API chính và điều kiện sử dụng

Các chữ ký trong `java.lang.reflect.Proxy`:

```java
public static boolean isProxyClass(Class<?> cl);
public static InvocationHandler getInvocationHandler(Object proxy)
        throws IllegalArgumentException;
```

| API | Đầu vào | Ý nghĩa khi thành công | Trường hợp cần lưu ý |
|---|---|---|---|
| `Proxy.isProxyClass(Class<?> cl)` | Đối tượng `Class` cần kiểm tra | `true` đúng khi `cl` là lớp proxy được sinh bởi cơ chế `java.lang.reflect.Proxy` | Không có nghĩa “bất kỳ lớp nào kế thừa `Proxy`”; với lớp thường kết quả là `false` |
| `Proxy.getInvocationHandler(Object proxy)` | **Instance** của JDK dynamic proxy | Trả về chính tham chiếu `InvocationHandler` đã gắn với proxy | Ném `IllegalArgumentException` nếu đối số không phải instance proxy hợp lệ |
| `Proxy.newProxyInstance(loader, interfaces, handler)` | Loader, mảng interface và handler | Tạo instance proxy triển khai những interface yêu cầu | Có thể thất bại nếu tập interface hoặc khả năng nhìn thấy interface không hợp lệ |

Chú ý sự khác biệt về đối số: `isProxyClass` nhận **`Class<?>`** (thường lấy qua `obj.getClass()`), còn `getInvocationHandler` nhận **instance `Object`**. Không truyền `Greeting.class` cho `getInvocationHandler`, và không truyền trực tiếp `greeting` cho `isProxyClass`.

Theo hợp đồng API, `isProxyClass` chỉ nhận diện lớp được tạo bằng cơ chế `Proxy.newProxyInstance` hoặc `Proxy.getProxyClass` (phương thức thứ hai đã bị đánh dấu deprecated từ Java 9). Nó không kiểm tra tên lớp theo mẫu `$Proxy...`, cũng không coi `Proxy.class` hoặc lớp tự viết `extends Proxy` là lớp proxy được sinh động.

`getInvocationHandler` cung cấp **handler đang gắn với proxy**, không tự động trả về đối tượng đích (target). Nếu handler đóng vai trò delegate tới một service thật, muốn biết target cần API do chính handler/framework cung cấp; JDK không định nghĩa một phương thức “unwrap target” chung.

## 3. Đường đi của một lời gọi phương thức

Luồng cơ bản:

```text
Mã gọi qua interface
        |
        v
proxy.greet("Lan")
        |
        v
Lớp proxy do JDK sinh tại runtime
        |
        v
InvocationHandler.invoke(proxy, method, args)
        |
        +-- log/kiểm tra quyền/chuyển tiếp tới target
        |
        v
Giá trị trả về hoặc exception đến phía gọi
```

Để tạo JDK dynamic proxy, trước hết phải có ít nhất một interface phù hợp và một handler. Ví dụ:

```java
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        handler
);
```

Đây là **mảnh code minh họa**: `Greeting` và `handler` được định nghĩa trong ví dụ chạy hoàn chỉnh bên dưới.

`Proxy.newProxyInstance` tạo proxy triển khai `Greeting` và gắn `handler`. Khi gọi `proxy.greet(...)`, đối tượng `Method` và đối số được chuyển tới `InvocationHandler.invoke(...)`. Điều này khác với Reflection thông thường: việc lấy `Class` hoặc lấy handler **không tự chạy phương thức nghiệp vụ**.

Ba phương thức `equals(Object)`, `hashCode()` và `toString()` của `Object` cũng được chuyển qua handler khi gọi trên JDK proxy; người viết handler nên định nghĩa hành vi phù hợp. Trái lại, `getClass()` là phương thức `final` của `Object` và không được dispatch qua handler.

## 4. Ví dụ Java 17+ chạy độc lập: kiểm tra lớp và lấy handler

Tạo file `ProxyInspectionDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyInspectionDemo {
    interface Greeting {
        String greet(String name);
    }

    static class ManualProxy extends Proxy {
        ManualProxy(InvocationHandler handler) {
            super(handler);
        }
    }

    public static void main(String[] args) {
        InvocationHandler handler = (proxy, method, parameters) -> {
            switch (method.getName()) {
                case "greet":
                    return "Xin chào, " + parameters[0];
                case "toString":
                    return "GreetingProxy";
                case "equals":
                    return proxy == parameters[0];
                case "hashCode":
                    return System.identityHashCode(proxy);
                default:
                    throw new UnsupportedOperationException(method.getName());
            }
        };

        Greeting greeting = (Greeting) Proxy.newProxyInstance(
                Greeting.class.getClassLoader(),
                new Class<?>[]{Greeting.class},
                handler
        );

        System.out.println("isProxyClass: " + Proxy.isProxyClass(greeting.getClass()));
        System.out.println("same handler: " + (Proxy.getInvocationHandler(greeting) == handler));
        System.out.println(greeting.greet("Lan"));
        System.out.println("toString: " + greeting);
        System.out.println("String.class isProxyClass: " + Proxy.isProxyClass(String.class));

        ManualProxy manual = new ManualProxy(handler);
        System.out.println("manual instanceof Proxy: " + (manual instanceof Proxy));
        System.out.println("manual isProxyClass: " + Proxy.isProxyClass(manual.getClass()));

        try {
            Proxy.getInvocationHandler(manual);
        } catch (IllegalArgumentException ex) {
            System.out.println("manual handler: IllegalArgumentException");
        }

        try {
            Proxy.getInvocationHandler("ordinary");
        } catch (IllegalArgumentException ex) {
            System.out.println("ordinary handler: IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac ProxyInspectionDemo.java
java ProxyInspectionDemo
```

Stdout:

```text
isProxyClass: true
same handler: true
Xin chào, Lan
toString: GreetingProxy
String.class isProxyClass: false
manual instanceof Proxy: true
manual isProxyClass: false
manual handler: IllegalArgumentException
ordinary handler: IllegalArgumentException
```

**Giải thích các điểm dễ nhầm:**

- `greeting.getClass()` là lớp proxy sinh bởi JDK, nên `isProxyClass` trả `true`. `Proxy.getInvocationHandler(greeting) == handler` trả `true` vì trả đúng tham chiếu handler đã cung cấp.
- `Greeting` là interface lồng trong lớp ví dụ; chương trình dùng loader có thể nhìn thấy interface đó. Không cần biết tên class mà JVM tạo ra.
- Lời gọi `greeting.greet("Lan")` được xử lý ở nhánh `"greet"` của handler. Kết quả `"Xin chào, Lan"` là giá trị handler trả về.
- `toString()` cũng qua handler. `Proxy.isProxyClass(String.class)` trả `false` vì `String` là lớp thường.
- `ManualProxy` **tự kế thừa** `Proxy` và dùng constructor `protected Proxy(InvocationHandler)`, nhưng không phải lớp sinh bởi Proxy API. Vì vậy `manual instanceof Proxy` là `true`, còn `isProxyClass(manual.getClass())` là `false`.
- `getInvocationHandler(manual)` và `getInvocationHandler("ordinary")` đều ném `IllegalArgumentException`. Việc một object kế thừa `Proxy` hoặc có trường handler không đủ để thỏa điều kiện API.

Đoạn xử lý `equals/hashCode/toString` trong ví dụ nhằm minh họa việc các lời gọi đó cũng qua handler. Với hệ thống thực, phải chọn chính sách `equals` và `hashCode` nhất quán, đặc biệt nếu proxy được dùng làm khóa trong `HashMap`/`HashSet`.

## 5. Vì sao `instanceof Proxy` và tên lớp không thay thế `isProxyClass`?

Xét ba cách kiểm tra:

```java
boolean a = candidate instanceof Proxy;
boolean b = candidate != null
        && Proxy.isProxyClass(candidate.getClass());
boolean c = candidate != null
        && candidate.getClass().getName().contains("$Proxy");
```

Đây là **mảnh code minh họa** với biến `candidate` kiểu `Object` đã có; không phải chương trình chạy độc lập.

- `a` chỉ cho biết đối tượng là instance của `Proxy` hoặc một lớp kế thừa `Proxy`. Ví dụ `ManualProxy` ở trên làm cho `a` đúng nhưng `b` sai.
- `b` là kiểm tra theo hợp đồng của JDK cho một **instance lớp proxy được sinh động**. Đây là lựa chọn phù hợp khi thực sự cần biết một object có phải JDK proxy.
- `c` là heuristic theo tên; có thể sai dương với lớp người dùng tự đặt tên chứa `$Proxy`, hoặc sai âm khi cơ chế đặt tên và package thay đổi. Đừng dùng trong code điều khiển nghiệp vụ hay kiểm tra bảo mật.

Một proxy vẫn có thể triển khai rất nhiều interface; `isProxyClass` **không nói proxy triển khai interface nào**. Nếu cần đảm bảo proxy dùng như `Greeting`, kiểm tra `candidate instanceof Greeting` hoặc `Greeting.class.isInstance(candidate)`. Ngược lại, một implementation bình thường của `Greeting` không tự trở thành dynamic proxy chỉ vì thực thi interface đó.

Nhận diện theo lớp và nhận diện theo năng lực phải phục vụ hai mục đích khác nhau:

| Bạn cần biết | Nên dùng |
|---|---|
| Đối tượng có đúng là JDK dynamic proxy? | `Proxy.isProxyClass(obj.getClass())`, sau khi kiểm tra null |
| Lấy JDK `InvocationHandler` đang gắn với instance | `Proxy.getInvocationHandler(obj)`, sau khi đã xác minh proxy |
| Đối tượng có thể được dùng qua interface `Service`? | `obj instanceof Service` hoặc `Service.class.isInstance(obj)` |
| Handler có chuyển tiếp tới target nào? | API/hợp đồng của handler hoặc framework cụ thể |
| Đây có phải proxy do CGLIB/Byte Buddy/Spring cơ chế khác tạo? | API phát hiện proxy của chính công cụ/framework tương ứng |

## 6. Giới hạn khi dựa vào tên lớp proxy

Ở một số lần chạy, `proxy.getClass().getName()` có thể trông giống `jdk.proxy1.$Proxy0` hoặc một tên khác chứa `$Proxy`. Đây **chỉ là ví dụ về tên có thể quan sát được**, không phải quy tắc đặt tên được JDK hứa bảo toàn. Các điều kiện ảnh hưởng đến lớp được tạo gồm:

1. **Phiên bản JDK, implementation và môi trường module:** cách tổ chức package/module cho proxy có thể thay đổi. Với interface không phải `public`, quy tắc package/module khác với trường hợp toàn bộ interface đều public.
2. **Class loader và tập interface:** proxy được định nghĩa trong không gian lớp phù hợp với loader và các interface. Một tên lớp khi tách khỏi class loader không đủ xác định runtime identity.
3. **Thứ tự và tập interface:** proxy tạo cho các danh sách interface khác nhau có thể là các `Class` khác nhau; thứ tự interface cũng có ý nghĩa đối với bộ nhớ cache và một số quy tắc chọn `Method`.
4. **Caching và thứ tự tạo proxy:** thời điểm/tên được cấp phát là chi tiết triển khai. Đừng giả định mọi lần tạo đều có hậu tố tăng dần hoặc proxy thứ nhất luôn là `$Proxy0`.

Do đó, những đoạn mã dưới đây không đáng tin cậy:

```java
// KHÔNG NÊN: dựa vào package/tên lớp phát sinh.
if (obj.getClass().getName().startsWith("com.sun.proxy.$Proxy")) {
    // ...
}

// KHÔNG NÊN: tự suy ra loại proxy từ hậu tố số.
String generatedName = obj.getClass().getSimpleName();
boolean guessed = generatedName.matches("\\$Proxy\\d+");
```

Đây là các **mảnh mã phản ví dụ**; biến `obj` phải được định nghĩa trong ngữ cảnh bao quanh.

Không đưa tên proxy sinh ra vào file cấu hình, định dạng dữ liệu lưu trữ, cache key hay điều kiện phân quyền. Nếu cần biết hợp đồng, lưu **tên interface hoặc định danh nghiệp vụ ổn định**. Nếu cần lấy handler, giữ API công khai của `Proxy`. Nếu cần log để chẩn đoán, có thể ghi tên lớp hiện tại, nhưng log đó là thông tin quan sát, không phải chuẩn tương thích.

### Class identity vẫn phụ thuộc class loader

Trong JVM, identity của một lớp được xác định bởi **binary name và defining class loader**. Hai class loader độc lập có thể định nghĩa hai lớp cùng binary name nhưng có identity khác nhau. Kết quả là so sánh `Class<?>`, phép ép kiểu và khả năng truy cập interface có thể khác ngay cả khi chuỗi `getName()` bằng nhau.

Không dùng `Class.forName("jdk.proxy1.$Proxy0")` hoặc tên sinh ngẫu nhiên đã thấy ở lần chạy trước để khôi phục proxy. Thay vào đó, giữ đối tượng hoặc interface cần thiết, và tạo proxy mới qua `Proxy.newProxyInstance` khi đúng yêu cầu.

## 7. Mẫu kiểm tra an toàn trước khi lấy handler

Nếu đầu vào có thể là object bình thường, có thể viết một utility nhỏ:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.util.Optional;

public final class ProxyHandlers {
    private ProxyHandlers() {
    }

    public static Optional<InvocationHandler> jdkHandler(Object candidate) {
        if (candidate == null || !Proxy.isProxyClass(candidate.getClass())) {
            return Optional.empty();
        }
        return Optional.of(Proxy.getInvocationHandler(candidate));
    }
}
```

Lưu thành `ProxyHandlers.java` và biên dịch:

```bash
javac ProxyHandlers.java
```

Phương thức `jdkHandler` không gọi vào handler hay tạo instance mới; nó chỉ trả về metadata đối tượng đang có. `Optional.empty()` cho biết đầu vào null hoặc không phải JDK proxy, không có nghĩa mọi object không phải JDK proxy đều không dùng cơ chế AOP/proxy nào khác.

Trường hợp ứng dụng **biết chắc** đầu vào là JDK proxy, có thể gọi trực tiếp:

```java
InvocationHandler handler = Proxy.getInvocationHandler(proxyObject);
```

Đây là **mảnh code minh họa**; `proxyObject` phải là instance JDK proxy hợp lệ trong ngữ cảnh. Với đầu vào từ bên ngoài, nên kiểm tra trước để tránh `IllegalArgumentException`. Không nên bắt mọi exception rồi im lặng coi mọi object là proxy.

Cũng cần phân biệt *lấy handler* với *dùng handler*. `getInvocationHandler` trả một đối tượng có thể chứa state, phụ thuộc framework, trạng thái kết nối hoặc dữ liệu ủy quyền. Không tùy tiện ép handler về kiểu nội bộ hoặc gọi trực tiếp `invoke` bên ngoài hợp đồng của framework.

## 8. Dùng trong framework, logging và kiểm tra lỗi

**Phát hiện một JDK proxy cho mục đích chẩn đoán:**

```java
if (service != null && Proxy.isProxyClass(service.getClass())) {
    InvocationHandler handler = Proxy.getInvocationHandler(service);
    System.out.println("JDK handler type: " + handler.getClass().getName());
}
```

Đây là **mảnh code minh họa**, giả định biến `service` đã có. Việc log *kiểu của handler* thường ổn hơn việc hard-code tên lớp proxy sinh ra. Không tự động log toàn bộ `toString()` của handler vì nó có thể bao gồm thông tin nội bộ.

**Nếu dùng Spring AOP hay thư viện proxy khác:** JDK dynamic proxy chỉ là một lựa chọn. Các proxy dựa trên subclass hoặc cơ chế bytecode khác có thể không được `Proxy.isProxyClass` nhận diện dù vẫn hoạt động như proxy. Khi cần phân biệt proxy framework, dùng API framework hỗ trợ, thay vì xây thuật toán đoán từ tên lớp hoặc từ `Proxy.isProxyClass` đơn lẻ.

**Khi debug sự cố:**

- `isProxyClass == false`: trước hết xác nhận đó thực sự là JDK dynamic proxy hay chỉ là lớp thường/subclass proxy khác. Đừng kết luận “không có proxy”.
- `getInvocationHandler` ném `IllegalArgumentException`: kiểm tra đúng object instance, không truyền target, `Class<?>`, `Proxy.class` hoặc một subclass viết tay.
- `ClassCastException` khi ép về interface: proxy có thể không triển khai interface đó, hoặc interface có identity khác do class loader. Kiểm tra `instanceof` và loader tương ứng.
- `InvocationHandler.invoke` trả sai kiểu hoặc `null` cho method trả primitive: phương thức proxy có thể phát sinh `ClassCastException` hoặc `NullPointerException`. Đó là lỗi hợp đồng giá trị trả về của handler, không phải lỗi nhận diện tên proxy.
- `UndeclaredThrowableException`: có thể xuất hiện khi handler ném checked exception không được khai báo tương thích với phương thức interface; cần xem exception gốc.

## 9. Các lưu ý về thiết kế và bảo trì

**Ưu tiên lập trình qua interface.** Tạo proxy và truyền nó như `Greeting`, `Service` hoặc interface nghiệp vụ. Không ép về lớp có tên `$ProxyN`, không tạo đối tượng bằng constructor của proxy sinh ra và không dựa vào thứ tự class được tạo.

**Không dùng handler như API nghiệp vụ.** Handler là cấu phần hạ tầng hỗ trợ dispatch. Framework có thể thay đổi implementation handler, thêm nhiều lớp delegate hoặc đổi chiến lược proxy. Nếu bạn cần truy cập mục tiêu, định nghĩa một giao diện hoặc sử dụng API chính thức của framework.

**Không đồng nhất nhiều loại proxy.** JDK proxy dựa trên interface; subclass-based proxy và proxy do instrumentation tạo có thể cần cách nhận diện khác. Hai phương thức của `java.lang.reflect.Proxy` chỉ có hợp đồng đối với JDK dynamic proxy.

**Kiểm tra cả logic và tương thích.** Test nên dựa vào kết quả gọi interface, `isProxyClass` và handler identity khi cần, thay vì assert tên `$Proxy0`. Các test phụ thuộc tên lớp thường thất bại khi cập nhật JDK hoặc thay đổi tổ chức class loader/module.

**Không dùng phát hiện proxy làm hàng rào an ninh.** `isProxyClass` cho biết nguồn gốc tạo lớp theo cơ chế JDK, không chứng minh handler đáng tin, target đã được xác thực hay người gọi có quyền. Việc kiểm tra input và phân quyền phải dựa trên chính sách bảo mật ứng dụng.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `obj instanceof Proxy` có thể đúng trong khi `Proxy.isProxyClass(obj.getClass())` sai? Vì lớp tự viết có thể `extends Proxy` nhưng không được JDK Proxy API sinh ra.
2. `Proxy.getInvocationHandler(obj)` có tự động trả target thật không? Không; nó trả handler đang gắn với proxy.
3. Có thể đoán một đối tượng là JDK proxy vì class name chứa `$Proxy` không? Không; đó là heuristic dựa trên chi tiết triển khai.
4. `isProxyClass` có khẳng định đối tượng triển khai `Runnable` hay một interface nghiệp vụ cụ thể không? Không; kiểm tra `instanceof Runnable` hoặc `Runnable.class.isInstance(obj)` riêng.
5. Nếu một thư viện chuyển từ JDK proxy sang subclass-based proxy, logic dựa trên `Proxy.isProxyClass` sẽ ra sao? Nó có thể trả `false`; cần xem hợp đồng của thư viện, thay vì giả định framework nào cũng dùng cùng một cơ chế.

## 11. Ghi nhớ

- `Proxy.isProxyClass(Class<?>)` kiểm tra **chính xác lớp JDK dynamic proxy được sinh qua Proxy API**.
- `Proxy.getInvocationHandler(Object)` lấy **handler đã gắn với instance JDK proxy**, và có thể ném `IllegalArgumentException` khi truyền object khác.
- `instanceof Proxy` rộng hơn điều kiện của `isProxyClass`; tên lớp `$Proxy...` là chi tiết triển khai.
- Interface và class loader mới là những điều cần xét khi sử dụng proxy; tên lớp phát sinh không phải khóa định danh ổn định.
- Dùng API JDK cho JDK dynamic proxy, API framework cho các dạng proxy khác và interface nghiệp vụ cho hành vi ứng dụng.
