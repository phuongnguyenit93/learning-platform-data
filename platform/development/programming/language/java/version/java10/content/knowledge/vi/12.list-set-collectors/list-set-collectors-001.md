# `Collectors.toUnmodifiableList` và kết quả không thể sửa trong Java

## 1. Mục tiêu của bài học

**`Collectors.toUnmodifiableList()`** là một collector được bổ sung từ **Java 10** trong `java.util.stream.Collectors`. Nó gom các phần tử của một `Stream` thành một **`List` không thể sửa đổi** (*unmodifiable list*), theo **thứ tự gặp phần tử** (*encounter order*) nếu luồng có thứ tự. Đây vẫn là API tiêu chuẩn, hữu ích trong Java hiện đại khi cần thực hiện một pipeline xử lý rồi công bố một danh sách kết quả chỉ đọc về mặt cấu trúc.

Câu hỏi quan trọng không chỉ là “cách dùng collector”, mà còn là “**không thể sửa đổi** nghĩa chính xác là gì?”:

- Không thể `add`, `remove`, `set`, `clear` hoặc dùng thao tác sửa cấu trúc thông qua danh sách kết quả.
- Collector **từ chối phần tử `null`** và ném `NullPointerException` nếu luồng đưa `null` vào kết quả.
- `List` **vẫn cho phép phần tử trùng nhau**, khác với `Set`.
- Nếu nguồn có encounter order, collector **giữ thứ tự**; nó không mặc định sắp xếp.
- Không thể sửa đổi **danh sách** không có nghĩa những **đối tượng phần tử** bên trong trở thành bất biến.
- Không nên dựa vào lớp triển khai cụ thể, địa chỉ đối tượng hay giả định hiệu năng của kết quả.

Bài phân biệt collector này với `Collectors.toList()`, `Collectors.toCollection(...)`, `Stream.toList()` (Java 16+), `List.of(...)` (Java 9+) và `List.copyOf(...)` (Java 10+), giúp chọn đúng API còn áp dụng hiện nay.

### Kết quả học tập

Sau bài này, bạn có thể viết một pipeline Stream tạo danh sách không sửa được, dự đoán thứ tự và ngoại lệ, xử lý `null`, bảo vệ ranh giới API, dùng downstream collector đúng mục đích và giải thích vì sao unmodifiable không đồng nghĩa immutable sâu.

## 2. Vị trí trong Stream API và cú pháp chuẩn

Phương thức được định nghĩa trong lớp tiện ích `java.util.stream.Collectors`:

~~~java
public static <T> Collector<T, ?, List<T>> toUnmodifiableList()
~~~

Nó **trả về một `Collector`**, không trả về một danh sách ngay tại thời điểm gọi. Phép toán kết thúc `Stream.collect(...)` sử dụng collector ấy để tạo `List<T>`.

Ví dụ:

~~~java
import java.util.List;
import java.util.stream.Collectors;

// Trong thân một phương thức:
List<String> result = List.of("java", "kotlin", "go")
        .stream()
        .filter(word -> word.length() >= 4)
        .map(String::toUpperCase)
        .collect(Collectors.toUnmodifiableList());

System.out.println(result); // [JAVA, KOTLIN]
~~~

Các bước:

1. `List.of(...)` tạo nguồn có thứ tự.
2. `stream()` tạo Stream các phần tử `String`.
3. `filter(...)` giữ những phần tử đáp ứng điều kiện.
4. `map(...)` chuyển đổi giá trị.
5. `collect(Collectors.toUnmodifiableList())` gom kết quả thành **`List<String>` không sửa được**.
6. `println` in theo thứ tự đầu vào còn lại vì Stream có encounter order.

Với `var`, Java suy luận kiểu của biến cục bộ từ kết quả `collect`:

~~~java
var words = java.util.stream.Stream.of("A", "B")
        .collect(Collectors.toUnmodifiableList());
// words có kiểu suy luận List<String>, không phải ArrayList<String> theo hợp đồng nguồn.
~~~

**Không dùng `var` để kết luận lớp triển khai runtime.** Kiểu biên dịch được suy luận là `List<String>`; implementation cụ thể có thể thay đổi giữa các JDK.

## 3. “Unmodifiable” nghĩa là kết quả chặn cập nhật

### 3.1. Các thao tác bị từ chối

Sau khi collection hoàn tất:

~~~java
var names = java.util.stream.Stream.of("An", "Binh")
        .collect(Collectors.toUnmodifiableList());

// Các dòng sau biên dịch được nhưng khi thực thi đều gây
// UnsupportedOperationException:
// names.add("Chi");
// names.remove("An");
// names.set(0, "Chi");
// names.clear();
// names.sort(String::compareTo);
~~~

Lý do: interface `List` định nghĩa các phương thức cập nhật. Compiler cho phép gọi vì kiểu `List<String>` có các phương thức ấy, nhưng đối tượng kết quả từ collector **không hỗ trợ cập nhật**. Đây là **lỗi runtime**, không phải lời gọi bị cấm ngay khi biên dịch.

Ví dụ bắt ngoại lệ cụ thể:

~~~java
try {
    names.add("Chi");
} catch (UnsupportedOperationException ex) {
    System.out.println("cannot modify");
}
~~~

Khi chạy, chương trình in `cannot modify`. Việc catch ở đây chỉ để **minh họa hành vi**; trong code ứng dụng thường không nên cố sửa danh sách rồi dựa vào ngoại lệ để rẽ nhánh. Thay vào đó, hãy chọn API đúng với yêu cầu mutable/unmodifiable.

