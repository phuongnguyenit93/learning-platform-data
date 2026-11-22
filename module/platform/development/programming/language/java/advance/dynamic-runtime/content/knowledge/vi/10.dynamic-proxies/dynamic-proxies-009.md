# 10.9. Gọi phương thức mặc định qua `InvocationHandler.invokeDefault`

Java dynamic proxy (proxy động) tạo đối tượng triển khai một hoặc nhiều interface tại runtime và chuyển các lời gọi phương thức vào một `InvocationHandler`. Điều dễ nhầm là **một phương thức `default` trong interface không tự động chạy thân mặc định khi được gọi trên dynamic proxy**: lời gọi cũng đi qua handler. Nếu muốn thực thi đúng thân `default`, từ Java 16 có thể dùng API chuẩn:

```java
InvocationHandler.invokeDefault(proxy, method, args);
```

Đây là phương thức **`static`** của `java.lang.reflect.InvocationHandler`, không phải method của đối tượng handler. Nó thực hiện lời gọi đặc biệt tới phần thân `default` của interface, tương đương về ngữ nghĩa với một lời gọi `InterfaceName.super.method(...)` hợp lệ từ proxy class. Bài này giải thích cơ chế, điều kiện hợp lệ của `Method`, xử lý tham số, đa kế thừa/default trùng tên, ngoại lệ và ví dụ Java 17+ hoàn chỉnh.

## 1. Vì sao dynamic proxy cần `invokeDefault`?

Trong một class thông thường, interface có thể cung cấp hành vi mặc định:

```java
interface Greeting {
    String prefix(String name);

    default String greet(String name) {
        return prefix(name) + name;
    }
}
```

Class tự triển khai `Greeting` có thể kế thừa `greet` và dùng thân mặc định đó. Nhưng với dynamic proxy:

```java
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        handler);
```

**Mọi lời gọi qua interface của proxy**, bao gồm `greet` là default, được chuyển vào:

```java
Object invoke(Object proxy, Method method, Object[] args)
        throws Throwable;
```

`Proxy` cung cấp cơ chế dispatch vào handler; nó không mặc định quyết định rằng `method.isDefault() == true` thì chạy code của interface. Handler phải chọn một hành vi:

- Trả kết quả do handler tự tính.
- Ủy quyền cho service/đối tượng đích thật.
- **Chạy thân default** với `InvocationHandler.invokeDefault(...)`.
- Từ chối lời gọi bằng exception có chủ đích.

Chẳng hạn, default method `greet` sẽ gọi `prefix(name)`; khi `greet` được thực thi trên proxy, lệnh `prefix` trong thân default **vẫn đi qua handler**, bởi `this` của thân default là proxy. Đây là một lợi ích thiết kế: default method có thể phối hợp các lời gọi abstract/interface được handler cung cấp.

**Điểm cốt lõi:** `invokeDefault` vượt qua dispatch của handler **đối với chính lời gọi thân default được chọn**. Nó không biến mọi lời gọi bên trong thân default thành lời gọi trực tiếp: các lời gọi virtual/interface tiếp theo trên proxy vẫn có thể quay lại handler.

## 2. API, phiên bản Java và chữ ký

Trong Java SE 17, API có chữ ký:

```java
public static Object invokeDefault(
        Object proxy, Method method, Object... args)
        throws Throwable;
```

Ý nghĩa từng tham số:

| Tham số | Ý nghĩa | Ràng buộc |
| --- | --- | --- |
| `proxy` | **Đối tượng dynamic proxy** sẽ đóng vai `this` của default method | Phải là instance proxy do `java.lang.reflect.Proxy` tạo; không chấp nhận `null` hoặc đối tượng thường |
| `method` | Metadata của default method cần chạy | Phải là default method hợp lệ được khai báo trong proxy interface hoặc kế thừa hợp lệ từ superinterface, không bị override làm target không còn phân giải được |
| `args` | Những tham số thực sự truyền vào default method | Số lượng và kiểu tương thích với tham số chính thức; có thể truyền `null` nếu phương thức không nhận tham số |

Kiểu trả về `Object` là giá trị trả về của default method (primitive được boxing khi cần; default `void` không có kết quả hữu ích). Phần thân default có thể ném lỗi; API khai báo `throws Throwable` để truyền exception từ mã đích.

**Tính sẵn có:** `InvocationHandler.invokeDefault` được thêm từ **Java 16**. Ví dụ trong bài biên dịch bằng `javac --release 17`. Nếu dự án dùng API level Java 8/11, không thể gọi trực tiếp method mới này; cần xem lại mức runtime tối thiểu hoặc một chiến lược tương thích khác. Không giả định việc một đoạn mã dùng reflection để né compile-time sẽ làm API tồn tại ở JDK cũ.

