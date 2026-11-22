# Thay thế mã xử lý phần tử đầu cuối bằng API biểu đạt đúng ý định

Java 21 bổ sung `SequencedCollection<E>` và các API hai đầu để mã nguồn thể hiện trực tiếp ý định lấy, thêm hoặc xóa phần tử ở đầu/cuối của một collection có encounter order. Thay vì tự dùng chỉ số `0`, `size() - 1` hoặc duyệt iterator để tìm phần tử cuối, có thể dùng `getFirst()` và `getLast()` khi kiểu dữ liệu hỗ trợ.

Việc refactor cần giữ đúng ngữ nghĩa của chương trình: collection phải có thứ tự xác định; hành vi khi rỗng phải được xử lý; và cần phân biệt thao tác đọc với thao tác lấy ra đồng thời xóa. Các API cũ như `List.get(index)` vẫn hợp lệ và không bị deprecated. Chỉ chuyển đổi khi cách viết mới làm rõ ý định và phù hợp với kiểu collection.

## 1. Xác định collection có thứ tự trước khi refactor

`getFirst()` và `getLast()` có trên `SequencedCollection<E>`. Trong Java 21, các kiểu quen thuộc sau hỗ trợ API sequenced:

- `List<E>`: thứ tự theo vị trí trong danh sách.
- `Deque<E>`: thứ tự từ head đến tail.
- `SequencedSet<E>`: tập hợp không trùng phần tử nhưng có encounter order.
- `SortedSet<E>` và `NavigableSet<E>`: thứ tự theo natural ordering hoặc comparator.

Không phải mọi `Collection` hoặc `Set` đều có thứ tự xác định. Ví dụ, `HashSet` không triển khai `SequencedSet`, vì vậy không có ý nghĩa ổn định để gọi phần tử đầu/cuối. Nếu nghiệp vụ cần phần tử nhỏ nhất hoặc lớn nhất, hãy dùng API theo thứ tự sắp xếp như `SortedSet.first()`/`last()` hoặc phép tìm min/max theo comparator, thay vì coi encounter order tùy ý là thứ tự nghiệp vụ.

Kiểu khai báo cũng quyết định API compiler cho phép gọi. Một đối tượng thực tế là `LinkedHashSet` nhưng được khai báo bằng `Set<E>` thì biến đó không có `getFirst()`/`getLast()` trong kiểu tĩnh. Khi hợp đồng phương thức yêu cầu thứ tự, khai báo bằng `SequencedCollection<E>` hoặc `SequencedSet<E>` phù hợp.

## 2. Thay thế truy cập đầu/cuối bằng chỉ số của List

Mã cũ thường dùng `get(0)` để lấy phần tử đầu và `get(size() - 1)` để lấy phần tử cuối:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

String first = names.get(0);
String last = names.get(names.size() - 1);
```

Với Java 21, có thể viết rõ ý định hơn:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh", "Chi"));

String first = names.getFirst();
String last = names.getLast();
```

Hai cách đều đọc phần tử và giữ nguyên list. `getFirst()`/`getLast()` không tự sắp xếp danh sách, cũng không đảm bảo phần tử đầu là nhỏ nhất hay phần tử cuối là lớn nhất; chúng chỉ dùng vị trí hiện tại trong encounter order.

### Thay đổi hành vi exception khi list rỗng

Đây là điểm cần xem xét khi refactor. Với list rỗng:

| Cách cũ | Kết quả khi rỗng | Cách Java 21 |
|---|---|---|
| `list.get(0)` | `IndexOutOfBoundsException` | `list.getFirst()` ném `NoSuchElementException` |
| `list.get(list.size() - 1)` | `IndexOutOfBoundsException` | `list.getLast()` ném `NoSuchElementException` |

Nếu collection rỗng là trạng thái bình thường, kiểm tra `isEmpty()` trước khi lấy phần tử:

```java
static void printLast(List<String> values) {
    if (values.isEmpty()) {
        System.out.println("Chưa có dữ liệu");
        return;
    }

    System.out.println(values.getLast());
}
```

Nếu list bắt buộc phải có phần tử, có thể để `NoSuchElementException` thể hiện vi phạm điều kiện hoặc chuyển thành exception nghiệp vụ ở ranh giới phù hợp. Không giữ `catch (IndexOutOfBoundsException)` cũ với giả định rằng API mới sẽ ném cùng loại exception.

## 3. Thay thế việc duyệt iterator để lấy phần tử đầu/cuối

Một số đoạn mã lấy phần tử đầu bằng `iterator().next()`:

```java
Collection<String> values = getValues();
String first = values.iterator().next();
```

Cách này chỉ có ý nghĩa khi collection có encounter order mà chương trình thực sự muốn sử dụng. Với một collection có thứ tự, hãy thể hiện yêu cầu đó qua kiểu `SequencedCollection`:

```java
static String firstValue(SequencedCollection<String> values) {
    if (values.isEmpty()) {
        return "(empty)";
    }
    return values.getFirst();
}
```

Lấy phần tử cuối bằng cách duyệt toàn bộ iterator thường dài dòng hơn:

```java
static <E> E lastByIteration(Iterable<E> values) {
    E last = null;
    for (E value : values) {
        last = value;
    }
    return last;
}
```

Đoạn mã này còn nhập nhằng giữa iterable rỗng và iterable có phần tử cuối là null. Nếu đầu vào có hợp đồng encounter order, đổi kiểu tham số sang `SequencedCollection<E>` rồi xử lý trạng thái rỗng rõ ràng:

```java
import java.util.NoSuchElementException;
import java.util.SequencedCollection;

static <E> E lastValue(SequencedCollection<E> values) {
    if (values.isEmpty()) {
        throw new NoSuchElementException("Collection is empty");
    }
    return values.getLast();
}
```

Đoạn mã mới phân biệt được collection rỗng với phần tử cuối có thể null. Hiệu năng cụ thể vẫn phụ thuộc implementation; không nên khẳng định mọi `getLast()` luôn có độ phức tạp O(1). Lợi ích trực tiếp của refactor là biểu đạt đúng yêu cầu và tránh tự viết vòng lặp xử lý biên.

## 4. Chọn get, peek hay remove cho Deque

`Deque<E>` đã có `getFirst()` và `getLast()` trước Java 21. Khi refactor mã dùng deque, điều cần làm là chọn phương thức theo hành vi mong muốn:

| Ý định | API | Khi deque rỗng |
|---|---|---|
| Đọc phần tử đầu | `getFirst()` | Ném `NoSuchElementException` |
| Đọc phần tử cuối | `getLast()` | Ném `NoSuchElementException` |
| Đọc đầu, chấp nhận không có phần tử | `peekFirst()` | Trả về `null` |
| Đọc cuối, chấp nhận không có phần tử | `peekLast()` | Trả về `null` |
| Lấy và xóa phần tử đầu | `removeFirst()` | Ném `NoSuchElementException` |
| Lấy và xóa phần tử cuối | `removeLast()` | Ném `NoSuchElementException` |
| Lấy và xóa đầu, chấp nhận deque rỗng | `pollFirst()` | Trả về `null` |
| Lấy và xóa cuối, chấp nhận deque rỗng | `pollLast()` | Trả về `null` |

Hợp đồng `Deque` khuyến khích implementation không chấp nhận phần tử null để có thể dùng null làm giá trị báo deque rỗng. Tuy nhiên, nếu một implementation cho phép null, kết quả null từ `peek` hoặc `poll` có thể nhập nhằng giữa deque rỗng và phần tử đầu/cuối là null; hãy kiểm tra chính sách của implementation đó.

Ví dụ, nếu chỉ muốn xem tác vụ tiếp theo, không xóa nó khỏi deque:

```java
Deque<String> tasks = new ArrayDeque<>();
tasks.addLast("compile");
tasks.addLast("test");

String next = tasks.peekFirst();
System.out.println(next);        // compile
System.out.println(tasks.size()); // 2
```

Nếu xử lý tác vụ và cần loại nó khỏi hàng đợi, dùng `pollFirst()` hoặc `removeFirst()` tùy hợp đồng khi rỗng. Không thay một lời gọi `pollFirst()` bằng `getFirst()` chỉ vì hai phương thức cùng truy cập đầu deque: việc đó sẽ thay đổi cả hành vi xóa và hành vi khi rỗng.

## 5. Thay thế xử lý đầu/cuối của Set có thứ tự

Trước Java 21, mã dùng `LinkedHashSet` đôi khi phải lấy iterator hoặc chuyển set thành list để truy cập phần tử đầu/cuối. Java 21 cung cấp `SequencedSet<E>` để thể hiện trực tiếp thứ tự hai đầu:

```java
import java.util.LinkedHashSet;
import java.util.SequencedSet;

SequencedSet<String> tags = new LinkedHashSet<>();
tags.add("java");
tags.add("collections");
tags.add("jdk21");

String first = tags.getFirst();
String last = tags.getLast();
```

Nếu code hiện khai báo biến bằng `Set<String>`, hãy cân nhắc đổi kiểu khai báo khi thứ tự là một phần của hợp đồng:

```java
// Kiểu Set không công bố API truy cập hai đầu.
Set<String> oldTags = new LinkedHashSet<>();

// Kiểu sequenced thể hiện rõ yêu cầu về encounter order.
SequencedSet<String> orderedTags = new LinkedHashSet<>();
```

Không đổi `HashSet` thành `SequencedSet` bằng cách ép kiểu. `HashSet` không triển khai interface này và không đảm bảo encounter order. Nếu cần thứ tự thêm, dùng `LinkedHashSet`; nếu cần thứ tự sắp xếp, dùng `TreeSet`/`SortedSet` theo hợp đồng phù hợp.

## 6. Dùng SequencedCollection trong API dùng chung

Nếu một hàm chỉ cần đọc hai đầu và có thể nhận list, deque hoặc sequenced set, khai báo tham số bằng interface chung:

```java
import java.util.SequencedCollection;

static <E> void reportEnds(SequencedCollection<E> values) {
    if (values.isEmpty()) {
        System.out.println("Không có phần tử");
        return;
    }

    System.out.println("First: " + values.getFirst());
    System.out.println("Last: " + values.getLast());
}
```

Kiểu tham số này diễn đạt chính xác yêu cầu: đầu vào phải có encounter order và hỗ trợ truy cập hai đầu. Một tham số `Collection<E>` không thể cung cấp bảo đảm đó. Nếu hàm cần sửa thứ tự hoặc thêm/xóa hai đầu, cần xem xét khả năng mutability và các phương thức tương ứng; interface sequenced không tự đảm bảo implementation có thể sửa đổi.

## 7. Không thay getFirst/getLast cho mọi tình huống

Các API mới không thay thế mọi thao tác truy cập phần tử:

| Nhu cầu | Cách phù hợp |
|---|---|
| Lấy phần tử ở vị trí bất kỳ trong `List` | `list.get(index)` |
| Lấy phần tử đầu/cuối theo encounter order | `getFirst()` / `getLast()` |
| Lấy giá trị nhỏ nhất/lớn nhất theo comparator | `min`/`max` với comparator hoặc API của `SortedSet` |
| Lấy một phần tử bất kỳ từ collection không có thứ tự | Xác định rõ nghiệp vụ; không giả định phần tử đầu/cuối ổn định |
| Đọc đầu deque và nhận null khi rỗng | `peekFirst()` |
| Lấy đồng thời xóa đầu/cuối | `removeFirst()` / `removeLast()` hoặc `pollFirst()` / `pollLast()` |
| Lấy phần tử đầu của stream theo encounter order | `stream.findFirst()` nếu cần kết quả dạng `Optional` và stream có encounter order |

