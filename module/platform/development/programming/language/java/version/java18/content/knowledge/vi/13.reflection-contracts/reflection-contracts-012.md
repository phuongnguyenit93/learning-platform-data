# Kết quả primitive được boxing và kết quả null của method trả void

## 1. Một lời gọi reflection có thể trả về gì?

Khi gọi trực tiếp một method Java, compiler biết kiểu trả về ngay tại vị trí gọi: `int`, `boolean`, `String` hoặc `void`. Khi gọi qua Core Reflection, chữ ký của `java.lang.reflect.Method.invoke` lại là:

```java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
```

Vì kiểu kết quả ở phía người gọi luôn là `Object`, Reflection cần quy tắc chuyển kết quả của method đích về một giá trị mà `Object` có thể biểu diễn.

Hợp đồng của `Method.invoke` được đặc tả rõ trong JDK hiện đại:

- Nếu method đích **trả primitive**, giá trị được đóng gói thành wrapper tương ứng trước khi trả cho người gọi.
- Nếu method đích **trả `void`** và hoàn thành bình thường, `invoke` trả `null`; các tác dụng phụ của method vẫn diễn ra.
- Nếu method đích **trả kiểu tham chiếu**, `invoke` trả tham chiếu ấy, bao gồm `null` khi chính method đích trả `null`.
- Nếu method đích trả **mảng primitive** như `int[]`, `invoke` giữ nguyên mảng; các phần tử không bị biến thành `Integer`.
- Nếu method đích **ném exception**, `invoke` không trả một giá trị kết quả thông thường; exception của method đích được bọc trong `InvocationTargetException`.

Các quy tắc này có từ trước Java 18 và vẫn hữu ích khi học kiểm chứng hợp đồng API trên JDK hiện đại. Đây là chủ đề thuộc chương **Hợp đồng reflection** của mô-đun **JAVA_VERSION_JAVA18**; nội dung chỉ tập trung vào hành vi vẫn còn áp dụng, không dựa vào cơ chế legacy.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định wrapper tương ứng với tám kiểu primitive khi nhận kết quả từ `Method.invoke`.
2. Giải thích tại sao method `void` trả `null` qua Reflection dù method đã chạy.
3. Phân biệt `void` với method tham chiếu trả `null` dựa trên `getReturnType()`.
4. Phân biệt kết quả `int[]` với `Integer[]` và phân biệt `void.class` với `Void.class`.
5. Viết kiểm thử xác nhận kiểu khai báo, kiểu thực tế, giá trị và tác dụng phụ.
6. Nhận biết exception do lời gọi Reflection và exception phát sinh từ method đích.
7. So sánh `Method.invoke` với `MethodHandle.invokeWithArguments` và `invokeExact` ở mức cần thiết.

## 2. Bảng quy tắc trả về của `Method.invoke`

| Kiểu khai báo của method | Kiểu giá trị nhận qua `invoke` | Có thể là `null` khi hoàn thành bình thường? |
| --- | --- | --- |
| `boolean` | `Boolean` | Không |
| `byte` | `Byte` | Không |
| `short` | `Short` | Không |
| `char` | `Character` | Không |
| `int` | `Integer` | Không |
| `long` | `Long` | Không |
| `float` | `Float` | Không |
| `double` | `Double` | Không |
| `void` | `null` | Luôn trả `null` |
| `String` hoặc một kiểu tham chiếu khác | Tham chiếu gốc | Có, nếu method đích trả `null` |
| `Integer`, `Boolean` và các wrapper khai báo trực tiếp | Tham chiếu wrapper gốc | Có, nếu method đích trả `null` |
| `int[]`, `double[]`... | Mảng primitive gốc | Có, nếu method đích trả `null` |

Chữ **boxing** ở đây nói về việc chuyển *giá trị trả về primitive* sang một đối tượng wrapper. Đừng nhầm nó với việc caller truyền `Integer` vào một tham số `int`: đó là hướng chuyển đổi tham số, được áp dụng trước khi method đích bắt đầu chạy.

Ví dụ:

```java
public static int twice(int value) {
    return value * 2;
}
```

Khi gọi `twice` qua `Method.invoke`, đối số `21` được đưa tới tham số `int` bằng cơ chế chuyển đổi thích hợp; kết quả `42` có kiểu `int` bên trong method nhưng xuất hiện dưới dạng một đối tượng `Integer` tại nơi nhận `Object`.

