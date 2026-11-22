# Stream.toList, collect và giới hạn bảo đảm về khả năng sửa

## 1. Cùng kiểu List nhưng quyền sửa có thể khác nhau

Một pipeline stream có thể tạo ra `List` để phía sau đọc, bổ sung dữ liệu, sắp xếp hoặc trả về từ một API. Chọn thao tác kết thúc không chỉ là chọn cách viết ngắn hơn; đó còn là chọn hợp đồng của đối tượng kết quả.

Ví dụ, hai đoạn minh họa sau cùng có biến kiểu `List<String>`:

```java
// Đoạn minh họa; source là List<String> đã có.
List<String> first = source.stream().toList();
List<String> second = source.stream().collect(Collectors.toList());
```

Từ kiểu `List<String>`, chưa thể kết luận cả hai đều cho gọi `add`, `remove` hoặc `set`. Các thao tác sửa trong giao diện `List` là những khả năng có thể không được hỗ trợ bởi một cách triển khai cụ thể.

Cần tách ba câu hỏi:

1. **Danh sách cho sửa qua API của nó không?** Có thể thêm, xóa, thay phần tử hoặc sắp xếp tại chỗ không?
2. **Danh sách có dùng trực tiếp cấu trúc của nguồn không?** Nếu nguồn thay đổi sau khi thu thập xong, kết quả có cập nhật theo không?
3. **Các đối tượng phần tử có thể thay đổi không?** Danh sách không cho thay phần tử chưa chắc đã ngăn được việc sửa một trường bên trong phần tử.

Bài này tập trung vào các bảo đảm đó khi dùng `Stream.toList()`, `collect` và những collector tạo danh sách. Các chương trình dùng Java 17, được lưu theo đúng tên `public class`, có lệnh biên dịch và stdout để tự kiểm chứng.

## 2. Đọc hợp đồng trước khi chọn cách thu thập

| Cách tạo kết quả | Bảo đảm về quyền sửa | Kiểu triển khai | Thứ tự |
| --- | --- | --- | --- |
| `stream.toList()` | Không cho sửa danh sách; các lời gọi phương thức sửa ném `UnsupportedOperationException` | Không được bảo đảm là một lớp cụ thể | Giữ thứ tự gặp nếu stream có thứ tự |
| `stream.collect(Collectors.toList())` | Không có bảo đảm về khả năng sửa | Không có bảo đảm là `ArrayList` | Thu thập theo thứ tự gặp |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Cho sửa theo hợp đồng của `ArrayList` | Chủ động yêu cầu `ArrayList` | Thu thập theo thứ tự gặp |
| `stream.collect(Collectors.toUnmodifiableList())` | Không cho sửa danh sách | Không chọn một lớp cụ thể để phụ thuộc | Thu thập theo thứ tự gặp |
| `collect` kết hợp `collectingAndThen` | Do bước thu thập và bước hoàn tất quyết định | Do cách tạo và cách hoàn tất quyết định | Phụ thuộc collector được dùng |

### Stream.toList có cam kết không cho sửa

`Stream.toList()` trả về danh sách không cho sửa. Điều này bao gồm cả thay phần tử bằng `set`, không chỉ những thao tác làm thay đổi kích thước như `add` hoặc `remove`. Phương thức có từ Java 16. [Javadoc Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList())

Nếu cần đổi thứ tự, có thể sắp xếp trong pipeline bằng `sorted` rồi thu thập. Nếu cần tiếp tục sửa sau khi đã thu thập, chọn rõ một kết quả cho phép sửa.

### Collectors.toList không cam kết cho sửa

`Collectors.toList()` không bảo đảm kiểu triển khai, khả năng sửa, khả năng tuần tự hóa hoặc tính an toàn đồng thời của danh sách trả về. Vì vậy, “đang chạy được `add` ở phiên bản JDK này” chưa phải hợp đồng cho mã ứng dụng. [Javadoc Collectors.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList())

Không thay điều chưa được bảo đảm bằng khẳng định ngược lại. Collector này cũng không cam kết kết quả luôn không cho sửa. Kết luận đúng là: nếu thuật toán cần một trong hai chính sách, hãy yêu cầu rõ chính sách đó.

### Muốn sửa thì yêu cầu một vùng chứa phù hợp

`Collectors.toCollection(ArrayList::new)` thể hiện trực tiếp rằng kết quả cần là `ArrayList`. Lớp này hỗ trợ thêm, xóa, thay phần tử và sắp xếp. Không phải đoán lớp nội bộ mà một collector khác hiện đang dùng.

Cũng có thể tạo bản sao cho phép sửa từ một danh sách đã có:

```java
// Đoạn minh họa; result là List<String> đã thu thập.
List<String> editable = new ArrayList<>(result);
```

Bản sao này độc lập về cấu trúc với `result`, nhưng vẫn có thể dùng chung các đối tượng phần tử. Phần 5 sẽ kiểm chứng giới hạn đó.

