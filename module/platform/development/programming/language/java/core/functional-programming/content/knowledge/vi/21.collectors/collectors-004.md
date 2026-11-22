# Collectors.toCollection() để chọn loại Collection tường minh trong Java

## 1. Vấn đề: gom Stream xong thì nhận loại Collection nào?

Trong Java Stream API, các phép toán như `filter`, `map` và `sorted` mô tả cách xử lý phần tử. Khi cần **thu thập kết quả thành một Collection**, ta dùng một terminal operation như `collect(...)`. Nếu yêu cầu nghiệp vụ đòi hỏi rõ **loại bộ sưu tập đầu ra**, `Collectors.toCollection(...)` là công cụ trực tiếp:

~~~java
ArrayList<String> names = source.stream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Đây là đoạn minh họa, giả định `source` là collection chứa String, với import `java.util.ArrayList` và `java.util.stream.Collectors`.

Với đoạn trên, người viết đang **chọn `ArrayList` cụ thể**, thay vì để một collector chung lựa chọn implementation. Điểm này quan trọng khi caller cần:

- **ArrayList**: danh sách có index, giữ phần tử trùng và thường thuận tiện cho truy cập theo chỉ số.
- **LinkedList**: một danh sách khác, đồng thời triển khai Deque, phù hợp khi thực sự cần hợp đồng và đặc tính của nó.
- **LinkedHashSet**: loại phần tử trùng theo `equals/hashCode` và duyệt theo thứ tự chèn.
- **HashSet**: loại phần tử trùng, không hứa thứ tự duyệt.
- **TreeSet**: loại phần tử được coi là trùng theo comparator hoặc thứ tự tự nhiên và duyệt theo thứ tự sắp xếp.
- **EnumSet**: tập chuyên cho các hằng của cùng một kiểu enum.

**Quy tắc chính:** `Collectors.toCollection(factory)` không biến đổi phần tử bằng phép map, không tự sắp xếp ngoài ngữ nghĩa của Collection được chọn, và không phải một cách viết tương đương tuyệt đối cho `toList()` hoặc `toSet()`. Nó tạo một **Collector** với mục tiêu tích lũy phần tử vào **một Collection do factory cung cấp**.

## 2. Chữ ký và ý nghĩa của Supplier

Chữ ký khái quát:

~~~java
public static <T, C extends Collection<T>>
Collector<T, ?, C> toCollection(Supplier<C> collectionFactory)
~~~

Đây là **chữ ký API rút gọn** để giải thích; không phải một phương thức độc lập để đặt vào file Java. Nó nằm trong `java.util.stream.Collectors`.

Các phần quan trọng:

| Thành phần | Vai trò |
| --- | --- |
| `T` | Kiểu phần tử của Stream nguồn |
| `C extends Collection<T>` | Loại Collection đích, ví dụ `ArrayList<T>`, `TreeSet<T>` |
| `Supplier<C>` | Nhà máy tạo một instance Collection mới khi collector cần |
| `Collector<T, ?, C>` | Bộ gom nhận phần tử T và tạo kết quả cuối kiểu C |
| `collect(...)` | Terminal operation chạy pipeline và tạo kết quả |

**Supplier** có phương thức `C get()` không tham số. Ví dụ:

~~~java
Supplier<ArrayList<String>> factory = ArrayList::new;
ArrayList<String> result = Stream.of("a", "b")
        .collect(Collectors.toCollection(factory));
~~~

Đây là đoạn minh họa cần import `Supplier`, `ArrayList`, `Stream`, `Collectors`. `ArrayList::new` là **constructor reference**: mỗi lần Supplier được gọi, nó tạo một danh sách mới.

Tương đương về cách cung cấp factory:

~~~java
Collectors.toCollection(ArrayList::new)
Collectors.toCollection(() -> new ArrayList<>())
~~~

Đây là hai biểu thức minh họa để so sánh. Constructor reference thường ngắn và dễ đọc; lambda hữu ích khi cần truyền tham số cấu hình, như comparator của TreeSet hoặc capacity ban đầu của ArrayList.

**Một lưu ý quan trọng:** `toCollection` là factory cho một Collector; các Collection trung gian hoặc kết quả được tạo **khi collect thực thi**. Trong chế độ parallel, quá trình thu gom có thể tạo **nhiều collection trung gian**, rồi kết hợp; không được giả định factory được gọi chính xác một lần trong mọi cách chạy.

## 3. Ví dụ Java 17 đầy đủ: ArrayList, LinkedHashSet và TreeSet

Tạo tệp **CollectionChoicesDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class CollectionChoicesDemo {
    public static void main(String[] args) {
        List<String> source = List.of(
                "Lan", "An", "Lan", "Binh", "An");

        ArrayList<String> list = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));

        LinkedHashSet<String> distinctInOrder = source.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));

        TreeSet<String> distinctSorted = source.stream()
                .collect(Collectors.toCollection(TreeSet::new));

        System.out.println("List: " + list);
        System.out.println("Ordered set: " + distinctInOrder);
        System.out.println("Sorted set: " + distinctSorted);

        list.add("Mai");
        System.out.println("Mutable list: " + list);
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 CollectionChoicesDemo.java
java CollectionChoicesDemo
~~~

