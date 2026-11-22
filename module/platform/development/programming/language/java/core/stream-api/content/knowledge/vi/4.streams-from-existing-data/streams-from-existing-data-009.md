# Chuyển Iterable, Iterator và Spliterator thành Stream

> **Chương:** Tạo Stream từ dữ liệu có sẵn  
> **Module:** JAVA_STREAM_API  
> **Mục tiêu:** Chuyển các nguồn dữ liệu chỉ hỗ trợ duyệt phần tử thành `Stream<T>` đúng cách, hiểu sự khác biệt về thứ tự, kích thước, vòng đời và khả năng xử lý song song.

Khi làm việc với Java Stream API, ta thường bắt đầu bằng `list.stream()`. Nhưng trong dự án thực tế, một thư viện, API cũ hoặc thành phần xử lý dữ liệu có thể chỉ cung cấp `Iterable<T>`, `Iterator<T>` hay `Spliterator<T>`. Những nguồn này vẫn có thể tham gia pipeline khai báo với `filter`, `map`, `reduce`, `collect` và các phép toán khác. Điểm quan trọng là **chuyển đổi đúng cơ chế duyệt** và **không gán cho nguồn những đặc tính mà nó không thực sự bảo đảm**.

Bài học thuộc module **JAVA_STREAM_API**, nơi pipeline lazy, grouping, collector tùy chỉnh, `Spliterator`, Stream song song và Stream Gatherers đều dựa vào cách phần tử đi từ nguồn qua các phép toán. Việc hiểu ba kiểu nguồn giúp tránh lỗi dùng lại nguồn đã tiêu thụ, mất thứ tự, quản lý sai tài nguyên hoặc kỳ vọng hiệu năng song song không thực tế.

Các ví dụ cơ bản sử dụng Java 17 trở lên để có `List.of(...)` và `Stream.toList()`. Phần chuyển đổi bằng `StreamSupport` và `Spliterators` đã có từ Java 8; nếu dùng Java 8, thay `.toList()` bằng `.collect(Collectors.toList())` khi cần thu danh sách.

## 1. Bức tranh tổng thể

```text
Collection<T> ───────────────────────────────► collection.stream()
        │
        └── implements Iterable<T>

Iterable<T> ─── iterable.spliterator() ──┐
                                         │
Iterator<T> ─── Spliterators.            ├──► StreamSupport.stream(
                 spliteratorUnknownSize()│         spliterator, false)
                                         │                 │
Spliterator<T> ──────────────────────────┘                 ▼
                                               Stream<T> pipeline
                                           filter → map → collect
```

Cả `Iterable`, `Iterator` và `Spliterator` đều liên quan tới việc duyệt phần tử, nhưng không đồng nhất:

| Kiểu | Năng lực chính | Có phương thức `stream()` trực tiếp? | Cách chuyển thông dụng |
| --- | --- | --- | --- |
| `Collection<T>` | Chứa các phần tử, cung cấp iterator và spliterator | **Có** | `collection.stream()` |
| `Iterable<T>` | Có `iterator()`, thường có thể yêu cầu một lượt duyệt mới | **Không** | `StreamSupport.stream(iterable.spliterator(), false)` |
| `Iterator<T>` | Duyệt tuần tự với `hasNext()` / `next()`; thường là con trỏ một lần | **Không** | Bọc bằng `Spliterators.spliteratorUnknownSize(...)`, rồi `StreamSupport.stream(...)` |
| `Spliterator<T>` | Duyệt và có thể chia miền phần tử thành các phần để xử lý | **Không** | `StreamSupport.stream(spliterator, false)` |

**Phân biệt quan trọng:** Mọi `Collection` đều là `Iterable`, nhưng một `Iterable` không nhất thiết là `Collection`. Nếu biến được khai báo là `Iterable<String>`, trình biên dịch không cho gọi `.stream()` chỉ dựa trên kiểu khai báo đó, dù đối tượng thực tế có thể là một `List`.

## 2. API trung tâm: StreamSupport và Spliterators

Các thành phần chính nằm trong `java.util` và `java.util.stream`:

```java
import java.util.Iterator;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;
```

Hai overload thường dùng của `StreamSupport.stream`:

```java
// Tạo Stream từ Spliterator đã có:
static <T> Stream<T> stream(
    Spliterator<T> spliterator,
    boolean parallel
);

// Cung cấp Spliterator khi quá trình thực thi bắt đầu:
static <T> Stream<T> stream(
    Supplier<? extends Spliterator<T>> supplier,
    int characteristics,
    boolean parallel
);
```

Hai hàm hỗ trợ tạo `Spliterator` từ `Iterator`:

```java
// Khi không biết chính xác số phần tử còn lại:
static <T> Spliterator<T> spliteratorUnknownSize(
    Iterator<? extends T> iterator,
    int characteristics
);

// Khi biết chính xác số phần tử sẽ duyệt:
static <T> Spliterator<T> spliterator(
    Iterator<? extends T> iterator,
    long size,
    int characteristics
);
```

Đây là chữ ký rút gọn để học cách dùng; các lớp tương ứng cung cấp thêm overload khác.

Ý nghĩa những đối số chính:

- `spliterator`: đối tượng mô tả cách lấy phần tử từ nguồn.
- `parallel=false`: bắt đầu bằng Stream tuần tự; `true` yêu cầu chế độ song song.
- `characteristics`: tập cờ mô tả các bảo đảm của nguồn; chỉ khai báo cờ đúng với dữ liệu.
- `supplier`: cách tạo/lấy `Spliterator` vào thời điểm Stream bắt đầu thực thi, hữu ích để trì hoãn việc ràng buộc với nguồn.
- `size`: số phần tử còn lại đã biết chính xác, không phải số lượng ước đoán.

