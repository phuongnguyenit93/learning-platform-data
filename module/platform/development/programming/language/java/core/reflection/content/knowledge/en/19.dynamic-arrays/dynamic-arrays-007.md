# getComponentType() cho từng tầng mảng trong Java Reflection

Trong Java, mảng một chiều và mảng nhiều chiều đều là **đối tượng có kiểu mảng**. Java Reflection cho phép đọc cấu trúc kiểu đó ngay cả khi chương trình không biết trước số chiều hay kiểu phần tử cụ thể. Hai API quan trọng nhất là `Class.isArray()` và `Class.getComponentType()`.

Ý tưởng cốt lõi: **mỗi lần gọi `getComponentType()` chỉ bỏ đi đúng một tầng mảng**. Nếu muốn tìm kiểu phần tử gốc của `int[][][]`, ta phải gọi lặp cho đến khi kiểu hiện tại không còn là mảng. Không nhầm kiểu thành phần của tầng kế tiếp với giá trị đang nằm trong một ô của mảng.

Bài thuộc chủ đề **Mảng động** trong Java Core Reflection; trọng tâm là khám phá từng tầng kiểu mảng và áp dụng metadata đó khi tạo/truy cập mảng bằng Reflection.

## 1. Khái niệm: array class, component type và element type

Xét ba biến:

```java
int[] one = new int[4];
int[][] two = new int[2][3];
String[][][] three = new String[2][3][4];
```

Đây là đoạn minh họa Java. Mỗi biến có một `Class<?>` khác nhau:

| Biểu thức lấy `Class<?>` | `isArray()` | `getComponentType()` | Kiểu phần tử gốc |
| --- | --- | --- | --- |
| `int[].class` | `true` | `int.class` | `int` |
| `int[][].class` | `true` | `int[].class` | `int` |
| `String[][][].class` | `true` | `String[][].class` | `String` |
| `Object[].class` | `true` | `Object.class` | `Object` |
| `int.class` | `false` | `null` | Không phải kiểu mảng |
| `String.class` | `false` | `null` | Không phải kiểu mảng |

Phân biệt:

- **Array class**: kiểu của **toàn bộ đối tượng mảng**, ví dụ `int[][].class`.
- **Immediate component type**: kiểu thành phần **trực tiếp**. `int[][].class.getComponentType()` trả `int[].class`, **không** trả ngay `int.class`.
- **Ultimate element type**: kiểu phần tử gốc khi bóc hết các chiều, ví dụ `int.class` đối với `int[][][]`.
- **Number of dimensions**: số lần cần gọi `getComponentType()` từ array class đến khi gặp kiểu không còn là array.

Đây là cấu trúc kiểu, không phải kích thước runtime: `int[2][3]` và `int[100][0]` đều có kiểu `int[][].class`, mặc dù độ dài và tình trạng các hàng khác nhau.

## 2. API Class.getComponentType() hoạt động thế nào?

API Java:

```java
Class<?> component = someType.getComponentType();
```

Với một `Class<?>` biểu diễn kiểu mảng, kết quả là `Class<?>` của thành phần trực tiếp. Nếu `someType` **không biểu diễn kiểu mảng**, kết quả là `null`. Phương thức `getComponentType()` không duyệt sâu toàn bộ số chiều và không truy cập phần tử nào của mảng.

```java
System.out.println(int[][][].class.getComponentType().getTypeName());
// int[][]

System.out.println(int[][].class.getComponentType().getTypeName());
// int[]

System.out.println(int[].class.getComponentType().getTypeName());
// int

System.out.println(int.class.getComponentType());
// null
```

Đoạn code minh họa có thể đặt trong `main`. `Class.getTypeName()` dùng để trình bày tên kiểu dễ đọc: `int[][]`, `java.lang.String[]`,... Trong khi đó, `Class.getName()` của array class sử dụng tên nhị phân/descriptor kiểu như `[[I`, nên khi viết tài liệu hoặc log cho người đọc, `getTypeName()` thường phù hợp hơn.

