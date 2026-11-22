# Thu thập bằng Stream.toList và phân biệt hợp đồng với Collector

Trong chương **Thu thập thành Collection** của **Java Stream API**, một pipeline khai báo thường bắt đầu từ nguồn dữ liệu, lọc bằng `filter`, biến đổi bằng `map`, có thể làm phẳng bằng `flatMap`, rồi cần giữ kết quả để dùng ở những bước sau. Từ **Java 16**, `Stream.toList()` là một cách ngắn gọn để biến các phần tử đầu ra thành `List`.

Tuy nhiên, cú pháp gần giống nhau **không có nghĩa là hợp đồng giống nhau**: `stream.toList()` trả về một danh sách **không sửa đổi được**, trong khi `stream.collect(Collectors.toList())` trả về `List` mà đặc tả **không bảo đảm** kiểu triển khai hoặc khả năng sửa đổi. Nếu ứng dụng cần `ArrayList` có thể chỉnh sửa, nên yêu cầu rõ bằng `Collectors.toCollection(ArrayList::new)`. Ngoài ra, `Collectors.toList()` còn là một **Collector**, vì vậy nó có thể lồng vào `groupingBy`, `mapping` hoặc các bước thu thập khác, còn `Stream.toList()` là một **terminal operation** trên Stream.

Bài học trình bày đầy đủ các khác biệt đó, cách lựa chọn API phù hợp và các bẫy liên quan đến `null`, thứ tự phần tử, tính bất biến, xử lý song song và bộ nhớ.

## 1. Bắt đầu từ một pipeline cụ thể

Giả sử ứng dụng có danh sách thành viên của nhiều nhóm. Ta muốn lấy tên các thành viên đang hoạt động trong nhóm `DEV`, giữ thứ tự ban đầu:

~~~java
import java.util.List;

public class MemberListDemo {
    record Member(String name, String team, boolean active) {}

    public static void main(String[] args) {
        List<Member> members = List.of(
                new Member("Lan", "DEV", true),
                new Member("Minh", "QA", true),
                new Member("An", "DEV", false),
                new Member("Huy", "DEV", true)
        );

        List<String> activeDevelopers = members.stream()
                .filter(Member::active)
                .filter(member -> "DEV".equals(member.team()))
                .map(Member::name)
                .toList();

        System.out.println(activeDevelopers); // [Lan, Huy]
    }
}
~~~

Pipeline được đọc từ trái sang phải:

1. `members.stream()` tạo Stream các `Member` từ một `List`.
2. Hai thao tác `filter` chỉ giữ thành viên đang hoạt động của nhóm `DEV`.
3. `map(Member::name)` chuyển `Stream<Member>` thành `Stream<String>`.
4. `toList()` kích hoạt pipeline, thu các chuỗi còn lại thành `List<String>`.

`filter` và `map` là các thao tác trung gian *lazy*; `toList` là terminal operation. Sau khi gọi `toList()`, đối tượng Stream đó đã được sử dụng và không thể gọi thêm một terminal operation khác trên chính nó.

**Điều quan trọng:** `activeDevelopers` hiển thị như một danh sách thông thường, nhưng mọi thao tác sửa đổi danh sách này đều không được hỗ trợ.

~~~java
activeDevelopers.add("Hoa");       // UnsupportedOperationException
activeDevelopers.remove("Lan");     // UnsupportedOperationException
activeDevelopers.set(0, "Linh");    // UnsupportedOperationException
~~~

Nếu chỉ cần đọc kết quả, duyệt, tra cứu hoặc truyền cho API không chỉnh sửa đầu vào thì đây là hợp đồng phù hợp.

## 2. Bốn cách thu thập thường bị nhầm lẫn

| Cách viết | Có từ Java | Hợp đồng về kết quả |
| --- | --- | --- |
| `stream.toList()` | Java 16 | Trả `List` **không sửa đổi được**; không cam kết lớp triển khai hoặc tính serializable. |
| `stream.collect(Collectors.toList())` | Java 8 | Trả `List`; **không bảo đảm** kiểu cụ thể, khả năng sửa đổi, tính serializable hoặc thread-safety. |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Java 8 | Trả kết quả từ `ArrayList::new`, vì vậy biết rõ là `ArrayList` và có thể thêm, xóa, sửa phần tử. |
| `stream.collect(Collectors.toUnmodifiableList())` | Java 10 | Trả `List` **không sửa đổi được** và **không chấp nhận phần tử `null`**. |

