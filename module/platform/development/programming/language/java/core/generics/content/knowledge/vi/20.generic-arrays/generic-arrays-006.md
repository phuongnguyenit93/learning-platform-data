# Dùng `Collection<T>` thay cho mảng khi phù hợp trong Java Generics

## 1. Vì sao cần lựa chọn giữa Collection và mảng?

Khi học Java Generics, một tình huống hay gặp là muốn lưu nhiều phần tử cùng một kiểu `T`:

```java
class Group<T> {
    // Không hợp lệ:
    // private T[] items = new T[10];
}
```

Hoặc muốn lưu nhiều danh sách chuỗi:

```java
// Không hợp lệ:
java.util.List<String>[] groups = new java.util.List<String>[3];
```

Hai biểu thức `new T[10]` và `new List<String>[3]` đều gặp giới hạn của **generic array creation**. Type variable `T` và kiểu tham số hóa `List<String>` không phải các component type *reifiable* thích hợp để trực tiếp tạo mảng.

Nếu bài toán chỉ cần một tập phần tử, ta thường có thể thay bằng:

```java
class Group<T> {
    private final java.util.Collection<T> items =
            new java.util.ArrayList<>();
}
```

Và thay “mảng các danh sách chuỗi” bằng:

```java
java.util.List<java.util.List<String>> groups =
        new java.util.ArrayList<>();
```

Cả hai ví dụ mới đều hợp lệ. Compiler giữ được các ràng buộc generic ở mã nguồn mà không cần tạo mảng có component type không reifiable.

**Nguyên tắc của bài:** Chọn abstraction thể hiện thao tác cần thiết trước. Nếu chỉ cần thêm, duyệt, đếm hoặc kiểm tra thành viên, `Collection<T>` có thể đủ. Nếu cần thứ tự và truy cập chỉ số, dùng `List<T>`; nếu cần tính duy nhất, `Set<T>`; nếu cần hàng đợi, `Queue<T>`; và nếu thực sự cần ngữ nghĩa mảng/runtime component class hoặc API bắt buộc nhận array, tiếp tục dùng mảng với cách tạo phù hợp.

`Collection<T>` không phải một “mẹo” để làm Generics trở thành reified. Nó là một cách thiết kế dữ liệu thường **phù hợp hơn với hệ thống kiểu generic của Java** và loại bỏ nhu cầu tạo những mảng không thể được JVM kiểm tra đầy đủ.

## 2. Khác biệt cần giữ khi thay array bằng collection

Mảng `String[]` giữ component type `String` tại runtime; nó cho phép alias kiểu `Object[]` nhưng JVM kiểm tra mỗi phép ghi để từ chối `Integer` bằng `ArrayStoreException`. `Collection<String>` dùng **generic compile-time checks**; runtime `ArrayList<String>` và `ArrayList<Integer>` dùng cùng một `ArrayList` class do erasure. Raw alias vẫn có thể phá hợp đồng.

| Quyết định | Array | Collection generic |
| --- | --- | --- |
| Truy cập phần tử | Theo index, có `length` | Duyệt/iterator/`size()`; chỉ `List` mới có `get(index)` |
| Kích thước | Cố định sau tạo | Tùy implementation, có thể hỗ trợ thêm/xóa |
| Kiểu phần tử | Runtime component class và store check | Compiler theo dõi type argument ở API typed |
| Thứ tự | Theo index | `Collection` không hứa thứ tự; `List` thì có |
| Primitive | `int[]` trực tiếp | `Collection<Integer>` có boxing |
| Khởi tạo generic | Không được `new T[n]` | Được `new ArrayList<T>()` |

Đổi sang Collection phù hợp khi thao tác nghiệp vụ cần **tập phần tử generic** chứ không đòi runtime array class. Điều đó không khiến generics reified hay collection tự mutable; phải tiếp tục chọn đúng implementation, ownership và null policy.

## 3. Chọn đúng interface: `Collection` không đồng nghĩa `List`

`java.util.Collection<E>` là interface cơ sở cho nhiều loại tập hợp. Những thao tác thường gặp gồm:

- `add`, `remove`, `contains`, `size`, `isEmpty`;
- duyệt bằng enhanced `for`;
- iterator, `stream`, `toArray`;
- thao tác trên tập hợp như `addAll`, `removeAll`, `retainAll`.

Nhưng `Collection` **không có `get(int)`**, không hứa duy trì thứ tự phần tử cho mọi implementation và không bảo đảm mọi collection đều hỗ trợ `add` hoặc `remove`.

Các interface chuyên biệt:

| Nhu cầu thật | Kiểu nên cân nhắc | Điểm quan trọng |
|---|---|---|
| Một tập phần tử để duyệt hoặc đếm | `Collection<T>` | Không cần index/order ở API |
| Thứ tự, truy cập vị trí, có thể trùng phần tử | `List<T>` | Có `get(int)` và thứ tự phần tử |
| Không muốn phần tử trùng theo tiêu chí equality | `Set<T>` | Không có index; thứ tự tùy implementation |
| Thêm và lấy phần tử theo chính sách hàng đợi | `Queue<T>`/`Deque<T>` | Hợp đồng thao tác đầu/cuối phù hợp |
| Ánh xạ từ key tới value | `Map<K,V>` | `Map` **không extends** `Collection` |
| Mảng component type thật sự ở runtime | `T[]` trong ngữ cảnh tạo an toàn | Dùng khi cần hợp đồng array |

Với `Collection<T>`, API nhận được nhiều loại triển khai. Đó là ưu điểm khi thuật toán chỉ cần năng lực tối thiểu. Nếu thuật toán cần gọi `get(i)`, đừng ép `Collection` xuống `List` vô căn cứ; hãy yêu cầu `List<T>` ngay trong chữ ký.

## 4. Ví dụ chạy được: viết generic container bằng Collection

