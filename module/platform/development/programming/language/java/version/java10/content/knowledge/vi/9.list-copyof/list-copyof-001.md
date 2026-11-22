# Chữ ký generic và nguồn `Collection` của `List.copyOf`

*Chủ đề: `List.copyOf` trong Java 10 trở đi. Bài học tập trung vào chữ ký generic `Collection<? extends E>`, cách chọn nguồn dữ liệu, suy luận kiểu và các bảo đảm API vẫn còn áp dụng trong Java hiện đại. Các chương trình đầy đủ dưới đây dùng JDK 17+.*

## 1. Mục tiêu và bản chất của `List.copyOf`

Sau bài học, bạn có thể:

1. Đọc đúng chữ ký `public static <E> List<E> copyOf(Collection<? extends E> coll)`.
2. Giải thích `E` và wildcard `? extends E`; biết vì sao nguồn có phần tử là kiểu con được phép truyền vào.
3. Phân tích kiểu trả về khi dùng `var`, khi có kiểu đích tường minh và khi nguồn có kiểu wildcard.
4. Phân biệt `Collection`, `List`, `Set`, `Queue` với `Iterable`, array, `Map` và `Stream` khi gọi `List.copyOf`.
5. Giải thích thứ tự phần tử, phần tử trùng, xử lý `null`, danh sách không cho sửa, bản sao nông và ảnh hưởng của việc sửa nguồn.
6. Chọn đúng giữa `List.copyOf`, `List.of`, `new ArrayList<>(source)` và `Collections.unmodifiableList` theo hợp đồng mong muốn.
7. Dùng `List.copyOf` để tạo defensive copy ở ranh giới API mà không hiểu nhầm đó là deep copy hay giải pháp thread-safety tự động.

`List.copyOf` là phương thức static của `java.util.List`, được bổ sung từ **Java 10** và vẫn được sử dụng trong Java hiện đại. Nó nhận một `Collection` và trả về một `List` **không cho phép sửa cấu trúc/phần tử thông qua các phương thức thay đổi danh sách**. Thứ tự phần tử trong danh sách trả về theo **thứ tự iterator của nguồn** ở thời điểm tạo kết quả; nguồn chứa `null` hoặc chính nguồn là `null` sẽ dẫn đến `NullPointerException`.

Ví dụ nhanh:

```java
var mutableNames = new java.util.ArrayList<>(
        java.util.List.of("Lan", "An"));
var names = java.util.List.copyOf(mutableNames); // List<String>
mutableNames.add("Binh");

// names vẫn biểu diễn [Lan, An], không nhận phần tử mới.
// names.add("Chi"); // Runtime: UnsupportedOperationException
```

Đoạn trên là minh họa bên trong một phương thức. `List.copyOf` tạo một danh sách kết quả có thể dùng độc lập với những thay đổi về **các vị trí phần tử trong collection nguồn** sau đó. Tuy nhiên, bản thân đối tượng phần tử có thể vẫn được chia sẻ: điều này sẽ được kiểm tra ở phần sau.

## 2. Đọc chữ ký generic chính xác

Chữ ký API:

```java
public static <E> List<E> copyOf(Collection<? extends E> coll)
```

Đây là **chữ ký phương thức minh họa từ API**, không phải một khai báo được phép đặt ngoài interface/class của riêng bạn.

Giải mã từng thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `public static` | Gọi bằng `List.copyOf(...)`, không cần đối tượng List |
| `<E>` trước kiểu trả về | Khai báo tham số kiểu generic **của phương thức** |
| `List<E>` | Kiểu trả về: danh sách có kiểu phần tử `E` |
| `Collection<? extends E>` | Tham số nhận một collection mà kiểu phần tử có thể là `E` **hoặc kiểu con của `E`** |
| `coll` | Nguồn để đọc các phần tử theo iterator |
| `? extends E` | Wildcard giới hạn trên: nguồn **cung cấp** các phần tử có thể xem như `E` |

Ví dụ `Integer` kế thừa `Number`. Một `Collection<Integer>` có thể được dùng làm nguồn để tạo `List<Number>`:

```java
java.util.Collection<Integer> integerSource = java.util.List.of(1, 2);
java.util.List<Number> numbers = java.util.List.copyOf(integerSource);
```

Điều này hợp lệ nhờ tham số nguồn là `Collection<? extends E>`. Nếu chỉ khai báo `Collection<E>`, trong trường hợp `E = Number` thì Java sẽ yêu cầu `Collection<Number>`; `Collection<Integer>` không thể tự đổi thành nó.

### 2.1. Vì sao Java không coi `List<Integer>` là `List<Number>`?

Generics Java **bất biến (invariant)**. Dù `Integer` là một `Number`, nhưng `List<Integer>` không phải kiểu con của `List<Number>`:

```java
java.util.List<Integer> integers = java.util.List.of(1, 2);
// java.util.List<Number> numbers = integers; // Lỗi biên dịch
```

Nếu cho phép phép gán đó, code cầm `List<Number>` có thể thêm `Double` vào danh sách vốn dành cho `Integer`. API `copyOf` giải quyết nhu cầu **đọc** từ nhiều loại collection bằng wildcard, còn **tạo kết quả** có kiểu `List<E>` phù hợp với ngữ cảnh gọi.

Đây là một ứng dụng quy tắc **PECS — Producer Extends, Consumer Super**: nguồn `coll` đóng vai trò cung cấp (producer) các giá trị cho danh sách kết quả. `copyOf` không định sửa collection nguồn; việc sử dụng `? extends E` cho phép nhận dữ liệu từ các kiểu con mà vẫn an toàn kiểu.

### 2.2. Wildcard ảnh hưởng quyền đọc/ghi ở compile time

Giả sử:

```java
java.util.Collection<? extends Number> source =
        java.util.List.of(1, 2, 3);

for (Number value : source) {
    System.out.println(value.intValue());
}

// source.add(4); // Lỗi biên dịch: không biết kiểu con Number cụ thể
```

Với `Collection<? extends Number>`, bạn có thể đọc phần tử dưới dạng `Number`. Nhưng không thể tự ý thêm `Integer`, vì collection thực tế có thể là collection của một kiểu con khác.

Lưu ý: **không được nhầm “không thể thêm” do wildcard trong kiểu của nguồn với “không cho sửa” của danh sách `List.copyOf` ở runtime.** Đó là hai bảo đảm khác nhau.

## 3. Suy luận `E`: `var`, kiểu đích và nguồn wildcard

### 3.1. `var` với nguồn có kiểu phần tử cụ thể

```java
java.util.Collection<Integer> source = java.util.List.of(1, 2, 3);

var inferred = java.util.List.copyOf(source);
// inferred: List<Integer>

java.util.List<Number> widened = java.util.List.copyOf(source);
// widened: List<Number>
```

Khi khai báo `var inferred`, không có kiểu đích viết tường minh cho toàn bộ phép gọi; trình biên dịch dựa vào biểu thức và suy luận `E` là `Integer`, nên kết quả là `List<Integer>`.

Với `List<Number> widened`, kiểu đích cung cấp ngữ cảnh để suy luận `E = Number`. `Collection<Integer>` tương thích `Collection<? extends Number>`, do đó kết quả là `List<Number>`. **Không có chuyển đổi hay biến đổi phần tử `Integer` thành một đối tượng `Number` khác**; vẫn là các giá trị số ban đầu được nhìn qua kiểu `Number`.

Có thể chỉ rõ tham số kiểu:

```java
var explicit = java.util.List.<Number>copyOf(source);
// explicit: List<Number>
```

Chữ ký generic được áp dụng khi biên dịch. `var` không làm generic trở thành “kiểu động”, và kiểu kết quả vẫn xác định trước khi chương trình chạy.

### 3.2. Với `Collection<? extends Number>`, `var` giữ wildcard

Đây là trường hợp khác với nguồn đã biết chính xác `Integer`:

```java
java.util.Collection<? extends Number> source =
        java.util.List.of(1, 2, 3);

var inferred = java.util.List.copyOf(source);
// Kiểu suy luận: List<? extends Number>

Number first = inferred.get(0);
// java.util.List<Number> wrong = inferred; // Lỗi biên dịch

java.util.List<Number> asNumbers = java.util.List.copyOf(source);
// Hợp lệ: kiểu đích Number cung cấp ngữ cảnh cho copyOf
```

`inferred` có kiểu `List<? extends Number>` trong ngữ cảnh này; phép gán trực tiếp từ biến đó sang `List<Number>` không hợp lệ vì bất biến generic. Nhưng **gọi lại** phương thức với kiểu đích `List<Number>` cho phép suy luận `E` rộng thành `Number`.

Bạn có thể viết rõ khi muốn:

```java
var asNumbers = java.util.List.<Number>copyOf(source);
// asNumbers: List<Number>
```

Đây là điểm quan trọng khi kết hợp `var` với wildcard. Nếu IDE hiển thị `List<? extends Number>`, hãy đọc đúng kiểu của biến; không tự rút gọn thành `List<Number>`.

### 3.3. Không thể thu hẹp bất kỳ collection nào xuống một kiểu con tùy ý

```java
java.util.Collection<Number> numbers =
        java.util.List.of(1, 2.5);

// java.util.List<Integer> ints = java.util.List.copyOf(numbers);
// Lỗi biên dịch: Number không bảo đảm mọi phần tử là Integer
```

