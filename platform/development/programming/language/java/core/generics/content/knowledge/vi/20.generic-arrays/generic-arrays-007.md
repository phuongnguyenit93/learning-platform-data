# Tạo mảng generic bằng IntFunction<T[]> hoặc thông tin Class<T> trong Java

## Mục tiêu học tập

Java cho phép một phương thức generic xử lý các phần tử kiểu `T`, nhưng không cho viết trực tiếp `new T[n]`. Đây không phải hạn chế về cú pháp đơn thuần: JVM cần biết **kiểu phần tử thực của mảng tại runtime** để kiểm tra thao tác ghi, trong khi `T` của generics bị *type erasure* và thường không có class token riêng.

Có hai cách phổ biến để tạo đúng loại mảng mà vẫn giữ API generic:

1. **Nhận `IntFunction<T[]>`** — người gọi cung cấp hàm tạo mảng như `String[]::new`. Phương pháp này là lựa chọn tự nhiên khi Java API đã dùng `Collection.toArray(IntFunction<T[]>)` hoặc khi caller biết cách cấp phát loại mảng mong muốn.
2. **Nhận `Class<T>`** — người gọi cung cấp `String.class` hoặc `Integer.class`, còn phương thức dùng `java.lang.reflect.Array.newInstance(componentType, n)` để tạo mảng có component type đúng tại runtime.

Sau bài này, bạn sẽ:

- Giải thích được vì sao `new T[n]` và `new List<String>[n]` bị compiler từ chối.
- Viết, gọi và kiểm thử hai API tạo mảng `<T> T[]` theo factory và class token.
- Hiểu khác biệt giữa **component type runtime**, **type inference ở compile time**, và **metadata generic**.
- Sử dụng `Collection.toArray(IntFunction<T[]>)`, `Collection.toArray(T[])` và `Array.newInstance` đúng mục đích.
- Tránh những lỗi như ép `Object[]` sang `String[]`, dùng `List<String>.class` không tồn tại, hoặc bỏ qua nguy cơ khi caller cung cấp factory không phù hợp.

## 1. Điều kiện nền tảng: `new T[n]` bị cấm

```java
static <T> T[] wrong(int length) {
    // return new T[length]; // generic array creation
    return null; // Chỉ giúp snippet biên dịch khi minh họa.
}
```

Type variable `T` không có một runtime component class cụ thể; erasure của `T` (thường là `Object`) không có nghĩa caller mong nhận `Object[]`. JVM cần biết component type thật để kiểm tra `array[i] = value`; `Object[]` không phải `String[]`, kể cả khi hiện chứa toàn chuỗi.

Bài này tập trung **hai cách tạo đúng runtime component type**: nhận `IntFunction<T[]>` do caller cung cấp, hoặc nhận `Class<T>` rồi dùng `Array.newInstance`. Cơ chế erasure, array covariance và generic array creation đã được chứng minh riêng; điều quan trọng tại đây là hợp đồng của factory/token và cách kiểm tra kết quả cấp phát.

## 2. So sánh hai chiến lược chính

| Tiêu chí | `IntFunction<T[]>` | `Class<T>` kết hợp `Array.newInstance` |
| --- | --- | --- |
| Dữ liệu caller cung cấp | Một hàm nhận chiều dài và trả mảng, ví dụ `String[]::new`. | Token kiểu phần tử, ví dụ `String.class`. |
| Cách cấp phát | Gọi `factory.apply(n)`. | Gọi `Array.newInstance(componentType, n)`. |
| Có biết component type thật lúc chạy? | Có, nhờ mảng do factory tạo. | Có, nhờ `Class<T>` truyền vào reflection. |
| Có cần unchecked cast bên trong helper? | Không, nếu chỉ gọi factory và nhận `T[]`. | Có cast từ kết quả `Object` của reflection về `T[]`; nên cô lập tại một chỗ. |
| Phù hợp nhất với | API caller-side lambda/constructor reference, các tiện ích collection. | Reflection, framework, API đã truyền `Class<T>`, tạo mảng khi chỉ có token kiểu phần tử. |
| Có hỗ trợ mảng của `List<String>` như component reified không? | Không thể tạo `new List<String>[n]` trực tiếp; chỉ có thể dùng mảng có component runtime là List. | `List<String>.class` không tồn tại; `List.class` không giữ đối số String. |
| Nguy cơ chính | Factory trả `null`, độ dài khác mong đợi hoặc mảng có runtime component không phù hợp. | Truyền nhầm token, thiếu null check, kiểu primitive và cast unchecked ngoài phạm vi an toàn. |