Trong thực hành, **`StreamSupport.stream(...)` là cầu nối**, còn `Spliterators` cung cấp tiện ích tạo `Spliterator` khi nguồn chỉ cho `Iterator`.

## 3. Chuyển Iterable thành Stream

### 3.1. Cách ngắn nhất

`Iterable<T>` có phương thức `spliterator()` từ Java 8. Do đó:

```java
import java.util.List;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

class IterableExample {
    public static void main(String[] args) {
        List<String> source = List.of("  Java  ", " ", " Stream ", " API ");

        // Khai báo ở kiểu Iterable, như khi một API chỉ trả về Iterable<T>.
        Iterable<String> items = () -> source.iterator();

        Stream<String> stream = StreamSupport.stream(
            items.spliterator(),
            false
        );

        List<String> result = stream
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .toList();

        System.out.println(result); // [Java, Stream, API]
    }
}
```

Giải thích:

1. `items.iterator()` cung cấp một `Iterator<String>` mỗi lần được yêu cầu.
2. `items.spliterator()` tạo đối tượng duyệt tương thích với Stream.
3. `StreamSupport.stream(..., false)` chuyển cơ chế duyệt đó thành `Stream<String>` tuần tự.
4. `map` và `filter` là phép trung gian; `toList` là phép kết thúc khiến pipeline thực thi.

Không có collection trung gian được tạo chỉ để chuyển dữ liệu sang Stream. Việc chuyển đổi này thường phù hợp hơn so với viết vòng lặp, thêm toàn bộ phần tử vào một `ArrayList`, rồi mới gọi `list.stream()`.

### 3.2. Khi nguồn đã là Collection, hãy dùng API trực tiếp

Ví dụ:

```java
List<Integer> numbers = List.of(2, 4, 6, 8);

long direct = numbers.stream()
    .filter(n -> n > 4)
    .count(); // 2
```

`List` là `Collection` nên có `stream()`. Cách này rõ ràng hơn `StreamSupport.stream(numbers.spliterator(), false)` khi không cần tùy biến cơ chế duyệt.

Nếu một API khai báo kiểu trả về là `Iterable<T>`, đừng ép kiểu sang `Collection<T>` nếu không có bảo đảm rằng đối tượng thực hiện giao diện đó:

```java
Iterable<String> items = obtainItems();

// Chuyển được với mọi Iterable hợp lệ:
Stream<String> stream = StreamSupport.stream(
    items.spliterator(),
    false
);
```

`obtainItems()` là phương thức giả định của thư viện. Muốn chạy độc lập, thay nó bằng một `Iterable` cụ thể như ví dụ trên.

### 3.3. Iterable có luôn duyệt lại được không?

Không thể kết luận một `Iterable` bất kỳ duyệt lại được chỉ từ tên giao diện. Hợp đồng `Iterable` chỉ cung cấp `iterator()`; việc mỗi lần gọi có tạo một lượt duyệt mới thực sự hay không phụ thuộc triển khai.

Ví dụ một `Iterable` thường có thể lặp lại:

```java
List<String> source = List.of("An", "Bình");
Iterable<String> repeatable = () -> source.iterator();

long count = StreamSupport.stream(
    repeatable.spliterator(), false
).count();

List<String> names = StreamSupport.stream(
    repeatable.spliterator(), false
).toList();

// count = 2; names = [An, Bình]
```

Trong đoạn trên, **mỗi lần tạo một Stream mới** dựa trên một lượt duyệt mới. Ngược lại, một adapter trả lại chính một `Iterator` đã tồn tại có thể chỉ dùng được một lượt:

```java
Iterator<String> cursor = List.of("An", "Bình").iterator();
Iterable<String> oneShot = () -> cursor;

// Không giả định oneShot có thể đọc lại sau khi iterator đã hết.
```

Ngay cả khi một `Iterable` có thể lặp lại, **mỗi đối tượng `Stream` vẫn chỉ tiêu thụ một lần**.

### 3.4. Lưu ý về thứ tự trong Iterable tự tạo

`Iterable.spliterator()` mặc định thường bọc iterator bằng một `Spliterator` có kích thước không biết trước và **không khai báo cờ `ORDERED`**. Điều này khác với `List.spliterator()`, vốn có thông tin rõ hơn về kích thước và thứ tự.

Trong trường hợp một lớp `Iterable` tự tạo có thứ tự duyệt được bảo đảm, có thể ghi rõ hợp đồng bằng cách cung cấp `spliterator()` thích hợp:

```java
List<String> source = List.of("An", "Bình", "Chi");

Iterable<String> orderedItems = new Iterable<>() {
    @Override
    public Iterator<String> iterator() {
        return source.iterator();
    }

    @Override
    public Spliterator<String> spliterator() {
        return source.spliterator();
    }
};

List<String> firstTwo = StreamSupport.stream(
    orderedItems.spliterator(), false
).limit(2).toList(); // [An, Bình]
```

Đoạn trên cần import `java.util.Iterator` và `java.util.Spliterator`. Việc override tận dụng đúng đặc tính của `List.spliterator()`. Đừng tự tuyên bố `ORDERED` cho nguồn không có thứ tự được bảo đảm.

## 4. Chuyển Iterator thành Stream

`Iterator<T>` chỉ biết cách duyệt theo `hasNext()` và `next()`, không có `spliterator()` hoặc `stream()`. Ta phải bọc nó:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

