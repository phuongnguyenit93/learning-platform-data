# Giới hạn thêm, xóa, thay thế và sắp xếp kết quả của `List.copyOf` (Java 10+)

## 1. Mục tiêu

`List.copyOf(Collection<? extends E>)` có từ **Java 10** và vẫn là API thông dụng của Java hiện đại. Nó trả về một danh sách **không thể sửa thông qua giao diện `List`** (*unmodifiable list*) chứa các phần tử của collection nguồn tại thời điểm sao chép.

Đây là lựa chọn phù hợp khi cần trao dữ liệu chỉ đọc cho nơi khác, chứ **không** phải lựa chọn để tiếp tục gọi `add`, `remove`, `set`, `replaceAll` hoặc `sort` trực tiếp trên kết quả. Những phép sửa này sẽ bị từ chối bằng `UnsupportedOperationException`.

Sau bài này, bạn cần biết:

1. Phân biệt **đọc danh sách** với **sửa danh sách** sau khi gọi `List.copyOf`.
2. Hiểu tại sao không chỉ thêm/xóa, mà cả ghi đè phần tử và sắp xếp tại chỗ cũng bị cấm.
3. Biết dùng `new ArrayList<>(...)` để tạo bản sao mutable khi thực sự cần chỉnh sửa.
4. Biết tạo **một kết quả sắp xếp mới** bằng stream và hiểu kết quả đó có thể vẫn unmodifiable.
5. Phân biệt snapshot của `List.copyOf` với `Collections.unmodifiableList`, `Arrays.asList` và các API list khác.
6. Nhận diện các giới hạn về `null`, đối tượng phần tử mutable, order và thread safety.

Chỉ dùng các hành vi và API còn được hỗ trợ hiện nay. Ví dụ hoàn chỉnh dùng **Java 17+** vì có `Stream.toList()` (được bổ sung từ Java 16); bản thân `List.copyOf` đã có từ Java 10.

## 2. `List.copyOf` bảo đảm điều gì?

Ví dụ:

```java
var source = new java.util.ArrayList<>(
        java.util.List.of("pear", "apple", "banana"));

var result = java.util.List.copyOf(source);

System.out.println(result);        // [pear, apple, banana]
System.out.println(result.get(1)); // apple
System.out.println(result.size()); // 3
```

Đoạn trên dùng trong thân một phương thức, không phải file Java chạy độc lập.

Các tính chất của `result`:

- **Unmodifiable:** các phương thức `List` dùng để thay đổi nội dung không được hỗ trợ. Kiểu tĩnh của biến có thể là `List<String>`, nhưng interface `List` không có nghĩa mọi implementation đều cho phép sửa.
- **Ảnh chụp cấu trúc:** thêm, xóa hoặc thay thế các tham chiếu phần tử trong `source` sau khi copy không thay đổi kết quả đã nhận. Đây không phải unmodifiable view trực tiếp lên một `ArrayList` nguồn mutable.
- **Thứ tự duyệt:** các phần tử được lưu theo iteration order của collection nguồn. Nếu nguồn là `List`, thứ tự của list được giữ. Phương thức **không tự sắp xếp**.
- **Giữ phần tử trùng:** `List.copyOf(List.of("A", "B", "A"))` vẫn có ba phần tử.
- **Từ chối `null`:** nguồn `null` hoặc bất cứ phần tử `null` nào trong nguồn sẽ dẫn đến `NullPointerException`.
- **Shallow copy:** các tham chiếu tới object phần tử được giữ, không deep-clone các object đó. Object mutable bên trong có thể thay đổi từ tham chiếu khác.
- **Không bảo đảm danh tính riêng:** JDK có thể tái sử dụng một list unmodifiable đã phù hợp. Không dựa vào `source == result` hoặc tên lớp runtime để xác định hành vi.

Các lời gọi `get`, `size`, `contains`, `indexOf`, duyệt `for-each` và đọc qua iterator vẫn hợp lệ. Giới hạn nằm ở các thao tác cố **sửa danh sách hoặc các vị trí chứa phần tử**.

