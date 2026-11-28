# Primitive narrowing, đối số sai số lượng hoặc sai kiểu và IllegalArgumentException

## 1. Vấn đề: lời gọi reflection chỉ được kiểm tra đầy đủ lúc chạy

Trong Java, lời gọi phương thức thông thường được trình biên dịch kiểm tra theo chữ ký phương thức. Khi dùng Core Reflection, bạn có thể lấy một `java.lang.reflect.Method` hoặc `Constructor`, sau đó truyền đối số dưới dạng `Object...` vào thời điểm chạy.

Ví dụ:

```java
import java.lang.reflect.Method;

public class ReflectionIntro {
    public static long doubleValue(long number) {
        return number * 2;
    }

    public static void main(String[] args) throws Exception {
        Method method = ReflectionIntro.class.getMethod(
            "doubleValue", long.class
        );

        Object result = method.invoke(null, Integer.valueOf(7));
        System.out.println(result); // 14, kiểu kết quả là Long
    }
}
```

Tham số được khai báo là `long`, nhưng đối số thực tế là `Integer`. Phép gọi vẫn hợp lệ: reflection unbox `Integer` thành `int`, rồi **primitive widening** từ `int` sang `long`.

Ngược lại, reflection **không tự thực hiện primitive narrowing** từ `int` sang `byte`, ngay cả khi giá trị số là `7` và nằm trong phạm vi của `byte`.

Nếu sai số lượng đối số, sai kiểu không thể chuyển đổi hoặc yêu cầu narrowing, `Method.invoke` và `Constructor.newInstance` có thể ném `IllegalArgumentException` ngay ở bước kiểm tra đối số.

Đây là hợp đồng công khai của Java Reflection, còn áp dụng trên JDK hiện đại, bao gồm JDK 27. Java 18 thay đổi cách triển khai Core Reflection bên trong qua JEP 416, nhưng không làm mất đi quy tắc chuyển đổi đối số này.

## 2. Các API liên quan và điểm phát sinh lỗi

| API | Chức năng | Trường hợp liên quan đến IllegalArgumentException |
| --- | --- | --- |
| `Method.invoke(receiver, args...)` | Gọi method qua reflection. | Sai số lượng đối số, sai kiểu, unboxing thất bại, cần primitive narrowing, receiver sai kiểu. |
| `Constructor.newInstance(args...)` | Tạo object qua constructor đã chọn. | Sai số lượng/kiểu đối số, unboxing thất bại hoặc cần primitive narrowing. |
| `Field.set(receiver, value)` | Ghi giá trị field. | Giá trị không chuyển được sang kiểu field bằng identity hoặc widening; receiver sai kiểu. |
| `Array.set(array, index, value)` | Ghi phần tử mảng qua reflection. | Mảng/giá trị sai kiểu hoặc không thể chuyển đổi phù hợp. |
| `Field.getInt`, `Array.getInt` và các biến thể typed | Đọc dữ liệu primitive theo kiểu đích được chỉ định. | Chuyển đổi cần narrowing hoặc kiểu nguồn không phù hợp. |

Bài tập trung trước hết vào `Method.invoke` và `Constructor.newInstance`, sau đó đối chiếu với `Field` và `Array` để thấy quy tắc nhất quán.

> `IllegalArgumentException` là unchecked exception. Vì vậy, nó không cần được liệt kê trong mệnh đề `throws` của chữ ký `Method.invoke`, dù Javadoc ghi rõ trường hợp này trong phần Throws.

## 3. Primitive widening và primitive narrowing

### 3.1. Primitive widening được phép

Widening primitive conversion là chuyển từ kiểu primitive nguồn sang kiểu đích rộng hơn theo quy tắc của Java Language Specification.

Các hướng widening thông thường:

| Kiểu nguồn | Kiểu đích widening được phép |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có primitive numeric widening sang kiểu khác. |
| `boolean` | Chỉ có identity conversion với `boolean`; không chuyển sang kiểu số. |

Ví dụ một method nhận `long`:

```java
public static long acceptLong(long value) {
    return value;
}
```

Các giá trị `Byte`, `Short`, `Character`, `Integer` hoặc `Long` có thể được unbox rồi widening nếu cần để khớp tham số `long`.

```java
Method method = Example.class.getMethod("acceptLong", long.class);

method.invoke(null, Byte.valueOf((byte) 5));      // OK
method.invoke(null, Short.valueOf((short) 5));    // OK
method.invoke(null, Integer.valueOf(5));         // OK
method.invoke(null, Long.valueOf(5L));           // OK
```

Các ví dụ giả định `Example` là lớp public có method `acceptLong` public static như trên.

Widening là quy tắc theo **kiểu**, không phải lời hứa mọi giá trị số đều giữ nguyên độ chính xác. Ví dụ `long` sang `float` là widening hợp lệ trong Java, nhưng vẫn có thể mất precision đối với những số nguyên lớn.

### 3.2. Primitive narrowing bị từ chối

Narrowing là chuyển đổi theo hướng có khả năng mất miền giá trị hoặc độ chính xác, ví dụ:

- `int` sang `short` hoặc `byte`.
- `long` sang `int`.
- `double` sang `float`.
- `float` sang `long`.
- `short` sang `char` hoặc chiều ngược lại.

Giả sử method nhận `byte`:

```java
public static byte acceptByte(byte value) {
    return value;
}
```

Phép gọi sau bị từ chối:

```java
Method method = Example.class.getMethod("acceptByte", byte.class);

method.invoke(null, Integer.valueOf(7));
// IllegalArgumentException: cần narrowing từ int sang byte
```

Giá trị `7` vừa miền `byte`, nhưng reflection không kiểm tra giá trị rồi tự giảm kiểu. Nó kiểm tra khả năng chuyển đổi hợp lệ từ kiểu primitive nguồn sau unboxing (`int`) tới kiểu tham số đích (`byte`).

Đây là điểm rất dễ nhầm với cú pháp gán một hằng số lúc biên dịch:

```java
byte valid = 7; // Hợp lệ: constant narrowing trong assignment context.
```

Lời gọi reflection không vận dụng quy tắc đặc biệt của assignment context đó. Theo JLS, method invocation context không có implicit narrowing của integer constant expression.

### 3.3. Ép kiểu tường minh trước khi gọi

Nếu bạn thực sự muốn truyền một giá trị `int` vào method nhận `byte`, hãy quyết định chuyển đổi ở phía caller:

```java
int value = 7;
byte converted = (byte) value;

method.invoke(null, Byte.valueOf(converted)); // OK
```

Với dữ liệu có thể vượt miền, cần kiểm tra trước để tránh kết quả bị cắt hoặc đổi dấu:

```java
static byte toByteExact(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException(
            "Value is outside the byte range: " + value
        );
    }
    return (byte) value;
}
```

Sau đó:

```java
byte converted = toByteExact(127);
method.invoke(null, Byte.valueOf(converted));
```

Lúc này, narrowing diễn ra một cách **tường minh và có kiểm soát trong code của caller**. Reflection chỉ nhận đối số kiểu `Byte` tương ứng với tham số `byte`.

Đối với `long` sang `int`, có thể dùng `Math.toIntExact(long)` để phát hiện overflow thay vì cast trực tiếp.

## 4. Boxing, unboxing và reference conversion

`Method.invoke` có chữ ký:

```java
Object invoke(Object obj, Object... args)
```

Phần tử trong `args` là các tham chiếu object. Vì vậy, khi truyền primitive từ Java source code vào `invoke`, trình biên dịch thường boxing thành wrapper trước.

Ví dụ:

```java
method.invoke(null, 5);
```

Giá trị `5` có kiểu primitive `int` ở biểu thức nguồn; ở điểm gọi `invoke` nó được boxing thành `Integer`. Reflection sau đó unbox sang `int` và có thể widening để khớp tham số đích.

### 4.1. Tham số primitive và wrapper khác nhau

Xét hai phương thức:

```java
public static void takesLong(long value) {
}

public static void takesLongObject(Long value) {
}
```

Hai chữ ký không giống nhau:

| Kiểu tham số đích | Đối số `Integer.valueOf(5)` | Kết quả |
| --- | --- | --- |
| `long` | Unbox `Integer` thành `int`, widen thành `long`. | Hợp lệ. |
| `Long` | `Integer` không là instance của `Long`. | `IllegalArgumentException`. |
| `Number` | `Integer` là subclass của `Number`. | Hợp lệ qua widening reference. |
| `Object` | `Integer` là object. | Hợp lệ. |

Điều quan trọng: reflection không tự tạo một wrapper `Long` mới từ một wrapper `Integer` chỉ vì hai kiểu đó chứa số.

### 4.2. Null cho reference và primitive

Nếu method nhận tham số tham chiếu như `String`, `null` là đối số hợp lệ:

```java
Method text = Example.class.getMethod("echo", String.class);
text.invoke(null, (Object) null); // Gửi đúng một đối số null.
```

Nếu method nhận primitive như `int` hoặc `long`, không thể unbox `null` thành primitive:

```java
Method number = Example.class.getMethod("acceptLong", long.class);
number.invoke(null, (Object) null);
// IllegalArgumentException: unboxing conversion thất bại.
```

Cast `(Object) null` ở đây có mục đích rõ ràng: biểu thị một phần tử `null` trong danh sách đối số của method phản chiếu.

Không nhầm nó với `(Object[]) null` – trường hợp này truyền mảng đối số `null`, được diễn giải là không có đối số khi underlying method không có tham số.

### 4.3. Không tự parse String thành number

Method có tham số `int` không chấp nhận chuỗi `"42"` chỉ vì có thể đọc nó thành số:

```java
Method number = Example.class.getMethod("acceptLong", long.class);
number.invoke(null, "42"); // IllegalArgumentException
```

Phải parse và kiểm tra dữ liệu trước:

```java
long value = Long.parseLong("42");
number.invoke(null, Long.valueOf(value)); // OK
```

