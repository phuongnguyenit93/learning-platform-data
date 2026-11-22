# Đối chiếu mảng kiểm tra kiểu lúc chạy với generic kiểm tra lúc biên dịch

## Mục tiêu học tập

Trong Java, **mảng (array)** và **generics** đều giúp mô tả kiểu phần tử, nhưng cách chúng bảo vệ tính đúng kiểu khác nhau. Mảng lưu giữ kiểu thành phần tại runtime nên JVM có thể kiểm tra phép ghi trực tiếp. Phần lớn đối số kiểu generic bị xóa (*type erasure*), vì thế compiler kiểm tra các thao tác generic tại thời điểm biên dịch; JVM không có một runtime class riêng cho `List<String>`.

Sau bài này, bạn có thể:

- Phân biệt kiểm tra kiểu **runtime của mảng** với kiểm tra kiểu **compile time của generics**.
- Giải thích vì sao `String[]` có thể gán cho `Object[]` nhưng `List<String>` không thể gán cho `List<Object>`.
- Dự đoán chính xác hai lỗi quan trọng: `ArrayStoreException` khi ghi không đúng loại vào một mảng có component type cụ thể; `ClassCastException` khi đọc một generic collection đã bị nhiễm kiểu.
- Hiểu tại sao Java cấm tạo `new List<String>[10]` và `new T[10]`, nhưng cho phép `new List<?>[10]`.
- Chọn các giải pháp như `List<T>`, array factory `IntFunction<T[]>`, `Class<T>` kết hợp `Array.newInstance` và varargs an toàn.
- Nhận diện **heap pollution**, raw types và cảnh báo unchecked/varargs khi bảo trì mã Java.

Các ví dụ đầy đủ được thiết kế cho **Java 17+**. Chỉ những đoạn được ghi rõ là “chương trình đầy đủ” mới cần lưu thành tệp tương ứng để chạy độc lập; các đoạn mã ngắn khác dùng để giải thích một quy tắc hoặc lỗi biên dịch.

## 1. Hai cơ chế nhìn giống nhau nhưng khác bản chất

Hãy bắt đầu với hai loại cấu trúc chứa chuỗi:

```java
String[] names = new String[2];
java.util.List<String> labels = new java.util.ArrayList<>();
```

Ở Java source, cả hai đều gợi ý rằng phần tử phải là `String`. Tuy nhiên, cách Java hiện thực cam kết khác nhau:

| Câu hỏi | `String[]` | `List<String>` |
| --- | --- | --- |
| Kiểu phần tử có tồn tại trong runtime class không? | **Có:** component type là `String` | **Không** có runtime class riêng `List<String>` |
| Nơi kiểm tra chính | Compiler **và** JVM khi thực hiện phép ghi mảng | Chủ yếu compiler qua đối số generic |
| Nếu “lách” bằng tham chiếu rộng hơn? | `Object[]` có thể trỏ tới `String[]`; JVM vẫn kiểm tra khi ghi | Raw `List` có thể chèn phần tử sai với cảnh báo unchecked |
| Lỗi đặc trưng | `ArrayStoreException` tại phép ghi sai | `ClassCastException` khi một giá trị sai bị ép về kiểu kỳ vọng |
| Có covariant không? | Có: `String[]` là subtype của `Object[]` | Không: `List<String>` **không** là subtype của `List<Object>` |
| Tạo trực tiếp | `new String[2]` hợp lệ | `new ArrayList<String>()` hoặc `new ArrayList<>()` hợp lệ |

Từ khóa quan trọng:

- **Reifiable type:** kiểu có thể được thể hiện đầy đủ ở runtime theo quy tắc của ngôn ngữ. Kiểu mảng có component reifiable, chẳng hạn `String[]`, có đủ thông tin để kiểm tra phép ghi.
- **Non-reifiable parameterized type:** kiểu như `List<String>` chứa đối số generic không có runtime representation tương ứng để JVM phân biệt mọi `String` trong danh sách.
- **Type erasure:** cơ chế biên dịch các khai báo/tham chiếu generic thành descriptor phù hợp với JVM, đồng thời compiler có thể thêm cast ở những vị trí cần thiết.

Lưu ý: `String[]` cũng được compiler kiểm tra kiểu tại source; không nên phát biểu “mảng *chỉ* kiểm tra runtime”. Điểm khác biệt là **mảng có thêm kiểm tra cửa ghi ở JVM dựa trên component type thực**, kể cả khi một tham chiếu `Object[]` làm che đi loại phần tử ở source.

## 2. Mảng có runtime component type

Xem đoạn minh họa:

```java
String[] names = {"Lan", "Minh"};
Object[] asObjects = names; // Hợp lệ: mảng là covariant.
```

Cả hai biến đang tham chiếu **cùng một đối tượng mảng**. Vì đối tượng được tạo là `String[]`, runtime class của nó vẫn là `String[].class` và component type vẫn là `String.class`, dù biến `asObjects` có kiểu source là `Object[]`.

Một lời gọi hợp lệ:

```java
asObjects[0] = "Hoa";
```

Một lời gọi bị JVM từ chối tại lúc ghi:

```java
// Biên dịch được vì asObjects có kiểu source Object[].
// Khi chạy với đối tượng mảng thực String[], dòng sau ném ArrayStoreException:
asObjects[0] = Integer.valueOf(42);
```

Vì `Integer` không thể lưu vào mảng có component type thực là `String`, JVM phát sinh **`ArrayStoreException`** ngay tại biểu thức gán mảng. Giá trị cũ tại vị trí đó không bị thay bởi đối tượng sai kiểu.

Chính tính **covariance** của mảng tạo ra tình huống compiler không thể kết luận tại source: phép ghi `Object` phù hợp với biến `Object[]`, nhưng runtime component type của đối tượng có thể hẹp hơn. Java cho phép quan hệ subtype mảng này vì lý do lịch sử; kiểm tra store runtime bù lại sự thiếu chặt chẽ đó.

Ngược lại, với một biến khai báo trực tiếp `String[]`:

```java
String[] direct = new String[1];
// direct[0] = 42; // Lỗi biên dịch.
```

Compiler đã thấy ngay đối số không đúng kiểu, nên không cần đợi phép kiểm tra store của JVM cho trường hợp này.

## 3. Generics không giữ một runtime `List<String>` chuyên biệt

Xem:

```java
java.util.List<String> strings = new java.util.ArrayList<>();
java.util.List<Integer> numbers = new java.util.ArrayList<>();
```

Nếu tạo trực tiếp hai `ArrayList` trên, `strings.getClass() == numbers.getClass()` là `true`: cùng runtime class `ArrayList`. Đối số kiểu `String` và `Integer` là thông tin quan trọng cho compiler tại mã nguồn, nhưng không tạo hai runtime class tương ứng.

Với biến typed, Java từ chối phép thêm sai:

```java
strings.add("Java"); // Hợp lệ.
// strings.add(42); // Lỗi biên dịch: Integer không phù hợp String.
```

Thế còn khi một tham chiếu raw được sử dụng?

```java
java.util.List raw = strings;
raw.add(42); // Compiler cảnh báo unchecked.
```

Lời gọi có thể chạy và đưa một `Integer` vào chính danh sách mà `strings` trỏ đến. Vì `ArrayList` không có runtime component type `String` để kiểm tra trong phương thức `add(Object)`, nó không tự ném `ArrayStoreException` như mảng.

Lỗi thường xảy ra khi mã typed đọc dữ liệu:

```java
String value = strings.get(1); // Có thể ClassCastException.
```

Ở source, compiler hiểu `List<String>.get(...)` cho `String`. Nhưng bytecode của `List.get(int)` trả `Object` sau erasure; compiler có thể chèn **`checkcast java/lang/String`** tại điểm sử dụng. Nếu giá trị thật là `Integer`, phép cast thất bại và ném `ClassCastException`.

Đó là một ví dụ **heap pollution**: trạng thái dữ liệu trong một đối tượng collection không phù hợp với kiểu tham số hóa mà code tin tưởng. Java generics bảo vệ tốt khi dùng API typed đúng cách; raw types và unchecked operations có thể phá bảo đảm đó.

## 4. Chương trình A — So sánh hai loại lỗi trên cùng một lần chạy

Tạo tệp **`ArraysGenericsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public final class ArraysGenericsDemo {
    public static void main(String[] args) {
        String[] names = {"Lan", "Minh"};
        Object[] asObjects = names; // covariance
        System.out.println("array component: "
                + asObjects.getClass().getComponentType().getSimpleName());
        System.out.println("same array: " + (asObjects == names));

        try {
            asObjects[0] = 42;
        } catch (ArrayStoreException ex) {
            System.out.println("array write: "
                    + ex.getClass().getSimpleName());
        }
        System.out.println("array[0]: " + names[0]);

        List<String> strings = new ArrayList<>(List.of("Java"));
        List<Integer> numbers = new ArrayList<>(List.of(7));
        System.out.println("same list class: "
                + (strings.getClass() == numbers.getClass()));
        // List<Object> objects = strings; // Compile-time error: invariant

        List raw = strings; // intentionally unsafe
        raw.add(42);        // unchecked
        System.out.println("list contents: " + strings);

        try {
            String second = strings.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("generic read: "
                    + ex.getClass().getSimpleName());
        }

        List<?>[] wildcardArray = new List<?>[1];
        wildcardArray[0] = List.of("safe", 5);
        System.out.println("wildcard read: " + wildcardArray[0].get(0));
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all ArraysGenericsDemo.java
java ArraysGenericsDemo
```