## 3. Thí nghiệm: cùng dữ liệu, khác quyền sửa

Lưu vào `StreamListGuaranteesDemo.java`.

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class StreamListGuaranteesDemo {
    private static void expectBlocked(String name, Runnable action) {
        try {
            action.run();
            throw new IllegalStateException("Expected rejection: " + name);
        } catch (UnsupportedOperationException e) {
            System.out.println(name + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> source = List.of("B", "A", "B");
        List<String> direct = source.stream().toList();
        List<String> unspecified = source.stream().collect(Collectors.toList());
        ArrayList<String> mutable = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        List<String> unmodifiable = source.stream()
                .collect(Collectors.toUnmodifiableList());

        System.out.println("direct=" + direct);
        System.out.println("collector=" + unspecified);
        System.out.println("explicitArrayList=" + mutable);
        System.out.println("unmodifiableCollector=" + unmodifiable);
        expectBlocked("directAdd", () -> direct.add("C"));
        expectBlocked("directSet", () -> direct.set(0, "X"));
        expectBlocked("directRemove", () -> direct.remove("B"));
        expectBlocked("directSort", () -> direct.sort(Comparator.naturalOrder()));
        expectBlocked("unmodifiableAdd", () -> unmodifiable.add("C"));

        mutable.sort(Comparator.naturalOrder());
        mutable.set(0, "A*");
        mutable.remove("B");
        mutable.add("C");
        System.out.println("mutableAfterEdits=" + mutable);
        System.out.println("source=" + source);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 StreamListGuaranteesDemo.java
java StreamListGuaranteesDemo
```

Stdout:

```text
direct=[B, A, B]
collector=[B, A, B]
explicitArrayList=[B, A, B]
unmodifiableCollector=[B, A, B]
directAdd=UnsupportedOperationException
directSet=UnsupportedOperationException
directRemove=UnsupportedOperationException
directSort=UnsupportedOperationException
unmodifiableAdd=UnsupportedOperationException
mutableAfterEdits=[A*, B, C]
source=[B, A, B]
```

Bốn kết quả ban đầu đều chứa `[B, A, B]`. Thứ tự và phần tử trùng được giữ lại; thu thập thành danh sách không tự loại trùng.

Các dòng lỗi được in có chủ đích:

- `directAdd` kiểm tra thêm phần tử.
- `directSet` kiểm tra thay phần tử tại chỉ số, dù thao tác đó không làm đổi kích thước.
- `directRemove` kiểm tra xóa.
- `directSort` kiểm tra sắp xếp tại chỗ.
- `unmodifiableAdd` kiểm tra danh sách từ `Collectors.toUnmodifiableList()`.

Tất cả lời gọi sửa tương ứng bị chặn. Chương trình bắt đúng `UnsupportedOperationException` và in nhãn cố định, nên stdout không phụ thuộc nội dung thông điệp ngoại lệ của từng bản JDK.

Biến `unspecified` được tạo bằng `Collectors.toList()` chỉ được đọc và in. Ví dụ không lấy việc thử sửa thành công trên một cách triển khai để tuyên bố có bảo đảm cho sửa.

Ngược lại, `mutable` được tạo với `ArrayList::new`, nên chương trình chủ động dựa vào hợp đồng của `ArrayList`: sắp xếp, thay giá trị đầu, xóa một `B`, thêm `C`, rồi nhận `[A*, B, C]`. Nguồn vẫn là `[B, A, B]`.

### final và List không quyết định quyền sửa ở thời gian chạy

Từ khóa `final` trên một biến tham chiếu chỉ ngăn gán biến sang đối tượng khác. Nó không làm một `ArrayList` tự trở thành danh sách không cho sửa.

Ngược lại, bỏ `final` khỏi biến chứa kết quả `toList()` không làm kết quả đó hỗ trợ `add`. Quyền sửa thuộc về hợp đồng của đối tượng danh sách, không phải khả năng gán lại biến.

### Sắp xếp trước hoặc sau phải chọn rõ

Nếu cần một kết quả đã sắp xếp và sau đó chỉ đọc, có thể dùng đoạn minh họa:

```java
// source là List<String> không có phần tử null.
List<String> sortedResult = source.stream().sorted().toList();
```

Nếu muốn tiếp tục chỉnh sửa danh sách đã thu thập, dùng một `ArrayList` kết quả rồi gọi `sort`. Không thu thập bằng `toList()` rồi mặc định lệnh `sort` sẽ chạy được.

## 4. Quyền sửa và chính sách null là hai lựa chọn riêng

Hai danh sách đều không cho sửa không có nghĩa chúng chấp nhận cùng loại dữ liệu đầu vào.

`Stream.toList()` có thể chứa phần tử `null`. Trong khi đó, `Collectors.toUnmodifiableList()` từ chối `null` và ném `NullPointerException` nếu gặp nó. Vì vậy, hai cách viết này không thể thay thế nhau chỉ dựa trên từ “không cho sửa”. [Javadoc Collectors.toUnmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList())

| Yêu cầu | Cách diễn đạt phù hợp |
| --- | --- |
| Danh sách không cho sửa, vẫn giữ phần tử null | `stream.toList()` |
| Danh sách không cho sửa và từ chối null | `collect(Collectors.toUnmodifiableList())` |
| ArrayList cho sửa, có thể chứa null | `collect(Collectors.toCollection(ArrayList::new))` |
| Bao một kết quả ArrayList riêng thành danh sách không cho sửa, vẫn giữ null | `collectingAndThen(toCollection(ArrayList::new), Collections::unmodifiableList)` |

Cách cuối dài hơn, nhưng cho thấy một collector có thể tích lũy trong vùng chứa cho phép sửa rồi trả một đối tượng không cho sửa ở bước hoàn tất.

Lưu vào `StreamListNullPolicyDemo.java`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

public class StreamListNullPolicyDemo {
    public static void main(String[] args) {
        List<String> source = Arrays.asList("A", null, "B");
        List<String> direct = source.stream().toList();
        ArrayList<String> mutable = source.stream()
                .collect(Collectors.toCollection(ArrayList::new));
        List<String> wrapped = source.stream().collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                Collections::unmodifiableList));

        System.out.println("direct=" + direct);
        System.out.println("mutable=" + mutable);
        System.out.println("wrapped=" + wrapped);

        try {
            source.stream().collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException e) {
            System.out.println("unmodifiableCollector=NullPointerException");
        }
        try {
            List.copyOf(direct);
        } catch (NullPointerException e) {
            System.out.println("copyOf=NullPointerException");
        }
        try {
            wrapped.set(0, "X");
        } catch (UnsupportedOperationException e) {
            System.out.println("wrappedSet=UnsupportedOperationException");
        }

        List<String> withoutNull = source.stream()
                .filter(value -> value != null)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("withoutNull=" + withoutNull);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 StreamListNullPolicyDemo.java
java StreamListNullPolicyDemo
```

Stdout:

```text
direct=[A, null, B]
mutable=[A, null, B]
wrapped=[A, null, B]
unmodifiableCollector=NullPointerException
copyOf=NullPointerException
wrappedSet=UnsupportedOperationException
withoutNull=[A, B]
```

Nguồn được tạo bằng `Arrays.asList` để chứa được `null`. Nếu dùng `List.of("A", null, "B")`, lỗi đã xảy ra ở bước tạo nguồn, chưa tới phép thu thập cần kiểm chứng.

Kết quả cho thấy:

1. `direct`, `mutable` và `wrapped` đều giữ phần tử `null`.
2. `toUnmodifiableList` từ chối đầu vào đó.
3. `List.copyOf(direct)` cũng từ chối `null`, dù `direct` vốn đã không cho sửa.
4. Lớp bao `wrapped` chặn `set`, nhưng việc không cho thay phần tử không đồng nghĩa phải loại bỏ phần tử `null` đang có.
5. Pipeline `withoutNull` chủ động lọc bỏ `null` trước khi dùng collector từ chối `null`.

Bước lọc cuối là một quyết định về dữ liệu, không phải thủ thuật luôn đúng để né lỗi. Nếu `null` là đầu vào không hợp lệ cần báo cho phía gọi, tự loại bỏ nó có thể che mất lỗi. Chỉ lọc khi yêu cầu cho phép bỏ những phần tử đó.

Cũng cần phân biệt phần tử `null` bên trong nguồn với chính biến nguồn hoặc stream là `null`. Chính sách chứa phần tử không làm một lời gọi phương thức trên tham chiếu `null` trở nên hợp lệ.

## 5. Không cho sửa danh sách không có nghĩa phần tử bất biến

Khi thu thập một stream của các đối tượng, danh sách kết quả thường chứa các tham chiếu phần tử đã đi qua pipeline. Nếu không có bước tạo đối tượng mới, việc thu thập không tự sao chép sâu từng đối tượng.

Lưu vào `ListResultAndElementsDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ListResultAndElementsDemo {
    static final class Task {
        private String label;

        Task(String label) {
            this.label = label;
        }
    }

    record TaskView(String label) {}

    public static void main(String[] args) {
        Task first = new Task("draft");
        List<Task> source = new ArrayList<>(List.of(first));
        List<Task> liveView = Collections.unmodifiableList(source);
        List<Task> result = source.stream().toList();
        List<TaskView> projected = source.stream()
                .map(task -> new TaskView(task.label))
                .toList();

        source.add(new Task("later"));
        System.out.println("sourceSizeAfterAdd=" + source.size());
        System.out.println("liveViewSizeAfterAdd=" + liveView.size());
        System.out.println("resultSizeAfterAdd=" + result.size());
        System.out.println("sameElementReference=" + (result.get(0) == first));

        first.label = "done";
        System.out.println("resultElementLabel=" + result.get(0).label);
        System.out.println("projectedLabel=" + projected.get(0).label());

        source.clear();
        System.out.println("liveViewSizeAfterClear=" + liveView.size());
        System.out.println("resultSizeAfterClear=" + result.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ListResultAndElementsDemo.java
java ListResultAndElementsDemo
```

Stdout:

```text
sourceSizeAfterAdd=2
liveViewSizeAfterAdd=2
resultSizeAfterAdd=1
sameElementReference=true
resultElementLabel=done
projectedLabel=draft
liveViewSizeAfterClear=0
resultSizeAfterClear=1
```

Chương trình tạo ba cách nhìn từ dữ liệu nguồn:

| Biến | Được tạo như thế nào | Tính chất trong ví dụ |
| --- | --- | --- |
| `liveView` | `Collections.unmodifiableList(source)` | Không cho sửa qua lớp bao, nhưng đọc cấu trúc nguồn trực tiếp |
| `result` | `source.stream().toList()` | Danh sách kết quả đã thu thập, chứa tham chiếu `Task` |
| `projected` | `map` sang `TaskView`, rồi `toList` | Chứa các đối tượng biểu diễn dữ liệu được tạo trong bước biến đổi |

Sau `source.add(...)`, nguồn và `liveView` cùng có hai phần tử, nhưng `result` vẫn có một. Sau `source.clear()`, `liveView` rỗng, còn `result` vẫn có phần tử đã thu thập.

`Collections.unmodifiableList` là một khung nhìn chỉ đọc của danh sách nền. Nó không tự sao chép cấu trúc nguồn; thay đổi danh sách nền qua một tham chiếu khác vẫn được phản ánh khi đọc khung nhìn. [Javadoc Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))

### Cấu trúc đã độc lập, đối tượng vẫn dùng chung

Dòng `sameElementReference=true` cho thấy `result.get(0)` chính là đối tượng `first`. Sửa trường `first.label` thành `done` làm giá trị đọc qua `result` cũng là `done`.

Không có lời gọi `result.set(...)` nào trong thay đổi đó. Danh sách không bị thay phần tử; chính đối tượng đang được phần tử tham chiếu đến đã đổi trạng thái.

Do vậy, câu “kết quả không cho sửa” cần được hiểu đúng phạm vi: chặn các thao tác sửa danh sách không đồng nghĩa chặn mọi thay đổi có thể nhìn thấy thông qua những phần tử của nó.

### Muốn một ảnh chụp dữ liệu phải chọn cách biểu diễn phần tử

`projected` chứa các `TaskView` được tạo khi nhãn còn là `draft`. Trường của `TaskView` trong ví dụ chỉ là một `String` bất biến, nên việc sửa `Task.label` sau đó không đổi `projectedLabel`.

Đây là một cách tách mô hình dữ liệu đầu ra khỏi đối tượng nguồn. Không suy ra mọi `record` đều bất biến sâu: nếu một record chứa trường tham chiếu đến danh sách hoặc đối tượng có thể sửa, vẫn phải thiết kế cách bảo vệ phần dữ liệu đó.

Tương tự, `new ArrayList<>(result)` tạo danh sách cho sửa nhưng không tự tạo các `Task` mới. Tạo bản sao cấu trúc và tạo bản sao trạng thái phần tử là hai công việc riêng.

### Không dùng “unmodifiable” để suy ra mọi bảo đảm khác

Một danh sách không cho sửa cũng không tự tạo chính sách phối hợp truy cập cho các đối tượng phần tử dùng chung. Khi dữ liệu được chia sẻ giữa các luồng thực thi, vẫn phải xem cách công bố dữ liệu và cách đọc hoặc sửa các đối tượng đó.

Bản thân `Stream.toList()` cũng không cam kết một lớp triển khai hay khả năng tuần tự hóa cụ thể. Không ép kiểu kết quả sang lớp nội bộ được quan sát ở một lần chạy để lấy thêm chức năng.

Kết quả có thể thuộc dạng đối tượng dựa trên giá trị; nên so sánh nội dung bằng `equals` khi đó là điều cần kiểm tra. Không xây giao thức dựa trên danh tính tham chiếu của hai kết quả `toList()`, và không dùng chính kết quả làm đối tượng khóa đồng bộ.

## 6. collect có thể tích lũy trong đối tượng sửa được nhưng trả kết quả không cho sửa

Tên “mutable reduction” mô tả cách tích lũy: các phần tử được đưa vào một vùng chứa bằng cách cập nhật vùng chứa đó. Nó không buộc đối tượng kết quả cuối cùng của mọi collector phải hỗ trợ sửa.

Có hai dạng sử dụng thường gặp:

- `collect(collector)`: collector đóng gói cách tạo vùng tích lũy, nhận phần tử, kết hợp và hoàn tất kết quả.
- `collect(supplier, accumulator, combiner)`: truyền trực tiếp cách tạo vùng chứa, đưa một phần tử vào và ghép hai phần kết quả.

Với `collectingAndThen`, sau bước thu thập còn có một hàm hoàn tất. Hàm đó có thể trả lớp bao không cho sửa. Vì vậy, nhìn thấy từ `collect` trong mã chưa đủ để kết luận kết quả có thể gọi `add`.

### Thí nghiệm thu thập song song

Lưu vào `ParallelListCollectionDemo.java`.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

public class ParallelListCollectionDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2, 3, 4, 5, 6);
        List<Integer> direct = source.parallelStream()
                .map(n -> n * 2)
                .toList();
        ArrayList<Integer> mutable = source.parallelStream()
                .map(n -> n * 2)
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
        List<Integer> wrapped = source.parallelStream()
                .map(n -> n * 2)
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(ArrayList::new),
                        Collections::unmodifiableList));

        System.out.println("direct=" + direct);
        System.out.println("mutable=" + mutable);
        System.out.println("wrapped=" + wrapped);
        System.out.println("equalBeforeEdits="
                + (direct.equals(mutable) && direct.equals(wrapped)));

        mutable.add(14);
        System.out.println("mutableAfterAdd=" + mutable);
        System.out.println("directAfterOtherEdit=" + direct);
        try {
            wrapped.add(14);
        } catch (UnsupportedOperationException e) {
            System.out.println("wrappedAdd=UnsupportedOperationException");
        }
        System.out.println("source=" + source);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ParallelListCollectionDemo.java
