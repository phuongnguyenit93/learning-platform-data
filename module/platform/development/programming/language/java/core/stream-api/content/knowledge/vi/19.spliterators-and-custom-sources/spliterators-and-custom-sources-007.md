# Tạo Stream bằng StreamSupport với Spliterator trực tiếp

Java Stream API thường bắt đầu từ những nguồn có sẵn như `list.stream()`, `Arrays.stream(...)` hoặc `IntStream.range(...)`. Tuy nhiên, có lúc dữ liệu nằm trong một cấu trúc tự định nghĩa, một `Iterator`, một bộ sinh giá trị hoặc một nguồn cần kiểm soát cách chia công việc. Khi đó, `Spliterator` kết hợp với `StreamSupport` cho phép **đưa nguồn dữ liệu tùy chỉnh vào pipeline Stream** mà không phải chuyển hết dữ liệu thành `List` trước.

Bài học thuộc chương **Spliterator và nguồn tự định nghĩa** của module `JAVA_STREAM_API`. Ta sẽ học cách tạo `Stream<T>` bằng `StreamSupport.stream(spliterator, parallel)`, xây `IntStream` bằng `StreamSupport.intStream(...)`, hiểu trách nhiệm của `tryAdvance`, `trySplit`, `estimateSize` và `characteristics`, phân biệt *early binding* với *late binding*, cũng như những giới hạn về trạng thái, tài nguyên và hiệu năng khi xử lý song song. Các ví dụ nối với pipeline lazy gồm `filter`, `map`, `reduce` và `collect`.

Các API cốt lõi trong bài đều có từ **Java 8**. Đoạn mã trong từng phần có thể dùng độc lập theo các `import` được ghi, hoặc tiếp tục sử dụng lớp đã định nghĩa ở phần trước.

## 1. Spliterator đóng vai trò gì?

`Spliterator<T>` là một đối tượng duyệt và có thể chia nguồn phần tử kiểu `T`. Tên gọi viết tắt từ *splitable iterator*. Khác với `Iterator` chỉ có thao tác duyệt tuần tự thông thường, `Spliterator` cung cấp:

- `tryAdvance(action)`: cố gắng đưa **một** phần tử kế tiếp vào `action`.
- `forEachRemaining(action)`: đưa các phần tử còn lại vào `action`.
- `trySplit()`: thử chia phần tử còn lại thành hai phần **không trùng nhau**.
- `estimateSize()`: ước lượng số phần tử còn lại.
- `characteristics()`: công bố các đặc điểm nguồn như `ORDERED`, `SIZED`, `SORTED` hoặc `IMMUTABLE`.

`StreamSupport` lấy một `Spliterator` làm nguồn, còn các thao tác Stream downstream phụ trách xử lý phần tử:

```text
Nguồn tùy chỉnh
      │
      ▼
Spliterator<T>
      │
      ├── tryAdvance() : phát phần tử
      ├── trySplit()   : chia phạm vi
      ├── estimateSize()
      └── characteristics()
      │
      ▼
StreamSupport.stream(spliterator, false)
      │
      ├── filter(...)
      ├── map(...)
      ├── distinct(...)
      └── collect(...)    ← terminal operation
      │
      ▼
Kết quả
```

**Điểm quan trọng:** `Spliterator` xác định **nguồn và cách duyệt**, không thay `Stream` thực hiện `map` hay `collect`. `StreamSupport` không sao chép toàn bộ các phần tử vào bộ nhớ chỉ để tạo Stream.

Không phải lúc nào cần tự viết `Spliterator`. Trước khi làm vậy, hãy tìm xem nguồn có `stream()`, `spliterator()` hoặc một factory chuẩn đã đáp ứng yêu cầu hay chưa.

## 2. Cách dùng trực tiếp StreamSupport.stream

Chữ ký cơ bản:

```java
public static <T> Stream<T> stream(
        Spliterator<T> spliterator,
        boolean parallel
)
```

- `spliterator`: đối tượng nguồn, bắt buộc không null.
- `parallel = false`: tạo pipeline tuần tự.
- `parallel = true`: tạo pipeline ở chế độ song song; **không hứa hẹn nhanh hơn**.
- Kết quả là một `Stream<T>` có thể gắn các thao tác trung gian và một terminal operation.

Ví dụ dùng `Spliterator` của danh sách:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<String> words = Arrays.asList(" Java ", "Stream", "", " API ");

Spliterator<String> source = words.spliterator();
Stream<String> pipeline = StreamSupport.stream(source, false);

List<String> cleaned = pipeline
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());

