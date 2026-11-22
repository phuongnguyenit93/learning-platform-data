# Set.copyOf: thứ tự duyệt không được bảo đảm

## 1. Kiến thức trọng tâm

`Set.copyOf(Collection<? extends E> coll)` là phương thức static trên `java.util.Set`, được bổ sung từ **Java 10** và vẫn hỗ trợ trong Java hiện đại. Phương thức nhận một collection, tạo kết quả **không sửa được (unmodifiable)** chứa các phần tử phân biệt của collection đó.

**Giới hạn phải nhớ:** `Set.copyOf` **không cam kết thứ tự duyệt phần tử**, kể cả khi collection đầu vào có thứ tự xác định.

~~~java
// Đoạn minh họa bên trong method, cần import java.util.*
var source = new LinkedHashSet<>(List.of("pear", "apple", "banana"));
var copy = Set.copyOf(source);

System.out.println(copy.size());            // 3
System.out.println(copy.contains("apple")); // true

// KHÔNG được giả định dòng sau luôn in "[pear, apple, banana]":
// System.out.println(copy);
~~~

`LinkedHashSet` nguồn duyệt theo thứ tự chèn, nhưng **không có quy tắc Java bảo đảm `Set.copyOf` duyệt theo thứ tự đó**. Trên một bản JDK, kết quả có thể trông đúng với thứ tự nguồn; ở một bản JDK khác hoặc một lần chạy khác, thứ tự có thể thay đổi. Điều này không làm sai chức năng của `Set.copyOf` vì hợp đồng của nó bảo vệ **membership**, không bảo vệ **iteration order**.

Hãy phân biệt ba yêu cầu:

- **Tập phần tử:** `copy.contains("apple")` và `copy.size()` phản ánh các phần tử phân biệt; không cần biết thứ tự.
- **Thứ tự duyệt:** `iterator()`, vòng `for-each`, một số thao tác stream và `toString()` có thể quan sát thứ tự phần tử; Set copy không cam kết thứ tự.
- **Khả năng sửa:** `copy.add(...)` hoặc `copy.remove(...)` bị từ chối bằng `UnsupportedOperationException`. “Không sửa được” không đồng nghĩa “có thứ tự”.

Đây không phải API cũ đã bị thay thế. Đặc tả Javadoc Java 17 và Java 27 đều nêu rằng iteration order của unmodifiable Set là **unspecified and is subject to change**.

## 2. Hợp đồng của `Set.copyOf`: có gì và không có gì?

Chữ ký API:

~~~java
static <E> Set<E> copyOf(Collection<? extends E> coll)
~~~

Đây chỉ là **chữ ký minh họa**; một chương trình bình thường sẽ gọi `Set.copyOf(...)` chứ không tự định nghĩa dòng trên.

| Thuộc tính | Cam kết / giới hạn |
| --- | --- |
| Kiểu kết quả | `Set<E>` không sửa được |
| Thứ tự duyệt | **Không được bảo đảm** và có thể thay đổi |
| Phần tử trùng theo `equals` | Một đại diện cho mỗi nhóm bằng nhau; không có duplicate trong set |
| Nguồn có thể là `List`? | Có, vì tham số là `Collection` |
| Nguồn/element chứa `null`? | Không; ném `NullPointerException` |
| Nguồn mutable thêm hoặc xóa sau khi copy | Không thay đổi membership của kết quả đã tạo |
| Các object element mutable | Có thể chia sẻ tham chiếu; không phải deep copy |
| Mỗi lần `copyOf` chắc chắn tạo object mới? | Không; có thể tái sử dụng unmodifiable Set phù hợp |
| `Set.copyOf` có tự sắp xếp không? | Không có cam kết sắp xếp hoặc comparator |

Ví dụ không phụ thuộc thứ tự:

~~~java
var copy = Set.copyOf(List.of("C", "A", "B"));
System.out.println(copy.size());                 // 3
System.out.println(copy.contains("A"));          // true
System.out.println(copy.equals(Set.of("B", "C", "A"))); // true
~~~

`Set.equals` so sánh tập thành viên, **không so sánh thứ tự iterator**. Hai set có thứ tự duyệt khác nhau vẫn bằng nhau nếu cùng các phần tử.