class IteratorExample {
    public static void main(String[] args) {
        Iterator<String> iterator =
            List.of("java", "stream", "api").iterator();

        Spliterator<String> spliterator =
            Spliterators.spliteratorUnknownSize(
                iterator,
                Spliterator.ORDERED | Spliterator.NONNULL
            );

        Stream<String> stream =
            StreamSupport.stream(spliterator, false);

        List<String> result = stream
            .map(String::toUpperCase)
            .filter(s -> s.length() >= 4)
            .toList();

        System.out.println(result); // [JAVA, STREAM]
    }
}
```

`spliteratorUnknownSize` phù hợp vì kiểu `Iterator` không cung cấp kích thước còn lại. Trong ví dụ, ta biết iterator lấy phần tử từ `List.of` theo thứ tự và các phần tử đều khác `null`, nên có thể khai báo `ORDERED | NONNULL`.

Nếu nguồn là một iterator tùy ý từ thư viện ngoài và chưa xác minh các đặc tính, dùng `0` là lựa chọn an toàn:

```java
Iterator<String> iterator = getLegacyIterator();

Stream<String> stream = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(iterator, 0),
    false
);
```

`getLegacyIterator()` ở đây đại diện cho API cũ của ứng dụng. Số `0` nghĩa là không khẳng định thêm đặc tính nào, không có nghĩa dữ liệu rỗng.

### 4.1. Iterator là vị trí duyệt, không phải kho dữ liệu

Xét ví dụ:

```java
Iterator<Integer> iterator = List.of(10, 20, 30).iterator();

Stream<Integer> stream = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(iterator, Spliterator.ORDERED),
    false
);

int sum = stream.mapToInt(Integer::intValue).sum(); // 60

// Không dùng lại cùng stream:
// long count = stream.count(); // IllegalStateException
```

Sau khi `sum()` kết thúc, Stream đã được tiêu thụ. Đồng thời, iterator bên dưới thường đã ở cuối, nên **bọc lại chính iterator đó** không khôi phục phần tử.

```java
// Có thể tạo iterator mới nếu nguồn gốc có thể duyệt lại:
List<Integer> numbers = List.of(10, 20, 30);

long count = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(
        numbers.iterator(), Spliterator.ORDERED
    ),
    false
).count(); // 3
```

Đối với một iterator lấy dữ liệu từ socket, truy vấn cơ sở dữ liệu hoặc API phân trang, có thể không có cách rẻ hoặc an toàn để duyệt lại. Hãy lên kế hoạch sử dụng nó một lần.

### 4.2. Nếu biết chính xác số phần tử

Khi một API cung cấp cả iterator **và số phần tử còn lại chính xác**, có thể dùng `Spliterators.spliterator(iterator, size, characteristics)`:

```java
List<String> source = List.of("An", "Bình", "Chi");

Iterator<String> iterator = source.iterator();
long exactSize = source.size();

Spliterator<String> spliterator = Spliterators.spliterator(
    iterator,
    exactSize,
    Spliterator.ORDERED | Spliterator.NONNULL
);

long count = StreamSupport.stream(spliterator, false).count(); // 3
```

Ví dụ nhằm minh họa overload có `size`; với `List` thật, `source.stream()` vẫn là lựa chọn đơn giản hơn.

**Chỉ cung cấp `size` nếu chắc chắn chính xác.** Một số phép kết thúc như `count()` có thể dùng metadata kích thước để tối ưu mà không đọc phần tử. Khai sai kích thước có thể tạo kết quả sai, phá vỡ giả định của API hoặc làm giảm độ đúng khi xử lý song song. Nếu kích thước chưa chắc chắn, hãy dùng `spliteratorUnknownSize`.

## 5. Chuyển Spliterator thành Stream

`Spliterator<T>` là giao diện ở mức thấp hơn, được Stream dùng để lấy phần tử và có thể phân chia việc duyệt. Nếu nguồn đã cung cấp `Spliterator`, không cần bọc thêm bằng `Spliterators`:

```java
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

class SpliteratorExample {
    public static void main(String[] args) {
        List<String> words = List.of("stream", "lambda", "collect");
        Spliterator<String> cursor = words.spliterator();

        List<Integer> lengths = StreamSupport.stream(cursor, false)
            .map(String::length)
            .toList();

        System.out.println(lengths); // [6, 6, 7]
    }
}
```

Trong chương trình thực tế, đối tượng `Spliterator` có thể được trả về bởi một thư viện, một lớp tùy chỉnh hoặc một collection. Lời gọi `StreamSupport.stream(cursor, false)` cho phép dùng toàn bộ hệ thống phép toán Stream trên nguồn này.

### 5.1. Các phương thức quan trọng của Spliterator

| Phương thức | Mục đích |
| --- | --- |
| `tryAdvance(Consumer<? super T> action)` | Lấy tối đa một phần tử kế tiếp, trả `true` nếu lấy được. |
| `forEachRemaining(Consumer<? super T> action)` | Thực thi hành động trên các phần tử còn lại. |
| `trySplit()` | Cố gắng tách một phần tử miền duyệt để có thể xử lý độc lập; có thể trả `null`. |
| `estimateSize()` | Ước lượng số phần tử chưa duyệt; có thể là `Long.MAX_VALUE`. |
| `characteristics()` | Trả bitmask các đặc tính được bảo đảm. |
| `hasCharacteristics(int characteristics)` | Kiểm tra có đủ một tập đặc tính hay không. |
| `getExactSizeIfKnown()` | Trả kích thước chính xác khi có `SIZED`, nếu không trả `-1`. |

Ví dụ quan sát `Spliterator` trước khi đưa vào Stream:

```java
List<Integer> numbers = List.of(10, 20, 30);
Spliterator<Integer> cursor = numbers.spliterator();