System.out.println(cleaned); // [Java, Stream, API]
```

Chúng ta không cần chuyển `words` thành một cấu trúc khác. `StreamSupport` chỉ nối `Spliterator` của nguồn vào pipeline.

Tuy vậy, với `List` thông thường, `words.stream()` ngắn gọn hơn và nên được ưu tiên. Việc viết `StreamSupport.stream(words.spliterator(), false)` trong ví dụ này nhằm giải thích cơ chế kết nối. Giá trị thực tế của `StreamSupport` xuất hiện khi nguồn **không tự cung cấp Stream**.

### Stream chỉ tiêu thụ một lần

`pipeline.collect(...)` đã dùng hết Stream trong ví dụ. Không được gọi thêm `pipeline.count()` trên cùng instance sau khi terminal operation chạy. Muốn duyệt lại nguồn danh sách, hãy tạo một Stream mới từ một `Spliterator` mới:

```java
long count = StreamSupport.stream(words.spliterator(), false)
        .filter(s -> !s.trim().isEmpty())
        .count();

System.out.println(count); // 3
```

Một `Spliterator` đã bị tiêu thụ cũng không nên dùng lại như một nguồn mới. Việc tạo Stream mới **không** tự khôi phục trạng thái duyệt của một nguồn một lần như Iterator hay Reader.

## 3. Kết nối Iterator bằng Spliterators.spliteratorUnknownSize

Một nguồn cũ chỉ cung cấp `Iterator<T>` cũng có thể đưa vào Stream:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

Iterator<String> iterator = Arrays.asList(
        "backend", "frontend", "qa"
).iterator();

Spliterator<String> source = Spliterators.spliteratorUnknownSize(
        iterator,
        Spliterator.ORDERED
);

List<String> upper = StreamSupport.stream(source, false)
        .map(String::toUpperCase)
        .collect(Collectors.toList());

System.out.println(upper); // [BACKEND, FRONTEND, QA]
```

Ý nghĩa:

1. `Spliterators.spliteratorUnknownSize(iterator, characteristics)` bọc Iterator thành Spliterator; không yêu cầu biết trước kích thước.
2. `Spliterator.ORDERED` chỉ đúng nếu Iterator thật sự có thứ tự gặp phần tử cần bảo toàn.
3. `StreamSupport.stream(source, false)` tạo Stream tuần tự từ nguồn đó.
4. `map` và `collect` chỉ tiêu thụ những phần tử thực tế được Iterator cung cấp.

Không khai báo `SIZED` hoặc `SUBSIZED` khi không biết kích thước chính xác. Factory `spliteratorUnknownSize` loại bỏ hai cờ này ngay cả khi người gọi vô tình truyền vào.

**Lưu ý:** đây không phải phép “nâng cấp Iterator thành nguồn song song lý tưởng”. Spliterator được tạo có thể hỗ trợ chia theo lô, nhưng hiệu quả phụ thuộc bản chất Iterator. Nếu Iterator đọc tuần tự từ một socket hoặc có tài nguyên bên ngoài, phải quản lý quyền sở hữu và vòng đời riêng.

## 4. Tạo nguồn đơn giản bằng AbstractSpliterator

Khi không có sẵn Collection hoặc Iterator, có thể tự cung cấp logic phát phần tử. `Spliterators.AbstractSpliterator<T>` giúp giảm mã mẫu khi ta chủ yếu cần định nghĩa `tryAdvance`.

Ví dụ phát năm mã sự kiện liên tiếp:

```java
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.Consumer;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

Spliterator<String> generated =
        new Spliterators.AbstractSpliterator<String>(
                5L,
                Spliterator.ORDERED
        ) {
            private int next = 0;

            @Override
            public boolean tryAdvance(Consumer<? super String> action) {
                Objects.requireNonNull(action, "action");
                if (next >= 5) {
                    return false;
                }

                action.accept("event-" + next++);
                return true;
            }
        };

System.out.println(
        StreamSupport.stream(generated, false)
                .collect(Collectors.toList())
);
// [event-0, event-1, event-2, event-3, event-4]
```

Trong ví dụ:

- `tryAdvance` phát **tối đa một** phần tử cho mỗi lần trả `true`.
- Khi không còn phần tử, nó trả `false`.
- `ORDERED` đúng vì mã được sinh theo thứ tự từ 0 tới 4.
- `estimateSize` khởi tạo bằng 5 là một giới hạn/ước lượng; ví dụ không khai báo `SIZED`, nên Stream không cần coi đó là số lượng chính xác tại mọi thời điểm.

`AbstractSpliterator` có sẵn thuật toán `trySplit` mặc định dựa trên gom phần tử thành các lô. Cách chia ấy không nhất thiết tối ưu cho mọi nguồn. Với nguồn đắt đỏ, có thứ tự, hoặc có trạng thái I/O, phải đánh giá xem việc chia có thật sự an toàn và có ích hay không.

**Đừng khai báo `IMMUTABLE`, `CONCURRENT` hoặc `SIZED` chỉ để tăng tốc.** Mỗi đặc tính là một cam kết về nguồn và hành vi, không phải tùy chọn trang trí.

## 5. Tự định nghĩa Spliterator có thể chia phạm vi

