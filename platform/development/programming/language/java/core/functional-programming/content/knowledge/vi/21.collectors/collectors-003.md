# `Collectors.toList()` không cam kết kiểu triển khai hoặc khả năng sửa

## 1. Vấn đề và mục tiêu

Khi làm việc với Java Stream, ta thường thu kết quả bằng:

~~~java
List<String> names = Stream.of("An", "Binh", "Chi")
        .collect(Collectors.toList());
~~~

Dòng này tạo một `List<String>` chứa các phần tử từ Stream. Nhưng từ chữ ký và Javadoc, **không thể kết luận danh sách chắc chắn là `ArrayList`, chắc chắn sửa được, có thể serialize hay an toàn đa luồng**. Hợp đồng `Collectors.toList()` không cam kết bốn đặc tính ấy. Một bản JDK cụ thể hiện có thể trả `ArrayList` và cho phép gọi `add`, nhưng đó **không phải bảo đảm API** mà chương trình nên phụ thuộc.

Nội dung bài học thuộc nhóm *Thu thập kết quả* và giải quyết câu hỏi: **khi cần List có một đặc tính cụ thể, chọn đúng collector hay terminal operation nào?**

Sau bài này, người học cần:

1. Giải thích đúng hợp đồng của `Collectors.toList()` và giới hạn của việc thử nghiệm trên một JVM.
2. Phân biệt `collect(Collectors.toList())` với `Stream.toList()`, `Collectors.toUnmodifiableList()` và `Collectors.toCollection(ArrayList::new)`.
3. Chọn **mutable List**, **unmodifiable List**, loại triển khai cụ thể hoặc snapshot cấu trúc có chủ đích.
4. Hiểu chính sách `null`, encounter order, phần tử trùng, generic và Stream song song.
5. Phân biệt unmodifiable List với **immutable element**, và `Collections.unmodifiableList` view với `List.copyOf`.
6. Tránh ép kiểu `ArrayList`, dựa vào class runtime, gọi `add` khi không được cam kết và thay thế API khác hợp đồng chỉ vì cùng tên `toList`.
7. Chạy chương trình Java 17 độc lập, so sánh đầu ra và làm bài tập áp dụng.

## 2. Hợp đồng của `Collectors.toList()`

### 2.1. Đây là một Collector, không phải method của List

~~~java
List<String> result = Stream.of("b", "a", "b")
        .collect(Collectors.toList());
~~~

Trong ví dụ trên, `Collectors.toList()` tạo ra một `Collector` dùng làm đối số cho terminal operation `Stream.collect(...)`. Kết quả là `List<String>`. Với nguồn ordered `Stream.of(...)`, các phần tử có thứ tự `[b, a, b]`. Collector không tự xóa trùng hoặc sắp xếp.

Ví dụ muốn lọc trùng và sort, cần thể hiện rõ thao tác:

~~~java
List<String> result = Stream.of("b", "a", "b")
        .distinct()
        .sorted()
        .collect(Collectors.toList());

System.out.println(result); // [a, b]
~~~

Những đoạn này là mảnh mã đặt trong phương thức, cần import `java.util.List`, `java.util.stream.Stream` và `java.util.stream.Collectors`.

### 2.2. Bốn đặc tính không được cam kết

Javadoc `Collectors.toList()` nói **không có bảo đảm** về:

| Đặc tính | Điều không được phép suy ra |
| --- | --- |
| **Type** | List được trả chắc chắn là `ArrayList`, `LinkedList` hoặc một class cụ thể |
| **Mutability** | `add`, `remove`, `set` chắc chắn thành công hoặc chắc chắn bị chặn |
| **Serializability** | List luôn có thể Java-serialize |
| **Thread safety** | List có thể sửa hoặc đọc/ghi đồng thời từ nhiều thread mà không cần cơ chế bảo vệ |

Bốn đặc tính này độc lập. Một `ArrayList` mutable thường không thread-safe; một List unmodifiable có thể chứa phần tử mutable; và khả năng serialization không được quyết định chỉ bằng tên interface `List`.

