# Giới hạn tạo mảng kiểu tham số hóa

## 1. Vì sao new String[] được nhưng new List<String>[] không được?

Mảng và generic bảo vệ kiểu theo hai cơ chế khác nhau:

- **Mảng** giữ kiểu thành phần tại lúc chạy. Một đối tượng `String[]` biết nó là mảng của `String`.
- **Generic** kiểm tra đối số kiểu chủ yếu tại lúc biên dịch. Sau xóa kiểu, `List<String>` và `List<Integer>` không trở thành hai lớp `List` runtime riêng.

Vì vậy, Java cho phép:

```java
String[] names = new String[3];
```

Nhưng không cho phép tạo trực tiếp:

```java
// List<String>[] groups = new List<String>[3]; // Loi: generic array creation
```

Trong một lớp generic, cũng không được viết:

```java
class Buffer<T> {
    // T[] values = new T[3]; // Loi: generic array creation
}
```

Các dòng bị chú thích là những biểu thức cố ý không hợp lệ. Giới hạn này vẫn tồn tại trong Java hiện nay; nó không phải một quy tắc chỉ liên quan tới phiên bản Java cũ.

Bài tập trung vào việc **tạo đối tượng mảng**, lý do bị giới hạn và các lựa chọn có thể dùng trong mã Java 17 trở lên.

## 2. Kiểu có thể biểu diễn đầy đủ lúc chạy: reifiable type

Một kiểu **có thể biểu diễn đầy đủ lúc chạy (reifiable type)** còn đủ thông tin cần thiết trong runtime để xác định kiểu đó theo các quy tắc của Java.

Các ví dụ quan trọng:

| Kiểu | Có tính reifiable? | Hệ quả đối với tạo mảng |
| --- | --- | --- |
| `String` | Có | Tạo được `new String[n]` |
| `Integer` | Có | Tạo được `new Integer[n]` |
| `int` | Có | Tạo được `new int[n]` |
| `List<String>` | Không | Không tạo trực tiếp `new List<String>[n]` |
| `T` là tham số kiểu | Không | Không tạo trực tiếp `new T[n]` |
| `List<?>` | Có | Tạo được `new List<?>[n]` |
| `List<? extends Number>` | Không | Không tạo trực tiếp mảng có kiểu thành phần này |

Đối với kiểu generic có đối số kiểu, trường hợp tất cả đối số là wildcard không giới hạn như `List<?>` đáp ứng quy tắc reifiable. Việc “có dấu `?`” nói chung không đủ: giới hạn cụ thể như `? extends Number` không còn là trường hợp đó.

Theo [JLS: Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.10.1), kiểu thành phần dùng để tạo mảng phải đáp ứng điều kiện reifiable liên quan. Khái niệm này được định nghĩa trong [JLS: Reifiable Types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.7).

Không nên diễn giải thành “generic không bao giờ đi cùng mảng”. Cần xét chính xác kiểu nào được khai báo và kiểu nào đang được dùng trong biểu thức `new`.

## 3. Tại sao mảng cần biết kiểu thành phần?

Mảng kiểu tham chiếu có tính **hiệp biến (covariance)**. Nếu `String` là kiểu con của `Object`, thì `String[]` có thể được gán cho `Object[]`.

Đoạn minh họa sau biên dịch được:

```java
Object[] values = new String[1];
// values[0] = 123; // Neu chay: ArrayStoreException
```

Kiểu tĩnh của `values` là `Object[]` nên trình biên dịch cho phép một phép gán `Integer` qua tham chiếu đó. Nhưng đối tượng mảng thực tế vẫn là `String[]`.

Khi thực hiện phép ghi, runtime phát hiện `Integer` không phù hợp với kiểu thành phần `String` và ném `ArrayStoreException`.

Dòng thời gian:

```text
Bien Object[] tham chieu doi tuong String[]
        |
        | ghi mot Integer
        v
Kiem tra kieu thanh phan runtime: String
        |
        v
Tu choi bang ArrayStoreException
```

Việc kiểm tra này là một phần cơ chế an toàn kiểu của mảng. Nó cần kiểu thành phần thực sự có thể được kiểm tra lúc chạy.

## 4. Điều gì sẽ sai nếu được tạo List<String>[]?

Xét chuỗi thao tác **giả định** sau. Mã không biên dịch ngay ở dòng tạo mảng:

```java
// Minh hoa gia dinh; Java khong cho phep dong new nay.
List<String>[] textGroups = new List<String>[1];
Object[] alias = textGroups;
alias[0] = List.of(123);
String text = textGroups[0].get(0);
```

