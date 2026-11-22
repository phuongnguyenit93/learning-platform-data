# Array.get, Array.set và các biến thể primitive trong Java Reflection

`java.lang.reflect.Array` là lớp tiện ích `final` cung cấp các **phương thức static** để tạo, đọc và ghi mảng Java khi kiểu thành phần chỉ được biết ở runtime. Hai thao tác trung tâm là `Array.get(array, index)` và `Array.set(array, index, value)`. Với mảng primitive, lớp còn cung cấp các getter/setter chuyên biệt như `getInt`, `getLong`, `getDouble`, `setInt`, `setLong`, `setDouble`.

Khác với thao tác chỉ số thông thường `ints[i]`, Reflection cho phép một biến kiểu `Object` đại diện cho `int[]`, `String[]` hay một kiểu mảng khác rồi truy cập phần tử động. Tuy nhiên, **không phải mọi phép chuyển đổi kiểu đều được phép**: API chỉ cho phép chuyển đổi đồng nhất (*identity*) hoặc mở rộng primitive (*widening*) khi đọc/ghi giá trị primitive; phép chuyển đổi thu hẹp (*narrowing*) sẽ bị từ chối.

Ví dụ:

```java
int[] scores = {10, 20};
Object array = scores;

Object boxed = Array.get(array, 0);  // Integer(10)
int exact = Array.getInt(array, 1);   // 20
long widened = Array.getLong(array, 1); // 20L

Array.set(array, 0, Byte.valueOf((byte) 7)); // byte -> int: hợp lệ
Array.setInt(array, 1, 99);                  // int -> int: hợp lệ
```

Đây là đoạn mã minh họa, cần `import java.lang.reflect.Array;`. Hai biến `boxed` và `exact` thể hiện sự khác nhau giữa **getter tổng quát trả `Object`** và **getter primitive trả kiểu nguyên thủy**. Chương trình độc lập có kết quả chính xác được trình bày ở mục 6.

## 1. “Mảng động” ở đây có nghĩa gì?

Mảng Java vẫn có **độ dài cố định sau khi được tạo**. “Mảng động” trong bối cảnh Reflection thường có nghĩa là **tạo mảng với kiểu phần tử hoặc số chiều xác định ở runtime**, không phải một cấu trúc có thể tự tăng dung lượng giống `ArrayList`.

Ví dụ nếu chương trình nhận `componentType` từ cấu hình:

```java
Class<?> componentType = int.class;
Object array = Array.newInstance(componentType, 3);
int length = Array.getLength(array); // 3
```

`Array.newInstance(int.class, 3)` tạo một đối tượng runtime thực sự là `int[]`, nhưng kiểu trả về tĩnh của phương thức là `Object`. `Array.getLength(array)` trả kích thước chiều ngoài của mảng được truyền vào. Để truy cập dữ liệu, có thể dùng `Array.get`/`Array.set` mà không cần cast thành `int[]`.

Khi đã biết tĩnh kiểu thành phần, cách thường dùng là `new int[3]` và `array[i]`: đơn giản, dễ đọc và thường phù hợp hơn. Reflection hữu ích cho mapper, serializer, factory, dependency injection, framework hoặc công cụ xử lý nhiều kiểu mảng chưa biết trước.

**Đối tượng truyền cho `Array.get/set` phải thật sự là mảng Java**, ví dụ `int[]`, `String[]`, `Object[]`, `int[][]`; một `List<Integer>` hay `ArrayList` không phải mảng và không thể dùng trực tiếp với các hàm này.

## 2. Array.get(array, index): đọc dưới dạng Object

Chữ ký:

```java
public static Object get(Object array, int index)
```

`Array.get` lấy phần tử tại vị trí `index`, không cần biết trước kiểu mảng ở compile time.

**Nếu mảng có component type primitive**, giá trị được **boxing** thành wrapper tương ứng:

| Kiểu phần tử mảng | Kiểu đối tượng nhận được khi `Array.get` |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