**Stdout đã kiểm chứng:**

```text
array component: String
same array: true
array write: ArrayStoreException
array[0]: Lan
same list class: true
list contents: [Java, 42]
generic read: ClassCastException
wildcard read: safe
```

Lệnh `javac -Xlint:all` đã phát cảnh báo `[rawtypes]` cho `List raw` và `[unchecked]` cho `raw.add(42)`. Đây là **diagnostics của compiler**, không thuộc stdout của lệnh `java ArraysGenericsDemo`.

Giải thích các dòng:

1. `array component: String`: component type có thể truy cập qua `getClass().getComponentType()`, chứng minh runtime biết đây là mảng `String[]`.
2. `same array: true`: phép gán `Object[] asObjects = names` **không** tạo bản sao; mọi phép ghi đều ảnh hưởng cùng đối tượng.
3. `array write: ArrayStoreException`: JVM từ chối giá trị sai trước khi lưu; vì thế `array[0]` vẫn là `Lan`.
4. `same list class: true`: hai `ArrayList` với đối số generic khác nhau dùng một class runtime.
5. `list contents: [Java, 42]`: raw type đã bỏ qua rào chắn compile-time của `List<String>`, trong khi chính đối tượng `ArrayList` không tự phân biệt generic argument.
6. `generic read: ClassCastException`: lỗi xuất hiện khi giá trị thực được sử dụng như một `String`.
7. `wildcard read: safe`: mảng của `List<?>` được phép tạo trực tiếp; phần sau bài giải thích vì sao.

**Kết luận tạm thời:** Phép ghi sai vào mảng bị từ chối ngay ở runtime. Trong ví dụ generic bị phá qua raw type, việc thêm sai đã thành công và lỗi bị phát hiện muộn ở lúc đọc.

## 5. Vì sao mảng là covariant còn generic thường invariant?

**Array covariance**:

```java
String[] strings = new String[2];
Object[] objects = strings; // Hợp lệ.
```

Nếu `S` là kiểu tham chiếu subtype của `T`, thì `S[]` cũng là subtype của `T[]` theo quy tắc covariance mảng của Java. Quan hệ này cho phép một tham chiếu rộng hơn nhìn vào mảng hẹp, nhưng buộc JVM kiểm tra store runtime.

**Generic invariance**:

```java
List<String> strings = new ArrayList<>();
// List<Object> objects = strings; // Không hợp lệ.
```

`String` là subtype của `Object`, nhưng `List<String>` **không** là subtype của `List<Object>`. Nếu Java cho phép phép gán ấy, lời gọi `objects.add(42)` sẽ làm hỏng danh sách chuỗi mà không có runtime generic component type tương ứng để chặn ngay.

Nếu muốn đọc danh sách nhiều kiểu khác nhau, dùng wildcard:

```java
List<?> unknown = strings;
Object first = unknown.isEmpty() ? null : unknown.get(0);
// unknown.add("new"); // Không biên dịch: không biết kiểu phần tử.
```

`List<?>` vẫn là một kiểu tham số hóa có ràng buộc; **không phải raw type**. Vì kiểu phần tử chưa biết, compiler không cho thêm giá trị không phải `null` qua tham chiếu wildcard.

Đối với API cụ thể, wildcard có thể diễn tả phương hướng dữ liệu:

```java
static double sum(List<? extends Number> source) {
    double total = 0;
    for (Number n : source) {
        total += n.doubleValue();
    }
    return total;
}
```

Đoạn này là phương thức minh họa cần được đặt trong lớp có import `java.util.List`. Nó chấp nhận `List<Integer>` hoặc `List<Double>` để đọc `Number`, nhưng không cho phép tùy ý thêm một `Number` vì kiểu phần tử thực có thể hẹp hơn.

Không suy ra rằng “generic không thể đa hình”. **Invariance** nói về mối quan hệ giữa các tham số hóa `List<S>` và `List<T>`; wildcard `? extends`/`? super` cho phép biểu diễn quan hệ linh hoạt và an toàn khi cần.

