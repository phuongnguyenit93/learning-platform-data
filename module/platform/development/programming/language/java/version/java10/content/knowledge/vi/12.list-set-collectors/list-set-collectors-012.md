# Phân biệt collector Java 10 với `Stream.toList()` của Java 16+

## Mục tiêu bài học

Java 10 bổ sung các collector như `Collectors.toUnmodifiableList()` và `Collectors.toUnmodifiableSet()`, giúp gom phần tử của một stream thành collection **không cho sửa**. Từ **Java 16**, interface `Stream` có thêm phương thức kết thúc `toList()`. Tên gần giống nhau nhưng đây **không phải cùng một API**, và có các khác biệt thực tế về xử lý `null`, suy luận generic, khả năng dùng làm downstream collector và loại kết quả.

Sau bài này, bạn có thể:

- Phân biệt `stream.collect(Collectors.toUnmodifiableList())` (Java 10+) với `stream.toList()` (Java 16+).
- Hiểu `Collectors.toUnmodifiableSet()` dùng để tạo **Set**, không thể thay trực tiếp bằng `Stream.toList()` trả **List**.
- Biết khi nào một stream chứa `null` có thể được xử lý bằng `toList()`, trong khi collector `toUnmodifiableList()`/`toUnmodifiableSet()` từ chối.
- So sánh hai phương thức trên với `Collectors.toList()`, vốn không cam kết kiểu triển khai hoặc khả năng sửa kết quả.
- Lựa chọn đúng API cho stream có thứ tự, dữ liệu trùng, collector lồng trong `groupingBy`, và kiểu generic cần chỉ rõ.
- Chạy chương trình Java 17+ với kết quả xác định.

> Nội dung chỉ sử dụng các cơ chế còn áp dụng trong Java hiện đại. Các API cũ hơn như `Collectors.toList()` vẫn hợp lệ và hữu ích, nhưng không nên đồng nhất hợp đồng của chúng với `Stream.toList()`.

## 1. Ba phương thức có chữ `toList` nhưng hợp đồng khác nhau

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Các ví dụ đặt trong một phương thức:
List<String> a = Stream.of("A", "B")
        .collect(Collectors.toUnmodifiableList()); // Có từ Java 10

List<String> b = Stream.of("A", "B").toList();     // Có từ Java 16

List<String> c = Stream.of("A", "B")
        .collect(Collectors.toList());           // API Collectors đã có từ Java 8
~~~

Trong cả ba trường hợp, kết quả có kiểu tĩnh `List<String>`. Tuy nhiên, **hợp đồng về khả năng sửa, chính sách `null` và hình thức gọi API không giống nhau**.

| Tiêu chí | `collect(Collectors.toUnmodifiableList())` | `Stream.toList()` | `collect(Collectors.toList())` |
| --- | --- | --- | --- |
| Phiên bản có API | Java 10+ | Java 16+ | Java 8+, vẫn dùng hiện nay |
| Cách sử dụng | `Collector` truyền vào `collect` | Phương thức kết thúc của `Stream` | `Collector` truyền vào `collect` |
| Kiểu kết quả | `List<T>` | `List<T>` | `List<T>` |
| Thứ tự | Giữ encounter order nếu stream có thứ tự | Giữ encounter order nếu stream có thứ tự | Giữ encounter order nếu stream có thứ tự |
| Có thể sửa kết quả? | **Không** | **Không** | **Không có cam kết** về khả năng sửa |
| Phần tử `null` | **Từ chối**, ném `NullPointerException` | **Có thể chứa `null`** | Không nên dựa vào một chính sách `null` chưa được cam kết trong hợp đồng |
| Sử dụng làm downstream collector? | **Có** | **Không** | **Có** |
| Giữ phần tử trùng? | Có | Có | Có |

Hai kết quả từ `toUnmodifiableList()` và `Stream.toList()` đều không hỗ trợ `add`, `remove`, `set` hoặc những thao tác sửa cấu trúc khác. Nhưng điều này **không** có nghĩa chúng là cùng một object, cùng một lớp triển khai nội bộ hay có thể dùng thay nhau trong mọi ngữ cảnh.

## 2. `Collectors.toUnmodifiableList()` — collector của Java 10

Cú pháp:

~~~java
var names = Stream.of("An", "Binh", "An")
        .collect(Collectors.toUnmodifiableList());