**Ý nghĩa thiết kế:** `List<T>` là kiểu tĩnh cho phép viết `list.add(value)` về mặt cú pháp, nhưng lời gọi có thành công hay không phụ thuộc hợp đồng của object thực tế. Khi API chỉ hứa `List` mà không hứa mutable, code không được coi `add` là hành vi chắc chắn.

### 2.3. `getClass()` không nâng implementation thành hợp đồng

~~~java
List<String> result = Stream.of("A")
        .collect(Collectors.toList());
System.out.println(result.getClass().getName());
~~~

Đây là **mã minh họa không có stdout cố định theo đặc tả**. Trên một JDK, nó có thể in một tên class cụ thể, nhưng Javadoc không bắt buộc mọi JDK/version đều trả class đó.

Tương tự, thử `result.add("B")` thành công trên máy cá nhân không đủ để viết một thư viện cam kết behavior ấy. Nếu yêu cầu mutable, chọn nguồn tạo collection rõ ràng; nếu cần unmodifiable, dùng API có bảo đảm tương ứng.

## 3. So sánh những cách thu List dễ nhầm lẫn

| API trên Java 17 | Kiểu kết quả | Cam kết về sửa List | Điều cần nhớ |
| --- | --- | --- | --- |
| `stream.collect(Collectors.toList())` | `List<T>` | **Không cam kết** | Không hứa concrete type, serialization, thread safety |
| `stream.toList()` | `List<T>` | **Unmodifiable** | Từ Java 16; có thể chứa `null` |
| `stream.collect(Collectors.toUnmodifiableList())` | `List<T>` | **Unmodifiable** | Từ Java 10; không chấp nhận phần tử `null` |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` hoặc biến `List<T>` | **Mutable ArrayList** | Chọn implementation qua supplier |
| `stream.collect(Collectors.toCollection(LinkedList::new))` | `LinkedList<T>` hoặc biến `List<T>` | **Mutable LinkedList** | Chọn khi thực sự cần |

**Tên gần giống không có nghĩa hợp đồng giống nhau.** `Stream.toList()` là terminal operation của `Stream`, còn `Collectors.toList()` là factory cho `Collector`, dùng với `collect(...)`.

### 3.1. Dùng `Collectors.toList()` khi không cần cam kết bổ sung

~~~java
List<String> words = Stream.of("Java", "Lambda")
        .collect(Collectors.toList());
System.out.println(words); // [Java, Lambda]
~~~

Nếu chỉ đọc, đếm, lặp, hoặc truyền list cho code không dựa vào việc sửa/kiểu cụ thể, collector này hợp lý. Không cần thay nó trong mọi codebase chỉ vì Javadoc không cam kết mutable.

Tuy nhiên, nếu API của bạn yêu cầu người gọi **không thể sửa** kết quả, `Collectors.toList()` cũng không phù hợp vì nó **không cam kết unmodifiable**.

### 3.2. `Stream.toList()` cam kết unmodifiable

~~~java
List<String> words = Stream.of("Java", "Lambda").toList();

// Lời gọi sau ném UnsupportedOperationException khi thực thi:
// words.add("Stream");
~~~

`Stream.toList()` từ Java 16 trở lên trả List unmodifiable. Không được thay `toList()` bằng `collect(Collectors.toList())` rồi tiếp tục khẳng định caller không thể sửa.

Unmodifiable **không đồng nghĩa** class phải là `List.of(...)`, cũng không tự biến các object bên trong thành bất biến.

### 3.3. `Collectors.toUnmodifiableList()` và quy tắc null

~~~java
List<String> words = Stream.of("Java", "Lambda")
        .collect(Collectors.toUnmodifiableList());
~~~

Collector này tạo List unmodifiable và **từ chối giá trị `null`**, ném `NullPointerException` nếu gặp. Đây là khác biệt thực tế với `Stream.toList()`, vốn cho phép phần tử null theo Java 17.

### 3.4. Cần mutable `ArrayList`: dùng `toCollection`

~~~java
ArrayList<String> words = Stream.of("Java", "Lambda")
        .collect(Collectors.toCollection(ArrayList::new));

words.add("Stream");
System.out.println(words); // [Java, Lambda, Stream]
~~~

Factory `ArrayList::new` là cách nói rõ loại collection cần tạo. `ArrayList` hỗ trợ mutation; ví dụ `add` được bảo đảm theo hợp đồng ArrayList khi không có yếu tố ngoại lệ khác như thiếu bộ nhớ.

Nếu chỉ muốn expose interface, vẫn có thể viết:

~~~java
List<String> words = Stream.of("Java", "Lambda")
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Biến là `List<String>` nhưng supplier tạo `ArrayList`. Điều này giúp API phía ngoài giảm phụ thuộc implementation trong khi logic bên trong biết danh sách có thể sửa.

### 3.5. Chỉ chọn `LinkedList` khi có lý do

~~~java
LinkedList<String> words = Stream.of("A", "B")
        .collect(Collectors.toCollection(LinkedList::new));
~~~

`LinkedList` không tự tốt hơn `ArrayList`. Cần cân nhắc kiểu truy cập, kích thước, memory, số lần thêm/xóa và đo trên workload phù hợp khi hiệu năng thực sự quan trọng.

## 4. Chương trình Java 17 hoàn chỉnh

Tạo tệp **`ListCollectorsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ListCollectorsDemo {
    public static void main(String[] args) {
        // 1. Thu List nhưng không phụ thuộc class hoặc mutability.
        List<String> collected = Stream.of("b", "a", "b")
                .collect(Collectors.toList());
        System.out.println("collected=" + collected);

        // 2. Yêu cầu rõ mutable ArrayList.
        List<String> mutable = Stream.of("b", "a")
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add("c");
        System.out.println("mutable=" + mutable);

        // 3. Stream.toList() cam kết unmodifiable.
        List<String> immutable = Stream.of("b", "a").toList();
        try {
            immutable.add("c");
        } catch (UnsupportedOperationException ex) {
            System.out.println("toList-add=blocked");
        }

        // 4. toUnmodifiableList() cũng không cho sửa.
        List<String> unmodifiable = Stream.of("b", "a")
                .collect(Collectors.toUnmodifiableList());
        try {
            unmodifiable.set(0, "x");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable-set=blocked");
        }

        // 5. Phân biệt chính sách null.
        System.out.println(
                "nullable=" + Stream.of("x", null, "z").toList()
        );
        try {
            Stream.of("x", null)
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("collector-null=rejected");
        }

        // 6. Unmodifiable view và snapshot cấu trúc.
        List<String> backing = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(backing);
        List<String> snapshot = List.copyOf(backing);
        backing.add("B");
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        // 7. List unmodifiable vẫn chứa object mutable.
        StringBuilder builder = new StringBuilder("old");
        List<StringBuilder> readonly = Stream.of(builder).toList();
        builder.append("-new");
        System.out.println("element=" + readonly.get(0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ListCollectorsDemo.java
java ListCollectorsDemo
~~~

**Stdout chính xác (Java 17):**

~~~text
collected=[b, a, b]
mutable=[b, a, c]
toList-add=blocked
unmodifiable-set=blocked
nullable=[x, null, z]
collector-null=rejected
view=[A, B]
snapshot=[A]
element=old-new
~~~

### Giải thích đầu ra

1. `collected=[b, a, b]`: thu các phần tử nguồn có thứ tự, không loại trùng. Không kiểm tra concrete class hay `add` vì chúng không được cam kết bởi collector.
2. `mutable=[b, a, c]`: supplier tạo `ArrayList` nên `add` hợp lệ.
3. `toList-add=blocked`: `Stream.toList()` tạo List unmodifiable; gọi `add` phát sinh `UnsupportedOperationException`.
4. `unmodifiable-set=blocked`: `Collectors.toUnmodifiableList()` cũng từ chối `set`.
5. `nullable=[x, null, z]`: `Stream.toList()` cho phép chứa null.
6. `collector-null=rejected`: `Collectors.toUnmodifiableList()` từ chối null bằng `NullPointerException`.
7. `view=[A, B]`: `Collections.unmodifiableList` là view trên nguồn mutable, phản ánh thao tác thêm `B` từ reference gốc.
8. `snapshot=[A]`: `List.copyOf` tạo kết quả unmodifiable theo cấu trúc tại thời điểm copy; nguồn thêm `B` không đổi snapshot.
9. `element=old-new`: danh sách unmodifiable không cho sửa cấu trúc nhưng `StringBuilder` vẫn mutable.

Chương trình minh họa hành vi API được **cam kết**, ngoại trừ cụ thể kết quả thu là `[b,a,b]` vốn dựa trên encounter order của `Stream.of`. Không sử dụng `getClass()` hoặc việc mutating `Collectors.toList()` để đưa ra một kết luận không có hợp đồng.

## 5. Unmodifiable, immutable và snapshot không giống nhau

### 5.1. Unmodifiable là ở cấp List

~~~java
StringBuilder builder = new StringBuilder("A");
List<StringBuilder> list = Stream.of(builder).toList();

builder.append("B");
System.out.println(list.get(0)); // AB
~~~

`list.add(...)` không được hỗ trợ, nhưng sửa `builder` vẫn được. List giữ tham chiếu đến phần tử; nó **không tạo deep copy**. Vì vậy, nếu hợp đồng là dữ liệu bất biến thực sự, cần kiểm soát cả kiểu phần tử và quyền tham chiếu từ bên ngoài.

### 5.2. `Collections.unmodifiableList` là view

~~~java
List<String> backing = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(backing);

backing.add("B");
System.out.println(view); // [A, B]
~~~

Wrapper không cho phép sửa **qua view**, nhưng nếu backing list thay đổi qua reference khác thì người dùng view có thể thấy thay đổi. Điều này không phải snapshot.

### 5.3. `List.copyOf` cho snapshot cấu trúc

~~~java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);

source.add("B");
System.out.println(snapshot); // [A]
~~~

Với nguồn ArrayList mutable, cấu trúc snapshot không đổi sau khi source thêm `B`. Tuy nhiên, `List.copyOf` chỉ sao chép tham chiếu element, không deep-copy object mutable. Nó cũng từ chối null. Nếu nguồn đã là một unmodifiable List phù hợp, Java có thể trả lại cùng instance thay vì tạo object mới; **không dựa vào identity khác nhau**.

### 5.4. Kết hợp collector với bước finishing

~~~java
List<String> result = Stream.of("A", "B")
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

Bước đầu tạo `ArrayList` theo supplier; bước sau tạo List unmodifiable bằng `List.copyOf`. Cách này hữu ích khi có logic finishing, nhưng nếu chỉ cần List unmodifiable và không chứa null, `Collectors.toUnmodifiableList()` thường ngắn hơn.

Không nên xây chuỗi collector phức tạp chỉ để thay một lời gọi `Stream.toList()` đơn giản khi không có nhu cầu thêm.

## 6. Null policy là lựa chọn riêng

| Cách thu | Chính sách null |
| --- | --- |
| `Stream.toList()` | Có thể chứa `null` trên Java 17 |
| `Collectors.toUnmodifiableList()` | Từ chối `null` |
| `Collectors.toCollection(ArrayList::new)` | Cho phép `null`, theo hợp đồng ArrayList |
| `List.of(...)` | Từ chối `null` |
| `List.copyOf(...)` | Từ chối phần tử `null` |
| `Collectors.toList()` | Không nên xây yêu cầu null theo suy đoán từ class implementation |

Mảnh mã cần danh sách **mutable và cho phép null**:

~~~java
List<String> values = Stream.of("A", null, "B")
        .collect(Collectors.toCollection(ArrayList::new));
values.add(null);
~~~

Nếu yêu cầu từ chối dữ liệu null, hãy nêu chính sách rõ trong API. Không tự ý `filter(Objects::nonNull)` nếu bỏ phần tử null có thể che mất dữ liệu sai: **bỏ qua** và **báo lỗi** là hai hành vi khác nhau.

### 6.1. Null và unmodifiable độc lập

Một List có thể **unmodifiable nhưng chứa null** như `Stream.of("A", null).toList()`. Một List mutable như ArrayList cũng có thể không chứa null đơn giản vì dữ liệu đầu vào không có null. Không suy luận chính sách null chỉ từ tính mutability.

## 7. Encounter order, duplicate và kết quả song song

### 7.1. Collector không sort, không distinct

~~~java
List<String> input = List.of("B", "A", "B");

List<String> result = input.stream()
        .collect(Collectors.toList());

System.out.println(result); // [B, A, B]
~~~

Nếu cần `[A, B]`, dùng:

~~~java
List<String> result = input.stream()
        .distinct()
        .sorted()
        .collect(Collectors.toList());
~~~

`distinct` loại phần tử trùng theo `equals`; `sorted` sắp theo thứ tự tự nhiên, với điều kiện kiểu phần tử hỗ trợ so sánh và dữ liệu phù hợp.

### 7.2. Nguồn unordered không cho thứ tự tùy ý

~~~java
Set<String> set = new HashSet<>(List.of("A", "B", "C"));
List<String> result = set.stream()
        .collect(Collectors.toList());
~~~

Đây là mảnh mã trong method, cần import `java.util.Set` và `HashSet`. `HashSet` không cam kết encounter order, nên **không viết stdout cụ thể** cho thứ tự phần tử thu được. Muốn kết quả theo bảng chữ cái, gọi `sorted()` trước `collect(...)`.

### 7.3. Parallel collect khác thread-safe List

~~~java
List<Integer> numbers = IntStream.range(0, 100)
        .parallel()
        .boxed()
        .collect(Collectors.toList());
~~~

Stream framework điều phối thu kết quả đúng với collector và thứ tự nguồn; việc pipeline có thể chạy song song **không làm danh sách kết quả được cam kết thread-safe**. Không nên chia sẻ để các thread cùng mutate List mà không có đồng bộ phù hợp.

Anti-pattern:

~~~java
List<Integer> shared = new ArrayList<>();
IntStream.range(0, 100)
        .parallel()
        .forEach(shared::add);
~~~

`ArrayList` chung bị mutate từ nhiều thread nên có nguy cơ race, thiếu phần tử và trạng thái không nhất quán. Thay bằng:

~~~java
List<Integer> numbers = IntStream.range(0, 100)
        .parallel()
        .boxed()
        .toList();
~~~

Nếu cần mutable result, dùng `collect(Collectors.toCollection(ArrayList::new))`. Không sử dụng `parallel().forEach` để tự xây collection ngoài pipeline.

## 8. Không cast kết quả thành `ArrayList`

Đoạn rủi ro:

~~~java
ArrayList<String> values = (ArrayList<String>)
        Stream.of("A", "B").collect(Collectors.toList());
~~~

Có thể chạy trên một JDK đang trả ArrayList nhưng **không được hợp đồng bảo đảm**. Nếu implementation thay đổi, phép cast có thể ném `ClassCastException`. Cast cũng không biến một List chưa biết thành mutable hay thread-safe.

Cách tường minh:

~~~java
ArrayList<String> values = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Hoặc khi cần sao chép từ List do API khác trả:

~~~java
List<String> external = service.getNames();
List<String> mutableCopy = new ArrayList<>(external);
mutableCopy.add("new");
~~~

Đoạn thứ hai là **mẫu minh họa**, cần `service.getNames()` được định nghĩa trong ứng dụng thực tế. Copy cấu trúc bảo đảm list mới mutable, nhưng các phần tử object vẫn được chia sẻ tham chiếu.

## 9. Khác biệt về generic type inference

Hai API còn có thể khác ở cách suy luận generic.

~~~java
List<CharSequence> a = Stream.of("A", "B")
        .collect(Collectors.toList());
~~~

Trong Java 17, compiler có thể suy luận kiểu của collector từ target type trong lời gọi `collect`.

Nhưng:

~~~java
// Lỗi: Stream<String>.toList() trả List<String>.
List<CharSequence> b = Stream.of("A", "B").toList();
~~~

`List<String>` không phải subtype của `List<CharSequence>` vì generic Java bất biến (*invariance*). Sửa bằng kiểu element tường minh:

~~~java
List<CharSequence> b =
        Stream.<CharSequence>of("A", "B").toList();
~~~

Đừng dùng raw `List` hay cast `(List<CharSequence>)(List<?>)...` để né compiler. Việc API có khả năng suy luận khác không làm thay đổi sự thật rằng `Collectors.toList()` vẫn không cam kết mutable hoặc class.

## 10. Downstream collector trong `groupingBy`

`Collectors.toList()` có ích khi là downstream collector:

~~~java
record Person(String name, String team) {}

List<Person> people = List.of(
        new Person("An", "A"),
        new Person("Binh", "B"),
        new Person("Chi", "A")
);

Map<String, List<Person>> groups = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.toList()));
~~~

Đây là mảnh mã trong class và method, cần import `List`, `Map`, `Collectors`. Các thành viên nhóm A gồm An, Chi; nhóm B gồm Binh. Nhưng List của **mỗi nhóm** cũng chỉ có bảo đảm của `Collectors.toList()`: không cam kết mutable hoặc concrete type.

Nếu cần mỗi nhóm là ArrayList mutable:

~~~java
Map<String, List<Person>> groups = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.toCollection(ArrayList::new)));
~~~