Một bảng so sánh theo nhu cầu thực tế:

| Yêu cầu | Lựa chọn phù hợp |
| --- | --- |
| Chỉ đọc kết quả, muốn cú pháp ngắn | `toList()` |
| Cần truyền Collector vào `groupingBy` hoặc `mapping` | `Collectors.toList()` hoặc collector khác phù hợp |
| Bắt buộc có danh sách có thể thêm/xóa | `Collectors.toCollection(ArrayList::new)` |
| Bắt buộc là danh sách không sửa đổi được và không có `null` | `Collectors.toUnmodifiableList()` |
| Cần một kiểu collection khác, như `LinkedList` | `Collectors.toCollection(LinkedList::new)` |
| Cần một `Set` thay vì `List` | `Collectors.toSet()` hoặc `Collectors.toCollection(LinkedHashSet::new)` |

Không nên kết luận `Collectors.toList()` “luôn trả `ArrayList` có thể sửa”. Nhiều phiên bản JDK hiện dùng một triển khai có thể sửa, nhưng đây **không phải bảo đảm của API**. Nếu quyền sửa đổi là một phần của hợp đồng phương thức, hãy biểu diễn nó qua lựa chọn collector rõ ràng.

## 3. Stream.toList() bảo đảm điều gì?

Theo hợp đồng API của `Stream.toList()`:

- **Các phần tử đầu ra được thu vào một `List`.** Với Stream có *encounter order*, danh sách giữ thứ tự gặp phần tử.
- **Danh sách không sửa đổi được (*unmodifiable*).** Các phương thức sửa đổi như `add`, `remove`, `set` và `sort` trên danh sách trả về sẽ ném `UnsupportedOperationException`.
- **Không bảo đảm lớp triển khai cụ thể**, khả năng serialization hoặc các thuộc tính ngoài hợp đồng đã công bố.
- **Đối tượng kết quả có thể là *value-based*.** Không nên dựa vào so sánh tham chiếu `==`, `System.identityHashCode` hay đồng bộ hóa bằng khóa của danh sách đó.
- **Phần tử `null` được chấp nhận.** Không nên đánh đồng hợp đồng của `Stream.toList` với `List.of` hoặc `Collectors.toUnmodifiableList`.

Ví dụ với `null`:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.<String>of("Java", null, "Stream")
        .toList();

System.out.println(values);        // [Java, null, Stream]
System.out.println(values.size()); // 3
~~~

Kết quả vẫn không sửa đổi được, dù có chứa `null`.

### Unmodifiable khác với “bất biến sâu”

Danh sách không thể thay đổi **cấu trúc hoặc phần tử tham chiếu tại các vị trí**, nhưng `toList()` **không tự sao chép sâu** các đối tượng nằm trong danh sách.

~~~java
import java.util.List;

class Box {
    int value;
    Box(int value) { this.value = value; }
}

Box box = new Box(10);
List<Box> boxes = java.util.stream.Stream.of(box).toList();

box.value = 99;

System.out.println(boxes.get(0).value); // 99
// boxes.add(new Box(20)); // UnsupportedOperationException
~~~

Khi `Box` thay đổi qua tham chiếu khác, danh sách vẫn chứa **chính đối tượng Box đó**. Vì vậy `toList()` thích hợp để bảo vệ cấu trúc danh sách, nhưng không tự tạo snapshot bất biến của toàn bộ đồ thị đối tượng.

Nếu cần dữ liệu độc lập với nguồn, hãy tạo DTO bất biến hoặc bản sao có chủ đích trong `map` trước khi thu danh sách.

## 4. Collectors.toList() là một Collector, không phải lệnh trên Stream

Hai câu sau đều thu những phần tử đầu ra vào `List`:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> a = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() >= 3)
        .toList();

List<String> b = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() >= 3)
        .collect(Collectors.toList());
~~~

Cả hai đều có nội dung `[Lan, Minh]`. Nhưng cơ chế API khác nhau:

- `Stream.toList()` là **terminal operation** thuộc giao diện `Stream<T>`. Nó không nhận một đối tượng Collector.
- `Stream.collect(...)` là **terminal operation** nhận Collector hoặc các hàm thu thập cụ thể.
- `Collectors.toList()` là **phương thức tạo một đối tượng `Collector`** kiểu khái quát `Collector<T, ?, List<T>>`; bản thân lời gọi factory không duyệt dữ liệu.
- Collector quy định cách tạo vùng tích lũy, nhận từng phần tử, kết hợp kết quả trung gian và hoàn thiện kết quả. Vì thế Collector có thể được ghép thành một collector phức tạp hơn.

Sơ đồ:

~~~text
Stream<T> → filter/map → toList()                → List<T>
                       [terminal operation]

Stream<T> → filter/map → collect(toList())       → List<T>
                       [terminal operation]
                              ↑
                    Collector được tạo bởi
                       Collectors.toList()
~~~

**Không thể** truyền `Stream::toList` thay cho một Collector tại vị trí cần đối tượng `Collector`. Đây là lý do nhiều ví dụ `groupingBy` dùng `Collectors.toList()` dù bên ngoài đã có `Stream.toList()`.

## 5. Khi nào cần danh sách có thể thay đổi?

Giả sử người dùng lọc được danh sách tên rồi muốn thêm một lựa chọn mặc định `"Khác"` vào cuối để hiển thị trên giao diện. Khi đó, yêu cầu **có thể thêm phần tử** là một phần của hợp đồng.

Cách rõ nhất là dùng `Collectors.toCollection`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> options = Stream.of("Java", "Kotlin", "Scala")
        .filter(language -> language.length() >= 5)
        .collect(Collectors.toCollection(ArrayList::new));

options.add("Khác");

System.out.println(options); // [Kotlin, Scala, Khác]
~~~

Một cách khác nếu trước đó đã có danh sách kết quả chỉ đọc:

~~~java
List<String> readOnly = Stream.of("Java", "Kotlin")
        .toList();

List<String> editable = new ArrayList<>(readOnly);
editable.add("Khác");
~~~

Điểm khác biệt: `editable` là **danh sách mới** có thể chỉnh sửa; `readOnly` vẫn không sửa được. Cách chuyển đổi này thích hợp khi thực sự phải cung cấp **cả hai phiên bản**. Nếu chỉ cần danh sách có thể sửa ngay từ đầu, thu thẳng với `toCollection(ArrayList::new)` giúp diễn đạt rõ hơn và tránh bước sao chép thêm.

Không nên viết:

~~~java
// Không nên phụ thuộc vào khả năng sửa của kết quả này:
List<String> names = Stream.of("A", "B")
        .collect(Collectors.toList());

names.add("C"); // Khả năng thành công không được API bảo đảm.
~~~

Khi gọi một phương thức yêu cầu `ArrayList` cụ thể thay vì `List`, hãy chọn factory tương ứng; đừng ép kiểu kết quả `toList()` hoặc `Collectors.toList()` thành `ArrayList`.

## 6. Thu thập không sửa đổi được và quy tắc với null

`Stream.toList()` và `Collectors.toUnmodifiableList()` cùng tạo danh sách không sửa đổi được, nhưng khác nhau ở **phần tử `null`**:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> accepted = Stream.<String>of("A", null, "B")
        .toList(); // Hợp lệ; có null.

// Ném NullPointerException trong quá trình collect:
List<String> rejected = Stream.<String>of("A", null, "B")
        .collect(Collectors.toUnmodifiableList());
~~~

`Collectors.toUnmodifiableList()` được thiết kế để từ chối `null`. Tương tự, `List.of(...)` (Java 9+) và `List.copyOf(...)` (Java 10+) không chấp nhận phần tử `null`.

Nếu yêu cầu đầu ra phải không có `null`, có thể lọc rõ ràng trước khi thu:

~~~java
import java.util.Objects;

List<String> clean = Stream.<String>of("A", null, "B")
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());

System.out.println(clean); // [A, B]
~~~

