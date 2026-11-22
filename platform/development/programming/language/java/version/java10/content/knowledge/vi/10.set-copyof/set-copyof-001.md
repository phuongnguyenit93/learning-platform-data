# Chữ ký generic và nguồn `Collection` của `Set.copyOf` trong Java

## Mục tiêu bài học

`Set.copyOf` được bổ sung từ **Java 10** và vẫn là một API chuẩn của Java hiện đại. Phương thức này tạo một `Set` **không cho sửa** từ các phần tử của một `Collection` hiện có. Điểm cần hiểu sâu là chữ ký generic `Collection<? extends E>`: nó quyết định loại nguồn có thể truyền vào, cách suy luận kiểu `E`, và kiểu `Set<E>` nhận về.

Sau bài này, bạn có thể:

- Đọc chính xác chữ ký `static <E> Set<E> copyOf(Collection<? extends E> coll)`.
- Phân biệt **`Collection`**, **`Iterable`**, **`Iterator`**, `Map`, mảng và `Stream` khi truyền nguồn cho `copyOf`.
- Giải thích wildcard `? extends E`, tính bất biến của generic và cách mở rộng kiểu từ `Integer` lên `Number`.
- Dùng khai báo tường minh, `var` hoặc type witness `Set.<Number>copyOf(...)` đúng mục đích.
- Hiểu cách xử lý phần tử trùng, `null`, snapshot, thứ tự duyệt và phần tử mutable.

Các ví dụ dùng cú pháp Java 17+, không dùng API đã lỗi thời.

## 1. Đọc từng phần của chữ ký

Chữ ký trong `java.util.Set`:

~~~java
static <E> Set<E> copyOf(Collection<? extends E> coll)
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `static` | Gọi trực tiếp trên interface `Set`: `Set.copyOf(source)` |
| `<E>` trước `Set<E>` | **Khai báo tham số kiểu của phương thức**; `E` được suy luận hoặc chỉ định tại lời gọi |
| `Set<E>` | Kiểu trả về: tập hợp có kiểu phần tử `E` |
| `Collection<? extends E>` | Nguồn là một `Collection` mà mỗi phần tử có kiểu phù hợp với `E` hoặc kiểu con của `E` |
| `coll` | Đối số là nguồn phần tử; phải khác `null` và không chứa phần tử `null` |

Ví dụ:

~~~java
List<String> names = List.of("An", "Binh", "An");
Set<String> uniqueNames = Set.copyOf(names);
~~~

- `List<String>` triển khai `Collection<String>` nên là nguồn hợp lệ.
- Trình biên dịch suy luận `E = String`.
- Kết quả có kiểu `Set<String>`, chỉ chứa mỗi giá trị duy nhất một lần; ở đây `uniqueNames.size()` là **2**.
- `Set.copyOf` không giữ một con trỏ tới `List` để phản ánh các lần thêm/xóa về sau.

`copyOf` không phải phương thức thành viên của đối tượng `List`, cũng không yêu cầu nguồn phải có sẵn kiểu `Set`: bạn gọi `Set.copyOf(collection)` để nhận **một Set từ bất kỳ nguồn Collection tương thích nào**.

## 2. Vì sao tham số là `Collection<? extends E>`?

Đây là kiểu tham số có **upper-bounded wildcard**. Nếu chọn `E = Number`, tham số `Collection<? extends Number>` chấp nhận nguồn chứa `Number` hoặc các lớp con như `Integer`, `Double`.

~~~java
List<Integer> integers = List.of(1, 2, 3);

Set<Integer> integersOnly = Set.copyOf(integers);
Set<Number> numbers = Set.copyOf(integers);
~~~

Dòng thứ hai dùng **kiểu đích `Set<Number>`** để suy luận `E = Number`. Lời gọi hợp lệ vì nguồn `List<Integer>` phù hợp với `Collection<? extends Number>`.

Nếu chữ ký yêu cầu đúng `Collection<E>` mà không dùng wildcard, với `E = Number` thì `Collection<Integer>` sẽ không phù hợp, vì Java generics **bất biến (invariant)**:

~~~java
List<Integer> integers = List.of(1, 2);

// List<Number> wrong = integers; // Lỗi biên dịch
~~~

