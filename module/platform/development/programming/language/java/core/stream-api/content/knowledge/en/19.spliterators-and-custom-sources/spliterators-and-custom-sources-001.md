# Vai trò của Spliterator trong duyệt và chia nguồn

## 1. Spliterator nằm ở đâu trong Java Stream API?

Trong **JAVA_STREAM_API**, lập trình viên thường xây dựng pipeline bằng `filter`, `map`, `reduce` và `collect`, nhưng ít khi phải tự viết vòng lặp đọc từng phần tử. Việc lấy dữ liệu từ một `List`, một mảng hay một nguồn tự định nghĩa được Stream API tổ chức qua một giao diện nền tảng: **`java.util.Spliterator<T>`**.

Tên `Spliterator` ghép từ *split* (chia) và *iterator* (duyệt). Nó có hai trách nhiệm chính:

1. **Duyệt phần tử:** lần lượt cung cấp phần tử cho một `Consumer` khi được yêu cầu.
2. **Chia nguồn:** tách phần việc còn lại thành các phần có thể được duyệt độc lập, để hệ thống có cơ hội thực thi song song.

Ngoài ra, Spliterator còn **mô tả đặc tính của nguồn**, chẳng hạn nguồn có thứ tự hay không, có biết chính xác kích thước hay không, có phần tử trùng hay `null` hay không. Những thông tin này giúp Stream API lựa chọn cách thực thi phù hợp.

~~~text
                List / Set / mảng / nguồn tùy chỉnh
                              │
                              ▼
                         Spliterator
                ┌─────────────┼──────────────┐
                ▼             ▼              ▼
           tryAdvance     trySplit()    characteristics()
           duyệt phần tử  chia phần     khai báo tính chất
                │             │              │
                └─────────────┴──────────────┘
                              │
                              ▼
                  StreamSupport / Stream API
                              │
                      filter → map → ...
                              │
                    collect / reduce / sum
~~~

**Phân biệt quan trọng:** Spliterator không phải một terminal operation và cũng không phải phép biến đổi như `map`. Nó là **cơ chế truy cập và phân chia nguồn** phía dưới pipeline. Nếu nguồn được chia tốt, parallel stream có thể xử lý các phần độc lập; nếu không chia được, chỉ gọi `parallel()` không tự biến bài toán thành nhiều phần việc hữu ích.

Bài thuộc chương **Spliterator và nguồn tự định nghĩa**; ví dụ dùng Java 17+ và tập trung vào ngữ nghĩa duyệt/chia nguồn, hợp đồng đặc tính, hiệu năng và vòng đời dữ liệu.

## 2. Spliterator so với Iterator và Stream

`Iterator<T>` thường chỉ cung cấp thao tác lấy phần tử tiếp theo. `Spliterator<T>` bổ sung khả năng chia công việc và thông báo đặc tính nguồn.

| Khía cạnh | `Iterator<T>` | `Spliterator<T>` | `Stream<T>` |
| --- | --- | --- | --- |
| Duyệt từng phần tử | `hasNext()`, `next()` | `tryAdvance(action)` | Pipeline xử lý nội bộ |
| Duyệt phần còn lại | Vòng lặp hoặc `forEachRemaining` | `forEachRemaining(action)` | `forEach` / terminal khác |
| Chia nguồn | Không có API chuẩn tương ứng | `trySplit()` | Hệ thống có thể tận dụng khi parallel |
| Ước lượng kích thước còn lại | Không có hợp đồng chung | `estimateSize()` | Có thể suy ra qua nguồn/Spliterator |
| Đặc tính về thứ tự/kích thước | Không có bộ cờ chuẩn | `characteristics()` | Có thể dựa vào hoặc thay đổi thông qua operation |
| Mục tiêu | Duyệt trực tiếp | Duyệt và phân hoạch nguồn | Mô tả phép biến đổi và tổng hợp khai báo |

Không nên dùng `Spliterator` trực tiếp chỉ vì muốn viết vòng lặp thay `Iterator`. Với nhu cầu xử lý dữ liệu thông thường, `stream()` và các operation cấp cao vẫn rõ ràng hơn. Làm việc trực tiếp với Spliterator có ý nghĩa khi cần **hiểu hoặc định nghĩa nguồn**, nhất là nguồn có quy tắc chia đặc biệt.

## 3. Các phương thức cốt lõi của Spliterator

Chữ ký rút gọn:

~~~java
public interface Spliterator<T> {
    boolean tryAdvance(Consumer<? super T> action);
    void forEachRemaining(Consumer<? super T> action);
    Spliterator<T> trySplit();
    long estimateSize();
    int characteristics();

    // API liên quan:
    long getExactSizeIfKnown();
    boolean hasCharacteristics(int characteristics);
    Comparator<? super T> getComparator();
}
~~~

| Phương thức | Ý nghĩa | Giá trị hoặc tác dụng |
| --- | --- | --- |
| `tryAdvance(action)` | Nếu còn phần tử, chuyển **đúng một** phần tử vào action | `true` nếu một phần tử được chuyển; `false` nếu hết |
| `forEachRemaining(action)` | Duyệt phần tử còn lại và gọi action cho từng phần tử | Không trả kết quả |
| `trySplit()` | Cố tách một phần của công việc chưa duyệt | Trả Spliterator con hoặc `null` |
| `estimateSize()` | Ước lượng số phần tử còn lại | `long` không âm, có thể là `Long.MAX_VALUE` khi chưa biết |
| `characteristics()` | Bitmask các đặc tính được **bảo đảm** | Tổ hợp cờ `ORDERED`, `SIZED`, ... |
| `getExactSizeIfKnown()` | Kích thước chính xác nếu có `SIZED` | Số lượng còn lại, hoặc `-1` |
| `hasCharacteristics(flags)` | Kiểm tra có đủ các cờ được hỏi không | `boolean` |
| `getComparator()` | Comparator cho Spliterator có `SORTED` | Comparator, hoặc `null` nếu thứ tự tự nhiên |