`copyOf` bảo toàn giá trị phần tử, không ép kiểu chúng. `Collection<Number>` có thể chứa `Double`; không thể dùng generic inference để tự biến chúng thành `Integer`. Đừng thêm raw type hoặc cast không kiểm tra chỉ để bỏ lỗi kiểu.

## 4. “Nguồn `Collection`” có nghĩa gì?

Tham số được khai báo là `Collection<? extends E>`. Vì vậy **mọi implementation phù hợp của `Collection`** đều có thể làm nguồn. Không bắt buộc phải là `List`.

| Nguồn | Gọi `List.copyOf` trực tiếp? | Điều cần nhớ |
| --- | --- | --- |
| `List<E>`, `ArrayList<E>` | Có | Giữ thứ tự iterator; phần tử trùng được giữ |
| `Set<E>`, `LinkedHashSet<E>` | Có | Không có phần tử trùng do Set; thứ tự phụ thuộc implementation |
| `Queue<E>` / `ArrayDeque<E>` | Có | Dựa trên thứ tự iterator, không thay đổi hàng đợi nguồn |
| `Collection<E>`, `Collection<? extends E>` | Có | Khớp đúng ràng buộc của tham số |
| `Map<K,V>` | Không | Map không mở rộng Collection; dùng `keySet()`, `values()` hoặc `entrySet()` nếu phù hợp |
| `Stream<E>` | Không | Stream không phải Collection; dùng terminal operation tạo collection nếu cần |
| `Iterable<E>` thông thường | Không mặc định | Chỉ gọi trực tiếp nếu đối tượng/kiểu tĩnh cũng triển khai `Collection` |
| Array `E[]` | Không | Array không phải Collection; có thể dùng `Arrays.asList(array)` với mảng đối tượng |
| Một đối tượng đơn `E` | Không | `copyOf` nhận collection, không nhận một phần tử đơn |

### 4.1. Vì sao `Set` hợp lệ dù kết quả là `List`?

`Set` là interface con của `Collection`. `List.copyOf(set)` duyệt các phần tử từ iterator của `Set` và tạo List theo thứ tự đó.

- Với `LinkedHashSet` thông thường, thứ tự iterator theo thứ tự chèn; do vậy có thể dự đoán kết quả từ một ví dụ chèn tuần tự.
- Với `HashSet`, không nên giả định thứ tự iterator cố định hoặc được sắp xếp. `List.copyOf` **không tự sắp xếp**.
- Nếu nguồn Set loại bỏ phần tử trùng, kết quả không thể phục hồi những phần tử đã bị Set loại bỏ. `List.copyOf` tự nó không phải thao tác `distinct()`.

### 4.2. `Map.values()` là collection nhưng `Map` không phải

Ví dụ:

```java
var scoresByName = java.util.Map.of(
        "Lan", 9,
        "An", 8
);

var scores = java.util.List.copyOf(scoresByName.values());
// scores: List<Integer>
```

`values()` trả về một `Collection<Integer>`, vì vậy phù hợp chữ ký. Tuy nhiên, **thứ tự duyệt từ `Map.of` không được bảo đảm**; không viết bài kiểm tra phụ thuộc thứ tự hai điểm số khi không có bước sắp xếp hoặc cấu trúc giữ thứ tự.

Tương tự, `keySet()` cho collection các khóa, `entrySet()` cho collection các `Map.Entry<K,V>`. Chọn nguồn theo **giá trị bạn muốn sao chép** thay vì tùy tiện đổi Map thành List.

### 4.3. `Stream` và array cần chuyển sang Collection theo cách có chủ đích

```java
var stream = java.util.stream.Stream.of("A", "B");
// java.util.List.copyOf(stream); // Lỗi biên dịch: Stream không phải Collection

var fromStream = stream.toList();       // List<String>, Java 16+
var copied = java.util.List.copyOf(fromStream); // List<String>

String[] namesArray = {"A", "B"};
var fromArray = java.util.List.copyOf(
        java.util.Arrays.asList(namesArray)); // List<String>
```

`Stream.toList()` đã tạo một danh sách không cho sửa ở Java hiện đại; có thể **không cần** `List.copyOf` lần nữa nếu hợp đồng của bạn chỉ cần danh sách đó. Nếu pipeline có thể sinh `null`, cần nhớ `Stream.toList()` có thể chứa `null`, trong khi `List.copyOf` từ chối `null`.

Với mảng primitive như `int[]`, `Arrays.asList(intArray)` **không** tạo `List<Integer>` từ từng số; nó tạo danh sách có một phần tử là cả mảng `int[]`. Muốn `List<Integer>` từ mảng `int[]`, cần chuyển từng phần tử qua `IntStream.of(array).boxed().toList()` hoặc cách biến đổi tương đương.

## 5. Thứ tự và phần tử trùng: nhìn iterator của nguồn