### Tính bất biến và tính độc lập của snapshot

~~~java
// Minh họa trong method.
var source = new LinkedHashSet<>(List.of("A", "B"));
var copy = Set.copyOf(source);
source.add("C");

System.out.println(source.contains("C")); // true
System.out.println(copy.contains("C"));   // false
~~~

`Set.copyOf` không phải live view lên `source`. Kết quả đã ghi nhận membership tại thời điểm copy, nên việc thêm phần tử về sau vào source không phản ánh vào copy. Nhưng nếu element là một object mutable và bị sửa trạng thái qua tham chiếu khác, các giá trị quan sát trong set vẫn có thể thay đổi; nếu đổi trường chi phối `equals/hashCode` thì thậm chí có thể làm tra cứu không nhất quán.

## 3. So sánh với các lớp Set có thứ tự

Không phải **mọi** `Set` đều “ngẫu nhiên”. Hợp đồng cụ thể phụ thuộc API và implementation:

| Kiểu/cách tạo | Hợp đồng iteration order |
| --- | --- |
| `LinkedHashSet` | Thông thường theo thứ tự chèn |
| `TreeSet` | Theo natural ordering hoặc comparator |
| `HashSet` | Không bảo đảm thứ tự |
| `Set.of(...)` | Không bảo đảm thứ tự |
| `Set.copyOf(...)` | **Không bảo đảm thứ tự**, không thừa hưởng hợp đồng của nguồn |
| `Collections.unmodifiableSet(linkedHashSet)` | Là view: duyệt theo thứ tự backing LinkedHashSet |
| `Collections.unmodifiableSortedSet(treeSet)` | Là view: duyệt theo thứ tự backing SortedSet |

### Sao chép từ `LinkedHashSet`

~~~java
// Có import java.util.*.
var source = new LinkedHashSet<>(List.of("C", "A", "B"));
var copy = Set.copyOf(source);

System.out.println(new ArrayList<>(source)); // [C, A, B]
// Không khẳng định copy.toString() cũng là [C, A, B].
~~~

### Sao chép từ `TreeSet`

~~~java
var sortedSource = new TreeSet<>(List.of("C", "A", "B"));
var copy = Set.copyOf(sortedSource);

System.out.println(new ArrayList<>(sortedSource)); // [A, B, C]
System.out.println(copy.size());                    // 3
~~~

`TreeSet` nguồn được sắp xếp. Kết quả `Set.copyOf` vẫn là một Set không được cam kết duyệt theo comparator đó; nó cũng không công bố mình là `SortedSet` hay giữ comparator nguồn.

**Sai lầm phổ biến:** nghĩ rằng “copy” có nghĩa giữ lại toàn bộ tính chất của implementation nguồn. `Set.copyOf` cung cấp **bản sao unmodifiable về membership**, không phải sao chép lớp `LinkedHashSet` hoặc `TreeSet`.

## 4. Vì sao `Set.copyOf` khác `List.copyOf`?

`List.copyOf` (cũng từ Java 10) tạo danh sách không sửa được, **giữ thứ tự duyệt của collection nguồn tại thời điểm copy** và giữ tất cả lần xuất hiện trùng. `Set.copyOf` thì giữ các giá trị phân biệt và không cam kết thứ tự.

~~~java
var data = List.of("C", "A", "B", "A");

var listCopy = List.copyOf(data);
var setCopy = Set.copyOf(data);

System.out.println(listCopy);      // [C, A, B, A]
System.out.println(setCopy.size()); // 3
~~~

Dùng `listCopy.get(0)` có ý nghĩa: phần tử đầu tiên của list là `"C"`. Dùng `setCopy.iterator().next()` rồi gọi đó là phần tử đầu tiên của **dữ liệu gốc** là sai: set copy không có thứ tự được cam kết.

Nếu đầu vào là collection vốn không có thứ tự duyệt bảo đảm (như `HashSet`), `List.copyOf` vẫn ghi lại thứ tự iterator **ở lần copy**, nhưng thứ tự của chính nguồn có thể khác giữa các lần chạy. Muốn kết quả có thứ tự thực sự ổn định, phải lấy dữ liệu từ nguồn có trật tự đáng tin hoặc sắp xếp chủ động.

