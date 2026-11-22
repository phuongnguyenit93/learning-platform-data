# Điều kiện widening và lỗi sai kiểu khi gán phần tử mảng bằng Java Reflection

Trong Java Reflection, lớp `java.lang.reflect.Array` cho phép tạo mảng và đọc, ghi phần tử khi chỉ biết kiểu tại runtime. Điểm dễ nhầm là lời gọi `Array.set(array, index, value)` **không cho phép mọi phép chuyển đổi số**, cũng không hành xử hoàn toàn giống toán tử gán trực tiếp cho mảng tham chiếu. Một giá trị có thể được ghi vào phần tử khi **kiểu runtime của mảng, loại giá trị và các quy tắc chuyển đổi được phép** tương thích với nhau.

Ví dụ:

```java
int[] values = new int[2];
Array.set(values, 0, Byte.valueOf((byte) 7)); // Được: byte -> int
Array.set(values, 1, Character.valueOf('A')); // Được: char -> int (65)
Array.set(values, 0, Long.valueOf(7));        // IllegalArgumentException
```

Đoạn trên minh họa API khi đã `import java.lang.reflect.Array;`. Ở lời gọi thứ ba, giá trị `long` dù bằng `7` vẫn không được tự động thu hẹp (*narrowing*) thành `int`. Các kiểm tra này dựa trên **kiểu**, không dựa vào việc số hiện tại có vừa giới hạn biểu diễn của kiểu đích hay không.

Bài học nằm trong nhóm **Mảng động**; trọng tâm là `Array.set`, `Array.setXxx`, widening primitive, mảng tham chiếu, exception và các bước kiểm tra trước khi gán bằng Reflection.

## 1. Mảng động và kiểu phần tử được xác định ở runtime

Một mảng Java luôn có **kiểu thành phần (component type)** và chiều dài cố định sau khi tạo. «Mảng động» trong ngữ cảnh Reflection nghĩa là **chọn loại mảng/tạo mảng bằng metadata `Class<?>` lúc runtime**, không phải mảng tự đổi kích thước giống `ArrayList`.

```java
Class<?> componentType = int.class;
Object array = Array.newInstance(componentType, 3);

System.out.println(array.getClass().getTypeName());        // int[]
System.out.println(array.getClass().getComponentType());   // int
System.out.println(Array.getLength(array));                // 3
```

Đoạn trên cần `import java.lang.reflect.Array;`. `Array.newInstance(componentType, length)` trả về `Object` ở mặt API, nhưng đối tượng thực vẫn là **một mảng JVM đúng kiểu**, chẳng hạn `int[]`, `String[]` hoặc `Number[]`.

Điều quyết định khi gọi `Array.set` là **kiểu phần tử của đối tượng mảng thực tế**, không đơn thuần là kiểu của biến đang giữ tham chiếu:

```java
Number[] numbers = new Integer[1];
// Kiểu khai báo của biến: Number[]
// Kiểu runtime của mảng: Integer[]
```

Khi ghi, JVM vẫn bảo vệ kiểu runtime `Integer[]`. Giá trị `Long` không thể được cất vào phần tử của `Integer[]` chỉ vì biến tham chiếu có kiểu `Number[]`.

## 2. API ghi phần tử: `Array.set` và các phương thức chuyên biệt

`java.lang.reflect.Array` có các API:

| API | Giá trị truyền vào | Vai trò |
| --- | --- | --- |
| `Array.set(Object array, int index, Object value)` | `Object`, gồm đối tượng wrapper | Ghi vào mảng tham chiếu hoặc unbox/widen hợp lệ vào mảng primitive |
| `Array.setBoolean(array, index, boolean)` | `boolean` | Ghi primitive boolean |
| `Array.setByte(array, index, byte)` | `byte` | Ghi byte hoặc widening sang loại primitive tương thích |
| `Array.setChar(array, index, char)` | `char` | Ghi char hoặc widening tương thích |
| `Array.setShort(array, index, short)` | `short` | Ghi short hoặc widening tương thích |
| `Array.setInt(array, index, int)` | `int` | Ghi int hoặc widening tương thích |
| `Array.setLong(array, index, long)` | `long` | Ghi long hoặc widening tương thích |
| `Array.setFloat(array, index, float)` | `float` | Ghi float hoặc widening tương thích |
| `Array.setDouble(array, index, double)` | `double` | Ghi double |