`Integer` là lớp con của `Number`, nhưng `List<Integer>` không phải kiểu con của `List<Number>`. Wildcard `? extends E` cho phép phương thức **đọc phần tử dưới góc nhìn kiểu `E`** mà không đòi hỏi collection nguồn phải có đúng cùng tham số kiểu.

Đây là trường hợp của nguyên tắc **Producer Extends**: nguồn `coll` cung cấp phần tử cho `copyOf`, vì vậy `? extends E` phù hợp. Điều này không có nghĩa bạn được phép tùy ý thêm `Number` vào `List<Integer>`.

## 3. Loại nguồn `Collection` nào được chấp nhận?

`Collection<E>` là interface cha của nhiều loại collection trong Java Collections Framework. `Set.copyOf` nhận một đối số có kiểu tương thích với `Collection<? extends E>`, trong đó có các trường hợp sau:

| Loại nguồn | Ví dụ | Hợp lệ? | Ghi chú |
| --- | --- | --- | --- |
| `List<String>` | `Set.copyOf(List.of("A", "B"))` | Có | Loại phần tử trùng |
| `ArrayList<Integer>` | `Set.copyOf(arrayList)` | Có | Kế thừa giao diện `Collection` qua `List` |
| `HashSet<String>` | `Set.copyOf(hashSet)` | Có | Nguồn đã có phần tử duy nhất |
| `LinkedHashSet<String>` | `Set.copyOf(linkedSet)` | Có | Kết quả **không bảo đảm giữ thứ tự duyệt** của nguồn |
| `Queue<String>` | `Set.copyOf(queue)` | Có | `Queue` kế thừa `Collection` |
| `ArrayDeque<String>` | `Set.copyOf(deque)` | Có | Deque là một Collection |
| `Collection<String>` | `Set.copyOf(collection)` | Có | Không cần biết implementation cụ thể |
| `Iterable<String>` (chỉ biết là Iterable) | `Set.copyOf(iterable)` | Không biên dịch trực tiếp | `Iterable` không nhất thiết là `Collection` |
| `Iterator<String>` | `Set.copyOf(iterator)` | Không biên dịch trực tiếp | `Iterator` không phải `Collection` |
| `String[]` | `Set.copyOf(array)` | Không biên dịch trực tiếp | Mảng không triển khai `Collection` |
| `Stream<String>` | `Set.copyOf(stream)` | Không biên dịch trực tiếp | `Stream` không phải `Collection` |
| `Map<K,V>` | `Set.copyOf(map)` | Không biên dịch trực tiếp | `Map` không kế thừa `Collection` |

**Lưu ý kiểu khai báo:** nếu một đối tượng ở runtime là `ArrayList<String>` nhưng biến được khai báo là `Iterable<String>`, lời gọi `Set.copyOf(variable)` vẫn không biên dịch chỉ dựa vào thông tin `Iterable`. Trình biên dịch kiểm tra **kiểu tĩnh** của đối số.

### Chuyển nguồn khác về một `Collection` hợp lệ

Với mảng đối tượng:

~~~java
String[] names = {"An", "Binh", "An"};
var uniqueNames = Set.copyOf(Arrays.asList(names)); // Set<String>
~~~

`Arrays.asList(names)` tạo một `List<String>`, nên truyền được cho `Set.copyOf`.

Với `Stream<String>` trên Java 17+:

~~~java
Stream<String> stream = Stream.of("A", "B", "A");
var unique = Set.copyOf(stream.toList()); // Set<String>
~~~

`Stream.toList()` trả về `List<String>`. Một `Stream` thường chỉ dùng cho một pipeline; nếu đã tiêu thụ stream thì không thể tái sử dụng nó tùy ý.

Với `Map<String, Integer>`:

~~~java
Map<String, Integer> scores = Map.of("An", 8, "Binh", 9);

var names = Set.copyOf(scores.keySet());   // Set<String>
var points = Set.copyOf(scores.values());  // Set<Integer>
var entries = Set.copyOf(scores.entrySet()); // Set<Map.Entry<String, Integer>>
~~~

`Map` không tự là `Collection`, nhưng các view `keySet()`, `values()`, `entrySet()` đều là những collection có kiểu phần tử phù hợp. `Set.copyOf` tạo kết quả không cho sửa từ **nội dung của view tại lúc gọi**, thay vì giữ một view theo dõi các thay đổi map nguồn.