## 3. Ma trận thao tác được phép và bị cấm

| Thao tác | Ví dụ | Trên list từ `List.copyOf` |
| --- | --- | --- |
| Đọc theo index | `get(0)` | Được phép |
| Đếm/tìm kiếm | `size()`, `contains(x)`, `indexOf(x)` | Được phép |
| Duyệt phần tử | `for-each`, `iterator().next()`, `stream()` | Được phép |
| Lấy đoạn để đọc | `subList(from, to)` | Được phép; đoạn cũng không dùng để sửa nguồn |
| Thêm phần tử | `add`, `addAll` | Không được |
| Xóa phần tử | `remove`, `removeAll`, `retainAll`, `clear`, `removeIf` | Không được |
| Thay giá trị vị trí | `set(index, item)` | Không được |
| Thay hàng loạt | `replaceAll(operator)` | Không được |
| Sắp xếp tại chỗ | `sort(comparator)`, `Collections.sort(list)` | Không được |
| Hoán đổi/đảo trộn | `Collections.reverse/shuffle/swap/fill/rotate` | Không được |
| Sửa qua iterator | `Iterator.remove`, `ListIterator.set/add/remove` | Không được |

Các thao tác cố sửa thực tế bị từ chối bằng `UnsupportedOperationException`. Một thuật toán trên danh sách rỗng hoặc trường hợp không đụng tới mutator có thể vô tình kết thúc mà không ném lỗi; **đó không phải dấu hiệu danh sách có thể sửa**. Không dựa vào một phép “thử sửa no-op” để xác định tính mutable. Dựa trên hợp đồng trả về của `List.copyOf`.

## 4. Thêm và xóa: không thể thay đổi số lượng phần tử

```java
var names = java.util.List.copyOf(
        java.util.List.of("Ada", "Linus", "Grace"));

// names.add("James");                 // UnsupportedOperationException
// names.add(0, "James");              // UnsupportedOperationException
// names.addAll(List.of("Ken"));       // UnsupportedOperationException
// names.remove("Ada");                // UnsupportedOperationException
// names.remove(0);                    // UnsupportedOperationException
// names.clear();                      // UnsupportedOperationException
// names.removeIf(s -> s.startsWith("A")); // UnsupportedOperationException
```

Các dòng comment là **ví dụ cố ý về lệnh bị từ chối**, không phải câu lệnh cần thực hiện. Việc kết quả có kiểu `List<String>` hoặc biến được khai báo bằng `var` không làm đối tượng mutable.

Nếu cần thêm phần tử trước khi trả kết quả cho người gọi:

```java
var working = new java.util.ArrayList<>(
        java.util.List.of("Ada", "Linus"));

working.add("Grace");
var published = java.util.List.copyOf(working);

System.out.println(published); // [Ada, Linus, Grace]
```

Mẫu này có thể gọi là **build mutable, publish unmodifiable**:

1. Tạo list mutable có chủ đích để xử lý dữ liệu.
2. Thực hiện các phép thêm, xóa, sắp xếp hoặc thay thế.
3. Dùng `List.copyOf` để chốt bản snapshot chỉ đọc.
4. Sau thời điểm xuất bản, đừng gọi mutator trên snapshot; nếu cần phiên bản mới, tạo bản mutable copy khác.

Một biến `final var published` cũng không phải nguyên nhân khiến list unmodifiable. `final` cấm **gán lại tham chiếu biến**, còn `List.copyOf` cấm **sửa nội dung list thông qua API `List`**. Đây là hai khái niệm khác nhau.

## 5. Thay thế: `set` và `replaceAll` cũng bị cấm

Nhiều người tưởng chỉ thao tác đổi kích thước mới không được, còn thay phần tử tại một index đã tồn tại thì hợp lệ. Điều đó **sai**:

```java
var colors = java.util.List.copyOf(
        java.util.List.of("red", "green", "blue"));

// colors.set(1, "yellow");                 // UnsupportedOperationException
// colors.replaceAll(String::toUpperCase);  // UnsupportedOperationException
```

