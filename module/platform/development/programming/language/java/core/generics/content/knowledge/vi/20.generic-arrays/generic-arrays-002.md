# Vì sao không thể trực tiếp tạo `new T[]` trong Java Generics?

Trong Java, bạn có thể **khai báo** biến hoặc tham số kiểu mảng `T[]` trong lớp/phương thức generic, nhưng **không thể trực tiếp khởi tạo** bằng `new T[n]`:

```java
// Đoạn minh họa: dòng có chú thích lỗi không thể biên dịch.
class Buffer<T> {
    private T[] data; // Hợp lệ: khai báo tham chiếu T[]

    Buffer(int capacity) {
        // data = new T[capacity]; // LỖI: generic array creation
    }
}
```

Nguyên nhân cốt lõi: **mảng Java lưu kiểu phần tử (component type) tại runtime và kiểm tra kiểu khi ghi**, còn **type variable `T` của generics không phải kiểu có đầy đủ thông tin tại runtime (non-reifiable)**. Khi compiler xóa kiểu (type erasure), `T` có thể đại diện cho nhiều kiểu cụ thể khác nhau nhưng `new T[n]` lại đòi tạo ra một mảng có component type thực sự, ổn định và kiểm tra được.

Có nhiều cách giải quyết tùy mục tiêu:

- Nếu chỉ cần một nhóm phần tử generic: **ưu tiên `List<T>`**, ví dụ `new ArrayList<T>()`.
- Nếu phải trả về **mảng thật có runtime component type đúng**: truyền `Class<T>` để dùng `Array.newInstance`, hoặc nhận một *array factory* như `IntFunction<T[]>`.
- Nếu thao tác với API chuyển danh sách thành mảng: truyền mảng mẫu hoặc generator, chẳng hạn `toArray(new String[0])` hay `toArray(String[]::new)`.
- Không xem `(T[]) new Object[n]` là lời giải an toàn phổ quát: đoạn ép kiểu đó **không tạo một mảng runtime `String[]` khi `T = String`**.

## 1. Mảng Java khác generic ở loại thông tin được lưu lúc chạy

Xét:

```java
String[] names = new String[2];
Object[] objects = names;

objects[0] = "An"; // Hợp lệ
// objects[1] = 42; // Biên dịch được nhưng ném ArrayStoreException khi chạy
```

Cả `names` và `objects` tham chiếu **cùng một mảng runtime `String[]`**. Cho dù biến `objects` có kiểu tĩnh là `Object[]`, JVM vẫn biết mảng thực có component type `String`. Vì vậy, khi ghi một `Integer` vào mảng ấy, JVM có thể kiểm tra và từ chối bằng `ArrayStoreException`.

Đối chiếu với generic:

```java
// Snippet minh họa, trong phương thức hoặc class có import phù hợp.
java.util.List<String> text = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();

boolean sameClass = text.getClass() == numbers.getClass(); // true
```

Cả hai collection dùng cùng runtime class `ArrayList`; Java không tự sinh `ArrayList<String>` và `ArrayList<Integer>` thành các class riêng. Generic type arguments được compiler kiểm tra ở mã nguồn nhưng bị xóa khỏi descriptor thông thường ở runtime.

Mảng có **covariance**: `String[]` gán được cho `Object[]`, song việc ghi sai kiểu bị kiểm tra lúc chạy. Generic `List<T>` lại **invariant**: `List<String>` không gán trực tiếp cho `List<Object>`. Java ưu tiên bảo vệ generic bằng các quy tắc kiểu ở compile time thay vì runtime component type riêng cho từng `T`.

## 2. Type variable `T` là non-reifiable: căn nguyên của lệnh cấm

Theo quy tắc về **reifiable types** của Java, `String`, `Number`, raw `List`, `List<?>` và array có component type reifiable có thể được biểu diễn đầy đủ theo nhu cầu kiểm tra runtime. Nhưng **type variable** như `T` hay `E` là non-reifiable.