`tryAdvance` và `trySplit` là hai phương thức trung tâm của bài. Một Spliterator có thể **duyệt đúng** mà không chia được; khi đó `trySplit()` có thể trả `null`. Giao diện không đòi mọi nguồn phải phân chia được hoặc chia thành hai phần bằng nhau.

## 4. Duyệt một nguồn bằng tryAdvance và forEachRemaining

### 4.1. tryAdvance: một lần gọi, tối đa một phần tử

~~~java
import java.util.List;
import java.util.Spliterator;

public class TraverseWithSpliterator {
    public static void main(String[] args) {
        Spliterator<String> cursor =
            List.of("An", "Bình", "Chi").spliterator();

        boolean first = cursor.tryAdvance(
            value -> System.out.println("Đầu tiên: " + value)
        );
        System.out.println(first); // true

        boolean second = cursor.tryAdvance(System.out::println);
        System.out.println(second); // true; đã chuyển phần tử "Bình"

        boolean third = cursor.tryAdvance(System.out::println);
        System.out.println(third); // true; đã chuyển phần tử "Chi"

        boolean done = cursor.tryAdvance(System.out::println);
        System.out.println(done); // false; không còn phần tử
    }
}
~~~

`tryAdvance` khác `Iterator.next()`: ta cung cấp **action** để Spliterator đưa phần tử vào, thay vì yêu cầu nó trả về phần tử cho người gọi. Mỗi lần trả `true`, action được gọi cho đúng một phần tử; khi trả `false`, không có phần tử nào được phát.

Nếu `action` là `null`, Spliterator có thể ném `NullPointerException` khi được dùng để xử lý phần tử. Để code tự định nghĩa dễ dự đoán, nên kiểm tra `Objects.requireNonNull(action)` trước khi gọi action.

### 4.2. forEachRemaining: duyệt toàn bộ phần còn lại

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> cursor =
    List.of("A", "B", "C", "D").spliterator();

cursor.tryAdvance(System.out::println); // A

cursor.forEachRemaining(System.out::println);
// B
// C
// D
~~~

`forEachRemaining` được định nghĩa mặc định qua các lần gọi `tryAdvance`, tuy nhiên một implementation có thể tối ưu cách duyệt hàng loạt.

**Quan trọng:** Spliterator là bộ duyệt có **trạng thái tiến lên**. Sau khi `tryAdvance` hoặc `forEachRemaining` tiêu thụ một phần, các lần duyệt sau chỉ thấy phần **chưa tiêu thụ**. Muốn duyệt lại từ đầu, thường phải xin một Spliterator mới từ nguồn.

### 4.3. Không nhầm side effect với kết quả pipeline

Mục tiêu của ví dụ trên là quan sát cách duyệt. Trong pipeline thực, không dựa vào việc callback của `peek` hay `map` chắc chắn được gọi cho từng phần tử để ghi audit hoặc thực hiện nghiệp vụ. Stream có thể kết thúc sớm hoặc tối ưu các bước trung gian; việc quản lý tác dụng phụ cần được thiết kế riêng.

## 5. Chia nguồn bằng trySplit

`trySplit()` có thể tạo **một Spliterator mới** bao phủ một phần các phần tử chưa duyệt. Spliterator ban đầu tiếp tục đại diện cho phần còn lại.

~~~text
Trước chia:
     original = [A, B, C, D, E, F, G, H]

Gọi original.trySplit()
                 │
                 ├── prefix = [A, B, C, D]
                 └── original còn [E, F, G, H]

Có thể tiếp tục chia:
     prefix.trySplit()  → [A, B] + [C, D]
     original.trySplit() → [E, F] + [G, H]
~~~

Đây là **một kiểu chia minh họa**. API không cam kết chia chính xác ở giữa, không cam kết luôn chia được, và không cam kết số lần chia cụ thể. Với Spliterator có `ORDERED`, Spliterator được trả về phải bao phủ một **tiền tố** của phần tử chưa duyệt theo encounter order, còn đối tượng gốc giữ phần tiếp theo.

### 5.1. Ví dụ thực tế với List

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

public class SplitListDemo {
    public static void main(String[] args) {
        List<String> source =
            List.of("A", "B", "C", "D", "E", "F");

        Spliterator<String> remaining = source.spliterator();
        Spliterator<String> prefix = remaining.trySplit();

        List<String> result = new ArrayList<>();

        if (prefix != null) {
            prefix.forEachRemaining(result::add);
        }
        remaining.forEachRemaining(result::add);

        System.out.println(result); // [A, B, C, D, E, F]
    }
}
~~~

Khi kết hợp **tiền tố trước, phần còn lại sau**, ta nhận lại đúng encounter order của nguồn `List`. Chú ý: một số Spliterator không chia được, vì thế kiểm tra `prefix != null` là bắt buộc.

### 5.2. Một lần split không nhất thiết tạo hai thread

`trySplit()` chỉ trả ra khả năng chia công việc. Nó **không tự tạo thread**. Việc lên lịch và chạy nhiều nhánh là trách nhiệm của framework hoặc chương trình gọi. Parallel stream có thể sử dụng cơ chế chia đệ quy, nhưng không có bảo đảm “mỗi Spliterator con tương ứng một thread”.