Nếu chuỗi không hợp lệ, `Long.parseLong` ném `NumberFormatException`. Đây là lỗi do bước parse của caller, không phải chuyển đổi được thực hiện bên trong `Method.invoke`.

## 5. Đối số sai số lượng: wrong number of arguments

Một `Method` đã được lấy theo chữ ký cụ thể. Khi gọi `invoke`, số phần tử trong mảng đối số phải phù hợp số tham số formal của method đó.

Ví dụ:

```java
public static int add(int left, int right) {
    return left + right;
}
```

Lấy method:

```java
Method add = Example.class.getMethod(
    "add", int.class, int.class
);
```

Các trường hợp:

```java
add.invoke(null, 1, 2);      // OK: 2 đối số.
add.invoke(null, 1);         // IllegalArgumentException: thiếu 1.
add.invoke(null, 1, 2, 3);   // IllegalArgumentException: thừa 1.
add.invoke(null);            // IllegalArgumentException: thiếu 2.
```

Có thể kiểm tra số lượng và thứ tự kiểu tham số trước khi gọi:

```java
System.out.println(add.getParameterCount()); // 2
System.out.println(
    java.util.Arrays.toString(add.getParameterTypes())
);
// [int, int]
```

`getParameterCount()` và `getParameterTypes()` là cách chẩn đoán chắc chắn hơn việc đoán theo tên method.

### 5.1. Receiver không nằm trong args

Tham số thứ nhất của `Method.invoke`, tức `obj`, là receiver dùng cho instance method. Nó không được tính vào số tham số formal của method đích.

Ví dụ:

```java
public int addOne(int value) {
    return value + 1;
}
```

Lời gọi đúng:

```java
Example receiver = new Example();
Method m = Example.class.getMethod("addOne", int.class);

m.invoke(receiver, 10); // OK: receiver + một đối số int.
```

`m.getParameterCount()` trả `1`, không phải `2`.

### 5.2. Constructor cũng kiểm tra arity

Constructor có hợp đồng tương tự:

```java
public class Invoice {
    private final long amount;

    public Invoice(long amount) {
        this.amount = amount;
    }

    public long amount() {
        return amount;
    }
}
```

Lấy constructor và gọi:

```java
Constructor<Invoice> ctor =
    Invoice.class.getConstructor(long.class);

Invoice invoice = ctor.newInstance(Integer.valueOf(20));
// OK: Integer -> int -> long.

ctor.newInstance();
// IllegalArgumentException: thiếu một đối số.

ctor.newInstance(20L, "extra");
// IllegalArgumentException: thừa một đối số.
```

Một số constructor có tham số ẩn do ngôn ngữ sinh ra, chẳng hạn constructor của non-static inner class cần enclosing instance. Nếu số lượng không như dự tính, kiểm tra `getParameterCount()` và `getParameterTypes()` của `Constructor` thay vì dựa vào chữ ký nhìn thấy trong mã nguồn.

## 6. Phân biệt tìm method với gọi method

`Class.getMethod` hoặc `getDeclaredMethod` cần tên và kiểu tham số formal **chính xác** để tìm đúng method.

Giả sử lớp có:

```java
public static long acceptLong(long value) {
    return value;
}
```

Tìm theo chữ ký chính xác:

```java
Method method = Example.class.getMethod("acceptLong", long.class);
```

Tìm bằng `int.class`:

```java
Example.class.getMethod("acceptLong", int.class);
// NoSuchMethodException: không có overload tham số int.
```

Điều này không mâu thuẫn với việc một `Integer` có thể được truyền khi gọi `method.invoke` đối với method `acceptLong(long)`.

Hai giai đoạn khác nhau:

| Giai đoạn | Đầu vào | Hành vi |
| --- | --- | --- |
| Lookup | Tên method và mảng `Class` của kiểu tham số formal. | Tìm chữ ký đã khai báo; không tự chọn overload qua widening. |
| Invocation | Method đã chọn, receiver và các giá trị thực tế. | Kiểm tra arity/kiểu, thực hiện các conversion được cho phép rồi mới gọi method. |

Không có overload resolution động chỉ vì bạn dùng reflection. Nếu class có cả `process(int)` và `process(long)`, bạn phải chọn đúng `Method` trước rồi mới gọi.

## 7. Varargs: method có dấu ... vẫn có một tham số mảng

Hai cấp varargs dễ bị nhầm:

1. `Method.invoke(Object obj, Object... args)` tự nó là varargs ở phía caller.
2. Underlying method bạn đang gọi cũng có thể khai báo `String...` hoặc `int...`.

Ví dụ:

```java
public static int countNames(String... names) {
    return names.length;
}
```

Ở JVM, chữ ký của phương thức này có một tham số `String[]`:

```java
Method m = Example.class.getMethod(
    "countNames", String[].class
);

System.out.println(m.isVarArgs());        // true
System.out.println(m.getParameterCount()); // 1
```

Gọi đúng: truyền một mảng `String[]` như **một phần tử** trong danh sách `Object...` của `Method.invoke`:

```java
String[] names = {"An", "Bình"};
Object result = m.invoke(null, (Object) names);
System.out.println(result); // 2
```