**Nguyên tắc:** Chọn một điểm mà **thông tin kiểu thực được cung cấp rõ ràng từ caller**. Không tạo `Object[]` và kỳ vọng compiler/JVM sẽ biến nó thành mảng T nhờ một cast generic.

## 3. Cách 1: `IntFunction<T[]>` và constructor reference

`java.util.function.IntFunction<R>` là functional interface với phương thức:

```java
R apply(int value);
```

Với `IntFunction<T[]>`, giá trị `R` được chuyên biệt hóa thành `T[]`: hàm nhận một số nguyên và trả về một mảng phù hợp.

Ví dụ:

```java
java.util.function.IntFunction<String[]> maker = String[]::new;
String[] result = maker.apply(3);
result[0] = "An";
```

`String[]::new` là một *array constructor reference*: khi được gọi với số 3, nó tạo `new String[3]`. Nó không dùng `new T[3]`; caller đã xác định component runtime là String.

### 3.1. Helper cấp phát mảng

Đặt trong một lớp:

```java
static <T> T[] allocateWithFactory(
        int length, java.util.function.IntFunction<T[]> factory) {
    if (length < 0) {
        throw new IllegalArgumentException("negative length");
    }
    T[] array = java.util.Objects.requireNonNull(
            factory.apply(length), "array");
    if (array.length != length) {
        throw new IllegalArgumentException("unexpected array length");
    }
    return array;
}
```

Đây là phương thức riêng lẻ minh họa; chương trình chạy đầy đủ ở phần 7 có chính implementation này.

Sử dụng:

```java
String[] names = allocateWithFactory(3, String[]::new);
Integer[] scores = allocateWithFactory(2, Integer[]::new);
```

Compiler suy luận T từ cả loại kết quả và array constructor reference. Không có unchecked cast ở đây: factory trả về đúng biểu thức `T[]` theo hợp đồng generic của nó.

Điều kiện `array.length == length` là lựa chọn thiết kế của **helper này**, không phải nghĩa vụ mặc định của mọi API nhận `IntFunction<T[]>`. Nó giúp phát hiện factory không thực hiện đúng hợp đồng cấp phát mà helper mong đợi. Nếu muốn cho phép mảng có độ dài khác, cần thay đổi hợp đồng và cách xử lý rõ ràng.

### 3.2. Vì sao constructor reference hay hơn lambda trong trường hợp đơn giản?

Hai biểu thức sau tương đương về mục đích:

```java
java.util.function.IntFunction<String[]> a = size -> new String[size];
java.util.function.IntFunction<String[]> b = String[]::new;
```

Constructor reference thường ngắn gọn, trực tiếp thể hiện kiểu mảng cần cấp phát và không cần viết lặp lại tên tham số. Lambda vẫn hữu ích nếu cần kiểm tra kích thước, log, caching hay một chiến lược cấp phát đặc biệt.

**Không nhầm `String::new` với `String[]::new`**: cái đầu là constructor của một đối tượng String; cái sau là constructor reference cho mảng String.

## 4. Cách 2: `Class<T>` và `Array.newInstance`

Khi caller đã có token `Class<T>`, ví dụ `String.class`, có thể dùng reflection:

```java
java.lang.reflect.Array.newInstance(String.class, 3);
```

Phương thức `Array.newInstance(Class<?> componentType, int length)` nhận kiểu phần tử và chiều dài rồi trả về một đối tượng mảng có **component type runtime chính xác theo token**. Giá trị trả về được khai báo là `Object`, vì API reflection còn hỗ trợ mảng primitive và mảng nhiều chiều.

Để cung cấp một API generic trả về `T[]`, có thể viết:

```java
@SuppressWarnings("unchecked")
static <T> T[] allocateWithClass(Class<T> componentType, int length) {
    java.util.Objects.requireNonNull(componentType, "componentType");
    if (componentType.isPrimitive()) {
        throw new IllegalArgumentException("reference components only");
    }
    return (T[]) java.lang.reflect.Array.newInstance(componentType, length);
}
```

Ví dụ:

```java
String[] names = allocateWithClass(String.class, 4);
Number[] numbers = allocateWithClass(Number.class, 2);
Integer[] scores = allocateWithClass(Integer.class, 3);
```

Trong các trường hợp này, mảng thực được tạo mang lần lượt component type String, Number và Integer. Phép `@SuppressWarnings("unchecked")` được đặt **tại đúng phương thức** chứa cast, không lan ra toàn bộ ứng dụng. Sự an toàn dựa vào lập luận: token `Class<T>` chỉ định component type mà `Array.newInstance` dùng để tạo mảng; vì thế kết quả là mảng của T đối với các **reference component types**.