Tạo tệp **`CollectionSourcesDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

public class CollectionSourcesDemo {
    public static void main(String[] args) {
        var names = new ArrayList<>(
                List.of("Lan", "An", "Lan"));

        var orderedSet = new LinkedHashSet<>(names);

        var queue = new ArrayDeque<String>();
        queue.addLast("first");
        queue.addLast("second");

        System.out.println("list=" + List.copyOf(names));
        System.out.println("set=" + List.copyOf(orderedSet));
        System.out.println("queue=" + List.copyOf(queue));
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac --release 17 CollectionSourcesDemo.java
java CollectionSourcesDemo
```

Stdout chính xác:

```text
list=[Lan, An, Lan]
set=[Lan, An]
queue=[first, second]
```

Giải thích:

1. `ArrayList` lưu các phần tử theo thứ tự chèn, có cả hai lần xuất hiện của `"Lan"`. `List.copyOf` giữ cả hai.
2. `LinkedHashSet` bỏ phần tử trùng và giữ thứ tự chèn từ dữ liệu nguồn; danh sách tạo từ nó có `[Lan, An]`.
3. `ArrayDeque` trong ví dụ duyệt theo thứ tự của các thao tác `addLast`; List kết quả chứa hai phần tử cùng thứ tự.
4. Không có câu lệnh nào lấy dữ liệu ra khỏi queue hoặc sửa các collection nguồn.

**Quy tắc:** `List.copyOf` bảo toàn *thứ tự lặp của Collection*, không “sửa” thứ tự vốn không được bảo đảm. Nếu thứ tự là một phần hợp đồng ứng dụng, hãy chọn collection nguồn có thứ tự được định nghĩa hoặc sắp xếp trước khi sao chép.

## 6. Chương trình generic: `var` và kiểu đích khác nhau thế nào?

Tạo **`CopyOfGenericDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CopyOfGenericDemo {
    public static void main(String[] args) {
        Collection<Integer> source =
                new ArrayList<>(List.of(1, 2, 3));

        var inferred = List.copyOf(source);
        List<Number> widened = List.copyOf(source);

        source.add(4);

        System.out.println("source=" + source);
        System.out.println("inferred=" + inferred);
        System.out.println("widened=" + widened);

        Collection<? extends Number> sourceWildcard = source;
        List<Number> asNumbers = List.copyOf(sourceWildcard);
        var fromWildcard = List.copyOf(sourceWildcard);

        System.out.println("numbers=" + asNumbers);
        System.out.println("wildcard=" + fromWildcard);
    }
}
```

Chạy:

```bash
javac --release 17 CopyOfGenericDemo.java
java CopyOfGenericDemo
```

Stdout:

```text
source=[1, 2, 3, 4]
inferred=[1, 2, 3]
widened=[1, 2, 3]
numbers=[1, 2, 3, 4]
wildcard=[1, 2, 3, 4]
```

Cần phân biệt **hai giai đoạn tạo bản sao**. `inferred` và `widened` được tạo *trước* `source.add(4)`, nên không có phần tử `4`; `asNumbers` và `fromWildcard` được tạo *sau*, nên có `4`.

Điều quan trọng hơn stdout là **kiểu biên dịch**:

| Biến | Kiểu tĩnh |
| --- | --- |
| `source` | `Collection<Integer>` |
| `inferred` | `List<Integer>` |
| `widened` | `List<Number>` |
| `sourceWildcard` | `Collection<? extends Number>` |
| `asNumbers` | `List<Number>` |
| `fromWildcard` | `List<? extends Number>` |

Bạn có thể dùng hover trong IDE hoặc JShell `/vars` để kiểm tra các kiểu. Hai danh sách cùng in ra những số như nhau **không có nghĩa** hai biến có cùng generic type; generics được kiểm tra lúc biên dịch, còn thông tin tham số kiểu không làm đổi giá trị phần tử được in ra.

## 7. Những bảo đảm và giới hạn của kết quả `List.copyOf`

### 7.1. Danh sách kết quả không cho phép sửa

`List.copyOf` trả `List<E>` không hỗ trợ các thao tác thay đổi danh sách, như `add`, `remove`, `clear`, `set`. Chúng gây `UnsupportedOperationException` lúc chạy.

```java
var snapshot = java.util.List.copyOf(
        java.util.List.of("A", "B"));
// snapshot.add("C"); // Biên dịch được nếu gọi trên List<String>, nhưng ném
// UnsupportedOperationException khi chạy.
```

Đừng nhầm điều này với việc biến là `final`. `final` chỉ giới hạn gán lại biến; tính không cho sửa nội dung danh sách xuất phát từ **hợp đồng của danh sách trả về**, bất kể khai báo `var` hay `List<String>`.

### 7.2. Các phần tử `null` và nguồn `null` đều bị từ chối