`set(1, ...)` thay tham chiếu phần tử ở vị trí 1. `replaceAll` thay giá trị tại những vị trí sau khi áp dụng hàm. Cả hai vẫn là mutator dù kích thước list không đổi.

### Cách thay đúng A: sao chép mutable trước

```java
var original = java.util.List.copyOf(
        java.util.List.of("red", "green", "blue"));

var editable = new java.util.ArrayList<>(original);
editable.set(1, "yellow");
editable.replaceAll(String::toUpperCase);

var revised = java.util.List.copyOf(editable);

System.out.println(revised);  // [RED, YELLOW, BLUE]
System.out.println(original); // [red, green, blue]
```

`editable` có thể thay đổi vì nó là `ArrayList` mới. `revised` là snapshot unmodifiable mới. `original` vẫn giữ nguyên.

### Cách thay đúng B: tạo kết quả mới từ stream

```java
var original = java.util.List.copyOf(
        java.util.List.of("red", "green", "blue"));

var uppercase = original.stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(uppercase); // [RED, GREEN, BLUE]
```

`Stream.toList()` có từ **Java 16**, kết quả **unmodifiable**. Nó không tạo một list có thể `set` hay `add` sau đó. Trên dự án chỉ dùng Java 10, có thể thay bằng:

```java
var uppercase = original.stream()
        .map(String::toUpperCase)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

`Collectors.toUnmodifiableList()` được đưa vào Java 10. Với bài toán cần sửa theo index, cách tạo `new ArrayList<>(original)` thường dễ hiểu hơn việc sử dụng stream.

## 6. Sắp xếp: `sort` và `Collections.sort` không tạo bản sao

```java
var values = java.util.List.copyOf(
        java.util.List.of("pear", "apple", "banana"));

// values.sort(java.util.Comparator.naturalOrder()); // Không được
// java.util.Collections.sort(values);               // Không được
```

Cả `List.sort(comparator)` lẫn `Collections.sort(list)` đều nhằm **sắp xếp ngay chính danh sách đã nhận** (*in-place*). Chúng cần đặt lại các phần tử theo vị trí, do đó không phù hợp với list do `List.copyOf` trả về.

Tương tự, các lời gọi `Collections.reverse`, `shuffle`, `swap`, `fill`, `rotate` là những thao tác thay đổi list đầu vào, không phải phép tạo một danh sách kết quả mới. Đừng xem chúng là cách “vượt” giới hạn của `List.copyOf`.

### Cách 1: sao chép rồi sort

```java
var values = java.util.List.copyOf(
        java.util.List.of("pear", "apple", "banana"));

var sortedMutable = new java.util.ArrayList<>(values);
sortedMutable.sort(java.util.Comparator.naturalOrder());

System.out.println(sortedMutable); // [apple, banana, pear]
System.out.println(values);        // [pear, apple, banana]
```

`sortedMutable` có thể thêm, xóa, set và sort. Nếu API kết quả vẫn phải chỉ đọc:

```java
var sortedSnapshot = java.util.List.copyOf(sortedMutable);
```

Đối với tiêu chí có thể không rõ thứ tự tự nhiên, chỉ ra Comparator:

```java
sortedMutable.sort(java.util.Comparator.reverseOrder());
```

### Cách 2: stream tạo danh sách sorted mới

```java
var values = java.util.List.copyOf(
        java.util.List.of("pear", "apple", "banana"));

var sortedImmutable = values.stream().sorted().toList();
System.out.println(sortedImmutable); // [apple, banana, pear]

// sortedImmutable.add("kiwi"); // UnsupportedOperationException
```

Chữ `sorted()` tạo một stream được sắp xếp theo thứ tự tự nhiên, và `toList()` tạo kết quả **unmodifiable**. `values` gốc không bị sửa. Để sắp xếp giảm dần:

```java
var descending = values.stream()
        .sorted(java.util.Comparator.reverseOrder())
        .toList();

