# Vì sao Reflection không tự narrowing hay đổi String thành số?

## 1. Vấn đề: Reflection gọi phương thức, không phải bộ chuyển đổi dữ liệu tùy ý

Trong Java Reflection, lời gọi `Method.invoke(receiver, args...)` phải truyền các đối số phù hợp với **kiểu tham số đã khai báo** của phương thức đích. Reflection hỗ trợ một tập chuyển đổi cụ thể, gồm **unboxing** từ wrapper tương ứng và **widening primitive conversion** được phép. Nó **không tự thực hiện narrowing primitive conversion** (ví dụ `long → int` hoặc `int → short`) và **không parse `String` thành số** (ví dụ `"42" → 42`).

Ví dụ, nếu phương thức đích có chữ ký:

~~~java
public static int doubleIt(int number) {
    return number * 2;
}
~~~

thì `Method.invoke(null, Integer.valueOf(7))` có thể gọi phương thức với tham số `int` bằng cách unbox `Integer`; `Method.invoke(null, Byte.valueOf((byte) 7))` cũng có thể gọi bằng cách unbox `byte` rồi widening `byte → int`. Nhưng truyền `Long.valueOf(7L)` hoặc `"7"` tới tham số `int` sẽ không tự chuyển thành số nguyên; lời gọi thất bại với `IllegalArgumentException`.

Đây là **thiết kế kiểm tra kiểu**, tránh suy đoán giá trị hoặc tự ý thực hiện chuyển đổi có thể gây mất dữ liệu, sai ý nghĩa hay phụ thuộc định dạng chuỗi.

## 2. Java cho phép những chuyển đổi nào khi `Method.invoke()`?

Chữ ký Reflection:

~~~java
Object Method.invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
~~~

Trong runtime, các đối số truyền vào `Object... args` là tham chiếu: khi viết `method.invoke(null, 7)`, trình biên dịch Java sẽ boxing literal `7` thành `Integer` để truyền qua varargs. Reflection sau đó đối chiếu **giá trị runtime** với kiểu tham số method đích.

Đối với tham số **primitive**, Reflection có thể unbox từ wrapper thích hợp rồi widening primitive nếu cần. Nó không narrow giá trị primitive. Đối với tham số **reference**, giá trị phải tương thích về quan hệ kiểu tham chiếu; Reflection không tự “biến” một `Integer` thành `Long` wrapper và không chuyển chuỗi chữ số thành bất cứ kiểu số nào.

| Tham số đích | Giá trị truyền cho `invoke()` | Kết quả | Lý do |
| --- | --- | --- | --- |
| `int` | `Integer.valueOf(7)` | Được | Unboxing `Integer → int`. |
| `int` | `Byte.valueOf((byte) 7)` | Được | Unbox `Byte → byte`, widening `byte → int`. |
| `int` | `Character.valueOf('A')` | Được | Unbox `char`, widening `char → int` (mã Unicode UTF-16 của `'A'` là 65). |
| `long` | `Integer.valueOf(7)` | Được | Unbox `int`, widening `int → long`. |
| `int` | `Long.valueOf(7L)` | **Không** | Cần narrowing `long → int`. |
| `short` | `Integer.valueOf(7)` | **Không** | Cần narrowing `int → short`, kể cả giá trị 7 có thể biểu diễn bằng short. |
| `int` | `"7"` | **Không** | `String` không phải wrapper số; không có tự động parse. |
| `int` | `null` | **Không** | Không thể unbox `null` thành primitive. |
| `Long` (reference) | `Integer.valueOf(7)` | **Không** | `Integer` không phải subtype của `Long`; không tự unbox–widen–rebox. |
| `Number` (reference) | `Integer.valueOf(7)` | Được | `Integer extends Number`: widening reference. |
| `String` | `"7"` | Được | Đã là `String`, không cần chuyển kiểu. |

Với widening, có thể mất **độ chính xác số học** trong một vài chuyển đổi (chẳng hạn `long → float`); “widening” mô tả quan hệ kiểu/miền biểu diễn, **không phải lời hứa rằng mọi giá trị được giữ nguyên từng bit**. Điểm chính là Java có quy tắc widening được định nghĩa sẵn, còn narrowing đòi hỏi quyết định tường minh của người viết.