Ví dụ tối thiểu ở vị trí handler:

```java
InvocationHandler handler = (proxy, method, arguments) -> {
    if (method.isDefault()) {
        return InvocationHandler.invokeDefault(proxy, method, arguments);
    }
    // Xử lý các lời gọi không có thân default theo contract ứng dụng.
    throw new UnsupportedOperationException(method.getName());
};
```

Đoạn trên **chỉ minh họa nhánh `default`**; phần còn lại của handler cần xử lý các phương thức abstract và phương thức `Object` phù hợp. Ví dụ chạy độc lập ở mục 7 bao gồm các nhánh đó.

## 3. Luồng dispatch: từ proxy tới thân `default`

Sơ đồ logic cho `greeting.greet("Lan")`:

```text
Caller -> proxy.greet("Lan")
          |
          v
 InvocationHandler.invoke(proxy, method=greet, args=["Lan"])
          |
          +-- method.isDefault() == true
          |
          v
 InvocationHandler.invokeDefault(proxy, method, args)
          |
          v
 Thực thi phần thân Greeting.default greet("Lan")
          |
          +-- thân default gọi prefix("Lan") trên this = proxy
                         |
                         v
              InvocationHandler.invoke(..., method=prefix, ...)
                         |
                         v
              Handler trả prefix, ví dụ "Hi, "
          |
          v
 Default method trả "Hi, Lan"
          |
          v
 Handler trả kết quả cho caller
```

`invokeDefault` làm việc tương đương một chỉ thị `invokespecial` hướng tới **thân default của interface** được chọn. Điều này khác với `Method.invoke(proxy, arguments)`:

- `InvocationHandler.invokeDefault(proxy, method, args)` chọn đúng thân default, không tự dispatch cùng lời gọi đó trở lại handler.
- `method.invoke(proxy, args)` là lời gọi reflection thông thường trên proxy; nó có thể **dispatch lại chính handler**. Nếu thực hiện nó bên trong nhánh xử lý cùng method, dễ tạo vòng lặp đệ quy vô hạn và `StackOverflowError`.
- `method.invoke(realTarget, args)` có thể hợp lệ nếu ứng dụng đang ủy quyền cho một **đối tượng thực sự** triển khai interface; đây là một cơ chế khác, không tương đương việc gọi thân default trên chính proxy.

**Không** dùng `method.invoke(proxy, args)` như một cách thay thế `invokeDefault` trong handler để “gọi về implementation mặc định”.

## 4. Phải truyền đúng `Method`: `isDefault` chưa đủ

`Method.isDefault()` cho biết một `Method` là default method của interface (khác phương thức abstract, static, private interface method). Nó hữu ích để rẽ nhánh, nhưng **chưa chứng minh method này hợp lệ đối với một proxy cụ thể**.

Để `invokeDefault(proxy, method, args)` hợp lệ, method phải là một default method mà proxy interface trực tiếp hoặc gián tiếp **có thể gọi qua quy tắc phân giải default method**. Nói cách khác, hành vi phải tương đương một lời gọi `X.super.m(...)` hợp lệ từ proxy class.

Vì vậy:

1. Phương thức `default` khai báo trực tiếp trong một interface mà proxy implements có thể là target.
2. Phương thức `default` được **kế thừa** từ superinterface (và không bị override làm mất khả năng phân giải tới thân đó) cũng có thể là target.
3. Phương thức `default` ở interface **không liên quan** tới proxy là target **không hợp lệ**, dù `method.isDefault()` trả `true`.
4. Nếu một proxy interface **override** thân default của superinterface, việc cố gọi `Method` cũ của superinterface có thể bị từ chối, vì nó không còn là method mà lời gọi `X.super.m` có thể phân giải tới.
5. Một phương thức **abstract** hoặc `static` không trở thành default method chỉ vì cùng tên/chữ ký với một method khác.

Ví dụ, với:

```java
interface Base {
    default String source() { return "base"; }
}
interface Inherited extends Base {}
interface Overridden extends Base {
    @Override
    default String source() { return "overridden"; }
}
```

Proxy chỉ implements `Inherited` có thể gọi thân `Base.source` vì `Inherited` thừa kế default đó. Proxy chỉ implements `Overridden` có thể gọi `Overridden.source`, nhưng không được cố gọi `Base.source` bằng `invokeDefault` như thể phiên bản override chưa tồn tại.