System.out.println(descending); // [pear, banana, apple]
```

Lưu ý phiên bản: `Stream.toList()` chỉ có từ Java 16; trên **Java 10** có thể sử dụng:

```java
var sortedOnJava10 = values.stream()
        .sorted()
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

### Cách 3: stream và collector trả về mutable list

Nếu muốn vừa sắp xếp vừa có thể chỉnh sửa sau đó:

```java
var editable = values.stream()
        .sorted()
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));

editable.add("kiwi"); // Hợp lệ
```

Không suy luận rằng `Collectors.toList()` *bảo đảm* `ArrayList` mutable: đặc tả `Collectors.toList()` không bảo đảm loại implementation, mutability, serializability hoặc thread safety. Nếu hợp đồng ứng dụng yêu cầu mutable, dùng `toCollection(ArrayList::new)` hoặc `new ArrayList<>(...)`.

## 7. Iterator và `subList` không mở ra quyền chỉnh sửa

```java
var values = java.util.List.copyOf(
        java.util.List.of("A", "B", "C"));

var it = values.listIterator();
System.out.println(it.next()); // A

// it.set("X"); // UnsupportedOperationException
// it.remove(); // UnsupportedOperationException
// it.add("Y"); // UnsupportedOperationException
```

`ListIterator` có cả API đọc lẫn sửa, nhưng implementation iterator của list unmodifiable sẽ từ chối các thao tác sửa. Chỉ vì bạn đã `next()` tới một phần tử không có nghĩa có thể `set` hoặc `remove` nó.

Tương tự:

```java
var slice = values.subList(0, 2);
System.out.println(slice); // [A, B]

// slice.clear(); // Không thể xóa qua subList.
```

`subList` trả về một view con để sử dụng phạm vi đó, không phải một `ArrayList` mutable mới. Muốn sửa độc lập:

```java
var editableSlice = new java.util.ArrayList<>(values.subList(0, 2));
editableSlice.set(0, "X");
System.out.println(editableSlice); // [X, B]
System.out.println(values);        // [A, B, C]
```

Dù thao tác ở một biến khác, qua iterator hay qua danh sách con, nếu nó cần thay đổi chính snapshot của `List.copyOf`, kết quả không được hỗ trợ.

## 8. Snapshot khác unmodifiable view

`List.copyOf` và `Collections.unmodifiableList` có thể cùng ngăn caller sửa qua kết quả trả về, nhưng chúng khác ở quan hệ với nguồn.

```java
var source = new java.util.ArrayList<>(
        java.util.List.of("pear", "apple"));

var snapshot = java.util.List.copyOf(source);
var view = java.util.Collections.unmodifiableList(source);

source.add("banana");

System.out.println(snapshot); // [pear, apple]
System.out.println(view);     // [pear, apple, banana]
```

Vì sao?

- `snapshot` lưu danh sách tham chiếu phần tử ở thời điểm gọi `List.copyOf`. Thay đổi thêm/xóa/thay thế phần tử qua `source` không làm nó thay đổi.
- `view` là **wrapper chỉ đọc lên backing list**. Không thể gọi `view.add(...)`, nhưng chủ sở hữu `source` vẫn có thể sửa list gốc; kết quả `view` phản ánh những thay đổi đó.
- Nếu list đầu vào của `List.copyOf` đã là một list unmodifiable phù hợp, implementation có thể tái sử dụng cùng object. Điều quan trọng là **hợp đồng snapshot**, không phải mọi lần gọi đều phải cấp phát object khác.

Dùng `List.copyOf` khi cần một kết quả có cấu trúc độc lập với các thay đổi tiếp theo của collection nguồn. Dùng `Collections.unmodifiableList` chỉ khi cố ý muốn một *view* cập nhật theo nguồn và đã quản lý quyền sở hữu nguồn, đồng thời và lifecycle phù hợp.

## 9. Unmodifiable list vẫn có thể chứa phần tử mutable

`List.copyOf` là **shallow copy**: nó sao chép tham chiếu đến object phần tử, không làm bản sao sâu hay tự đóng băng trạng thái object ấy.