```java
class GenericSample<T> {
    T value;   // Hợp lệ
    T[] items; // Hợp lệ

    void example() {
        // T element = new T();    // Không hợp lệ
        // Class<?> kind = T.class; // Không hợp lệ
        // items = new T[10];      // Không hợp lệ
    }
}
```

Ba phép `new T()`, `T.class` và `new T[10]` liên quan những giới hạn khác nhau nhưng cùng phản ánh việc compiler không biết một runtime class cụ thể đủ để thực hiện thao tác được yêu cầu.

Ví dụ, khi dùng `GenericSample<String>`, một người lập trình có thể mong `items` là `String[]`; khi dùng `GenericSample<Integer>`, lại mong `Integer[]`. Nếu một triển khai giả định âm thầm tạo `Object[]` cho mọi `T`, mảng sẽ **không có runtime component type đúng với kiểu mà bên gọi kỳ vọng**.

### Quy tắc xóa kiểu không cứu được `new T[]`

Nếu `T` không có giới hạn trên rõ ràng, erasure của `T` là `Object`. Nếu có `<T extends Number>`, erasure là `Number`. Tuy vậy:

```java
class NumericBuffer<T extends Number> {
    T[] numbers;

    void allocate(int n) {
        // numbers = new T[n]; // Vẫn là generic array creation không hợp lệ
    }
}
```

Việc biết giới hạn `Number` không cho phép compiler khẳng định người dùng yêu cầu một `Number[]` thay vì `Integer[]` hoặc `Double[]`. `T` vẫn là type variable non-reifiable, không tự trở thành một class runtime cụ thể.

## 3. Vì sao `new Object[n]` rồi ép `(T[])` không tương đương `new T[n]`?

Một mẹo thường gặp là:

```java
// Ví dụ có thể biên dịch nhưng không an toàn cho API trả T[].
@SuppressWarnings("unchecked")
static <T> T[] unsafeArray(int size) {
    return (T[]) new Object[size];
}
```

Hãy phân biệt hai điều:

1. `new Object[size]` **luôn tạo runtime mảng `Object[]`**, không phụ thuộc type argument `T` được suy luận khi gọi.
2. Cast `(T[])` trong phương thức generic có thể chỉ được kiểm tra theo **erasure của `T[]`**, nên một mảng `Object[]` có thể tạm đi qua bước cast ở đây. Điều đó không làm runtime component type đổi thành `String` hoặc `Integer`.

Ví dụ:

```java
// Snippet minh họa khi gọi phương thức unsafeArray đã khai báo:
try {
    String[] data = unsafeArray(3);
    System.out.println(data.length);
} catch (ClassCastException exception) {
    System.out.println("ClassCastException");
}
```

Bên gọi muốn nhận `String[]`; vì object thực tế vẫn là `Object[]`, runtime cast tương ứng có thể ném `ClassCastException` **ngay tại chỗ gán kết quả**. Đây là ví dụ chứng minh rằng ép kiểu tham chiếu không biến đổi đối tượng mảng đã được tạo.

**Đừng nhầm `ClassCastException` với `ArrayStoreException`:** lỗi thứ nhất xảy ra khi không thể coi object là kiểu đích của một cast; lỗi thứ hai xảy ra khi cố ghi một phần tử không phù hợp vào array có runtime component type xác định.

### Khi nào có thể dùng `Object[]` làm bộ lưu trữ nội bộ?

Nếu đang hiện thực một cấu trúc dữ liệu generic, bạn có thể giữ `Object[]` **nội bộ** rồi kiểm soát các thao tác đọc/ghi, thay vì công khai nó dưới danh nghĩa mảng `T[]` có runtime type chính xác:

```java
// Snippet class có thể biên dịch độc lập khi nằm trong file phù hợp.
class ObjectBackedBuffer<T> {
    private final Object[] values;
    private int count;

    ObjectBackedBuffer(int capacity) {
        values = new Object[capacity];
    }

    void add(T value) {
        values[count++] = value; // Cần kiểm tra capacity ở code sản xuất
    }

    @SuppressWarnings("unchecked")
    T get(int index) {
        return (T) values[index];
    }
}
```