### Duplicate cũng khác nhau

~~~java
var source = List.of("A", "B", "A");
var setCopy = Set.copyOf(source);
var listCopy = List.copyOf(source);

System.out.println(setCopy.size());  // 2
System.out.println(listCopy.size()); // 3
~~~

`Set.copyOf` không ném lỗi do duplicate từ list: nó giữ một đại diện cho mỗi nhóm bằng nhau. Đừng nhầm với `Set.of("A", "A")`, vốn ném `IllegalArgumentException` vì đối số trực tiếp trùng nhau.

## 5. Những lệnh dễ vô tình phụ thuộc thứ tự

### 5.1. `for-each`, `iterator`

~~~java
var copied = Set.copyOf(List.of("pending", "active", "closed"));

// Lệnh dưới hợp lệ nhưng không được hứa thứ tự in:
// for (var item : copied) {
//     System.out.println(item);
// }
~~~

`for-each` lấy iterator của `copied`. Không dùng nó để xác định thứ tự ưu tiên từ tập nguồn. Tương tự, `copied.iterator().next()` chỉ lấy phần tử đầu theo iterator hiện tại, **không có nghĩa** là bản ghi được chèn đầu tiên hay giá trị nhỏ nhất.

### 5.2. `findFirst()` và kết quả từ stream

~~~java
var copied = Set.copyOf(List.of("C", "A", "B"));

// Không coi copied.stream().findFirst() là giá trị đầu tiên của list gốc.
~~~

Một stream không có encounter order được bảo đảm không thể cung cấp “phần tử đầu” có nghĩa cố định của nguồn. Nếu cần phần tử nhỏ nhất:

~~~java
var smallest = copied.stream().min(String::compareTo).orElseThrow();
System.out.println(smallest); // A
~~~

Ở đây `min` dùng comparator để chọn kết quả, độc lập thứ tự duyệt. Với set có thể rỗng, cần xử lý trường hợp `Optional` không có giá trị.

### 5.3. `toString()`, CSV, JSON, cache key

~~~java
var copied = Set.copyOf(List.of("B", "A", "C"));
String csv = String.join(",", copied); // Không được cam kết "B,A,C".
~~~

`String.join` duyệt các phần tử của `copied`. Nếu dùng chuỗi này làm cache key, báo cáo, output API hoặc snapshot test, sự khác biệt thứ tự có thể làm hệ thống khó tái hiện dù membership không thay đổi.

**Đừng viết** assert so sánh `copied.toString()` với một chuỗi theo thứ tự giả định. Hãy test membership bằng `equals`, `contains` và `size`, hoặc chuyển sang cấu trúc đã có quy tắc sắp xếp phù hợp.

### 5.4. Chuyển sang `ArrayList` sau khi đã copy không khôi phục thứ tự

~~~java
var input = List.of("C", "A", "B");
var copy = Set.copyOf(input);
var asList = new ArrayList<>(copy);
~~~

`asList` ghi lại iterator của `copy`, không khôi phục thứ tự `C, A, B` ban đầu. Muốn giữ encounter order thì phải bảo toàn nó từ trước khi tạo `Set.copyOf`, hoặc sắp xếp tường minh nếu có comparator.

## 6. Những cách tạo kết quả theo thứ tự một cách đúng đắn

### Cách A — Chỉ cần tập thành viên nhưng muốn hiển thị sắp xếp

~~~java
var copy = Set.copyOf(List.of("pear", "apple", "banana"));
var sorted = new TreeSet<>(copy);
System.out.println(sorted); // [apple, banana, pear]
~~~

`TreeSet<String>` dùng thứ tự tự nhiên của `String`. Với object tự định nghĩa, cần `Comparable` hoặc `Comparator` phù hợp. Cũng có thể:

~~~java
var sortedList = copy.stream().sorted().toList();
System.out.println(sortedList); // [apple, banana, pear]
~~~

`Stream.toList()` có từ Java 16 và trả danh sách không sửa được; `sorted()` tạo trật tự theo natural ordering ở ví dụ này. Dù đầu vào là Set không có thứ tự, kết quả đã được sort chủ động.

