# Array.newInstance với kiểu thành phần xác định lúc chạy

## 1. Từ một đối tượng Class đến một mảng thật

Khi viết `new String[3]`, ta đã chỉ rõ kiểu `String` trong mã nguồn. Nhưng một bộ chuyển đổi dữ liệu, công cụ kiểm thử hoặc thư viện xử lý nhiều loại đối tượng có thể chỉ nhận được một `Class<?>` lúc chương trình đang chạy. Khi đó, `java.lang.reflect.Array.newInstance` tạo mảng dựa trên đối tượng `Class` ấy.

Ở đây, **kiểu thành phần (component type)** là kiểu của mỗi ô trực tiếp trong mảng. Với `String[]`, đó là `String`; với `String[][]`, đó là `String[]`. Bài học tập trung vào việc chọn đúng kiểu và cấp phát đúng hình dạng mảng.

“Mảng động” trong ngữ cảnh này nghĩa là **quyết định kiểu hoặc kích thước khi chạy**. Mảng được tạo vẫn có độ dài cố định. Muốn thêm phần tử vượt độ dài cũ, ta phải tạo mảng khác và sao chép dữ liệu, hoặc dùng cấu trúc như `ArrayList`.

Ví dụ minh họa trong một phương thức, với import `java.lang.reflect.Array`:

~~~java
Class<?> componentType = String.class;
Object result = Array.newInstance(componentType, 3);
~~~

Kết quả là một đối tượng có kiểu thực tế `String[]`, dù biến `result` được khai báo là `Object`. Đây là **cấp phát mảng**, không chỉ là truy vấn thông tin về một kiểu.

## 2. Hợp đồng của hai overload

Hai dạng sử dụng chính:

~~~java
Array.newInstance(Class<?> componentType, int length)
Array.newInstance(Class<?> componentType, int... dimensions)
~~~

Đoạn trên biểu diễn cách gọi API, không phải khai báo phương thức đầy đủ để biên dịch.

- `componentType` mô tả kiểu dùng để tạo mảng.
- `length` là độ dài của một chiều mới.
- `dimensions` cho biết độ dài của các chiều mới.
- Giá trị trả về có kiểu khai báo `Object`, còn kiểu mảng thực tế được quyết định bởi đầu vào.

Bảng đọc nhanh:

| Lời gọi | Kiểu thực tế | Nội dung ngay sau khi tạo |
| --- | --- | --- |
| `Array.newInstance(String.class, 3)` | `String[]` | Ba ô chứa `null` |
| `Array.newInstance(int.class, 3)` | `int[]` | Ba ô chứa `0` |
| `Array.newInstance(Integer.class, 3)` | `Integer[]` | Ba ô chứa `null` |
| `Array.newInstance(Runnable.class, 2)` | `Runnable[]` | Hai ô chứa `null` |
| `Array.newInstance(String.class, 2, 3)` | `String[][]` | Hai mảng con, mỗi mảng có ba ô `null` |
| `Array.newInstance(String[].class, 2)` | `String[][]` | Hai ô ngoài chứa `null`; chưa tạo mảng con |

Lời gọi với một số nguyên, chẳng hạn `newInstance(String.class, 3)`, dùng overload `int length`. Muốn truyền các kích thước như một giá trị, có thể dùng `newInstance(String.class, new int[] {2, 3})`.

Không viết `new componentType[3]`: một biến kiểu `Class<?>` không thể thay thế tên kiểu trong cú pháp `new T[n]`.

## 3. Ví dụ chạy được: cùng một luồng xử lý, hai kiểu mảng

Lưu thành `DynamicArrayCreationDemo.java`. Chương trình dùng một tham số dòng lệnh để chọn kiểu thành phần khi chạy:

~~~java
import java.lang.reflect.Array;

public class DynamicArrayCreationDemo {
    private static Class<?> selectComponentType(String choice) {
        return switch (choice) {
            case "text" -> String.class;
            case "count" -> int.class;
            default -> throw new IllegalArgumentException(
                    "Expected text or count");
        };
    }