Đừng gọi `getTypeName()` trên kết quả null:

```java
Class<?> next = String.class.getComponentType();
// next == null; next.getTypeName() sẽ gây NullPointerException.
```

Quy tắc an toàn là kiểm tra `type.isArray()` trước mỗi lần lấy tầng tiếp theo, hoặc kiểm tra `component != null`.

## 3. Bóc từng tầng: sơ đồ cho int[][][]

Tưởng tượng bắt đầu bằng `int[][][].class`:

```text
Tầng 0: int[][][]  --getComponentType()--> int[][]
Tầng 1: int[][]    --getComponentType()--> int[]
Tầng 2: int[]      --getComponentType()--> int
Tầng 3: int        --getComponentType()--> null
```

Vậy số chiều là **3**. Khi dừng ở `int.class`, ta đã tìm được kiểu phần tử gốc. `int.class.isArray()` là `false`, cho dù `int` được tìm thấy bằng cách bóc từ một mảng.

Điều tương tự đúng cho:

```text
java.lang.String[][] → java.lang.String[] → java.lang.String
boolean[][]          → boolean[]           → boolean
Object[]             → Object
```

Không được “nhảy” trực tiếp từ `String[][]` đến `String.class` nếu yêu cầu là khám phá **từng tầng**. Thông tin `String[].class` ở tầng giữa thường cần khi phản chiếu mảng đa chiều hoặc tạo các đoạn mảng không đều.

## 4. Chương trình Java 17+ chạy độc lập

Tạo tệp `ArrayComponentLayersDemo.java`:

```java
import java.lang.reflect.Array;

public class ArrayComponentLayersDemo {

    static void describe(String label, Class<?> startingType) {
        System.out.println(label + ":");
        Class<?> current = startingType;
        int dimensions = 0;

        while (current.isArray()) {
            Class<?> next = current.getComponentType();
            System.out.println("  " + current.getTypeName()
                    + " -> " + next.getTypeName());
            current = next;
            dimensions++;
        }

        System.out.println("  dimensions=" + dimensions
                + ", element=" + current.getTypeName());
        System.out.println("  non-array component="
                + current.getComponentType());
    }

    public static void main(String[] args) {
        describe("primitive 3D", int[][][].class);
        describe("reference 2D", String[][].class);
        describe("scalar", int.class);

        int[][] rectangular =
                (int[][]) Array.newInstance(int.class, 2, 3);
        rectangular[0][1] = 7;

        System.out.println("rectangular type="
                + rectangular.getClass().getTypeName());
        System.out.println("rectangular direct component="
                + rectangular.getClass().getComponentType().getTypeName());
        System.out.println("outer length=" + Array.getLength(rectangular));
        System.out.println("row length="
                + Array.getLength(Array.get(rectangular, 0)));
        System.out.println("value=" + Array.getInt(rectangular[0], 1));

        int[][] ragged = new int[2][];
        ragged[0] = new int[] {1, 2};
        ragged[1] = new int[] {3};

        System.out.println("ragged type="
                + ragged.getClass().getTypeName());
        System.out.println("ragged lengths="
                + ragged[0].length + "," + ragged[1].length);

        int[][] unfilled =
                (int[][]) Array.newInstance(int[].class, 2);
        System.out.println("unfilled type="
                + unfilled.getClass().getTypeName());
        System.out.println("unfilled row null=" + (unfilled[0] == null));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ArrayComponentLayersDemo.java
java ArrayComponentLayersDemo
```

Stdout chính xác:

```text
primitive 3D:
  int[][][] -> int[][]
  int[][] -> int[]
  int[] -> int
  dimensions=3, element=int
  non-array component=null
reference 2D:
  java.lang.String[][] -> java.lang.String[]
  java.lang.String[] -> java.lang.String
  dimensions=2, element=java.lang.String
  non-array component=null
scalar:
  dimensions=0, element=int
  non-array component=null
rectangular type=int[][]
rectangular direct component=int[]
outer length=2
row length=3
value=7
ragged type=int[][]
ragged lengths=2,1
unfilled type=int[][]
unfilled row null=true
```

