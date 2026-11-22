# Thiết kế Spliterator từ Iterator với kích thước biết trước hoặc chưa biết

Trong chương **Spliterator và nguồn tự định nghĩa** của **Java Stream API**, không phải nguồn dữ liệu nào cũng đã cung cấp `Stream` hoặc `Spliterator`. Một thư viện cũ có thể chỉ trả về `Iterator<T>`; một hệ thống phân trang có thể lấy phần tử lần lượt; một bộ đọc tệp có thể cung cấp từng bản ghi nhưng không biết trước tổng số bản ghi. Muốn kết hợp các nguồn này với `filter`, `map`, `reduce`, `collect` hoặc xử lý song song, ta có thể **bọc Iterator thành Spliterator** rồi dùng `StreamSupport.stream(...)`.

Lựa chọn quan trọng nhất là: **có biết chính xác số phần tử còn lại hay không?**

- **Biết chính xác**: dùng `Spliterators.spliterator(iterator, size, characteristics)`.
- **Chưa biết chính xác**: dùng `Spliterators.spliteratorUnknownSize(iterator, characteristics)`.

Hai factory giống nhau về mục tiêu chuyển đổi nhưng có hợp đồng khác nhau về **kích thước, đặc tính `SIZED`/`SUBSIZED` và khả năng tối ưu**. Bài này giải thích cách chọn factory, khai báo characteristics trung thực, hiểu `tryAdvance`/`trySplit` và tránh lỗi về số lượng, thứ tự, tài nguyên hoặc trạng thái của Iterator.

**Phiên bản Java:** `Spliterators`, `Spliterator` và `StreamSupport` có từ Java 8. Một số ví dụ dùng `List.of(...)` (Java 9+), `Path.of(...)` (Java 11+) và `Stream.toList()` (Java 16+). Nếu học trên Java 8, có thể thay bằng `Arrays.asList(...)`, `Paths.get(...)` và `collect(Collectors.toList())` tương ứng; với lớp vô danh `new Iterator<>()`, Java 8 cần viết đầy đủ kiểu như `new Iterator<Integer>()`.

## 1. Iterator và Spliterator khác nhau như thế nào?

`Iterator<T>` cung cấp một giao diện duyệt tuần tự cơ bản:

~~~java
import java.util.Iterator;

Iterator<String> iterator = source.iterator();

while (iterator.hasNext()) {
    String value = iterator.next();
    // Xử lý một phần tử.
}
~~~

Hai phương thức `hasNext()` và `next()` giúp lấy lần lượt các phần tử. Tuy nhiên, `Iterator` không có phương thức chuẩn để công bố tổng số phần tử còn lại, chia nguồn thành phần con hoặc mô tả các đặc tính như `DISTINCT` hay `ORDERED`.

`Spliterator<T>` mở rộng mô hình duyệt theo cách phù hợp hơn với Stream API:

| Khả năng | `Iterator<T>` | `Spliterator<T>` |
| --- | --- | --- |
| Yêu cầu một phần tử | `hasNext()` rồi `next()` | `tryAdvance(Consumer)` |
| Duyệt những phần tử còn lại | `forEachRemaining(Consumer)` | `forEachRemaining(Consumer)` |
| Ước lượng số phần tử còn lại | Không có API chung | `estimateSize()` |
| Khai báo kích thước chính xác | Không có API chung | Characteristic `SIZED` |
| Chia phần việc | Không có API chung | `trySplit()` |
| Khai báo thứ tự / tính chất nguồn | Không có API chung | `characteristics()`, `hasCharacteristics(...)` |

Ví dụ gọi một `Spliterator`:

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> split = List.of("A", "B", "C").spliterator();

split.tryAdvance(System.out::println);       // In A, trả true.
split.forEachRemaining(System.out::println);  // In B rồi C.
~~~

Cả Iterator và Spliterator đều là công cụ **duyệt tiến**, không tự động quay lại đầu nguồn sau khi đã tiêu thụ. `Spliterator` cũng không biến một nguồn chỉ đọc tuần tự thành nguồn chia nhỏ hiệu quả chỉ vì có phương thức `trySplit()`.

## 2. Hai factory từ Iterator cần phân biệt

Lớp tiện ích `java.util.Spliterators` cung cấp hai phương thức dùng trực tiếp với `Iterator`:

~~~java
// Biết chính xác số phần tử còn lại:
static <T> Spliterator<T> spliterator(
        Iterator<? extends T> iterator,
        long size,
        int characteristics);

// Không biết chính xác số phần tử còn lại:
static <T> Spliterator<T> spliteratorUnknownSize(
        Iterator<? extends T> iterator,
        int characteristics);
~~~

Sau khi có `Spliterator<T>`, tạo Stream bằng:

~~~java
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

Stream<T> stream = StreamSupport.stream(spliterator, false);
~~~

`false` yêu cầu pipeline tuần tự; `true` yêu cầu chế độ song song. Ở đây `T` là kiểu phần tử thực tế của nguồn; các đoạn mã minh họa chữ ký tổng quát, còn ví dụ đầy đủ bên dưới sẽ dùng `String` và `Integer` cụ thể.

### Bảng so sánh