**Hệ quả khi nâng cấp thư viện:** Một handler lưu sẵn `Base.class.getMethod("source")` và dùng nó qua mọi phiên bản của `Derived` có thể hỏng sau khi `Derived` bổ sung override của `source`. Đó không chỉ là thay đổi kết quả; lời gọi `invokeDefault` tới method cũ có thể ném `IllegalArgumentException`. Nên kiểm tra version/interface graph và tránh giả định mọi default method ở ancestor luôn hợp lệ mãi mãi.

## 5. Hai interface cùng có default method: chọn implementation có chủ đích

Giả sử:

```java
interface Left {
    default String label() { return "left"; }
}
interface Right {
    default String label() { return "right"; }
}
```

Một class thường không thể triển khai hai default trùng signature mà không giải quyết xung đột. Dynamic proxy có thể implement cả `Left` và `Right`, vì phương thức trên proxy được dispatch tới handler, và handler có thể chọn thân default nào bằng `invokeDefault`.

Điểm quan trọng: khi proxy được tạo từ danh sách:

```java
new Class<?>[]{Left.class, Right.class}
```

một lời gọi `label()` có thể mang vào handler đối tượng `Method` thuộc **interface đứng trước trong danh sách** (ở đây `Left`), ngay cả khi caller gọi qua biến `Right`. Proxy không tự biết caller dùng static interface reference nào để quyết định method cùng signature.

Vì vậy, code handler như sau có thể **không** chọn thân default người dùng mong đợi:

```java
// method có thể là Left.label() cho cả hai kiểu reference.
return InvocationHandler.invokeDefault(proxy, method, args);
```

Nếu hợp đồng ứng dụng chọn **Right** cho cả hai đường gọi, hãy chọn `Right.class.getMethod("label")` tường minh:

```java
InvocationHandler chooseRight = (proxy, method, args) -> {
    Method rightMethod = Right.class.getMethod("label");
    return InvocationHandler.invokeDefault(proxy, rightMethod, args);
};
```

Đoạn này chỉ đúng khi handler gắn với proxy implements cả `Left` và `Right`, và đang xử lý lời gọi `label`; trong code thực tế cần rẽ nhánh theo tên/chữ ký, tránh áp dụng mọi `Method` vào một default method duy nhất. Chương trình đầy đủ bên dưới tạo proxy đúng ngữ cảnh và cho thấy cả `((Left) proxy).label()` lẫn `((Right) proxy).label()` đều có thể trả `"right"`.

**Không nhầm với việc `Method` được truyền vào handler:** Nó là metadata mô tả phương thức proxy dispatch, không bắt buộc phải được đưa nguyên vẹn vào `invokeDefault`. Khi chọn method khác, phải bảo đảm method đó vẫn thuộc các default target hợp lệ của proxy.

## 6. Tham số, `null`, primitive và varargs

### 6.1. Mảng `Object[] args` của handler

`InvocationHandler.invoke(proxy, method, args)` nhận một `Object[]` chứa các đối số đã boxing primitive. Với phương thức **không có tham số**, JVM có thể truyền `args == null`. `invokeDefault` cũng chấp nhận `args == null` khi method đích có **0 tham số**.

Chuyển tiếp tự nhiên:

```java
if (method.isDefault()) {
    return InvocationHandler.invokeDefault(proxy, method, args);
}
```

Cú pháp này sử dụng `args` kiểu `Object[]` cho tham số varargs `Object...` của `invokeDefault`, do đó truyền **các phần tử của mảng** làm đối số cho default method. Nếu handler nhận `args == null` khi method không có tham số, lời gọi vẫn hợp lệ. Có thể chuẩn hóa bằng `args == null ? new Object[0] : args` nếu ứng dụng cần một mảng không null cho xử lý riêng, nhưng không bắt buộc để gọi default method 0 tham số.

### 6.2. Số lượng đối số và unboxing phải phù hợp

Với:

```java
interface NumberOps {
    default int twice(int n) { return n * 2; }
}
```

Giả sử `numberProxy` đã được tạo để implement `NumberOps` và `twice` là `NumberOps.class.getMethod("twice", int.class)`:

```java
Object ok = InvocationHandler.invokeDefault(
        numberProxy, twice, 6);              // Integer(12)
Object bad = InvocationHandler.invokeDefault(
        numberProxy, twice, (Object) null);  // IllegalArgumentException
```