    public static void main(String[] args) {
        String choice = args.length == 0 ? "text" : args[0];
        Class<?> componentType = selectComponentType(choice);
        Object array = Array.newInstance(componentType, 3);

        System.out.println("type=" + array.getClass().getTypeName());
        System.out.println("component="
                + array.getClass().getComponentType().getTypeName());
        System.out.println("length=" + Array.getLength(array));
        System.out.println("default[0]=" + Array.get(array, 0));

        if (componentType == int.class) {
            Array.setInt(array, 0, 7);
        } else {
            Array.set(array, 0, "Lan");
        }

        System.out.println("value[0]=" + Array.get(array, 0));
        System.out.println("is Object[]=" + (array instanceof Object[]));
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 DynamicArrayCreationDemo.java
java DynamicArrayCreationDemo text
~~~

Kết quả:

~~~text
type=java.lang.String[]
component=java.lang.String
length=3
default[0]=null
value[0]=Lan
is Object[]=true
~~~

Chạy lại với lựa chọn còn lại:

~~~bash
java DynamicArrayCreationDemo count
~~~

Kết quả:

~~~text
type=int[]
component=int
length=3
default[0]=0
value[0]=7
is Object[]=false
~~~

Hãy đọc ví dụ theo ba bước:

1. `selectComponentType` quyết định đối tượng `Class` từ dữ liệu đầu vào.
2. `Array.newInstance` dùng kiểu đó để tạo mảng có ba ô, với giá trị mặc định tương ứng.
3. `Array.getLength`, `Array.get` và `Array.setInt`/`Array.set` thao tác trên mảng qua biến `Object`.

Phần ghi và đọc phần tử chỉ nhằm chứng minh mảng đã được tạo đúng kiểu. Việc tạo mảng không tự điền các giá trị nghiệp vụ như `"Lan"` hoặc `7`.

Cách chọn kiểu trong ví dụ là một danh sách lựa chọn nhỏ, dễ kiểm soát. Trong ứng dụng thật, `Class<?>` còn có thể đến từ tham số phương thức, metadata của một field hoặc kiểu thực tế của một mảng có sẵn. Cần xác định rõ nguồn nào là hợp đồng đúng cho dữ liệu đang xử lý.

## 4. Vì sao kết quả là Object, và khi nào ép kiểu được?

Mảng nguyên thủy như `int[]` cũng là một đối tượng, nên có thể gán cho biến `Object`. Nhưng `int[]` **không phải** là `Object[]`. Các phần tử của nó là giá trị `int`, không phải các tham chiếu đối tượng.

Các đoạn sau là minh họa trong một phương thức có import `java.lang.reflect.Array`:

~~~java
Object raw = Array.newInstance(int.class, 2);
int[] numbers = (int[]) raw;       // Hop le: kieu thuc te la int[].
// Object[] wrong = (Object[]) raw; // Neu chay: ClassCastException.
~~~

Ngược lại:

~~~java
Object raw = Array.newInstance(String.class, 2);
String[] names = (String[]) raw;  // Hop le: kieu thuc te la String[].
Object[] references = names;     // String[] la mot loai Object[].
~~~

Phép ép kiểu không chuyển đổi mảng này thành mảng khác. Nó chỉ kiểm tra xem đối tượng hiện có có phù hợp với kiểu đích hay không. Vì thế:

- Nếu mã gọi biết chắc hợp đồng trả về là `String[]`, có thể ép về `String[]`.
- Nếu mã gọi phải hỗ trợ cả `String[]`, `int[]`, `boolean[]` và các kiểu khác, nên giữ biến `Object` rồi dùng API `Array`.
- Muốn biến `int[]` thành `Integer[]`, phải tạo mảng đích và chuyển từng giá trị; ép kiểu không làm việc đóng hộp cho toàn bộ mảng.

`Array.get` trả về `Object`; khi đọc từ mảng nguyên thủy, giá trị được đóng hộp. Điều đó giải thích vì sao lệnh in trong ví dụ có thể xử lý cả hai loại mảng, nhưng **không biến `int[]` thành mảng tham chiếu**.

Kiểu `int.class` và `Integer.class` là hai đầu vào khác nhau. Chọn nhầm chúng sẽ tạo sai loại mảng ngay từ bước cấp phát.

## 5. Mảng nhiều chiều: phân biệt kiểu và các mảng con đã được tạo

Java biểu diễn mảng nhiều chiều bằng mảng chứa các tham chiếu đến mảng con. Vì vậy, cần trả lời riêng hai câu hỏi:

1. Đối tượng ngoài cùng có kiểu gì?
2. Những mảng con nào đã được cấp phát, với độ dài bao nhiêu?

Nếu kiểu đầu vào đã có `k` chiều và lời gọi bổ sung `d` kích thước, kiểu kết quả có `k + d` chiều. Các chiều đã có trong kiểu đầu vào không tự được cấp phát thành mảng con.

Ví dụ:

| Đầu vào | Kiểu kết quả | Phần được cấp phát |
| --- | --- | --- |
| `String.class, 2, 3` | `String[][]` | Mảng ngoài dài 2 và hai mảng `String[]` dài 3 |
| `String[].class, 2` | `String[][]` | Mảng ngoài dài 2; mỗi ô đang là `null` |
| `String[].class, 2, 3` | `String[][][]` | Mảng ngoài dài 2, các mảng tầng tiếp theo dài 3; các ô chứa `String[]` ở tầng ấy vẫn là `null` |

Đừng truyền `String[].class` khi ý định là tạo một `String[]`. Đầu vào đó đã là một kiểu mảng; thêm một chiều sẽ tạo `String[][]`.

Lưu chương trình sau thành `ArrayDimensionsDemo.java`:

~~~java
import java.lang.reflect.Array;
import java.util.Arrays;

public class ArrayDimensionsDemo {
    public static void main(String[] args) {
        Object rectangular = Array.newInstance(String.class, 2, 3);
        Object outerOnly = Array.newInstance(String[].class, 2);

        System.out.println("rect.type="
                + rectangular.getClass().getTypeName());
        System.out.println("rect.component="
                + rectangular.getClass().getComponentType().getTypeName());
        System.out.println("rect.rows=" + Array.getLength(rectangular));
        System.out.println("rect.row0.length="
                + Array.getLength(Array.get(rectangular, 0)));
        System.out.println("rect.values="
                + Arrays.deepToString((Object[]) rectangular));

        System.out.println("outer.type="
                + outerOnly.getClass().getTypeName());
        System.out.println("outer.row0=" + Array.get(outerOnly, 0));

        Array.set(outerOnly, 0, new String[] {"A"});
        System.out.println("outer.values="
                + Arrays.deepToString((Object[]) outerOnly));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ArrayDimensionsDemo.java
java ArrayDimensionsDemo
~~~

Kết quả:

~~~text
rect.type=java.lang.String[][]
rect.component=java.lang.String[]
rect.rows=2
rect.row0.length=3
rect.values=[[null, null, null], [null, null, null]]
outer.type=java.lang.String[][]
outer.row0=null
outer.values=[[A], null]
~~~

Hai mảng có cùng kiểu thực tế `String[][]`, nhưng hình dạng dữ liệu khác nhau. Mảng thứ nhất được tạo đầy đủ theo hai kích thước. Mảng thứ hai mới có tầng ngoài; mã phải gán từng mảng con khi cần.

`getComponentType()` bóc đúng **một tầng**. Với `String[][]`, nó trả về `String[].class`, không trả ngay `String.class`. Muốn biết kiểu phần tử ở tầng sâu nhất, cần tiếp tục bóc khi `Class.isArray()` còn trả về `true`.

Độ dài bằng 0 vẫn hợp lệ: `Array.newInstance(int.class, 2, 0)` tạo một `int[][]` có hai mảng con rỗng. Độ dài và số chiều là hai thông tin khác nhau.

## 6. Lấy component type từ một mảng có sẵn

Một nhu cầu thực tế là tạo mảng mới cùng kiểu với mảng nguồn, nhưng có độ dài khác. Đoạn sau là một phương thức tiện ích; đặt trong một lớp có import `java.lang.reflect.Array` và `java.util.Objects`:

~~~java
static Object emptyLike(Object sourceArray, int newLength) {
    Objects.requireNonNull(sourceArray, "sourceArray");
    Class<?> arrayType = sourceArray.getClass();
    if (!arrayType.isArray()) {
        throw new IllegalArgumentException("Expected an array");
    }
    return Array.newInstance(arrayType.getComponentType(), newLength);
}
~~~

Ví dụ gọi trong cùng lớp:

~~~java
Object first = emptyLike(new long[] {10L, 20L}, 4);
// first la long[4], tat ca gia tri ban dau bang 0L.

Object second = emptyLike(new String[][] {{"A"}}, 3);
// second la String[3][], ba tham chieu mang con deu null.
~~~

Hàm này **chỉ tạo mảng rỗng cùng kiểu**, không sao chép phần tử. Với mảng nhiều chiều, nó cấp phát tầng ngoài và giữ kiểu của các ô bên trong; không nhân bản các mảng con.

Phải kiểm tra `isArray()` trước khi lấy component type. Với một lớp không phải mảng, `getComponentType()` trả về `null`; đưa giá trị đó cho `Array.newInstance` không thể tạo mảng mong muốn.

Cũng cần phân biệt **kiểu khai báo** và **kiểu thực tế**. Nếu biến khai báo `Number[]` đang trỏ đến một `Integer[]`, lấy từ `sourceArray.getClass()` sẽ giữ kiểu `Integer[]`. Nếu yêu cầu nghiệp vụ là tạo `Number[]`, cần truyền `Number.class` rõ ràng thay vì suy ra từ đối tượng nguồn.

## 7. Tạo mảng không phải tạo từng phần tử

Với kiểu tham chiếu, bước cấp phát tạo các ô chứa `null`. Ví dụ `Array.newInstance(Runnable.class, 2)` hợp lệ dù `Runnable` là interface. Không có đối tượng thực thi `Runnable` nào được sinh ra bởi lời gọi ấy.

Tương tự, có thể tạo mảng của một lớp trừu tượng hoặc một lớp không có constructor không tham số. Không cần gọi constructor của lớp thành phần để tạo mảng tham chiếu. Việc tạo hoặc tìm từng đối tượng để điền vào các ô là một bước riêng.

Với kiểu nguyên thủy, các ô nhận giá trị mặc định: kiểu số nhận 0 tương ứng, `boolean` nhận `false`, `char` nhận ký tự `'\u0000'`. Ký tự này không phải chữ số `'0'` và thường không nhìn thấy khi in trực tiếp.

Vì vậy, khi thiết kế một bộ chuyển đổi dữ liệu, hãy tách rõ:

1. Chọn đúng kiểu mảng đích.
2. Cấp phát đúng độ dài/hình dạng.
3. Chuyển đổi và gán từng giá trị tương thích.

Thành công ở bước 2 chưa chứng minh dữ liệu đầu vào chuyển đổi được ở bước 3.

## 8. Giới hạn đầu vào và lỗi thường gặp

| Tình huống | Kết quả cần dự kiến |
| --- | --- |
| `Array.newInstance(null, 3)` | `NullPointerException`: thiếu kiểu thành phần |
| `Array.newInstance(String.class, -1)` | `NegativeArraySizeException` |
| `Array.newInstance(String.class, 0)` | Hợp lệ: tạo mảng rỗng |
| `Array.newInstance(void.class, 1)` | `IllegalArgumentException`: không có mảng `void[]` |
| `Array.newInstance(String.class, new int[0])` | `IllegalArgumentException`: không cung cấp chiều nào |
| Tổng số chiều yêu cầu vượt 255 | `IllegalArgumentException` |
| Độ dài hợp lệ nhưng không đủ bộ nhớ để cấp phát | Có thể gặp `OutOfMemoryError` |

`new int[0]` trong bảng là **một danh sách kích thước rỗng**, không phải một chiều có độ dài 0. Một chiều rỗng phải được diễn tả bằng `new int[] {0}` hoặc overload nhận `length = 0`.

Kiểm tra độ dài không âm chưa đủ cho dữ liệu bên ngoài. Một kích thước rất lớn vẫn có thể làm ứng dụng tiêu thụ quá nhiều bộ nhớ; nên áp dụng giới hạn theo yêu cầu của ứng dụng trước khi cấp phát. Với nhiều chiều, cần xét toàn bộ hình dạng, không chỉ độ dài mảng ngoài.

Đừng bắt mọi lỗi rồi trả về `new Object[0]` như một cách “dự phòng” âm thầm. Cách đó làm mất kiểu đích và che giấu đầu vào sai; mã sử dụng sau đó sẽ khó xác định nguyên nhân.

## 9. Liên hệ với generic và lựa chọn API

Java không cho viết `new T[n]` với một biến kiểu generic thông thường, vì kiểu `T` không cung cấp đủ thông tin cụ thể để cấp phát mảng trong mã ấy. Truyền thêm một đối tượng `Class` là một cách cung cấp kiểu lúc chạy cho `Array.newInstance`.

Tuy nhiên, Reflection không khôi phục mọi thông tin generic đã bị xóa:

- Không có cú pháp `List<String>.class`.
- `Array.newInstance(List.class, n)` tạo mảng có kiểu thực tế `List[]`; JVM không vì thế kiểm chứng rằng mọi danh sách bên trong chỉ chứa `String`.
- Không được hứa rằng một hàm trả `T[]` hỗ trợ mọi đầu vào `Class`, bao gồm kiểu nguyên thủy, chỉ bằng một phép ép kiểu không kiểm tra.

Trong bài này, kiểu trả về `Object` giúp giữ đúng khả năng hỗ trợ cả mảng nguyên thủy và mảng tham chiếu. Khi thiết kế một hàm generic riêng, phải xác định hợp đồng kiểu tham chiếu và kiểm soát chỗ ép kiểu; không sao chép phép ép `(T[])` mà bỏ qua điều kiện hợp lệ.

Nên dùng `new String[n]` khi đã biết kiểu trong mã nguồn: cách này trực tiếp và được trình biên dịch kiểm tra rõ ràng. Dùng `Array.newInstance` khi việc chọn kiểu là dữ liệu của quá trình chạy. Nếu nhu cầu chính là tăng/giảm số phần tử liên tục, cân nhắc collection thay vì dùng Reflection cho mọi thao tác.

## 10. Tự kiểm tra

1. `Array.newInstance(Integer.class, 2)` tạo `Integer[]` hay `int[]`? Giá trị mặc định là gì?
2. Vì sao một `int[]` có thể gán vào `Object` nhưng không thể ép thành `Object[]`?
3. `Array.newInstance(String[].class, 4)` có tạo bốn chuỗi hay bốn mảng con hay không?
4. Muốn tạo đầy đủ một bảng `String[4][2]`, nên truyền kiểu nào và các kích thước nào?
5. Hàm `emptyLike` có sao chép giá trị từ mảng nguồn không?

Đáp án:

1. `Integer[]`, hai ô `null`; `int.class` mới tạo mảng nguyên thủy `int[]`.
2. Bản thân mảng là một đối tượng, nhưng các ô `int` không phải tham chiếu đối tượng để tạo thành `Object[]`.
3. Nó tạo `String[4][]`; cả bốn ô ngoài đều `null`, chưa có mảng con hoặc chuỗi nào được tạo.
4. `Array.newInstance(String.class, 4, 2)`.
5. Không. Hàm chỉ giữ kiểu thực tế của mảng và cấp phát một mảng mới với giá trị mặc định.

Điểm cần nhớ: đối tượng `Class` là thông tin đầu vào để chọn kiểu; `Array.newInstance` dùng thông tin ấy để cấp phát một mảng thật. Kiểu mảng, số chiều, độ dài và giá trị các ô là những khía cạnh phải kiểm tra riêng.

## Tài liệu đối chiếu

- [Java 17 — Array.newInstance và API thao tác mảng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html).
- [Java 17 — Class.getComponentType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getComponentType()).
- [JLS 17 — Chương 10: kiểu mảng và mảng nhiều chiều](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html).
- [JLS 17 — Tạo mảng](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.1).
- [JLS 17 — Kiểu có thông tin đầy đủ lúc chạy](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7).
