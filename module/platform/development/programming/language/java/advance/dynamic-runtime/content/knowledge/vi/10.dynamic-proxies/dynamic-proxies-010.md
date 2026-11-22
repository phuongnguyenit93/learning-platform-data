# 10.10. Phương thức trùng giữa nhiều interface, thứ tự interface và giới hạn throws

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu cơ chế của **JDK dynamic proxy** khi một đối tượng proxy đồng thời implements nhiều interface có **phương thức cùng tên và cùng danh sách kiểu tham số**.
2. Giải thích vì sao **thứ tự các interface** trong `Proxy.newProxyInstance(...)` quyết định đối tượng `Method` nào được đưa vào `InvocationHandler.invoke(...)`, **không phụ thuộc kiểu reference dùng để gọi** trong trường hợp phương thức trùng có cùng kiểu JVM.
3. Biết ngoại lệ đặc biệt đối với `equals`, `hashCode` và `toString` (ưu tiên `java.lang.Object`), và ảnh hưởng khi method đến từ interface cha.
4. Áp dụng chính xác **giới hạn checked exceptions**: handler chỉ được để thoát trực tiếp throwable checked tương thích với **throws clause của tất cả các method trùng**; nếu vi phạm, proxy ném `UndeclaredThrowableException`.
5. Kiểm tra điều kiện tương thích **return type** khi tạo proxy (primitive/`void` phải trùng; reference cần có kiểu trả về tương thích), và hiểu hậu quả nếu handler trả giá trị không đúng.
6. Viết và chạy ví dụ Java 17+ minh họa thứ tự interface, checked exception chồng lấn/không giao nhau, covariant returns, phương thức `Object` và lỗi bọc kép khi delegate qua reflection.
7. Thiết kế `InvocationHandler` không phụ thuộc sai vào `Method.getDeclaringClass()` để đoán kiểu interface mà caller đã dùng.

**Ngữ cảnh:** Java dynamic proxy thuộc `java.lang.reflect.Proxy`, không phải một class con sinh từ target cụ thể. Proxy triển khai danh sách **interface** và chuyển các lời gọi vào `InvocationHandler`. Khi ghép nhiều API, client, interceptor hoặc facet interface vào cùng một proxy, các chữ ký trùng có thể tạo quy tắc không trực quan, nhất là với `throws`.

## 1. Nhắc lại cơ chế JDK dynamic proxy

Tạo một proxy cơ bản:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

interface Greeting {
    String say(String name);
}

InvocationHandler handler = (proxy, method, args) ->
        "Hello, " + args[0];

Greeting greeting = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[]{Greeting.class},
        handler);
```

Đây là **đoạn minh họa**, cần đặt phần khởi tạo biến trong một method hoặc initializer; phần 7 có chương trình chạy độc lập.

Ở runtime, lớp proxy do Java sinh:
- implements đúng những interface được cung cấp (và theo **thứ tự đó**);
- chuyển lời gọi interface vào `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`;
- dùng `method` biểu diễn phương thức được dispatch, và `args` chứa đối số đã boxing nếu là primitive (với phương thức không tham số, `args` có thể là `null`);
- lấy `Object` do handler trả về rồi kiểm tra/chuyển sang return type mà phương thức proxy yêu cầu; nếu không phù hợp, có thể gây `ClassCastException` hoặc `NullPointerException` cho primitive result;
- áp dụng chính sách exception của proxy trước khi trả lại caller.

`InvocationHandler.invoke` được khai báo `throws Throwable`. Điều này **không có nghĩa** mọi checked exception handler ném ra sẽ tới caller nguyên vẹn: lớp proxy **thực thi giới hạn throws** của interface và có thể thay lỗi bằng một wrapper unchecked.

### 1.1. Phương thức "trùng" được hiểu như thế nào?

Trong phạm vi JDK proxy, hai interface có **phương thức trùng về tên và parameter signature** khi cùng tên method và cùng danh sách kiểu tham số theo thứ tự, kể cả method kế thừa từ superinterface.

```java
interface A {
    String find(String key);
}
interface B {
    String find(String key);
}
```

Đây là hai khai báo trùng. Ngược lại, `find(int)` và `find(String)` là **overload**, không phải cặp trùng chữ ký tham số. `throws` không phải thành phần dùng để phân biệt overload, vì vậy:

```java
interface FileService {
    void execute() throws java.io.IOException;
}
interface SqlService {
    void execute() throws java.sql.SQLException;
}
```

Hai khai báo `execute()` vẫn là phương thức trùng, dù `throws` khác nhau. Java cho phép tạo proxy implements cả hai nếu những điều kiện khác hợp lệ; **giới hạn checked exception xảy ra khi handler ném lỗi**, không phải quy tắc “chỉ có thể tạo proxy nếu throws giống hệt”.

**Lưu ý về return type:** Một số interface khai báo cùng tên/cùng tham số nhưng return type khác theo hướng **covariant** (ví dụ `Object` và `String`); proxy được phép nếu return types tương thích. JVM method descriptor có chứa return type nên có thể tồn tại đường dispatch/bridge riêng. Không áp dụng máy móc giả định "luôn thấy cùng một Method dù mọi return type đều khác" cho trường hợp covariant; phần 6 giải thích.

## 2. Thứ tự interface quyết định Method được giao cho handler

Giả sử:

```java
interface First {
    String echo(String value) throws java.io.IOException;
}
interface Second {
    String echo(String value) throws Exception;
}
```

Khi tạo:

```java
Object proxy = Proxy.newProxyInstance(
        loader,
        new Class<?>[]{First.class, Second.class},
        handler);
