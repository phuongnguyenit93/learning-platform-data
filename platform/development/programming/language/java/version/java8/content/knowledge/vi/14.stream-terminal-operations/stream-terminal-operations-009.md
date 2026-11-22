# `iterator()`, `spliterator()` và điều khiển duyệt thủ công trong Java Stream

**Phạm vi:** Java 8 trở lên; các API dưới đây vẫn được hỗ trợ trên các JDK hiện đại. Ví dụ chính viết theo Java 17+. Bài này thuộc nhóm **kết thúc Stream (terminal operations)**, tập trung vào hai cách lấy quyền điều khiển việc tiêu thụ phần tử từ pipeline. Khi chỉ cần lọc, tìm kiếm, thống kê hoặc gom kết quả thông thường, nên ưu tiên terminal operation ở mức cao hơn.

## 1. Vì sao `iterator()` và `spliterator()` là terminal operations?

Một pipeline thường có dạng:

```text
Nguồn dữ liệu -> filter/map/... (intermediate, lazy) -> terminal operation
                                                     |
                               iterator()/spliterator(): trả bộ duyệt
                                                     |
                                           mã của bạn gọi bước tiếp theo
```

- `stream.iterator()` trả `Iterator<T>`; `stream.spliterator()` trả `Spliterator<T>` (với `IntStream`, `LongStream`, `DoubleStream` có biến thể chuyên biệt). **Cả hai đều là terminal operations**, dù phần lớn phần tử chưa được duyệt ngay khi gọi.
- Chúng là hai “cửa thoát” khỏi mô hình duyệt nội bộ của Stream: mã gọi tự quyết định **khi nào lấy phần tử tiếp**, **dừng ở đâu** và, với `Spliterator`, **chia nguồn thành các phần**.
- Khác `count()`, `collect()` hoặc `forEach()`, hai phương thức này không nhất thiết duyệt hết nguồn trước khi trả về. `filter`, `map` và các bước lazy thường chạy khi bộ duyệt được yêu cầu lấy dữ liệu. Có thể có thao tác **đọc trước (look-ahead)**, nên một lần `hasNext()` không đồng nghĩa chính xác một lần xử lý phần tử nguồn.
- Sau khi lấy `Iterator` hoặc `Spliterator`, coi pipeline gốc **đã được tiêu thụ**: không gọi terminal/intermediate operation khác trên cùng đối tượng stream; tạo stream mới từ nguồn nếu cần một lượt mới. Thực thi lại một stream đã tiêu thụ là không hợp lệ.
- Đừng nhầm với `Collection.iterator()` / `Collection.spliterator()`: chúng duyệt trực tiếp collection. `stream.filter(...).iterator()` và `stream.map(...).spliterator()` duyệt **kết quả của pipeline**, không chỉ nguồn ban đầu.

| Công cụ | Điều khiển thủ công | Khả năng chia | Khi phù hợp |
| --- | --- | --- | --- |
| `Iterator<T>` | `hasNext()`, `next()`, vòng `while`; dừng bằng `break` | Không | Tiêu thụ tuần tự theo nhu cầu, tích hợp API nhận iterator |
| `Spliterator<T>` | `tryAdvance()`, `forEachRemaining()` | `trySplit()` nếu hỗ trợ | Bộ xử lý mức thấp, chia công việc, tích hợp `StreamSupport` |
| `forEach()/forEachOrdered()` | Callback trên phần tử, không có `break` thông thường | Stream quyết định | Xử lý toàn bộ phần tử |
| `findFirst()/anyMatch()/limit()/takeWhile()` | Diễn đạt điều kiện ở pipeline | Do Stream điều phối | Tìm, dừng theo điều kiện hoặc giới hạn kết quả |

## 2. Duyệt bằng `Iterator<T>`

Giao diện `Iterator<T>` có các thao tác chính:

- `hasNext()`: kiểm tra còn phần tử hay không; có thể kích hoạt xử lý upstream.
- `next()`: lấy phần tử tiếp theo; ném `NoSuchElementException` khi đã hết. Dùng cùng `hasNext()` hoặc có quy trình kiểm soát rõ ràng.
- `forEachRemaining(action)`: xử lý toàn bộ phần còn lại, nhưng không có cách `break` trực tiếp trong callback.
- `remove()` là thao tác *tùy chọn* của `Iterator`; không giả định iterator từ stream hỗ trợ xóa. Nếu mục tiêu là sửa collection, thao tác trực tiếp lên collection bằng API phù hợp, chẳng hạn `removeIf`.

