# 3.7 Truyền tham số primitive, boxing, unboxing, widening và giá trị `null`

**Ngữ cảnh:** Java Advance → dynamic-runtime → 3. Reflection.

Reflection cho phép tìm và gọi phương thức, constructor khi chương trình đang chạy. Khó khăn thường xuất hiện khi tham số đích là `int`, `long` hoặc kiểu primitive khác, trong khi `Method.invoke(...)` và `Constructor.newInstance(...)` nhận đối số qua `Object...`. Cần phân biệt **kiểu của tham số đã khai báo**, **đối tượng thật được truyền vào**, **các chuyển đổi hợp lệ** và **thời điểm kiểm tra lỗi**. Bài này giải thích đầy đủ boxing, unboxing, widening và `null` tại ranh giới lời gọi reflection.

## 1. Hai giai đoạn khác nhau: tìm đúng thành viên và gọi thành viên ấy

**Giai đoạn A — tra cứu chữ ký (lookup):** `Class.getMethod(name, parameterTypes...)` và `Class.getConstructor(parameterTypes...)` dùng các đối tượng `Class<?>` để mô tả **chính xác** kiểu tham số đã khai báo. Lookup **không tự áp dụng** boxing, unboxing hay widening để tìm overload gần giống.

```java
Method m = Service.class.getMethod("update", long.class);
```

Dòng trên tìm phương thức `update(long)`; `update(int)` hoặc `update(Long)` là chữ ký khác và không thay thế được. `getMethod` tìm phương thức `public` có thể truy cập theo cơ chế reflection; `getDeclaredMethod` tìm thành viên được khai báo trực tiếp trên class, nhưng việc gọi vẫn chịu kiểm tra quyền truy cập.

**Giai đoạn B — gọi thành viên đã tìm được:** sau khi có `Method` hoặc `Constructor`, JVM kiểm tra số lượng và kiểu của giá trị truyền. Lúc này có thể xảy ra **unboxing và widening primitive** phù hợp, hoặc **widening reference**. Ví dụ: `Integer(8)` có thể được unbox thành `int`, rồi widen thành `long` cho phương thức đã tìm là `update(long)`.

```text
Class.getMethod("update", long.class)
     │      tìm chữ ký CHÍNH XÁC
     ▼
Method đại diện cho update(long)
     │
Method.invoke(target, 8)
     │      Java đóng gói 8 thành Integer trong Object...
     ▼
Reflection: Integer -> int (unboxing) -> long (widening)
     │
     ▼
Thực thi update(long)
```

Không có chuyện `invoke` tự tìm overload thích hợp nhất dựa vào đối tượng runtime: overload đã được chọn khi thực hiện `getMethod` hoặc `getConstructor`.

## 2. Primitive, wrapper và boxing/unboxing ở ranh giới reflection

Java có 8 kiểu primitive và 8 wrapper tương ứng:

| Primitive | Wrapper | Ví dụ đối số trong `Object[]` |
| --- | --- | --- |
| `boolean` | `Boolean` | `Boolean.TRUE` |
| `byte` | `Byte` | `Byte.valueOf((byte) 3)` |
| `short` | `Short` | `Short.valueOf((short) 3)` |
| `char` | `Character` | `Character.valueOf('A')` |
| `int` | `Integer` | `Integer.valueOf(3)` |
| `long` | `Long` | `Long.valueOf(3L)` |
| `float` | `Float` | `Float.valueOf(3.0f)` |
| `double` | `Double` | `Double.valueOf(3.0)` |

**Boxing** chuyển một giá trị primitive thành wrapper, ví dụ `int` → `Integer`. **Unboxing** lấy primitive từ wrapper, ví dụ `Integer` → `int`. Trong biểu thức `method.invoke(null, 7)`, lời gọi tới `Method.invoke(Object, Object...)` được **trình biên dịch Java** xử lý trước: `7` kiểu `int` được boxing thành `Integer` để nằm trong `Object[]`. Khi thực hiện phương thức đích có tham số `long`, **reflection** unbox `Integer` thành `int` rồi widen thành `long`.

