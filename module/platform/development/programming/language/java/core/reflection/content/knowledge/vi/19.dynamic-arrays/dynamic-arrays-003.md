# Array.getLength và kiểm tra isArray trong Java Reflection

## 1. Vì sao cần kiểm tra mảng khi dữ liệu chỉ có kiểu Object?

Trong Java thông thường, nếu biến có kiểu mảng tại thời điểm biên dịch, ta lấy độ dài bằng thuộc tính `length`:

```java
int[] numbers = {4, 5, 6};
int count = numbers.length; // 3
```

Tuy nhiên, khi dữ liệu được nhận qua `Object`, từ một `Field.get(...)`, `Method.invoke(...)`, thư viện ánh xạ dữ liệu hoặc khi tạo mảng động, mã nguồn không biết chắc đối tượng có phải mảng hay không. Reflection cung cấp hai thao tác quan trọng:

- `value.getClass().isArray()` xác định **lớp runtime của đối tượng có phải kiểu mảng**. Cần kiểm tra `value != null` trước khi gọi `getClass()`.
- `java.lang.reflect.Array.getLength(value)` đọc **số phần tử của đối tượng mảng**, bất kể đó là mảng primitive (`int[]`, `double[]`) hay mảng tham chiếu (`String[]`, `Object[]`).

Ví dụ:

```java
Object value = new int[] {4, 5, 6};

if (value != null && value.getClass().isArray()) {
    int length = java.lang.reflect.Array.getLength(value);
    System.out.println(length); // 3
}
```

Đoạn code trên là **mảnh mã đặt trong phương thức**. Nếu sử dụng `((Object[]) value).length` thay vì `Array.getLength(value)`, mảng `int[]` sẽ gây `ClassCastException`, bởi `int[]` không phải `Object[]`.

## 2. Hai API phục vụ hai câu hỏi khác nhau

| API / biểu thức | Hỏi điều gì? | Giá trị trả về | Điều kiện |
| --- | --- | --- | --- |
| `someArray.length` | Mảng này có bao nhiêu phần tử? | `int` | Trình biên dịch đã biết biến là kiểu mảng |
| `type.isArray()` | Đối tượng `Class` này biểu diễn kiểu mảng không? | `boolean` | Đã có `Class<?>` |
| `obj.getClass().isArray()` | Kiểu thực của đối tượng có phải mảng không? | `boolean` | `obj != null` |
| `Array.getLength(obj)` | Đối tượng mảng này có bao nhiêu phần tử? | `int` | `obj` phải là **một đối tượng mảng**, khác `null` |
| `type.getComponentType()` | Thành phần của kiểu mảng là loại gì? | `Class<?>` hoặc `null` | `type.isArray() == true` để có component |
| `Array.get(array, index)` | Phần tử tại chỉ số này là gì? | `Object` | Đối tượng mảng hợp lệ; chỉ số hợp lệ |

`Class.isArray()` kiểm tra **kiểu**, không kiểm tra độ dài. `Array.getLength()` làm việc với **đối tượng mảng thật**, không nhận `Class` làm đại diện cho mảng:

```java
int[].class.isArray();                  // true
java.lang.reflect.Array.getLength(
        new int[] {1, 2});             // 2

// Sai: int[].class là đối tượng Class, không phải một mảng.
// Array.getLength(int[].class);        // IllegalArgumentException
```

Đừng nhầm `Array.getLength()` với `java.lang.reflect.Array.newInstance(...)`: cái đầu **đo kích thước mảng hiện có**; cái sau **tạo một đối tượng mảng mới**.

## 3. isArray áp dụng cho cả mảng primitive và mảng tham chiếu

```java
int[].class.isArray();          // true
Integer[].class.isArray();      // true
String[].class.isArray();       // true
int[][].class.isArray();        // true
String.class.isArray();         // false
int.class.isArray();            // false
Object.class.isArray();         // false
```

**Các kiểu mảng trong Java đều là kiểu tham chiếu**, kể cả `int[]`. Vì thế:

- `int[].class.isArray()` là `true`.
- `int[].class.isPrimitive()` là `false`.
- `int[].class.getComponentType().isPrimitive()` là `true`, vì component của `int[]` là `int`.
- `Integer[].class.getComponentType().isPrimitive()` là `false`.
- `int[]` có thể gán vào biến `Object` và tuân thủ các interface mảng như `Cloneable`, `Serializable`, nhưng **không thể gán cho `Object[]`**.
- `String[]` là mảng tham chiếu, nên có thể gán vào `Object[]`.

