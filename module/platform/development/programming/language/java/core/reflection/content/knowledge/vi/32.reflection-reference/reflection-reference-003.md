# Bảng chuyển đổi kiểu được phép khi Reflection `get`, `set`, `invoke` và `newInstance`

Khi sử dụng Java Reflection, tên kiểu có thể được biết tại runtime nhưng lời gọi vẫn phải tuân theo **quy tắc chuyển đổi kiểu**. Một số chuyển đổi được Java Reflection hỗ trợ tự động, đặc biệt là **mở rộng kiểu nguyên thủy (primitive widening)** và **mở hộp (unboxing)** trong các trường hợp phù hợp. Ngược lại, **thu hẹp kiểu (narrowing)** như `long → int` hay `double → float` không được Reflection tự thực hiện.

Bốn nhóm API dễ bị nhầm:

- `Field.get(...)`, `Field.getInt(...)`, `Field.getLong(...)`...: **đọc giá trị một field**, có thể boxing hoặc widening tùy getter được gọi.
- `Field.set(...)`, `Field.setInt(...)`, `Field.setLong(...)`...: **ghi một giá trị vào field**, chỉ khi giá trị phù hợp kiểu field.
- `Method.invoke(...)`: gọi **method đã được tìm thấy**, kiểm tra/chuyển đổi **đối số thực tế sang kiểu tham số khai báo**.
- `Constructor.newInstance(...)`: tạo đối tượng bằng **constructor đã được tìm thấy**, sử dụng các quy tắc chuyển đổi đối số tương tự `Method.invoke`.

Bài này đưa ra bảng đầy đủ cho tám primitive, đối chiếu các nhóm API, ví dụ Java 17+ biên dịch được và những trường hợp thất bại cần nhận biết. Chủ đề là **kiểu dữ liệu**, không phải tự động vượt qua quyền truy cập `private`, `final` hay ranh giới module.

## 1. Nền tảng: identity, widening, boxing và unboxing

### 1.1. Identity và widening primitive

**Identity conversion** giữ nguyên kiểu, ví dụ `int → int`.

**Widening primitive conversion** chuyển kiểu nguyên thủy sang kiểu đích được Java cho phép theo sơ đồ:

```text
byte  ──> short ──> int ──> long ──> float ──> double
                 ^
char ────────────┘

boolean  (chỉ chuyển sang boolean)
```

Sơ đồ chỉ minh họa những nhánh chính. Bảng đầy đủ dưới đây mới là chuẩn để tra cứu, đặc biệt vì `char` không chuyển trực tiếp sang `short` và các kiểu số có nhiều nhánh mở rộng.

| Kiểu nguồn | Kiểu đích primitive được phép (bao gồm chính nó) |
| --- | --- |
| `boolean` | `boolean` |
| `byte` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `short` | `short`, `int`, `long`, `float`, `double` |
| `char` | `char`, `int`, `long`, `float`, `double` |
| `int` | `int`, `long`, `float`, `double` |
| `long` | `long`, `float`, `double` |
| `float` | `float`, `double` |
| `double` | `double` |

**Không được phép tự động:** `int → byte`, `long → int`, `double → float`, `short → char`, `char → short`, và mọi chuyển đổi giữa `boolean` với các kiểu số.

`byte → char` cũng không được phép dù có những giá trị byte dương biểu diễn được bởi `char`. Reflection tuân theo **quan hệ chuyển đổi kiểu**, không tự xét giá trị hiện tại có vừa miền giá trị của kiểu đích hay không.

**Widening không đồng nghĩa giữ nguyên độ chính xác tuyệt đối:** ví dụ `long → float` và `int → float` là chuyển đổi hợp lệ nhưng có thể mất bit chính xác do floating-point representation. Quy tắc widening ở đây nói đến **khả năng chuyển kiểu**, không phải bảo đảm không mất thông tin số.

### 1.2. Boxing và unboxing

Tám cặp primitive/wrapper tương ứng:

| Primitive | Wrapper |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

- **Boxing**: `int` thành đối tượng `Integer`.
- **Unboxing**: `Integer` trở lại primitive `int`.
- **Unboxing rồi widening**: `Integer(4) → int → long` là hợp lệ khi method/constructor/field đích yêu cầu `long`.
- **Không có chuyển đổi tự động theo chuỗi unbox → widen → box sang wrapper khác**: `Integer` không tự biến thành `Long` để điền field hoặc tham số **khai báo `Long`**.