Tạo tệp **`GenericCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;

public class GenericCollectionDemo {

    static final class Bag<T> {
        private final Collection<T> elements = new ArrayList<>();

        void add(T value) {
            elements.add(value);
        }

        int size() {
            return elements.size();
        }

        Collection<T> snapshot() {
            return new ArrayList<>(elements);
        }
    }

    public static void main(String[] args) {
        Bag<String> names = new Bag<>();
        names.add("Lan");
        names.add("Mai");

        System.out.println(names.size());

        for (String name : names.snapshot()) {
            System.out.println(name);
        }

        Bag<Integer> points = new Bag<>();
        points.add(8);
        points.add(9);

        System.out.println(points.size());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac GenericCollectionDemo.java
java GenericCollectionDemo
```

Stdout:

```text
2
Lan
Mai
2
```

Điểm cần phân tích:

1. `Bag<T>` không thể trực tiếp cấp phát `new T[n]`, nhưng có thể khai báo trường `Collection<T>` và gán một `ArrayList<T>`.
2. Khi dùng `Bag<String>`, compiler yêu cầu `add` nhận `String`; dùng `Bag<Integer>` thì yêu cầu `Integer`.
3. `snapshot()` tạo một **collection mới** để caller không nắm trực tiếp collection nội bộ; ví dụ không tuyên bố rằng các object phần tử được sao chép sâu.
4. Vòng `for-each` làm việc trên `Collection<T>` vì collection hỗ trợ `Iterable<T>`.
5. `ArrayList` duy trì thứ tự chèn, nên stdout của ví dụ là xác định. Nếu implementation đổi thành `HashSet`, không nên mặc định thứ tự in giống vậy.

Ví dụ dùng `Collection` để lưu trữ thay cho một generic array mà không cần cast unchecked.

### Vì sao không viết `Collection<T> elements = new Collection<>();`?

`Collection` là **interface**, không thể khởi tạo trực tiếp. Ta chọn một concrete implementation:

```java
Collection<T> elements = new ArrayList<>();
```

Hoặc nếu cần tập duy nhất:

```java
Collection<T> elements = new java.util.HashSet<>();
```

Nếu thứ tự là điều quan trọng, dùng `ArrayList` hoặc một implementation có thứ tự phù hợp; nếu chỉ cần tính duy nhất, cân nhắc `Set`.

## 5. Bài toán quan trọng: thay `List<String>[]` bằng `List<List<String>>`

Giả sử cần một số nhóm, mỗi nhóm có nhiều tên. Cách trực tiếp tạo mảng không hợp lệ:

```java
// Cố ý không biên dịch:
List<String>[] groups = new List<String>[3];
```

Hãy mô hình hóa là một danh sách chứa những danh sách chuỗi:

```java
List<List<String>> groups = new ArrayList<>();
```

Đó là **List của List**, trong đó cả hai cấp generic đều được compiler kiểm tra ở code bình thường.

Tệp **`NestedListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class NestedListDemo {
    public static void main(String[] args) {
        List<List<String>> groups = new ArrayList<>();

        groups.add(new ArrayList<>(List.of("An", "Binh")));
        groups.add(new ArrayList<>(List.of("Chi")));

        groups.get(1).add("Dung");

        System.out.println(groups.size());
        System.out.println(groups.get(0).get(1));

        for (List<String> group : groups) {
            System.out.println(String.join(", ", group));
        }
    }
}
```

Chạy:

```bash
javac NestedListDemo.java
java NestedListDemo
```

Stdout:

```text
2
Binh
An, Binh
Chi, Dung
```

Lý do đây thường là thiết kế tốt:

- Không cần `new List<String>[n]`.
- Outer list duy trì thứ tự nhóm và có `get(index)`.
- Inner list có kiểu `List<String>`; compiler ngăn chèn `Integer` vào một nhóm trong code typed thông thường.
- Thêm/bỏ nhóm không bị giới hạn bởi số slot mảng đã tạo.
- Có thể thay outer `ArrayList` bằng implementation `List` khác mà không đổi phần lớn code client.

**Lưu ý:** Dùng `Collection<Collection<String>>` sẽ quá tổng quát nếu yêu cầu là truy cập nhóm và học viên theo index. Chọn `List<List<String>>` khi cần truy cập hai cấp bằng vị trí.

## 6. `Collection<T>` là lựa chọn cho API chỉ cần duyệt

Đừng vô tình tạo một yêu cầu “array” nếu hàm chỉ cần duyệt các phần tử.

Thay:

```java
// Khai báo hợp lệ, nhưng gắn API với array.
static int countNames(String[] names) {
    return names.length;
}
```

Có thể dùng:

```java
static int countNames(Collection<String> names) {
    return names.size();
}
```

Trong trường hợp muốn nhận cả các subtype, wildcard có thể có ích. Ví dụ:

```java
static void printAll(Collection<?> values) {
    for (Object value : values) {
        System.out.println(value);
    }
}
```

Đây là các **đoạn method độc lập để so sánh**, cần đặt trong class thích hợp và import `java.util.Collection`.

Một method nhận `Collection<?>` diễn đạt “tôi chỉ đọc các phần tử với kiểu chưa biết”. Nếu cần xử lý mỗi phần tử theo một kiểu cụ thể, giữ tham số hóa như `Collection<String>` hoặc dùng bound/callback thích hợp.

Tuy nhiên, **không dùng `Collection<T>` chỉ vì mọi thứ đều là collection**. Nếu code cần sắp xếp dựa trên index hoặc truy cập phần tử thứ 10 thường xuyên, `List<T>` là hợp đồng đúng hơn.

## 7. Một utility generic không cần `T[]`

Tạo tệp **`CollectionUtilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CollectionUtilityDemo {

    static <T> List<T> copyOf(Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    static <T> void addAll(
            Collection<? super T> target,
            Collection<? extends T> source) {
        for (T value : source) {
            target.add(value);
        }
    }

    public static void main(String[] args) {
        List<String> words = copyOf(List.of("red", "blue"));
        List<Object> output = new ArrayList<>();

        addAll(output, words);
        addAll(output, List.of(10, 20));

        System.out.println(words);
        System.out.println(output);
    }
}
```