## 3. Ví dụ độc lập Java 17+: các trường hợp thành công và thất bại

Tạo file `ReflectionConversionDemo.java`:

~~~java
import java.lang.reflect.Method;

public class ReflectionConversionDemo {
    public static int acceptInt(int n) {
        return n * 2;
    }

    public static short acceptShort(short n) {
        return n;
    }

    public static long acceptLong(long n) {
        return n + 1;
    }

    private static void test(String label, Method method, Object arg)
            throws Exception {
        try {
            System.out.println(label + " => " + method.invoke(null, arg));
        } catch (IllegalArgumentException e) {
            System.out.println(label + " => " + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Method intMethod =
                ReflectionConversionDemo.class.getMethod("acceptInt", int.class);
        Method shortMethod =
                ReflectionConversionDemo.class.getMethod("acceptShort", short.class);
        Method longMethod =
                ReflectionConversionDemo.class.getMethod("acceptLong", long.class);

        test("Integer -> int", intMethod, Integer.valueOf(7));
        test("Byte -> int", intMethod, Byte.valueOf((byte) 3));
        test("Character -> int", intMethod, Character.valueOf('A'));
        test("Integer -> long", longMethod, Integer.valueOf(7));
        test("Long -> int", intMethod, Long.valueOf(7));
        test("Integer -> short", shortMethod, Integer.valueOf(7));
        test("String -> int", intMethod, "7");
        test("null -> int", intMethod, null);
        test("explicit parse", intMethod, Integer.parseInt("7"));
        test("explicit narrow", shortMethod, (short) 7);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ReflectionConversionDemo.java
java ReflectionConversionDemo
~~~

Stdout, đã chạy và xác nhận bằng JDK biên dịch tương thích Java 17:

~~~text
Integer -> int => 14
Byte -> int => 6
Character -> int => 130
Integer -> long => 8
Long -> int => IllegalArgumentException
Integer -> short => IllegalArgumentException
String -> int => IllegalArgumentException
null -> int => IllegalArgumentException
explicit parse => 14
explicit narrow => 7
~~~

**Cách đọc chương trình:**

- `getMethod("acceptInt", int.class)` tra cứu **chữ ký khai báo**, không gọi method; kiểu mong đợi là `int.class`.
- `test(...)` nhận `Object arg`; tại `method.invoke(null, arg)`, Reflection xét **kiểu runtime của arg**. Ví dụ `Byte.valueOf((byte) 3)` mang primitive nguồn `byte` khi unbox, có thể widening thành `int`; `acceptInt(3)` trả `6`.
- `Character.valueOf('A')` unbox thành `char`; widening sang `int` tạo `65`; method nhân đôi nên trả `130`. Đây là xử lý mã ký tự, **không phải parse chuỗi**.
- `Long.valueOf(7)` bị từ chối đối với `int` mặc dù `7L` đủ nhỏ để vừa `int`. Reflection không tự narrowing theo giá trị.
- `"7"` là `String`. Reflection không biết người viết muốn hệ cơ số 10, 16, cách xử lý khoảng trắng, số âm hay lỗi input, nên phải parse trước khi invoke.
- `null` không thể trở thành primitive `int`; ví dụ bắt `IllegalArgumentException` từ việc truyền đối số không hợp lệ.
- `Integer.parseInt("7")` thực hiện chuyển đổi có **quy tắc parsing rõ ràng** trước khi gọi; kết quả `int 7` khi đưa vào `Object...` sẽ boxing thành `Integer` rồi Reflection unbox khi gọi.
- `(short) 7` là narrowing tường minh trong Java source; sau khi boxing thành `Short`, Reflection có thể gọi `acceptShort(short)`. Lưu ý cast với số vượt phạm vi có thể làm mất dữ liệu.

## 4. Tại sao `String` không tự động thành số?

Chuỗi chỉ lưu **ký tự**. Dữ liệu người dùng, dòng CSV, tham số HTTP và nội dung JSON có thể chứa các giá trị như `"15"`, `" 15 "`, `"1,500"`, `"0xFF"`, `""` hoặc `"abc"`. Chúng có ý nghĩa số hay không tùy quy ước dữ liệu:

- `"15"` có thể parse theo hệ 10 thành `15`.
- `" 15 "` cần quyết định có `trim()` hay `strip()` trước không; `Integer.parseInt` thuần không chấp nhận dấu cách ở hai đầu.
- `"1,500"` có thể là một nghìn năm trăm hoặc một phẩy năm tùy locale; không thể đoán bằng Reflection.
- `"0xFF"` có thể muốn hiểu là hệ 16 nhưng `Integer.parseInt(text)` mặc định parse hệ 10; muốn hệ 16 phải chỉ định xử lý thích hợp.
- `"abc"` hoặc giá trị vượt miền `int` phải được xử lý như dữ liệu không hợp lệ.

Reflection không phải parser hoặc data-binding framework. Để gọi method nhận `int`, mã của bạn phải có **quy tắc chuyển String thành int** được chọn rõ ràng:

~~~java
String input = " 42 ";
int parsed = Integer.parseInt(input.strip());
Object result = intMethod.invoke(null, parsed);
~~~

Đoạn này phụ thuộc biến `intMethod` từ phần 3 và không phải chương trình độc lập. `parsed` là `int`; khi truyền vào `Object...` của `invoke`, trình biên dịch boxing rồi Reflection tự unbox theo API. Kết quả method `acceptInt` sẽ là `Integer(84)`.

Các API parse phổ biến:

| Kiểu cần tạo | Ví dụ chuyển đổi tường minh | Sai dữ liệu |
| --- | --- | --- |
| `int` | `Integer.parseInt(text)` | `NumberFormatException` |
| `long` | `Long.parseLong(text)` | `NumberFormatException` |
| `double` | `Double.parseDouble(text)` | `NumberFormatException` với cú pháp không hợp lệ; có giá trị đặc biệt như `NaN` nếu cú pháp hỗ trợ. |
| `BigDecimal` | `new BigDecimal(text)` | `NumberFormatException`; phù hợp hơn binary floating-point khi cần biểu diễn thập phân chính xác. |
| `short` | `Short.parseShort(text)` | `NumberFormatException` nếu không parse được hoặc ngoài miền `short`. |

Với dữ liệu phân biệt locale, dùng parser phù hợp như `NumberFormat` và quản lý `ParsePosition`/kiểm tra chuỗi đã được tiêu thụ hết nếu yêu cầu nghiêm ngặt. Đừng gọi `Double.parseDouble` rồi cast `int` để parse mã định danh hay số nguyên: có nguy cơ mất phần thập phân và vượt miền.

## 5. Khi bắt buộc narrowing, hãy quyết định rõ về mất dữ liệu

Narrowing primitive là chuyển sang kiểu có miền biểu diễn nhỏ hơn, ví dụ:

~~~java
long source = 3_000_000_000L;
int narrowed = (int) source; // Có thể mất dữ liệu
~~~

Cú pháp cast ở trên hợp lệ trong Java source, nhưng kết quả không nhất thiết bằng giá trị ban đầu. Nếu muốn **từ chối overflow** thay vì làm mất dữ liệu, dùng:

~~~java
long source = 3_000_000_000L;
int safe = Math.toIntExact(source); // Ném ArithmeticException nếu ngoài miền int
~~~

Với giá trị thực sự thuộc miền, chẳng hạn `long source = 7L;`, `Math.toIntExact(source)` trả `int 7`; đem số `int` này truyền cho method có tham số `int` là hợp lệ.

Cân nhắc hai cách:

- **Chấp nhận mất dữ liệu có chủ đích:** dùng cast `(int) someLong`, `(short) someInt` theo thiết kế dữ liệu và giải thích giới hạn.
- **Không chấp nhận mất dữ liệu:** kiểm tra miền bằng `Math.toIntExact` hoặc điều kiện `Short.MIN_VALUE <= n && n <= Short.MAX_VALUE` trước khi cast.

Reflection không thể chọn hộ giữa hai chính sách này; caller phải quyết định trước khi đưa đối số cho `invoke()`.

## 6. Quy trình chuyển đổi dữ liệu an toàn trước khi gọi Reflection

Khi xây hệ thống đọc cấu hình, CLI, HTTP request hay CSV và gọi các phương thức động:

1. **Xác định signature:** Dùng `Method.getParameterTypes()` hoặc `getGenericParameterTypes()` khi có generic; hiểu rõ method yêu cầu `int`, `Long`, `String` hay một kiểu khác.
2. **Xác định schema input:** Biết định dạng, locale, khả năng null, giới hạn miền, đơn vị, và cách báo lỗi. Đừng suy kiểu số chỉ từ chuỗi hiển thị.
3. **Parse nếu dữ liệu dạng text:** Dùng parser đúng kiểu. Xử lý `NumberFormatException`, chuỗi trống, khoảng trắng, overflow và giá trị không hợp lệ.
4. **Chuyển số tường minh khi cần narrowing:** Cân nhắc cast có chủ đích hoặc kiểm tra miền bằng hàm/điều kiện phù hợp. Đừng truyền `Long` vào `int` rồi mong Reflection tự xử lý.
5. **Kiểm tra null và kiểu tham chiếu:** Primitive không nhận null; reference có thể nhận null nếu logic method cho phép. Không có phép “chuyển thành null hợp lệ” cho primitive.
6. **Chỉ sau đó gọi `invoke(...)`:** Truyền đúng receiver và đối số theo thứ tự. Xử lý `IllegalArgumentException` cho lỗi đối số; `InvocationTargetException.getCause()` cho lỗi phát sinh từ method đích.

Ví dụ xử lý một chuỗi số trước khi gọi phương thức nhận `int`:

~~~java
static Object invokeIntFromText(Method method, Object target, String text)
        throws ReflectiveOperationException {
    int value = Integer.parseInt(text.strip());
    return method.invoke(target, value);
}
~~~

Đây là **method minh họa** phải đặt trong class có import `java.lang.reflect.Method`. Nó dành cho tình huống đã biết chắc method đích nhận đúng một `int`. `Integer.parseInt` có thể ném `NumberFormatException` (unchecked) khi input sai; chữ ký trên không thay thế validation ở biên hệ thống. Với kiểu mục tiêu khác, phải chọn parser/converter tương ứng.

## 7. Tự luyện và kiểm tra

1. `acceptInt(int)` nhận `Short.valueOf((short) 4)` qua Reflection hay không? Dự đoán output nếu logic method nhân đôi.
2. `acceptInt(int)` nhận `Float.valueOf(4.0f)` không? Dù giá trị bằng một số nguyên, lý do từ chối là gì?
3. Với `acceptLong(long)`, truyền `Long.valueOf(9)` và `Integer.valueOf(9)` có khác nhau không? Trường hợp nào phải widening?
4. Nếu dữ liệu text là `" 2147483648 "` và đích là `int`, cần xử lý điều gì ngoài `strip()`? Có nên cast trực tiếp từ `long`?
5. Nếu đích là `Long` reference (không phải `long` primitive), vì sao truyền `Integer.valueOf(9)` không được?
6. Hãy sửa code ở phần 3 để sau khi `Long -> int` bị từ chối, dùng `Math.toIntExact(7L)` và gọi lại. Giải thích vì sao giờ tham số đã phù hợp.

**Ghi nhớ:** Reflection giữ quy tắc chuyển đổi **có định nghĩa rõ**: nhận unboxing và widening thích hợp, nhưng **không đoán parsing String, không tự narrowing, không đổi wrapper này sang wrapper khác tùy ý**. Caller chịu trách nhiệm chọn cách chuyển và xác thực input trước khi gọi.

## Tài liệu chuẩn

- [Java SE 17 — `Method.invoke()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Java SE 17 — `Constructor.newInstance()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...))
- [Java SE 17 — `Field.set()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html#set(java.lang.Object,java.lang.Object))
- [Java Language Specification §5.1 — Kinds of Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1)
- [Java Language Specification §5.3 — Method Invocation Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3)