Để thấy rõ cách phân hoạch, ta xây một `Spliterator.OfInt` phát dãy số nguyên từ `startInclusive` đến `endExclusive - 1`. Bài toán tương đương `IntStream.range(...)`, nhưng chủ đích ở đây là học cách implement nguồn tùy chỉnh.

### 5.1. Một lớp Spliterator.OfInt hoàn chỉnh

```java
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;

final class IntRangeSpliterator implements Spliterator.OfInt {
    private int cursor;
    private final int fence;

    IntRangeSpliterator(int startInclusive, int endExclusive) {
        if (startInclusive < 0 || endExclusive < startInclusive) {
            throw new IllegalArgumentException("Invalid range");
        }
        this.cursor = startInclusive;
        this.fence = endExclusive;
    }

    @Override
    public boolean tryAdvance(IntConsumer action) {
        Objects.requireNonNull(action, "action");

        if (cursor >= fence) {
            return false;
        }

        action.accept(cursor++);
        return true;
    }

    @Override
    public Spliterator.OfInt trySplit() {
        int remaining = fence - cursor;
        if (remaining < 2) {
            return null;
        }

        int midpoint = cursor + remaining / 2;

        Spliterator.OfInt prefix =
                new IntRangeSpliterator(cursor, midpoint);

        cursor = midpoint;
        return prefix;
    }

    @Override
    public long estimateSize() {
        return (long) fence - cursor;
    }

    @Override
    public int characteristics() {
        return Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED
                | Spliterator.SORTED
                | Spliterator.DISTINCT
                | Spliterator.NONNULL
                | Spliterator.IMMUTABLE;
    }

    @Override
    public Comparator<? super Integer> getComparator() {
        return null; // SORTED theo thứ tự tự nhiên tăng dần
    }
}
```

Để giữ ví dụ rõ ràng, constructor chấp nhận phạm vi **không âm**, với `endExclusive >= startInclusive`. Khi dùng nguồn số nguyên ở miền khác, cần cẩn thận với tính toán midpoint và tràn số; không thể lấy phép trừ `int` tùy ý để tính khoảng cách giữa mọi cặp giá trị `int` mà vẫn an toàn.

### 5.2. Dùng StreamSupport.intStream

```java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

IntStream numbers = StreamSupport.intStream(
        new IntRangeSpliterator(10, 15),
        false
);

int[] values = numbers.toArray();
System.out.println(Arrays.toString(values));
// [10, 11, 12, 13, 14]
```

Đây là kết quả của `IntStream`, không cần boxing thành `Stream<Integer>`. Sau khi gọi `toArray()`, Stream đã bị tiêu thụ.

Khi thay `parallel` bằng `true`:

```java
int evenSum = StreamSupport.intStream(
        new IntRangeSpliterator(0, 20),
        true
).filter(n -> n % 2 == 0)
 .sum();

System.out.println(evenSum); // 90
```

`IntRangeSpliterator` có thể tách miền `[0, 20)` thành những miền con không trùng. Phép cộng số nguyên ở đây nằm trong giới hạn nên cho cùng kết quả khi chạy tuần tự hoặc song song.

### 5.3. Vì sao trySplit phải trả về đúng phần của nguồn?

Giả sử trạng thái ban đầu là `[0, 8)`:

```text
Trước khi chia:
  this = [0, 8)

Sau trySplit():
  kết quả trả về = [0, 4)    ← phần đứng trước
  this           = [4, 8)    ← phần còn lại

Tiếp tục chia this:
  kết quả trả về = [4, 6)
  this           = [6, 8)
```

Sau khi chia, **tổng số phần tử không được mất hoặc lặp lại**. `trySplit()` không được trả về Spliterator chứa các phần tử vẫn còn ở Spliterator gốc. Với nguồn `ORDERED`, phần được trả về nên là **tiền tố** của các phần tử còn lại.

Khi không thể chia có ích (ở ví dụ chỉ còn 0 hoặc 1 phần tử), trả `null`. Đừng giả định framework sẽ gọi `trySplit` đúng một lần hoặc chia thành số nhánh cố định; mức phân hoạch có thể thay đổi theo thuật toán thực thi.

## 6. Giải thích từng phương thức của IntRangeSpliterator

| Phương thức | Đảm bảo trong ví dụ | Lỗi thường gặp |
| --- | --- | --- |
| `tryAdvance` | Phát đúng một số `int` nếu còn dữ liệu; trả `false` khi hết | Trả `true` mà không phát phần tử, hoặc phát hai phần tử |
| `trySplit` | Trả một phạm vi tiền tố không trùng; thu hẹp phạm vi của `this` | Hai nhánh cùng phát một phần tử hoặc bỏ sót một đoạn |
| `estimateSize` | Số phần tử còn lại chính xác | Không giảm sau `tryAdvance` hoặc `trySplit` |
| `characteristics` | Mô tả chính xác thứ tự và miền giá trị | Khai báo `SIZED`, `SORTED` sai sự thật |
| `getComparator` | Trả `null` khi có `SORTED` theo thứ tự tự nhiên | Khai báo `SORTED` nhưng không cung cấp comparator hợp lệ |