~~~

`toUnmodifiableList()` là một **factory trả về `Collector<T, ?, List<T>>`**. `collect(...)` là thao tác kết thúc của Stream: nó lấy collector và dùng các bước tích lũy/kết hợp/hoàn thiện kết quả của collector đó.

Đặc điểm chính:

- Kết quả là `List<T>` **không cho sửa**.
- Giữ các phần tử **theo encounter order** khi stream có thứ tự, và **không tự loại trùng**.
- Không chấp nhận phần tử `null`; có thể ném `NullPointerException` nếu stream chứa `null`.
- Có thể truyền collector vào các thao tác `collect` khác, nhất là làm **downstream collector** cho `groupingBy` hoặc `mapping`.
- Không có cam kết về lớp triển khai cụ thể của List kết quả; không dùng `getClass()` để xác định ngữ nghĩa.

Ví dụ:

~~~java
var names = Stream.of("An", "Binh", "An")
        .collect(Collectors.toUnmodifiableList());

System.out.println(names); // [An, Binh, An]
// names.add("Chi");       // UnsupportedOperationException
~~~

Các phần tử trùng vẫn được giữ nguyên vì đây là **List**, không phải Set.

## 3. `Stream.toList()` — phương thức được bổ sung từ Java 16

Cú pháp gọn hơn:

~~~java
var names = Stream.of("An", "Binh", "An").toList();
~~~

`toList()` ở đây là **phương thức trên `Stream<T>`**, không phải phương thức của `Collectors`. Đây là thao tác kết thúc (*terminal operation*), trực tiếp trả `List<T>`.

Hợp đồng chính:

- Kết quả **không cho sửa**; gọi thao tác làm thay đổi nội dung List sẽ ném `UnsupportedOperationException`.
- Giữ encounter order nếu stream có encounter order; nếu không, không được đoán một thứ tự cụ thể.
- Giữ **phần tử trùng**.
- Có thể chứa phần tử `null`, khác `Collectors.toUnmodifiableList()`.
- Không bảo đảm lớp triển khai, khả năng tuần tự hóa hay danh tính object; kết quả có thể là đối tượng *value-based*.

~~~java
var result = Stream.<String>of("An", null, "Binh").toList();

System.out.println(result.size());          // 3
System.out.println(result.contains(null));  // true
// result.add("Chi");                       // UnsupportedOperationException
~~~

Việc chấp nhận `null` **không có nghĩa `null` là lựa chọn thiết kế tốt**. Bạn vẫn cần chính sách rõ ràng cho dữ liệu thiếu. Nếu mục tiêu là loại bỏ `null`, nên lọc theo nghiệp vụ trước khi tạo List.

Đừng lẫn `Stream.toList()` với `List.of(...)` hoặc `List.copyOf(collection)`: hai factory List đó từ chối phần tử `null`. Vì vậy, lấy kết quả `Stream.toList()` rồi truyền vào `List.copyOf` **có thể ném `NullPointerException`** nếu List chứa `null`.

## 4. `Collectors.toUnmodifiableSet()` — cũng được thêm vào Java 10

`Stream.toList()` không phải cách thay thế tương đương cho `Collectors.toUnmodifiableSet()`, vì **List và Set có hợp đồng khác nhau**.

~~~java
var uniqueNames = Stream.of("An", "Binh", "An")
        .collect(Collectors.toUnmodifiableSet());

System.out.println(uniqueNames.size());          // 2
System.out.println(uniqueNames.contains("An"));  // true
~~~

Các điểm quan trọng:

- `Collectors.toUnmodifiableSet()` trả `Set<T>` **không cho sửa**.
- Nó loại phần tử trùng theo `equals`; nếu có những đối tượng khác nhau nhưng bằng nhau, **không cam kết đại diện nào được giữ**.
- Nó **không chấp nhận `null`**.
- Đây là collector **không bảo đảm thứ tự duyệt**, kể cả khi stream nguồn có thứ tự.
- Kết quả khác `Stream.toList()`: List giữ phần tử trùng và thứ tự khi có encounter order.

So sánh một nguồn:

~~~java
var list = Stream.of("A", "B", "A").toList();
var set = Stream.of("A", "B", "A")
        .collect(Collectors.toUnmodifiableSet());