Ngược lại, với:

```java
public static void touch() {
    System.out.println("Đã chạm");
}
```

Lời gọi `invoke` vẫn in văn bản nhưng giá trị được gán cho `Object` sẽ là `null`. `null` không phải dấu hiệu rằng method không chạy.

## 3. Ví dụ hoàn chỉnh: so sánh primitive, void, reference và mảng

Tạo file `ReflectionReturnDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;

public final class ReflectionReturnDemo {
    private ReflectionReturnDemo() {
    }

    public static final class Sample {
        private static int touches;

        public static int twice(int input) {
            return input * 2;
        }

        public static void touch() {
            touches++;
        }

        public static String nullableText() {
            return null;
        }

        public static Integer nullableWrapper() {
            return null;
        }

        public static int[] numbers() {
            return new int[] {2, 4, 6};
        }

        public int instanceNumber() {
            return 7;
        }

        public static int fail() {
            throw new IllegalStateException("Ví dụ lỗi từ method đích");
        }
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method twice = Sample.class.getMethod("twice", int.class);
        Object primitiveResult = twice.invoke(null, 21);
        check(primitiveResult instanceof Integer, "int phải thành Integer");
        check(((Integer) primitiveResult) == 42, "Sai kết quả int");
        check(twice.getReturnType() == int.class, "Sai kiểu khai báo");
        System.out.println("int -> " + primitiveResult.getClass().getSimpleName()
                + ": " + primitiveResult);

        Method touch = Sample.class.getMethod("touch");
        int before = Sample.touches;
        Object voidResult = touch.invoke(null);
        check(touch.getReturnType() == void.class, "Sai kiểu void");
        check(voidResult == null, "void phải trả null");
        check(Sample.touches == before + 1, "Method void chưa chạy");
        System.out.println("void -> null, touches=" + Sample.touches);

        Method nullableText = Sample.class.getMethod("nullableText");
        Object textResult = nullableText.invoke(null);
        check(textResult == null, "Reference phải trả null");
        check(nullableText.getReturnType() == String.class, "Không phải void");
        System.out.println("String -> null");

        Method nullableWrapper = Sample.class.getMethod("nullableWrapper");
        Object wrapperResult = nullableWrapper.invoke(null);
        check(wrapperResult == null, "Wrapper có thể trả null");
        check(nullableWrapper.getReturnType() == Integer.class, "Không phải int");
        System.out.println("Integer -> null");

        Method numbers = Sample.class.getMethod("numbers");
        Object arrayResult = numbers.invoke(null);
        check(arrayResult instanceof int[], "Mảng primitive phải giữ nguyên");
        check(arrayResult.getClass() == int[].class, "Không phải Integer[]");
        System.out.println("int[] -> " + Arrays.toString((int[]) arrayResult));

        Method instance = Sample.class.getMethod("instanceNumber");
        Object instanceResult = instance.invoke(new Sample());
        check(instanceResult instanceof Integer, "Instance int phải được boxing");
        System.out.println("instance int -> " + instanceResult);

        try {
            Sample.class.getMethod("fail").invoke(null);
            throw new AssertionError("Đáng lẽ phải có exception");
        } catch (InvocationTargetException ex) {
            check(ex.getCause() instanceof IllegalStateException,
                    "Sai nguyên nhân lỗi");
            System.out.println("exception -> "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK đang được sử dụng:

```bash
javac -encoding UTF-8 ReflectionReturnDemo.java
java ReflectionReturnDemo
```

Kết quả kỳ vọng:

```text
int -> Integer: 42
void -> null, touches=1
String -> null
Integer -> null
int[] -> [2, 4, 6]
instance int -> 7
exception -> IllegalStateException
```

**Điểm quan sát quan trọng:** Cả `voidResult`, `textResult` và `wrapperResult` đều là `null`. Chỉ nhìn vào giá trị `Object` không đủ để biết chúng đến từ kiểu trả về nào. Ngược lại, `primitiveResult` đến từ `int` nên luôn có một `Integer` nếu method hoàn thành bình thường.

Trong ví dụ, các method đều `public` để có thể tra cứu bằng `getMethod` mà không cần can thiệp vào quyền truy cập. Trong hệ thống module hiện đại, việc cố truy cập method không public có thể còn chịu ràng buộc đóng gói của module; quy tắc boxing và `void` không thay thế quy tắc quyền truy cập ấy.

## 4. Kiểm tra cả tám kiểu primitive

Kiểu khai báo của method và lớp của đối tượng nhận được là hai thông tin khác nhau:

```java
Method m = Sample.class.getMethod("twice", int.class);

