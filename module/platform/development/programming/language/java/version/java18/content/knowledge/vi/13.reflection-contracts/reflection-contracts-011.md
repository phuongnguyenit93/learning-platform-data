# Phân biệt Object[] của Method.invoke() với một tham số đích có kiểu mảng hoặc varargs

> **Chương:** Hợp đồng reflection  
> **Module học:** JAVA_VERSION_JAVA18 — học cách kiểm chứng hợp đồng API reflection trên JDK hiện đại. Java 18 có JEP 416, triển khai lại Core Reflection bằng Method Handle; quy tắc truyền đối số của `Method.invoke()` được giữ nguyên và vẫn hữu ích khi làm việc với JDK mới.  
> **Mục tiêu:** Phân biệt mảng `Object[]` biểu diễn **danh sách tham số của lời gọi phản chiếu** với một mảng là **giá trị của một tham số đích**; truyền đúng vào method thường nhận mảng, method khai báo varargs, trường hợp `null` và mảng kiểu nguyên thủy.

## 1. Tình huống dễ nhầm

Giả sử một phương thức nhận đúng **một** mảng chuỗi:

~~~java
public static int count(String[] names) {
    return names.length;
}
~~~

Gọi trực tiếp không có gì khó:

~~~java
String[] names = {"An", "Bình"};
int count = count(names); // 2
~~~

Nhưng khi gọi qua reflection:

~~~java
Method method = Demo.class.getMethod("count", String[].class);
method.invoke(null, names); // Dễ gây nhầm và có thể ném IllegalArgumentException!
~~~

Vấn đề là `Method.invoke()` **cũng có tham số varargs `Object... args`**. Một `String[]` vừa là mảng dữ liệu của method đích, vừa tương thích với kiểu `Object[]` ở call site của `invoke`. Trình biên dịch Java có thể xem từng phần tử trong `names` là từng đối số để truyền vào reflection, thay vì xem cả `names` là **một** đối số.

Sửa bằng cách chỉ rõ mảng đích là một giá trị:

~~~java
method.invoke(null, (Object) names);
// Hoặc đóng gói bằng một Object[] ở tầng ngoài:
method.invoke(null, new Object[] { names });
~~~

Cả hai cách đều khiến method đích nhận đúng một đối số kiểu `String[]`.

## 2. Hai tầng đối số trong Method.invoke()

Chữ ký chính thức:

~~~java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
~~~

- `obj`: đối tượng nhận lời gọi nếu method đích là instance method; với static method có thể dùng `null`.
- `args`: **mảng đối số của lời gọi phản chiếu**, mỗi phần tử tương ứng với một formal parameter của method đích.
- Kiểu trả về của `invoke` là `Object`. Kết quả nguyên thủy được boxing; method đích `void` trả về `null`.

Đừng đồng nhất hai ý nghĩa của mảng:

~~~text
                                  Method.invoke(target, Object... args)
                                               |
                                               v
                           Mảng Object[] ở tầng gọi reflection
                             [ argument0, argument1, ... ]
                                               |
                                               v
                               Method đích nhận từng tham số

Đích: count(String[] names)    -->  [ String[]{"An", "Bình"} ]
                                    ^ một phần tử, chính nó là mảng String[]

Sai: count(String[] names)     -->  [ "An", "Bình" ]
                                    ^ hai phần tử, sai số tham số
~~~

**Quy tắc:** Nếu method đích có `N` formal parameters, mảng đối số thực tế của `invoke` phải có đúng `N` phần tử và từng phần tử phải tương thích với formal parameter tương ứng. Một formal parameter là mảng vẫn chỉ tính là **một** phần tử.

## 3. Compiler đóng gói Object... ở call site như thế nào?

`Object... args` tương đương với `Object[] args` ở cấp khai báo phương thức. Khi gọi `invoke` bằng cú pháp Java, compiler có hai cách:

- **Fixed arity:** caller đã cung cấp trực tiếp một `Object[]` làm `args`. Các phần tử của nó là từng đối số reflection.
- **Variable arity:** caller cung cấp các giá trị riêng lẻ; compiler tạo một `Object[]` để chứa chúng.

