# Mảng generic, erasure và giới hạn tạo `T[]` trong Java

## 1. Bài toán: tại sao mảng động generic không thể dùng `new T[n]`?

Khi xây dựng một mảng động (dynamic array), ta cần vùng lưu trữ có thể tăng dung lượng khi số phần tử vượt quá sức chứa ban đầu. Với kiểu cố định, việc cấp phát mảng rất trực tiếp:

```java
String[] values = new String[10];
```

Nhưng trong lớp generic, cách viết tưởng như tương đương lại không hợp lệ:

```java
class DynamicArray<T> {
    // Không biên dịch: generic array creation
    // private T[] values = new T[10];

    private T[] values; // Khai báo T[] thì hợp lệ.
}
```

Giới hạn này không xuất phát từ việc JVM không có mảng. Nguyên nhân là sự kết hợp giữa **mảng kiểm tra kiểu phần tử tại runtime** và **generic sử dụng type erasure**. Nắm rõ hai cơ chế này giúp chọn cấu trúc lưu trữ đúng, tránh ép kiểu thiếu an toàn và thiết kế API trả mảng chuẩn kiểu.

## 2. Mảng (array) và generic có hai cơ chế kiểm tra kiểu khác nhau

| Đặc điểm | Mảng `String[]` | Generic `List<String>` |
| --- | --- | --- |
| Kiểu thành phần tại runtime | Có: đối tượng mảng biết component type là `String` | Tham số `String` thường bị xóa bởi erasure |
| Quan hệ kiểu | Mảng kiểu tham chiếu có tính **covariant**: `String[]` gán được cho `Object[]` | Generic mặc định **invariant**: `List<String>` không gán được cho `List<Object>` |
| Kiểm tra thao tác lưu | JVM kiểm tra phần tử khi gán vào mảng; sai kiểu gây `ArrayStoreException` | Trình biên dịch kiểm tra tham số generic chủ yếu tại compile time |
| Ví dụ runtime | `new String[2].getClass()` biểu diễn lớp mảng `String[]` | `new ArrayList<String>().getClass()` không giữ đối số kiểu `String` như một `Class<List<String>>` riêng |

Ví dụ mảng covariance và kiểm tra tại runtime:

```java
Object[] array = new String[1]; // Hợp lệ: String[] là subtype của Object[].
array[0] = "OK";                // Hợp lệ.
array[0] = 123;                 // Ném ArrayStoreException tại runtime.
```

Biến `array` có kiểu tĩnh `Object[]`, nhưng đối tượng thực tế vẫn là `String[]`. JVM kiểm tra kiểu thực tế khi ghi, nên phần tử `Integer` bị từ chối.

Ngược lại, hai biến `List<String>` và `List<Integer>` về cơ bản đều dựa trên đối tượng có lớp runtime như `ArrayList`. JVM không có một component type runtime riêng là `List<String>` để kiểm tra phép ghi vào mảng.

### Erasure hoạt động thế nào?

**Type erasure** là quá trình Java compiler chuyển kiểu generic sang dạng không giữ đầy đủ đối số kiểu trong mã thực thi: `List<String>` và `List<Integer>` đều có erasure là `List`; biến kiểu không bị chặn `T` có erasure là `Object`; với `T extends Number`, erasure của `T` là bound bên trái `Number`.

```java
class Holder<T> {
    T value; // Về cơ bản dùng Object sau erasure nếu T không có bound.

    T get() {
        return value;
    }
}
```

Compiler có thể chèn phép ép kiểu ở nơi sử dụng để bảo toàn kỳ vọng kiểu tĩnh. Do vậy, generic tạo được kiểm tra kiểu mạnh ở compile time nhưng không biến `T` thành một lớp runtime có thể dùng trực tiếp để khởi tạo mảng.

## 3. Reifiable type và các phép tạo mảng được phép

Một kiểu được gọi là **reifiable** khi có đủ thông tin kiểu cần thiết tại runtime. Các ví dụ gồm kiểu nguyên thủy, lớp không generic, raw type, kiểu parameterized chỉ chứa wildcard không giới hạn như `List<?>`, và mảng có component type reifiable.

| Biểu thức | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `new String[4]` | Có | `String` là reifiable. |
| `new int[4]` | Có | `int` là kiểu nguyên thủy. |
| `new List<?>[4]` | Có | `List<?>` là reifiable. |
| `new List[4]` | Có nhưng dùng raw type | Mất kiểm tra kiểu generic khi dùng raw. |
| `new List<String>[4]` | Không | `List<String>` không reifiable. |
| `new List<? extends Number>[4]` | Không | Wildcard có bound này không phải dạng reifiable `List<?>`. |
| `new T[4]` trong lớp/phương thức generic | Không | Type variable `T` không reifiable để làm component type của biểu thức tạo mảng. |
| `List<String>[] items;` | Có | Khai báo biến mảng khác với cấp phát mảng. |
| `T[] items;` | Có | Khai báo tham chiếu `T[]` vẫn hợp lệ. |