### Ví dụ chạy được: dừng khi gặp phần tử mong muốn

Lưu dưới tên **`ManualTraversalDemo.java`**:

```java
import java.util.Iterator;
import java.util.Spliterator;
import java.util.StringJoiner;
import java.util.stream.Stream;

public class ManualTraversalDemo {
    public static void main(String[] args) {
        iteratorExample();
        spliteratorExample();
    }

    private static void iteratorExample() {
        Iterator<String> iterator = Stream.of("  Lan  ", " ", " Minh ", "An")
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .iterator();

        while (iterator.hasNext()) {
            String name = iterator.next();
            System.out.println(name);
            if (name.equals("Minh")) {
                break;
            }
        }
    }

    private static void spliteratorExample() {
        Spliterator<Integer> remaining = Stream.of(1, 2, 3, 4, 5, 6)
                .map(n -> n * 10)
                .spliterator();

        Spliterator<Integer> prefix = remaining.trySplit();
        StringJoiner output = new StringJoiner(" ");

        if (prefix != null) {
            prefix.forEachRemaining(n -> output.add(String.valueOf(n)));
        }
        remaining.forEachRemaining(n -> output.add(String.valueOf(n)));
        System.out.println(output);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ManualTraversalDemo.java
java ManualTraversalDemo
```

**Stdout chính xác:**

```text
Lan
Minh
10 20 30 40 50 60
```

Trong `iteratorExample`, `map(String::trim)` và `filter` vẫn được áp dụng; vòng lặp chỉ **in** đến `Minh` rồi dừng. Đừng kết luận rằng phần tử `An` chắc chắn chưa được chạm tới: cách triển khai có thể đọc trước khi kiểm tra `hasNext()`. Nếu điều kiện dừng chỉ phụ thuộc giá trị, `findFirst`, `anyMatch` hoặc `takeWhile` thường diễn đạt ý định rõ hơn.

### Khi nào cần vòng lặp bên ngoài Stream?

Ví dụ: giao một phần tử mỗi lần cho giao thức yêu cầu–đáp ứng; tạm dừng giữa các bước; kết hợp một iterator vào thư viện chỉ chấp nhận `Iterator`; hoặc kết thúc khi tín hiệu bên ngoài thay đổi. Nếu logic thuần túy là “lấy 10 phần tử đầu”, sử dụng `limit(10)` sẽ đơn giản hơn và dễ tối ưu hơn.

## 3. Duyệt bằng `Spliterator<T>`

`Spliterator` là bộ duyệt có thể **traverse** và **partition**; nó không tự tạo thread. Một số thao tác quan trọng:

- `boolean tryAdvance(Consumer<? super T>)`: nếu còn phần tử, chuyển **tối đa một** phần tử cho callback và trả `true`; nếu không còn thì trả `false` mà không gọi callback.
- `void forEachRemaining(Consumer<? super T>)`: lần lượt chuyển tất cả phần tử còn lại cho callback trong thread gọi; không dùng khi cần dừng chủ động giữa chừng.
- `Spliterator<T> trySplit()`: thử tách một phần công việc thành spliterator **mới**, hoặc trả `null` nếu không chia được. Phần được tách **không còn nằm trong** spliterator ban đầu. Với spliterator mang cờ `ORDERED`, phần mới là **tiền tố** theo encounter order. Kích thước mỗi nhánh không được cố định.
- `estimateSize()`: số phần tử **ước lượng còn lại**; có thể là `Long.MAX_VALUE` khi không biết hoặc quá tốn để tính. `getExactSizeIfKnown()` trả số chính xác khi có cờ `SIZED`, còn không trả `-1`.
- `characteristics()` và `hasCharacteristics(flags)`: kiểm tra các đặc tính mà **chính spliterator đó công bố**, thay vì suy đoán từ kiểu nguồn.

### Ví dụ điều khiển từng bước với `tryAdvance`

```java
import java.util.Spliterator;
import java.util.stream.Stream;

public class AdvanceDemo {
    public static void main(String[] args) {
        Spliterator<Integer> cursor = Stream.of(12, 24, 36).spliterator();
        int consumed = 0;

        while (consumed < 2) {
            if (!cursor.tryAdvance(System.out::println)) {
                break;
            }
            consumed++;
        }
    }
}
```

Chạy `javac --release 17 AdvanceDemo.java` rồi `java AdvanceDemo`, kết quả:

```text
12
24
```

