# 1.4 Bản đồ Class, reflection, MethodHandle, VarHandle, Proxy và CallSite

Java có nhiều cơ chế “động” nhưng chúng giải quyết **những câu hỏi khác nhau**: biết một kiểu là gì, khám phá và gọi thành viên tại runtime, tạo lời gọi có chữ ký kiểu rõ ràng, truy cập biến với ngữ nghĩa bộ nhớ, chặn lời gọi qua interface, hoặc gắn một vị trí gọi với mục tiêu có thể thay đổi. Nhầm các vai trò này dễ dẫn đến lỗi truy cập, lỗi kiểu, và giả định sai về hiệu năng.

Sau bài này, bạn có thể vẽ được quan hệ giữa sáu cơ chế, chọn API phù hợp theo yêu cầu thực tế, đọc được chữ ký của handle, và giải thích các giới hạn về module, exception, thread safety và `invokedynamic`.

## 1. Bản đồ tổng thể

| Cơ chế | Đối tượng chính | Câu hỏi / việc giải quyết | Điểm cần nhớ |
| --- | --- | --- | --- |
| **Class** | `Class<?>` | “Đây là kiểu nào? Có superclass, interface, annotation, member gì?” | Biểu diễn kiểu đã được JVM nạp; tự nó không phải một lời gọi method. |
| **Reflection** | `Method`, `Field`, `Constructor<?>` | “Tôi biết tên/chữ ký lúc chạy; khám phá, gọi, đọc hoặc ghi thành viên thế nào?” | API thao tác theo metadata; lời gọi `Method.invoke` đóng gói kết quả/đối số dạng `Object`. |
| **MethodHandle** | `MethodHandle`, `MethodType`, `MethodHandles.Lookup` | “Làm sao nắm một thao tác gọi đã được resolve dưới dạng tham chiếu có kiểu?” | Handle mang chữ ký cụ thể, có thể biến đổi/ghép; `invokeExact` đòi khớp đúng kiểu. |
| **VarHandle** | `VarHandle` | “Làm sao đọc/ghi trường hoặc phần tử mảng, kể cả volatile, acquire/release, CAS?” | Truy cập biến và memory ordering; không phải cơ chế gọi method. |
| **Proxy** | `Proxy`, `InvocationHandler` | “Làm sao tạo object thực thi interface và chuyển lời gọi đến handler?” | JDK dynamic proxy dựa trên **interface**; handler quyết định kết quả mỗi lần gọi. |
| **CallSite** | `ConstantCallSite`, `MutableCallSite`, `VolatileCallSite` | “Tại một vị trí gọi động, MethodHandle đích được gắn và cập nhật thế nào?” | Giữ `target: MethodHandle`; quan trọng trong liên kết `invokedynamic`. |

Sơ đồ quan hệ (các mũi tên là **quan hệ sử dụng**, không phải quan hệ kế thừa):

~~~text
Đối tượng / tên lớp
    └─> Class<?> ──> tra cứu Method / Field / Constructor ──> reflection
                  └─> biết kiểu và chữ ký để tạo Lookup/MethodType
Lookup + tên + MethodType ──> MethodHandle ──> gọi / biến đổi lời gọi
Lookup + trường / array element ──> VarHandle ──> get / set / CAS
Interface[] + InvocationHandler ──> Proxy instance ──> handler.invoke(...)
Bootstrap / dynamic linker ──> CallSite ──> target: MethodHandle
                                       └─> dynamicInvoker() gọi target hiện tại
~~~

Các cơ chế có thể đi cùng nhau: một framework dùng `Class<?>` tìm annotation, reflection đọc phương thức, `MethodHandle` để giữ thao tác gọi đã resolve, `Proxy` để bọc interface, rồi dùng `CallSite` khi xây dựng liên kết động. Không có API nào thay thế toàn bộ các API còn lại.

## 2. Class: điểm xuất phát để nhận diện và khám phá kiểu

`Class<?>` là đối tượng đại diện cho một kiểu Java tại runtime, bao gồm class, interface, primitive, array và một số dạng kiểu đặc biệt. Một `Class` gắn với **định danh kiểu trong JVM**, bao gồm class loader định nghĩa nó: hai class cùng tên do hai loader khác nhau định nghĩa có thể là hai kiểu không tương thích.

