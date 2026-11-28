# Method.invoke() với override: virtual dispatch vẫn chọn triển khai theo receiver

## 1. Vấn đề: giữ `Method` của lớp cha có đồng nghĩa gọi mã lớp cha?

Trong Java, **override** cho phép lớp con cung cấp triển khai mới của một phương thức instance có thể ghi đè. Khi gọi một phương thức như vậy, JVM chọn triển khai theo **kiểu thực tế của đối tượng nhận lời gọi (receiver)**. Điều này vẫn đúng khi lời gọi được thực hiện qua Reflection API bằng `java.lang.reflect.Method.invoke(...)`.

Giả sử `Base` khai báo `describe()` và `Child` override nó. Ta lấy đối tượng `Method` từ `Base.class`, nhưng truyền một đối tượng `Child` vào `invoke()`:

```text
Method m = Base.class.getDeclaredMethod("describe")
                 |  thông tin khai báo: Base.describe()
                 v
          m.invoke(new Child())
                 |  receiver thực tế: Child
                 v
          Child.describe() được thực thi
```

**Hợp đồng cần nhớ:** `Method` xác định phương thức được tra cứu (tên, danh sách tham số, lớp khai báo, ...); còn với phương thức instance có thể override, bước gọi vẫn thực hiện *virtual dispatch* để chọn triển khai phù hợp với receiver. Việc một `Method` có `getDeclaringClass()` là `Base.class` **không buộc** `invoke()` phải chạy thân hàm của `Base`.

Đây là một nội dung thuộc chương **Hợp đồng reflection** của module `JAVA_VERSION_JAVA18`, giúp kiểm chứng hành vi reflection và MethodHandle trên JDK đang dùng. Java 18 có thay đổi cách triển khai nội bộ Core Reflection (JEP 416), nhưng quy tắc chọn phương thức của API công khai vẫn cần được hiểu theo hợp đồng Java. Bài học chỉ sử dụng những API và hành vi vẫn được hỗ trợ trên JDK hiện đại.

## 2. Ví dụ hoàn chỉnh: phương thức lấy từ `Base` vẫn chạy override của `Child`

Lưu đoạn mã sau thành `ReflectionDispatchDemo.java` và chạy trên JDK hiện đại:

```java
import java.lang.reflect.Method;

public final class ReflectionDispatchDemo {
    public static class Base {
        public String describe() {
            return "Base.describe";
        }

        public String format(Object value) {
            return "Base.format(Object): " + value;
        }

        public static String category() {
            return "Base.category";
        }

        public final String stable() {
            return "Base.stable";
        }
    }

    public static class Child extends Base {
        @Override
        public String describe() {
            return "Child.describe";
        }

        // Khác danh sách tham số: overload, không override format(Object).
        public String format(String value) {
            return "Child.format(String): " + value;
        }

        // Cùng chữ ký với phương thức static của Base: hiding, không override.
        public static String category() {
            return "Child.category";
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Base receiver = new Child();

        Method virtual = Base.class.getDeclaredMethod("describe");
        System.out.println(virtual.getDeclaringClass().getSimpleName());
        System.out.println(virtual.invoke(receiver));

        Method overload = Base.class.getDeclaredMethod("format", Object.class);
        System.out.println(overload.invoke(receiver, "hello"));

        Method staticMethod = Base.class.getDeclaredMethod("category");
        System.out.println(staticMethod.invoke(null));

        Method finalMethod = Base.class.getDeclaredMethod("stable");
        System.out.println(finalMethod.invoke(receiver));
    }
}
```

Kết quả dự kiến:

```text
Base
Child.describe
Base.format(Object): hello
Base.category
Base.stable
```

Giải thích lần lượt:

1. `virtual.getDeclaringClass()` trả về `Base.class`: đối tượng `Method` thực sự biểu diễn khai báo `Base.describe()`.
2. `virtual.invoke(receiver)` chạy `Child.describe()` vì biến `receiver` đang trỏ đến một **đối tượng `Child`**. Kiểu khai báo của biến Java (`Base`) không làm mất thông tin kiểu thực tế của đối tượng.
3. `overload` biểu diễn đúng chữ ký `format(Object)`. Trong `Child` chỉ có `format(String)`, đây là **overload**, không phải override. Do đó `Base.format(Object)` được chạy, dù giá trị đối số thực tế là chuỗi `"hello"`.
4. `category()` là `static`; phương thức cùng tên trong `Child` chỉ *hide* phương thức của `Base`. Lời gọi qua `Method` của `Base` chạy `Base.category()`; không có virtual dispatch.
5. `stable()` là `final`, không thể bị override; dù nhận đối tượng `Child`, triển khai vẫn là `Base.stable()`.