Tuy nhiên, **lọc `null` không luôn là chính sách phù hợp**. Đối với dữ liệu kế toán, danh sách ID nghiệp vụ hoặc mã giao dịch, việc tự loại một phần tử có thể làm sai báo cáo. Khi `null` có nghĩa là dữ liệu lỗi, kiểm tra và từ chối dữ liệu sẽ minh bạch hơn.

### Khác biệt với Collections.unmodifiableList

Một cách tạo danh sách không sửa được từ trước Java 16 là:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(source);

source.add("C");
System.out.println(view); // [A, B, C]
~~~

`Collections.unmodifiableList(source)` tạo **view không sửa được trên một danh sách có thể thay đổi**. Khi `source` thay đổi, view phản ánh thay đổi đó. Đây không phải bằng chứng rằng một kết quả `Stream.toList()` cũng là view sống trên nguồn; các phương thức có hợp đồng khác nhau.

Nếu cần một snapshot không sửa được và không chứa `null`, `List.copyOf(source)` là một lựa chọn phù hợp; nếu đang có pipeline Stream và cần hỗ trợ `null`, `Stream.toList()` đáp ứng hợp đồng đó.

## 7. Thứ tự, trùng lặp và Stream song song

Với nguồn có *encounter order*, chẳng hạn `List`, `Stream.toList()` và `collect(Collectors.toList())` đều giữ thứ tự phần tử gặp được trong một pipeline có thứ tự:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(5, 2, 5, 1);

List<Integer> kept = numbers.stream()
        .filter(n -> n >= 2)
        .toList();

System.out.println(kept); // [5, 2, 5]
~~~

**Trùng lặp không bị loại tự động.** Muốn chỉ có phần tử phân biệt, phải yêu cầu bằng `distinct()`; muốn sắp xếp, dùng `sorted()`:

~~~java
List<Integer> sortedDistinct = numbers.stream()
        .distinct()
        .sorted()
        .toList();

System.out.println(sortedDistinct); // [1, 2, 5]
~~~

Trong pipeline song song, thứ tự vẫn được giữ **nếu Stream có encounter order** và các thao tác không làm mất ràng buộc đó:

~~~java
List<Integer> parallelResult = numbers.parallelStream()
        .filter(n -> n >= 2)
        .toList();

System.out.println(parallelResult); // [5, 2, 5]
~~~

`parallel()` **không tự động biến danh sách thành unordered**. Ngược lại, nếu nguồn không có thứ tự xác định, như một số kiểu `Set`, hoặc pipeline chủ động gọi `unordered()`, không được dựa vào thứ tự phần tử thu được.

Cũng không nên giả định `toList()` hoặc `Collectors.toList()` tự tạo ra `TreeSet`, sắp xếp hay đảm bảo uniqueness. Hợp đồng loại collection cần được lựa chọn rõ khi những thuộc tính đó quan trọng.

## 8. Vì sao Collector cần thiết khi grouping và mapping?

Một điểm khác biệt thực tế lớn nhất là **khả năng kết hợp Collector**. Giả sử cần nhóm tên thành viên theo phòng ban.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Member(String name, String department, boolean active) {}

// Giả sử members là List<Member> có dữ liệu hợp lệ.
Map<String, List<String>> namesByDepartment = members.stream()
        .filter(Member::active)
        .collect(Collectors.groupingBy(
                Member::department,
                Collectors.mapping(
                        Member::name,
                        Collectors.toList()
                )
        ));
~~~

Ở đây `Collectors.groupingBy` cần một **downstream Collector** để thu tên thành viên của mỗi phòng ban. `Collectors.mapping` biến `Member` thành `String` trước khi giao cho `Collectors.toList()`. Ta không thể thay trực tiếp `Collectors.toList()` bằng `Stream.toList()` ở vị trí đó, bởi `Stream.toList()` không phải Collector.

Sơ đồ xử lý:

~~~text
Stream<Member>
    |
    +-- filter(active)
    |
    +-- groupingBy(department)
            |
            +-- mapping(name)
                    |
                    +-- Collectors.toList()
                           |
                           +-- List<String> cho từng phòng ban
~~~

Nếu yêu cầu **danh sách của từng nhóm không sửa được và không chứa `null`**, có thể dùng `Collectors.toUnmodifiableList()` ở downstream:

~~~java
Map<String, List<String>> immutableGroupLists = members.stream()
        .filter(Member::active)
        .collect(Collectors.groupingBy(
                Member::department,
                Collectors.mapping(
                        Member::name,
                        Collectors.toUnmodifiableList()
                )
        ));
~~~

Lưu ý: collector phía trong tạo danh sách không sửa được; **điều đó không tự biến Map phía ngoài thành Map không sửa được**. Muốn bảo vệ cả cấu trúc Map phải có quyết định riêng và cần xem lại chính sách với `null`.

Nếu cần một `ArrayList` có thể sửa trong từng nhóm:

~~~java
Map<String, ArrayList<String>> editableGroupLists = members.stream()
        .collect(Collectors.groupingBy(
                Member::department,
                Collectors.mapping(
                        Member::name,
                        Collectors.toCollection(ArrayList::new)
                )
        ));
~~~

Ví dụ này giả định đã import `java.util.ArrayList` và không có khóa nhóm `null`. Với `groupingBy` tiêu chuẩn, khóa phân nhóm `null` không được chấp nhận; cần chuẩn hóa hoặc xử lý dữ liệu trước nếu trường nhóm có thể rỗng.

## 9. Khái niệm Collector và các đặc tính quan trọng

`Collector<T, A, R>` mô tả cách giảm (*mutable reduction*) các phần tử kiểu `T` thông qua vùng tích lũy kiểu `A` để tạo kết quả kiểu `R`.

Một Collector có thể có:

| Thành phần | Vai trò |
| --- | --- |
| `supplier` | Cung cấp container tích lũy mới. |
| `accumulator` | Đưa một phần tử đầu vào vào container. |
| `combiner` | Ghép hai container tích lũy. |
| `finisher` | Chuyển container thành kết quả cuối. |
| `characteristics` | Mô tả một số tính chất như `CONCURRENT`, `UNORDERED` hoặc `IDENTITY_FINISH`. |

Ví dụ `Collectors.toCollection(ArrayList::new)` nhận supplier do người viết chỉ định và sử dụng nó trong quá trình thu thập. Với `parallelStream()`, API có thể tạo các container tích lũy riêng và ghép chúng. Không nên tự thêm phần tử vào một `ArrayList` chia sẻ từ `forEach` song song để mô phỏng Collector.

Đặc tính Collector chỉ được suy ra từ **hợp đồng mà collector công bố**, không từ tên method hoặc lớp container bạn tình cờ thấy ở một JDK. Đặc biệt:

- `CONCURRENT` liên quan đến khả năng tích lũy đồng thời theo hợp đồng Collector; không được mặc định mọi Collector dùng được theo cách đó.
- `UNORDERED` biểu thị collector không cam kết giữ thứ tự encounter trong kết quả.
- `IDENTITY_FINISH` cho phép bỏ qua một bước chuyển đổi kết quả riêng trong những điều kiện của hợp đồng.

Không cần tự xây Collector tùy chỉnh để dùng `toList` thường ngày. Nhưng hiểu cấu trúc Collector giúp phân biệt vì sao `Collectors.toList()` được truyền vào `collect(...)` và vì sao các collector có thể ghép tầng với `groupingBy`, `mapping`, `filtering` hoặc `collectingAndThen`.

## 10. Generic và suy luận kiểu của Stream.toList()

`Stream.toList()` trả về `List<T>`, trong đó `T` đã là kiểu phần tử của **Stream hiện tại**. Java generics không hiệp biến giữa `List<String>` và `List<CharSequence>`.

Ví dụ:

~~~java
import java.util.List;
import java.util.stream.Stream;

// Stream.of("A", "B") có kiểu phần tử String.
// List<CharSequence> wrong = Stream.of("A", "B").toList();
// Sai khi biên dịch: List<String> không phải List<CharSequence>.

List<CharSequence> valid = Stream.<CharSequence>of("A", "B")
        .toList();
~~~

Có thể thay bằng một bước biến đổi kiểu nếu pipeline cần kiểu rộng hơn:

~~~java
List<CharSequence> widened = Stream.of("A", "B")
        .map(value -> (CharSequence) value)
        .toList();
~~~

