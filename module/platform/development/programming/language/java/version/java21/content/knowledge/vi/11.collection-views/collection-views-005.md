# Giới hạn của unmodifiable view khi dữ liệu gốc vẫn có thể thay đổi

Trong Java 21, `Collections.unmodifiableList`, `unmodifiableSet`, `unmodifiableMap` và các wrapper tương ứng tạo ra một **unmodifiable view**: mã đang giữ view không thể dùng API của view để thay đổi cấu trúc collection. Tuy nhiên, view vẫn được liên kết với collection gốc. Nếu một nơi khác còn giữ tham chiếu đến collection gốc và thay đổi nó, các thay đổi đó sẽ xuất hiện khi đọc qua view.

Vì vậy, unmodifiable view không đồng nghĩa với một bản sao bất biến độc lập. Cũng cần phân biệt việc không thể thay đổi cấu trúc collection với việc các object được lưu bên trong có thể thay đổi trạng thái. Bài này tập trung vào những giới hạn đó và cách chọn giải pháp phù hợp khi công khai dữ liệu chỉ đọc.

## 1. Unmodifiable view là một lớp bọc đọc qua dữ liệu gốc

`Collections.unmodifiableList(source)` tạo một view không cho phép sửa đổi thông qua view, nhưng vẫn đọc dữ liệu từ `source`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>();
source.add("Java");

List<String> view = Collections.unmodifiableList(source);

System.out.println(view); // [Java]

source.add("Kotlin");
System.out.println(view); // [Java, Kotlin]

view.add("Scala"); // UnsupportedOperationException
```

Lệnh `source.add("Kotlin")` thành công vì `source` vẫn là một `ArrayList` có thể sửa đổi. `view` hiển thị phần tử mới vì nó đọc từ cùng collection đó. Lệnh `view.add("Scala")` bị từ chối vì wrapper không cho sửa đổi thông qua view.

Đây là đặc điểm cốt lõi của view:

- Không tạo snapshot độc lập của các phần tử tại thời điểm gọi.
- Đọc qua view sẽ thấy các thay đổi mà collection gốc cho phép thực hiện.
- Không thể dùng các phương thức sửa đổi của view để thay đổi collection gốc.
- Mọi tham chiếu khác đến collection gốc vẫn có thể thay đổi dữ liệu theo quyền của chúng.

Các wrapper `unmodifiableSet`, `unmodifiableMap`, `unmodifiableSortedSet`, `unmodifiableNavigableMap` và những biến thể khác cũng có nguyên tắc tương tự. Với map, thay đổi mapping qua tham chiếu gốc sẽ được phản ánh qua view, bao gồm các view `keySet()`, `values()` và `entrySet()` được cung cấp bởi unmodifiable map.

## 2. Những đường sửa đổi bị chặn qua view

Wrapper unmodifiable chặn các thao tác làm thay đổi collection thông qua chính wrapper. Điều này áp dụng cả các phương thức sửa đổi trực tiếp, iterator và các view con.

Với `List`, các thao tác sau không được phép:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(source);

view.add("C");
view.remove("A");
view.set(0, "X");
view.clear();
view.sort(String::compareTo);
view.replaceAll(String::toLowerCase);
view.removeIf(String::isBlank);
```

Mỗi lời gọi cố gắng sửa đổi view sẽ ném `UnsupportedOperationException`. Các dòng minh họa là những trường hợp độc lập; một lời gọi ném exception sẽ kết thúc luồng thực thi hiện tại. Iterator và list iterator lấy từ view cũng không cho phép sửa collection:

```java
var iterator = view.iterator();
iterator.next();
iterator.remove(); // UnsupportedOperationException

var listIterator = view.listIterator();
listIterator.next();
listIterator.set("X"); // UnsupportedOperationException
listIterator.add("C"); // UnsupportedOperationException
```

Với `Map`, các thao tác cập nhật qua wrapper như `put`, `remove`, `clear`, `putAll`, `replace`, `replaceAll`, `compute`, `computeIfAbsent`, `computeIfPresent` và `merge` đều không được hỗ trợ. Các view `keySet`, `values`, `entrySet` cũng không cho phép xóa hoặc cập nhật mapping.

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> source = new HashMap<>();
source.put("A", 1);