```

Đây là đoạn minh họa trong method đã có `loader` và `handler`. Với cặp method `echo(String)` cùng return type, một lời gọi `echo` qua **bất kỳ view nào** cũng đưa vào handler đối tượng `Method` của interface **xuất hiện trước trong danh sách** và chứa method đó.

| Thứ tự interface tạo proxy | View dùng để gọi | `method.getDeclaringClass()` được chọn |
| --- | --- | --- |
| `[First, Second]` | `((First) proxy).echo("x")` | `First.class` |
| `[First, Second]` | `((Second) proxy).echo("x")` | `First.class` |
| `[Second, First]` | `((First) proxy).echo("x")` | `Second.class` |
| `[Second, First]` | `((Second) proxy).echo("x")` | `Second.class` |

Vì sao? **Một method triển khai chung của proxy không biết caller đã giữ reference là interface nào.** Phương thức được gọi đã tới cùng implementation của lớp proxy; nó không nhận một tham số ẩn “caller cast qua First hay Second”.

Quy tắc này được Java SE 17 tài liệu hóa dưới mục **Methods Duplicated in Multiple Proxy Interfaces**. Nó có hai hệ quả trực tiếp:

1. **Không phân nhánh handler theo ý định caller chỉ bằng `method.getDeclaringClass()`.** Với `[First,Second]`, caller có thể dùng `Second` nhưng handler vẫn nhận `Method` khai báo ở `First`.
2. **Thứ tự interface là một phần của cấu hình proxy có ý nghĩa.** Nếu đổi `[First,Second]` thành `[Second,First]`, cùng một lời gọi có thể khiến logging, annotation lookup hay routing dựa trên `Method` thay đổi.

### 2.1. Interface có chứa method do kế thừa

Java xét interface sớm nhất **có method trực tiếp hoặc kế thừa từ interface cha**. Ví dụ:

```java
interface Parent {
    String ping();
}
interface Child extends Parent { }
interface Other {
    String ping();
}
```

Với danh sách `[Child.class, Other.class]`, interface đầu `Child` **chứa** `ping()` do kế thừa. `Method` mà handler thấy có thể có `method.getDeclaringClass() == Parent.class` vì khai báo thực sự nằm ở `Parent`. Do đó:

- “Interface xuất hiện trước trong mảng” khác với “Class trả về bởi `Method.getDeclaringClass()`”.
- Không so sánh duy nhất `getDeclaringClass() == Child.class` để kết luận proxy không xử lý nhánh `Child`.
- Nếu cần logic theo hợp đồng interface, nên gắn thông tin ngữ nghĩa khi tạo proxy thay vì truy ngược kiểu reference của caller từ `Method`.

### 2.2. Đổi thứ tự tạo ra proxy class khác

JDK `Proxy` quy định hai yêu cầu tạo proxy có cùng các interface nhưng **khác thứ tự** tạo ra **hai proxy class khác nhau**. Ví dụ lớp cho `[First,Second]` không đồng nhất với lớp cho `[Second,First]`; `proxy.getClass().getInterfaces()` cũng phản ánh thứ tự đã cung cấp.

Đây không chỉ là vấn đề hiển thị. Nếu code cache proxy class, lưu key hoặc dựng handler từ array interface, phải giữ thứ tự ổn định. Đừng coi hai mảng interface là “một tập hợp không thứ tự”.

## 3. Ngoại lệ đặc biệt: Object.equals, hashCode, toString

Ba phương thức public, non-final quen thuộc của `Object` được dynamic proxy xử lý như thể `Object` đứng **trước tất cả proxy interfaces** trong việc quyết định `Method` gửi cho handler:

- `boolean equals(Object other)`
- `int hashCode()`
- `String toString()`

Ngay cả khi một proxy interface khai báo lại `toString()` với đúng chữ ký, handler vẫn nhận `Method` có `getDeclaringClass() == Object.class` cho lời gọi đó.

```java
interface Label {
    String toString();
}
```

Đây là interface minh họa. Nếu handler định route bằng `method.getDeclaringClass() == Label.class`, nhánh `toString` sẽ không đi như dự kiến. Nên xử lý rõ ba phương thức `Object`, tránh đệ quy như gọi `proxy.toString()` bên trong handler của chính `toString()`.

Ví dụ một handler có thể chọn:
- `equals`: so sánh identity theo `proxy == args[0]` hoặc định nghĩa giá trị miền phù hợp;
- `hashCode`: trả `System.identityHashCode(proxy)` nếu dùng identity;
- `toString`: trả một mô tả proxy ổn định, không tự gọi lại `proxy.toString()`.

Các quyết định `equals/hashCode` phải **nhất quán với nhau**. Lưu ý các phương thức này có return type tương ứng `boolean` và `int`; handler phải trả các wrapper `Boolean`, `Integer` hợp lệ, không trả `null`.

## 4. Quy tắc throws: phép giao ở mức checked exception

Đây là phần dễ sai nhất khi kết hợp nhiều interface.

### 4.1. Một interface đơn

Cho:

```java
interface Reader {
    String read() throws java.io.IOException;
}
```

Một handler ném `IOException` phù hợp với `throws IOException`; proxy có thể truyền `IOException` trực tiếp. Nếu handler ném `SQLException` (checked, không phải subtype của `IOException`), caller sẽ nhận `UndeclaredThrowableException` thay vì `SQLException` trực tiếp.

`RuntimeException` và `Error` là **unchecked**, nên có thể truyền thẳng ra ngoài bất kể `throws` có khai báo chúng hay không.

### 4.2. Nhiều interface trùng method

Cho:

```java
interface Broad {
    void act() throws Exception;
}
interface Narrow {
    void act() throws java.io.IOException;
}
```

Một proxy implements cả hai. Khi handler ném một **checked Throwable T**, muốn `T` ra caller trực tiếp thì cần:

> Với **mỗi** method `act()` được khai báo hoặc kế thừa trong tất cả proxy interfaces liên quan, `T` phải **assignable** vào **ít nhất một** exception type trong `throws` của method đó.

Nói cách khác, `T` phải thỏa **từng** throws clause; không được chỉ xem clause của interface xuất hiện trước hay chỉ interface mà caller cast sang.

Ví dụ trong `[Broad,Narrow]`:
- `IOException` và các subclass của nó: **hợp lệ**; `IOException` vừa là subtype của `Exception` vừa thuộc `throws IOException`.
- `SQLException`: **không hợp lệ**; nó phù hợp `throws Exception` ở `Broad` nhưng không phù hợp `throws IOException` ở `Narrow`.
- `Exception` (đúng kiểu base): **không hợp lệ**; không assignable tới `IOException`.
- `IllegalStateException`: là unchecked, nên **được phép truyền trực tiếp**.

Đó là ý nghĩa của “giới hạn throws” ở proxy. Nó **không** yêu cầu tất cả interface ghi chính xác cùng một danh sách `throws`, mà yêu cầu **mỗi checked throwable cụ thể** tương thích với mọi declaration liên quan.

### 4.3. Hai throws clause rời nhau

```java
interface FileAction {
    void save() throws java.io.IOException;
}
interface SqlAction {
    void save() throws java.sql.SQLException;
}
```

Proxy implements đồng thời `FileAction` và `SqlAction` vẫn có thể được tạo. Tuy nhiên một handler ném trực tiếp `IOException` hay `SQLException` đều **không** thỏa cả hai `throws` clause. Lời gọi qua **bất kỳ view nào** cũng sẽ nhận `UndeclaredThrowableException` đối với checked exception không được phép đó.

Đổi thứ tự thành `[SqlAction,FileAction]` **không mở rộng** tập checked exceptions được phép. Thứ tự thay đổi `Method` được đưa cho handler, nhưng giới hạn checked throws vẫn dựa trên **tất cả các method trùng**.

### 4.4. Một interface không khai báo throws

Nếu `A.run() throws IOException` nhưng `B.run()` **không** khai báo checked exception, thì bất kỳ checked exception nào từ handler cho cặp method trùng đó đều không được phép truyền trực tiếp. `RuntimeException` và `Error` vẫn có thể thoát thẳng.

Điều này có thể khiến một API trông cho phép I/O failure ở một interface, nhưng proxy đa interface lại bọc lỗi khi có thêm một interface khác không khai báo checked exception.

### 4.5. Bảng quyết định

| Các throws clause của cặp method trùng | Handler ném | Kết quả gọi proxy |
| --- | --- | --- |
| `IOException` và `Exception` | `IOException` | `IOException` trực tiếp |
| `Exception` và `IOException` | `SQLException` | `UndeclaredThrowableException` chứa `SQLException` |
| `IOException` và `SQLException` | `IOException` | `UndeclaredThrowableException` chứa `IOException` |
| `IOException` và không có checked throws | `IOException` | `UndeclaredThrowableException` chứa `IOException` |
| Bất kỳ hai clause hợp lệ | `IllegalStateException` | `IllegalStateException` trực tiếp |
| Bất kỳ hai clause hợp lệ | `AssertionError` | `AssertionError` trực tiếp |

**Quan trọng:** `Method.getExceptionTypes()` trên **một** `Method` handler nhận được chỉ cho biết throws clause của method **được chọn** (thường thuộc interface trước). Nó **không** tính sẵn giao của tất cả method trùng. Với thứ tự `[Broad,Narrow]`, handler có thể thấy `[Exception.class]` nhưng `SQLException` vẫn bị proxy bọc vì `Narrow` chỉ cho `IOException`.

Không xây chính sách lỗi bằng cách kiểm tra **duy nhất** `method.getExceptionTypes()` rồi cho rằng mọi checked throwable thuộc danh sách đó sẽ được proxy truyền thẳng.

## 5. UndeclaredThrowableException: wrapper của dynamic proxy

`java.lang.reflect.UndeclaredThrowableException` là một **unchecked exception** do proxy ném nếu handler đưa ra một checked Throwable không hợp lệ với declared throws.

```java
try {
    api.save();
} catch (java.lang.reflect.UndeclaredThrowableException wrapper) {
    Throwable original = wrapper.getUndeclaredThrowable();
    // original là checked Throwable do InvocationHandler ném.
}
```

Đây là đoạn minh họa: `api` là proxy triển khai một interface có `save()`. `getUndeclaredThrowable()` trả throwable gốc và có thể đọc tương đương qua `getCause()`.

### 5.1. Phân biệt với InvocationTargetException

Hai lớp này có **nguồn tạo khác nhau**:

| Wrapper | Nguồn thường gặp | Chứa throwable nào? |
| --- | --- | --- |
| `InvocationTargetException` | `Method.invoke(...)` ở cơ chế reflection khi target ném lỗi | Throwable thật sự của target, xem `getCause()` |
| `UndeclaredThrowableException` | JDK proxy khi `InvocationHandler.invoke` ném checked Throwable **không hợp lệ** với throws clause của proxy method | Checked Throwable do handler ném, xem `getUndeclaredThrowable()` |

**Bẫy phổ biến:** handler dùng reflection để gọi delegate:

```java
InvocationHandler handler = (proxy, method, args) ->
        method.invoke(delegate, args);