Lệnh:

```bash
javac CollectionUtilityDemo.java
java CollectionUtilityDemo
```

Stdout:

```text
[red, blue]
[red, blue, 10, 20]
```

Ví dụ minh họa quy tắc **PECS** (*Producer Extends, Consumer Super*):

- `Collection<? extends T> source`: phần tử đọc từ nguồn có thể dùng như `T`.
- `Collection<? super T> target`: đích có thể nhận các phần tử kiểu `T`.
- `copyOf` trả một `List<T>` mới, không cần `T[]` ở bất kỳ nơi nào.

Khi gọi `addAll(output, words)`, tham số đích `Collection<Object>` có thể nhận `String`; các generic constraints giúp compiler xác minh quan hệ hợp lệ. Việc method nhận một `Collection` giúp callers dùng nhiều kiểu container mà không phải chuyển tạm sang mảng.

### Vì sao không dùng `Collection<T>` cho cả source lẫn target?

Khai báo:

```java
static <T> void addAll(Collection<T> target, Collection<T> source)
```

không nhận được mọi cặp phù hợp mà `<? super T>` và `<? extends T>` cho phép. Chẳng hạn `Collection<Object>` là đích hợp lý của `Collection<String>`, nhưng hai container không có **cùng** type argument `T`.

Bounded wildcards giúp giữ an toàn và giảm yêu cầu ép kiểu. Tuy nhiên không cần áp dụng PECS một cách máy móc: nếu một tham số vừa đọc vừa ghi một `T` chính xác, `Collection<T>` có thể thích hợp hơn.

## 8. Nếu muốn phần tử duy nhất, dùng `Set<T>`

Một mảng có thể chứa bản sao trùng nhau; một `List` cũng vậy. Nếu nghiệp vụ muốn các phần tử duy nhất theo `equals`/`hashCode`, chọn `Set<T>`.

Ví dụ **`SetInsteadOfArrayDemo.java`**:

```java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

public class SetInsteadOfArrayDemo {
    static <T> int uniqueCount(Collection<? extends T> source) {
        Set<T> unique = new LinkedHashSet<>(source);
        return unique.size();
    }

    public static void main(String[] args) {
        System.out.println(uniqueCount(
                java.util.List.of("A", "B", "A")));
        System.out.println(uniqueCount(
                java.util.List.of(2, 2, 3, 4)));
    }
}
```

Biên dịch/chạy:

```bash
javac SetInsteadOfArrayDemo.java
java SetInsteadOfArrayDemo
```

Stdout:

```text
2
3
```

`LinkedHashSet` được dùng để hỗ trợ thứ tự lặp dựa trên thứ tự chèn khi cần, nhưng chương trình chỉ in kích thước. Còn `HashSet` không cung cấp hợp đồng thứ tự lặp tương ứng.

Nếu API phải truy cập phần tử theo vị trí, `Set` không thay thế được `List`. Chọn abstraction từ đặc tính dữ liệu thật.

## 9. Khi nào `Collection<T>` không đủ?

Đây là giới hạn quan trọng của lời khuyên “dùng Collection thay array”.

### 9.1. Cần truy cập index

```java
List<String> names = new ArrayList<>();
names.add("An");
String first = names.get(0);
```

`List` có `get(int)`, còn `Collection` không có. Đừng biến `Collection<String>` thành `List<String>` bằng cast nếu nguồn có thể là `HashSet`.

### 9.2. Cần kích thước cố định và vị trí trống

Một array `String[3]` lập tức có **ba slot**, tất cả mang giá trị mặc định `null`. `new ArrayList<String>(3)` chỉ đặt **dung lượng ban đầu** (*capacity*), không tạo ba phần tử.

```java
List<String> slots = new ArrayList<>(3);
System.out.println(slots.size()); // 0
```

Nếu muốn có ba vị trí thực sự:

```java
List<String> slots = new ArrayList<>(
        java.util.Arrays.asList(null, null, null));
System.out.println(slots.size()); // 3
```

Đây là các đoạn minh họa; đặt trong phương thức thích hợp. Một list có kích thước 3 không tự trở thành cấu trúc cố định trừ khi API chủ động giới hạn thay đổi.

Nếu cần container có số slot cố định hoặc bố cục dữ liệu sát phần cứng, array vẫn có thể phù hợp.

### 9.3. Cần primitive arrays

`int[]`, `double[]` lưu trực tiếp các giá trị primitive. `Collection<Integer>` và `Collection<Double>` dùng wrapper objects theo hệ thống kiểu của Java Generics và có autoboxing/unboxing ở các điểm thích hợp.

Với khối lượng tính toán số lớn, primitive arrays có thể giảm chi phí đối tượng và bộ nhớ; tuy nhiên hiệu năng thực tế cần đo bằng benchmark thay vì suy luận tuyệt đối từ cú pháp.

### 9.4. Cần API Java/Java native yêu cầu array

Một số API nhận hoặc trả `String[]`, `byte[]`, `char[]`, `int[]` vì contract được thiết kế theo mảng. Khi đó phải cung cấp array đúng kiểu, thay vì cố thay đổi chữ ký do bên thứ ba quy định.

### 9.5. Cần runtime component type

Nếu chương trình thực sự phải biết component class lúc chạy, mảng mang thông tin hữu ích qua `array.getClass().getComponentType()`. Một generic `Collection<T>` không tự mang `T` theo cùng cơ chế.

**Kết luận:** Dùng `Collection<T>` để tránh array không reifiable khi bài toán cho phép, **không phải loại bỏ toàn bộ array** khỏi Java.

## 10. Phân biệt kích thước `ArrayList` với độ dài mảng

Một lỗi rất phổ biến khi thay array bằng collection:

```java
int[] array = new int[5];          // array.length == 5.
ArrayList<Integer> list = new ArrayList<>(5);
                                   // list.size() == 0.
```