Map<String, Integer> view = Collections.unmodifiableMap(source);

view.put("B", 2);                  // UnsupportedOperationException
view.keySet().remove("A");         // UnsupportedOperationException
view.values().clear();             // UnsupportedOperationException
var entryIterator = view.entrySet().iterator();
entryIterator.next();
entryIterator.remove();             // UnsupportedOperationException
```

Các lời gọi sửa đổi trong ví dụ map cũng là các trường hợp độc lập; dừng hoặc bắt exception sau từng lời gọi nếu muốn quan sát từng kết quả.

Entry lấy từ `entrySet()` của unmodifiable map cũng không thể dùng `setValue()` để cập nhật mapping:

```java
Map.Entry<String, Integer> entry = view.entrySet().iterator().next();
entry.setValue(99); // UnsupportedOperationException
```

Các thao tác truy vấn như `get`, `containsKey`, `size`, duyệt phần tử và đọc entry vẫn hoạt động bình thường. Chúng đọc trạng thái hiện tại của collection gốc thông qua wrapper.

## 3. Thay đổi từ collection gốc vẫn xuất hiện trong view

Một unmodifiable view chỉ giới hạn quyền truy cập qua một đường tham chiếu. Nó không thu hồi quyền sửa đổi của những nơi khác đang giữ collection gốc.

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> source = new HashMap<>();
source.put("A", 1);

Map<String, Integer> readOnly = Collections.unmodifiableMap(source);

source.put("B", 2);
source.remove("A");

System.out.println(readOnly); // {B=2}
```

View phản ánh cả việc thêm và xóa mapping. Đây có thể là hành vi mong muốn nếu ứng dụng cần công khai một góc nhìn chỉ đọc luôn theo sát dữ liệu đang được cập nhật. Nhưng nếu yêu cầu là công bố một trạng thái ổn định tại thời điểm tạo, unmodifiable view trực tiếp trên collection có thể sửa đổi không đáp ứng yêu cầu đó.

Một view có thể được tạo từ một view khác. Ví dụ `Collections.unmodifiableList(source).subList(0, n)` vẫn phụ thuộc vào list gốc; việc thay đổi cấu trúc list gốc có thể ảnh hưởng view con và iterator. Không nên xem việc tạo thêm một lớp view là tạo ra bản sao độc lập.

## 4. Unmodifiable không có nghĩa là phần tử bất biến

Wrapper chặn thay đổi cấu trúc collection, nhưng không tự làm bất biến các object được lưu bên trong. Nếu một phần tử là object mutable, người đọc vẫn có thể gọi phương thức thay đổi trạng thái của object đó.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

final class Task {
    private boolean completed;

    void complete() {
        completed = true;
    }

    boolean isCompleted() {
        return completed;
    }
}

List<Task> source = new ArrayList<>();
source.add(new Task());

List<Task> view = Collections.unmodifiableList(source);

view.get(0).complete();
System.out.println(view.get(0).isCompleted()); // true
```

Lệnh `view.get(0).complete()` không thay đổi số lượng hoặc vị trí phần tử trong list; nó thay đổi object `Task` mà list đang tham chiếu. Unmodifiable view không thể ngăn hành động đó.

Điều tương tự xảy ra với map: `unmodifiableMap` ngăn thay đổi mapping qua `put` hoặc `entry.setValue`, nhưng nếu value là object mutable, người đọc vẫn có thể gọi phương thức làm thay đổi object value.

Do đó, cần phân biệt:

| Thuộc tính | Unmodifiable view bảo đảm? |
|---|---|
| Không thêm/xóa/thay thế phần tử qua view | Có |
| Không cập nhật mapping qua view | Có |
| Không thấy thay đổi từ collection gốc | Không |
| Không thay đổi trạng thái object phần tử | Không |
| Thread-safe khi nhiều thread cùng truy cập | Không tự bảo đảm |
| Deep immutability của toàn bộ object graph | Không |

Muốn dữ liệu thực sự ổn định, cần kiểm soát cả collection gốc lẫn các object có thể truy cập từ collection. Có thể dùng phần tử immutable, tạo defensive copy cho từng phần tử, hoặc chỉ công khai DTO/giá trị không cho phép sửa đổi.

## 5. So sánh unmodifiable view với List.copyOf và Map.copyOf

Java cung cấp các factory `List.copyOf`, `Set.copyOf` và `Map.copyOf` để tạo collection không cho sửa đổi. Khác với `Collections.unmodifiableX(source)`, các phương thức `copyOf` tạo kết quả có nội dung không phản ánh những thay đổi collection về sau của nguồn đầu vào.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));

List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
```