Stdout:

~~~text
List: [Lan, An, Lan, Binh, An]
Ordered set: [Lan, An, Binh]
Sorted set: [An, Binh, Lan]
Mutable list: [Lan, An, Lan, Binh, An, Mai]
~~~

**Phân tích chi tiết:**

1. `source` là một List có 5 phần tử, trong đó **Lan** và **An** xuất hiện hai lần.
2. `ArrayList::new` tích lũy mọi phần tử theo thứ tự gặp của Stream có thứ tự này. Danh sách giữ cả bản sao: **[Lan, An, Lan, Binh, An]**.
3. `LinkedHashSet::new` loại bản sao nhưng duy trì thứ tự chèn các giá trị đầu tiên: **[Lan, An, Binh]**.
4. `TreeSet::new` dùng thứ tự tự nhiên của String, loại giá trị trùng theo quy tắc so sánh và duyệt theo thứ tự sắp xếp: **[An, Binh, Lan]**.
5. `list.add("Mai")` thành công vì `ArrayList` do factory tạo là **mutable**; kết quả hiển thị phần tử mới.

Đây là ưu điểm rõ nhất của `toCollection`: **loại collection cuối cùng được chỉ định tường minh trong chính đoạn code thu gom**.

## 4. So sánh với Stream.toList(), Collectors.toList(), toSet()

Các API thu thập thường bị nhầm với nhau:

| Cách viết | Kiểu được công bố | Thứ tự, bản sao và khả năng sửa đổi |
| --- | --- | --- |
| `stream.toList()` (Java 16+) | `List<T>` | Giữ encounter order nếu có; danh sách **unmodifiable** |
| `collect(Collectors.toList())` | `List<T>` | Không cam kết implementation cụ thể, tính mutable, serialization hay thread safety |
| `collect(Collectors.toSet())` | `Set<T>` | Không cam kết implementation hoặc thứ tự duyệt; loại phần tử trùng theo hợp đồng Set |
| `collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` | ArrayList cụ thể; giữ trùng/thứ tự; mutable |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | `LinkedHashSet<T>` | LinkedHashSet cụ thể; loại trùng, thứ tự chèn |
| `collect(Collectors.toCollection(TreeSet::new))` | `TreeSet<T>` | TreeSet cụ thể; sắp xếp và quy tắc comparator |
| `collect(Collectors.toUnmodifiableList())` | `List<T>` | Unmodifiable, **không chấp nhận null element** |

**Điểm cần nhớ:** `Collectors.toList()` hiện nay có thể trả một loại List phổ biến ở một implementation, nhưng API **không hứa** đó là ArrayList hay luôn cho phép `add`. Nếu caller bắt buộc có **ArrayList mutable**, hãy chọn `toCollection(ArrayList::new)`. Nếu caller chỉ cần một danh sách không sửa được, `Stream.toList()` có hợp đồng phù hợp và diễn đạt ngắn gọn hơn.

**Không đánh đồng `unmodifiable` với `immutable deep`:** danh sách không cho thêm/bớt phần tử vẫn có thể chứa các object mutable; trạng thái của object bên trong có thể thay đổi. Cũng không suy ra tính thread-safe chỉ vì danh sách không sửa cấu trúc được.

### 4.1. Cách chọn theo hợp đồng

- Cần một `List` đầu ra **không được sửa cấu trúc**: cân nhắc `stream.toList()`.
- Cần **đúng ArrayList** để tương thích API khác hay dùng `add/remove`: `toCollection(ArrayList::new)`.
- Cần loại trùng **và giữ thứ tự gặp đầu tiên**: `LinkedHashSet::new`.
- Cần tập hợp **có sắp xếp**: `TreeSet::new` hoặc factory có comparator.
- Cần một tập chuyên cho enum: factory `EnumSet.noneOf(EnumType.class)`.
- Không có yêu cầu loại collection cụ thể: ưu tiên API ngắn và đúng hợp đồng; không thêm `toCollection` chỉ cho phức tạp.

Chọn loại Collection phải được thúc đẩy bởi **ngữ nghĩa và thao tác sẽ thực hiện tiếp**, không chỉ bởi thói quen dùng ArrayList.

## 5. ArrayList và LinkedList: cùng là List, khác cấu trúc

`ArrayList` sử dụng một mảng có thể thay đổi kích thước; thường phù hợp với truy cập chỉ số và các danh sách thông thường. `LinkedList` là danh sách liên kết đôi và triển khai cả `List` và `Deque`. Không nên khẳng định LinkedList luôn tốt hơn khi thêm/xóa: chi phí tìm vị trí, locality bộ nhớ, cấp phát node và mẫu truy cập đều ảnh hưởng.

Ví dụ:

~~~java
ArrayList<Integer> a = IntStream.rangeClosed(1, 4)
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));

LinkedList<Integer> b = IntStream.rangeClosed(1, 4)
        .boxed()
        .collect(Collectors.toCollection(LinkedList::new));
~~~