### 3.2. Các thao tác đọc vẫn dùng bình thường

~~~java
var names = java.util.stream.Stream.of("An", "Binh", "An")
        .collect(Collectors.toUnmodifiableList());

System.out.println(names.size());       // 3
System.out.println(names.get(0));       // An
System.out.println(names.contains("An")); // true
System.out.println(names.indexOf("An"));  // 0
~~~

Bạn vẫn đọc, duyệt, so sánh và tạo Stream mới từ kết quả. **Không sửa** không có nghĩa dữ liệu không thể sử dụng.

### 3.3. Không có bảo đảm về identity hay lớp triển khai

Không nên viết:

~~~java
// KHÔNG nên dựa vào:
// names instanceof ArrayList
// names.getClass().getName().contains("ImmutableCollections")
// names == anotherResult
~~~

Đặc tả collector cam kết **hành vi danh sách không sửa được** và **encounter order**; không hứa kiểu lớp triển khai, số lần cấp phát, khả năng tái sử dụng instance hoặc độ phức tạp cố định. Khi kiểm thử, dùng `equals`, `size`, `get` và kiểm tra các hành vi được công bố.

## 4. Encounter order: thứ tự nào được giữ?

### 4.1. List Stream có thứ tự

Với một nguồn `List`, Stream thông thường có **encounter order** (thứ tự gặp các phần tử của nguồn). Collector giữ thứ tự ấy:

~~~java
var result = java.util.List.of("C", "A", "B")
        .stream()
        .collect(Collectors.toUnmodifiableList());

System.out.println(result); // [C, A, B]
~~~

Collector **không tự sort**. Nếu muốn kết quả được sắp xếp, dùng `sorted()` trước khi collect:

~~~java
var sorted = java.util.List.of("C", "A", "B")
        .stream()
        .sorted()
        .collect(Collectors.toUnmodifiableList());

System.out.println(sorted); // [A, B, C]
~~~

Không nên `result.sort(...)` **sau** collect, vì `sort` là thao tác cập nhật và bị từ chối.

### 4.2. `filter` và `map` giữ thứ tự ở pipeline có thứ tự

~~~java
var result = java.util.List.of("a", "bb", "ccc", "dddd")
        .stream()
        .filter(s -> s.length() >= 2)
        .map(String::toUpperCase)
        .collect(Collectors.toUnmodifiableList());

System.out.println(result); // [BB, CCC, DDDD]
~~~

Các bước trên không làm mất encounter order. Kết quả giữ đúng thứ tự những phần tử còn lại sau lọc và chuyển đổi.

### 4.3. Nguồn không có thứ tự: không đoán vị trí phần tử

Một `HashSet` **không cam kết** encounter order. Nếu lấy Stream từ `HashSet` hoặc gọi `unordered()` và không thiết lập thứ tự rõ ràng sau đó, không nên viết test đòi kết quả `toUnmodifiableList` luôn có một thứ tự cụ thể.

~~~java
var source = new java.util.HashSet<>(java.util.Set.of("A", "B", "C"));
var result = source.stream()
        .collect(Collectors.toUnmodifiableList());

// result chứa A, B, C nhưng đừng khẳng định vị trí cụ thể của từng phần tử.
~~~

Nếu thứ tự quan trọng, hãy dùng nguồn có thứ tự rõ ràng, hoặc áp dụng `sorted(...)` trước collector.

### 4.4. Parallel Stream có thể vẫn giữ thứ tự

Với **ordered stream**, collector vẫn giữ encounter order ngay cả khi xử lý song song:

~~~java
var numbers = java.util.stream.IntStream.rangeClosed(1, 5)
        .parallel()
        .boxed()
        .collect(Collectors.toUnmodifiableList());

System.out.println(numbers); // [1, 2, 3, 4, 5]
~~~

Các tác vụ trong `parallel()` có thể chạy theo thứ tự khác nhau, nhưng kết quả của pipeline có encounter order vẫn giữ thứ tự nguồn. Không dùng một kết quả ngẫu nhiên của `parallelStream()` làm bằng chứng rằng công việc chạy tuần tự.

Nếu pipeline thay đổi tính ordered/unordered, hãy xét ngữ nghĩa của toàn bộ pipeline, không chỉ tên collector.

## 5. Danh sách cho phép phần tử trùng: khác với Set

`List` giữ **mọi phần tử đầu vào**, kể cả giá trị trùng lặp:

~~~java
var values = java.util.stream.Stream.of("java", "java", "kotlin")
        .collect(Collectors.toUnmodifiableList());

System.out.println(values);      // [java, java, kotlin]
System.out.println(values.size()); // 3
~~~

`toUnmodifiableList` **không loại duplicate**. Nếu cần loại trùng theo `equals` trong pipeline có thứ tự, có thể thêm `distinct()`:

~~~java
var distinct = java.util.stream.Stream.of("java", "java", "kotlin")
        .distinct()
        .collect(Collectors.toUnmodifiableList());

System.out.println(distinct); // [java, kotlin]
~~~

Cũng có `Collectors.toUnmodifiableSet()` từ Java 10, nhưng đó là collector cho **`Set`**, có hợp đồng khác về phần tử trùng và thứ tự. Đừng thay `toUnmodifiableList` bằng `toUnmodifiableSet` nếu vị trí hoặc số lần xuất hiện mang ý nghĩa nghiệp vụ.