### 4.1. Vì sao phải cân nhắc `isPrimitive()`?

Reflection có thể tạo mảng nguyên thủy:

```java
int[] rawPrimitives =
        (int[]) java.lang.reflect.Array.newInstance(int.class, 2);
```

Nhưng một `int[]` **không phải** `Integer[]` hay `Object[]`. Generic array `T[]` trong helper thông thường được sử dụng như mảng tham chiếu, nên wrapper ở trên chủ động từ chối `componentType.isPrimitive()` để có hợp đồng rõ ràng.

Chi tiết dễ nhầm: trong biểu thức Java, `int.class` có kiểu tĩnh tương ứng `Class<Integer>`, nhưng đối tượng token vẫn **mô tả primitive int**, không mô tả wrapper Integer. Do đó:

- `Integer.class` tạo component type `Integer`.
- `int.class` tạo component type `int` nếu dùng `Array.newInstance` trực tiếp.
- Đừng xem autoboxing là cơ chế tự chuyển mảng `int[]` thành `Integer[]`; autoboxing áp dụng ở các biểu thức giá trị, không biến đổi hai loại array.

Nếu API thật sự cần mảng primitive, hãy cung cấp API rõ ràng trả về `Object` hoặc một loại mảng primitive cụ thể, thay vì cố nhét chúng vào `<T> T[]`.

### 4.2. Kiểm tra component type tại runtime

Mảng có thể tự báo loại phần tử:

```java
String[] names = allocateWithClass(String.class, 2);
System.out.println(
        names.getClass().getComponentType().getSimpleName());
```

Kết quả:

```text
String
```

Thông tin này xuất phát từ đối tượng mảng thực, không phải chỉ từ ký hiệu `T` ở mã nguồn. Điều đó cũng giải thích vì sao array store check có thể từ chối đối tượng sai kiểu ngay lúc ghi.

## 5. Trường hợp phổ biến nhất: `Collection.toArray`

Nếu đã có một `Collection<T>` hoặc `List<T>` và cần đổi sang mảng, **thường không cần viết lại helper tạo mảng**: Java Collections Framework đã có API hỗ trợ.

### 5.1. `toArray(T[] a)`

Ví dụ:

```java
java.util.List<String> values = java.util.List.of("A", "B");
String[] array = values.toArray(new String[0]);
```

`toArray(T[] a)` dùng component runtime của mảng truyền vào để tạo mảng kết quả khi mảng đầu vào không đủ sức chứa. Nếu `a` có đủ chỗ, kết quả có thể chính là `a`; khi thừa chỗ, vị trí ngay sau phần tử cuối được gán `null` theo hợp đồng API.

Có thể truyền mảng đúng kích thước:

```java
String[] exact = values.toArray(new String[values.size()]);
```

Đừng khẳng định việc truyền mảng độ dài đúng luôn nhanh hơn truyền mảng zero-length: chi phí và tối ưu hóa phụ thuộc JDK, loại collection và hoàn cảnh đo. Hãy chọn cách dễ đọc trước, dùng benchmark khi hiệu năng thật sự quan trọng.

### 5.2. `toArray(IntFunction<T[]> generator)`

Từ Java 11, `Collection` có overload thuận tiện:

```java
String[] array = java.util.List.of("A", "B").toArray(String[]::new);
```

Cách này gọn, thể hiện trực tiếp component type và thường là lựa chọn tốt khi đã có Collection.

**Một điểm quan trọng về đối số truyền cho factory:** default implementation của `Collection.toArray(IntFunction<T[]>)` gọi `generator.apply(0)` rồi chuyển mảng kết quả cho `toArray(T[])`. Vì vậy đừng viết generator với giả định rằng tham số luôn bằng `collection.size()`. Trong chương trình được kiểm chứng ở phần 7, factory thực sự nhận `0` nhưng kết quả vẫn có đủ hai phần tử.

Sự khác nhau:

```java
// Helper tự viết: chủ động gọi factory bằng kích thước yêu cầu.
T[] array = factory.apply(length);

// Collection.toArray(IntFunction): default implementation gọi generator với 0.
// Collection sau đó tự tạo/điền mảng kết quả đúng kích thước.
String[] names = List.of("A", "B").toArray(String[]::new);
```

Dòng dùng `T` ở đầu là **mô tả trong ngữ cảnh generic**, không phải chương trình độc lập. Khi thiết kế một callback dạng `IntFunction<T[]>`, phải đọc hợp đồng của **API gọi callback**, không suy ra ý nghĩa của số nguyên chỉ từ tên interface.