Đây là **đoạn minh họa** cần import `ArrayList`, `LinkedList`, `IntStream`, `Collectors`.

Cả hai có nội dung **[1, 2, 3, 4]**, nhưng kết quả cụ thể là ArrayList và LinkedList. `boxed()` chuyển `IntStream` thành `Stream<Integer>`, từ đó dùng được `Collectors.toCollection` theo mẫu ở đây.

**Quan trọng:** `Collectors.toCollection` là collector dành cho **object Stream<T>**. Các primitive stream `IntStream`, `LongStream`, `DoubleStream` không có `collect(Collector<...>)` cùng chữ ký. Nếu cần gom Integer vào ArrayList từ IntStream, hãy `boxed()` trước hoặc dùng cơ chế collect chuyên cho primitive stream phù hợp.

### 5.1. Chọn capacity ban đầu

Khi biết trước hoặc ước lượng số phần tử, có thể tạo factory có capacity:

~~~java
ArrayList<String> result = source.stream()
        .collect(Collectors.toCollection(
                () -> new ArrayList<>(128)));
~~~

Đây là đoạn minh họa, source là collection/stream tương thích String. `new ArrayList<>(128)` tạo **dung lượng ban đầu**, **không** tạo sẵn 128 phần tử. `result.size()` vẫn là số phần tử thực tế được thu thập.

**Không cần tối ưu sớm:** factory được gọi để tạo các container phục vụ quá trình collect; nhất là trong parallel pipeline, nhiều container có thể tồn tại cùng lúc. Việc cấp capacity lớn cho mỗi container đôi khi lãng phí bộ nhớ. Chỉ chọn capacity sau khi hiểu workload và đo hiệu năng.

## 6. LinkedHashSet: loại trùng nhưng vẫn giữ thứ tự xuất hiện

Một yêu cầu phổ biến là loại trùng mà người dùng vẫn muốn thấy item theo thứ tự đầu tiên xuất hiện.

~~~java
LinkedHashSet<String> selected = Stream.of(
        "java", "go", "java", "kotlin", "go")
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

Đây là đoạn minh họa với các import tương ứng. Khi in set, kết quả là:

~~~text
[java, go, kotlin]
~~~

`LinkedHashSet` dựa trên thứ tự chèn của các phần tử riêng biệt. Với stream có encounter order và quá trình thu gom thông thường, các phần tử được tích lũy theo thứ tự gặp, nên tập kết quả thể hiện lần gặp đầu tiên của mỗi giá trị.

**Phân biệt với `HashSet`:**

~~~java
HashSet<String> selected = Stream.of(
        "java", "go", "java", "kotlin")
        .collect(Collectors.toCollection(HashSet::new));
~~~

Đây là đoạn minh họa. HashSet cũng loại phần tử trùng nhưng **không cam kết thứ tự duyệt**. Không đưa ra stdout cụ thể cho HashSet như một quy tắc ổn định vì thứ tự phụ thuộc implementation, hash, dữ liệu và thay đổi môi trường.

**Không dùng LinkedHashSet để thay thế sort:** nó giữ thứ tự chèn, **không sắp xếp theo alphabet/score**. Muốn sắp xếp, dùng `sorted(...)` trước khi collect vào LinkedHashSet hoặc chọn một loại sorted collection phù hợp nếu muốn duy trì semantics sắp xếp trong tập.

## 7. TreeSet: chọn thứ tự tự nhiên hoặc Comparator tùy chỉnh

`TreeSet` triển khai `NavigableSet`, giữ phần tử được sắp xếp dựa trên **Comparable** hoặc **Comparator**. Nó hữu ích khi cần tập kết quả duy trì thứ tự và cho phép thao tác như `first`, `last`, `floor`, `ceiling`, `subSet` theo hợp đồng.

### 7.1. Thứ tự tự nhiên

~~~java
TreeSet<Integer> numbers = Stream.of(9, 2, 5, 2)
        .collect(Collectors.toCollection(TreeSet::new));
~~~

Đây là đoạn minh họa. Kết quả sắp xếp là **[2, 5, 9]**; số 2 trùng chỉ giữ một.

`TreeSet::new` không có comparator tường minh, vì vậy các phần tử cần có thứ tự tự nhiên thích hợp và có thể so sánh với nhau. Nếu phần tử không Comparable hoặc không so sánh được, thao tác thêm vào TreeSet có thể ném **ClassCastException** khi chạy.

### 7.2. Comparator tùy chỉnh bằng lambda factory

Khi cần sắp xếp theo chính sách nghiệp vụ:

~~~java
TreeSet<String> byLengthThenText = Stream.of(
        "java", "go", "kotlin", "rust", "go")
        .collect(Collectors.toCollection(() ->
                new TreeSet<>(
                        Comparator.comparingInt(String::length)
                                .thenComparing(
                                        Comparator.naturalOrder()))));
~~~

Đây là đoạn minh họa cần import TreeSet, Comparator, Stream, Collectors. Thứ tự sẽ là:

~~~text
[go, java, rust, kotlin]
~~~