Nếu mảng có **component type tham chiếu**, `get` trả chính giá trị tham chiếu của phần tử (có thể là `null`); không chuyển đổi thành một kiểu primitive.

Ví dụ:

```java
Object a = new int[] {4};
Object v = Array.get(a, 0);
System.out.println(v.getClass().getSimpleName()); // Integer
```

Đoạn minh họa cần import `Array`, cho thấy `get` không giữ kiểu trả về `int` trên chữ ký Java: nó trả `Object` trỏ tới `Integer`.

Vì `Array.get` không nhận thêm một kiểu đích, **nó không tự chuyển `int` thành `long` rồi boxing thành `Long`**. Mảng `int[]` sẽ trả `Integer` khi dùng `get`. Muốn đọc trực tiếp dạng `long`, dùng `Array.getLong` (nếu kiểu phần tử mảng tương thích).

## 3. Các primitive getter và quy tắc widening khi đọc

Các getter chuyên biệt gồm `getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble`. Ví dụ:

```java
int x = Array.getInt(array, index);
double y = Array.getDouble(array, index);
```

Đối tượng `array` phải là **mảng primitive có kiểu thành phần tương thích với kiểu trả về của getter**. Quy tắc kiểm tra là:

> **Kiểu nguồn = component type của mảng. Kiểu đích = kiểu trả về của primitive getter.** Được phép nếu cùng kiểu hoặc có widening primitive conversion từ nguồn sang đích.

Bảng đầy đủ:

| Getter | Component type được đọc |
| --- | --- |
| `getBoolean` | `boolean` |
| `getByte` | `byte` |
| `getShort` | `byte`, `short` |
| `getChar` | `char` |
| `getInt` | `byte`, `short`, `char`, `int` |
| `getLong` | `byte`, `short`, `char`, `int`, `long` |
| `getFloat` | `byte`, `short`, `char`, `int`, `long`, `float` |
| `getDouble` | `byte`, `short`, `char`, `int`, `long`, `float`, `double` |

Các ví dụ hợp lệ:

- `Array.getInt(new byte[]{3}, 0)` trả `3` kiểu `int`.
- `Array.getLong(new int[]{7}, 0)` trả `7L` kiểu `long`.
- `Array.getDouble(new float[]{1.25f}, 0)` trả `1.25` kiểu `double`.
- `Array.getInt(new char[]{'A'}, 0)` trả `65`, là giá trị số UTF-16 code unit của `'A'`.

Các ví dụ bị từ chối bằng `IllegalArgumentException`:

- `Array.getInt(new long[]{7L}, 0)`: `long -> int` là narrowing.
- `Array.getInt(new double[]{7.0}, 0)`: `double -> int` là narrowing, **dù giá trị hiện tại bằng số nguyên**.
- `Array.getLong(new float[]{7.0f}, 0)`: `float -> long` không phải widening.
- `Array.getInt(new boolean[]{true}, 0)`: không có chuyển đổi boolean sang số.
- `Array.getInt(new Integer[]{7}, 0)`: **mảng wrapper `Integer[]` không phải `int[]`**; primitive getter không thực hiện unboxing trên reference array.

Mảng `char[]` không thể đọc bằng `getShort` vì `char -> short` không phải widening, mặc dù cả hai đều có 16 bit: `char` là unsigned 16-bit code unit, còn `short` là signed 16-bit integer.

### Widening có thể làm tròn số

`long -> double` và `int -> float` **hợp lệ** về quy tắc widening nhưng có thể **mất độ chính xác**. Ví dụ `Array.getDouble(new long[]{9_007_199_254_740_993L}, 0)` cho một số `double` đã làm tròn vì `2^53+1` không biểu diễn chính xác trong `double`.

Điều này không ném `IllegalArgumentException`, vì Java phân biệt **tính hợp lệ của conversion** với **việc mọi giá trị có được giữ chính xác hay không**. Không nên dùng `getDouble` với số nguyên lớn nếu yêu cầu giữ nguyên từng chữ số.

