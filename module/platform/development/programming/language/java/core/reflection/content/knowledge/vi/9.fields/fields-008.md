# Field.set với kiểu tham chiếu hoặc primitive trong Java Reflection

## 1. Đặt vấn đề và hợp đồng của Field.set

`java.lang.reflect.Field` mô tả một field **cụ thể** được khai báo trong class/interface. `Field.set(Object obj, Object value)` đặt giá trị mới cho field đó nếu quyền truy cập, quyền ghi, đối tượng đích và kiểu dữ liệu đều phù hợp. Cùng một API áp dụng cho field **kiểu tham chiếu** (ví dụ `String`, `Number`, `Integer`, `List<?>`, mảng) và field **primitive** (`boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`), nhưng các quy tắc kiểm tra `value` không giống nhau.

Khi viết công cụ mapping, serializer hoặc binder, cần trả lời bốn câu hỏi độc lập:

1. Field có kiểu gì? `field.getType()` trả về kiểu đã khai báo; `field.getType().isPrimitive()` phân biệt nhánh primitive với reference.
2. `obj` trỏ đến đối tượng hợp lệ không? Instance field yêu cầu object của class khai báo (hoặc subtype); với static field `obj` bị bỏ qua, có thể là `null`.
3. Field có được phép ghi không? `getDeclaredField` tìm thấy field private nhưng chưa chắc truy cập được. `trySetAccessible()` có thể thất bại do module; field `final` còn có giới hạn write access.
4. Giá trị truyền vào có tương thích với **kiểu của field** không? Với reference, đó là quan hệ assignability của object. Với primitive, đó là **unboxing** wrapper rồi identity/widening primitive conversion.

`Field.set` không parse số từ chuỗi, không ép kiểu tùy ý, không tự tạo object, không bảo đảm an toàn generic và không bỏ qua giới hạn của Java Platform Module System.

Các chữ ký API liên quan:

~~~java
// Chữ ký API minh họa; không phải chương trình biên dịch độc lập.
public void set(Object obj, Object value)
        throws IllegalArgumentException, IllegalAccessException;
public void setInt(Object obj, int i)
        throws IllegalArgumentException, IllegalAccessException;
~~~

Khi viết `field.set(obj, 42)`, compiler boxing giá trị literal `42` thành `Integer` để truyền qua tham số `Object`. Nếu field thực là `int`, Reflection unboxing `Integer` thành `int` trước khi ghi. Không nhầm boxing tại chỗ gọi với unboxing trong implementation của `Field.set`.

## 2. Quy tắc cho field kiểu tham chiếu

Field tham chiếu có kiểu `T` nhận `null` hoặc một object có thể gán cho `T` theo kiểu runtime. Những giá trị không tương thích khiến `Field.set` ném `IllegalArgumentException`, dù có thể chuyển đổi được qua logic do ứng dụng tự viết.

| Field khai báo | Value đưa vào `set` | Kết quả |
| --- | --- | --- |
| `String name` | `"Lan"` | Thành công vì đúng kiểu. |
| `CharSequence text` | `new StringBuilder("hi")` | Thành công vì implements `CharSequence`. |
| `Number amount` | `Integer.valueOf(10)` | Thành công vì `Integer` là subtype của `Number`. |
| `Object payload` | `new int[] {1, 2}` | Thành công, mảng cũng là object. |
| `Integer boxed` | `Integer.valueOf(10)` | Thành công; `Integer` **không** phải primitive. |
| `Integer boxed` | `Long.valueOf(10)` | Thất bại; không tự ép wrapper `Long` sang `Integer`. |
| `String name` | `null` | Thành công nếu có quyền ghi field. |
| `String name` | `Integer.valueOf(10)` | Thất bại; API không gọi `toString()`. |

Kiểm tra thông thường trước khi ghi reference:

~~~java
// Đoạn chèn vào method đã có Field field, Object obj, Object value.
Class<?> type = field.getType();
if (!type.isPrimitive()) {
    if (value != null && !type.isInstance(value)) {
        throw new IllegalArgumentException("Reference type mismatch");
    }
    field.set(obj, value);
}
~~~

`Class.isAssignableFrom` cũng kiểm tra được quan hệ kiểu khi `value != null`, ví dụ `type.isAssignableFrom(value.getClass())`. Không gọi `value.getClass()` với `null`; cũng đừng dùng `isInstance` để suy ra phép chuyển từ wrapper sang primitive.

