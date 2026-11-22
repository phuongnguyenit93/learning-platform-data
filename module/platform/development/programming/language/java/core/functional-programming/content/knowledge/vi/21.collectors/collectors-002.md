# `Stream.toList()` trả về danh sách không cho sửa cấu trúc

## 1. Bài toán: thu thập dữ liệu từ Stream thành List

Trong Java, Stream thường được dùng để **biến đổi, lọc, sắp xếp** dữ liệu, rồi thu thập kết quả thành một danh sách. Từ **Java 16**, giao diện `java.util.stream.Stream<T>` cung cấp terminal operation:

```java
List<T> toList();
```

Ví dụ:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> names = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() >= 3)
        .toList();

System.out.println(names); // [Lan, Minh]
```

`toList()` **tiêu thụ stream** và trả một `List<T>` chứa các phần tử của luồng. Nếu nguồn có *encounter order* (thứ tự gặp phần tử), kết quả giữ thứ tự ấy. Nhưng có một điều kiện quan trọng:

**Danh sách do `Stream.toList()` trả về là *unmodifiable*: mọi lời gọi tới phương thức sửa đổi trên danh sách sẽ ném `UnsupportedOperationException`.**

Điều này không chỉ có nghĩa “không được `add`/`remove` để đổi số phần tử”. Nó còn có nghĩa **không được thay phần tử ở chỉ số cũ bằng `set`, sắp xếp ngay trên list bằng `sort` hoặc áp dụng `replaceAll`**. Một danh sách “không thay đổi kích thước” nhưng cho phép `set` là một khái niệm khác; `Stream.toList()` có ràng buộc chặt hơn.

Những điều cần phân biệt trong bài:

- **Không sửa được List** ≠ **phần tử bên trong bất biến**.
- **Danh sách kết quả không sửa được** ≠ **nguồn ban đầu cũng không sửa được**.
- `Stream.toList()` ≠ `Collectors.toList()` ≠ `Collectors.toUnmodifiableList()`.
- `Stream.toList()` có thể chứa phần tử `null`; một số cách tạo list unmodifiable khác **không** cho phép `null`.

## 2. Terminal operation: khi nào dữ liệu được thu thập?

`Stream.toList()` là một **terminal operation**, tức một phép toán kết thúc pipeline. Các phép toán trung gian như `filter`, `map`, `sorted` được xây dựng lười (*lazy*), còn `toList` yêu cầu tiêu thụ nguồn để tạo kết quả.

```java
List<Integer> squares = Stream.of(1, 2, 3, 4)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();

System.out.println(squares); // [4, 16]
```

Ở đây:

1. Nguồn cung cấp `1,2,3,4`.
2. `filter` giữ `2,4`.
3. `map` chuyển thành `4,16`.
4. `toList` thực hiện phép thu thập và trả `List<Integer>` theo encounter order.

`toList` không trả một Stream mới để nối tiếp `map`. Sau khi đã gọi terminal operation, stream đã tiêu thụ và không được tái sử dụng:

```java
Stream<Integer> numbers = Stream.of(1, 2, 3);
List<Integer> first = numbers.toList();

// SAI ở runtime: stream đã được tiêu thụ.
// List<Integer> second = numbers.toList();
```

Nếu cần chạy hai pipeline, hãy tạo **hai stream** từ nguồn có khả năng cung cấp lại dữ liệu:

```java
List<Integer> values = List.of(1, 2, 3);
List<Integer> first = values.stream().toList();
long count = values.stream().count();
```

Đoạn này chạy hợp lệ vì mỗi lời gọi `values.stream()` tạo một stream mới.

## 3. “Không cho sửa cấu trúc” phải hiểu thế nào cho chính xác?

Xét:

```java
List<String> letters = Stream.of("A", "B").toList();
```

Các phép sau đều là **thao tác sửa đổi** trên list kết quả, không được hỗ trợ:

| Phương thức | Ý định | Kết quả với `Stream.toList()` |
| --- | --- | --- |
| `letters.add("C")` | Thêm phần tử | `UnsupportedOperationException` |
| `letters.add(0, "C")` | Chèn vào chỉ số | `UnsupportedOperationException` |
| `letters.remove("A")` | Xóa phần tử | `UnsupportedOperationException` |
| `letters.clear()` | Xóa hết | `UnsupportedOperationException` |
| `letters.set(0, "X")` | Đổi phần tử tại một chỉ số | `UnsupportedOperationException` |
| `letters.sort(...)` | Sắp xếp *tại chỗ* | `UnsupportedOperationException` |
| `letters.replaceAll(...)` | Thay các phần tử bằng giá trị mới | `UnsupportedOperationException` |
| `letters.removeIf(...)` | Xóa phần tử thỏa điều kiện | `UnsupportedOperationException` |
| `letters.listIterator().set(...)` | Thay qua iterator | `UnsupportedOperationException` |

**Đừng nhầm “unmodifiable” với “fixed-size”.** Ví dụ `Arrays.asList("A","B")` tạo một list kích thước cố định: `add`/`remove` bị chặn, nhưng `set(0,"X")` vẫn có thể thành công. `Stream.toList()` chặn cả `set`.

Các hành động **chỉ đọc** vẫn hợp lệ:

```java
List<String> letters = Stream.of("A", "B").toList();