Hoặc đóng gói đối số tường minh:

```java
m.invoke(null, new Object[] {names}); // OK.
```

Còn câu lệnh:

```java
m.invoke(null, "An", "Bình");
// IllegalArgumentException: underlying method chỉ có một tham số String[].
```

Reflection không tự động gom hai đối số riêng thành một mảng `String[]` theo varargs của method đích.

### 7.1. Vì sao cần cast (Object) cho array?

Lời gọi không có cast như sau có thể bị trình biên dịch hiểu là truyền mảng `String[]` để tạo danh sách `Object...` của chính `Method.invoke`:

```java
m.invoke(null, names);
```

Vì `String[]` cũng là `Object[]`, compiler có thể xem từng phần tử chuỗi như các đối số riêng của `invoke`. Điều này dễ tạo lỗi sai số lượng hoặc sai kiểu.

Cast `(Object) names` nói rõ với compiler rằng bạn đang truyền **một đối số**, và đối số đó là một object có kiểu runtime `String[]`.

Tương tự, khi method đích khai báo `main(String[] args)`, cách gọi reflection quen thuộc là:

```java
mainMethod.invoke(null, (Object) new String[]{"alpha", "beta"});
```

### 7.2. Mảng null và một đối số null

Đối với method đích không có tham số:

```java
Method noArgs = Example.class.getMethod("ping");

noArgs.invoke(null);                     // OK.
noArgs.invoke(null, new Object[0]);       // OK.
noArgs.invoke(null, (Object[]) null);    // OK: coi như không có đối số.
```

Đối với method đích cần một đối số tham chiếu:

```java
Method echo = Example.class.getMethod("echo", String.class);

echo.invoke(null, (Object) null);        // OK: đúng một đối số null.
echo.invoke(null, (Object[]) null);      // IllegalArgumentException: 0 đối số.
```

Sự khác biệt này là về **cách đóng gói mảng đối số của Method.invoke**, chưa liên quan đến nội dung method đích.

## 8. Wrong receiver: instance method khác static method

Nếu underlying method là instance method, tham số `obj` của `invoke` phải là instance tương thích với class/interface khai báo method.

Ví dụ:

```java
Method instance = Example.class.getMethod("addOne", int.class);

instance.invoke(new Example(), 5); // OK.
instance.invoke("wrong receiver", 5);
// IllegalArgumentException: receiver sai kiểu.

instance.invoke(null, 5);
// NullPointerException: receiver null cho instance method.
```

Nếu underlying method là static, `obj` không được dùng và có thể là `null`:

```java
Method staticMethod = Example.class.getMethod(
    "acceptLong", long.class
);

staticMethod.invoke(null, 5); // OK.
```

Phân biệt:

- Receiver sai kiểu cho instance method → `IllegalArgumentException`.
- Receiver `null` cho instance method → `NullPointerException`.
- Đối số không hợp lệ cho tham số primitive → thường `IllegalArgumentException`.
- Việc tìm method theo tên/chữ ký không tồn tại → `NoSuchMethodException` ở bước lookup.

## 9. Phân biệt lỗi trước khi gọi và lỗi bên trong method đích

Đây là một trong những chỗ quan trọng nhất khi xử lý exception.

Giả sử method đích tự ném `IllegalArgumentException`:

```java
public static int validatePositive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("value must be positive");
    }
    return value;
}
```

Khi reflection nhận số lượng và kiểu đối số hợp lệ, method đích chạy rồi ném lỗi:

```java
Method m = Example.class.getMethod(
    "validatePositive", int.class
);

m.invoke(null, 0);
```

Ngoại lệ thoát ra từ `Method.invoke` ở tình huống này là **`InvocationTargetException`**. Nguyên nhân gốc nằm trong `getCause()` (hoặc `getTargetException()`) và là `IllegalArgumentException("value must be positive")` của method đích.

Ngược lại:

```java
m.invoke(null, "not a number");
```

sai kiểu đối số nên chính lớp reflection ném `IllegalArgumentException` trước khi method đích được gọi. Không có `InvocationTargetException` trong trường hợp này.

| Tình huống | Ngoại lệ bên ngoài | Có chạy method đích? |
| --- | --- | --- |
| Thiếu/thừa đối số. | `IllegalArgumentException`. | Không. |
| Cần primitive narrowing. | `IllegalArgumentException`. | Không. |
| Đối số tham chiếu sai kiểu. | `IllegalArgumentException`. | Không. |
| Method đích chủ động ném `IllegalArgumentException`. | `InvocationTargetException`, cause là `IllegalArgumentException`. | Có. |
| Method đích ném `IOException` hoặc một exception khác. | `InvocationTargetException`, cause là exception đích. | Có. |
| Method không đủ quyền truy cập. | `IllegalAccessException` hoặc lỗi access tương ứng. | Không. |

Nếu bạn chỉ `catch (IllegalArgumentException)` quanh `invoke`, bạn **không bắt được trực tiếp** lỗi nghiệp vụ nằm bên trong `InvocationTargetException`.