Ba cách thường gặp:

~~~java
Class<String> literal = String.class;
Class<?> actual = "hello".getClass();
Class<?> byName = Class.forName("java.lang.String");

System.out.println(literal == actual); // true
System.out.println(actual == byName);   // true
~~~

Đoạn trên minh họa ba cách lấy `Class`; khi đặt các statement trong `main` sẽ in hai dòng `true`. `SomeType.class` phù hợp khi kiểu biết tại compile time; `obj.getClass()` lấy kiểu thực của đối tượng; `Class.forName(name)` dùng tên kiểu tại runtime và mặc định có thể kích hoạt khởi tạo class. Dùng `Class.forName(name, false, loader)` khi cần tải/lấy thông tin mà chưa muốn yêu cầu khởi tạo class ngay.

Phân biệt các API khám phá:

- `getMethods()`: các phương thức `public` có thể nhìn thấy, kể cả phương thức kế thừa.
- `getDeclaredMethods()`: phương thức **khai báo trực tiếp** trong kiểu, kể cả `private`, nhưng không tự động bao gồm phương thức kế thừa.
- `getMethod(name, types...)` và `getDeclaredMethod(name, types...)`: tra cứu một phương thức theo **tên và kiểu tham số**; không truyền kiểu trả về vào phép tra cứu.
- `isAssignableFrom`, `getInterfaces`, `getSuperclass`, `getAnnotations`: kiểm tra quan hệ kiểu và metadata.

`Class<?>` giúp bạn *biết thứ gì tồn tại*. Muốn gọi method hoặc đọc/ghi field qua metadata, chuyển sang reflection; muốn biểu diễn thao tác đã resolve thành lời gọi typed, dùng method/variable handle.

## 3. Reflection: khám phá và thực hiện thao tác tại runtime

Reflection trong `java.lang.reflect` cung cấp `Method`, `Field`, `Constructor`. Ví dụ, nếu tên method do cấu hình cung cấp:

~~~java
Method method = String.class.getMethod("substring", int.class);
Object result = method.invoke("dynamic", 3);
System.out.println(result); // amic
~~~

Đây là một đoạn statement minh họa (đặt trong `main` với `import java.lang.reflect.Method;`), không phải một file Java độc lập. Trình tự gồm: tra cứu `Method` theo tên/chữ ký; cung cấp **receiver** ở đối số đầu của `invoke` đối với instance method; cung cấp các đối số của method; nhận kết quả dạng `Object`. Method `static` nhận receiver `null`. Reflection tự xử lý boxing/unboxing phù hợp và có kiểm tra access.

Các giới hạn quan trọng:

1. `getDeclaredMethod` nhìn thấy member `private` không có nghĩa được phép gọi nó. `setAccessible(true)` hoặc `trySetAccessible()` vẫn chịu kiểm soát của Java Platform Module System (JPMS) và quyền truy cập runtime.
2. Nếu method được gọi tự ném exception, `Method.invoke` bọc exception đích trong `InvocationTargetException`; lấy `getCause()` để xử lý nguyên nhân thực.
3. Sai tên/chữ ký dẫn đến `NoSuchMethodException`; sai đối tượng/đối số có thể dẫn đến `IllegalArgumentException`; thiếu quyền truy cập có thể dẫn đến `IllegalAccessException` hoặc `InaccessibleObjectException` khi cố mở access không hợp lệ.
4. Reflection có ích cho serializer, DI container, test tooling, plugin discovery. Với lời gọi lặp đi lặp lại đã xác định chữ ký, cân nhắc `MethodHandle`; quyết định hiệu năng phải đo trên workload thực tế.

## 4. MethodHandle: một thao tác gọi có kiểu, có thể tổ hợp

`MethodHandle` thuộc `java.lang.invoke`, biểu diễn thao tác gọi method/constructor hoặc một số thao tác truy cập thành viên. `MethodType` mô tả **kiểu trả về và dãy kiểu tham số** của handle. `MethodHandles.Lookup` là đối tượng dùng để tìm handle trong phạm vi quyền truy cập của code đang tạo lookup.

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle length = lookup.findVirtual(
        String.class, "length", MethodType.methodType(int.class));