```

Đây là đoạn minh họa với biến `delegate` và một `Method` thực sự có thể gọi trên delegate. Nếu delegate ném `IOException` thì `Method.invoke` tạo `InvocationTargetException`. Handler **vô tình ném wrapper checked** đó ra. Nếu proxy interface chỉ khai báo `throws IOException`, nó **không** cho phép `InvocationTargetException`, nên proxy bọc **thêm** `UndeclaredThrowableException`:

```text
Caller
  -> UndeclaredThrowableException
       -> InvocationTargetException
            -> IOException ("disk")
```

Ngay cả khi `IOException` gốc nằm trong hợp đồng, **wrapper `InvocationTargetException`** không nằm trong `throws IOException`. Vì vậy phải bóc đúng tầng reflection trước khi để throwable ra từ handler.

### 5.2. Delegate bằng reflection đúng cách

```java
InvocationHandler handler = (proxy, method, args) -> {
    try {
        return method.invoke(delegate, args);
    } catch (java.lang.reflect.InvocationTargetException ex) {
        throw ex.getCause();
    }
};
```

Đây vẫn là đoạn minh họa trong một method đã có `delegate` tương thích với **declaring class** của `method`. Nó chỉ giải quyết wrapper từ reflection, **không** tự bảo đảm throwable gốc thuộc throws clause của mọi interface trùng. Nếu cause là `SQLException` nhưng cặp method có `throws IOException` ở một interface, proxy vẫn bọc trong `UndeclaredThrowableException`.

Đặc biệt, khi proxy ghép nhiều interface, `Method` mà handler nhận có thể là method của interface **khác view mà caller dùng**. Nếu delegate không implements interface khai báo bởi `method`, `method.invoke(delegate, args)` có thể thất bại vì receiver không hợp lệ. Hãy đảm bảo delegate thực sự hỗ trợ method đó hoặc resolve mục tiêu cụ thể bằng dispatch có chủ đích.

### 5.3. Khi xử lý exception ở boundary

Trong ứng dụng, nên:
1. Giữ nguyên unchecked exceptions nếu hợp đồng yêu cầu, nhưng không nuốt `Error`.
2. Chỉ rethrow checked exception trực tiếp khi nó hợp lệ với **tất cả** method trùng.
3. Nếu không hợp lệ, chuyển thành **exception domain unchecked có cause**, thiết kế lại interface hoặc tách proxy, thay vì dựa vào wrapper bất ngờ.
4. Khi nhận `UndeclaredThrowableException`, quan sát `getUndeclaredThrowable()` để chẩn đoán, nhưng không mặc định unwrap tùy tiện mọi lớp wrapper.
5. Giữ nguyên stack trace/cause khi chuyển lỗi: `new IllegalStateException("Operation failed", original)` tốt hơn việc chỉ sao chép message.

## 6. Return type tương thích khi các interface trùng method

Không phải mọi bộ interface có tên method/các tham số giống nhau đều có thể ghép thành proxy.

### 6.1. Return type primitive hoặc void

Nếu một method trong bộ trùng có return type là **primitive** hoặc `void`, tất cả method còn lại phải có **chính xác cùng return type**. Ví dụ:
- `int number()` và `int number()`: hợp lệ.
- `int number()` và `long number()`: **không** hợp lệ (dù có thể widen `int → long`, proxy không hợp nhất như vậy).
- `void run()` và `int run()`: **không** hợp lệ.

Khi gọi `Proxy.newProxyInstance` với bộ return không tương thích, API ném `IllegalArgumentException` trước khi có proxy object.

### 6.2. Return type tham chiếu (covariant)

Nếu return types đều là **reference**, phải tồn tại **một kiểu trả về** assignable tới **tất cả return types còn lại** trong bộ. Ví dụ:

```java
interface Wide { Object value(); }
interface Tight { String value(); }
```

`String` là subtype của `Object`, nên proxy implements cả hai được phép. Ngược lại `String value()` và `Integer value()` **không** thể cùng được đáp ứng bằng một return type cụ thể là subtype của cả hai class final đó, nên tạo proxy ném `IllegalArgumentException`.

Với nhiều interface có generic erasure hoặc bridge methods, đừng suy luận đơn giản từ tên method in ra. **JVM method descriptor còn chứa return type**, dù Java source method signature cho overload không dùng return type. Các call sites với covariant returns có thể đi qua các entry khác nhau và tạo khác biệt trong đối tượng `Method` quan sát được. Không nên dựa vào `getDeclaringClass()` để đoán source-interface view trong những trường hợp này; hãy dựa trên hợp đồng chính thức, xác thực behavior trên JDK mục tiêu và giữ dispatcher rõ ràng.

### 6.3. Handler phải trả giá trị đúng kiểu

Khi phương thức proxy trả `String`, handler phải trả `String` tương thích (hoặc `null` nếu return là reference). Nếu trả `Integer` thay vì `String` thì proxy có thể ném `ClassCastException`.

Với method trả `int`, handler phải trả kiểu wrapper tương ứng `Integer`; nếu trả `null`, proxy có thể ném `NullPointerException` khi unbox. Với `void`, giá trị kết quả của handler không trở thành return payload của caller.

**Sửa return type bằng cast trong handler không thể làm một bộ interface có return type không tương thích thành hợp lệ.** Việc kiểm tra bộ interface xảy ra lúc tạo proxy.

## 7. Ví dụ hoàn chỉnh Java 17+: thứ tự, throws, returns và wrapper

Lưu file **`ProxyDuplicateDemo.java`**. Chương trình dùng interface lồng trong một class để dễ chạy độc lập, không phụ thuộc framework ngoài JDK.

```java
import java.io.IOException;
import java.sql.SQLException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.lang.reflect.UndeclaredThrowableException;
import java.util.Arrays;