Ở `ArrayList<>(5)`, số `5` là initial capacity cho implementation, không có nghĩa đã tạo năm phần tử. Do đó:

```java
// Cố ý gây lỗi runtime nếu list còn rỗng:
list.set(0, 10);
```

sẽ không hợp lệ theo giới hạn chỉ số của danh sách và có thể ném `IndexOutOfBoundsException`.

Nếu muốn có các slot với giá trị mặc định:

```java
List<Integer> list = new ArrayList<>(
        java.util.Collections.nCopies(5, 0));
```

Sau đó có thể `set` trong vùng chỉ số hợp lệ. `Collections.nCopies` tạo một List có số phần tử được chỉ định; constructor `ArrayList` sao chép chúng sang danh sách có thể sửa.

Khác với mảng primitive `new int[5]`, `List<Integer>` không có default zero tự động nếu chỉ gọi constructor đặt capacity.

## 11. Tệp chạy được: đối chiếu `length`, `size()` và `get()`

Tạo **`ArrayVsListSizeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ArrayVsListSizeDemo {
    public static void main(String[] args) {
        int[] array = new int[3];
        ArrayList<Integer> empty = new ArrayList<>(3);

        System.out.println(array.length);
        System.out.println(empty.size());

        List<Integer> filled =
                new ArrayList<>(Collections.nCopies(3, 0));

        filled.set(1, 7);
        array[1] = 7;

        System.out.println(filled);
        System.out.println(array[1]);
    }
}
```

Biên dịch và chạy:

```bash
javac ArrayVsListSizeDemo.java
java ArrayVsListSizeDemo
```

Stdout:

```text
3
0
[0, 7, 0]
7
```

Câu hỏi tự kiểm tra: Vì sao `new ArrayList<>(3)` không tạo sẵn ba phần tử? Vì constructor này chỉ cung cấp **initial capacity**; số phần tử thực là một khái niệm riêng, trả về bởi `size()`.

## 12. Bảo toàn hợp đồng khi expose collection từ class

Một field kiểu `Collection<T>` hoặc `List<T>` có thể chứa collection mutable. Nếu getter trả thẳng collection nội bộ, caller có thể thêm/xóa phần tử và phá invariant nghiệp vụ.

Có một số lựa chọn:

- **Trả bản sao mutable** như `new ArrayList<>(elements)`: caller sửa bản sao không làm thay đổi tập hợp nội bộ; phần tử vẫn là cùng object reference nếu chúng mutable.
- **Trả snapshot unmodifiable** như `List.copyOf(elements)` khi chấp nhận điều kiện `null` và thứ tự phù hợp.
- **Trả unmodifiable view** như `Collections.unmodifiableList(list)`: ngăn sửa qua view, nhưng có thể phản ánh các thay đổi từ tham chiếu khác tới backing list.
- **Trả interface đọc-only về mặt ý định** như `Collection<T>` không đủ để bảo đảm immutable, vì `Collection` có các phương thức thay đổi và implementation có thể hỗ trợ chúng.

Dùng abstraction tốt và bảo vệ ownership là **hai quyết định khác nhau**. Chỉ đổi `T[]` thành `Collection<T>` không tự động che được trạng thái nội bộ.

## 13. Ví dụ chạy được: snapshot có thể đọc nhưng không sửa

Tệp **`SnapshotCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class SnapshotCollectionDemo {
    static class Registry<T> {
        private final List<T> items = new ArrayList<>();

        void register(T value) {
            items.add(value);
        }

        Collection<T> snapshot() {
            return List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        Registry<String> registry = new Registry<>();
        registry.register("A");

        Collection<String> oldSnapshot = registry.snapshot();
        registry.register("B");

        System.out.println(oldSnapshot);
        System.out.println(registry.snapshot());

        try {
            oldSnapshot.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("UnsupportedOperationException");
        }
    }
}
```

Chạy:

```bash
javac SnapshotCollectionDemo.java
java SnapshotCollectionDemo
```

Stdout:

```text
[A]
[A, B]
UnsupportedOperationException
```

`List.copyOf` là **shallow snapshot** và từ chối `null`. Mỗi lần gọi `snapshot()` ở ví dụ lấy trạng thái collection mới; snapshot cũ không tự cập nhật khi `registry` nhận thêm phần tử.

Với phần tử mutable, object bên trong vẫn có thể thay đổi trạng thái thông qua những tham chiếu bên ngoài. Nếu muốn bất biến sâu, phải tự thiết kế cơ chế copy/immutable element tương ứng.

## 14. Chuyển từ `Collection<T>` sang `T[]` khi thực sự cần

Trong nhiều trường hợp, cách tốt nhất là **lưu trữ bằng collection**, chỉ tạo mảng ở ranh giới API yêu cầu mảng.

Ví dụ `Collection.toArray(IntFunction<T[]>)` cho phép caller cung cấp array constructor reference có runtime component type cụ thể.

Tạo tệp **`CollectionToArrayDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;

public class CollectionToArrayDemo {

    static <T> T[] asArray(
            Collection<? extends T> input,
            java.util.function.IntFunction<T[]> factory) {
        return input.toArray(factory.apply(0));
    }

    public static void main(String[] args) {
        Collection<String> words =
                new ArrayList<>(List.of("A", "B"));

        String[] direct = words.toArray(String[]::new);
        String[] fromHelper = asArray(words, String[]::new);

        System.out.println(Arrays.toString(direct));
        System.out.println(Arrays.toString(fromHelper));
        System.out.println(direct.getClass()
                .getComponentType().getName());
    }
}
```

Biên dịch và chạy với Java 17+:

```bash
javac CollectionToArrayDemo.java
java CollectionToArrayDemo
```

Stdout:

```text
[A, B]
[A, B]
java.lang.String
```

**Phân tích hai cách chuyển:**