**Mảng được xếp vào nhóm reference.** Field `int[] values` có kiểu runtime là array class, tức `valuesField.getType().isPrimitive() == false`. Có thể gán một `int[]` khác hoặc `null`; không gán được `Integer[]` thay `int[]` bằng auto-boxing của từng phần tử. Muốn sửa một phần tử mảng hiện có là thao tác khác (`Array.setInt` hoặc code mảng thông thường), không phải `Field.set` trên field.

**Generic bị erasure:** Một field `List<String> names` vẫn có `getType() == List.class`. `Field.set` không kiểm tra parameter `String` của từng phần tử, do đó việc gán `List<Integer>` có thể qua được kiểm tra kiểu runtime dù sau này code đọc phần tử như `String` sẽ gặp `ClassCastException`. `getGenericType()` phản ánh khai báo tham số hóa để framework tự xây dựng kiểm tra bổ sung.

## 3. Quy tắc cho field primitive: unboxing và widening

`Field.set` nhận `Object value` nên muốn ghi field primitive thì đối tượng giá trị thông thường là một trong tám wrapper: `Boolean`, `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`. Reflection thử unboxing, sau đó dùng identity hoặc **widening primitive conversion** phù hợp với Java. API không thực hiện narrowing dù số thực tế có thể nằm gọn trong miền đích.

| Kiểu primitive sau khi unbox | Field đích cho phép |
| --- | --- |
| `boolean` (từ `Boolean`) | `boolean` |
| `byte` (từ `Byte`) | `byte`, `short`, `int`, `long`, `float`, `double` |
| `short` (từ `Short`) | `short`, `int`, `long`, `float`, `double` |
| `char` (từ `Character`) | `char`, `int`, `long`, `float`, `double` |
| `int` (từ `Integer`) | `int`, `long`, `float`, `double` |
| `long` (từ `Long`) | `long`, `float`, `double` |
| `float` (từ `Float`) | `float`, `double` |
| `double` (từ `Double`) | `double` |

Ví dụ có thể lý giải theo thứ tự:

- `int count` nhận `Integer.valueOf(7)`, `Byte.valueOf((byte) 7)`, `Character.valueOf('A')`: identity hoặc widening đến `int`.
- `long elapsed` nhận `Integer.valueOf(7)`: `Integer → int → long`.
- `double ratio` nhận `Float.valueOf(1.5f)`: `Float → float → double`.
- `int count` **không** nhận `Long.valueOf(7L)`: `long → int` là narrowing bị cấm.
- `short small` **không** nhận `Integer.valueOf(1)`: số `1` nhỏ vẫn không tạo quyền narrowing `int → short`.
- `boolean active` chỉ nhận `Boolean` phù hợp; giá trị `"true"` và `Integer.valueOf(1)` không được tự parse/coerce.
- Mọi field primitive đều **không** nhận `null`: không unbox được, `Field.set` ném `IllegalArgumentException`. Field reference nhận `null` nếu quyền ghi hợp lệ.

Widening là quy tắc **kiểu**, không phải cam kết không mất precision. Ví dụ `long → float` được phép nhưng số nguyên lớn có thể mất độ chính xác; công cụ nghiệp vụ có thể áp dụng quy tắc chặt hơn khi cần bảo toàn giá trị.

Một công cụ nhận dữ liệu người dùng từ `String`/JSON cần **converter tường minh** trước khi gọi `set`. Chẳng hạn parse `"42"` thành `Integer.valueOf(42)`, kiểm tra tràn số rồi mới ghi `int`; không truyền thẳng `"42"` vào `Field.set` mong API tự xử lý.

## 4. Các phương thức setXxx cho primitive

Ngoài `set(Object, Object)`, `Field` cung cấp `setBoolean`, `setByte`, `setShort`, `setChar`, `setInt`, `setLong`, `setFloat` và `setDouble`. Kiểu của tham số thứ hai trong các phương thức này là primitive tương ứng.

~~~java
// Mảnh minh họa các API, không phải source độc lập.
field.setBoolean(target, true);
field.setByte(target, (byte) 3);
field.setShort(target, (short) 3);
field.setChar(target, 'A');
field.setInt(target, 3);
field.setLong(target, 3L);
field.setFloat(target, 1.5f);
field.setDouble(target, 1.5);
~~~

Phải phân biệt **kiểu giá trị nguồn** và **kiểu field đích**. Ví dụ `setInt(target, 9)` trên field `long` thành công nhờ `int → long`, nhưng `setLong(target, 9L)` trên field `int` thất bại vì narrowing. Tương tự, `setDouble` không tự hạ xuống field `float`.