Phân tích:

1. Mỗi vòng lặp `while (current.isArray())` tiến xuống **một chiều**, tăng biến `dimensions` một đơn vị. Khi `current` là kiểu gốc không phải mảng, vòng lặp kết thúc.
2. `int[][][].class` cho ba dòng chuyển tiếp và phần tử gốc `int`. `String[][].class` cho hai dòng và phần tử gốc `java.lang.String`.
3. Khi đầu vào là `int.class`, số chiều bằng 0 và `getComponentType()` của kiểu đó là null.
4. `Array.newInstance(int.class, 2, 3)` tạo mảng `int[][]` có hai hàng và mỗi hàng dài ba phần tử. Kiểu trực tiếp bên trong là `int[]`.
5. `Array.get(rectangular, 0)` lấy đối tượng mảng con ở hàng đầu; `Array.getLength(...)` sau đó đo độ dài **mảng con**, không phải toàn mảng hai chiều.
6. `Array.getInt(rectangular[0], 1)` đọc phần tử primitive int ở hàng đầu, vị trí 1. Không được truyền thẳng `rectangular` vào `Array.getInt` với chỉ số hàng rồi mong nhận một int, vì component trực tiếp của `rectangular` là mảng `int[]`.
7. `ragged` có hai hàng dài khác nhau, nhưng runtime class vẫn là `int[][].class`. Kiểu không mã hóa kích thước hoặc tính “hình chữ nhật”.
8. `Array.newInstance(int[].class, 2)` tạo mảng hai chiều theo kiểu tổng thể `int[][]` nhưng chỉ cấp phát một tầng ngoài; các phần tử `int[]` bên trong còn null.

## 5. Khác biệt giữa cấp độ kiểu và cấp độ dữ liệu

`Class.getComponentType()` là thao tác **trên kiểu**; `java.lang.reflect.Array.get(...)` và `Array.getLength(...)` là thao tác **trên đối tượng mảng cụ thể**.

Ví dụ:

```java
int[][] data = {
    {10, 20, 30},
    {40}
};

Class<?> outerType = data.getClass();                // int[][].class
Class<?> innerType = outerType.getComponentType();   // int[].class
Object firstRow = Array.get(data, 0);                // một int[]
int rowCount = Array.getLength(data);                // 2
int firstRowLength = Array.getLength(firstRow);      // 3
int secondRowLength = Array.getLength(Array.get(data, 1)); // 1
```

Đây là đoạn minh họa, cần `import java.lang.reflect.Array;`. Kiểu `int[][]` không cho biết hàng thứ nhất dài 3 và hàng thứ hai dài 1. Chỉ **đối tượng mảng cụ thể** mới chứa các độ dài thực tế này.

Đặc biệt:

- `getComponentType()` không trả **phần tử tại index 0**; nó trả một **Class** mô tả kiểu thành phần.
- `Array.get(data, 0)` trả **Object** thực tế ở slot 0, ở ví dụ này là một mảng `int[]`.
- Nếu hàng chưa khởi tạo, `Array.get(data, 0)` có thể trả null, trong khi `data.getClass().getComponentType()` vẫn trả `int[].class`.
- `Array.getLength(someArray)` nhận một đối tượng mảng; nếu truyền scalar hoặc null không phù hợp sẽ ném exception theo API, không mang ý nghĩa “số chiều của kiểu”.

Điều này quan trọng khi duyệt dữ liệu JSON, cấu trúc ma trận hoặc mảng răng cưa: thông tin từ `Class<?>` quyết định **kiểu**, còn muốn duyệt dữ liệu phải xem **mỗi mảng con**.

## 6. Tạo mảng động với Array.newInstance và component type

API `Array.newInstance` có hai dạng thường dùng:

```java
Object newInstance(Class<?> componentType, int length)
Object newInstance(Class<?> componentType, int... dimensions)
```