`Class.getComponentType()` giúp phát hiện kiểu phần tử. Với mảng nhiều chiều `int[][]`, lần gọi đầu tiên trả `int[].class`, tiếp theo trả `int.class`. `getComponentType()` trên một kiểu không phải mảng trả `null`.

Mảng primitive và wrapper như `int[]` và `Integer[]` đều có `isArray() == true`, nhưng vẫn là **hai kiểu runtime khác nhau**. Boxing/unboxing phần tử `int` không tự động chuyển nguyên mảng `int[]` thành `Integer[]`.

## 4. Array.getLength nhận gì và gây ngoại lệ nào?

Chữ ký của API:

```java
public static int getLength(Object array)
```

`Array.getLength` không yêu cầu mảng phần tử đối tượng (`Object[]`); đối số `Object` có thể giữ bất cứ mảng nào, bao gồm `boolean[]`, `char[]`, `double[]`, `String[]` hoặc mảng nhiều chiều.

| Truyền vào | Kết quả |
| --- | --- |
| `new int[] {1, 2, 3}` | `3` |
| `new String[0]` | `0` |
| `new int[2][3]` | `2` (chiều ngoài) |
| `"hello"` | `IllegalArgumentException` |
| `Integer.valueOf(3)` | `IllegalArgumentException` |
| `new java.util.ArrayList<>()` | `IllegalArgumentException`; `List` không phải Java array |
| `int[].class` | `IllegalArgumentException`; đây là đối tượng `Class` |
| `null` | `NullPointerException` |

Đây là **ngoại lệ khi gọi trực tiếp `Array.getLength`**: không phải `NoSuchMethodException`, vì không hề tra cứu một phương thức theo tên. Để tránh lỗi trên dữ liệu không chắc chắn, kiểm tra:

```java
// Mảnh mã minh họa trong phương thức đã có biến Object value.
if (value == null) {
    System.out.println("No object");
} else if (!value.getClass().isArray()) {
    System.out.println("Not an array");
} else {
    System.out.println(Array.getLength(value));
}
```

Cần `import java.lang.reflect.Array;` nếu không dùng tên lớp đầy đủ.

**Không dùng `instanceof Object[]` để nhận diện tất cả mảng**: `new int[] {1, 2}` trả `false` cho phép thử này dù thật sự là mảng; `getClass().isArray()` nhận diện được.

## 5. Mảng hai chiều: getLength không tự đo tất cả chiều

Ví dụ:

```java
int[][] ragged = {
    {1, 2, 3},
    {4},
    new int[0],
    null
};
```

- `Array.getLength(ragged)` trả **4** vì mảng ngoài có bốn phần tử, mỗi phần tử là một tham chiếu tới `int[]` (có thể `null`).
- `Array.getLength(ragged[0])` trả **3**.
- `Array.getLength(ragged[1])` trả **1**.
- `Array.getLength(ragged[2])` trả **0**.
- `Array.getLength(ragged[3])` ném `NullPointerException`, vì hàng đó là `null`.

Đây là **mảng jagged/ragged**, mỗi hàng có độ dài độc lập. Không thể suy ra mọi hàng dài 3 chỉ từ `ragged[0].length`, cũng không nên nhân `ragged.length * ragged[0].length` như thể đó luôn là số phần tử của một ma trận hình chữ nhật.

Dùng `Array.get` để duyệt từng phần tử mảng ngoài khi loại thành phần chỉ được biết ở runtime:

```java
// Mảnh mã minh họa trong phương thức; object phải là một đối tượng mảng.
int outerLength = Array.getLength(object);

for (int i = 0; i < outerLength; i++) {
    Object element = Array.get(object, i);
    if (element != null && element.getClass().isArray()) {
        System.out.println("row " + i + ": "
                + Array.getLength(element));
    }
}
```

Ở đây `Array.get` trả `Object`; nếu phần tử là mảng con, ta có thể dùng tiếp `getClass().isArray()` và `Array.getLength`. Nếu phần tử là một primitive value, `Array.get` sẽ boxing giá trị đó thành wrapper trước khi trả về `Object`; wrapper không phải mảng.

### Khi dùng Array.newInstance tạo mảng nhiều chiều