Đối với mảng nguyên thủy `int[]`, không dùng `Arrays.asList(intArray)` để kỳ vọng nhận `List<Integer>`: nó coi toàn bộ mảng `int[]` là một phần tử. Có thể chuyển thành các đối tượng wrapper trước:

~~~java
int[] numbers = {1, 2, 2, 3};
var uniqueNumbers = Set.copyOf(
        Arrays.stream(numbers).boxed().toList()
); // Set<Integer>
~~~

## 4. Suy luận `E`: kiểu đích, `var` và type witness

**Trường hợp 1 — suy luận từ kiểu generic của nguồn:**

~~~java
List<Integer> source = List.of(1, 2, 2);
var result = Set.copyOf(source); // Set<Integer>
~~~

Vì `source` biểu lộ phần tử `Integer`, trình biên dịch có đủ thông tin để suy luận `E = Integer`. `var` nhận kiểu của biểu thức khởi tạo, không làm biến đổi Set thành raw type hay một kiểu động.

**Trường hợp 2 — mong muốn kiểu kết quả rộng hơn:**

~~~java
List<Integer> source = List.of(1, 2, 2);
Set<Number> numbers = Set.copyOf(source);
~~~

Kiểu đích `Set<Number>` giúp chọn `E = Number`; nguồn `List<Integer>` đáp ứng `Collection<? extends Number>`. Điều này không có nghĩa rằng `Set<Integer>` có thể được gán trực tiếp cho `Set<Number>`:

~~~java
Set<Integer> integers = Set.copyOf(List.of(1, 2));
// Set<Number> invalid = integers; // Lỗi biên dịch: generic invariant
~~~

**Trường hợp 3 — muốn giữ `var` nhưng chọn `E` rõ ràng:**

~~~java
List<Integer> source = List.of(1, 2);
var widened = Set.<Number>copyOf(source); // Set<Number>
~~~

Cú pháp `Set.<Number>copyOf(...)` là một **type witness** chỉ định đối số kiểu của phương thức generic. Dấu `<Number>` nằm **sau `Set.` và trước `copyOf`**, không nằm sau tên phương thức.

**Trường hợp 4 — nguồn chỉ biểu lộ kiểu quá rộng:**

~~~java
Collection<Object> source = List.of("A", "B");
var broad = Set.copyOf(source);           // Set<Object>
Set<Object> stillBroad = Set.copyOf(source);
~~~

Đừng giả định compiler quan sát giá trị cụ thể lúc chạy rồi tự suy ra `String`: kiểu tĩnh của `source` là `Collection<Object>`. Nếu muốn `Set<String>`, cần biểu diễn nguồn là collection có kiểu phần tử thích hợp hoặc thực hiện bước chuyển đổi/kiểm tra kiểu được thiết kế rõ ràng.

**Trường hợp 5 — cần kiểu rộng hơn nhưng không có type witness:**

~~~java
Collection<? extends Number> numbers = List.of(1, 2, 3);
Set<Number> copy = Set.copyOf(numbers);
~~~

Wildcard cũng được phép xuất hiện ở biến nguồn. Dòng cuối hợp lệ vì mọi phần tử mà nguồn cung cấp đều tương thích với `Number`.

**Không thể** dùng kiểu nguyên thủy làm type argument như `Set<int>`; Java generics cần kiểu tham chiếu, nên dùng `Integer`, `Long`, v.v.

## 5. Duplicate, `null` và thứ tự duyệt: kết quả phải hiểu đúng

### 5.1. Phần tử trùng bị loại bỏ

~~~java
var input = List.of("A", "A", "B");
var unique = Set.copyOf(input);
System.out.println(unique.size()); // 2
~~~

Nếu nguồn chứa các phần tử bằng nhau theo `equals`, `Set.copyOf` chỉ giữ **một đại diện tùy ý** trong số đó. Với hai đối tượng khác tham chiếu nhưng được xem là bằng nhau, không được dựa vào việc đại diện đầu tiên hay cuối cùng được chọn.

Đây là khác biệt quan trọng với `Set.of`:

~~~java
// Set.of("A", "A"); // Ném IllegalArgumentException
Set<String> unique = Set.copyOf(List.of("A", "A")); // Hợp lệ, size = 1
~~~

### 5.2. Không chấp nhận nguồn hoặc phần tử `null`

~~~java
// Set.copyOf(null); // Ném NullPointerException
// Set.copyOf(Arrays.asList("A", null)); // Ném NullPointerException
~~~

Nguồn `ArrayList` có thể chứa `null`, nhưng `Set.copyOf` vẫn phải từ chối. Hãy kiểm tra/làm sạch đầu vào theo quy tắc nghiệp vụ; **không dùng `copyOf` để tự động bỏ qua null**.

### 5.3. Không có thứ tự duyệt được cam kết

Ngay cả khi nguồn là `LinkedHashSet` hoặc `ArrayDeque` có thứ tự duyệt xác định, `Set.copyOf` không hứa giữ thứ tự ấy:

~~~java
var ordered = new LinkedHashSet<>(List.of("B", "A", "C"));
var result = Set.copyOf(ordered); // Không hứa duyệt theo "B", "A", "C"
~~~

Tránh viết test so sánh `result.toString()` với một thứ tự cố định. Kiểm tra `size()`, `contains()`, `equals()`, hoặc sắp xếp kết quả khi cần hiển thị theo thứ tự nghiệp vụ.

## 6. Chương trình Java 17+ hoàn chỉnh