Khi viết `method.invoke(target, 5)`, trình biên dịch tự boxing literal `5` thành `Integer` để đưa vào danh sách đối số `Object...`. Sau đó, nếu **tham số phương thức đích là `long`**, Reflection có thể unbox `Integer → int` và widen `int → long`.

## 2. Bảng nhanh: API nào nhận chuyển đổi nào?

| Lời gọi Reflection | Kiểu nguồn thực tế | Kiểu đích/giá trị cần nhận | Quy tắc chính |
| --- | --- | --- | --- |
| `field.get(obj)` | Kiểu khai báo của field | `Object` trả về | Field primitive được **box theo đúng kiểu gốc**; field tham chiếu trả chính giá trị tham chiếu |
| `field.getInt(obj)` hoặc `getX` | Primitive của field | Primitive theo tên getter | Chỉ đọc được khi **field type → getter type** là identity/widening |
| `field.set(obj, value)` | Đối tượng `value` | Kiểu khai báo của field | Field primitive: **unbox wrapper** rồi (nếu cần) widen; field tham chiếu: kiểm tra giá trị assignable hoặc `null` |
| `field.setInt(obj, n)` hoặc `setX` | Primitive theo tên setter | Kiểu khai báo của field | Chỉ ghi được nếu **setter type → field type** là identity/widening |
| `method.invoke(obj, args...)` | Từng đối số `Object`/wrapper | Tham số khai báo của **method đã chọn** | Unbox + widen cho primitive; tham chiếu phải tương thích; không tự narrowing |
| `constructor.newInstance(args...)` | Từng đối số `Object`/wrapper | Tham số khai báo của **constructor đã chọn** | Tương tự `Method.invoke`; không tự narrowing |

**Hai chiều dễ nhầm nhất:**

- Getter có kiểu đích: `Field.getLong` có thể đọc field `int` vì `int → long`.
- Setter có kiểu nguồn: `Field.setLong` **không** thể ghi vào field `int` vì `long → int` là narrowing.

Nói ngắn gọn: đọc dùng hướng **field → kết quả getter**; ghi/gọi/tạo đối tượng dùng hướng **đối số → vị trí đích**.

## 3. `Field.get(obj)`: đọc field dưới dạng `Object`

`Field.get(Object obj)` trả về một `Object`.

- Nếu field là reference, trả về reference đang lưu, có thể là `null`.
- Nếu field primitive, giá trị được **box** thành wrapper tương ứng. Field `short` trả `Short`, field `int` trả `Integer`; không biến `short` thành `Integer` chỉ vì kết quả khai báo của `get` là `Object`.
- Lệnh `(int) field.get(obj)` có thể unbox khi đối tượng thực tế là `Integer`, nhưng **không** phải cách tổng quát để chuyển một `Short` đã box thành `int`: cách ép kiểu này có thể ném `ClassCastException`.

Ví dụ:

```java
class Sample {
    public short small = 7;
}

// Giả định một đoạn code khác đã tạo đối tượng Sample:
Sample x = new Sample();
java.lang.reflect.Field field = Sample.class.getField("small");

Object raw = field.get(x);          // một Short chứa giá trị 7
short small = (Short) raw;          // đúng
int widened = field.getInt(x);     // đúng: short → int
```

Đây là đoạn minh họa phụ thuộc vào vị trí đặt class `Sample` để có quyền truy cập thích hợp; chương trình đầy đủ, độc lập nằm ở mục 7.

## 4. `Field.getBoolean/getByte/.../getDouble`: tra cứu phép đọc widening

Các getter primitive bao gồm `getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble`.

**Hướng bảng: cột “kiểu field” là nguồn, “getter được phép” là kiểu đích.**

| Kiểu field | Những getter primitive hợp lệ |
| --- | --- |
| `boolean` | `getBoolean` |
| `byte` | `getByte`, `getShort`, `getInt`, `getLong`, `getFloat`, `getDouble` |
| `short` | `getShort`, `getInt`, `getLong`, `getFloat`, `getDouble` |
| `char` | `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble` |
| `int` | `getInt`, `getLong`, `getFloat`, `getDouble` |
| `long` | `getLong`, `getFloat`, `getDouble` |
| `float` | `getFloat`, `getDouble` |
| `double` | `getDouble` |