```java
final class Note {
    String text;

    Note(String text) {
        this.text = text;
    }
}

var note = new Note("draft");
var notes = java.util.List.copyOf(java.util.List.of(note));

note.text = "approved";
System.out.println(notes.get(0).text); // approved
```

Ví dụ trên gồm khai báo class và các câu lệnh đặt trong ngữ cảnh hợp lệ, không phải một file Java độc lập.

So sánh:

- `notes.set(0, new Note("new"))`: **không hợp lệ**, vì sửa phần tử tại index 0.
- `notes.get(0).text = "approved"`: **có thể hợp lệ**, vì sửa trạng thái của object được tham chiếu, không đổi phần tử tại vị trí list.
- Nếu phần tử là `String` hoặc một kiểu immutable phù hợp, list và phần tử cùng ít nguy cơ bị thay đổi. Nếu phần tử mutable, cần chính sách defensive copy/immutable element riêng.

Không suy luận rằng kết quả `List.copyOf` tự động **deep immutable**, tự động **thread-safe** ở mọi cấp hoặc có thể được chia sẻ tự do bất kể phần tử chứa gì. Bảo đảm bất biến cấu trúc list và tính an toàn của **toàn bộ đồ thị đối tượng** là hai câu hỏi khác nhau.

## 10. `null`, thứ tự, phần tử trùng

### Phần tử null

```java
var nullable = new java.util.ArrayList<String>();
nullable.add("A");
nullable.add(null);

// var failed = java.util.List.copyOf(nullable); // NullPointerException
```

`List.copyOf(null)` cũng ném `NullPointerException`. Không nên âm thầm bỏ `null` khi chưa hiểu ý nghĩa dữ liệu; hãy lựa chọn chính sách null trước khi gọi `copyOf`.

### Trùng lặp

```java
var result = java.util.List.copyOf(
        java.util.List.of("B", "A", "B"));

System.out.println(result); // [B, A, B]
```

`List.copyOf` không có chức năng distinct; nó giữ ba phần tử. Nếu cần loại trùng, thực hiện bằng xử lý dữ liệu trước khi copy hoặc tạo kết quả khác.

### Thứ tự

`List.copyOf` giữ **iteration order** nguồn, chứ không sắp xếp tự động. Với `List`, iteration order chính là thứ tự của list. Với collection như `HashSet`, thứ tự duyệt không có bảo đảm cố định; `List.copyOf` không bổ sung một trật tự xác định. Muốn luôn có thứ tự nghiệp vụ, sắp xếp có chủ đích.

## 11. So sánh với những API dễ gây nhầm lẫn

| API tạo list | Thêm/xóa | `set` | Sort tại chỗ | Quan hệ với nguồn |
| --- | --- | --- | --- | --- |
| `new ArrayList<>(source)` | Có | Có | Có | Sao chép tham chiếu; thay đổi cấu trúc nguồn không phản ánh |
| `List.copyOf(source)` | Không | Không | Không | Snapshot không đổi cấu trúc theo nguồn |
| `List.of(...)` | Không | Không | Không | Tạo list unmodifiable trực tiếp |
| `Collections.unmodifiableList(source)` | Không qua wrapper | Không qua wrapper | Không qua wrapper | View phản ánh thay đổi backing list |
| `Arrays.asList(array)` | Không thể đổi kích thước | Có | Có | Fixed-size list được backing bằng mảng |
| `Stream.toList()` (Java 16+) | Không | Không | Không | List kết quả unmodifiable |

**Điểm quan trọng về `Arrays.asList`:** đây là list **fixed-size** được hỗ trợ bằng array, không phải unmodifiable list theo nghĩa của `List.copyOf`. Nó cho phép `set` và sắp xếp tại chỗ (đổi các phần tử hiện có) nhưng không cho `add/remove` thay kích thước. Vì vậy việc `Arrays.asList(...).sort(...)` hoạt động không chứng minh `List.copyOf(...).sort(...)` cũng hoạt động.