java ParallelListCollectionDemo
```

Stdout:

```text
direct=[2, 4, 6, 8, 10, 12]
mutable=[2, 4, 6, 8, 10, 12]
wrapped=[2, 4, 6, 8, 10, 12]
equalBeforeEdits=true
mutableAfterAdd=[2, 4, 6, 8, 10, 12, 14]
directAfterOtherEdit=[2, 4, 6, 8, 10, 12]
wrappedAdd=UnsupportedOperationException
source=[1, 2, 3, 4, 5, 6]
```

Ba kết quả ban đầu cùng chứa `[2, 4, 6, 8, 10, 12]` theo thứ tự gặp của nguồn. Chế độ song song không tự làm danh sách đầu ra mất thứ tự hoặc trở thành danh sách cho sửa.

Ở cách thu thập ba tham số:

```text
ArrayList::new     tạo vùng chứa mới
ArrayList::add     đưa một phần tử vào vùng chứa
ArrayList::addAll  ghép phần thứ hai vào phần thứ nhất
```

Thư viện có thể tạo nhiều vùng chứa trung gian và kết hợp chúng, thay vì cho mọi bên cùng sửa một `ArrayList` bên ngoài. Hàm tạo phải trả một vùng chứa mới mỗi lần được gọi; không trả lại cùng một danh sách dùng chung từ supplier. [Javadoc Stream.collect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.function.Supplier,java.util.function.BiConsumer,java.util.function.BiConsumer))

Trong `wrapped`, collector tích lũy vào các `ArrayList` rồi bước hoàn tất trả một lớp bao `Collections.unmodifiableList`. Vùng chứa nền này được tạo riêng cho kết quả; chương trình không để lộ một tham chiếu khác để sửa nó. Vì vậy, phía nhận `wrapped` không thể thêm phần tử qua API của danh sách.

`mutable.add(14)` chạy được vì cách thu thập đã chọn rõ `ArrayList`. Sửa `mutable` không sửa `direct` hay nguồn. Gọi `wrapped.add(14)` bị chặn.

### Đừng thay collect bằng tích lũy bên ngoài

Một cách viết gọi `forEach(output::add)` với `output` là `ArrayList` bên ngoài không có cùng giao thức tích lũy và kết hợp của collector. Với parallel stream, những hành động có thể cùng cập nhật một đối tượng không được bảo vệ.

Nếu mục tiêu là tạo danh sách, dùng thao tác thu thập diễn đạt đúng chính sách đầu ra. Không tự thêm trạng thái dùng chung chỉ để có được một danh sách cho sửa.

Ngay cả khi collector tổ chức quá trình tích lũy song song an toàn, đối tượng `ArrayList` trả về sau đó vẫn có hợp đồng thông thường của `ArrayList`. Nó không tự trở thành một collection an toàn cho mọi truy cập đồng thời trong phần còn lại của ứng dụng.

## 7. Thay cách thu thập còn có thể ảnh hưởng suy luận kiểu

Khi đổi từ `collect(Collectors.toList())` sang `toList()`, ngoài quyền sửa cần kiểm tra kiểu dữ liệu mà đoạn mã đang yêu cầu.

`String` là một `CharSequence`, nhưng Java không coi `List<String>` là kiểu con của `List<CharSequence>`. Nếu coi hai kiểu danh sách này như nhau, một phía có thể thêm một loại `CharSequence` khác vào danh sách mà phía còn lại tin rằng chỉ chứa `String`. [Java Language Specification về kiểu con](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.2)

Lời gọi `collect` tổng quát có thể suy luận kiểu collector từ ngữ cảnh kiểu đích. Trong khi đó, `toList()` trả `List<T>` theo kiểu phần tử của stream đang có.

Lưu chương trình hợp lệ sau vào `ListCollectionTypeDemo.java`.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ListCollectionTypeDemo {
    public static void main(String[] args) {
        List<CharSequence> collected =
                Stream.of("A", "B").collect(Collectors.toList());
        List<CharSequence> widened =
                Stream.<CharSequence>of("A", "B").toList();
        List<? extends CharSequence> readable =
                Stream.of("A", "B").toList();

        System.out.println("collected=" + collected);
        System.out.println("widened=" + widened);
        System.out.println("readable=" + readable);
        System.out.println("firstLength=" + readable.get(0).length());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ListCollectionTypeDemo.java
java ListCollectionTypeDemo
```