Trong ví dụ, các phương thức được phản chiếu đều `public` và nằm trong các lớp truy cập được, nên không cần can thiệp kiểm tra truy cập bằng `setAccessible(true)`.

## 3. Tách ba bước: tìm `Method`, kiểm tra receiver, chọn triển khai

Một lỗi suy luận thường gặp là gộp bước **tra cứu phương thức bằng reflection** với bước **thực thi phương thức**. Chúng có vai trò khác nhau:

| Bước | Quy tắc | Ý nghĩa trong ví dụ |
|---|---|---|
| Tra cứu `Method` | `getDeclaredMethod("describe")` chọn khai báo theo tên và danh sách kiểu tham số | Chọn `Base.describe()` |
| Kiểm tra receiver | Với phương thức instance, đối tượng phải tương thích với lớp khai báo và không được `null` | `new Child()` là một `Base`, nên hợp lệ |
| Gọi phương thức | Với phương thức instance có thể override, áp dụng dynamic method lookup trên receiver thực tế | Chạy `Child.describe()` |

Điều này tương tự lời gọi Java thông thường:

```java
Base receiver = new Child();
System.out.println(receiver.describe()); // Child.describe
```

Với reflection, ta chủ động chỉ ra `Method` trước khi gọi:

```java
Method m = Base.class.getDeclaredMethod("describe");
System.out.println(m.invoke(receiver));   // Child.describe
```

Hai đoạn có cùng kết quả ở trường hợp override này. **`Method.invoke()` không phải công cụ tự động bỏ qua virtual dispatch.**

### `getDeclaredMethod()` và `getMethod()` khác nhau ở bước tra cứu

`Class.getDeclaredMethod(name, parameterTypes...)` tìm phương thức **khai báo trực tiếp** trong lớp hoặc interface được chỉ định; không tự tìm các khai báo kế thừa. `Class.getMethod(...)` tìm một phương thức `public` phù hợp, bao gồm các phương thức được kế thừa theo quy tắc của API.

```java
Method fromBase = Base.class.getDeclaredMethod("describe");
Method fromChild = Child.class.getDeclaredMethod("describe");

System.out.println(fromBase.getDeclaringClass());  // class ReflectionDispatchDemo$Base
System.out.println(fromChild.getDeclaringClass()); // class ReflectionDispatchDemo$Child

Child child = new Child();
System.out.println(fromBase.invoke(child));        // Child.describe
System.out.println(fromChild.invoke(child));       // Child.describe
```

Việc chọn một `Method` khai báo ở `Base` hay `Child` không thay đổi kết quả khi receiver là `Child` và phương thức instance được override. Tuy nhiên, **receiver phải tương thích với lớp khai báo**: một `Method` lấy từ `Child.class` không thể được gọi với đối tượng chỉ là `new Base()`.

```java
Method childMethod = Child.class.getDeclaredMethod("describe");
childMethod.invoke(new Base()); // IllegalArgumentException: receiver không phải Child
```

Ví dụ này minh họa lỗi khi chạy; không đặt dòng cuối trong chương trình cần chạy thành công nếu chưa xử lý ngoại lệ.

## 4. Những trường hợp dễ nhầm với override

Không phải mọi cặp phương thức cùng tên đều tham gia virtual dispatch. Cần xác định đúng quan hệ trong hệ phân cấp lớp trước khi dự đoán kết quả:

| Trường hợp | Có virtual dispatch tới override theo receiver? | Giải thích |
|---|---|---|
| Instance method được override hợp lệ | **Có** | Lựa chọn triển khai lúc gọi theo lớp thực tế của receiver |
| Phương thức `abstract` ở lớp cha/interface, lớp con triển khai | **Có** | Receiver cung cấp triển khai thực tế |
| Phương thức `static` có cùng tên ở lớp con | **Không** | Đây là static method hiding; gọi khai báo được biểu diễn bởi `Method` |
| Phương thức `final` | **Không có override** | Không có triển khai ghi đè để lựa chọn |
| Phương thức `private` cùng tên ở lớp con | **Không** | Phương thức private của lớp cha không được override; kiểm tra quyền truy cập vẫn áp dụng |
| Hai overload khác kiểu tham số | **Không phải override** | `Method` đã được chọn theo kiểu tham số tại bước tra cứu |

### Overload được quyết định trước khi `invoke()` nhận đối số

Xét hai phương thức:

```java
public String format(Object value) { /* ... */ }
public String format(String value) { /* ... */ }
```