Ví dụ:

~~~java
Object[] args = {"An", 23};
method.invoke(target, args);        // Fixed arity: 2 đối số reflection.
method.invoke(target, "An", 23);    // Variable arity: compiler tạo Object[]{"An", 23}.
method.invoke(target, (Object) args);
// Variable arity: compiler tạo Object[]{args}, chỉ có 1 đối số reflection.
~~~

Vì `String[]` là kiểu con của `Object[]`, lệnh dưới đây chọn dạng fixed arity và dùng **các phần tử chuỗi** làm danh sách đối số:

~~~java
String[] values = {"A", "B"};
method.invoke(target, values); // Tương tự truyền Object[] có 2 phần tử.
~~~

Compiler có thể báo warning về lời gọi varargs không rõ ý định, gợi ý cast thành `Object` để truyền một đối số hoặc `Object[]` để truyền mảng argument list. Đây là warning cần giải quyết đúng ngữ nghĩa, không nên chỉ tắt warning.

## 4. Khác nhau giữa (Object) và (Object[])

Giả sử:

~~~java
public static int count(String[] values) {
    return values.length;
}

Method m = Example.class.getMethod("count", String[].class);
String[] values = {"A", "B"};
~~~

| Cách gọi | `args` mà Method.invoke nhận | Kết quả |
| --- | --- | --- |
| `m.invoke(null, (Object) values)` | `new Object[]{values}` | Đúng: đích nhận một `String[]`. |
| `m.invoke(null, new Object[]{values})` | `new Object[]{values}` | Đúng: outer array là argument list, phần tử thứ nhất là `String[]`. |
| `m.invoke(null, values)` | `values` được dùng như argument list có 2 phần tử | Sai số đối số → `IllegalArgumentException`. |
| `m.invoke(null, (Object[]) values)` | `values` được dùng làm argument list có 2 phần tử | Sai số đối số → `IllegalArgumentException`. |
| `m.invoke(null, (Object) new Object[]{values})` | `new Object[]{new Object[]{values}}` | Sai kiểu: đích cần `String[]` nhưng nhận `Object[]`. |

**Diễn giải chính xác:** Ép kiểu `(Object)` **không sửa hoặc sao chép mảng**; nó đổi kiểu tĩnh của biểu thức để compiler chọn cách đóng gói một phần tử. Ép kiểu `(Object[])` nói với compiler rằng chính mảng này là **argument list** cho `invoke`. Nếu cần một array argument ở bên trong, hãy tạo outer array chứa nó.

Đối với method đích nhận `Object[]` thay cho `String[]`, lỗi tương tự vẫn xảy ra:

~~~java
public static int countObjects(Object[] values) {
    return values.length;
}

Object[] payload = {"A", "B"};
Method m = Example.class.getMethod("countObjects", Object[].class);

m.invoke(null, (Object) payload);       // Đúng: 1 tham số, chính là Object[].
m.invoke(null, new Object[]{payload}); // Đúng: outer Object[] có 1 phần tử.
m.invoke(null, payload);               // Sai: 2 tham số thay vì 1.
~~~

Nếu `payload.length == 1`, gọi sai bằng `m.invoke(null, payload)` có thể vẫn thất bại vì phần tử duy nhất không có kiểu `Object[]`; nếu phần tử đó lại là một `Object[]`, lời gọi có thể chạy nhưng truyền **sai tầng mảng**. Vì thế đừng dựa vào độ dài ngẫu nhiên của payload.

## 5. Method đích khai báo varargs vẫn có formal parameter kiểu mảng

Xét một method:

~~~java
public static String format(String prefix, String... parts) {
    return prefix + String.join("-", parts);
}
~~~

`String... parts` là cú pháp varargs tại **nơi gọi trực tiếp**. Ở cấp formal parameter, tham số cuối là `String[]`. Reflection nhìn thấy **hai** tham số:

~~~java
Method format = Example.class.getMethod(
        "format", String.class, String[].class);

System.out.println(format.isVarArgs());           // true
System.out.println(format.getParameterCount());   // 2
System.out.println(format.getParameterTypes()[1] == String[].class); // true
~~~