System.out.println(letters.size()); // 2
System.out.println(letters.get(0)); // A
System.out.println(letters.contains("B")); // true
System.out.println(letters.stream().map(String::toLowerCase).toList());
// [a, b]
```

Một danh sách unmodifiable vẫn có thể được **đọc, duyệt, lọc và dùng làm đầu vào cho một pipeline mới**. Chỉ không thể chỉnh trực tiếp danh sách ấy.

## 4. Chương trình Java 17 hoàn chỉnh: kiểm chứng các hợp đồng

Tạo tệp **`StreamToListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamToListDemo {
    static final class Box {
        private String value;

        Box(String value) {
            this.value = value;
        }

        void rename(String next) {
            this.value = next;
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> names = Stream.of("Lan", "Minh", "An")
                .filter(name -> name.length() >= 3)
                .toList();
        System.out.println("Names: " + names);

        try {
            names.add("Hoa");
        } catch (UnsupportedOperationException ex) {
            System.out.println("add: blocked");
        }

        try {
            names.set(0, "Mai");
        } catch (UnsupportedOperationException ex) {
            System.out.println("set: blocked");
        }

        try {
            names.sort(Comparator.naturalOrder());
        } catch (UnsupportedOperationException ex) {
            System.out.println("sort: blocked");
        }

        try {
            names.remove("Lan");
        } catch (UnsupportedOperationException ex) {
            System.out.println("remove: blocked");
        }

        System.out.println("Names after attempts: " + names);

        // Muốn một danh sách có thể thêm/xóa/sửa: tạo bản mutable.
        List<String> mutable = new ArrayList<>(names);
        mutable.add("Hoa");
        mutable.set(0, "Mai");
        System.out.println("Mutable: " + mutable);

        // toList chấp nhận phần tử null trong Stream.
        List<String> nullable = Stream.of(
                "A", (String) null, "B").toList();
        System.out.println("Null preserved: " + nullable);

        try {
            Stream.of("A", (String) null, "B")
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("toUnmodifiableList null: blocked");
        }

        // Thu thập rõ ràng thành ArrayList mutable.
        List<String> collectedMutable = Stream.of("P", "Q")
                .collect(Collectors.toCollection(ArrayList::new));
        collectedMutable.add("R");
        System.out.println("Collector mutable: " + collectedMutable);

        // toList là kết quả riêng về cấu trúc danh sách.
        ArrayList<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> snapshot = source.stream().toList();
        List<String> liveView = Collections.unmodifiableList(source);
        source.add("C");
        System.out.println("Source now: " + source);
        System.out.println("Stream result: " + snapshot);
        System.out.println("Live view: " + liveView);

        // List không sửa được, nhưng đối tượng bên trong có thể mutable.
        Box first = new Box("OLD");
        Box second = new Box("SECOND");
        List<Box> boxes = Stream.of(first, second).toList();
        first.rename("NEW");
        System.out.println("Mutable elements: " + boxes);

        // Stream có encounter order -> toList giữ encounter order.
        List<String> ordered = IntStream.rangeClosed(1, 4)
                .parallel()
                .mapToObj(n -> "N" + n)
                .toList();
        System.out.println("Parallel ordered: " + ordered);

        // Một phép biến đổi mới tạo list mới, không sửa names.
        List<String> sortedCopy = names.stream()
                .sorted()
                .toList();
        System.out.println("Sorted copy: " + sortedCopy);
        System.out.println("Original names: " + names);

        // Stream rỗng vẫn cho ra list không sửa được.
        List<String> empty = Stream.<String>empty().toList();
        System.out.println("Empty: " + empty);
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 StreamToListDemo.java
java StreamToListDemo
```

**Stdout kỳ vọng chính xác:**

```text
Names: [Lan, Minh]
add: blocked
set: blocked
sort: blocked
remove: blocked
Names after attempts: [Lan, Minh]
Mutable: [Mai, Minh, Hoa]
Null preserved: [A, null, B]
toUnmodifiableList null: blocked
Collector mutable: [P, Q, R]
Source now: [A, B, C]
Stream result: [A, B]
Live view: [A, B, C]
Mutable elements: [NEW, SECOND]
Parallel ordered: [N1, N2, N3, N4]
Sorted copy: [Lan, Minh]
Original names: [Lan, Minh]
Empty: []
```

### Kiểm tra từng nhóm kết quả

**Nhóm sửa đổi:** `names` giữ `[Lan, Minh]`. Mỗi thao tác `add`, `set`, `sort`, `remove` đều ném `UnsupportedOperationException` và được bắt riêng, vì thế bốn dòng `blocked` xuất hiện. Kết quả `names` không đổi.

**Nhóm mutable:** `new ArrayList<>(names)` sao chép các tham chiếu phần tử sang một list riêng có thể chỉnh. Thêm Hoa rồi đặt phần tử đầu thành Mai cho `[Mai, Minh, Hoa]`. List ban đầu vẫn là `[Lan, Minh]`.

**Nhóm `null`:** `Stream.of("A", (String) null, "B").toList()` có thể thu thập cả phần tử null. `Collectors.toUnmodifiableList()` thì từ chối null và ném `NullPointerException`; chương trình bắt lỗi để tiếp tục.

**Nhóm collector:** `Collectors.toCollection(ArrayList::new)` tạo một `ArrayList` thực sự mutable theo yêu cầu. Thêm R cho kết quả `[P, Q, R]`.

**Nhóm snapshot/view:** Sau khi `source.add("C")`, bản `snapshot` do stream đã thu thập vẫn có hai phần tử. `Collections.unmodifiableList(source)` là **view không sửa được** nhưng phản ánh thay đổi của danh sách gốc, nên hiển thị thêm C.

**Nhóm object mutable:** `boxes` không cho đổi cấu trúc qua list mutators, nhưng `first.rename("NEW")` thay đổi trạng thái của `Box` mà list đang tham chiếu. Do đó khi in, thấy `[NEW, SECOND]`.

**Nhóm thứ tự:** `IntStream.rangeClosed(1,4)` có encounter order; dù map có thể thực thi song song, `toList()` giữ thứ tự `N1, N2, N3, N4`. `names.stream().sorted().toList()` tạo kết quả riêng; nó không gọi `List.sort` trên list gốc.

**Nhóm rỗng:** `Stream.<String>empty().toList()` trả list không có phần tử. Không suy ra list rỗng đó có implementation class cụ thể hoặc có thể dùng `==` để xác định canonical instance.

## 5. So sánh `Stream.toList()` với `Collectors.toList()`

Hai cách sau đều có thể tạo một `List<String>` gồm cùng dữ liệu:

```java
List<String> direct = Stream.of("A", "B").toList();

List<String> viaCollector = Stream.of("A", "B")
        .collect(Collectors.toList());
```

Nhưng **hợp đồng về quyền sửa** khác nhau:

| Tiêu chí | `Stream.toList()` | `Collectors.toList()` |
| --- | --- | --- |
| Có từ phiên bản | Java 16 | Java 8 |
| Cách gọi | Terminal trực tiếp trên Stream | `collect` với collector |
| Kiểu kết quả | `List<T>` | `List<T>` |
| Encounter order | Giữ nếu nguồn có encounter order | Collector bảo đảm theo encounter order của nguồn có thứ tự |
| Có được sửa list không? | **Không; mọi mutator đều bị chặn** | **Không có bảo đảm** về khả năng sửa |
| Bảo đảm loại implementation | Không | Không |
| Bảo đảm serializable | Không | Không |
| Có bảo đảm thread-safe | Không | Không |

**Quan trọng:** Trên nhiều bản JDK, `Collectors.toList()` hiện có thể cho kết quả `ArrayList` có thể sửa. Nhưng Javadoc **không bảo đảm** tính mutable hay implementation cụ thể. Do vậy không được viết logic phụ thuộc rằng `Collectors.toList()` chắc chắn luôn trả list mutable qua mọi JDK/triển khai.

Nếu cần một list mutable với loại cụ thể, hãy nói rõ mục đích:

```java
List<String> mutable = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));

mutable.add("C");
System.out.println(mutable); // [A, B, C]
```

Hoặc tạo bản mutable từ kết quả `toList`:

```java
List<String> mutable = new ArrayList<>(
        Stream.of("A", "B").toList());

mutable.add("C");
```

Trong các đoạn trên, `ArrayList` cần được import từ `java.util`. Hai chiến lược phù hợp tùy tổ chức code: thu thập trực tiếp vào collection mutable, hoặc thu thập không sửa được trước rồi sao chép khi thật sự cần chỉnh.

### `Collectors.toList()` có giống `Collectors.toUnmodifiableList()` không?

Không. Tên `Collectors.toList` **không hứa** mutable/unmodifiable. `Collectors.toUnmodifiableList()` (Java 10+) có hợp đồng **trả list unmodifiable** và **không chấp nhận phần tử null**.

Hãy chọn API theo *contract*, không theo một lần chạy quan sát class name của collection.

## 6. So sánh `Stream.toList()` với `Collectors.toUnmodifiableList()`

Cả hai đều có thể tạo danh sách không sửa được. Nhưng chúng khác nhau ở cách dùng và **chính sách null**:

```java
List<String> allowsNull = Stream.of(
        "A", (String) null, "B").toList();

System.out.println(allowsNull); // [A, null, B]
```

Trong khi:

```java
// Ném NullPointerException vì collector cấm phần tử null.
List<String> disallowsNull = Stream.of(
        "A", (String) null, "B")
        .collect(Collectors.toUnmodifiableList());
```

Đoạn thứ hai là ví dụ runtime lỗi có chủ đích, **không** chạy tiếp nếu không bắt exception. Khi viết chương trình hoàn chỉnh, cần kiểm tra dữ liệu hoặc dùng `try/catch` nếu có chính sách xử lý lỗi rõ ràng.

Bảng:

| Tiêu chí | `Stream.toList()` | `Collectors.toUnmodifiableList()` |
| --- | --- | --- |
| Phiên bản | Java 16+ | Java 10+ |
| Cách dùng | `stream.toList()` | `stream.collect(...)` |
| Kết quả | Unmodifiable `List<T>` | Unmodifiable `List<T>` |
| Phần tử null | **Được phép** | **Không được phép** |
| Có thể `add`, `remove`, `set` | Không | Không |
| Bảo đảm là một lớp cụ thể | Không | Không |

Nếu null là dữ liệu không hợp lệ, có thể **validate trước** và báo lỗi rõ hơn, hoặc dùng collector cấm null làm một lớp kiểm tra bổ sung. Nếu null hợp lệ trong ứng dụng, đừng tự thay `toList()` bằng `toUnmodifiableList()` mà không xét thay đổi contract.

### `List.of` và `List.copyOf`

`List.of(...)` (Java 9+) tạo list unmodifiable và **từ chối null**. `List.copyOf(collection)` (Java 10+) cũng tạo kết quả unmodifiable và **từ chối null** trong collection đầu vào.

```java
List<String> a = List.of("A", "B");
List<String> b = List.copyOf(a);

System.out.println(a); // [A, B]
System.out.println(b); // [A, B]
```

Không suy ra `a == b` phải đúng hoặc sai: những API unmodifiable/value-based có thể tái sử dụng instance theo implementation. Dùng `equals` khi cần so sánh nội dung.

## 7. Unmodifiable list không đồng nghĩa các phần tử đều immutable

Đây là điểm quan trọng trong thiết kế API:

```java
class Ticket {
    private String status;

    Ticket(String status) {
        this.status = status;
    }

    void setStatus(String status) {
        this.status = status;
    }

    @Override
    public String toString() {
        return status;
    }
}
```

Nếu một List chứa các `Ticket` mutable:

```java
Ticket ticket = new Ticket("NEW");
List<Ticket> tickets = Stream.of(ticket).toList();

ticket.setStatus("DONE");
System.out.println(tickets); // [DONE]
```

Các đoạn này là **mã minh họa cần đặt trong ngữ cảnh lớp/phương thức phù hợp**. `tickets` không cho thêm/xóa/thay phần tử, nhưng object `ticket` vẫn đổi trạng thái từ `NEW` sang `DONE`. List giữ **tham chiếu đến object**, không tạo bản deep copy của object ấy.

Vì thế cần phân biệt:

- **Unmodifiable collection:** không được thay đổi membership/vị trí/tham chiếu phần tử thông qua collection.
- **Immutable element:** trạng thái của từng phần tử không thể thay đổi thông qua API thông thường.
- **Deep immutability:** cả đồ thị đối tượng có thể truy cập từ cấu trúc đều bất biến theo hợp đồng.
- **Thread safety:** không tự suy ra chỉ vì list không cho sửa.

`Stream.toList()` chỉ đưa ra hợp đồng **unmodifiable list**. Nó không tự biến các object mutable thành record bất biến, không clone từng phần tử, và không bảo đảm nội dung object an toàn khi nhiều thread chỉnh sửa.

### Dùng record và bản sao phòng vệ khi cần

`record` giúp định nghĩa dữ liệu mang tính giá trị rõ ràng, nhưng **record chứa một tham chiếu tới list mutable** vẫn có thể lộ thay đổi qua list ấy.

Ví dụ:

```java
record Order(String id, List<String> items) {
    Order {
        items = List.copyOf(items);
    }
}
```

Constructor compact tạo bản danh sách không sửa được; việc này bảo vệ cấu trúc danh sách. `List.copyOf` từ chối phần tử null, và đây là lựa chọn chủ ý. Nếu phần tử của `items` lại là object mutable, vẫn cần xem xét sao chép hoặc mô hình bất biến ở cấp sâu hơn.

## 8. Kết quả có phản ánh thay đổi của danh sách nguồn không?

Khi chạy:

```java
ArrayList<String> source = new ArrayList<>(List.of("A", "B"));
List<String> result = source.stream().toList();

source.add("C");

System.out.println(source); // [A, B, C]
System.out.println(result); // [A, B]
```

`result` là một danh sách kết quả riêng về **cấu trúc phần tử đã thu thập**. Một lần thêm phần tử mới vào `source` **sau khi `toList` hoàn tất** không tự thêm phần tử đó vào `result`.

Tuy vậy, với phần tử là object mutable, **tham chiếu tới phần tử** vẫn có thể cùng trỏ vào một object; sửa object qua nguồn có thể khiến cả nguồn và kết quả quan sát giá trị mới. Đây là “shallow snapshot” theo cách diễn đạt thực hành, không phải một deep snapshot của toàn bộ trạng thái.

### `Collections.unmodifiableList(source)` là một view

`Collections.unmodifiableList(source)` có ngữ nghĩa khác: nó tạo một **view** ngăn sửa thông qua view, nhưng các thay đổi vào collection nguồn vẫn phản ánh qua view.

```java
ArrayList<String> source = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(source);

source.add("C");
System.out.println(view); // [A, B, C]
```

Cần import `java.util.Collections` và `java.util.ArrayList`. Không nhầm view với `Stream.toList`. Chúng đều chặn `view.add(...)`/`result.add(...)`, nhưng phản ứng khác nhau khi nguồn được cập nhật **sau khi** tạo kết quả.

**Không chỉnh danh sách nguồn trong lúc đang stream** nếu nguồn không hỗ trợ concurrent modification phù hợp. Quy tắc *non-interference* của Stream yêu cầu tránh thay đổi nguồn trong quá trình vận hành pipeline; việc minh họa cập nhật **sau terminal** là tình huống khác.

## 9. Muốn danh sách có thể sửa: ba lựa chọn an toàn

### Cách 1 — `Collectors.toCollection(ArrayList::new)`

Đây là cách biểu đạt rõ nhất trong chính pipeline:

```java
List<String> values = Stream.of("B", "A")
        .sorted()
        .collect(Collectors.toCollection(ArrayList::new));

values.add("C");
values.set(0, "X");
System.out.println(values); // [X, B, C]
```

`Collectors.toCollection` dùng factory `ArrayList::new` để tạo collection đích, nên quyền sửa của `ArrayList` là phần có thể dựa vào.

### Cách 2 — Copy từ `toList`

```java
List<String> values = new ArrayList<>(
        Stream.of("A", "B").toList());

values.remove("A");
System.out.println(values); // [B]
```

Phù hợp khi API trung gian cần trả unmodifiable list và chỉ một số caller cần bản mutable.

### Cách 3 — Chọn dữ liệu khác khi không cần List

Nếu yêu cầu là tra cứu theo mã, `Map` có thể tốt hơn List. Nếu yêu cầu là tổng hợp số, `sum`/`reduce` có thể bỏ qua cả bước tạo list. Không nên tự tạo một collection chỉ để cộng số rồi bỏ đi.

```java
int total = Stream.of(10, 20, 30)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 60
```

Thiết kế theo mục tiêu nghiệp vụ sẽ tránh các bước trung gian và sai lầm “thu thập rồi cố mutate” không cần thiết.

## 10. Dùng `sorted`, `map`, `filter` để tạo kết quả mới

Khi danh sách đã không cho chỉnh, các phép biến đổi nên tạo **danh sách mới**:

```java
List<String> original = Stream.of("c", "a", "b").toList();

List<String> sorted = original.stream()
        .sorted()
        .toList();

List<String> upper = original.stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(original); // [c, a, b]
System.out.println(sorted);   // [a, b, c]
System.out.println(upper);    // [C, A, B]
```

`sorted` trong pipeline **không đồng nghĩa** với `List.sort` sửa chính danh sách. Nó xây một stream theo thứ tự sắp xếp rồi `toList` tạo list kết quả. Cả ba danh sách ở ví dụ đều có thể là unmodifiable list; bạn vẫn có thể biến đổi dữ liệu bằng cách khởi tạo pipeline mới.

Nếu cần loại một phần tử:

```java
List<String> withoutA = original.stream()
        .filter(value -> !value.equals("a"))
        .toList();

System.out.println(withoutA); // [c, b]
```

Đây là hướng tiếp cận **không mutate**, rất thuận lợi khi làm việc với dữ liệu được dùng ở nhiều tầng của ứng dụng.

## 11. Thứ tự, stream song song và `toList`

Một stream có encounter order, như từ `List` hoặc `IntStream.range`, cho kết quả `toList` theo thứ tự đó, kể cả khi stream xử lý song song:

```java
List<String> ids = java.util.stream.IntStream
        .rangeClosed(1, 5)
        .parallel()
        .mapToObj(n -> "ID-" + n)
        .toList();

System.out.println(ids);
// [ID-1, ID-2, ID-3, ID-4, ID-5]
```

Nhưng điều này **không có nghĩa** các phép gọi mapper thực thi lần lượt theo cùng thứ tự. Các phép tính trung gian có thể chạy trên nhiều thread; `toList` chịu trách nhiệm thu thập kết quả theo encounter order của luồng có thứ tự.

Nếu nguồn không có thứ tự như `HashSet`, hoặc đã gọi `unordered()` để bỏ ràng buộc, không nên dựa vào một thứ tự kết quả cụ thể cho nghiệp vụ. Hãy dùng `sorted` khi muốn đặt thứ tự rõ ràng.

### Unmodifiable không tự động thread-safe cho cả ứng dụng

Việc nhiều thread **đọc** một list đã được công bố an toàn và có các phần tử bất biến thường dễ quản lý hơn việc chia sẻ một `ArrayList` mutable. Tuy nhiên, `Stream.toList` không tự giải quyết việc công bố tham chiếu giữa các thread (*safe publication*) hay việc các phần tử bên trong bị mutate đồng thời.

Không dùng `parallelStream().forEach(result::add)` để thu thập vào một list ngoài mà không có cơ chế bảo vệ. Với mục tiêu tạo list, `map(...).toList()` hoặc collector phù hợp tốt hơn. Nếu thực sự cần cập nhật trạng thái chia sẻ, thiết kế đồng bộ và quyền sở hữu rõ ràng.

## 12. Có thể phụ thuộc class name, serializable hay identity của kết quả không?

Javadoc của `Stream.toList()` **không bảo đảm implementation type cụ thể** hay khả năng serializable của danh sách kết quả. Ngoài ra, danh sách trả về **có thể là value-based**, nghĩa là không nên dùng reference equality `==`, `System.identityHashCode` hoặc dùng bản thân object làm khóa đồng bộ để xác lập logic ứng dụng.

Ví dụ nên làm:

```java
List<String> a = Stream.of("A", "B").toList();
List<String> b = Stream.of("A", "B").toList();

System.out.println(a.equals(b)); // true
```

`equals` kiểm tra nội dung list theo contract. Không nên viết `a == b` rồi giả định sẽ luôn true hoặc false: việc tái sử dụng instance và lớp triển khai không phải một cam kết cần dùng trong code nghiệp vụ.

Tương tự, đừng tự ép kiểu:

```java
// KHÔNG ĐƯỢC giả định kết quả là ArrayList.
// ArrayList<String> a = (ArrayList<String>) Stream.of("A").toList();
```

Nếu cần `ArrayList`, hãy tạo cụ thể một `ArrayList` hoặc thu thập vào `Collectors.toCollection(ArrayList::new)`.

## 13. Generics và khác biệt suy luận kiểu

`Stream.toList()` trả về `List<T>` dựa trên **kiểu T của stream nguồn**. Trong khi đó, `Collectors.toList()` là một collector generic và một số ngữ cảnh gán có thể giúp compiler suy luận kiểu khác nhau.

Ví dụ:

```java
List<CharSequence> values =
        Stream.<CharSequence>of("A", "B").toList();
```

Tại đây ta chỉ rõ `T = CharSequence` nên kết quả có kiểu `List<CharSequence>`. Nếu viết `Stream.of("A","B")`, Java thường suy ra `Stream<String>`; `List<String>` không phải subtype của `List<CharSequence>` vì generic Java bất biến theo tham số kiểu (*invariant*).

Một cách khác là đặt kiểu ở bước trung gian:

```java
List<CharSequence> values = Stream.of("A", "B")
        .<CharSequence>map(s -> s)
        .toList();
```

Hai đoạn là **hai phương án riêng**, không khai báo cùng biến `values` trong cùng một scope. Khi refactor từ `collect(Collectors.toList())` sang `toList()`, có thể cần điều chỉnh kiểu nguồn, dùng biến có kiểu rõ ràng hoặc mapper, chứ không chỉ thay chuỗi phương thức.

Đây là lỗi **kiểu lúc biên dịch**, không liên quan quyền sửa danh sách lúc runtime.

## 14. Chi phí và lý do chọn API

`Stream.toList()` thường giúp code ngắn gọn khi mục tiêu thật sự là một danh sách kết quả **không cần sửa**. Tránh tự chọn dựa trên giả định “luôn dùng ít bộ nhớ hơn” hay “luôn nhanh hơn” `collect(Collectors.toList())`. Việc tối ưu tùy JDK, kiểu nguồn, kích thước, các phép biến đổi trước đó và JVM.

Một số nguyên tắc:

- Nếu chỉ cần **list đọc được**, `toList()` rõ ràng, ít ký tự và có hợp đồng unmodifiable.
- Nếu cần **list mutable cụ thể**, dùng `Collectors.toCollection(ArrayList::new)`.
- Nếu cần **unmodifiable và cấm null**, dùng `Collectors.toUnmodifiableList()` (hoặc một API khác có cùng chính sách được xác minh).
- Nếu **không cần list** mà chỉ cần `sum`, `count`, `max`, hãy gọi terminal thích hợp.
- Nếu muốn tối ưu về hiệu năng, đo benchmark với workload đại diện, thay vì dựa vào class nội bộ của kết quả.

Đừng xem unmodifiable là “không cần kiểm thử”: hãy kiểm tra quyền sửa, trường hợp null, thứ tự kết quả và tính bất biến của dữ liệu phần tử theo đúng yêu cầu API.

## 15. Những lỗi thường gặp

| Lỗi hoặc suy luận | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `stream.toList().add(x)` | Kết quả unmodifiable | Tạo `ArrayList` hoặc `toCollection` |
| `stream.toList().set(0,x)` | `set` cũng là mutator và bị chặn | Copy mutable hoặc tạo list mới qua `map` |
| `list.sort(...)` trên kết quả `toList` | Sắp xếp tại chỗ không được hỗ trợ | `list.stream().sorted(...).toList()` |
| “Không sửa cấu trúc” nghĩa là vẫn `set` được | Nhầm với list fixed-size | Phân biệt unmodifiable và fixed-size |
| “`Collectors.toList` luôn mutable” | Không có bảo đảm contract | Dùng `toCollection(ArrayList::new)` |
| “`toList` không cho null” | Thực tế `toList` cho phép null | Phân biệt với `toUnmodifiableList`/`List.of` |
| “List unmodifiable thì object con immutable” | Chỉ hạn chế thao tác qua list | Dùng model bất biến/copy phòng vệ khi cần |
| “Source thêm phần tử thì kết quả `toList` tự cập nhật” | Kết quả không phải live view của nguồn | Tạo lại stream nếu cần snapshot mới |
| “`unmodifiableList(source)` là snapshot” | Đó là view phản ánh thay đổi nguồn | Copy trước nếu cần ngắt liên hệ cấu trúc |
| “`toList` trả `ArrayList`” | Implementation không bảo đảm | Không ép kiểu hay dùng class name |
| “Dùng `==` để kiểm tra hai kết quả `toList`” | Identity không đáng tin cho value-based list | Dùng `equals` |
| “Stream vẫn dùng được sau `toList`” | Terminal đã tiêu thụ stream | Tạo stream mới |
| “Parallel `toList` không giữ thứ tự” | Nếu nguồn ordered, kết quả vẫn giữ encounter order | Phân biệt thứ tự kết quả và thứ tự mapper |
| “List unmodifiable luôn thread-safe” | Phần tử mutable/safe publication vẫn là vấn đề | Xem xét toàn bộ dữ liệu và mô hình luồng |

## 16. Bài tập vận dụng

1. Tạo `Stream.of("A","B").toList()`. Lần lượt thử `add`, `set`, `remove`, `sort` và ghi lại exception. Tại sao “không được đổi kích thước” không mô tả đủ contract?
2. Dùng `List.of("A","B")` rồi so sánh quyền sửa của nó với `Arrays.asList("A","B")` và `Stream.of("A","B").toList()`.
3. Sửa code `stream.toList().add("C")` bằng hai cách: `new ArrayList<>(stream.toList())` và `stream.collect(Collectors.toCollection(ArrayList::new))`. Dùng **stream mới** cho mỗi cách.
4. Tạo một stream chứa `(String) null`. So sánh `toList` với `collect(Collectors.toUnmodifiableList())`, có `try/catch` để kiểm tra hành vi.
5. Dùng `Collectors.toList` rồi in class name ở một phiên chạy để quan sát. Tại sao không được dùng quan sát đó làm contract về mutability của API?
6. Từ nguồn `List.of("c","a","b")`, tạo `sorted` mới và `uppercase` mới bằng `stream().sorted().toList()` và `stream().map(...).toList()`, không sửa nguồn.
7. Tạo `List<Box> boxes = Stream.of(box).toList()` với `Box` có setter. Thử sửa `Box` sau khi tạo list. Giải thích vì sao list không đổi membership nhưng hiển thị giá trị mới.
8. Tạo một `ArrayList` nguồn và cả `source.stream().toList()` lẫn `Collections.unmodifiableList(source)`. Sau khi thêm một phần tử vào `source`, so sánh hai kết quả.
9. Thử tạo `List<CharSequence>` từ `Stream.of("A","B").toList()`. Sửa bằng `Stream.<CharSequence>of(...)`; nêu nguyên nhân generic invariance.
10. Với `IntStream.rangeClosed(1,100).parallel().mapToObj(n -> "ID"+n).toList()`, giải thích vì sao kết quả vẫn ordered nhưng việc log trong mapper không nên có expected stdout cố định.
11. Nếu một record chứa `List<MutableItem>`, `List.copyOf` có biến các `MutableItem` thành immutable không? Đề xuất model dữ liệu/defensive copy đúng hơn.
12. Khi tổng hợp đơn hàng, so sánh lựa chọn `orders.stream().mapToInt(Order::amount).sum()` với thu thập tất cả amount vào list rồi cộng sau. Trường hợp nào thực sự cần list?

## 17. Checklist trước khi dùng `Stream.toList()`

- Phiên bản Java mục tiêu có từ **Java 16** không?
- Caller có cần **thêm/xóa/đổi/sort** list kết quả không?
- Đã phân biệt **unmodifiable list** với **fixed-size list** chưa?
- Nguồn có phần tử `null` không? Chính sách null của downstream là gì?
- Phần tử trong list là immutable hay mutable? Có yêu cầu deep immutability không?
- Có đang mong dữ liệu cập nhật theo nguồn sau khi terminal hoàn tất không?
- Có cần giữ encounter order hoặc sắp xếp theo tiêu chí nghiệp vụ không?
- Nếu cần mutable, đã dùng `ArrayList`/`toCollection(ArrayList::new)` rõ ràng chưa?
- Có phụ thuộc class nội bộ, serializability hoặc identity của list kết quả không?
- Có tái sử dụng stream sau terminal hoặc đặt side effect nguy hiểm trong parallel pipeline không?
- Đã kiểm thử dữ liệu **rỗng, null, phần tử mutable, thao tác sửa, parallel order** chưa?

**Kết luận:** `Stream.toList()` (Java 16+) thu thập các phần tử thành một `List<T>` **không cho phép sửa đổi**, không chỉ cấm thay kích thước mà còn cấm `set`, `sort`, `replaceAll` và mọi mutator. Nó giữ encounter order khi nguồn có thứ tự, có thể chứa null, nhưng **không đóng băng trạng thái của object phần tử**. Khi cần danh sách mutable, hãy chọn rõ `Collectors.toCollection(ArrayList::new)` hoặc sao chép sang `ArrayList`; khi cần cấm null, hãy dùng contract tương ứng như `Collectors.toUnmodifiableList()`.