public class ProxyDuplicateDemo {
    interface Left { String call(String s) throws IOException; }
    interface Right { String call(String s) throws Exception; }
    interface Broad { void act() throws Exception; }
    interface Narrow { void act() throws IOException; }
    interface FileAction { void save() throws IOException; }
    interface SqlAction { void save() throws SQLException; }
    interface Wide { Object value(); }
    interface Tight { String value(); }
    interface InvalidA { String value(); }
    interface InvalidB { Integer value(); }
    interface ObjectLike { String toString(); }
    interface Data { String read() throws IOException; }

    static final class DataImpl implements Data {
        public String read() throws IOException {
            throw new IOException("disk");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader loader = ProxyDuplicateDemo.class.getClassLoader();

        InvocationHandler echo = (proxy, method, values) -> {
            System.out.println("selected=" + method.getDeclaringClass().getSimpleName());
            return "ok:" + values[0];
        };
        Object leftFirst = Proxy.newProxyInstance(
                loader, new Class<?>[]{Left.class, Right.class}, echo);
        System.out.println("asRight=" + ((Right) leftFirst).call("A"));

        Object rightFirst = Proxy.newProxyInstance(
                loader, new Class<?>[]{Right.class, Left.class}, echo);
        System.out.println("asLeft=" + ((Left) rightFirst).call("B"));
        System.out.println("classesEqual="
                + (leftFirst.getClass() == rightFirst.getClass()));

        Object broadFirst = Proxy.newProxyInstance(
                loader, new Class<?>[]{Broad.class, Narrow.class},
                (proxy, method, values) -> {
                    System.out.println("methodThrows="
                            + Arrays.toString(method.getExceptionTypes()));
                    throw new SQLException("db");
                });
        try {
            ((Broad) broadFirst).act();
        } catch (UndeclaredThrowableException wrapper) {
            System.out.println("overlapWrapper="
                    + wrapper.getUndeclaredThrowable().getClass().getSimpleName());
        }

        Object compatible = Proxy.newProxyInstance(
                loader, new Class<?>[]{Broad.class, Narrow.class},
                (proxy, method, values) -> { throw new IOException("disk"); });
        try {
            ((Narrow) compatible).act();
        } catch (IOException original) {
            System.out.println("overlapPass=" + original.getClass().getSimpleName());
        }

        Object disjoint = Proxy.newProxyInstance(
                loader, new Class<?>[]{FileAction.class, SqlAction.class},
                (proxy, method, values) -> { throw new IOException("disk"); });
        try {
            ((FileAction) disjoint).save();
        } catch (UndeclaredThrowableException wrapper) {
            System.out.println("fileView="
                    + wrapper.getUndeclaredThrowable().getClass().getSimpleName());
        }
        try {
            ((SqlAction) disjoint).save();
        } catch (UndeclaredThrowableException wrapper) {
            System.out.println("sqlView="
                    + wrapper.getUndeclaredThrowable().getClass().getSimpleName());
        }

        Object unchecked = Proxy.newProxyInstance(
                loader, new Class<?>[]{FileAction.class, SqlAction.class},
                (proxy, method, values) -> {
                    throw new IllegalStateException("state");
                });
        try {
            ((FileAction) unchecked).save();
        } catch (IllegalStateException original) {
            System.out.println("unchecked="
                    + original.getClass().getSimpleName());
        }

        Object covariance = Proxy.newProxyInstance(
                loader, new Class<?>[]{Wide.class, Tight.class},
                (proxy, method, values) -> "text");
        System.out.println("covariantValue=" + ((Tight) covariance).value());
        try {
            Proxy.newProxyInstance(
                    loader, new Class<?>[]{InvalidA.class, InvalidB.class}, echo);
        } catch (IllegalArgumentException incompatible) {
            System.out.println("badReturns="
                    + incompatible.getClass().getSimpleName());
        }

        Object objectMethod = Proxy.newProxyInstance(
                loader, new Class<?>[]{ObjectLike.class},
                (proxy, method, values) -> {
                    System.out.println("objectDeclaring="
                            + method.getDeclaringClass().getSimpleName());
                    return "proxy-text";
                });
        System.out.println("objectResult=" + objectMethod.toString());

        DataImpl target = new DataImpl();
        Data raw = (Data) Proxy.newProxyInstance(
                loader, new Class<?>[]{Data.class},
                (proxy, method, values) -> method.invoke(target, values));
        try {
            raw.read();
        } catch (UndeclaredThrowableException wrapper) {
            System.out.println("rawForwarding="
                    + wrapper.getUndeclaredThrowable().getClass().getSimpleName());
        }

        Data unwrapped = (Data) Proxy.newProxyInstance(
                loader, new Class<?>[]{Data.class},
                (proxy, method, values) -> {
                    try {
                        return method.invoke(target, values);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });
        try {
            unwrapped.read();
        } catch (IOException original) {
            System.out.println("unwrapped=" + original.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac --release 17 ProxyDuplicateDemo.java
java ProxyDuplicateDemo
```

**Stdout đã kiểm chứng:**

```text
selected=Left
asRight=ok:A
selected=Right
asLeft=ok:B
classesEqual=false
methodThrows=[class java.lang.Exception]
overlapWrapper=SQLException
overlapPass=IOException
fileView=IOException
sqlView=IOException
unchecked=IllegalStateException
covariantValue=text
badReturns=IllegalArgumentException
objectDeclaring=Object
objectResult=proxy-text
rawForwarding=InvocationTargetException
unwrapped=IOException
```

### 7.1. Vì sao handler chọn Left khi caller gọi qua Right?

Proxy thứ nhất được tạo theo thứ tự `[Left,Right]`. Dù caller cast về `Right` rồi gọi `call("A")`, handler vẫn nhận `Method` khai báo ở `Left`. Proxy thứ hai đảo thứ tự `[Right,Left]` nên handler nhận `Right` dù caller cast về `Left`. `classesEqual=false` thể hiện thứ tự cũng phân biệt proxy classes.

### 7.2. Vì sao `SQLException` bị bọc dù Method cho biết `throws Exception`?

Proxy `broadFirst` có `[Broad,Narrow]`. `Method` handler nhận đến từ `Broad`, nên `method.getExceptionTypes()` in `[class java.lang.Exception]`. Tuy nhiên method trùng ở `Narrow` chỉ khai báo `throws IOException`. `SQLException` không phải subtype của `IOException`, vì vậy proxy ném `UndeclaredThrowableException`; chương trình unwrap và in `overlapWrapper=SQLException`.

Đây là bằng chứng thực tế rằng **chỉ đọc metadata của Method đầu tiên là không đủ để kết luận tập checked exceptions hợp lệ**.

### 7.3. Trường hợp giao throws chấp nhận IOException

Proxy `compatible` cũng implements `[Broad,Narrow]`, nhưng handler ném `IOException`. Nó tương thích cả `throws Exception` và `throws IOException`, nên caller `((Narrow) compatible).act()` bắt trực tiếp `IOException`.

### 7.4. Trường hợp hai throws không có phần giao hợp lệ

`disjoint` ghép `FileAction.save() throws IOException` và `SqlAction.save() throws SQLException`. Một handler ném `IOException`, proxy bọc trong `UndeclaredThrowableException` bất kể caller dùng `FileAction` hay `SqlAction`. Hai dòng `fileView=IOException` và `sqlView=IOException` ghi lại **original** lấy từ wrapper, không phải exception class ở cấp ngoài.

### 7.5. Unchecked exception và Object methods

`IllegalStateException` là unchecked, nên proxy không buộc nó vào throws intersection. `ObjectLike.toString()` được chọn như method của `Object`, do đó in `objectDeclaring=Object`.

### 7.6. Tương thích return type và giới hạn lúc tạo proxy

`Wide.value(): Object` và `Tight.value(): String` có return tương thích; proxy được tạo và trả `"text"`. `InvalidA.value(): String` và `InvalidB.value(): Integer` có return reference không tương thích, nên `Proxy.newProxyInstance` ném `IllegalArgumentException`. Đây là lỗi **tạo proxy**, không phải checked exception của target.

### 7.7. Vì sao forward reflection sai gây bọc kép?

`Data.read() throws IOException` là contract hợp lệ cho target `DataImpl`. Khi handler viết `method.invoke(target, values)`, `Method.invoke` tạo **`InvocationTargetException`**; wrapper checked đó không nằm trong `throws IOException` nên proxy thêm **`UndeclaredThrowableException`**. Dòng `rawForwarding=InvocationTargetException` cho biết throwable bên trong proxy wrapper là reflection wrapper. Phiên bản `unwrapped` catch `InvocationTargetException` rồi throw cause, vì vậy `IOException` truyền trực tiếp như contract và in `unwrapped=IOException`.

## 8. Thiết kế handler an toàn cho nhiều interface

### 8.1. Đừng dùng declaring class làm "caller identity"

Đây là anti-pattern:

```java
InvocationHandler handler = (proxy, method, args) -> {
    if (method.getDeclaringClass() == First.class) {
        return callFirstBusinessLogic(args);
    }
    if (method.getDeclaringClass() == Second.class) {
        return callSecondBusinessLogic(args);
    }
    throw new UnsupportedOperationException(method.toString());
};
```

Đây là **phản ví dụ minh họa**; `callFirstBusinessLogic` và `callSecondBusinessLogic` tượng trưng cho nghiệp vụ, không phải method có sẵn. Với chữ ký trùng và `[First,Second]`, nhánh `Second` có thể **không bao giờ chạy cho `echo(String)`**, dù caller cast sang `Second`.

Một proxy không thể nhận biết "kiểu reference caller muốn dùng" chỉ từ `Method` của chữ ký trùng. Nếu hai interface định nghĩa **ngữ nghĩa khác nhau** cho cùng tên/tham số, cần tránh ghép cả hai vào một proxy cùng dispatcher hoặc giới thiệu API rõ ràng hơn.

### 8.2. Các lựa chọn thiết kế đáng tin hơn

- **Thống nhất contract:** Nếu hai interface có phương thức trùng cùng ngữ nghĩa, viết một nhánh xử lý chung. Kiểm tra throws intersection và return type khi thiết kế.
- **Tách proxy:** Nếu chữ ký trùng nhưng ngữ nghĩa khác nhau, dùng **hai proxy objects** hoặc hai adapter với context riêng. Caller biết đối tượng nào thực hiện nghiệp vụ nào.
- **Dispatch theo signature và cấu hình:** Tạo key gồm tên + parameter types (và return descriptor nếu thực sự cần), liên kết trước tới một handler mục tiêu rõ ràng. Không dùng identity của `Method` hay tên interface được suy ra từ cast ở caller.
- **Cung cấp explicit operation identifier:** Nếu app cần phân biệt hai hành vi, đặt tên method khác nhau hoặc truyền thông tin operation trong đối số, thay vì trông chờ proxy đoán từ reference.
- **Xây chính sách lỗi tại boundary:** Kiểm tra tất cả declaration trùng trước khi cho checked exception thoát; với lỗi không biểu diễn được trong contract, dùng exception domain unchecked có cause hoặc thiết kế lại interface.

### 8.3. Gắn metadata khi tạo proxy

Một hệ thống lớn có thể dựng trước một descriptor cho mỗi method group:
- method name và parameter types;
- danh sách các interface có khai báo/kế thừa method đó;
- return types khả dụng;
- tập checked exceptions được phép truyền qua mọi declaration;
- dispatcher target, security checks và exception translation policy.

Việc này có thể thực hiện ở **thời điểm tạo proxy** thay vì mỗi lời gọi. Nó giúp phát hiện xung đột sớm và tránh lặp reflection không cần thiết. Tuy nhiên descriptor vẫn không thể biến hai ngữ nghĩa khác nhau thành có thể phân biệt chỉ nhờ cast của caller.

### 8.4. Thứ tự interface và annotation

Nếu hai interface có annotation khác nhau trên method trùng, `Method` được đưa cho handler theo thứ tự interface trong trường hợp cùng descriptor. Vì vậy một handler đọc `method.getAnnotation(...)` có thể quan sát metadata **khác nhau khi đổi thứ tự**, dù caller giữ cùng interface view.

Đừng coi việc đọc annotation trên một `Method` đó là đủ nếu cần tổng hợp policy từ **mọi interface**. Nên resolve tất cả declaration khi khởi tạo proxy, áp dụng quy tắc xung đột được xác định rõ và test thứ tự đảo.

### 8.5. Default methods và interface order

Dynamic proxy cũng chuyển lời gọi interface method vào handler. Java 17 hỗ trợ `InvocationHandler.invokeDefault(proxy, method, args)` để handler có thể **chủ động** gọi một default method phù hợp. Nếu nhiều interface có default methods cạnh tranh, không nên suy rằng đổi thứ tự interface sẽ tự động chọn "business implementation" mong muốn. Phải chọn default method hợp lệ một cách tường minh theo contract của API.

Quy tắc chọn `Method` cho method trùng, việc chọn **target** muốn delegate và việc kiểm tra throws là ba trách nhiệm khác nhau.

## 9. Các ràng buộc khác của Proxy.newProxyInstance

Khi ghép interface, ngoài return compatibility và throws, còn cần kiểm tra:

1. Mỗi phần tử `interfaces` thực sự là **interface type** phù hợp; Java 17 không chấp nhận class, primitive, hidden hoặc sealed interface làm proxy interface theo điều kiện API.
2. Không được lặp lại **chính cùng một Class object** trong mảng `interfaces`; nhưng được ghép nhiều interface **khác nhau** có method trùng.
3. Tất cả interface phải được **class loader chỉ định nhìn thấy** bằng identity chính xác; dùng sai class loader có thể làm tạo proxy thất bại.
4. Với **non-public interfaces**, phải đáp ứng các điều kiện cùng package/module và khả năng truy cập liên quan. Không phải cứ có `Class<?>` là proxy luôn tạo được.
5. Return type của các method trùng phải tương thích. Nếu không, `Proxy.newProxyInstance` ném `IllegalArgumentException`.
6. Danh sách interface và generated proxy class phải nằm trong giới hạn JVM; đừng dựng danh sách tùy ý từ input chưa xác thực.

Tài liệu Java SE 17 cũng mô tả vị trí package/module của proxy class trong JPMS. Khi gặp lỗi do encapsulation, phải phân biệt **lỗi cấu hình module/loader** với **throws restriction trong handler**; chúng xuất hiện ở các pha khác nhau.

## 10. Kiểm thử và debug theo ma trận

Một bộ kiểm thử cho proxy ghép nhiều interface nên bao gồm:

| Nhóm test | Điều kiện | Kết quả nên xác minh |
| --- | --- | --- |
| Thứ tự interface | `[A,B]` và `[B,A]` với method trùng cùng return | `Method` được chọn thay đổi; hai proxy classes khác nhau |
| Reference view | Gọi một proxy qua `A` và `B` | Với cùng duplicate descriptor, method khai báo do thứ tự interface quyết định, không do cast |
| Inheritance | Interface đầu kế thừa method từ parent | `Method.getDeclaringClass()` có thể là parent |
| Object methods | Interface khai báo lại `toString()` | `Method.getDeclaringClass() == Object.class` |
| Checked throws chồng lấn | `throws Exception` và `throws IOException`, handler ném `IOException` | IOException trực tiếp |
| Checked throws không tương thích | Cặp trên, handler ném `SQLException` | UndeclaredThrowableException chứa SQLException |
| Hai throws rời nhau | `IOException` và `SQLException` | Không cho phép IOException/SQLException trực tiếp |
| Một declaration không throws | Một interface không khai báo checked throws | Checked từ handler bị bọc |
| Unchecked | Handler ném `IllegalStateException` | Đi ra trực tiếp |
| Covariant returns | `Object` và `String` | Có thể tạo proxy, trả giá trị tương thích |
| Return conflict | `String` và `Integer` hoặc `int` với `long` | Proxy creation từ chối bằng IllegalArgumentException |
| Sai kết quả từ handler | Method trả `String`, handler trả `Integer` | ClassCastException ở proxy boundary |
| Reflection delegate | Handler rethrow `InvocationTargetException` không unwrap | Có thể thành wrapper kép; xử lý đúng phải throw cause hợp lệ |

**Lưu ý khi đo/so sánh:** không dùng `Method.toString()` như ID duy nhất cho routing. Tên hiển thị, generic erasure, inheritance, return covariance và class loader có thể làm phân tích sai. Dùng metadata có cấu trúc và kiểm tra đúng ngữ cảnh.

## 11. Lỗi hiểu sai thường gặp

1. **“Caller cast sang interface nào thì handler nhận Method của interface đó.”** Sai với duplicate method có cùng descriptor: interface xuất hiện trước quyết định.
2. **“Hai interface có throws khác nhau thì không thể tạo proxy.”** Sai. Throws restriction được áp dụng khi handler ném checked throwable.
3. **“Handler được khai báo throws Throwable nên proxy không kiểm tra.”** Sai. Checked Throwable vẫn phải tương thích với tất cả method trùng.
4. **“Method.getExceptionTypes() ở handler là danh sách checked throwable được phép.”** Không đủ: nó chỉ phản ánh một Method được chọn, không phải giao của nhiều interface.
5. **“Một caller dùng FileAction có thể nhận IOException trực tiếp, dù proxy cũng implements SqlAction có save() giống hệt.”** Sai nếu checked throwable đó không tương thích với SqlAction.save().
6. **“UndeclaredThrowableException và InvocationTargetException là một.”** Sai: chúng thuộc hai boundary khác nhau và có thể bị lồng nhau.
7. **“Chỉ cần đổi thứ tự interface là sửa được checked exception mismatch.”** Sai. Chỉ đổi Method được chọn; không đổi hợp đồng của tất cả methods.
8. **“Đổi return từ int thành long cũng được vì primitive widening.”** Sai. Proxy yêu cầu primitive/void return trùng chính xác.
9. **“Dùng Method.getDeclaringClass() để phân biệt ngữ nghĩa khi hai interface cùng method.”** Không thể suy caller view đáng tin theo cách đó.
10. **“Proxy tự gọi default method thay vì vào handler.”** Không được dựa vào giả định này. Handler phải xử lý/default-dispatch theo API.
11. **“Method.invoke(delegate, args) luôn là forwarding đúng.”** Không nếu delegate không implements declaring interface, hoặc khi reflection wrapper checked không được unwrap.
12. **“Không khai báo checked exceptions thì mọi throwable sẽ bị bọc.”** Sai. `RuntimeException` và `Error` là unchecked và không bị giới hạn theo cách đó.

## 12. Bài tập tự kiểm tra

### Bài 1 — Thứ tự và view

Cho:

```java
interface A { String name(); }
interface B { String name(); }
```

Proxy tạo theo `[B.class,A.class]`. Caller dùng `((A)p).name()`. Trong trường hợp hai method có cùng return descriptor, `method.getDeclaringClass()` trong handler là class nào?

**Đáp án:** `B.class`. Reference view `A` không quyết định Method được gửi cho handler.

### Bài 2 — Giao checked exceptions

Cho:
- `A.run() throws Exception`;
- `B.run() throws IOException`;
- `C.run() throws FileNotFoundException`.

Handler ném `IOException` thì có được truyền trực tiếp khi proxy implements cả ba không? Nếu handler ném `FileNotFoundException` thì sao?

**Đáp án:** `IOException` thông thường không được vì không assignable vào `FileNotFoundException` của `C`; một instance thực sự thuộc `FileNotFoundException` được phép vì là subtype của cả ba loại exception.

### Bài 3 — Không giao nhau

Một proxy implements `X.send() throws IOException` và `Y.send() throws SQLException`. Handler ném `IOException`. Có khác nhau không nếu caller cast proxy sang `X` hoặc `Y`?

**Đáp án:** Không. Checked `IOException` không thỏa `Y` nên proxy bọc `UndeclaredThrowableException` ở cả hai view.

### Bài 4 — Wrapper kép

Handler gọi `method.invoke(delegate,args)`, delegate ném `IOException`, interface chỉ khai báo `throws IOException`. Vì sao caller thấy `UndeclaredThrowableException` mà không phải `IOException`?

**Đáp án:** `Method.invoke` đã bọc cause trong checked `InvocationTargetException`; handler ném chính wrapper đó. `InvocationTargetException` không phải subtype của `IOException`, nên proxy tạo wrapper unchecked. Cần catch `InvocationTargetException` và rethrow `getCause()`.

### Bài 5 — Return type

Có thể tạo proxy ghép:
- `Object item()` với `String item()`?
- `Number item()` với `Integer item()`?
- `int count()` với `long count()`?
- `String item()` với `Integer item()`?

**Đáp án:** Hai cặp đầu hợp lệ vì tồn tại return reference subtype tương thích (String và Integer). Hai cặp sau không hợp lệ: primitive phải trùng chính xác; String và Integer là hai reference types không có return subtype chung đáp ứng cả hai class final.

### Bài 6 — Thiết kế đúng hợp đồng

Hai interface cùng khai báo `void submit(String id)` nhưng một interface có nghĩa “thanh toán” và interface kia có nghĩa “xác nhận vận chuyển”. Có nên ghép chúng vào một proxy rồi dùng cast của caller để tự phân biệt trong handler không?

**Đáp án:** Không. Cùng duplicate signature không mang thông tin caller reference view vào handler. Hãy dùng hai proxy objects, hai method có tên khác nhau hoặc truyền explicit operation để không trộn ngữ nghĩa.

## Tài liệu chính thức

- [Java SE 17 — Proxy, mục Methods Duplicated in Multiple Proxy Interfaces](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): lựa chọn Method theo thứ tự interface, Object methods, checked throws và quy tắc return type.
- [Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): contract của `invoke`, giá trị trả về và giới hạn throwable.
- [Java SE 17 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): wrapper cho checked exception chưa được interface cho phép.
- [Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): wrapper do `Method.invoke` khi target ném throwable.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `getDeclaringClass`, `getExceptionTypes` và `invoke`.

## Kết luận

Khi một JDK dynamic proxy implements nhiều interface chứa cùng tên method và cùng parameter signature, **thứ tự interface quyết định Method được dispatch cho chữ ký trùng tương ứng**, chứ không phải kiểu reference được caller sử dụng. Nhưng **throws không được quyết định chỉ bởi Method ấy**: một checked throwable muốn ra trực tiếp phải tương thích với **tất cả các throws clause** của những method trùng; nếu không, proxy ném `UndeclaredThrowableException`. Với return types, proxy chỉ được tạo nếu các khai báo tương thích; với `Object` methods và covariance còn có các quy tắc đặc biệt. Hãy xây handler theo **hợp đồng chung rõ ràng**, kiểm tra exception policy trước khi delegate, unwrap đúng `InvocationTargetException` khi dùng reflection, và tách proxy nếu hai interface trùng chữ ký nhưng khác ngữ nghĩa.