`List.copyOf` không chấp nhận collection đầu vào `null` và không cho phần tử `null` trong collection. Ví dụ:

```java
var listWithNull = java.util.Arrays.asList("A", null);
// var copied = java.util.List.copyOf(listWithNull);
// Khi thực thi sẽ ném NullPointerException.
```

Không sửa một dữ liệu nullable bằng cách cast hoặc ép generic type rồi gọi `copyOf`; phải quyết định hợp đồng: loại `null`, thay giá trị phù hợp, hoặc dùng cấu trúc/API cho phép `null` nếu nghiệp vụ thực sự cần.

### 7.3. Thay đổi cấu trúc nguồn sau khi sao chép không phản ánh sang kết quả

Với `ArrayList` hay các mutable collection, sau `List.copyOf`, thêm/xóa/thay vị trí phần tử ở nguồn không tự cập nhật vào danh sách kết quả. Điều này cho phép xây dựng **defensive snapshot** của các tham chiếu phần tử hiện có tại lúc sao chép.

Tuy nhiên, nếu một collection bị sửa **đồng thời trong chính lúc** đang sao chép, không được giả định `copyOf` tạo ra một “ảnh chụp nguyên tử” với bảo đảm đồng bộ. Đảm bảo thread-safety/snapshot đồng nhất là trách nhiệm của cách phối hợp truy cập nguồn.

### 7.4. `List.copyOf` là bản sao nông (shallow), không deep copy

Danh sách kết quả giữ **các đối tượng phần tử** được đọc từ nguồn; nó không tự tạo bản sao sâu của từng đối tượng. Nếu phần tử là mutable, thay đổi chính đối tượng có thể quan sát được qua danh sách kết quả.

```java
// Đoạn minh họa bên trong method:
var element = new StringBuilder("draft");
var snapshot = java.util.List.copyOf(
        java.util.List.of(element));

element.append("-edited");
System.out.println(snapshot.get(0)); // draft-edited
```

`snapshot` không hỗ trợ `set(0, ...)`, nhưng đối tượng `StringBuilder` trong phần tử vẫn được sửa bên ngoài. Do đó “unmodifiable list” **không đồng nghĩa** “toàn bộ đồ thị đối tượng bất biến”. Với phần tử mutable, nếu cần bất biến sâu hoặc an toàn luồng, hãy thiết kế kiểu phần tử, sao chép hoặc đồng bộ phù hợp.

### 7.5. Không dựa vào danh tính implementation hoặc `==`

Một số implementation có thể tái sử dụng đối tượng List nguồn nếu nó đã đáp ứng hợp đồng không cho sửa. API không bảo đảm mọi lần gọi `copyOf` đều tạo một object mới, hoặc luôn trả về đúng cùng instance. Tránh viết:

```java
// Không dựa vào kết quả so sánh danh tính:
var source = java.util.List.of("A");
var copied = java.util.List.copyOf(source);
// boolean sameObject = source == copied; // Không dùng làm hợp đồng
```

Khi cần so nội dung, dùng `equals`. Khi cần đảm bảo tính độc lập của các đối tượng phần tử mutable, phải xử lý riêng chứ không dựa vào việc danh sách trả về có identity khác.

## 8. So sánh với những API Collection còn dùng hiện nay

| Cách tạo | Đầu vào | Sửa danh sách kết quả? | Ghi chú |
| --- | --- | --- | --- |
| `List.copyOf(collection)` | Một `Collection<? extends E>` | Không | Giữ thứ tự iterator; từ chối `null`; bản sao nông |
| `List.of(e1, e2, ...)` | Các phần tử hoặc varargs | Không | Không nhận `null`; không có nghĩa là sao chép từ Collection |
| `new ArrayList<>(collection)` | Một `Collection<? extends E>` | Có | Danh sách mới mutable, có thể chứa `null` nếu nguồn cho phép |
| `Collections.unmodifiableList(list)` | Một `List<? extends E>` phù hợp | Không qua view | Trả **view không cho sửa**, có thể phản ánh thay đổi từ List nền |
| `stream.toList()` | Một `Stream<E>` (Java 16+) | Không | Terminal operation, có thể chứa `null` |
| `Collectors.toUnmodifiableList()` | Collector cho Stream (Java 10+) | Không | Từ chối phần tử `null`, dùng trong `collect` |

### 8.1. `List.of(sourceCollection)` không đồng nghĩa `List.copyOf(sourceCollection)`

Ví dụ:

```java
var source = java.util.List.of("A", "B");

var nested = java.util.List.of(source);
// nested: List<List<String>> — một phần tử là toàn bộ source

var copied = java.util.List.copyOf(source);
// copied: List<String> — hai phần tử "A" và "B"
```