Nếu tạo được mảng như vậy:

1. Theo quan hệ kiểu của mảng, nó có thể được nhìn qua `Object[]`.
2. Đối tượng `List.of(123)` là một danh sách số nguyên.
3. Runtime có thể nhận biết nó là một `List`, nhưng không có một kiểu lớp runtime riêng `List<String>` để dùng cho kiểm tra ghi mảng.
4. Một danh sách số nguyên có thể lọt vào vị trí mà người dùng `textGroups` tin là `List<String>`.
5. Khi lấy phần tử như `String`, phép kiểm tra ép kiểu có thể thất bại.

Tình trạng một biến có kiểu tham số hóa tham chiếu tới dữ liệu không phù hợp với hợp đồng kiểu của nó liên quan tới **ô nhiễm vùng nhớ kiểu (heap pollution)**.

Java chặn biểu thức tạo mảng không reifiable để ngăn lỗ hổng này trong cách sử dụng thông thường được kiểm tra đầy đủ.

Điểm khác với `String[]`: runtime có thể phân biệt một `String` với `Integer`, nhưng không thể chỉ dựa trên lớp `List` để chứng minh toàn bộ danh sách chứa `String`.

## 5. Khai báo kiểu mảng và tạo mảng là hai việc khác nhau

Các khai báo dưới đây hợp lệ:

```java
class Container<T> {
    T[] values;
    List<String>[] groups;
}
```

Đây là đoạn khai báo minh họa, cần import `java.util.List`. Các trường chưa được cấp đối tượng mảng mới.

Giới hạn không phải là “cấm viết `T[]` hoặc `List<String>[]` ở mọi nơi”. Nó nằm ở biểu thức tạo mảng như `new T[n]` hoặc `new List<String>[n]`.

Một phương thức generic có thể nhận mảng đã được tạo với kiểu cụ thể ở bên gọi:

```java
static <T> T first(T[] values) {
    return values[0];
}
```

Ví dụ sử dụng trong một phương thức:

```java
String[] words = {"alpha", "beta"};
String firstWord = first(words);
```

Trong trường hợp này, đối tượng mảng được tạo với kiểu thành phần cụ thể `String`. Phương thức generic chỉ nhận và đọc nó.

Hợp đồng của `first` vẫn cần nêu điều kiện mảng khác `null` và có ít nhất một phần tử; generic không tự bảo đảm kích thước.

Ngay cả `T extends Number` cũng không cho phép `new T[n]`. Biết `T` thuộc họ `Number` không có nghĩa biết `T` cụ thể là `Integer`, `Double` hay một kiểu khác.

## 6. Trường hợp hợp lệ: mảng List<?>[]

Có thể tạo:

```java
List<?>[] groups = new List<?>[2];
groups[0] = List.of("text");
groups[1] = List.of(7);
```

Tại mỗi vị trí, `List<?>` chỉ cam kết đó là một danh sách có kiểu phần tử chưa biết. Việc một vị trí chứa `List<String>` và vị trí khác chứa `List<Integer>` không vi phạm hợp đồng.

Khi đọc:

```java
Object first = groups[0].get(0);
// String text = groups[0].get(0); // Khong bien dich neu khong kiem tra them
```

Nó không phải một cách tạo `List<String>[]` được bảo đảm an toàn. Đổi kết quả thành kiểu mảng mạnh hơn bằng một phép ép kiểu không được kiểm tra sẽ đưa trở lại điều cần chứng minh.

Tính reifiable ở đây cũng không cho phép ghi mọi đối tượng vào mảng. Đối tượng mảng vẫn có kiểu thành phần runtime là `List`; nếu nhìn qua `Object[]` rồi ghi một chuỗi trực tiếp vào vị trí mảng, runtime sẽ từ chối vì chuỗi không phải `List`.

### Đừng biến wildcard thành một bước trung gian để ép kiểu

Không nên coi “tạo `List<?>[]` rồi ép thành `List<String>[]`” là tương đương với việc tạo một mảng runtime có thể kiểm tra danh sách chuỗi. Runtime vẫn chỉ biết kiểu thành phần là `List`.

Nếu cần bảo đảm mọi nhóm có phần tử `String`, cấu trúc như `List<List<String>>` thường phù hợp hơn.

## 7. Cách thay thế thứ nhất: dùng List thay vì mảng generic

Nếu không bị một API yêu cầu mảng, hãy cân nhắc:

```java
List<List<String>> rows = new ArrayList<>();
rows.add(List.of("An", "Binh"));
rows.add(List.of("Chi"));
```