### 5.3. Sao chép từ `Collection<? extends T>` sang mảng T

Nếu nguồn là `Collection<Integer>` còn đích mong muốn `Number[]`, có thể dùng factory:

```java
static <T> T[] copyToArray(
        java.util.Collection<? extends T> source,
        java.util.function.IntFunction<T[]> factory) {
    return source.toArray(factory.apply(0));
}
```

Caller:

```java
Number[] values = copyToArray(
        java.util.List.of(2, 5), Number[]::new);
```

Phương thức tạo một mảng có component type runtime Number, đưa các Integer vào đó hợp lệ vì Integer là subtype của Number. Việc đưa rộng sang Number[] ở đây có chủ đích; khác với chuyện ép một mảng Object[] thành String[] không có bằng chứng.

Nếu API không cần helper riêng, dùng `Collection.toArray(Number[]::new)` trực tiếp cũng có thể đáp ứng cùng mục đích.

## 6. Sử dụng `Class<T>` để copy một collection

Có thể kết hợp hai bước: tạo mảng qua class token và đổ phần tử từ collection vào.

```java
static <T> T[] copyWithClass(
        java.util.Collection<? extends T> source,
        Class<T> componentType) {
    T[] target = allocateWithClass(componentType, source.size());
    return source.toArray(target);
}
```

Đây là phương thức thuộc cùng lớp đã có `allocateWithClass` ở phần 4, và có bản chạy đầy đủ ở phần 7.

Ví dụ:

```java
Number[] result = copyWithClass(
        java.util.List.of(3, 4), Number.class);
```

Khi nguồn có phần tử không tương thích với component type thực của mảng, `Collection.toArray` có thể ném `ArrayStoreException`. Trong một chương trình chỉ sử dụng generics an toàn và truyền token phù hợp, compiler thường ngăn các cách gọi không tương thích. Nhưng nếu dữ liệu đã bị ô nhiễm bởi raw type, unchecked cast hoặc nguồn không tin cậy, runtime array store check vẫn là lớp phòng vệ.

**Cần phân biệt:** `Class<T>` mô tả một component type runtime có thể dùng làm mảng, chứ không thể biểu diễn các đối số generic lồng sâu như `List<String>`. Cách dùng `copyWithClass(..., List.class)` chỉ mô tả mảng của các List, không kiểm tra bên trong từng List có chứa String.

## 7. Chương trình Java 17 hoàn chỉnh

**Tệp `GenericArrayFactoriesDemo.java`:**

```java
import java.lang.reflect.Array;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntFunction;

public class GenericArrayFactoriesDemo {
    static <T> T[] allocateWithFactory(int length, IntFunction<T[]> factory) {
        if (length < 0) throw new IllegalArgumentException("negative length");
        T[] array = Objects.requireNonNull(factory.apply(length), "array");
        if (array.length != length) {
            throw new IllegalArgumentException("unexpected array length");
        }
        return array;
    }

    @SuppressWarnings("unchecked")
    static <T> T[] allocateWithClass(Class<T> componentType, int length) {
        Objects.requireNonNull(componentType, "componentType");
        if (componentType.isPrimitive()) {
            throw new IllegalArgumentException("reference components only");
        }
        return (T[]) Array.newInstance(componentType, length);
    }

    static <T> T[] copyToArray(
            Collection<? extends T> source, IntFunction<T[]> factory) {
        return source.toArray(factory.apply(0));
    }

    static <T> T[] copyWithClass(
            Collection<? extends T> source, Class<T> componentType) {
        T[] target = allocateWithClass(componentType, source.size());
        return source.toArray(target);
    }

    static <T> List<T> newList() {
        return new ArrayList<>();
    }

    public static void main(String[] args) {
        String[] slots = allocateWithFactory(3, String[]::new);
        slots[0] = "A";
        System.out.println("factory=" + Arrays.toString(slots));
        System.out.println("factoryComponent="
                + slots.getClass().getComponentType().getSimpleName());

        Integer[] scores = allocateWithClass(Integer.class, 2);
        scores[0] = 7;
        System.out.println("class=" + Arrays.toString(scores));
        System.out.println("classComponent="
                + scores.getClass().getComponentType().getSimpleName());

        Number[] wider = copyToArray(List.of(2, 5), Number[]::new);
        System.out.println("copiedNumbers=" + Arrays.toString(wider));

        String[] names = List.of("An", "Binh").toArray(String[]::new);
        System.out.println("library=" + Arrays.toString(names));

        AtomicInteger requestedLength = new AtomicInteger(-1);
        String[] viaCollection = List.of("X", "Y").toArray(length -> {
            requestedLength.set(length);
            return new String[length];
        });
        System.out.println("collectionResult=" + Arrays.toString(viaCollection));
        System.out.println("generatorRequested=" + requestedLength.get());

        Number[] fromClass = copyWithClass(List.of(3, 4), Number.class);
        System.out.println("copyClass=" + Arrays.toString(fromClass));

        try {
            String[] words = allocateWithFactory(2, String[]::new);
            Object[] alias = words;
            alias[0] = 99;
        } catch (ArrayStoreException error) {
            System.out.println("storeCheck=" + error.getClass().getSimpleName());
        }

        try {
            allocateWithClass(int.class, 2);
        } catch (IllegalArgumentException error) {
            System.out.println("primitiveGuard=" + error.getMessage());
        }

        List<?>[] lists = new List<?>[2];
        lists[0] = List.of("one");
        lists[1] = List.of(10);
        System.out.println("wildcardArray=" + lists[0] + "|" + lists[1]);
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 -Xlint:all GenericArrayFactoriesDemo.java
java GenericArrayFactoriesDemo
```

