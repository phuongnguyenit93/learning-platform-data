# So sánh tính sửa đổi được, thứ tự và chính sách null của kết quả

## 1. Cùng một pipeline, nhưng Collection đầu ra có thể mang hợp đồng khác nhau

Trong chương **Thu thập thành Collection** của **JAVA_STREAM_API**, sau các bước `filter`, `map` hay `flatMap`, ta thường muốn materialize dữ liệu thành `List`, `Set` hoặc `Map` để dùng tiếp. Lựa chọn terminal operation không chỉ quyết định **kiểu dữ liệu**, mà còn ảnh hưởng đến ba hợp đồng có ý nghĩa trực tiếp với chương trình:

1. **Tính sửa đổi được (mutability):** Collection có cho phép `add`, `remove`, `set` hoặc `put` sau khi thu thập không?
2. **Thứ tự (ordering):** Collection có duy trì encounter order của Stream, thứ tự chèn, thứ tự sắp xếp hay không bảo đảm thứ tự duyệt?
3. **Chính sách `null`:** Collection hoặc collector có chấp nhận phần tử `null`, khóa `null`, giá trị `null` hay ném ngoại lệ?

Ví dụ hai câu lệnh có thể tạo các danh sách trông giống nhau, nhưng hợp đồng sử dụng về sau khác nhau:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> immutableResult = List.of("An", "Bình")
    .stream()
    .toList();

List<String> unspecifiedResult = List.of("An", "Bình")
    .stream()
    .collect(Collectors.toList());
~~~

Danh sách đầu từ `Stream.toList()` **không sửa đổi được** theo đặc tả. Với `Collectors.toList()`, API **không cam kết** kiểu triển khai, tính sửa đổi được, tính tuần tự hóa hoặc an toàn luồng. Nhiều JDK hiện nay trả `ArrayList` có thể sửa, nhưng viết code phụ thuộc vào đặc điểm đó là dựa vào implementation detail.

~~~text
                 Stream<T> sau filter / map / ...
                               │
                 Chọn cách materialize dữ liệu
                               │
           ┌───────────────────┼────────────────────┐
           ▼                   ▼                    ▼
       Danh sách             Tập hợp               Ánh xạ
        (List)                (Set)                 (Map)
           │                   │                    │
       - Giữ trùng?        - Loại trùng         - Khóa trùng?
       - Thứ tự?           - Thứ tự?           - Thứ tự key?
       - Sửa được?         - Sửa được?         - Sửa được?
       - Cho null?         - Cho null?         - Key/value null?
~~~

**Nguyên tắc chính:** Chọn collector dựa trên **hợp đồng cần bảo đảm**, không dựa vào việc một JDK cụ thể tình cờ trả về `ArrayList` hay `HashMap`.

Các ví dụ dùng **Java 17+**. `Stream.toList()` xuất hiện từ Java 16; `Collectors.toUnmodifiableList/Set/Map` và `List.copyOf/Set.copyOf/Map.copyOf` có từ Java 10. Những collector cơ bản như `toList`, `toSet`, `toMap`, `toCollection` có từ Java 8.

## 2. Bảng đối chiếu nhanh các cách thu thập phổ biến

Bảng dưới mô tả **những điều code được phép dựa vào**, khác với chi tiết triển khai thường thấy:

| Cách thu thập | Sửa đổi Collection sau khi tạo | Thứ tự duyệt kết quả | Chính sách `null` |
| --- | --- | --- | --- |
| `stream.toList()` | **Không**: danh sách không sửa đổi được | Giữ encounter order nếu Stream có thứ tự | Có thể chứa phần tử `null` |
| `collect(Collectors.toList())` | **Không cam kết** | Theo encounter order nếu Stream có thứ tự | Không có cam kết riêng rõ ràng trong mô tả collector; JDK thông dụng giữ được `null` |
| `collect(Collectors.toUnmodifiableList())` | **Không** | Giữ encounter order nếu Stream có thứ tự | **Cấm `null`**; ném `NullPointerException` |
| `collect(Collectors.toCollection(ArrayList::new))` | **Có**: `ArrayList` cụ thể | Giữ encounter order nếu Stream có thứ tự | `ArrayList` cho phép `null` |
| `collect(Collectors.toSet())` | **Không cam kết** | **Không cam kết** thứ tự duyệt | Không có cam kết riêng về `null`; tránh phụ thuộc chi tiết triển khai |
| `collect(Collectors.toUnmodifiableSet())` | **Không** | **Không cam kết** thứ tự duyệt | **Cấm `null`**; ném `NullPointerException` |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | **Có**: `LinkedHashSet` | Theo thứ tự chèn; với nguồn ordered là thứ tự lần xuất hiện đầu của mỗi giá trị | Cho phép một phần tử `null` |
| `collect(Collectors.toCollection(TreeSet::new))` | **Có**: `TreeSet` | Thứ tự so sánh tự nhiên (hoặc comparator do supplier cung cấp) | `TreeSet` sắp xếp tự nhiên không chấp nhận `null` |

