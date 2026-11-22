# Chọn kiểu bộ chứa bằng `Collectors.toCollection`

Trong **Java Stream API**, các phép toán trung gian như `filter`, `map`, `distinct` hoặc `sorted` mô tả pipeline xử lý dữ liệu theo cách khai báo và thường được thực thi *lazy*. Khi cần lưu các phần tử sau xử lý vào một collection, ta sử dụng terminal operation `collect`.

Một lựa chọn quen thuộc là `Collectors.toList()` hoặc `Collectors.toSet()`. Nhưng nếu yêu cầu phải trả về đúng **`ArrayList`**, giữ thứ tự xuất hiện bằng **`LinkedHashSet`**, sắp theo bộ so sánh bằng **`TreeSet`**, hay xây **`ArrayDeque`**, hãy dùng `Collectors.toCollection(collectionFactory)`.

Bài học thuộc chương **Thu thập thành Collection**, tập trung vào cách chọn đúng bộ chứa và hiểu hợp đồng về kiểu dữ liệu, phần tử trùng, thứ tự, tính mutable và xử lý song song.

## 1. `toCollection` nhận một factory, trả về collector

Chữ ký khái quát của phương thức (Java 8+):

```java
public static <T, C extends Collection<T>> Collector<T, ?, C>
toCollection(Supplier<C> collectionFactory);
```

Đây là phương thức tĩnh của `java.util.stream.Collectors`. Nó nhận một `Supplier<C>`: hàm **không có đối số**, khi được gọi phải cung cấp collection để tích lũy phần tử. Collection được tạo ra có kiểu `C`, còn phần tử có kiểu `T`.

```java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> words = Stream.of("Java", "Stream", "API")
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(words);            // [Java, Stream, API]
System.out.println(words.getClass());  // class java.util.ArrayList
words.add("Collector");                // Được phép vì ArrayList mutable
```

`ArrayList::new` là *constructor reference* phù hợp với `Supplier<ArrayList<String>>`. `toCollection` tạo một collector và `stream.collect(...)` sử dụng collector ấy để kết thúc pipeline. Collection được xây xong là kết quả có thể truy cập sau khi stream đã bị tiêu thụ.

### Vì sao truyền `ArrayList::new` thay vì `new ArrayList<>()`?

```java
// ĐÚNG: truyền factory, tạo container khi collect cần.
Collectors.toCollection(ArrayList::new);

// SAI KIỂU: toCollection cần Supplier, không nhận một instance.
// Collectors.toCollection(new ArrayList<String>());
```

Đối với pipeline song song, collector có thể gọi supplier **nhiều lần** để tạo các container tích lũy độc lập, rồi gộp kết quả. Vì vậy factory phải tạo container mới phù hợp cho từng lần gọi. Không dùng:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> shared = new ArrayList<>();

// VÍ DỤ SAI: mọi lần gọi supplier đều trả cùng một danh sách.
List<String> broken = Stream.of("A", "B", "C").parallel()
    .collect(Collectors.toCollection(() -> shared));