Đoạn này là minh họa, biến `numberProxy`/`twice` phải được tạo trước. Primitive `int` được boxing thành `Integer` trên ranh giới Object/varargs và được unboxing khi thực thi default method. `null` không thể unbox thành `int`. `invokeDefault` có thể ném **`IllegalArgumentException`** nếu số hoặc kiểu đối số không khớp, bao gồm unboxing thất bại như trường hợp này. Đây là lỗi **đối số đầu vào**, không phải ngoại lệ do thân `twice` tự ném.

### 6.3. Khi chính phương thức đích nhận một mảng

Ví dụ default method nhận một tham số `String[]`:

```java
interface Tags {
    default int count(String[] tags) { return tags.length; }
}
```

Nếu gọi `invokeDefault` từ ngoài handler và muốn truyền mảng như **một đối số**, tránh để Java trải phần tử mảng qua `Object...`:

```java
// Giả định tagProxy implements Tags và countMethod là Tags.count(String[]).
int n = (int) InvocationHandler.invokeDefault(
        tagProxy, countMethod, (Object) new String[]{"a", "b"});
```

Cast `(Object)` buộc mảng `String[]` được truyền như **một phần tử** của varargs; không nhầm số lượng tham số của `count(String[])` với độ dài của `tags`. Nếu nhận lời gọi thông thường `tagsProxy.count(array)` trong handler thì `args` đã có **một phần tử là mảng `String[]`**; chuyển thẳng `args` cho `invokeDefault` là đúng.

Không dùng cast/bao mảng tùy tiện: `invokeDefault(proxy, method, new Object[]{args})` sẽ truyền nguyên `Object[] args` làm *một* tham số, thường sai với method có nhiều tham số.

## 7. Ví dụ Java 17+ hoàn chỉnh: default, kế thừa, trùng method, override và lỗi