Tương tự, `groupingBy` không tự cam kết một loại Map cụ thể trong các overload không có map factory. Nếu API cần map implementation, dùng overload nhận supplier rõ ràng. Khi dữ liệu lồng nhau, unmodifiable ở cấp List không tự bảo vệ Map và ngược lại; cần xác định hợp đồng cho từng tầng.

## 11. Bảng chọn API theo mục đích

| Bạn muốn | Chọn | Vì sao |
| --- | --- | --- |
| Thu List rồi chỉ đọc, không cần concrete type | `collect(Collectors.toList())` | Không yêu cầu các bảo đảm thiếu |
| List unmodifiable, Java 16+, có thể có null | `stream.toList()` | Cam kết unmodifiable |
| Collector unmodifiable và từ chối null | `collect(Collectors.toUnmodifiableList())` | Cam kết và null policy rõ |
| Mutable ArrayList | `collect(Collectors.toCollection(ArrayList::new))` | Supplier xác định loại |
| Mutable LinkedList | `collect(Collectors.toCollection(LinkedList::new))` | Supplier xác định loại |
| Mutable copy từ List ngoài | `new ArrayList<>(external)` | Tạo bản riêng, thay được cấu trúc |
| Snapshot cấu trúc unmodifiable, không null | `List.copyOf(source)` | Không phản ánh mutation cấu trúc sau đó |
| Unmodifiable view lên backing List | `Collections.unmodifiableList(source)` | Chặn sửa qua view, không snapshot |
| Gom nhóm với downstream List | `groupingBy(key, toList())` hoặc `toCollection` | Chọn hợp đồng cho List từng nhóm |