**Không dùng `setInt` để ghi field `Integer`:** Field `Integer` là reference, không phải primitive `int`. Trên Java 17/21, `setInt` vào field `Integer` ném `IllegalArgumentException`; dùng `set(target, Integer.valueOf(9))`. Trên field `Number`, cũng hãy dùng `set` với đối tượng `Integer` thay vì setter primitive. Chọn API dựa vào `field.getType()`:

~~~java
// Mảnh minh họa: field và target đã được xác định, kiểm tra quyền riêng.
Class<?> type = field.getType();
if (type == int.class) {
    field.setInt(target, 9);
} else if (type == Integer.class) {
    field.set(target, Integer.valueOf(9));
} else {
    // Kiểm tra / chuyển đổi theo kiểu khai báo thực tế.
}
~~~

`int.class` và `Integer.class` là hai đối tượng `Class` khác nhau; Reflection không coi chúng là một khai báo field.

## 5. Ví dụ Java 17+ hoàn chỉnh: các phép ghi hợp lệ và không hợp lệ

Tạo file `FieldSetTypesDemo.java`:

~~~java
import java.lang.reflect.Field;

public class FieldSetTypesDemo {
    static class Sample {
        private Number amount;
        private String label = "initial";
        private int pieces;
        private long ticks;
        private double price;
        private boolean available;
        private Integer boxed;
        private static int visits = 1;
    }

    @FunctionalInterface
    interface WriteAction {
        void run() throws IllegalAccessException;
    }

    static Field field(String name) throws NoSuchFieldException {
        Field result = Sample.class.getDeclaredField(name);
        if (!result.trySetAccessible()) {
            throw new IllegalStateException("Cannot access: " + name);
        }
        return result;
    }

