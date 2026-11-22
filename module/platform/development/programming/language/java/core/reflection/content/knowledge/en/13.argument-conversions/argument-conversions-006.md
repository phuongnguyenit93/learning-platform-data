# Receiver `null` khi gọi phương thức instance bằng Java Reflection

Khi dùng Java Reflection để gọi một phương thức, cần phân biệt **đối tượng nhận lời gọi** (receiver) với **các đối số của phương thức**. Trong `Method.invoke(Object obj, Object... args)`, tham số `obj` là receiver; còn `args` là các giá trị truyền cho những tham số do phương thức khai báo.

Với **instance method**, Java phải có một đối tượng thực để thực hiện lời gọi. Nếu receiver là `null`, `Method.invoke` ném **`NullPointerException` trực tiếp**. Với **static method**, không cần receiver nên đối số `obj` được bỏ qua và có thể là `null`.

Sự khác biệt này quan trọng trong nhóm **Đối số và chuyển đổi**: mã gọi Reflection thường truyền cả receiver, tham số và các giá trị `null` động. Nếu đặt sai vị trí, lỗi xuất hiện trước khi logic của phương thức đích chạy, hoặc xảy ra một kiểu lỗi khác với dự đoán.

## 1. Phân biệt receiver và đối số phương thức

Chữ ký cần nhớ:

```java
Object Method.invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException;
```

Đây là **chữ ký minh họa API**, không phải khai báo một phương thức mới có thể đặt trực tiếp vào class để biên dịch. Ý nghĩa các thành phần:

| Thành phần | Vai trò | Với phương thức instance | Với phương thức static |
| --- | --- | --- | --- |
| `Method` | Metadata của phương thức đã tra cứu | Xác định phương thức instance sẽ gọi | Xác định phương thức static sẽ gọi |
| `obj` | Receiver | Phải là instance tương thích; **không được `null`** | Bị bỏ qua; thường truyền `null` cho rõ ý |
| `args` | Các đối số thực tế của method đích | Khớp số lượng/kiểu với tham số khai báo | Cũng phải khớp số lượng/kiểu |
| Giá trị trả về | Kết quả sau khi method thực thi | Trả giá trị đóng hộp nếu primitive; `null` nếu return type là `void` | Cùng quy tắc |

Giả sử:

```java
public class Calculator {
    public int add(int a, int b) { return a + b; }
    public static int twice(int value) { return value * 2; }
}
```

Các lời gọi Reflection tương ứng:

```java
Calculator calculator = new Calculator();

Method add = Calculator.class.getMethod(
        "add", int.class, int.class);
Object result = add.invoke(calculator, 3, 4); // Integer(7)

Method twice = Calculator.class.getMethod(
        "twice", int.class);
Object doubled = twice.invoke(null, 5);      // Integer(10)
```

Hai khối trên là **mã minh họa** cần được đặt trong ngữ cảnh có `import java.lang.reflect.Method;` và xử lý checked exceptions. Ví dụ hoàn chỉnh có thể biên dịch/chạy ở mục 4. Điểm quyết định là `calculator` nằm ở **vị trí receiver**, còn `3` và `4` là tham số thật của method đích.

## 2. Vì sao receiver `null` gây `NullPointerException`?

Instance method sử dụng một đối tượng làm `this`, dù nội dung method có đọc field của object hay không. Phương thức phản chiếu thực hiện cơ chế gọi instance trên receiver được đưa vào. Không có receiver hợp lệ thì method đích không thể được gọi.

Ví dụ:

```java
Method add = Calculator.class.getMethod(
        "add", int.class, int.class);
add.invoke(null, 3, 4); // NullPointerException trực tiếp
```

Lời gọi này **không chuyển sang gọi static**, không tạo một `Calculator` mới, và không suy đoán receiver từ tham số `3` hay `4`. Dù đối số khác đúng kiểu, receiver vẫn không hợp lệ.

Các trường hợp tương ứng:

| Phương thức đích | Gọi qua Reflection | Kết quả |
| --- | --- | --- |
| `int add(int, int)` (instance) | `add.invoke(calculator, 3, 4)` | Hợp lệ nếu có quyền và kiểu phù hợp |
| `int add(int, int)` (instance) | `add.invoke(null, 3, 4)` | `NullPointerException` |
| `int add(int, int)` (instance) | `add.invoke(new Object(), 3, 4)` | `IllegalArgumentException`: sai loại receiver |
| `static int twice(int)` | `twice.invoke(null, 5)` | Hợp lệ; receiver không cần thiết |
| `static int twice(int)` | `twice.invoke(calculator, 5)` | Hợp lệ; receiver được bỏ qua |