Với các Spliterator reference type, `tryAdvance` nhận `Consumer<? super T>`. Với `OfInt`, đối số nguyên thủy được truyền vào `IntConsumer` để tránh boxing. `OfLong` và `OfDouble` sử dụng `LongConsumer` và `DoubleConsumer` tương ứng.

**Không chia sẻ trực tiếp cùng một Spliterator đang thay đổi cursor giữa hai luồng.** Khả năng chạy parallel đến từ việc framework tạo những *phạm vi tách biệt* bằng `trySplit`; nó không có nghĩa mọi phương thức của cùng một instance Spliterator đều thread-safe khi caller tự gọi đồng thời.

## 7. Characteristics: công bố sự thật về nguồn dữ liệu

`Spliterator.characteristics()` trả về một bitmask kết hợp các đặc tính. Các cờ thường gặp:

| Đặc tính | Ý nghĩa | Khi nào được công bố |
| --- | --- | --- |
| `ORDERED` | Nguồn có encounter order xác định | Danh sách có thứ tự, dãy số theo thứ tự |
| `DISTINCT` | Không có hai phần tử bằng nhau theo `equals` | Dãy số không trùng, Set theo đúng hợp đồng |
| `SORTED` | Phần tử được sắp xếp theo thứ tự tự nhiên hoặc comparator | Chỉ khi thứ tự nguồn thực sự được đảm bảo |
| `SIZED` | `estimateSize()` là số phần tử còn lại chính xác khi không bị can thiệp trái phép | Mảng, khoảng cố định với kích thước được biết |
| `SUBSIZED` | Mọi Spliterator tạo từ `trySplit` cũng đảm bảo `SIZED` và `SUBSIZED` | Chia phạm vi có kích thước chính xác |
| `NONNULL` | Nguồn không phát phần tử null | Primitive Spliterator, nguồn đã đảm bảo khác null |
| `IMMUTABLE` | Nguồn dữ liệu không bị thay đổi cấu trúc trong lúc duyệt | Miền số sinh theo công thức, dữ liệu bất biến |
| `CONCURRENT` | Nguồn cho phép sửa đổi đồng thời theo hợp đồng | Một số cấu trúc dữ liệu concurrent có thiết kế phù hợp |

**Hai ranh giới cần nhớ:**

1. `SIZED` không có nghĩa mọi Stream downstream vẫn có kích thước chính xác như nguồn. `filter` làm thay đổi số phần tử đi qua pipeline, nên không thể suy ra kết quả sau lọc có đúng `estimateSize` của nguồn.
2. `CONCURRENT` của Spliterator **khác** `Collector.Characteristics.CONCURRENT`. Cờ đầu nói về **nguồn có thể chịu sửa đổi đồng thời**; cờ sau nói về **cách nhiều luồng có thể tích lũy vào cùng một kết quả**.

Một Spliterator nguồn tự viết cho List mutable không được tùy tiện khai báo `IMMUTABLE` nếu List đó có thể bị sửa trong lúc duyệt. Ngược lại, việc thay đổi `cursor` của một Spliterator khi duyệt là trạng thái **traversal**, không tự động vi phạm tính bất biến của **nguồn dữ liệu** được mô tả bởi `IMMUTABLE`.

### SORTED đòi getComparator hợp lệ

Với `Spliterator.SORTED`, `getComparator()` phải cung cấp comparator đúng khi có comparator tự định nghĩa, hoặc trả `null` nếu thứ tự tự nhiên. Trong ví dụ `IntRangeSpliterator`, dãy số tăng dần nên `getComparator()` trả `null`.

Nếu một Spliterator thực sự không biết thứ tự, **không được khai báo `SORTED`**. Khai báo sai có thể làm pipeline bỏ những bước sắp xếp cần thiết hoặc thực thi tối ưu không phù hợp, dẫn tới kết quả không đúng.

## 8. Tạo primitive stream mà không boxing

`StreamSupport` có các factory riêng:

```java
StreamSupport.intStream(Spliterator.OfInt spliterator, boolean parallel);
StreamSupport.longStream(Spliterator.OfLong spliterator, boolean parallel);
StreamSupport.doubleStream(Spliterator.OfDouble spliterator, boolean parallel);
```

Ba dòng trên minh họa **chữ ký khái niệm**, không phải lời gọi Java độc lập. Ví dụ dùng factory có sẵn để tạo `LongStream` từ mảng:

```java
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.stream.LongStream;
import java.util.stream.StreamSupport;

long[] amounts = {10L, 20L, 30L};

Spliterator.OfLong source = Spliterators.spliterator(
        amounts,
        Spliterator.ORDERED
);

long total = StreamSupport.longStream(source, false).sum();

System.out.println(total); // 60
```