**Stdout đã kiểm chứng:**

```text
factory=[A, null, null]
factoryComponent=String
class=[7, null]
classComponent=Integer
copiedNumbers=[2, 5]
library=[An, Binh]
collectionResult=[X, Y]
generatorRequested=0
copyClass=[3, 4]
storeCheck=ArrayStoreException
primitiveGuard=reference components only
wildcardArray=[one]|[10]
```

Chương trình đã biên dịch với `--release 17 -Xlint:all` và chạy thành công trong kiểm thử. Các chi tiết quan trọng:

- `slots` thật sự là `String[]` có ba vị trí; vị trí chưa gán có giá trị mặc định `null`.
- `scores` thật sự là `Integer[]` do reflection tạo, không phải `int[]`.
- `copyToArray` dùng factory Number[] để nhận phần tử Integer theo quan hệ subtype.
- `Collection.toArray(String[]::new)` trực tiếp trả về `String[]`.
- Với implementation `List.of(...).toArray(generator)` đã chạy, generator được gọi bằng số 0; Collection vẫn tạo kết quả đúng độ dài sau đó.
- `alias[0] = 99` chứng minh mảng String[] vẫn được JVM kiểm tra đúng component type tại runtime.
- Helper dựa `Class<T>` từ chối primitive token theo hợp đồng đã thiết kế.
- `List<?>[]` hợp lệ nhưng không mang cam kết rằng mọi List bên trong đều có cùng đối số generic.

## 8. Các lỗi biên dịch liên quan cần nhận diện

**Tệp `InvalidArrayCreation.java` — cố ý không biên dịch:**

```java
import java.util.List;

class InvalidArrayCreation {
    static <T> T[] make(int length) {
        return new T[length];
    }

    List<String>[] lists = new List<String>[2];
}
```

Lệnh:

```bash
javac --release 17 InvalidArrayCreation.java
```

Compiler từ chối cả hai biểu thức bằng lỗi có phần cốt lõi:

```text
error: generic array creation
```

Hai trường hợp có cơ sở liên quan nhưng khác nhau:

1. `new T[length]`: T là type variable, không có class runtime độc lập để tạo mảng.
2. `new List<String>[2]`: kiểu phần tử `List<String>` không *reifiable*, do JVM không có component runtime phân biệt tham số generic String.

Trong khi đó:

```java
String[] strings = new String[2];    // Hợp lệ.
List<?>[] lists = new List<?>[2];    // Hợp lệ.
List[] rawLists = new List[2];       // Hợp lệ nhưng là raw type.
```

Đoạn này minh họa các khai báo trong phạm vi có import `List`. `List<?>` là reifiable theo quy tắc của Java do mọi đối số là wildcard không giới hạn. Tuy nhiên, `List<?>[]` có component runtime là List, và **không** kiểm tra được tham số kiểu phần tử bên trong mỗi List.

### `List<String>.class` có giúp được không?

Không. Biểu thức:

```java
// Không hợp lệ:
// Class<List<String>> token = List<String>.class;
```

không có trong cú pháp class literal của Java. `List.class` có thể tạo mảng của List ở mức raw runtime, nhưng không biến nó thành một mảng có component type `List<String>` reified.

Nếu bài toán cần lưu **nhiều List<String>**, thường có thể dùng `List<List<String>>` để tránh tạo generic array. Nếu phải làm việc với mảng do API cũ yêu cầu, cần một giải pháp được kiểm soát, xác thực dữ liệu và giới hạn cast unchecked; không thể yêu cầu JVM tự kiểm tra sâu các đối số generic chỉ bằng `List.class`.

