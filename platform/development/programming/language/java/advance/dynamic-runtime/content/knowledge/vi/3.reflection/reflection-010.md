# 3.10. Tạo và thao tác mảng chưa biết kiểu thành phần bằng java.lang.reflect.Array

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích tại sao khi **kiểu phần tử chỉ được biết ở runtime**, không thể dùng trực tiếp cú pháp `new T[n]` hay `new SomeType[n]` với một tên kiểu chưa xác định lúc biên dịch.
2. Dùng `java.lang.reflect.Array` để tạo mảng đúng **component type** (kiểu thành phần) kể cả khi đó là `int`, `boolean`, `String`, một class tùy chọn hoặc chính một kiểu mảng.
3. Đọc độ dài, lấy/ghi phần tử, kiểm tra kiểu runtime và làm việc với mảng nhiều chiều mà không ép mọi mảng thành `Object[]`.
4. Phân biệt boxing/unboxing, primitive widening, reference assignment, lỗi index và lỗi kiểu.
5. Xây dựng tiện ích tổng quát xử lý được cả mảng primitive và mảng tham chiếu; biết khi nào nên quay lại API có kiểu tĩnh.

**Ngữ cảnh:** Java hỗ trợ reflection để framework ánh xạ dữ liệu từ schema, metadata, annotation, plugin hoặc tên kiểu trong cấu hình. Ví dụ một serializer có thể nhận `Class<?> componentType` khi chạy và cần tạo đúng `String[]`, `long[]` hay `Customer[]` mà chưa biết trước loại nào lúc viết source.

## 1. Tại sao cần `java.lang.reflect.Array`?

Cách bình thường:

```java
String[] names = new String[3];
int[] scores = new int[3];
```

Ở hai dòng này, compiler đã biết `String` và `int`. Nếu chỉ nhận một biến `Class<?> componentType`, bạn **không thể** viết `new componentType[3]`: đây là biến chứa thông tin kiểu, không phải tên kiểu trong cú pháp Java. Với generic `T` cũng không thể trực tiếp viết `new T[3]` vì type erasure.

Lúc đó dùng:

```java
Class<?> componentType = String.class; // Minh họa: giá trị này có thể đến từ metadata.
Object array = java.lang.reflect.Array.newInstance(componentType, 3);
```

Dù kiểu khai báo của biến `array` là `Object`, **kiểu runtime của đối tượng được tạo vẫn là `String[]`**. JVM không tạo một `Object[]` thay thế cho `String[]`. Phải giữ hai khái niệm riêng:

- **Kiểu của biến ở compile time:** `Object`, vì `Array.newInstance(...)` phải trả được cả `int[]` và `String[]`.
- **Kiểu thực của đối tượng ở runtime:** ví dụ `int[]`, `String[]`, `java.time.LocalDate[]`; JVM dùng kiểu này để kiểm tra phép gán và truy cập phần tử.

Mọi mảng Java đều là object, có độ dài cố định, chỉ số từ `0` đến `length - 1`. Một mảng có thể chứa primitive, reference hoặc một kiểu mảng khác làm phần tử.

## 2. API cốt lõi của `java.lang.reflect.Array`

`Array` thuộc package `java.lang.reflect` và cung cấp **các phương thức static**; không dùng `new Array(...)`.

| API | Vai trò | Điểm quan trọng |
| --- | --- | --- |
| `Array.newInstance(Class<?> componentType, int length)` | Tạo mảng với kiểu thành phần và độ dài cho trước | Trả `Object`; kiểu runtime chính xác theo `componentType` |
| `Array.newInstance(Class<?> componentType, int... dimensions)` | Tạo mảng nhiều chiều | Các kích thước truyền vào được khởi tạo; chiều tổng cộng phụ thuộc cả `componentType` nếu nó đã là kiểu mảng |
| `Array.getLength(Object array)` | Đọc độ dài một mảng | Áp dụng cho `int[]` lẫn `Object[]`; không nhận object không phải mảng |
| `Array.get(Object array, int index)` | Lấy phần tử dạng `Object` | Giá trị primitive được **boxing** thành wrapper |
| `Array.set(Object array, int index, Object value)` | Ghi phần tử | Nếu mảng primitive, có bước unboxing và chỉ chấp nhận conversion hợp lệ |
| `Array.getInt(...)`, `getLong(...)`, `getBoolean(...)`, ... | Đọc phần tử theo kiểu primitive cụ thể | Có thể thực hiện primitive **widening** phù hợp; tránh boxing khi dùng đúng |
| `Array.setInt(...)`, `setLong(...)`, `setBoolean(...)`, ... | Ghi kiểu primitive cụ thể | Chỉ chấp nhận identity hoặc widening sang kiểu phần tử đích |