### 5.3. Quy tắc không làm mất hoặc lặp phần tử

Với một lần chia hợp lệ, tập hợp phần tử chưa duyệt ban đầu phải được phân thành các phần **không chồng lặp và không thất lạc**. Nếu nguồn có encounter order, thứ tự nối tiền tố và phần còn lại phải biểu diễn đúng trình tự còn lại của nguồn. Đây là bất biến quan trọng nhất khi thiết kế `trySplit` cho nguồn tự định nghĩa.

## 6. Ước lượng kích thước và các characteristics

Spliterator mô tả đặc điểm nguồn qua các cờ bit. Đây là **lời cam kết về nguồn**, không phải gợi ý tùy tiện để “bật tối ưu hóa”.

| Cờ | Ý nghĩa cam kết | Tình huống điển hình |
| --- | --- | --- |
| `ORDERED` | Phần tử có encounter order xác định | `List`, dãy tăng dần |
| `DISTINCT` | Các phần tử không trùng theo `equals` | `Set`, dãy số nguyên không lặp |
| `SORTED` | Các phần tử có thứ tự theo comparator hoặc tự nhiên; đồng thời có `ORDERED` | Dãy số đã sắp |
| `SIZED` | `estimateSize()` chính xác trước khi duyệt/chia, theo hợp đồng kích thước | Mảng cố định, `List` ổn định |
| `SUBSIZED` | Mọi Spliterator con sinh từ `trySplit` đều có `SIZED` và `SUBSIZED` | Mảng, dải số chia theo khoảng |
| `NONNULL` | Phần tử do nguồn phát ra không phải `null` | `IntStream` và một số nguồn tham chiếu |
| `IMMUTABLE` | Không thể sửa cấu trúc nguồn trong khi duyệt | Nguồn dữ liệu cố định |
| `CONCURRENT` | Nguồn có cơ chế hỗ trợ sửa cấu trúc đồng thời khi duyệt | Một số collection concurrent |

Một nguồn có thể khai báo nhiều cờ:

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<Integer> spliterator =
    List.of(10, 20, 30).spliterator();

boolean ordered = spliterator.hasCharacteristics(
    Spliterator.ORDERED
);

boolean sized = spliterator.hasCharacteristics(
    Spliterator.SIZED
);

System.out.println(ordered); // true
System.out.println(sized);   // true
~~~

**Không suy diễn quá mức:**

- `ORDERED` không có nghĩa phải xử lý các callback theo thứ tự thời gian khi chạy song song; nó nói về encounter order và ngữ nghĩa kết quả của các operation có ràng buộc thứ tự.
- `SORTED` phải gắn với `ORDERED` và quy tắc comparator phù hợp. Với nguồn sắp theo thứ tự tự nhiên, `getComparator()` trả `null`. Nếu Spliterator không có `SORTED`, `getComparator()` ném `IllegalStateException`.
- `DISTINCT` phải đúng với giá trị thực tế do nguồn phát, không chỉ đúng với khóa mà ta hy vọng là duy nhất.
- `IMMUTABLE` nói về **cấu trúc nguồn**, không cam kết mọi object bên trong là bất biến sâu.
- `CONCURRENT` không làm cho lambda cập nhật `ArrayList` hoặc biến dùng chung trở nên thread-safe.
- `SIZED` và `SUBSIZED` không có nghĩa toàn bộ pipeline sau `filter` vẫn biết chính xác số phần tử đầu ra.

### 6.1. estimateSize và getExactSizeIfKnown

~~~java
import java.util.List;
import java.util.Spliterator;

Spliterator<String> s = List.of("A", "B", "C").spliterator();

System.out.println(s.estimateSize());        // 3
System.out.println(s.getExactSizeIfKnown()); // 3

s.tryAdvance(value -> {});
System.out.println(s.estimateSize());        // 2
~~~

Nếu nguồn **không có `SIZED`**, `getExactSizeIfKnown()` trả `-1`. `estimateSize()` vẫn phải cung cấp một ước lượng theo hợp đồng; có thể dùng `Long.MAX_VALUE` cho nguồn không giới hạn hoặc không biết kích thước.

Đánh dấu `SIZED` sai rất nguy hiểm: một terminal như `count()` có thể dựa vào kích thước được khai báo để tối ưu, dẫn đến số đếm sai mà không cần duyệt từng phần tử. Không bao giờ dùng `SIZED` để “giúp Stream nhanh hơn” nếu không thể bảo đảm số lượng thực sự.

## 7. Spliterator của Stream nguyên thủy

Để tránh boxing, Java cung cấp các giao diện chuyên biệt:

| Kiểu dữ liệu | Spliterator | Action của tryAdvance | Stream tương ứng |
| --- | --- | --- | --- |
| `int` | `Spliterator.OfInt` | `IntConsumer` | `IntStream` |
| `long` | `Spliterator.OfLong` | `LongConsumer` | `LongStream` |
| `double` | `Spliterator.OfDouble` | `DoubleConsumer` | `DoubleStream` |

Ví dụ lấy Spliterator từ một `IntStream`:

~~~java
import java.util.Spliterator;
import java.util.stream.IntStream;

Spliterator.OfInt cursor = IntStream.rangeClosed(1, 4)
    .spliterator();

cursor.forEachRemaining((int n) -> System.out.println(n));
// 1
// 2
// 3
// 4
~~~