## 4. Array.set(array, index, value): ghi qua Object

Chữ ký:

```java
public static void set(Object array, int index, Object value)
```

`Array.set` quyết định tương thích theo **component type thực của mảng đích**:

**Với mảng reference** (`String[]`, `Number[]`, `Object[]`...), giá trị phải là `null` hoặc một reference **gán được cho component type**. Ví dụ:

```java
String[] strings = new String[2];
Array.set(strings, 0, "Java");
Array.set(strings, 1, null);
```

Ghi `Integer` vào `String[]` không hợp lệ. Trong môi trường Reflection, `Array.set` ném `IllegalArgumentException` nếu không thể chuyển giá trị cho component type.

**Với mảng primitive**, tham số `value` là `Object`, nên thường là wrapper. `Array.set` có thể **unbox wrapper** rồi widening primitive nếu cần, nhưng không narrowing:

```java
int[] integers = new int[2];
Array.set(integers, 0, Byte.valueOf((byte) 7)); // byte -> int: được
Array.set(integers, 1, Integer.valueOf(9));     // int -> int: được
```

Ngược lại:

- `Array.set(integers, 0, Long.valueOf(1))` thất bại vì `long -> int` là narrowing.
- `Array.set(integers, 0, Double.valueOf(1.0))` cũng thất bại.
- `Array.set(integers, 0, null)` thất bại: không thể unbox `null` thành giá trị primitive.
- `Array.set(new boolean[1], 0, Integer.valueOf(1))` thất bại: boolean không chuyển sang số.

Ghi vào mảng có kiểu `Number[]` với giá trị `Integer` là hợp lệ vì `Integer` là `Number`; nhưng điều này **không** có nghĩa `Array.set` biến một `Number` bất kỳ thành `int` theo yêu cầu tùy ý.

### Phân biệt hai loại chuyển đổi

- **Reference array:** kiểm tra reference assignability (hoặc `null`).
- **Primitive array:** kiểm tra wrapper có thể unbox thành primitive và chuyển tiếp bằng identity/widening hay không.

Trong Java Reflection, “thấy giá trị mang dạng số” chưa đủ. Chẳng hạn `Long.valueOf(3)` không trở thành đối số hợp lệ cho `int[]` chỉ vì số 3 nằm trong miền `int`.

## 5. Các primitive setter: hướng widening đảo chiều so với getter

Primitive setter gồm `setBoolean`, `setByte`, `setShort`, `setChar`, `setInt`, `setLong`, `setFloat`, `setDouble`.

Chữ ký ví dụ:

```java
Array.setInt(array, index, 10);
Array.setFloat(array, index, 1.25f);
```

Khác với getter, khi **ghi**:

> **Kiểu nguồn = tham số primitive của setter. Kiểu đích = component type của mảng.** Được phép nếu nguồn bằng đích hoặc widening primitive conversion từ nguồn sang đích.

Bảng đầy đủ:

| Setter | Component type mảng có thể ghi |
| --- | --- |
| `setBoolean` | `boolean` |
| `setByte` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `setShort` | `short`, `int`, `long`, `float`, `double` |
| `setChar` | `char`, `int`, `long`, `float`, `double` |
| `setInt` | `int`, `long`, `float`, `double` |
| `setLong` | `long`, `float`, `double` |
| `setFloat` | `float`, `double` |
| `setDouble` | `double` |

**Ví dụ đối xứng để nhớ:**

- `Array.getLong(new int[1], 0)` hợp lệ: **đọc int dưới dạng long**.
- `Array.setInt(new long[1], 0, 7)` hợp lệ: **ghi int vào long[]**.
- `Array.getInt(new long[1], 0)` không hợp lệ: đọc long thành int là narrowing.
- `Array.setLong(new int[1], 0, 7L)` không hợp lệ: ghi long vào int[] là narrowing.