- `Comparator.comparingInt(String::length)` xếp chuỗi ngắn trước.
- `thenComparing(Comparator.naturalOrder())` dùng thứ tự từ điển khi cùng độ dài.
- "java" và "rust" đều dài 4 nên được sắp xếp theo thứ tự từ điển, java trước rust.
- "go" xuất hiện hai lần nhưng chỉ giữ một vì hai String bằng nhau có cùng thứ tự.

**Tại sao cần `() -> new TreeSet<>(comparator)`?** Factory không nhận tham số ở chữ ký Supplier, nhưng trong thân lambda ta có thể tạo TreeSet với comparator đã cấu hình. **`TreeSet::new`** dạng không tham số mặc định dùng natural ordering; nó không tự biết comparator nghiệp vụ.

### 7.3. Comparator quyết định cả thế nào là trùng trong TreeSet

Một điều rất quan trọng: với `TreeSet`, **hai phần tử được coi là cùng một vị trí trong Set khi comparator.compare(a,b) == 0**. Do đó, nếu comparator chỉ so sánh một thuộc tính không duy nhất, bạn có thể mất các phần tử khác nhau:

~~~java
record Product(String sku, int price) {}

Comparator<Product> byPriceOnly =
        Comparator.comparingInt(Product::price);

TreeSet<Product> items = Stream.of(
        new Product("A", 100),
        new Product("B", 100))
        .collect(Collectors.toCollection(
                () -> new TreeSet<>(byPriceOnly)));
~~~

Đây là đoạn minh họa cần import Comparator, TreeSet, Stream, Collectors và đặt record Product ở phạm vi hợp lệ. **items.size() bằng 1**, vì cả A và B có cùng price=100 nên comparator trả 0. Điều này có thể không đúng ý nghĩa “sản phẩm duy nhất theo SKU”.

Nếu cần giữ cả A và B và vẫn sắp xếp theo price, thêm khóa phân biệt:

~~~java
Comparator<Product> byPriceThenSku =
        Comparator.comparingInt(Product::price)
                .thenComparing(Product::sku);
~~~

Với comparator mới, hai sản phẩm giá 100 nhưng SKU khác nhau được giữ. Khi chọn comparator cho TreeSet, hãy kiểm tra quan hệ **consistent with equals** nếu cần tuân thủ đúng semantics chung của Set. Một comparator không nhất quán với equals có thể tạo hành vi Set gây bất ngờ ở các API khác.

## 8. Ví dụ Java 17 hoàn chỉnh: TreeSet với Comparator trên record

Tạo tệp **SortedProductsDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

record Product(String sku, int price) {}

public class SortedProductsDemo {
    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("B", 20),
                new Product("A", 30),
                new Product("C", 20),
                new Product("A", 30)
        );

        Comparator<Product> priceThenSku =
                Comparator.comparingInt(Product::price)
                        .thenComparing(Product::sku);

        TreeSet<Product> sorted = products.stream()
                .collect(Collectors.toCollection(
                        () -> new TreeSet<>(priceThenSku)));

        System.out.println("Count: " + sorted.size());
        System.out.println("SKUs: " + sorted.stream()
                .map(Product::sku)
                .toList());
        System.out.println("First: " + sorted.first().sku());
        System.out.println("Last: " + sorted.last().sku());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SortedProductsDemo.java
java SortedProductsDemo
~~~

Stdout:

~~~text
Count: 3
SKUs: [B, C, A]
First: B
Last: A
~~~

**Phân tích:**

1. Có bốn Product đầu vào, trong đó `Product("A",30)` xuất hiện hai lần.
2. Comparator sắp xếp giá tăng dần; khi cùng giá, SKU theo thứ tự từ điển.
3. Hai Product B/C cùng giá 20 nhưng SKU khác nhau nên cả hai được giữ; B trước C.
4. Hai Product A giống nhau theo cả price và SKU được coi là trùng và chỉ giữ một.
5. TreeSet cuối có thứ tự `B(20), C(20), A(30)`. Các thao tác `first()` và `last()` theo comparator, không theo thứ tự xuất hiện trong List đầu vào.

**Đừng nhầm với `Stream.sorted(comparator).toList()`:** cách đó sắp xếp nhưng **vẫn giữ các phần tử trùng**. TreeSet đồng thời áp dụng quy tắc tập hợp, nên số phần tử có thể giảm.

## 9. EnumSet: Collection chuyên cho enum

Khi phần tử thuộc cùng một kiểu **enum**, `EnumSet` là một lựa chọn hiệu quả và giàu ngữ nghĩa cho tập hợp các hằng enum. Nó giữ thứ tự **theo thứ tự khai báo hằng trong enum**, không phải theo thứ tự đầu vào.

Factory phù hợp thường là:

~~~java
() -> EnumSet.noneOf(Permission.class)
~~~

Đây là biểu thức Supplier minh họa, giả định đã định nghĩa enum Permission. Không dùng `EnumSet::new` vì EnumSet không có public no-argument constructor để gọi như ArrayList.

Tạo tệp **EnumSetCollectorDemo.java**:

~~~java
import java.util.EnumSet;
import java.util.List;
import java.util.stream.Collectors;

enum Permission {
    READ, WRITE, EXECUTE
}

