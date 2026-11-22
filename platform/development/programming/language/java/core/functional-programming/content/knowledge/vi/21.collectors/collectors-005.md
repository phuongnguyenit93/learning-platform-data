# `toSet()`, `toUnmodifiableList()` và `toUnmodifiableSet()` trong Java Stream

Khi xử lý Stream, ta thường cần **thu thập các phần tử** thành một `List` hoặc `Set`. Ba collector trong `java.util.stream.Collectors` là:

- `Collectors.toSet()` — thu thập thành một `Set` để loại các phần tử trùng nhau; **không bảo đảm** loại triển khai, thứ tự duyệt hoặc khả năng sửa kết quả.
- `Collectors.toUnmodifiableList()` — thu thập thành một `List` **không thể sửa cấu trúc**, giữ các phần tử trùng nhau và giữ *encounter order* khi stream có thứ tự; **không cho phép null**.
- `Collectors.toUnmodifiableSet()` — thu thập thành một `Set` **không thể sửa cấu trúc**, loại phần tử trùng nhau, **không bảo đảm thứ tự** và **không cho phép null**.

Chúng đều là **collector** được truyền vào **terminal operation** `Stream.collect(...)`. Không nhầm với `Stream.toList()` là một phương thức terminal trực tiếp, hay với `Set` có thể thay đổi được.

Ví dụ:

~~~java
List<String> words = List.of("pear", "apple", "pear", "banana");

Set<String> a = words.stream().collect(Collectors.toSet());
List<String> b = words.stream().collect(Collectors.toUnmodifiableList());
Set<String> c = words.stream().collect(Collectors.toUnmodifiableSet());
~~~

Đoạn mã cần `import java.util.List;`, `import java.util.Set;` và `import java.util.stream.Collectors;`, nằm trong phương thức. Kết quả `b` giữ bốn phần tử đúng thứ tự đầu vào; hai Set chứa ba giá trị phân biệt. Tuy nhiên, **không dựa vào kết quả in trực tiếp Set để khẳng định thứ tự**.

## 1. Bối cảnh: collector, terminal và sự khác nhau giữa List và Set

Pipeline Stream thường gồm nguồn → các phép trung gian → thao tác kết thúc:

~~~text
List<String> source
       |
       v
source.stream().filter(...).map(...)
       |
       v
collect(Collectors.toUnmodifiableList())  <-- terminal
       |
       v
List<String> kết quả, không sửa được
~~~

`Collectors.toSet()` **không** tự tiêu thụ một Stream; nó trả về một đối tượng `Collector` mô tả cách thu thập. Lệnh `stream.collect(collector)` mới là terminal yêu cầu thực thi pipeline và trả kết quả.

Một vài khác biệt có ý nghĩa trực tiếp:

| Tiêu chí | `List<E>` | `Set<E>` |
| --- | --- | --- |
| Trùng phần tử theo `equals` | Cho phép | Không cho phép |
| Vị trí và thứ tự | Có thứ tự chỉ số | Tùy triển khai; `Set` nói chung không cam kết |
| Tra cứu | `get(index)` | `contains(value)`, không có `get(index)` |
| Nhiều đối tượng bằng nhau | Có thể cùng hiện diện | Chỉ một phần tử tương đương được giữ |
| Khả năng sửa | Tùy đối tượng/triển khai | Tùy đối tượng/triển khai |

**List hay Set** mô tả hợp đồng lưu trữ và trùng lặp; **modifiable hay unmodifiable** mô tả hợp đồng thay đổi kết quả. Hai câu hỏi này độc lập: một List có thể không sửa được, một Set có thể sửa được — nhưng riêng `Collectors.toSet()` **không cam kết** kết quả có thể sửa.

### Encounter order

*Encounter order* là thứ tự phần tử do nguồn và pipeline xác định. `List.stream()` có thứ tự gặp phần tử tương ứng list; `HashSet.stream()` không có cam kết thứ tự như vậy.

Collector cho List bảo toàn thứ tự gặp trên stream ordered theo hợp đồng phù hợp. Ngược lại, `Collectors.toSet()` và `Collectors.toUnmodifiableSet()` là **unordered collectors**, nên thứ tự duyệt Set thu được không phải là thứ tự đầu vào được bảo đảm.

## 2. `Collectors.toSet()` — bỏ trùng nhưng không hứa mutable

Cách dùng:

~~~java
Set<String> unique = Stream.of("A", "B", "A")
        .collect(Collectors.toSet());
~~~

Tập kết quả có hai giá trị phân biệt `A` và `B`. `Set` xác định tính trùng lặp bằng `equals`. Với kiểu tự viết, hãy thiết kế `equals` và `hashCode` nhất quán để hoạt động với các cấu trúc hash phổ biến.

Hợp đồng API **không bảo đảm**:

1. Kiểu Set cụ thể (`HashSet`, `LinkedHashSet`, `TreeSet`...).
2. Thứ tự duyệt kết quả.
3. Khả năng sửa kết quả.
4. Tính tuần tự hóa (*serializability*) hay thread-safety.
5. Việc cho phép các phần tử `null` trong mọi triển khai.

Trên nhiều JDK hiện hành, có thể thấy một Set có thể gọi `add(...)`, nhưng **không nên viết chương trình phụ thuộc vào chi tiết triển khai đó**. Nếu muốn một Set có thể sửa, hãy chọn collector nói rõ kiểu Set được tạo:

~~~java
Set<String> mutable = words.stream()
        .collect(Collectors.toCollection(HashSet::new));
mutable.add("melon");
~~~

Đây là đoạn minh họa có `words` và import `Set`, `HashSet`, `Collectors`; `toCollection(HashSet::new)` tạo `HashSet` bằng supplier chỉ định. Nếu cần bảo toàn thứ tự gặp (với stream ordered), dùng `LinkedHashSet`:

~~~java
LinkedHashSet<String> insertionOrdered = words.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

`LinkedHashSet` thường lặp theo thứ tự chèn; đây là lựa chọn tường minh khi yêu cầu duyệt theo thứ tự xuất hiện đầu tiên, không phải đặc tính của `toSet()`.

### Kiểu suy luận

~~~java
Set<Integer> ids = Stream.of(2, 1, 2, 3)
        .collect(Collectors.toSet());
~~~

Phương thức collector tự suy luận kiểu `Integer`. Vì `Set` không có chỉ số, `ids.get(0)` không hợp lệ. Nếu cần "phần tử đầu", phải xác định một thứ tự (hoặc một tiêu chí) trước khi chọn; không nên suy diễn "đầu tiên" từ một Set không cam kết thứ tự.

## 3. `Collectors.toUnmodifiableList()` — giữ thứ tự, giữ trùng và cấm sửa

Từ **Java 10**, `Collectors.toUnmodifiableList()` trả về collector tạo `List` không cho phép sửa cấu trúc:

~~~java
List<String> result = Stream.of("A", "B", "A")
        .collect(Collectors.toUnmodifiableList());
// [A, B, A]
~~~

Đặc điểm:

- **Giữ phần tử trùng lặp:** hai phần tử `"A"` vẫn hiện diện.
- **Giữ encounter order:** với stream có thứ tự, kết quả theo thứ tự gặp từ pipeline.
- **Unmodifiable:** các thao tác sửa như `add`, `remove` hoặc `set` ném `UnsupportedOperationException`.
- **Không cho phép phần tử null:** nếu stream cung cấp `null` cho collector, thao tác thu thập ném `NullPointerException`.
- Không được suy ra kiểu triển khai List, tính tuần tự hóa hoặc các đặc tính không được API hứa.

Ví dụ minh họa hành vi:

~~~java
List<String> fixed = List.of("a", "b").stream()
        .collect(Collectors.toUnmodifiableList());

// fixed.add("c");  // Biên dịch được nhưng ném UnsupportedOperationException.
// fixed.set(0, "x"); // Tương tự.
~~~

Unmodifiable là ràng buộc **của collection trả về**, không phải bảo vệ toàn bộ mọi object được tham chiếu bên trong. Nếu phần tử là đối tượng mutable, các trường của phần tử vẫn có thể thay đổi; xem mục về shallow immutability.

`toUnmodifiableList()` không phải cách "sort" tự động. Nếu muốn thứ tự cụ thể, đặt `sorted(...)` trong pipeline **trước** `collect`.

## 4. `Collectors.toUnmodifiableSet()` — không sửa được và không trùng

Cũng từ **Java 10**, `Collectors.toUnmodifiableSet()` thu thập giá trị thành Set không thể sửa cấu trúc:

~~~java
Set<String> codes = Stream.of("A", "B", "A")
        .collect(Collectors.toUnmodifiableSet());
// Chứa A và B, không cam kết thứ tự duyệt.
~~~