System.out.println(list.size()); // 3
System.out.println(set.size());  // 2
~~~

Nếu muốn một List duy nhất, giữ thứ tự xuất hiện đầu tiên trong stream có thứ tự, có thể dùng `stream.distinct().toList()`. Nhưng nếu API yêu cầu một `Set<T>` để thể hiện tính duy nhất và truy vấn membership, hãy dùng collector Set phù hợp. Đừng cố biến List thành Set chỉ để làm ngắn cú pháp.

## 5. `null`: điểm phân biệt dễ gây lỗi nhất

Hãy quan sát cùng một chuỗi giá trị:

~~~java
var allowed = Stream.<String>of("A", null, "B").toList();
// allowed có 3 phần tử, trong đó có null.

var rejected = Stream.<String>of("A", null, "B")
        .collect(Collectors.toUnmodifiableList());
// Ném NullPointerException: không tạo được List kết quả.
~~~

Chú ý đây là **hai stream khác nhau** được tạo từ cùng dữ liệu. Một stream đã được tiêu thụ bởi terminal operation thì không dùng lại để thu thập lần thứ hai.

Collector tạo Set của Java 10 cũng từ chối `null`:

~~~java
// Ném NullPointerException:
Stream.<String>of("A", null)
        .collect(Collectors.toUnmodifiableSet());
~~~

**Quy tắc chọn nhanh khi nguồn có thể chứa `null`:**

1. Nếu `null` là lỗi dữ liệu, xác thực hoặc lọc trước; dùng `toUnmodifiableList()` để tiếp tục áp dụng ràng buộc chặt, hoặc tự báo lỗi rõ ràng trước khi collect.
2. Nếu nghiệp vụ thật sự cho phép giữ `null` trong List, `Stream.toList()` có thể giữ nguyên dữ liệu; code dùng List sau đó vẫn phải xử lý `null` an toàn.
3. Nếu mục tiêu là Set không cho sửa, `toUnmodifiableSet()` không có lựa chọn giữ `null`; hãy làm sạch hoặc biểu diễn thiếu dữ liệu theo cách khác trước khi thu thập.

Ví dụ lọc `null` một cách có chủ đích:

~~~java
var names = Stream.<String>of("An", null, "Binh")
        .filter(java.util.Objects::nonNull)
        .toList();

System.out.println(names); // [An, Binh]
~~~

Đây là **hành vi do `filter` thực hiện**, không phải `Stream.toList()` tự xóa `null`.

## 6. `Collectors.toList()` không đồng nghĩa `Stream.toList()`

Đây là nhầm lẫn phổ biến:

~~~java
var byCollector = Stream.of("A", "B")
        .collect(Collectors.toList());

var byStream = Stream.of("A", "B").toList();
~~~

`Collectors.toList()` đã có từ Java 8 và vẫn được dùng. Hợp đồng của nó **không đưa ra bảo đảm** về kiểu List cụ thể, khả năng sửa, tính thread-safe hay tính tuần tự hóa của kết quả. Trong các JDK phổ biến, kết quả thường là `ArrayList` có thể sửa, nhưng **không được lấy chi tiết triển khai đó làm hợp đồng của chương trình**.

Ngược lại, `Stream.toList()` **cam kết không cho sửa**. Vì vậy **không nên thay máy móc**:

~~~java
var names = stream.collect(Collectors.toList());
// thành:
var names = stream.toList();
~~~

nếu mã sau đó còn gọi `add`, `remove` hoặc `set`, hay đang dựa vào khả năng sửa không được collector `toList` cam kết.

Khi **cần bảo đảm** có danh sách mutable, nên chọn rõ:

~~~java
var writable = Stream.of("A", "B")
        .collect(Collectors.toCollection(java.util.ArrayList::new));

writable.add("C");
System.out.println(writable); // [A, B, C]
~~~

`Collectors.toCollection(ArrayList::new)` thể hiện rõ loại collection mutable cần tạo, tránh dựa vào implementation ngầm định của `Collectors.toList()`.

## 7. Khi cần downstream collector, `Stream.toList()` không thay thế được

`Stream.toList()` là **terminal operation trả List**, không phải một đối tượng `Collector`. Vì vậy nó không thể truyền trực tiếp vào vị trí yêu cầu downstream collector.