System.out.println(cursor.estimateSize()); // 3
System.out.println(cursor.hasCharacteristics(Spliterator.ORDERED)); // true

StreamSupport.stream(cursor, false).forEach(System.out::println);
```

**Không gọi `tryAdvance` để kiểm tra dữ liệu rồi kỳ vọng Stream sau đó vẫn nhận toàn bộ nguồn.** Lệnh `tryAdvance` thực sự làm tiến vị trí duyệt.

```java
Spliterator<Integer> cursor = List.of(10, 20, 30).spliterator();

cursor.tryAdvance(System.out::println); // In 10, đã tiêu thụ phần tử đầu

List<Integer> rest = StreamSupport.stream(cursor, false)
    .toList(); // [20, 30]
```

Spliterator cũng là một đối tượng duyệt có trạng thái, tương tự Iterator. Muốn thực thi lại pipeline từ đầu, cần có cơ chế lấy Spliterator mới từ nguồn phù hợp.

### 5.2. `trySplit()` liên quan gì đến xử lý song song?

`trySplit()` có thể trả về một `Spliterator` mới đại diện cho một phần công việc, đồng thời giảm phần công việc mà `Spliterator` gốc cần xử lý. Các phần này cần không chồng lặp dữ liệu. Với nguồn `ORDERED`, việc chia phải tuân thủ các bảo đảm về thứ tự của giao diện.

```java
Spliterator<Integer> rest = List.of(1, 2, 3, 4).spliterator();
Spliterator<Integer> part = rest.trySplit();

if (part != null) {
    part.forEachRemaining(System.out::println);
}
rest.forEachRemaining(System.out::println);
```

Ví dụ cho thấy thao tác chia và duyệt hai phần, nhưng **không cần tự gọi `trySplit` khi sử dụng Stream bình thường**. Khi được yêu cầu xử lý song song, framework có thể thực hiện chia việc dựa trên cơ chế này.

Một `Spliterator` hỗ trợ chia không đồng nghĩa pipeline sẽ tự chạy nhanh hơn. Hiệu quả còn phụ thuộc độ lớn dữ liệu, chi phí xử lý, đặc tính nguồn, tính thứ tự và các phép trung gian như `sorted` hay `distinct`.

## 6. Đặc tính Spliterator: khai báo đúng bảo đảm của nguồn

Các cờ đặc tính nằm trong `java.util.Spliterator` và được kết hợp bằng toán tử bitwise OR `|`:

```java
int characteristics = Spliterator.ORDERED | Spliterator.NONNULL;
```

| Cờ | Ý nghĩa của bảo đảm | Khi nào cân nhắc |
| --- | --- | --- |
| `ORDERED` | Nguồn có thứ tự gặp phần tử xác định. | Iterator duyệt theo thứ tự của `List`, dữ liệu đọc theo trình tự. |
| `DISTINCT` | Các phần tử không trùng nhau theo `equals`. | Nguồn bảo đảm không có phần tử trùng. |
| `SORTED` | Phần tử đã theo một thứ tự sắp xếp được khai báo. | Nguồn thực sự có thứ tự so sánh phù hợp. |
| `SIZED` | Kích thước còn lại được biết chính xác. | Collection/Spliterator có thể cung cấp độ dài đúng. |
| `SUBSIZED` | Mọi Spliterator thu được qua chia cũng có kích thước chính xác. | Nguồn hỗ trợ chia thành các phần với kích thước biết trước. |
| `NONNULL` | Không phần tử nào là `null`. | Nguồn đảm bảo không có `null`, như `List.of(...)`. |
| `IMMUTABLE` | Nguồn không bị thay đổi cấu trúc trong khi duyệt theo hợp đồng này. | Nguồn thực sự bảo đảm tính bất biến cấu trúc. |
| `CONCURRENT` | Nguồn được thiết kế hỗ trợ sửa đổi đồng thời phù hợp trong lúc duyệt. | Một số cấu trúc dữ liệu concurrent. |

Ví dụ kiểm tra:

```java
Spliterator<String> source =
    List.of("A", "B", "C").spliterator();

boolean ordered = source.hasCharacteristics(Spliterator.ORDERED);
boolean sized = source.hasCharacteristics(Spliterator.SIZED);
long exactSize = source.getExactSizeIfKnown();

System.out.println(ordered);   // true
System.out.println(sized);     // true
System.out.println(exactSize); // 3
```

Không phải mọi `Iterable` tự tạo đều có `SIZED`, ngay cả khi dữ liệu gốc thực chất chỉ có vài phần tử. Khi dùng `spliteratorUnknownSize`, kích thước không được khai báo là `SIZED` hoặc `SUBSIZED`.

**Đặc tính không phải nhãn gợi ý hiệu năng:** API có thể dựa vào chúng để tối ưu hoặc bảo toàn ngữ nghĩa. Không thêm `DISTINCT`, `SORTED`, `SIZED`, `IMMUTABLE` hay `CONCURRENT` chỉ để mong Stream chạy nhanh. Ví dụ, đặt `DISTINCT` cho một nguồn chứa phần tử trùng có thể làm `distinct()` bị tối ưu bỏ qua bước thực sự cần thiết.

Lưu ý thêm: `IMMUTABLE` nói về tính bất biến của *nguồn khi duyệt*, không bảo đảm các đối tượng phần tử cũng bất biến; `CONCURRENT` cũng không cho phép tùy tiện cập nhật những đối tượng chia sẻ bên trong lambda của pipeline.

## 7. Pipeline có lazy, nhưng việc ràng buộc nguồn cần phân biệt

Các phép toán trung gian như `filter` và `map` thường là **lazy**. Việc tạo Stream chưa có nghĩa toàn bộ phần tử đã được xử lý:

```java
Iterable<String> items = List.of("An", "Bình", "Chi");