```java
Object matrix = Array.newInstance(int.class, 2, 3);
```

Đối tượng có runtime type `int[][]`, chiều ngoài dài 2 và mỗi hàng là `int[3]`. Nếu chỉ muốn một mảng ngoài gồm các hàng tùy biến, có thể tạo `int[][]` thông thường và gán từng hàng riêng. `Array.getLength(matrix)` vẫn chỉ đọc kích thước chiều ngoài, không có cơ chế tự trả tổng số ô của mọi chiều.

## 6. Chương trình Java 17+ đầy đủ và kiểm chứng được

Lưu mã sau thành tệp **`ArrayLengthLesson.java`**:

```java
import java.lang.reflect.Array;

public class ArrayLengthLesson {
    static void printInfo(String label, Object value) {
        if (value == null) {
            System.out.println(label + ": null");
            return;
        }

        Class<?> type = value.getClass();
        System.out.println(label + ": isArray=" + type.isArray()
                + ", type=" + type.getTypeName()
                + (type.isArray()
                        ? ", length=" + Array.getLength(value)
                        : ""));
    }

    public static void main(String[] args) {
        int[] ints = {4, 5, 6};
        String[] words = {"a", "b"};
        int[][] ragged = {{1, 2, 3}, {4}, new int[0], null};
        int[][] rectangle =
                (int[][]) Array.newInstance(int.class, 2, 3);

        printInfo("ints", ints);
        printInfo("words", words);
        printInfo("ragged", ragged);
        printInfo("row0", ragged[0]);
        printInfo("row1", ragged[1]);
        printInfo("row2", ragged[2]);
        printInfo("row3", ragged[3]);

        printInfo("rectangle", rectangle);
        System.out.println("rectangle row0="
                + Array.getLength(rectangle[0]));

        System.out.println("int[] class.isArray="
                + int[].class.isArray());
        System.out.println("int.class.isArray="
                + int.class.isArray());
        System.out.println("int[] component="
                + int[].class.getComponentType().getTypeName());
        System.out.println("int[] component primitive="
                + int[].class.getComponentType().isPrimitive());
        System.out.println("int[] instanceof Object[]="
                + Object[].class.isInstance(ints));
        System.out.println("int[] instanceof Object="
                + (ints instanceof Object));

        try {
            Array.getLength("abc");
        } catch (IllegalArgumentException e) {
            System.out.println("not array: IllegalArgumentException");
        }
        try {
            Array.getLength(null);
        } catch (NullPointerException e) {
            System.out.println("null: NullPointerException");
        }

        Object[] nested = {ints, words};
        System.out.println("nested length=" + Array.getLength(nested));
        System.out.println("nested first length="
                + Array.getLength(Array.get(nested, 0)));
    }
}
```

Biên dịch/chạy từ thư mục chứa tệp bằng JDK 17+:

```bash
javac ArrayLengthLesson.java
java ArrayLengthLesson
```

Stdout:

```text
ints: isArray=true, type=int[], length=3
words: isArray=true, type=java.lang.String[], length=2
ragged: isArray=true, type=int[][], length=4
row0: isArray=true, type=int[], length=3
row1: isArray=true, type=int[], length=1
row2: isArray=true, type=int[], length=0
row3: null
rectangle: isArray=true, type=int[][], length=2
rectangle row0=3
int[] class.isArray=true
int.class.isArray=false
int[] component=int
int[] component primitive=true
int[] instanceof Object[]=false
int[] instanceof Object=true
not array: IllegalArgumentException
null: NullPointerException
nested length=2
nested first length=3
```

**Phân tích kết quả:**

1. `printInfo` xử lý `null` trước, tránh `NullPointerException` từ `getClass()`. Đối tượng không-null được phân loại bằng runtime class.
2. `int[]` và `String[]` đều được `isArray()` xác nhận; `Array.getLength` đọc đúng 3 và 2.
3. `ragged` có 4 phần tử ở chiều ngoài; từng hàng có kích thước 3, 1, 0, hoặc `null`.
4. `rectangle` được tạo động với chiều dài `2 × 3`; tuy nhiên `getLength(rectangle)` chỉ trả 2.
5. `int[].class.isArray()` là `true`, còn `int.class.isArray()` là `false`; kiểu `int` là primitive nhưng `int[]` là array object.
6. `Object[].class.isInstance(ints)` là `false`; `ints instanceof Object` là `true`. Không nên dùng phép cast `Object[]` cho mảng primitive.
7. `Array.getLength("abc")` ném `IllegalArgumentException`; `Array.getLength(null)` ném `NullPointerException`.
8. `nested` là `Object[]` chứa hai đối tượng mảng ở cấp phần tử. Mảng ngoài dài 2, mảng đầu (một `int[]`) dài 3.