Primitive Spliterator có những phương thức chuyên biệt để tránh phải tạo `Integer`, `Long` hay `Double` cho mỗi phần tử. Khi tự định nghĩa nguồn số lớn, chọn đúng Spliterator primitive có thể giảm chi phí cấp phát và cho phép nối tiếp các terminal operation như `sum`, `average`, `summaryStatistics`.

## 8. Ví dụ đầy đủ: Spliterator.OfInt cho dải số tự định nghĩa

Ta sẽ xây một Spliterator cho dải số nguyên **từ `startInclusive` đến trước `endExclusive`**, tương tự `IntStream.range`. Điểm cần quan sát là hai phần của hợp đồng:

- `tryAdvance` duyệt từng số đúng một lần.
- `trySplit` chia dải còn lại thành một **tiền tố** và phần còn lại, không tạo trùng hoặc mất số.

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.Objects;
import java.util.Spliterator;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class CustomIntRangeDemo {
    static final class RangeSpliterator implements Spliterator.OfInt {
        private int current;
        private final int fence;

        RangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start > end");
            }
            this.current = startInclusive;
            this.fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action, "action");
            if (current >= fence) {
                return false;
            }

            action.accept(current++);
            return true;
        }

        @Override
        public OfInt trySplit() {
            long remaining = estimateSize();
            if (remaining <= 1) {
                return null;
            }

            // Tính bằng long để không tràn khi current âm và fence dương.
            int middle = (int) ((long) current + remaining / 2);

            RangeSpliterator prefix =
                new RangeSpliterator(current, middle);
            current = middle; // Đối tượng gốc giữ nửa sau.

            return prefix;
        }

        @Override
        public long estimateSize() {
            return (long) fence - current;
        }

        @Override
        public int characteristics() {
            return ORDERED | DISTINCT | SORTED | SIZED
                | SUBSIZED | NONNULL | IMMUTABLE;
        }

        @Override
        public Comparator<? super Integer> getComparator() {
            // Có SORTED và sắp theo thứ tự tự nhiên.
            return null;
        }
    }

    public static void main(String[] args) {
        int[] numbers = StreamSupport.intStream(
                new RangeSpliterator(2, 11),
                true // Cho phép Stream chạy song song.
            )
            .filter(n -> n % 2 == 0)
            .toArray();

        System.out.println(Arrays.toString(numbers));
        // [2, 4, 6, 8, 10]
    }
}
~~~

### 8.1. Vì sao tryAdvance đúng?

`current` biểu diễn số tiếp theo chưa phát; `fence` là giới hạn trên, không bao gồm. Nếu `current < fence`, ta phát một số và tăng cursor. Khi `current >= fence`, hàm trả `false`. Mỗi giá trị trong dải được phát đúng một lần nếu Spliterator được dùng đúng hợp đồng.

Ví dụ `RangeSpliterator(2, 5)` phát `2, 3, 4` rồi kết thúc.

### 8.2. Vì sao trySplit đúng?

Giả sử phần còn lại là `[2, 3, 4, 5, 6, 7, 8, 9, 10]`. `middle` tính gần điểm giữa. Spliterator mới nhận `[2, middle)`, còn Spliterator gốc chuyển `current = middle` để nắm `[middle, 11)`. Hai dải **không chồng lặp**, và nối theo thứ tự trả về tiền tố rồi phần còn lại sẽ khôi phục toàn bộ dải cũ.

Nếu còn 0 hoặc 1 số, `trySplit` trả `null` vì không có lợi ích chia tiếp. Dùng `long` để tính hiệu số và điểm giữa, tránh tràn `int` nếu hai đầu dải cách xa nhau. Việc chia không tạo luồng dữ liệu trước; nó chỉ chuyển ranh giới của các phần việc chưa duyệt.

### 8.3. Vì sao các cờ characteristics hợp lệ?

- `ORDERED`: các số trong dải tăng dần.
- `DISTINCT`: không có số lặp.
- `SORTED`: theo thứ tự tự nhiên; `getComparator()` trả `null`.
- `SIZED`: `estimateSize()` luôn bằng số phần tử còn lại.
- `SUBSIZED`: các dải con đều đáp ứng `SIZED` và `SUBSIZED`.
- `NONNULL`: primitive `int` không thể là `null`.
- `IMMUTABLE`: nguồn là các khoảng số cố định, không có cấu trúc dữ liệu nền có thể sửa.

Vì các đặc tính được khai báo dựa vào đúng quy tắc sinh dữ liệu, Stream có thể sử dụng chúng để thực thi hoặc tối ưu hóa pipeline. Nếu một phiên bản tùy chỉnh sau này bỏ số hoặc đổi thứ tự, cần xem lại các cờ được công bố.

## 9. Kiểm thử việc chia: không trùng, không mất và đúng encounter order

Một cách kiểm tra đơn giản là chia thủ công trước, duyệt **Spliterator được trả về trước** rồi duyệt Spliterator gốc.

Đoạn sau đặt trong cùng lớp `CustomIntRangeDemo`, nơi có `RangeSpliterator`:

~~~java
import java.util.Arrays;
import java.util.Spliterator;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

Spliterator.OfInt remaining = new RangeSpliterator(0, 10);
Spliterator.OfInt prefix = remaining.trySplit();

int[] first = prefix == null
    ? new int[0]
    : StreamSupport.intStream(prefix, false).toArray();

int[] second = StreamSupport.intStream(remaining, false)
    .toArray();

int[] combined = IntStream.concat(
    IntStream.of(first),
    IntStream.of(second)
).toArray();

int[] expected = IntStream.range(0, 10).toArray();