public class EnumSetCollectorDemo {
    public static void main(String[] args) {
        List<Permission> granted = List.of(
                Permission.WRITE,
                Permission.READ,
                Permission.WRITE
        );

        EnumSet<Permission> permissions = granted.stream()
                .collect(Collectors.toCollection(
                        () -> EnumSet.noneOf(Permission.class)));

        System.out.println("Permissions: " + permissions);
        System.out.println("Has write: "
                + permissions.contains(Permission.WRITE));

        permissions.add(Permission.EXECUTE);
        System.out.println("Updated: " + permissions);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumSetCollectorDemo.java
java EnumSetCollectorDemo
~~~

Stdout:

~~~text
Permissions: [READ, WRITE]
Has write: true
Updated: [READ, WRITE, EXECUTE]
~~~

**Giải thích:**

- WRITE xuất hiện hai lần ở nguồn, EnumSet chỉ chứa một hằng WRITE.
- READ được khai báo trước WRITE nên danh sách in theo thứ tự READ, WRITE dù nguồn có WRITE trước.
- `noneOf(Permission.class)` tạo một EnumSet rỗng gắn với đúng kiểu Permission.
- Kết quả là một EnumSet mutable; thêm EXECUTE thành công.
- EnumSet **không cho null element**; nếu nguồn chứa null, phải có chính sách kiểm tra/loại/báo lỗi trước khi collect.

EnumSet là ví dụ điển hình mà `toCollection` giúp tạo một loại collection **khó diễn đạt bằng `Collectors.toSet()`**, vì toSet không cam kết chọn EnumSet.

## 10. Null: chọn Collection quyết định khả năng chấp nhận dữ liệu

Không phải Collection nào cũng có cùng chính sách đối với `null`:

- **ArrayList** và **LinkedList** có thể chứa null element.
- **HashSet** và **LinkedHashSet** có thể chứa một null element.
- **TreeSet** với natural ordering **không chấp nhận null** trong sử dụng thông thường; thêm null sẽ gây NPE. Comparator tùy chỉnh có thể hỗ trợ null nếu được thiết kế rõ ràng, nhưng không nên mặc định.
- **EnumSet** không chấp nhận null.
- **Collectors.toUnmodifiableList/Set** không chấp nhận null; khác với các collection mutable kể trên.
- **Stream.toList()** có thể chứa null nhưng danh sách tạo ra là unmodifiable.

Ví dụ:

~~~java
List<String> values = Arrays.asList("A", null, "B");

ArrayList<String> list = values.stream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Đây là đoạn minh họa với imports List, Arrays, ArrayList, Collectors. **list** có nội dung `["A", null, "B"]`, và `System.out.println(list)` in **[A, null, B]**.

Tuy nhiên:

~~~java
// CÓ THỂ NÉM NPE nếu nguồn có null:
TreeSet<String> sorted = values.stream()
        .collect(Collectors.toCollection(TreeSet::new));
~~~

Đây là **đoạn minh họa gây lỗi runtime** khi TreeSet dùng natural ordering gặp null. Nếu null được phép xuất hiện nhưng không nên lọt vào tập kết quả:

~~~java
TreeSet<String> sorted = values.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toCollection(TreeSet::new));
~~~

Đây là đoạn minh họa cần thêm import Objects. Kết quả sorted là **[A, B]**.

**Không tự động filter null nếu null biểu thị dữ liệu sai phải báo lỗi.** Khi chính sách yêu cầu fail fast, cân nhắc `Objects.requireNonNull` ở boundary và thông báo dữ liệu lỗi. Việc chọn một collector không thay thế validation.

## 11. Quan hệ giữa thứ tự Stream, thứ tự thu gom và thứ tự duyệt Collection

Có **ba khái niệm thứ tự** khác nhau:

1. **Encounter order của Stream:** thứ tự mà nguồn/chuỗi thao tác định nghĩa, ví dụ List có thứ tự, HashSet không có yêu cầu thứ tự.
2. **Thứ tự tích lũy vào Collection:** `toCollection` thu thập các phần tử theo encounter order nếu Stream có thứ tự, theo hợp đồng collector.
3. **Thứ tự khi duyệt Collection kết quả:** phụ thuộc vào loại collection: ArrayList/LinkedList theo vị trí, LinkedHashSet theo chèn, TreeSet theo comparator, HashSet không cam kết thứ tự.

Vì vậy:

~~~java
LinkedHashSet<Integer> chosen = Stream.of(4, 2, 4, 3, 2)
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

Đây là đoạn minh họa; khi duyệt, `chosen` cho **[4, 2, 3]**. Nhưng:

~~~java
TreeSet<Integer> chosen = Stream.of(4, 2, 4, 3, 2)
        .collect(Collectors.toCollection(TreeSet::new));
~~~

Lại cho **[2, 3, 4]** do natural ordering.

**Một lưu ý với `unordered()` hoặc nguồn unordered:** nếu Stream không có encounter order, không nên suy ra LinkedHashSet sẽ ổn định như List có thứ tự. LinkedHashSet chỉ giữ **thứ tự chèn mà nó nhận được**, chứ không tạo ra một thứ tự nghiệp vụ vốn không được nguồn định nghĩa.

## 12. Collector factory phải tạo Collection mới và phù hợp

Đây là điểm rất dễ bị bỏ qua. Một Supplier dùng với `toCollection` nên tạo **một Collection trống, độc lập**, có khả năng nhận phần tử. Đừng trả một Collection đã có dữ liệu, hoặc trả cùng instance dùng chung qua nhiều lần gọi Supplier.

Phản mẫu:

~~~java
List<String> shared = new ArrayList<>();

// SAI VỀ THIẾT KẾ: factory trả cùng một object.
// Collectors.toCollection(() -> shared)
~~~

Đây là đoạn phản mẫu minh họa, giả định các imports phù hợp. Với parallel stream, collector có thể cần nhiều container tích lũy và **kết hợp chúng**. Nếu factory trả cùng object, kết quả có thể sai, trùng, race hoặc vi phạm contract; ngay cả tuần tự, việc dùng lại container sẽ khiến các lần collect không độc lập.

Đúng:

~~~java
Collectors.toCollection(ArrayList::new)
~~~

hoặc khi có cấu hình:

~~~java
Collectors.toCollection(() -> new TreeSet<>(comparator))
~~~

với comparator đã được định nghĩa phù hợp.

**Không dùng singleton collection immutable** như `() -> List.of()` làm factory tích lũy: Collector cần gọi phương thức thêm phần tử; collection không sửa được có thể ném **UnsupportedOperationException**. Tương tự, factory cho collection đã chứa dữ liệu có thể làm xuất hiện phần tử ngoài nguồn.

### 12.1. Mỗi lần collect nên độc lập

Tạo tệp **IndependentCollectionsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

public class IndependentCollectionsDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2, 3);

        ArrayList<Integer> first = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));

        ArrayList<Integer> second = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));

        first.add(99);

        System.out.println("first: " + first);
        System.out.println("second: " + second);
        System.out.println("same instance: " + (first == second));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac IndependentCollectionsDemo.java