Stdout:

```text
collected=[A, B]
widened=[A, B]
readable=[A, B]
firstLength=1
```

Có ba lựa chọn khác nhau trong ví dụ:

- `collected` dùng suy luận kiểu ở lời gọi `collect`.
- `widened` yêu cầu ngay từ bước tạo stream rằng phần tử có kiểu `CharSequence`.
- `readable` dùng kiểu có ký tự đại diện để đọc những phần tử thuộc một kiểu con của `CharSequence`.

Chúng có thể in cùng nội dung, nhưng lý do các phép gán hợp lệ thuộc về hệ thống kiểu, không thuộc về quyền sửa ở thời gian chạy.

### Một thay thế máy móc có thể không biên dịch

Lưu riêng ví dụ **cố ý sai kiểu** dưới đây vào `IncompatibleToListAssignment.java`. Đây là thí nghiệm lỗi biên dịch, không phải chương trình được kỳ vọng chạy:

```java
import java.util.List;
import java.util.stream.Stream;

public class IncompatibleToListAssignment {
    public static void main(String[] args) {
        List<CharSequence> result = Stream.of("A", "B").toList();
    }
}
```

Kiểm chứng lỗi bằng:

```shell
javac --release 17 -encoding UTF-8 IncompatibleToListAssignment.java
```