Ví dụ:

```java
// field là một Field thuộc instance có kiểu short.
int a = field.getInt(instance);      // hợp lệ: short → int
double b = field.getDouble(instance);// hợp lệ: short → double
byte c = field.getByte(instance);    // IllegalArgumentException: short → byte
```

Đoạn trên là minh họa, không phải file chạy độc lập. Lưu ý các **typed getter không tự unbox reference field**: nếu field khai báo `Integer` thì `getInt` không phải phương án tổng quát để đọc wrapper. Hãy dùng `get`, kiểm tra `Integer`, sau đó tự unbox.

Ngữ nghĩa của bảng không phụ thuộc giá trị: field `short` đang chứa số 7 vẫn **không** thể được lấy bằng `getByte` vì kiểu field là `short`.

## 5. `Field.set(obj, value)`: viết field, kiểm tra kiểu đích

`Field.set(Object obj, Object value)` nhận đối số thứ hai dưới dạng tham chiếu.

### 5.1. Ghi vào primitive field

Giả sử field khai báo:

```java
public long count;
```

Các giá trị được phép:

```java
field.set(obj, Long.valueOf(9));     // Long → long
field.set(obj, Integer.valueOf(9));  // Integer → int → long
field.set(obj, Short.valueOf((short) 9)); // Short → short → long
field.set(obj, Character.valueOf('A'));  // Character → char → long
```

Với field `long`, `Byte`, `Short`, `Character`, `Integer` và `Long` được unbox rồi widening nếu cần; `Float`, `Double` và `Boolean` không phù hợp.

Những thao tác sau thất bại:

```java
field.set(obj, Double.valueOf(9)); // IllegalArgumentException: double → long
field.set(obj, "9");               // IllegalArgumentException: String không phải wrapper số
field.set(obj, null);              // IllegalArgumentException: không unbox được null
```

Reflection **không parse chuỗi số**, không kiểm tra và tự thu hẹp một `Long` xuống `int`, và không tự chuyển `Double` sang `Integer` theo phép ép tường minh. Khi input từ JSON/CSV/String, ứng dụng phải tự parse, kiểm tra giới hạn và đưa ra wrapper có thể unbox/widen hợp lệ.

### 5.2. Ghi vào reference field

Nếu field khai báo `CharSequence`, có thể gán `String`, `StringBuilder` hoặc `null` vì chúng tương thích với kiểu đích:

```java
// Field text được khai báo: public CharSequence text;
textField.set(instance, "abc");                    // hợp lệ
textField.set(instance, new StringBuilder("abc")); // hợp lệ
textField.set(instance, null);                     // hợp lệ
textField.set(instance, Integer.valueOf(3));       // IllegalArgumentException
```

Đối với field khai báo `Long`, `Integer.valueOf(3)` **không** được chuyển thành `Long.valueOf(3)`: đây là hai wrapper reference khác nhau.

### 5.3. Final, static, receiver và accessibility là những vấn đề khác

- Instance field cần receiver đúng class hoặc subtype, không được truyền `null`.
- Với static field, receiver bị bỏ qua (có thể dùng `null`).
- Ghi field `final` bị giới hạn riêng, và việc cố mở quyền bằng `setAccessible(true)` không bảo đảm được phép ghi. Final static field thuộc diện ràng buộc chặt.
- `getDeclaredField` tìm được metadata của private field nhưng không đồng nghĩa được phép đọc/ghi; `IllegalAccessException` có thể xảy ra.
- Khi tên/receiver/quyền truy cập không hợp lệ, lỗi có thể xảy ra **trước khi** quy tắc chuyển đổi giá trị được áp dụng.

## 6. `Field.setBoolean/setByte/.../setDouble`: bảng setter primitive

Các typed setter nhận một giá trị primitive (ví dụ `setInt(Object obj, int i)`). **Hướng bảng: kiểu tham số của setter → kiểu field đích.**