Ở đây, việc đọc qua `T` dựa vào invariant rằng **chỉ các giá trị `T` đi vào bằng API được kiểm tra kiểu**, không có đường raw/unchecked phá ràng buộc. `get` có thể trả giá trị bằng cast gắn với erasure của `T`; ở bên gọi, compiler cũng có thể chèn cast sang kiểu cụ thể.

Đây là mô hình bộ lưu trữ generic nội bộ, **không phải một cách tạo `T[]` thật**. Nếu API phải trả mảng cho caller, không nên đưa thẳng `Object[]` ra bằng cast giả làm `T[]`.

## 4. Cách tạo mảng đúng runtime type bằng `Class<T>` và reflection

Khi caller có thể cung cấp runtime class của thành phần, `Array.newInstance` là cách phổ biến:

```java
import java.lang.reflect.Array;

static <T> T[] createArray(Class<T> elementType, int size) {
    @SuppressWarnings("unchecked")
    T[] result = (T[]) Array.newInstance(elementType, size);
    return result;
}
```

Ví dụ sử dụng:

```java
String[] names = createArray(String.class, 3);
Integer[] scores = createArray(Integer.class, 2);
```

Khác với `new Object[n]`, `Array.newInstance(String.class, n)` tạo **mảng runtime `String[]` thật**. Kết quả là `Object` theo chữ ký phản xạ và cần cast, nhưng cast có thể biện minh được vì chính đối tượng `Class<T>` đã được dùng để chọn component type khi tạo mảng.

Cần lưu ý:

- `Class<T>` mô tả một runtime class cụ thể, ví dụ `String.class` hoặc `Integer.class`; không có `List<String>.class` trong Java.
- `Array.newInstance` nhận `Class<?>` làm thành phần và kích thước; với `size < 0` sẽ có lỗi kích thước mảng âm như `NegativeArraySizeException`.
- Ví dụ generic `createArray` phù hợp với **reference type `T`** như `String` hoặc `Integer`. Nếu truyền token cho primitive như `int.class` qua API khác, kết quả có thể là `int[]` nhưng không tương thích với ý tưởng một mảng generic tham số hóa `T[]` theo kiểu tham chiếu.
- Nếu phải tạo mảng cho một kiểu tham số hóa lồng nhau như `List<String>`, token `List.class` chỉ chọn được component runtime là raw `List`, **không tạo được một runtime component type `List<String>` riêng biệt**.

Vì vậy, `Class<T>` giải quyết được nhu cầu “cần đúng runtime class của phần tử”, không biến toàn bộ generics của Java thành reified generics.

## 5. Chương trình Java 17+ so sánh các cách tạo mảng

Lưu nguyên đoạn dưới đây vào tệp **`GenericArrayDemo.java`**:

```java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.List;

public class GenericArrayDemo {
    static <T> T[] createArray(Class<T> elementType, int size) {
        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(elementType, size);
        return result;
    }

    static <T> T[] unsafeArray(int size) {
        @SuppressWarnings("unchecked")
        T[] result = (T[]) new Object[size];
        return result;
    }

    public static void main(String[] args) {
        String[] names = createArray(String.class, 2);
        names[0] = "An";
        names[1] = "Binh";

        System.out.println("String array: " + Arrays.toString(names));
        System.out.println("Runtime array: "
                + names.getClass().getTypeName());

        Integer[] scores = createArray(Integer.class, 2);
        scores[0] = 10;
        System.out.println("Integer array: "
                + Arrays.toString(scores));

        try {
            String[] wrong = unsafeArray(2);
            System.out.println(wrong.length);
        } catch (ClassCastException exception) {
            System.out.println("Unsafe Object[] cast: ClassCastException");
        }

        Object[] asObjects = names;
        try {
            asObjects[0] = 42;
        } catch (ArrayStoreException exception) {
            System.out.println("Wrong array store: ArrayStoreException");
        }

        List<?>[] groups = new List<?>[2];
        groups[0] = List.of("Java");
        groups[1] = List.of(42);

        System.out.println("Wildcard arrays: "
                + Arrays.toString(groups));
        System.out.println("Wildcard component: "
                + groups.getClass().getComponentType().getTypeName());
    }
}
```