Đây là chữ ký rút gọn từ `java.lang.reflect.Array`; nó mô tả hai overload chứ không phải method cần tự khai báo. Cơ chế khác nhau:

### Cung cấp kiểu phần tử gốc và nhiều chiều

```java
Object created = Array.newInstance(int.class, 2, 3);
System.out.println(created.getClass().getTypeName()); // int[][]
```

Một `componentType` là `int.class` và hai số chiều trong `dimensions` tạo mảng kiểu `int[][]`, với tất cả các tầng kích thước được cấp phát theo các giá trị truyền vào.

### Cung cấp sẵn một kiểu mảng làm component

```java
Object created = Array.newInstance(int[].class, 2);
System.out.println(created.getClass().getTypeName()); // int[][]
```

Tình huống này cấp phát **một tầng bên ngoài** có hai phần tử, mỗi phần tử có kiểu `int[]` và được khởi tạo mặc định là null. Chỉ sau khi gán từng mảng con, các hàng mới có dữ liệu:

```java
int[][] values = (int[][]) Array.newInstance(int[].class, 2);
values[0] = new int[3];
values[1] = new int[1];
```

Nếu dùng `Array.newInstance(int[].class, 2, 3)`, kết quả là **`int[][][]`**, không phải `int[][]`: kiểu component đã có một chiều, rồi lời gọi thêm hai chiều nữa.

Đây là lỗi hay gặp ở mã xử lý số chiều động. Công thức tổng quát cho kiểu:

**Số chiều kiểu kết quả = số chiều vốn có của componentType + số chiều mới yêu cầu ở Array.newInstance.**

Lưu ý: overload `Array.newInstance(componentType, int length)` luôn thêm một chiều kiểu. Overload có `int... dimensions` có thể thêm nhiều chiều; mảng `dimensions` phải không rỗng. Kích thước âm gây `NegativeArraySizeException`; số chiều kết quả vượt giới hạn JVM hoặc `void.class` làm component là không hợp lệ (`IllegalArgumentException`). Không được gọi `Array.newInstance` rồi tùy tiện ép sang một kiểu mảng khác với runtime class mà nó tạo.

## 7. Primitive arrays khác reference arrays

`int[]` là mảng **primitive**, trong khi `String[]` và `int[][]` đều có component trực tiếp là **reference type**:

| Kiểu mảng | Component trực tiếp | Có thể cast toàn bộ mảng sang `Object[]`? |
| --- | --- | --- |
| `int[]` | `int` | Không |
| `double[]` | `double` | Không |
| `String[]` | `String` | Có |
| `int[][]` | `int[]` (reference type) | Có |
| `int[][][]` | `int[][]` (reference type) | Có |

Ví dụ:

```java
int[] numbers = {1, 2};
int[][] rows = {{1, 2}, {3}};

Object anyNumbers = numbers;  // Hợp lệ: mọi mảng đều là Object
Object[] outerRows = rows;    // Hợp lệ: component trực tiếp là int[]
// Object[] bad = numbers;     // Sai tại compile time
```

Mảng `int[]` không phải `Object[]` dù chính đối tượng mảng có thể gán vào biến `Object`. Trong khi đó `int[][]` là một mảng các reference `int[]`, nên tầng ngoài phù hợp với `Object[]`.

Reflection API `Array.get(anyArray, index)` giúp viết logic dùng chung cho cả primitive và reference arrays. Khi cần gán phần tử, `Array.set(array, index, value)` kiểm tra kiểu hợp lệ và chuyển đổi primitive phù hợp; nó không làm phép chuyển tùy ý.

Đối với primitive array, `Array.get(intArray, index)` trả wrapper object (ví dụ `Integer`), còn `Array.getInt(intArray, index)` trả giá trị int trực tiếp, miễn array và kiểu thành phần tương thích với getter đó.

## 8. Hỗ trợ số chiều chưa biết khi chạy

Trong công cụ generic, ta có thể không biết trước đối tượng là `String[]`, `long[][]` hay `Customer[][][]`. Một utility lấy kiểu phần tử gốc và đếm chiều:

```java
public static Class<?> deepestElementType(Class<?> type) {
    if (type == null) {
        throw new IllegalArgumentException("type must not be null");
    }

    Class<?> current = type;
    while (current.isArray()) {
        current = current.getComponentType();
    }
    return current;
}

public static int dimensions(Class<?> type) {
    if (type == null) {
        throw new IllegalArgumentException("type must not be null");
    }

    int count = 0;
    Class<?> current = type;
    while (current.isArray()) {
        count++;
        current = current.getComponentType();
    }
    return count;
}
```

Đây là hai hàm tiện ích minh họa để đặt bên trong một class Java, không phải chương trình `main` độc lập. Kết quả:

```text
deepestElementType(int[][][].class) = int.class
dimensions(int[][][].class) = 3
deepestElementType(String[][].class) = String.class
dimensions(String[][].class) = 2
deepestElementType(String.class) = String.class
dimensions(String.class) = 0
```

Dòng minh họa ở đây thể hiện **giá trị logic trả về**, không phải stdout tự động in bởi hai hàm.

Với yêu cầu “đầu vào bắt buộc là array”, hãy kiểm tra `type.isArray()` ở ranh giới tiện ích và báo lỗi nếu false. Còn các hàm ở trên chấp nhận scalar và trả kiểu đó cùng số chiều 0: cách xử lý này có thể hữu ích khi bộ phân tích hỗ trợ cả hai nhóm kiểu.

### Duyệt từng tầng và không tạo mảng vô hạn

Vòng lặp `while (type.isArray())` luôn kết thúc đối với một array class hợp lệ: mỗi bước `getComponentType()` bỏ đi đúng một chiều và cuối cùng đến kiểu phần tử gốc. Điều cần tránh là gọi `getComponentType()` mãi sau khi kiểu không còn là mảng, rồi thao tác với null.

Khi cần xây cấu trúc mới dựa trên số chiều được phát hiện, phải xác định rõ **kiểu thành phần dùng làm đầu vào Array.newInstance**. Nếu đưa nguyên kiểu mảng đã có vào đó mà lại yêu cầu thêm toàn bộ số chiều đếm được, kết quả sẽ thừa chiều.

## 9. Class.getComponentType không mang thông tin generic arguments

`Class<?>` biểu thị **runtime type** theo Java type erasure. Nếu có khai báo:

```java
java.util.List<String>[] lists;
```

thì runtime component class tương ứng của kiểu mảng là `java.util.List.class`, không phải một đối tượng `Class<List<String>>` bảo tồn `String` dưới dạng type argument.

Với một `Field` phản chiếu khai báo generic, `Field.getGenericType()` trả `java.lang.reflect.Type`, có thể là `GenericArrayType` hoặc loại `Type` khác để phân tích generic declaration tùy trường hợp. Trong khi đó, `Field.getType()` trả một `Class<?>` theo kiểu đã erasure; gọi `getComponentType()` trên nó cho biết các **tầng mảng của runtime class**, không giải mã đầy đủ kiểu generic.

Vì vậy:

- Muốn biết số chiều mảng và kiểu phần tử runtime: dùng `Class.isArray()/getComponentType()`.
- Muốn hiểu chữ ký generic đã khai báo trong source: xem `Field.getGenericType()` hoặc metadata generic tương ứng.
- Đừng giả định runtime `Class` lưu sẵn type arguments của `List<String>`.

Đây là ranh giới thông tin giữa Class và Type, không phải lỗi của `getComponentType()`.