var stream = StreamSupport.stream(items.spliterator(), false)
    .filter(name -> {
        System.out.println("Kiểm tra: " + name);
        return name.length() >= 3;
    });

System.out.println("Đã tạo pipeline");
List<String> names = stream.toList();

// Dòng "Đã tạo pipeline" được in trước các lần đánh giá filter.
```

**Tuy vậy, lazy operation khác với late binding của nguồn.** Một số Spliterator có thể gắn với dữ liệu ngay khi được tạo; số khác trì hoãn việc ràng buộc. Việc Stream lazy không cho phép ta suy luận rằng tất cả các nguồn đều phản ánh mọi thay đổi sau lúc tạo Stream.

### 7.1. Overload dùng Supplier để trì hoãn lấy Spliterator

`StreamSupport.stream` có overload nhận `Supplier<? extends Spliterator<T>>`. Khi đó việc gọi supplier để lấy Spliterator được trì hoãn tới sau khi phép kết thúc của pipeline bắt đầu.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

class LateBindingExample {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("Java"));

        Stream<String> pipeline = StreamSupport.stream(
            () -> source.spliterator(),
            Spliterator.ORDERED | Spliterator.SIZED | Spliterator.SUBSIZED,
            false
        );

        // Sửa dữ liệu trước khi thực thi pipeline, trên cùng một luồng:
        source.add("Stream");

        List<String> result = pipeline.toList();
        System.out.println(result); // [Java, Stream]
    }
}
```

Ở đây `ArrayList.spliterator()` cung cấp các đặc tính `ORDERED`, `SIZED` và `SUBSIZED`. **Giá trị `characteristics` truyền cho overload Supplier phải khớp với các đặc tính thực tế mà Spliterator do supplier cung cấp báo cáo**. Không dùng một bitmask đoán mò với nguồn chưa biết.

Ví dụ chỉ minh họa sửa nguồn **trước khi** đánh giá terminal operation. Không được coi việc đổi collection **trong lúc đang duyệt** là hợp lệ; với nguồn thông thường, cần tuân thủ quy tắc không can thiệp (*non-interference*). Nếu một API chỉ cung cấp iterator một lần, gọi supplier để trả lại cùng iterator đã tiêu thụ cũng không khiến nguồn có thể dùng lại.

### 7.2. Vì sao kích thước và đặc tính ảnh hưởng đến tối ưu?

Ví dụ một pipeline chỉ đếm số phần tử:

```java
long count = List.of("A", "B", "C").stream()
    .map(String::toLowerCase)
    .count(); // 3
```

Với nguồn có kích thước đã biết và các phép toán không làm thay đổi số phần tử, triển khai Stream có thể tính `count()` mà không chạy `map` trên từng phần tử. Vì vậy không nên đặt hành động cần thực hiện bắt buộc trong lambda của `map` hoặc `peek`.

Đối với nguồn iterator không biết kích thước, việc đếm thường đòi hỏi duyệt, nhưng cũng không nên lập trình dựa vào số lần lambda được gọi nếu pipeline có thể dừng sớm hoặc được tối ưu khác đi.

## 8. Ví dụ thực tế: xử lý bản ghi từ ba kiểu nguồn

Bài toán: dữ liệu bán hàng được cung cấp qua ba API khác nhau. Ta cần lọc giao dịch có doanh thu dương, gom tổng doanh thu theo nhóm, đếm đơn có giá trị lớn và tìm giao dịch đầu tiên hợp lệ.

Ví dụ Java 17+, có thể lưu trong `ExistingDataStreamsDemo.java`:

```java
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

public class ExistingDataStreamsDemo {
    record Sale(String category, long amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("Sách", 120),
            new Sale("Thiết bị", 300),
            new Sale("Sách", 80),
            new Sale("Thiết bị", -50)
        );

        // 1) API cung cấp Iterable<Sale>.
        Iterable<Sale> iterable = () -> sales.iterator();

        Map<String, Long> revenueByCategory =
            StreamSupport.stream(iterable.spliterator(), false)
                .filter(sale -> sale.amount() > 0)
                .collect(Collectors.groupingBy(
                    Sale::category,
                    TreeMap::new,
                    Collectors.summingLong(Sale::amount)
                ));

        System.out.println(revenueByCategory);
        // {Sách=200, Thiết bị=300}

        // 2) API cung cấp Iterator<Sale>.
        Iterator<Sale> iterator = sales.iterator();

        long largeSales = StreamSupport.stream(
                Spliterators.spliteratorUnknownSize(
                    iterator,
                    Spliterator.ORDERED | Spliterator.NONNULL
                ),
                false
            )
            .filter(sale -> sale.amount() >= 100)
            .count();

        System.out.println(largeSales); // 2

        // 3) API cung cấp trực tiếp Spliterator<Sale>.
        Spliterator<Sale> spliterator = sales.spliterator();

        Optional<Sale> firstPositive = StreamSupport.stream(
                spliterator, false
            )
            .filter(sale -> sale.amount() > 0)
            .findFirst();

        String firstLabel = firstPositive
            .map(sale -> sale.category() + ": " + sale.amount())
            .orElse("Không có giao dịch phù hợp");

        System.out.println(firstLabel); // Sách: 120
    }
}
```