Vì nguồn là mảng primitive, không phải tạo từng `Long` cho mỗi phần tử. Với `Stream<Integer>` thông thường, thao tác `mapToInt(Integer::intValue)` có thể cần unboxing; `OfInt` là cách tự nhiên hơn khi nguồn vốn phát `int`.

Nếu chỉ có mảng primitive, `Arrays.stream(amounts)` vẫn là cách đọc trực tiếp và gọn hơn. Mục đích của `StreamSupport` là tích hợp nguồn đặc biệt, không bắt buộc thay mọi factory chuẩn.

## 9. Spliterator trực tiếp và Supplier: early binding, late binding

`StreamSupport` cung cấp thêm overload nhận Supplier:

```java
public static <T> Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel
)
```

Sự khác nhau quan trọng:

- `stream(spliterator, parallel)` nhận **một Spliterator đã được tạo** tại thời điểm xây Stream.
- `stream(supplier, characteristics, parallel)` hoãn việc **lấy Spliterator từ Supplier** cho tới khi terminal operation bắt đầu; factory được gọi không quá một lần theo hợp đồng API.

Đó là cách thực hiện *late binding*, hữu ích khi cần chọn snapshot tại thời điểm tiêu thụ.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

List<String> source = new ArrayList<>(
        Arrays.asList("A", "B")
);

Supplier<Spliterator<String>> supplier =
        () -> new ArrayList<>(source).spliterator();

Stream<String> deferred = StreamSupport.stream(
        supplier,
        Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED,
        false
);

// Sửa nguồn trước khi terminal operation bắt đầu.
source.add("C");

List<String> snapshot = deferred.collect(Collectors.toList());
System.out.println(snapshot); // [A, B, C]
```

Trong ví dụ này, Supplier tạo **bản sao danh sách tại lúc terminal operation bắt đầu**. Việc này làm rõ ranh giới nguồn: chỉnh sửa `source` trước terminal có thể được nhìn thấy trong bản sao, còn thay đổi sau khi bản sao hình thành thì không thuộc snapshot đó.

**Không được khai báo một tập characteristics khác với Spliterator mà Supplier thực sự trả về.** Các cờ truyền cho overload Supplier phải khớp với cờ của Spliterator trả về tại thời điểm được tạo; khai báo mâu thuẫn là vi phạm hợp đồng.

### Khi nào chọn overload nào?

| Trường hợp | Lựa chọn |
| --- | --- |
| Đã có Spliterator và muốn tiêu thụ một lần | `stream(spliterator, false)` |
| Muốn tạo Spliterator sát thời điểm terminal bắt đầu | `stream(supplier, flags, false)` |
| Cần Stream số nguyên thủy từ nguồn tùy chỉnh | `intStream` / `longStream` / `doubleStream` |
| Nguồn đã có `stream()` | Dùng `stream()` sẵn có nếu đáp ứng nhu cầu |
| Có Iterator cũ | `spliteratorUnknownSize` rồi `StreamSupport.stream` |

**Cẩn trọng với thay đổi đồng thời:** việc trì hoãn tạo Spliterator không làm một `ArrayList` đang bị luồng khác chỉnh sửa trở thành thread-safe. Nếu nhiều luồng chia sẻ nguồn, cần mô hình đồng bộ, snapshot bất biến hoặc cấu trúc concurrent phù hợp.

## 10. Những bẫy về trạng thái và tính đúng đắn

### 10.1. tryAdvance trả true nhưng không phát phần tử

```java
// SAI: báo có phần tử nhưng không gọi action.accept(...).
@Override
public boolean tryAdvance(Consumer<? super String> action) {
    if (hasNext()) {
        moveCursor();
        return true;
    }
    return false;
}
```

`tryAdvance` phải gọi action với **chính xác một** phần tử khi trả `true`. Khi trả `false`, không được âm thầm phát phần tử. Vi phạm hợp đồng này có thể khiến kết quả thiếu dữ liệu hoặc hành vi pipeline không hợp lệ.

### 10.2. Hai nhánh trySplit trùng dữ liệu

```text
SAI:
  prefix = [0, 5)
  this   = [3, 8)

  Các số 3 và 4 sẽ bị xử lý hai lần.

ĐÚNG:
  prefix = [0, 4)
  this   = [4, 8)