Hợp đồng chính:

- Phần tử trùng theo `equals` được loại bỏ, như một Set.
- Set trả về **unmodifiable**; gọi `add`, `remove`... ném `UnsupportedOperationException`.
- **`null` bị từ chối** bằng `NullPointerException`.
- Collector **unordered**: không cam kết duyệt theo thứ tự gặp.
- Khi nhiều đối tượng khác nhau mà `equals` xem là bằng nhau, một đại diện **bất kỳ** trong những đối tượng tương đương có thể được giữ. Không dựa vào việc giữ "đối tượng đầu tiên".
- Không dùng comparator cho việc xác định trùng: `toUnmodifiableSet()` dựa trên quy tắc bằng nhau của Set, không phải kết quả từ `sorted(comparator)`.

Ví dụ, nếu cần "lấy một bản ghi cho mỗi ID" với yêu cầu ưu tiên bản ghi mới nhất, `toUnmodifiableSet` **không tự biết chính sách** đó. Hãy thiết kế bước chọn đại diện bằng `toMap` cùng merge function phù hợp, rồi mới tạo collection theo yêu cầu.

### Set unmodifiable khác với deep immutable

~~~java
List<StringBuilder> builders = Stream.of(new StringBuilder("A"))
        .collect(Collectors.toUnmodifiableList());
builders.get(0).append("B"); // Đối tượng StringBuilder vẫn thay đổi được.
~~~

Đoạn nằm trong một phương thức có import `Stream`, `Collectors`, `List`. Ta **không thể thay** phần tử trong danh sách, nhưng đối tượng được tham chiếu vẫn có thể bị sửa. Với Set, việc sửa khóa của phần tử theo cách làm thay đổi `equals/hashCode` còn có thể gây hỏng tính nhất quán của thao tác tìm kiếm. Hãy dùng phần tử immutable nếu cần tập kết quả ổn định.

## 5. Bảng so sánh trực tiếp ba collector

| Đặc tính | `toSet()` | `toUnmodifiableList()` | `toUnmodifiableSet()` |
| --- | --- | --- | --- |
| Kết quả | `Set<T>` | `List<T>` | `Set<T>` |
| Trùng lặp | Loại trùng | Giữ trùng | Loại trùng |
| Thứ tự kết quả | Không bảo đảm | Theo encounter order nếu có | Không bảo đảm |
| Được sửa kết quả? | **Không có cam kết** | **Không** | **Không** |
| `null` trong dữ liệu | **Không nên dựa vào hỗ trợ null** | **Từ chối** | **Từ chối** |
| Java tối thiểu | Java 8 | Java 10 | Java 10 |
| Collector unordered? | Có | Không theo nghĩa của collector dành cho danh sách có thứ tự | Có |
| Dùng khi | Muốn Set và không cần các bảo đảm bổ sung | Muốn List đọc-only, giữ trùng, có thứ tự | Muốn Set đọc-only, không trùng |

"Đọc-only"/"không sửa" ở bảng là **không hỗ trợ sửa collection**. Nó **không khẳng định** phần tử là immutable hoặc an toàn luồng trong mọi trường hợp.

`Collectors.toSet()` đáng dùng khi chỉ cần một Set và không có yêu cầu rõ về thứ tự/mutability. Nếu yêu cầu của API là "trả dữ liệu không cho bên gọi sửa collection", hãy ưu tiên collector unmodifiable phù hợp. Nếu cần khả năng sửa chắc chắn hoặc thứ tự duyệt xác định, chọn `toCollection(...)` với loại triển khai cụ thể.

## 6. Ví dụ Java 17+ hoàn chỉnh và kiểm chứng kết quả