Đây là ba Stream **độc lập**. Trong ví dụ, nguồn gốc `sales` là một danh sách có thể lấy nhiều iterator/spliterator mới. Nếu cả ba API cùng trỏ tới **một iterator duy nhất**, không được giả định có thể đọc lại toàn bộ dữ liệu ở lượt thứ hai hoặc thứ ba.

| Đường chuyển đổi | Phép toán tiếp theo | Kết quả |
| --- | --- | --- |
| `Iterable → spliterator() → Stream` | `filter`, `groupingBy`, `summingLong` | Tổng theo nhóm hàng |
| `Iterator → spliteratorUnknownSize() → Stream` | `filter`, `count` | Số giao dịch có số tiền từ 100 |
| `Spliterator → Stream` | `filter`, `findFirst` | Giao dịch hợp lệ đầu tiên |

Sau bước chuyển đổi, ta dùng cùng hệ sinh thái thao tác Stream; khác biệt chủ yếu nằm ở **bảo đảm và vòng đời của nguồn**.

## 9. Nguồn một lần và tài nguyên bên ngoài

Một Iterator có thể dựa trên cơ sở dữ liệu, tệp, socket, cursor hoặc một dịch vụ truy xuất theo trang. Stream chỉ là lớp thao tác trên các phần tử; **phép toán kết thúc không tự động đóng tài nguyên nền**.

### 9.1. Ví dụ: Scanner là Iterator và có tài nguyên cần đóng

`Scanner` hỗ trợ `Iterator<String>`. Ta có thể đưa các token của tệp vào Stream qua `spliteratorUnknownSize`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Scanner;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

class FileTokensExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.txt");

        try (Scanner scanner = new Scanner(path, StandardCharsets.UTF_8)) {
            Stream<String> tokens = StreamSupport.stream(
                Spliterators.spliteratorUnknownSize(
                    scanner,
                    Spliterator.ORDERED | Spliterator.NONNULL
                ),
                false
            );

            long longTokens = tokens
                .filter(token -> token.length() >= 4)
                .count();

            System.out.println(longTokens);
        }
    }
}
```

Ví dụ giả định `data.txt` tồn tại và chứa văn bản được phân tách thành token theo quy tắc của `Scanner`. `try-with-resources` đóng `Scanner` khi hoàn tất hoặc khi có ngoại lệ.

Trong Java hiện đại, `Scanner.tokens()` đã cung cấp Stream token trực tiếp (Java 9+); hãy ưu tiên API đó nếu có. Chuyển thủ công ở đây minh họa cách tích hợp một iterator từ thư viện khác.

Tương tự, nếu mục tiêu chỉ là đọc các dòng của tệp, `Files.lines(path)` thường phù hợp hơn; vẫn phải đóng Stream trả về qua `try-with-resources`.

### 9.2. Dùng onClose khi muốn gắn vòng đời tài nguyên với Stream

Với API bên ngoài trả về một iterator gắn với đối tượng đóng được, có thể đăng ký handler:

```java
try (Scanner scanner = new Scanner(Path.of("data.txt"), StandardCharsets.UTF_8);
     Stream<String> tokens = StreamSupport.stream(
         Spliterators.spliteratorUnknownSize(
             scanner,
             Spliterator.ORDERED | Spliterator.NONNULL
         ),
         false
     ).onClose(scanner::close)) {

    long count = tokens.count();
    System.out.println(count);
}
```

Ở ví dụ này, việc đóng scanner cả trong handler của Stream và trong `try-with-resources` là thừa, vì scanner vốn đã được quản lý trực tiếp. Trong thiết kế API thực tế, thường **chọn một cơ chế sở hữu/đóng tài nguyên rõ ràng**; chẳng hạn, chỉ quản lý Stream (đã có `onClose`) và để nó đóng tài nguyên khi thoát khối. `onClose(...)` chỉ đăng ký hành động chạy khi gọi `Stream.close()`, **không tự kích hoạt sau `count()` hay `toList()`**.

### 9.3. Phải quyết định cách xử lý ngoại lệ của nguồn

Một iterator từ I/O có thể ném ngoại lệ khi gọi `hasNext()` hoặc `next()`; khi đã chuyển thành Stream, lỗi có thể xuất hiện trong lúc thực thi terminal operation thay vì lúc tạo pipeline. Với những nguồn như cơ sở dữ liệu hoặc I/O, cần xác định cơ chế quản lý lỗi và đóng tài nguyên ngay tại ranh giới truy cập nguồn.

Không nên xử lý bằng cách âm thầm trả về Stream rỗng sau khi có lỗi đọc dữ liệu: hành vi đó dễ khiến báo cáo thống kê trông hợp lệ dù đã thiếu dữ liệu.

## 10. Thứ tự, xử lý song song và hiệu năng

### 10.1. Thứ tự gặp phần tử không phải thuộc tính của mọi Iterator

Nếu iterator lấy từ `List`, thứ tự duyệt có ý nghĩa; khi bọc, có thể khai báo `ORDERED`. Nếu iterator lấy từ nguồn không có thứ tự được bảo đảm, không được suy luận rằng vị trí mà nó đang trả ra là thứ tự ổn định.

Điều này ảnh hưởng tới:

- `findFirst()`: tìm phần tử đầu tiên **theo encounter order** nếu nguồn có thứ tự.
- `limit(n)` và `skip(n)`: ý nghĩa “đầu tiên” phụ thuộc thứ tự gặp phần tử.
- `forEachOrdered(...)`: duy trì thứ tự gặp khi Stream có thứ tự, với chi phí điều phối có thể lớn hơn.
- `sorted(...)`: thiết lập thứ tự theo comparator, nhưng có chi phí sắp xếp.

Với Stream không có thứ tự, `findFirst()` không cam kết chọn phần tử mà một lần duyệt tuần tự ngẫu nhiên nào đó trả ra trước. Nếu thứ tự là yêu cầu nghiệp vụ, hãy bảo đảm nó từ nguồn hoặc sắp xếp rõ ràng.

### 10.2. Nguồn Iterator không tự nhiên chia việc tốt

So sánh:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

// Collection có spliterator giàu thông tin:
long a = numbers.parallelStream()
    .filter(n -> n % 2 == 0)
    .count();

// Iterator được bọc với kích thước không biết trước:
long b = StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(
        numbers.iterator(), Spliterator.ORDERED
    ),
    true
).filter(n -> n % 2 == 0).count();
```