- `words.toArray(String[]::new)` gọi overload `Collection.toArray(IntFunction<T[]>)`, có từ Java 11. Constructor reference chỉ ra mảng `String[]` có component class runtime là `String`.
- `asArray` truyền một array được tạo bởi factory vào overload `toArray(T[])`. Mảng được tạo dài 0; contract của `toArray` cho phép cấp phát mảng mới khi kích thước chưa đủ. Khi trả về, kết quả vẫn là `String[]` đúng component type.
- Không cần tạo `new T[n]` bên trong generic helper.

Đoạn helper dùng `factory.apply(0)` như kỹ thuật minh họa tương thích với overload `toArray(T[])`. Trong code chỉ nhằm chuyển collection sang mảng với JDK 17+, cách trực tiếp `input.toArray(factory)` thường gọn hơn.

**Không suy ra** rằng có thể tạo `List<String>[]` bằng `List<String>[]::new`: component type của một array constructor reference vẫn phải đáp ứng quy tắc array creation. Type witness/factory không làm một parameterized type non-reifiable trở thành reifiable.

## 15. Chuyển từ mảng sang collection

Ngược lại, khi nhận một mảng có kiểu phần tử cụ thể, có thể tạo collection từ mảng.

Một số cách quen thuộc:

```java
String[] source = {"A", "B"};

List<String> backedView = java.util.Arrays.asList(source);

List<String> independent =
        new java.util.ArrayList<>(java.util.Arrays.asList(source));

List<String> unmodifiable =
        List.copyOf(java.util.Arrays.asList(source));
```

Đây là đoạn minh họa cần đặt trong phương thức có import `java.util.List`.

Những cách này **không đồng nghĩa**:

- `Arrays.asList(source)` cho **list kích thước cố định, backed by array**: gọi `set` trên list có thể ảnh hưởng mảng, và thay phần tử mảng có thể phản ánh vào list. Không thể thêm hoặc xóa qua list này.
- `new ArrayList<>(...)` tạo một list có thể thay đổi kích thước, có các phần tử tham chiếu được sao chép từ dữ liệu đầu vào.
- `List.copyOf(...)` tạo list không thể sửa qua API chuẩn và không cho phần tử `null`; đây là snapshot ở mức cấu trúc.

Ngoài ra, với **primitive arrays** phải cẩn thận:

```java
int[] values = {1, 2, 3};
List<int[]> oneElement = java.util.Arrays.asList(values);
```

`Arrays.asList(int[])` xem toàn bộ `int[]` là **một phần tử tham chiếu**, không biến primitive `int` thành ba `Integer`.

Khi cần `List<Integer>`, có thể dùng `Arrays.stream(values).boxed().toList()` trên Java 17; kết quả của `Stream.toList()` là unmodifiable. Nếu cần mutable list, thu thập sang `ArrayList` bằng collector hoặc tạo bản sao sau đó.

## 16. Bài thực hành: chuyển mảng và danh sách đúng ngữ nghĩa

Tệp **`ArraysAsListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ArraysAsListDemo {
    public static void main(String[] args) {
        String[] source = {"A", "B"};

        List<String> backed = Arrays.asList(source);
        List<String> copied = new ArrayList<>(backed);

        source[0] = "X";

        System.out.println(backed);
        System.out.println(copied);

        backed.set(1, "Y");
        System.out.println(Arrays.toString(source));

        copied.add("C");
        System.out.println(copied);
    }
}
```

Chạy:

```bash
javac ArraysAsListDemo.java
java ArraysAsListDemo
```

Stdout:

```text
[X, B]
[A, B]
[X, Y]
[A, B, C]
```

Sau `source[0] = "X"`, `backed` đổi theo vì là view backed by array, còn `copied` không đổi cấu trúc. `backed.set(1, "Y")` cập nhật chính phần tử của mảng. `copied.add("C")` thêm được phần tử do `ArrayList` là resizable.

Ví dụ giúp thấy “thay array bằng collection” cần xét **ownership**, **khả năng thay đổi số lượng**, và **liên kết dữ liệu gốc** chứ không chỉ xét cú pháp generic.

## 17. Khi cần đầu vào read-only, dùng wildcard và hợp đồng rõ

Một generic API chỉ cần đọc các đối tượng kiểu `Number` có thể khai báo:

```java
static double total(java.util.Collection<? extends Number> numbers) {
    double sum = 0;
    for (Number value : numbers) {
        sum += value.doubleValue();
    }
    return sum;
}
```

Hàm này nhận `Collection<Integer>`, `Collection<Double>` hoặc những collection có phần tử subtype của `Number`, mà không cần chuyển sang `Number[]`.

Đây là **đoạn method minh họa**, đặt trong class nếu biên dịch. Với tham số `? extends Number`, không được tùy tiện thêm `Number` vào collection vì kiểu phần tử cụ thể có thể là `Integer`, `Double`, v.v.

Tương tự, nếu cần ghi `Integer` vào một đích chấp nhận kiểu cha:

```java
static void addScores(
        java.util.Collection<? super Integer> target) {
    target.add(10);
    target.add(20);
}
```

`Collection<? super Integer>` có thể nhận `Collection<Integer>`, `Collection<Number>` hoặc `Collection<Object>` theo quy tắc generic compatibility.

Một ưu điểm lớn của collection + wildcard là diễn đạt năng lực **đọc từ producer** hoặc **ghi vào consumer** mà không tạo array alias covariant dễ bị lạm dụng.

## 18. `Object[]` là storage nội bộ, không phải mảng `T[]` công khai

```java
Object[] data = new Object[]{"A", "B"};
// String[] bad = (String[]) data; // ClassCastException tại runtime.
```

Cho dù hai phần tử hiện tại đều là `String`, mảng thực vẫn có component class `Object`; cast cả mảng **không** tạo `String[]`. Có thể giữ `private Object[]` làm backing storage của cấu trúc `Store<T>` khi mọi đường ghi được kiểm soát theo `T`, chỉ cast từng phần tử ở nơi có invariant rõ, và không lộ mảng ra ngoài. Nếu không cần low-level storage, `ArrayList<T>` thường đơn giản hơn.