Đối với `Map`, cần phân biệt khóa và giá trị. `toMap` không bảo đảm kiểu Map, tính sửa đổi được hay thứ tự; `toUnmodifiableMap` cho Map không sửa đổi được, cấm khóa hoặc giá trị `null`. Muốn một `LinkedHashMap` có thứ tự và sửa được, truyền supplier cho overload bốn tham số của `Collectors.toMap`.

**Hai cảnh báo khi đọc bảng:** (1) “Không cam kết sửa đổi được” khác với “không sửa đổi được”; (2) với `Set`, thứ tự *in ra khi thử chạy* không tạo thành bảo đảm thứ tự của API.

## 3. Tính sửa đổi được: toList, toUnmodifiableList và toCollection

### 3.1. `Stream.toList()` trả List không sửa đổi được

~~~java
import java.util.List;
import java.util.stream.Stream;

public class StreamToListDemo {
    public static void main(String[] args) {
        List<String> names = Stream.of("An", "Bình", "Chi")
            .toList();

        System.out.println(names); // [An, Bình, Chi]

        // names.add("Dung");      // UnsupportedOperationException
        // names.remove("An");     // UnsupportedOperationException
        // names.set(0, "Khác");   // UnsupportedOperationException
    }
}
~~~

Theo hợp đồng, lời gọi phương thức thay đổi danh sách sẽ ném `UnsupportedOperationException`. `Stream.toList()` không cam kết loại implementation, `Serializable` hay danh tính đối tượng; kết quả có thể là đối tượng dựa trên giá trị (*value-based*), nên tránh đồng bộ bằng khóa trên chính danh sách hoặc dựa vào `==` để so sánh hai kết quả.

“Không sửa đổi được” áp dụng cho **cấu trúc Collection**, không ngăn ta thay đổi trạng thái của **phần tử mutable** nằm bên trong; sẽ có ví dụ ở mục 10.

### 3.2. `Collectors.toList()` không có bảo đảm về mutability

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> collected = Stream.of("An", "Bình")
    .collect(Collectors.toList());

// Không viết code nghiệp vụ cần bảo đảm collected.add("Chi") hoạt động.
// Đặc tả của Collectors.toList() không hứa điều đó.
~~~

Trên một bản JDK hiện tại, việc gọi `add` thường hoạt động vì collector sử dụng một `ArrayList`. Kết quả này không phải hợp đồng API. Nếu yêu cầu là **danh sách có thể sửa**, hãy chọn `toCollection` với supplier rõ ràng.

~~~java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> names = Stream.of("An", "Bình")
    .collect(Collectors.toCollection(ArrayList::new));

names.add("Chi");
names.remove("An");
names.set(0, "Bình mới");

System.out.println(names); // [Bình mới, Chi]
~~~

`toCollection(ArrayList::new)` làm rõ cả kiểu container lẫn khả năng sửa đổi. Truyền supplier khác nếu cần cấu trúc dữ liệu khác, ví dụ `LinkedList::new` hoặc `LinkedHashSet::new`.

### 3.3. `Collectors.toUnmodifiableList()` cũng không cho sửa

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình")
    .collect(Collectors.toUnmodifiableList());

// names.add("Chi"); // UnsupportedOperationException
~~~

Khi không cần sửa kết quả và biết chắc phần tử không có `null`, cả `Stream.toList()` và `Collectors.toUnmodifiableList()` đều là lựa chọn phù hợp. Tuy nhiên, chúng **khác nhau ở chính sách null**, và `Stream.toList()` thường ngắn gọn hơn khi không cần collector đặc biệt.

### 3.4. Tại sao không thể chỉ nhìn kiểu trả về List?

Giao diện `List<E>` bao gồm các phương thức sửa đổi **tùy chọn**. Một biến có kiểu `List<String>` có thể trỏ tới `ArrayList` có thể sửa, hoặc danh sách không sửa đổi được. Trình biên dịch không thể suy ra chỉ từ kiểu `List` rằng `add` sẽ thành công. Hợp đồng phải đến từ cách tạo danh sách và tài liệu API.

## 4. Chính sách null của List: khác biệt dễ gây lỗi runtime

`null` có thể xuất hiện khi API cũ trả giá trị vắng mặt, khi map dữ liệu chưa đầy đủ hoặc khi callback của `map` trả về `null`.

### 4.1. `Stream.toList()` có thể chứa null

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("A", null, "B")
    .toList();

System.out.println(values); // [A, null, B]
System.out.println(values.get(1) == null); // true
~~~

Danh sách vẫn **không sửa đổi được**, mặc dù bên trong có phần tử `null`. “Không sửa đổi được” và “không cho null” là **hai thuộc tính độc lập**.