Một subclass cũng có thể dùng làm receiver nếu tương thích với lớp/interface khai báo. Khi gọi instance method bằng Reflection, **dynamic dispatch** vẫn có thể chọn bản override trên lớp runtime của receiver. Nhưng một receiver `null` không có runtime class để dispatch.

## 3. Kiểm tra `static` trước khi truyền receiver

Khi code chỉ có một `Method` lấy từ cấu hình, không nên suy đoán static/instance qua tên hay giá trị đầu vào. Dùng modifier:

```java
boolean isStatic = java.lang.reflect.Modifier.isStatic(
        method.getModifiers());

Object receiver = isStatic ? null : target;
Object value = method.invoke(receiver, arguments);
```

Đây là **đoạn minh họa**, giả định `method`, `target`, `arguments` đã khai báo và có xử lý exceptions phù hợp. Với instance method, cần kiểm tra `target` không `null` và có kiểu tương thích trước khi gọi.

**Cách kiểm tra an toàn hơn:**

```java
if (!java.lang.reflect.Modifier.isStatic(method.getModifiers())) {
    java.util.Objects.requireNonNull(target, "instance receiver");
    if (!method.getDeclaringClass().isInstance(target)) {
        throw new IllegalArgumentException("Wrong receiver type");
    }
}
Object receiver = java.lang.reflect.Modifier.isStatic(
        method.getModifiers()) ? null : target;
Object value = method.invoke(receiver, arguments);
```

Đây cũng là đoạn minh họa, áp dụng khi receiver được dùng cho phương thức instance. Thực tế có thể cần xét ràng buộc quyền truy cập, method của interface, proxy hoặc subclass, và chuẩn bị mảng đối số đúng số lượng.

Phương thức `canAccess(receiver)` của `AccessibleObject` có quy tắc receiver khác **kiểu lỗi** của `Method.invoke`: với instance method, `canAccess(null)` ném **`IllegalArgumentException`**, trong khi `invoke(null, ...)` ném **`NullPointerException`**. Với static method, `canAccess` yêu cầu đối số **đúng bằng `null`**, còn `invoke` bỏ qua receiver và chấp nhận cả giá trị khác `null`. Hai API không dùng cùng quy tắc kiểm tra tham số.

## 4. Ví dụ Java 17+ chạy độc lập: mọi nhánh quan trọng