**Điểm quan trọng về `Stream.toList`:** phương thức từ Java 16 này trả về list **unmodifiable**. Nếu cần mutable list từ stream, chọn `toCollection(ArrayList::new)`.

## 12. Ví dụ hoàn chỉnh Java 17+: chạy và kiểm tra các giới hạn

Tạo tệp **`ListCopyOfRestrictionsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.ListIterator;

public final class ListCopyOfRestrictionsDemo {
    private static void check(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + ": succeeded");
        } catch (UnsupportedOperationException ex) {
            System.out.println(name + ": UnsupportedOperationException");
        }
    }

    private static final class Note {
        String text;

        Note(String text) {
            this.text = text;
        }

        @Override
        public String toString() {
            return text;
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("pear", "apple", "banana"));
        var snapshot = List.copyOf(source);
        System.out.println("snapshot=" + snapshot);

        check("add", () -> snapshot.add("kiwi"));
        check("remove", () -> snapshot.remove("apple"));
        check("set", () -> snapshot.set(0, "plum"));
        check("replaceAll", () -> snapshot.replaceAll(String::toUpperCase));
        check("sort", () -> snapshot.sort(Comparator.naturalOrder()));
        check("Collections.sort", () -> Collections.sort(snapshot));
        check("clear", snapshot::clear);

        ListIterator<String> it = snapshot.listIterator();
        it.next();
        check("iterator.set", () -> it.set("plum"));

        source.add("kiwi");
        System.out.println("source=" + source);
        System.out.println("snapshot after source change=" + snapshot);

        var sortedMutable = new ArrayList<>(snapshot);
        sortedMutable.sort(Comparator.naturalOrder());
        sortedMutable.set(0, "apricot");
        System.out.println("sorted mutable=" + sortedMutable);
        System.out.println("snapshot still=" + snapshot);

        var sortedImmutable = snapshot.stream().sorted().toList();
        System.out.println("stream sorted=" + sortedImmutable);
        check("stream result.add", () -> sortedImmutable.add("fig"));

        var sortedSnapshot = List.copyOf(sortedMutable);
        System.out.println("sorted snapshot=" + sortedSnapshot);

        var view = Collections.unmodifiableList(source);
        source.add("fig");
        System.out.println("view after source change=" + view);

        var note = new Note("draft");
        var noteSnapshot = List.copyOf(List.of(note));
        note.text = "approved";
        System.out.println("mutable element=" + noteSnapshot.get(0));

        var nullableSource = new ArrayList<String>();
        nullableSource.add(null);
        try {
            List.copyOf(nullableSource);
            System.out.println("null element: accepted");
        } catch (NullPointerException ex) {
            System.out.println("null element: NullPointerException");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 ListCopyOfRestrictionsDemo.java
java ListCopyOfRestrictionsDemo
```

Đầu ra **chính xác** (đã đối chiếu với chương trình chạy):

```text
snapshot=[pear, apple, banana]
add: UnsupportedOperationException
remove: UnsupportedOperationException
set: UnsupportedOperationException
replaceAll: UnsupportedOperationException
sort: UnsupportedOperationException
Collections.sort: UnsupportedOperationException
clear: UnsupportedOperationException
iterator.set: UnsupportedOperationException
source=[pear, apple, banana, kiwi]
snapshot after source change=[pear, apple, banana]
sorted mutable=[apricot, banana, pear]
snapshot still=[pear, apple, banana]
stream sorted=[apple, banana, pear]
stream result.add: UnsupportedOperationException
sorted snapshot=[apricot, banana, pear]
view after source change=[pear, apple, banana, kiwi, fig]
mutable element=approved
null element: NullPointerException
```

Giải thích:

1. Các lệnh `check` cố ý thử mutator và bắt `UnsupportedOperationException` để làm rõ hợp đồng; đây **không** phải cách thông thường để chỉnh sửa list.
2. `source.add("kiwi")` không xuất hiện trong `snapshot` đã tạo, khẳng định thay đổi cấu trúc nguồn không tác động đến snapshot.
3. `sortedMutable` tạo từ `new ArrayList<>(snapshot)` nên `sort`/`set` hợp lệ; snapshot ban đầu vẫn giữ thứ tự cũ.
4. `stream().sorted().toList()` trả list mới đã sắp nhưng unmodifiable. Gọi `add` lên nó cũng thất bại.
5. `List.copyOf(sortedMutable)` cho một snapshot mới với thứ tự và giá trị đã được chỉnh sửa.
6. `Collections.unmodifiableList(source)` là view: khi thêm `fig` vào `source`, view nhìn thấy nó.
7. Trường hợp `Note` cho thấy object phần tử mutable có thể đổi; trường hợp `null` cho thấy copy không chấp nhận phần tử null.

Ví dụ chứa `Stream.toList()` nên lệnh `--release 17` là phù hợp. Nếu yêu cầu đúng Java 10, thay đoạn `toList()` bằng `collect(Collectors.toUnmodifiableList())`. Các hành vi cốt lõi của `List.copyOf`, `ArrayList`, `Collections.unmodifiableList` vẫn đúng trong Java hiện đại.

## 13. Mẫu thiết kế áp dụng trong dự án

### Khi trả về dữ liệu công khai chỉ đọc

```java
static java.util.List<String> publishedNames(
        java.util.List<String> incoming) {
    return java.util.List.copyOf(incoming);
}
```

Cách này làm rõ ràng người gọi **không thể sửa cấu trúc kết quả qua `List`**. Các sửa đổi cấu trúc tiếp theo của `incoming` không làm đổi snapshot trả về. Vì phần tử là `String` immutable, kết quả cũng tránh nhiều vấn đề chia sẻ trạng thái phần tử.

### Khi nhận list chỉ đọc nhưng muốn chỉnh sửa

```java
var received = java.util.List.copyOf(
        java.util.List.of("B", "A"));

var work = new java.util.ArrayList<>(received);
work.add("C");
work.sort(java.util.Comparator.naturalOrder());

var result = java.util.List.copyOf(work);
System.out.println(result);   // [A, B, C]
System.out.println(received); // [B, A]
```

Đây là workflow rõ ràng: **copy mutable → transform → copy unmodifiable**. Không có bước nào cố sửa `received`.

### Khi chỉ muốn sort mà không cần trạng thái mutable

```java
var received = java.util.List.copyOf(
        java.util.List.of("B", "A"));

var sorted = received.stream().sorted().toList();
System.out.println(sorted); // [A, B]
```

Kết quả đã sắp và unmodifiable; nếu cần thêm phần tử sau đó, dùng chiến lược tạo mutable list ngay từ đầu.

### Khi collection nguồn vẫn thay đổi liên tục

Nếu API cần dữ liệu **cập nhật theo nguồn**, `List.copyOf` mỗi lần tạo chỉ cho một snapshot tại thời điểm đó. Một view từ `Collections.unmodifiableList(source)` có đặc tính phản ánh backing source, nhưng không thay thế được các quy tắc concurrency và ownership. Cần chọn rõ một trong hai hợp đồng “snapshot” hoặc “live view”, không đánh đồng chúng.

## 14. Các lỗi phổ biến

1. **Dùng `List.copyOf` để mong kết quả mutable.** Tên `copyOf` không đồng nghĩa `new ArrayList<>(...)`.
2. **Chỉ kiểm tra `add/remove` mà quên `set/replaceAll/sort`.** Thay cùng index vẫn là sửa list.
3. **Gọi `Collections.sort` trên kết quả.** Đây là sắp xếp in-place, không trả list mới đã sorted.
4. **Sửa qua iterator hoặc `subList`.** Iterator/view không cấp khả năng viết cho list unmodifiable.
5. **Nhầm snapshot với `Collections.unmodifiableList`.** View phản ánh backing source khi nguồn bị sửa; snapshot copyOf không phản ánh thay đổi cấu trúc nguồn.
6. **Tưởng unmodifiable list đồng nghĩa deep immutable.** Phần tử mutable vẫn có thể bị thay đổi thông qua tham chiếu khác.
7. **Quên `null`.** `List.copyOf` không chấp nhận null source/element.
8. **Nghĩ `List.copyOf` tự sắp xếp hoặc tự distinct.** Nó giữ thứ tự duyệt và phần tử lặp.
9. **Dựa vào danh tính/nội bộ implementation.** Không dùng `==` với input hoặc tên class JDK để quyết định hợp đồng.
10. **Tưởng `Collectors.toList()` luôn mutable** hoặc `Stream.toList()` mutable; hãy đọc hợp đồng API và chọn collector đúng.
11. **Dùng `final var` để mong đóng băng object bên trong.** `final` chỉ ngăn gán lại biến, không tạo deep immutability.