### 4.2. `Collectors.toUnmodifiableList()` cấm null

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Phát sinh NullPointerException trong terminal collect:
List<String> invalid = Stream.of("A", null, "B")
    .collect(Collectors.toUnmodifiableList());
~~~

Collector này ném `NullPointerException` nếu có phần tử `null`. Đây là hành vi theo hợp đồng, khác với `Stream.toList()`.

Nếu yêu cầu là **bỏ phần tử null và trả một danh sách không sửa đổi được**:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> cleaned = Stream.of("A", null, "B")
    .filter(Objects::nonNull)
    .collect(Collectors.toUnmodifiableList());

System.out.println(cleaned); // [A, B]
~~~

Hoặc có thể dùng `filter(Objects::nonNull).toList()` nếu chính sách đầu ra không yêu cầu collector `toUnmodifiableList`.

### 4.3. `List.of` và `List.copyOf` cấm null

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> withNull = Stream.of("A", null).toList();

// List.copyOf(withNull); // NullPointerException.
// List.of("A", null);    // NullPointerException.
~~~

Vì vậy, nếu chọn một phương thức chuyển đổi không sửa đổi được bằng `List.copyOf`, cần xử lý `null` **trước** khi chuyển.

### 4.4. `Collectors.toList()` với null có đáng dựa vào không?

Nhiều JDK hiện tại tích lũy `Collectors.toList()` vào `ArrayList` và chấp nhận `null`. Tuy nhiên, tài liệu collector không cam kết kiểu List hay một chính sách null riêng theo cách `Collectors.toUnmodifiableList()` tuyên bố rõ ràng. Với dữ liệu có null là một yêu cầu nghiệp vụ, hãy thể hiện chính sách rõ: `toCollection(ArrayList::new)` nếu muốn chứa null trong một ArrayList mutable, `Stream.toList()` nếu cần List không sửa đổi được nhưng có thể chứa null, hoặc lọc/chuyển null trước khi dùng collector cấm null.

## 5. Encounter order: thứ tự nguồn khác thứ tự duyệt Collection

**Encounter order** là thứ tự mà Stream phải tôn trọng nếu nguồn và pipeline có thứ tự. Ví dụ `List.stream()` có thứ tự phần tử của List; `HashSet.stream()` không cam kết encounter order.

### 5.1. List từ Stream ordered giữ encounter order

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> names = List.of("Chi", "An", "Bình");

List<String> a = names.stream().toList();

List<String> b = names.stream()
    .collect(Collectors.toList());

List<String> c = names.stream()
    .collect(Collectors.toUnmodifiableList());

System.out.println(a); // [Chi, An, Bình]
System.out.println(b); // [Chi, An, Bình]
System.out.println(c); // [Chi, An, Bình]
~~~

`toList()` bảo toàn encounter order nếu có. `Collectors.toList()` và `toUnmodifiableList()` là những collector có thứ tự; với nguồn ordered, chúng cũng tích lũy theo encounter order, kể cả khi terminal chạy trên parallel stream.

### 5.2. `parallel()` không tự xóa encounter order

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 5)
    .parallel()
    .boxed()
    .toList();

System.out.println(values); // [1, 2, 3, 4, 5]
~~~

Pipeline có thể xử lý các phần tử trên nhiều worker khác nhau, nhưng kết quả của terminal `toList()` phải giữ encounter order khi nguồn có thứ tự.

Ngược lại, `forEach` trên parallel stream không cam kết thứ tự **thực thi action**. Không tự tạo danh sách kết quả bằng cách `parallelStream().forEach(shared::add)` với `ArrayList` dùng chung: hành vi vừa không thread-safe vừa làm mất cơ chế gom kết quả đúng của Stream API.

### 5.3. `unordered()` cho phép bỏ ràng buộc

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> values = IntStream.rangeClosed(1, 5)
    .parallel()
    .unordered()
    .boxed()
    .toList();

// Có thể vẫn là [1, 2, 3, 4, 5], nhưng không còn cam kết thứ tự đó.
~~~

`unordered()` không phải phép trộn ngẫu nhiên; nó loại bỏ ràng buộc encounter order. Khi cần danh sách luôn theo thứ tự cố định, dùng nguồn có thứ tự hoặc `sorted(...)` với comparator đủ phân biệt các phần tử.

### 5.4. Đừng lấy thứ tự in ra một lần làm hợp đồng

Một `HashSet` hoặc `HashMap` có thể cho cùng thứ tự duyệt trên vài lần chạy, nhưng thứ tự đó không được bảo đảm. Trong kiểm thử, so sánh theo cấu trúc thích hợp: nếu thứ tự có ý nghĩa, dùng List/LinkedHashSet/LinkedHashMap hoặc sorted collection; nếu không, so sánh theo tập phần tử.

## 6. Thu thập thành Set: loại trùng, thứ tự và null