| Tiêu chí | `spliterator(iterator, size, flags)` | `spliteratorUnknownSize(iterator, flags)` |
| --- | --- | --- |
| Thông tin độ dài | Caller cung cấp **số phần tử còn lại chính xác** | Không cần thông tin độ dài |
| `estimateSize()` ban đầu | Dựa trên `size` đã cung cấp | Dùng giá trị ước lượng không xác định, thường là `Long.MAX_VALUE` |
| `SIZED` / `SUBSIZED` | Được bổ sung theo hợp đồng của factory, trừ trường hợp công bố `CONCURRENT` | Không công bố `SIZED` hay `SUBSIZED` |
| Có thể dùng với nguồn hữu hạn | Có, nếu biết số lượng chính xác | Có, kể cả nguồn hữu hạn |
| Có thể dùng với nguồn không giới hạn | Không phù hợp nếu không có số lượng hữu hạn chính xác | Có thể bọc, nhưng terminal operation cần điểm dừng |
| Khả năng chia việc | Có thể tách theo lô bằng cách đọc Iterator vào mảng | Cũng có thể tách theo lô, không cần biết trước tổng số |
| Rủi ro chính | Cung cấp `size` sai làm vi phạm hợp đồng nguồn | Không có tối ưu dựa trên kích thước chính xác |

**Không biết kích thước ≠ nguồn vô hạn.** Một Iterator có thể kết thúc sau năm phần tử nhưng không có phương thức nào cho biết con số năm từ trước. Đây chính là trường hợp nên dùng `spliteratorUnknownSize`.

## 3. Trường hợp 1: biết chính xác kích thước

Giả sử có một Iterator và metadata độc lập xác nhận số phần tử còn lại. Ví dụ đơn giản nhất là Iterator vừa tạo từ một danh sách không bị sửa trong lúc xử lý.

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class KnownSizeIteratorDemo {
    public static void main(String[] args) {
        List<String> events = List.of(
                "INFO started",
                "ERROR timeout",
                "WARN slow",
                "ERROR denied"
        );

        Iterator<String> iterator = events.iterator();
        long remaining = events.size(); // Đúng tại thời điểm tạo Iterator.

        Spliterator<String> split = Spliterators.spliterator(
                iterator,
                remaining,
                Spliterator.ORDERED | Spliterator.NONNULL
        );

        System.out.println(split.hasCharacteristics(Spliterator.SIZED));
        // true

        System.out.println(split.hasCharacteristics(Spliterator.SUBSIZED));
        // true

        System.out.println(split.getExactSizeIfKnown()); // 4

        List<String> errors = StreamSupport.stream(split, false)
                .filter(line -> line.startsWith("ERROR"))
                .toList();

        System.out.println(errors);
        // [ERROR timeout, ERROR denied]
    }
}
~~~

Giải thích từng đối số của factory:

1. `iterator` là **nguồn duyệt**, sẽ được tiêu thụ khi Spliterator hoặc Stream cần phần tử.
2. `remaining = 4` là **số phần tử còn lại**, không phải dung lượng vùng chứa hay số lượng từng được sinh ra.
3. `Spliterator.ORDERED` khẳng định nguồn có *encounter order* theo danh sách.
4. `Spliterator.NONNULL` phù hợp vì `List.of(...)` không chứa `null`.
5. Factory biết kích thước thông thường công bố `SIZED` và `SUBSIZED`, giúp downstream có thêm thông tin để lập kế hoạch xử lý.

Đây là ví dụ để hiểu factory; trong chương trình thực tế, nếu đã có `List` thì thường dùng `events.stream()` hoặc `events.spliterator()` sẽ trực tiếp và tự nhiên hơn. Cách bọc Iterator có giá trị khi nguồn chỉ cung cấp API Iterator.

### Kích thước phải là số phần tử **còn lại**

Giả sử danh sách có năm phần tử nhưng Iterator đã trả hai phần tử:

~~~java
List<Integer> values = List.of(10, 20, 30, 40, 50);
Iterator<Integer> it = values.iterator();

it.next(); // Đã lấy 10.
it.next(); // Đã lấy 20.

// Iterator lúc này chỉ còn 30, 40, 50.
Spliterator<Integer> rest = Spliterators.spliterator(
        it,
        3L,
        Spliterator.ORDERED | Spliterator.NONNULL
);
~~~

Truyền `5L` vào factory tại thời điểm này là **khai báo sai**. Nếu không còn biết chính xác số phần tử chưa duyệt, dùng `spliteratorUnknownSize` an toàn hơn việc đoán.

> **Quy tắc:** “Biết trước kích thước” chỉ đúng khi con số cung cấp phản ánh chính xác phần tử còn lại theo hợp đồng nguồn, không phải một dự đoán hoặc thông tin đã hết hiệu lực.

## 4. Vì sao báo kích thước sai lại nguy hiểm?

Một `Spliterator` có `SIZED` cam kết kích thước theo hợp đồng API; Stream có quyền dùng thông tin này cho tối ưu hóa.

Ví dụ **không nên dùng**:

~~~java
// Sai: Iterator thực sự chỉ có ba phần tử.
Iterator<Integer> it = List.of(1, 2, 3).iterator();