```

Cách làm sai có thể khiến các phần tích lũy cùng sửa một đối tượng và bị gộp lặp. Ngay cả khi chỉ chạy tuần tự, kết quả còn phụ thuộc vào nội dung có sẵn của `shared`. Hãy để factory trả **collection rỗng mới**, ví dụ `ArrayList::new`.

## 2. Bảng chọn collection theo yêu cầu

Không có một loại collection phù hợp với mọi bài toán. Hãy chọn theo đặc tính nghiệp vụ cần bảo đảm.

| Factory truyền vào `toCollection` | Kiểu kết quả | Trùng lặp | Thứ tự khi duyệt kết quả | Trường hợp sử dụng |
| --- | --- | --- | --- | --- |
| `ArrayList::new` | `ArrayList<T>` | Giữ lại | Theo thứ tự thêm | Danh sách có truy cập chỉ số, cần thay đổi sau khi thu thập. |
| `LinkedList::new` | `LinkedList<T>` | Giữ lại | Theo thứ tự thêm | Cần API của `LinkedList`, ví dụ `Deque`; cân nhắc chi phí bộ nhớ. |
| `HashSet::new` | `HashSet<T>` | Loại trùng theo `equals/hashCode` | Không bảo đảm | Tập phần tử không trùng, không cần thứ tự. |
| `LinkedHashSet::new` | `LinkedHashSet<T>` | Loại trùng theo `equals/hashCode` | Theo thứ tự thêm | Loại trùng nhưng vẫn muốn duyệt theo thứ tự xuất hiện. |
| `TreeSet::new` | `TreeSet<T>` | Loại phần tử tương đương theo phép so sánh | Theo thứ tự sắp xếp | Cần tập có thứ tự tự nhiên hoặc comparator. |
| `ArrayDeque::new` | `ArrayDeque<T>` | Giữ lại | Theo thứ tự từ đầu đến cuối deque | Hàng đợi hai đầu; không chứa `null`. |
| `() -> EnumSet.noneOf(MyEnum.class)` | `EnumSet<MyEnum>` | Loại trùng | Theo thứ tự khai báo enum | Tập hiệu quả cho một kiểu enum xác định. |

Hai điểm cần phân biệt:

1. **Encounter order** là thứ tự logic của phần tử đầu vào, chẳng hạn thứ tự phần tử của `List`. Theo hợp đồng `toCollection`, phần tử được tích lũy theo encounter order nếu stream có thứ tự.
2. **Iteration order** là thứ tự quan sát khi duyệt collection **sau khi thu thập**. `TreeSet` duyệt theo comparator, `HashSet` không bảo đảm thứ tự, `EnumSet` duyệt theo thứ tự khai báo enum. Vì thế `toCollection` không có nghĩa mọi collection kết quả đều được duyệt theo thứ tự nguồn.

## 3. `ArrayList`: danh sách mutable có thứ tự

Nếu cần giữ mọi phần tử, kể cả phần tử trùng, và muốn thêm hoặc xóa sau khi thu thập, `ArrayList` là lựa chọn đơn giản:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> raw = Arrays.asList("  Java  ", "Stream", "Java", "API");

ArrayList<String> names = raw.stream()
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(names); // [Java, Stream, Java, API]

names.remove("Java");      // Xóa phần tử Java xuất hiện đầu tiên
names.add("Collector");
System.out.println(names); // [Stream, Java, API, Collector]
```

`map` và `filter` là trung gian lazy; `collect` kích hoạt xử lý. Vì nguồn là `List` có thứ tự, kết quả `ArrayList` giữ thứ tự các phần tử vượt qua bộ lọc. `ArrayList` không tự loại trùng.

**Lưu ý về shallow collection:** `toCollection` lưu **tham chiếu đến các phần tử** được phát ra. Nếu các phần tử là đối tượng mutable và bạn không tạo bản sao trong `map`, thay đổi một đối tượng sau đó có thể được nhìn thấy cả qua nguồn lẫn collection kết quả. Tạo collection mới không đồng nghĩa sao chép sâu từng phần tử.

## 4. `LinkedHashSet`: loại trùng nhưng giữ thứ tự xuất hiện

Khi xử lý nhãn hoặc mã từ dữ liệu đầu vào, ta có thể cần loại trùng mà vẫn giữ thứ tự lần đầu xuất hiện:

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.stream.Collectors;

List<String> rawTags = Arrays.asList(
    "  Java ", "Stream", "JAVA", "API", "Stream", "API"
);

LinkedHashSet<String> tags = rawTags.stream()
    .map(String::trim)
    .map(String::toLowerCase)
    .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(tags); // [java, stream, api]
```

`LinkedHashSet` dùng `equals` và `hashCode` để xác định phần tử trùng, và giữ thứ tự thêm phần tử. Nhờ chuẩn hóa chữ thường **trước khi** thu thập, `"Java"` và `"JAVA"` trở thành cùng một giá trị.

Với một `HashSet`, kết quả vẫn là ba nhãn nhưng **thứ tự duyệt không được bảo đảm**. Nếu dùng `Collectors.toSet()`, cũng không nên dựa vào thứ tự, kiểu triển khai cụ thể hay khả năng thay đổi của tập kết quả.

### Có cần gọi `distinct()` trước khi thu thập vào Set?

```java
LinkedHashSet<String> a = rawTags.stream()
    .map(String::trim)
    .collect(Collectors.toCollection(LinkedHashSet::new));