Phần tử `36` chưa được giao cho callback và có thể được duyệt tiếp bằng chính `cursor`, miễn không phát sinh lỗi hoặc vi phạm điều kiện sử dụng nguồn. Trong ví dụ `ManualTraversalDemo`, nếu `trySplit()` trả một tiền tố, chương trình xử lý **tiền tố trước, phần còn lại sau**, nhờ vậy thứ tự in là xác định. Không được dự đoán số phần tử trong tiền tố hoặc giả định lần nào `trySplit()` cũng thành công.

### Cách hiểu tám đặc tính thường gặp

| Cờ `Spliterator` | Ý nghĩa thực tế |
| --- | --- |
| `ORDERED` | Có encounter order; `tryAdvance` tuân theo thứ tự, `trySplit` tách tiền tố. |
| `DISTINCT` | Không có hai phần tử bằng nhau theo `equals` trong tập phần tử được duyệt. |
| `SORTED` | Phần tử theo thứ tự sắp xếp; `getComparator()` chỉ hợp lệ khi có `SORTED`. |
| `SIZED` | Ước lượng kích thước là chính xác theo điều kiện của hợp đồng API. |
| `SUBSIZED` | Các nhánh tạo từ `trySplit` cũng có `SIZED` và `SUBSIZED`; cờ này hàm ý `SIZED`. |
| `NONNULL` | Bảo đảm không có phần tử `null`. |
| `IMMUTABLE` | Nguồn được bảo đảm không bị thay đổi cấu trúc trong khi duyệt theo hợp đồng của spliterator. |
| `CONCURRENT` | Nguồn có chính sách cho phép sửa đổi đồng thời khi duyệt; **không** biến callback hay bộ tích lũy thành thread-safe. |

Ví dụ kiểm tra cờ, không phụ thuộc vào một tập cờ cụ thể:

```java
import java.util.List;
import java.util.Spliterator;

public class CharacteristicsDemo {
    public static void main(String[] args) {
        Spliterator<String> source = List.of("A", "B", "C").spliterator();

        if (source.hasCharacteristics(Spliterator.ORDERED)) {
            System.out.println("Có thứ tự duyệt");
        }
        System.out.println("Kích thước chính xác nếu biết: "
                + source.getExactSizeIfKnown());
    }
}
```

Với `List.of("A", "B", "C")` trên JDK 17+, stdout:

```text
Có thứ tự duyệt
Kích thước chính xác nếu biết: 3
```

Một nguồn có kích thước xác định **không có nghĩa mọi pipeline từ nguồn đó vẫn mang `SIZED`**: ví dụ `filter` khiến số phần tử cuối cùng có thể không xác định trước. Cờ chỉ là bảo đảm khi được công bố; sự **vắng mặt** của cờ không chứng minh dữ liệu chắc chắn thiếu tính chất ấy.

## 4. `trySplit()` và xử lý song song: điều gì được bảo đảm?

Giả sử dữ liệu có thứ tự `[10, 20, 30, 40, 50, 60]`. Khi gọi `trySplit()` trên một spliterator `ORDERED`, nhánh được trả về phải phủ **một tiền tố** và nhánh cũ phủ phần còn lại. Tuy nhiên, có thể tách 1–5 phần tử hoặc không tách được; kích thước phụ thuộc loại nguồn, trạng thái duyệt và triển khai.

- Gọi `trySplit()` **trước khi bắt đầu duyệt**, rồi giao mỗi nhánh cho một tác vụ độc lập, là chiến lược điển hình. Chia quá nhỏ tăng overhead; chia quá lệch làm giảm khả năng cân tải.
- Không cho hai thread đồng thời gọi `tryAdvance`/`trySplit` trên **cùng một instance** nếu không có phối hợp đồng bộ thích hợp; đa số spliterator không được thiết kế cho cách dùng đó.
- Nếu các nhánh ghi vào cùng `ArrayList`/`StringBuilder` hoặc biến đếm không đồng bộ thì vẫn có data race. Giải pháp phải có phân vùng kết quả, cơ chế kết hợp hoặc cấu trúc dữ liệu an toàn.
- `stream.parallel().iterator()` hay `stream.parallel().spliterator()` **không tự biến vòng lặp bên ngoài thành nhiều thread**. Việc lặp/chia và điều phối sau khi trả bộ duyệt là trách nhiệm của mã gọi; với nghiệp vụ song song thông thường, hãy để Stream xử lý bằng `parallelStream()`/`parallel()` và terminal operation thích hợp, sau khi đo đạc hiệu năng.
- Không sửa collection nguồn trong khi duyệt pipeline, trừ khi loại nguồn và hợp đồng API cho phép rõ ràng. Kể cả với nguồn concurrent, hành vi nhìn thấy các thay đổi phải dựa vào bảo đảm cụ thể của collection.