int n = (int) length.invokeExact("abc");
System.out.println(n); // 3
~~~

Đặt đoạn minh họa trong `main` với `import java.lang.invoke.*;` và khai báo `throws Throwable`. Chữ ký thực của `length` là `(String)int`: đối tượng nhận method trở thành tham số đầu của handle. Compile-time call site của `invokeExact` cũng phải có **tham số `String` và kiểu trả về `int`**; cast `(int)` trong mã thể hiện kiểu trả về mà compiler ghi nhận. Sai chữ ký gây `WrongMethodTypeException`.

- `invokeExact(...)`: lời gọi có chữ ký phải khớp chính xác với `MethodType`, kể cả kiểu kết quả mà compiler mong đợi.
- `invoke(...)`: có thể thực hiện một số chuyển đổi kiểu tương thích tương đương `asType`; không phải cơ chế “chuyển mọi object thành mọi kiểu”.
- `asType`, `bindTo`, `insertArguments`, `filterArguments`, `guardWithTest`: điều chỉnh chữ ký, cố định đối số, nối bước biến đổi hoặc chọn đích theo điều kiện. Mỗi phép biến đổi có quy tắc kiểu riêng.
- `findStatic`, `findVirtual`, `findConstructor`: lấy các kiểu thao tác khác nhau. MethodHandle đã resolve không tự động bỏ qua các giới hạn access.

Trái với `Method.invoke`, lời gọi qua handle thường ném exception của target trực tiếp (không tự bọc bằng `InvocationTargetException`). Handle có thể được JVM tối ưu trong một số mô hình gọi, nhưng không có bảo đảm rằng mọi lời gọi `MethodHandle` đều nhanh hơn reflection. Việc tạo lookup, chuyển đổi type, ghép adaptor và tần suất gọi đều ảnh hưởng kết quả.

## 5. VarHandle: truy cập biến cùng ngữ nghĩa bộ nhớ

`VarHandle` là handle đến một **biến** như instance field, static field hoặc phần tử mảng. Nó mang kiểu giá trị và các “coordinate types” để xác định vị trí biến; không chứa hành vi gọi method nghiệp vụ. Ví dụ `findVarHandle(Counter.class, "value", int.class)` tạo handle để truy cập trường `int value` bằng coordinate `Counter`.

Các access mode thường dùng:

| Mode | Ý nghĩa chính | Khi nào cân nhắc |
| --- | --- | --- |
| `get` / `set` | Truy cập plain | Không cần ordering liên luồng ở chính phép truy cập này. |
| `getOpaque` / `setOpaque` | Truy cập opaque, ordering yếu | Thuật toán rất chuyên biệt, đã thiết kế theo Java Memory Model. |
| `getAcquire` / `setRelease` | Acquire/read và release/write | Mô hình publish–consume có phân tích happens-before đúng. |
| `getVolatile` / `setVolatile` | Ngữ nghĩa volatile | Cần visibility/ordering kiểu volatile. |
| `compareAndSet` / `compareAndExchange` | So sánh và cập nhật nguyên tử | Triển khai chuyển trạng thái cạnh tranh giữa threads. |
| `getAndAdd` / `getAndSet` | Cập nhật nguyên tử, nếu mode/kiểu hỗ trợ | Bộ đếm/trạng thái khi phương thức được hỗ trợ. |

Ví dụ `compareAndSet(counter, 10, 11)` chỉ đổi `value` từ 10 thành 11 nếu giá trị hiện tại vẫn là 10; trả về `boolean`. `getVolatile(counter)` đọc theo ngữ nghĩa volatile. `VarHandle` không khiến mọi thao tác phức hợp tự trở thành atomic: `get` rồi `set` trong hai lời gọi riêng vẫn có thể bị thread khác chen vào. Không phải mọi access mode đều được hỗ trợ cho mọi kiểu biến (ví dụ các cập nhật không hợp lệ với `final`); mode không hỗ trợ có thể ném `UnsupportedOperationException`.

Với cấu trúc dữ liệu thông thường, hãy ưu tiên field, `volatile`, `synchronized` hoặc lớp `java.util.concurrent.atomic` khi chúng diễn đạt đúng ý định; `VarHandle` cần khi thư viện hạ tầng thực sự cần mức điều khiển truy cập thấp hơn.