## 10. Lỗi thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| `int[][].class.getComponentType()` trả `int.class` | Chỉ bóc một tầng mỗi lần | Kết quả là `int[].class` |
| `getComponentType()` trả số phần tử | Nó thao tác trên metadata của kiểu | Muốn độ dài của mảng cụ thể, dùng `Array.getLength(array)` |
| `getComponentType()` luôn trả Class khác null | Kiểu không phải mảng cho kết quả null | Kiểm tra `isArray()` trước |
| Mảng hai chiều luôn có các hàng dài bằng nhau | Java cho phép mảng răng cưa | Đo độ dài từng mảng con riêng |
| `new int[2][]` đã tạo hai hàng `int[]` | Chỉ mảng ngoài được cấp phát | Ban đầu mỗi slot hàng là null |
| `Array.newInstance(int[].class, 2, 3)` trả `int[][]` | Input `int[]` đã có một chiều | Kết quả là `int[][][]` |
| `Object[] values = new int[3]` hợp lệ | Primitive array không là `Object[]` | `int[]` chỉ gán được vào `Object`; dùng `Array.get` cho logic chung |
| `int[][]` không thể xem là `Object[]` | Component của tầng ngoài là `int[]`, một reference type | Toàn mảng hai chiều có thể gán cho `Object[]` |
| `int[2][3]` và `int[2][1]` là hai class khác nhau | Độ dài không thuộc định danh kiểu mảng | Cả hai có class `int[][].class` |
| Có thể lấy generic `String` từ `List<String>[]` bằng `getComponentType()` | Runtime erasure không lưu generic type argument trong Class | Dùng GenericType metadata của khai báo nếu cần |
| `getName()` và `getTypeName()` luôn giống nhau | Tên array class có thể là descriptor | Ưu tiên `getTypeName()` khi hiển thị dễ đọc |

## 11. Bài tập thực hành

**Bài 1.** Cho `byte[][][][]`. Hãy liệt kê kết quả của ba lần đầu gọi `getComponentType()` rồi xác định tầng cuối.

**Đáp án:** `byte[][][]`, `byte[][]`, `byte[]`; lần thứ tư trả `byte.class`. Có bốn chiều.

**Bài 2.** Cho `String[][] names = new String[2][];`. Tại sao `names.getClass().getComponentType()` vẫn trả `String[].class` dù `names[0] == null`?

**Đáp án:** Component type là metadata của **kiểu mảng**, độc lập với việc một slot có chứa đối tượng mảng con hay còn null.

**Bài 3.** `Array.newInstance(double[][].class, 4)` tạo kiểu gì?

**Đáp án:** `double[][][]`, gồm một tầng ngoài dài 4, các phần tử `double[][]` ban đầu là null.

**Bài 4.** Vì sao `int[][] matrix` có thể gán cho `Object[]` nhưng `int[] row` thì không?

**Đáp án:** Component trực tiếp của `int[][]` là reference type `int[]`. Component của `int[]` là primitive `int`, nên `int[]` không là `Object[]`.

**Bài 5.** Có thể biết số hàng/cột của một mảng nhiều chiều chỉ từ `Class.getComponentType()` không?

**Đáp án:** Không. API này chỉ mô tả kiểu từng tầng. Cần có đối tượng mảng và dùng `Array.getLength()` ở từng tầng thực tế; các mảng con có thể null hoặc dài khác nhau.

## 12. Tổng kết

**Quy tắc quan trọng nhất:** với mọi array class, **`getComponentType()` chỉ lấy một tầng thành phần trực tiếp**.

1. Bắt đầu từ `Class<?>` của đối tượng hoặc kiểu đã biết.
2. Trong khi `isArray() == true`, gọi `getComponentType()` để chuyển xuống một tầng và tăng số chiều đã đếm.
3. Khi đến kiểu không phải mảng, đó là kiểu phần tử gốc; `getComponentType()` lúc này trả null.
4. Khi tạo mảng, phân biệt `Array.newInstance(baseType, dimensions...)` với `Array.newInstance(existingArrayType, length)` để không thêm thừa chiều.
5. Khi đọc dữ liệu, dùng `Array.getLength` và `Array.get` trên **đối tượng mảng thật**, không suy độ dài từ `Class<?>`.

**Tài liệu tham khảo:** [Java SE 17 — Class.getComponentType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getComponentType()) · [Java SE 17 — java.lang.reflect.Array](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html)