Nếu Java cho phép `new List<String>[1]`, một tham chiếu `Object[]` có thể đưa `List<Integer>` vào đó. Runtime chỉ nhận ra đối tượng `List` mà không đủ thông tin để từ chối `Integer` nằm bên trong; tính an toàn kiểu generic sẽ bị phá vỡ.

**Phân biệt quan trọng:** cấm *biểu thức tạo mảng* với element type không reifiable; không cấm dùng `T[]` làm kiểu biến, tham số, kết quả trả về, hoặc nhận mảng thực do bên gọi cấp phát.

## 4. Heap pollution và hai kiểu lỗi runtime khác nhau

**Heap pollution** xảy ra khi một biến khai báo bằng kiểu parameterized trỏ đến dữ liệu không phù hợp với kiểu tham số mà nó hứa hẹn. Mảng của kiểu generic kết hợp unchecked cast là một cách tạo ra tình huống này:

```java
@SuppressWarnings("unchecked")
static void demonstrateHeapPollution() {
    List<String>[] words = (List<String>[]) new List<?>[1]; // Unchecked cast.
    Object[] alias = words;  // Runtime component type chỉ là List.

    alias[0] = List.of(42);  // Qua kiểm tra mảng: đối tượng là List.
    String value = words[0].get(0); // ClassCastException.
}
```

Điểm cần chú ý:

1. `new List<?>[1]` hợp lệ, vì component type ở runtime là `List`.
2. Cast sang `List<String>[]` không thể được chứng minh hoàn toàn tại runtime; compiler phải cảnh báo `unchecked`.
3. `alias[0] = List.of(42)` vượt qua kiểm tra lưu phần tử, vì đó vẫn là một `List`.
4. Khi lấy phần tử ra theo kỳ vọng `String`, phép cast do compiler chèn vào có thể ném `ClassCastException`.

So sánh: `ArrayStoreException` xảy ra **ngay khi ghi** giá trị sai loại vào mảng có component type runtime không tương thích; `ClassCastException` thường lộ ra **khi đọc/ép kiểu** sau khi thông tin kiểu generic bị phá vỡ. Cả hai lỗi có thể xuất hiện ở những tình huống khác, nhưng phân biệt này đặc biệt hữu ích khi chẩn đoán mảng generic.

## 5. Cách 1 — Lưu bằng `Object[]`, tự kiểm soát biên generic

Đây là cách thường phù hợp để cài đặt **mảng động tổng quát** nếu API chính là `add(T)`, `get(int)` và các thao tác trên từng phần tử, không cần trả về trực tiếp `T[]`. Vùng nhớ có thể chứa tham chiếu đối tượng, còn lớp generic giới hạn đường ghi dữ liệu.

```java
import java.util.Arrays;
import java.util.Objects;

final class DynamicBuffer<T> {
    private Object[] elements = new Object[2];
    private int size;

    public void add(T value) {
        if (size == elements.length) {
            elements = Arrays.copyOf(elements, elements.length * 2);
        }
        elements[size++] = value;
    }

    @SuppressWarnings("unchecked")
    public T get(int index) {
        Objects.checkIndex(index, size);
        return (T) elements[index];
    }

    public int size() {
        return size;
    }
}
```

Vì sao có thể dùng unchecked cast trong `get()`? Trường `elements` là `private`, chỉ phương thức `add(T)` ghi dữ liệu vào đó; lớp không để bên ngoài sửa mảng qua một tham chiếu alias. Khi ràng buộc được giữ vững, mỗi phần tử đọc trong các vị trí hợp lệ đều được thêm như một `T`. Annotation được đặt **cục bộ** ở phương thức thực sự cần cast; nó tắt cảnh báo compiler nhưng không tự chứng minh an toàn, nên bất biến của lớp phải được kiểm tra khi sửa code.

Khi hết chỗ, `Arrays.copyOf` tạo mảng `Object[]` lớn hơn và sao chép dữ liệu. Một lần mở rộng có chi phí O(n), nhưng nếu tăng dung lượng theo hệ số (ví dụ gấp đôi) thì chi phí thêm một phần tử được phân bổ trung bình là **O(1) amortized**. Phép đọc theo chỉ số là O(1).

Đừng vô tình làm lộ mảng nội bộ:

```java
// Không nên: người gọi có thể ghi thẳng Object sai kiểu.
public Object[] unsafeBackingArray() {
    return elements;
}
```

Cũng **không nên** hứa trả về `T[]` bằng cách ép trực tiếp `Object[]`:

```java
@SuppressWarnings("unchecked")
T[] brokenToArray() {
    return (T[]) new Object[size]; // Có thể thành công bên trong do erasure.
}

// Với Buffer<String>, phép gán kết quả sang String[] có thể
// ném ClassCastException: Object[] thực tế không phải String[].
```

Một kết quả trả về an toàn hơn cho API mảng động là `List<T>`, hoặc tạo mảng đầu ra bằng factory/class token do bên gọi cung cấp.

## 6. Cách 2 — Tạo `T[]` bằng `Array.newInstance` và `Class<T>`

Khi cần **mảng thật sự có component type runtime cụ thể** (như `String[]`), nhận `Class<T>` từ bên gọi, dùng Java Reflection để cấp phát, rồi cast cục bộ:

```java
import java.lang.reflect.Array;

static <T> T[] newTypedArray(Class<T> componentType, int length) {
    @SuppressWarnings("unchecked")
    T[] result = (T[]) Array.newInstance(componentType, length);
    return result;
}

// Sử dụng:
String[] names = newTypedArray(String.class, 3);
Integer[] scores = newTypedArray(Integer.class, 2);
```

Ở đây `Array.newInstance(String.class, 3)` thật sự tạo đối tượng `String[]`. JVM biết kiểu thành phần và tiếp tục bảo vệ phép ghi bằng kiểm tra runtime. Cast sang `T[]` vẫn là unchecked ở cấp generic; tính đúng đắn dựa trên việc ta dùng chính `componentType` do bên gọi cung cấp để tạo mảng.

Cách này hữu ích cho buffer cần trả về typed array:

```java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.Objects;

final class TypedBuffer<T> {
    private T[] elements;
    private int size;

    @SuppressWarnings("unchecked")
    TypedBuffer(Class<T> componentType, int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity < 0");
        }
        Objects.requireNonNull(componentType);
        elements = (T[]) Array.newInstance(componentType, capacity);
    }

    void add(T value) {
        if (size == elements.length) {
            elements = Arrays.copyOf(elements, Math.max(1, elements.length * 2));
        }
        elements[size++] = value;
    }

    T[] snapshot() {
        return Arrays.copyOf(elements, size);
    }
}
```

`snapshot()` trả về một mảng mới có runtime component type phù hợp với mảng nguồn, tránh cho người gọi sửa bộ nhớ đang được `TypedBuffer` sử dụng. Một giới hạn: `String.class` là token cụ thể, còn **không có** `List<String>.class`. `List.class` chỉ mô tả `List` sau erasure nên không thể dùng cách này để kiểm tra phần tử `String` bên trong mỗi `List` tại runtime.

Trong ví dụ trên, `add(null)` hợp lệ với component type tham chiếu; các thao tác sau đó cần tự quy định cách xử lý `null`. Với tham số lớp token, API cũng cần tránh để người gọi sử dụng raw type/unchecked cast làm sai lời hứa kiểu.

## 7. Cách 3 — Nhận `IntFunction<T[]>` (array factory)

Factory giúp bên gọi quyết định chính xác loại mảng, còn lớp generic không phải biết `T.class`:

```java
import java.util.function.IntFunction;

static <T> T[] createArray(IntFunction<T[]> factory, int length) {
    return factory.apply(length);
}

// Method reference tạo mảng:
String[] labels = createArray(String[]::new, 4);
Integer[] ids = createArray(Integer[]::new, 4);

// Có thể dùng lambda:
String[] other = createArray(n -> new String[n], 4);
```

Áp dụng vào mảng động: constructor có thể nhận `IntFunction<T[]> arrayFactory` và gọi nó mỗi khi cần cấp phát. Nhớ lưu factory, giữ phần tử, sao chép dữ liệu khi tăng sức chứa và tránh trả trực tiếp mảng backing. Đây cũng là hướng mà nhiều API thư viện sử dụng khi cần mảng đúng loại từ generic.

So với `Class<T>`, factory linh hoạt hơn khi muốn tách thao tác cấp phát khỏi logic lưu trữ. Tuy vậy, nó **không thay đổi quy tắc erasure**: factory chỉ tạo được mảng theo component type reifiable mà biểu thức khởi tạo cụ thể cho phép.

## 8. Chương trình Java 17+ chạy độc lập