## 6. Proxy: tạo object cho interface và chuyển lời gọi

JDK dynamic proxy tạo một object implement một hoặc nhiều **interface** rồi gửi các lời gọi interface tới `InvocationHandler.invoke(proxy, method, args)`. Handler có thể log, kiểm soát truy cập, cache, chọn implementation hoặc delegate sang object thật.

~~~java
interface Greeting {
    String hello(String name);
}
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[] { Greeting.class },
        (instance, method, args) -> "Chào " + args[0]);
System.out.println(proxy.hello("An")); // Chào An
~~~

Đoạn trên minh họa các khai báo trong cùng scope thích hợp; cần `import java.lang.reflect.Proxy;`. Dùng JDK dynamic proxy để intercept **interface methods**; nó không tự tạo subclass của một concrete class bất kỳ. Proxy vẫn là object bình thường đối với caller, nhưng handler nhận `Method` và đối số tại mỗi lần gọi.

Ba điều hay bị bỏ sót: `equals`, `hashCode` và `toString` cũng đi qua handler, nên cần semantics nhất quán; handler có thể dùng `InvocationHandler.invokeDefault` để gọi default method của interface khi thích hợp (Java 16+); checked exception không khai báo trên interface có thể bị bọc thành `UndeclaredThrowableException`. Tránh delegate ngược lại chính proxy, gây đệ quy vô hạn.

## 7. CallSite: mục tiêu tại vị trí gọi động

`CallSite` là holder của `MethodHandle target`. Với bytecode `invokedynamic`, bootstrap method liên kết một vị trí gọi tới `CallSite`; những lần gọi tiếp theo thực thi target tương ứng. Đây là cơ chế nền cho một số tính năng runtime và dynamic language implementation, **không đồng nghĩa** với việc gọi reflection theo tên trên từng lần thực thi.

Ba loại khác nhau ở khả năng đổi target và visibility liên luồng:

- **`ConstantCallSite`**: target cố định; `setTarget` không cho đổi. Dùng khi liên kết không đổi.
- **`MutableCallSite`**: cho `setTarget`, nhưng thread khác không được bảo đảm thấy target mới chỉ nhờ lệnh gán; `MutableCallSite.syncAll(...)` dùng để đồng bộ việc quan sát các target đã cập nhật.
- **`VolatileCallSite`**: target có ngữ nghĩa volatile; các thread quan sát update theo quy tắc volatile mà không gọi `syncAll`, có thể phải trả chi phí đồng bộ cao hơn.

Dù đổi được target, **`MethodType` của target mới phải bằng MethodType cũ**; không được âm thầm đổi số lượng/kiểu tham số hay kiểu trả về. `site.dynamicInvoker()` cho một `MethodHandle` luôn chuyển tiếp tới target hiện tại. Tạo `CallSite` bằng tay rồi gọi `dynamicInvoker()` là cách mô phỏng cơ chế này; bản thân thao tác ấy **không chèn một lệnh `invokedynamic` mới vào bytecode**.

## 8. Ví dụ Java 17+: sáu API trong cùng một chương trình

Tạo file `DynamicRuntimeMapDemo.java`:

~~~java
import java.lang.invoke.*;
import java.lang.reflect.*;

public class DynamicRuntimeMapDemo {
    public static class Counter {
        public volatile int value;

        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    public interface Greeter {
        String greet(String name);
    }