| Setter được gọi | Kiểu field có thể nhận |
| --- | --- |
| `setBoolean` | `boolean` |
| `setByte` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `setShort` | `short`, `int`, `long`, `float`, `double` |
| `setChar` | `char`, `int`, `long`, `float`, `double` |
| `setInt` | `int`, `long`, `float`, `double` |
| `setLong` | `long`, `float`, `double` |
| `setFloat` | `float`, `double` |
| `setDouble` | `double` |

Ví dụ field có kiểu `long`:

```java
wideField.setInt(instance, 42);       // hợp lệ: int → long
wideField.setLong(instance, 42L);     // hợp lệ: long → long
wideField.setDouble(instance, 42.0);  // IllegalArgumentException
```

Đừng đảo hướng của bảng getter và setter. `getLong` từ field `int` hợp lệ, trong khi `setLong` vào field `int` không hợp lệ.

## 7. Chương trình Java 17+: chạy thật các ca thành công và thất bại

Ví dụ sau minh họa **cả bốn API**, gồm primitive widening, unboxing, reference assignability, lookup theo chữ ký chính xác, `void`, varargs và các lỗi thu hẹp kiểu.

Tạo file **`ReflectionConversionsDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionConversionsDemo {
    public static class Target {
        public short small = 7;
        public int number = 10;
        public long wide;
        public CharSequence text = "before";
        public static int shared = 3;

        public Target(long seed) {
            this.wide = seed;
        }

        public double twice(double value) {
            return 2 * value;
        }

        public String describe(CharSequence value) {
            return "[" + value + "]";
        }

        public void touch() {}

        public static String join(String... words) {
            return String.join("|", words);
        }
    }

    @FunctionalInterface
    interface Checked {
        void run() throws Exception;
    }

    private static void expectIllegal(String label, Checked action)
            throws Exception {
        try {
            action.run();
            System.out.println(label + ": unexpected success");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + ": IllegalArgumentException");
        }
    }

    public static void main(String[] args) throws Exception {
        Constructor<Target> ctor = Target.class.getConstructor(long.class);
        Target target = ctor.newInstance(Integer.valueOf(4));
        System.out.println("constructor long=" + target.wide);

        Field small = Target.class.getField("small");
        System.out.println("Field.get wrapper="
                + small.get(target).getClass().getSimpleName());
        System.out.println("Field.getInt short=" + small.getInt(target));
        expectIllegal("Field.getByte short", () -> small.getByte(target));

        Field wide = Target.class.getField("wide");
        wide.set(target, Integer.valueOf(21));
        System.out.println("Field.set Integer -> long="
                + wide.getLong(target));
        wide.setInt(target, 33);
        System.out.println("Field.setInt -> long="
                + wide.getLong(target));

        Field number = Target.class.getField("number");
        number.set(target, Character.valueOf('A'));
        System.out.println("Field.set Character -> int="
                + number.getInt(target));
        expectIllegal("Field.set Long -> int",
                () -> number.set(target, Long.valueOf(5)));

        Field text = Target.class.getField("text");
        text.set(target, new StringBuilder("ready"));
        System.out.println("Field.set subtype=" + text.get(target));
        expectIllegal("Field.set incompatible reference",
                () -> text.set(target, Integer.valueOf(3)));

        Method twice = Target.class.getMethod("twice", double.class);
        System.out.println("Method.invoke Integer -> double="
                + twice.invoke(target, Integer.valueOf(6)));
        expectIllegal("Method.invoke String -> double",
                () -> twice.invoke(target, "6"));

        Method describe =
                Target.class.getMethod("describe", CharSequence.class);
        System.out.println("Method.invoke String -> CharSequence="
                + describe.invoke(target, "abc"));

        try {
            Target.class.getMethod("twice", int.class);
            System.out.println("getMethod int: unexpected success");
        } catch (NoSuchMethodException expected) {
            System.out.println("getMethod int: NoSuchMethodException");
        }

        Method touch = Target.class.getMethod("touch");
        System.out.println("void invoke -> null="
                + (touch.invoke(target) == null));

        Method join = Target.class.getMethod("join", String[].class);
        System.out.println("varargs array="
                + join.invoke(null, (Object) new String[]{"a", "b"}));
        expectIllegal("varargs no auto packing",
                () -> join.invoke(null, "a", "b"));

        expectIllegal("newInstance String -> long",
                () -> ctor.newInstance("4"));
        System.out.println("primitive get boxed="
                + (number.get(target) instanceof Integer));
    }
}
```