## 9. Vì sao ép `Object[]` thành `T[]` là bẫy?

Một cách làm trông ngắn nhưng nguy hiểm:

```java
// KHÔNG NÊN DÙNG:
@SuppressWarnings("unchecked")
static <T> T[] wrongArray(int length) {
    return (T[]) new Object[length];
}
```

Cast sang `T[]` ở mã nguồn generic không thay đổi **loại mảng được cấp phát**. Đối tượng vẫn là `Object[]`. Nếu caller viết:

```java
// Dùng wrongArray ở trên:
String[] names = wrongArray(2);
```

kết quả có thể ném `ClassCastException` ở phía caller khi cần chuyển Object[] thành String[]. Đây không phải vấn đề “JVM quên generic nên mọi mảng đều dùng được”: runtime biết rất rõ Object[] khác String[].

Hai trường hợp so sánh:

```text
new Object[2] -> runtime type: Object[]
new String[2] -> runtime type: String[]

Đặt cast (T[]) trước Object[] không biến Object[] thành String[].
String[]::new và Array.newInstance(String.class, 2) thật sự tạo String[].
```

Ngoài ra, `ArrayStoreException` là một kiểu lỗi khác: nó xảy ra khi bạn **ghi phần tử sai kiểu vào một mảng tham chiếu** đã có component type thực. `ClassCastException` có thể xảy ra khi bạn **ép tham chiếu mảng** hoặc giá trị trả về sang một kiểu không tương thích.

### Factory cũng cần có hợp đồng rõ ràng

`IntFunction<T[]>` dựa vào caller cung cấp factory có kiểu đúng. Nếu caller cố tình dùng raw type hoặc unchecked cast để cung cấp một factory trả mảng không phù hợp, hệ thống có thể gặp lỗi kiểu ở một thời điểm nào đó. Một chữ ký generic không tự kiểm tra mọi trường hợp đã cố ý vượt qua type safety.

Bởi vậy nên:

- Dùng array constructor reference rõ ràng, ví dụ `String[]::new`.
- Tránh factory `length -> (T[]) new Object[length]`.
- Quy định rõ có chấp nhận `null`, chiều dài khác hay không; helper `allocateWithFactory` ở trên kiểm tra hai yếu tố này.
- Hạn chế dùng `@SuppressWarnings`; chỉ dùng khi có lập luận an toàn tại một điểm nhỏ, ví dụ phản chiếu với `Class<T>` chính xác.

## 10. Factory không biến generics thành reified

Mảng được tạo bằng `String[]::new` hoặc `Array.newInstance(String.class,n)` có component type thật là `String`; nhưng `List<String>` vẫn không có runtime class specialization. `List.class` chỉ đại diện raw `List`, còn `List<String>.class` không hợp lệ.

```java
Object[] names = new String[2];
try {
    names[0] = 12;
} catch (ArrayStoreException expected) {
    System.out.println("Rejected by runtime String[] component type");
}
```

Mảng tham chiếu vẫn covariant, trong khi `List<String>` không gán được cho `List<Object>`. Khi cần đọc từ `Collection<Integer>` để tạo `Number[]`, dùng `Collection<? extends Number>` và factory `Number[]::new`. Tránh unchecked cast `(T[]) new Object[n]`: factory/token cung cấp **bằng chứng component runtime** mà cast đơn thuần không có.

Đây là ranh giới của hai phương pháp cấp phát, không phải lời hứa kiểm tra nested generic arguments hoặc dữ liệu đầu vào thiếu tin cậy.

## 11. Sự khác nhau giữa `Class<T>` và `Class<T[]>`

Đôi khi một API nhận **token của loại phần tử**:

```java
Class<String> component = String.class;
```

Khi đó `Array.newInstance(component, length)` là cách tự nhiên để tạo mảng.

Một API khác có thể đã nhận **token của loại mảng hoàn chỉnh**:

```java
Class<String[]> arrayType = String[].class;
System.out.println(arrayType.getComponentType().getSimpleName());
```

Kết quả:

```text
String
```

`Class<T[]>` mô tả toàn bộ kiểu mảng `T[]`, còn `Class<T>` mô tả kiểu phần tử. Không được truyền `String[].class` như thể nó là `Class<String>`: hai token có ý nghĩa khác nhau.

Ngoài ra, `Class<T>` không biểu diễn đầy đủ các kiểu tham số hóa sâu như `List<String>`. Nếu một thư viện cần lưu mô tả `List<String>` để deserialize hoặc thao tác reflection generic, có thể cần `java.lang.reflect.Type`/`ParameterizedType`/type reference, **không** chỉ `Class<T>`. Nhưng `Type` là mô tả kiểu; không thể truyền một `ParameterizedType` tùy ý cho `Array.newInstance(Class, length)` để tạo component runtime không tồn tại.