Spliterator<Integer> wrong = Spliterators.spliterator(
        it,
        100L, // Không đúng số phần tử còn lại.
        Spliterator.ORDERED
);
~~~

Nếu tạo Stream từ `wrong` và gọi `count()`, một số triển khai/phiên bản JDK có thể dựa trên thông tin `SIZED` thay vì duyệt từng phần tử, nên kết quả hoặc hành vi có thể không đúng với nguồn thực tế. Khi kết hợp `limit`, `skip`, xử lý song song hoặc phép thu thập dùng mảng, một kích thước sai cũng có thể làm các giả định nội bộ không còn hợp lệ.

Không cần khẳng định phương thức nào *chắc chắn* trả sai trên mọi JDK để thấy vấn đề: **bản thân đặc tả của Spliterator đã bị vi phạm**.

Các tình huống dễ đưa ra số lượng sai:

- Dùng kích thước ban đầu sau khi đã gọi `next()` nhiều lần.
- Nguồn có thể thêm/xóa phần tử trong lúc duyệt.
- Đọc metadata “tổng số bản ghi” nhưng Iterator chỉ trả những bản ghi vượt qua bộ lọc nội bộ.
- Số phần tử trong API phân trang là ước lượng, không phải con số cuối.
- Coi giới hạn cấp phát bộ đệm là số phần tử còn lại.

Khi chỉ biết **giới hạn trên** hoặc số lượng dự kiến, không truyền con số đó làm kích thước chính xác cho factory báo `SIZED`.

## 5. Trường hợp 2: chưa biết trước số phần tử

Giả sử một Iterator phát ra các số lẻ cho đến khi hết dữ liệu. Người sử dụng Iterator không cần biết trước tổng số để bắt đầu duyệt.

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class UnknownSizeIteratorDemo {
    public static void main(String[] args) {
        Iterator<Integer> odds = new Iterator<>() {
            private int current = 1;

            @Override
            public boolean hasNext() {
                return current <= 9;
            }

            @Override
            public Integer next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                int value = current;
                current += 2;
                return value;
            }
        };

        Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
                odds,
                Spliterator.ORDERED | Spliterator.NONNULL
        );

        System.out.println(split.hasCharacteristics(Spliterator.SIZED));
        // false

        System.out.println(split.getExactSizeIfKnown());
        // -1

        List<Integer> result = StreamSupport.stream(split, false).toList();

        System.out.println(result); // [1, 3, 5, 7, 9]
    }
}
~~~

Factory không cần `size`. Dù nguồn ví dụ thực sự dừng sau **năm** phần tử, Spliterator **không công bố số lượng chính xác từ trước**. Stream vẫn tiêu thụ từng phần tử cho tới khi Iterator báo `hasNext() == false`.

Nếu nguồn có thể bị chặn khi tìm phần tử kế tiếp, `spliteratorUnknownSize` không tự tạo timeout hay giới hạn lượt đọc. Tương tự, nếu Iterator thực sự vô hạn, `collect` hoặc `toList` không thể kết thúc bằng cách duyệt đến hết. Cần thêm điều kiện dừng hữu hạn như `limit(n)` khi bài toán cho phép.

### Không gắn SIZED cho nguồn không biết kích thước

~~~java
Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        odds,
        Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED
);
~~~

Factory `spliteratorUnknownSize` loại bỏ các cờ `SIZED` và `SUBSIZED` mà caller có thể truyền vào. Việc truyền hai cờ này không biến nguồn thành nguồn biết trước kích thước.

Cách viết rõ ràng hơn:

~~~java
Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        odds,
        Spliterator.ORDERED | Spliterator.NONNULL
);
~~~

Hãy chỉ công bố các đặc tính thật sự được nguồn bảo đảm.

## 6. SIZED, SUBSIZED và estimateSize khác nhau ra sao?

`SIZED` và `SUBSIZED` là **characteristics**, còn `estimateSize()` là một phương thức trên `Spliterator`.

| Khái niệm | Ý nghĩa |
| --- | --- |
| `estimateSize()` | Ước lượng số phần tử còn lại; có thể là giá trị gần đúng hoặc `Long.MAX_VALUE` nếu không biết/không có giới hạn hữu hạn được biết. |
| `SIZED` | Công bố rằng ước lượng kích thước là chính xác theo hợp đồng khi không có biến đổi cấu trúc nguồn. |
| `SUBSIZED` | Công bố rằng Spliterator này và mọi Spliterator do nó phân tách cũng có `SIZED`. |
| `getExactSizeIfKnown()` | Trả kích thước nếu Spliterator có `SIZED`; nếu không, trả `-1`. |

Đối với factory bọc Iterator **biết chính xác kích thước**, `SIZED` và `SUBSIZED` thường được thêm tự động, ngoại trừ trường hợp `CONCURRENT` được cung cấp theo hợp đồng factory. Đối với factory **không biết kích thước**, các cờ `SIZED`/`SUBSIZED` không được công bố.

Với Spliterator không biết kích thước, giá trị `Long.MAX_VALUE` thường đóng vai trò *sentinel* cho kích thước chưa xác định, **không phải bằng chứng rằng nguồn thực sự có 9,22 × 10¹⁸ phần tử** hoặc vô hạn.