java IndependentCollectionsDemo
~~~

Stdout:

~~~text
first: [1, 2, 3, 99]
second: [1, 2, 3]
same instance: false
~~~

Hai lần `collect` chạy trên **hai Stream mới** tạo từ source và dùng factory tạo collection mới. Thay đổi first không ảnh hưởng second; đây là hành vi mong muốn.

**Lưu ý:** Kết quả collection mới độc lập về **cấu trúc**, không nhất thiết tạo bản sao sâu của **mọi phần tử**. Nếu T là một object mutable, cả hai collection có thể vẫn tham chiếu cùng object phần tử từ source. Muốn deep copy, phải có chính sách và phép chuyển đổi phần tử riêng.

## 13. Parallel Stream: không tự chia sẻ Collection giữa các worker

Khi dùng `parallelStream()`, collector thông thường có thể:

1. Tạo nhiều container trung gian từ Supplier.
2. Tích lũy phần tử vào từng container.
3. Kết hợp các container bằng combiner.
4. Trả Collection cuối.

`Collectors.toCollection` có cách kết hợp riêng; với các factory như `ArrayList::new`, `LinkedHashSet::new`, `TreeSet::new`, không cần tự viết synchronized block chỉ để dùng collector theo cơ chế chuẩn.

~~~java
ArrayList<Integer> result = IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Đây là đoạn minh họa cần import IntStream, ArrayList, Collectors. Với nguồn có encounter order 1..1000, collector giữ kết quả theo encounter order; kết quả ArrayList chứa 1000 phần tử theo thứ tự tương ứng.

**Nhưng không được suy ra:**

- Supplier luôn được gọi đúng một lần trong parallel stream.
- ArrayList do Supplier tạo được chia sẻ an toàn trực tiếp giữa nhiều thread để cùng `add` đồng thời.
- Mỗi nhánh hoặc worker của Stream chạy theo một lịch cố định.
- Chọn parallel chắc chắn nhanh hơn: có chi phí chia việc, merge và allocation.
- HashSet/TreeSet tự trở thành thread-safe chỉ vì xuất hiện trong một collector parallel.

Về thuật ngữ, collector `toCollection` không phải collector **CONCURRENT** theo nghĩa cho mọi worker tích lũy đồng thời vào cùng container. Các container trung gian được kết hợp theo cơ chế collect. Sau khi thu gom xong, **kết quả ArrayList/TreeSet/LinkedHashSet không tự thread-safe** nếu bạn cho nhiều thread sửa nó về sau.

### 13.1. Khi nào parallel gây vấn đề?

Nếu `collectionFactory` có side effect, ví dụ ghi một counter global hay trỏ tới trạng thái mutable chung, số lần gọi factory không nên được dùng như dữ liệu nghiệp vụ. Nếu mapper/filter có side effect hoặc phụ thuộc trạng thái thay đổi, kết quả có thể không ổn định. Hãy ưu tiên **pure functions** và các factory độc lập.