    public static void main(String[] args) throws Throwable {
        Counter counter = new Counter();

        // Class: nhận diện kiểu
        Class<?> type = counter.getClass();
        System.out.println("Class: " + type.getSimpleName());

        // Reflection: tìm Method theo tên rồi invoke
        Method method = type.getMethod("greet", String.class);
        System.out.println("Reflection: " + method.invoke(counter, "Lan"));

        // MethodHandle: chữ ký (Counter, String)String
        MethodHandle handle = MethodHandles.lookup().findVirtual(
                Counter.class, "greet",
                MethodType.methodType(String.class, String.class));
        String invoked = (String) handle.invokeExact(counter, "Minh");
        System.out.println("MethodHandle: " + invoked);

        // VarHandle: truy cập field int với mode volatile và CAS
        VarHandle variable = MethodHandles.lookup().findVarHandle(
                Counter.class, "value", int.class);
        variable.setVolatile(counter, 10);
        boolean swapped = (boolean) variable.compareAndSet(counter, 10, 11);
        System.out.println("VarHandle CAS: " + swapped);
        System.out.println("VarHandle value: " + (int) variable.getVolatile(counter));

        // Proxy: lời gọi interface chuyển sang InvocationHandler
        Greeter proxy = (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[] { Greeter.class },
                (instance, called, values) -> {
                    if (called.getDeclaringClass() == Object.class) {
                        return switch (called.getName()) {
                            case "toString" -> "GreeterProxy";
                            case "hashCode" -> System.identityHashCode(instance);
                            case "equals" -> instance == values[0];
                            default -> throw new UnsupportedOperationException();
                        };
                    }
                    return "Hi, " + values[0];
                });
        System.out.println("Proxy: " + proxy.greet("Hoa"));

        // CallSite: target cố định
        CallSite site = new ConstantCallSite(
                MethodHandles.constant(String.class, "v1"));
        String result = (String) site.dynamicInvoker().invokeExact();
        System.out.println("CallSite constant: " + result);

        // CallSite: target có thể được thay, nhưng chữ ký ()String giữ nguyên
        MutableCallSite mutable = new MutableCallSite(
                MethodHandles.constant(String.class, "v1"));
        MethodHandle dynamic = mutable.dynamicInvoker();
        System.out.println("CallSite mutable before: " + (String) dynamic.invokeExact());
        mutable.setTarget(MethodHandles.constant(String.class, "v2"));
        MutableCallSite.syncAll(new MutableCallSite[] { mutable });
        System.out.println("CallSite mutable after: " + (String) dynamic.invokeExact());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file (Java 17 trở lên):

~~~bash
javac DynamicRuntimeMapDemo.java
java DynamicRuntimeMapDemo
~~~

`stdout` mong đợi:

~~~text
Class: Counter
Reflection: Hello, Lan
MethodHandle: Hello, Minh
VarHandle CAS: true
VarHandle value: 11
Proxy: Hi, Hoa
CallSite constant: v1
CallSite mutable before: v1
CallSite mutable after: v2
~~~

Cách đọc kết quả: `Class` cung cấp metadata của `Counter`; `Method.invoke` thực thi theo metadata; `MethodHandle.invokeExact` thực thi method đã resolve với chữ ký rõ ràng; `VarHandle` cập nhật field bằng CAS; `Proxy` tạo hành vi cho interface `Greeter`; `CallSite` giữ target cố định hoặc cho thay target có kiểm soát. Ví dụ này chạy `dynamicInvoker` trực tiếp để minh họa liên kết, không tự phát ra opcode `invokedynamic`.

## 9. Chọn cơ chế theo yêu cầu thực tế

| Yêu cầu | Điểm bắt đầu phù hợp | Vì sao |
| --- | --- | --- |
| Kiểm tra annotation, superclass, các interface, class loader | `Class<?>` | Bài toán metadata và nhận diện kiểu. |
| Plugin framework nhận tên method từ file cấu hình | Reflection (`Method` / `Constructor`) | Khám phá và thực thi thành viên theo metadata khi chưa biết ở compile time. |
| Dynamic dispatcher gọi lặp lại thao tác đã biết chữ ký | `MethodHandle` | Mô tả lời gọi typed, có thể bind/adapt/combine. |
| Thư viện concurrent cần CAS hoặc acquire/release cho field/mảng | `VarHandle` | Có access mode và memory ordering rõ ràng. |
| Thêm logging/authorization vào interface service | `Proxy` + `InvocationHandler` | Tạo object implement interface và chặn từng method call. |
| Dynamic linker muốn đổi đích của vị trí gọi | `CallSite` + `MethodHandle` | Phân tách vị trí gọi khỏi target hiện tại, giữ chữ ký bất biến. |

Ví dụ pipeline trong framework: dùng `Class.forName` để tải implementation theo tên; kiểm tra annotations bằng `Class`/reflection; tạo `MethodHandle` cho method đã chọn; bọc interface bằng `Proxy` khi muốn intercept; nếu thực hiện dynamic language linking thì `CallSite` có thể nắm MethodHandle target. Pipeline này là **một kiến trúc có thể có**, không phải chuỗi thao tác bắt buộc.

## 10. Quyền truy cập, JPMS, lỗi kiểu và hiệu năng

**Quyền truy cập:** `MethodHandles.lookup()` mang quyền của ngữ cảnh tạo lookup. `privateLookupIn(target, lookup)` chỉ hoạt động khi đáp ứng điều kiện quyền truy cập và module; nó không phải cách vượt JPMS. Với module có tên, `exports` thường dành cho API công khai; `opens` cấp quyền reflection sâu vào package theo phạm vi khai báo. `--add-opens` có thể hữu ích khi chạy tooling cần mở package, nhưng chỉ dùng khi thực sự hiểu và chấp nhận phạm vi truy cập. Không giả định `setAccessible(true)` luôn thành công.

**Lỗi thường gặp và cách chẩn đoán:**

1. `NoSuchMethodException` khi tra cứu reflection: kiểm tra tên, kiểu tham số, static/instance, public so với declared; tên trùng nhưng tham số khác không phải cùng phương thức.
2. `InvocationTargetException` từ `Method.invoke`: kiểm tra `getCause()`; lỗi business bên trong khác với lỗi reflection ngoài.
3. `WrongMethodTypeException` ở `invokeExact` hoặc khi đổi `CallSite` target: in `handle.type()`, so với kiểu đối số/kiểu kết quả tại lời gọi; đừng quên receiver instance là tham số đầu.
4. `IllegalAccessException` / `InaccessibleObjectException`: kiểm tra visibility, Lookup context, `exports` / `opens` và caller module.
5. `UnsupportedOperationException` ở `VarHandle`: kiểm tra `isAccessModeSupported(...)`, kiểu field và tính chất `final`; đừng giả định mọi phép atomic hợp lệ.
6. Proxy trả sai kiểu, thiếu hành vi `Object` methods hoặc delegate vòng lại proxy: kiểm tra contract của interface, `equals`/`hashCode`/`toString` và luồng gọi của handler.
7. Cập nhật `MutableCallSite` rồi thread khác vẫn thấy target cũ: phân tích visibility và dùng `syncAll` hoặc `VolatileCallSite` đúng yêu cầu; không suy từ kết quả chạy một luồng.

**Hiệu năng và an toàn:** nên cache kết quả tra cứu/resolve khi hợp lý, tránh nhận tên method/class không tin cậy rồi cấp quyền truy cập quá rộng, validate input và kiểm soát class loader. Không kết luận reflection luôn chậm, handle luôn nhanh hoặc proxy luôn tốn chi phí đáng kể: đo với JMH, có warm-up, đúng đường gọi, đúng kiểu dữ liệu và tải thực. Đối với code ứng dụng bình thường, lời gọi Java trực tiếp vẫn là lựa chọn đơn giản và dễ kiểm tra nhất khi biết kiểu tại compile time.

## 11. Tự kiểm tra

- Cần đọc tất cả annotations của một class, đã biết object tại runtime: dùng gì? → `obj.getClass()` và API metadata của `Class` (hoặc `AnnotatedElement`).
- Đã tìm được `MethodHandle` có type `(String)int`; lời gọi `(Object)int` qua `invokeExact` có khớp không? → Không; phải khớp chính xác hoặc thích nghi handle/kiểu gọi hợp lệ.
- Muốn update `int` theo CAS giữa threads: dùng `MethodHandle` hay `VarHandle`? → `VarHandle` (hoặc các atomic abstraction phù hợp).
- Muốn intercept method của một interface nhưng không đổi interface: dùng gì? → JDK `Proxy` với `InvocationHandler`.
- Vì sao `MutableCallSite.setTarget` chưa đủ để mọi thread thấy target mới ngay? → Vì không có bảo đảm visibility tương đương volatile; xem `syncAll` hoặc `VolatileCallSite`.
- Có thể đổi target của `MutableCallSite` từ `(String)int` sang `(String)String` không? → Không; `MethodType` của target mới phải giữ nguyên.

## Tham khảo API chuẩn (Java SE 21)

- [Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Reflection: Method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [MethodHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [VarHandle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Proxy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html) và [InvocationHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [CallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html), [MutableCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MutableCallSite.html) và [VolatileCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