```

Số phần tử sau tách phải được bảo toàn. Với `SIZED` và `SUBSIZED`, kích thước công bố phải còn chính xác sau những lần tách/duyệt.

### 10.3. Khai báo SIZED cho nguồn chưa biết bao giờ dừng

Nếu nguồn là log liên tục, socket hoặc iterator không có số lượng phần tử xác định, đừng khai báo `SIZED` chỉ dựa trên một dự đoán. `estimateSize()` có thể trả `Long.MAX_VALUE` khi không có ước lượng hữu ích, nhưng nguồn không vì thế mà trở thành nguồn hữu hạn.

Một terminal operation trên nguồn vô hạn như `collect(toList())` hoặc `sorted()` có thể không bao giờ hoàn tất và gây áp lực bộ nhớ. Với nguồn phù hợp, `limit(n)` có thể giúp pipeline dừng sớm, nhưng không tự đóng tài nguyên.

### 10.4. Dùng cùng Spliterator cho hai Stream

```java
Spliterator<String> oneShot = words.spliterator();

long firstCount = StreamSupport.stream(oneShot, false)
        .filter(s -> !s.isEmpty())
        .count(); // filter yêu cầu duyệt các phần tử của nguồn này

// SAI về kỳ vọng: Spliterator đã bị tiêu thụ;
// không tạo nguồn mới bằng cách bọc lại chính instance này.
long secondCount = StreamSupport.stream(oneShot, false)
        .filter(s -> !s.isEmpty())
        .count(); // nguồn đã cạn; không phải lượt đọc mới
```

Lần thứ hai có thể trả 0 hoặc hành vi phụ thuộc nguồn, không phải “duyệt lại danh sách”. Hãy yêu cầu nguồn tạo Spliterator mới nếu cần nhiều lượt xử lý.

### 10.5. Dùng peek hoặc biến ngoài làm bộ đếm

```java
// KHÔNG NÊN: biến ngoài không an toàn cho parallel,
// và side effect ở peek không phải cách thiết kế kết quả.
int[] seen = {0};

StreamSupport.stream(words.spliterator(), true)
        .peek(s -> seen[0]++)
        .count();
```

Thao tác `peek` không nên dùng để thực hiện side effect mà nghiệp vụ phụ thuộc vào; terminal operation có thể tận dụng thông tin kích thước để không duyệt từng phần tử trong những trường hợp phù hợp. Với parallel stream, cập nhật `seen[0]++` còn gây data race. Khi cần đếm, sử dụng `count()`; khi cần trạng thái tổng hợp tùy chỉnh, dùng `collect` với Collector đúng hợp đồng.

## 11. Quản lý tài nguyên với Spliterator tùy chỉnh

`StreamSupport.stream(...)` **không tự biết** nguồn có đang giữ tệp, kết nối mạng, Reader hay socket. Nó chỉ nhận một Spliterator để duyệt; việc tạo một Stream không đồng nghĩa đã có close handler đóng mọi tài nguyên phía dưới.

Ví dụ học cách gắn một Reader đã mở với StreamSupport:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Spliterator;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

static long countErrorLines(Path path) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

        Spliterator<String> source = reader.lines().spliterator();

        Stream<String> lines = StreamSupport.stream(source, false);
        return lines.filter(s -> s.startsWith("ERROR")).count();
    }
}
```

Phần **quan trọng** là `try-with-resources` đóng `BufferedReader` dù terminal operation hoàn tất hay ném ngoại lệ. Đoạn trên cố ý sử dụng `StreamSupport` để giải thích cơ chế. Trong code thực tế, dùng trực tiếp `reader.lines().filter(...).count()` thường đơn giản hơn; việc bọc lại Reader Stream thành Spliterator rồi thành Stream không tự mang lại lợi ích.

Nếu muốn **trả ra một Stream sở hữu tài nguyên** để caller đóng, cần thiết kế rõ quyền sở hữu và có thể dùng `onClose(...)` để đăng ký handler đóng nguồn. Khi close handler cần chuyển `IOException` thành unchecked exception, có thể dùng `UncheckedIOException`. Nhưng người gọi vẫn phải dùng `try-with-resources`: ngay cả terminal operation như `limit` hoặc `count` cũng **không tự đóng Stream**.

**Không đóng Reader trước khi Stream lazy được tiêu thụ.** Cũng không được tự ý đọc đồng thời từ một Reader trong `tryAdvance` của nhiều nhánh, trừ khi nguồn được thiết kế bảo đảm điều đó.

## 12. Thiết kế nguồn chịu được parallel stream

Muốn dùng `StreamSupport.stream(spliterator, true)` hiệu quả, cần nhiều hơn việc đặt `parallel = true`.

### Đầu vào phải chia được

`trySplit` nên tạo những phạm vi dữ liệu đủ lớn và đủ cân bằng để có ích. Nếu luôn trả `null`, nhiều trường hợp pipeline không thể phân công đọc nguồn ra nhiều nhánh đáng kể. Nếu việc chia quá nhỏ, chi phí lập lịch và gộp có thể lấn át công việc thực.

### Mỗi nhánh phải độc lập về trạng thái duyệt