Lưu **toàn bộ** chương trình dưới đây thành file `ProxyDefaultMethodsDemo.java`. Các interface được khai báo `public` lồng trong class public để tránh phụ thuộc package ngoài; chương trình dùng duy nhất các API chuẩn của `java.base`. Khi biên dịch, JVM có thể sinh các file `.class` phụ cho nested interface như bình thường.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class ProxyDefaultMethodsDemo {
    public interface Greeter {
        String prefix(String name);
        default String greet(String name) { return prefix(name) + name; }
        default String signature() { return "from-Greeter"; }
        default int doubleNumber(int n) { return n * 2; }
    }

    public interface Left {
        default String label() { return "left"; }
    }

    public interface Right {
        default String label() { return "right"; }
    }

    public interface Base {
        default String source() { return "base"; }
    }

    public interface Inherited extends Base {}

    public interface Overridden extends Base {
        @Override
        default String source() { return "overridden"; }
    }

    public interface Failure {
        default void crash() {
            throw new IllegalStateException("from-default");
        }
    }

    public static void main(String[] args) throws Throwable {
        InvocationHandler greeterHandler = (proxy, method, arguments) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreeterProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == arguments[0];
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }
            if (method.isDefault()) {
                return InvocationHandler.invokeDefault(proxy, method, arguments);
            }
            if (method.getName().equals("prefix")) {
                return "Hi, ";
            }
            throw new UnsupportedOperationException(method.getName());
        };

        Greeter g = (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[] {Greeter.class}, greeterHandler);

        System.out.println("greet=" + g.greet("Lan"));
        System.out.println("signature=" + g.signature());
        System.out.println("toString=" + g);
        System.out.println("double=" + g.doubleNumber(4));

        Method greetMethod = Greeter.class.getMethod("greet", String.class);
        System.out.println("isDefault=" + greetMethod.isDefault());
        System.out.println("direct=" +
                InvocationHandler.invokeDefault(g, greetMethod, "Mai"));

        Method twice = Greeter.class.getMethod("doubleNumber", int.class);
        System.out.println("directDouble=" +
                InvocationHandler.invokeDefault(g, twice, 6));

        InvocationHandler chooseRight = (proxy, method, arguments) -> {
            Method right = Right.class.getMethod("label");
            return InvocationHandler.invokeDefault(proxy, right, arguments);
        };
        Left both = (Left) Proxy.newProxyInstance(
                Left.class.getClassLoader(),
                new Class<?>[] {Left.class, Right.class}, chooseRight);

        System.out.println("twoDefaults.left=" + both.label());
        System.out.println("twoDefaults.right=" + ((Right) both).label());

        Inherited inherited = (Inherited) Proxy.newProxyInstance(
                Inherited.class.getClassLoader(),
                new Class<?>[] {Inherited.class},
                (proxy, method, arguments) ->
                        InvocationHandler.invokeDefault(
                                proxy, method, arguments));
        System.out.println("inherited=" + inherited.source());

        Overridden overridden = (Overridden) Proxy.newProxyInstance(
                Overridden.class.getClassLoader(),
                new Class<?>[] {Overridden.class},
                (proxy, method, arguments) ->
                        InvocationHandler.invokeDefault(
                                proxy, method, arguments));
        System.out.println("overridden=" + overridden.source());

        try {
            Method obsolete = Base.class.getMethod("source");
            InvocationHandler.invokeDefault(overridden, obsolete);
        } catch (IllegalArgumentException e) {
            System.out.println("overridden.base="
                    + e.getClass().getSimpleName());
        }

        try {
            InvocationHandler.invokeDefault(g, greetMethod);
        } catch (IllegalArgumentException e) {
            System.out.println("badArity=" + e.getClass().getSimpleName());
        }

        try {
            InvocationHandler.invokeDefault(g, twice, (Object) null);
        } catch (IllegalArgumentException e) {
            System.out.println("badPrimitive=" + e.getClass().getSimpleName());
        }

        try {
            InvocationHandler.invokeDefault(
                    g, Greeter.class.getMethod("prefix", String.class), "A");
        } catch (IllegalArgumentException e) {
            System.out.println("notDefault=" + e.getClass().getSimpleName());
        }

        try {
            InvocationHandler.invokeDefault(
                    new Object(), greetMethod, "Hoa");
        } catch (IllegalArgumentException e) {
            System.out.println("notProxy=" + e.getClass().getSimpleName());
        }

        Failure failure = (Failure) Proxy.newProxyInstance(
                Failure.class.getClassLoader(),
                new Class<?>[] {Failure.class},
                (proxy, method, arguments) ->
                        InvocationHandler.invokeDefault(
                                proxy, method, arguments));
        try {
            failure.crash();
        } catch (IllegalStateException e) {
            System.out.println("targetException="
                    + e.getClass().getSimpleName() + ":" + e.getMessage());
        }
    }
}
```

Mở terminal ở thư mục chứa file và chạy:

```bash
javac --release 17 ProxyDefaultMethodsDemo.java
java ProxyDefaultMethodsDemo
```

Kết quả **`stdout` chính xác** của chương trình:

```text
greet=Hi, Lan
signature=from-Greeter
toString=GreeterProxy
double=8
isDefault=true
direct=Hi, Mai
directDouble=12
twoDefaults.left=right
twoDefaults.right=right
inherited=base
overridden=overridden
overridden.base=IllegalArgumentException
badArity=IllegalArgumentException
badPrimitive=IllegalArgumentException
notDefault=IllegalArgumentException
notProxy=IllegalArgumentException
targetException=IllegalStateException:from-default
```

### 7.1. Giải thích những điểm quan trọng

**`greet=Hi, Lan`:** handler nhận `Greeter.greet` là default, dùng `invokeDefault` chạy thân mặc định; bên trong, `prefix("Lan")` gọi lại proxy nên handler nhận `prefix` và trả `"Hi, "`. Đây là **re-entry có chủ đích**, không phải vòng lặp gọi lại cùng `greet`.

**`signature=from-Greeter`:** `signature` không có tham số; trong handler, mảng `arguments` có thể `null`. `invokeDefault(proxy, method, arguments)` xử lý hợp lệ trường hợp 0 tham số. **`toString=GreeterProxy`**: phương thức `Object.toString` không phải interface default method, nên handler xử lý riêng.

**`double=8` và `directDouble=12`:** default method trả primitive `int`; handler trả giá trị dưới dạng `Object`, ứng dụng nhận đúng primitive qua cơ chế boxing/unboxing của proxy. Lời gọi trực tiếp `invokeDefault` trả về một `Integer` ở vị trí `Object`.

**`twoDefaults.left=right` và `twoDefaults.right=right`:** proxy implements cả `Left` lẫn `Right`, nhưng handler cố ý chọn `Right.label`. Chọn implementation là **chính sách của handler**, không phải do static type `Left`/`Right` của biểu thức caller tự quyết định.

**`inherited=base`:** proxy implements `Inherited`, và `Inherited` kế thừa default method `Base.source` hợp lệ, nên có thể gọi thân `Base`.

**`overridden=overridden` / `overridden.base=IllegalArgumentException`:** khi `Overridden` đã override `Base.source`, method có thể gọi mặc định là `Overridden.source`; cố cưỡng ép `Base.source` theo đường `invokeDefault` với proxy chỉ implements `Overridden` bị từ chối.

**`badArity`, `badPrimitive`, `notDefault`, `notProxy`:** lần lượt kiểm tra sai số tham số, `null` cho `int`, chọn abstract method không phải default, và đối tượng không phải dynamic proxy.

**`targetException=IllegalStateException:from-default`:** ngoại lệ do **chính thân default** ném được truyền đến handler/caller, không được `invokeDefault` tự bọc trong `InvocationTargetException`.

## 8. Ngoại lệ và lỗi: phân biệt nơi phát sinh

### 8.1. Lỗi chuẩn bị lời gọi `invokeDefault`

| Ngoại lệ | Điều kiện điển hình | Cách xử lý |
| --- | --- | --- |
| `NullPointerException` | `proxy == null` hoặc `method == null` | Kiểm tra tham chiếu trước khi gọi |
| `IllegalArgumentException` | `proxy` không phải dynamic proxy, `Method` không phải default target hợp lệ hoặc không thuộc interface của proxy | Kiểm tra proxy interfaces, `method.isDefault()`, declaring class và override chain |
| `IllegalArgumentException` | Số lượng/kiểu argument sai, không thể unbox primitive, hoặc value không gán được vào parameter | So sánh `method.getParameterTypes()` và mảng đối số |
| `IllegalAccessException` | Declaring class của default method không truy cập được từ caller | Kiểm tra visibility, package/module và API public |
| `Throwable` do default body ném | Thực thi đã đi vào thân default rồi bị lỗi | Xử lý ngoại lệ của nghiệp vụ; không đổ lỗi tự động cho chữ ký reflection |

`NoSuchMethodException` có thể đến từ thao tác **tìm Method** bằng `Interface.class.getMethod(...)`; nó không phải ngoại lệ của bản thân `invokeDefault` khi đã có đúng `Method`.

**Lưu ý:** Với default method kiểu `void`, `invokeDefault` trả về `Object` nhưng không có giá trị nghiệp vụ để dùng. Với default method trả primitive, kết quả được boxing để đáp ứng return `Object`. Khi handler trả `null` cho một interface method có primitive return type, lần gọi qua proxy có thể ném `NullPointerException` do unboxing ở ranh giới proxy; đó không phải cách bình thường để đại diện giá trị `0`/`false`.

### 8.2. Lỗi từ thân default không tự biến thành `InvocationTargetException`

Hai API tên tương tự nhưng semantics khác nhau:

```java
// Gọi thân default theo special invocation:
InvocationHandler.invokeDefault(proxy, defaultMethod, args);