Chương trình chủ động **không dùng một thứ tự duyệt Reflection không được đảm bảo**; stdout chỉ phụ thuộc giá trị mảng cố định và kiểu runtime.

## 7. Khi Class đã có từ Reflection: kiểm tra trước khi lấy độ dài

Ví dụ dữ liệu được đọc từ một field:

```java
// Mảnh code đặt trong phương thức có Class<?> type và Object receiver.
java.lang.reflect.Field field = type.getDeclaredField("data");
Object value = field.get(receiver); // Cần quyền truy cập hợp lệ.

if (value != null && value.getClass().isArray()) {
    int count = Array.getLength(value);
    // Xử lý số phần tử.
}
```

`field.getType().isArray()` cũng có ích nếu muốn hỏi **kiểu khai báo của field**, trước khi đọc giá trị. Tuy nhiên cần phân biệt:

- **Kiểu khai báo:** `Object data;` → `field.getType().isArray()` là `false`, ngay cả khi hiện đang giữ `new int[3]`.
- **Kiểu runtime của giá trị:** `value.getClass().isArray()` là `true` nếu `value` thực sự là `int[]`.
- **Giá trị `null`:** kiểu field có thể là `int[]` nhưng `field.get(...)` trả `null`; không có đối tượng mảng để đo độ dài.

Lựa chọn tùy mục đích: kiểm tra **schema** thì dùng kiểu khai báo; xử lý **dữ liệu đang nhận** thì dùng lớp runtime sau khi kiểm tra null.

Điều tương tự áp dụng cho `Method.getReturnType().isArray()` (kiểu trả về khai báo) và giá trị thực tế sau `Method.invoke`; những method khai báo trả `Object` vẫn có thể trả mảng.

## 8. Thiết kế hàm lấy độ dài an toàn

Đối với ứng dụng chỉ muốn xử lý mảng, có thể viết hàm dùng chung:

```java
// Đặt trong một lớp Java, dùng import java.lang.reflect.Array.
static int requireArrayLength(Object value) {
    if (value == null) {
        throw new IllegalArgumentException("Array value must not be null");
    }
    if (!value.getClass().isArray()) {
        throw new IllegalArgumentException(
                "Expected array but got " + value.getClass().getTypeName());
    }
    return Array.getLength(value);
}
```

Đây là **hàm minh họa**, không phải chương trình độc lập. Nó chủ ý gộp trường hợp `null` và không-phải-mảng thành `IllegalArgumentException` theo hợp đồng ứng dụng, **khác** với ngoại lệ gốc `NullPointerException` của `Array.getLength(null)`. Không khẳng định rằng bản thân API Reflection tự sinh thông báo lỗi trên.

Khi đối tượng không phải mảng là một tình huống bình thường (chẳng hạn input đa kiểu), có thể trả một `OptionalInt` hoặc một kết quả có trạng thái thay vì bắt/nuốt ngoại lệ. Đừng quy ước `0` là “không phải mảng”, vì **mảng rỗng hợp lệ cũng có độ dài 0**.

## 9. Lưu ý về Array.get, Array.set và mảng động

Ngoài `getLength`, lớp `java.lang.reflect.Array` còn cung cấp:

- `Array.get(array, index)`: đọc một phần tử tại runtime, kết quả kiểu `Object`; nếu phần tử primitive, API boxing thành wrapper.
- `Array.set(array, index, value)`: ghi phần tử khi kiểu/chuyển đổi hợp lệ; không có nghĩa mọi wrapper có thể gán cho mọi mảng primitive.
- `Array.newInstance(componentType, length)`: tạo mảng động dựa trên `Class` của thành phần.
- `Array.newInstance(componentType, dimensions...)`: tạo mảng nhiều chiều với các kích thước được chỉ định.