    static void expectFailure(String label, WriteAction action) {
        try {
            action.run();
            System.out.println(label + " -> unexpected success");
        } catch (IllegalAccessException
                 | IllegalArgumentException
                 | NullPointerException error) {
            System.out.println(label + " -> "
                    + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Sample sample = new Sample();
        Field amount = field("amount");
        Field label = field("label");
        Field pieces = field("pieces");
        Field ticks = field("ticks");
        Field price = field("price");
        Field available = field("available");
        Field boxed = field("boxed");
        Field visits = field("visits");

        // Reference: object tương thích, hoặc null.
        amount.set(sample, Integer.valueOf(25));
        label.set(sample, null);
        boxed.set(sample, Integer.valueOf(12));

        // Primitive: unboxing rồi widening nếu cần.
        pieces.set(sample, Byte.valueOf((byte) 7));  // byte -> int
        ticks.setInt(sample, 9);                     // int -> long
        price.set(sample, Float.valueOf(1.5f));     // float -> double
        available.setBoolean(sample, true);

        // Static field: target là null.
        visits.setInt(null, 4);

        System.out.println("amount=" + sample.amount
                + " (" + sample.amount.getClass().getSimpleName() + ")");
        System.out.println("label=" + sample.label
                + ", pieces=" + sample.pieces
                + ", ticks=" + sample.ticks
                + ", price=" + sample.price
                + ", available=" + sample.available
                + ", boxed=" + sample.boxed
                + ", visits=" + Sample.visits);

        expectFailure("reference wrong type",
                () -> amount.set(sample, "not a Number"));
        expectFailure("primitive narrowing",
                () -> pieces.set(sample, Long.valueOf(10L)));
        expectFailure("primitive null",
                () -> pieces.set(sample, null));
        expectFailure("instance null target",
                () -> label.set(null, "new"));
        expectFailure("primitive setter on wrapper",
                () -> boxed.setInt(sample, 8));
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac -encoding UTF-8 FieldSetTypesDemo.java
java FieldSetTypesDemo
~~~

Đầu ra:

~~~text
amount=25 (Integer)
label=null, pieces=7, ticks=9, price=1.5, available=true, boxed=12, visits=4
reference wrong type -> IllegalArgumentException
primitive narrowing -> IllegalArgumentException
primitive null -> IllegalArgumentException
instance null target -> NullPointerException
primitive setter on wrapper -> IllegalArgumentException
~~~

Giải thích kết quả:

- `amount` khai báo `Number` nhưng giữ object `Integer`; đây là gán reference tương thích.
- `pieces` khai báo `int`, nhận `Byte` rồi unboxing thành `byte` và widening thành `int`.
- `ticks` khai báo `long`, nhận giá trị nguồn primitive `int` thông qua `setInt`.
- `price` khai báo `double`, nhận `Float` unboxing và widening.
- `boxed` là reference `Integer` nên `set` nhận `Integer` thành công; riêng `setInt` không áp dụng cho field reference.
- `set(sample, null)` là yêu cầu ghi **giá trị null**, còn `set(null, "new")` cung cấp **target null**. Điều thứ hai gây `NullPointerException` với instance field. Với static field, target null là hợp lệ.

`trySetAccessible()` trong ví dụ có thể bật vì mã và class model thuộc cùng unnamed module; chương trình không cần thư viện bên ngoài, không truy cập field nội bộ JDK. Ở ứng dụng module tách biệt, cần kiểm tra `exports`/`opens` và caller thực tế.

## 6. Field thuộc lớp cha, field bị che và kiểu đích

`Field` ràng buộc với **khai báo field gốc**, không tự chọn lại theo tên ở kiểu runtime của `obj`. Nếu hai tầng phân cấp cùng tên `id`, `Parent.class.getDeclaredField("id")` và `Child.class.getDeclaredField("id")` là hai đối tượng `Field` khác nhau, có thể mang **hai kiểu khác nhau**. Các luật type conversion áp dụng theo `field.getType()` của từng đối tượng `Field`.

Ví dụ độc lập, lưu `HiddenFieldDemo.java`:

~~~java
public class HiddenFieldDemo {
    static class Parent {
        int id = 1;
    }
    static class Child extends Parent {
        long id = 2;
    }

    public static void main(String[] args) throws Exception {
        Child child = new Child();
        Parent.class.getDeclaredField("id").setInt(child, 5);
        Child.class.getDeclaredField("id").setLong(child, 8L);

        System.out.println("Parent.id=" + ((Parent) child).id);
        System.out.println("Child.id=" + child.id);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 HiddenFieldDemo.java
java HiddenFieldDemo
~~~

Output:

~~~text
Parent.id=5
Child.id=8
~~~

Một công cụ tự duyệt superclass cần nêu rõ chính sách khi field trùng tên: chọn field gần class con nhất, chọn field của cha hoặc báo xung đột. Không nên dùng tên `id` một mình để quyết định kiểu giá trị mà không xác định `getDeclaringClass()`.

## 7. Quyền truy cập, final và lỗi runtime

Chọn value đúng kiểu **chưa đủ** để `Field.set` thành công.

| Lỗi hoặc điều kiện | Ý nghĩa thực tế |
| --- | --- |
| `NoSuchFieldException` lúc tra cứu | Sai tên hoặc tìm ở class không khai báo field đó; `getDeclaredField` không tự duyệt cha. |
| `trySetAccessible() == false` | Không thể bỏ qua access check, thường do module/package không mở. |
| `InaccessibleObjectException` khi `setAccessible(true)` | Deep reflection bị Java Platform Module System chặn. |
| `IllegalAccessException` ở `set` | Field không cho phép ghi hoặc access check không đạt. |
| `IllegalArgumentException` ở `set` | Sai kiểu value, không unboxing/widening được hoặc target không đúng loại. |
| `NullPointerException` ở `set` | Target là null cho instance field. |
| `ExceptionInInitializerError` | Khởi tạo class của static field bị lỗi. |

Các field **`static final`**, field `final` trong record và field `final` trong hidden class không có quyền ghi qua `Field.set`, ngay cả khi `setAccessible(true)` đã bật được quyền đọc. `private final` instance trong class thông thường có quy tắc đặc biệt ở Java 17: đôi khi Reflection cho phép ghi nếu mở quyền hợp lệ, nhưng sửa sau khi object được công bố có thể tạo hành vi khó đoán; không dùng cách này để cập nhật trạng thái nghiệp vụ.

Khi target khác `null`, nó phải là instance của class khai báo (hoặc subtype phù hợp). Khi static field được ghi, đối tượng target bị bỏ qua; thao tác có thể khiến class khai báo được khởi tạo. Vì vậy, không coi mọi lỗi tại `Field.set` là “ép kiểu thất bại”.

Quyền `setAccessible` không phải quyền cập nhật tất cả mọi field. Trong JPMS, mở private member ở module khác thường cần package được `opens` đến module của caller; `exports` cho public API không tự cấp deep reflection.

## 8. Thiết kế một bộ chuyển dữ liệu có chủ đích

Với mapper/binder, luồng xử lý nên dựa vào **kiểu đích**, không chỉ dựa vào kiểu nguồn:

~~~text
Field + target + rawValue
   |
   +-- Xác định declaringClass, static/instance, final và quyền truy cập
   |
   +-- Class<?> type = field.getType()
   |
   +-- type.isPrimitive() ?
          |
          +-- false: rawValue == null hoặc type.isInstance(rawValue)?
          |             đúng -> field.set(target, rawValue)
          |             sai  -> converter riêng hoặc lỗi
          |
          +-- true: rawValue là wrapper tương ứng?
                        unboxing -> identity/widening hợp lệ?
                           đúng -> field.set hoặc setXxx
                           sai  -> converter có range check hoặc lỗi
~~~

Các quyết định phải được ghi rõ ở tầng nghiệp vụ:

- Với primitive nhận input `null`: báo thiếu giá trị hay dùng default đã thống nhất; không âm thầm biến `null` thành `0` hay `false`.
- Với chuỗi số: dùng parser phù hợp, xử lý overflow và precision; `Field.set` không parse.
- Với generic: có thể cần kiểm tra `getGenericType()` và từng phần tử, vì runtime field check không đủ.
- Với field final hoặc object bất biến: ưu tiên constructor, factory, builder hoặc tạo object mới.
- Với conversion thu hẹp: chỉ cho phép khi chính sách nghiệp vụ yêu cầu và có kiểm tra overflow, không giả định `Field.set` hỗ trợ.
- Với lỗi: báo vị trí `declaringClass.fieldName`, kiểu đích và kiểu nguồn, tránh log giá trị nhạy cảm.
- Với hiệu năng: cache metadata khi có nhiều lần gán, nhưng chú ý vòng đời `ClassLoader` và quyền truy cập.

## 9. Các bẫy thường gặp

1. **Nhầm `Integer` với `int`:** `Integer.class.isPrimitive() == false`. `setInt` không phải lối tắt an toàn cho field `Integer`; dùng `set` với `Integer`.
2. **Nhầm boxing với chuyển đổi tùy ý:** `field.set(obj, 3)` có boxing ở Java caller, nhưng field `short` vẫn không nhận `Integer(3)` qua narrowing `int → short`.
3. **Nhầm `null` ở hai tham số:** `set(obj, null)` có thể ghi field reference; `set(null, value)` ném lỗi cho instance field.
4. **Nhầm String parse với primitive widening:** `"5"` không được Reflection biến thành `int 5`. Việc chuyển kiểu dữ liệu đầu vào thuộc về bộ chuyển của ứng dụng.
5. **Nhầm generic declaration với runtime check:** `List<String>` không bảo đảm giá trị đưa vào bằng `Field.set` chứa toàn String.
6. **Nhầm array primitive với primitive field:** `int[]` là reference; một mảng `Integer[]` không tự thay thế được `int[]`.
7. **Nhầm quyền truy cập với quyền ghi:** `trySetAccessible` thành công chưa chắc field final/modifier/module/target hợp lệ.
8. **Bỏ qua mất precision ở widening số:** một phép `long → float` hợp lệ theo kiểu vẫn có thể mất thông tin số học.

## 10. Bài tập và kiểm chứng

- Với field `int`, thử các wrapper `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`; lý giải từng kết quả từ bảng widening.
- Với field `long`, so sánh `setInt(target, 9)` và `setDouble(target, 9.0)`.
- Với field `Integer`, so sánh `set(target, Integer.valueOf(9))` và `setInt(target, 9)`.
- Với field `CharSequence`, thử `String`, `StringBuilder`, `null` và `Integer`.
- Với field `List<String>`, gán `List<Integer>` rồi đọc như String để thấy hậu quả của generic erasure.
- Với `static int counter`, gọi `setInt(null, 4)`; so sánh với `int counter` instance, target `null`.
- Mở rộng `HiddenFieldDemo` bằng `getDeclaringClass()` và chứng minh mỗi `Field` mang kiểu từ khai báo riêng.

## 11. Tài liệu tham khảo

- [Java SE 17 — Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html): `set`/`setXxx`, primitive unboxing/widening, target, exception, write access của field final.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `trySetAccessible` và quyền deep reflection dưới JPMS.
- [Java Language Specification `5.1.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2): các chuyển đổi widening primitive hợp lệ.

**Ghi nhớ:** Field tham chiếu theo **khả năng gán object/null**; field primitive theo **wrapper → unboxing → identity/widening**. Xác định rõ kiểu field và target, sau đó mới chọn `set` hoặc `setXxx` và xử lý quyền ghi.