// Gọi phản chiếu Method.invoke theo dispatch thông thường:
defaultMethod.invoke(proxy, args);
```

`Method.invoke` dùng reflection thông thường và bọc exception do target ném bằng `InvocationTargetException`; khi receiver là proxy, target về mặt dispatch là phương thức trên proxy và có thể quay lại handler. `InvocationHandler.invokeDefault` là lối gọi **thân default** và truyền `Throwable` từ thân đó theo contract của nó. Đừng bắt `InvocationTargetException` từ `invokeDefault` như thể đó luôn là wrapper do API này tạo ra.

Nếu một default method tự ném `IllegalStateException`, handler gọi `invokeDefault` có thể nhận thẳng exception đó. Nếu handler để một **checked exception không được khai báo** thoát khỏi `InvocationHandler.invoke`, lời gọi thông qua proxy có thể bọc checked exception trong `UndeclaredThrowableException` theo quy tắc của dynamic proxy. Đây là **bước kiểm tra ở ranh giới proxy method**, không phải sự bọc `InvocationTargetException` của `invokeDefault`.

Trong hệ thống thực tế, nên có chính sách exception rõ ràng: giữ nguyên các checked exception đã khai báo của interface; log/cấp context cho lỗi nghiệp vụ; bảo toàn cause và stack trace; tránh bắt hết `Throwable` rồi âm thầm trả `null`.

## 9. Visibility, module và thay đổi interface theo thời gian

`InvocationHandler.invokeDefault` chỉ có thể gọi method phù hợp với quy tắc truy cập. Nếu declaring class không truy cập được từ caller, API có thể ném **`IllegalAccessException`**. Việc tạo thành công dynamic proxy không nhất thiết bảo đảm **mọi default method mà code truy xuất tùy ý** đều có thể gọi từ mọi module.

Với Java Platform Module System (JPMS):

- Interface cần được nhìn thấy/đủ điều kiện để tạo proxy theo luật của `Proxy.newProxyInstance`.
- Default method cần hợp lệ và declaring interface phải truy cập được trong ngữ cảnh caller.
- Không mặc định dùng `setAccessible(true)` hoặc `--add-opens` làm cách sửa mọi `IllegalAccessException`: đây không phải thao tác `Field.set` hay `Method.invoke` thông thường. Trước hết xác định lỗi là **lookup**, **proxy eligibility**, **access** hay **target exception**.
- Khi nâng cấp thư viện, thêm override default vào một subinterface có thể làm `Method` cũ từ parent không còn là target gọi được. Đặc biệt nguy hiểm nếu handler cache metadata theo tên/chữ ký mà không kiểm tra lại interface graph.

Dự án cần tương thích nhiều phiên bản interface nên có **integration test** cho các trường hợp inherited default, override, duplicate signature và interface mới thêm default method. Nếu API được xây dựng để chọn một implementation cụ thể, lưu rõ chính sách chọn interface thay vì suy đoán từ `method.getDeclaringClass()` của invocation được proxy dispatch.

## 10. Cách tổ chức handler thực tế

Một handler cho production nên tách các nhánh:

1. Xử lý `Object.equals`, `hashCode` và `toString` theo semantics mong muốn. Chúng được dispatch vào handler với `Method` khai báo từ `Object`; không phải default methods. Nếu code handler tự gọi `proxy.toString()` trong nhánh `toString` để log, có thể vô tình đệ quy.
2. Xử lý method có hành vi custom/ủy quyền service theo contract và kiểm tra kiểu return.
3. Với default method hợp lệ, gọi `InvocationHandler.invokeDefault(proxy, method, args)`.
4. Với method abstract chưa có handler, trả lỗi minh bạch như `UnsupportedOperationException` thay vì `null`; đặc biệt tránh `null` cho primitive return type.
5. Bảo toàn exceptions phù hợp interface và làm rõ chính sách xử lý khi nhiều interfaces có method trùng signature.

Khung handler (minh họa; chưa phải chương trình độc lập):

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.getDeclaringClass() == Object.class) {
        // Xử lý equals/hashCode/toString có chủ đích.
        return handleObjectMethod(proxy, method, args);
    }
    if (isCustomMethod(method)) {
        return invokeCustomBehavior(method, args);
    }
    if (method.isDefault()) {
        return InvocationHandler.invokeDefault(proxy, method, args);
    }
    throw new UnsupportedOperationException(method.toString());
};
```