## 12. Chiều dài, mảng rỗng và trường hợp biên

### 12.1. Chiều dài bằng 0

Cả `String[]::new` với n = 0 và `Array.newInstance(String.class, 0)` đều tạo được mảng String có độ dài 0. Mảng rỗng vẫn mang runtime component type String; nó không “mất kiểu” vì không có phần tử.

`Collection.toArray(String[]::new)` có thể dùng generator với độ dài 0 như một tín hiệu tạo mảng đúng loại; khi collection có nhiều phần tử hơn, overload chịu trách nhiệm cung cấp mảng kết quả phù hợp.

### 12.2. Chiều dài âm

`new String[-1]` và `Array.newInstance(String.class, -1)` theo hành vi cấp phát mảng có thể ném `NegativeArraySizeException`. Helper `allocateWithFactory` trong ví dụ **cố ý tự kiểm tra và ném `IllegalArgumentException`** để thể hiện một hợp đồng đầu vào riêng; đừng suy ra đó là hành vi mặc định của mọi constructor reference.

### 12.3. Factory trả `null`

`IntFunction<T[]>` là functional interface nên về mặt kiểu trả về có thể trả `null`. Nếu bạn định dùng mảng ngay, nên kiểm tra và báo lỗi gần ranh giới factory. `Objects.requireNonNull(factory.apply(length))` sẽ ném `NullPointerException` với thông báo thích hợp, thay vì để lỗi phát sinh muộn trong code xử lý.

### 12.4. Factory trả sai kích thước

Trong helper tự viết, có thể yêu cầu `array.length == length`. Nhưng `Collection.toArray` có các quy tắc riêng cho mảng truyền vào: nếu quá nhỏ, nó có thể cấp phát mảng mới đúng loại; nếu đủ chỗ, nó điền vào mảng sẵn có theo hợp đồng.

Vì vậy không nên thêm kiểm tra “factory luôn phải trả đúng collection.size()” khi làm việc với `Collection.toArray(IntFunction)`, vì default implementation có thể chủ động gọi factory với 0.

### 12.5. Primitive arrays

`int[]`, `double[]` là các mảng nguyên thủy, khác với `Integer[]`, `Double[]`. `Class<T>`/`T[]` trong generic helper tham chiếu không tự hỗ trợ tạo hoặc trả về mảng primitive theo cách thông thường. Nếu cần mảng primitive, dùng API cụ thể (`new int[n]`, `IntStream.toArray()`...) hoặc reflection với hợp đồng return type rõ ràng.

## 13. Các tình huống thực tế nên chọn cách nào?

| Tình huống | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Chuyển `List<String>` sang `String[]` | `list.toArray(String[]::new)` | Thư viện chuẩn, ít mã, component type rõ ràng. |
| Viết helper cấp phát mảng generic và caller biết loại mảng | `IntFunction<T[]>`, caller truyền `TConcrete[]::new` | Không cần unchecked cast trong helper. |
| Viết framework có sẵn `Class<T>` | `Array.newInstance(Class<T>, n)` | Token cung cấp runtime component type. |
| Sao chép `List<Integer>` sang `Number[]` | `toArray(Number[]::new)` hoặc factory tương ứng | Nhận quan hệ subtype an toàn. |
| Cần tạo `int[]` | Cấp phát primitive trực tiếp/primitive API | `int[]` không phải `Integer[]`. |
| Muốn tạo mảng các `List<String>` | Cân nhắc `List<List<String>>`; nếu cần mảng, chỉ có runtime component List | Không có `List<String>.class`. |
| Dữ liệu từ API legacy/không đáng tin | Xác thực phần tử trước khi lưu ở cấu trúc typed | Factory không kiểm tra sâu nested generics. |
| Không thật sự cần mảng | Giữ `List<T>` | Tránh hạn chế generic array creation và cast. |

Điều quan trọng là **đừng ép generic API phải trả mảng nếu consumer có thể dùng List**. Mảng phù hợp khi thư viện yêu cầu nó, khi cần component type runtime hoặc các thao tác đặc thù mảng. Nếu chỉ cần một tập hợp có kích thước thay đổi, `List<T>` thường diễn đạt nghiệp vụ rõ hơn.

## 14. Bài tập và đáp án

### Bài 1. Viết một helper cấp phát mảng String mà không dùng cast.

**Đáp án:**