Class<?> declared = m.getReturnType();    // int.class
Object result = m.invoke(null, 21);      // Integer chứa 42
Class<?> actual = result.getClass();      // Integer.class
```

Hãy phân biệt:

- `m.getReturnType()`: kiểu **khai báo** trong chữ ký method, chẳng hạn `int.class`.
- `result.getClass()`: kiểu runtime của **đối tượng nhận được**, chẳng hạn `Integer.class`.

Để kiểm tra toàn bộ tám loại, dùng lớp ví dụ sau:

```java
import java.lang.reflect.Method;

public final class PrimitiveResults {
    public static boolean flag() { return true; }
    public static byte smallByte() { return 1; }
    public static short smallShort() { return 2; }
    public static char letter() { return 'A'; }
    public static int integer() { return 3; }
    public static long large() { return 4L; }
    public static float fractional() { return 5.0f; }
    public static double decimal() { return 6.0d; }

    public static void main(String[] args) throws ReflectiveOperationException {
        Object[][] cases = {
                {"flag", boolean.class, Boolean.class},
                {"smallByte", byte.class, Byte.class},
                {"smallShort", short.class, Short.class},
                {"letter", char.class, Character.class},
                {"integer", int.class, Integer.class},
                {"large", long.class, Long.class},
                {"fractional", float.class, Float.class},
                {"decimal", double.class, Double.class}
        };

        for (Object[] testCase : cases) {
            String name = (String) testCase[0];
            Class<?> primitiveType = (Class<?>) testCase[1];
            Class<?> wrapperType = (Class<?>) testCase[2];

            Method method = PrimitiveResults.class.getMethod(name);
            Object value = method.invoke(null);

            if (method.getReturnType() != primitiveType
                    || value == null
                    || value.getClass() != wrapperType) {
                throw new AssertionError("Sai hợp đồng: " + name);
            }
            System.out.println(name + " -> " + wrapperType.getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PrimitiveResults.java
java PrimitiveResults
```

Nếu tất cả kiểm tra qua, chương trình in tên method cùng kiểu wrapper tương ứng. Mã dùng phép so sánh `==` trên các đối tượng `Class<?>` vì mỗi kiểu runtime có đối tượng `Class` đại diện tương ứng.

Lưu ý rằng **boxing không biến `int[]` thành `Integer[]`**. `int[]` vốn đã là kiểu tham chiếu (một đối tượng mảng), nên `invoke` chỉ trả tham chiếu mảng; không boxing từng phần tử. Nếu API thực sự cần `Integer[]`, phải chuyển đổi mảng một cách tường minh.

## 5. Vì sao `void` trả `null`, nhưng `null` không chứng minh là `void`?

`Method.invoke` có kiểu trả về `Object`. Method `void` không tạo giá trị Java có thể gán cho biến, nên API Reflection dùng `null` để biểu diễn *không có giá trị kết quả*. Đây là hợp đồng đầu ra của `Method.invoke` khi method đích hoàn thành bình thường.

Không nên suy luận ngược:

```java
Object result = method.invoke(receiver, args);
if (result == null) {
    // Chưa thể kết luận method trả void!
}
```

Một method khai báo `String`, `Integer`, `Void` hoặc một kiểu tham chiếu khác cũng có thể hợp lệ trả `null`. Thậm chí method trả `int[]` cũng có thể trả `null` vì bản thân mảng là kiểu tham chiếu.

**Cách phân biệt đúng** là kiểm tra chữ ký của method:

```java
Class<?> returnType = method.getReturnType();

if (returnType == void.class) {
    // Method có chữ ký trả void.
} else if (returnType.isPrimitive()) {
    // Một trong tám primitive; kết quả thành wrapper nếu hoàn thành.
} else {
    // Kiểu tham chiếu hoặc mảng; kết quả có thể là null.
}
```

Thứ tự ở trên quan trọng: `void.class.isPrimitive()` cũng trả `true` theo hợp đồng của `Class.isPrimitive()`. Nếu nhánh `isPrimitive()` chạy trước mà không loại trừ `void.class`, chương trình phân loại sai `void` như một primitive có wrapper.

### 5.1. `void.class` khác `Void.class`

Hai biểu thức sau không tương đương:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `void.class` | Đối tượng `Class` đại diện pseudo-type `void`; tương đương `Void.TYPE`. |
| `Void.class` | Đối tượng `Class` của lớp tham chiếu `java.lang.Void`. |
| `method.getReturnType() == void.class` | Method khai báo keyword `void`. |
| `method.getReturnType() == Void.class` | Method khai báo trả tham chiếu `java.lang.Void`. |

`java.lang.Void` là lớp không thể tạo instance thông thường; một method khai báo trả `Void` thường trả `null`. Nhưng loại method này vẫn khác method khai báo `void`. Sự khác biệt nằm trong chữ ký, dù kết quả `invoke` đều có thể là `null`.

```java
public static void noValue() { }
public static Void nullableVoidReference() { return null; }
```

Hai method này có kiểu trả về khác nhau:

```java
Method a = Example.class.getMethod("noValue");
Method b = Example.class.getMethod("nullableVoidReference");

boolean firstIsVoid = a.getReturnType() == void.class;   // true
boolean secondIsVoid = b.getReturnType() == void.class;  // false
```

Đoạn trên minh họa logic nếu đặt hai method trong lớp `Example`; tên lớp và cách tra cứu cần đổi nếu bạn đưa method vào lớp khác.

### 5.2. Quy tắc nhận diện kết quả trong công cụ gọi động

Với framework gọi method động, có thể giữ thêm thông tin chữ ký thay vì chỉ lưu `Object`:

```java
record CallOutcome(boolean returnedVoid, Object value) {
}

static CallOutcome call(Method method, Object receiver, Object... args)
        throws ReflectiveOperationException {
    Object value = method.invoke(receiver, args);
    return new CallOutcome(method.getReturnType() == void.class, value);
}
```

Nếu `returnedVoid == true`, `value` luôn bằng `null` khi lời gọi thành công. Nếu `returnedVoid == false` và `value == null`, method đã trả một tham chiếu `null`. Nếu method ném exception, hàm `call` không tạo `CallOutcome` bình thường.

Đây là cách thiết kế an toàn hơn cho RPC adapter, hệ thống plugin hoặc bộ gọi hàm theo metadata vì nó không trộn lẫn “không có giá trị trả về” với “giá trị trả về là null”.

## 6. Boxing, unboxing và ép kiểu an toàn

Khi biết method khai báo `int`, bạn có thể nhận kết quả theo hai bước:

```java
Method method = Sample.class.getMethod("twice", int.class);
Object raw = method.invoke(null, 21);

Integer boxed = (Integer) raw;
int value = boxed.intValue();  // 42
```

Hoặc dùng auto-unboxing:

```java
int value = (Integer) method.invoke(null, 21);
```

Nếu method khai báo `long`, wrapper là `Long`. Ép một kết quả `Integer` sang `Long` trực tiếp sẽ gây `ClassCastException`:

```java
// Sai nếu method đích trả int:
Long wrong = (Long) method.invoke(null, 21);

// Đúng khi method đích trả int:
Integer correct = (Integer) method.invoke(null, 21);
```

Để xử lý nhiều loại số với mục tiêu chuyển thành `long`, có thể dùng `Number` rồi gọi `longValue()` sau khi đã kiểm tra hợp đồng và khả năng chuyển đổi:

```java
Object raw = method.invoke(null, 21);
if (!(raw instanceof Number number)) {
    throw new IllegalStateException("Kết quả không phải kiểu số");
}
long asLong = number.longValue();
```

Cách này có thể làm mất độ chính xác hoặc thay đổi giá trị khi chuyển `float`/`double` hoặc số lớn sang `long`. Vì thế, không thay thế việc kiểm tra kiểu cụ thể và quy tắc chuyển đổi mà API yêu cầu.

### 6.1. Không gọi `getClass()` trên một kết quả `null`

```java
Object result = method.invoke(receiver);
System.out.println(result.getClass()); // NPE nếu void hoặc reference null
```

Với một công cụ quan sát động, nên ghi kiểu từ metadata trước, rồi ghi kiểu runtime khi có giá trị:

```java
Class<?> declaredType = method.getReturnType();
Object result = method.invoke(receiver);
String actualType = result == null
        ? "<null>"
        : result.getClass().getTypeName();

System.out.println("declared=" + declaredType.getTypeName());
System.out.println("actual=" + actualType);
```

Ký hiệu `<null>` trong log chỉ là văn bản hiển thị; nó không phải tên kiểu Java. Khi method trả `void`, cách ghi nhận quan trọng là `declared=void` cùng `actual=<null>`.

## 7. Những lỗi Reflection không được hiểu là “trả null”

Chỉ có lời gọi **hoàn thành bình thường** mới có kết quả theo bảng ở phần 2. Nếu lời gọi thất bại, không có giá trị trả về thông thường:

| Tình huống | Hành vi |
| --- | --- |
| Method đích ném `IllegalStateException` | `Method.invoke` ném `InvocationTargetException`, nguyên nhân nằm ở `getCause()`. |
| Gọi instance method với receiver `null` | `NullPointerException` phát sinh ở thao tác Reflection. |
| Truyền sai số lượng tham số | `IllegalArgumentException`; method đích chưa được gọi. |
| Truyền `null` cho tham số primitive `int` | `IllegalArgumentException` do không thể unbox `null` thành `int`. |
| Không có quyền truy cập method | Có thể phát sinh `IllegalAccessException` hoặc lỗi truy cập theo quy tắc module. |
| Method đích trả `void` và chạy xong | `invoke` trả `null`; đây là thành công, không phải exception. |

Để lấy lỗi từ method đích:

```java
try {
    Object result = method.invoke(receiver, args);
    // Chỉ xử lý result sau khi lệnh invoke đã hoàn thành.
} catch (InvocationTargetException ex) {
    Throwable targetFailure = ex.getCause();
    System.err.println("Method đích lỗi: " + targetFailure);
}
```

`getCause()` giúp phân biệt lỗi nghiệp vụ của method đích với lỗi gọi Reflection, chẳng hạn receiver không phù hợp hoặc tham số không thể chuyển đổi. Không nên catch mọi exception rồi trả `null` vì cách đó che giấu sự khác nhau giữa thất bại và kết quả `void` hợp lệ.

### 7.1. Static method và instance method

Với static method, tham số receiver đầu tiên của `Method.invoke` bị bỏ qua; có thể truyền `null`. Với instance method, phải truyền đối tượng hợp lệ:

```java
Method staticMethod = Sample.class.getMethod("twice", int.class);
Object a = staticMethod.invoke(null, 3); // Integer chứa 6

Method instanceMethod = Sample.class.getMethod("instanceNumber");
Object b = instanceMethod.invoke(new Sample()); // Integer chứa 7
```

Ở đây tên `Sample` là lớp lồng trong ví dụ đầy đủ ở phần 3. Đừng truyền `null` cho instance method rồi coi `NullPointerException` là “kết quả null”.

## 8. Kiểm chứng với JUnit

Nếu ứng dụng hoặc thư viện dựa vào Reflection, hãy test cả **kiểu khai báo** và **giá trị nhận về**. Ví dụ sau dùng JUnit Jupiter và lớp `ReflectionReturnDemo.Sample` từ phần 3:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ReflectionReturnDemoTest {
    @Test
    void primitiveReturnIsBoxed() throws ReflectiveOperationException {
        Method method = ReflectionReturnDemo.Sample.class
                .getMethod("twice", int.class);
        Object value = method.invoke(null, 5);

        assertSame(int.class, method.getReturnType());
        assertInstanceOf(Integer.class, value);
        assertEquals(10, ((Integer) value).intValue());
    }

    @Test
    void voidReturnIsNullEvenWhenMethodRuns()
            throws ReflectiveOperationException {
        Method method = ReflectionReturnDemo.Sample.class
                .getMethod("touch");

        Object value = method.invoke(null);

        assertSame(void.class, method.getReturnType());
        assertNull(value);
    }

    @Test
    void referenceNullIsNotVoid() throws ReflectiveOperationException {
        Method method = ReflectionReturnDemo.Sample.class
                .getMethod("nullableText");

        Object value = method.invoke(null);

        assertSame(String.class, method.getReturnType());
        assertNull(value);
    }

    @Test
    void primitiveArrayIsNotConvertedToWrapperArray()
            throws ReflectiveOperationException {
        Method method = ReflectionReturnDemo.Sample.class
                .getMethod("numbers");

        Object value = method.invoke(null);

        assertSame(int[].class, method.getReturnType());
        assertInstanceOf(int[].class, value);
        assertArrayEquals(new int[] {2, 4, 6}, (int[]) value);
    }

    @Test
    void targetExceptionIsNotAResult() throws ReflectiveOperationException {
        Method method = ReflectionReturnDemo.Sample.class
                .getMethod("fail");

        InvocationTargetException ex = assertThrows(
                InvocationTargetException.class,
                () -> method.invoke(null)
        );
        assertInstanceOf(IllegalStateException.class, ex.getCause());
    }
}
```

Để kiểm tra tác dụng phụ của `touch` trong test, nên bổ sung một getter hoặc dependency được inject mà test kiểm soát và xác nhận bộ đếm tăng sau lời gọi. Bản test trên xác nhận hình thức `void → null`; chương trình độc lập ở phần 3 còn kiểm tra cả tác dụng phụ.

Một test mạnh phải có cả assertion về kiểu, về giá trị, và về đường đi ngoại lệ. Chỉ `assertNull(method.invoke(...))` không đủ xác nhận method khai báo `void`.

## 9. Liên hệ với MethodHandle trên JDK hiện đại

Core Reflection `Method.invoke` luôn có kiểu trả về Java được khai báo là `Object`. MethodHandle có thêm cách gọi mang kiểu mạnh hơn:

- `MethodHandle.invokeWithArguments(...)` trả `Object`; primitive được boxing và `void` được quy về `null` theo đặc tả của phương thức này.
- `MethodHandle.invokeExact(...)` là lời gọi *signature-polymorphic*: kiểu tham số và kiểu trả về tại call site phải khớp chính xác với `MethodType` của handle. Kết quả primitive không bắt buộc phải đi qua một `Object`; lời gọi `void` có thể là một statement.

Ví dụ dưới đây giả định có lớp `ReflectionReturnDemo.Sample` ở phần 3:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class MethodHandleResultDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle twice = lookup.findStatic(
                ReflectionReturnDemo.Sample.class,
                "twice",
                MethodType.methodType(int.class, int.class)
        );
        MethodHandle touch = lookup.findStatic(
                ReflectionReturnDemo.Sample.class,
                "touch",
                MethodType.methodType(void.class)
        );

        Object boxed = twice.invokeWithArguments(21);
        Object noValue = touch.invokeWithArguments();
        if (!(boxed instanceof Integer) || !boxed.equals(42)
                || noValue != null) {
            throw new AssertionError("Sai hợp đồng invokeWithArguments");
        }

        int exact = (int) twice.invokeExact(21);
        touch.invokeExact(); // Call site có kiểu trả về void.
        System.out.println("exact=" + exact);
    }
}
```

Phép ép kiểu `(int)` ở vị trí `invokeExact` chỉ ra kiểu trả về tại call site; nếu handle thực tế có kiểu trả về khác, lời gọi có thể ném `WrongMethodTypeException`. MethodHandle thường truyền exception của method đích theo quy tắc riêng; không giả định lúc nào cũng có `InvocationTargetException` như `Method.invoke`.

Không dùng cách gọi `invokeExact` rồi ép mọi kết quả sang `Object` để suy luận về `void`. Hai API phục vụ hai cơ chế gọi khác nhau; quy tắc `void → null` ở phần đầu bài là quy tắc của `Method.invoke` và `MethodHandle.invokeWithArguments`.

## 10. Sai lầm thường gặp và cách xử lý

| Sai lầm | Vì sao sai? | Cách kiểm tra/sửa |
| --- | --- | --- |
| Thấy `null` thì kết luận method trả `void` | Reference method cũng có thể trả `null` | Kiểm tra `getReturnType() == void.class` |
| Thấy method khai báo `int` và ép kết quả trực tiếp sang `Long` | `invoke` đóng gói bằng `Integer` | Kiểm tra wrapper đúng với kiểu khai báo |
| Cho rằng `int[]` biến thành `Integer[]` | Mảng primitive đã là đối tượng | Kiểm tra `result instanceof int[]` |
| Gọi `result.getClass()` không kiểm tra `null` | `void` và reference null sẽ gây NPE | Dùng điều kiện `result == null` trước |
| Dùng `isPrimitive()` để xác nhận một trong tám kiểu mà quên `void` | `void.class.isPrimitive()` cũng là `true` | So sánh `void.class` trước |
| Nhầm `Void.class` với `void.class` | Một bên là lớp tham chiếu, một bên là pseudo-type | Dùng `method.getReturnType()` |
| Nuốt `InvocationTargetException` rồi trả `null` | Che giấu lỗi method đích | Lấy `getCause()` và xử lý/phát lại lỗi |
| Truyền receiver `null` cho instance method | Reflection sẽ ném NPE | Dùng đối tượng instance thực |
| Cho rằng method `void` không có tác dụng phụ | `void` chỉ nói về kiểu trả về | Test trạng thái, log hoặc side effect phù hợp |
| Áp dụng quy tắc `invokeExact` giống hệt `Method.invoke` | Call site MethodHandle có hợp đồng kiểu riêng | Kiểm tra `MethodType` và kiểu lời gọi |

## 11. Checklist kiểm chứng trong dự án

Khi viết một adapter gọi method theo metadata, dùng checklist:

1. Đọc `getReturnType()` trước khi giải nghĩa kết quả trả về.
2. Phân nhánh riêng cho `void.class`.
3. Với primitive, kiểm tra wrapper và unbox đúng kiểu; không ép nhầm wrapper.
4. Với reference, cho phép `null` nếu hợp đồng method cho phép.
5. Với mảng primitive, giữ đúng loại mảng; không boxing từng phần tử ngoài ý muốn.
6. Phân biệt lỗi ở quá trình gọi Reflection với exception ném từ method đích.
7. Test cả static/instance method, primitive/void/reference và một đường đi lỗi.
8. Chỉ thêm MethodHandle khi thực sự cần và kiểm thử kiểu lời gọi của API đó riêng.

### Bài tự luyện

1. Viết method trả `boolean` và dùng `Method.invoke` để kiểm tra kết quả là `Boolean.TRUE`.
2. Viết method trả `double` bằng `0.0`; giải thích vì sao kết quả vẫn khác `null`.
3. Tạo hai method: một trả `void`, một trả `String` nhưng luôn `return null`. So sánh kết quả `invoke` và `getReturnType()`.
4. Viết method trả `Void`. Vì sao `getReturnType() == void.class` là `false` dù giá trị thường trả `null`?
5. Viết method trả `int[]`. So sánh `result.getClass()` với `int[].class` và `Integer[].class`.
6. Cố tình truyền `null` làm đối số cho tham số `int`; giải thích loại exception xảy ra trước khi method đích chạy.
7. Viết method `void` có side effect, kiểm tra side effect và kết quả `null`.
8. Viết method trả `int` nhưng ném `IllegalStateException`; lấy nguyên nhân từ `InvocationTargetException`.
9. Thử `invokeWithArguments` và `invokeExact` trên handle trả `int`/`void`; phân biệt kiểu lời gọi và kết quả.

## 12. Tài liệu tham khảo chính thức

- [Method.invoke — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)): hợp đồng boxing kết quả primitive, `null` cho `void`, giữ nguyên mảng primitive và exception từ method đích.
- [Class.isPrimitive — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#isPrimitive()): kiểm tra primitive và trường hợp `void.class`.
- [Void — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Void.html): phân biệt `java.lang.Void`, `Void.TYPE` và `void.class`.
- [InvocationTargetException — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): exception do method đích ném và cách lấy nguyên nhân bằng `getCause()`.
- [MethodHandle — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeWithArguments`, `invokeExact`, kiểu call site và quy tắc chuyển đổi.

**Ghi nhớ:** `Method.invoke` trả `Object`. Kết quả primitive được boxing đúng wrapper; method `void` hoàn thành bình thường trả `null`; mảng primitive được giữ nguyên. Một giá trị `null` tự nó không nói được kiểu khai báo của method, vì method tham chiếu cũng có thể trả `null`. Hãy đọc `getReturnType()` và xử lý exception riêng để kiểm chứng đúng hợp đồng.