Bài chuyên sâu về `Object[]` trình bày cách khoanh vùng `@SuppressWarnings("unchecked")`, kiểm tra `size` và những đường raw/reflection/alias phá invariant. Với API cần array thật, yêu cầu `T[]` factory hoặc class token, không trả `Object[]` dưới danh nghĩa `T[]`.

## 19. Collection có thể thay varargs generic khi chỉ cần duyệt dữ liệu

Varargs `List<T>... values` được truyền dưới dạng array, với element type generic thường non-reifiable; các phương thức thiếu cẩn trọng có nguy cơ heap pollution. Nếu yêu cầu chỉ là **duyệt nhiều danh sách chuỗi**, thay bằng:

```java
static void showGroups(Collection<? extends List<String>> groups) {
    for (List<String> group : groups) {
        System.out.println(group.size());
    }
}
```

Lời gọi `showGroups(List.of(List.of("A"), List.of("B","C")))` có kiểu an toàn, không buộc caller tạo array of `List<String>`. Nếu API cố ý dùng varargs, cần kiểm chứng body và chỉ sử dụng `@SafeVarargs` khi được ngôn ngữ cho phép và nội dung thực sự an toàn. Trọng tâm ở đây là **lựa chọn abstraction đầu vào**, không phải toàn bộ quy tắc varargs.

## 20. Collection không làm generic type reified

Một misunderstanding cần tránh là nghĩ `Collection<T>` “giữ” `T` như một thuộc tính runtime của mỗi instance. Thực tế:

```java
java.util.Collection<String> words =
        new java.util.ArrayList<>();

java.util.Collection<Integer> numbers =
        new java.util.ArrayList<>();
```

Hai biến có kiểu tĩnh khác nhau nhưng cả hai runtime objects đều là `ArrayList`. Java Generics vẫn dùng erasure.

Do đó:

```java
words.getClass() == numbers.getClass()
```

sẽ là `true` khi cả hai được tạo như trên.

Dùng `Collection<T>` tăng **an toàn tại compile time** bằng cách cho compiler theo dõi type arguments khi code được kiểm tra bình thường. Nó không ngăn hoàn toàn heap pollution từ raw types, unchecked casts hoặc dữ liệu reflection không an toàn.

Nếu chương trình cần xác minh thực tế rằng collection chứa toàn `String`, phải kiểm tra dữ liệu (ví dụ duyệt `Collection<?>` và dùng `instanceof String`) hoặc tạo bản sao đã xác minh với class token `String.class` theo hợp đồng rõ ràng.

## 21. Khi nhận collection từ một nguồn không tin cậy

Nếu đọc từ một API legacy, reflection hoặc dữ liệu bên ngoài, không thể chỉ cast:

```java
// Cố ý không an toàn:
@SuppressWarnings("unchecked")
Collection<String> names = (Collection<String>) unknown;
```

và kết luận phần tử đã là `String`. Runtime cast chỉ xác minh đối tượng là `Collection` có raw type phù hợp; nó không xác minh `String`.

Một cách rõ ràng hơn là kiểm tra từng phần tử và đưa vào một collection mới.