`getXxx/setXxx` có đủ biến thể cho tám kiểu primitive: `boolean`, `byte`, `char`, `short`, `int`, `long`, `float` và `double`.

**Mấu chốt:** không có một kiểu `Object[]` chung chứa được mọi mảng. `int[]` là `Object`, nhưng **không** phải `Object[]`, vì các phần tử của nó là giá trị primitive. `Array.getLength/get/set` giải quyết khoảng trống đó.

## 3. Tạo mảng một chiều từ kiểu runtime

### 3.1. Mảng tham chiếu

```java
Class<?> type = String.class;
Object dynamicNames = Array.newInstance(type, 2);
Array.set(dynamicNames, 0, "Java");
Array.set(dynamicNames, 1, "Reflection");

String[] names = (String[]) dynamicNames; // Chỉ cast khi đã xác thực kiểu runtime.
```

Đây là đoạn mã **minh họa, dùng trong ngữ cảnh đã import `java.lang.reflect.Array`**. `dynamicNames.getClass() == String[].class` trả `true`. Các phần tử mảng tham chiếu mới tạo mặc định là `null`.

Khi một kiểu đến từ tên đầy đủ trong cấu hình, có thể resolve `Class<?>` bằng `Class.forName("java.lang.String")` rồi truyền vào `Array.newInstance`. `Class.forName("int")` không phải cách tìm primitive `int`; primitive có class literal `int.class` (hoặc `Integer.TYPE`). Đừng nhận tên class tùy ý từ đầu vào không đáng tin rồi tự ý nạp mọi class trong ứng dụng.

### 3.2. Mảng primitive

```java
Object dynamicScores = Array.newInstance(int.class, 3);
Array.setInt(dynamicScores, 0, 10);
Array.set(dynamicScores, 1, Integer.valueOf(20));
int value = Array.getInt(dynamicScores, 1); // 20
```

Đây cũng là đoạn minh họa trong ngữ cảnh đã import `Array`. Kiểu runtime là `int[]`, không phải `Integer[]`. Phần tử `int[]` mới tạo mặc định là `0`. `Array.set` nhận `Integer` rồi unbox phù hợp vào `int`; `Array.get` sẽ trả `Integer` khi đọc một giá trị `int`.

Không làm thế này:

```java
Object array = Array.newInstance(int.class, 3);
Object[] wrong = (Object[]) array; // ClassCastException khi chạy!
```

Nếu biết chắc kiểu phần tử là `int` thì có thể cast sang `int[]` và dùng cú pháp trực tiếp. Nếu chưa biết kiểu lúc compile time, hãy tiếp tục dùng các API của `Array`.

### 3.3. Kiểm tra kiểu và độ dài

```java
Object array = Array.newInstance(String.class, 3);

Class<?> arrayClass = array.getClass();
boolean isArray = arrayClass.isArray();            // true
Class<?> elementClass = arrayClass.getComponentType(); // String.class
int length = Array.getLength(array);               // 3
```

Đoạn minh họa này có import `Array` như trên. `Class.getComponentType()` trả thành phần **của một chiều**; với `int[][]`, nó trả `int[].class`, không trả ngay `int.class`. Nếu cần kiểu cơ sở, lặp `getComponentType()` đến khi kết quả không còn là array class.

`Array.getLength(...)` trả **số phần tử ở chiều đang xét**, không tự đếm tất cả giá trị trong một cấu trúc nhiều chiều. Muốn biết độ dài của một hàng, lấy hàng đó bằng `Array.get(matrix, rowIndex)` rồi gọi `Array.getLength(row)`.

## 4. Đọc/ghi phần tử và các quy tắc chuyển đổi kiểu