Ví dụ nhóm các chuỗi theo độ dài và tạo List không cho sửa cho từng nhóm:

~~~java
var groups = Stream.of("a", "cat", "dog")
        .collect(Collectors.groupingBy(
                String::length,
                Collectors.toUnmodifiableList()
        ));
~~~

`groups` có kiểu tương ứng `Map<Integer, List<String>>`. Mỗi List của nhóm được tạo bởi `toUnmodifiableList()`, nên không cho sửa:

~~~java
System.out.println(groups.get(3)); // [cat, dog]
// groups.get(3).add("fox");       // UnsupportedOperationException
~~~

Còn dòng sau **không hợp lệ**, vì `Stream.toList()` không phải là một Collector truyền vào `groupingBy`:

~~~java
// Sai về API, không phải mã có thể biên dịch:
// Stream.of("a", "cat").collect(
//     Collectors.groupingBy(String::length, Stream.toList())
// );
~~~

Lưu ý: việc List ở từng nhóm không cho sửa **không tự chứng minh Map bao ngoài cũng không cho sửa**. Nếu hợp đồng yêu cầu một Map snapshot không cho sửa, cần xử lý lớp Map đó riêng, ví dụ áp dụng `Map.copyOf(groups)` khi nguồn phù hợp. `Map.copyOf` không sao chép sâu giá trị, nên việc dùng List không cho sửa ở đây giúp giảm rủi ro thay đổi nội dung nhóm qua các tham chiếu.

Có thể dùng các collector này trong `mapping`, `filtering`, `flatMapping` hoặc các phép phân nhóm khác khi chữ ký API yêu cầu một `Collector`. `Stream.toList()` được gọi khi bạn cần một List kết quả ở **cuối** pipeline.

## 8. Suy luận generic: `toList()` có thể khác lời gọi `collect`

Về mặt cú pháp và type inference, `Stream.toList()` trả `List<T>` theo đúng tham số kiểu `T` của stream hiện tại. Nó không dùng kiểu đích ở phép gán để thay đổi kiểu của phần tử stream đã xác định.

~~~java
List<CharSequence> fromCollector =
        Stream.of("An", "Binh").collect(Collectors.toList());

List<CharSequence> fromStream =
        Stream.<CharSequence>of("An", "Binh").toList();
~~~

Hai khai báo trên hợp lệ. Ở dòng thứ nhất, lời gọi `collect` cùng phương thức generic có thể khai thác kiểu đích trong quá trình suy luận; ở dòng thứ hai, `<CharSequence>` được chỉ định ngay trên factory của stream để tạo `Stream<CharSequence>`.

Trong khi đó:

~~~java
// Lỗi biên dịch: Stream.of("An", "Binh") suy luận Stream<String>
// và Stream.toList() trả List<String>.
// List<CharSequence> invalid = Stream.of("An", "Binh").toList();
~~~

`List<String>` không thể gán cho `List<CharSequence>` vì generic của Java **bất biến**. `Stream.toList()` không tự thực hiện chuyển đổi kiểu `List<String>` sang `List<CharSequence>`.

Cách giải quyết là khai báo đúng kiểu stream nếu nghiệp vụ thực sự cần `CharSequence`:

~~~java
var chars = Stream.<CharSequence>of("An", "Binh").toList();
// chars có kiểu List<CharSequence>.
~~~

Điều này cho thấy “cùng trả List” không có nghĩa các biểu thức generic có quy tắc suy luận hoàn toàn giống nhau.

## 9. Chương trình Java 17+ hoàn chỉnh