Tệp **`ValidatedCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class ValidatedCollectionDemo {

    static <T> List<T> verifiedCopy(
            Collection<?> input, Class<T> elementType) {
        List<T> result = new ArrayList<>();

        for (Object element : input) {
            result.add(elementType.cast(element));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> valid = verifiedCopy(
                List.of("A", "B"), String.class);

        System.out.println(valid);

        try {
            verifiedCopy(List.of("A", 10), String.class);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Lệnh:

```bash
javac ValidatedCollectionDemo.java
java ValidatedCollectionDemo
```

Stdout:

```text
[A, B]
ClassCastException
```

`Class<T>.cast` kiểm tra object là instance của class runtime `T`, còn `List.copyOf` tạo snapshot unmodifiable. Trong ví dụ, dữ liệu không chứa `null`; với dữ liệu cho phép `null`, cần quyết định chính sách riêng vì `List.copyOf` không chấp nhận `null`.

Đối với kiểu phần tử lồng nhau như `List<String>`, không có `List<String>.class`. Khi đó phải kiểm tra cấu trúc lồng nhau thực tế hoặc dùng schema/`Type` cho bộ giải mã phù hợp; việc có một `Class<List>` không đủ bảo đảm type arguments.

## 22. `Collection<T>` và tính bất biến: không nên nhầm interface với trạng thái

Cùng có kiểu `Collection<String>`, nhưng các giá trị sau có hành vi sửa đổi khác nhau:

```java
Collection<String> mutable = new ArrayList<>();
Collection<String> immutable = List.of("A");
Collection<String> snapshot = List.copyOf(mutable);
```

Cần import `java.util.Collection`, `java.util.ArrayList`, `java.util.List`.

- `mutable.add("B")` thường hợp lệ vì là `ArrayList`.
- `immutable.add("B")` ném `UnsupportedOperationException`.
- `snapshot.add("B")` cũng ném `UnsupportedOperationException`.

Interface `Collection` **cho phép khai báo các phương thức thay đổi** nhưng một implementation có thể không hỗ trợ một số thao tác tùy chọn. Một API chỉ nhận `Collection<T>` không tự bảo đảm collection có thể sửa.

Nếu một method cần thêm phần tử vào collection nhận được, hợp đồng phải nói rõ yêu cầu mutability, hoặc method tự tạo `new ArrayList<>(input)` trước khi sửa. Nếu method chỉ đọc, nên giữ hành vi không làm thay đổi input.

## 23. So sánh hiệu năng đúng cách

Một số người chọn array vì “array luôn nhanh”, hoặc chọn `ArrayList` vì “Generics luôn tốt hơn”. Cả hai là kết luận quá rộng.

Các cân nhắc thực tế:

- `int[]` lưu primitive liên tiếp theo biểu diễn mảng JVM; `List<Integer>` dùng wrapper objects và có thể xuất hiện chi phí boxing/unboxing.
- `ArrayList<T>` thường lưu các object references trong một mảng nội bộ và hỗ trợ truy cập index hiệu quả. Kích thước logic có thể tăng; đôi khi nó cần cấp phát vùng lưu trữ mới và sao chép tham chiếu.
- `LinkedList<T>` có đặc tính truy cập index và bộ nhớ rất khác với `ArrayList<T>`.
- `HashSet<T>` tối ưu cho yêu cầu membership/uniqueness nhưng không dùng index.
- Array có fixed length; một list có thể tăng/giảm số phần tử tùy implementation.
- Một container có API đơn giản, bảo đảm type safety và dễ bảo trì thường đáng giá hơn chênh lệch vi mô chưa được đo.

Để quyết định ở đường code nhạy hiệu năng, dùng benchmark đáng tin cậy, chẳng hạn JMH, với kích thước dữ liệu và pattern truy cập thực tế. Không dùng một vòng lặp nhỏ thiếu warm-up như bằng chứng tổng quát cho hiệu năng JVM.

## 24. Dấu hiệu nên dùng Collection thay mảng

Có thể ưu tiên generic collection khi:

1. Phần tử có kiểu generic chưa biết tại nơi viết implementation, chẳng hạn `T`.
2. Bài toán không cần runtime array component class.
3. Cần thêm/bớt phần tử theo thời gian.
4. API cần hoạt động với nhiều implementation mà không cần biết container cụ thể.
5. Cần hợp đồng an toàn kiểu cho collection lồng nhau như `List<List<String>>`.
6. Muốn dùng `Iterator`, stream, `contains`, `addAll` và các thao tác chuẩn collections.
7. Có thể tránh được unchecked casts hoặc rủi ro array covariance.
8. Không cần tối ưu primitive array theo khối lượng dữ liệu lớn.

Đồng thời, hãy cân nhắc giữ mảng khi:

- API bên ngoài yêu cầu mảng;
- số slot cố định là một phần quan trọng của mô hình;
- cần lưu primitive trực tiếp;
- code xử lý cần kiểu phần tử runtime xác định;
- đo đạc hiệu năng chứng minh mảng phù hợp hơn và không vi phạm an toàn kiểu.

Các tiêu chí không loại trừ nhau: một module có thể giữ dữ liệu bằng `List<T>` trong nghiệp vụ và chuyển thành `T[]` tại ranh giới tích hợp.

## 25. Những lỗi phổ biến khi đổi generic array thành collection

**Lỗi 1 — “`Collection<T>` có `get(index)` như array.”** Không. Hợp đồng `Collection` không có phương thức truy cập theo index; dùng `List<T>`.

**Lỗi 2 — “`new ArrayList<>(10)` tạo mười slot giống `new T[10]`.”** Không. Đó là initial capacity, `size()` ban đầu là 0.

**Lỗi 3 — “`Collection<T>` giữ `T` tại runtime.”** Không theo nghĩa reification của type argument; JVM vẫn thường thấy class runtime như `ArrayList`.

**Lỗi 4 — “`Collection<T>` luôn mutable.”** Không. `List.of`, `Set.of` hoặc `List.copyOf` có thể cung cấp collection không cho sửa.

**Lỗi 5 — “Chỉ đổi kiểu vế trái thành Collection là có an toàn kiểu.”** Không nếu code còn raw type, unchecked casts hoặc thao tác dữ liệu không kiểm tra. Cần duy trì typed contract xuyên suốt.

**Lỗi 6 — “`ArrayList` giống `HashSet` về thứ tự.”** Không. `ArrayList` giữ thứ tự phần tử; `HashSet` không cam kết iteration order.

**Lỗi 7 — “`Arrays.asList` tạo list hoàn toàn độc lập với array gốc.”** Không. Nó là fixed-size list backed by array.

**Lỗi 8 — “`List.copyOf` luôn là deep copy.”** Không. Nó tạo snapshot ở mức cấu trúc collection và không sao chép sâu các object phần tử mutable.

**Lỗi 9 — “`List<List<String>>` có thể nhận `List<List<Integer>>`.”** Không. Generic invariance ngăn thay đổi type argument không tương thích trong typed code.

**Lỗi 10 — “Thêm `@SuppressWarnings` là đã giải quyết generic array.”** Không. Annotation chỉ tắt một số cảnh báo, không tạo thông tin kiểu runtime còn thiếu.

**Lỗi 11 — “`Collection<? extends T>` thích hợp để thêm mọi `T`.”** Không. Với producer kiểu `? extends T`, compiler không biết subtype cụ thể; không thể ghi tùy ý một `T` khác vào.

**Lỗi 12 — “`Collection<? super T>` bảo đảm đọc ra `T`.”** Không. Kết quả đọc an toàn có thể chỉ được coi là `Object`, vì collection đích có thể là `Collection<Object>`.

**Lỗi 13 — “`List<T>` tốt hơn array trong mọi trường hợp.”** Không. Mảng primitive, fixed slots hoặc một API có contract array là những trường hợp tiếp tục cần mảng.

## 26. Bài tập thực hành có đáp án

### Bài 1: Container generic

Viết `class Bag<T>` dùng `Collection<T>` để lưu phần tử. Có thể tạo `Bag<String>` và `Bag<Integer>` mà không cần `new T[n]` không?

**Đáp án:** Có. Field `Collection<T>` có thể khởi tạo bằng `new ArrayList<>()`; compiler kiểm tra `T` tại các lời gọi. Không cần cấp phát array với component `T`.

### Bài 2: Nhiều danh sách chuỗi

Yêu cầu hai nhóm tên có thể thêm/xóa phần tử, đồng thời truy cập `groups.get(0).get(1)`. Dùng `Collection<Collection<String>>` hay `List<List<String>>`?

**Đáp án:** `List<List<String>>`, vì yêu cầu truy cập theo index ở cả hai cấp.

### Bài 3: Không biết kiểu phần tử

Một hàm chỉ cần in số lượng phần tử của bất kỳ collection nào. Chữ ký nào gọn và đúng?

```java
static int sizeOf(java.util.Collection<?> values) {
    return values.size();
}
```

**Đáp án:** Dạng trên phù hợp vì không cần biết `T`. Không cần raw `Collection`.

### Bài 4: Duy trì tính duy nhất

Cần loại phần tử trùng khi giữ một tập tên. Nên dùng gì?

**Đáp án:** `Set<String>`; nếu cần thứ tự chèn có thể dùng `LinkedHashSet<String>`. Không cần dựng mảng rồi tự quét trùng.

### Bài 5: Initial capacity

`new ArrayList<String>(5).size()` trả bao nhiêu ngay sau khởi tạo?

**Đáp án:** `0`. Capacity không phải số phần tử thực.

### Bài 6: Chuyển collection sang array

Có `Collection<String> words`. Cách tạo `String[]` không cần unchecked cast?

```java
String[] array = words.toArray(String[]::new);
```

**Đáp án:** Hợp lệ với Java 17. Array constructor reference cung cấp runtime component class là `String`.

### Bài 7: Chuyển mảng sang list

`Arrays.asList(source)` có bảo đảm thay `source[0]` không ảnh hưởng list không?

**Đáp án:** Không. List này backed by array và phản ánh thay đổi phần tử.

### Bài 8: Collection đầu vào là dữ liệu không tin cậy

Một object thỏa `instanceof Collection<?>` có đủ bằng chứng là `Collection<String>` không?

**Đáp án:** Không. Kiểm tra runtime này chỉ xác nhận raw container. Cần kiểm tra từng phần tử nếu hợp đồng đòi `String`.

### Bài 9: PECS

Một helper sao chép từ `Collection<String>` vào `Collection<Object>` có thể dùng chữ ký nào?

```java
static <T> void copy(
        java.util.Collection<? extends T> source,
        java.util.Collection<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}