### 4.1. `get` và `set` tổng quát

Với mọi mảng, `Array.get(array, i)` trả một `Object`. Nếu mảng chứa reference thì nhận reference tương ứng; nếu chứa primitive, giá trị được boxing thành `Integer`, `Double`, `Boolean`, ... Vì vậy thao tác tổng quát bằng `get/set` rất hữu ích cho framework, nhưng trong vòng lặp dày đặc có thể tạo chi phí boxing/unboxing.

`Array.set(array, i, value)` tôn trọng kiểu runtime của mảng. Ví dụ `String[]` chấp nhận `String` hoặc `null`, không chấp nhận một `Integer`. `int[]` chấp nhận `Integer` (unbox thành `int`), nhưng không nhận `Long` theo kiểu thu hẹp từ `long` xuống `int`.

### 4.2. `getXxx` và `setXxx` cho primitive

Có thể dùng phương thức có kiểu khi biết quan hệ chuyển đổi primitive:

| Lời gọi | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `Array.getInt(new short[] {7}, 0)` | Có | Đọc `short` và widen thành `int` |
| `Array.getLong(new int[] {7}, 0)` | Có | Đọc `int` rồi widen thành `long` |
| `Array.setInt(new long[1], 0, 7)` | Có | Ghi `int` vào thành phần `long` bằng widening |
| `Array.setLong(new int[1], 0, 7L)` | Không | `long → int` là narrowing; `IllegalArgumentException` |
| `Array.getInt(new Integer[] {7}, 0)` | Không | `getInt` áp dụng cho kiểu phần tử primitive có conversion phù hợp, không tự unbox `Integer[]` |
| `Array.setInt(new Integer[1], 0, 7)` | Không | `setInt` không tự biến typed primitive write thành gán vào wrapper array |
| `Array.set(new int[1], 0, null)` | Không | `null` không thể unbox thành `int` |

**Lưu ý:** widening là quy tắc chuyển đổi kiểu được hỗ trợ, không phải cam kết bảo toàn tuyệt đối mọi giá trị số khi chuyển sang floating point (ví dụ `long → float` có thể mất độ chính xác). `boolean` không widening sang kiểu số.

### 4.3. Exception phải dự phòng

| Tình huống | Lỗi thường gặp |
| --- | --- |
| `componentType == null` khi tạo mảng | `NullPointerException` |
| `componentType == void.class` | `IllegalArgumentException` |
| Kích thước âm | `NegativeArraySizeException` |
| Đọc độ dài/tương tác với object không phải mảng | `IllegalArgumentException` |
| Tham số mảng là `null` khi đọc/ghi/độ dài | `NullPointerException` |
| Index âm hoặc ≥ length | `ArrayIndexOutOfBoundsException` |
| Ghi sai kiểu phần tử, unboxing không hợp lệ hoặc narrowing | `IllegalArgumentException` |
| Cast một `int[]` sang `Object[]` | `ClassCastException` |

`Array.newInstance(componentType, dimensions)` cũng từ chối danh sách kích thước rỗng và mảng có tổng số chiều lớn hơn giới hạn JVM (255 chiều). Không nên dùng exception như nhánh điều khiển bình thường: hãy kiểm tra `array != null`, `getClass().isArray()`, độ dài/index, kiểu phần tử và tính hợp lệ của dữ liệu đầu vào trước.

## 5. Mảng nhiều chiều và mảng răng cưa

Trong Java, `int[][]` thực chất là “mảng các `int[]`”. Điều này giải thích vì sao reflection truy cập từng chiều như một mảng riêng.

### 5.1. Tạo sẵn tất cả chiều được chỉ định

```java
Object matrix = Array.newInstance(int.class, 2, 3); // Runtime: int[2][3]
Object secondRow = Array.get(matrix, 1);             // Runtime: int[3]
Array.setInt(secondRow, 2, 9);
int cell = Array.getInt(Array.get(matrix, 1), 2);    // 9
```

Đây là đoạn minh họa với import `Array`. Cấu trúc mới có 2 hàng, mỗi hàng 3 ô `int` mặc định `0`. Lấy một hàng qua `Array.get(matrix, 1)` rồi tiếp tục dùng API `Array`. Nếu biết chắc kiểu ở caller, có thể ép `matrix` sang `int[][]`.