Điều này không có nghĩa wrapper `Integer` đã bị chuyển trực tiếp thành wrapper `Long`. Nếu tham số **khai báo là `Long`**, việc đưa `Integer` vào vẫn không hợp lệ. Phân biệt:

- Tham số `long` (primitive): `Integer(7)` hợp lệ vì `Integer → int → long`.
- Tham số `Long` (reference): `Integer(7)` **không** được đổi thành `Long(7)`; phải truyền một `Long` hoặc `null`.
- Tham số `Number` (reference): `Integer(7)` hợp lệ nhờ **widening reference** (`Integer` là lớp con của `Number`).
- Tham số `Object` (reference): wrapper nhận vào như một đối tượng, không bắt buộc unboxing.

`Method.invoke` trả về `Object`: nếu phương thức đích trả `int`, `double` hoặc primitive khác, giá trị trả về được **boxing** vào wrapper tương ứng; nếu đích trả `void`, giá trị từ `invoke` là `null`. Trả về mảng primitive, ví dụ `int[]`, vẫn là một đối tượng mảng `int[]` chứ không tự chuyển mỗi phần tử thành `Integer`.

## 3. Widening primitive: khi nào hợp lệ?

**Widening primitive conversion** cho phép chuyển giữa các kiểu primitive theo hướng sau, **không tự suy ra chiều ngược lại**:

| Từ primitive | Có thể widen đến |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có kiểu primitive rộng hơn |
| `boolean` | Chỉ tương thích `boolean`; không chuyển sang số |

Khi truyền wrapper cho primitive formal parameter, reflection có thể **unbox trước và widen sau**. Chẳng hạn:

| Tham số đích | Đối tượng truyền | Kết quả | Vì sao |
| --- | --- | --- | --- |
| `long` | `Byte(7)` | Hợp lệ | `Byte → byte → long` |
| `long` | `Integer(8)` | Hợp lệ | `Integer → int → long` |
| `double` | `Character('A')` | Hợp lệ | `Character → char → double`, giá trị `65.0` |
| `float` | `Long(9L)` | Hợp lệ | `Long → long → float` |
| `short` | `Integer(7)` | Lỗi | `int → short` là **narrowing** |
| `int` | `Long(7L)` | Lỗi | `long → int` là **narrowing** |
| `char` | `Byte(65)` | Lỗi | Không có widening từ `byte` sang `char` |
| `boolean` | `Integer(1)` | Lỗi | Không có chuyển đổi số → boolean |
| `Long` | `Integer(7)` | Lỗi | Hai wrapper khác loại; không tự unbox–widen–rebox |
| `Number` | `Integer(7)` | Hợp lệ | Quan hệ kế thừa reference |

**Không được narrowing ngầm** dù giá trị nhỏ và "vừa" kiểu đích. Ví dụ `Integer.valueOf(7)` vẫn không thể truyền cho tham số `short`. Nếu chủ động muốn `short`, phía gọi phải kiểm tra giới hạn số và tạo đúng `Short` (ví dụ `Short.valueOf((short) 7)`). `Method.invoke` cũng không tự parse `"7"` thành số, không tự đổi `BigDecimal` thành `double`.

Một tên dễ gây hiểu sai: **widening không đồng nghĩa luôn chính xác tuyệt đối**. Chuyển `long` sang `float` hoặc `double` có thể làm tròn một số nguyên rất lớn do giới hạn độ chính xác biểu diễn dấu phẩy động, dù chuyển đổi đó là hợp lệ về kiểu.

## 4. `null`: phụ thuộc kiểu tham số và cách gọi `Object...`

`null` không thể unbox thành primitive. Phải phân biệt các trường hợp:

| Tình huống | Kết quả |
| --- | --- |
| Tham số `String`, `Long`, `Integer`, `Object`... nhận `null` | Hợp lệ về chuyển đổi tham số; code đích tự quyết định xử lý |
| Tham số `int`, `long`, `boolean`... nhận `null` qua reflection | `IllegalArgumentException` khi chuyển đối số cho primitive thất bại |
| Code đích nhận `Integer == null` rồi **tự** unbox | Có thể `NullPointerException` **bên trong phương thức đích**, được `Method.invoke` bọc trong `InvocationTargetException` |
| Gọi instance method với receiver `obj == null` | `NullPointerException` do receiver không hợp lệ; khác với `null` ở danh sách tham số |
| Gọi static method với receiver `obj == null` | Hợp lệ: tham số receiver bị bỏ qua đối với phương thức static |

### Cảnh báo: `null` có thể là một đối số hoặc chính mảng đối số

Chữ ký API là `Method.invoke(Object obj, Object... args)`. `Object...` là **varargs ở lời gọi `invoke`**, nên cách Java xây dựng mảng đối số rất quan trọng:

```java
Method m = Demo.class.getMethod("accept", String.class);

// Một đối số duy nhất có giá trị null:
m.invoke(null, (Object) null);        // truyền [null]

// Mảng Object[] đại diện cho một đối số null:
m.invoke(null, new Object[]{null});   // truyền [null]

// Không phải một đối số null:
// m.invoke(null, (Object[]) null);   // danh sách đối số rỗng -> sai số lượng
```

Đoạn trên **minh họa** một static method `Demo.accept(String)` được định nghĩa ở nơi khác, nên không phải chương trình độc lập. Ép `(Object) null` rất hữu ích để tránh sự nhập nhằng của cú pháp varargs Java. Với phương thức **không có tham số**, `m.invoke(null, (Object[]) null)` lại được API cho phép như một danh sách đối số rỗng.

Đừng nhầm `null` của **đối số đầu tiên** (receiver) với `null` nằm trong `args`. Ví dụ `m.invoke(null, (Object) null)` nghĩa là receiver của static method bằng `null` và phương thức đích được truyền **một đối số `null`**.

## 5. Ví dụ Java 17+ chạy độc lập, kiểm chứng từng trường hợp