`Array.setXxx` hỗ trợ giá trị primitive và chỉ hoạt động với **mảng primitive** có kiểu phần tử thích hợp. Nó không có mục đích tự boxing để ghi vào `Object[]`/`Number[]`. Muốn ghi wrapper vào mảng tham chiếu, dùng `Array.set` với đối tượng tương ứng.

Với `Array.set`, primitive truyền ở mã Java sẽ **được boxing trước** vì tham số cuối của API có kiểu `Object`:

```java
int[] ints = new int[1];

Array.set(ints, 0, 5);                // Compiler boxing 5 thành Integer
Array.set(ints, 0, Integer.valueOf(5)); // Tương đương kiểu đối số
Array.setInt(ints, 0, 5);             // API ghi primitive trực tiếp
```

Khi nhận `Integer` để ghi vào `int[]`, Reflection unbox thành `int`. Đối với mảng đích primitive khác, có thể có thêm bước **widening primitive**.

## 3. Quy tắc widening primitive khi ghi mảng

*Widening primitive conversion* là chuyển từ một primitive sang primitive khác theo quy tắc Java cho phép mà không cần phép ép tường minh. Chẳng hạn `byte -> int`, `int -> long`, `float -> double`. Ngược lại, `long -> int`, `double -> float` hoặc `short -> byte` là *narrowing* và không được Reflection tự thực hiện khi ghi.

Bảng dưới mô tả **nguồn primitive** và các **kiểu phần tử mảng đích được phép** khi ghi bằng phương thức `Array.setXxx` thích hợp hoặc khi `Array.set` nhận đúng wrapper nguồn:

| Kiểu nguồn | Kiểu đích hợp lệ (gồm chính kiểu nguồn) |
| --- | --- |
| `boolean` | `boolean` |
| `byte` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `short` | `short`, `int`, `long`, `float`, `double` |
| `char` | `char`, `int`, `long`, `float`, `double` |
| `int` | `int`, `long`, `float`, `double` |
| `long` | `long`, `float`, `double` |
| `float` | `float`, `double` |
| `double` | `double` |

Một số hệ quả quan trọng:

- `byte -> char` **không** là widening primitive. `short -> char` và `char -> short` cũng không được phép tự động.
- `boolean` không tự chuyển sang số và số không tự chuyển sang `boolean`.
- `Integer -> long[]` hợp lệ với `Array.set`: unbox `Integer` thành `int`, rồi widening `int -> long`.
- `Character -> int[]` hợp lệ vì `char -> int`, nên ký tự `'A'` trở thành số `65`.
- `Long -> int[]` **không** hợp lệ, dù giá trị `Long.valueOf(7)` có thể biểu diễn bằng `int`.
- Không có phép chuyển đổi wrapper-sang-wrapper tự động: `Integer` không tự biến thành đối tượng `Long` để cất vào `Long[]`.

**Widening không luôn bảo toàn chính xác tất cả chữ số.** Chuyển `long -> float` hoặc `int -> float` có thể mất độ chính xác số học do giới hạn độ chính xác của số thực; quy tắc widening vẫn cho phép chuyển đổi. Vì vậy không nên đồng nhất «được ghi» với «không thể mất precision».

## 4. `Array.set` trên mảng primitive thực hiện hai bước chuyển đổi

Với API tổng quát `Array.set(array, index, value)`, giá trị truyền vào có kiểu `Object`. Nếu mảng đích có kiểu phần tử primitive:

1. `value` phải là đối tượng của **một wrapper primitive tương ứng**, ví dụ `Byte`, `Character`, `Integer`, `Long`, `Float`, `Double`, `Boolean`, `Short`.
2. Reflection unbox wrapper thành primitive nguồn.
3. Nếu primitive nguồn cùng kiểu với component type hoặc có **widening primitive** tới component type, phần tử được cập nhật.
4. Nếu đòi hỏi narrowing, chuyển đổi không hợp lệ hoặc `value == null`, `Array.set` ném `IllegalArgumentException`.

Ví dụ:

```java
int[] ints = new int[2];

Array.set(ints, 0, Byte.valueOf((byte) 7));  // byte -> int
Array.set(ints, 1, Character.valueOf('A')); // char -> int
System.out.println(java.util.Arrays.toString(ints)); // [7, 65]
```

Ngược lại:

```java
Array.set(ints, 0, Long.valueOf(7L)); // IllegalArgumentException
Array.set(ints, 0, null);             // IllegalArgumentException
```

Số `7L` không được tự thu hẹp dù nằm trong miền giá trị `int`; Reflection không áp dụng conversion tùy ý dựa trên nội dung số. Cũng không thể unbox `null` để ghi vào primitive.

Nếu một ứng dụng muốn chuyển `long -> int` theo chính sách riêng (ví dụ chỉ cho phép giá trị nằm trong phạm vi `int`), ứng dụng phải **tự kiểm tra miền giá trị, ép kiểu có chủ đích và truyền một `Integer`/`int` hợp lệ**. Không để `Array.set` tự đoán chính sách thu hẹp.

## 5. `Array.setXxx` cũng cho phép widening thích hợp

Một suy luận sai là `Array.setInt` chỉ ghi được `int[]`. Theo hợp đồng của Reflection, nó cũng có thể ghi sang mảng có component type chấp nhận widening của `int`:

```java
long[] longs = new long[1];
double[] doubles = new double[1];

Array.setInt(longs, 0, 99);       // int -> long
Array.setFloat(doubles, 0, 2.5f); // float -> double

System.out.println(longs[0]);   // 99
System.out.println(doubles[0]); // 2.5
```

Trong khi đó:

```java
int[] ints = new int[1];
Array.setLong(ints, 0, 7L); // IllegalArgumentException
```

`long -> int` là narrowing, không hợp lệ với setter chuyên biệt. `Array.setDouble(floatArray, i, value)` cũng bị từ chối vì `double -> float` là narrowing.

Các hàm getter chuyên biệt như `Array.getInt(array, index)` có quy tắc chuyển đổi riêng khi **đọc**. Không nên suy ra quy tắc ghi chỉ từ tên hàm hoặc chỉ từ việc một cách đọc thành công. Ở bài này, ta quan tâm chính xác đến chiều **source value -> array component type** khi gán phần tử.

## 6. Mảng tham chiếu: cần tương thích kiểu runtime của phần tử

Nếu component type là **reference type**, `Array.set` không sử dụng widening primitive để tạo đối tượng reference mới. Giá trị phải:

- Là `null`; hoặc
- Là đối tượng có kiểu runtime tương thích với component type của mảng, theo quan hệ gán reference hợp lệ.

Ví dụ:

```java
Number[] values = new Number[3];

Array.set(values, 0, Integer.valueOf(1)); // Integer extends Number
Array.set(values, 1, Long.valueOf(2));    // Long extends Number
Array.set(values, 2, null);               // Mảng reference nhận null
```

`Integer` và `Long` đều là subtype của `Number` nên có thể đặt vào `Number[]`. Nhưng `Integer` không là subtype của `Long` và ngược lại:

```java
Long[] longValues = new Long[1];
Array.set(longValues, 0, Integer.valueOf(1)); // IllegalArgumentException
```

Không có chuyện `Integer -> int -> long -> Long` được Reflection tự thực hiện để ghi vào `Long[]`.

### Cẩn thận với covariance của mảng

Java cho phép:

```java
Number[] numbers = new Integer[1];
```

Mảng **thực** vẫn là `Integer[]`. Vì vậy:

```java
Array.set(numbers, 0, Integer.valueOf(10)); // Thành công
Array.set(numbers, 0, Long.valueOf(20));    // IllegalArgumentException
```

Dù biến tham chiếu mang kiểu `Number[]`, thành phần runtime là `Integer`. Lời gọi qua `Array.set` với giá trị không tương thích báo `IllegalArgumentException`.

Phép gán mảng **trực tiếp** lại báo exception khác:

```java
numbers[0] = Long.valueOf(20); // ArrayStoreException tại runtime
```

Đây là một phân biệt hữu ích:

| Đường ghi | Mảng thực | Giá trị sai kiểu | Lỗi điển hình |
| --- | --- | --- | --- |
| `Array.set(numbers, 0, Long.valueOf(20))` | `Integer[]` | `Long` | `IllegalArgumentException` |
| `numbers[0] = Long.valueOf(20)` | `Integer[]` | `Long` | `ArrayStoreException` |

Đừng gom hai exception thành một loại khi bắt lỗi và hiển thị chẩn đoán. Thao tác reflection và phép gán mảng bytecode bình thường có hợp đồng báo lỗi khác nhau.

## 7. Ví dụ Java 17+ hoàn chỉnh, chạy độc lập

Lưu toàn bộ mã dưới đây vào `ArrayWideningDemo.java`. Ví dụ có mảng được tạo động bằng `Array.newInstance`, widening hợp lệ, narrowing bị từ chối, mảng tham chiếu và lỗi truy cập ngoài chỉ số.

```java
import java.lang.reflect.Array;
import java.util.Arrays;

public class ArrayWideningDemo {
    public static void main(String[] args) {
        int[] ints = (int[]) Array.newInstance(int.class, 3);

        // Byte -> byte -> int (unboxing, widening).
        Array.set(ints, 0, Byte.valueOf((byte) 7));

        // Character -> char -> int. Ký tự 'A' có mã 65.
        Array.set(ints, 1, Character.valueOf('A'));

        // Ghi primitive int bằng setter chuyên biệt.
        Array.setInt(ints, 2, 42);
        System.out.println("int[]: " + Arrays.toString(ints));

        long[] longs = (long[]) Array.newInstance(long.class, 1);
        Array.setInt(longs, 0, 99);
        System.out.println("long[] from int: " + longs[0]);

        double[] doubles =
                (double[]) Array.newInstance(double.class, 1);
        Array.set(doubles, 0, Float.valueOf(2.5f));
        System.out.println("double[] from float: " + doubles[0]);

        // Narrowing long -> int không được tự động.
        try {
            Array.set(ints, 0, Long.valueOf(6L));
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "long -> int: IllegalArgumentException");
        }

        // Primitive không thể chứa null.
        try {
            Array.set(ints, 0, null);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "null -> int: IllegalArgumentException");
        }

        // short -> char không phải widening primitive.
        try {
            Array.set(new char[1], 0, Short.valueOf((short) 1));
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "short -> char: IllegalArgumentException");
        }

        // Kiểu khai báo Number[] không đổi kiểu mảng runtime Integer[].
        Number[] numbers = new Integer[1];
        Array.set(numbers, 0, Integer.valueOf(10));
        System.out.println("runtime array type: "
                + numbers.getClass().getTypeName());

        try {
            Array.set(numbers, 0, Long.valueOf(20));
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "Long -> Integer[] via Array.set: IllegalArgumentException");
        }

        try {
            numbers[0] = Long.valueOf(20);
        } catch (ArrayStoreException e) {
            System.out.println(
                    "Long -> Integer[] direct: ArrayStoreException");
        }

        Object[] objects = new Object[1];
        Array.set(objects, 0, Integer.valueOf(11));
        System.out.println("Object[]: "
                + objects[0].getClass().getSimpleName());

        try {
            Array.set(ints, 8, Integer.valueOf(1));
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println(
                    "out-of-bounds: ArrayIndexOutOfBoundsException");
        }

        // API get tổng quát boxing giá trị primitive thành Integer.
        System.out.println("Array.get(int[]): "
                + Array.get(ints, 0).getClass().getSimpleName());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac ArrayWideningDemo.java
java ArrayWideningDemo
```

Kết quả:

```text
int[]: [7, 65, 42]
long[] from int: 99
double[] from float: 2.5
long -> int: IllegalArgumentException
null -> int: IllegalArgumentException
short -> char: IllegalArgumentException
runtime array type: java.lang.Integer[]
Long -> Integer[] via Array.set: IllegalArgumentException
Long -> Integer[] direct: ArrayStoreException
Object[]: Integer
out-of-bounds: ArrayIndexOutOfBoundsException
Array.get(int[]): Integer
```

Ba nhóm thông điệp đáng nhớ:

1. `byte -> int`, `char -> int`, `int -> long` và `float -> double` đều hợp lệ. Reflection áp dụng đúng đường widening primitive.
2. `long -> int`, `short -> char` và `null -> int` thất bại bằng `IllegalArgumentException` vì loại chuyển đổi/giá trị không hợp lệ, dù chỉ số mảng vẫn đúng.
3. Khi ghi `Long` vào mảng runtime `Integer[]`, `Array.set` báo `IllegalArgumentException` còn gán trực tiếp qua biến `Number[]` báo `ArrayStoreException`. Cả hai đều bảo vệ kiểu phần tử runtime.

Cuối ví dụ, `Array.get(ints, 0)` có kiểu trả về `Object` nên primitive `int` được boxing thành đối tượng `Integer`. Điều này **không biến `int[]` thành `Integer[]`**.

## 8. Kiểm tra trước khi gán bằng Reflection

Nếu viết framework nhận danh sách đối tượng từ nguồn dữ liệu không biết trước, không nên chỉ nhìn kiểu của đối số và rồi gọi `Array.set` một cách ngẫu nhiên. Trình tự tốt hơn:

1. **Xác nhận đối tượng đích là mảng:** `array != null` và `array.getClass().isArray()`.
2. **Xác định kiểu phần tử runtime:** `Class<?> component = array.getClass().getComponentType()`.
3. **Xác định chỉ số:** `0 <= index < Array.getLength(array)`.
4. **Nếu component là primitive:** `null` bị từ chối; lấy wrapper thực tế của `value`, ánh xạ sang primitive nguồn và kiểm tra widening primitive có hợp lệ.
5. **Nếu component là reference:** `null` được chấp nhận; các đối tượng khác cần `component.isInstance(value)`.
6. **Gọi `Array.set` một lần** sau khi chính sách đã rõ; vẫn xử lý exception đúng loại vì dữ liệu/đích có thể thay đổi trong môi trường concurrent.

Một helper đơn giản cho mảng **reference** có thể viết:

```java
import java.lang.reflect.Array;

public final class ReferenceArrayGuard {
    public static void set(Object array, int index, Object value) {
        if (array == null || !array.getClass().isArray()) {
            throw new IllegalArgumentException("Expected array");
        }
        Class<?> component = array.getClass().getComponentType();
        if (component.isPrimitive()) {
            throw new IllegalArgumentException(
                    "This helper only supports reference arrays");
        }
        if (index < 0 || index >= Array.getLength(array)) {
            throw new IndexOutOfBoundsException("index=" + index);
        }
        if (value != null && !component.isInstance(value)) {
            throw new IllegalArgumentException(
                    value.getClass().getTypeName()
                    + " is not an instance of "
                    + component.getTypeName());
        }
        Array.set(array, index, value);
    }
}
```

Đây là class tiện ích **không chứa `main`**; có thể biên dịch độc lập, nhưng chỉ xử lý mảng reference theo mục tiêu đã ghi. Đối với mảng primitive, helper kiểu chung cần một **bảng widening** giống phần 3. Không được tự suy ra widening từ `component.isAssignableFrom(value.getClass())`: `Class.isAssignableFrom` kiểm tra quan hệ kiểu, **không** biểu diễn boxing/unboxing hay widening primitive.

Ví dụ `int.class.isAssignableFrom(Byte.class)` là `false`, nhưng `Array.set(new int[1], 0, Byte.valueOf((byte) 1))` vẫn thành công.

## 9. Các lỗi cần phân biệt khi thao tác mảng