`Set` loại bỏ phần tử trùng theo quy tắc bằng nhau của loại Set tương ứng. Khi chuyển từ Stream sang Set, ta đổi cả **chính sách giữ phần tử trùng** lẫn có thể đổi thứ tự duyệt kết quả.

### 6.1. `Collectors.toSet()` không cam kết thứ tự hay mutability

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

List<String> source = List.of("B", "A", "B", "C");

Set<String> unique = source.stream()
    .collect(Collectors.toSet());

System.out.println(unique.size()); // 3
System.out.println(unique.containsAll(List.of("A", "B", "C"))); // true
~~~

Không viết kiểm thử đòi `unique.toString().equals("[B, A, C]")` hoặc `unique.add("D")` phải hoạt động: `toSet()` không cam kết thứ tự duyệt, kiểu Set hay tính sửa đổi được.

### 6.2. `toUnmodifiableSet()` không sửa được và cấm null

~~~java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Set<String> unique = Stream.of("B", "A", "B", "C")
    .collect(Collectors.toUnmodifiableSet());

System.out.println(unique.size()); // 3

// unique.add("D"); // UnsupportedOperationException
// Stream.of("A", null).collect(Collectors.toUnmodifiableSet());
//                              ^ NullPointerException
~~~

Khi có nhiều phần tử **bằng nhau** theo `equals`, collector có thể giữ **bất kỳ đại diện nào** trong nhóm đó; không dựa vào việc luôn giữ object xuất hiện đầu tiên. Thứ tự duyệt Set trả về cũng không được bảo đảm.

### 6.3. `LinkedHashSet` cho tập hợp có thứ tự chèn

~~~java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.stream.Collectors;

LinkedHashSet<String> uniqueInOrder = List.of("B", "A", "B", "C")
    .stream()
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(uniqueInOrder); // [B, A, C]

uniqueInOrder.add("D"); // Có thể sửa.
~~~

Với nguồn có encounter order, lần xuất hiện đầu tiên của mỗi giá trị xác định thứ tự chèn vào `LinkedHashSet`. Tuy nhiên, nếu nguồn đã `unordered()`, collection này chỉ giữ **thứ tự nhận/chèn thực tế**; nó không thể tái tạo thứ tự gốc đã bỏ.

`LinkedHashSet` cho phép một phần tử `null`, vì vậy có thể dùng nếu chính sách nghiệp vụ yêu cầu “giữ một giá trị rỗng” trong tập kết quả.

### 6.4. `TreeSet` thiết lập thứ tự theo comparator

~~~java
import java.util.TreeSet;
import java.util.List;
import java.util.stream.Collectors;

TreeSet<Integer> sortedUnique = List.of(5, 2, 5, 1, 3)
    .stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(sortedUnique); // [1, 2, 3, 5]
~~~

`TreeSet` có thể sửa được và duyệt theo thứ tự so sánh. Nó loại phần tử khi comparator coi chúng tương đương (`compare(a,b) == 0`), ngay cả khi `equals` của hai phần tử khác nhau; vì vậy nên bảo đảm comparator phù hợp với quy tắc bằng nhau theo mục tiêu nghiệp vụ. `TreeSet` dùng natural ordering không cho phép null.

Nếu chỉ cần một List không sửa đổi được theo thứ tự, có thể dùng `distinct().sorted().toList()`, không nhất thiết phải tạo TreeSet.

## 7. Thu thập thành Map: ba loại hợp đồng cần rõ ràng

`Map<K,V>` thêm hai vấn đề: **khóa trùng** và **null ở khóa/giá trị**. Một collector có thể chọn chính sách khóa trùng, trong khi Map trả về có chính sách thứ tự hoặc khả năng sửa đổi khác với List hay Set.

### 7.1. `toMap` mặc định từ chối khóa trùng

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record User(int id, String name) {}

List<User> users = List.of(
    new User(1, "An"),
    new User(2, "Bình")
);

Map<Integer, String> byId = users.stream()
    .collect(Collectors.toMap(User::id, User::name));

System.out.println(byId.get(1)); // An
~~~

Nếu có hai phần tử cùng `id`, overload hai tham số của `toMap` sẽ ném `IllegalStateException`. Phải xác định chính sách gộp hoặc chọn khóa thực sự duy nhất; không dựa vào “giá trị cuối tự ghi đè”.

~~~java
List<User> duplicated = List.of(
    new User(1, "An"),
    new User(1, "An cập nhật")
);

// Chọn dữ liệu xuất hiện sau theo thứ tự gặp:
Map<Integer, String> lastWins = duplicated.stream()
    .collect(Collectors.toMap(
        User::id,
        User::name,
        (oldValue, newValue) -> newValue
    ));
~~~