**Không có một phương án tốt nhất cho mọi code.** `Collectors.toList()` hợp lý khi không phụ thuộc vào các thuộc tính mà nó không hứa. Lỗi nằm ở việc **gán cho nó một cam kết không được Javadoc đưa ra**.

## 12. Những lỗi phổ biến

### 12.1. Gọi `add` với giả định luôn hoạt động

~~~java
List<String> result = values.stream()
        .collect(Collectors.toList());

// Không được dựa vào việc dòng sau luôn thành công:
result.add("new");
~~~

Nếu yêu cầu thêm phần tử, chọn `toCollection(ArrayList::new)` hoặc copy mutable. Nếu chỉ cần thu, không nhất thiết phải thay collector.

### 12.2. Cast theo implementation hiện tại

~~~java
ArrayList<String> a = (ArrayList<String>)
        values.stream().collect(Collectors.toList());
~~~

Có nguy cơ `ClassCastException` khi môi trường thay đổi. Chọn supplier rõ hoặc bỏ sự phụ thuộc vào class.

### 12.3. Cho rằng unmodifiable đồng nghĩa immutable sâu

~~~java
List<StringBuilder> list =
        Stream.of(new StringBuilder("A")).toList();
list.get(0).append("B"); // Element thay đổi.
~~~

List không cho thêm/xóa/đổi element qua List API, nhưng object phần tử có thể mutate. Nếu yêu cầu immutable thực sự, thiết kế kiểu element hoặc deep copy.