Biên dịch/chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 -Xlint:unchecked GenericArrayDemo.java
java GenericArrayDemo
```

Đầu ra standard output:

```text
String array: [An, Binh]
Runtime array: java.lang.String[]
Integer array: [10, null]
Unsafe Object[] cast: ClassCastException
Wrong array store: ArrayStoreException
Wildcard arrays: [[Java], [42]]
Wildcard component: java.util.List
```

Ý nghĩa:

1. `createArray(String.class, 2)` tạo một đối tượng runtime `String[]`, đúng với kiểu biến bên gọi.
2. `createArray(Integer.class, 2)` tạo `Integer[]`, giá trị thứ hai còn mặc định `null` vì đây là mảng tham chiếu mới.
3. `unsafeArray(2)` chỉ tạo `Object[]`. Khi caller yêu cầu `String[]`, cast ở đường gọi ném `ClassCastException`.
4. Cùng một `String[]` có thể xem qua `Object[]`, nhưng JVM chặn thao tác ghi `Integer` bằng `ArrayStoreException`.
5. `new List<?>[2]` hợp lệ vì component type `List<?>` là **reifiable**; mảng có runtime component class `java.util.List`, không giữ `String` hay `Integer` cho từng danh sách con.

Các dòng cố ý không hợp lệ như `new T[n]` chỉ nằm trong những snippet đã được chú thích, **không** xuất hiện dưới dạng code chạy của chương trình này.

## 6. Vì sao `new List<?>[n]` được nhưng `new List<String>[n]` bị cấm?

Quy tắc tạo array trong Java yêu cầu **kiểu thành phần** tại biểu thức `new ElementType[n]` phải reifiable.

```java
// Hợp lệ:
java.util.List<?>[] unknownLists = new java.util.List<?>[3];

// Không biên dịch:
// java.util.List<String>[] names = new java.util.List<String>[3];
```

Mặc dù cả `List<?>` và `List<String>` đều sử dụng runtime interface `List`, hai kiểu này phát biểu các ràng buộc khác nhau:

- `List<?>` không nói phần tử của các danh sách con có một kiểu cụ thể. Runtime chỉ cần kiểm tra mỗi giá trị đặt vào mảng là một `List`.
- `List<String>` ràng buộc kiểu phần tử `String`, điều mà runtime `List` không thể xác minh trực tiếp cho mỗi đối tượng. Vì thế việc cho phép tạo mảng `List<String>[]` có thể tạo ảo giác rằng JVM sẽ chặn mọi cách đưa list sai kiểu vào.

Ví dụ phản chứng mô phỏng nếu một `List<String>[]` tồn tại thông qua thao tác unsafe:

```java
// Snippet cố ý không an toàn, chỉ để giải thích.
java.util.List<?>[] rawArray = new java.util.List<?>[1];
Object[] objects = rawArray;
objects[0] = java.util.List.of(42); // Runtime cho phép: đây là List

// Không có đảm bảo rằng mọi phần tử trong List là String.
```

Đối tượng `List<Integer>` ở đây vẫn là một `List` hợp lệ xét theo runtime component type của mảng. Không có kiểm tra generic element type giống kiểm tra `String[]` khi ghi `Integer` trực tiếp.

**Nhớ:** `List<?>[]` không phải `List<Object>[]`; wildcard giữ phần tử kiểu chưa biết, còn `List<Object>` là một parameterized type cụ thể và không được tự động suy ra từ `List<String>`.

## 7. Vì sao khai báo `T[]` hợp lệ nhưng khởi tạo bằng `new T[n]` không?

Nên phân biệt:

```java
class Holder<T> {
    private T[] values; // Hợp lệ