### 5.2. Tạo mảng răng cưa (jagged array)

```java
Object rows = Array.newInstance(int[].class, 2); // Runtime: int[][]
// Ban đầu hai hàng đều là null, vì phần tử của mảng ngoài có kiểu int[].
Array.set(rows, 0, new int[] {1});
Array.set(rows, 1, new int[] {2, 3, 4});
```

`Array.newInstance(int[].class, 2)` tạo một `int[][]` có **hai reference tới các hàng**, ban đầu chưa được cấp phát hàng. Ta gán mảng con có độ dài khác nhau, tạo cấu trúc răng cưa. Ngược lại, `Array.newInstance(int.class, 2, 3)` đã cấp phát hàng độ dài 3 theo tất cả kích thước được truyền.

Khi `componentType` **đã là một kiểu mảng**, số chiều tổng cộng = số chiều của `componentType` + số kích thước truyền vào. Ví dụ `Array.newInstance(String[].class, 2)` tạo `String[][]`; `Array.newInstance(String[].class, 2, 3)` tạo `String[][][]` với hai chiều đầu được cấp phát và các mảng `String[]` ở tầng sau cùng ban đầu còn `null`.

Điều này có ích khi muốn dựng mảng nhiều chiều từ metadata, nhưng cần kiểm soát kích thước để tránh cấp phát bộ nhớ quá lớn.

## 6. Ví dụ hoàn chỉnh: tạo, đọc, ghi, thao tác và kiểm tra lỗi

Tạo file **`ReflectArrayDemo.java`**. Chương trình dưới đây chạy độc lập trên Java 17+ và dùng một hàm `reverseCopy` xử lý được cả mảng primitive lẫn mảng tham chiếu **mà không cast đầu vào thành `Object[]`**.

```java
import java.lang.reflect.Array;
import java.util.Arrays;

public class ReflectArrayDemo {
    static Object reverseCopy(Object source) {
        if (source == null || !source.getClass().isArray()) {
            throw new IllegalArgumentException("Expected an array");
        }

        Class<?> componentType = source.getClass().getComponentType();
        int length = Array.getLength(source);
        Object result = Array.newInstance(componentType, length);

        for (int i = 0; i < length; i++) {
            Array.set(result, i, Array.get(source, length - 1 - i));
        }
        return result;
    }

    public static void main(String[] args) {
        Object scores = Array.newInstance(int.class, 3);
        Array.setInt(scores, 0, 2);
        Array.set(scores, 1, Integer.valueOf(3));
        Array.setInt(scores, 2, 5);

        System.out.println("type=" + scores.getClass().getTypeName());
        System.out.println("length=" + Array.getLength(scores));
        System.out.println("values=" + Arrays.toString((int[]) scores));
        System.out.println("boxed=" + Array.get(scores, 1).getClass().getSimpleName());
        System.out.println("reverse=" + Arrays.toString((int[]) reverseCopy(scores)));

        Object tags = Array.newInstance(String.class, 2);
        Array.set(tags, 0, "JVM");
        Array.set(tags, 1, "Reflection");
        System.out.println("tags=" + Arrays.toString((String[]) tags));

        Object matrix = Array.newInstance(String.class, 2, 3);
        Array.set(Array.get(matrix, 1), 2, "X");
        System.out.println("matrix=" + Arrays.deepToString((Object[]) matrix));

        Object jagged = Array.newInstance(String[].class, 2);
        Array.set(jagged, 0, new String[] {"A"});
        Array.set(jagged, 1, new String[] {"B", "C"});
        System.out.println("jagged=" + Arrays.deepToString((Object[]) jagged));

        try {
            Array.set(scores, 0, Long.valueOf(7L));
        } catch (IllegalArgumentException expected) {
            System.out.println("narrowing=" + expected.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac --release 17 ReflectArrayDemo.java
java ReflectArrayDemo
```

**Stdout chính xác:**

```text
type=int[]
length=3
values=[2, 3, 5]
boxed=Integer
reverse=[5, 3, 2]
tags=[JVM, Reflection]
matrix=[[null, null, null], [null, null, X]]
jagged=[[A], [B, C]]
narrowing=IllegalArgumentException
```