## 15. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** `var x = List.copyOf(List.of("b", "a")); x.sort(Comparator.naturalOrder());` có hợp lệ không?

**Đáp án:** Không. `sort` là mutator; list không cho sửa nên ném `UnsupportedOperationException`. Tạo `new ArrayList<>(x)` rồi sort hoặc dùng `x.stream().sorted().toList()` (Java 16+) để có kết quả mới.

**Câu 2.** `x.set(0, "z")` có hợp lệ nếu kích thước list không đổi?

**Đáp án:** Không. Đây vẫn là thay thế phần tử tại index 0, nên bị cấm.

**Câu 3.** Sau `var x = List.copyOf(source); source.add("new");`, `x` có thêm phần tử mới không?

**Đáp án:** Không. `List.copyOf` chốt snapshot cấu trúc, độc lập với thay đổi cấu trúc tiếp theo của `source`.

**Câu 4.** Có thể sửa field của một object phần tử đang nằm trong `x` không?

**Đáp án:** Có thể, nếu object đó mutable và có quyền truy cập thích hợp. Đây là thay đổi trạng thái object được tham chiếu, không phải thay phần tử tại vị trí list.

**Câu 5.** Tại sao `Arrays.asList(...).set(...)` có thể hoạt động, nhưng `List.copyOf(...).set(...)` không hoạt động?

**Đáp án:** `Arrays.asList` trả về fixed-size list cho phép ghi đè vị trí; `List.copyOf` trả về unmodifiable list không cho mutator.

**Câu 6.** `Stream.toList()` có thể thay thế `new ArrayList<>(...)` khi cần thêm/xóa sau đó không?

**Đáp án:** Không. `Stream.toList()` trả về unmodifiable list. Muốn mutable, dùng `toCollection(ArrayList::new)` hoặc tạo `ArrayList` rõ ràng.

**Câu 7.** `List.copyOf` có tự distinct/sort và chấp nhận null phần tử không?

**Đáp án:** Không distinct, không sort, và không chấp nhận null phần tử. Nó giữ các phần tử theo thứ tự duyệt nguồn.

**Câu 8.** Bạn cần thêm, xóa, thay thế và sắp xếp dữ liệu rồi trả ra một list chỉ đọc: làm thế nào?

**Đáp án:** Thao tác trên một `ArrayList` mutable trong phạm vi kiểm soát, sau đó `return List.copyOf(workingList);`. Nếu phần tử có trạng thái mutable, cần thiết kế thêm chính sách phòng vệ ở cấp phần tử.

## Tài liệu tham khảo chính thức còn hiệu lực

- [Java SE — `List.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): hợp đồng unmodifiable, quy tắc null, thứ tự phần tử và copy từ collection.
- [Java SE — `List.sort`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)): sắp xếp tại chỗ cần list hỗ trợ thay phần tử.
- [Java SE — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): wrapper chỉ đọc với backing list.
- [Java SE — `Stream.toList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#toList()): kết quả unmodifiable từ Java 16.
- [Java SE — `Collectors.toCollection` và `toUnmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): chọn collection mutable có chủ đích hoặc tạo unmodifiable list.
- [Java SE — `Arrays.asList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list backed by array, khác snapshot unmodifiable của `List.copyOf`.