Các hàm `handleObjectMethod`, `isCustomMethod` và `invokeCustomBehavior` chỉ là **điểm mở rộng minh họa**; cần viết implementation thực tế. Không nên lắp trực tiếp đoạn khung vào project khi chưa định nghĩa các hàm. Chương trình ở mục 7 là code đầy đủ đã chạy.

**Về hiệu năng:** `invokeDefault` hữu ích vì tránh yêu cầu caller tự dựng các `MethodHandles.Lookup`/adapter để gọi thân mặc định trên proxy. Nhưng vẫn có chi phí runtime của proxy/handler và có thể có thêm lượt dispatch từ thân default sang handler. Ưu tiên thiết kế đúng và đo hiệu năng trong hệ thống thực tế trước khi tối ưu.

## 11. Những lỗi suy luận phổ biến

| Suy luận sai | Thực tế | Cách sửa |
| --- | --- | --- |
| “Proxy implements interface thì default body sẽ tự chạy” | Mọi lời gọi qua interface đều vào handler | Rẽ nhánh `method.isDefault()` và gọi `invokeDefault` nếu muốn hành vi mặc định |
| “Cứ `method.invoke(proxy, args)` là chạy thân default” | Có thể quay lại handler/đệ quy | Dùng `InvocationHandler.invokeDefault` cho thân default |
| “`method.isDefault()` nghĩa là dùng được trên mọi proxy” | Method cần thuộc proxy interface/inherited target hợp lệ | Kiểm tra proxy interfaces và override chain |
| “Caller dùng `Right` thì handler chắc chắn nhận `Right.label`” | Method trùng signature phụ thuộc thứ tự interface proxy | Chọn `Right.class.getMethod(...)` nếu đó là chính sách cần |
| “Parent default luôn gọi được dù child override” | Override có thể làm lời gọi `Parent.super` tương đương không còn hợp lệ | Dùng method thuộc implementation hiện hành |
| “`args == null` tức là luôn thiếu tham số” | Handler có thể nhận `null` khi method 0 tham số | Cho phép `null` với arity 0, kiểm tra arity với method khác |
| “Mảng là nhiều tham số của method đích” | Mảng có thể là **một tham số**; varargs của helper dễ trải mảng | Dùng `(Object) array` khi gọi trực tiếp |
| “`invokeDefault` luôn bọc lỗi target trong `InvocationTargetException`” | API truyền `Throwable` của thân default trực tiếp | Bắt đúng exception, phân biệt `Method.invoke` |
| “`toString` là interface default” | Proxy xử lý `Object` methods qua handler | Tách nhánh `Object.class` |
| “Thấy `IllegalArgumentException` là do body default ném” | Có thể là proxy/method/args không hợp lệ trước invocation | Đọc stack trace và kiểm tra giai đoạn lỗi |