| Exception | Tình huống thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException` | `Array.set` nhận giá trị không tương thích với component type; hoặc đối tượng truyền vào không phải array | Kiểm tra component type, wrapper nguồn và bảng widening |
| `NullPointerException` | Đối tượng `array` của API bằng `null` | Xác minh array trước lời gọi; khác với giá trị phần tử `null` |
| `ArrayIndexOutOfBoundsException` | Chỉ số âm hoặc lớn hơn/bằng độ dài mảng | Kiểm tra `Array.getLength(array)` và miền chỉ số |
| `ArrayStoreException` | Gán trực tiếp qua biến mảng tham chiếu nhưng phần tử không tương thích với kiểu mảng runtime | Xác định kiểu mảng thực tế, đặc biệt với array covariance |

Ví dụ đối tượng mảng hoàn toàn hợp lệ mà chỉ số sai:

```java
int[] data = new int[2];
Array.set(data, 2, Integer.valueOf(10)); // ArrayIndexOutOfBoundsException
```

Đây là lỗi giới hạn chỉ số, không phải lỗi widening. Mặt khác:

```java
int[] data = new int[2];
Array.set(data, 0, Long.valueOf(10L)); // IllegalArgumentException
```

Chỉ số 0 hợp lệ, nhưng `Long -> int` đòi narrowing nên lỗi nằm ở kiểu giá trị.

**Không nên bắt mọi `RuntimeException` rồi gọi chung là «sai kiểu».** Việc phân loại đúng sẽ giúp báo lỗi có thể sửa được trong framework nhập dữ liệu, mapper, serializer hoặc plugin reflection.

## 10. Các trường hợp dễ suy luận nhầm

### 10.1. Giá trị nhỏ không làm narrowing trở thành widening

`Long.valueOf(1L)` vẫn mang kiểu `Long`. Gán qua `Array.set` vào `int[]` không được, dù `1L` nằm trọn trong miền `int`. Nếu cố ý cho phép narrowing có kiểm tra phạm vi:

```java
long raw = 1L;
int converted = Math.toIntExact(raw);
Array.setInt(new int[1], 0, converted);
```

`Math.toIntExact` ném `ArithmeticException` nếu giá trị `long` nằm ngoài miền `int`. Đây là **chính sách chuyển đổi tường minh của ứng dụng**, không phải quy tắc mặc định của `Array.set`.

### 10.2. Wrapper khác không có nghĩa là primitive compatible

`Array.set(new Long[1], 0, Integer.valueOf(1))` thất bại. Mặc dù `int -> long` widening được phép với **mảng primitive `long[]`**, mục tiêu `Long[]` là mảng **đối tượng**, cần một instance `Long` hoặc `null`. Muốn ghi thành `Long`, tự tạo đối tượng:

```java
Long[] boxed = new Long[1];
Array.set(boxed, 0, Long.valueOf(1L));
```

### 10.3. Không ép kiểu cho `boolean`

Không có widening giữa `boolean` và các kiểu số. `Array.set(new boolean[1], 0, Boolean.TRUE)` hợp lệ; `Array.set(new boolean[1], 0, Integer.valueOf(1))` không hợp lệ. Tương tự `Array.set(new int[1], 0, Boolean.TRUE)` không hợp lệ.

### 10.4. Mảng nhiều chiều có component là một mảng

Với:

```java
int[][] matrix = new int[2][3];
```

Kiểu thành phần của **mảng ngoài** là `int[]`, tức một **reference type**. `Array.set(matrix, 0, new int[] {1, 2, 3})` hợp lệ, còn `Array.set(matrix, 0, Integer.valueOf(1))` không hợp lệ vì phần tử mảng ngoài phải là `int[]`, không phải một số nguyên. Nếu muốn ghi một ô số, lấy mảng con hoặc dùng hai bước:

```java
Object row = Array.get(matrix, 0);
Array.setInt(row, 1, 9);
```

Lúc ghi `row[1]`, component type của **mảng con** mới là `int`. Luôn kiểm tra đúng cấp mảng mà bạn đang gán.

### 10.5. Widening có thể mất độ chính xác

`long -> float` được cho phép nhưng `float` không thể biểu diễn chính xác mọi số nguyên 64-bit. Widening ở đây có nghĩa conversion được ngôn ngữ chấp nhận mà không cần cast tường minh; nó **không bảo đảm giữ nguyên toàn bộ giá trị số học**. Nếu hệ thống cần độ chính xác tuyệt đối, phải đặt thêm quy tắc kiểm tra hoặc dùng kiểu dữ liệu thích hợp.

## 11. Quy trình chẩn đoán khi `Array.set` thất bại

Khi thấy exception trong reflection-driven array mapper, hãy kiểm tra theo thứ tự:

1. **Array thật:** `array.getClass().getTypeName()` là gì? Có đúng là array không? Có phải `Integer[]` dù biến khai báo `Number[]`?
2. **Component thật:** `getComponentType()` là `int.class` hay `Integer.class`? Hai tình huống có quy tắc ghi khác nhau.
3. **Index:** có nằm trong `[0, Array.getLength(array))`?
4. **Value:** có phải `null`? Nếu không, `value.getClass().getTypeName()` là gì?
5. **Primitive target:** wrapper nguồn tương ứng primitive nào? Có đường widening trong bảng phần 3 không? Có lỡ yêu cầu narrowing không?
6. **Reference target:** `component.isInstance(value)` có đúng không? Có gặp array covariance không?
7. **Đường gọi nào:** đang dùng `Array.set`, setter chuyên biệt hay phép gán mảng Java trực tiếp? Exception báo ra tương ứng có thể khác.
8. **Chuyển đổi có chủ đích:** nếu nghiệp vụ muốn parse chuỗi, chuẩn hóa JSON number hoặc thu hẹp số có kiểm soát, làm bước đó **trước** `Array.set`, với chính sách lỗi rõ ràng.

Ví dụ ngắn giúp quan sát metadata:

```java
Object array = new int[2];
Object value = Long.valueOf(7L);
Class<?> component = array.getClass().getComponentType();