Trong `IntRangeSpliterator`, các nhánh dùng cursor/fence riêng. Không tồn tại một biến chỉ số dùng chung bị nhiều luồng tăng mà không có quy tắc đồng bộ. Một nguồn đọc từ cùng `BufferedReader` không thể đơn giản chia theo số thứ tự dòng nếu không có cách truy cập độc lập và xác định ranh giới.

### Characteristics phải chính xác

Nếu nguồn là dãy số tăng với số lượng cố định, có thể khai báo `SIZED`, `SUBSIZED`, `ORDERED` và `SORTED`. Nếu nguồn bị thay đổi cấu trúc trong lúc duyệt và không có chính sách nhất quán, không được tùy tiện khai báo `IMMUTABLE` hay `CONCURRENT`.

### Phép toán downstream cũng phải phù hợp

`filter`, `map` và `reduce` cần hàm thuần, stateless, không can thiệp vào nguồn. Các thao tác `sorted`, `distinct`, `skip`, `limit` có thể tăng chi phí phối hợp nếu cần giữ encounter order. Bản thân nguồn có khả năng chia không đảm bảo toàn pipeline có lợi khi parallel.

**Đo trên dữ liệu thực.** Một nguồn 100 phần tử với bước xử lý rẻ thường không hưởng lợi rõ ràng từ song song; nguồn lớn và mỗi phần tử xử lý CPU nặng có thể khác. Chi phí boxing, bộ đệm, tải I/O và phân bố kích thước nhánh đều ảnh hưởng.

## 13. Khi nào không cần StreamSupport?

Trước khi viết Spliterator tùy chỉnh, kiểm tra các lựa chọn có sẵn:

| Nguồn hoặc yêu cầu | API thường nên dùng |
| --- | --- |
| `List<T>`, `Set<T>` | `collection.stream()` hoặc `parallelStream()` |
| Mảng object hoặc primitive | `Arrays.stream(...)` |
| Khoảng số nguyên | `IntStream.range(...)` / `rangeClosed(...)` |
| Một số phần tử định sẵn | `Stream.of(...)` |
| Sinh phần tử theo quy tắc | `Stream.generate(...)` / `Stream.iterate(...)` |
| Đọc từng dòng tệp | `Files.lines(path)` với `try-with-resources` |
| Reader đã có sẵn | `BufferedReader.lines()` với Reader được đóng đúng vòng đời |
| Iterator tùy chỉnh | `Spliterators.spliteratorUnknownSize(...)` + `StreamSupport.stream(...)` |
| Cấu trúc tự định nghĩa cần chia đặc thù | `Spliterator` tự viết + `StreamSupport` |
| Dữ liệu cần giữ kết quả mutable theo nhóm | `collect(...)`, không phải sửa nguồn trong `tryAdvance` |

Trong một module học Stream API, hiểu `StreamSupport` giúp biết Stream được xây trên `Spliterator` như thế nào. Nhưng trong ứng dụng, **cách viết đơn giản nhất vẫn nên là lựa chọn đầu tiên** nếu nó thỏa hợp đồng nghiệp vụ và tài nguyên.

## 14. Ví dụ tổng hợp: xử lý phạm vi số theo cả hai chế độ

Giả sử yêu cầu tính tổng bình phương các số chia hết cho 3 trong phạm vi `[0, 100)`. Thay vì tạo trước một danh sách, dùng `IntRangeSpliterator` đã viết ở phần 5:

```java
import java.util.stream.StreamSupport;

int sequential = StreamSupport.intStream(
        new IntRangeSpliterator(0, 100),
        false
).filter(n -> n % 3 == 0)
 .map(n -> n * n)
 .sum();

int parallel = StreamSupport.intStream(
        new IntRangeSpliterator(0, 100),
        true
).filter(n -> n % 3 == 0)
 .map(n -> n * n)
 .sum();

System.out.println(sequential); // 112761
System.out.println(parallel);   // 112761
```

Phạm vi 0 đến 99 có các bội số 3 là `0, 3, ..., 99`. Tổng bình phương của chúng là `9 * (0² + 1² + ... + 33²) = 112761` và nằm trong giới hạn `int`; nếu mở rộng phạm vi lớn, tổng và phép nhân `n*n` có thể tràn. Khi đó nên chuyển sang `LongStream` và thực hiện phép nhân trên `long` hoặc sử dụng kiểu số lớn hơn theo yêu cầu.

Ví dụ minh họa:

1. `tryAdvance` phát phần tử một lần khi chạy tuần tự.
2. Khi song song, `trySplit` có thể chia thành các phần không trùng.
3. `filter` và `map` là các thao tác trung gian lazy.
4. `sum()` là terminal operation, tiêu thụ toàn bộ kết quả được tạo.
5. Việc đổi cờ `parallel` không đổi phép tính khi các điều kiện số học và trạng thái đều phù hợp.

**Cảnh báo hiệu năng:** chỉ 100 phần tử, việc chạy song song có thể tốn thời gian hơn tuần tự. Ví dụ hướng đến tính đúng đắn, không phải benchmark.