Nếu đã gọi `getMethod("format", Object.class)`, thì `Method` thu được là phiên bản nhận `Object`. Việc sau đó truyền đối tượng có kiểu runtime là `String` vào `invoke(...)` **không khiến reflection tự chọn lại** overload `format(String)`. Để dùng overload `String`, phải lấy đúng `Method` theo `String.class`.

Phân biệt hai cơ chế giúp tránh các bug ở framework serialization, dependency injection và RPC: **overload resolution** xác định chữ ký được gọi; **override dispatch** xác định thân phương thức tại thời điểm gọi trên receiver.

### Interface cũng có thể tham gia dispatch

Một `Method` lấy từ interface vẫn có thể được gọi trên đối tượng lớp triển khai. Ví dụ:

```java
interface Greeting {
    String say();
}

final class GreetingImpl implements Greeting {
    @Override
    public String say() {
        return "Xin chào";
    }
}

Method say = Greeting.class.getMethod("say");
System.out.println(say.invoke(new GreetingImpl())); // Xin chào
```

Đoạn mã là ví dụ đặt trong ngữ cảnh Java hợp lệ có các import reflection và xử lý ngoại lệ được kiểm tra. Quy tắc tương tự cũng áp dụng khi lớp triển khai override một **default method** của interface: `Method.invoke()` với receiver là lớp triển khai sẽ chọn override thích hợp.

## 5. Vì sao `Method` của lớp cha không giúp gọi cố định `super.method()`?

Giả sử `Child.describe()` muốn gọi `super.describe()` từ thân phương thức của chính nó. Trong mã Java, `super.describe()` có cơ chế gọi đặc biệt, khác với một lời gọi virtual thông thường:

```java
public String describeBoth() {
    return super.describe() + " / " + describe();
}
```

Khi đứng **bên ngoài** và chỉ có `Method` lấy từ `Base.class`, biểu thức sau **không** ép JVM bỏ qua override của `Child`:

```java
Method baseMethod = Base.class.getDeclaredMethod("describe");
baseMethod.invoke(new Child()); // Vẫn là Child.describe
```

Nếu thực sự cần mô phỏng lời gọi kiểu `super` trong một công cụ có quyền truy cập phù hợp, có thể nghiên cứu `java.lang.invoke.MethodHandles.Lookup.findSpecial(...)`. API này diễn đạt ngữ nghĩa gọi phương thức đặc biệt và áp dụng các kiểm tra quyền truy cập riêng. Không thể thay thế đơn giản `findSpecial` bằng `Method.invoke()` hoặc giả định mọi caller đều được phép gọi trực tiếp triển khai lớp cha.

Trong ứng dụng thông thường, một lựa chọn dễ bảo trì hơn là thiết kế API rõ ràng: đưa phần hành vi chung vào phương thức trợ giúp có tên riêng (ví dụ `protected baseDescription()`), rồi để override chủ động gọi phần dùng chung đó khi cần.

## 6. Truy cập, đối số và ngoại lệ không biến mất khi dùng reflection

Dynamic dispatch chỉ giải thích **phương thức nào chạy**. `Method.invoke()` còn có các kiểm tra về quyền truy cập, receiver, đối số và ngoại lệ:

| Tình huống | Kết quả điển hình | Gợi ý xử lý |
|---|---|---|
| Receiver `null` với instance method | `NullPointerException` | Cung cấp đối tượng thực tế |
| Receiver không phải instance của lớp khai báo | `IllegalArgumentException` | Kiểm tra `method.getDeclaringClass().isInstance(receiver)` cho instance method |
| Số lượng/kiểu đối số không phù hợp | `IllegalArgumentException` | Chọn đúng chữ ký, chuẩn bị đúng đối số |
| Phương thức không truy cập được từ caller | `IllegalAccessException` | Sử dụng API công khai hoặc thiết kế quyền truy cập module phù hợp |
| Thân phương thức được gọi ném ngoại lệ | `InvocationTargetException` | Xem `getCause()` để biết ngoại lệ gốc |
| Không tìm thấy phương thức ở bước tra cứu | `NoSuchMethodException` | Kiểm tra tên, parameter types, `getMethod` so với `getDeclaredMethod` |