```java
static <T> T[] make(int size, java.util.function.IntFunction<T[]> factory) {
    return factory.apply(size);
}

// Gọi bên trong main/method:
String[] names = make(4, String[]::new);
```

Cần bảo đảm caller đưa factory phù hợp. Phiên bản có kiểm tra đầu vào và độ dài được trình bày ở phần 3.

### Bài 2. Đâu là khác biệt giữa `String[]::new` và `String.class`?

**Đáp án:** `String[]::new` là một hàm có thể nhận kích thước và tạo String[]; `String.class` là class token mô tả kiểu phần tử String, cần truyền vào API như `Array.newInstance` để tạo mảng.

### Bài 3. Vì sao `new T[5]` không hợp lệ?

**Đáp án:** Type variable T không tự cung cấp runtime component type cụ thể cho mảng mới; Java từ chối generic array creation. Dùng factory hoặc `Class<T>` do caller cung cấp.

### Bài 4. Cho `List<Integer>`, có thể tạo `Number[]` không?

**Đáp án:** Có. Caller có thể viết `Number[] result = integers.toArray(Number[]::new)` hoặc dùng helper nhận `Collection<? extends Number>` và factory Number[]. Phần tử Integer gán được vào mảng Number[].

### Bài 5. `Collection.toArray(IntFunction)` có luôn gọi factory bằng `collection.size()` không?

**Đáp án:** Không. Default implementation sử dụng `generator.apply(0)` rồi xử lý mảng theo `toArray(T[])`. Cần tuân theo hợp đồng của API gọi factory; không mặc định tham số bằng size.

### Bài 6. Tại sao `(T[]) new Object[5]` không an toàn?

**Đáp án:** Đối tượng mảng thực vẫn là Object[]. Khi caller kỳ vọng mảng có component type như String[], runtime có thể ném ClassCastException. Cast không đổi loại mảng.

### Bài 7. `List<String>.class` có thể được truyền vào `Array.newInstance` không?

**Đáp án:** Không vì `List<String>.class` không phải class literal hợp lệ. `List.class` chỉ đại diện kiểu runtime List sau erasure, không có kiểm tra sâu đối số String.

### Bài 8. Một helper từ chối `int.class` khi nhận `Class<T>` có mâu thuẫn Java reflection hỗ trợ int[] không?

**Đáp án:** Không. Reflection hỗ trợ tạo primitive array khi gọi trực tiếp với `int.class`. Helper trả `T[]` ở ví dụ chủ động giới hạn vào reference component types để tránh hiểu nhầm với primitive arrays.

### Bài 9. Factory trả mảng String[4] khi helper yêu cầu độ dài 2. Đây là lỗi Java generics hay lỗi hợp đồng?

**Đáp án:** Không nhất thiết là lỗi kiểu; cả hai vẫn là String[]. Nhưng nếu helper cam kết mảng có đúng độ dài n, cần kiểm tra và báo lỗi hợp đồng, như `allocateWithFactory`.

### Bài 10. Nếu một List chứa phần tử sai kiểu do raw operation, việc chuyển nó bằng `toArray(String[]::new)` có tự sửa dữ liệu không?

**Đáp án:** Không. Khi chuyển dữ liệu sang mảng String, runtime có thể phát hiện phần tử không tương thích và ném ArrayStoreException. Cần sửa nguồn heap pollution hoặc xác thực/chuyển đổi phần tử theo quy tắc nghiệp vụ.

## 15. Tổng kết

- Không tạo được `new T[n]` vì generic type variable không tự cung cấp component type runtime cho mảng.
- `IntFunction<T[]>` giúp caller cung cấp factory như `String[]::new`, tránh unchecked cast trong helper.
- `Class<T>` kết hợp `Array.newInstance` dùng được khi caller có token của kiểu phần tử; hãy cô lập cast và xử lý primitive token theo hợp đồng API.
- `Collection.toArray(String[]::new)` thường là lựa chọn gọn nhất để chuyển collection thành mảng. Chú ý generator có thể nhận `0` theo default implementation, không nhất thiết nhận `size()`.
- Runtime array type được giữ thật: String[] khác Object[], và JVM thực thi array store check.
- Class token/factory cho loại container `List` không reify đối số `String` nằm sâu trong `List<String>`.
- Khi không thật sự cần mảng, `List<T>` thường giúp API đơn giản và tránh các hạn chế generic array creation.

**Quy tắc thực hành:** Hãy đưa việc tạo mảng về nơi có thông tin kiểu cụ thể (array factory hoặc class token), để mảng được tạo **đúng runtime component type** thay vì phụ thuộc vào cast không kiểm tra được.