LinkedHashSet<String> b = rawTags.stream()
    .map(String::trim)
    .distinct()
    .collect(Collectors.toCollection(LinkedHashSet::new));
```

Trong ví dụ này, hai kết quả có cùng các phần tử theo `equals`. Vì `LinkedHashSet` tự loại trùng, `distinct()` thường không cần nếu **mục đích duy nhất** là loại trùng trước khi bỏ vào Set. `distinct` là phép trung gian có trạng thái và có thể làm tăng công việc; chỉ thêm nếu nó cần cho ngữ nghĩa hoặc các bước xử lý phía sau.

Tuy nhiên, nếu có `map` **sau** `distinct` làm nhiều giá trị khác nhau biến thành cùng một nhãn, Set cuối vẫn là nơi quyết định tính duy nhất của kết quả.

## 5. `TreeSet`: thứ tự sắp xếp và quy tắc trùng lặp theo comparator

Khi cần tập hợp không trùng và được duyệt theo thứ tự tăng dần, dùng `TreeSet`:

```java
import java.util.Arrays;
import java.util.TreeSet;
import java.util.stream.Collectors;

TreeSet<Integer> numbers = Arrays.asList(8, 3, 8, 1, 5).stream()
    .collect(Collectors.toCollection(TreeSet::new));

System.out.println(numbers);        // [1, 3, 5, 8]
System.out.println(numbers.first()); // 1
System.out.println(numbers.last());  // 8
```

`TreeSet` sử dụng **thứ tự tự nhiên** nếu không cung cấp comparator. Phần tử phải có khả năng so sánh phù hợp; nếu không, quá trình thêm phần tử có thể ném `ClassCastException`. Với comparator không hỗ trợ `null`, đưa phần tử `null` vào có thể gây `NullPointerException`.

### Truyền comparator qua lambda factory

```java
import java.util.Comparator;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Comparator<String> byLengthThenText = Comparator
    .comparingInt(String::length)
    .thenComparing(Comparator.naturalOrder());

TreeSet<String> names = Stream.of("Bob", "Ana", "Al", "Ana", "Zoe")
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(byLengthThenText)
    ));

System.out.println(names); // [Al, Ana, Bob, Zoe]
```

Vì `TreeSet` không có constructor không đối số cho **comparator cụ thể**, factory thích hợp là `() -> new TreeSet<>(byLengthThenText)`. Mỗi lần gọi factory phải tạo một `TreeSet` riêng nhưng dùng cùng quy tắc so sánh.

**Lưu ý quan trọng:** Với `TreeSet`, hai phần tử được coi là trùng nếu comparator trả về **0**, ngay cả khi `equals` của chúng trả `false`. Ví dụ:

```java
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

TreeSet<String> words = Stream.of("Java", "JAVA", "API")
    .collect(Collectors.toCollection(
        () -> new TreeSet<>(String.CASE_INSENSITIVE_ORDER)
    ));

System.out.println(words.size()); // 2: Java và JAVA tương đương theo comparator
```

Khi dùng `TreeSet` làm `Set`, comparator **nên nhất quán với `equals`** nếu muốn tuân thủ đầy đủ hợp đồng chung của Set. Nếu yêu cầu nghiệp vụ thực sự là gộp không phân biệt hoa thường, cần hiểu quy tắc tương đương đang sử dụng và giá trị đại diện nào còn lại.

## 6. Những collection chuyên biệt: `ArrayDeque` và `EnumSet`

### Thu thập vào deque để xử lý hàng đợi

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Deque<String> jobs = Stream.of("parse", "validate", "save")
    .collect(Collectors.toCollection(ArrayDeque::new));

System.out.println(jobs.peekFirst()); // parse
System.out.println(jobs.pollFirst()); // parse, đồng thời lấy khỏi deque
System.out.println(jobs.peekFirst()); // validate
```