System.out.println("array type: "
        + array.getClass().getTypeName());
System.out.println("component: "
        + component.getTypeName());
System.out.println("value type: "
        + value.getClass().getTypeName());
```

Đầu ra:

```text
array type: int[]
component: int
value type: java.lang.Long
```

Từ đây suy ra cần `long -> int`, không được Reflection cho phép; phải sửa giá trị/kiểu mảng hoặc áp dụng chuyển đổi tường minh có kiểm tra.

## 12. Tự kiểm tra nhanh

**Câu 1.** `Array.set(new long[1], 0, Integer.valueOf(10))` có hợp lệ không?  
Có. `Integer` được unbox thành `int`, sau đó widening thành `long`.

**Câu 2.** `Array.set(new int[1], 0, Long.valueOf(10))` có hợp lệ không?  
Không. `long -> int` là narrowing; `Array.set` ném `IllegalArgumentException`.

**Câu 3.** `Array.set(new char[1], 0, Short.valueOf((short) 65))` có hợp lệ không?  
Không. `short -> char` không phải widening primitive dù số 65 tương ứng ký tự `'A'`.

**Câu 4.** `Array.set(new Number[1], 0, Integer.valueOf(1))` có hợp lệ không?  
Có. `Integer` là subtype của `Number` nên tương thích với component type reference `Number`.

**Câu 5.** Với `Number[] x = new Integer[1]`, `Array.set(x, 0, Long.valueOf(1))` ném gì?  
`IllegalArgumentException`, vì đối tượng mảng thực có component type `Integer`. Nếu thay bằng `x[0] = Long.valueOf(1)`, JVM gán mảng trực tiếp có thể ném `ArrayStoreException`.

**Câu 6.** Tại sao `Array.set(new Long[1], 0, Integer.valueOf(1))` không tương đương với `Array.set(new long[1], 0, Integer.valueOf(1))`?  
Vì `Long[]` chứa **đối tượng `Long`** và cần reference compatibility; `long[]` chứa **primitive `long`** và cho phép unboxing `Integer` rồi widening `int -> long`.

## Ghi nhớ

- Với **mảng primitive**, `Array.set` nhận wrapper rồi **unbox và widening primitive** nếu đường chuyển đổi hợp lệ. Không tự narrowing và không nhận `null`.
- Với **mảng tham chiếu**, `Array.set` yêu cầu giá trị là `null` hoặc instance tương thích với **component type runtime**; không tự biến wrapper này thành wrapper khác.
- `Array.setXxx` có thể ghi sang mảng primitive rộng hơn theo bảng widening, không chỉ mảng cùng kiểu với `Xxx`.
- **Sai kiểu trong `Array.set`** thường là `IllegalArgumentException`; gán trực tiếp vào mảng tham chiếu sai kiểu có thể là `ArrayStoreException`.
- Luôn kiểm tra riêng **đối tượng mảng, component type, index và value** để phân biệt lỗi kiểu với lỗi truy cập ngoài phạm vi.

Nắm vững điều kiện **unboxing → widening primitive** và **reference assignability theo kiểu mảng thực** giúp ghi phần tử an toàn và chẩn đoán chính xác các lỗi khi sử dụng Java Reflection với mảng động.