**Biên dịch/chạy:**

```bash
javac -encoding UTF-8 ReflectionConversionsDemo.java
java ReflectionConversionsDemo
```

**Output thực tế của chương trình:**

```text
constructor long=4
Field.get wrapper=Short
Field.getInt short=7
Field.getByte short: IllegalArgumentException
Field.set Integer -> long=21
Field.setInt -> long=33
Field.set Character -> int=65
Field.set Long -> int: IllegalArgumentException
Field.set subtype=ready
Field.set incompatible reference: IllegalArgumentException
Method.invoke Integer -> double=12.0
Method.invoke String -> double: IllegalArgumentException
Method.invoke String -> CharSequence=[abc]
getMethod int: NoSuchMethodException
void invoke -> null=true
varargs array=a|b
varargs no auto packing: IllegalArgumentException
newInstance String -> long: IllegalArgumentException
primitive get boxed=true
```

Kết quả trên được kiểm chứng bằng `javac` và `java`. Một số câu lệnh dùng `expectIllegal` để minh họa và **chủ động bắt lỗi**, vì vậy chương trình vẫn kết thúc bình thường.

**Đọc kết quả theo nhóm:**

1. `Constructor<Target>` nhận tham số khai báo `long`. Truyền `Integer(4)` được unbox thành `int` rồi widen thành `long`, nên `wide = 4`.
2. `small` là field `short`. `Field.get` box thành `Short`; `getInt` hợp lệ; `getByte` thất bại vì sẽ phải thu hẹp `short → byte`.
3. `wide` là field `long`. Ghi `Integer(21)` hoặc `setInt(33)` đều hợp lệ. `number` là field `int`; ghi `Character('A')` thành 65, còn `Long(5)` không thể tự thu hẹp xuống `int`.
4. `text` khai báo `CharSequence`, nhận được `StringBuilder` vì implements interface này, nhưng không nhận `Integer`.
5. `twice(double)` nhận `Integer(6)` sau unbox+widen và trả về `Double(12.0)`. Truyền chuỗi `"6"` không tự parse.
6. `describe(CharSequence)` nhận `String` vì `String` implements `CharSequence`.
7. `getMethod("twice", int.class)` **không tìm thấy** chỉ vì tồn tại `twice(double)`: lookup yêu cầu **chữ ký tham số khai báo**, không áp dụng quy tắc widening khi tìm method.
8. `void` trả `null` qua `Method.invoke`. Phương thức nhận `String...` thực chất có tham số reflection cuối kiểu `String[]`, nên phải truyền một mảng như **một đối số**.
9. Constructor `Target(long)` không tự chuyển `String` thành `long`.

## 8. `Method.invoke`: chuyển đổi tham số sau khi đã chọn method

`Method.invoke(Object receiver, Object... args)` cho phép các chuyển đổi kiểu khi **truyền giá trị** cho từng tham số method:

| Method đích | Đối số truyền vào | Kết quả |
| --- | --- | --- |
| `f(long)` | `Integer.valueOf(3)` | Hợp lệ: unbox `int`, widen `long` |
| `f(double)` | `Long.valueOf(3)` | Hợp lệ: unbox `long`, widen `double` |
| `f(CharSequence)` | `"abc"` | Hợp lệ: reference tương thích |
| `f(Number)` | `Integer.valueOf(3)` | Hợp lệ: `Integer` là subtype của `Number` |
| `f(Long)` | `Integer.valueOf(3)` | Không hợp lệ: không tự unbox+widen+box thành `Long` |
| `f(int)` | `Long.valueOf(3)` | Không hợp lệ: phải narrowing `long → int` |
| `f(boolean)` | `Integer.valueOf(1)` | Không hợp lệ: số không tự đổi thành boolean |
| `f(int)` | `null` | Không hợp lệ: không thể unbox `null` |
| `f(String)` | `null` | Hợp lệ nếu việc gọi method/logic bên trong chấp nhận `null` |
| `f(int)` | `"123"` | Không hợp lệ: Reflection không parse String |

**Cực kỳ quan trọng:** hai bước sau hoàn toàn khác nhau:

```java
Method m = Target.class.getMethod("twice", double.class); // TÌM đúng signature
Object result = m.invoke(target, Integer.valueOf(6));    // CHUYỂN giá trị
```

`getMethod` và `getDeclaredMethod` tra cứu dựa trên **tên + kiểu tham số khai báo chính xác**, không tự chọn overload theo khả năng widening của đối số. Reflection không thay compiler làm overload resolution.

### Giá trị trả về của `invoke`

- Method trả primitive: `Method.invoke` box thành wrapper tương ứng, ví dụ `double → Double`.
- Method trả reference: trả object thực tế, có thể `null`.
- Method trả `void`: `invoke` trả `null`.
- Mảng primitive như `int[]` được trả dưới dạng đối tượng mảng `int[]`, **không** tự box mỗi phần tử thành `Integer`.

**Lỗi khác chuyển đổi:** method hợp lệ nhưng code đích ném exception thì `Method.invoke` bọc exception trong `InvocationTargetException`; xem `getCause()`. Lỗi kiểm tra đối số do Reflection thường là `IllegalArgumentException`, lỗi truy cập có thể là `IllegalAccessException`, receiver không phù hợp cũng dẫn đến lỗi riêng.

## 9. `Constructor.newInstance`: cùng quy tắc đối số, nhưng constructor phải chọn đúng

`Constructor<T>.newInstance(Object... args)` áp dụng **unboxing và method invocation conversions** để khớp từng đối số với kiểu tham số của constructor đã chọn.

```java
Constructor<Target> constructor =
        Target.class.getConstructor(long.class); // lookup chính xác long
Target value = constructor.newInstance(Integer.valueOf(4)); // hợp lệ
```

Trong đoạn trên, `Target` là class được định nghĩa ở ví dụ mục 7. Nếu thay `getConstructor(int.class)`, lookup ném `NoSuchMethodException` vì chỉ có constructor `Target(long)`.

Một vài tình huống:

- `newInstance(Short.valueOf((short) 5))` với constructor `(long)`: hợp lệ.
- `newInstance(Long.valueOf(5))` với constructor `(int)`: không hợp lệ.
- `newInstance("5")` với constructor `(long)`: không hợp lệ vì Reflection không parse.
- `newInstance(null)` có thể gây nhập nhằng ở **lời gọi varargs Java**. Nếu muốn đưa **một tham số `null`** cho constructor có một tham số reference, dùng `newInstance((Object) null)`. Đối với constructor không tham số, có thể dùng `newInstance()`.

Tương tự `Method.invoke`, constructor có tham số varargs **không tự nhận từng đối số rời rạc của method đích rồi đóng gói vào mảng**. Hãy truyền một mảng đúng kiểu như một tham số formal.

Một class `abstract`, enum, class không truy cập được hoặc constructor ném exception vẫn có thể làm `newInstance` thất bại vì lý do ngoài chuyển đổi. `Class.newInstance()` đã bị deprecated từ Java 9; dùng `getDeclaredConstructor().newInstance()` khi phù hợp thay thế.

## 10. Varargs có hai tầng: của API Reflection và của method đích

Chữ ký `Method.invoke(Object receiver, Object... args)` nghĩa là **chính API Reflection nhận varargs**. Điều đó không làm `invoke` tự thực hiện cơ chế gom varargs cho method được gọi.

Ví dụ method đích:

```java
public static String join(String... words) {
    return String.join("|", words);
}
```

Runtime signature của nó là `join(String[])`. Khi dùng Reflection:

```java
Method join = Target.class.getMethod("join", String[].class);
Object result = join.invoke(null, (Object) new String[]{"a", "b"}); // đúng
```

Ép `(Object)` bảo đảm mảng là **một phần tử** của `args` thay vì có thể bị diễn giải thành chính mảng chứa các đối số cho `Method.invoke`.

```java
join.invoke(null, "a", "b"); // Sai: 2 đối số thay vì 1 đối số String[]
```

Trong tình huống phức tạp, cách rõ nhất là tạo mảng `Object[]` chứa đúng số lượng/thứ tự formal parameters:

```java
Object[] supplied = {new String[]{"a", "b"}};
Object output = join.invoke(null, supplied);
```