~~~java
Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        List.of(1, 2, 3).iterator(),
        Spliterator.ORDERED
);

System.out.println(split.estimateSize() == Long.MAX_VALUE); // true
System.out.println(split.getExactSizeIfKnown());             // -1
~~~

Ở ví dụ trên Iterator chỉ có ba phần tử. `estimateSize()` chưa xác định bởi vì factory không nhận được kích thước, chứ không phải vì nguồn không bao giờ kết thúc.

Không nên đặt logic nghiệp vụ như “chọn mảng có đúng `estimateSize()` phần tử” khi `SIZED` không tồn tại. Với nguồn lớn, ngay cả `SIZED` cũng cần xét giới hạn kích thước mảng và bộ nhớ trước khi vật hóa toàn bộ Stream.

## 7. Chọn characteristics trung thực

Đối số `characteristics` là tổ hợp cờ bit, ví dụ `Spliterator.ORDERED | Spliterator.NONNULL`. Không nên thêm càng nhiều cờ càng tốt; **mỗi cờ là một lời cam kết của nguồn**.

| Characteristic | Chỉ khai báo khi | Lưu ý |
| --- | --- | --- |
| `ORDERED` | Nguồn có encounter order được định nghĩa | Iterator từ `List` có thứ tự; Iterator từ `HashSet` không có thứ tự duyệt được cam kết. |
| `NONNULL` | Không phần tử nào là `null` | Nếu có thể có `null`, bỏ cờ này. |
| `DISTINCT` | Không có hai phần tử trùng nhau theo quy tắc bằng nhau của nguồn | Không gắn cho log sự kiện có thể lặp giá trị. |
| `IMMUTABLE` | Nguồn không thể bị sửa cấu trúc trong quá trình duyệt theo hợp đồng | Không đồng nghĩa với “caller hứa sẽ không sửa” nếu bản thân nguồn mutable và không có bảo đảm phù hợp. |
| `CONCURRENT` | Nguồn được thiết kế để chấp nhận thay đổi đồng thời trong lúc duyệt | Không dùng chỉ vì Stream sẽ chạy `parallel()`. |
| `SORTED` | Nguồn có thứ tự sắp xếp theo hợp đồng của Spliterator | Cần tương thích với `getComparator()`; không gắn chỉ vì dữ liệu trông có vẻ đã sắp xếp. |
| `SIZED` | Có số phần tử còn lại chính xác | Factory biết kích thước xử lý cờ này theo hợp đồng; đừng tự gắn cho số ước lượng. |
| `SUBSIZED` | Mọi phần được tách cũng báo kích thước chính xác | Không được suy diễn nếu nguồn phân tách tùy ý, không giữ kích thước chính xác. |

Ví dụ một nguồn mã sự kiện có thứ tự, có thể chứa `null` và có bản ghi lặp:

~~~java
int characteristics = Spliterator.ORDERED;
// Không khai báo NONNULL, DISTINCT hay SORTED nếu không thể bảo đảm.
~~~

Nếu có thể bảo đảm từng phần tử không bao giờ `null`:

~~~java
int characteristics = Spliterator.ORDERED | Spliterator.NONNULL;
~~~

### Lưu ý với nguồn có thể thay đổi

Spliterator được bọc từ một `Iterator` kế thừa các hạn chế của Iterator đó. Nếu collection nguồn bị sửa trong khi Stream đang duyệt, hành vi phụ thuộc hợp đồng collection/iterator: có thể có `ConcurrentModificationException`, có thể quan sát dữ liệu yếu nhất quán hoặc có kết quả không được bảo đảm.

**Không có “phép màu” về thread safety khi dùng `Spliterators`.** Chỉ khai báo `CONCURRENT` nếu nguồn thực sự bảo đảm semantics đó. Khi dùng nguồn thông thường, tránh sửa collection trong khi duyệt và tránh nhiều luồng truy cập trực tiếp cùng Iterator.

## 8. tryAdvance: cầu nối từ Iterator sang cơ chế kéo phần tử

`Spliterator.tryAdvance(action)` gọi `action` cho một phần tử tiếp theo nếu có, rồi trả về `true`; nếu hết dữ liệu, trả về `false`.

~~~java
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

List<Integer> values = List.of(10, 20, 30);

Spliterator<Integer> split = Spliterators.spliterator(
        values.iterator(),
        values.size(),
        Spliterator.ORDERED | Spliterator.NONNULL
);

boolean firstFound = split.tryAdvance(System.out::println);
// In 10, firstFound == true.

split.forEachRemaining(System.out::println);
// In 20 và 30.

boolean more = split.tryAdvance(System.out::println);
// false
~~~

`tryAdvance` không tự tạo một phần tử mới; nó lấy tiếp phần tử từ Iterator được bọc. Khi đã gọi một hoặc nhiều lần, Iterator **đã bị tiêu thụ** tương ứng. Nếu sau đó tạo Stream từ cùng Spliterator, Stream chỉ còn nhận phần chưa duyệt, không thể “chạy lại” từ đầu.