Trình biên dịch kiểm tra phần tử ngoài là `List<String>`. Thêm một `List<Integer>` vào `rows` không được chấp nhận trong cách sử dụng generic thông thường.

Ưu điểm:

- Không cần tạo mảng có kiểu thành phần không reifiable.
- Giữ quan hệ kiểu giữa các tầng.
- Không cần phép ép kiểu không được kiểm tra.
- Dễ tăng giảm số nhóm.

Đây không phải khẳng định rằng mọi mảng phải đổi sang `List`. Mảng vẫn hữu ích khi API yêu cầu mảng, cần kích thước cố định hoặc cần làm việc trực tiếp với mảng nguyên thủy. Hãy chọn theo yêu cầu dữ liệu.

## 8. Cách thay thế thứ hai: để bên gọi cung cấp cách tạo mảng

Khi đã có tập hợp phần tử, dùng một hàm tạo mảng có kiểu thành phần cụ thể:

```java
List<String> words = List.of("alpha", "beta");
String[] result = words.toArray(String[]::new);
```

`String[]::new` biết cách tạo đối tượng `String[]`. Kiểu thành phần cụ thể được cung cấp bởi biểu thức của bên gọi, thay vì yêu cầu phương thức generic tự tạo `new T[n]`.

Một phương thức tiện ích có thể nhận `IntFunction<T[]>`:

```java
static <T> T[] copyToArray(
        List<T> source,
        IntFunction<T[]> arrayFactory) {
    return source.toArray(arrayFactory);
}
```

Đây là khai báo minh họa trong lớp có import `List` và `IntFunction`. `IntFunction` nhận độ dài kiểu `int` và tạo mảng. Bản đầy đủ có trong chương trình bên dưới.

Không viết hàm tạo với giả định nó chỉ được gọi đúng một lần hoặc luôn nhận đúng `source.size()`; hãy cung cấp một hàm tạo mảng thông thường theo hợp đồng `toArray`.

### Không ép kết quả toArray() không đối số thành String[]

```java
List<String> words = List.of("alpha", "beta");
// String[] wrong = (String[]) words.toArray(); // ClassCastException
```

`toArray()` không đối số tạo `Object[]`. Một `Object[]` đang chứa các chuỗi không vì thế trở thành đối tượng `String[]`.

### Hàm tạo sai kiểu vẫn có thể gây lỗi lúc chạy

API `Collection.toArray(IntFunction<T[]>)` có tham số kiểu của riêng phương thức. Vì vậy, lời gọi trực tiếp sau có thể biên dịch:

```java
List<String> words = List.of("alpha", "beta");
// Integer[] wrong = words.toArray(Integer[]::new); // ArrayStoreException
```

Mảng đích không chứa được các chuỗi của nguồn. Khi chuyển phần tử, runtime phát hiện sự không tương thích.

Do đó, dùng hàm tạo không có nghĩa mọi lựa chọn hàm tạo đều đúng. Phải cung cấp kiểu mảng phù hợp với dữ liệu. Hợp đồng được mô tả trong [Collection.toArray](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)).

## 9. Cách thay thế thứ ba: Class<T> và tạo mảng bằng reflection

Khi chỉ có độ dài và một kiểu lớp cụ thể, có thể dùng `Array.newInstance`.

Ví dụ tạo mảng tham chiếu:

```java
static <T> T[] newReferenceArray(Class<T> componentType, int length) {
    Objects.requireNonNull(componentType, "componentType");
    if (componentType.isPrimitive()) {
        throw new IllegalArgumentException("reference component required");
    }
    @SuppressWarnings("unchecked")
    T[] result = (T[]) Array.newInstance(componentType, length);
    return result;
}
```

Ở đây có một phép ép kiểu không được kiểm tra, nhưng nó được đặt trong phạm vi nhỏ và có lập luận cụ thể:

- `Array.newInstance` tạo mảng với đúng kiểu thành phần do `componentType` chỉ ra.
- `Class<T>` liên kết kiểu thành phần được truyền vào với `T` của kết quả.
- Helper chỉ hỗ trợ kiểu thành phần tham chiếu; kiểm tra `isPrimitive()` ngăn việc tạo `int[]` rồi coi nó như một mảng `T[]` của generic.
- Không dùng phép ép để giả vờ một `Object[]` đã trở thành `String[]`.

Kiểm tra kiểu nguyên thủy là cần thiết vì các biểu thức như `int.class` có thể đi vào API dùng `Class<T>` với kiểu wrapper tương ứng ở hệ generic. Mảng `int[]` không phải `Integer[]` và cũng không phải `Object[]`.