## 6. Reification và giới hạn tạo generic arrays

Biểu thức tạo array `new ComponentType[n]` đòi **component type reifiable**, tức thông tin kiểu thích hợp phải có thể được runtime biểu diễn để JVM kiểm tra việc ghi. `String`, raw `List` và parameterized `List<?>` (mọi type arguments là wildcard `?` không giới hạn) đáp ứng yêu cầu; `List<String>`, `List<? extends Number>` và type variable `T` thì không.

```java
String[] words = new String[3];            // Hợp lệ.
List<?>[] lists = new List<?>[3];          // Hợp lệ.
// List<String>[] bad = new List<String>[3]; // Lỗi generic array creation.
// T[] bad = new T[3];                       // Lỗi khi T là type variable.
```

Một phần tử của `List<?>[]` có thể là `List<String>` hoặc `List<Integer>`: runtime component type chỉ là `List`, không phải một `List<String>` có thể xác minh từng phần tử. Việc cho phép trực tiếp `new List<String>[n]` sẽ tạo cam kết kiểu mà array store check không thể giữ khi người dùng ghi qua `Object[]` alias. **Không nhầm** `List<?>[]` với `List<Object>[]`, cũng không dùng unchecked cast để giả lập mảng các list chuỗi.

Quy tắc reifiable type, mảng chứa list tham số hóa và heap pollution được phân tích bằng ví dụ chạy riêng trong các bài về `new List<String>[]` và `List<?>[]`.

## 7. Khai báo `T[]` không phải cấp phát `new T[n]`

```java
class Holder<T> {
    private final T[] elements;
    Holder(T[] elements) { this.elements = elements; }
    T first() { return elements[0]; }
}
```

`Holder<String>` có thể **nhận** `new String[]{"A"}` từ caller, rồi đọc `first()` như `String`. Nhưng bên trong `Holder<T>` không thể viết `new T[n]`: `T` là type variable, không có runtime component class để tạo mảng đúng cho mọi cách tham số hóa. Kể cả `T extends Number`, mảng `Number[]` cũng không đương nhiên là `Integer[]`.

Đừng sửa bằng `(T[]) new Object[n]`: mảng thật vẫn có runtime class `Object[]`, nên caller yêu cầu `String[]` có thể gặp `ClassCastException`. Muốn tạo mảng đúng component type, hãy nhận một factory hoặc `Class<T>` đáng tin; chương trình kế tiếp minh họa hai cách, và bài chuyên sâu về `new T[]` giải thích giới hạn bytecode/erasure.

## 8. Chương trình B — Tạo typed array an toàn bằng factory hoặc `Class<T>`

Tạo tệp **`TypedArrayDemo.java`**:

```java
import java.lang.reflect.Array;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.IntFunction;

public final class TypedArrayDemo {
    static <T> T[] withFactory(IntFunction<T[]> factory, int n) {
        T[] result = factory.apply(n);
        return result;
    }

    static <T> T[] withClass(Class<T> elementType, int n) {
        Objects.requireNonNull(elementType);
        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(elementType, n);
        return result;
    }

    @SafeVarargs
    static <T> List<T> concat(List<? extends T>... groups) {
        List<T> result = new ArrayList<>();
        for (List<? extends T> group : groups) {
            result.addAll(group);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        String[] words = withFactory(String[]::new, 2);
        words[0] = "A";
        words[1] = "B";
        System.out.println("factory: " + Arrays.toString(words));

        Integer[] ids = withClass(Integer.class, 2);
        ids[0] = 10;
        System.out.println("reflection component: "
                + ids.getClass().getComponentType().getSimpleName());

        try {
            Object[] view = ids;
            view[1] = "wrong";
        } catch (ArrayStoreException ex) {
            System.out.println("reflection store: "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("concat: "
                + concat(List.of("x"), List.of("y")));
    }
}
```

Biên dịch và chạy:

```bash
javac -Xlint:all TypedArrayDemo.java
java TypedArrayDemo
```

**Stdout đã kiểm chứng:**

```text
factory: [A, B]
reflection component: Integer
reflection store: ArrayStoreException
concat: [x, y]
```

### Cách 1 — Factory `IntFunction<T[]>`

`String[]::new` là một **array constructor reference**: khi nhận độ dài `2`, nó tạo `String[2]` thực, không phải `Object[2]` được gán nhãn generic. Phương thức `withFactory` chỉ yêu cầu factory tạo đúng loại mảng mà caller cung cấp.

Ưu điểm: tránh phải cast `Object[]` thủ công và diễn tả rõ trách nhiệm tạo array. Với API dùng nhiều loại `T`, một factory thích hợp thường là cách giữ code generic mà vẫn bảo toàn component type tại runtime.