Ví dụ một override chủ động ném lỗi:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationExceptionDemo {
    public static class Base {
        public void execute() { }
    }

    public static class Child extends Base {
        @Override
        public void execute() {
            throw new IllegalStateException("Lỗi từ Child.execute");
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Method method = Base.class.getDeclaredMethod("execute");
        try {
            method.invoke(new Child());
        } catch (InvocationTargetException ex) {
            System.out.println(ex.getCause().getClass().getSimpleName());
            System.out.println(ex.getCause().getMessage());
        }
    }
}
```

Kết quả:

```text
IllegalStateException
Lỗi từ Child.execute
```

`InvocationTargetException` là lớp bọc do API reflection tạo ra khi phương thức đích phát sinh ngoại lệ; nó không có nghĩa dispatch đã chọn sai phương thức. Với các phương thức `void`, giá trị trả về của `Method.invoke()` là `null`.

### Quyền truy cập trên JDK hiện đại

Khả năng tìm thấy một `Method` không bảo đảm có quyền gọi nó. Các kiểm tra Java access control và ranh giới module vẫn áp dụng. Việc tùy tiện gọi `setAccessible(true)` không bảo đảm thành công với thành phần không được mở (`opens`) trong Java Platform Module System; việc bỏ qua kiểm tra truy cập có thể bị từ chối, chẳng hạn bằng `InaccessibleObjectException`.

Với code ứng dụng, nên ưu tiên phương thức `public` của kiểu có thể truy cập, hoặc khai báo `exports`/`opens` phù hợp khi thiết kế framework. Không phụ thuộc vào các cơ chế truy cập nội bộ hay flag mở module tùy tiện chỉ để buộc một lời gọi reflection thành công.

## 7. Kiểm chứng hợp đồng bằng các trường hợp thử tối thiểu

Các bài kiểm thử sau tập trung vào hành vi có thể quan sát được, độc lập với chi tiết JVM dùng cơ chế nào bên dưới để triển khai reflection:

| Thử nghiệm | `Method` lấy từ | Receiver | Kỳ vọng |
|---|---|---|---|
| Override instance | `Base.describe()` | `new Child()` | `Child.describe` |
| Không có override | `Base.format(Object)` | `new Child()` | `Base.format(Object): hello` |
| Static hiding | `Base.category()` | `null` | `Base.category` |
| Phương thức `final` | `Base.stable()` | `new Child()` | `Base.stable` |
| Sai loại receiver | `Child.describe()` | `new Base()` | `IllegalArgumentException` |
| Override ném lỗi | `Base.execute()` | `new Child()` ném `IllegalStateException` | `InvocationTargetException`, cause là `IllegalStateException` |

Với một kiểm thử tự động, nên so sánh **giá trị trả về hoặc loại ngoại lệ** thay vì kiểm tra nội bộ JDK, stack frame, chi tiết bytecode hay tốc độ của `Method.invoke()`. Sau JEP 416, triển khai Core Reflection có thể dùng MethodHandle bên trong; hợp đồng quan sát được ở các trường hợp trên vẫn là điểm cần bảo vệ khi nâng phiên bản JDK.

Một kiểm thử JUnit có thể biểu diễn điều kiện cốt lõi như sau (đặt trong lớp kiểm thử đã có `Base`/`Child`, cùng import JUnit phù hợp):

```java
@Test
void invokingBaseMethodDispatchesToChildOverride() throws Exception {
    Method method = Base.class.getDeclaredMethod("describe");
    Base receiver = new Child();

    assertEquals(Base.class, method.getDeclaringClass());
    assertEquals("Child.describe", method.invoke(receiver));
}
```

Test cố ý kiểm tra **hai sự kiện cùng lúc**: `Method` vẫn đại diện cho khai báo ở lớp cha, nhưng thân phương thức thực thi đến từ lớp con. Đây là bằng chứng trực tiếp cho hợp đồng cần ghi nhớ.

## 8. Những câu hỏi tự kiểm tra

1. `Base.class.getDeclaredMethod("describe").invoke(new Child())` chạy ở `Base` hay `Child`? Vì sao `getDeclaringClass()` vẫn trả `Base.class`?
2. Nếu `Child` chỉ thêm `format(String)` còn `Base` có `format(Object)`, tại sao truyền một `String` vào `Method` của `Base.format(Object)` vẫn không gọi `Child.format(String)`?
3. Vì sao một `Method` của phương thức `static` cùng tên với phương thức ở lớp con không thực hiện virtual dispatch?
4. Khi phương thức override ném `IllegalStateException`, caller của `Method.invoke()` quan sát ngoại lệ nào trực tiếp và lấy ngoại lệ gốc ra sao?
5. Tại sao không thể dùng `Base.class.getDeclaredMethod(...).invoke(child)` để buộc gọi bản triển khai `super`?

**Ghi nhớ:** `Method` mô tả phương thức được chọn để gọi; **receiver thực tế** quyết định bản override được thực thi khi phương thức là instance method có virtual dispatch. Phân biệt rõ bước tra cứu chữ ký, bước kiểm tra quyền truy cập và bước chọn triển khai sẽ giúp sử dụng reflection đúng trên các JDK hiện đại.