| Tiêu chí | `Collections.unmodifiableList(source)` | `List.copyOf(source)` |
|---|---|---|
| Mục đích | Tạo view không cho sửa đổi qua view | Tạo list không cho sửa đổi từ nội dung nguồn tại thời điểm gọi |
| Thay đổi cấu trúc nguồn sau đó | Được phản ánh trong view | Không được phản ánh trong kết quả |
| Sửa đổi qua kết quả | Bị chặn | Bị chặn |
| Chấp nhận phần tử null | Phụ thuộc collection nguồn; wrapper không tự loại null | Không; ném `NullPointerException` nếu có phần tử null |
| Phần tử mutable | Vẫn có thể thay đổi qua tham chiếu phần tử | Vẫn có thể thay đổi qua tham chiếu phần tử |

`Set.copyOf` và `Map.copyOf` có cùng mục đích tạo collection không sửa đổi độc lập với thay đổi cấu trúc nguồn. `Set.copyOf` không chấp nhận phần tử null; `Map.copyOf` không chấp nhận null key hoặc null value.

Lưu ý rằng “copy” ở đây là copy cấu trúc collection và các tham chiếu phần tử/key/value. Nó không tự sao chép sâu từng object. Nếu một phần tử mutable được giữ trong cả nguồn và kết quả, thay đổi object đó vẫn được nhìn thấy từ cả hai nơi.

### Tạo defensive copy rồi bọc unmodifiable

Khi cần giữ null trong collection, hoặc muốn chủ động chọn implementation, có thể sao chép nguồn trước rồi bọc bản sao:

```java
List<String> source = new ArrayList<>();
source.add("A");
source.add(null);

List<String> independentReadOnly =
        Collections.unmodifiableList(new ArrayList<>(source));

source.add("B");

System.out.println(independentReadOnly); // [A, null]
```

Bản sao `ArrayList` không còn bị thay đổi khi `source` thay đổi. Wrapper chặn người dùng sửa cấu trúc bản sao thông qua `independentReadOnly`. Đây vẫn là defensive copy nông: nếu phần tử là object mutable, bản sao và nguồn vẫn giữ cùng tham chiếu đến object đó.

Với map có thứ tự trong Java 21, có thể sao chép sang `LinkedHashMap` rồi bọc bằng `Collections.unmodifiableSequencedMap`:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String, Integer> source = new LinkedHashMap<>();
source.put("A", 1);
source.put("B", 2);

SequencedMap<String, Integer> independentReadOnly =
        Collections.unmodifiableSequencedMap(new LinkedHashMap<>(source));