### Cách 2 — `Class<T>` với `Array.newInstance`

`Integer.class` được truyền vào tường minh, vì vậy reflection có đủ thông tin để cấp phát đối tượng mảng với component type là `Integer`. Kết quả thực sự là `Integer[]`, được chứng minh bởi dòng:

```text
reflection component: Integer
```

Trong `withClass`, phép cast `(T[])` được đặt trong phạm vi nhỏ có `@SuppressWarnings("unchecked")`. Do erasure, compiler không thể kiểm tra tổng quát cast từ `Object` trả bởi `Array.newInstance`; tuy nhiên ở ví dụ này việc truyền **`Class<T>` đúng kiểu**, không cho bên khác tùy tiện thay token, tạo căn cứ rằng mảng được cấp phát theo component type tương ứng.

`Class<T>` là token runtime cho lớp cụ thể, không tự khôi phục kiểu lồng nhau `List<String>` từ `List.class`. Tránh sử dụng một `Class` raw không có hợp đồng rồi tuyên bố rằng `List<String>[]` sẽ được kiểm tra đầy đủ.

### Mảng tạo đúng kiểu vẫn kiểm tra store ở runtime

Dù được tạo qua factory hay reflection, đối tượng `Integer[]` thực vẫn mang component type `Integer`. Phép viết một `String` qua biến `Object[]` rộng hơn lập tức bị từ chối bằng `ArrayStoreException`. Đây là kiểm chứng rằng cách cấp phát giữ đúng loại **mảng thực**, không chỉ giữ một chú thích generic ở source.

## 9. Generic method `T[]` trong bytecode: một chi tiết nâng cao

Bạn có thể tự xem phần chữ ký của `TypedArrayDemo` đã biên dịch:

```bash
javap -p -s TypedArrayDemo
```

Trích descriptor đã xác minh:

```text
static <T> T[] withFactory(java.util.function.IntFunction<T[]>, int);
  descriptor: (Ljava/util/function/IntFunction;I)[Ljava/lang/Object;

static <T> T[] withClass(java.lang.Class<T>, int);
  descriptor: (Ljava/lang/Class;I)[Ljava/lang/Object;
```

`[Ljava/lang/Object;` là descriptor của **`Object[]`**, tức kiểu erasure của `T[]` khi `T` không có giới hạn. Điều này **không mâu thuẫn** với việc `withFactory(String[]::new, 2)` trả một đối tượng thực là `String[]`: erased return descriptor của method và runtime class của đối tượng được trả là hai khía cạnh khác nhau.

Trình biên dịch có thể thêm `checkcast [Ljava/lang/String;` ở điểm gọi cần gán kết quả thành `String[]`. Vì factory/token tạo đúng component type, cast ấy thành công trong chương trình hợp lệ của ví dụ.

Nếu bạn thay factory bằng code luôn tạo `Object[]` rồi cast về `T[]`, phần source có thể trông giống nhau nhưng runtime class của kết quả không còn bảo đảm đúng kiểu, khiến cast ở caller có nguy cơ thất bại.

## 10. Chương trình C — Vì sao unchecked cast với mảng generic nguy hiểm

Đoạn thử nghiệm sau cố ý tạo heap pollution mà `ArrayStoreException` **không ngăn được**, vì component type runtime của mảng chỉ là `List`.

Tạo tệp **`UnsafeGenericArrayDemo.java`**:

```java
import java.util.List;

public final class UnsafeGenericArrayDemo {
    public static void main(String[] args) {
        List<?>[] backing = new List<?>[1];

        @SuppressWarnings("unchecked")
        List<String>[] strings = (List<String>[]) backing;

        Object[] objects = strings;
        objects[0] = List.of(123);

        System.out.println("array component: "
                + objects.getClass().getComponentType().getSimpleName());

        try {
            String value = strings[0].get(0);
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("polluted read: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -Xlint:all UnsafeGenericArrayDemo.java
java UnsafeGenericArrayDemo
```

**Stdout đã kiểm chứng:**

```text
array component: List
polluted read: ClassCastException
```

Các bước phân tích:

1. `new List<?>[1]` hợp lệ vì `List<?>` là reifiable; mảng thực có component type `List`.
2. Cast `(List<String>[]) backing` mang tính **unchecked** ở cấp source. Nó không xác thực rằng mỗi danh sách bên trong chỉ chứa `String`. Suppression trong ví dụ chỉ làm rõ vị trí thiếu bằng chứng, **không biến cast thành an toàn**.
3. Biến `Object[] objects` vẫn tham chiếu cùng mảng; `objects[0] = List.of(123)` được JVM cho phép vì đối tượng đưa vào là một `List`, phù hợp với component type runtime của array.
4. `strings[0].get(0)` được compiler xem như trả `String`, nhưng giá trị thực là `Integer`; `ClassCastException` xảy ra khi đọc/cast.

**Bài học:** Mảng kiểm tra được **loại đối tượng ở mỗi ô của mảng** (ở đây là `List`), không kiểm tra được **đối số generic bị xóa** của đối tượng ấy (`String` hay `Integer`). Vì vậy, dù mảng có store check runtime, nó vẫn không cứu được những cam kết generic được dựng lên bằng unchecked cast.

Không nên dùng đoạn thử nghiệm này làm thiết kế data structure trong sản phẩm. Nếu cần nhiều nhóm `List<String>`, một lựa chọn tự nhiên hơn là `List<List<String>>` với các thao tác typed.

## 11. Generic varargs cũng dùng array ở runtime

`List<T>... groups` là varargs có backing array mang component type generic thường **non-reifiable**. Caller/compiler có thể phải dùng array sau erasure và phát cảnh báo unchecked; nếu method gán một `List<Integer>` vào mảng bị người dùng xem là `List<String>[]`, một lần đọc `String` về sau có thể gây `ClassCastException`.

Trên Java 17, `@SafeVarargs` được phép ở constructor và method đủ điều kiện (static, final, private instance method). Annotation này **không** làm `List<T>` reifiable và không tự thêm runtime validation: người viết chịu trách nhiệm không ghi sai component, không để array varargs thoát ra vùng có thể mutate không kiểm soát.

```java
@SafeVarargs
static <T> List<T> concat(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return List.copyOf(result);
}
```

Ví dụ `concat` chỉ đọc các list, không sửa/lộ mảng varargs, trả collection mới; vì vậy có cơ sở cho annotation. Nếu API chỉ cần duyệt các phần tử, nhận `Collection<? extends T>` thường đơn giản hơn. Đây là một **giao điểm bổ sung** của mảng và generics, không phải đường vòng để hợp thức hóa `new T[n]` hay `new List<String>[n]`.

## 12. Runtime class và khả năng quan sát kiểu

Có một số câu hỏi riêng biệt thường bị trộn lẫn:

| Câu hỏi | Cách quan sát | Kết quả |
| --- | --- | --- |
| Mảng `String[]` thực có component type gì? | `array.getClass().getComponentType()` | `String.class` |
| Hai `ArrayList` với type arguments khác nhau có cùng runtime class không? | `list1.getClass() == list2.getClass()` | Có, nếu đều tạo trực tiếp từ cùng class `ArrayList` trong cùng ngữ cảnh class loading |
| Đối tượng nằm trong `List<String>` có kiểu thực gì? | `list.get(i).getClass()` khi phần tử khác `null` | Lớp thực của **giá trị**, không xác nhận đối số generic của mọi phần tử |
| JVM biết `ArrayList<String>` là subclass riêng không? | `list.getClass()` | Không có lớp runtime riêng cho cách tham số hóa ấy |
| `List<?>[]` kiểm tra gì khi ghi? | Runtime array store | Phần tử phải là `List` tương thích, không kiểm tra các type arguments bên trong |

Reflection có thể đọc **metadata generic trên khai báo** của lớp, field hoặc method (ví dụ `Field.getGenericType()`). Điều đó khác với việc runtime có khả năng kiểm tra toàn bộ tham số `String` trong một đối tượng `ArrayList<String>` cụ thể ở lúc gọi `add(Object)`. Không suy luận kiểu phần tử chỉ từ `getClass()` của collection.

Một chi tiết khác: `int[]` là một mảng primitive. `int[]` **không phải subtype của `Object[]`**, dù bản thân `int[]` là một `Object` và có runtime class riêng. Array covariance như ví dụ `String[] -> Object[]` áp dụng cho **mảng chứa kiểu tham chiếu** có quan hệ subtype phù hợp.

## 13. Trường hợp nào dùng array, trường hợp nào dùng collection generic?

Mảng và generic collection có ưu nhược điểm khác nhau; không nên tuyệt đối hóa một lựa chọn.

**Array thích hợp khi:**

- Số phần tử được tổ chức theo chỉ số và thường biết hoặc cố định độ dài.
- Cần giao tiếp với API yêu cầu array, đặc biệt các API cũ hoặc các giao diện cấp thấp.
- Cần mảng primitive như `int[]`, `double[]` để tránh boxing phần tử.
- Có component type cụ thể và muốn tận dụng store check runtime.