### Phân tích từng kết quả

- `type=int[]` xác nhận `Array.newInstance(int.class, 3)` tạo **primitive array thật**, dù kết quả được giữ trong biến `Object`.
- `Array.getLength(scores)` hoạt động với `int[]`, không yêu cầu ép về `Object[]`.
- `Array.setInt` ghi trực tiếp `int`; `Array.set(..., Integer)` unbox thành `int`; `Array.get(scores, 1)` boxing thành `Integer` như dòng `boxed=Integer`.
- `reverseCopy` đọc `componentType` **từ chính mảng nguồn**, tạo mảng đích cùng kiểu, rồi sao chép ngược bằng `Array.get/set`. Nó hoạt động với `int[]`, `String[]`, `boolean[]` hoặc mảng reference khác. Hàm đảo **thứ tự phần tử của một chiều**; nếu phần tử là mảng con hoặc object, đây là sao chép reference ở cấp phần tử, không phải deep clone.
- `matrix` sử dụng `newInstance(String.class, 2, 3)`: mọi hàng 3 phần tử đã được tạo, giá trị reference mặc định `null`. `Arrays.deepToString` được dùng vì đối tượng `String[][]` có thể được nhìn dưới dạng `Object[]` ở chiều ngoài.
- `jagged` dùng `String[].class` làm component type: hai hàng chỉ được cấp phát khi chúng ta gán vào.
- Lời gọi cuối cố đưa `Long` vào phần tử `int`, yêu cầu narrowing từ `long` sang `int` nên ném `IllegalArgumentException`. Việc số `7` vẫn nằm trong miền `int` **không** khiến reflection tự động cho phép narrowing.

### Vì sao phương pháp `reverseCopy` giữ được kiểu thực?

Trường hợp đầu vào là `String[]`, `source.getClass().getComponentType() == String.class`, nên `Array.newInstance` cũng tạo `String[]`. Với `int[]`, component type là `int.class`, nên mảng mới cũng là `int[]`. Không dùng cách tạo `new Object[length]` vì như thế sẽ **làm mất kiểu mảng gốc** và không thể thay thế `int[]` hoặc `String[]` trong mọi ngữ cảnh.

Đây là chiến lược thường dùng khi framework nhận một `Object` được xác nhận là mảng: **khám phá kiểu thực → tạo mảng đúng kiểu → truy cập qua `Array` → chuyển sang kiểu cụ thể ở boundary nếu hợp đồng cho phép**.

## 7. Kết hợp với generic và các giới hạn cần hiểu

Khi code của bạn **biết kiểu tham chiếu thông qua `Class<T>`**, có thể tạo helper trả `T[]`:

```java
static <T> T[] newReferenceArray(Class<T> type, int length) {
    if (type == null || type.isPrimitive()) {
        throw new IllegalArgumentException("Expected a reference type");
    }
    @SuppressWarnings("unchecked")
    T[] result = (T[]) Array.newInstance(type, length);
    return result;
}

// Sử dụng trong một chương trình đã import java.lang.reflect.Array:
String[] names = newReferenceArray(String.class, 2);
```

Đây là **đoạn minh họa phải đặt trong class chứa static method**, không phải file Java độc lập. Dòng unchecked cast có cơ sở khi `type` là token chính xác của kiểu tham chiếu `T`; helper chặn primitive để tránh cast `int[]` thành mảng reference. Không dùng raw `Class` hay cast không an toàn để qua mặt hệ thống kiểu.

Chú ý phân biệt:

- `String[]` giữ kiểu phần tử ở runtime; gán `Integer` bằng một reference alias không đúng có thể bị JVM ngăn lại.
- `List<String>` chịu generic type erasure: reflection không thể tạo một “mảng của `List<String>`” có toàn bộ tham số generic được bảo đảm ở runtime chỉ bằng `List.class`.
- Mảng là **covariant**: `Object[] alias = new String[1]` biên dịch được, nhưng `alias[0] = Integer.valueOf(1)` sẽ ném `ArrayStoreException`. Reflection cũng kiểm tra phép gán theo kiểu thực, dù biểu hiện exception có thể khác theo API gọi.
- Không nên cố dùng `Object[]` để tổng quát hóa mọi array; primitive arrays là trường hợp phản ví dụ rõ nhất.