Lệnh biên dịch thất bại. Phần thông báo chỉ ra nguyên nhân là:

```text
List<String> cannot be converted to List<CharSequence>
```

Đây là trích đoạn nguyên nhân từ thông báo trình biên dịch, không phải stdout của chương trình. Không có bước chạy `java` cho tệp cố ý sai này.

Cách sửa phù hợp trong tình huống đó là xác định kiểu stream cần có, chẳng hạn `Stream.<CharSequence>of(...)`, hoặc chọn kiểu biến nhận phù hợp với mục đích sử dụng. Không sửa bằng ép kiểu không được kiểm chứng hoặc chuyển sang kiểu thô để che lỗi.

### Ký tự đại diện không phải cơ chế làm danh sách chỉ đọc

`List<? extends CharSequence>` giới hạn những phép đưa giá trị vào ở mức kiểm tra kiểu; nó không phải lời hứa rằng mọi thao tác sửa danh sách đều bị cấm. Một số thao tác như xóa vẫn có thể được gọi về mặt kiểu.

Trong chương trình, `readable` không cho sửa ở thời gian chạy vì đối tượng thực được tạo bằng `toList()`, không phải vì chỉ riêng dấu `? extends` tạo ra tính chất đó.

Nếu một API cần bảo đảm kết quả không cho sửa, phải tạo và mô tả đúng kết quả theo hợp đồng. Không dùng một kiểu có ký tự đại diện để thay thế lời hứa đó.