Gọi trực tiếp:

~~~java
format("v=", "A", "B"); // Compiler gộp các chuỗi vào một String[].
~~~

Gọi reflectively phải tự cung cấp mảng cuối:

~~~java
String[] parts = {"A", "B"};
Object answer = format.invoke(null, "v=", (Object) parts); // "v=A-B"

// Tương đương: Object[] ở tầng ngoài có hai phần tử.
answer = format.invoke(null, new Object[]{"v=", parts});
~~~

Lời gọi sau **không tương đương**:

~~~java
format.invoke(null, "v=", "A", "B");
// IllegalArgumentException: đích chỉ có 2 formal parameters, không phải 3.
~~~

`Method.isVarArgs() == true` chỉ cho biết khai báo của method đích dùng varargs. Nó **không** khiến `Method.invoke()` tự động gom các phần tử dư thành `String[]`. Cơ chế varargs của method đích và cơ chế varargs của chính `Method.invoke()` là **hai tầng độc lập**.

### Method đích varargs không có tham số đứng trước

~~~java
public static int size(String... items) {
    return items.length;
}

Method size = Example.class.getMethod("size", String[].class);
String[] items = {"A", "B"};

size.invoke(null, (Object) items); // Đúng: một String[] với 2 phần tử.
size.invoke(null, items);          // Sai: Method.invoke thấy 2 đối số.
size.invoke(null, "A", "B");       // Sai tương tự.
~~~

**Kể cả khi method đích được khai báo varargs, lookup vẫn dùng kiểu mảng:** `getMethod("size", String[].class)`, không phải `getMethod("size", String.class)`.

## 6. Object[] ở tầng ngoài: một cách đóng gói rõ ràng

Trong code quản lý reflection tổng quát, nên tạo argument list có cấu trúc tường minh:

~~~java
String[] names = {"An", "Bình"};
Object[] invokeArgs = { names }; // Một đối số: String[].
Object result = method.invoke(receiver, invokeArgs);
~~~

Nếu method đích có nhiều tham số:

~~~java
Object[] invokeArgs = {
    "Nhân viên: ",                 // Tham số 0: String
    new String[]{"An", "Bình"}     // Tham số 1: String[]
};

Object result = method.invoke(null, invokeArgs);
~~~

Không nên ép `invokeArgs` thành `Object` khi gọi `invoke`. Làm vậy sẽ đóng gói **cả argument list** vào thành một phần tử mới, khiến method đích nhận một `Object[]` thay vì hai tham số như mong đợi.

Có thể viết helper chuyên dụng cho method nhận đúng một tham số mảng:

~~~java
static Object invokeOneArray(
        Method method, Object receiver, Object array)
        throws ReflectiveOperationException {
    if (method.getParameterCount() != 1
            || !method.getParameterTypes()[0].isArray()) {
        throw new IllegalArgumentException(
                "Method đích phải nhận đúng một tham số mảng");
    }
    return method.invoke(receiver, new Object[]{array});
}
~~~

Helper này thể hiện rõ **một tham số đích** ngay cả khi `array` là `String[]`, `Object[]`, `int[]` hoặc `null`. Reflection vẫn kiểm tra khả năng gán kiểu của giá trị cho loại mảng mà method thực sự yêu cầu.

## 7. Trường hợp mảng nguyên thủy và mảng nhiều chiều

`int[]` là một `Object`, nhưng **không phải** `Object[]`. Vì vậy:

~~~java
public static int sum(int[] values) {
    return Arrays.stream(values).sum();
}

Method sum = Example.class.getMethod("sum", int[].class);
sum.invoke(null, (Object) new int[]{1, 2, 3}); // Đúng, trả Integer(6).
sum.invoke(null, new Object[]{new int[]{1, 2, 3}}); // Cũng đúng.
~~~

Với `int[]` đơn chiều, viết `sum.invoke(null, new int[]{1, 2, 3})` cũng được compiler đóng thành một đối số vì `int[]` không phải `Object[]`. Tuy vậy, dùng `(Object)` hoặc outer `new Object[]{...}` giúp ý định luôn rõ.

Đừng suy rộng quy tắc này sang mảng nhiều chiều:

~~~java
int[][] matrix = {{1, 2}, {3, 4}};
// int[][] là mảng của int[], nên bản thân nó cũng là Object[].
// Nếu đích nhận int[][], cần:
matrixMethod.invoke(null, (Object) matrix);
matrixMethod.invoke(null, new Object[]{matrix});
~~~

Tương tự, `String[][]` và mọi mảng nhiều chiều có thể tương thích với `Object[]` ở tầng ngoài. Khi một mảng là **dữ liệu cho đúng một formal parameter**, cách đóng gói tường minh vẫn an toàn nhất.

## 8. Null: không có đối số khác với một đối số có giá trị null

Các cách viết sau có ý nghĩa khác nhau:

| Lời gọi | Ý nghĩa đối với `Method.invoke` |
| --- | --- |
| `m.invoke(receiver)` | Không có đối số nào, `args` là mảng rỗng. |
| `m.invoke(receiver, new Object[0])` | Không có đối số nào. |
| `m.invoke(receiver, (Object[]) null)` | `args` ở tầng reflection là null; hợp lệ nếu method đích không có formal parameter. |
| `m.invoke(receiver, (Object) null)` | Có **một** đối số, giá trị của nó là null. |
| `m.invoke(receiver, new Object[]{null})` | Có **một** đối số, giá trị của nó là null. |

Ví dụ với đích nhận `String[]`:

~~~java
public static String inspect(String[] names) {
    return names == null ? "null-array" : "size=" + names.length;
}

Method m = Example.class.getMethod("inspect", String[].class);

m.invoke(null, (Object) null);         // Đúng: "null-array".
m.invoke(null, new Object[]{null});   // Đúng: "null-array".
m.invoke(null, (Object[]) null);      // Sai: 0 đối số -> IllegalArgumentException.
m.invoke(null, new Object[0]);        // Sai: 0 đối số -> IllegalArgumentException.
~~~

Trong lời gọi `m.invoke(receiver, null)` không ép kiểu, compiler có thể cảnh báo về cách hiểu varargs. Hãy viết `(Object) null` khi muốn **một đối số null**, hoặc `(Object[]) null` khi muốn **danh sách đối số null**. Cách viết tường minh loại bỏ sự nhập nhằng.

Với method không tham số, `m.invoke(receiver)` và `m.invoke(receiver, (Object[]) null)` đều hợp lệ. Với method có một tham số kiểu mảng, chỉ cách truyền **một phần tử null** mới đúng số đối số.

## 9. Ví dụ Java hoàn chỉnh để tự kiểm chứng

Lưu đoạn sau thành `ReflectiveArrayArguments.java`. Ví dụ chỉ dùng API có trên Java 18 và chạy được trên JDK hiện đại:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;

public class ReflectiveArrayArguments {
    public static int countStrings(String[] values) {
        return values == null ? -1 : values.length;
    }

    public static int countObjects(Object[] values) {
        return values == null ? -1 : values.length;
    }

    public static int countInts(int[] values) {
        return values.length;
    }

    public static String join(String prefix, String... values) {
        return prefix + Arrays.toString(values);
    }

    public static String ping() {
        return "pong";
    }

    public static void failInside() {
        throw new IllegalStateException("Lỗi từ method đích");
    }

    @FunctionalInterface
    interface CheckedCall {
        void run() throws Exception;
    }

    static void expectIllegalArgument(String label, CheckedCall call)
            throws Exception {
        try {
            call.run();
            throw new AssertionError("Đáng lẽ phải có lỗi: " + label);
        } catch (IllegalArgumentException expected) {
            System.out.println(label + ": IllegalArgumentException");
        }
    }