`ArrayDeque` phù hợp với thao tác đầu/cuối hàng đợi. Nó giữ phần tử trùng, duyệt theo thứ tự từ đầu đến cuối, **không chấp nhận `null`** và không được thiết kế cho nhiều luồng sửa đồng thời cùng một instance. Khi cần luồng công việc đồng thời thực sự, phải chọn cấu trúc dữ liệu và cách phối hợp thích hợp thay vì chỉ thêm `parallel()` vào pipeline thu thập.

### Thu thập các giá trị enum

```java
import java.util.EnumSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class PermissionExample {
    enum Permission { READ, WRITE, EXECUTE }

    public static void main(String[] args) {
        EnumSet<Permission> permissions =
            Stream.of(Permission.WRITE, Permission.READ, Permission.WRITE)
                .collect(Collectors.toCollection(
                    () -> EnumSet.noneOf(Permission.class)
                ));

        System.out.println(permissions); // [READ, WRITE]
    }
}
```

`EnumSet.noneOf(Permission.class)` tạo tập rỗng chuyên dụng cho kiểu `Permission`; `Permission.class` là tham số cần thiết, nên không dùng trực tiếp `EnumSet::noneOf` làm `Supplier` không đối số. `EnumSet` duyệt theo thứ tự **khai báo enum**, không phải thứ tự các phần tử được stream đưa vào. Nó cũng không hỗ trợ phần tử `null`.

## 7. `toCollection` khác `toList`, `toSet` và `Stream.toList` thế nào?

Các phương thức trông tương tự nhưng có hợp đồng khác nhau:

| API | Kiểu kết quả được hứa hẹn | Có thể sửa collection kết quả? | Thứ tự và phần tử trùng |
| --- | --- | --- | --- |
| `collect(Collectors.toCollection(ArrayList::new))` | Đúng `ArrayList<T>` | Có, theo hợp đồng `ArrayList` | Giữ trùng, duyệt theo encounter order của nguồn có thứ tự. |
| `collect(Collectors.toCollection(LinkedHashSet::new))` | Đúng `LinkedHashSet<T>` | Có | Loại trùng, duyệt theo thứ tự thêm. |
| `collect(Collectors.toList())` | `List<T>`, không hứa lớp cài đặt | **Không bảo đảm** mutable hoặc immutable | Giữ trùng và thứ tự nguồn khi có encounter order. |
| `collect(Collectors.toSet())` | `Set<T>`, không hứa lớp cài đặt | **Không bảo đảm** mutable hoặc immutable | Loại trùng; collector không có ràng buộc về thứ tự. |
| `stream.toList()` (Java 16+) | `List<T>` không thể sửa đổi | Không; `add`, `set`, `remove` ném `UnsupportedOperationException` | Giữ trùng, giữ encounter order nếu có. |
| `collect(Collectors.toUnmodifiableList())` (Java 10+) | `List<T>` không thể sửa đổi | Không | Giữ trùng, giữ encounter order; từ chối phần tử `null`. |

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<Integer> editable = Stream.of(1, 2, 3)
    .collect(Collectors.toCollection(ArrayList::new));
editable.add(4); // Hợp lệ

List<Integer> unspecified = Stream.of(1, 2, 3)
    .collect(Collectors.toList());
// Không lập trình dựa trên giả định unspecified là ArrayList.

// Java 16+
List<Integer> readOnly = Stream.of(1, 2, 3).toList();
// readOnly.add(4); // UnsupportedOperationException
```

Lựa chọn `toCollection` nên xuất phát từ **hợp đồng đầu ra cần thiết**, không phải giả định về lớp cài đặt hiện tại của JDK. Nếu chỉ cần `List<T>` để đọc, `toList()` hoặc `Collectors.toList()` thường đủ; nếu cần `ArrayList` cụ thể, `ArrayDeque` hay `TreeSet`, hãy truyền factory rõ ràng.

## 8. Encounter order, song song và container mutable

`toCollection` tạo một collector cho phép tích lũy vào collection mutable. Điều đó **không** có nghĩa các tác vụ song song phải cùng ghi vào một collection dùng chung.

```java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

ArrayList<Integer> values = IntStream.range(0, 10_000)
    .parallel()
    .boxed()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(values.size());        // 10000