Tạo file `ReflectionConversionsDemo.java` với nội dung đầy đủ dưới đây. Hai lớp `Target` và `Box` là nested class `public static` để có thể truy xuất constructor/method `public` bằng reflection mà không cần can thiệp kiểm tra truy cập.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReflectionConversionsDemo {
    public static class Target {
        public static String longValue(long value) { return "long:" + value; }
        public static String doubleValue(double value) { return "double:" + value; }
        public static String shortValue(short value) { return "short:" + value; }
        public static String longWrapper(Long value) { return "Long:" + value; }
        public static String numberValue(Number value) {
            return "Number:" + (value == null ? "null" : value.getClass().getSimpleName() + ":" + value);
        }
        public static String stringValue(String value) { return "String:" + value; }
        public static int triple(int value) { return value * 3; }
        public static String choose(int value) { return "int overload"; }
        public static String choose(long value) { return "long overload"; }
        public static String join(String... values) {
            return values == null ? "varargs:null" : "varargs:" + values.length;
        }
        public static void fail(int value) { throw new IllegalStateException("boom"); }
    }

    public static class Box {
        private final long value;
        public Box(long value) { this.value = value; }
        @Override public String toString() { return "Box:" + value; }
    }

    private static void attempt(String label, Method method, Object... args)
            throws IllegalAccessException {
        try {
            System.out.println(label + " -> " + method.invoke(null, args));
        } catch (IllegalArgumentException ex) {
            System.out.println(label + " -> IllegalArgumentException");
        } catch (InvocationTargetException ex) {
            System.out.println(label + " -> InvocationTargetException("
                    + ex.getCause().getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Target> c = Target.class;
        Method forLong = c.getMethod("longValue", long.class);
        Method forDouble = c.getMethod("doubleValue", double.class);
        Method forShort = c.getMethod("shortValue", short.class);
        Method forWrapper = c.getMethod("longWrapper", Long.class);
        Method forNumber = c.getMethod("numberValue", Number.class);
        Method forString = c.getMethod("stringValue", String.class);
        Method triple = c.getMethod("triple", int.class);
        Method chooseLong = c.getMethod("choose", long.class);
        Method join = c.getMethod("join", String[].class);
        Method fail = c.getMethod("fail", int.class);

        attempt("Byte to long", forLong, Byte.valueOf((byte) 7));
        attempt("Integer to long", forLong, Integer.valueOf(8));
        attempt("Character to double", forDouble, Character.valueOf('A'));
        attempt("Integer to short", forShort, Integer.valueOf(7));
        attempt("Long to int", triple, Long.valueOf(9L));
        attempt("Integer to Long", forWrapper, Integer.valueOf(7));
        attempt("Long to Long", forWrapper, Long.valueOf(7));
        attempt("Integer to Number", forNumber, Integer.valueOf(7));
        attempt("null to String", forString, (Object) null);
        attempt("null to long", forLong, (Object) null);
        attempt("null to Long", forWrapper, (Object) null);

        Object result = triple.invoke(null, 4);
        System.out.println("return boxed -> " + result.getClass().getSimpleName() + ":" + result);

        attempt("choose(long) with Integer", chooseLong, Integer.valueOf(3));
        try {
            c.getMethod("longValue", Integer.class);
            System.out.println("lookup -> FOUND");
        } catch (NoSuchMethodException ex) {
            System.out.println("lookup(Integer.class) -> NoSuchMethodException");
        }

        attempt("String to String...", join, "x");
        attempt("String[] to String...", join, (Object) new String[]{"a", "b"});

        Constructor<Box> constructor = Box.class.getConstructor(long.class);
        System.out.println("constructor Short to long -> "
                + constructor.newInstance(Short.valueOf((short) 5)));

        attempt("target throws", fail, Integer.valueOf(1));
    }
}
```

Từ thư mục chứa file trên, biên dịch theo mức ngôn ngữ Java 17 và chạy:

```bash
javac --release 17 ReflectionConversionsDemo.java
java ReflectionConversionsDemo
```

**Stdout chính xác** của chương trình:

```text
Byte to long -> long:7
Integer to long -> long:8
Character to double -> double:65.0
Integer to short -> IllegalArgumentException
Long to int -> IllegalArgumentException
Integer to Long -> IllegalArgumentException
Long to Long -> Long:7
Integer to Number -> Number:Integer:7
null to String -> String:null
null to long -> IllegalArgumentException
null to Long -> Long:null
return boxed -> Integer:12
choose(long) with Integer -> long overload
lookup(Integer.class) -> NoSuchMethodException
String to String... -> IllegalArgumentException
String[] to String... -> varargs:2
constructor Short to long -> Box:5
target throws -> InvocationTargetException(IllegalStateException)
```

Các điểm đáng chú ý từ kết quả:

1. `Byte → byte → long`, `Integer → int → long` và `Character → char → double` **hợp lệ**, khẳng định khả năng unboxing rồi widening.
2. `Integer → short` và `Long → int` **không** hợp lệ vì yêu cầu narrowing; thông báo rơi vào nhánh `IllegalArgumentException` **trước khi vào thân phương thức**.
3. `Integer` không tự chuyển thành `Long`, nhưng `Long` vào tham số `Long` thì đúng, còn `Integer` vào tham số `Number` đúng do quan hệ kế thừa.
4. `null` được chấp nhận với tham số reference (`String` và `Long`), bị từ chối với `long` primitive.
5. `triple(int)` trả về `int`, nhưng `Method.invoke` nhận kết quả dưới dạng một đối tượng `Integer`.
6. `choose(long)` đã được chọn bằng `getMethod("choose", long.class)`. Đối số `Integer` chỉ được chuyển để **gọi overload đã chọn**; nó không làm reflection đổi sang `choose(int)`.
7. `getMethod("longValue", Integer.class)` không tìm thấy `longValue(long)` và ném `NoSuchMethodException`. Đây là **lỗi lookup**, khác `IllegalArgumentException` lúc invoke.
8. Trường hợp `join(String...)` cho thấy **varargs ở phương thức đích không khiến `Method.invoke` tự đóng gói từng đối số**.
9. `Constructor<Box>.newInstance(Short)` dùng cùng quy tắc `Short → short → long`.
10. Khi chính `Target.fail` ném `IllegalStateException`, reflection bọc lỗi đó trong `InvocationTargetException`; chương trình lấy `getCause()` để báo nguyên nhân.

## 6. Varargs của phương thức đích không đồng nghĩa varargs của `Method.invoke`

Giả sử phương thức được khai báo như sau:

```java
public static String join(String... values) {
    return values == null ? "varargs:null" : "varargs:" + values.length;
}
```

Ở mức bytecode/Reflection, tham số cuối này có kiểu **`String[]`**. `getMethod("join", String[].class)` mới là lookup đúng. `Method.isVarArgs()` giúp nhận biết metadata có khai báo `...`, nhưng lời gọi reflection **không thực hiện tự động kiểu đóng gói `join("a", "b")` như cú pháp gọi trực tiếp của Java**.

- `joinMethod.invoke(null, "x")`: chỉ truyền một `String` cho formal parameter `String[]` → `IllegalArgumentException`.
- `joinMethod.invoke(null, (Object) new String[]{"a", "b"})`: truyền **một** đối tượng `String[]` → đúng, đích thấy hai phần tử.
- `joinMethod.invoke(null, (Object) null)`: truyền **một** đối số `null` cho tham số array (kiểu reference) → đích nhận `values == null`.
- `joinMethod.invoke(null, new Object[]{new String[]{"a", "b"}})`: cũng là danh sách gồm **một** array argument.
- `joinMethod.invoke(null, new String[]{"a", "b"})`: dễ gây cảnh báo varargs từ trình biên dịch; mảng `String[]` có thể bị diễn giải như mảng `Object[]` của chính `invoke`, dẫn đến **hai** đối số thay vì một. Nên ép `(Object)` khi muốn chuyển cả mảng thành một đối số.

Điểm cốt lõi: có **hai tầng `...`**; tầng thứ nhất là cú pháp biên dịch của Java để gọi `Method.invoke`, tầng thứ hai là kiểu mảng của tham số mà phương thức đích khai báo. Phải kiểm soát tầng thứ nhất trước khi suy luận tầng thứ hai.

## 7. `Constructor.newInstance` áp dụng nguyên tắc tương tự

`Constructor<?>.newInstance(Object... initargs)` cũng nhận `Object...` và thực hiện các chuyển đổi cần thiết cho tham số constructor.

```java
// Minh họa khi Box là lớp public có constructor public Box(long):
Constructor<Box> ctor = Box.class.getConstructor(long.class);
Box box = ctor.newInstance(Short.valueOf((short) 5));
```

Snippet trên dùng `Box` từ chương trình hoàn chỉnh ở mục 5. Lookup đòi đúng `long.class`, nhưng invocation chấp nhận `Short` vì có unboxing+widening. Ngược lại:

- `Box.class.getConstructor(Short.class)`: `NoSuchMethodException` nếu class chỉ có `Box(long)`.
- `ctor.newInstance(Integer.valueOf(5))`: hợp lệ, `int → long`.
- `ctor.newInstance(Long.valueOf(5))`: hợp lệ, `long → long`.
- `ctor.newInstance((Object) null)`: `IllegalArgumentException` do `long` không nhận `null`.
- `ctor.newInstance(Double.valueOf(5))`: `IllegalArgumentException` do `double → long` là narrowing.
- Nếu **thân constructor** ném exception, `newInstance` bọc nguyên nhân trong `InvocationTargetException`.

Một lưu ý về thuật ngữ: **reflection không thực hiện "constructor overload resolution" thay cho bạn**. Đã có `Constructor` nào thì áp dụng chuyển đổi giá trị để gọi **chính** constructor đó.

## 8. Phân biệt ngoại lệ để chẩn đoán đúng

| Ngoại lệ | Xuất hiện ở đâu? | Hướng xử lý |
| --- | --- | --- |
| `NoSuchMethodException` | `getMethod`/`getDeclaredMethod` hoặc `getConstructor` khi chữ ký không khớp | Kiểm tra đúng tên, đúng `.class` của từng tham số, `public`/declared, overload |
| `IllegalArgumentException` | `invoke`/`newInstance` khi sai số lượng hoặc kiểu đối số; null cho primitive; narrowing không hợp lệ; receiver không đúng kiểu | So `getParameterTypes()` với runtime class của từng đối số; đừng tự động đổi kiểu nếu chưa có quy tắc |
| `InvocationTargetException` | Thân method/constructor **đã chạy** và ném exception | Kiểm tra `getCause()` để lấy lỗi thực tế, kể cả `NullPointerException` hay `IllegalArgumentException` do code đích ném |
| `NullPointerException` | Receiver `null` của instance method, hoặc unbox `null` do code Java tự làm | Phân biệt receiver, đối số và unboxing ở code caller/callee |
| `IllegalAccessException` | Thành viên không thể truy cập theo quyền hiện hành | Kiểm tra visibility và quyền module; lỗi này độc lập với chuyển đổi giá trị |

Không nên bắt mọi exception rồi đổi thành một lỗi "reflection failed" chung chung vì như vậy mất dấu giai đoạn xảy ra sự cố. Ví dụ, **`IllegalArgumentException` ném bởi thân phương thức** sẽ nằm trong `InvocationTargetException.getCause()`, khác với `IllegalArgumentException` do kiểm tra đối số **trước** khi gọi thân phương thức.

## 9. Cách xây dựng lời gọi reflection an toàn

Khi nhận giá trị từ cấu hình, JSON, dòng lệnh hoặc giao diện người dùng rồi gọi method động, nên làm rõ hợp đồng trước:

1. **Chọn chữ ký đích:** lấy `Method`/`Constructor` dựa vào `getParameterTypes()`; ví dụ `long.class` khác `Long.class`. Nếu có overload, chọn có chủ đích.
2. **Xác định kiểu và nullability:** `null` có được chấp nhận không? Primitive có bắt buộc? Nếu thiếu số liệu, quyết định báo lỗi hay dùng default một cách tường minh.
3. **Chuyển đổi ở ranh giới dữ liệu:** nếu nguồn là `String` hoặc kiểu số không đúng, hãy parse/validate trong logic ứng dụng. Reflection chỉ hỗ trợ chuyển đổi nhất định, không phải công cụ chuyển đổi dữ liệu tổng quát.
4. **Kiểm tra narrowing:** nếu cần `long` → `int` hoặc `int` → `short`, phải kiểm tra miền giá trị và làm rõ ý nghĩa dữ liệu. Tránh ép kiểu tự động làm mất thông tin.
5. **Đóng gói mảng đối số đúng:** truyền `Object[]` chứa đúng một phần tử cho mỗi formal parameter; chú ý tham số array và varargs, đặc biệt khi phần tử `null`.
6. **Phân loại lỗi:** lookup (`NoSuchMethodException`), mismatch (`IllegalArgumentException`), exception từ thân method (`InvocationTargetException`), quyền truy cập (`IllegalAccessException`) là các hướng xử lý khác nhau.

**Đoạn quan sát tham số** sau là *snippet minh họa* để đặt trong chương trình đang có đối tượng `Method m`, không phải chương trình chạy độc lập:

```java
System.out.println("declaringClass = " + m.getDeclaringClass().getName());
System.out.println("name = " + m.getName());
System.out.println("varArgs = " + m.isVarArgs());
for (Class<?> type : m.getParameterTypes()) {
    System.out.println("parameter = " + type.getTypeName());
}
```

Khi lỗi liên quan loader, hai class có thể có cùng tên nhưng không cùng runtime type identity; lúc đó cũng cần kiểm tra `type.getClassLoader()`. Đây là bước bổ sung trong hệ thống plugin, nhưng chưa thay đổi các quy tắc boxing/unboxing/widening được giải thích ở bài này.

## 10. Bài tập tự kiểm tra có đáp án

**Câu 1.** Method có chữ ký `f(double)`. Truyền `Integer.valueOf(9)` cho `Method.invoke` được không?

**Đáp án:** Được. `Integer → int` bằng unboxing, sau đó `int → double` bằng widening. Kết quả tham số ở đích là `9.0`.

**Câu 2.** Method có chữ ký `f(Double)`. Truyền `Integer.valueOf(9)` có được không?

**Đáp án:** Không. `Integer` không phải `Double`; reflection không tự thực hiện `Integer → int → double → Double`. Nếu ứng dụng muốn chuyển, tự tạo `Double.valueOf(9.0)` trước khi gọi.

**Câu 3.** Method có chữ ký `f(short)`. Truyền `Integer.valueOf(1)` có được không, dù giá trị nằm trong miền `short`?

**Đáp án:** Không. `int → short` là narrowing, không được áp dụng tự động khi invoke. Phía gọi phải kiểm tra và chuyển sang `Short` có chủ đích.

**Câu 4.** Khác nhau thế nào giữa `getMethod("f", long.class)` và `invoke(target, Integer.valueOf(1))`?

**Đáp án:** `getMethod` chọn **chính xác** overload có tham số `long`; `invoke` chỉ chuyển `Integer → int → long` để gọi overload đó. Nó không tìm lại overload `f(int)`.

**Câu 5.** Tại sao `m.invoke(null, (Object) null)` có thể hợp lệ cho `f(String)` nhưng lỗi cho `f(int)`?

**Đáp án:** Cả hai đều nhận **một** đối số `null`. `String` là reference, nhận `null`; `int` là primitive, không unbox được `null` nên `IllegalArgumentException`.

**Câu 6.** Code đích `f(Integer value)` thực hiện `int x = value;` khi value bằng `null`, và được gọi qua reflection. Người gọi nhận ngoại lệ nào?

**Đáp án:** Thân method gây `NullPointerException` lúc unboxing. `Method.invoke` bọc nó trong `InvocationTargetException`; xem `getCause()` để nhận `NullPointerException`.

**Câu 7.** Với `f(String... values)`, làm sao chuyển hai chuỗi như **một tham số array** qua reflection?

**Đáp án:** Tra `getMethod("f", String[].class)`, rồi gọi `m.invoke(target, (Object) new String[]{"a", "b"})` hoặc truyền `new Object[]{new String[]{"a", "b"}}`. Không tự trải chuỗi thành nhiều đối số của `invoke`.

**Câu 8.** Nếu method đích trả `void` hoặc `int`, `Method.invoke` trả gì?

**Đáp án:** Với `void`, trả `null`; với `int`, trả `Integer` chứa giá trị trả về.

## Tóm tắt quy tắc cần nhớ

- **Lookup theo chữ ký chính xác:** `long.class`, `Long.class`, `int.class` là những tham số khác nhau.
- **Đối số đi qua `Object...`:** primitive ở lời gọi `invoke` thường đã được Java boxing thành wrapper; reflection có thể unbox và widen cho primitive formal parameter.
- **Widening được, narrowing không tự động:** `Integer → long` được; `Long → int` không được, dù dữ liệu tình cờ vừa trong `int`.
- **Wrapper khác wrapper không tự chuyển:** `Integer` không tự trở thành `Long`; reference widening như `Integer → Number` vẫn hợp lệ.
- **`null` chỉ gắn được với kiểu reference:** với primitive, reflection báo `IllegalArgumentException`; nếu thân code tự unbox `null` thì đó là exception từ code đích.
- **Varargs có hai tầng:** `Method.invoke(Object, Object...)` không tự đóng gói varargs của method đích; hãy truyền đúng mảng và ép `(Object)` khi cần.
- **Lỗi phản ánh giai đoạn:** `NoSuchMethodException` (lookup), `IllegalArgumentException` (binding/conversion), `InvocationTargetException` (thân method/constructor).

### Tài liệu chuẩn

- [Java SE 17 — `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — `Constructor.newInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [JLS Java SE 17 — `5.1.2 Widening Primitive Conversion, `5.1.7 Boxing, `5.1.8 Unboxing, `5.3 Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html)