Lý do Stream API dựa trên cơ chế kéo phần tử là để các terminal operation có thể yêu cầu dữ liệu khi cần và dừng ở điều kiện thích hợp, ví dụ `findFirst` hoặc `limit`. Tuy vậy, một số thao tác có trạng thái như `sorted` vẫn có thể cần xem nhiều phần tử trước khi xuất kết quả.

## 9. trySplit: chia việc theo lô chứ không đảo ngược Iterator

`trySplit()` cố tách một phần dữ liệu thành Spliterator mới để xử lý độc lập. Phương thức có thể trả về `null` khi không thể hoặc không đáng tách.

Các factory bọc Iterator thường phải **đọc lần lượt một lô phần tử từ Iterator và đặt chúng vào mảng** để tạo phần có thể tách. Vì Iterator không có truy cập ngẫu nhiên, việc chia này không tương đương với thao tác chia dãy theo chỉ số.

~~~text
Iterator gốc:
  A -> B -> C -> D -> E -> F -> ...

trySplit():
  Đọc một lô từ Iterator vào mảng: [A, B, C]
  Trả Spliterator tách cho lô [A, B, C]
  Spliterator gốc giữ phần chưa đọc: D -> E -> F -> ...
~~~

Số phần tử mỗi lô và cách chia thật sự do triển khai quyết định; sơ đồ trên chỉ minh họa. Không nên viết mã nghiệp vụ phụ thuộc vào kích thước hoặc số lần `trySplit()`.

~~~java
Spliterator<Integer> original = Spliterators.spliterator(
        List.of(1, 2, 3, 4, 5, 6).iterator(),
        6,
        Spliterator.ORDERED | Spliterator.NONNULL
);

Spliterator<Integer> prefix = original.trySplit();

if (prefix != null) {
    prefix.forEachRemaining(System.out::println);
}
original.forEachRemaining(System.out::println);
~~~

Nếu Spliterator có encounter order, phần trả về từ `trySplit()` là một **tiền tố** của phần dữ liệu được chia. Khi duyệt tiền tố trước phần còn lại như ví dụ, có thể tái hiện thứ tự phần tử. Tuy nhiên, `trySplit` **không bắt buộc** phải trả một phần tách trong mọi tình huống.

### Tác động tới parallel stream

~~~java
Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        sourceIterator,
        Spliterator.ORDERED
);

long sum = StreamSupport.stream(split, true)
        .mapToLong(Integer::longValue)
        .sum();
~~~

`true` yêu cầu Stream song song, nhưng **không bảo đảm tốc độ cao hơn**. Việc tách từ Iterator có thể phải đọc tuần tự để tạo lô dữ liệu, phát sinh cấp phát mảng và đồng bộ tác vụ. Nếu nguồn chủ yếu là I/O chậm hoặc phần xử lý trên mỗi phần tử rất nhẹ, chi phí này có thể lớn hơn lợi ích.

Nếu nguồn cho phép truy cập theo đoạn hoặc theo chỉ số, một Spliterator tự định nghĩa có `trySplit()` chia khoảng chỉ số có thể hiệu quả hơn. Nhưng điều đó là một bài toán thiết kế nguồn khác; không nên lạm dụng custom Spliterator khi wrapper mặc định đã đủ.

## 10. Ví dụ gần thực tế: nguồn token từ tệp không biết kích thước

Giả sử ứng dụng nhận một tệp văn bản có số token chưa xác định. `Scanner` tự triển khai `Iterator<String>` và cũng cần được đóng khi sử dụng nguồn tệp. Ta có thể bọc Scanner thành Spliterator không biết kích thước, rồi lọc token.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.StreamSupport;

public class ScannerIteratorSourceDemo {
    public static void main(String[] args) throws IOException {
        Path input = Path.of("events.txt");

        try (Scanner scanner = new Scanner(
                input, StandardCharsets.UTF_8.name())) {

            Spliterator<String> split =
                    Spliterators.spliteratorUnknownSize(
                            scanner,
                            Spliterator.ORDERED | Spliterator.NONNULL
                    );

            long errors = StreamSupport.stream(split, false)
                    .filter(token -> token.equalsIgnoreCase("ERROR"))
                    .count();

            System.out.println("Số token ERROR: " + errors);
        }
    }
}
~~~

Điều quan trọng trong ví dụ:

- `Scanner` không biết trước số token phải đọc cho tới khi duyệt hết.
- `spliteratorUnknownSize` không gán kích thước chính xác không có thật.
- `StreamSupport.stream(split, false)` cho phép dùng Stream API trên nguồn Iterator.
- `try-with-resources` đóng **Scanner sở hữu tệp** khi xử lý hoàn tất hoặc phát sinh ngoại lệ.
- `Scanner` phân tách token theo delimiter mặc định (thường là khoảng trắng); ví dụ **đếm token**, không đếm dòng. Muốn xử lý dòng, có thể dùng `Files.lines` với `try-with-resources`.

Việc đóng Stream được tạo từ một Iterator bất kỳ **không tự động đóng tài nguyên gốc** nếu không có close handler thích hợp. Ở đây Scanner được đóng riêng, vì Scanner mới là đối tượng sở hữu nguồn I/O.