**Generic collection thích hợp khi:**

- Số phần tử thay đổi theo hoạt động chương trình.
- Cần các thao tác `add`, `remove`, traversal, transformation linh hoạt.
- Muốn mô hình hóa container lồng nhau như `List<List<String>>` mà không tạo generic arrays không an toàn.
- Muốn dùng wildcard để diễn đạt quan hệ kiểu giữa producer/consumer.

Một API có thể kết hợp cả hai. Ví dụ, hàm nhận `Collection<? extends T>` rồi trả `T[]` có thể yêu cầu một array factory hoặc type token. Quan trọng là **runtime component type của mảng trả về phải phù hợp với kiểu được hứa**.

Tránh truyền raw collection xuyên nhiều tầng ứng dụng rồi ép về generic ở cuối. Nếu phải tương tác với API legacy, kiểm tra dữ liệu tại ranh giới và chuyển về kiểu typed càng sớm càng tốt.

## 14. Những lỗi hiểu sai cần loại bỏ

**Sai 1 — “Mảng chỉ kiểm tra kiểu lúc chạy.”**

Mảng cũng được compiler kiểm tra với khai báo như `String[]`. Khác biệt là JVM biết runtime component type và có thêm kiểm tra store, cần thiết do covariance.

**Sai 2 — “Generics không an toàn vì bị xóa kiểu.”**

Trong chương trình dùng typed API đúng cách, compiler ngăn các phép ghi không phù hợp. Lỗi muộn trong ví dụ xuất hiện vì code **chủ động** dùng raw type/unchecked cast và vi phạm hợp đồng.

**Sai 3 — “`List<String>` là một subtype của `List<Object>` vì `String extends Object`.”**

Java generics invariant theo mặc định. Nếu API cần đọc nhiều loại list, dùng `List<?>` hoặc wildcard phù hợp.

**Sai 4 — “Dùng `new Object[n]` rồi cast là tạo được `T[]` thật.”**

Mảng thực vẫn là `Object[]`; phép cast ở caller khi yêu cầu `String[]` có thể thất bại. Dùng `IntFunction<T[]>` hoặc `Class<T>` để tạo đúng runtime component type khi cần.

**Sai 5 — “`new List<?>[n]` là bất hợp lệ giống `new List<String>[n]`.”**

`List<?>` là trường hợp reifiable với unbounded wildcard, nên có thể làm component type của array được tạo. `List<String>` không thỏa điều kiện đó.

**Sai 6 — “ArrayStoreException bảo đảm mọi danh sách trong mảng có đúng type arguments.”**

Runtime array kiểm tra object từng slot có phải `List` hay không. Nó không kiểm tra được `List<Integer>` khác `List<String>` ở runtime chỉ bằng array store check.

**Sai 7 — “Mọi `ClassCastException` trong generics đều xảy ra ngay khi `add`.”**

Sai kiểu có thể được thêm qua raw reference. Lỗi thường phát sinh khi code typed đọc phần tử và cast được compiler chèn để dùng dưới dạng `String`.

**Sai 8 — “`@SafeVarargs` sửa vấn đề heap pollution một cách tự động.”**

Annotation không thay đổi bytecode theo hướng bổ sung runtime component type cho generic. Nó là cam kết về tính an toàn của cách dùng varargs và cần được kiểm tra bằng lập luận/kiểm thử.

## 15. Thực hành bổ sung và đáp án

### Bài 1 — Dự đoán thời điểm lỗi

```java
String[] data = {"A"};
Object[] ref = data;
ref[0] = 9;
```

**Đáp án:** code biên dịch được, nhưng JVM ném `ArrayStoreException` tại dòng `ref[0] = 9`. `Integer` không thuộc `String[]`; phần tử cũ vẫn được giữ.

### Bài 2 — Vì sao phép gán generic không hợp lệ?

```java
List<String> a = new ArrayList<>();
// List<Object> b = a;
```

**Đáp án:** `List<String>` và `List<Object>` invariant. Cho phép sẽ tạo đường ghi `Object` không phải `String` vào danh sách chuỗi, trong khi runtime không lưu trữ generic argument để chặn như `String[]`.

### Bài 3 — Hai lỗi khác nhau

Sau khi `List raw = typedList`, code gọi `raw.add(100)`, rồi `String s = typedList.get(0)`. Lỗi có thể xuất hiện ở đâu?