`List.of` nhận **các phần tử**; khi bạn truyền một đối tượng `List` làm một đối số, nó tạo danh sách gồm chính đối tượng List đó (một phần tử). `List.copyOf` nhận một **Collection nguồn** và đưa *từng phần tử của collection* vào kết quả. Hai cách có ý nghĩa khác nhau.

### 8.2. `Collections.unmodifiableList` là view; `copyOf` dùng khi cần snapshot

Giả sử:

```java
var mutable = new java.util.ArrayList<>(
        java.util.List.of("A", "B"));
var view = java.util.Collections.unmodifiableList(mutable);
var snapshot = java.util.List.copyOf(mutable);
mutable.add("C");

// view chứa [A, B, C]
// snapshot chứa [A, B]
```

Đây là khác biệt thiết kế quan trọng khi nhận dữ liệu đầu vào từ code khác. `Collections.unmodifiableList` vẫn là API hợp lệ hiện nay, nhưng một **view** phụ thuộc nguồn bên dưới; nếu muốn giao một danh sách độc lập với thao tác thêm/xóa sau đó, `copyOf` thường dễ diễn đạt hợp đồng hơn.

`new ArrayList<>(source)` cũng tạo bản sao cấu trúc lúc tạo, nhưng cho phép sửa nội dung danh sách kết quả. Hãy chọn dựa vào nhu cầu sử dụng, không dùng `copyOf` khi thực sự cần thêm/xóa phần tử về sau.

## 9. Chương trình thực hành về snapshot, null và shallow copy

Tạo tệp **`CopySemanticsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class CopySemanticsDemo {
    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B"));
        var snapshot = List.copyOf(source);
        var view = Collections.unmodifiableList(source);

        source.add("C");

        System.out.println("source=" + source);
        System.out.println("snapshot=" + snapshot);
        System.out.println("view=" + view);

        try {
            snapshot.add("X");
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshot-add=blocked");
        }

        try {
            List.copyOf(Arrays.asList("ok", null));
        } catch (NullPointerException e) {
            System.out.println("null-element=blocked");
        }

        var item = new StringBuilder("draft");
        var objects = List.copyOf(List.of(item));
        item.append("-edited");

        System.out.println("shared-object=" + objects.get(0));
    }
}
```

Chạy:

```bash
javac --release 17 CopySemanticsDemo.java
java CopySemanticsDemo
```

Stdout:

```text
source=[A, B, C]
snapshot=[A, B]
view=[A, B, C]
snapshot-add=blocked
null-element=blocked
shared-object=draft-edited
```

Ba thông điệp cần nhớ từ ví dụ:

1. **Snapshot cấu trúc:** thêm `"C"` vào nguồn không ảnh hưởng danh sách `snapshot`.
2. **Hợp đồng API:** sửa trực tiếp danh sách kết quả và sao chép nguồn chứa `null` đều bị từ chối bằng ngoại lệ rõ ràng.
3. **Shallow copy:** đối tượng `StringBuilder` bị sửa vẫn hiển thị trạng thái mới qua danh sách chứa tham chiếu đến nó.

## 10. Dùng `List.copyOf` ở ranh giới API/constructor

Một công dụng thực tế là **defensive copy** của đầu vào khi tạo đối tượng không muốn lộ collection mutable ra bên ngoài. Với Java 17+, có thể dùng `record` và compact constructor.

Tạo **`PolicyCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PolicyCopyDemo {
    record Policy(List<String> roles) {
        public Policy {
            roles = List.copyOf(roles);
        }
    }

    public static void main(String[] args) {
        var sourceRoles = new ArrayList<>(
                List.of("READ", "WRITE"));

        var policy = new Policy(sourceRoles);
        sourceRoles.add("ADMIN");

        System.out.println("source=" + sourceRoles);
        System.out.println("policy=" + policy.roles());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 PolicyCopyDemo.java
java PolicyCopyDemo
```

Stdout:

```text
source=[READ, WRITE, ADMIN]
policy=[READ, WRITE]
```

Trong compact constructor của record, tham số `roles` được gán bằng danh sách trả về từ `List.copyOf`; trường của record được khởi tạo từ tham số đó sau phần thân constructor. Vì vậy thêm role vào `sourceRoles` không đổi `policy.roles()`.

Lợi ích:

- Bảo vệ cấu trúc danh sách lưu trong đối tượng khỏi việc caller thêm/xóa phần tử bằng tham chiếu nguồn.
- Không cho người gọi `policy.roles().add(...)` sửa danh sách được trả về.
- Từ chối `null` trong danh sách role hoặc chính đối số `roles` ngay khi tạo bản sao.
- Dùng kiểu interface `List<String>` làm hợp đồng, không phụ thuộc lớp cụ thể của danh sách nguồn.

**Giới hạn:** Ví dụ dùng phần tử `String` là immutable. Nếu đối tượng chứa `List<MutableRole>`, `List.copyOf` sẽ vẫn giữ tham chiếu đến từng `MutableRole`. Khi cần bảo vệ nội dung sâu của các phần tử, phải thiết kế và sao chép riêng.