    Holder(T[] values) { // Hợp lệ
        this.values = values;
    }

    T[] getValues() { // Hợp lệ
        return values;
    }
}
```

Mã này **không tạo mảng mới**. Nó chỉ nhận một tham chiếu `T[]` đã tồn tại. Ví dụ caller tạo `String[]` bên ngoài và truyền vào:

```java
Holder<String> h = new Holder<>(new String[] { "An", "Binh" });
String[] data = h.getValues();
```

Tại runtime, object mảng ban đầu thực sự là `String[]`, nên việc trả về qua phương thức generic phù hợp với tham chiếu `String[]` của bên gọi.

Ngược lại, biểu thức `new T[n]` buộc compiler phải **tự chọn runtime component type**, nhưng không có token kiểu cụ thể để lựa chọn. Đó là điều bị cấm.

Một class generic cần mảng có thể nhận mảng từ constructor, hoặc nhận `Class<T>`/factory để tự tạo mảng đúng kiểu.

### Thiết kế class nhận `Class<T>`

```java
// Snippet minh họa Java 17+, cần import java.lang.reflect.Array.
class TypedBuffer<T> {
    private final T[] data;

    @SuppressWarnings("unchecked")
    TypedBuffer(Class<T> elementType, int size) {
        data = (T[]) java.lang.reflect.Array.newInstance(elementType, size);
    }

    void set(int index, T value) {
        data[index] = value;
    }

    T[] toArray() {
        return data.clone();
    }
}
```

Caller:

```java
TypedBuffer<String> buffer = new TypedBuffer<>(String.class, 2);
buffer.set(0, "An");
String[] copy = buffer.toArray();
```

Ở đây, `toArray()` trả về bản clone có runtime component type giống mảng gốc, tức `String[]`. `clone()` là **sao chép nông**: với phần tử mutable, bản thân các object phần tử không tự được clone.

Hàm `set` trong ví dụ dùng mảng Java làm bộ lưu trữ: cần thêm kiểm tra index, capacity và các ràng buộc nghiệp vụ khác khi xây dựng thư viện thực tế.

## 8. Dùng `IntFunction<T[]>` để caller chọn cách tạo mảng

Một cách khác là yêu cầu caller cung cấp một **array factory**:

```java
// Snippet trong class/method thích hợp:
static <T> T[] allocate(int size, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(size);
}
```

Khi gọi:

```java
String[] names = allocate(2, String[]::new);
Integer[] numbers = allocate(3, Integer[]::new);
```

Biểu thức method reference `String[]::new` đặt việc tạo mảng vào nơi đã biết rõ component type `String`. Phương thức generic nhận factory và sử dụng nó; nó **không phải tự viết `new T[n]`**.

Cách này hữu ích khi viết API generic không muốn phụ thuộc reflection hoặc khi một bộ sưu tập/cơ chế xử lý nhận generator có thể cung cấp mảng đúng kiểu.

Lưu ý rằng caller có trách nhiệm cung cấp factory tương thích; nếu ép raw/unchecked để truyền factory sai, những rủi ro an toàn kiểu vẫn có thể phát sinh.

## 9. Chuyển collection sang mảng: tránh tự tạo `T[]`

Nhiều API Java đã có cơ chế để caller quyết định runtime component type.

Ví dụ:

```java
java.util.List<String> list = java.util.List.of("An", "Binh");