**Đáp án:** compiler cảnh báo unchecked ở lời gọi raw `add`. Nếu phần tử được đọc thật là `Integer`, việc dùng nó làm `String` gây `ClassCastException`. Raw `ArrayList` không bảo đảm ném `ArrayStoreException` khi thêm giá trị.

### Bài 4 — Kiểm tra generic array creation

Trong các biểu thức sau, biểu thức nào hợp lệ?

```java
new String[3];
new List<?>[3];
// new List<String>[3];
// new T[3]; // T là type variable.
```

**Đáp án:** hai biểu thức đầu hợp lệ; hai biểu thức sau không thể dùng trực tiếp để tạo mảng trong Java source.

### Bài 5 — Phân tích một cast

Vì sao `(T[]) new Object[n]` không tương đương `String[]::new` khi `T = String`?

**Đáp án:** bản đầu tạo mảng thực `Object[]` rồi dùng unchecked cast, còn bản thứ hai tạo trực tiếp `String[]`. Runtime component type là khác nhau; `String[]` yêu cầu array thật có thành phần tương thích và `Object[]` không đáp ứng yêu cầu đó.

### Bài 6 — Thiết kế API

Bạn cần phương thức tạo một mảng của kiểu phần tử bất kỳ. Hãy đưa ra hai lựa chọn chữ ký:

```java
static <T> T[] create(java.util.function.IntFunction<T[]> factory, int size)
static <T> T[] create(Class<T> type, int size)
```

**Đáp án định hướng:** biến thể factory gọi `factory.apply(size)` (ví dụ `String[]::new`); biến thể token dùng `Array.newInstance(type, size)` và một cast được giới hạn cẩn thận. Hãy tự kiểm tra component type của mảng được trả về bằng reflection.

### Bài 7 — Vì sao mảng `List<?>[]` vẫn có thể chứa danh sách số?

```java
List<?>[] groups = new List<?>[1];
groups[0] = List.of(1, 2);
```

**Đáp án:** runtime array cần phần tử là `List`, còn wildcard không hứa loại phần tử cụ thể. Giá trị khi lấy ra được nhìn như `Object` nếu chưa kiểm tra thêm.

### Bài 8 — Chú thích varargs

Một generic varargs method có thể thêm các `List<Integer>` vào mảng varargs được caller coi là các `List<String>`, rồi vẫn gắn `@SafeVarargs` không?

**Đáp án:** không nên; thao tác đó gây heap pollution, phá lời cam kết an toàn mà annotation hàm ý. Chỉ dùng `@SafeVarargs` cho một cách hiện thực thực sự không gây các thao tác nguy hiểm trên varargs array.

## 16. Checklist tự đánh giá

Bạn có thể coi bài này hoàn thành khi giải thích được:

1. Mảng chứa kiểu tham chiếu có **covariance**, compiler vẫn kiểm tra kiểu, và JVM kiểm tra store theo runtime component type.
2. `List<String>` **invariant**, và generic arguments không tạo runtime class `ArrayList<String>` riêng.
3. `ArrayStoreException` khác `ClassCastException` ở vị trí phát hiện cũng như điều kiện gây lỗi.
4. `new List<String>[n]` và `new T[n]` không hợp lệ, còn `new List<?>[n]` hợp lệ.
5. `T[]` có thể làm kiểu trả về/field/parameter; nhưng muốn cấp phát đúng mảng runtime thì phải biết cách tạo component type.
6. Array factory hoặc `Class<T>` giúp tạo mảng đúng loại thực, thay vì dựa vào unchecked cast từ `Object[]`.
7. Generic varargs là một nơi cần thận trọng với heap pollution và `@SafeVarargs` là lời cam kết từ người viết.
8. Không coi phản ánh `getClass()` của collection là bằng chứng về type arguments của danh sách.

## Kết luận

**Mảng Java giữ runtime component type và kiểm tra phép ghi**, nên một `String[]` nhìn qua `Object[]` vẫn từ chối `Integer` bằng `ArrayStoreException`. **Generics kiểm tra kiểu chủ yếu ở compile time và bị type erasure**, nên `List<String>` không có “hàng rào store” runtime tương đương; raw type/unchecked cast có thể gây heap pollution, rồi `ClassCastException` khi đọc. Chính sự khác nhau ấy giải thích vì sao Java giữ array covariance nhưng generics invariant, và vì sao tạo array của non-reifiable generic types bị hạn chế. Khi thật sự cần `T[]`, hãy dùng factory hoặc token kiểu đáng tin; còn với cấu trúc generic linh hoạt, ưu tiên collections và các wildcard diễn đạt đúng hợp đồng.