Tạo tệp **`NullReceiverReflectionDemo.java`** với toàn bộ mã sau:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class NullReceiverReflectionDemo {
    public static class Counter {
        private int total = 10;

        public int add(int step) {
            total += step;
            return total;
        }

        public int current() {
            return total;
        }

        public String describe(String text) {
            return "length=" + text.length();
        }

        public static String label(String text) {
            return "label=" + text;
        }
    }

    public static void main(String[] args) throws Exception {
        Counter counter = new Counter();

        Method add = Counter.class.getMethod("add", int.class);
        try {
            add.invoke(null, 2);
        } catch (NullPointerException e) {
            System.out.println("nullReceiver=NullPointerException");
        }

        System.out.println("afterNullAttempt=" + counter.current());
        System.out.println("validInstance=" + add.invoke(counter, 2));

        try {
            add.invoke(new Object(), 3);
        } catch (IllegalArgumentException e) {
            System.out.println("wrongReceiver=IllegalArgumentException");
        }

        Method label = Counter.class.getMethod("label", String.class);
        System.out.println("isStatic="
                + Modifier.isStatic(label.getModifiers()));
        System.out.println("staticNull=" + label.invoke(null, "A"));
        System.out.println("staticIgnored="
                + label.invoke("not a Counter", "B"));

        Method describe = Counter.class.getMethod(
                "describe", String.class);
        try {
            describe.invoke(counter, (Object) null);
        } catch (InvocationTargetException e) {
            System.out.println("methodThrew="
                    + e.getCause().getClass().getSimpleName());
        }

        try {
            describe.invoke(null, (Object) null);
        } catch (NullPointerException e) {
            System.out.println("nullReceiverBeforeBody="
                    + e.getClass().getSimpleName());
        }

        Method current = Counter.class.getMethod("current");
        try {
            current.canAccess(null);
        } catch (IllegalArgumentException e) {
            System.out.println("canAccessNull="
                    + e.getClass().getSimpleName());
        }
        System.out.println("canAccessValid="
                + current.canAccess(counter));
        System.out.println("currentValue=" + current.invoke(counter));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac NullReceiverReflectionDemo.java
java NullReceiverReflectionDemo
```

Kết quả dự kiến chính xác:

```text
nullReceiver=NullPointerException
afterNullAttempt=10
validInstance=12
wrongReceiver=IllegalArgumentException
isStatic=true
staticNull=label=A
staticIgnored=label=B
methodThrew=NullPointerException
nullReceiverBeforeBody=NullPointerException
canAccessNull=IllegalArgumentException
canAccessValid=true
currentValue=12
```

**Diễn giải:**

1. `add.invoke(null, 2)` ném `NullPointerException` **trực tiếp**, vì `add` là instance method. Phương thức chưa chạy nên `afterNullAttempt` vẫn là 10.
2. `add.invoke(counter, 2)` có receiver hợp lệ nên tăng `total` thành 12 và trả `Integer` được tự động nối thành chuỗi.
3. `new Object()` khác `null` nhưng vẫn **sai loại receiver**, nên nhận `IllegalArgumentException`.
4. `Counter.label` là static method. Receiver `null` được phép; thậm chí đối tượng chuỗi `"not a Counter"` cũng được **bỏ qua**, vì không có instance receiver.
5. `describe.invoke(counter, (Object) null)` có receiver đúng nhưng truyền **một đối số `null`** cho tham số `String text`. Method đích bắt đầu chạy rồi `text.length()` ném `NullPointerException`. Reflection bọc lỗi này trong `InvocationTargetException`.
6. Với `describe.invoke(null, (Object) null)`, **receiver** đã `null`, nên `NullPointerException` xảy ra **trước khi body method đích được thực thi**.
7. `current.canAccess(null)` ném `IllegalArgumentException`; `current.canAccess(counter)` trả `true` do đây là phương thức public và caller có quyền truy cập.

Ví dụ không dùng `setAccessible(true)` vì các method đang được gọi đều `public`. Việc bật bỏ qua kiểm tra truy cập không cần thiết để minh họa receiver.

## 5. Phân biệt `NullPointerException` trực tiếp với lỗi từ method đích

Đây là bẫy quan trọng nhất khi debug Reflection:

| Nguồn lỗi | Biểu hiện | Method đích đã chạy chưa? |
| --- | --- | --- |
| Instance receiver `null` | `Method.invoke` ném trực tiếp `NullPointerException` | Chưa |
| Receiver hợp lệ nhưng method đích dereference đối số `null` | `InvocationTargetException` có `getCause()` là `NullPointerException` | Rồi |
| Receiver khác `null` nhưng không phải instance phù hợp | `IllegalArgumentException` | Chưa |
| Số lượng/kiểu đối số truyền vào không phù hợp | `IllegalArgumentException` | Chưa |
| Caller không đủ quyền truy cập method | Có thể là `IllegalAccessException` | Chưa |

Một cách xử lý được thiết kế phù hợp:

```java
try {
    Object result = method.invoke(receiver, values);
    System.out.println(result);
} catch (InvocationTargetException e) {
    Throwable actualFailure = e.getCause();
    System.out.println("Method body failed: " + actualFailure);
} catch (NullPointerException e) {
    System.out.println("Check instance receiver: " + e);
} catch (IllegalArgumentException e) {
    System.out.println("Check receiver type and method arguments: " + e);
} catch (IllegalAccessException e) {
    System.out.println("Reflective access denied: " + e);
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập; các biến `method`, `receiver`, `values` cần được khai báo. Nếu method đích ném một exception, `InvocationTargetException.getCause()` là thông tin quan trọng để debug. Ngoài các loại trên, method static có thể kích hoạt việc khởi tạo class; nếu khởi tạo class thất bại, một lỗi như `ExceptionInInitializerError` có thể phát sinh.

Không nên chỉ bắt `InvocationTargetException` rồi tin rằng đã xử lý được `null` receiver. Lỗi receiver `null` của instance method **không phải** exception do method đích ném.

## 6. Receiver đúng kiểu: lớp cha, interface và override

Giả sử Reflection lấy metadata của instance method từ lớp cha:

```java
class Parent {
    public String name() { return "parent"; }
}
class Child extends Parent {
    @Override
    public String name() { return "child"; }
}
```

Khi dùng `Method m = Parent.class.getMethod("name");`, lời gọi `m.invoke(new Child())` thực thi override trên `Child` và trả `"child"`. Receiver vẫn phải **khác `null`** và là instance tương thích với declaring class hoặc subclass. Với interface method, receiver có thể là object của class triển khai interface.

Đoạn trên là minh họa, không có `main`. Điều quan trọng: receiver là một **instance**, không nhất thiết phải đúng class một cách tuyệt đối; việc `obj.getClass() == method.getDeclaringClass()` không bắt buộc. Do đó, kiểm tra kiểu hợp lý thường dùng `getDeclaringClass().isInstance(obj)` thay vì so sánh hai đối tượng `Class` bằng `==`.

Nếu method là `private`, việc gọi cần có quyền truy cập thích hợp (và khả năng bật override theo JPMS nếu cần) **ngoài** yêu cầu receiver hợp lệ. `setAccessible(true)` không bao giờ “biến instance method thành static” hoặc làm `null` trở thành một receiver hợp lệ.

## 7. Cách tránh lỗi trong framework và công cụ gọi động

Một reflection dispatcher hoặc plugin loader thường lưu tên method, loại method, target object và đối số ở các vị trí khác nhau. Chỉ cần quên gán target object, instance invocation sẽ hỏng dù tra cứu method và tham số chính xác.

Một quy trình hữu ích:

1. **Tra cứu đúng method:** dùng `getMethod` hoặc `getDeclaredMethod` với tên và kiểu tham số chính xác. Bước tra cứu không tự cung cấp receiver.
2. **Xác định static/instance:** kiểm tra `Modifier.isStatic(method.getModifiers())`. Với static có thể truyền receiver `null`; với instance phải có object đang sống và kiểu tương thích.
3. **Chuẩn bị đối số của method đích:** kiểm tra số lượng, kiểu, boxing/unboxing và chuyển đổi hợp lệ. Tách riêng khái niệm **receiver** khỏi mảng **arguments**.
4. **Kiểm tra quyền truy cập:** `canAccess(receiver)` có thể dùng để kiểm tra trước khi gọi khi truyền receiver đúng chuẩn API; còn `getDeclaredMethod` không tự cấp quyền.
5. **Gọi và phân loại lỗi:** phân biệt `NullPointerException` do receiver với `InvocationTargetException` bọc lỗi của code đích; phân biệt sai receiver type với sai argument.
6. **Không “chữa” null receiver bằng `setAccessible(true)`**. Nếu thiếu object, cần khởi tạo đúng hoặc lấy đúng instance từ container/factory/registry.

Các lỗi thường gặp khi debug:

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| Gọi `instanceMethod.invoke(null)` như gọi static | Instance method cần receiver hợp lệ; `null` ném NPE |
| Cho rằng `null` cho receiver là `null` cho tham số đầu tiên | Đây là hai vị trí khác nhau trong `Method.invoke` |
| Chỉ catch `InvocationTargetException` | NPE do receiver xảy ra ngoài method đích, không bọc kiểu này |
| Coi `canAccess(null)` và `invoke(null)` là cùng một phép kiểm tra | Với instance, API đầu ném IAE, API sau ném NPE |
| Tạo một object bất kỳ làm receiver của instance method | Receiver phải là instance tương thích của declaring class/interface |
| Cho rằng static method bắt buộc truyền instance | Receiver của static method bị bỏ qua; `null` là cách truyền rõ ràng nhất |
| Cho rằng `setAccessible(true)` giải quyết receiver `null` | Accessible flag chỉ liên quan kiểm tra quyền truy cập, không tạo receiver |
| Dùng varargs của `invoke` mà không kiểm tra mảng và ép kiểu | Có thể truyền nhầm số lượng đối số; bọc/ép kiểu rõ ý |

## 8. Ghi nhớ và tài liệu đối chiếu

**Quy tắc cốt lõi:** Với `Method.invoke(obj, args)`, **instance method → `obj` phải là instance hợp lệ, không được `null`**; **static method → `obj` được bỏ qua, thường truyền `null`**. Giá trị `null` nằm trong `args` là chuyện khác: đó là đối số method đích và có thể hợp lệ tùy kiểu/thao tác.

Tài liệu chuẩn Java 17:

- [Method.invoke(Object, Object...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)) — quy tắc receiver, chuyển đổi arguments và ngoại lệ.
- [AccessibleObject.canAccess(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#canAccess(java.lang.Object)) — kiểm tra quyền truy cập và yêu cầu receiver tương ứng.

Khi lỗi xuất hiện, luôn xác định **method có phải static không**, **receiver có đúng object không**, **đối số có đúng chữ ký không** và **exception phát sinh từ Reflection hay chính method đích**.