Nếu phải lưu một tập phần tử có thể thêm/xóa và **không cần đúng kiểu array runtime**, một `List<?>` hoặc collection có generic contract thường dễ bảo trì hơn. Array có độ dài cố định; muốn đổi độ dài phải tạo mảng mới rồi sao chép dữ liệu (ví dụ `System.arraycopy` nếu đã có hai mảng tương thích).

## 8. Trường hợp sử dụng thực tế và cách thiết kế

### 8.1. Serializer hoặc mapper theo schema

Một schema có thể khai báo “đây là mảng của `Customer`, `String` hoặc `double`”. Framework đọc component type, xác thực dữ liệu, cấp phát bằng `Array.newInstance` rồi điền từng phần tử. Đối với primitive, phải kiểm tra giá trị đầu vào có thể được chuyển đúng quy tắc, không dựa vào phép cast tùy tiện.

Luồng tiêu biểu:

1. Lấy `Class<?> componentType` từ metadata đã được **xác thực**.
2. Kiểm tra kích thước tối đa cho phép và cấp phát mảng bằng `newInstance`.
3. Với mỗi item, chuyển dữ liệu nguồn sang kiểu Java hợp lệ; kiểm tra `null`/primitive, reference assignability và chuyển đổi số.
4. Ghi bằng `Array.set` hoặc phương thức `setXxx` phù hợp; báo lỗi kèm vị trí item khi chuyển đổi không hợp lệ.
5. Trả mảng qua hợp đồng đã xác định; tránh để client phải tự đoán và ép kiểu.

### 8.2. Reflection với `Field` là kiểu mảng

Một field có thể mang metadata cho kiểu mảng:
- `Field.getType().isArray()` nhận biết nó là array field.
- `Field.getType().getComponentType()` lấy component type một chiều.
- `Array.newInstance(componentType, n)` tạo một mảng tương thích để gán cho field, **nếu** caller có quyền gán field, object nhận hợp lệ và dữ liệu đúng kiểu.

Phân biệt rõ `Field.get(obj)` / `Field.set(obj, value)` để lấy/gán **toàn bộ field**, với `Array.get(array, i)` / `Array.set(array, i, value)` để thao tác **từng phần tử** của array object. Access control của `Field` vẫn phải tuân thủ quy tắc Java/module; `Array` không mở được một private field bị chặn.

### 8.3. Plugin và cấu hình động

Có thể chọn loại phần tử theo plugin lúc runtime rồi tạo mảng phục vụ API cũ yêu cầu mảng có kiểu cụ thể. Nên thực hiện discovery/validation tại ranh giới plugin và giữ interface rõ ràng để phần logic nghiệp vụ không bị phân tán các thao tác phản chiếu.

## 9. Hiệu năng, bộ nhớ và các giới hạn vận hành

- `Array.get/set` dùng được cho mọi kiểu mảng, nhưng thao tác `Object` với mảng primitive có thể boxing/unboxing; đường gọi trực tiếp `int[]` hoặc API `getInt/setInt` có thể phù hợp hơn khi biết kiểu và tác vụ nhạy hiệu năng.
- `Array.newInstance` cấp phát mảng thực sự; kích thước lớn hoặc nhiều chiều có thể gây `OutOfMemoryError`. Hãy kiểm tra giới hạn số phần tử/kích thước từ dữ liệu cấu hình hoặc request.
- `int[]` lưu giá trị primitive; `Integer[]` lưu references đến wrapper objects. Hai kiểu **không tương đương** về API, khả năng null, chi phí cấp phát và truy cập.
- Với mảng nhiều chiều, tạo theo tất cả kích thước sẽ cấp phát các lớp mảng con tương ứng. Nếu muốn jagged array hoặc lazy allocation, chỉ tạo chiều ngoài rồi cấp phát các mảng con khi cần.
- Không tối ưu chỉ bằng suy đoán “reflection luôn chậm”. Dùng profiler hoặc benchmark phù hợp với workload; phần parse/config, chuyển đổi dữ liệu và cấp phát thường có thể chiếm phần lớn tổng chi phí.
- Không thay thế invariant, validation hay giới hạn tài nguyên của ứng dụng bằng `Array.set`: JVM chỉ bảo vệ các quy tắc kiểu và bounds ở mức array.