Nếu nguồn là HTTP cursor hoặc database cursor, nguyên tắc cũng tương tự: phải có **quyền sở hữu vòng đời** rõ ràng; chỉ chuyển sang Spliterator không bảo đảm cursor được giải phóng.

## 11. Biết kích thước: không đồng nghĩa phải vật hóa toàn bộ dữ liệu

Việc biết trước `size` chỉ cung cấp metadata; bọc Iterator không có nghĩa là toàn bộ phần tử được đưa ngay vào List.

~~~java
Spliterator<String> split = Spliterators.spliterator(
        iterator,
        exactRemainingCount,
        Spliterator.ORDERED
);

long matches = StreamSupport.stream(split, false)
        .filter(value -> value.startsWith("A"))
        .count();
~~~

Trong ví dụ này, `iterator` phải là nguồn `Iterator<String>` và `exactRemainingCount` phải là `long` biểu diễn đúng số phần tử còn lại. Stream có thể duyệt dần các phần tử; `filter` chỉ xử lý dữ liệu khi terminal operation yêu cầu.

Tuy nhiên, nếu bật song song, `trySplit` có thể tạo **mảng đệm theo lô** để chia Iterator. Các thao tác như `sorted` hoặc `toList` cũng có thể giữ nhiều phần tử trong bộ nhớ. Không nên suy rằng “nguồn từ Iterator” bảo đảm chi phí bộ nhớ luôn hằng số.

Nếu đã có một `Collection<T>`, nên ưu tiên `collection.stream()` hoặc `collection.spliterator()`. Collection có thể cung cấp Spliterator phù hợp hơn với cấu trúc dữ liệu, tránh bước bọc lại Iterator.

## 12. Một nguồn, một lượt duyệt và quản lý trạng thái

Iterator thường là một đối tượng **có trạng thái**. Mỗi lần gọi `next()` tiến nguồn lên một bước. Spliterator bọc Iterator kế thừa tính chất đó:

~~~java
Iterator<String> it = List.of("a", "b", "c").iterator();

Spliterator<String> split = Spliterators.spliteratorUnknownSize(
        it, Spliterator.ORDERED
);

List<String> first = StreamSupport.stream(split, false).toList();
// [a, b, c]

// Không tạo Stream mới từ cùng một Spliterator đã dùng để mong đọc lại.
~~~

Bản thân Stream cũng chỉ hỗ trợ một pipeline terminal operation. Khi cần chạy hai phép tổng hợp độc lập, có thể:

1. Đọc một lần rồi thu danh sách hữu hạn, nếu đủ bộ nhớ, sau đó tạo Stream mới từ danh sách.
2. Dùng một collector kết hợp nhiều chỉ số trong cùng một lượt duyệt.
3. Nếu nguồn có thể mở lại, **tạo Iterator mới** cho lượt thứ hai và đảm bảo đóng nguồn tương ứng.

Không nên dùng một Iterator vừa để “đếm trước” vừa để “duyệt sau” nếu không thể tái tạo Iterator. Làm vậy có thể khiến Stream chỉ còn nhìn thấy phần đuôi, hoặc kích thước khai báo trở thành sai.

## 13. Những đặc tính cần xác minh khi thiết kế nguồn tự định nghĩa

Dù chỉ dùng factory có sẵn, người viết ứng dụng vẫn chịu trách nhiệm về dữ liệu đầu vào và cờ được công bố.

### 13.1. Các bất biến về Iterator

Một Iterator bình thường cần đáp ứng:

- `hasNext()` cho biết liệu `next()` có thể trả về phần tử tiếp theo hay không.
- `next()` trả một phần tử nếu còn; khi hết phải ném `NoSuchElementException`.
- Nếu hỗ trợ `remove()`, không gọi nó bừa bãi trong lúc Stream đang xử lý cùng nguồn.
- Không thay đổi nguồn từ bên ngoài theo cách vi phạm hợp đồng Iterator, nhất là trong xử lý song song.
- Nếu lấy dữ liệu từ I/O hoặc cursor, quản lý tài nguyên độc lập với quyền duyệt.

### 13.2. Các bất biến về Spliterator

Với Spliterator biết kích thước:

- `size` mô tả **đúng số phần tử còn lại tại thời điểm bọc**, theo hợp đồng của nguồn.
- `SIZED`/`SUBSIZED` phải nhất quán với cách nguồn được duyệt và chia.
- `ORDERED`, `NONNULL` và những cờ khác chỉ được khai báo nếu thật sự đúng.
- `trySplit` có thể trả `null`; code dùng Spliterator không được xem đây là lỗi.
- Việc đọc phần còn lại phải cung cấp **đúng tập phần tử cần duyệt**, không nhân đôi hay bỏ sót khi phân tách.
- Không có bảo đảm rằng Stream sẽ gọi `tryAdvance`, `trySplit` hay mapper đúng số lần mà ứng dụng mong đợi nếu những side effect đó không được đặc tả.

Với Spliterator chưa biết kích thước, các điều kiện tương tự vẫn áp dụng, chỉ khác là không được giả định có số lượng chính xác để tối ưu.

## 14. Bảng quyết định: chọn cách chuyển nguồn