Lưu tệp sau thành `GenericArrayDemo.java`. Chương trình có cả mảng động qua `Object[]`, mảng typed tạo bằng Reflection, factory, và một tình huống heap pollution được bắt ngoại lệ để người học thấy dấu hiệu runtime.

```java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.IntFunction;

public class GenericArrayDemo {
    static final class Buffer<T> {
        private Object[] data = new Object[2];
        private int size;

        void add(T value) {
            if (size == data.length) {
                data = Arrays.copyOf(data, data.length * 2);
            }
            data[size++] = value;
        }

        @SuppressWarnings("unchecked")
        T get(int index) {
            Objects.checkIndex(index, size);
            return (T) data[index];
        }

        int size() {
            return size;
        }
    }

    @SuppressWarnings("unchecked")
    static <T> T[] newTypedArray(Class<T> componentType, int size) {
        return (T[]) Array.newInstance(componentType, size);
    }

    static <T> T[] createWithFactory(IntFunction<T[]> factory, int size) {
        return factory.apply(size);
    }

    @SuppressWarnings("unchecked")
    static void demonstrateHeapPollution() {
        List<String>[] words = (List<String>[]) new List<?>[1];
        Object[] alias = words;
        alias[0] = List.of(42);
        try {
            String s = words[0].get(0);
            System.out.println(s);
        } catch (ClassCastException e) {
            System.out.println("ClassCastException");
        }
    }

    public static void main(String[] args) {
        Buffer<String> buffer = new Buffer<>();
        buffer.add("Java");
        buffer.add("Generics");
        buffer.add("Arrays");
        System.out.println(buffer.size() + ": " + buffer.get(2));

        String[] reflected = newTypedArray(String.class, 2);
        reflected[0] = "reflection";
        System.out.println(reflected.getClass().getComponentType().getSimpleName()
                + ": " + Arrays.toString(reflected));

        String[] factoryArray = createWithFactory(String[]::new, 2);
        factoryArray[0] = "factory";
        System.out.println(Arrays.toString(factoryArray));

        demonstrateHeapPollution();
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac --release 17 -Xlint:unchecked GenericArrayDemo.java
java GenericArrayDemo
```

Stdout chính xác:

```text
3: Arrays
String: [reflection, null]
[factory, null]
ClassCastException
```

Code đã được kiểm tra biên dịch với `--release 17`. Cảnh báo unchecked trong đoạn minh họa heap pollution được khoanh vùng bằng `@SuppressWarnings("unchecked")` để người học chủ động biết vị trí mất đảm bảo kiểu; **không** nên coi annotation này là một cơ chế bảo đảm type safety.

## 9. Liên hệ với `ArrayList<T>` và API thư viện

Trong phần lớn ứng dụng, nên dùng `ArrayList<T>` thay vì tự xây mảng động nếu không có yêu cầu đặc thù về layout, quản lý cấp phát hoặc bài tập cấu trúc dữ liệu:

```java
List<String> names = new java.util.ArrayList<>();
names.add("Ada");
names.add("Grace");
String second = names.get(1);
```

`ArrayList` tự quản lý dung lượng và che giấu cách lưu trữ bên trong. API `List<T>` duy trì kiểm tra kiểu ở compile time cho `add`/`get`; việc sử dụng một cấu trúc lưu trữ kiểu `Object[]` ở tầng cài đặt không làm API trở thành `Object[]`.

Khi cần typed array từ collection, các overload thông dụng gồm:

```java
List<String> names = List.of("Ada", "Grace");

String[] a = names.toArray(String[]::new);     // Java 11+.
String[] b = names.toArray(new String[0]);      // Mẫu lâu đời.
Object[] c = names.toArray();                   // Chỉ Object[].
```

`toArray()` không tham số trả `Object[]`; không được ép mảng đó thành `String[]` bằng unchecked cast rồi kỳ vọng JVM chấp nhận. Dùng typed overload khi cần đúng component type.

## 10. Generic varargs: một trường hợp liên quan

Varargs `T...` về mặt biểu diễn là một tham số mảng `T[]`. Với kiểu phần tử không reifiable, compiler có thể cảnh báo nguy cơ heap pollution tại nơi khai báo và/hoặc gọi:

```java
static <T> void accept(T... values) {
    // values là T[]; tránh ghi sai kiểu hoặc phát tán alias.
}
```

Có thể dùng `@SafeVarargs` khi **đã chứng minh thân phương thức an toàn**: không ghi phần tử không đúng kiểu, không chuyển mảng cho mã không tin cậy, không trả/lưu alias để bị sửa ngoài ý muốn. Ví dụ sao chép dữ liệu ngay vào collection bất biến:

```java
import java.util.Arrays;
import java.util.List;

@SafeVarargs
static <T> List<T> immutableCopy(T... values) {
    return List.copyOf(Arrays.asList(values));
}
```

`List.copyOf` không chấp nhận phần tử `null`. `@SafeVarargs` là một cam kết của tác giả API, không làm cho kiểu `T` trở thành reifiable; sử dụng sai vẫn có thể gây heap pollution. Với Java 17+, annotation áp dụng được cho constructor, phương thức static/final và private instance method theo quy tắc ngôn ngữ.

## 11. Lỗi thường gặp và cách chọn giải pháp

| Tình huống | Vấn đề | Hướng giải quyết |
| --- | --- | --- |
| `new T[n]` | Compile error vì tạo mảng generic | Dùng `Object[]` nội bộ, `Array.newInstance` hoặc array factory. |
| `new List<String>[n]` | Component type không reifiable | Dùng `List<List<String>>` hoặc chỉ `List<?>[]` khi thực sự phù hợp. |
| `(T[]) new Object[n]` rồi trả về `String[]` | Runtime có thể ném `ClassCastException` | Nhận `String[]::new` hoặc `String.class` để tạo đúng kiểu mảng. |
| Lạm dụng `(List<String>[]) new List<?>[n]` | Unchecked cast, có thể heap pollution | Tránh cast; nếu phải dùng, bao kín alias và chứng minh bất biến. |
| Trả backing array cho caller | Phá encapsulation, bên gọi chỉnh dữ liệu trực tiếp | Trả bản sao/collection view thích hợp. |
| Dùng `@SuppressWarnings` toàn bộ lớp | Che giấu vị trí mất bảo đảm kiểu | Thu hẹp annotation vào đúng phép cast và ghi giải thích. |
| Nghĩ `Class<List<String>>` tồn tại như `String.class` | Erasure làm mất đối số kiểu generic | Dùng `List.class` chỉ cho lớp thô; kiểm tra phần tử bằng quy tắc riêng. |
| Nhầm `ArrayStoreException` với `ClassCastException` | Chẩn đoán sai điểm lỗi | Kiểm tra runtime component type, đường ghi mảng, unchecked cast và đường đọc. |

Quy tắc chọn nhanh:

- **Chỉ cần danh sách co giãn:** ưu tiên `ArrayList<T>`.
- **Tự cài đặt mảng động generic với `add/get`:** giữ `Object[]` ở nội bộ, bất biến kiểu rõ ràng, cast cục bộ khi đọc.
- **Cần trả typed array như `String[]`:** nhận `Class<T>` hoặc `IntFunction<T[]>`; tạo mảng có runtime component type chính xác.
- **Phần tử vốn là kiểu generic sâu như `List<String>`:** ưu tiên collection lồng nhau; không kỳ vọng runtime array kiểm tra được đối số kiểu bên trong.

## 12. Tự kiểm tra hiểu bài

1. Tại sao `List<String>[] a;` hợp lệ nhưng `new List<String>[5]` không hợp lệ? Hãy giải thích bằng reifiability và kiểm tra ghi của mảng.
2. Khi `Object[] alias = new String[2]; alias[0] = 5;`, lỗi nào xảy ra và ở thao tác nào? Khi alias là `List<String>[]` bị unchecked cast từ `List<?>[]`, lỗi có thể bộc lộ khác thế nào?
3. Trong `class Box<T>`, vì sao `(T[]) new Object[3]` có thể lọt qua phép cast nội bộ nhưng trả về `String[]` lại lỗi?
4. Hãy bổ sung `remove(int)` cho `DynamicBuffer<T>`: dồn phần tử, giảm `size` và gán `null` vào ô cuối để giải phóng tham chiếu không còn dùng.
5. Viết overload `toArray(IntFunction<T[]> factory)` cho buffer, sao chép đúng `size` phần tử và trả mảng độc lập. Kiểm tra với `String[]::new`.

**Ghi nhớ:** Java generic bảo vệ kiểu chủ yếu lúc biên dịch và dùng erasure; Java array lưu component type thật để kiểm tra lúc chạy. Thiết kế mảng động generic an toàn là quản lý ranh giới giữa hai cơ chế đó.

### Tài liệu chuẩn để tra cứu

- Java Language Specification, §4.6 (*Type Erasure*) và §4.7 (*Reifiable Types*): https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html
- Java Language Specification, §10 (*Arrays*) và §10.5 (*Array Store Exception*): https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html
- Java Tutorials, *Non-Reifiable Types / Heap Pollution / Varargs*: https://docs.oracle.com/javase/tutorial/java/generics/nonReifiableVarargsType.html
- Java API, `java.lang.reflect.Array`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html