### Cách B — Cần unique và giữ thứ tự xuất hiện đầu tiên của List

~~~java
var source = List.of("C", "A", "C", "B", "A");
var uniqueInOrder = List.copyOf(new LinkedHashSet<>(source));

System.out.println(uniqueInOrder); // [C, A, B]
~~~

`LinkedHashSet` loại duplicate mà vẫn giữ thứ tự lần xuất hiện đầu của các giá trị phân biệt. `List.copyOf` bảo toàn iterator order của `LinkedHashSet` và trả một **List unmodifiable có thứ tự**, chứ không phải Set. Nếu API nhận list, cách này thể hiện rõ cả uniqueness lẫn order. **Không** thay bằng `Set.copyOf(new LinkedHashSet<>(source))` rồi mong thứ tự được giữ.

### Cách C — Cần kiểu Set không sửa được, vẫn theo insertion order

~~~java
Set<String> ordered = Collections.unmodifiableSet(
        new LinkedHashSet<>(List.of("C", "A", "B"))
);

System.out.println(new ArrayList<>(ordered)); // [C, A, B]
~~~

Đây là **view unmodifiable trên một LinkedHashSet mới**. Nếu không có tham chiếu khác tới backing set này để sửa, kết quả có snapshot cấu trúc độc lập với collection nguồn trước đó, cùng hợp đồng iterator order của LinkedHashSet. Lưu ý wrapper vẫn là *view* của backing set; nếu backing bị sửa thông qua tham chiếu ở nơi khác, view sẽ phản ánh thay đổi.

Không nhầm với:

~~~java
var source = new LinkedHashSet<>(List.of("C", "A", "B"));
var liveView = Collections.unmodifiableSet(source);
source.add("D");

System.out.println(new ArrayList<>(liveView)); // [C, A, B, D]
~~~

Ở ví dụ thứ hai, wrapper nhìn trực tiếp vào mutable source, vì thế không phải snapshot độc lập.

### Cách D — Cần SortedSet với comparator

~~~java
var source = new TreeSet<>(List.of("C", "A", "B"));
var sortedSnapshot = Collections.unmodifiableSortedSet(
        new TreeSet<>(source)
);

System.out.println(new ArrayList<>(sortedSnapshot)); // [A, B, C]
~~~

`TreeSet` có trật tự so sánh, còn wrapper ngăn sửa qua kết quả. Nếu ứng dụng cần comparator đặc biệt, chọn và duy trì comparator đó; khi sao chép, bảo đảm constructor/cách tạo thực sự dùng comparator theo yêu cầu.

| Yêu cầu | Lựa chọn |
| --- | --- |
| Unmodifiable, chỉ quan tâm membership | `Set.copyOf(source)` |
| Unmodifiable, giữ thứ tự và duplicate | `List.copyOf(source)` nếu source có iterator order đáng tin |
| Unique, giữ thứ tự xuất hiện đầu tiên | `List.copyOf(new LinkedHashSet<>(source))` |
| Unmodifiable Set, giữ insertion order | `Collections.unmodifiableSet(new LinkedHashSet<>(source))` |
| Set có thứ tự so sánh | `Collections.unmodifiableSortedSet(new TreeSet<>(source))` |
| Danh sách giá trị sort từ Set | `set.stream().sorted().toList()` |

## 7. Chương trình hoàn chỉnh Java 17+ và stdout đáng tin

Ví dụ sau không in trực tiếp thứ tự của `Set.copyOf`. Nó kiểm tra membership, snapshot cấu trúc, live view, duplicate, null và các kết quả được sắp xếp hoặc bảo toàn insertion order **có chủ đích**.