Ví dụ xử lý rõ ràng:

```java
try {
    Object result = m.invoke(null, 0);
    System.out.println(result);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable targetFailure = ex.getCause();
    System.err.println(
        "Method body failed: " + targetFailure
    );
} catch (IllegalArgumentException ex) {
    System.err.println(
        "Reflection arguments invalid: " + ex
    );
} catch (IllegalAccessException ex) {
    System.err.println(
        "Method is not accessible: " + ex
    );
}
```

Không dựa vào chuỗi thông báo exception để xác định hợp đồng. Thông báo và stack trace có thể khác giữa các JDK hoặc cách triển khai.

## 10. Chương trình thực hành hoàn chỉnh: Method.invoke

Lưu mã sau thành `ReflectionArgumentContractDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionArgumentContractDemo {
    public static final class Api {
        public static long widen(long value) {
            return value + 1;
        }

        public static byte acceptByte(byte value) {
            return value;
        }

        public static String echo(String value) {
            return value;
        }

        public static String join(String left, String right) {
            return left + "-" + right;
        }

        public static int count(String... values) {
            return values.length;
        }

        public static int throwFromBody(int value) {
            throw new IllegalArgumentException(
                "Invalid business value: " + value
            );
        }

        public int instance(int value) {
            return value;
        }
    }

    @FunctionalInterface
    interface CheckedCall {
        Object run() throws Exception;
    }

    private static void attempt(String label, CheckedCall call) {
        try {
            System.out.println(label + " -> " + call.run());
        } catch (InvocationTargetException ex) {
            System.out.println(
                label + " -> InvocationTargetException, cause="
                + ex.getCause().getClass().getSimpleName()
            );
        } catch (IllegalArgumentException ex) {
            System.out.println(label + " -> IllegalArgumentException");
        } catch (Exception ex) {
            System.out.println(
                label + " -> " + ex.getClass().getSimpleName()
            );
        }
    }

    public static void main(String[] args) throws Exception {
        Method widen = Api.class.getMethod("widen", long.class);
        Method byteMethod = Api.class.getMethod(
            "acceptByte", byte.class
        );
        Method echo = Api.class.getMethod("echo", String.class);
        Method join = Api.class.getMethod(
            "join", String.class, String.class
        );
        Method count = Api.class.getMethod(
            "count", String[].class
        );
        Method body = Api.class.getMethod(
            "throwFromBody", int.class
        );
        Method instance = Api.class.getMethod(
            "instance", int.class
        );

        attempt("int -> long", () ->
            widen.invoke(null, Integer.valueOf(7)));

        attempt("double -> long", () ->
            widen.invoke(null, Double.valueOf(7.0)));

        attempt("int -> byte", () ->
            byteMethod.invoke(null, Integer.valueOf(7)));

        attempt("Byte -> byte", () ->
            byteMethod.invoke(null, Byte.valueOf((byte) 7)));

        attempt("wrong reference type", () ->
            echo.invoke(null, Integer.valueOf(7)));

        attempt("reference null", () ->
            echo.invoke(null, (Object) null));

        attempt("too few arguments", () ->
            join.invoke(null, "A"));

        attempt("too many arguments", () ->
            join.invoke(null, "A", "B", "C"));

        attempt("varargs flattened", () ->
            count.invoke(null, "A", "B"));

        attempt("varargs packed", () ->
            count.invoke(null, (Object) new String[]{"A", "B"}));

        attempt("wrong receiver", () ->
            instance.invoke("wrong", 7));

        attempt("null receiver", () ->
            instance.invoke(null, 7));

        attempt("exception from body", () ->
            body.invoke(null, 0));
    }
}
```

Biên dịch và chạy trên JDK hiện đại:

```sh
javac ReflectionArgumentContractDemo.java
java ReflectionArgumentContractDemo
```

Kết quả dự kiến theo tên tình huống:

| Tình huống | Kết quả |
| --- | --- |
| `int -> long` | `8`. |
| `double -> long` | `IllegalArgumentException`. |
| `int -> byte` | `IllegalArgumentException`. |
| `Byte -> byte` | `7`. |
| `wrong reference type` | `IllegalArgumentException`. |
| `reference null` | `null`. |
| `too few arguments` | `IllegalArgumentException`. |
| `too many arguments` | `IllegalArgumentException`. |
| `varargs flattened` | `IllegalArgumentException`. |
| `varargs packed` | `2`. |
| `wrong receiver` | `IllegalArgumentException`. |
| `null receiver` | `NullPointerException`. |
| `exception from body` | `InvocationTargetException`, cause là `IllegalArgumentException`. |

Chương trình cố ý dùng method public và nested class public để không phải sửa access bằng `setAccessible(true)`. Điều này giữ bài thực hành tập trung vào hợp đồng đối số.

## 11. Constructor.newInstance: cùng luật chuyển đổi, khác API

`Constructor.newInstance(Object... initargs)` cũng unbox wrapper và cho phép method invocation conversions tương ứng.

Ví dụ hoàn chỉnh:

```java
import java.lang.reflect.Constructor;

public class ReflectionConstructorDemo {
    public static class Item {
        private final long count;

        public Item(long count) {
            this.count = count;
        }

        public long count() {
            return count;
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Item> ctor =
            Item.class.getConstructor(long.class);

        Item item = ctor.newInstance(Integer.valueOf(12));
        System.out.println(item.count()); // 12

        try {
            ctor.newInstance(Double.valueOf(12.0));
        } catch (IllegalArgumentException ex) {
            System.out.println("Narrowing is not supported");
        }

        try {
            ctor.newInstance(); // Không truyền đối số.
        } catch (IllegalArgumentException ex) {
            System.out.println("Wrong argument count");
        }
    }
}
```

Constructor yêu cầu một `long`, nên `Integer -> int -> long` hợp lệ, còn `Double -> double -> long` là narrowing và bị từ chối.

Nếu **code trong constructor** ném exception, lời gọi reflective `Constructor.newInstance` bọc exception đó vào `InvocationTargetException`, tương tự `Method.invoke`.

Nếu constructor được lấy bằng `getConstructor` với chữ ký không tồn tại, lỗi là `NoSuchMethodException` ở bước lookup. Trường hợp constructor của enum không được gọi để tự tạo instance theo cách này, vì `newInstance` có quy tắc từ chối riêng đối với enum.

## 12. Field.set và Array.set: quy tắc widening/narrowing tương ứng

Hợp đồng này không chỉ xuất hiện khi gọi method hoặc constructor. Core Reflection còn cho phép đọc/ghi field và array element.

### 12.1. Field.set

```java
import java.lang.reflect.Field;

public class ReflectionFieldDemo {
    public static class Holder {
        public long total;
        public byte small;
    }

    public static void main(String[] args) throws Exception {
        Holder holder = new Holder();

        Field total = Holder.class.getField("total");
        total.set(holder, Integer.valueOf(8)); // int -> long, OK.
        System.out.println(holder.total);       // 8

        Field small = Holder.class.getField("small");
        try {
            small.set(holder, Integer.valueOf(8));
        } catch (IllegalArgumentException ex) {
            System.out.println("Cannot narrow int to byte");
        }

        small.set(holder, Byte.valueOf((byte) 8)); // OK.
        System.out.println(holder.small);          // 8
    }
}
```

`Field.set` unbox đối số nếu field có kiểu primitive rồi cho phép identity hoặc widening conversion. Không có primitive narrowing tự động.

Nếu field là instance field nhưng receiver sai kiểu, `Field.set` có thể ném `IllegalArgumentException`. Nếu receiver `null` cho instance field, lỗi là `NullPointerException`.

Field `final` hoặc không accessible còn chịu các quy định quyền ghi riêng. Không nên sửa modifier hoặc vượt giới hạn module chỉ để ép một thao tác `set` thành công.

### 12.2. Array.set

```java
import java.lang.reflect.Array;

public class ReflectionArrayDemo {
    public static void main(String[] args) {
        int[] values = new int[2];

        Array.set(values, 0, Short.valueOf((short) 3));
        System.out.println(values[0]); // 3, short -> int.

        try {
            Array.set(values, 1, Long.valueOf(3L));
        } catch (IllegalArgumentException ex) {
            System.out.println("Cannot narrow long to int");
        }

        Array.set(values, 1, Integer.valueOf(3));
        System.out.println(values[1]); // 3
    }
}
```

Khi array có kiểu phần tử primitive, `Array.set` unbox wrapper rồi chỉ chấp nhận conversion thích hợp. Kiểu `long` không thể được narrowing tự động sang `int`.

Các biến thể như `Array.setLong` hoặc `Array.getInt` cũng tuân theo quy tắc primitive widening được nêu trong API. Lỗi index ngoài phạm vi là `ArrayIndexOutOfBoundsException`; mảng `null` dẫn đến `NullPointerException`. Đó là các lỗi khác với `IllegalArgumentException` vì sai conversion.

## 13. Generic type không được kiểm tra như kiểu cụ thể tại Method.invoke

Đối với tham số generic như `List<String>`, chữ ký runtime dùng kiểu đã erasure, thường là `List`.

```java
public static void consume(java.util.List<String> names) {
    for (String name : names) {
        System.out.println(name.toUpperCase());
    }
}
```

Ở bước reflection, `getParameterTypes()` thấy kiểu runtime `List.class`. Nếu caller truyền một `List<Integer>`, phần kiểm tra reference type có thể chấp nhận vì đối tượng vẫn là `List` tại runtime. Khi body cố dùng phần tử như `String`, exception có thể phát sinh **trong method đích**.

Vì thế, `IllegalArgumentException` ở bước kiểm tra reflection không thay thế việc validation nội dung collection và hợp đồng generic của ứng dụng. Với dữ liệu từ JSON hoặc nguồn bên ngoài, hãy validate đầy đủ trước khi gọi.

## 14. Chẩn đoán dựa trên loại lỗi, không dựa vào thông báo

Khi gặp lỗi, hãy tách theo giai đoạn:

```text
Tìm Method / Constructor
          |
          +-- Không tìm thấy chữ ký --> NoSuchMethodException
          |
          v
Kiểm tra receiver / access
          |
          +-- Receiver null của instance --> NullPointerException
          +-- Receiver sai kiểu --> IllegalArgumentException
          +-- Không đủ quyền --> IllegalAccessException / access error
          |
          v
Kiểm tra số lượng và kiểu đối số
          |
          +-- Sai arity --> IllegalArgumentException
          +-- Unboxing thất bại --> IllegalArgumentException
          +-- Narrowing / kiểu không tương thích --> IllegalArgumentException
          |
          v
Chạy body của method / constructor
          |
          +-- Body ném exception --> InvocationTargetException (cause là lỗi gốc)
          |
          v
Trả kết quả
```

Lưu ý một số quá trình như khởi tạo lớp có thể phát sinh `ExceptionInInitializerError` theo hợp đồng API. Sơ đồ tập trung vào những lỗi thường gặp liên quan đến đối số và lời gọi.

### 14.1. Tập thông tin nên ghi khi debug

Ghi nhận:

- Tên lớp, method hoặc constructor đã chọn.
- `getParameterCount()` và `getParameterTypes()`.
- `isVarArgs()` và kiểu tham số mảng cuối.
- Số lượng phần tử thực sự trong `Object[]` đưa vào invocation.
- Kiểu runtime của từng argument, ví dụ `Integer`, `Long`, `String[]`, hoặc `null`.
- Receiver là `null` hay instance của lớp nào.
- Ngoại lệ ngoài cùng và `getCause()` nếu là `InvocationTargetException`.

Ví dụ một helper chẩn đoán đối số:

```java
static void printArguments(java.lang.reflect.Method method, Object[] args) {
    System.out.println("Method: " + method);
    System.out.println("Formal: " +
        java.util.Arrays.toString(method.getParameterTypes()));

    System.out.println("Varargs: " + method.isVarArgs());
    System.out.println("Actual count: " + args.length);

    for (int i = 0; i < args.length; i++) {
        Object arg = args[i];
        System.out.println(i + ": " +
            (arg == null ? "null" : arg.getClass().getTypeName()));
    }
}
```

Helper này không tự quyết định mọi trường hợp conversion; nó giúp bạn quan sát đúng chữ ký và dữ liệu mà reflection sẽ kiểm tra. Với hệ thống thực tế, không ghi giá trị bí mật hoặc dữ liệu cá nhân vào log chỉ để chẩn đoán.

## 15. Các lỗi thực tế thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Method nhận `byte` nhưng truyền `Integer(7)` bị IAE. | `int -> byte` là narrowing, dù giá trị vừa miền. | Kiểm tra miền, cast tường minh và truyền `Byte`. |
| Method nhận `long` nhưng truyền `Double(7.0)` bị IAE. | `double -> long` là narrowing. | Chọn quy tắc làm tròn/kiểm tra miền riêng trước khi chuyển. |
| Method nhận `Long` nhưng truyền `Integer` bị IAE. | Hai wrapper là hai reference type khác nhau. | Dùng `Long.valueOf(...)` nếu phù hợp hợp đồng. |
| Method nhận primitive nhưng truyền `null`. | Không unbox được `null` thành primitive. | Cấp giá trị primitive hợp lệ hoặc đổi API sang kiểu tham chiếu nếu cho phép null. |
| Method nhận hai tham số nhưng chỉ truyền một. | Sai arity. | Xem `getParameterCount()`. |
| Truyền mảng `String[]` nhưng bị sai arity. | Varargs của `Method.invoke` có thể làm phẳng mảng. | Dùng `(Object) names` hoặc `new Object[]{names}`. |
| Method có tham số `String...` nhưng truyền từng chuỗi. | Target thực tế có một tham số `String[]`. | Đóng gói chuỗi thành mảng đúng kiểu. |
| Lookup bằng `int.class` cho method nhận `long` thất bại. | Lookup cần chữ ký formal chính xác. | Dùng `long.class`; widening diễn ra lúc invoke. |
| Instance method được gọi với receiver `null`. | Không có object để dispatch. | Truyền receiver hợp lệ. |
| Receiver sai kiểu. | Receiver không là instance của lớp/interface khai báo method. | Kiểm tra `method.getDeclaringClass()`. |
| Method đích ném `IllegalArgumentException` nhưng catch IAE không bắt. | Lỗi body được bọc trong `InvocationTargetException`. | Catch wrapper và kiểm tra `getCause()`. |
| Reflection call thành công rồi cast kết quả sai kiểu. | Kết quả primitive được boxing, ví dụ `long` thành `Long`. | Kiểm tra `getReturnType()` và cast đúng kiểu. |

## 16. Quy tắc thiết kế an toàn cho reflection caller

Khi dữ liệu đầu vào đến từ configuration, JSON, CLI hoặc plugin:

1. **Chọn Method/Constructor theo chữ ký chính xác.** Không dùng reflection để đoán overload qua giá trị runtime.
2. **So sánh arity trước khi gọi.** Dùng `getParameterCount()` và dữ liệu trong `Object[]`.
3. **Đóng gói varargs đúng kiểu mảng.** Chú ý `Method.invoke` cũng là varargs.
4. **Chuẩn hóa numeric input tường minh.** Parse string, kiểm tra phạm vi, quyết định cast hoặc làm tròn nếu cần.
5. **Không mong reflection tự narrowing.** Giá trị số vừa miền cũng không thay đổi luật conversion theo kiểu.
6. **Đối chiếu null với primitive/reference.** Primitive không nhận null; reference có thể nhận null.
7. **Phân biệt lỗi reflection và lỗi nghiệp vụ.** Bắt `InvocationTargetException` riêng và xem cause.
8. **Giữ access theo hợp đồng module.** Dùng member public hoặc một cơ chế truy cập hợp lệ; không cố sửa nội bộ JDK.
9. **Không phụ thuộc message của exception.** Phân loại bằng kiểu lỗi và trạng thái input.
10. **Kiểm thử bảng ca hợp lệ và không hợp lệ.** Bao gồm widening, narrowing, wrong arity, wrong type, null, varargs và target exception.

Không nên dùng `MethodHandle` hay cơ chế ép kiểu khác chỉ để né hợp đồng `Method.invoke`. Các API `java.lang.invoke` có luật adaptation và ngoại lệ riêng; nếu chuyển sang chúng, phải đọc hợp đồng tương ứng thay vì áp dụng máy móc quy tắc của Core Reflection.

## 17. Bài tập tự kiểm tra

1. Viết method `acceptLong(long)` rồi thử truyền `Byte`, `Integer`, `Long` và `Double` qua `Method.invoke`. Giải thích kết quả từng trường hợp.
2. Viết method `acceptByte(byte)` rồi truyền `Integer.valueOf(7)`. Vì sao lỗi xảy ra dù `7` thuộc miền byte?
3. Chuyển `int` sang `byte` với kiểm tra khoảng giá trị trước khi invoke.
4. Viết method có hai tham số. Thử thiếu một và thừa một argument; quan sát exception.
5. Dùng `getParameterCount()` và `getParameterTypes()` in chữ ký runtime của method.
6. Viết method nhận `String` và method nhận `int`. Thử truyền `null` với cast `(Object) null`; so sánh hai kết quả.
7. Viết method nhận `String...`. So sánh `m.invoke(null, "A", "B")` với `m.invoke(null, (Object) new String[]{"A","B"})`.
8. Dùng `getMethod` tra cứu `int.class` cho method chỉ có tham số `long.class`. Xác định exception ở lookup.
9. Gọi instance method với receiver đúng, sai kiểu và `null`. Phân biệt `IllegalArgumentException` với `NullPointerException`.
10. Để method đích tự ném `IllegalArgumentException`. Bắt `InvocationTargetException` và đọc nguyên nhân gốc.
11. Tạo constructor nhận `long` và thử một đối số `Integer`, `Double`, và không truyền đối số.
12. Thử `Field.set` cho `long` và `byte` field với `Integer`; giải thích trường hợp chấp nhận/từ chối.
13. Thử `Array.set` với `Short` và `Long` vào mảng `int[]`; ghi nhận kết quả.
14. Lập một bảng test đảm bảo kết quả không thay đổi khi nâng JDK trong dự án của bạn.

**Tiêu chí hoàn thành:** bạn phân biệt được primitive widening với narrowing, giải thích vì sao narrowing không tự động trong Core Reflection, dự đoán được `IllegalArgumentException` khi sai arity/kiểu đối số, đóng gói đúng varargs, và phân loại được ngoại lệ reflection với `InvocationTargetException` từ method/constructor đích.

## 18. Tài liệu tham khảo

- [Oracle Java SE 27 — Method API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Method.html): hợp đồng của `Method.invoke`, narrowing/widening, receiver, unboxing, sai số lượng/kiểu và `InvocationTargetException`.
- [Oracle Java SE 27 — Constructor API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Constructor.html): hợp đồng của `Constructor.newInstance`, arity, unboxing, widening/narrowing và exception của constructor đích.
- [Oracle Java SE 27 — Field API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Field.html): `Field.set`, identity/widening conversion, receiver và access checks.
- [Oracle Java SE 27 — Array API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Array.html): `Array.set` và các typed accessors, widening/narrowing của primitive array.
- [Oracle Java SE 27 — Java Language Specification, Chapter 5](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html): các kiểu conversion, method invocation context và sự khác nhau với assignment context.
- [Oracle Java SE 27 — Executable API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Executable.html): `getParameterCount()`, `getParameterTypes()` và `isVarArgs()`.
- [Oracle Java Tutorials — Invoking Methods](https://docs.oracle.com/javase/tutorial/reflect/member/methodInvocation.html): ví dụ thực tế về đóng gói array trong `Method.invoke`.
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): bối cảnh thay đổi implementation từ Java 18; hợp đồng API Core Reflection vẫn là điểm cần kiểm chứng.