## 11. Lỗi thường gặp khi đọc signature và chọn source

| Lỗi/nhầm lẫn | Nguyên nhân và cách sửa |
| --- | --- |
| “`copyOf` chỉ nhận `List<E>`.” | Sai: tham số là `Collection<? extends E>`; `Set`, `Queue` cũng hợp lệ |
| “`List<Integer>` là `List<Number>` vì `Integer extends Number`.” | Sai do generic invariance; dùng `List<Number> result = List.copyOf(integerSource)` khi muốn danh sách kết quả kiểu Number |
| “Dùng `var` với wildcard luôn tạo `List<Number>`.” | Sai: từ `Collection<? extends Number>`, `var copy = List.copyOf(source)` suy luận `List<? extends Number>` |
| “`copyOf` chuyển kiểu mọi phần tử về `E`.” | Không: type inference không ép/chuyển giá trị runtime |
| “`copyOf` tự sắp xếp Set.” | Không: giữ iterator order của nguồn; chọn ordered collection nếu cần thứ tự |
| “`copyOf` loại trùng trong List.” | Không: các phần tử trùng của List được giữ; Set loại trùng theo quy tắc của Set trước đó |
| “Danh sách không cho sửa thì phần tử cũng bất biến.” | Sai: bản sao nông, đối tượng mutable vẫn có thể thay đổi |
| “`copyOf` cho phép `null` vì Collection cho phép.” | Không: nguồn/phần tử `null` gây `NullPointerException` |
| “`List.of(existingList)` sao chép các phần tử.” | Không: là List chứa một phần tử List, khác `List.copyOf(existingList)` |
| “`Collections.unmodifiableList` tạo snapshot.” | Không: là view nên có thể phản ánh thay đổi của List nền |
| “`copyOf` luôn cấp phát instance mới.” | Không có bảo đảm danh tính như vậy; đừng so sánh `==` để dựa vào nó |
| “Đầu vào đã typed là `Iterable<E>` thì gọi thẳng `copyOf` được.” | Chữ ký cần `Collection`; phải có kiểu/đối tượng phù hợp hoặc chuyển đổi |

### 11.1. Một số lỗi biên dịch mẫu

Các dòng chú thích sau **không phải chương trình chạy độc lập**:

```java
java.util.Map<String, Integer> map =
        java.util.Map.of("a", 1);

// java.util.List.copyOf(map); // Map không phải Collection
var values = java.util.List.copyOf(map.values()); // List<Integer>

var numbers = java.util.List.of(1, 2);
// java.util.List<Number> invalid = numbers; // Generic invariant
java.util.List<Number> valid = java.util.List.copyOf(numbers);

// var streamCopy = java.util.List.copyOf(numbers.stream());
// Stream không implement Collection
var streamResult = numbers.stream().toList(); // List<Integer>
```

Với các ví dụ có `var`, kiểu kết quả được suy luận từ initializer; dùng IDE hover hoặc `javac` để đọc lỗi thay vì suy đoán.

## 12. Hiệu năng và an toàn khi dùng Collection lớn

`List.copyOf` phải tạo kết quả biểu diễn các phần tử hiện tại của collection, trừ trường hợp implementation có thể tái sử dụng một List không cho sửa phù hợp. **Không giả định luôn tạo mới hoặc luôn tái sử dụng**.

- Sao chép một collection lớn có chi phí duyệt/chuẩn bị dữ liệu; cân nhắc khi gọi nhiều lần trong đường xử lý nóng.
- Không dựa vào chi tiết lớp implementation của kết quả (ví dụ ép về `ArrayList`); chỉ dựa vào hợp đồng `List<E>`.
- Trong môi trường nhiều thread, không cho rằng `copyOf` tự khóa nguồn mutable và chụp snapshot nguyên tử. Phối hợp truy cập hoặc tạo dữ liệu ổn định trước khi sao chép khi cần tính nhất quán.
- Danh sách không cho sửa không làm cho một phần tử mutable trở nên thread-safe.
- Nguồn có thứ tự không được bảo đảm sẽ làm kết quả có thứ tự tùy nguồn; khi ứng dụng cần thứ tự xác định, hãy áp dụng quy tắc sort hoặc chọn collection duy trì thứ tự ngay từ đầu.

Đây là các điểm thiết kế và đo đạc của ứng dụng hiện đại; không cần dựa vào chi tiết triển khai JVM của một phiên bản cụ thể.

## 13. Bài tập có đáp án

**Bài 1 — Đọc generic.** Với:

```java
java.util.Collection<Integer> source = java.util.List.of(1, 2);
java.util.List<Number> copied = java.util.List.copyOf(source);
```