    public static void main(String[] args) throws Exception {
        Method strings = ReflectiveArrayArguments.class.getMethod(
                "countStrings", String[].class);
        Method objects = ReflectiveArrayArguments.class.getMethod(
                "countObjects", Object[].class);
        Method ints = ReflectiveArrayArguments.class.getMethod(
                "countInts", int[].class);
        Method join = ReflectiveArrayArguments.class.getMethod(
                "join", String.class, String[].class);
        Method ping = ReflectiveArrayArguments.class.getMethod("ping");
        Method fail = ReflectiveArrayArguments.class.getMethod("failInside");

        String[] names = {"An", "Bình"};
        Object[] values = {"A", "B"};

        System.out.println("strings parameterCount = "
                + strings.getParameterCount());             // 1
        System.out.println("strings isVarArgs = "
                + strings.isVarArgs());                     // false
        System.out.println("join parameterCount = "
                + join.getParameterCount());                // 2
        System.out.println("join isVarArgs = "
                + join.isVarArgs());                        // true
        System.out.println("join last is String[] = "
                + (join.getParameterTypes()[1] == String[].class)); // true

        System.out.println("String[] as one = "
                + strings.invoke(null, (Object) names));       // 2
        System.out.println("String[] outer args = "
                + strings.invoke(null, new Object[]{names})); // 2
        System.out.println("Object[] as one = "
                + objects.invoke(null, (Object) values));      // 2
        System.out.println("int[] as one = "
                + ints.invoke(null, (Object) new int[]{3, 5})); // 2
        System.out.println("varargs target = "
                + join.invoke(null, "prefix=", (Object) names));
        System.out.println("varargs outer args = "
                + join.invoke(null, new Object[]{"prefix=", names}));
        System.out.println("single null array = "
                + strings.invoke(null, new Object[]{null}));   // -1
        System.out.println("no-arg null vector = "
                + ping.invoke(null, (Object[]) null));          // pong

        expectIllegalArgument("spreading String[]",
                () -> strings.invoke(null, (Object[]) names));
        expectIllegalArgument("spreading Object[]",
                () -> objects.invoke(null, values));
        expectIllegalArgument("extra varargs target values",
                () -> join.invoke(null, "prefix=", "A", "B"));
        expectIllegalArgument("null args vector for 1 parameter",
                () -> strings.invoke(null, (Object[]) null));

        try {
            fail.invoke(null);
            throw new AssertionError("Expected InvocationTargetException");
        } catch (InvocationTargetException e) {
            System.out.println("target failure = "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReflectiveArrayArguments.java
java ReflectiveArrayArguments
~~~

Kết quả dự kiến:

~~~text
strings parameterCount = 1
strings isVarArgs = false
join parameterCount = 2
join isVarArgs = true
join last is String[] = true
String[] as one = 2
String[] outer args = 2
Object[] as one = 2
int[] as one = 2
varargs target = prefix=[An, Bình]
varargs outer args = prefix=[An, Bình]
single null array = -1
no-arg null vector = pong
spreading String[]: IllegalArgumentException
spreading Object[]: IllegalArgumentException
extra varargs target values: IllegalArgumentException
null args vector for 1 parameter: IllegalArgumentException
target failure = IllegalStateException
~~~

Đây là chương trình tự kiểm tra: nếu một ca lẽ ra lỗi nhưng không ném `IllegalArgumentException`, helper sẽ ném `AssertionError`. Ví dụ dùng method `public static` để tập trung vào cách đóng gói đối số, không cần xử lý quyền truy cập thành viên riêng tư.

## 10. Vì sao xuất hiện IllegalArgumentException?

Theo hợp đồng `Method.invoke`, `IllegalArgumentException` có thể xảy ra khi:

- Số **đối số thực tế** khác số formal parameters của method đích.
- Giá trị đối số không chuyển đổi được sang kiểu formal parameter tương ứng.
- Với instance method, `obj` không phải instance của lớp/interface khai báo method.
- Với kiểu nguyên thủy, chuyển đổi unboxing/widening không hợp lệ.

Trong bài này, hai tình huống thường gặp nhất là:

~~~java
// Đích có 1 tham số String[] nhưng reflection nhận 2 đối số String.
m.invoke(null, (Object[]) new String[]{"A", "B"});

// Đích có 1 tham số String[] nhưng reflection nhận 1 String.
m.invoke(null, (Object[]) new String[]{"A"});
~~~

Ca đầu sai **số lượng**; ca sau đúng số lượng nhưng sai **kiểu của phần tử**. Cả hai đều có thể ném `IllegalArgumentException`.

Phân biệt với các exception khác:

| Exception | Nguồn gốc tiêu biểu | Cách chẩn đoán |
| --- | --- | --- |
| `IllegalArgumentException` | Sai số lượng/kiểu đối số, hoặc receiver không phù hợp | Kiểm tra outer `Object[]`, `getParameterCount()` và `getParameterTypes()`. |
| `InvocationTargetException` | Code **bên trong method đích** ném exception | Đọc `getCause()` để lấy exception gốc. |
| `IllegalAccessException` | Reflection không được phép truy cập method đích | Xem visibility và quy tắc truy cập module; không mặc định mở quyền tùy ý. |
| `NullPointerException` | Gọi instance method với `obj == null` | Cung cấp receiver hợp lệ; `null` chỉ phù hợp với static method. |

Đừng gộp tất cả vào một `catch (Exception)` rồi kết luận lỗi là do varargs. Một lỗi trong method đích sẽ được bọc bằng `InvocationTargetException` và cần được xem xét riêng.

## 11. Quy trình debug một lời gọi Method.invoke

Khi gặp lỗi `wrong number of arguments` hoặc `argument type mismatch`, làm theo thứ tự:

1. **Đọc chữ ký method đích:** xác định số formal parameters, nhớ `T...` tương ứng với một `T[]`.
2. **Kiểm tra metadata reflection:** in `getParameterCount()`, `Arrays.toString(getParameterTypes())` và `isVarArgs()`.
3. **Tạo outer argument list:** chuẩn bị `Object[] invokeArgs` mà độ dài đúng số formal parameters.
4. **Xem từng phần tử:** nếu formal parameter là `String[]` thì phần tử tương ứng phải là `String[]` hoặc `null`, không phải một `String` lẻ.
5. **Không nhầm varargs ở tầng invoke:** `m.invoke(target, array)` với `array` tĩnh là `Object[]` có thể bị hiểu thành toàn bộ argument list.
6. **Kiểm tra receiver:** static method cho phép `target == null`; instance method cần đối tượng hợp lệ.
7. **Phân loại exception:** `IllegalArgumentException` trước khi method đích chạy; `InvocationTargetException` cho exception do method đích ném.

Ví dụ in metadata và argument list để xác minh trước khi gọi:

~~~java
System.out.println(Arrays.toString(method.getParameterTypes()));
System.out.println("Parameter count = " + method.getParameterCount());
System.out.println("Declared varargs = " + method.isVarArgs());

Object[] invokeArgs = { new String[]{"A", "B"} };
System.out.println("Invoke args count = " + invokeArgs.length); // 1
System.out.println("Argument type = "
        + invokeArgs[0].getClass().getTypeName()); // java.lang.String[]

Object result = method.invoke(null, invokeArgs);
~~~

Chú ý: `Arrays.toString(invokeArgs)` khi chứa mảng lồng nhau không hiển thị nội dung sâu theo cách dễ đọc. Nếu cần xem cấu trúc mảng, dùng `Arrays.deepToString(invokeArgs)` cho debug; **đừng** dùng output debug để suy ra kiểu thực tế mà bỏ qua `getClass()`/`getParameterTypes()`.

## 12. Phân biệt reflection varargs với MethodHandle

Trong Java 18, JEP 416 thay đổi cách Core Reflection được triển khai bên dưới bằng Method Handle. Đây là thay đổi ở implementation; nó **không thay đổi** ý nghĩa `Method.invoke(Object, Object...)`, số formal parameters của method đích hoặc nhu cầu đóng gói đối số thành `Object[]`.

`MethodHandle.invoke`, `invokeExact` và `invokeWithArguments` có hợp đồng riêng liên quan đến kiểu ở call site và việc chuyển đổi/spread/collect đối số. Không suy diễn quy tắc của `MethodHandle.invokeWithArguments` để giải thích `Method.invoke`. Trong bài này, mọi ví dụ đều dùng **`java.lang.reflect.Method`**.

## 13. Những sai lầm cần tránh

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Nghĩ method đích `String...` có thể nhận bao nhiêu đối số reflect cũng được | `IllegalArgumentException` do sai số đối số | Đóng gói các phần tử thành `String[]` ở formal parameter cuối. |
| Truyền trực tiếp `String[]` vào `invoke` | Dễ bị compiler xem là `Object[]` argument list | Ép `(Object)` hoặc dùng `new Object[]{stringArray}`. |
| Truyền trực tiếp `Object[]` là payload | Các phần tử payload bị trải thành từng đối số | Bọc payload bằng outer `Object[]` hoặc ép `(Object)`. |
| Ép cả outer argument list thành `Object` | Biến nhiều tham số thành một tham số `Object[]` | Truyền outer `Object[]` trực tiếp. |
| Dùng `getMethod("f", String.class)` cho `f(String...)` | Không tìm thấy method | Lookup bằng `String[].class`. |
| Nghĩ `null` luôn là một đối số null | Có thể bị hiểu thành `args == null`, tương đương 0 đối số | Dùng `(Object)null` hoặc `new Object[]{null}`. |
| Nhầm `int[]` với `Object[]` | Dự đoán sai quá trình đóng gói | Nhớ `int[]` không phải `Object[]`; mảng nhiều chiều lại có thể là `Object[]`. |
| Coi `InvocationTargetException` là lỗi đóng gói mảng | Chẩn đoán nhầm lỗi bên trong method | Đọc `getCause()` và kiểm tra method đích. |

## 14. Câu hỏi tự kiểm tra và bài thực hành

1. Tham số `Object... args` của `Method.invoke` đại diện cho điều gì?
2. Vì sao `String[]` có thể bị xem là argument list khi truyền trực tiếp vào `invoke`?
3. `(Object) array` khác `(Object[]) array` như thế nào tại call site?
4. Nếu method đích khai báo `f(String...)`, `getParameterCount()` trả về bao nhiêu khi method chỉ có tham số đó?
5. Vì sao `f.invoke(null, "A", "B")` không tự đóng gói thành `String[]`?
6. Cách an toàn để truyền một `Object[]` vào method đích nhận `Object[]` là gì?
7. Vì sao `int[]` và `int[][]` có hành vi khác nhau liên quan đến `Object[]`?
8. `m.invoke(null, (Object)null)` khác `m.invoke(null, (Object[])null)` thế nào?
9. Hai nguyên nhân khác nhau nào có thể làm `Method.invoke` ném `IllegalArgumentException`?
10. Lỗi được bọc trong `InvocationTargetException` đến từ đâu?
11. Khi debug, dùng các API nào để xác định số lượng và loại formal parameters của method?
12. JEP 416 thay đổi hợp đồng gọi phản chiếu hay chỉ thay đổi implementation?

**Bài thực hành:** chạy `ReflectiveArrayArguments`, sau đó thử sửa `(Object) names` thành `(Object[]) names` và quan sát `IllegalArgumentException`. Đổi mảng `names` thành một phần tử để phân biệt lỗi sai số lượng với lỗi sai kiểu. Tạo method đích `report(String title, int... ids)`, tìm bằng `getMethod("report", String.class, int[].class)` và gọi với `new Object[]{"IDs: ", new int[]{1, 2, 3}}`. Cuối cùng kiểm thử các trường hợp mảng rỗng và `null` bằng một `Object[]` outer có đúng số phần tử.

## Tài liệu tham khảo chính thức

- [Oracle JDK 18 — `Method.invoke`](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/reflect/Method.html): chữ ký `invoke(Object, Object...)`, lỗi số lượng/kiểu đối số và cách xử lý method tĩnh.
- [Oracle JDK 26 — `Method.invoke`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Method.html): xác nhận hợp đồng reflection vẫn được hỗ trợ trên JDK hiện đại.
- [Oracle — Reflection Troubleshooting: `Method.invoke()`](https://docs.oracle.com/javase/tutorial/reflect/member/methodTrouble.html): ví dụ của Oracle về varargs, `null`, ép kiểu `Object` và `Object[]`.
- [Java Language Specification — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12): quy tắc compiler chọn fixed arity/variable arity khi gọi `invoke` bằng mã Java.
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): thay đổi triển khai reflection trong JDK 18.