System.out.println(values.get(0));        // 0
System.out.println(values.get(9_999));    // 9999
```

`IntStream.range` có encounter order xác định. Collector `toCollection` tích lũy theo thứ tự gặp phần tử, nên danh sách sau cùng vẫn mang thứ tự `0, 1, ..., 9999` khi pipeline giữ thứ tự. Trong quá trình xử lý song song, các container trung gian có thể được tạo và kết hợp theo cách khác nhau; ta **không dựa vào thứ tự gọi lambda**, số lần gọi supplier hay lịch làm việc của thread.

Những nguyên tắc cần giữ:

- Factory như `ArrayList::new` hoặc `LinkedHashSet::new` phải tạo **container độc lập**; không trả một danh sách chung từ biến ngoài.
- Các bước `map`/`filter` nên **không can thiệp nguồn** và **không phụ thuộc trạng thái chia sẻ mutable**, nhất là khi song song.
- `toCollection` không phải collector `CONCURRENT`: khả năng tích lũy an toàn đến từ cách framework tổ chức container riêng và kết hợp chúng, không phải từ việc mọi collection đều thread-safe.
- Chọn `TreeSet` hay `LinkedHashSet` có chi phí bộ nhớ và tính toán khác `ArrayList`. Dùng `parallel()` không bảo đảm nhanh hơn; khi hiệu năng quan trọng, đo trên dữ liệu thực tế.
- Nếu gọi `unordered()` hoặc nguồn vốn không có encounter order, không được suy ra kết quả `ArrayList` hay `LinkedHashSet` có thứ tự ổn định giữa các lần chạy.

Ví dụ nguy hiểm là đưa hiệu ứng phụ vào mapper:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> shared = new ArrayList<>();

// VÍ DỤ SAI: ghi thêm vào collection ngoài pipeline từ nhiều luồng.
List<String> result = Stream.of("A", "B", "C").parallel()
    .map(value -> {
        shared.add(value);
        return value;
    })
    .collect(Collectors.toCollection(ArrayList::new));
```

`shared.add` có thể chạy đồng thời và không phải cách đáng tin để thu thập mọi phần tử. Kết quả cần dùng chính là collection mà `collect` trả về; không cần bộ chứa ngoài pipeline.

## 9. Những giới hạn dễ bỏ sót

### Stream chỉ được tiêu thụ một lần

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Stream<String> stream = Stream.of("A", "B", "A");
ArrayList<String> list =
    stream.collect(Collectors.toCollection(ArrayList::new));

// Không hợp lệ: cùng Stream đã bị tiêu thụ.
// LinkedHashSet<String> set =
//     stream.collect(Collectors.toCollection(LinkedHashSet::new));
```

Nếu cần hai loại collection từ cùng một `List` có sẵn, tạo **hai stream mới từ List**. Nếu nguồn chỉ duyệt được một lần như `Files.lines`, hãy cân nhắc có thực sự cần lưu tạm dữ liệu hay có thể tổng hợp các kết quả bằng một collector thích hợp.

### Nguồn vô hạn cần giới hạn

```java
import java.util.ArrayList;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> five = Stream.generate(() -> "sample")
    .limit(5)
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(five.size()); // 5
```

`collect(toCollection(...))` thường phải duyệt hết đầu vào. Nếu nguồn vô hạn mà không có điều kiện dừng hoặc giới hạn hữu hạn, phép thu thập **không thể hoàn thành**. Ngay cả nguồn hữu hạn cũng có thể gây áp lực bộ nhớ lớn vì toàn bộ phần tử phải được giữ lại.

### Collection có thể thay đổi nhưng không nhất thiết giữ được phần tử `null`

`ArrayList` hỗ trợ `null`, còn `ArrayDeque` và `EnumSet` không cho phép; `TreeSet` với thứ tự tự nhiên cũng không chấp nhận `null`. Đặt `filter(Objects::nonNull)` trước `collect` khi đó là chính sách dữ liệu phù hợp:

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Collectors;

ArrayDeque<String> queue = Arrays.asList("A", null, "B").stream()
    .filter(Objects::nonNull)
    .collect(Collectors.toCollection(ArrayDeque::new));

System.out.println(queue); // [A, B]
```