### 12.4. Cho rằng Parallel Stream trả List thread-safe

`parallel()` là một cách tổ chức chạy pipeline, không phải yêu cầu thread-safe List kết quả. `Collectors.toList()` không hứa kết quả concurrent-safe. Đánh giá đồng bộ khi List thực sự được chia sẻ giữa thread.

### 12.5. Nhầm `List.copyOf` với view

`List.copyOf(source)` tạo kết quả unmodifiable theo cấu trúc hiện tại của source. `Collections.unmodifiableList(source)` là wrapper nhìn vào backing list. Nếu nguồn thay đổi sau đó, view phản ánh còn snapshot không phản ánh thay đổi cấu trúc.

### 12.6. Thay `Stream.toList()` bằng collector cùng tên

Sửa `stream.toList()` thành `stream.collect(Collectors.toList())` có thể làm mất bảo đảm unmodifiable. Ngược lại, thay collector bằng method có thể khiến code dựa vào việc sửa danh sách thất bại. Đọc hợp đồng trước khi refactor.

## 13. Bài tập và gợi ý

**Bài 1 — Nêu đúng hợp đồng.** Với `Stream.of("A","B").collect(Collectors.toList())`, hãy kể tên bốn thuộc tính không được bảo đảm. Đáp án: concrete implementation, mutability, serializability, thread safety.