Trong các thuật toán cần encounter order, kết quả của các nhánh song song phải được **ghép đúng thứ tự**; việc cùng in ra console từ nhiều thread không bảo đảm thứ tự in.

## 5. So sánh với các terminal operation và intermediate operation phù hợp hơn

Khi mục tiêu là dừng theo dữ liệu, thường không cần thao tác con trỏ bằng tay:

| Mục tiêu | Diễn đạt bằng Stream | Ghi chú |
| --- | --- | --- |
| Lấy phần tử đầu thỏa điều kiện | `filter(...).findFirst()` | Trả `Optional`; với nguồn có thứ tự, giữ semantics phần tử đầu. |
| Kiểm tra tồn tại | `anyMatch(...)` | Short-circuit, có thể dừng khi tìm thấy. |
| Giới hạn N kết quả | `limit(n)` | Intermediate operation, đi kèm terminal operation. |
| Lấy tới trước phần tử không đạt điều kiện | `takeWhile(predicate)` | Có từ **Java 9**; trên stream có thứ tự, lấy tiền tố liên tiếp thỏa điều kiện. |
| Bỏ một tiền tố thỏa điều kiện | `dropWhile(predicate)` | Có từ **Java 9**. |
| Duyệt toàn bộ với side effect | `forEach(...)` hoặc `forEachOrdered(...)` | Trong parallel stream, `forEach` không hứa giữ thứ tự; `forEachOrdered` bảo đảm encounter order khi có. |
| Tạo danh sách | `toList()` | Có từ **Java 16**, danh sách trả về không sửa được; khi cần list mutable, chọn collector hoặc tự tạo loại list phù hợp. |
| Tìm/tổng hợp số liệu | `count()`, `reduce()`, `sum()`, `collect()` | Để Stream quản lý vòng duyệt. |

Ví dụ thay vòng lặp tìm phần tử:

```java
import java.util.Optional;
import java.util.stream.Stream;

public class FindDemo {
    public static void main(String[] args) {
        Optional<String> found = Stream.of("An", "Bình", "Minh")
                .filter(name -> name.startsWith("M"))
                .findFirst();
        System.out.println(found.orElse("không tìm thấy"));
    }
}
```

Stdout khi chạy với Java 17+:

```text
Minh
```

`findFirst()` diễn đạt việc tìm kết quả; `iterator()` phù hợp hơn nếu chương trình cần phản hồi hoặc tạm dừng **sau từng phần tử** theo trạng thái bên ngoài. Với `Stream` có nguồn vô hạn, tránh `forEachRemaining()` nếu không có điều kiện dừng hữu hạn; có thể dùng `limit()` hoặc kiểm soát bằng `tryAdvance()`.

## 6. Quản lý tài nguyên khi duyệt chưa hết

Phần lớn stream từ collection không sở hữu tài nguyên cần đóng. Stream tạo từ file hoặc I/O thì **có thể sở hữu tài nguyên**; ví dụ `Files.lines(...)` mở tài nguyên đọc file. Việc thoát vòng lặp, hết iterator hay trả về từ `tryAdvance` **không tự bảo đảm stream được đóng**. Luôn đặt stream I/O trong `try-with-resources`.

Mẫu sau là **đoạn trích trong một phương thức**, cần có file thật để chạy:

```java
Path path = Path.of("app.log");
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    Iterator<String> errors = lines
            .filter(line -> line.contains("ERROR"))
            .iterator();

    int shown = 0;
    while (shown < 3 && errors.hasNext()) {
        System.out.println(errors.next());
        shown++;
    }
} // close() được gọi cả khi dừng sau 3 dòng hoặc có ngoại lệ
```

Các import tương ứng: `java.nio.file.Path`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`, `java.util.Iterator`, `java.util.stream.Stream`; phương thức cần xử lý/khai báo `IOException`. Cần phân biệt `Stream.close()` với `Iterator`: iterator thường không có `close()`. Một số lỗi I/O phát sinh khi duyệt có thể được bọc trong `UncheckedIOException`.

## 7. Chuyển đổi giữa Iterator, Spliterator và Stream

`StreamSupport` giúp xây stream từ spliterator khi phải nối với API cấp thấp:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class AdapterDemo {
    public static void main(String[] args) {
        Iterator<Integer> source = List.of(2, 4, 6).iterator();
        Spliterator<Integer> cursor =
                Spliterators.spliteratorUnknownSize(source, Spliterator.ORDERED);
        Stream<Integer> stream = StreamSupport.stream(cursor, false);
        System.out.println(stream.mapToInt(Integer::intValue).sum());
    }
}
```