Điều này không liên quan đến quyền sửa danh sách, mà đến **kiểu `T` mà Stream đang mang**. Với `collect(Collectors.toList())`, suy luận kiểu generic của Collector có thể linh hoạt hơn trong một số ngữ cảnh, nhưng cần ưu tiên chữ ký rõ ràng và biên dịch an toàn thay vì dựa vào ép kiểu danh sách không hợp lệ.

## 11. Tính lazy, vòng đời và nguồn vô hạn

`filter`, `map` và `flatMap` thường là các thao tác trung gian *lazy*. `toList()` và `collect(...)` là terminal operation: chúng kích hoạt pipeline để tạo kết quả.

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of(" java ", " stream ")
        .map(String::trim);

// Chỉ đến đây pipeline mới cần tính toàn bộ đầu ra.
List<String> result = pipeline.toList();

System.out.println(result); // [java, stream]

// Không được dùng lại pipeline đã kết thúc.
// long count = pipeline.count();
~~~

Không thể gọi `toList` xong rồi tiếp tục `count` trên **cùng một đối tượng Stream**. Nếu nguồn là collection có thể duyệt lại, tạo Stream mới; nếu cần kích thước của danh sách vừa thu, dùng `result.size()`.

Vì `toList` phải thu toàn bộ kết quả, **nguồn vô hạn không có giới hạn** là một rủi ro:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Long> firstFive = Stream.iterate(1L, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
~~~

Ngược lại:

~~~java
// Không chạy trong ứng dụng: không có điểm kết thúc hữu hạn.
List<String> neverFinished = Stream.generate(() -> "event")
        .toList();
~~~

Nếu bộ lọc không bao giờ cho phần tử đi qua, `filter(...).limit(n).toList()` vẫn có thể không kết thúc trên nguồn vô hạn vì `limit` tính **số phần tử đầu ra sau bộ lọc**, không phải số lượt xem đầu vào.

Nếu nguồn gắn với tài nguyên như `Files.lines`, cần `try-with-resources` để đóng tài nguyên. Gọi `toList` hay `collect` không tự thay thế việc quản lý tài nguyên I/O.

## 12. Bộ nhớ, hiệu năng và lựa chọn terminal operation

Cả `toList()` và `collect(Collectors.toList())` đều thu và giữ **toàn bộ các phần tử đầu ra** trong bộ nhớ. Tên phương thức không làm việc thu thập trở thành xử lý streaming vô hạn bộ nhớ.

- Với kết quả vài chục hoặc vài trăm phần tử, dùng `toList()` thường đơn giản và dễ đọc.
- Với hàng triệu phần tử, chi phí bộ nhớ tỷ lệ theo số phần tử được giữ; đối tượng phần tử còn có thể chiếm thêm bộ nhớ riêng.
- Một pipeline có `sorted` hoặc `distinct` có thể dùng bộ nhớ trung gian bên cạnh kết quả cuối; `parallel` cũng có chi phí chia/ghép.
- `Stream.toList()` có thể tận dụng thông tin kích thước và chiến lược triển khai để tối ưu, nhưng API **không cam kết** nó luôn nhanh hơn hay tốn ít bộ nhớ hơn một Collector trong mọi trường hợp.
- Nếu chỉ cần số lượng, tổng, cực trị hoặc điều kiện tồn tại, các terminal operation `count`, `sum`, `min`, `max`, `anyMatch` hoặc `reduce` có thể tránh giữ mọi phần tử.
- Nếu cần danh sách làm việc có thể sửa tiếp, `toCollection(ArrayList::new)` thể hiện đúng nhu cầu hơn `toList()` rồi thử sửa kết quả.

Ví dụ chỉ cần biết có đơn hàng bị quá hạn hay không:

~~~java
boolean hasOverdue = orders.stream()
        .anyMatch(order -> order.isOverdue());
~~~

Điều này có thể dừng sớm khi gặp một đơn quá hạn; không cần tạo danh sách toàn bộ đơn hàng quá hạn chỉ để kiểm tra một điều kiện. Ví dụ giả định `orders` là collection có các đối tượng hỗ trợ `isOverdue()`.

Sử dụng Stream song song chỉ nên dựa trên kích thước dữ liệu và kết quả đo. Song song không biến danh sách không sửa được thành danh sách mutable, cũng không bảo đảm có lợi cho pipeline rất nhỏ.

## 13. Thiết kế API: hợp đồng danh sách thuộc về người trả kết quả

Giả sử một service công khai:

~~~java
List<String> findActiveIds();
~~~

Chỉ chữ ký `List<String>` **không cho caller biết** danh sách có được sửa hay không. Nếu dùng `Stream.toList()` trong implementation, hãy truyền đạt hợp đồng “danh sách kết quả không sửa đổi được” qua tài liệu API.

Ví dụ:

~~~java
/**
 * Trả về danh sách ID đã lọc theo encounter order.
 * Danh sách kết quả không hỗ trợ sửa đổi.
 */
public List<String> findActiveIds() {
    return users.stream()
            .filter(User::active)
            .map(User::id)
            .toList();
}
~~~

Trong ví dụ này, `users` và `User` là thành phần giả định của service. Tính không sửa đổi của danh sách giúp service tránh việc caller thêm hoặc xóa phần tử **trên đối tượng List trả về**. Nó không đóng băng trạng thái của các đối tượng nếu chúng có thể thay đổi.

Nếu hợp đồng yêu cầu danh sách có thể sửa, implementation có thể dùng:

~~~java
public List<String> findEditableActiveIds() {
    return users.stream()
            .filter(User::active)
            .map(User::id)
            .collect(Collectors.toCollection(ArrayList::new));
}
~~~

Cả hai method đều nên nêu rõ ý nghĩa với `null`, thứ tự, trùng lặp và khả năng thay đổi của các phần tử nếu các thuộc tính đó quan trọng cho người gọi.

## 14. Lỗi phổ biến và cách nhận diện

| Dấu hiệu | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `UnsupportedOperationException` khi gọi `add` hoặc `set` | Danh sách từ `Stream.toList()` không sửa đổi được | Nếu cần sửa, thu bằng `toCollection(ArrayList::new)` hoặc tạo `new ArrayList<>(result)`. |
| `ClassCastException` khi ép kết quả sang `ArrayList` | `toList()` không cam kết lớp triển khai | Dùng interface `List` hoặc factory yêu cầu `ArrayList` từ đầu. |
| Mã chạy được trên JDK hiện tại nhưng dựa vào khả năng sửa `Collectors.toList()` | API không bảo đảm khả năng sửa đổi của collector này | Dùng `Collectors.toCollection(ArrayList::new)`. |
| `NullPointerException` với `toUnmodifiableList()` | Collector từ chối `null` | Xác minh nguồn; lọc, biến đổi hoặc từ chối `null` theo nghiệp vụ. |
| Không thể dùng `Stream.toList()` trong `groupingBy` | `groupingBy` yêu cầu downstream `Collector` | Dùng `Collectors.toList()` hoặc `Collectors.toUnmodifiableList()`. |
| Thứ tự danh sách không ổn định | Nguồn Stream unordered hoặc mất encounter order | Dùng nguồn có thứ tự hoặc `sorted` theo khóa rõ ràng. |
| Danh sách không sửa được nhưng thuộc tính của phần tử vẫn đổi | `toList` không sao chép sâu đối tượng | Tạo DTO bất biến hoặc bản sao khi cần snapshot dữ liệu. |
| Bộ nhớ tăng mạnh khi chạy `toList()` | Thu toàn bộ kết quả; đầu vào quá lớn | Giới hạn đầu vào, xử lý theo lô hoặc chọn terminal operation tổng hợp. |
| `IllegalStateException` khi gọi thêm terminal operation | Tái sử dụng Stream đã chạy `toList()` | Tạo Stream mới từ nguồn có thể đọc lại hoặc dùng danh sách đã thu. |

## 15. Bài tập tự kiểm tra

### Bài 1 — Có sửa được danh sách không?

~~~java
List<String> values = Stream.of("A", "B")
        .toList();

values.add("C");
~~~

**Đáp án:** Không. `Stream.toList()` trả về danh sách không sửa đổi được. Lời gọi `add` ném `UnsupportedOperationException`. Nếu cần thêm phần tử, hãy thu trực tiếp vào `ArrayList` bằng `Collectors.toCollection(ArrayList::new)`.

### Bài 2 — Có bảo đảm Collectors.toList() là ArrayList không?

~~~java
List<String> values = Stream.of("A", "B")
        .collect(Collectors.toList());
~~~

**Đáp án:** Không. `Collectors.toList()` chỉ cam kết kết quả thuộc `List`. Đặc tả không bảo đảm kiểu triển khai, khả năng sửa đổi, tính serializable hoặc thread-safety. Không được thiết kế API dựa trên quan sát lớp cụ thể ở một phiên bản JDK.

### Bài 3 — Chọn Collector cho nhóm

Yêu cầu: từ `Stream<Member>`, nhóm tên thành viên theo phòng ban, mỗi nhóm là danh sách không sửa được và nguồn bảo đảm không có tên `null`.

**Đáp án:**

~~~java
Map<String, List<String>> namesByDepartment = members.stream()
        .collect(Collectors.groupingBy(
                Member::department,
                Collectors.mapping(
                        Member::name,
                        Collectors.toUnmodifiableList()
                )
        ));
~~~

`toUnmodifiableList` là downstream Collector; `Stream.toList()` không thể được truyền trực tiếp vào vị trí này. Map bên ngoài có hợp đồng riêng.

### Bài 4 — Null khác nhau ra sao?

~~~java
List<String> a = Stream.<String>of("A", null).toList();
List<String> b = Stream.<String>of("A", null)
        .collect(Collectors.toUnmodifiableList());
~~~

**Đáp án:** `a` được tạo thành công và chứa `null`; việc tạo `b` ném `NullPointerException` vì `toUnmodifiableList` không chấp nhận `null`.

### Bài 5 — Danh sách không sửa được có bảo vệ đối tượng con không?

Một `List<Box>` được tạo bởi `Stream.of(box).toList()`. Sau đó caller gọi `box.value = 42`. Giá trị đọc từ `list.get(0).value` có đổi không?

**Đáp án:** Có. Danh sách chứa tham chiếu tới cùng đối tượng `Box`. Tính không sửa đổi chỉ áp dụng cho các phương thức sửa **danh sách**, không làm đối tượng phần tử tự trở thành bất biến.

### Bài 6 — Kết quả sau parallel stream

~~~java
List<Integer> nums = List.of(3, 1, 3, 2);
List<Integer> result = nums.parallelStream()
        .filter(n -> n >= 2)
        .toList();
~~~

**Đáp án:** `[3, 3, 2]`. `List` là nguồn có encounter order, `filter` giữ thứ tự và `toList` thu theo thứ tự gặp được, kể cả khi pipeline dùng `parallelStream()`. Kết quả có phần tử trùng lặp vì không gọi `distinct()`.

## 16. Ghi nhớ

- `Stream.toList()` là terminal operation **từ Java 16**, trả danh sách **không sửa đổi được** và có thể chứa `null`.
- `Collectors.toList()` là **Collector factory** từ Java 8; kết quả thuộc `List` nhưng API không bảo đảm kiểu triển khai hoặc khả năng sửa đổi.
- Muốn danh sách **mutable** và biết rõ kiểu, dùng `Collectors.toCollection(ArrayList::new)`. Muốn danh sách không sửa đổi được và từ chối `null`, dùng `Collectors.toUnmodifiableList()`.
- Trong `groupingBy`, `mapping` và collector lồng nhau, truyền **đối tượng Collector**, không truyền `Stream.toList()`.
- Unmodifiable chỉ bảo vệ cấu trúc của `List`; không tự sao chép sâu các đối tượng bên trong.
- `toList()` và `collect(...)` đều kích hoạt pipeline và thu toàn bộ đầu ra; cân nhắc thứ tự, trùng lặp, vòng đời nguồn và bộ nhớ trước khi chọn.

**Ý chính:** Hãy chọn cách thu thập dựa trên **hợp đồng của kết quả**: danh sách có được sửa hay không, có chấp nhận `null` hay không, có cần Collector để lồng ghép hay không, và có phải duy trì thứ tự không. `Stream.toList()` mang hợp đồng đơn giản cho kết quả chỉ đọc; `Collectors` cung cấp những cơ chế thu thập có thể cấu hình và kết hợp linh hoạt hơn.