Với parallel stream có encounter order, collector có thể kết hợp các nhánh nhưng vẫn phải tuân thủ ngữ nghĩa tương ứng của một collector ordered; dù vậy, khi “mới nhất” mang nghĩa **thời gian nghiệp vụ**, hãy so sánh timestamp hoặc phiên bản một cách tường minh, không mặc định rằng thứ tự stream phản ánh bản ghi mới nhất.

### 7.2. `toMap` không cam kết Map trả về sửa được hoặc có thứ tự

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, String> orderedById = users.stream()
    .collect(Collectors.toMap(
        User::id,
        User::name,
        (left, right) -> left,
        LinkedHashMap::new
    ));

System.out.println(orderedById); // {1=An, 2=Bình}
orderedById.put(3, "Chi"); // Có thể sửa.
~~~

Overload bốn tham số cho phép chọn Map cụ thể. `LinkedHashMap` dùng thứ tự chèn; với nguồn ordered, thứ tự chèn phản ánh lần xuất hiện đầu của khóa trong pipeline. Muốn Map có **thứ tự theo khóa** thì chọn `TreeMap::new` với kiểu khóa so sánh được hoặc supplier kèm comparator phù hợp.

### 7.3. `toUnmodifiableMap` tạo Map không sửa được

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, String> immutableById = users.stream()
    .collect(Collectors.toUnmodifiableMap(
        User::id,
        User::name
    ));

// immutableById.put(3, "Chi"); // UnsupportedOperationException
~~~

`toUnmodifiableMap` cấm `null` ở **cả khóa lẫn giá trị**. Nó cũng ném `IllegalStateException` nếu có khóa trùng trong overload hai tham số; có overload ba tham số nhận merge function để xác định cách giải quyết trùng khóa. Không dựa vào thứ tự duyệt của Map mà collector trả về.

### 7.4. Khóa và giá trị null trong Map: xử lý trước terminal

Không nên thiết kế pipeline phụ thuộc vào việc `Collectors.toMap` có chấp nhận khóa `null` hay giá trị `null` trong một bản JDK cụ thể. API không đưa ra bảo đảm chung về một Map hỗ trợ cả hai; một số tổ hợp ném `NullPointerException` khi thu thập.

Một cách rõ ràng là lọc dữ liệu không đầy đủ trước khi tạo Map:

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

record Entry(String key, String value) {}

List<Entry> raw = List.of(
    new Entry("A", "Alpha"),
    new Entry(null, "Không có khóa"),
    new Entry("B", null)
);

Map<String, String> safe = raw.stream()
    .filter(entry -> entry.key() != null && entry.value() != null)
    .collect(Collectors.toUnmodifiableMap(
        Entry::key,
        Entry::value
    ));

System.out.println(safe); // {A=Alpha}
~~~

Nếu null có ý nghĩa nghiệp vụ (ví dụ “giá trị chưa được ghi nhận”), hãy chọn kiểu dữ liệu thể hiện trạng thái này rõ ràng, như một record kết quả có trường trạng thái, thay vì âm thầm bỏ bản ghi hoặc dựa vào chính sách null của HashMap.

## 8. `groupingBy`, thứ tự Map và thứ tự danh sách trong từng nhóm

`groupingBy` là collector phổ biến khi một phần tử được đưa vào nhóm theo khóa. Collection trả về thường là một Map, nên phải xem xét đồng thời **thứ tự khóa** và **thứ tự phần tử của mỗi nhóm**.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(String customer, int quantity) {}

List<Order> orders = List.of(
    new Order("An", 2),
    new Order("Bình", 1),
    new Order("An", 3)
);

Map<String, List<Order>> grouped = orders.stream()
    .collect(Collectors.groupingBy(Order::customer));
~~~

`Collectors.groupingBy` dạng mặc định **không cam kết** kiểu Map, mutability, serializability hay thread safety của Map kết quả. `Collectors.toList()` ở tầng downstream cũng không bảo đảm List có thể sửa. Với source ordered, các danh sách nhóm thường giữ thứ tự phần tử gặp trong nhóm theo ngữ nghĩa của downstream collector; nhưng nếu cần một loại List hoặc thứ tự duyệt khóa cụ thể, hãy khai báo rõ.

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> orderedGroups = orders.stream()
    .collect(Collectors.groupingBy(
        Order::customer,
        LinkedHashMap::new,
        Collectors.toCollection(ArrayList::new)
    ));

// Key theo thứ tự gặp đầu tiên: An, Bình.
// Trong nhóm An, các đơn xuất hiện theo thứ tự [2, 3].
~~~

`LinkedHashMap::new` bảo đảm duyệt khóa theo thứ tự chèn, còn `toCollection(ArrayList::new)` tạo danh sách mutable và giữ encounter order của các phần tử trong nhóm khi nguồn ordered. Nếu muốn đầu ra không sửa đổi được, cần một bước chuyển đổi phù hợp cho cả Map và các List bên trong; chỉ bọc Map ở ngoài **không** làm các List bên trong tự bất biến.