if (!Arrays.equals(combined, expected)) {
    throw new AssertionError("trySplit đã mất, lặp hoặc đảo phần tử");
}

System.out.println("PASS"); // Đã tái tạo đúng dãy 0..9.
~~~

Với Spliterator này, chia một lần tạo tiền tố khoảng `[0,5)` và phần gốc khoảng `[5,10)`. Tuy nhiên, không viết test chung cho **mọi loại** Spliterator mà bắt buộc phải chia đúng ở giữa: kích thước và vị trí chia là quyền quyết định của implementation.

### Kiểm tra kết quả tuần tự và song song

~~~java
long serialSum = StreamSupport.intStream(
        new RangeSpliterator(0, 100_000),
        false
    )
    .asLongStream()
    .sum();

long parallelSum = StreamSupport.intStream(
        new RangeSpliterator(0, 100_000),
        true
    )
    .asLongStream()
    .sum();

if (serialSum != parallelSum || serialSum != 4_999_950_000L) {
    throw new AssertionError("Tổng không khớp");
}
~~~

Mỗi terminal dùng **một Spliterator mới**, vì Spliterator cũ đã tiêu thụ. `asLongStream()` chuyển sang `long` trước khi tính tổng để tránh tràn số `int`.

Những kiểm tra quan trọng khác cho nguồn tùy chỉnh: dải rỗng, dải một phần tử, các dải có số âm, ranh giới gần `Integer.MIN_VALUE` và `Integer.MAX_VALUE`, nhiều lần chia liên tiếp, cùng phép tính với các kích thước nguồn khác nhau. Các kiểm tra này cần làm trong bước QA/test chuyên biệt; ở đây ta minh họa hợp đồng thiết kế.

## 10. Nối Spliterator với StreamSupport

`StreamSupport` có các phương thức tạo Stream từ Spliterator đã có:

~~~java
Stream<T> StreamSupport.stream(
    Spliterator<T> spliterator,
    boolean parallel
);

IntStream StreamSupport.intStream(
    Spliterator.OfInt spliterator,
    boolean parallel
);
~~~

Ví dụ với List:

~~~java
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

Spliterator<String> source =
    List.of("Java", "Stream", "API").spliterator();

List<String> result = StreamSupport.stream(source, false)
    .map(String::toLowerCase)
    .toList();

System.out.println(result); // [java, stream, api]
~~~

`parallel = true` cho phép pipeline parallel; **không cam kết** sẽ nhanh hơn hay bắt buộc phải có nhiều thread thực sự xử lý dữ liệu. Tính hữu ích của parallel phụ thuộc khả năng chia, chi phí mỗi phần tử, số lõi CPU, tải hệ thống và các ràng buộc thứ tự.

### 10.1. Phiên bản nhận Supplier của Spliterator

`StreamSupport.stream(...)` và `StreamSupport.intStream(...)` còn có overload nhận **Supplier** cùng tập characteristics:

~~~java
import java.util.Spliterator;
import java.util.function.Supplier;
import java.util.stream.IntStream;
import java.util.stream.StreamSupport;

// RangeSpliterator được định nghĩa ở mục 8.
int flags = Spliterator.ORDERED | Spliterator.DISTINCT
    | Spliterator.SORTED | Spliterator.SIZED
    | Spliterator.SUBSIZED | Spliterator.NONNULL
    | Spliterator.IMMUTABLE;

Supplier<Spliterator.OfInt> factory =
    () -> new RangeSpliterator(0, 100);

IntStream values = StreamSupport.intStream(
    factory,
    flags,
    true
);

long count = values.count(); // 100
~~~

Supplier được gọi khi terminal operation bắt đầu, nên thích hợp cho những nguồn cần ràng buộc việc tạo Spliterator vào thời điểm tiêu thụ. Đặc tính truyền cho overload Supplier **phải khớp với** `characteristics()` của Spliterator mà Supplier tạo ra; khai báo sai có thể làm hành vi của Stream trở nên không xác định theo hợp đồng API.

Không dùng Supplier như cách ngầm mở nhiều kết nối hoặc lặp lại một Stream cũ: một Stream vẫn là **đối tượng dùng một lần**.

### 10.2. Các factory có sẵn từ Spliterators

Nếu dữ liệu đã nằm trong mảng, collection hoặc iterator, hãy cân nhắc API có sẵn trước khi tự viết:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Spliterator;
import java.util.Spliterators;

Iterator<String> iterator =
    List.of("A", "B", "C").iterator();

Spliterator<String> source = Spliterators.spliteratorUnknownSize(
    iterator,
    Spliterator.ORDERED
);
~~~

`spliteratorUnknownSize` bọc một Iterator có kích thước không biết trước. Đừng khai báo `SIZED` hoặc `SUBSIZED` nếu không có hợp đồng kích thước chính xác; implementation có thể chia theo các lô nội bộ, nhưng không biến nguồn thành dữ liệu được truy cập ngẫu nhiên.

Với mảng hoặc collection chuẩn, `Arrays.spliterator(...)`, `Collection.spliterator()` và các phương thức `stream()` có sẵn thường đủ cho ứng dụng. Tự viết Spliterator chỉ khi cần nguồn/chiến lược chia mà các lựa chọn chuẩn chưa mô tả đúng.

## 11. Encounter order, split và các operation phía sau

Đặc tính `ORDERED` của nguồn có ý nghĩa khi các operation phụ thuộc thứ tự:

- `findFirst()` chọn phần tử đầu tiên theo encounter order, nếu có.
- `limit(n)` trên nguồn ordered lấy `n` phần tử đầu tiên.
- `forEachOrdered` thực thi action theo encounter order nếu Stream có thứ tự.
- `sorted()` có thể thiết lập thứ tự mới ở đầu ra.
- `unordered()` **bỏ ràng buộc** về encounter order; nó không tạo phép xáo trộn ngẫu nhiên.

~~~java
import java.util.List;
import java.util.stream.StreamSupport;

// RangeSpliterator từ mục 8.
List<Integer> firstFive = StreamSupport.intStream(
        new RangeSpliterator(0, 100),
        true
    )
    .limit(5)
    .boxed()
    .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

Vì nguồn khai báo `ORDERED` và `trySplit` trả tiền tố, pipeline có thể giữ ngữ nghĩa “5 phần tử đầu”. Nếu bỏ `ORDERED` hoặc triển khai `trySplit` sai (ví dụ trẻ em nhận một đoạn không đúng tiền tố mà vẫn báo `ORDERED`), những operation yêu cầu thứ tự có thể cho kết quả sai.

### 11.1. Ràng buộc thứ tự có thể hạn chế tốc độ song song

Với parallel stream, `limit` và `skip` trên nguồn ordered có thể yêu cầu phối hợp để xác định chính xác tiền tố. Nếu nghiệp vụ cho phép “lấy bất kỳ 5 phần tử” thì `unordered()` có thể nới ràng buộc, nhưng sẽ **thay đổi ngữ nghĩa**:

~~~java
List<Integer> anyFive = StreamSupport.intStream(
        new RangeSpliterator(0, 100),
        true
    )
    .unordered()
    .limit(5)
    .boxed()
    .toList();

// Có 5 số thuộc dải, không cam kết là 0..4.
~~~

Không dùng `unordered().limit(...)` cho phân trang, lấy bản ghi sớm nhất hay top-N theo tiêu chí. Muốn top-N, cần sắp xếp theo tiêu chí rồi mới giới hạn.

## 12. Late-binding, fail-fast và việc thay đổi nguồn

Một số Spliterator là **late-binding**: chúng chỉ ràng buộc vào trạng thái nguồn tại lần duyệt/chia/tính kích thước đầu tiên. Một số implementation khác ràng buộc sớm hơn. Với collection thông thường, nếu có sửa đổi cấu trúc không được cho phép **sau khi đã bắt đầu duyệt**, kết quả có thể không xác định hoặc bị phát hiện bằng ngoại lệ.

Ví dụ `ArrayList` có Spliterator late-binding, đồng thời có cơ chế phát hiện sửa đổi cấu trúc kiểu fail-fast theo hướng *best effort*:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Spliterator;

ArrayList<String> source = new ArrayList<>(List.of("A"));

Spliterator<String> s = source.spliterator();
source.add("B"); // Trước khi bắt đầu sử dụng s.

s.forEachRemaining(System.out::println);
// Với ArrayList, lần ràng buộc muộn sẽ nhìn thấy A và B.
~~~

Đây là đặc điểm của `ArrayList`, **không phải bảo đảm chung cho mọi Spliterator**. Khi đã bắt đầu duyệt, không sửa cấu trúc nguồn nếu hợp đồng nguồn không cho phép. Đặc biệt, fail-fast không phải cơ chế đồng bộ hoặc kiểm tra tính đúng đắn đáng tin cậy; nó chỉ hỗ trợ phát hiện một số lỗi sử dụng.

**`IMMUTABLE`** và **`CONCURRENT`** có ý nghĩa khác nhau:

- `IMMUTABLE`: nguồn không bị sửa cấu trúc trong lúc duyệt; không đồng nghĩa phần tử con bất biến sâu.
- `CONCURRENT`: nguồn hỗ trợ sửa cấu trúc đồng thời với traversal theo hợp đồng riêng của nguồn; không suy ra encounter order hay snapshot cố định.
- Nguồn không có hai cờ trên thường cần tránh can thiệp cấu trúc từ bên ngoài trong lúc pipeline xử lý.

Khi tạo Stream từ một nguồn mutable tùy chỉnh, overload `StreamSupport.stream(supplier, characteristics, parallel)` có thể giúp hoãn thời điểm nhận Spliterator. Tuy nhiên, **nó không làm một nguồn vốn không thread-safe trở thành an toàn**; cần tuân thủ quy tắc sửa đổi nguồn và đồng bộ của kiểu dữ liệu.

## 13. Chất lượng chia nguồn quyết định hiệu quả parallel stream

Một Spliterator có `trySplit` hợp lệ chưa chắc tạo parallel stream nhanh.

### Các yếu tố ảnh hưởng

| Yếu tố | Hệ quả có thể gặp |
| --- | --- |
| `trySplit()` luôn trả `null` | Không tạo được nhiều phần việc từ nguồn này |
| Chia quá lệch, một nhánh rất lớn | Khó cân bằng tải giữa các worker |
| Chia thành quá nhiều phần rất nhỏ | Overhead tạo/quản lý tác vụ tăng |
| `estimateSize()` không hợp lý | Framework khó chọn ngưỡng chia tốt |
| `ORDERED` khi bài toán không cần thứ tự | Có thể làm một số operation như `limit`/`distinct` tốn phối hợp hơn |
| Mapper thực hiện I/O chậm hoặc ghi state chung | Tranh chấp/tắc nghẽn có thể lấn át lợi ích chia nguồn |
| Nguồn nhỏ, phép biến đổi rẻ | Parallel overhead có thể lớn hơn chi phí xử lý |