```

**Đáp án:** Đây là một thiết kế hợp lệ. Source là producer; target là consumer. Không cần tạo mảng `T[]` trung gian.

### Bài 10: Không thể bỏ mảng khi nào?

Một API native yêu cầu `byte[]` cho dữ liệu nhị phân. Có nên ép thiết kế sang `Collection<Byte>` chỉ để dùng Generics?

**Đáp án:** Không. `byte[]` là lựa chọn tự nhiên cho contract ấy và tránh boxing thành `Byte`. Chỉ chuyển dạng ở ranh giới cần thiết nếu API khác thực sự yêu cầu.

## 27. Checklist trước khi chọn cấu trúc

Đối với một lớp generic hoặc API mới, trả lời các câu hỏi sau:

- Tôi cần **danh sách có thứ tự**, **tập duy nhất**, **queue**, hay chỉ **tập phần tử để duyệt**?
- Tôi có cần truy cập index thường xuyên không?
- Số phần tử có tăng/giảm không? Có phải giữ số slot cố định không?
- Tôi có thật sự cần một array component type runtime để tích hợp/kiểm tra không?
- Kiểu phần tử là `T` hoặc `List<String>` non-reifiable ở vị trí tạo array không?
- Có thể dùng `List<T>` hay `List<List<String>>` để loại bỏ generic array creation không?
- Cần quyền sửa collection hay snapshot unmodifiable? Có cho phép `null` không?
- Có đang giao collection nội bộ cho caller không?
- Có thể dùng `Collection<? extends T>` hoặc `Collection<? super T>` để tránh copy/cast không?
- Nếu cuối cùng cần `T[]`, caller có thể cung cấp `IntFunction<T[]>` hoặc array constructor reference hợp lệ không?
- Có đường raw/unchecked nào làm heap pollution không?
- Các yêu cầu hiệu năng (primitive, memory, latency) đã được đo chưa?

Checklist giúp chọn cấu trúc theo hợp đồng thay vì theo một mẹo vượt lỗi compiler.

## 28. Tổng kết và tài liệu đối chiếu

**`Collection<T>` là một thay thế phù hợp cho mảng khi dữ liệu cần thao tác như một tập phần tử generic, đặc biệt khi việc tạo `new T[n]` hoặc `new List<String>[n]` không hợp lệ.** Nó cho phép compiler kiểm tra kiểu qua một API tổng quát, giúp xử lý nhiều phần tử mà không yêu cầu JVM tạo array component type không reifiable.

Hãy chọn interface hẹp nhất thể hiện đúng nhu cầu: `Collection<T>` để duyệt/đếm, `List<T>` để giữ thứ tự và truy cập index, `Set<T>` để loại trùng, hoặc `Queue<T>` cho xử lý hàng đợi. `List<List<String>>` thường là lời giải tự nhiên thay cho ý định “một mảng các danh sách chuỗi”.

Tuy nhiên, `Collection<T>` không tự reify `T`, không bảo đảm mutable hay có thứ tự, và không thay thế được mọi công dụng của array. Khi một API thật sự cần mảng, có thể chuyển từ collection bằng `toArray(String[]::new)` hoặc array factory hợp lệ; khi cần primitive storage hay fixed slots, sử dụng array có thể chính xác hơn.

Tài liệu chuẩn:

- [Java Language Specification §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): kiểu nào đủ thông tin tại runtime.
- [Java Language Specification §15.10.1 — Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.1): quy tắc tạo mảng với kiểu phần tử.
- [Java Language Specification §10.5 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5): kiểm tra gán phần tử mảng lúc chạy.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): kiểu generic sau xóa.
- [Java SE 17 `Collection<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): hợp đồng collection, `toArray`, các thao tác tùy chọn.
- [Java SE 17 `List<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): thứ tự, index, unmodifiable factories.
- [Java SE 17 `Arrays.asList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list backed by array.
- [Java SE 17 `ArrayList<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): capacity, size và implementation linh hoạt.