**Lưu ý null:** implementation của `groupingBy` không cho phép classifier trả về khóa `null`, thường ném `NullPointerException`. Hãy lọc hoặc thay thế khóa null bằng một nhóm có tên rõ ràng trước khi grouping.

## 9. Mutable, unmodifiable và immutable là ba ý niệm cần phân biệt

- **Mutable Collection:** các phép sửa cấu trúc như `add`, `remove`, `put` được hỗ trợ theo hợp đồng.
- **Unmodifiable Collection:** không sửa cấu trúc qua tham chiếu Collection đó; nhưng các phần tử chứa bên trong vẫn có thể mutable.
- **Deep immutable:** toàn bộ đồ thị dữ liệu có thể quan sát qua Collection không bị thay đổi sau khi tạo. Đây là yêu cầu mạnh hơn mà `toList()`, `toUnmodifiableList()` và `List.copyOf()` **không tự bảo đảm**.

### 9.1. Danh sách không sửa được vẫn có thể chứa object mutable

~~~java
import java.util.List;
import java.util.stream.Stream;

StringBuilder builder = new StringBuilder("A");

List<StringBuilder> result = Stream.of(builder).toList();

// result.add(new StringBuilder("B")); // UnsupportedOperationException
builder.append("!");

System.out.println(result.get(0)); // A!
~~~

Bản thân danh sách không bị thêm, bớt hay thay thế phần tử, nhưng nội dung phần tử thay đổi. Nếu ứng dụng cần một snapshot thật sự bất biến, hãy chuyển dữ liệu thành các value object bất biến hoặc bản sao phòng vệ trước khi thu thập.

~~~java
List<String> snapshot = Stream.of(builder)
    .map(StringBuilder::toString)
    .toList();

// snapshot chứa "A!" tại thời điểm tạo.
builder.append("?");
System.out.println(snapshot); // [A!]
~~~

### 9.2. `Collections.unmodifiableList` là view; `List.copyOf` tạo bản sao hợp đồng

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

ArrayList<String> source = new ArrayList<>(List.of("A"));

List<String> view = Collections.unmodifiableList(source);
List<String> copy = List.copyOf(source);

source.add("B");

System.out.println(view); // [A, B] vì view phản ánh list nền.
System.out.println(copy); // [A] vì copy không phụ thuộc thay đổi của source.
~~~

`Collections.unmodifiableList(source)` chặn chỉnh sửa **qua view**, nhưng vẫn phản ánh việc một tham chiếu khác sửa `source`. `List.copyOf(source)` trả danh sách không sửa được, độc lập với các sửa đổi sau này của `source`; nó không tạo bản sao sâu của từng phần tử.

Cả `List.copyOf` lẫn `Set.copyOf` và `Map.copyOf` đều cấm null ở những vị trí liên quan. `Set.copyOf`/`Map.copyOf` không cam kết thứ tự duyệt như `LinkedHashSet`/`LinkedHashMap`.

### 9.3. `collectingAndThen` có ích khi cần bước hoàn thiện

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> immutableCopy = Stream.of("A", "B")
    .collect(Collectors.collectingAndThen(
        Collectors.toList(),
        List::copyOf
    ));
~~~

`collectingAndThen` chạy finisher sau khi tích lũy, có thể chuyển List sang kiểu/định dạng cuối. Với `List::copyOf`, finisher sẽ ném NPE nếu kết quả chứa null.

Không cần thêm một bước bọc như vậy nếu `Stream.toList()` hoặc `Collectors.toUnmodifiableList()` đã đáp ứng hoàn toàn yêu cầu. Khi cần một **view** hay snapshot có thể có null, phải xác định rõ chính sách thay vì tự động dùng `copyOf`.

## 10. Một bài toán thực tế: danh sách mã khách hàng sạch, có thứ tự

Dữ liệu nhập từ hệ thống cũ có thể có khoảng trắng, chữ hoa/chữ thường không nhất quán, giá trị null và mã trùng. Yêu cầu sản phẩm:

- Loại bỏ mã null và mã rỗng.
- Chuẩn hóa và loại trùng.
- Sắp xếp để hiển thị ổn định.
- Trả kết quả không sửa đổi được.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class CustomerCodes {
    public static void main(String[] args) {
        List<String> rawCodes = Arrays.asList(
            " b02 ", null, "A01", "a01 ", "", "C03", "B02"
        );

        List<String> codes = rawCodes.stream()
            .filter(Objects::nonNull)
            .map(String::strip)
            .filter(code -> !code.isEmpty())
            .map(code -> code.toUpperCase(Locale.ROOT))
            .distinct()
            .sorted()
            .toList();

        System.out.println(codes); // [A01, B02, C03]

        // codes.add("D04"); // UnsupportedOperationException
    }
}
~~~