Cả hai kết quả đều là `2`. Tuy nhiên, `a` sử dụng cơ chế Spliterator của chính collection, thường biết kích thước và dễ chia miền công việc. `b` bắt đầu từ một iterator tuần tự; việc chia cần cơ chế gom phần tử thành các lô và có thể tốn thêm chi phí.

`parallel=true` chỉ yêu cầu chế độ song song cho pipeline; không bảo đảm việc xử lý nhanh hơn. Với dữ liệu nhỏ, tác vụ nhẹ, nguồn một lần, I/O chậm hoặc thứ tự bắt buộc, overhead có thể lớn hơn lợi ích. Cần đo đạc trên tải thực tế trước khi tối ưu.

### 10.3. Quy tắc non-interference vẫn áp dụng

Dù nguồn bắt đầu từ `Iterable`, `Iterator` hay `Spliterator`, lambda trong pipeline nên tránh thay đổi nguồn đang được duyệt:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

StreamSupport.stream(numbers.spliterator(), false)
    .forEach(n -> {
        // Không thêm/xóa phần tử vào numbers ở đây.
        System.out.println(n);
    });
```

Ví dụ cần `import java.util.ArrayList;`. Việc sửa một collection thông thường khi đang duyệt có thể gây `ConcurrentModificationException` hoặc kết quả không xác định. Các cờ `CONCURRENT` và `IMMUTABLE` chỉ có ý nghĩa khi nguồn thực sự đáp ứng hợp đồng; chúng không tự khiến mọi lambda thao tác chung trạng thái trở nên an toàn.

### 10.4. Kết hợp với collect, grouping và xử lý trạng thái

Sau khi chuyển đổi, có thể dùng grouping như với bất kỳ Stream nào:

```java
Iterator<String> iterator =
    List.of("Java", "Stream", "Java", "Lambda").iterator();

Map<String, Long> counts = StreamSupport.stream(
        Spliterators.spliteratorUnknownSize(
            iterator, Spliterator.ORDERED | Spliterator.NONNULL
        ),
        false
    )
    .collect(Collectors.groupingBy(
        word -> word,
        Collectors.counting()
    ));

// counts có Java=2, Stream=1, Lambda=1
```

Đoạn này cần import `java.util.Iterator`, `java.util.List`, `java.util.Map`, `java.util.Spliterator`, `java.util.Spliterators`, `java.util.stream.Collectors` và `java.util.stream.StreamSupport`.

Các collector gom nhóm thường có trạng thái tích lũy nhưng được thiết kế để tích hợp với Stream. Khi tự viết collector hoặc Spliterator, cần bảo toàn hợp đồng về kết hợp kết quả, phân chia dữ liệu, xử lý song song và non-interference. Những chủ đề đó là phần mở rộng của nguyên tắc được học ở đây.

## 11. Lựa chọn phương án chuyển đổi

| Bạn nhận từ API | Cách làm nên dùng | Lưu ý |
| --- | --- | --- |
| `List<T>` hoặc `Collection<T>` | `source.stream()` | Đơn giản, giữ các đặc tính nguồn hỗ trợ. |
| `Iterable<T>` không có `stream()` | `StreamSupport.stream(source.spliterator(), false)` | Kiểm tra khả năng duyệt lại và đặc tính thứ tự. |
| `Iterator<T>`, chưa biết kích thước | `StreamSupport.stream(Spliterators.spliteratorUnknownSize(iterator, flags), false)` | Iterator thường chỉ dùng một lần; `flags` phải chính xác. |
| `Iterator<T>`, biết kích thước chính xác | `StreamSupport.stream(Spliterators.spliterator(iterator, size, flags), false)` | Không cung cấp kích thước giả định. |
| `Spliterator<T>` đã có | `StreamSupport.stream(spliterator, false)` | Không tiêu thụ `Spliterator` trước khi chuyển nếu cần toàn bộ dữ liệu. |
| Nguồn cần lấy Spliterator khi terminal operation bắt đầu | `StreamSupport.stream(supplier, characteristics, false)` | Cờ khai báo phải khớp Spliterator thực tế. |
| Đầu vào là tệp văn bản | Ưu tiên `Files.lines(path)` | Dùng `try-with-resources` để đóng Stream. |
| Đầu vào là `Scanner` | Ưu tiên `scanner.tokens()` khi phù hợp | Đóng `Scanner`; chuyển qua Iterator nếu tích hợp API cũ. |

Có thể dùng một hàm tiện ích khi phải hỗ trợ `Iterable` tại nhiều nơi:

```java
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public static <T> Stream<T> fromIterable(Iterable<T> source) {
    return StreamSupport.stream(source.spliterator(), false);
}
```

Đây là **phương thức** để đặt bên trong một lớp Java. Khi sử dụng:

```java
Iterable<String> names = List.of("An", "Bình");
List<String> result = fromIterable(names)
    .map(String::toUpperCase)
    .toList(); // [AN, BÌNH]