Ví dụ `RangeSpliterator` chia gần đôi phần còn lại mỗi lần, một chiến lược thường phù hợp với dữ liệu có chi phí xử lý tương đối đồng đều. Với dữ liệu có chi phí rất lệch theo phần tử, chia đều **số lượng** chưa chắc cân bằng **thời gian xử lý**.

### Không cố tối ưu bằng cách khai báo sai characteristics

Việc thêm `SIZED`, `DISTINCT` hoặc `SORTED` dù nguồn không đáp ứng hợp đồng có thể khiến Stream **tính sai** chứ không chỉ “hiển thị sai metadata”. Ví dụ, `count()` có thể bỏ qua việc duyệt nếu số lượng đã biết; `distinct()` có thể tận dụng `DISTINCT` để tránh công việc; `sorted()` có thể tận dụng `SORTED`. Chỉ khai báo những gì implementation thực sự bảo đảm.

## 14. Nguồn gắn với tài nguyên: Spliterator không tự đóng file

Spliterator mô tả **duyệt và chia**, không phải giao thức quản lý tài nguyên. Nếu Stream nguồn mở file, socket hoặc cursor cơ sở dữ liệu, chỉ hoàn thành terminal operation chưa chắc tự đóng tài nguyên.

Với file, dùng API và cơ chế đóng chuẩn:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileStreamExample {
    static long countNonBlankLines(Path path) throws IOException {
        try (Stream<String> lines = Files.lines(path)) {
            return lines
                .filter(line -> !line.isBlank())
                .count();
        }
    }
}
~~~

`Files.lines(path)` trả một Stream gắn với tài nguyên file cần đóng bằng `try-with-resources`. Không tự xây Spliterator đọc file chỉ để thử parallel mà bỏ qua quy tắc đóng reader, exception I/O và an toàn truy cập nguồn.

Khi một nguồn tùy chỉnh phải mở và đóng tài nguyên, cần thiết kế rõ **ai sở hữu tài nguyên**, **ai đóng**, **khi nào đóng**, và liệu nhiều nhánh sau `trySplit` có thể sử dụng an toàn cùng một nguồn hay không. `StreamSupport.stream(...)` không tự phát minh quy tắc đóng cho nguồn; có thể tích hợp đóng qua `Stream.onClose(...)` và `try-with-resources` nếu thiết kế cho phép.

## 15. Những sai lầm thường gặp khi tự viết hoặc sử dụng Spliterator

### Sai lầm 1: tryAdvance trả true nhưng không phát phần tử

~~~java
// KHÔNG ĐÚNG hợp đồng:
// public boolean tryAdvance(Consumer<? super T> action) {
//     return true; // Không gọi action.accept(...)
// }
~~~

Nếu trả `true`, phải chuyển đúng một phần tử cho action. Nếu đã hết, trả `false`. Không dùng `true` để biểu diễn “vẫn còn khả năng sinh phần tử trong tương lai” khi chưa phát gì.

### Sai lầm 2: trySplit làm mất hoặc lặp dữ liệu

~~~text
Nguồn chưa duyệt: [0, 1, 2, 3, 4, 5]

Sai:   child = [0, 1, 2, 3]   original = [3, 4, 5]
                                        ↑ lặp số 3

Sai:   child = [0, 1]         original = [3, 4, 5]
                                ↑ mất số 2

Đúng:  child = [0, 1, 2]      original = [3, 4, 5]
~~~

Với nguồn ordered, Spliterator con trả về còn phải là **tiền tố đúng thứ tự** của phần chưa duyệt. Khi nhiều lần split, bảo đảm này phải tiếp tục đúng đệ quy.

### Sai lầm 3: chia cùng một Spliterator từ nhiều thread

Spliterator nói chung **không được bảo đảm thread-safe** cho thao tác duyệt/chia đồng thời trên **cùng một instance**. Mẫu dùng đúng là phân hoạch trước, rồi mỗi nhánh được quản lý riêng; không gọi `tryAdvance` hoặc `trySplit` đồng thời trên một cursor dùng chung nếu implementation không có hợp đồng hỗ trợ điều đó.

### Sai lầm 4: khai báo SIZED cho nguồn không biết kích thước

~~~java
// Không khai báo SIZED nếu estimateSize() chỉ là một dự đoán.
// Không khai báo SUBSIZED nếu Spliterator con không có kích thước chính xác.
~~~

`SIZED` là cam kết số lượng, không phải “kích thước có vẻ gần đúng”. Sửa bằng cách chỉ khai báo đặc tính thực sự có và trả ước lượng phù hợp.

### Sai lầm 5: khai báo SORTED nhưng không xử lý getComparator

Spliterator có `SORTED` phải có quy tắc thứ tự đúng và hỗ trợ `getComparator()`: trả `null` cho natural ordering hoặc trả comparator tương ứng. Đừng đánh dấu `SORTED` cho nguồn chỉ “thường trông đã sắp”.

### Sai lầm 6: dùng parallel để sửa source mutable

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

// Sai: sửa cấu trúc nguồn trong khi Stream đang duyệt nó.
// source.parallelStream().forEach(source::add);
~~~

Việc can thiệp nguồn trong pipeline có thể gây lỗi, bỏ dữ liệu, lặp dữ liệu hoặc hành vi không xác định. `CONCURRENT` chỉ áp dụng khi **chính nguồn** hỗ trợ sửa đồng thời theo hợp đồng riêng, không hợp thức hóa mọi callback có tác dụng phụ.

### Sai lầm 7: nghĩ Spliterator tự động chạy song song