Vì dữ liệu cuối **không chứa null**, `toList()` là lựa chọn gọn. `distinct()` là stateful intermediate operation để loại trùng; `sorted()` tạo thứ tự theo ký tự. Khi nguồn lớn, hai operation này có thể tiêu thụ bộ nhớ đáng kể; hãy đo nếu hiệu năng quan trọng.

Nếu nghiệp vụ cần **duy trì thứ tự mã xuất hiện đầu tiên** thay vì sắp xếp, bỏ `sorted()` và dùng `distinct().toList()` trên nguồn ordered. Nếu cần một tập mã **có thể sửa** theo thứ tự xuất hiện, dùng:

~~~java
import java.util.LinkedHashSet;
import java.util.stream.Collectors;

LinkedHashSet<String> editable = rawCodes.stream()
    .filter(Objects::nonNull)
    .map(String::strip)
    .filter(code -> !code.isEmpty())
    .map(code -> code.toUpperCase(Locale.ROOT))
    .collect(Collectors.toCollection(LinkedHashSet::new));
~~~

Nếu mục tiêu chỉ là kiểm tra sự hiện diện của mã, một `Set` thường phù hợp hơn `List`. Nhưng nếu giao diện người dùng cần hiển thị thứ tự cụ thể, hãy lựa chọn cấu trúc dữ liệu thể hiện yêu cầu này.

## 11. Những lỗi thường gặp

### Lỗi 1: Dựa vào khả năng sửa của Collectors.toList

~~~java
List<String> names = source.stream()
    .collect(Collectors.toList());

// names.add("X") có thể chạy trên JDK hiện tại,
// nhưng không được bảo đảm trong hợp đồng của Collectors.toList().
~~~

Dùng `Collectors.toCollection(ArrayList::new)` khi kết quả chắc chắn phải có thể sửa.

### Lỗi 2: Tưởng `toList()` và `toUnmodifiableList()` luôn tương đương

~~~java
List<String> a = Stream.of("X", null).toList(); // Có thể chứa null.

// Dòng này ném NullPointerException:
// List<String> b = Stream.of("X", null)
//     .collect(Collectors.toUnmodifiableList());
~~~

Cả hai đều không sửa được, nhưng chính sách null khác nhau.

### Lỗi 3: Tưởng toSet giữ encounter order

~~~java
Set<Integer> set = List.of(3, 1, 2, 1).stream()
    .collect(Collectors.toSet());

// Chỉ được khẳng định set chứa 1, 2, 3; không dựa vào thứ tự in.
~~~

Dùng `toCollection(LinkedHashSet::new)` để giữ thứ tự lần xuất hiện đầu, hoặc `toCollection(TreeSet::new)` nếu cần thứ tự so sánh.

### Lỗi 4: Giả định parallel stream làm mất thứ tự List

~~~java
List<Integer> values = List.of(3, 1, 2).parallelStream()
    .toList();

// values vẫn có encounter order [3, 1, 2].
~~~

Parallel stream có thể chia tác vụ nhưng không mặc nhiên làm mất ràng buộc thứ tự của terminal. Nếu bỏ thứ tự bằng `unordered()`, hành vi mới có thể khác.

### Lỗi 5: Không xử lý khóa trùng trong toMap

~~~java
// Với hai User có cùng id:
// users.stream().collect(Collectors.toMap(User::id, User::name));
// Có thể ném IllegalStateException vì khóa trùng.
~~~

Hãy xác định khóa duy nhất hoặc truyền merge function, chẳng hạn chọn bản ghi theo timestamp có quy tắc.

### Lỗi 6: Bọc Map ngoài rồi tưởng dữ liệu lồng nhau bất biến

~~~java
// Map<String, List<Order>> groups = ...
// Collections.unmodifiableMap(groups) chỉ chặn thay đổi map
// qua wrapper, không tự làm từng List<Order> bất biến.
~~~

Nếu công bố API không cho phép khách hàng sửa cấu trúc lồng nhau, hãy tạo bản sao bất biến của từng nhóm và của Map ở tầng cuối, đồng thời kiểm soát object con mutable.

### Lỗi 7: So sánh Collection bằng toString khi thứ tự không được bảo đảm

~~~java
// Không so sánh chuỗi in ra của HashSet/HashMap để kiểm tra tập giá trị.
// So sánh Set bằng equals, Map bằng equals nếu thứ tự không có ý nghĩa.
~~~

Với List, `List.equals` có xét thứ tự. Với Set và Map, `equals` mô tả quan hệ phần tử/khóa-giá trị, không dựa vào thứ tự duyệt.

## 12. Checklist lựa chọn collector