String[] first = list.toArray(new String[0]);
String[] second = list.toArray(String[]::new);
```

Hai cách đều nhận kết quả kiểu `String[]`. Mảng `String[0]` đóng vai trò mẫu thể hiện kiểu thành phần; API có thể tạo một mảng có kích thước phù hợp theo hợp đồng `toArray(T[])`. Với `toArray(IntFunction<T[]>)`, generator `String[]::new` tạo mảng đúng runtime component type.

Nếu chỉ gọi `list.toArray()` **không truyền gì**, kiểu trả về là `Object[]`, không thể giả định đó là `String[]`:

```java
Object[] values = list.toArray(); // Hợp lệ
// String[] wrong = (String[]) list.toArray(); // Có thể ClassCastException
```

Cách tiếp cận này làm rõ trách nhiệm: thư viện generic xử lý các phần tử, còn caller cung cấp thông tin kiểu để tạo mảng đúng runtime.

## 10. Vì sao `List<T>` thường đơn giản hơn `T[]`?

Nếu mục tiêu chỉ là lưu trữ một số phần tử kiểu `T`, dùng collection generic thông thường:

```java
import java.util.ArrayList;
import java.util.List;

class DynamicBuffer<T> {
    private final List<T> elements = new ArrayList<>();

    void add(T value) {
        elements.add(value);
    }