Nếu method đích có hai tham số, trong đó tham số cuối là varargs, hãy truyền **hai phần tử** cho mảng đối số Reflection; phần tử thứ hai là mảng đã được đóng gói đúng kiểu.

## 11. Kết hợp boxing/unboxing có giới hạn quan trọng

### Không coi tất cả `Number` là có thể unbox thành mọi primitive

Dù `Integer` và `Long` cùng extends `Number`, Reflection chỉ dùng các wrapper primitive phù hợp cho unboxing. Một đối tượng `BigDecimal` **không** tự chuyển sang `double` theo `doubleValue()` chỉ vì nó extends `Number`.

```java
// Minh họa; không phải chương trình độc lập:
methodExpectingDouble.invoke(target, new java.math.BigDecimal("1.2"));
// IllegalArgumentException: không phải wrapper primitive hợp lệ để unbox
```

Nếu muốn nhận `Number` linh hoạt, phải tự xác định quy tắc chuyển đổi/độ chính xác và truyền một `Double` hoặc wrapper được cho phép tới method có formal `double`.

### Không có implicit narrowing dù giá trị “vừa”

```java
// Method đích có tham số byte:
methodExpectingByte.invoke(target, Integer.valueOf(5));
// IllegalArgumentException: int → byte bị cấm tự động dù 5 vừa byte.
```

Nếu có chính sách cho phép chuyển đổi thu hẹp, ứng dụng phải **chủ động kiểm tra miền giá trị**, ví dụ `value >= Byte.MIN_VALUE && value <= Byte.MAX_VALUE`, sau đó tạo `Byte.valueOf((byte) value)` trước khi invoke.

### Kiểu tham chiếu không được biến thành wrapper mới

```java
// Method đích khai báo Long, đối số là Integer:
methodExpectingLongObject.invoke(target, Integer.valueOf(8));
// IllegalArgumentException: Integer không assignable tới Long.
```

Khác với method đích khai báo `long`, trường hợp này **không** tự động thực hiện `Integer → int → long → Long`.

### Null và primitive

Nếu formal parameter là primitive, `null` không thể được unbox; lời gọi có thể ném `IllegalArgumentException`. Đối với reference parameter, `null` có thể được truyền qua, nhưng code đích vẫn có thể ném exception nếu tự dereference `null`.

## 12. Phân biệt lỗi tra cứu, lỗi chuyển đổi và lỗi quyền truy cập

| Hoạt động | Vấn đề | Kết quả tiêu biểu |
| --- | --- | --- |
| `getMethod("f", int.class)` khi chỉ có `f(long)` | Tìm sai signature; chưa gọi method | `NoSuchMethodException` |
| `getDeclaredField("missing")` | Không có field khai báo | `NoSuchFieldException` |
| `getInt` trên field `short` | Widening hợp lệ | Trả `int` |
| `getByte` trên field `short` | Narrowing bị cấm | `IllegalArgumentException` |
| `setInt` trên field `long` | Widening hợp lệ | Ghi giá trị |
| `setLong` trên field `int` | Narrowing bị cấm | `IllegalArgumentException` |
| `invoke` với `Long` cho tham số `int` | Narrowing bị cấm | `IllegalArgumentException` |
| `invoke` đúng đối số nhưng target ném lỗi | Lỗi thực thi business method | `InvocationTargetException` bọc cause |
| `newInstance` sai kiểu đối số | Không chuyển được theo quy tắc | `IllegalArgumentException` |
| Truy cập member không được phép | Access/JPMS | `IllegalAccessException` hoặc `InaccessibleObjectException` ở thao tác mở quyền |
| Receiver sai class hoặc `null` cho instance member | Truy cập sai đối tượng | `IllegalArgumentException` hoặc `NullPointerException` tùy API |

**Nên tách hai bước xử lý lỗi:**

1. **Tra cứu và kiểm tra metadata**: xác nhận field/method/constructor được chọn đúng, receiver đúng, access hợp lệ, kiểu formal và đối số có thể chuyển đổi.
2. **Đọc/ghi/gọi/tạo instance**: bắt lỗi Reflection theo API, đồng thời phân biệt exception do **code được gọi** phát sinh.