| Câu hỏi | Nếu câu trả lời là có | Lựa chọn gợi ý |
| --- | --- | --- |
| Có cần List **không sửa đổi được**, giữ encounter order? | Có | `Stream.toList()` |
| Có cần List **không sửa đổi được** và **loại null**? | Có | `filter(Objects::nonNull).toList()` hoặc `toUnmodifiableList()` sau lọc |
| Có cần `ArrayList` có thể thay đổi? | Có | `toCollection(ArrayList::new)` |
| Cần Set nhưng không quan tâm thứ tự duyệt? | Có | `toSet()` hoặc `toUnmodifiableSet()`, theo chính sách sửa/null |
| Cần Set theo thứ tự xuất hiện đầu tiên? | Có | `toCollection(LinkedHashSet::new)` |
| Cần Set có thứ tự sắp xếp? | Có | `toCollection(TreeSet::new)` với comparator phù hợp |
| Cần Map có thứ tự chèn và có thể sửa? | Có | `toMap(..., merge, LinkedHashMap::new)` |
| Cần Map không sửa được, không chứa null? | Có | `toUnmodifiableMap(...)` |
| Cần grouping với thứ tự khóa xác định? | Có | `groupingBy(..., LinkedHashMap::new, downstream)` |
| Dữ liệu có thể chứa null hay khóa trùng? | Có | Lọc, chuẩn hóa hoặc mô hình hóa lỗi và merge policy trước terminal |

**Lưu ý:** “Cần List không sửa được và loại null” không yêu cầu phải dùng `toUnmodifiableList()` nếu `filter(...).toList()` đã mô tả chính xác mong muốn. Ngược lại, nếu muốn **phát hiện null như lỗi**, có thể dùng collector cấm null để thất bại sớm; ứng dụng phải chọn rõ chính sách thay vì chỉ dựa vào hành vi tình cờ.

## 13. Câu hỏi tự kiểm tra

1. **`Stream.toList()` có hỗ trợ `add` sau khi thu thập không?** Không; thao tác sửa sẽ ném `UnsupportedOperationException`.
2. **`Collectors.toList()` có cam kết trả `ArrayList` mutable không?** Không; kiểu và mutability của List không được bảo đảm.
3. **`Stream.of("A", null).toList()` có thể cho kết quả gì?** Một List không sửa đổi được chứa `"A"` và `null`.
4. **`Collectors.toUnmodifiableList()` gặp null thì sao?** Ném `NullPointerException`.
5. **Vì sao `Collectors.toSet()` không dùng để bảo đảm thứ tự hiển thị?** Collector không cam kết thứ tự duyệt của Set kết quả.
6. **Nếu cần giữ thứ tự xuất hiện đầu tiên nhưng bỏ trùng, nên dùng gì?** `Collectors.toCollection(LinkedHashSet::new)` hoặc `distinct().toList()` nếu muốn List không sửa đổi được.
7. **`TreeSet` khác `LinkedHashSet` ở điểm nào?** TreeSet dùng thứ tự so sánh; LinkedHashSet dùng thứ tự chèn.
8. **Hai phần tử có cùng khóa đi vào `toMap(keyMapper, valueMapper)` thì sao?** Collector ném `IllegalStateException` nếu không có merge policy.
9. **Muốn Map giữ thứ tự chèn, mutable và loại trùng theo quy tắc xác định, dùng gì?** Overload `toMap(key, value, merge, LinkedHashMap::new)`.
10. **`toUnmodifiableMap` cho phép null ở khóa hay giá trị không?** Không; cả hai đều bị cấm.
11. **`List.copyOf` khác `Collections.unmodifiableList(source)` thế nào?** Copy không phản ánh việc sửa cấu trúc nguồn sau này; unmodifiable view phản ánh thay đổi của backing list.
12. **List không sửa đổi được chứa `StringBuilder` có bất biến sâu không?** Không; nội dung StringBuilder vẫn có thể thay đổi.
13. **`parallelStream().toList()` có giữ encounter order của List không?** Có, nếu pipeline giữ encounter order.
14. **Nếu classifier của `groupingBy` trả null thì nên làm gì?** Lọc, chuẩn hóa hoặc ánh xạ thành khóa thay thế trước khi grouping.
15. **Khi nào nên dùng `Collectors.toCollection`?** Khi cần kiểm soát chính xác loại collection, tính sửa đổi được và những thuộc tính như thứ tự chèn/sắp xếp.

**Ghi nhớ:** Đầu ra của Stream phải được đánh giá theo **mutability, ordering và null policy** như ba hợp đồng độc lập. `Stream.toList()` và `Collectors.toUnmodifiableList()` đều không sửa đổi được nhưng có chính sách null khác nhau; `Collectors.toList()`/`toSet()` không cam kết mutability; `toCollection` và `toMap` có supplier giúp chọn cấu trúc cụ thể. Khi yêu cầu nghiệp vụ rõ ràng, lựa chọn terminal operation rõ ràng sẽ giảm lỗi runtime và làm pipeline dễ bảo trì, ngay cả khi chuyển sang xử lý song song.