`Stream.findFirst()` trả về `Optional<T>` và có semantics khác với `getFirst()`: nó không sửa collection, nhưng yêu cầu xử lý Optional và không biểu diễn được phần tử null; nếu phần tử được chọn là null, phương thức ném `NullPointerException`. Nếu stream không có encounter order, phần tử được chọn không nhất thiết có thứ tự ổn định. Không đổi máy móc từ `findFirst()` sang `getFirst()` nếu hợp đồng Optional hoặc nguồn dữ liệu stream là một phần của thiết kế.

## 8. Lưu ý về null và trạng thái rỗng

`getFirst()` và `getLast()` của `SequencedCollection` ném `NoSuchElementException` khi collection rỗng. Nếu implementation cho phép null, phương thức vẫn có thể trả về null khi phần tử đầu/cuối thực sự là null. Vì vậy, không dùng giá trị trả về null làm dấu hiệu chung cho collection rỗng.

```java
List<String> values = new ArrayList<>();
values.add(null);

System.out.println(values.isEmpty()); // false
System.out.println(values.getFirst()); // null
```

Nếu cần biểu diễn kết quả tùy chọn bằng `Optional`, hãy bảo đảm phần tử không null trước khi dùng `Optional.of(...)`. `Optional.ofNullable(...)` sẽ gộp hai trạng thái “không có phần tử” và “có phần tử null” thành cùng một `Optional.empty()`, nên chỉ dùng khi nghiệp vụ chấp nhận mất phân biệt đó.

## 9. Quy trình refactor an toàn

Khi thay mã cũ, thực hiện theo thứ tự:

1. Xác định kiểu thực tế và kiểu khai báo của collection; kiểm tra nó có encounter order xác định không.
2. Xác định ý định là đọc, đọc tùy chọn, hay lấy và xóa phần tử.
3. Thay `get(0)`/`get(size() - 1)` hoặc vòng lặp đầu/cuối bằng API sequenced nếu kiểu phù hợp.
4. Xem lại hành vi collection rỗng: `IndexOutOfBoundsException`, `NoSuchElementException` hay giá trị `null` có được xử lý đúng không.
5. Xem lại chính sách phần tử null và khả năng sửa đổi của collection.
6. Giữ `get(index)` khi cần truy cập vị trí bất kỳ; không đổi sang API hai đầu nếu ý định khác.

Các API trước Java 21 vẫn có giá trị và không bị loại bỏ. Mục tiêu là chọn phương thức có tên thể hiện đúng thao tác và dùng kiểu khai báo phản ánh đúng hợp đồng thứ tự của dữ liệu.

## 10. Checklist sau khi refactor

- Kiểu collection bảo đảm encounter order và cung cấp API hai đầu.
- Không dùng `getFirst()`/`getLast()` trên biến có kiểu chỉ là `Collection` hoặc `Set` không sequenced.
- Không giả định `HashSet` có phần tử đầu/cuối ổn định.
- Phân biệt đọc (`get`), đọc tùy chọn (`peek`) và lấy kèm xóa (`remove`/`poll`).
- Cập nhật cách xử lý exception khi collection rỗng.
- Phân biệt collection rỗng với phần tử null nếu implementation cho phép null.
- Không giả định mọi implementation có cùng độ phức tạp cho thao tác đầu/cuối.
- Giữ API chỉ số khi thực sự cần vị trí bất kỳ.
- Không coi `get(index)` hoặc các API cũ là lỗi thời hay deprecated chỉ vì có API sequenced.

Sử dụng API sequenced khi thao tác thực sự nhắm đến đầu hoặc cuối của collection có encounter order. Cách viết này làm rõ ý định, giảm mã thủ công và giúp hợp đồng về thứ tự, trạng thái rỗng và thao tác xóa được thể hiện ngay trong API được gọi.