    T get(int index) {
        return elements.get(index);
    }
}
```

Khi dùng `DynamicBuffer<String>`, compiler kiểm tra `add(String)` ở mã nguồn, và không cần dựng runtime array `String[]`. `ArrayList` có thể quản lý bộ lưu trữ nội bộ bằng một cấu trúc array phù hợp với triển khai của nó, nhưng API công khai vẫn giữ kiểu `List<T>`.

Đây thường là lựa chọn tốt vì:

- Không yêu cầu `Class<T>` hoặc factory chỉ để lưu trữ phần tử.
- Dễ thay đổi kích thước; array có độ dài cố định.
- Các phương thức `List<T>` cung cấp thao tác thêm/xóa/truy xuất có kiểm tra generic ở nguồn.
- Giảm nhu cầu ép kiểu `Object[]` thành `T[]` để trả kết quả cho caller.

Chọn `T[]` khi cần tương tác với API mảng, tận dụng cấu trúc array hoặc có yêu cầu đặc biệt về runtime component type. Không nên dùng array như lựa chọn mặc định chỉ vì từng quen với `new int[n]` trong các thuật toán không generic.

### Mảng primitive là trường hợp khác

`int[]` và `double[]` là các mảng runtime có thành phần nguyên thủy rõ ràng. Java generic thông thường không dùng `List<int>` hay `T = int` theo kiểu tham số generic thông thường; với collections cần `List<Integer>` và boxing/unboxing. Việc cần `int[]` hiệu quả về biểu diễn nên được thiết kế riêng, không kỳ vọng `new T[]` trong generic tự động tạo primitive array.

## 11. Generic varargs: có `T...` mà vẫn cấm `new T[]`?

Java cho phép khai báo phương thức varargs generic:

```java
@SafeVarargs
static <T> int count(T... values) {
    return values.length;
}
```

Khi gọi varargs, compiler có cơ chế tạo mảng cho đối số ở call site. Trong trường hợp element type **non-reifiable**, compiler có thể tạo mảng dựa trên erasure và phát **unchecked/generic array creation warning**, vì runtime component type không thể biểu diễn đầy đủ type argument.

Vì vậy, **cho phép khai báo `T...` không có nghĩa trong thân phương thức được phép viết `new T[10]`**. Varargs là một cú pháp gọi phương thức có quy tắc biên dịch riêng, và nó cũng có những rủi ro heap pollution nếu mã làm lộ hoặc ghi dữ liệu sai kiểu vào mảng varargs.

`@SafeVarargs` là một lời cam kết của người viết phương thức rằng phần thân **không thực hiện thao tác không an toàn** với mảng varargs. Annotation được phép trên constructor và những phương thức đáp ứng điều kiện, ví dụ static, final hoặc private theo phiên bản Java phù hợp. Nó **không** làm `T` reifiable và cũng không phải công cụ che cảnh báo khi mã vẫn làm hỏng dữ liệu.

Ví dụ có thể được gắn `@SafeVarargs` nếu chỉ đếm phần tử là như trên; với phương thức lưu array vào trường dùng chung, đưa nó ra ngoài hoặc ghi sai kiểu qua alias, cần đánh giá rất cẩn thận trước khi hứa `@SafeVarargs`.

## 12. Array covariance và heap pollution: lý do bảo vệ này quan trọng

Giả sử Java cho phép tạo array có component type generic không reifiable mà mọi người nhầm rằng nó sẽ chặn dữ liệu sai kiểu:

```java
// Snippet minh họa thao tác với List<?>[] vốn hợp lệ.
java.util.List<?>[] lists = new java.util.List<?>[1];
Object[] objects = lists;
objects[0] = java.util.List.of(42); // Hợp lệ: vẫn là một List
```

Mảng runtime chỉ kiểm tra phần tử được ghi có là một `List` hay không; nó không kiểm tra được `Integer` hay `String` trong từng list.

Nếu mã khác bằng unchecked cast hoặc raw type tin rằng mảng này là `List<String>[]`, một phần tử list chứa `Integer` có thể được đọc sau đó dưới giả định `String`, dẫn đến lỗi cast. Trạng thái một biến generic tuyên bố có kiểu tham số hóa không phù hợp dữ liệu thực gọi là **heap pollution**.

Đây là nguyên nhân khiến Java phân biệt nghiêm ngặt mảng và generic:

- Mảng có kiểm tra **runtime component type** và tính covariance.
- Generics kiểm tra chủ yếu ở **compile time**, dùng erasure và thường bất biến.
- Array có component type là generic non-reifiable sẽ tạo ra một ranh giới khó bảo đảm an toàn kiểu.

Do đó, các biểu thức như `new List<String>[n]` và `new T[n]` bị cấm, trong khi khai báo tham chiếu đến loại array ấy vẫn có thể hợp lệ trong những ngữ cảnh thích hợp.

## 13. Các lỗi thường gặp và cách sửa

**Lỗi 1 — “`T` sẽ được thay bằng `String` khi gọi nên `new T[n]` phải chạy.”** Sai. Type arguments của Java Generics thông thường không tạo class specialization cho từng lần gắn kiểu. Compiler không có một runtime class component duy nhất cho biểu thức này.

**Lỗi 2 — “Dùng `(T[]) new Object[n]` là mảng kiểu `T[]` thật.”** Sai. Object thật vẫn là `Object[]`; bên gọi yêu cầu `String[]` có thể gặp `ClassCastException`.

**Lỗi 3 — “`T extends Number` sẽ cho phép `new T[n]`.”** Sai. `T` vẫn non-reifiable dù erasure có thể là `Number`.

**Lỗi 4 — “Đã không tạo được `T[]` thì cũng không khai báo trường `T[]` được.”** Sai. Khai báo/nhận/trả tham chiếu `T[]` được phép; bị hạn chế là biểu thức khởi tạo array với component type non-reifiable.

**Lỗi 5 — “`new List<?>[n]` cũng bị cấm vì có dấu `<...>`.”** Sai. `List<?>` là reifiable, nên array có component type này được phép tạo. Nhưng `List<String>` không reifiable.

**Lỗi 6 — “Reflection không an toàn vì luôn trả `Object[]`.”** Sai. `Array.newInstance(String.class, n)` thực sự tạo `String[]`; giá trị phản xạ có kiểu trả về tổng quát là `Object` nhưng runtime class mảng đúng theo component type token.

**Lỗi 7 — “`List<T>` là mảng trá hình, nên nó cũng cần `new T[n]`.”** Sai. Collection generic dùng API generic; cơ chế lưu trữ nội bộ không buộc public API trả một mảng runtime `T[]`.

**Lỗi 8 — “`@SuppressWarnings("unchecked")` khiến cast từ `Object[]` thành `T[]` an toàn.”** Sai. Annotation chỉ ẩn compiler warning, không thay runtime component class.

**Lỗi 9 — “`@SafeVarargs` cho phép tạo mọi generic array mà không có rủi ro.”** Sai. Nó biểu thị cam kết về thao tác an toàn trên tham số varargs, không biến non-reifiable type thành reifiable.

**Lỗi 10 — “Nếu cast `Object[]` sang `String[]` không chạy thì mọi cast từ array đều sai.”** Sai. Cast tới mảng có runtime component type tương ứng là bình thường; vấn đề nằm ở việc object mảng thực sự được tạo bằng kiểu nào.

## 14. Bài tập tự kiểm tra

**Câu 1.** Trong `class Box<T>`, `T[] array;` có hợp lệ không?

Có. Khai báo một biến tham chiếu đến mảng `T[]` không yêu cầu tạo mảng mới.

**Câu 2.** Tại sao `array = new T[10];` không hợp lệ?

Vì `T` là type variable non-reifiable, trong khi biểu thức tạo mảng đòi một runtime component type có thể biểu diễn và kiểm tra được.

**Câu 3.** `String[] result = createArray(String.class, 5)` có runtime class gì?

Là `String[]`, vì `Array.newInstance` tạo mảng dựa trực tiếp trên `String.class`.

**Câu 4.** Hàm `<T> T[] f() { return (T[]) new Object[3]; }` có chắc an toàn khi caller cần `String[]` không?

Không. Runtime mảng vẫn là `Object[]`, và cast ở caller có thể ném `ClassCastException`.

**Câu 5.** `new List<?>[2]` và `new List<String>[2]` khác nhau thế nào?

Cái đầu hợp lệ vì `List<?>` reifiable; cái sau bị cấm vì `List<String>` non-reifiable.

**Câu 6.** Khi nào nên ưu tiên `List<T>`?

Khi chủ yếu cần tập hợp phần tử generic, không cần mảng runtime với component type cụ thể và muốn tránh cast array khó chứng minh an toàn.

**Câu 7.** `String[] data = {"A"}; Object[] objects = data; objects[0] = 42;` gây lỗi gì?

`ArrayStoreException`, vì array thực có component type `String`. Đây khác với `ClassCastException` có thể xảy ra khi cố coi một `Object[]` là `String[]`.

**Câu 8.** `List<String> names = List.of("A"); String[] values = names.toArray(String[]::new);` có hợp lệ không?

Có. Caller cung cấp generator `String[]::new`, cho phép API tạo runtime mảng đúng component type.

## 15. Tóm tắt bằng quyết định thiết kế

| Nhu cầu | Cách làm nên chọn | Điều cần tránh |
| --- | --- | --- |
| Lưu nhiều giá trị generic và thêm/xóa linh hoạt | `List<T>` / `ArrayList<T>` | Tạo `T[]` khi không cần |
| Bộ lưu trữ nội bộ với độ dài cố định | `Object[]` trong cấu trúc dữ liệu được bao kín, bảo vệ invariant | Công khai `Object[]` dưới lời hứa runtime `T[]` |
| Trả mảng đúng class phần tử | `Class<T>` + `Array.newInstance` | `(T[]) new Object[n]` khi caller có thể cần `String[]` |
| Caller đã biết kiểu phần tử | `IntFunction<T[]>`, ví dụ `String[]::new` | Giả định compiler khôi phục `T` runtime |
| Chuyển `List<String>` thành mảng | `toArray(new String[0])` hoặc `toArray(String[]::new)` | Cast `Object[]` trả về từ `toArray()` thành `String[]` |
| Cần danh sách nhiều kiểu chưa biết | `List<?>` hoặc mảng `List<?>[]` khi thực sự cần mảng | Tin `List<?>[]` xác nhận nội dung của mọi `List<String>` |

**Kết luận:** Java cấm trực tiếp `new T[]` không phải vì không thể đặt generic vào mảng, mà vì **type variable `T` không reifiable còn mảng cần biết component type tại runtime**. Một `Object[]` được cast thành `T[]` không tự hóa thành `String[]` hay `Integer[]`, gây nguy cơ lỗi runtime. Khi cần một mảng đúng kiểu, truyền `Class<T>` hoặc array factory; khi chỉ cần cấu trúc lưu trữ generic, `List<T>` thường đơn giản và ít rủi ro hơn.