```

Kết quả giữ encounter order tại thời điểm sao chép và không phản ánh những thay đổi cấu trúc về sau của `source`. Các API `unmodifiableSequencedCollection`, `unmodifiableSequencedSet` và `unmodifiableSequencedMap` là các wrapper theo thứ tự được cung cấp trong Java 21; chúng vẫn là view trên đối tượng được truyền vào, nên nếu truyền trực tiếp collection có thể sửa đổi thì các thay đổi từ tham chiếu gốc vẫn được phản ánh.

## 6. Chọn giải pháp theo yêu cầu dữ liệu

| Yêu cầu | Cách tiếp cận phù hợp |
|---|---|
| Muốn người nhận không sửa được collection, nhưng vẫn thấy cập nhật từ nguồn | `Collections.unmodifiableList(source)` hoặc wrapper tương ứng |
| Muốn kết quả không phản ánh thay đổi cấu trúc nguồn sau thời điểm tạo | `List.copyOf`, `Set.copyOf`, `Map.copyOf` |
| Cần giữ null trong bản sao độc lập | Sao chép sang implementation phù hợp rồi bọc bằng `Collections.unmodifiableX` |
| Cần giữ thứ tự của map trong Java 21 | Sao chép sang `LinkedHashMap` hoặc implementation có thứ tự phù hợp, sau đó dùng `unmodifiableSequencedMap` |
| Cần trạng thái phần tử cũng không thay đổi | Dùng phần tử immutable hoặc tạo defensive copy sâu/DTO phù hợp |
| Cần chia sẻ dữ liệu giữa nhiều thread | Chọn cấu trúc đồng thời hoặc cơ chế đồng bộ riêng; unmodifiable wrapper không thay thế concurrency control |

Nếu mục tiêu là công khai dữ liệu chỉ đọc từ một service, hãy xác định trước API muốn cung cấp live view hay snapshot. Live view phù hợp khi người gọi cần quan sát trạng thái cập nhật liên tục; snapshot phù hợp khi người gọi cần một kết quả ổn định để xử lý hoặc lưu lại.

## 7. Iterator, thay đổi đồng thời và thread safety

Vì view đọc từ collection gốc, việc một tham chiếu khác sửa đổi cấu trúc nguồn trong lúc đang duyệt có thể ảnh hưởng iterator. Với các collection fail-fast như `ArrayList` hoặc `HashMap`, iterator có thể ném `ConcurrentModificationException` khi phát hiện thay đổi cấu trúc không thông qua iterator đó.

Fail-fast chỉ là cơ chế phát hiện lỗi theo best-effort, không phải bảo đảm đồng bộ hay bảo vệ dữ liệu giữa các thread. `Collections.unmodifiableList` và `Collections.unmodifiableMap` không tự biến collection gốc thành thread-safe. Một thread vẫn có thể sửa nguồn trong khi thread khác đọc view.

Nếu cần chia sẻ an toàn:

- Dùng collection concurrent phù hợp với kiểu truy cập, hoặc đồng bộ hóa tất cả đường đọc/ghi theo cùng một quy tắc.
- Nếu chỉ cần công bố một trạng thái ổn định, tạo snapshot/defensive copy dưới cơ chế đồng bộ thích hợp rồi công khai bản sao.
- Không giả định rằng wrapper unmodifiable làm cho object mutable bên trong trở nên thread-safe.

## 8. Checklist trước khi công khai unmodifiable view

- [ ] Đã quyết định cần live view hay snapshot độc lập.
- [ ] Nếu dùng `Collections.unmodifiableX(source)`, đã kiểm soát các tham chiếu khác có thể sửa `source`.
- [ ] Đã hiểu thay đổi từ nguồn sẽ xuất hiện trong view.
- [ ] Đã kiểm tra người nhận có thể thay đổi trạng thái object phần tử hoặc value hay không.
- [ ] Đã xem xét null: `copyOf` không chấp nhận null, còn wrapper unmodifiable giữ quy tắc của nguồn.
- [ ] Đã sao chép cấu trúc trước khi bọc nếu cần defensive copy độc lập.
- [ ] Đã chọn phần tử immutable hoặc cách copy sâu nếu cần bảo vệ cả object graph.
- [ ] Đã có quy tắc đồng bộ/concurrency riêng khi chia sẻ giữa nhiều thread.

## Tài liệu tham khảo

- [Collections — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html): các wrapper `unmodifiableX`, gồm collection, list, set, map và sequenced collection.
- [List — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html): hợp đồng của `List.copyOf` và các factory list không sửa đổi.
- [Set — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html): hợp đồng của `Set.copyOf`.
- [Map — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html): hợp đồng của `Map.copyOf` và các view của map.
- [ArrayList — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html): iterator fail-fast và giới hạn best-effort của cơ chế phát hiện sửa đổi đồng thời.