Không âm thầm bỏ `null` nếu giá trị thiếu cần được báo lỗi hoặc lưu lại để xử lý riêng.

## 10. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Truyền một collection đã tạo vào `toCollection` | Sai chữ ký; API cần `Supplier`. | Dùng `ArrayList::new` hoặc `() -> new TreeSet<>(comparator)`. |
| Factory trả về một collection mutable dùng chung | Sai hợp đồng tích lũy; dễ tranh chấp hoặc gộp lặp. | Mỗi lần gọi supplier tạo instance độc lập. |
| Dùng `toList()` rồi giả định có thể `add` | `Stream.toList()` (Java 16+) trả list không thể sửa đổi. | Dùng `toCollection(ArrayList::new)`. |
| Dùng `toSet()` rồi giả định duyệt theo thứ tự nguồn | `toSet()` không hứa thứ tự hoặc kiểu cài đặt. | Dùng `toCollection(LinkedHashSet::new)` trên nguồn có thứ tự. |
| Dùng `TreeSet` nhưng comparator chỉ so sánh một trường không duy nhất | Phần tử khác nhau có thể bị coi là trùng. | Xác định quy tắc tương đương hoặc thêm tiêu chí phụ vào comparator. |
| Thu phần tử `null` vào `ArrayDeque` | Ném `NullPointerException`. | Xử lý dữ liệu thiếu trước khi thu thập. |
| Dùng `collect` để thu toàn bộ stream vô hạn | Không kết thúc hoặc cạn tài nguyên. | Giới hạn đầu vào hoặc chọn phép tổng hợp hữu hạn. |
| Thêm phần tử vào collection ngoài trong `parallel().map(...)` | Hiệu ứng phụ có tranh chấp và không đáng tin. | Để `collect` quản lý tích lũy và trả kết quả. |

## 11. Bài tập áp dụng

**Bài 1 — Danh sách có thể chỉnh sửa.** Tạo `Stream.of("a", "b", "a")`, thu bằng `toCollection(ArrayList::new)`, sau đó `add("c")`. Dự đoán kết quả `[a, b, a, c]` và giải thích vì sao không nên giả định `Stream.toList()` cũng cho phép thay đổi.

**Bài 2 — Loại trùng có thứ tự.** Cho dữ liệu `["Java", "Stream", "Java", "API", "Stream"]`. Thu vào `LinkedHashSet` và `TreeSet`, so sánh thứ tự duyệt cũng như quy tắc loại trùng. Giải thích vì sao `HashSet` không phù hợp khi phải giữ thứ tự lần đầu xuất hiện.

**Bài 3 — Comparator.** Thu `Stream.of("apple", "pear", "kiwi", "fig")` vào `TreeSet` bằng comparator chỉ xét độ dài chuỗi. Dự đoán vì sao `"pear"` và `"kiwi"` không thể cùng tồn tại trong tập đó. Sửa comparator để dùng chữ cái làm tiêu chí phụ.

**Bài 4 — EnumSet.** Định nghĩa `enum Status { NEW, RUNNING, DONE }`. Từ stream `DONE, NEW, DONE`, tạo `EnumSet<Status>` qua `toCollection(() -> EnumSet.noneOf(Status.class))`; kiểm tra tập kết quả và thứ tự duyệt.

**Bài 5 — Song song.** Thu `IntStream.range(0, 10000).parallel().boxed()` vào `ArrayList` bằng factory. Kiểm tra số lượng và phần tử đầu/cuối. Thử dùng `unordered()` rồi giải thích vì sao không nên kiểm thử danh sách bằng một thứ tự mong đợi cố định.

**Ghi nhớ:** `Collectors.toCollection` giúp **chỉ định chính xác collection cần tạo** bằng một `Supplier`. Hãy chọn loại bộ chứa theo yêu cầu về thứ tự, phần tử trùng, khả năng thay đổi, null, comparator và chi phí. Khi thu thập song song, dùng factory tạo container mới và để collector quản lý việc kết hợp; khi nguồn vô hạn, giới hạn số phần tử trước khi lưu toàn bộ vào bộ nhớ.