## 8. Chọn cách tạo kết quả theo công việc tiếp theo

### Cần đọc một danh sách kết quả

Nếu chỉ cần duyệt kết quả hoặc trả danh sách không cho sửa qua API, `toList()` thường diễn đạt trực tiếp ý định. Nó giữ thứ tự gặp nếu có và vẫn giữ các lần xuất hiện trùng.

Tuy nhiên, cần xem dữ liệu có chứa đối tượng thay đổi được không. Nếu muốn một kết quả dữ liệu ổn định, chọn cách tạo phần tử đầu ra phù hợp thay vì chỉ chặn thao tác trên danh sách.

### Cần tiếp tục thêm, xóa, thay hoặc sắp xếp

Yêu cầu rõ `ArrayList` bằng `toCollection(ArrayList::new)`, hoặc tạo `new ArrayList<>(result)` khi đã có một danh sách kết quả.

Cách chọn này làm hợp đồng rõ với cả người viết và người đọc mã. Không cần phụ thuộc vào lớp triển khai ngầm của `Collectors.toList()`, và không cần thử sửa rồi bắt ngoại lệ để đoán chính sách ở thời gian chạy.

Nếu dùng phép tạo bản sao, hãy đặt tên phản ánh vai trò của bản sao trong công việc tiếp theo. Việc sao chép phải có mục đích; không cần sao chép thêm chỉ để đạt một lớp nội bộ mà chương trình không thực sự cần.