Lưu toàn bộ mã sau vào file **SetCopyOfGenericDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public class SetCopyOfGenericDemo {
    private static void acceptNumbers(Set<Number> numbers) {
        System.out.println("number set size: " + numbers.size());
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>(List.of(1, 2, 2, 3));

        var inferred = Set.copyOf(integers); // Set<Integer>
        System.out.println("distinct count: " + inferred.size());
        System.out.println("contains 2: " + inferred.contains(2));

        Set<Number> widened = Set.copyOf(integers);
        acceptNumbers(widened);

        var explicitWitness = Set.<Number>copyOf(integers);
        acceptNumbers(explicitWitness);

        Collection<String> queue =
                new ArrayDeque<>(List.of("a", "b", "a"));
        var fromQueue = Set.copyOf(queue); // Set<String>
        System.out.println("queue distinct: " + fromQueue.size());

        var source = new ArrayList<>(List.of("A", "B"));
        var snapshot = Set.copyOf(source);
        source.add("C");

        System.out.println("source size: " + source.size());
        System.out.println("snapshot contains C: " + snapshot.contains("C"));

        try {
            Set.copyOf(Arrays.asList("ok", null));
        } catch (NullPointerException error) {
            System.out.println("null rejected: NullPointerException");
        }

        try {
            inferred.add(4);
        } catch (UnsupportedOperationException error) {
            System.out.println("add rejected: UnsupportedOperationException");
        }

        System.out.println(
                "copyOf duplicates: " + Set.copyOf(List.of("A", "A")).size()
        );

        try {
            Set.of("A", "A");
        } catch (IllegalArgumentException error) {
            System.out.println("of duplicate: IllegalArgumentException");
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac SetCopyOfGenericDemo.java
java SetCopyOfGenericDemo
~~~

Kết quả chính xác:

~~~text
distinct count: 3
contains 2: true
number set size: 3
number set size: 3
queue distinct: 2
source size: 3
snapshot contains C: false
null rejected: NullPointerException
add rejected: UnsupportedOperationException
copyOf duplicates: 1
of duplicate: IllegalArgumentException
~~~

Giải thích kết quả:

1. `integers` chứa bốn phần tử nhưng chỉ có ba giá trị duy nhất `1, 2, 3`. `inferred` có kiểu `Set<Integer>` và kích thước 3.
2. Cả `Set<Number> widened` và `Set.<Number>copyOf(integers)` đều hợp lệ nhờ `? extends Number`; cả hai có ba giá trị duy nhất.
3. `queue` được khai báo là `Collection<String>`, dù đối tượng là `ArrayDeque<String>`. Chữ ký `copyOf` chấp nhận nó; ba giá trị đầu vào chỉ còn hai giá trị duy nhất.
4. Thêm `"C"` vào `source` sau khi tạo `snapshot` không thay đổi nội dung `snapshot`.
5. `null` bị từ chối bằng `NullPointerException`, còn thao tác `add` lên kết quả bị từ chối bằng `UnsupportedOperationException`.
6. `Set.copyOf` loại trùng, trong khi `Set.of` từ chối đối số trùng bằng `IllegalArgumentException`.

Chương trình chỉ in kích thước và truy vấn `contains`, không in thứ tự duyệt nên kết quả ổn định, không phụ thuộc vào cách triển khai nội bộ của Set.

## 7. Snapshot của Set và tính bất biến của phần tử

`Set.copyOf` trả về kết quả **không cho sửa**. Sau khi copy, thay đổi cấu trúc collection nguồn sẽ không được phản ánh vào Set kết quả:

~~~java
var original = new ArrayList<>(List.of("A", "B"));
var unique = Set.copyOf(original);
original.add("C");

System.out.println(unique.contains("C")); // false
~~~

Tuy nhiên, `copyOf` **không sao chép sâu** các đối tượng phần tử. Nếu phần tử là một đối tượng mutable, những tham chiếu ngoài vẫn có thể thay đổi trạng thái của nó. Với phần tử dùng trong Set, điều này còn đặc biệt nguy hiểm: nếu sửa các thuộc tính quyết định `equals` hoặc `hashCode`, hành vi của Set có thể không còn được bảo đảm theo hợp đồng Java.

Vì vậy, nếu muốn an toàn khi truyền dữ liệu qua ranh giới API, hãy ưu tiên các phần tử được thiết kế bất biến như `String`, wrapper số hoặc các value object bất biến.

**Một điểm nữa:** `copyOf` không bảo đảm luôn cấp phát instance mới. Nếu nguồn đã là unmodifiable Set phù hợp, implementation có thể tái sử dụng instance. Không dùng `==` để kiểm tra copy thành công; hãy dựa vào nội dung, tính không cho sửa và hợp đồng của API.

## 8. Các lỗi thường gặp khi đọc chữ ký generic

| Lỗi hoặc hiểu nhầm | Vì sao không đúng | Cách viết đúng |
| --- | --- | --- |
| `Set.copyOf(array)` với `String[]` | Mảng không phải `Collection` | `Set.copyOf(Arrays.asList(array))` |
| `Set.copyOf(stream)` | `Stream` không phải `Collection` | `Set.copyOf(stream.toList())` trên Java 17+ |
| `Set.copyOf(map)` | `Map` không phải `Collection` | `Set.copyOf(map.keySet())`, `values()` hoặc `entrySet()` |
| `Set.copyOf(iterable)` khi biến chỉ có kiểu `Iterable<T>` | `Iterable` không nhất thiết triển khai `Collection` | Tạo một `Collection<T>` thực sự từ phần tử nguồn |
| `Set<Number> values = setOfIntegers;` | Generics bất biến | Chọn `E=Number` khi gọi `Set.copyOf` |
| `var values = Set.copyOf(source)` và cho rằng luôn là `Set<Object>` | Kiểu phụ thuộc vào generic của nguồn | Xem kiểu phần tử của `source` |
| `Set.<int>copyOf(source)` | Primitive không hợp lệ làm type argument | Dùng `Integer` |
| Giả định `Set.copyOf` giữ thứ tự `List` | Set không bảo đảm thứ tự duyệt | Sắp xếp riêng nếu cần |
| Giả định source có duplicate sẽ báo lỗi | `copyOf` chỉ giữ một đại diện tùy ý | Kiểm tra trùng trước nếu trùng là lỗi nghiệp vụ |
| Giả định có thể truyền phần tử `null` | `copyOf` từ chối `null` | Kiểm tra dữ liệu đầu vào |
| Giả định Set kết quả có thể `add` | Kết quả là unmodifiable | Dùng `new HashSet<>(source)` nếu cần Set mutable |

Đặc biệt, **đừng ép kiểu raw hoặc dùng unchecked cast** để vượt qua lỗi generic chỉ vì `copyOf` không nhận đối số đang có. Trước hết hãy xác nhận nguồn thực sự là `Collection` và các phần tử có kiểu tương thích; sau đó dùng kiểu đích rõ ràng hoặc type witness nếu cần.

## 9. Chọn `Set.copyOf` hay cách khác?

- **`Set.copyOf(collection)`**: đã có `Collection`, cần loại trùng và trả kết quả không cho sửa; không cần duy trì thứ tự duyệt.
- **`Set.of(values...)`**: biết trực tiếp các phần tử tại nơi gọi; muốn factory báo lỗi khi các đối số trùng.
- **`new HashSet<>(collection)`**: cần một Set có thể thay đổi tiếp, không phải unmodifiable.
- **`new LinkedHashSet<>(collection)`**: cần Set có thể sửa và giữ thứ tự xuất hiện ban đầu của các phần tử duy nhất.
- **`Collections.unmodifiableSet(existingSet)`**: cần một view không cho sửa trên một Set hiện có, có chủ đích theo dõi những thay đổi thông qua tham chiếu gốc.

Nếu chỉ cần loại trùng rồi tiếp tục xử lý, chọn loại Set theo yêu cầu về sửa đổi và thứ tự. Nếu cần trao ra kết quả với cấu trúc không đổi, `Set.copyOf` là lựa chọn phù hợp, với lưu ý rằng phần tử mutable vẫn phải được kiểm soát.

## 10. Tự kiểm tra

Dự đoán những dòng nào hợp lệ và kiểu của biến kết quả:

~~~java
List<Integer> ints = List.of(1, 1, 2);

var a = Set.copyOf(ints);
Set<Number> b = Set.copyOf(ints);
var c = Set.<Number>copyOf(ints);

Iterable<Integer> iterable = ints;
// var d = Set.copyOf(iterable); // Có biên dịch không?

var e = Set.copyOf(Arrays.asList("A", "A", "B"));
// Set.of("A", "A"); // Có ném lỗi không?
~~~

**Đáp án:**

1. `a` có kiểu `Set<Integer>`, kích thước 2.
2. `b` có kiểu `Set<Number>`, kích thước 2; `Integer` là kiểu con của `Number`.
3. `c` có kiểu `Set<Number>`, kích thước 2; đây là type witness của generic method.
4. `d` không biên dịch vì biến `iterable` chỉ có kiểu tĩnh `Iterable<Integer>`, không phù hợp với tham số `Collection<? extends E>`, dù đối tượng thực tế là một List.
5. `e` có kiểu `Set<String>` và kích thước 2 vì `copyOf` loại trùng. `Set.of("A", "A")` ném `IllegalArgumentException`.

Tự hỏi thêm: nếu bạn muốn kiểu `Set<Number>` ngay khi dùng `var`, không có kiểu đích cho lời gọi `copyOf`, nên cần cách nào? **Đáp án:** `var result = Set.<Number>copyOf(ints);` hoặc khai báo biến bằng `Set<Number>` ngay từ đầu.

## 11. Tài liệu chuẩn và ghi nhớ

- Chữ ký chính thức: **`static <E> Set<E> copyOf(Collection<? extends E> coll)`**.
- Nguồn phải là `Collection` phù hợp (List, Set, Queue/Deque, hoặc các triển khai khác); `Iterable` đơn thuần, Map, Stream, Iterator và mảng không truyền trực tiếp được.
- `? extends E` cho phép nhận collection có phần tử là kiểu con của `E`, hữu ích khi suy luận trả về `Set<Number>` từ `Collection<Integer>`.
- `copyOf` bỏ phần tử trùng, từ chối `null`, trả unmodifiable Set, không cam kết thứ tự duyệt và không phản ánh thay đổi cấu trúc nguồn về sau.
- Kết quả không deep copy phần tử, và không cam kết instance mới khi nguồn đã là unmodifiable Set.

Tài liệu chính thức:

- [Java SE 17 — `Set.copyOf` và hợp đồng unmodifiable Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection))
- [Java SE 17 — `Collection<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html)
- [Java Language Specification §4.5.1 — Type Arguments and Wildcards](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1)
- [Java Language Specification §18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html)

**Kết luận:** Để sử dụng `Set.copyOf` đúng, hãy xác định **kiểu phần tử `E`** và **kiểu nguồn `Collection<? extends E>`** trước. Từ đó bạn kiểm soát được tính an toàn kiểu generic, loại nguồn hợp lệ và các đặc tính của Set kết quả.