Nếu `Array.getLength(array) == n`, các chỉ số hợp lệ cho mảng này là `0` đến `n - 1`. Truy cập `n` hoặc chỉ số âm sẽ ném `ArrayIndexOutOfBoundsException`. Đọc độ dài không tự cấp quyền vượt giới hạn chỉ số.

**Không nhầm loại API:**

- `java.lang.reflect.Array` dành cho các mảng Java, bao gồm primitive arrays.
- `java.util.Arrays` cung cấp nhiều hàm tiện ích như `toString`, `deepToString`, `copyOf`, `stream`.
- `java.util.List.size()` là kích thước của một collection, không phải `Array.getLength(list)`.
- `String.length()` là độ dài chuỗi theo đơn vị UTF-16 code unit, không phải `Array.getLength(string)`.

## 10. Những lỗi phổ biến

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `Array.getLength(null)` | `NullPointerException` | Kiểm tra `value != null` |
| `Array.getLength("abc")` | `IllegalArgumentException` | Xác minh `value.getClass().isArray()` |
| `value.getClass().isArray()` khi `value == null` | `NullPointerException` trước cả kiểm tra `isArray` | Kiểm tra `null` trước |
| `value instanceof Object[]` để kiểm mọi mảng | Bỏ sót `int[]`, `boolean[]`, ... | Dùng `getClass().isArray()` |
| `((Object[]) intArray).length` | `ClassCastException` | Dùng `Array.getLength(intArray)` |
| Cho rằng `Array.getLength(matrix)` trả tổng phần tử 2D | Chỉ trả độ dài **chiều ngoài** | Duyệt từng hàng, kiểm tra `null` |
| Dùng `getComponentType()` trên class không phải mảng mà không kiểm tra | Trả `null`; dễ gây NPE khi dùng tiếp | Kiểm tra `Class.isArray()` |
| Dùng `Array.getLength(int[].class)` | `IllegalArgumentException`; đối số là `Class`, không phải array instance | Truyền một đối tượng `int[]` |
| Đánh đồng `field.getType().isArray()` với kiểu runtime của giá trị | Field kiểu `Object` có thể giữ mảng và field kiểu mảng có thể đang `null` | Phân biệt kiểu khai báo và kiểu runtime |
| Coi `List` hoặc `String` là mảng | `Array.getLength` không dùng cho hai loại này | `list.size()` hoặc `string.length()` |
| Trả `0` khi đầu vào không phải mảng | Không phân biệt được với mảng rỗng | Dùng trạng thái tường minh hoặc ngoại lệ |

## 11. Câu hỏi tự kiểm tra

1. **`new int[0]` có `isArray() == true` không?** Có. `Array.getLength` trả `0`; rỗng không có nghĩa “không phải mảng”.
2. **`int[].class.isArray()` và `int.class.isArray()` khác nhau thế nào?** Kết quả lần lượt là `true` và `false`.
3. **`Array.getLength(new int[2][3])` trả bao nhiêu?** `2`, chiều ngoài. Mỗi hàng có độ dài `3`.
4. **Một `Object data = new int[]{1,2}` có thể dùng `((Object[]) data).length` không?** Không; cast gây `ClassCastException`. Dùng `Array.getLength(data)`.
5. **Nếu `Object data = "hi"`, `data.getClass().isArray()` trả gì?** `false`; gọi `Array.getLength(data)` sẽ ném `IllegalArgumentException`.
6. **Làm sao xem mảng có kiểu phần tử primitive?** Trước hết xác nhận `type.isArray()`, sau đó dùng `type.getComponentType().isPrimitive()`. Với mảng nhiều chiều `int[][]`, component trực tiếp là `int[]` (không primitive); phải đi sâu thêm để đến `int`.
7. **`Array.getLength(null)` và `Array.getLength(new Object[0])` khác nhau thế nào?** Cái đầu ném `NullPointerException`, cái sau trả `0`.

**Ghi nhớ:** `Class.isArray()` là câu trả lời cho **“đây có phải một kiểu mảng?”**; `Array.getLength(value)` là câu trả lời cho **“đối tượng mảng này có bao nhiêu phần tử ở chiều hiện tại?”**. Trước khi đo độ dài dữ liệu động, kiểm tra `null` và kiểu runtime, nhất là với mảng primitive và mảng nhiều chiều.

Tài liệu chính thức: [`java.lang.reflect.Array` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html), [`java.lang.Class.isArray` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isArray()), [JLS §10.7 Array Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.7).