Tương tự, `setFloat` có thể ghi vào `double[]`, nhưng không ghi vào `long[]`; `getDouble` có thể đọc `float[]`, nhưng `getFloat` không thể đọc `double[]`.

**Getter và setter có thể cùng hợp lệ trên một mảng nhưng không nhất thiết theo cùng một cặp kiểu.** Phải xác định đúng *hướng conversion* ở mỗi thao tác.

### Không phải “kiểu lớn hơn” theo số bit

Quan hệ widening không chỉ dựa vào số bit. `char` không widening sang `short`, `float` không widening sang `long`, và `boolean` không widening sang loại số. Hãy dùng quy tắc Java Language Specification §5.1.2, đừng tự so sánh kích thước bộ nhớ của các primitive.

## 6. Ví dụ Java 17+ độc lập: đọc, ghi và lỗi tương thích

Ví dụ sau dùng `Array.newInstance` để tạo `int[]` động, dùng cả `get`/`set` tổng quát lẫn primitive getters/setters, kiểm tra một số trường hợp bị từ chối, và duyệt một mảng hai chiều.

Tạo tệp `ArrayAccessDemo.java`:

```java
import java.lang.reflect.Array;

public class ArrayAccessDemo {
    public static void main(String[] args) {
        Object numbers = Array.newInstance(int.class, 3);
        Array.set(numbers, 0, Byte.valueOf((byte) 7));
        Array.setInt(numbers, 1, 42);
        Array.setShort(numbers, 2, (short) -5);

        System.out.println(
                "ints=" + Array.getInt(numbers, 0)
                + "," + Array.getInt(numbers, 1)
                + "," + Array.getInt(numbers, 2)
        );

        Object boxed = Array.get(numbers, 0);
        System.out.println(
                "get type=" + boxed.getClass().getSimpleName()
                + ",value=" + boxed
        );
        System.out.println(
                "getLong(int[])=" + Array.getLong(numbers, 1)
        );

        long[] longs = new long[2];
        Array.setInt(longs, 0, 100);
        Array.set(longs, 1, Integer.valueOf(200));
        System.out.println(
                "longs=" + Array.getLong(longs, 0)
                + "," + Array.getLong(longs, 1)
        );

        double[] real = new double[2];
        Array.setFloat(real, 0, 1.25f);
        Array.setLong(real, 1, 300L);
        System.out.println(
                "real=" + Array.getDouble(real, 0)
                + "," + Array.getDouble(real, 1)
        );

        char[] letters = {'A'};
        System.out.println(
                "char as int=" + Array.getInt(letters, 0)
        );

        String[] words = new String[2];
        Array.set(words, 0, "java");
        Array.set(words, 1, null);
        System.out.println(
                "words=" + Array.get(words, 0)
                + "," + Array.get(words, 1)
        );

        int[][] grid = (int[][]) Array.newInstance(int.class, 2, 2);
        Object row = Array.get(grid, 0);
        Array.setInt(row, 1, 99);
        System.out.println("matrix=" + grid[0][1]);

        try {
            Array.getInt(real, 0);
        } catch (IllegalArgumentException e) {
            System.out.println("getInt(double[])=rejected");
        }

        try {
            Array.setDouble(numbers, 0, 1.0);
        } catch (IllegalArgumentException e) {
            System.out.println("setDouble(int[])=rejected");
        }

        try {
            Array.set(numbers, 0, Long.valueOf(1));
        } catch (IllegalArgumentException e) {
            System.out.println("set(Long,int[])=rejected");
        }

        try {
            Array.set(numbers, 0, null);
        } catch (IllegalArgumentException e) {
            System.out.println("set(null,int[])=rejected");
        }

        try {
            Array.set(words, 0, Integer.valueOf(3));
        } catch (IllegalArgumentException e) {
            System.out.println("set(Integer,String[])=rejected");
        }

        try {
            Array.get(numbers, 3);
        } catch (ArrayIndexOutOfBoundsException e) {
            System.out.println("index=out of bounds");
        }
    }
}
```