Lưu đúng tên file **`SetCopyOfIterationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SetCopyOfIterationDemo {
    public static void main(String[] args) {
        var source = new LinkedHashSet<>(
                List.of("pear", "apple", "banana")
        );

        var copy = Set.copyOf(source);

        System.out.println("sourceOrder=" + new ArrayList<>(source));
        System.out.println("copySize=" + copy.size());
        System.out.println("copyHasApple=" + copy.contains("apple"));
        System.out.println("equalAsSet="
                + copy.equals(Set.of("banana", "pear", "apple")));
        System.out.println("copySorted=" + new TreeSet<>(copy));

        var orderedList = List.copyOf(source);
        Set<String> orderedSetSnapshot = Collections.unmodifiableSet(
                new LinkedHashSet<>(source)
        );
        Set<String> liveView = Collections.unmodifiableSet(source);

        source.add("date");

        System.out.println("sourceAfterAdd=" + new ArrayList<>(source));
        System.out.println("copyHasDate=" + copy.contains("date"));
        System.out.println("liveViewHasDate=" + liveView.contains("date"));
        System.out.println("orderedListAfterAdd=" + orderedList);
        System.out.println("orderedSetAfterAdd="
                + new ArrayList<>(orderedSetSnapshot));

        var unique = Set.copyOf(List.of("x", "y", "x"));
        System.out.println("duplicatesSize=" + unique.size());
        System.out.println("duplicatesHaveX=" + unique.contains("x"));

        try {
            copy.add("new");
        } catch (UnsupportedOperationException expected) {
            System.out.println("copyImmutable=true");
        }

        try {
            Set.copyOf(Arrays.asList("ok", null));
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn hỗ trợ `--release 17`:

~~~bash
javac --release 17 SetCopyOfIterationDemo.java
java SetCopyOfIterationDemo
~~~

**Stdout chính xác:**

~~~text
sourceOrder=[pear, apple, banana]
copySize=3
copyHasApple=true
equalAsSet=true
copySorted=[apple, banana, pear]
sourceAfterAdd=[pear, apple, banana, date]
copyHasDate=false
liveViewHasDate=true
orderedListAfterAdd=[pear, apple, banana]
orderedSetAfterAdd=[pear, apple, banana]
duplicatesSize=2
duplicatesHaveX=true
copyImmutable=true
nullRejected=true
~~~

### Vì sao các dòng đều xác định?

1. `source` là `LinkedHashSet`, nên `new ArrayList<>(source)` ban đầu có thứ tự `pear, apple, banana`.
2. Kết quả `copy` có ba phần tử; `copy.contains("apple")` là true, và `Set.equals` so sánh membership nên không phụ thuộc iteration order.
3. `new TreeSet<>(copy)` chủ động sort theo `String`, tạo `[apple, banana, pear]`.
4. `orderedList` và `orderedSetSnapshot` được tạo **trước** khi thêm `"date"` vào source; chúng giữ cấu trúc ban đầu.
5. `liveView` đọc trực tiếp source, vì thế thấy `"date"`; `copy` và những snapshot không thấy phần tử thêm sau khi copy.
6. `Set.copyOf(List.of("x", "y", "x"))` gộp duplicate; membership của `x` vẫn là true và kích thước là 2.
7. Gọi `copy.add("new")` ném `UnsupportedOperationException`. Nguồn chứa null làm `Set.copyOf` ném `NullPointerException`; hai ngoại lệ được bắt để chương trình chạy hết.

Không có một dòng stdout nào phụ thuộc vào thứ tự ngẫu nhiên của unmodifiable Set.

## 8. Cẩn trọng với duplicate, null và object mutable

### Duplicate theo `equals`

~~~java
var source = List.of("A", "B", "A");
var copy = Set.copyOf(source);

System.out.println(copy.size());        // 2
System.out.println(copy.contains("B")); // true
~~~

Nếu nguồn có **nhiều object khác nhau nhưng bằng nhau theo `equals`**, `Set.copyOf` chỉ giữ một đại diện cho mỗi nhóm trùng, và **không cam kết chọn object đầu tiên hay cuối cùng**. Nếu nghiệp vụ muốn “giữ bản ghi sớm nhất” hoặc “giữ bản ghi mới nhất”, phải thực hiện lựa chọn đó chủ động trong thuật toán trước khi trả kết quả.

`Set.of("A", "A")` là API khác: nó ném `IllegalArgumentException` khi có duplicate argument, chứ không loại trùng như `Set.copyOf`.

### Null

~~~java
// Các lời gọi minh họa lỗi runtime:
Set.copyOf(null); // NullPointerException
Set.copyOf(java.util.Arrays.asList("A", null)); // NullPointerException
~~~

`Set.copyOf` từ chối cả nguồn null và phần tử null. Không kết luận rằng phần tử null sẽ bị lọc giống duplicate. Nếu input có khả năng chứa null, cần chính sách xử lý đầu vào rõ ràng.

### Element mutable

Giữ một object mutable trong `Set.copyOf` không biến object thành immutable. Nếu thay trạng thái của object sau khi copy, đối tượng vẫn là object đó. Đặc biệt, nếu sửa trường ảnh hưởng `equals/hashCode` của phần tử được dùng trong set, những thao tác tra cứu theo hash có thể không còn ổn định.

Đối với key, ID hoặc value object dùng trong set, nên ưu tiên kiểu có equality bất biến hoặc sao chép/chuẩn hóa phần tử nếu yêu cầu snapshot bất biến sâu. Đây là giới hạn của **shallow copy**, không phải giới hạn riêng về iteration order.

### Identity và concurrency

- Không dùng `copy == source` hoặc `copy != source` làm hợp đồng: `Set.copyOf` có thể tái sử dụng unmodifiable input phù hợp.
- Unmodifiable set không tự tạo một snapshot giao dịch an toàn khi collection nguồn đang bị **sửa đồng thời** từ thread khác; cần đồng bộ phù hợp khi chốt dữ liệu.
- Không dùng identity của collection factory trả về cho đồng bộ hóa hay quy tắc nghiệp vụ. Các unmodifiable collection factory được đặc tả theo hướng value-based.

## 9. Vì sao có thể thấy thứ tự khác giữa các lần chạy?

Tài liệu **Creating Unmodifiable Lists, Sets, and Maps** của Oracle có mục “Randomized Iteration Order” giải thích: việc unmodifiable Set/Map có thứ tự duyệt thay đổi có chủ đích nhằm giúp người lập trình phát hiện phụ thuộc sai vào order.

Cần diễn đạt đúng:

- Có thể thấy các thứ tự khác nhau khi khởi động JVM nhiều lần hoặc thay đổi bản JDK.
- **Không có quy tắc** rằng thứ tự bắt buộc đổi ở *mọi* lần chạy. Hai lần giống nhau không tạo thành cam kết.
- Không suy từ hash code, implementation private hoặc hệ điều hành rằng `Set.copyOf` “vốn luôn duyệt theo thứ tự X”.
- Không đánh đồng mọi Set: `LinkedHashSet` có iteration order theo chèn, `TreeSet` theo comparator, còn `Set.copyOf` thì không bảo đảm.
- Đặc tả về order mới là căn cứ viết API và test, không phải hình thức `toString()` quan sát được trên một máy.

Ví dụ nếu muốn CSV có thứ tự:

~~~java
var data = List.of("pending", "active", "closed");

String byEncounter = String.join(
        ",", new LinkedHashSet<>(data)
);
String alphabetical = String.join(
        ",", new TreeSet<>(data)
);

System.out.println(byEncounter);  // pending,active,closed
System.out.println(alphabetical); // active,closed,pending
~~~

Ở đây, **LinkedHashSet** hoặc **TreeSet** quyết định thứ tự. Không phụ thuộc `String.join(",", Set.copyOf(data))`, vì điều đó không có hợp đồng thứ tự phù hợp cho kết quả cần ổn định.

## 10. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Giả định `Set.copyOf(linkedHashSet)` luôn giữ insertion order | Hợp đồng Set copy không hứa điều đó | Dùng `List.copyOf(new LinkedHashSet<>(source))` hoặc unmodifiable LinkedHashSet snapshot |
| Giả định `Set.copyOf(treeSet)` giữ sort order | Kết quả không được công bố là SortedSet | Dùng TreeSet/sorted wrapper hoặc sort tường minh |
| So sánh `set.toString()` với một thứ tự cụ thể | `toString()` duyệt theo iterator | So sánh membership bằng `Set.equals` |
| Dùng `set.iterator().next()` làm phần tử được chèn đầu tiên | Không có first theo hợp đồng Set copy | Duy trì list/ordered set từ đầu |
| Dùng `new ArrayList<>(Set.copyOf(source))` để giữ thứ tự nguồn | Chỉ sao chép iterator của set copy | Giữ order trước, hoặc sắp xếp sau theo comparator |
| Dùng `Set.copyOf` và mong giữ duplicate | Set chỉ có các giá trị phân biệt | Dùng List khi số lần xuất hiện có ý nghĩa |
| Cho rằng `Set.copyOf` ném `IllegalArgumentException` do duplicate | Quy tắc này thuộc `Set.of` | `Set.copyOf` gộp duplicate |
| Cho rằng Set copy chấp nhận null | `Set.copyOf` từ chối null | Xử lý null trước khi copy |
| Cho rằng `Collections.unmodifiableSet(source)` là snapshot | Nó là view lên source; sửa nguồn vẫn thấy trong view | Sao chép backing set trước khi bọc |
| Cho rằng unmodifiable nghĩa object element immutable | Không tự sao chép sâu phần tử | Dùng immutable element/defensive copy khi cần |

## 11. Tự đánh giá

**Câu 1.** `Set.copyOf(new LinkedHashSet<>(List.of("B", "A")))` có bảo đảm iterator trả B trước A?

**Đáp án:** Không. `LinkedHashSet` có thứ tự chèn, nhưng `Set.copyOf` không giữ cam kết đó.

**Câu 2.** Có thể test `Set.copyOf(List.of("B", "A"))` bằng `equals(Set.of("A", "B"))` không?

**Đáp án:** Có. `Set.equals` không phụ thuộc thứ tự, và hai set có cùng membership.

**Câu 3.** `new ArrayList<>(Set.copyOf(list))` có khôi phục thứ tự ban đầu của list không?

**Đáp án:** Không. Nó chỉ ghi thứ tự iterator của set copy, vốn không được cam kết.

**Câu 4.** Cách nào vừa loại trùng vừa giữ lần xuất hiện đầu tiên của một List nguồn?

**Đáp án:** `List.copyOf(new LinkedHashSet<>(sourceList))`, khi input không có null và đã có thứ tự đáng tin.

**Câu 5.** Muốn Set unmodifiable với insertion order, có thể dùng gì?

**Đáp án:** `Collections.unmodifiableSet(new LinkedHashSet<>(source))` khi backing copy không bị rò rỉ; khác với `Collections.unmodifiableSet(source)` nếu source vẫn mutable ở nơi khác.

**Câu 6.** `Set.copyOf(List.of("A", "A", "B"))` có lỗi duplicate không?

**Đáp án:** Không. Kết quả có hai giá trị phân biệt. `Set.of("A", "A", "B")` mới ném `IllegalArgumentException`.

**Câu 7.** `Set.copyOf` có bảo đảm thứ tự thay đổi ở mọi lần JVM khởi động?

**Đáp án:** Không. API chỉ nói iteration order unspecified và subject to change. Không có cam kết order phải đổi theo lịch nào.

**Câu 8.** `Set.copyOf` có cho phép phần tử null không?

**Đáp án:** Không. Nguồn chứa null hoặc chính nguồn là null dẫn đến `NullPointerException`.

## 12. Nguồn chính thức đang áp dụng

- [Oracle Java SE 27 — Set](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): đặc điểm unmodifiable Set, iteration order “unspecified and is subject to change” và API `Set.copyOf`.
- [Oracle Java SE 17 — Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): hợp đồng và mốc Since: 10.
- [Oracle JDK 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): tạo unmodifiable copies và giải thích randomized iteration order.
- [Oracle Java SE 17 — LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html): insertion order.
- [Oracle Java SE 17 — TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html): sorted set và comparator.
- [Oracle Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): bảo toàn iteration order đầu vào thành list không sửa được.
- [Oracle Java SE 17 — Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)): unmodifiable view trên backing set.
- [Dev.java — Collection Factory Methods](https://dev.java/learn/api/collections-and-streams/collections-framework/factory-methods/): cách dùng factory hiện hành.

**Ghi nhớ:** `Set.copyOf` chỉ cam kết một **tập phần tử phân biệt, không sửa được**; nó **không hứa thứ tự duyệt**. Khi bài toán cần thứ tự cố định, hãy chọn đúng `LinkedHashSet`, `TreeSet`, một `List` ghi nhận order hoặc thao tác sort tường minh.