## 12. Bài tập tự kiểm tra

**A.** `interface A { default String id(){ return "A"; } }`. Handler trả `"custom"` cho mọi method và không gọi `invokeDefault`. `((A) proxy).id()` trả gì? Vì sao?

**B.** Handler nhận `method` là `A.id` và làm `method.invoke(proxy)`, trong khi handler vẫn chạy logic tương tự mỗi lần. Nguy cơ gì? Vì sao không gọi được body mặc định đúng cách?

**C.** Proxy implements `Left` và `Right`, cả hai đều có `default String label()`. Handler muốn luôn trả thân `Right.label`. Nên làm gì thay vì tin rằng static type của caller cho biết interface nào?

**D.** Proxy chỉ implements `Child extends Parent`, `Child` kế thừa `Parent.default m()`. `InvocationHandler.invokeDefault(proxy, Parent.class.getMethod("m"))` có thể hợp lệ không? Nếu `Child` override `m` bằng một default mới thì điều gì thay đổi?

**E.** Một `default int twice(int n)` được gọi bằng `InvocationHandler.invokeDefault(proxy, method, (Object) null)`. Có thể mong nhận `0` không? Vì sao?

**F.** `default void run() { throw new IllegalStateException("bad"); }`. Handler gọi `invokeDefault`. Ngoại lệ trong handler là `IllegalStateException` trực tiếp hay mặc định `InvocationTargetException`?

**G.** Handler nhận `args == null` cho `default String ping()` không có tham số. Có cần tạo `new Object[]{null}` để gọi default không?

**Đáp án:**

- **A:** Trả `"custom"`. Proxy không tự chạy thân default; kết quả do handler quyết định.
- **B:** Có thể đệ quy qua handler và cuối cùng `StackOverflowError`. `Method.invoke(proxy)` vẫn dispatch lời gọi trên proxy; dùng `invokeDefault` để chạy thân default đã chọn.
- **C:** Truy xuất `Right.class.getMethod("label")` và truyền `Method` đó vào `invokeDefault`, với điều kiện proxy thật sự implements `Right` và method là default target hợp lệ.
- **D:** Có thể hợp lệ khi `Child` chỉ kế thừa `Parent.m`. Nếu `Child` override, method `Parent.m` có thể không còn là default target hợp lệ và `invokeDefault` ném `IllegalArgumentException`; dùng `Child.m`.
- **E:** Không. `null` không unbox thành `int`; với args sai, `invokeDefault` ném `IllegalArgumentException`.
- **F:** Thân default ném `IllegalStateException`, `invokeDefault` truyền lỗi đó trực tiếp. `InvocationTargetException` là wrapper thường thấy từ `Method.invoke`, không phải mặc định ở đây.
- **G:** Không. `null` làm danh sách đối số được API chấp nhận khi arity 0. `new Object[]{null}` sẽ thành **một** đối số, sai arity.

## 13. Nguồn chính thức Java 17

- [Oracle Javadoc: `InvocationHandler.invokeDefault`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html#invokeDefault(java.lang.Object,java.lang.reflect.Method,java.lang.Object...)): signature, `invokespecial`, inherited/default override, quy tắc `args` và các ngoại lệ.
- [Oracle Javadoc: `Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): dispatch vào handler, phương thức trùng signature, `Object` methods và quy tắc module.
- [Oracle Javadoc: `Method.isDefault`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#isDefault()): nhận diện method default của interface.
- [Java SE 17 JLS `9.4.3 — Interface Method Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.3): quy tắc về các phương thức default trong interface.

**Ghi nhớ:** Dynamic proxy **không tự động chạy thân default**; `InvocationHandler.invokeDefault(proxy, method, args)` thực thi một **default method hợp lệ** trên chính proxy bằng special invocation. Chọn `Method` đúng interface, chú ý inherited/override/duplicate methods, chuyển đúng số và kiểu args, và phân biệt lỗi chuẩn bị lời gọi với exception phát sinh trong thân default.