Vì sao hợp lệ? **Đáp án:** đặt `E = Number`; `Collection<Integer>` tương thích với `Collection<? extends Number>`. Danh sách kết quả có kiểu `List<Number>` và chứa hai giá trị số ban đầu.

**Bài 2 — Suy luận bằng `var`.**

```java
java.util.Collection<? extends Number> source =
        java.util.List.of(1, 2);
var copied = java.util.List.copyOf(source);
```

Kiểu của `copied`? **Đáp án:** `List<? extends Number>`. Biến có thể đọc phần tử như `Number`; không gán trực tiếp nó cho `List<Number>`. Nếu cần `List<Number>`, dùng kiểu đích rõ lúc gọi `copyOf`.

**Bài 3 — Nguồn Set và thứ tự.**

```java
var names = new java.util.LinkedHashSet<>(
        java.util.List.of("A", "B", "A"));
var output = java.util.List.copyOf(names);
```

`output` là gì? **Đáp án:** `List<String>` chứa `[A, B]`. Set đã loại trùng, LinkedHashSet giữ thứ tự chèn; `copyOf` không tự loại trùng hoặc sắp xếp.

**Bài 4 — Nguồn Map.** Vì sao `List.copyOf(map)` sai nhưng `List.copyOf(map.values())` có thể hợp lệ? **Đáp án:** `Map` không phải `Collection`; `values()` trả một Collection các giá trị. Thứ tự duyệt tùy hợp đồng của implementation Map.

**Bài 5 — Mutable source.**

```java
var source = new java.util.ArrayList<>(
        java.util.List.of("a", "b"));
var copy = java.util.List.copyOf(source);
source.add("c");
```

`copy` và `source` lần lượt là gì? **Đáp án:** `copy` có `[a, b]`; `source` có `[a, b, c]`. Không thể sửa `copy` bằng `add`.

**Bài 6 — Phần tử mutable.**

```java
var buffer = new StringBuilder("a");
var copy = java.util.List.copyOf(
        java.util.List.of(buffer));
buffer.append("b");
```

`copy.get(0).toString()` là gì? **Đáp án:** `"ab"`. `copyOf` là bản sao nông, vẫn chia sẻ đối tượng `StringBuilder`.

**Bài 7 — So sánh factory.**

```java
var source = java.util.List.of("A", "B");
var a = java.util.List.of(source);
var b = java.util.List.copyOf(source);
```

Kiểu và nội dung? **Đáp án:** `a` có kiểu `List<List<String>>` và một phần tử chính là `source`; `b` có kiểu `List<String>` chứa hai chuỗi `A`, `B`.

## 14. Checklist áp dụng trong dự án

Trước khi dùng `List.copyOf`, tự kiểm tra:

1. **Nguồn có phải `Collection`?** Nếu là Map/Stream/array/Iterable, chọn cách chuyển dữ liệu hợp lý.
2. **Kiểu phần tử là gì?** Xác định `E`, nguồn `? extends E` và kiểu của biến trả về; lưu ý khác biệt giữa `var` và kiểu đích tường minh.
3. **Có thể có `null` không?** Nếu có, cân nhắc hợp đồng dữ liệu thay vì trông chờ copyOf chấp nhận.
4. **Thứ tự có quan trọng không?** Đừng dựa vào thứ tự của Set/Map không có bảo đảm.
5. **Có cần sửa danh sách sau đó không?** Nếu cần, dùng một collection mutable phù hợp, chẳng hạn `new ArrayList<>(source)`.
6. **Có cần snapshot hay chỉ read-only view?** `copyOf` thích hợp khi muốn tránh thay đổi về cấu trúc nguồn sau đó.
7. **Phần tử có mutable không?** Nếu có, `copyOf` chưa tạo bất biến sâu.
8. **Nguồn có bị truy cập/sửa đồng thời không?** Không tự coi `copyOf` là cơ chế đồng bộ hóa.
9. **Có đang phụ thuộc danh tính object hoặc lớp triển khai không?** Tránh `==` và cast implementation.
10. **Ví dụ có được biên dịch theo JDK dự án không?** Java 17+ chạy toàn bộ các chương trình hoàn chỉnh ở trên; `Stream.toList()` yêu cầu Java 16 trở lên.

**Ghi nhớ:** `List.copyOf` có chữ ký `<E> List<E> copyOf(Collection<? extends E>)` để nhận nhiều loại nguồn `Collection` an toàn kiểu. Nó trả một `List` không cho sửa và không chứa `null`, theo thứ tự iterator nguồn, với các tham chiếu phần tử được sao chép nông. Đọc đúng generic type, chọn nguồn có thứ tự phù hợp và hiểu ranh giới giữa snapshot cấu trúc với tính mutable của phần tử là nền tảng để sử dụng API này chính xác.