Kết quả:

```text
12
```

`spliteratorUnknownSize` báo không biết kích thước từ trước, nên đừng khai `SIZED`/`SUBSIZED` khi không thể bảo đảm. Tham số thứ hai của `StreamSupport.stream(cursor, false)` là lựa chọn **sequential**; truyền `true` chỉ bật chế độ stream parallel, không bảo đảm ứng dụng nhanh hơn. Đây là kỹ thuật tích hợp API, còn trường hợp sẵn `Collection` thì gọi `collection.stream()` đơn giản hơn.

## 8. Các lỗi thực tế và cách tránh

1. **Tái dùng cùng stream:** `Stream<T> s = ...; s.iterator(); s.count();` là không hợp lệ. Tạo stream mới từ nguồn khi cần lượt thứ hai.
2. **Cho rằng `iterator()` duyệt hết ngay:** việc tính toán các bước lazy phần lớn diễn ra khi bộ duyệt được yêu cầu phần tử. Không dựa vào số lần `peek`/`map` được gọi như một công cụ đếm side effect.
3. **Giả định `hasNext()` không có side effect:** một số pipeline phải tìm trước phần tử hợp lệ; vì vậy side effect trong `filter`/`map` là thiết kế dễ gây bất ngờ.
4. **Gọi `next()` khi hết:** kiểm tra `hasNext()`; hiểu `NoSuchElementException`.
5. **Nhầm `trySplit()` với tạo luồng:** tách dữ liệu không tự tạo thread; hai nhánh cũng không được phép trùng phần tử theo hợp đồng.
6. **Tưởng `SIZED`/`ORDERED` luôn tồn tại:** kiểm tra `hasCharacteristics`, nhất là sau các thao tác trung gian và với nguồn không có encounter order.
7. **Dùng `forEachRemaining` khi cần dừng giữa chừng:** chọn vòng `while` hoặc `tryAdvance`. Không dùng ngoại lệ như một lệnh `break`; nếu callback ném ngoại lệ, trạng thái spliterator về sau có thể không được xác định.
8. **Không đóng stream đọc file khi break:** giữ đối tượng `Stream` trong phạm vi `try-with-resources`.
9. **Sửa nguồn hoặc chia sẻ bộ duyệt bừa bãi giữa thread:** có thể gây kết quả khó dự đoán, `ConcurrentModificationException` hoặc data race tùy nguồn/triển khai. Không dựa vào fail-fast như cơ chế đồng bộ.
10. **Tự viết cơ chế chia song song cho việc thường ngày:** tăng độ phức tạp, tốn chi phí lập lịch và khó giữ thứ tự. Chỉ dùng ở mức thấp khi có yêu cầu điều phối thực sự và có benchmark.

## 9. Tự kiểm tra kiến thức

- Khi gọi `Stream.of(1, 2, 3).filter(n -> n > 1).iterator()`, lời gọi nào bắt đầu yêu cầu các phần tử đi qua pipeline? Vì sao `hasNext()` có thể làm nhiều việc hơn một lần kiểm tra?
- Một `Spliterator` `ORDERED` tách thành hai nhánh: thứ tự nào bảo đảm khi xử lý nhánh tách trước rồi nhánh còn lại? Có thể đoán chính xác tỷ lệ chia không?
- Tại sao `Files.lines` kết hợp `iterator()` và `break` vẫn cần `try-with-resources`?
- Nếu chỉ cần tìm phần tử đầu tiên thỏa điều kiện, sẽ chọn `findFirst` hay vòng `Iterator`? Khi nào yêu cầu tương tác từng bước khiến lựa chọn thay đổi?

**Ghi nhớ:** `iterator()` và `spliterator()` kết thúc **quyền xây pipeline** nhưng mở ra **quyền điều khiển cách duyệt** cho caller. `Iterator` phục vụ duyệt tuần tự có điểm dừng; `Spliterator` thêm điều khiển từng bước, thông tin đặc tính và khả năng chia. Hãy để Stream thực hiện terminal operation cấp cao khi không thực sự cần quyền điều khiển này.

## Tham khảo API chính thức

- Stream và hành vi terminal/lazy: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- `BaseStream.iterator()` và `BaseStream.spliterator()`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/BaseStream.html
- `Iterator`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html
- `Spliterator` (traverse, split, characteristics): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html
- `StreamSupport`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/StreamSupport.html