Các phần tử trong TreeSet cần comparator có hợp đồng nhất quán, không phụ thuộc vào thứ tự thời gian hoặc trạng thái mutable. Nếu comparator thay đổi ý nghĩa khi các phần tử đã ở trong set, cấu trúc sorted set có thể không còn phản ánh đúng thứ tự.

## 14. Ví dụ thiết kế nghiệp vụ: sắp thứ tự nhưng không mất đơn hàng

Giả sử một hệ thống muốn hiển thị mọi đơn hàng theo tổng tiền tăng dần, kể cả nhiều đơn cùng tổng tiền. Nếu dùng TreeSet với comparator chỉ theo tổng tiền, nhiều đơn có giá trị bằng nhau sẽ bị coi là trùng và mất bớt bản ghi.

Phản mẫu:

~~~java
Comparator<Order> byTotal =
        Comparator.comparingLong(Order::totalCents);

TreeSet<Order> ordersByPrice = orders.stream()
        .collect(Collectors.toCollection(
                () -> new TreeSet<>(byTotal)));
~~~

Đây là đoạn minh họa, Order là loại đã định nghĩa và có `totalCents()`. Nếu hai đơn cùng tổng tiền, comparator trả 0 và TreeSet chỉ giữ một. Không phù hợp nếu yêu cầu là **sắp xếp tất cả đơn**, không phải tạo tập không trùng.

Cách đúng khi muốn giữ toàn bộ đơn:

~~~java
ArrayList<Order> sortedOrders = orders.stream()
        .sorted(Comparator.comparingLong(Order::totalCents)
                .thenComparing(Order::id))
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Đây là đoạn minh họa, giả định Order.id là khóa phù hợp và imports cần thiết. Stream.sorted sắp xếp phần tử nhưng không tự loại trùng; ArrayList giữ đủ bản ghi, kể cả những bản ghi bằng nhau.

Khi **muốn loại trùng** theo một khóa, phải xác định rõ quy tắc ưu tiên: giữ bản ghi đầu, giữ bản ghi mới nhất, có giá lớn nhất hay báo lỗi. TreeSet với comparator chỉ theo khóa có thể loại phần tử khác biệt mà không cho biết vì sao; đôi khi `Map<Id,Order>` và merge function theo hợp đồng nghiệp vụ phù hợp hơn.

## 15. Lỗi phổ biến với Collectors.toCollection()

| Lỗi/ngộ nhận | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ `Collectors.toList()` luôn là ArrayList mutable | Phụ thuộc implementation, không được API hứa | Dùng `toCollection(ArrayList::new)` khi cần cụ thể |
| Nghĩ `stream.toList()` có thể `add` | UnsupportedOperationException | Chọn mutable collection nếu thực sự cần sửa |
| Dùng `HashSet::new` rồi dựa vào thứ tự in | Không có guarantee thứ tự | LinkedHashSet hoặc TreeSet tùy mục tiêu |
| Dùng `TreeSet::new` với object không Comparable | ClassCastException khi thu gom | Truyền comparator hợp lệ |
| Comparator chỉ so một thuộc tính không duy nhất | TreeSet làm mất bản ghi có comparator == 0 | Thêm tie-breaker hoặc dùng List nếu phải giữ tất cả |
| Cho rằng TreeSet luôn dùng `equals` để xác định trùng | Thực tế dùng compareTo/comparator == 0 | Thiết kế comparator nhất quán với identity mong muốn |
| Không kiểm tra null trước TreeSet/EnumSet | NPE khi thêm phần tử không hợp lệ | Validation hoặc filter theo chính sách |
| Dùng `() -> shared` trả cùng collection | Thu gom sai, đặc biệt khi parallel | Tạo instance mới mỗi lần Supplier được gọi |
| Dùng `() -> List.of()` làm factory | Collector không thể thêm phần tử | Supplier phải trả collection có thể tích lũy |
| Cho rằng `IntStream.collect(Collectors.toCollection(...))` hợp lệ | Sai API collect của primitive stream | Dùng `boxed()` hoặc primitive collect thích hợp |
| Cho rằng factory chỉ gọi một lần | Không đúng với một số cách thu gom parallel | Không gắn side effect vào factory |
| Nhầm collection mutable với phần tử mutable | Thay đổi cấu trúc không có nghĩa deep copy | Xác định ownership và khả năng sửa object |
| Dựa vào thứ tự với nguồn `unordered()` | Không có thứ tự ổn định để bảo toàn | Định nghĩa thứ tự hoặc sort tường minh |
| Dùng collector để thay thế validation | Dữ liệu hỏng có thể bị loại/đổi nghĩa | Kiểm tra hợp đồng đầu vào rõ ràng |

## 16. Checklist chọn Collection tường minh

Trước khi viết `collect(Collectors.toCollection(...))`, tự trả lời:

1. **Có cần một loại Collection cụ thể không?** Nếu chỉ cần List không sửa, `toList()` có thể gọn hơn.
2. **Có cần giữ bản sao/trùng không?** List giữ trùng; Set loại trùng theo semantics riêng.
3. **Thứ tự nào cần thiết?** Thứ tự gặp, thứ tự chèn, thứ tự tự nhiên, hay comparator tùy biến?
4. **Sau khi collect có cần add/remove/sort lại không?** Chọn factory có mutability phù hợp.
5. **Nguồn có null không?** Chọn chính sách theo Collection và hợp đồng nghiệp vụ.
6. **Nếu TreeSet, comparator có thể trả 0 cho hai thực thể khác nhau không?** Cân nhắc tie-breaker hoặc dùng List.
7. **Nếu enum, có thể dùng EnumSet không?** Factory phải có kiểu enum tường minh.
8. **Supplier tạo object mới mỗi lần không?** Không dùng shared mutable instance.
9. **Có chạy parallel không?** Không dựa vào số lần gọi Supplier hoặc lịch thực thi.
10. **Có cần deep copy không?** `toCollection` thường chỉ gom tham chiếu phần tử; không sao chép trạng thái.
11. **Có cần tiếp tục làm việc qua interface hay concrete type?** Công bố kiểu trả về tối thiểu trong public API, giữ lựa chọn implementation cục bộ khi có thể.
12. **Đã test source rỗng, null, phần tử trùng, comparator và thứ tự chưa?** Đây là những case có khả năng làm lộ sai thiết kế.

## 17. Bài tập thực hành

### Bài 1: Loại trùng và giữ thứ tự

Nguồn `["a", "b", "a", "c", "b"]`. Thu thập bằng `ArrayList::new`, `LinkedHashSet::new` và `TreeSet::new`. Dự đoán kết quả và giải thích vì sao Set không giữ bản sao.

### Bài 2: Chọn kiểu mutable

Cho `Stream.of("A", "B")`. Thu kết quả bằng `toList()` và `toCollection(ArrayList::new)`. Thử gọi `add("C")` trên hai kết quả. Dự đoán cái nào ném UnsupportedOperationException; giải thích vì sao.

### Bài 3: Comparator làm mất bản ghi

Có hai Product `("A", 100)` và `("B", 100)`. Hãy viết TreeSet với comparator chỉ theo price và quan sát size. Sau đó thêm `thenComparing(Product::sku)` để giữ cả hai. Nếu yêu cầu thực sự là giữ toàn bộ mọi bản ghi (kể cả bản ghi có cùng SKU), kiểu collection nào hợp lý hơn?

### Bài 4: Factory cho EnumSet

Tạo enum `Role { VIEWER, EDITOR, ADMIN }`. Từ stream có nhiều lần VIEWER, collect vào `EnumSet<Role>` bằng `toCollection(() -> EnumSet.noneOf(Role.class))`. Dự đoán thứ tự in theo khai báo enum.

### Bài 5: Primitive stream cần boxed()

Tạo `IntStream.rangeClosed(1, 5)`, chuyển thành Stream<Integer> bằng `boxed()`, rồi gom vào `LinkedList<Integer>`. Tại sao `IntStream` không dùng cùng overload `collect(Collector)` như Stream<Integer>?

### Bài 6: Kiểm tra factory độc lập

Hãy tạo hai kết quả bằng `source.stream().collect(toCollection(ArrayList::new))`. Sửa danh sách thứ nhất rồi kiểm tra danh sách thứ hai không đổi cấu trúc. Thử giải thích tại sao `() -> sharedList` không phải Supplier đúng cho trường hợp này.

### Bài 7: Chọn loại Collection cho nghiệp vụ

Một trang web cần:
- Hiển thị **tất cả** đơn theo tổng tiền tăng dần.
- Hiển thị danh sách tag **không trùng** theo thứ tự lần đầu xuất hiện.
- Lưu quyền truy cập bằng **enum**.
- Tìm giá trị nhỏ nhất/lớn nhất trong một tập có comparator.

Hãy đề xuất Collection phù hợp cho từng mục, chỉ ra trường hợp cần List thay vì TreeSet để không làm mất phần tử.

## 18. Ghi nhớ

**`Collectors.toCollection(Supplier<C>)` cho phép chọn tường minh loại Collection kết quả** của một object Stream: `ArrayList`, `LinkedList`, `HashSet`, `LinkedHashSet`, `TreeSet`, `EnumSet`... Supplier cung cấp **collection mới có thể tích lũy**. Khi cần cấu hình comparator/capacity/kiểu enum, dùng lambda factory.

**Loại Collection quyết định ngữ nghĩa đầu ra:** List giữ bản sao và có vị trí; Set loại trùng; LinkedHashSet giữ thứ tự chèn; TreeSet sắp xếp và dùng comparator để xác định trùng; EnumSet dùng thứ tự enum. Chọn sai loại có thể **làm mất dữ liệu**, không chỉ thay đổi kiểu Java.

**`Stream.toList()` không sửa được cấu trúc**, còn `Collectors.toList()` không cam kết implementation hay mutability. Nếu caller cần **ArrayList mutable**, `toCollection(ArrayList::new)` thể hiện hợp đồng rõ hơn.

Trước khi dùng collector, hãy hỏi: **“Tôi thực sự cần giữ tất cả phần tử, giữ thứ tự, loại trùng, hay một kiểu collection chuyên biệt — và factory có tạo object mới phù hợp với những yêu cầu đó không?”**