| Tình huống | Cách chọn | Lý do |
| --- | --- | --- |
| Đã có `List<T>` hoặc `Collection<T>` | `collection.stream()` | Nguồn đã hỗ trợ Stream, không cần bọc Iterator. |
| API cũ chỉ trả Iterator nhưng có metadata chính xác về số phần tử còn lại | `spliterator(iterator, size, flags)` | Có thể công bố kích thước chính xác. |
| API chỉ trả Iterator, không biết trước còn bao nhiêu phần tử | `spliteratorUnknownSize(iterator, flags)` | Không tạo cam kết sai về `SIZED`. |
| Chỉ có giới hạn trên hoặc dự báo số phần tử | `spliteratorUnknownSize(iterator, flags)` | Ước lượng không phải kích thước chính xác. |
| Iterator đã bị tiêu thụ một phần nhưng chỉ có kích thước ban đầu | `spliteratorUnknownSize(...)` hoặc tính lại số còn lại chính xác | Không khai báo số cũ là `size`. |
| Cần xử lý song song hiệu quả trên nguồn có thể chia theo chỉ số | Cân nhắc Spliterator tự định nghĩa | Wrapper Iterator thường phải gom phần tử theo lô. |
| Nguồn gắn tệp, Scanner, socket hoặc cursor | Bọc phù hợp **và** quản lý AutoCloseable nguồn | `StreamSupport` không tự giải phóng tài nguyên của Iterator tùy ý. |
| Nguồn không giới hạn nhưng chỉ lấy N phần tử | `spliteratorUnknownSize(...), rồi limit(N)` | Tạo ranh giới hữu hạn cho terminal operation. |

## 15. Bẫy thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `count()` có kết quả kỳ lạ hoặc pipeline tối ưu bỏ qua phần tử | Dùng `spliterator(iterator, size, ...)` với `size` không chính xác | Chỉ truyền số còn lại chính xác; nếu không chắc, dùng `spliteratorUnknownSize`. |
| `getExactSizeIfKnown()` trả `-1` dù nguồn cuối cùng hữu hạn | Factory không được cung cấp kích thước chính xác | Đây là hành vi đúng; không cần tự gắn `SIZED`. |
| Có giá trị `Long.MAX_VALUE` ở `estimateSize()` | Kích thước chưa biết | Không coi là số phần tử thực hoặc bắt buộc vô hạn. |
| Tạo Stream xong nhưng một số phần tử biến mất | Iterator đã bị gọi `next()` trước khi tạo Spliterator | Bọc từ đúng vị trí và cập nhật số còn lại. |
| Kết quả đổi sau khi sửa collection nguồn | Vi phạm giả định ổn định nguồn hoặc semantics Iterator | Tránh sửa nguồn trong lúc duyệt; dùng snapshot khi cần. |
| Thứ tự đầu ra không đúng giả định | Khai báo `ORDERED` sai hoặc dùng nguồn unordered | Chỉ công bố thứ tự khi nguồn bảo đảm, hoặc `sorted` theo yêu cầu. |
| Dùng `parallel()` nhưng chậm hơn | Spliterator tách Iterator bằng cách đọc lô và tạo mảng | Đo hiệu năng; ưu tiên Stream trực tiếp từ Collection hoặc Spliterator chia theo chỉ số nếu cần. |
| Tệp/cursor còn mở sau khi thu kết quả | Chỉ đóng Stream bọc Iterator, không đóng nguồn I/O | Đặt resource gốc vào `try-with-resources` hoặc thiết kế close handler/ownership rõ ràng. |
| Terminal operation không hoàn tất | Iterator không kết thúc hoặc thao tác kéo phần tử bị chặn | Giới hạn đầu vào, đặt timeout/hủy ở tầng nguồn khi thích hợp. |
| Null xuất hiện dù đã gắn `NONNULL` | Cờ characteristic không đúng dữ liệu | Bỏ cờ hoặc xác thực/chuẩn hóa nguồn theo hợp đồng. |

## 16. Bài tập tự kiểm tra

### Bài 1 — Chọn đúng factory

Một API trả `Iterator<Event>`. API công bố chính xác còn 2.500 bản ghi, chưa có bản ghi nào được tiêu thụ và nguồn không bị sửa trong lúc đọc. Nên chọn factory nào?

**Đáp án:** `Spliterators.spliterator(iterator, 2_500L, characteristics)`, với characteristics chỉ gồm những đặc tính thật sự được API bảo đảm. Nếu Iterator có encounter order cố định, có thể cung cấp `Spliterator.ORDERED`. Không tự thêm `NONNULL` nếu nguồn vẫn có thể trả `null`.

### Bài 2 — Có phải Long.MAX_VALUE chứng minh vô hạn?

~~~java
var split = Spliterators.spliteratorUnknownSize(
        List.of("A", "B").iterator(), Spliterator.ORDERED
);

System.out.println(split.estimateSize());
~~~

**Đáp án:** Không. Spliterator không biết kích thước nên có thể báo `Long.MAX_VALUE`, nhưng nguồn này rõ ràng chỉ có hai phần tử. Giá trị đó mô tả **độ thiếu thông tin về kích thước**, không phải số phần tử thực.