### Cần kết quả không cho sửa và từ chối null

`Collectors.toUnmodifiableList()` diễn đạt cả hai điều kiện. Nếu đầu vào có thể chứa `null`, quyết định báo lỗi, thay bằng giá trị hợp lệ hay loại bỏ phải đến từ hợp đồng nghiệp vụ.

Không đổi sang `toList()` chỉ để hết `NullPointerException` nếu việc từ chối `null` vốn là một điều kiện đúng của API.

### Cần tùy chỉnh bước hoàn tất

`collectingAndThen` cho phép thu thập rồi chuyển đổi kết quả một lần ở cuối, ví dụ bao danh sách nền riêng thành lớp không cho sửa. Quyền sửa cuối cùng phụ thuộc cả hai bước, không chỉ bộ tích lũy trung gian. [Javadoc collectingAndThen](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#collectingAndThen(java.util.stream.Collector,java.util.function.Function))

Nếu dùng lớp bao, đừng để lộ tham chiếu sửa được của danh sách nền rồi gọi đó là một ảnh chụp không thể thay đổi. Hơn nữa, đối tượng phần tử vẫn cần một chính sách riêng.

### Cần thứ tự khác với thứ tự gặp

Các cách tạo `List` không tự sắp xếp hoặc tự loại trùng. Nếu muốn sắp xếp, dùng một bước sắp xếp; nếu muốn loại trùng, mô tả rõ quy tắc loại trùng.

Nếu nguồn không có thứ tự gặp được bảo đảm, tạo `List` không tự tạo thêm một thứ tự nghiệp vụ ổn định cho các giá trị đó. Muốn kết quả có thứ tự xác định, cần chỉ định tiêu chí phù hợp.

Thứ tự đầu ra và quyền sửa là hai quyết định độc lập. Một danh sách đã sắp xếp có thể cho sửa hoặc không cho sửa tùy cách thu thập.

### Kiểm tra phiên bản khi chuyển mã

| API | Có từ Java |
| --- | --- |
| `Stream`, `Collectors.toList()` và `Collectors.toCollection(...)` | 8 |
| `Collectors.toUnmodifiableList()` | 10 |
| `Stream.toList()` | 16 |

Các lệnh trong bài dùng `--release 17`, nên đều nằm trong phạm vi hỗ trợ của Java 17. Nếu dự án phải biên dịch với Java 8 hoặc 11, không thể chỉ thay sang `Stream.toList()` rồi mong vẫn giữ được mức tương thích đó.

Một lần chuyển đổi mã cần kiểm tra cả nơi sử dụng kết quả: thao tác sửa, chính sách `null`, kiểu đích và phiên bản Java. So sánh hai dòng tạo danh sách mà không đọc các thao tác theo sau có thể bỏ sót thay đổi hành vi.

## 9. Những kết luận cần tránh

| Kết luận sai | Cách hiểu đúng |
| --- | --- |
| Kết quả có kiểu `List` thì phải gọi được `add` | Giao diện không bảo đảm mọi cách triển khai hỗ trợ sửa |
| `collect(Collectors.toList())` luôn trả ArrayList cho sửa | Kiểu triển khai và khả năng sửa không được API bảo đảm |
| `toList()` chỉ cấm thay đổi kích thước | Các thao tác sửa như `set` và `sort` cũng bị chặn |
| Mọi cách thu thập bằng collect đều cho sửa | Bước hoàn tất có thể trả kết quả không cho sửa |
| Hai kết quả không cho sửa có cùng chính sách null | `toList` và `toUnmodifiableList` khác nhau ở điểm này |
| Danh sách không cho sửa là bản sao sâu | Các đối tượng phần tử có thể vẫn dùng chung |
| Lớp bao unmodifiable không đổi khi nguồn đổi | Khung nhìn đọc danh sách nền và có thể phản ánh thay đổi từ đường khác |
| Tạo ArrayList từ kết quả sẽ sao chép từng đối tượng | Nó sao chép cấu trúc chứa các tham chiếu, không tự sao chép sâu |
| `final List` làm danh sách bất biến | `final` điều khiển phép gán lại biến tham chiếu |
| Parallel stream trả kết quả cho sửa hoặc không có thứ tự | Các điều kiện đó vẫn do thao tác và collector cụ thể quyết định |
| Collector dùng ArrayList trung gian thì kết quả luôn sửa được | Hàm hoàn tất có thể bao hoặc chuyển đổi kết quả |
| Đổi collect sang toList chỉ là rút gọn cú pháp | Có thể đổi quyền sửa, tính tương thích kiểu hoặc yêu cầu phiên bản |
| `List<? extends T>` tự bảo đảm không cho sửa | Ký tự đại diện giải quyết quan hệ kiểu, không tạo lớp bao bảo vệ |
| Có thể đồng bộ trên danh tính kết quả toList | API không cho phép phụ thuộc vào danh tính của kết quả theo cách đó |

Đối với một API trả danh sách, lời mô tả hữu ích cần nêu kết quả có cho sửa không, có chấp nhận `null` không, thứ tự nào được giữ và dữ liệu phần tử được bảo vệ tới mức nào. Chỉ ghi kiểu `List<T>` chưa truyền đạt đủ các điều kiện này.

## 10. Thực hành kiểm chứng hợp đồng

### Bài 1: sửa sau khi thu thập

Một phương thức tạo kết quả bằng `source.stream().toList()`, rồi gọi `result.add(extra)`. Thay sang `collect(Collectors.toList())` có đủ để bảo đảm thuật toán sẽ luôn sửa được kết quả không?

**Đối chiếu:**

Không. `Collectors.toList()` không có cam kết cho sửa. Nếu thuật toán cần thêm phần tử, yêu cầu rõ `ArrayList` bằng `toCollection(ArrayList::new)`, hoặc tạo một bản sao `ArrayList` trước giai đoạn sửa.

### Bài 2: thay phần tử không đổi size

Kết quả của `toList()` có ba phần tử. Gọi `set(0, value)` có hợp lệ vì kích thước vẫn bằng ba không?

**Đối chiếu:**

Không. Thay phần tử vẫn là thao tác sửa danh sách và bị chặn bằng `UnsupportedOperationException`. “Không cho sửa” mạnh hơn “không cho đổi kích thước”.

### Bài 3: đầu vào có null

Pipeline đang dùng `toList()` và dữ liệu có một phần tử `null`. Đổi sang `collect(Collectors.toUnmodifiableList())` có giữ nguyên hành vi chỉ vì cả hai không cho sửa không?

**Đối chiếu:**

Không. Collector thứ hai từ chối `null`. Cần quyết định có giữ phần tử `null`, báo lỗi hay biến đổi dữ liệu theo hợp đồng.

### Bài 4: nguồn và phần tử cùng thay đổi

Thu thập một `List<Task>` bằng `toList()`. Sau khi hoàn tất, thêm một `Task` mới vào nguồn, rồi đổi nhãn của một `Task` đã nằm trong kết quả. Hai thay đổi có tác động giống nhau không?

**Đối chiếu:**

Không. Thêm vào cấu trúc nguồn không tự thêm phần tử vào danh sách kết quả đã thu thập. Nhưng sửa trạng thái đối tượng `Task` đang dùng chung có thể được nhìn thấy qua phần tử trong kết quả.

Muốn một ảnh chụp dữ liệu độc lập, cần tạo phần tử đầu ra phù hợp, như `TaskView` chứa nhãn `String` trong chương trình.

### Bài 5: vùng tích lũy và kết quả cuối

Một collector tích lũy vào `ArrayList`, sau đó bước hoàn tất gọi `Collections.unmodifiableList`. Phía gọi có được thêm vào danh sách trả về vì biết bên trong là ArrayList không?

**Đối chiếu:**

Không. API của kết quả cuối bị lớp bao chặn các thao tác sửa. Biết vùng chứa trung gian cho sửa không thay đổi hợp đồng của đối tượng đã trả về.

Nếu một tham chiếu khác tới danh sách nền bị để lộ, cần đánh giá đường sửa đó riêng; lớp bao không tự cắt quan hệ với dữ liệu nền.

### Bài 6: đổi cách viết và lỗi kiểu

Một phép gán vào `List<CharSequence>` biên dịch với `Stream.of("A", "B").collect(Collectors.toList())`. Đổi đuôi sang `toList()` thì lỗi. Có phải vì kết quả không cho sửa nên Java từ chối phép gán không?

**Đối chiếu:**

Không. Đây là vấn đề suy luận kiểu và quan hệ giữa `List<String>` với `List<CharSequence>`. Có thể yêu cầu kiểu stream là `CharSequence` ngay từ đầu hoặc chọn kiểu biến nhận phù hợp. Quyền sửa là một hợp đồng khác.

### Bài 7: chọn hai phiên bản kết quả

Từ danh sách số `[3, 1, 3, 2]`, hãy tạo:

1. Một danh sách sắp tăng dần, giữ phần tử trùng và không cho sửa.
2. Một `ArrayList` sắp tăng dần, giữ phần tử trùng và cho phép thêm `4` sau khi thu thập.

**Đối chiếu về cách làm:**

Phiên bản đầu có thể dùng `sorted().toList()`, cho `[1, 2, 3, 3]`. Phiên bản sau dùng `sorted().collect(Collectors.toCollection(ArrayList::new))`, rồi thêm `4` để có `[1, 2, 3, 3, 4]`.

Khi kiểm chứng, đọc lại nguồn để xác nhận không bị sắp xếp tại chỗ. Đồng thời giải thích vì sao việc giữ thứ tự kết quả và việc cho phép sửa là hai quyết định được lựa chọn riêng.