**Bài 2 — Mutable List.** Thu `["Java","Stream"]` và thêm `"API"`. Viết `Collectors.toCollection(ArrayList::new)`; kết quả `[Java, Stream, API]`. Giải thích vì sao `Collectors.toList()` không nên là nguồn của một cam kết `add` luôn thành công.

**Bài 3 — Unmodifiable.** Thu bằng `Stream.toList()`, thử `add` và `set` trong `try/catch (UnsupportedOperationException)`. So sánh với hợp đồng của `Collectors.toList()`.

**Bài 4 — Chính sách null.** Với `Stream.of("A",null,"B")`, thử `toList()`, `toUnmodifiableList()` và `toCollection(ArrayList::new)`. Nêu kết quả hoặc exception, chọn cách phù hợp khi nghiệp vụ chấp nhận null.

**Bài 5 — View và snapshot.** Tạo `ArrayList` một phần tử, tạo `Collections.unmodifiableList` và `List.copyOf`, thêm phần tử vào backing. Dự đoán nội dung hai danh sách.

**Bài 6 — Element mutable.** Thu `StringBuilder` bằng `Stream.toList()` rồi đổi nội dung `StringBuilder`. Giải thích tại sao kết quả vẫn thay đổi và gợi ý thay bằng `String` nếu cần snapshot giá trị.