Ví dụ:

```java
String[] names = newReferenceArray(String.class, 2);
```

Điều này tạo đúng `String[]`.

Ngược lại, không có class literal `List<String>.class`. `List.class` không mang đối số `String` để runtime kiểm tra toàn bộ thành phần của từng danh sách. Reflection không tự phục hồi đối số kiểu đã xóa.

`length` âm vẫn gây `NegativeArraySizeException` theo hợp đồng tạo mảng. Helper không tạo cơ chế thay đổi kích thước hay tự khởi tạo phần tử; các vị trí mảng tham chiếu mới có giá trị `null`.

Xem [Array.newInstance](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Array.html#newInstance(java.lang.Class,int)).

## 10. Chương trình đầy đủ: đối chiếu các giải pháp và lỗi runtime

Lưu thành `GenericArrayLimitsDemo.java`:

```java
import java.lang.reflect.Array;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.IntFunction;

public class GenericArrayLimitsDemo {
    static <T> T[] copyToArray(
            List<T> source, IntFunction<T[]> arrayFactory) {
        return source.toArray(arrayFactory);
    }

    static <T> T[] newReferenceArray(Class<T> componentType, int length) {
        Objects.requireNonNull(componentType, "componentType");
        if (componentType.isPrimitive()) {
            throw new IllegalArgumentException("reference component required");
        }
        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(componentType, length);
        return result;
    }

    public static void main(String[] args) {
        List<List<String>> rows = new ArrayList<>();
        rows.add(List.of("An", "Binh"));
        rows.add(List.of("Chi"));
        System.out.println("rows = " + rows);

        List<?>[] mixedGroups = new List<?>[2];
        mixedGroups[0] = List.of("text");
        mixedGroups[1] = List.of(7);
        System.out.println("mixed groups = " + Arrays.toString(mixedGroups));

        List<String> words = List.of("alpha", "beta");
        String[] copied = copyToArray(words, String[]::new);
        System.out.println("copied = " + Arrays.toString(copied));
        System.out.println("copied component = "
                + copied.getClass().getComponentType().getTypeName());

        String[] allocated = newReferenceArray(String.class, 2);
        allocated[0] = "left";
        allocated[1] = "right";
        System.out.println("allocated = " + Arrays.toString(allocated));

        Object[] covariant = new String[1];
        try {
            covariant[0] = 7;
        } catch (ArrayStoreException exception) {
            System.out.println("wrong element rejected");
        }

        try {
            String[] wrong = (String[]) words.toArray();
            System.out.println(wrong.length);
        } catch (ClassCastException exception) {
            System.out.println("Object[] cannot become String[]");
        }

        try {
            Integer[] wrong = words.toArray(Integer[]::new);
            System.out.println(wrong.length);
        } catch (ArrayStoreException exception) {
            System.out.println("wrong array factory rejected");
        }

        try {
            newReferenceArray(int.class, 2);
        } catch (IllegalArgumentException exception) {
            System.out.println("primitive component rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all GenericArrayLimitsDemo.java
java GenericArrayLimitsDemo
```

Stdout:

```text
rows = [[An, Binh], [Chi]]
mixed groups = [[text], [7]]
copied = [alpha, beta]
copied component = java.lang.String
allocated = [left, right]
wrong element rejected
Object[] cannot become String[]
wrong array factory rejected
primitive component rejected
```

Giải thích:

1. `rows` thể hiện các nhóm chuỗi bằng `List<List<String>>`.
2. `mixedGroups` là `List<?>[]` hợp lệ; các nhóm có thể chứa kiểu phần tử khác nhau.
3. `copyToArray(words, String[]::new)` tạo `String[]` thật, thể hiện qua `getComponentType()`.
4. Helper reflection tạo mảng mới với kiểu thành phần `String`.
5. Ghi `Integer` vào đối tượng `String[]` qua tham chiếu `Object[]` gây `ArrayStoreException`.
6. Ép `Object[]` từ `toArray()` thành `String[]` gây `ClassCastException`.
7. Yêu cầu `Integer[]` để chứa các chuỗi gây `ArrayStoreException`.
8. Helper từ chối `int.class` theo hợp đồng chỉ tạo mảng tham chiếu.

Các ngoại lệ được bắt để chương trình minh họa tiếp tục chạy. Trong mã ứng dụng, nên chọn đúng kiểu dữ liệu và đúng hàm tạo ngay từ đầu.

## 11. Vì sao (T[]) new Object[n] không phải lời giải tổng quát?

Phép ép kiểu không thay đổi loại đối tượng mảng đã được cấp phát.

`new Object[n]` tạo một `Object[]`. Dù thêm phép ép sang `T[]` và tắt cảnh báo, đối tượng runtime vẫn là `Object[]`.

Một helper tự nhận trả `String[]` thông qua việc suy luận `T = String` có thể chỉ trả được `Object[]` rồi thất bại ở phép ép do bên gọi cần `String[]`. Nếu `T` có giới hạn như `Number`, lỗi còn có thể xuất hiện ngay khi ép một `Object[]` sang `Number[]` trong helper.

Đây là lý do không nên sửa lỗi `new T[n]` bằng một công thức ép kiểu áp dụng mọi nơi.

Một cấu trúc generic có thể dùng `Object[]` như **bộ nhớ nội bộ** nếu chứng minh và bảo vệ các quy tắc ghi/đọc của riêng nó, không để lộ nó như một `T[]` giả. Thiết kế đó có trách nhiệm khác với API hứa trả một mảng có kiểu thành phần runtime cụ thể.

Nếu cần trả `T[]` thật, hãy nhận hàm tạo mảng, nhận một mảng mẫu phù hợp hoặc nhận `Class<T>` theo hợp đồng rõ ràng.

## 12. Chọn cách nào?

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Nhiều nhóm dữ liệu có cùng kiểu phần tử generic | `List<List<T>>` |
| Các vị trí có thể chứa danh sách khác kiểu phần tử | `List<?>[]` khi thực sự cần mảng |
| Chuyển một tập hợp chuỗi thành mảng chuỗi | `toArray(String[]::new)` |
| Thuật toán generic cần bên gọi quyết định loại mảng | Nhận `IntFunction<T[]>` |
| Chỉ biết kiểu lớp thành phần lúc chạy | `Class<T>` và `Array.newInstance` với hợp đồng chặt |
| Dữ liệu nguyên thủy như `int` cần mảng | `int[]` trực tiếp; không coi đó là `Integer[]` |

Các tham số `T...` trong phương thức varargs là một chủ đề liên quan: chúng có thể đưa mảng của kiểu không reifiable vào quá trình gọi và sinh cảnh báo. Điều đó không cấp quyền viết `new T[n]` trong thân phương thức. Không dùng `@SafeVarargs` như một cách làm cho biểu thức tạo mảng bị cấm trở nên hợp lệ.

## 13. Tự kiểm tra

### Bài 1: Khai báo và cấp phát

Trong một lớp generic, `T[] values;` và `values = new T[3];` có cùng tình trạng hợp lệ không?

**Đáp án:** không. Khai báo biến kiểu `T[]` hợp lệ; biểu thức `new T[3]` bị cấm vì `T` không reifiable.

### Bài 2: Mảng wildcard

Có thể tạo `new List<?>[3]` không? Có thể đọc phần tử bên trong một danh sách rồi gán trực tiếp cho `String` không?

**Đáp án:** tạo được. Nhưng đọc qua `List<?>` chỉ bảo đảm kiểu tổng quát `Object`; không tự có quyền coi phần tử là `String`.

### Bài 3: T extends Number

Đổi `<T>` thành `<T extends Number>` có cho phép `new T[3]` không?

**Đáp án:** không. Kiểu cụ thể vẫn chưa được biết. `new Number[3]` tạo `Number[]`, không phải tự động tạo một `Integer[]` nếu bên gọi chọn `T = Integer`.

### Bài 4: Tất cả phần tử là String có đủ để ép Object[] không?

**Đáp án:** không. Một đối tượng `Object[]` chứa toàn chuỗi vẫn có loại mảng runtime là `Object[]`. Phải cấp phát `String[]` thật hoặc dùng API chuyển đổi có hàm tạo phù hợp.

### Bài 5: Tại sao helper reflection phải loại kiểu nguyên thủy?

**Đáp án:** `Array.newInstance(int.class, n)` tạo `int[]`. Generic `T[]` mô tả mảng kiểu tham chiếu, không thể biến `int[]` thành `Integer[]`. Kiểm tra giúp helper giữ đúng hợp đồng đã công bố.

Khi gặp lỗi tạo mảng generic, hãy hỏi đối tượng mảng phải mang kiểu thành phần runtime nào và ai có thông tin để cung cấp kiểu đó. Câu trả lời thường dẫn tới cấu trúc `List`, một hàm tạo mảng từ bên gọi hoặc một token `Class<T>` có giới hạn rõ ràng.