## 10. Lỗi/ngộ nhận thường gặp

1. **Ép mọi mảng về `Object[]`.** `String[]` làm được, nhưng `int[]`/`double[]` không; dùng `Array.getLength/get/set` khi chưa biết component type.
2. **Cho rằng `Array.newInstance(Object.class, n)` đủ thay cho mọi kiểu.** Nó chỉ tạo `Object[]`; không giữ kiểu `Customer[]` hay `int[]` mà API khác có thể yêu cầu.
3. **Lẫn lộn `int[]` với `Integer[]`.** Một cái lưu primitive, một cái lưu wrapper reference; `getInt/setInt` không mặc nhiên hoạt động với `Integer[]`.
4. **Dùng narrowing một cách ngầm định.** `Array.set(new int[1], 0, Long.valueOf(1))` vẫn sai, dù số nằm trong range của `int`.
5. **Truy cập mảng nhiều chiều như khối dữ liệu phẳng.** `Array.getLength(matrix)` chỉ trả chiều ngoài; lấy hàng rồi thao tác tiếp.
6. **Quên mảng ngoài có thể chứa hàng `null`.** `Array.newInstance(String[].class, 2)` tạo `String[][]` nhưng chưa cấp phát hai hàng `String[]`.
7. **Giả định reflect có thể vượt qua access control của `Field` hoặc loại bỏ quy tắc kiểu.** `Array` chỉ thao tác trên array object hợp lệ, còn metadata/member access tuân thủ các quy tắc riêng.
8. **Dùng array dù cần kích thước linh hoạt.** Mảng cố định; hãy dùng `List` nếu số phần tử thay đổi thường xuyên và API không bắt buộc mảng.

## 11. Tự kiểm tra

**Bài 1.** Đầu vào là `Class<?> c = int.class` và `length = 4`. Hãy tạo mảng, ghi các giá trị `1, 2, 3, 4` rồi tính tổng **mà không cast sang `int[]`**. Gợi ý: `Array.newInstance`, `Array.setInt`, `Array.getInt`. Tổng đúng là `10`.

**Bài 2.** So sánh:
- `Array.newInstance(double.class, 2, 3)`
- `Array.newInstance(double[].class, 2)`

Cả hai đều có runtime type `double[][]`, nhưng trường hợp đầu tạo sẵn hai hàng `double[3]`; trường hợp sau có hai hàng ban đầu là `null`.

**Bài 3.** Vì sao `Array.get(new long[] {4L}, 0)` có kiểu static là `Object`, còn `Array.getLong(new long[] {4L}, 0)` trả `long`? Trả lời: API thứ nhất là generic accessor nên boxing thành `Long`; API thứ hai là primitive accessor.

**Bài 4.** Viết một `copyOf(Object source, int newLength)` tự tạo array có component type đúng, sao chép `min(oldLength, newLength)` phần tử và xử lý dữ liệu đầu vào không phải mảng. Đối chiếu với `java.util.Arrays.copyOf` cho những kiểu đã biết. Khi API cho phép, `System.arraycopy` là cách sao chép vùng mảng hiệu quả; cần xác minh kiểu mảng tương thích.

## Tài liệu chính thức

- [Java SE 17 API — java.lang.reflect.Array](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html)
- [Oracle Java Tutorials — Arrays và Reflection](https://docs.oracle.com/javase/tutorial/reflect/special/array.html)

## Kết luận

`java.lang.reflect.Array` là công cụ chuẩn khi **biết kiểu thành phần ở runtime nhưng cần tạo và thao tác đúng kiểu array của JVM**. Hãy lấy `Class<?>` từ nguồn đáng tin, tạo mảng bằng `newInstance`, đọc/ghi bằng `get/set` hoặc các biến thể primitive, kiểm tra index/conversion và phân biệt mảng nhiều chiều đã cấp phát với mảng răng cưa. Sau khi hoàn tất phần tích hợp động, ưu tiên trả về một hợp đồng có kiểu rõ ràng cho lớp nghiệp vụ.