## 15. Checklist trước khi viết nguồn Stream tùy chỉnh

1. **Đã có API nguồn phù hợp chưa?** Nếu có `stream()` hoặc `Arrays.stream`, thường không cần `StreamSupport`.
2. **tryAdvance có phát đúng một phần tử mỗi lần trả true không?** Khi hết nguồn phải trả false.
3. **trySplit có bảo toàn tất cả phần tử không trùng nhau không?** Với nguồn có thứ tự, phần trả về cần là tiền tố.
4. **estimateSize có khớp với SIZED và SUBSIZED không?** Nếu không chắc, đừng khai báo các cờ đó.
5. **SORTED có đúng không và getComparator hợp lệ không?** Khác nhau giữa thứ tự tự nhiên và comparator.
6. **Nguồn có thể thay đổi khi duyệt không?** Đánh giá IMMUTABLE, CONCURRENT và tương tác với dữ liệu ngoài.
7. **Có cần primitive Spliterator không?** `OfInt`, `OfLong`, `OfDouble` tránh boxing khi nguồn thực sự là primitive.
8. **Có cần late binding không?** Supplier có thể trì hoãn thời điểm lấy Spliterator, nhưng phải công bố characteristics đúng.
9. **Nguồn giữ tài nguyên nào?** StreamSupport không tự đóng file/Reader/socket; xác định quyền sở hữu và close handler.
10. **Stream có được tiêu thụ đúng một lần không?** Không tái dùng Stream hoặc Spliterator đã cạn.
11. **Parallel có giúp gì không?** Chỉ bật sau khi kiểm chứng chia nhánh, trạng thái và chi phí.
12. **Nguồn vô hạn có cách dừng không?** `limit` và short-circuit có thể giúp, nhưng không thay trách nhiệm close.

## 16. Câu hỏi tự kiểm tra

1. `StreamSupport.stream(spliterator, false)` trả kiểu gì? **`Stream<T>`**, dùng Spliterator đã cấp làm nguồn tuần tự.
2. `tryAdvance` trả `true` thì phải làm gì? **Gọi action đúng một lần với một phần tử**.
3. `trySplit` trả `null` có phải lỗi không? **Không**, nó báo hiện tại không thể hoặc không cần chia.
4. Với `ORDERED`, nhánh do `trySplit` trả về nên chứa phần nào? **Tiền tố** của các phần tử còn lại.
5. Vì sao không được dùng cùng Spliterator đã duyệt hết cho lượt thứ hai? **Nó đã giữ trạng thái tiêu thụ**, không tự đặt lại cursor.
6. `SIZED` có được khai báo nếu chỉ đoán độ dài nguồn không? **Không**, khi công bố SIZED phải bảo đảm kích thước chính xác theo hợp đồng.
7. `CONCURRENT` của Spliterator có đồng nghĩa với `Collector.Characteristics.CONCURRENT` không? **Không**, một bên mô tả nguồn, bên kia mô tả tích lũy kết quả.
8. Vì sao `IntRangeSpliterator.getComparator()` trả `null`? **Vì** nguồn được đánh dấu SORTED theo thứ tự tự nhiên.
9. Cách tạo primitive stream từ `Spliterator.OfInt` là gì? **`StreamSupport.intStream(spliterator, parallel)`**.
10. Có nên thêm `parallel = true` cho mọi nguồn không? **Không**, cần nguồn chia được và phép toán đủ nặng để đáng chi phí.
11. Overload Supplier giúp gì? **Hoãn việc lấy Spliterator cho đến khi terminal operation bắt đầu**.
12. StreamSupport có tự đóng Reader do Spliterator đọc không? **Không**, phải quản lý nguồn và quyền sở hữu tài nguyên.
13. Khi dùng `spliteratorUnknownSize`, có nên khai báo `SUBSIZED` không? **Không**, kích thước nguồn không được biết trước.
14. `StreamSupport.stream(list.spliterator(), false)` có luôn tốt hơn `list.stream()` không? **Không**, với List thường dùng `stream()` trực tiếp.
15. Nếu `trySplit` tạo hai phần có chồng lặp, kết quả `count()` và `sum()` sẽ ra sao? **Có thể đếm hoặc cộng trùng**, vi phạm hợp đồng Spliterator.

**Nguyên tắc áp dụng:** `StreamSupport` là cầu nối đưa **Spliterator của một nguồn tự định nghĩa** vào Java Stream API, không phải công cụ thay thế mọi factory Stream chuẩn. Hãy đảm bảo `tryAdvance` phát đúng phần tử, `trySplit` chia không trùng và giữ thứ tự khi được cam kết, công bố `characteristics` đúng sự thật, và quản lý tài nguyên bên ngoài rõ ràng. Chỉ chuyển sang parallel khi nguồn thật sự có khả năng chia an toàn và chi phí xử lý đủ để bù overhead.