Lệnh:

```bash
javac ArrayAccessDemo.java
java ArrayAccessDemo
```

Output:

```text
ints=7,42,-5
get type=Integer,value=7
getLong(int[])=42
longs=100,200
real=1.25,300.0
char as int=65
words=java,null
matrix=99
getInt(double[])=rejected
setDouble(int[])=rejected
set(Long,int[])=rejected
set(null,int[])=rejected
set(Integer,String[])=rejected
index=out of bounds
```

Những điểm cần hiểu:

1. `numbers` có kiểu biến `Object`, nhưng **đối tượng thực** là `int[]`. `Array.getInt` xử lý đúng mảng đó nhờ kiểm tra kiểu ở runtime.
2. `Array.set(numbers, 0, Byte)` unbox `Byte` rồi widening `byte -> int`. `Array.setShort` cũng widening `short -> int`.
3. `Array.get(numbers, 0)` boxing phần tử `int` thành `Integer`. `getLong` đọc một giá trị `int` dưới dạng `long` hợp lệ.
4. Ghi `int` vào `long[]` qua `setInt` và `Array.set` đều hợp lệ. Ghi `float` hoặc `long` vào `double[]` cũng hợp lệ.
5. `getInt` đọc một phần tử `char[]` thành giá trị số UTF-16 là `65` với `'A'`.
6. `Array.set(words, 1, null)` hợp lệ vì `String[]` là mảng reference. Trường hợp tương tự với `int[]` bị từ chối.
7. `grid` là `int[][]`; phần tử thứ nhất của nó là một **đối tượng `int[]`**, nên `Array.get(grid, 0)` trả một hàng, sau đó mới dùng `Array.setInt(row, 1, 99)`.
8. Các nhánh `try/catch` cố ý kiểm thử vi phạm conversion hoặc chỉ số; chúng không liên quan đến lỗi truy cập Java `private` hay vấn đề module.

Kết quả được viết rõ, không dựa vào nội dung thông điệp exception (vốn có thể khác giữa các phiên bản JVM). Ví dụ chỉ bắt loại exception dự kiến rồi in một chuỗi cố định.

## 7. Mảng nhiều chiều: Array.get không tự đi xuống mọi cấp

Mảng nhiều chiều trong Java là **mảng của các mảng**. Vì thế với `int[][]`:

- Mảng ngoài có component type là `int[]` (một **kiểu reference**, không phải primitive `int`).
- `Array.get(matrix, rowIndex)` trả một đối tượng `int[]` của hàng.
- Chỉ sau khi lấy được hàng mới gọi `Array.getInt(row, columnIndex)` hoặc `Array.setInt(row, columnIndex, value)`.

Ví dụ đoạn mã độc lập về ý tưởng:

```java
Object matrix = Array.newInstance(int.class, 2, 3);
Object firstRow = Array.get(matrix, 0);

Array.setInt(firstRow, 1, 88);
int result = Array.getInt(firstRow, 1); // 88
```

`Array.getInt(matrix, 0)` **không** hợp lệ: phần tử của `int[][]` là `int[]`, không phải một primitive `int`. Hãy dùng `Array.get` ở tầng ngoài rồi getter primitive ở tầng trong.

`Array.getLength(matrix)` trả `2`, còn `Array.getLength(firstRow)` trả `3`. Trong mảng jagged (`int[][]` có các hàng dài khác nhau), cần đọc chiều dài **riêng từng hàng**, không giả định mọi hàng đều cùng kích thước.

**Không có hàm `Array.getLength` trả toàn bộ shape nhiều chiều cùng lúc.** Chương trình phải điều hướng từng mảng con, kiểm tra `null` và `getLength` của mỗi cấp khi cần.

## 8. Kiểm tra kiểu component trước khi đọc hoặc ghi

Vì `Array.get`/`Array.set` nhận `Object`, công cụ Reflection tổng quát phải xác định liệu một đối tượng có phải mảng và kiểu thành phần của nó là gì:

```java
Class<?> arrayClass = array.getClass();

if (!arrayClass.isArray()) {
    throw new IllegalArgumentException("Expected an array");
}

Class<?> component = arrayClass.getComponentType();
int count = Array.getLength(array);
```

Đoạn minh họa giả định biến `array` không `null`. Nếu `array` là `int[]`, `component == int.class`. Nếu `array` là `Integer[]`, `component == Integer.class`. Nếu là `int[][]`, component của mảng **ngoài** là `int[].class`, và `component.isPrimitive()` bằng `false` vì bản thân `int[]` là kiểu tham chiếu.

Có thể chọn cách truy cập bằng một nhánh rõ ràng:

```java
Object value;

if (component == int.class) {
    value = Array.getInt(array, index);  // Boxing khi gán vào Object.
} else if (component == double.class) {
    value = Array.getDouble(array, index);
} else {
    value = Array.get(array, index);
}
```

Đây là đoạn mã minh họa, giả định `component`, `array`, `index` nằm trong phạm vi và đã kiểm tra receiver. Nếu công cụ chỉ cần giá trị dưới dạng `Object`, **`Array.get(array, index)` thường đã đủ**; chỉ chọn primitive getter khi cần kết quả primitive hoặc muốn giảm thao tác boxing trong thiết kế thích hợp.

Không cần phân nhánh `if (value instanceof Integer)` để quyết định dùng `setInt` trên `Integer[]`: mảng `Integer[]` vẫn là reference array. Kiểu component *của mảng* quyết định API primitive nào được áp dụng.

## 9. Ngoại lệ thường gặp khi dùng Array

| Tình huống | Lỗi/điều kiện |
| --- | --- |
| Truyền `null` thay cho đối tượng mảng vào `get`/`set` | `NullPointerException` |
| Truyền `String`, `List` hoặc object không phải mảng | `IllegalArgumentException` |
| Chỉ số âm hoặc `index >= length` | `ArrayIndexOutOfBoundsException` |
| `getInt` trên `double[]`, `Integer[]` hoặc kiểu không tương thích | `IllegalArgumentException` |
| `setLong` vào `int[]` | `IllegalArgumentException` do narrowing |
| `Array.set` đưa `Long` vào `int[]` | `IllegalArgumentException` do narrowing |
| `Array.set` đưa `null` vào mảng primitive | `IllegalArgumentException` |
| `Array.set` đưa `Integer` vào `String[]` | `IllegalArgumentException` vì không gán được cho component type |
| `Array.newInstance(componentType, -1)` | `NegativeArraySizeException` |
| `Array.newInstance(void.class, length)` | `IllegalArgumentException`: không tạo được mảng `void` |

Để tránh lỗi, hãy kiểm tra `array != null`, `array.getClass().isArray()`, `Array.getLength(array)`, `array.getClass().getComponentType()`, rồi xác định conversion có được phép hay không.

**Không bắt tất cả `IllegalArgumentException` và mặc định đó là lỗi quyền truy cập Reflection.** `java.lang.reflect.Array` không cần `setAccessible(true)` để đọc một mảng do mã có reference tới nó. Những lỗi ở đây thường là **không phải mảng**, **không đúng kiểu thành phần**, hoặc **không tương thích khi chuyển đổi**.

## 10. Lỗi tư duy phổ biến và cách khắc phục

**Nhầm 1: `Array.get` trả primitive nếu mảng là primitive.** Không. Chữ ký trả `Object`; primitive được boxing. Muốn kết quả kiểu `int`, dùng `getInt`.

**Nhầm 2: Getter `getDouble` đọc được bất kỳ đối tượng số.** Không. Nó chỉ dùng cho **mảng primitive số** có component type được widening tới `double`. `Double[]` và `Number[]` không được tự unbox để dùng primitive getter.