**Bài 7 — Ordered và unordered.** So sánh List kết quả từ `List.stream()` và `HashSet.stream()`; chỉ ra vì sao không được khẳng định thứ tự của HashSet. Thêm `sorted()` để có thứ tự định nghĩa được.

**Bài 8 — Parallel.** Chạy `IntStream.range(0,1000).parallel().boxed().toList()`; kiểm tra kích thước 1000 và phần tử đầu/cuối. So sánh với việc dùng `parallel().forEach(shared::add)` trên ArrayList chung và nêu rủi ro.

**Bài 9 — Grouping.** Tạo `record Person(String name,String team)`. Gom nhóm bằng `groupingBy(Person::team,toList())`, rồi bằng `groupingBy(Person::team,toCollection(ArrayList::new))`. Khi nào cần loại thứ hai?

**Bài 10 — Generic.** Thử `List<CharSequence> x = Stream.of("a").collect(Collectors.toList());` và `List<CharSequence> y = Stream.of("a").toList();`. Giải thích khác biệt suy luận type và sửa dòng thứ hai bằng `Stream.<CharSequence>of("a").toList()`.

**Bài 11 — Thiết kế API.** Một service trả danh sách cho frontend hoặc plugin. Trước khi chọn cách thu, xác định caller có được sửa, có cần null, có cần snapshot, phần tử có mutable, và danh sách có bị chia sẻ giữa thread không. Viết test cho những bảo đảm bạn thực sự yêu cầu.