`trySplit` chỉ cho phép tách. Để tạo parallel stream từ Spliterator, dùng `StreamSupport.stream(s, true)` hoặc `StreamSupport.intStream(s, true)`; framework mới quyết định cách chạy. Và nếu nguồn không thể chia, chỉ bật cờ parallel không đem lại công việc độc lập.

### Sai lầm 8: tiêu thụ Spliterator trước rồi muốn tạo Stream đầy đủ từ nó

~~~java
import java.util.List;
import java.util.Spliterator;
import java.util.stream.StreamSupport;

Spliterator<Integer> source = List.of(1, 2, 3).spliterator();
source.tryAdvance(value -> {}); // Đã tiêu thụ 1.

List<Integer> remaining = StreamSupport.stream(source, false)
    .toList();

// remaining chỉ còn [2, 3], không phải [1, 2, 3].
~~~

Một Spliterator không tự rewind. Khi cần tái duyệt từ đầu, lấy Spliterator mới từ nguồn hoặc thiết kế một factory cho các phiên chạy độc lập.

## 16. Cách chọn tiếp cận cho nguồn dữ liệu

| Nhu cầu | Giải pháp thường nên chọn |
| --- | --- |
| Xử lý `List`, `Set` hoặc mảng thông thường | Dùng `collection.stream()` hoặc `Arrays.stream(...)` |
| Duyệt trực tiếp một lần, không cần pipeline | `Iterator` hoặc vòng lặp |
| Tạo Stream từ một Spliterator tự định nghĩa | `StreamSupport.stream(s, parallel)` |
| Nguồn sinh số `int`, `long`, `double` | `Spliterator.OfInt/OfLong/OfDouble` hoặc primitive Stream có sẵn |
| Bọc Iterator chưa biết số phần tử | `Spliterators.spliteratorUnknownSize(...)` |
| Cần hỗ trợ song song từ nguồn tùy chỉnh | Thiết kế `trySplit`, kích thước và đặc tính đúng; benchmark |
| Cần bảo đảm thứ tự lấy phần tử | Nguồn có `ORDERED`, `trySplit` trả tiền tố, giữ ràng buộc thứ tự trong pipeline |
| Nguồn gắn với file/tài nguyên I/O | API đã quản lý tài nguyên và `try-with-resources`; tránh tự chia nguồn khi không an toàn |
| Chỉ cần lọc/map/gộp dữ liệu thông thường | Ưu tiên các operation cấp cao thay vì tự viết Spliterator |

## 17. Câu hỏi tự kiểm tra

1. **Spliterator giải quyết hai trách nhiệm nào?** Duyệt phần tử và chia phần chưa duyệt thành các phần độc lập.
2. **`tryAdvance(action)` trả `true` thì phải xảy ra điều gì?** Action được gọi để nhận đúng một phần tử.
3. **`trySplit()` trả `null` có nghĩa là nguồn đã hết không?** Không nhất thiết; có thể còn phần tử nhưng nguồn không thể hoặc không muốn chia tiếp.
4. **Với `ORDERED`, Spliterator trả từ `trySplit` phải đại diện cho phần nào?** Một tiền tố của phần tử chưa duyệt.
5. **`estimateSize()` trả `Long.MAX_VALUE` có nghĩa nguồn chắc chắn có từng đó phần tử không?** Không. Nó có thể đại diện cho ước lượng chưa biết hoặc nguồn vô hạn.
6. **`getExactSizeIfKnown()` trả gì nếu không có `SIZED`?** `-1`.
7. **`SIZED` khác `SUBSIZED` thế nào?** `SIZED` cam kết kích thước chính xác ở Spliterator hiện tại; `SUBSIZED` mở rộng cam kết này tới các Spliterator con do split tạo ra.
8. **`SORTED` có thể dùng với nguồn unordered không?** Không. `SORTED` bao hàm `ORDERED`.
9. **Với Spliterator có `SORTED` theo thứ tự tự nhiên, `getComparator()` trả gì?** `null`.
10. **`Spliterator.OfInt` có lợi thế nào?** Duyệt số `int` qua `IntConsumer`, tránh boxing cho từng phần tử.
11. **Gọi `parallel()` có đảm bảo nhiều thread làm việc hiệu quả nếu Spliterator không chia được không?** Không.
12. **Tại sao khai báo `DISTINCT` hoặc `SIZED` sai có thể làm chương trình tính sai?** Stream có thể tin đặc tính và bỏ qua một số bước xử lý/duyệt.
13. **Một Spliterator đã dùng một phần có tự bắt đầu lại được không?** Không; cần nguồn hoặc Spliterator mới.
14. **`CONCURRENT` có khiến callback ghi vào `ArrayList` dùng chung an toàn không?** Không; đặc tính đó nói về hợp đồng nguồn.
15. **`StreamSupport.stream(s, true)` có tự đóng file do nguồn tùy chỉnh mở không?** Không; việc quản lý tài nguyên phải được thiết kế và đóng rõ ràng.

**Ghi nhớ:** `Spliterator` là cầu nối giữa **nguồn dữ liệu** và khả năng **duyệt, phân hoạch** của Java Stream API. `tryAdvance` phát từng phần tử, `trySplit` tạo công việc độc lập, còn `estimateSize` và `characteristics` mô tả những bảo đảm mà framework có thể tận dụng. Chỉ tự định nghĩa Spliterator khi thật sự cần, bảo đảm không mất/trùng phần tử, khai báo đặc tính trung thực và luôn kiểm soát thứ tự, trạng thái nguồn, tài nguyên và hiệu năng trước khi song song hóa.