**Nhầm 3: `Array.set` chỉ nhận wrapper có kiểu chính xác.** Không. Với mảng primitive, nó có thể unbox và widening; ví dụ `Byte` vào `int[]` hợp lệ. Nhưng không narrowing.

**Nhầm 4: `setInt` vào `short[]` sẽ tự cắt phần dư.** Không. `int -> short` là narrowing và `Array.setInt` từ chối; muốn phép chuyển đổi thu hẹp, ứng dụng phải thực hiện có chủ đích trước khi gọi setter thích hợp.

**Nhầm 5: `getInt(long[])` và `setInt(long[])` đều hợp lệ.** Chỉ cái thứ hai đúng. Hướng conversion **đọc** và **ghi** khác nhau.

**Nhầm 6: Mảng multidimensional là vùng bộ nhớ có thể index như một vector phẳng bằng `Array.getInt`.** Không. Java dùng mảng lồng nhau; phải lấy từng subarray bằng `get`.

**Nhầm 7: `Array.newInstance` tạo mảng có thể tự tăng độ dài.** Không. Kích thước từng mảng cố định sau khởi tạo. Dùng collection như `ArrayList` nếu mục tiêu là tăng/giảm số phần tử.

**Nhầm 8: Widening bảo đảm giữ nguyên mọi chữ số.** Không. `long -> float/double` và `int -> float` có thể làm tròn dù conversion hợp lệ.

## 11. Câu hỏi tự kiểm tra

1. `Array.get(new int[]{5}, 0)` trả `int` hay `Integer`? **Trả `Object` chứa `Integer(5)`**.
2. `Array.getLong(new int[]{5}, 0)` có hợp lệ không? **Có** vì `int -> long` là widening.
3. `Array.getInt(new long[]{5L}, 0)` có hợp lệ không? **Không**, vì `long -> int` narrowing.
4. `Array.setInt(new long[1], 0, 7)` có được không? **Có**, vì ghi `int -> long`.
5. `Array.setLong(new int[1], 0, 7L)` có được không? **Không**, vì ghi `long -> int` cần narrowing.
6. `Array.set(new double[1], 0, Integer.valueOf(7))` có được không? **Có**, unbox `int` rồi widening `int -> double`.
7. `Array.set(new int[1], 0, Long.valueOf(1))` có được không? **Không**, giá trị nhỏ vẫn phải tuân thủ kiểu conversion.
8. `Array.getInt(new Integer[]{7}, 0)` có được không? **Không**, `Integer[]` là mảng reference.
9. Muốn đọc số ở `matrix[1][2]` khi `matrix` là `int[][]` nhưng có biến kiểu `Object`, làm sao? **`Array.get(matrix, 1)` lấy hàng, rồi `Array.getInt(row, 2)`.**
10. Khi mảng có kích thước 3, `Array.get(a, 3)` báo lỗi gì? **`ArrayIndexOutOfBoundsException`**.

## 12. Tài liệu chính thức

- [Oracle Java SE 21 — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Array.html): hợp đồng `newInstance`, `getLength`, `get/set`, các getter/setter primitive và các ngoại lệ.
- [Java Language Specification SE 21 — §5.1.2 Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.2): định nghĩa các chuyển đổi primitive được phép và các trường hợp làm tròn.
- [Oracle Java SE 21 — `Class.isArray()` và `getComponentType()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): kiểm tra đối tượng class biểu diễn mảng và kiểu thành phần.

**Ghi nhớ:** `Array.get` **đọc phần tử dưới dạng `Object`**, boxing nếu phần tử primitive; `Array.set` **ghi `Object`**, kiểm tra reference assignability hoặc unboxing + widening vào primitive array. Primitive getter widening từ **kiểu phần tử mảng sang kiểu trả về**, primitive setter widening từ **kiểu giá trị ghi sang kiểu phần tử mảng**. Chuyển đổi thu hẹp luôn bị API từ chối, dù giá trị thực tế trông có vẻ vừa miền kiểu đích.