Không nên dựa vào việc catch `Exception` chung rồi suy đoán lỗi chuyển đổi khi thực tế lỗi đến từ quyền truy cập hoặc logic nghiệp vụ.

## 13. Tiền kiểm kiểu khi xử lý danh sách field/method

Một thư viện mapping hoặc batch runner không nên thử `invoke` với từng giá trị rồi chờ vỡ tại mục cuối. Có thể làm preflight:

1. Với mỗi member đã chọn, lấy **kiểu đích thực tế** qua `Field.getType()`, `Method.getParameterTypes()` hoặc `Constructor.getParameterTypes()`.
2. Đối với **kiểu đích tham chiếu**, xác nhận giá trị `null` hoặc `targetType.isInstance(value)`.
3. Đối với **kiểu đích primitive**, xác định wrapper nguồn (nếu giá trị khác `null`), unbox về primitive tương ứng rồi kiểm tra bảng widening ở mục 1.
4. Với typed `Field.getX/setX`, so sánh **kiểu primitive khai báo** với đúng chiều bảng ở mục 4/6.
5. Kiểm tra số lượng đối số, varargs array đã đóng gói, receiver, static/instance và quyền truy cập.
6. Chỉ khi tất cả entry đạt thì lập kế hoạch thực thi, đồng thời vẫn xử lý lỗi phát sinh khi thực thi.

Có thể tự cài một hàm `canWidenPrimitive(source, target)` dựa trên bảng ở mục 1; **đừng** dùng `target.isAssignableFrom(source)` cho primitive widening vì `isAssignableFrom` là quan hệ runtime type assignability, không phải bảng primitive widening.

Ví dụ:

```java
int.class.isAssignableFrom(short.class); // false: không kiểm tra widening
Number.class.isAssignableFrom(Integer.class); // true: subtype tham chiếu
```

Các mapper cần hỗ trợ chuyển từ text, enum, date/time hoặc numeric custom type phải định nghĩa chính sách chuyển đổi **ngoài** quy tắc Reflection và thông báo khi giá trị không thể chuyển đổi an toàn.

## 14. Checklist và câu hỏi tự kiểm tra

**Checklist:**

- Đã biết **kiểu field/formal parameter chính xác** và hướng chuyển đổi cần kiểm tra?
- Nếu là primitive, kiểu nguồn có nằm trong bảng widening của kiểu đích?
- Nếu là reference, giá trị có assignable hoặc `null` không? Có đang nhầm `Integer` với `Long`?
- Đã phân biệt `Field.get` (boxing) với `Field.getX` (widening) và chiều ngược `Field.setX`?
- `getMethod`/`getConstructor` có được tra cứu bằng signature khai báo chính xác?
- Varargs đã được đóng gói thành **một tham số mảng** chưa?
- Có xử lý access control, receiver, final/static và exception từ code đích không?

**Tự kiểm tra:**

1. Field khai báo `char` có đọc được bằng `getShort`, `getInt` và `getDouble` không? Vì sao?
2. Field khai báo `int` có nhận `Long.valueOf(3)` qua `Field.set` không, dù số 3 rất nhỏ?
3. Với constructor `Widget(double)`, truyền `Integer.valueOf(5)` cho `Constructor.newInstance` có hợp lệ không? Tra cứu bằng `getConstructor(int.class)` có tìm thấy constructor ấy không?
4. `Method.invoke` gọi method trả `long` thì trả về wrapper gì? Method trả `void` thì sao?
5. Vì sao `Field.get` một field `short` trả `Short` trong khi `Field.getInt` trên field đó trả `int`?
6. Một method có chữ ký `f(Long)` có nhận `Integer` tự động không? Nó khác `f(long)` ở đâu?
7. Với `String... args`, vì sao `Method.invoke(receiver, "a", "b")` có thể sai?
8. Trường hợp nào Reflection trả `InvocationTargetException` thay vì `IllegalArgumentException` khi gọi method?

### Nguồn tham khảo chính thức

- [Java SE 17: `Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): getter/setter, widening và boxing.
- [Java SE 17: `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke`, chuyển đổi đối số và return value.
- [Java SE 17: `Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): `newInstance`, tham số và exception.
- [Java Language Specification 17 §5.1–5.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html): widening, boxing, unboxing và method invocation conversions.