### Bài 3 — Iterator đã đi qua một phần dữ liệu

~~~java
List<String> values = List.of("a", "b", "c", "d");
Iterator<String> iterator = values.iterator();

iterator.next();
iterator.next();
~~~

**Câu hỏi:** Nếu bọc Iterator với kích thước biết trước, cần truyền bao nhiêu?

**Đáp án:** Truyền `2L` vì chỉ còn `"c"` và `"d"`. Nếu ứng dụng không thể tính số còn lại chính xác, dùng `spliteratorUnknownSize`.

### Bài 4 — Công bố characteristics

Một Iterator đọc các ID có thể lặp, có `null` và không có thứ tự được cam kết. Có thể gắn `ORDERED | DISTINCT | NONNULL` không?

**Đáp án:** Không. Cả ba cờ đều vi phạm hợp đồng nguồn. Dùng `0` nếu không có characteristic nào khác được chứng minh. Việc một lần chạy trả dữ liệu theo thứ tự cụ thể không đủ để biến thứ tự đó thành cam kết.

### Bài 5 — Thiết kế dữ liệu theo Stream

~~~java
Iterator<Integer> iterator = List.of(1, 2, 3).iterator();

Spliterator<Integer> split = Spliterators.spliteratorUnknownSize(
        iterator, Spliterator.ORDERED | Spliterator.NONNULL
);

int sum = StreamSupport.stream(split, false)
        .mapToInt(Integer::intValue)
        .sum();
~~~

**Câu hỏi:** Kết quả là gì? Có cần `SIZED` để `sum` đúng không?

**Đáp án:** `sum = 6`. Không cần `SIZED` để tổng hợp chính xác. `SIZED` là thông tin về kích thước phục vụ hợp đồng và khả năng tối ưu, không phải điều kiện bắt buộc của phép cộng.

### Bài 6 — Tại sao không tự động nhanh khi song song?

**Câu hỏi:** Một Iterator đọc dữ liệu mạng tuần tự. Bọc bằng `spliteratorUnknownSize` rồi tạo `parallelStream` có chắc nhanh hơn không?

**Đáp án:** Không. Việc tách Iterator có thể cần đọc tuần tự để tạo lô; nguồn mạng bị chặn và các lambda nhẹ có thể khiến song song chỉ thêm overhead. Muốn cải thiện tốc độ cần xem lại khả năng chia nguồn, chi phí I/O, giới hạn kết nối và đo hiệu năng trên dữ liệu thực.

### Bài 7 — Ai đóng nguồn?

Một `Scanner` đọc tệp được bọc thành Spliterator rồi thành Stream. Sau `count()`, tệp đã chắc chắn đóng chưa?

**Đáp án:** Không. `count()` chỉ là terminal operation; `StreamSupport.stream(...)` không tự thiết lập hợp đồng đóng Scanner. Đặt Scanner trong `try-with-resources` và thực hiện toàn bộ pipeline khi Scanner còn mở.

## 17. Ghi nhớ

- `Spliterators.spliterator(iterator, size, characteristics)` dành cho Iterator có **số phần tử còn lại chính xác**; factory thông thường công bố `SIZED` và `SUBSIZED` khi nguồn không khai báo `CONCURRENT`.
- `Spliterators.spliteratorUnknownSize(iterator, characteristics)` dành cho nguồn **chưa biết số phần tử**; không công bố `SIZED`/`SUBSIZED`, dù nguồn thực sự hữu hạn.
- `estimateSize() == Long.MAX_VALUE` không có nghĩa nguồn chắc chắn vô hạn; `getExactSizeIfKnown() == -1` nghĩa Spliterator không cam kết kích thước chính xác.
- Khai báo `ORDERED`, `NONNULL`, `DISTINCT`, `IMMUTABLE` hoặc `CONCURRENT` **chỉ khi đúng hợp đồng** của nguồn. Cờ sai có thể khiến các tối ưu và kết quả không đáng tin cậy.
- `tryAdvance` tiêu thụ tiếp dữ liệu từ Iterator; `trySplit` trên wrapper Iterator có thể đọc trước và tạo mảng theo lô để chia việc.
- `StreamSupport.stream(split, parallel)` kết nối Spliterator với Stream API; `parallel = true` không tự bảo đảm hiệu năng hoặc an toàn luồng.
- Stream và Iterator thường chỉ dùng cho một lượt duyệt; nguồn I/O cần có cơ chế đóng riêng như `try-with-resources`.
- Nếu nguồn đã là Collection có Stream/Spliterator phù hợp, **ưu tiên dùng trực tiếp** thay vì bọc lại Iterator.

**Ý chính:** Thiết kế Spliterator từ Iterator không chỉ là chọn một factory. Bạn cần **biết mình có thật sự biết số phần tử còn lại không, khai báo chính xác characteristics, hiểu giới hạn của việc chia lô và chịu trách nhiệm quản lý nguồn**. Khi các hợp đồng này đúng, Stream API có thể áp dụng pipeline lazy, lọc, biến đổi, rút gọn và thu thập lên cả những nguồn chỉ cung cấp Iterator.