**Ví dụ nghiệp vụ:** danh sách các sự kiện giao dịch cần giữ tất cả lần xuất hiện, kể cả hai giao dịch có cùng nhãn. Nếu dùng Set để loại trùng, có thể làm mất bản ghi hợp lệ. Chọn cấu trúc theo nghĩa của dữ liệu.

## 6. `null`: điểm khác biệt quan trọng

Theo JavaDoc, `Collectors.toUnmodifiableList()` **không chấp nhận phần tử `null`**. Nếu Stream đưa một giá trị `null` vào collector, quá trình collect ném `NullPointerException`.

### 6.1. Ví dụ gây lỗi

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

// Trong thân một phương thức:
var input = Arrays.asList("A", null, "B");

// Dòng sau biên dịch được nhưng ném NullPointerException khi chạy:
// var output = input.stream()
//         .collect(Collectors.toUnmodifiableList());
~~~

Không cần bản thân Stream là `null`; chỉ một **phần tử** được đưa vào collector là `null` cũng đủ gây lỗi.

**Phân biệt:** nếu biến `input == null`, gọi `input.stream()` đã ném NPE **trước** khi collector được gọi. Đây là một lỗi khác với collector nhận phần tử `null`.

### 6.2. Lọc `null` trước khi gom

~~~java
var input = java.util.Arrays.asList("A", null, "B");

var filtered = input.stream()
        .filter(java.util.Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());

System.out.println(filtered); // [A, B]
~~~

Cách này phù hợp nếu nghiệp vụ định nghĩa “bản ghi rỗng thì bỏ qua”. **Đánh đổi:** số lượng và chỉ số phần tử thay đổi. Nếu vị trí mang ý nghĩa, việc lọc có thể làm sai dữ liệu.

### 6.3. Thay `null` bằng giá trị có chủ đích

~~~java
var input = java.util.Arrays.asList("A", null, "B");

var normalized = input.stream()
        .map(value -> value == null ? "(missing)" : value)
        .collect(Collectors.toUnmodifiableList());

System.out.println(normalized); // [A, (missing), B]
~~~

Việc dùng một chuỗi đại diện phải được quy định rõ. Nếu `"(missing)"` có thể trùng với một giá trị thật, hãy dùng mô hình dữ liệu có trạng thái thiếu vắng tường minh thay vì âm thầm thay thế.

### 6.4. Cả `map` cũng có thể tạo ra `null`

Ngay cả khi nguồn không chứa `null`, một phép biến đổi vẫn có thể tạo phần tử `null`:

~~~java
var input = java.util.List.of("A", "unknown", "B");

// Cố ý minh họa lỗi:
// var output = input.stream()
//         .map(value -> value.equals("unknown") ? null : value)
//         .collect(Collectors.toUnmodifiableList());
~~~

Đoạn trên sẽ ném NPE khi collect. Khi cần lọc giá trị trống, đặt `filter(Objects::nonNull)` **sau** bước `map` có thể tạo `null`.

### 6.5. Không phụ thuộc thời điểm hoặc thông điệp NPE

API cam kết ném `NullPointerException` khi collector gặp giá trị `null`; không nên yêu cầu test khớp chi tiết stack trace, thông điệp của JDK hoặc nội bộ giai đoạn *accumulation/finisher*. Các chi tiết ấy có thể thay đổi theo implementation.

Đối với hệ thống nghiệp vụ cần báo rõ dữ liệu hỏng ở vị trí nào, nên validation với lỗi có ngữ cảnh trước khi collect hoặc giữ chỉ số/bản ghi nguồn trong kiểu dữ liệu thích hợp.

## 7. Danh sách không sửa được không phải deep immutable

Một `List` không cho cập nhật **cấu trúc** vẫn có thể chứa **phần tử mutable**.

Ví dụ:

~~~java
class Note {
    private String title;

    Note(String title) {
        this.title = title;
    }

    void rename(String next) {
        title = next;
    }

    String title() {
        return title;
    }
}
~~~

Trong phương thức:

~~~java
var note = new Note("draft");
var result = java.util.stream.Stream.of(note)
        .collect(Collectors.toUnmodifiableList());

note.rename("edited");
System.out.println(result.get(0).title()); // edited
~~~

Kết quả `result` không cho `add` hay `set`, nhưng vẫn tham chiếu **đúng đối tượng `note` ban đầu**. Khi đối tượng ấy thay đổi trạng thái, dữ liệu quan sát được qua danh sách cũng thay đổi.

Có hai lớp trách nhiệm:

1. **Cấu trúc danh sách:** `toUnmodifiableList` bảo vệ khỏi sửa bằng các phương thức mutator của danh sách kết quả.
2. **Trạng thái phần tử:** người thiết kế kiểu `Note` chịu trách nhiệm về khả năng thay đổi, sao chép, validation và quyền sở hữu.

`toUnmodifiableList` **không tự deep-copy, không clone phần tử và không biến `ArrayList` bên trong từng phần tử thành immutable**.

### 7.1. Khi nào có thể xem kết quả là bất biến về giá trị?

Nếu danh sách chỉ chứa phần tử bất biến như `String` hoặc những giá trị bất biến được thiết kế đúng cách, có thể xem danh sách kết quả là bất biến về **trạng thái quan sát được**. Nếu chứa phần tử mutable, không thể kết luận như vậy.

Một record chứa component mutable cũng không tự deep-freeze:

~~~java
record Row(String id, java.util.List<String> tags) {}
~~~