## 14. Checklist rà soát

1. Bạn đang dùng `Collectors.toList()` hay `Stream.toList()`? Hai API không cùng hợp đồng mutability.
2. Có yêu cầu `add`/`remove`/`set` luôn thành công? Nếu có, chọn collection mutable tường minh.
3. Có cast kết quả collector sang `ArrayList` vì quan sát `getClass()` không?
4. Có yêu cầu List unmodifiable cho caller? Nếu có, dùng API có bảo đảm rõ.
5. Có hiểu chính sách `null`? `toUnmodifiableList` và `List.copyOf` từ chối null.
6. Có cần snapshot hay unmodifiable view? Hai khái niệm khác nhau.
7. Phần tử là mutable object không? Unmodifiable List không deep-copy.
8. Có yêu cầu serialize hoặc thread safety không? `Collectors.toList()` không cam kết.
9. Nguồn có encounter order không? Nếu cần thứ tự xác định, có thêm `sorted` phù hợp?
10. Có đang dùng `parallel().forEach` mutate collection chung không?
11. Có List do `groupingBy(...,toList())` tạo không? Không tự giả định các List con mutable.
12. Code phụ thuộc contract hay chi tiết implementation của một bản JDK?

## 15. Tổng kết và tài liệu tra cứu

**`Collectors.toList()` trả List nhưng không cam kết concrete type, mutability, serializability hay thread safety.** Dù một implementation hiện tại có thể trả `ArrayList` sửa được, không viết code phụ thuộc vào điều đó.

Khi cần **List unmodifiable**, `Stream.toList()` từ Java 16 trở lên có hợp đồng rõ và có thể chứa null; `Collectors.toUnmodifiableList()` cũng unmodifiable nhưng từ chối null. Khi cần **ArrayList mutable**, dùng `Collectors.toCollection(ArrayList::new)` hoặc tạo `new ArrayList<>(source)`. Khi cần **snapshot cấu trúc**, xem xét `List.copyOf`; khi cần wrapper unmodifiable phản ánh backing, dùng `Collections.unmodifiableList`.

Cuối cùng, **unmodifiable không đồng nghĩa deep immutable**, và quá trình thu bằng Stream song song không bảo đảm danh sách kết quả an toàn cho concurrent mutation. Chọn theo yêu cầu API thay vì dựa vào hành vi quan sát được ở một môi trường.

**Nguồn chuẩn:** Javadoc Java SE 17 của `java.util.stream.Collectors` (`toList`, `toUnmodifiableList`, `toCollection`, `groupingBy`), `java.util.stream.Stream.toList`, `java.util.List.copyOf`, `java.util.Collections.unmodifiableList` và `java.util.ArrayList`.