Lưu vào file **CollectorVsToListDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorVsToListDemo {
    private static void showAdd(String label, List<String> values) {
        try {
            values.add("C");
            System.out.println(label + ": add supported");
        } catch (UnsupportedOperationException e) {
            System.out.println(label + ": UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        var byCollector = Stream.of("A", "B", "A")
                .collect(Collectors.toUnmodifiableList());
        var byStream = Stream.of("A", "B", "A").toList();
        var byOldCollector = Stream.of("A", "B", "A")
                .collect(Collectors.toList());

        System.out.println("collector list: " + byCollector);
        System.out.println("stream list: " + byStream);
        System.out.println("collect toList size: " + byOldCollector.size());
        showAdd("collector list", byCollector);
        showAdd("stream list", byStream);

        var listWithNull = Stream.<String>of("A", null, "B").toList();
        System.out.println(
                "stream list contains null: " + listWithNull.contains(null)
        );

        try {
            Stream.<String>of("A", null, "B")
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println(
                    "unmodifiable collector null: NullPointerException"
            );
        }

        var set = Stream.of("A", "B", "A")
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("unmodifiable set size: " + set.size());
        System.out.println("unmodifiable set has B: " + set.contains("B"));

        try {
            Stream.<String>of("A", null)
                    .collect(Collectors.toUnmodifiableSet());
        } catch (NullPointerException ex) {
            System.out.println(
                    "unmodifiable set null: NullPointerException"
            );
        }

        var grouped = Stream.of("a", "cat", "dog")
                .collect(Collectors.groupingBy(
                        String::length,
                        Collectors.toUnmodifiableList()
                ));
        System.out.println("length 3: " + grouped.get(3));

        try {
            grouped.get(3).add("fox");
        } catch (UnsupportedOperationException ex) {
            System.out.println(
                    "downstream list: UnsupportedOperationException"
            );
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac CollectorVsToListDemo.java
java CollectorVsToListDemo
~~~

Kết quả chuẩn:

~~~text
collector list: [A, B, A]
stream list: [A, B, A]
collect toList size: 3
collector list: UnsupportedOperationException
stream list: UnsupportedOperationException
stream list contains null: true
unmodifiable collector null: NullPointerException
unmodifiable set size: 2
unmodifiable set has B: true
unmodifiable set null: NullPointerException
length 3: [cat, dog]
downstream list: UnsupportedOperationException
~~~

**Phân tích:**

1. Cả `toUnmodifiableList()` và `Stream.toList()` giữ `[A, B, A]` theo encounter order; hai List đều từ chối thao tác `add`.
2. `Collectors.toList()` vẫn được gọi hợp lệ; ví dụ chỉ in kích thước, không đoán khả năng sửa của kết quả collector này.
3. `Stream.toList()` giữ `null`. Collector `toUnmodifiableList()` từ chối `null` bằng `NullPointerException`.
4. `toUnmodifiableSet()` chỉ giữ hai giá trị duy nhất và từ chối `null`. Ví dụ dùng `size` và `contains`, không in thứ tự duyệt Set.
5. `groupingBy` kết hợp downstream collector `toUnmodifiableList()` tạo các List theo nhóm không cho sửa.

Chương trình không dựa vào class triển khai nội bộ, thông báo chi tiết của ngoại lệ hay thứ tự duyệt Set/Map, nên stdout có tính xác định.

## 10. Encounter order, duplicate và stream song song

### Stream có thứ tự

Với `Stream.of("A", "B", "A")`, encounter order được xác định theo thứ tự các phần tử được đưa vào. Cả `Stream.toList()` và `Collectors.toUnmodifiableList()` giữ thứ tự ấy; vì đây là List, phần tử trùng cũng được giữ.

### Stream không có thứ tự được cam kết

Ví dụ stream lấy từ `HashSet` không bảo đảm encounter order. Gọi `toList()` hoặc thu thập bằng `toUnmodifiableList()` không tự tạo ra một thứ tự có ý nghĩa nghiệp vụ. Nếu cần thứ tự cố định, hãy `sorted()` theo một comparator phù hợp trước khi thu thập.

### Stream song song

Cả hai cách tạo List đều có thể làm việc với pipeline song song khi dùng đúng hợp đồng Stream. Không nên tự kết luận cách nào nhanh hơn chỉ từ cú pháp ngắn hơn; hiệu năng phụ thuộc kích thước, nguồn, pipeline, môi trường, JDK và cách benchmark.

Trong mọi trường hợp, một stream **không được tái sử dụng sau terminal operation**:

~~~java
var stream = Stream.of("A", "B");
var first = stream.toList();

// Không hợp lệ về trạng thái stream đã tiêu thụ:
// var second = stream.collect(Collectors.toUnmodifiableList());
~~~

Nếu cần so sánh, hãy tạo **hai stream mới** từ cùng dữ liệu, như ở ví dụ chương trình hoàn chỉnh.

## 11. Không cho sửa cấu trúc không có nghĩa phần tử bất biến sâu

Một List do `Stream.toList()` hoặc `Collectors.toUnmodifiableList()` trả về không cho `add`, `remove`, `set`, nhưng **không tự sao chép sâu** từng phần tử:

~~~java
var builder = new StringBuilder("old");
var byStream = Stream.of(builder).toList();
var byCollector = Stream.of(builder)
        .collect(Collectors.toUnmodifiableList());

builder.append("-new");

System.out.println(byStream.get(0));    // old-new
System.out.println(byCollector.get(0)); // old-new
~~~

Cả hai List chứa tham chiếu tới cùng một `StringBuilder`. Thay đổi trạng thái của object bên ngoài vẫn có thể quan sát qua List. Nếu nghiệp vụ đòi hỏi dữ liệu bất biến, hãy cân nhắc phần tử immutable hoặc copy trạng thái theo chủ đích trước khi thu thập.

Điều này cũng áp dụng cho Set từ `Collectors.toUnmodifiableSet()`. Với Set, thay đổi thuộc tính tham gia `equals`/`hashCode` của phần tử sau khi đưa vào Set có thể gây lỗi logic; nên ưu tiên phần tử bất biến khi dùng làm phần tử Set.

## 12. Quy tắc lựa chọn trong mã ứng dụng

| Tình huống | Nên cân nhắc | Vì sao |
| --- | --- | --- |
| Đang dùng Java 17+; cần List không cho sửa, chấp nhận dữ liệu hiện có | `stream.toList()` | Ngắn gọn, là terminal operation, giữ encounter order |
| Cần List không cho sửa và không chấp nhận phần tử `null` | `collect(Collectors.toUnmodifiableList())` | Collector Java 10 có hợp đồng từ chối `null` |
| Cần Set không cho sửa, phần tử duy nhất, không có `null` | `collect(Collectors.toUnmodifiableSet())` | Đúng kiểu `Set<T>`, loại trùng |
| Cần List cho từng nhóm trong `groupingBy` hoặc `mapping` | `Collectors.toUnmodifiableList()` làm downstream | `Stream.toList()` không phải Collector |
| Cần List mutable một cách có bảo đảm | `collect(Collectors.toCollection(ArrayList::new))` | Chỉ định rõ implementation có thể sửa |
| Đang có code `collect(Collectors.toList())` | Xem cách dùng sau khi collect | Hợp đồng không cam kết khả năng sửa; tránh thay bằng `toList()` máy móc |
| Muốn loại trùng nhưng vẫn giữ thứ tự xuất hiện đầu tiên trong stream có thứ tự | `stream.distinct().toList()` | List giữ kết quả theo encounter order sau `distinct()` |
| Cần kết quả có thứ tự xác định từ nguồn không có thứ tự | `stream.sorted(...).toList()` | Sắp xếp trước khi thu thập |
| Cần `List<CharSequence>` từ các literal `String` với `Stream.toList()` | `Stream.<CharSequence>of(...).toList()` | Xác định kiểu phần tử stream trước khi gọi `toList()` |

Nếu hỗ trợ runtime Java 10–15, bạn không thể biên dịch code gọi `Stream.toList()` cho phiên bản đó; các collector Java 10 là lựa chọn phù hợp khi cần đầu ra không cho sửa. Nếu target Java 17+ như các ví dụ trong bài, cả hai lựa chọn đều có sẵn.

## 13. Các lỗi thường gặp

**Lỗi 1 — Đồng nhất `Stream.toList()` với `Collectors.toList()`:** cái đầu cam kết List không cho sửa, cái sau **không cam kết** List có thể sửa hay không. Không dùng khả năng sửa quan sát ở một JDK làm cơ sở thiết kế API.

**Lỗi 2 — Tưởng `toUnmodifiableList()` luôn tương đương `Stream.toList()`:** hai phương thức **khác nhau khi có `null`** và ở vị trí sử dụng trong API (`Collector` vs terminal operation).

**Lỗi 3 — Dùng `Stream.toList()` khi mục đích là Set:** List giữ trùng, còn `toUnmodifiableSet()` loại trùng. Chọn kiểu kết quả theo hợp đồng nghiệp vụ, không chỉ chọn cú pháp ngắn.

**Lỗi 4 — Nghĩ kết quả `toUnmodifiableSet()` giữ thứ tự stream:** không có cam kết thứ tự duyệt. Nếu dùng `toString()` của Set để so sánh, test có thể phụ thuộc implementation.

**Lỗi 5 — Cố truyền `Stream.toList()` vào vị trí `Collector`:** `toList()` trả một List; downstream cần một Collector như `Collectors.toUnmodifiableList()`.

**Lỗi 6 — Tái sử dụng một Stream sau khi gọi terminal operation:** stream đã tiêu thụ; phải tạo stream mới nếu cần collect theo cách khác.

**Lỗi 7 — Nghĩ unmodifiable đồng nghĩa phần tử bất biến:** object mutable vẫn có thể đổi trạng thái, dù cấu trúc List/Set không thể sửa.

**Lỗi 8 — Bỏ qua generic invariance:** `Stream<String>.toList()` trả `List<String>`; không tự trở thành `List<CharSequence>`. Chọn kiểu stream phù hợp hoặc sử dụng phương thức generic với target typing đúng.

## 14. Tự kiểm tra

Xem các đoạn dưới đây là minh họa độc lập, với các import thích hợp:

~~~java
var a = Stream.of("x", "y", "x").toList();
var b = Stream.of("x", "y", "x")
        .collect(Collectors.toUnmodifiableList());
var c = Stream.of("x", "y", "x")
        .collect(Collectors.toUnmodifiableSet());

var d = Stream.<String>of("x", null).toList();
// var e = Stream.<String>of("x", null)
//         .collect(Collectors.toUnmodifiableList());
~~~

Hãy trả lời:

1. Kích thước `a`, `b` và `c` là bao nhiêu?
2. Có thể gọi `a.add("z")` hay `b.add("z")` thành công không?
3. `d` có được tạo thành công không?
4. Tại sao dòng `e`, nếu bỏ comment, sẽ không chạy thành công?
5. Nếu dùng `groupingBy(..., downstream)`, dùng `Stream.toList()` hay `Collectors.toUnmodifiableList()`?
6. `Collectors.toList()` có cam kết kết quả là `ArrayList` mutable không?

**Đáp án:** (1) `a=3`, `b=3`, `c=2`; (2) không, cả hai ném `UnsupportedOperationException`; (3) có, `d` chứa `"x"` và `null`; (4) `toUnmodifiableList()` từ chối `null`, ném `NullPointerException`; (5) dùng `Collectors.toUnmodifiableList()` vì nó là Collector; (6) không, không có cam kết như vậy trong API.

## 15. Ghi nhớ và tài liệu chuẩn

- **Java 10:** `Collectors.toUnmodifiableList()`, `Collectors.toUnmodifiableSet()` là **collector** tạo collection không cho sửa; chúng từ chối `null`.
- **Java 16:** `Stream.toList()` là **terminal operation** trả List không cho sửa, giữ `null` nếu stream có `null`.
- **Java 8+:** `Collectors.toList()` vẫn hợp lệ, nhưng **không cam kết khả năng sửa của List**. Khi cần mutable List có bảo đảm, dùng `toCollection(ArrayList::new)`.
- List giữ phần tử trùng và encounter order nếu có; Set loại trùng và `toUnmodifiableSet()` không cam kết thứ tự duyệt.
- `Stream.toList()` không thay thế collector trong các API yêu cầu `Collector`, chẳng hạn downstream của `groupingBy`.
- Cả hai kiểu List không cho sửa đều **không deep copy** phần tử; cần thiết kế riêng nếu muốn bất biến sâu.

Tài liệu chính thức vẫn áp dụng:

- [Java SE 17 — `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())
- [Java SE 17 — `Collectors.toUnmodifiableList()`, `toUnmodifiableSet()`, `toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)
- [Java SE 17 — `Collectors.groupingBy` và downstream collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#groupingBy(java.util.function.Function,java.util.stream.Collector))
- [Java SE 17 — `List` và unmodifiable List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

**Kết luận:** Khi đọc code Java hiện đại, đừng chỉ so sánh tên `toList`. Hãy kiểm tra **phiên bản Java**, **kiểu kết quả List hay Set**, **khả năng sửa**, **chính sách `null`**, **kiểu suy luận generic** và **việc API cần một Collector hay terminal operation**. Đây là các khác biệt quyết định dùng đúng collector Java 10 hay `Stream.toList()` từ Java 16.