Lưu vào tệp **`CollectorChoicesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorChoicesDemo {
    public static void main(String[] args) {
        List<String> source = List.of("pear", "apple", "pear", "banana");

        Set<String> regular = source.stream().collect(Collectors.toSet());
        List<String> immutableList =
                source.stream().collect(Collectors.toUnmodifiableList());
        Set<String> immutableSet =
                source.stream().collect(Collectors.toUnmodifiableSet());

        System.out.println("toSet(sorted for display)=" + regular.stream().sorted().toList());
        System.out.println("toUnmodifiableList=" + immutableList);
        System.out.println("toUnmodifiableSet(sorted for display)="
                + immutableSet.stream().sorted().toList());

        try {
            immutableList.add("melon");
        } catch (UnsupportedOperationException e) {
            System.out.println("listMutation=unsupported");
        }
        try {
            immutableSet.add("melon");
        } catch (UnsupportedOperationException e) {
            System.out.println("setMutation=unsupported");
        }

        List<String> nullable = Arrays.asList("a", null, "b");
        System.out.println("streamToListWithNull=" + nullable.stream().toList());
        try {
            nullable.stream().collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException e) {
            System.out.println("unmodifiableListNull=rejected");
        }
        try {
            nullable.stream().collect(Collectors.toUnmodifiableSet());
        } catch (NullPointerException e) {
            System.out.println("unmodifiableSetNull=rejected");
        }

        LinkedHashSet<String> insertionOrdered = source.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));
        ArrayList<String> mutableList = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        mutableList.add("melon");
        System.out.println("linkedHashSet=" + insertionOrdered);
        System.out.println("mutableList=" + mutableList);
    }
}
~~~

Lệnh biên dịch và chạy (JDK 17 trở lên):

~~~bash
javac CollectorChoicesDemo.java
java CollectorChoicesDemo
~~~

**Stdout chính xác:**

~~~text
toSet(sorted for display)=[apple, banana, pear]
toUnmodifiableList=[pear, apple, pear, banana]
toUnmodifiableSet(sorted for display)=[apple, banana, pear]
listMutation=unsupported
setMutation=unsupported
streamToListWithNull=[a, null, b]
unmodifiableListNull=rejected
unmodifiableSetNull=rejected
linkedHashSet=[pear, apple, banana]
mutableList=[pear, apple, pear, banana, melon]
~~~

Phân tích:

1. `toSet()` loại `"pear"` trùng; khi in, code **chủ động sắp xếp lại** bằng `regular.stream().sorted().toList()` nên stdout xác định. Không phải `toSet()` tự sắp xếp.
2. `toUnmodifiableList()` giữ cả hai `"pear"` và giữ thứ tự List nguồn.
3. `toUnmodifiableSet()` loại trùng, không cho phép sửa; kết quả in cũng được sorted riêng.
4. `add(...)` trên hai collection unmodifiable gây `UnsupportedOperationException` được bắt và in thông báo.
5. `nullable.stream().toList()` từ Java 16+ có thể chứa `null`. Hai collector unmodifiable ở đây **không chấp nhận null** và ném `NullPointerException`.
6. `toCollection(LinkedHashSet::new)` tạo Set có thứ tự chèn theo nguồn ordered; `toCollection(ArrayList::new)` tạo danh sách chắc chắn có thể thêm phần tử.
7. Ví dụ **không gọi `add(...)` trên kết quả `Collectors.toSet()`** vì việc đó không được hợp đồng API bảo đảm.

Mã chạy được trên Java 17, các trường hợp lỗi được bắt đúng kiểu ngoại lệ, đầu ra đã được kiểm chứng bằng biên dịch và thực thi thực tế.

## 7. Không nhầm với `Stream.toList()` và `Collectors.toList()`

Ba API tên gần nhau nhưng hợp đồng khác nhau:

~~~java
List<String> a = stream.toList();                              // Java 16+
List<String> b = stream.collect(Collectors.toList());          // Java 8+
List<String> c = stream.collect(Collectors.toUnmodifiableList()); // Java 10+
~~~

**Lưu ý:** đây là ba **cách dùng thay thế**, không được gọi liên tục trên cùng biến `stream` đã tiêu thụ. Mỗi terminal cần một Stream mới từ nguồn; đoạn mã chỉ mang tính đối chiếu cú pháp.

| API | Hợp đồng quan trọng |
| --- | --- |
| `Stream.toList()` | Trả List unmodifiable; vẫn có thể chứa phần tử `null` |
| `Collectors.toList()` | Trả List; **không cam kết** kiểu triển khai, tính mutability, serializability hay thread-safety |
| `Collectors.toUnmodifiableList()` | Trả List unmodifiable; **từ chối null** |
| `Collectors.toCollection(ArrayList::new)` | Tạo một `ArrayList` cụ thể có thể thêm/xóa |

`Stream.toList()` và `Collectors.toUnmodifiableList()` đều không cho sửa List, nhưng **khác chính sách null**. Đừng tự động thay phương thức này bằng phương thức kia khi đầu vào có khả năng chứa `null`.

Khi cần giá trị trả về có thể sửa, một cách rõ ràng:

~~~java
ArrayList<String> editable = source.stream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Khi muốn có List không cho sửa và đã kiểm chứng dữ liệu không null, `Collectors.toUnmodifiableList()` rất phù hợp. Không cần dùng `Collections.unmodifiableList(...)` để bọc lại một List đã unmodifiable.

## 8. Null: cần quyết định chính sách dữ liệu

Hai collector unmodifiable từ Java 10 **bác bỏ phần tử `null`**. Nếu nguồn chứa `null`, lời gọi terminal có thể ném `NullPointerException`:

~~~java
List<String> nullable = Arrays.asList("A", null, "B");

// Ném NullPointerException:
nullable.stream().collect(Collectors.toUnmodifiableList());
nullable.stream().collect(Collectors.toUnmodifiableSet());
~~~

Đây là đoạn code minh họa, đừng chạy nếu không xử lý ngoại lệ. Nếu ứng dụng có quy tắc **bỏ giá trị thiếu**:

~~~java
List<String> nonNull = nullable.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());
~~~

Đoạn này cần import `java.util.Objects` và `List`. Đối với Set:

~~~java
Set<String> nonNullUnique = nullable.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableSet());
~~~

Khi dữ liệu `null` mang ý nghĩa "lỗi nhập" hoặc "bắt buộc phải có", không nên tự xóa bằng filter; hãy kiểm tra và báo lỗi theo hợp đồng nghiệp vụ. Một lựa chọn khác là `map(s -> s == null ? "<missing>" : s)` khi ứng dụng có quy tắc thay thế, nhưng phải bảo đảm marker không trùng giá trị hợp lệ.

**Không suy luận ngược** rằng `Collectors.toSet()` là cách portable để giữ `null`. Một số triển khai nhận null, nhưng hợp đồng API không đưa ra bảo đảm về việc đó; nếu dữ liệu yêu cầu lưu null, chọn cấu trúc cụ thể hỗ trợ và thử nghiệm chính sách dữ liệu.

## 9. Unmodifiable collection: snapshot hay view?

Hai collector unmodifiable **tạo ra kết quả thu thập** từ các phần tử Stream. Sau khi collect hoàn tất, ta không thể gọi các thao tác thay đổi cấu trúc của chính List/Set đó. Điều này khác với:

~~~java
List<String> backing = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(backing);
backing.add("C");
// view cũng nhìn thấy "C" vì đây là view bao ngoài backing list.
~~~

Đoạn này cần import `java.util.List`, `java.util.ArrayList`, `java.util.Collections`. `Collections.unmodifiableList(...)` tạo một *unmodifiable view*; việc thay đổi collection gốc qua một tham chiếu khác vẫn có thể nhìn thấy qua view.

Ngược lại, `Collectors.toUnmodifiableList()` xây dựng kết quả thu thập, không cung cấp cơ chế để bên gọi sau đó thay đổi collection ấy. Nhưng **các đối tượng phần tử mutable vẫn được tham chiếu**, không tự deep-copy toàn bộ graph dữ liệu.

`List.copyOf(collection)` và `Set.copyOf(collection)` cũng tạo kết quả unmodifiable từ collection sẵn có, từ chối null. Khi nguồn đã có một collection không cho sửa, implementation có thể tái sử dụng đối tượng thay vì tạo bản sao vật lý; không dựa vào khác biệt danh tính (`==`) để xác định "bản sao". `Set.copyOf` loại trùng và có thể giữ đại diện bất kỳ nếu các phần tử bằng nhau.

### Bất biến nông và thread safety

~~~java
List<StringBuilder> values = Stream.of(new StringBuilder("start"))
        .collect(Collectors.toUnmodifiableList());
values.get(0).append("-changed"); // Thay đổi chính StringBuilder.
~~~

Không thể thêm/xóa phần tử trong `values` nhưng có thể sửa nội dung `StringBuilder`. Nếu API trả tập dữ liệu nhạy cảm, dùng giá trị immutable (ví dụ `String` hoặc record có field immutable thích hợp), hoặc tạo bản sao an toàn theo hợp đồng cụ thể.

Unmodifiable không tự động làm cho mọi thao tác trên các phần tử an toàn với nhiều thread. Không chia sẻ một object mutable giữa các thread mà không có đồng bộ phù hợp chỉ vì nó nằm trong List unmodifiable.

## 10. Dữ liệu trùng nhau, `equals` và chính sách chọn đại diện

Với `Set`, hai phần tử tương đương dựa trên `equals` được xem là một mục. Điều này khác với cách `Comparator` đánh giá thứ tự.

Ví dụ:

~~~java
record Product(String id, int version) {}

List<Product> products = List.of(
        new Product("A", 1),
        new Product("A", 2),
        new Product("A", 1)
);

Set<Product> items = products.stream()
        .collect(Collectors.toUnmodifiableSet());
// Set có Product("A",1) và Product("A",2).
~~~

Đây là đoạn minh họa trong lớp có record Java 17 và import `List`, `Set`, `Collectors`. Record mặc định so sánh cả `id` và `version`; vì vậy hai Product có cùng `id` nhưng khác `version` **không trùng** theo `equals`.

Nếu yêu cầu là "một Product cho mỗi id, ưu tiên version lớn nhất", chỉ dùng Set không đủ để mô tả:

~~~java
Map<String, Product> newestById = products.stream().collect(
        Collectors.toMap(
                Product::id,
                Function.identity(),
                BinaryOperator.maxBy(Comparator.comparingInt(Product::version))
        )
);
~~~

Đoạn này cần `Map`, `Collectors`, `Function`, `BinaryOperator`, `Comparator` và biến `products` từ ví dụ trên. `toMap` với merge function diễn đạt chính sách chọn bản ghi; sau đó có thể thu lại values thành một Set/List nếu cần. Hãy lưu ý việc lặp qua `Map.values()` cũng không tự bảo đảm thứ tự trừ khi dùng map có thứ tự phù hợp.

**Điểm cần nhớ:** `toUnmodifiableSet` có thể giữ bất kỳ đại diện nào từ các phần tử bằng nhau, không nhất thiết là phần tử gặp trước. Nếu "bản ghi đầu tiên" hoặc "bản ghi tốt nhất" quan trọng, cần diễn đạt logic chọn đại diện ở bước trước, không kỳ vọng collector đưa ra lựa chọn theo ý mình.

## 11. Song song, thứ tự và chi phí

Khi stream song song, collector được thực thi thông qua các bước thu thập một phần rồi kết hợp. `toSet()` và `toUnmodifiableSet()` là unordered collectors, do đó không thể dựa vào thứ tự chèn/duyệt kết quả. `toUnmodifiableList()` bảo toàn encounter order khi nguồn có thứ tự, dù pipeline xử lý song song.

Không suy ra rằng **unordered luôn nhanh hơn**, hoặc Set luôn hiệu quả hơn List. Chi phí phụ thuộc:

- Số phần tử, số giá trị phân biệt và chi phí `equals/hashCode`.
- Chi phí lưu trữ/tái cấu trúc của loại collection được triển khai.
- Chi phí phối hợp, kết hợp các container trung gian trong parallel stream.
- Yêu cầu duy trì encounter order và khả năng xảy ra hash collision.

Nếu yêu cầu giữ tất cả phần tử và thứ tự, chọn List. Nếu chỉ cần membership của các giá trị duy nhất, chọn Set. Nếu muốn Set hiển thị ổn định, **sắp xếp khi xuất kết quả**:

~~~java
List<String> sortedValues = uniqueSet.stream()
        .sorted()
        .toList();
~~~

Đây là đoạn minh họa với `Set<String> uniqueSet` đã có. Mã không nói rằng `uniqueSet` tự sắp xếp; chỉ tạo một List đã sắp xếp từ nội dung Set. Nếu muốn **Set có thứ tự chèn**, chọn `LinkedHashSet` rõ ràng; nếu muốn Set có thứ tự theo comparator, chọn `TreeSet` và nhận thức rằng nó có chính sách xem trùng dựa trên comparator `compare == 0`, có thể khác `equals`.

## 12. Lỗi thường gặp

### Nghĩ `toSet()` luôn trả `HashSet` mutable

Sai ở cấp hợp đồng API: không có bảo đảm loại Set hoặc khả năng sửa. Cần mutable rõ ràng: `Collectors.toCollection(HashSet::new)`. Cần giữ thứ tự chèn: `Collectors.toCollection(LinkedHashSet::new)`.

### Nghĩ `toUnmodifiableList()` tự loại trùng

Nó giữ trùng, vì là List. Muốn unique và vẫn là List có thứ tự xuất hiện đầu tiên, cần thiết kế bước loại trùng, ví dụ:

~~~java
List<String> uniqueList = source.stream()
        .distinct()
        .collect(Collectors.toUnmodifiableList());
~~~

Với `source` là List ordered, `distinct` giữ phần tử đầu tiên theo `equals`, rồi List kết quả giữ encounter order. Điều này khác `toUnmodifiableSet()`, vốn không bảo đảm thứ tự duyệt Set.

### Dựa vào thứ tự in trực tiếp một Set

~~~java
Set<String> result = source.stream().collect(Collectors.toUnmodifiableSet());
// Không cam kết: System.out.println(result) in theo thứ tự đầu vào.
~~~

Nếu thứ tự quan trọng cho báo cáo/test, hãy `result.stream().sorted().toList()` hoặc chọn cấu trúc có thứ tự xác định theo yêu cầu. Không viết bài test đối chiếu nguyên văn `Set.toString()` của một Set unordered.

### Nhầm chính sách null của collector và `Stream.toList()`

`Stream.toList()` có thể chứa `null`, nhưng `Collectors.toUnmodifiableList()` và `toUnmodifiableSet()` từ chối null. Nếu thay API vì tối ưu hay phong cách, phải kiểm tra dữ liệu nguồn và hợp đồng đầu ra.

### Nghĩ unmodifiable nghĩa là deep immutable

Không thể `add/remove/set` phần tử nhưng một `StringBuilder` hoặc object mutable bên trong có thể bị sửa. Thiết kế immutable element hoặc bản sao phòng vệ nếu cần dữ liệu bất biến sâu.

### Nghĩ Set trùng theo comparator

`toSet()` và `toUnmodifiableSet()` không nhận comparator; tính trùng phụ thuộc `equals`. `sorted(comparator)` chỉ thay thứ tự, không thay quy tắc Set xem bằng nhau.

### Cho rằng dữ liệu nguồn thay đổi đồng thời luôn an toàn

Stream pipeline không được thiết kế để tùy ý sửa nguồn trong lúc duyệt. Với parallel stream, không dùng thao tác side effect trên collection ngoài mà thiếu đồng bộ. Hãy thu thập kết quả bằng Collector thích hợp và giữ non-interference.

### Dùng lại Stream sau collect

~~~java
Stream<String> once = source.stream();
List<String> list = once.collect(Collectors.toUnmodifiableList());
// Sai: once đã được tiêu thụ.
// Set<String> set = once.collect(Collectors.toUnmodifiableSet());
~~~

Muốn hai kết quả, tạo hai Stream mới từ nguồn hoặc thiết kế phép thu thập tổng hợp khi có lý do và hợp đồng rõ ràng.

## 13. Chọn collector theo yêu cầu nghiệp vụ

| Yêu cầu | Cách viết phù hợp |
| --- | --- |
| Chỉ cần tập giá trị duy nhất, không yêu cầu thứ tự/mutability | `collect(Collectors.toSet())` |
| Muốn List không sửa được, giữ thứ tự/trùng, không có null | `collect(Collectors.toUnmodifiableList())` |
| Muốn Set không sửa được, loại trùng, không có null | `collect(Collectors.toUnmodifiableSet())` |
| Muốn List có thể thay đổi rõ ràng | `collect(Collectors.toCollection(ArrayList::new))` |
| Muốn Set có thể thay đổi rõ ràng | `collect(Collectors.toCollection(HashSet::new))` |
| Muốn Set theo thứ tự gặp từ nguồn ordered | `collect(Collectors.toCollection(LinkedHashSet::new))` |
| Muốn List unmodifiable trực tiếp và có thể chứa null | `stream.toList()` (Java 16+) |
| Muốn danh sách unique giữ thứ tự xuất hiện đầu tiên | `stream.distinct().collect(Collectors.toUnmodifiableList())` |
| Muốn chọn bản ghi đại diện theo khóa | `toMap(key, value, merge)` với chính sách rõ ràng |

**Tóm lại:** lựa chọn collector phải dựa trên **cấu trúc đích (List/Set), chính sách trùng, thứ tự, null và khả năng thay đổi**. `Collectors.toSet()` không hứa mutable; `toUnmodifiableList()` giữ trùng và encounter order nhưng từ chối null; `toUnmodifiableSet()` loại trùng, không sửa được, không cam kết thứ tự và từ chối null. Khi có yêu cầu khác, hãy dùng collector/collection tường minh thay vì dựa vào hành vi tình cờ của JDK đang chạy.