`Row` không tự sao chép `tags`. Nếu muốn record giữ snapshot an toàn, cần defensive copy:

~~~java
record SafeRow(String id, java.util.List<String> tags) {
    public SafeRow {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

Các đoạn định nghĩa record là ví dụ độc lập. `List.copyOf` chỉ bảo vệ cấu trúc danh sách; nếu component chứa phần tử mutable, vẫn cần kiểm tra sâu tùy yêu cầu.

## 8. Kết quả collect khác với view của nguồn

Một kết quả `toUnmodifiableList` **không phải unmodifiable view đọc xuyên qua collection nguồn**. Sau khi pipeline collect hoàn tất, cấu trúc danh sách kết quả không tự phản ánh các phần tử được thêm/xóa khỏi nguồn sau đó.

~~~java
var source = new java.util.ArrayList<>(java.util.List.of("A", "B"));
var snapshot = source.stream()
        .collect(Collectors.toUnmodifiableList());

source.add("C");
System.out.println(snapshot); // [A, B]
~~~

Đối chiếu với:

~~~java
var source = new java.util.ArrayList<>(java.util.List.of("A", "B"));
var view = java.util.Collections.unmodifiableList(source);

source.add("C");
System.out.println(view); // [A, B, C]
~~~

Hai giá trị đều từ chối cập nhật qua chính tham chiếu kết quả, nhưng:

- **Collector:** chốt cấu trúc những phần tử đã đi qua pipeline, không là view sống của nguồn.
- **`Collections.unmodifiableList`:** bọc một *backing list*, có thể phản ánh thay đổi mà caller thực hiện trực tiếp trên backing list.

Trong cả hai trường hợp, nếu phần tử là đối tượng mutable được chia sẻ, trạng thái phần tử vẫn có thể thay đổi. Sự khác biệt đang nói về **membership/vị trí phần tử của danh sách**, không phải deep copy.

**Lưu ý concurrency:** nếu collection nguồn bị sửa đồng thời khi Stream đang duyệt, `collect` không tự biến thao tác đó thành snapshot nguyên tử; có thể xảy ra lỗi hoặc kết quả không nhất quán tùy nguồn và giao thức đồng bộ. Hãy bảo vệ đầu vào trước khi khởi chạy pipeline nếu cần một snapshot nhất quán.

## 9. So sánh đúng với những API gần giống

Đây là bảng cần nhớ khi lựa chọn trong code Java hiện đại:

| API | Xuất hiện từ | Kết quả có cam kết unmodifiable? | Chính sách `null` | Dùng khi |
| --- | --- | --- | --- | --- |
| `stream.collect(Collectors.toUnmodifiableList())` | **Java 10** | **Có** | **Từ chối `null`**, ném NPE | Chốt kết quả Stream thành List không sửa được, null-free. |
| `stream.collect(Collectors.toList())` | Java 8 | **Không cam kết** có thể hay không thể sửa | Không có lời cam kết null-free giống `toUnmodifiableList` | Chỉ cần một List, không phụ thuộc tính mutable. |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Java 8 | Tạo `ArrayList` có thể sửa | Theo hợp đồng `ArrayList` | Cần sửa tiếp sau khi collect. |
| `stream.toList()` | **Java 16** | **Có** | Không có quy tắc từ chối `null` như collector trên; trong JDK 17+ minh họa có thể giữ `null` | Cú pháp ngắn, cần List unmodifiable, chấp nhận chính sách phần tử của nguồn. |
| `List.of(elements...)` | Java 9 | **Có** | Không chấp nhận `null` | Đã biết các phần tử tại nơi tạo. |
| `List.copyOf(existingCollection)` | **Java 10** | **Có** | Nguồn và phần tử phải khác `null` | Có Collection sẵn và muốn snapshot. |
| `Collections.unmodifiableList(backing)` | API lâu đời, vẫn dùng được | **Có**, qua view | Backing list có thể chứa `null` | Muốn live read-only view theo nguồn. |

**Ghi nhớ:** cùng có tên `toList` nhưng **`Collectors.toList()` khác `Stream.toList()`**.

### 9.1. `Collectors.toList()` không cam kết mutable

~~~java
var result = java.util.stream.Stream.of("A", "B")
        .collect(Collectors.toList());
~~~

JavaDoc không bảo đảm loại list, tính mutable, serialization hay thread safety. Dù trong một JDK hiện tại kết quả có thể là `ArrayList`, **đừng viết code nghiệp vụ phụ thuộc vào điều ấy**. Nếu cần mutable `ArrayList`:

~~~java
var editable = java.util.stream.Stream.of("A", "B")
        .collect(Collectors.toCollection(java.util.ArrayList::new));

editable.add("C"); // hợp lệ
~~~

Nếu cần unmodifiable với null bị từ chối, dùng `toUnmodifiableList()`.

### 9.2. `Stream.toList()` không phải collector

~~~java
var result = java.util.stream.Stream.of("A", "B").toList();
~~~

Đây là **terminal method** của interface `Stream`, có từ Java 16, trả List không cho sửa đổi. Nó không sử dụng cú pháp `collect(Collectors...)`.

Một trường hợp phân biệt chính sách dữ liệu:

~~~java
var withNull = java.util.Arrays.asList("A", null, "B");

var byStreamMethod = withNull.stream().toList();
// Trên JDK 17+ hiện dùng: [A, null, B]

// Dòng dưới ném NullPointerException:
// var byCollector = withNull.stream()
//         .collect(Collectors.toUnmodifiableList());
~~~

Không được thay hai cách trên máy móc nếu luồng có thể tạo `null`. **Chọn dựa trên hợp đồng cần bảo đảm**, không chỉ cú pháp ngắn hay tên tương tự.

### 9.3. `List.copyOf` khi có dữ liệu đầu vào là Collection

~~~java
var source = java.util.List.of("A", "B");
var copy = java.util.List.copyOf(source);
~~~

`List.copyOf` không cần Stream nếu mục tiêu chỉ là chốt nội dung của một Collection đã có. Nó từ chối nguồn `null` hoặc phần tử `null`. Khi nguồn đã là unmodifiable List phù hợp, runtime có thể tái sử dụng instance; không được xem reference equality là hợp đồng.

Đừng thêm Stream vô cớ chỉ để sao chép một danh sách mà không lọc, không chuyển đổi gì. Ngược lại, khi cần `filter`, `map`, `sorted`, collector phù hợp với pipeline.

### 9.4. `Collectors.collectingAndThen(...)` có còn cần không?

`collectingAndThen(downstream, finisher)` vẫn là API hợp lệ và hữu ích để áp dụng một bước cuối cho kết quả collector. Nhưng nếu mục đích **duy nhất** là tạo List không cho sửa, `Collectors.toUnmodifiableList()` thường diễn đạt ý định rõ hơn:

~~~java
var direct = java.util.stream.Stream.of("A", "B")
        .collect(Collectors.toUnmodifiableList());
~~~

Không nên thay mọi pipeline `collectingAndThen(...)` bằng collector này mà không kiểm tra cách xử lý `null`, loại collection, công việc trong finisher hoặc ngữ nghĩa live view/snapshot của bản cũ.

## 10. Downstream collector: chỉ phần nào thực sự unmodifiable?

Các collector có thể lồng nhau. Ví dụ nhóm chuỗi theo độ dài:

~~~java
var grouped = java.util.stream.Stream.of("a", "bb", "cc")
        .collect(Collectors.groupingBy(
                String::length,
                Collectors.toUnmodifiableList()
        ));

System.out.println(grouped.get(2)); // [bb, cc]
~~~

Đây là `Map<Integer, List<String>>`. **Giá trị List ở mỗi nhóm** được tạo bằng `toUnmodifiableList` nên không cho sửa:

~~~java
// grouped.get(2).add("dd"); // UnsupportedOperationException
~~~

Nhưng **bản thân Map do `groupingBy` trả về không được collector phía trong hứa là unmodifiable**. Đừng kết luận cả cấu trúc lồng nhau bất biến chỉ vì List values unmodifiable.

Nếu thực sự cần chốt Map bên ngoài (và các List phần tử đã được chốt), có thể dùng:

~~~java
var frozenGroups = java.util.Map.copyOf(grouped);
~~~

Điều này bảo vệ phép thêm/xóa ánh xạ trên Map, còn mỗi List value đã không sửa được. Nếu các phần tử của List là mutable, tính bất biến sâu vẫn chưa có.

### 10.1. Kết hợp `mapping` và `toUnmodifiableList`

~~~java
record User(String name) {}

var users = java.util.List.of(new User("An"), new User("Binh"));

var names = users.stream()
        .collect(Collectors.mapping(
                User::name,
                Collectors.toUnmodifiableList()
        ));

System.out.println(names); // [An, Binh]
~~~

Đây là một dạng downstream khác, hữu ích trong các phép `groupingBy` hoặc `partitioningBy`. Trong pipeline đơn giản, `map(User::name).collect(Collectors.toUnmodifiableList())` thường dễ đọc hơn. Cả hai đều tuân theo chính sách không nhận `null` của collector đích.

## 11. Thứ tự, duplicate và kết quả của các phép biến đổi

Một bài toán hay gặp: đọc dữ liệu, chuẩn hóa, lọc rỗng, rồi trả danh sách không sửa được.

~~~java
var source = java.util.List.of(" java ", "go", " java ", "rust");

var names = source.stream()
        .map(String::trim)
        .filter(s -> s.length() >= 4)
        .map(String::toUpperCase)
        .collect(Collectors.toUnmodifiableList());

System.out.println(names); // [JAVA, JAVA, RUST]
~~~

Phân tích:

- `map(String::trim)` đổi `" java "` thành `"java"`.
- `filter(...)` loại `"go"` vì độ dài chưa đủ.
- `map(String::toUpperCase)` chuẩn hóa các từ còn lại.
- `toUnmodifiableList` **giữ cả hai** phần tử `"JAVA"`, vì List không loại duplicate.
- Thứ tự vẫn là thứ tự các phần tử đi qua ordered stream.

Nếu nghiệp vụ muốn không trùng:

~~~java
var distinctNames = source.stream()
        .map(String::trim)
        .filter(s -> s.length() >= 4)
        .map(String::toUpperCase)
        .distinct()
        .collect(Collectors.toUnmodifiableList());

System.out.println(distinctNames); // [JAVA, RUST]
~~~

Nếu nghiệp vụ cần kết quả theo thứ tự chữ cái:

~~~java
var sortedNames = source.stream()
        .map(String::trim)
        .filter(s -> s.length() >= 4)
        .map(String::toUpperCase)
        .sorted()
        .collect(Collectors.toUnmodifiableList());

System.out.println(sortedNames); // [JAVA, JAVA, RUST]
~~~

Cần quyết định **sắp xếp, loại trùng và lọc** ở pipeline trước khi collect, vì danh sách sau collect đã đóng cấu trúc.

## 12. Chương trình Java 17+ hoàn chỉnh, chạy được

Tạo file **`UnmodifiableListCollectorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class UnmodifiableListCollectorDemo {
    static final class Note {
        private String label;

        Note(String label) {
            this.label = label;
        }

        void rename(String value) {
            this.label = value;
        }

        String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of(" java ", "go", " java ", "rust"));
        var result = source.stream()
                .map(String::trim)
                .filter(s -> s.length() >= 4)
                .map(String::toUpperCase)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("result=" + result);

        source.add("new");
        System.out.println("after source add=" + result);

        try {
            result.add("KOTLIN");
        } catch (UnsupportedOperationException ex) {
            System.out.println("add blocked");
        }
        try {
            result.set(0, "X");
        } catch (UnsupportedOperationException ex) {
            System.out.println("set blocked");
        }

        var valuesWithNull = Arrays.asList("A", (String) null, "B");
        try {
            valuesWithNull.stream().collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("null rejected");
        }

        var cleaned = valuesWithNull.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("cleaned=" + cleaned);
        System.out.println("Stream.toList=" + valuesWithNull.stream().toList());

        var note = new Note("draft");
        var notes = Stream.of(note).collect(Collectors.toUnmodifiableList());
        note.rename("edited");
        System.out.println("mutable element=" + notes.get(0).label());

        var parallel = IntStream.rangeClosed(1, 5)
                .parallel()
                .boxed()
                .collect(Collectors.toUnmodifiableList());
        System.out.println("parallel ordered=" + parallel);

        var mutable = Stream.of("one", "two")
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add("three");
        System.out.println("mutable result=" + mutable);

        var grouped = Stream.of("a", "bb", "cc")
                .collect(Collectors.groupingBy(
                        String::length, Collectors.toUnmodifiableList()));
        System.out.println("group length 2=" + grouped.get(2));
        try {
            grouped.get(2).add("dd");
        } catch (UnsupportedOperationException ex) {
            System.out.println("group value blocked");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 UnmodifiableListCollectorDemo.java
java UnmodifiableListCollectorDemo
~~~

**Stdout chính xác:**

~~~text
result=[JAVA, JAVA, RUST]
after source add=[JAVA, JAVA, RUST]
add blocked
set blocked
null rejected
cleaned=[A, B]
Stream.toList=[A, null, B]
mutable element=edited
parallel ordered=[1, 2, 3, 4, 5]
mutable result=[one, two, three]
group length 2=[bb, cc]
group value blocked
~~~

### 12.1. Giải thích từng kết quả

1. **`result`:** pipeline đã trim, lọc độ dài và uppercase; collector giữ thứ tự và giữ hai giá trị `JAVA` giống nhau.
2. **`after source add`:** thêm `"new"` vào `source` sau khi collect không làm thay đổi danh sách `result`. `result` không là live view của source.
3. **`add blocked` / `set blocked`:** `List` kết quả không cho thêm phần tử hoặc thay tại một vị trí.
4. **`null rejected`:** collector từ chối phần tử `null` và ném NPE.
5. **`cleaned`:** lọc `null` trước collect, được `[A, B]`.
6. **`Stream.toList`:** method Java 16+ cho List không sửa được; ví dụ JDK 17+ giữ `null` trong danh sách thay vì áp dụng quy tắc NPE của collector.
7. **`mutable element`:** chính đối tượng `Note` vẫn thay đổi được; tính không sửa cấu trúc là *shallow*.
8. **`parallel ordered`:** Stream từ `IntStream.rangeClosed` có encounter order; `parallel()` không làm mất thứ tự trong kết quả collector.
9. **`mutable result`:** `Collectors.toCollection(ArrayList::new)` tạo `ArrayList` cụ thể cho phép `add`.
10. **`group length 2` / `group value blocked`:** downstream collector tạo danh sách nhóm không cho cập nhật; không mặc nhiên kết luận Map ngoài cùng unmodifiable.

Chương trình được thiết kế để không phụ thuộc thứ tự duyệt của `HashSet`, bản địa hóa số/ngày, luồng cạnh tranh hoặc tên lớp triển khai JDK. Các ngoại lệ được bắt theo **kiểu ngoại lệ**, không dựa vào thông điệp runtime.

## 13. Lỗi thường gặp và cách sửa

| Giả định sai hoặc lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “`Collectors.toUnmodifiableList` là một phương thức trả ngay List.” | Nhầm giữa Collector và terminal operation. | Dùng `stream.collect(Collectors.toUnmodifiableList())`. |
| “Kết quả là List nên `add`, `set` dùng được.” | `UnsupportedOperationException` ở runtime. | Cập nhật trong pipeline hoặc chọn collector mutable. |
| “`toUnmodifiableList` tự sắp xếp.” | Thứ tự không theo ý định. | Áp dụng `sorted()` trước khi collect. |
| “Mọi Stream đều có encounter order.” | Test dựa vào thứ tự nguồn unordered bị sai. | Dùng nguồn ordered hoặc sort tường minh. |
| “Collector danh sách tự loại phần tử trùng.” | Số bản ghi không đúng mong muốn. | Giữ duplicate nếu nghiệp vụ cần; dùng `distinct()` khi cần loại. |
| “Collector tự bỏ qua phần tử `null`.” | `NullPointerException` khi collect. | `filter(Objects::nonNull)` hoặc quy tắc mặc định có chủ đích. |
| “`Stream.toList()` và `Collectors.toUnmodifiableList()` luôn giống nhau.” | Khác biệt chính sách `null`. | Kiểm tra đầu vào và chọn hợp đồng. |
| “`Collectors.toList()` luôn tạo `ArrayList` mutable.” | Code phụ thuộc implementation. | Cần mutable rõ ràng thì dùng `toCollection(ArrayList::new)`. |
| “Unmodifiable list chứa immutable objects.” | Đối tượng phần tử vẫn có thể đổi. | Dùng phần tử bất biến hoặc defensive copy trước khi collect. |
| “`groupingBy(..., toUnmodifiableList())` làm cả Map bất biến.” | Có thể sửa Map ngoài. | Chốt thêm Map nếu cần; phân biệt từng cấp. |
| “`parallel()` luôn cho thứ tự ngẫu nhiên.” | Suy luận sai về encounter order của kết quả. | Ordered stream + ordered collector vẫn giữ encounter order. |
| “Có thể dùng `result.getClass()` để xác định API contract.” | Dễ vỡ khi nâng JDK. | Dựa vào JavaDoc, không vào lớp nội bộ. |
| “Có thể sửa nguồn đồng thời khi Stream đang collect vì kết quả không sửa được.” | Có thể gây race, lỗi hoặc kết quả không nhất quán. | Bảo đảm nguồn ổn định và an toàn trong lúc duyệt. |

## 14. Chọn collector trong code thực tế

### 14.1. Trả về dữ liệu từ service

Giả sử một service muốn trả danh sách tên hợp lệ, không để caller thay nội dung danh sách kết quả:

~~~java
static List<String> normalizedNames(List<String> raw) {
    java.util.Objects.requireNonNull(raw, "raw");

    return raw.stream()
            .filter(java.util.Objects::nonNull)
            .map(String::trim)
            .filter(name -> !name.isEmpty())
            .collect(Collectors.toUnmodifiableList());
}
~~~

Phương thức trên:

- Từ chối **chính tham chiếu nguồn `null`** bằng validation rõ ràng.
- Bỏ **phần tử `null`** theo chính sách được chủ động chọn (không phải mặc định của collector).
- Chuẩn hóa và bỏ chuỗi trống.
- Trả List không thể sửa cấu trúc qua tham chiếu kết quả.
- Vì phần tử là `String` bất biến, giá trị kết quả cũng ổn định hơn so với một List chứa đối tượng mutable.

Nếu mỗi phần tử là mã nghiệp vụ bắt buộc, **lọc `null` có thể làm mất dữ liệu**; khi đó nên thay bằng validation báo lỗi và không tạo snapshot.

### 14.2. Khi cần tiếp tục xử lý mutable

Nếu muốn người gọi có thể thêm/xóa:

~~~java
static ArrayList<String> editableNames(List<String> raw) {
    return raw.stream()
            .map(String::trim)
            .collect(Collectors.toCollection(ArrayList::new));
}
~~~

`ArrayList` trả về mutable. Không nên collect thành List unmodifiable rồi cố `add`, bắt lỗi và tạo lại list trừ khi luồng xử lý thật sự yêu cầu hai giai đoạn khác nhau.

### 14.3. Khi chỉ cần kết quả không sửa được và Java 16+

Nếu **không cần** tính năng downstream collector, `stream.toList()` có thể là cách viết gọn:

~~~java
var result = java.util.stream.Stream.of("A", "B")
        .map(String::toLowerCase)
        .toList();
~~~

Cần lưu ý chính sách `null` khác so với `Collectors.toUnmodifiableList()`. **Không mặc định** phương thức ngắn hơn cũng bảo đảm null-free.

### 14.4. Lựa chọn dựa trên hợp đồng thay vì benchmark phỏng đoán

Đừng khẳng định `toUnmodifiableList()` chắc chắn nhanh/chậm hơn `Stream.toList()` hoặc `List.copyOf` trên mọi JDK và kích thước dữ liệu. Khác biệt còn phụ thuộc pipeline, số phần tử, collector, parallel mode và implementation. Trước tiên chọn phương thức thể hiện **quy tắc dữ liệu** đúng; nếu hiệu năng quan trọng, đo bằng benchmark trên workload thực tế.

## 15. Luyện tập có đáp án

**Câu 1.** Đoán đầu ra:

~~~java
var names = java.util.stream.Stream.of("A", "A", "B")
        .collect(Collectors.toUnmodifiableList());
System.out.println(names.size());
System.out.println(names);
~~~

**Đáp án:** In `3` và `[A, A, B]` vì List giữ phần tử trùng và Stream nguồn có thứ tự.

**Câu 2.** Khi gọi `names.add("C")` sau collect, lỗi xảy ra khi biên dịch hay chạy?

**Đáp án:** Câu lệnh biên dịch hợp lệ, nhưng khi chạy ném `UnsupportedOperationException` vì danh sách kết quả unmodifiable.

**Câu 3.** Với `Arrays.asList("A", null)`, collector có âm thầm bỏ `null` không?

**Đáp án:** Không. `toUnmodifiableList` ném `NullPointerException`. Nếu muốn bỏ giá trị thiếu, đặt `filter(Objects::nonNull)` trước collector, sau khi cân nhắc tác động nghiệp vụ.

**Câu 4.** Vì sao `Stream.of("B", "A").sorted().collect(...)` trả `[A, B]` nhưng collector không phải phương thức sort?

**Đáp án:** `sorted()` thay đổi thứ tự encounter order của pipeline. Collector chỉ gom theo encounter order của Stream đưa tới.

**Câu 5.** Có nên thay `Collectors.toUnmodifiableList()` bằng `Collectors.toList()` vì ở máy mình `toList()` trả `ArrayList` hay không?

**Đáp án:** Không. `Collectors.toList()` không cam kết unmodifiable hoặc mutable. Chỉ đổi khi yêu cầu thực sự thay đổi; nếu cần mutable rõ ràng, dùng `toCollection(ArrayList::new)`.

**Câu 6.** `Stream.toList()` và `Collectors.toUnmodifiableList()` giống nhau về khả năng sửa kết quả không?

**Đáp án:** Cả hai trả List không cho sửa; khác biệt quan trọng là collector **cấm phần tử `null`**, còn `Stream.toList()` không có hợp đồng cấm `null` tương tự và ví dụ Java 17+ có thể giữ nó.

**Câu 7.** Một `List<Note>` không cho sửa được tạo bằng collector. Phần tử `Note` có còn đổi tên được không?

**Đáp án:** Có nếu bản thân `Note` mutable và caller còn giữ tham chiếu. Collector không deep-copy hay đóng băng phần tử.

**Câu 8.** Với `groupingBy(key, toUnmodifiableList())`, cả Map đã được bảo vệ khỏi `put` chưa?

**Đáp án:** Chưa thể khẳng định. Collector phía trong bảo vệ **List của từng nhóm**. Nếu muốn Map ngoài cùng không cho sửa, hãy áp dụng một bước chốt Map phù hợp như `Map.copyOf(grouped)`, đồng thời xem xét kiểu phần tử.

**Câu 9.** Một Stream song song từ `IntStream.rangeClosed(1,5)` có kết quả chắc chắn `[1,2,3,4,5]` khi collect bằng phương thức này không?

**Đáp án:** Có với pipeline ordered như ví dụ, vì collector giữ encounter order. Lịch chạy tác vụ song song không định nghĩa thứ tự danh sách kết quả.

**Câu 10.** Muốn output có thể gọi `add` sau khi collect, nên chọn API nào?

**Đáp án:** `Collectors.toCollection(ArrayList::new)` khi cần `ArrayList` mutable. Đừng dùng `toUnmodifiableList` rồi sửa kết quả.

## 16. Checklist trước khi dùng `toUnmodifiableList`

- [ ] Tôi cần **List** (giữ thứ tự và duplicate), không phải Set.
- [ ] Tôi thực sự muốn kết quả **không thể sửa cấu trúc** sau terminal operation.
- [ ] Tôi biết nguồn có encounter order hay không; nếu cần thứ tự tuyệt đối, đã sắp xếp hoặc chọn nguồn ordered.
- [ ] Tôi biết pipeline có thể tạo `null` ở bước nào; đã quyết định reject/filter/default theo nghiệp vụ.
- [ ] Tôi phân biệt `Collectors.toList` với `Stream.toList` và `Collectors.toUnmodifiableList`.
- [ ] Nếu cần mutable, tôi dùng `toCollection(ArrayList::new)` thay vì dựa vào class triển khai.
- [ ] Nếu muốn bỏ duplicate, tôi làm điều đó **trước collect** bằng `distinct()` hoặc quy tắc thích hợp.
- [ ] Tôi không mong collector **deep-copy** đối tượng phần tử.
- [ ] Tôi không trả về mutable collection nội bộ hoặc live view khi API yêu cầu snapshot ổn định.
- [ ] Với downstream collector, tôi đã kiểm tra **từng cấp cấu trúc** cần unmodifiable.
- [ ] Tôi không dùng lớp runtime, identity hoặc benchmark phỏng đoán làm cơ sở thiết kế.
- [ ] Nếu source bị cập nhật đồng thời, tôi bảo đảm nguồn ổn định/được đồng bộ hóa trong lúc thực hiện Stream.

## 17. Nguồn tham khảo chính thức

1. [Java SE 26 — `Collectors` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): mô tả `toUnmodifiableList`, `toList`, `toCollection`, `groupingBy` và các downstream collector; `toUnmodifiableList` có từ Java 10, giữ encounter order và không nhận `null`.
2. [Java SE 26 — `Stream` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): terminal `collect`, `toList` từ Java 16, encounter order, parallel stream, quy tắc non-interference.
3. [Java SE 26 — `List` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): hợp đồng unmodifiable List, chính sách phần tử `null` của `List.of`/`copyOf`, shallow immutability và value-based factory instances.
4. [Java SE 26 — `Collection` Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html): phân biệt unmodifiable collection, immutable elements và unmodifiable view.
5. [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): hướng dẫn chọn factory và collector không sửa đổi từ Stream.
6. [Java SE 10 — `Collectors.toUnmodifiableList`](https://docs.oracle.com/javase/10/docs/api/java/util/stream/Collectors.html): xác nhận tính năng được bổ sung trong Java 10 và hành vi ban đầu vẫn tiếp tục được hỗ trợ.

**Kết luận:** `Collectors.toUnmodifiableList()` là cách chốt đầu ra Stream thành **List giữ encounter order và duplicate, không cho sửa cấu trúc, không chấp nhận `null`**. Nó không deep-copy các đối tượng phần tử và không bảo đảm lớp triển khai cụ thể. Hãy chọn giữa nó, `Stream.toList()`, `Collectors.toCollection(...)` và `List.copyOf(...)` theo **hợp đồng dữ liệu** thay vì chỉ theo tên phương thức.