```

Hàm tiện ích này không thay đổi tính chất của nguồn. Nếu `source` chỉ hỗ trợ một lượt duyệt, hàm không khiến nó tự nhiên duyệt lại được.

## 12. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `iterable.stream()` khi biến chỉ có kiểu `Iterable` | Lỗi biên dịch: `Iterable` không định nghĩa `stream()`. | Dùng `StreamSupport.stream(iterable.spliterator(), false)`. |
| Gọi `iterator.stream()` | Lỗi biên dịch: `Iterator` không có `stream()`. | Bọc bằng `Spliterators.spliteratorUnknownSize`. |
| Tái sử dụng Stream đã gọi terminal operation | `IllegalStateException`. | Tạo Stream mới từ nguồn có thể duyệt lại. |
| Bọc lại chính Iterator đã tiêu thụ | Thiếu dữ liệu hoặc Stream rỗng. | Xin iterator mới từ nguồn nếu nguồn hỗ trợ. |
| Gắn `SIZED`/`DISTINCT` không đúng | Thao tác tối ưu có thể dẫn đến kết quả sai. | Khai báo duy nhất những đặc tính được nguồn bảo đảm. |
| Cho kích thước ước đoán vào `spliterator(iterator, size, ...)` | Metadata kích thước sai. | Dùng `spliteratorUnknownSize` khi chưa biết chính xác. |
| Nghĩ Stream tự đóng tệp khi gọi `count()` | Tài nguyên có thể không được giải phóng. | Dùng `try-with-resources`; hiểu rõ `onClose`. |
| Duyệt thử Spliterator rồi mới chuyển | Phần tử đã duyệt không xuất hiện lần nữa. | Lấy Spliterator mới hoặc không tiêu thụ trước. |
| Bật `parallel=true` và kỳ vọng tự tăng tốc | Phải trả overhead chia việc, có thể chậm hơn. | Đánh giá nguồn và đo đạc thực tế. |
| Sửa collection nguồn trong `forEach` | Có thể ném ngoại lệ hoặc gây kết quả không tin cậy. | Dùng `collect` hoặc xử lý thay đổi ngoài quá trình duyệt. |

## 13. Câu hỏi tự kiểm tra

1. `Iterable<T>` và `Collection<T>` khác nhau ở điểm nào liên quan đến `stream()`?
2. Vì sao cần `Spliterators.spliteratorUnknownSize` khi API chỉ trả về `Iterator<T>`?
3. Một iterator đã hết có thể “hồi sinh” bằng cách đưa nó vào `StreamSupport.stream` lần nữa không?
4. Khi nào được khai báo `Spliterator.ORDERED` hoặc `Spliterator.NONNULL`?
5. `estimateSize()` và `getExactSizeIfKnown()` có ý nghĩa giống nhau trong mọi trường hợp không?
6. Một lệnh `tryAdvance` trước khi tạo Stream có ảnh hưởng đến kết quả không?
7. Khi nào overload `StreamSupport.stream(supplier, characteristics, parallel)` có ích?
8. Vì sao nguồn `List` có thể hỗ trợ xử lý song song tốt hơn một `Iterator` không rõ kích thước?
9. Terminal operation có tự đóng `Scanner` hoặc tệp nguồn không?
10. Tại sao không thể dùng cờ `DISTINCT` như một mẹo tăng hiệu năng với dữ liệu có trùng lặp?

**Đáp án định hướng:** (1) `Collection` có `stream()`, `Iterable` không; (2) bọc iterator thành cơ chế mà Stream hiểu; (3) không; (4) chỉ khi nguồn thực sự bảo đảm; (5) không, ước lượng có thể không chính xác; (6) có, phần tử bị tiêu thụ; (7) khi cần trì hoãn lấy Spliterator tới lúc terminal operation bắt đầu; (8) biết kích thước và có khả năng chia việc phù hợp; (9) không, phải quản lý việc đóng; (10) vì cờ sai có thể làm bước loại trùng bị tối ưu bỏ qua.

## 14. Ghi nhớ cốt lõi

- **`Iterable<T>` → `iterable.spliterator()` → `StreamSupport.stream(...)`** là cầu nối cơ bản khi API không cung cấp `stream()`.
- **`Iterator<T>` → `Spliterators.spliteratorUnknownSize(...)` → `StreamSupport.stream(...)`** phù hợp với nguồn duyệt một lần hoặc kích thước chưa biết.
- **`Spliterator<T>` → `StreamSupport.stream(...)`** dùng trực tiếp khi đã có một đối tượng duyệt có thể chia.
- **Không tự gán metadata sai:** các đặc tính như `ORDERED`, `SIZED`, `DISTINCT`, `SORTED`, `IMMUTABLE` và `CONCURRENT` là hợp đồng về nguồn, không phải gợi ý tùy ý.
- **Stream và cursor chỉ được tiêu thụ theo vòng đời của chúng;** nguồn có thể duyệt lại cần cấp iterator/spliterator mới cho từng lượt xử lý.
- **Lazy pipeline không có nghĩa tài nguyên tự đóng.** Cần quản lý I/O và hạn chế tác động phụ trong lambda, nhất là khi chạy song song.
- Khi đã tạo được `Stream<T>` đúng cách, các phép `filter`, `map`, `reduce`, `collect`, grouping, collector tùy chỉnh, cùng các kỹ thuật `Spliterator` và Stream Gatherers có thể xây dựng trên cùng mô hình pipeline.
