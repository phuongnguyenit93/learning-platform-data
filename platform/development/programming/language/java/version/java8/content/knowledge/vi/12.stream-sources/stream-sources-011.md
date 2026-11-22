# StreamSupport và nguồn Stream tùy biến trong Java

`java.util.stream.StreamSupport` là cầu nối giữa **nguồn dữ liệu có thể duyệt** và **Stream API**. Khi bạn đã có `Collection` hoặc mảng, thường nên gọi `collection.stream()` hoặc `Arrays.stream(array)`. Nhưng khi dữ liệu đến từ một cấu trúc tự thiết kế, bộ sinh hữu hạn, một iterator đặc biệt hoặc nguồn cần chia thành các khối độc lập, `StreamSupport` và `Spliterator` giúp bạn khai báo cách lấy phần tử, thứ tự, kích thước và khả năng tách việc để tận dụng các toán tử `map`, `filter`, `reduce`, `collect`.

**Trọng tâm của bài:** biết **khi nào cần nguồn tùy biến**, xây `Spliterator` đúng contract, tránh khai sai các characteristics, hiểu sự khác nhau giữa tạo stream và thực sự đọc dữ liệu, kiểm soát tài nguyên và cân nhắc parallel stream. Các API này tồn tại từ Java 8 và vẫn phù hợp với JDK hiện đại. Ví dụ hoàn chỉnh chạy trên **Java 17+**, không phụ thuộc thư viện ngoài.

## 1. StreamSupport giải quyết bài toán nào?

Giả sử ứng dụng có dữ liệu được tạo theo quy tắc, hoặc một nguồn chỉ có thể trả bản ghi lần lượt. Bạn muốn thao tác theo pipeline:

```java
long count = sourceStream
        .filter(item -> item.isActive())
        .count();
```

Đây là **mã ý tưởng**, trong đó `sourceStream` và `item` là các thành phần của ứng dụng chứ không phải chương trình độc lập. Câu hỏi không nằm ở `filter` hay `count`: **làm sao tạo nguồn Stream đúng nghĩa** từ dữ liệu không phải một Collection chuẩn?

Các tầng liên quan:

```text
Nguồn nghiệp vụ
   |
   | mô tả cách duyệt, phân chia, đếm, xác định thứ tự
   v
Spliterator<T> hoặc Spliterator.OfInt/OfLong/OfDouble
   |
   | StreamSupport.stream(...) / intStream(...), ...
   v
Stream pipeline: filter -> map -> distinct -> ...
   |
   v
Terminal operation: toList / sum / count / reduce / ...
```

`StreamSupport` **không phải** một kho dữ liệu và cũng không tự làm nguồn tùy biến trở nên thread-safe. Nó tạo stream từ traversal contract của `Spliterator`. Độ chính xác, thứ tự và tính an toàn của pipeline phụ thuộc trực tiếp vào contract đó.

### Khi không cần StreamSupport

Nếu đã có API chuẩn đơn giản hơn, ưu tiên API đó:

| Nguồn | Cách thường phù hợp | Vì sao |
| --- | --- | --- |
| `List<T>`, `Set<T>` | `collection.stream()` | Collection đã cung cấp spliterator |
| Mảng object hoặc `int[]`/`long[]`/`double[]` | `Arrays.stream(array)` | Đúng overload, ít code |
| Dãy số nguyên hữu hạn | `IntStream.range(start,end)` | JDK đã tối ưu nguồn theo chỉ số |
| Một vài giá trị | `Stream.of(a,b,c)` | Rõ ràng, không cần adapter |
| Nguồn phát sinh bằng generator | `Stream.generate(supplier)` hoặc `Stream.iterate(...)` | Đúng khi phù hợp semantics |
| File văn bản theo dòng | `Files.lines(path)` trong try-with-resources | JDK quản lý nguồn dòng và tài nguyên |
| `Iterator<T>` từ API cũ | `Spliterators.spliteratorUnknownSize(...)` + `StreamSupport.stream(...)` | Có adapter chính thức |
| Bộ sinh có đặc tính riêng, chia khối được | `Spliterator` tùy biến + `StreamSupport` | Chỉ khi thực sự cần kiểm soát traversal |

**Đừng tự viết `Spliterator` chỉ để đổi `List` thành stream.** Mỗi implementation tùy biến phải thỏa những luật tinh tế về `tryAdvance`, `trySplit` và characteristics; dùng chuẩn của JDK khi có thể sẽ giảm nguy cơ lỗi.

## 2. Các overload cốt lõi của StreamSupport

Có hai nhóm nguồn: **reference streams** và **primitive streams**.

### Tạo Stream<T> từ Spliterator<T>

```java
static <T> Stream<T> stream(
        Spliterator<T> spliterator,
        boolean parallel)
```

Đây là **chữ ký API được rút gọn để giải thích**, không phải phương thức người học tự khai báo. Tham số `parallel` là `false` nếu muốn pipeline ở chế độ sequential và `true` nếu muốn pipeline ở chế độ parallel.

Ví dụ:

```java
List<String> words = List.of("alpha", "beta", "gamma");

Stream<String> stream = StreamSupport.stream(
        words.spliterator(), false);

List<String> upper = stream.map(String::toUpperCase).toList();
System.out.println(upper); // [ALPHA, BETA, GAMMA]
```

Đây là **mảnh minh họa** cần imports `java.util.List`, `java.util.stream.Stream` và `StreamSupport`. `List.spliterator()` vốn đã có sẵn nên ví dụ chỉ giải thích cơ chế; trong thực tế, `words.stream()` ngắn hơn và dễ đọc hơn.

### Tạo stream bằng Supplier<Spliterator<T>>

```java
static <T> Stream<T> stream(
        Supplier<? extends Spliterator<T>> supplier,
        int characteristics,
        boolean parallel)
```

Đây cũng là **chữ ký API rút gọn**. Khác biệt quan trọng: `supplier` được gọi **không quá một lần**, và chỉ **sau khi terminal operation bắt đầu**. Điều này giúp trì hoãn việc lấy nguồn/snapshot/bộ đọc tới thời điểm stream được tiêu thụ.

Tham số `characteristics` phải phản ánh chính xác đặc tính mà spliterator do supplier trả về báo cáo. Khai báo không đúng có thể dẫn đến hành vi không xác định theo contract. Đừng viết `SIZED` vì “nghĩ chắc sẽ có vài phần tử”, hoặc `IMMUTABLE` nếu nguồn có thể thay đổi.

### Overload cho primitive stream

```java
IntStream ints = StreamSupport.intStream(
        intSpliterator, false);

LongStream longs = StreamSupport.longStream(
        longSpliterator, false);

DoubleStream doubles = StreamSupport.doubleStream(
        doubleSpliterator, false);
```

Đây là các mảnh minh họa, các biến `intSpliterator`, `longSpliterator`, `doubleSpliterator` cần được định nghĩa. Mỗi nhóm cũng có overload nhận supplier và characteristics. Kiểu nguồn cần tương ứng: `Spliterator.OfInt`, `OfLong` hoặc `OfDouble`.

Không có `StreamSupport.byteStream(...)` hay `StreamSupport.booleanStream(...)` trong thư viện chuẩn. Khi dữ liệu được biểu diễn bằng `byte`/`short`/`char`, thường dùng `IntStream` hoặc một nguồn object, tùy ngữ nghĩa.

## 3. Spliterator khác Iterator ở đâu?

`Iterator<T>` chủ yếu trả lời câu hỏi “lấy phần tử kế tiếp” bằng `hasNext()` và `next()`. `Spliterator<T>` mô tả thêm **khả năng chia nguồn** thành các phần để xử lý, ước lượng số phần tử còn lại và một số characteristics.

Các method chính:

| Method | Vai trò |
| --- | --- |
| `tryAdvance(Consumer<? super T>)` | Nếu còn phần tử: đưa một phần tử vào action và trả `true`; hết thì trả `false` |
| `forEachRemaining(Consumer<? super T>)` | Duyệt các phần tử còn lại; interface có implementation mặc định |
| `trySplit()` | Tách một phần công việc sang spliterator mới, hoặc `null` nếu không chia được |
| `estimateSize()` | Ước lượng số phần tử còn lại, dùng `long` |
| `characteristics()` | Bit flags mô tả ORDERED, SIZED, DISTINCT... |
| `hasCharacteristics(mask)` | Kiểm tra có đầy đủ các characteristics trong mask |
| `getExactSizeIfKnown()` | Trả kích thước khi `SIZED` được báo cáo, nếu không là `-1` |
| `getComparator()` | Comparator khi spliterator `SORTED`; thông thường ném exception nếu không SORTED |

Một spliterator có thể **không hỗ trợ chia**. `trySplit() == null` vẫn hợp lệ: nó chỉ nghĩa là không có phần công việc để tách tại thời điểm đó. Nhưng một nguồn khó split có thể làm `parallelStream` không đạt hiệu quả mong muốn.

### Vì sao method tên “tryAdvance”?

`tryAdvance` vừa kiểm tra **còn phần tử** vừa bàn giao phần tử tiếp theo cho `Consumer`. Nó phải trả về:

- `true` **chỉ khi** consumer đã được gọi với một phần tử;
- `false` khi đã hết phần tử và không gọi consumer.

Một spliterator hỏng có thể trả `true` mãi dù không tạo phần tử, lặp vô hạn, hoặc bỏ sót/nhân đôi phần tử khi split. Những lỗi này lan tới mọi terminal operation — `count`, `toArray`, `findFirst` và cả quá trình chạy song song.

## 4. Cách hoạt động của trySplit()

Một spliterator có thể giữ một khoảng chỉ số nửa mở `[cursor, fence)`. Khi tách, nó trả **một spliterator mới giữ phần đầu** và tự giữ phần còn lại:

```text
Ban đầu: [0, 8)

trySplit()
    return [0, 4)
    this   [4, 8)

Tách tiếp:
    [0, 2), [2, 4), [4, 6), [6, 8)
```

Đối với ordered source, phần spliterator trả về cần là **strict prefix** của các phần tử còn lại; source hiện tại giữ suffix. Không chia bằng cách hai spliterators cùng đọc **một chỉ số** hoặc cùng tăng **một biến cursor không đồng bộ**.

### Ba bất biến quan trọng

1. **Không mất phần tử:** mọi phần tử ban đầu thuộc về đúng một nhánh sau split.
2. **Không lặp phần tử:** hai spliterators sau split không có phạm vi giao nhau.
3. **Thứ tự có nghĩa:** nếu báo `ORDERED` thì các nhánh được chia phải tôn trọng encounter order; split trả prefix theo contract.

Đây là các thuộc tính cần test bằng cách split nhiều lần rồi ghép/traversal, không chỉ test `tryAdvance` tuần tự.

## 5. Characteristics phải phản ánh sự thật

`Spliterator.characteristics()` trả bit mask của các cờ. Những cờ này có thể giúp Stream API thực hiện tối ưu hóa, đồng thời tạo ra **cam kết có thể ảnh hưởng kết quả**. Khai sai nguy hiểm hơn thiếu tối ưu.

| Cờ | Ý nghĩa thực tế |
| --- | --- |
| `ORDERED` | Có encounter order được định nghĩa |
| `DISTINCT` | Không có hai phần tử bằng nhau theo `equals` |
| `SORTED` | Encounter order theo comparator hoặc thứ tự tự nhiên |
| `SIZED` | `estimateSize()` chính xác cho phạm vi spliterator hiện tại khi được quan sát theo contract |
| `SUBSIZED` | Mọi spliterators sinh từ `trySplit` đều `SIZED` và `SUBSIZED` |
| `NONNULL` | Không có phần tử null |
| `IMMUTABLE` | Nguồn cấu trúc không thể bị sửa trong quá trình traversal theo contract |
| `CONCURRENT` | Nguồn hỗ trợ chỉnh sửa cấu trúc đồng thời an toàn theo ngữ nghĩa riêng |
| `SORTED` đi kèm comparator | `getComparator()` phải phù hợp; nếu natural order, có thể trả `null` |

Các dòng trên tóm lược. Cần hiểu **điều kiện cụ thể của từng cờ** trước khi khai báo.

### ORDERED: không phải “đã sorted”

Một nguồn mang các phần tử `[9,1,7]` vẫn có `ORDERED` nếu thứ tự `9 → 1 → 7` là encounter order rõ ràng. `SORTED` là cam kết mạnh hơn: các phần tử xuất hiện theo thứ tự comparator/natural order.

Khai `SORTED` cho `[9,1,7]` là sai ngay cả khi pipeline sau đó sẽ gọi `sorted()`. Cờ mô tả **spliterator ban đầu**, không mô tả kết quả bạn muốn.

### SIZED và SUBSIZED: phải cẩn thận với filter

Nếu source là một danh sách cố định có `n` phần tử chưa duyệt, nó có thể biết chính xác `estimateSize()==n`. Nhưng một nguồn đang duyệt records và loại những records không thỏa điều kiện **ngay trong `tryAdvance`** thường không biết số phần tử output cuối, nên không được tự báo `SIZED` chỉ dựa trên số record đầu vào.

`SUBSIZED` là cam kết cho **mọi nhánh con**, không chỉ nhánh gốc. Nếu bạn tính `estimateSize()` sai sau split, đừng gắn cờ này.

### IMMUTABLE và CONCURRENT không đồng nghĩa

- `IMMUTABLE`: nguồn không thể bị thay đổi cấu trúc trong traversal, ví dụ bộ sinh số từ các biên cố định không có storage thay đổi.
- `CONCURRENT`: nguồn được thiết kế cho các structural modifications đồng thời mà traversal vẫn có semantics phù hợp, ví dụ một số concurrent collection spliterators.

Một mảng object/primitive **có thể sửa phần tử**; đừng khai `IMMUTABLE` cho nguồn tùy biến đọc một array đang bị các thread khác sửa chỉ vì kích thước mảng cố định. Không dùng `CONCURRENT` để che data races trong code tự viết.

### DISTINCT và SORTED không được đoán

Một iterator trả các phần tử ngẫu nhiên có thể *tình cờ* không trùng, nhưng không vì thế mà bảo đảm `DISTINCT` cho mọi lần duyệt. Nếu spliterator khai `DISTINCT`, các optimization của `distinct()` có thể dựa vào cam kết này. Nếu khai `SORTED` sai, `sorted()` có thể bị tối ưu hóa khác mong đợi.

**Quy tắc thực hành:** bắt đầu với **chỉ những flags được chứng minh đúng**, thêm cờ sau khi có invariant và test.

## 6. Chuyển Iterator thành Stream bằng Spliterators

Khi đã có `Iterator<T>` và chưa cần một spliterator thiết kế đặc biệt, hãy dùng adapter chính thức:

```java
Iterator<String> iterator =
        List.of("red", "green", "blue").iterator();

Spliterator<String> spliterator =
        Spliterators.spliteratorUnknownSize(
                iterator,
                Spliterator.ORDERED | Spliterator.NONNULL);

Stream<String> stream =
        StreamSupport.stream(spliterator, false);

List<Integer> lengths =
        stream.map(String::length).toList();

System.out.println(lengths); // [3, 5, 4]
```

Đây là **mảnh minh họa** với imports `java.util.*` và `java.util.stream.*`.

`spliteratorUnknownSize` hữu ích khi **không biết chính xác số phần tử** của iterator. Không gắn `SIZED` theo ước đoán; adapter này xử lý sizing phù hợp với unknown-size source. `NONNULL` ở đây là cam kết an toàn vì `List.of` không chứa null. Nếu iterator có thể trả null, phải bỏ `NONNULL`.

### Có nên chạy song song với iterator?

Adapter từ iterator **không tự biến iterator thành nguồn chia ngẫu nhiên hiệu quả**. Một số adapter có thể gom phần tử theo batch để split, nhưng hiệu quả tùy nguồn. Đặc biệt, iterator từ I/O, cursor dữ liệu hoặc client có trạng thái thường không có khả năng truy cập song song an toàn.

Vì vậy, mặc định dùng `false` (sequential) khi không có lý do và kiểm thử cụ thể để bật parallel. Nếu muốn parallel có hiệu quả, cấu trúc nguồn nên được thiết kế để partition rõ ràng (ví dụ khoảng chỉ số, tệp có phân vùng độc lập hoặc chunk dữ liệu đã materialize).

### Iterator là nguồn một lượt

Một iterator có trạng thái có thể bị tiêu thụ; Stream tạo từ iterator đó cũng chỉ dùng **một lần**. Đừng tạo hai stream trên cùng iterator rồi mong cả hai đọc lại toàn bộ records. Nếu cần nhiều lần duyệt, hãy tạo một iterable có thể sinh iterator mới hoặc snapshot dữ liệu, nếu nguồn cho phép.

## 7. Custom Spliterator.OfInt: một bộ sinh có thể tách

Đây là ví dụ trung tâm: tạo stream các số nguyên trong khoảng `[startInclusive,endExclusive)` mà không giữ chúng trong một List hay array. `IntStream.range` đã giải quyết bài toán này trong JDK; ta tự viết để **hiểu Spliterator contract**, không phải khuyến nghị thay `IntStream.range` trong ứng dụng thường ngày.

```java
static final class RangeSpliterator implements Spliterator.OfInt {
    private int cursor;
    private final int fence;

    RangeSpliterator(int startInclusive, int endExclusive) {
        if (startInclusive > endExclusive) {
            throw new IllegalArgumentException("start > end");
        }
        this.cursor = startInclusive;
        this.fence = endExclusive;
    }

    @Override
    public boolean tryAdvance(IntConsumer action) {
        Objects.requireNonNull(action);
        if (cursor >= fence) {
            return false;
        }
        action.accept(cursor++);
        return true;
    }

    @Override
    public Spliterator.OfInt trySplit() {
        int lo = cursor;
        int mid = lo + (fence - lo) / 2;
        if (lo >= mid) {
            return null;
        }
        cursor = mid;
        return new RangeSpliterator(lo, mid);
    }

    @Override
    public long estimateSize() {
        return (long) fence - cursor;
    }

    @Override
    public int characteristics() {
        return ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL;
    }
}
```

Đây là **mảnh class minh họa**, cần imports `java.util.Objects`, `java.util.Spliterator`, `java.util.function.IntConsumer` và đặt trong class hoặc file phù hợp. Một phiên bản độc lập đầy đủ xuất hiện ở phần sau.

### Phân tích từng method

- **Constructor**: đặt `cursor` và `fence`; từ chối khoảng bị đảo đầu/cuối.
- **`tryAdvance`**: khi còn phần tử, gọi consumer với giá trị hiện tại và tăng cursor; khi hết, trả false.
- **`trySplit`**: trả **nửa đầu** của khoảng chưa duyệt rồi giữ nửa sau trong object hiện tại.
- **`estimateSize`**: trả số phần tử chưa phát ra, luôn chính xác trong mô hình không có can thiệp.
- **`ORDERED`**: các số được phát theo chỉ số tăng từ nguồn.
- **`SIZED` + `SUBSIZED`**: cả nguồn và mọi nhánh split biết chính xác độ dài.
- **`IMMUTABLE`**: bộ sinh dựa trên hai biên và cursor nội bộ, không phụ thuộc một collection bị sửa từ bên ngoài.
- **`NONNULL`**: primitive `int` không có giá trị null.

**Giới hạn kỹ thuật của mảnh code:** biểu thức `fence - lo` tính bằng `int` có thể overflow khi khoảng trải từ các giá trị âm rất lớn sang dương rất lớn. Trong chương trình hoàn chỉnh, ta dùng arithmetic `long` để xử lý trường hợp đó. Luôn nhớ điều kiện biên khi viết spliterator chung; ví dụ minh họa nhỏ không được coi là implementation cho mọi khoảng `int`.

### Tạo stream từ custom spliterator

```java
IntStream numbers = StreamSupport.intStream(
        new RangeSpliterator(1, 6), false);

System.out.println(numbers.sum()); // 15
```

Đoạn minh họa có đủ `RangeSpliterator` và import `IntStream`, `StreamSupport`. Mỗi giá trị `1,2,3,4,5` được phát một lần, không bị bỏ hoặc trùng. Nếu muốn chạy parallel, đổi cờ thành `true`:

```java
int[] squares = StreamSupport.intStream(
        new RangeSpliterator(1, 6), true)
        .map(n -> n * n)
        .toArray();

System.out.println(Arrays.toString(squares)); // [1, 4, 9, 16, 25]
```

Đây là minh họa; `toArray()` bảo toàn encounter order cho nguồn ordered, mặc dù các nhánh có thể được xử lý song song. Không nên suy từ thứ tự array kết quả rằng lời gọi mapper luôn xảy ra tuần tự.

## 8. Lỗi số học khi split một khoảng int lớn

Để tránh overflow trong phép chia khoảng, làm toán trên `long`:

```java
long remaining = (long) fence - cursor;
long middle = (long) cursor + remaining / 2;
int mid = (int) middle;
```

Đây là đoạn minh họa trong `trySplit`. Các endpoints đều là `int`, nên điểm giữa luôn nằm trong miền `int` và phép cast sau khi tính bằng `long` hợp lệ. Cách viết này an toàn cho khoảng trải từ `Integer.MIN_VALUE` đến `Integer.MAX_VALUE`, có **4.294.967.295** giá trị, lớn hơn `Integer.MAX_VALUE` nhưng vẫn biểu diễn được bằng `long`.

Vì vậy `estimateSize()` nên trả `(long) fence - cursor`, không dùng `fence - cursor` bằng `int` rồi mới ép sang `long`. Đổi sang `long` **trước khi trừ** để tránh overflow.

Chỉ số/khoảng của spliterator là một phần dữ liệu, không phải mục tiêu cố đạt mọi kiểu số. Nếu bài toán vượt cả miền biểu diễn `long`, cần định nghĩa mô hình BigInteger hoặc kiểu range khác và xem liệu stream có còn là công cụ phù hợp.

## 9. Supplier overload: trì hoãn việc lấy nguồn

Overload nhận `Supplier<? extends Spliterator<T>>` giúp tạo stream mà **chưa phải lấy spliterator ngay lúc gọi `StreamSupport.stream`**.

```java
AtomicInteger calls = new AtomicInteger();

Supplier<Spliterator<String>> source = () -> {
    calls.incrementAndGet();
    return List.of("alpha", "beta").spliterator();
};

Stream<String> lazy = StreamSupport.stream(
        source,
        Spliterator.ORDERED | Spliterator.SIZED
                | Spliterator.SUBSIZED,
        false);

System.out.println(calls.get()); // 0
System.out.println(lazy.map(String::toUpperCase).toList());
// [ALPHA, BETA]
System.out.println(calls.get()); // 1
```

Đây là minh họa cần imports `AtomicInteger`, `Supplier`, `Spliterator`, `StreamSupport`, `Stream`, `List`. Supplier có thể được gọi **một lần sau khi terminal operation bắt đầu**. Không coi `stream(...)` đã truy vấn nguồn chỉ vì object Stream đã tồn tại.

### Đừng dùng Supplier để che đổi trạng thái nguy hiểm

Supplier đọc dữ liệu lúc terminal bắt đầu, nhưng dữ liệu có thể đã bị thay đổi bởi thread khác trong lúc traversal. Sự trì hoãn không tự giải quyết vấn đề **interference**. Cần một trong các chiến lược:

- Nguồn **immutable/snapshot**.
- Nguồn có concurrency semantics phù hợp.
- Giữ quyền sở hữu độc quyền cho traversal.
- Đồng bộ hóa hoặc phân chia nguồn dữ liệu trước khi bắt đầu, nếu thực sự cần.

Với dữ liệu có `size` thay đổi trong lúc đọc, khai `SIZED` chỉ vì kích thước từng đúng ở thời điểm tạo Stream là sai.

### Characteristics của Supplier phải khớp

Tham số `characteristics` trong overload Supplier là bản **cam kết trước** về spliterator sẽ được trả. Nó phải bằng các characteristics mà spliterator thật báo. Ví dụ trên dùng `List.of(...).spliterator()` có ít nhất những flags thuộc `ORDERED|SIZED|SUBSIZED`. Khi viết code thực, hãy xác minh các characteristics cụ thể của loại spliterator bạn trả về trước khi khai; nếu có nhiều implementations khác nhau tùy điều kiện, không được tùy tiện báo mask không thống nhất.

**Không được coi mask là “tập cờ tôi muốn Java thử tối ưu”.** Nó là metadata thật của nguồn và sai lệch có thể gây hành vi ngoài contract.

## 10. Khi nào dùng overload trực tiếp, khi nào dùng Supplier?

| Tình huống | Cách tiếp cận | Lý do |
| --- | --- | --- |
| Đã có spliterator immutable/concurrent/late-binding đáng tin | `stream(spliterator,parallel)` | Đơn giản, giảm tầng indirection |
| Nguồn có thể thay đổi trước terminal và cần trì hoãn tạo spliterator | `stream(supplier,characteristics,parallel)` | Tạo nguồn gần thời điểm traversal |
| Nguồn là iterator chưa biết size | `spliteratorUnknownSize` + direct overload | Đúng semantics về unknown size |
| Đọc I/O với resource phải đóng | API chuyên dụng như `Files.lines` hoặc stream gắn `onClose` | Quản lý vòng đời tường minh |
| Muốn tính toán từ range số nguyên | `IntStream.range` | JDK đã có nguồn optimized |
| Nguồn dữ liệu phải chia theo shard/partition | Custom spliterator hoặc tầng phân phối riêng | Mỗi split sở hữu một partition độc lập |

Supplier overload được khuyến khích khi muốn thu hẹp cửa sổ giữa thời điểm ràng buộc nguồn và terminal traversal đối với nguồn vừa mutable vừa không concurrent, nhưng **không biến nguồn đó thành an toàn khi chỉnh sửa đồng thời trong traversal**.

## 11. late-binding và nguồn thay đổi

Một spliterator có thể **late-binding**: việc gắn vào nguồn/đếm/khoanh phạm vi duyệt được trì hoãn đến lần bắt đầu traversal, split hoặc truy vấn cần thiết. Nhưng tính late-binding **phụ thuộc implementation cụ thể**, không phải mọi spliterator đều late-binding.

Ví dụ các spliterators của collections chuẩn có những guarantees riêng; nếu muốn biết loại cụ thể có “fail-fast”, “weakly consistent”, “immutable” hoặc late-binding hay không, cần đọc tài liệu của class đó. Đừng suy ra:

- Có spliterator là tự snapshot.
- Có Stream là dữ liệu được copy.
- Supplier overload là tự thread-safe.
- `estimateSize()` có thể gọi bao nhiêu lần cũng không ảnh hưởng việc binding ở mọi nguồn.

Khi source là **mutable** và không phải **CONCURRENT/IMMUTABLE**, tốt nhất không sửa cấu trúc nguồn từ lúc traversal bắt đầu cho tới khi terminal kết thúc. Nếu ứng dụng cần mutation trong thời gian đó, chọn một concurrency model chính thức hoặc snapshot dữ liệu.

## 12. forEachRemaining(): nên viết hay dùng mặc định?

`Spliterator` có implementation mặc định cho `forEachRemaining` thông qua nhiều lần gọi `tryAdvance`. Nếu `tryAdvance` đúng, cách mặc định thường đủ cho nguồn nhỏ và giúp giảm code.

Bạn có thể override `forEachRemaining` để tối ưu traversal theo lô, nhưng phải giữ các invariant:

- Không bỏ sót/nhân đôi phần tử.
- Không phát phần tử sau khi hết.
- Cập nhật cursor/state nhất quán với những method khác.
- Tôn trọng encounter order nếu báo `ORDERED`.
- Không thay đổi nguồn từ bên trong callback theo cách vi phạm non-interference.
- Không che exception hoặc thay đổi semantics của `Consumer`.

Với một spliterator tập trung vào correctness, bắt đầu từ `tryAdvance` và `trySplit` đúng rồi mới tối ưu `forEachRemaining` nếu có benchmark.

## 13. Primitive Spliterator và chi phí boxing

`Spliterator.OfInt` đưa phần tử `int` vào `IntConsumer`. `StreamSupport.intStream` tạo `IntStream`; các phép `sum`, `average`, `map`, `filter` có thể tránh boxing wrapper `Integer`.

```java
IntStream numbers = StreamSupport.intStream(
        new RangeSpliterator(1, 5),
        false);

int total = numbers.sum(); // 10
```

Đây là minh họa cần class `RangeSpliterator` đã định nghĩa. Tương tự `Spliterator.OfLong` và `OfDouble` đi kèm `longStream`/`doubleStream`. Không cast `Spliterator<Integer>` tùy ý thành `Spliterator.OfInt`: hai API không cùng chức năng chỉ vì value type tương ứng là wrapper của nhau.

### Khi nào boxed()?

Nếu consumer cần `List<Integer>`:

```java
List<Integer> boxed = StreamSupport.intStream(
        new RangeSpliterator(1, 4), false)
        .boxed()
        .toList();

System.out.println(boxed); // [1, 2, 3]
```

Đây là minh họa. `boxed()` chuyển sang object `Stream<Integer>`; chỉ dùng khi API đích thực sự cần wrapper. Nếu chỉ cần `sum` hoặc `max`, giữ `IntStream` để tránh boxing không cần.

## 14. Parallel đúng cần cả chia việc và độc lập dữ liệu

`StreamSupport.stream(spliterator,true)` báo rằng pipeline có thể chạy **song song**, nhưng không tự bảo đảm hiệu năng. Nếu `trySplit` luôn trả null, một nguồn có thể vẫn được xử lý chủ yếu tuần tự.

Để parallel hiệu quả:

1. Nguồn có thể **chia thành các partition độc lập** với chi phí hợp lý.
2. Mỗi partition xử lý một tập phần tử **không chồng lấn**.
3. Callback của pipeline **stateless, non-interfering**.
4. Reduction phù hợp với việc kết hợp kết quả từ nhiều nhánh.
5. Nếu cần `ORDERED`, spliterator split đúng prefix/suffix và terminal operation giữ order khi contract yêu cầu.
6. Tổng chi phí tính toán đủ lớn để bù chi phí split, scheduling và merge.

### Không chia bằng một Iterator chung không đồng bộ

Phản ví dụ về thiết kế:

```java
// PSEUDOCODE SAI:
// Spliterator A và Spliterator B cùng gọi iterator.next()
// trên một iterator mutable không thread-safe.
```

Đây là pseudocode, không phải mã biên dịch. Các nhánh sẽ tranh trạng thái, có thể bỏ sót, lặp hoặc phát sai phần tử. Thay vào đó, tách theo index, chunk snapshot hoặc partition API có quyền sở hữu rõ ràng.

### Thứ tự kết quả khác thứ tự thực thi

Nguồn `ORDERED` có thể tạo kết quả ordered khi dùng `toArray`/`toList` dù mapper chạy ngoài thứ tự trên các threads. `parallel().forEach(...)` không cam kết encounter order; nếu bắt buộc thực thi terminal action theo order thì dùng `forEachOrdered`, đồng thời hiểu chi phí ordering.

Không nên dùng shared mutable `ArrayList` và `parallel().forEach(list::add)` để tự gom kết quả. Dùng collector hoặc `toList`/`toArray` mà stream library quản lý đúng ngữ nghĩa.

## 15. Stream không tự đóng tài nguyên sau terminal operation

`Stream` có `close()` và `onClose(Runnable)`. **Các terminal operations thông thường không tự gọi `close()`.** Với dữ liệu hoàn toàn trong bộ nhớ, điều này thường không đáng kể. Nhưng nếu custom spliterator đọc file, socket hoặc cursor dữ liệu, phải quy định vòng đời rõ.

Có thể gắn một close handler:

```java
Stream<String> stream = StreamSupport.stream(
        spliterator, false)
        .onClose(resource::close);
```

Đây là **đoạn minh họa**, `resource` và `spliterator` là thành phần ứng dụng cần định nghĩa. `onClose` đăng ký action để chạy khi stream đóng; nó **không bảo đảm** resource tự đóng khi gọi `count()`, `findFirst()` hoặc `toList()`.

Dùng try-with-resources:

```java
try (Stream<String> stream = StreamSupport.stream(
        spliterator, false).onClose(resource::close)) {
    long count = stream.count();
    System.out.println(count);
}
```

Đây là minh họa, cần resource có `close()` thích hợp. Khi thoát khối `try`, `Stream.close()` kích hoạt close handler, kể cả khi terminal operation ném exception, theo cơ chế try-with-resources. Nếu handler ném exception, quy tắc suppressed exceptions của Java có thể áp dụng.

**Lưu ý ownership:** tránh đóng một resource mà ứng dụng khác còn đang dùng nếu stream không sở hữu nó. Khi thiết kế adapter, cần ghi rõ ai tạo, ai đóng, có được duyệt lại không và có được chạy parallel không.

### onClose là hook, không phải checkpoint

`onClose` không được dùng để thực thi logic cần chạy sau **mỗi** terminal operation nếu stream không bị đóng; terminal operation không tự bảo đảm gọi hook. Nếu ứng dụng cần cleanup chắc chắn, yêu cầu caller dùng try-with-resources hoặc cung cấp một API bọc vòng đời chặt chẽ hơn.

## 16. Một nguồn tùy biến từ cursor: chọn gì để an toàn?

Các cursor từ database, paginated API hoặc message queue thường có trạng thái và I/O. Adapter Stream có thể giúp người gọi dùng pipeline, nhưng cần đặc tả thêm:

- **Tính một lần:** cursor đã đọc thì không tự tua lại.
- **Tính đóng:** đóng khi dừng sớm (ví dụ `findFirst()`) bằng try-with-resources.
- **Thứ tự:** `ORDERED` chỉ khi nguồn có thứ tự rõ ràng; không tự suy từ thứ tự record trả về một lần.
- **Kích thước:** không khai `SIZED` nếu nguồn không biết chính xác remaining count.
- **Chia:** `trySplit()==null` thường an toàn hơn chia giả nếu cursor không hỗ trợ partition độc lập.
- **Cancellation:** short-circuit có thể ngừng gọi `tryAdvance` sớm, nhưng không có nghĩa upstream resource tự đóng.
- **Lỗi I/O:** `tryAdvance` không khai checked exception; adapter phải chọn chính sách chuyển lỗi thành unchecked exception hợp lý hoặc API khác.
- **Thread safety:** nếu cursor không hỗ trợ concurrent reads, không hứa `CONCURRENT` và không bật parallel mặc định.

Những yêu cầu này có thể khiến API thao tác paging/cursor riêng dễ kiểm soát hơn Stream, nhất là khi cần retry, backpressure, async hoặc deadline. Không ép mọi luồng dữ liệu bất đồng bộ vào Stream đồng bộ.

## 17. Ví dụ Java 17+ hoàn chỉnh: custom Spliterator, Supplier và resource closure

Ví dụ này có ba nguồn:

1. **RangeSpliterator** sinh số nguyên theo khoảng nửa mở, có split cân bằng và characteristics đúng.
2. **Iterator adapter** tạo `Stream<String>` từ nguồn chưa biết kích thước.
3. **Supplier overload** chứng minh nguồn được tạo trễ tới terminal operation.
4. **onClose** chứng minh close hook chỉ chạy khi stream được đóng.

Lưu thành **CustomStreamSupportDemo.java**:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.IntConsumer;
import java.util.function.Supplier;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class CustomStreamSupportDemo {

    static final class RangeSpliterator implements Spliterator.OfInt {
        private int cursor;
        private final int fence;

        RangeSpliterator(int startInclusive, int endExclusive) {
            if (startInclusive > endExclusive) {
                throw new IllegalArgumentException("start > end");
            }
            cursor = startInclusive;
            fence = endExclusive;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action);
            if (cursor >= fence) {
                return false;
            }
            action.accept(cursor++);
            return true;
        }

        @Override
        public Spliterator.OfInt trySplit() {
            long remaining = (long) fence - cursor;
            if (remaining < 2) {
                return null;
            }
            int midpoint = (int) ((long) cursor + remaining / 2);
            int start = cursor;
            cursor = midpoint;
            return new RangeSpliterator(start, midpoint);
        }

        @Override
        public long estimateSize() {
            return (long) fence - cursor;
        }

        @Override
        public int characteristics() {
            return ORDERED | SIZED | SUBSIZED | IMMUTABLE | NONNULL;
        }
    }

    public static void main(String[] args) {
        RangeSpliterator range = new RangeSpliterator(1, 7);

        System.out.println("rangeSize=" + range.estimateSize());
        System.out.println("exactSize=" + range.getExactSizeIfKnown());

        int[] squares = StreamSupport.intStream(range, true)
                .map(n -> n * n)
                .toArray();
        System.out.println("squares=" + Arrays.toString(squares));

        int total = StreamSupport.intStream(
                new RangeSpliterator(1, 7), false).sum();
        System.out.println("sum=" + total);

        Iterator<String> iterator =
                List.of("red", "green", "blue").iterator();
        Spliterator<String> fromIterator =
                Spliterators.spliteratorUnknownSize(
                        iterator,
                        Spliterator.ORDERED | Spliterator.NONNULL);

        List<Integer> lengths =
                StreamSupport.stream(fromIterator, false)
                        .map(String::length)
                        .toList();
        System.out.println("iteratorLengths=" + lengths);

        AtomicInteger supplied = new AtomicInteger();
        Supplier<Spliterator<String>> supplier = () -> {
            supplied.incrementAndGet();
            return List.of("alpha", "beta").spliterator();
        };

        Stream<String> late = StreamSupport.stream(
                supplier,
                Spliterator.ORDERED | Spliterator.SIZED
                        | Spliterator.SUBSIZED,
                false);

        System.out.println("supplierBefore=" + supplied.get());
        System.out.println("supplierValues=" +
                late.map(String::toUpperCase).toList());
        System.out.println("supplierAfter=" + supplied.get());

        AtomicBoolean closed = new AtomicBoolean(false);
        try (Stream<String> closeable =
                StreamSupport.stream(
                        List.of("x", "y").spliterator(), false)
                        .onClose(() -> closed.set(true))) {
            System.out.println("closeableCount=" + closeable.count());
            System.out.println("closedInside=" + closed.get());
        }
        System.out.println("closedAfter=" + closed.get());
    }
}
```

Biên dịch/chạy với **JDK 17 trở lên**:

```bash
javac CustomStreamSupportDemo.java
java CustomStreamSupportDemo
```

**Stdout xác định:**

```text
rangeSize=6
exactSize=6
squares=[1, 4, 9, 16, 25, 36]
sum=21
iteratorLengths=[3, 5, 4]
supplierBefore=0
supplierValues=[ALPHA, BETA]
supplierAfter=1
closeableCount=2
closedInside=false
closedAfter=true
```

### Vì sao stdout đúng?

1. Khoảng `[1,7)` chứa sáu số 1 tới 6. `estimateSize()` và `getExactSizeIfKnown()` đều trả `6` vì implementation báo `SIZED` đúng và chưa duyệt phần tử.
2. `trySplit()` trả các prefixes không chồng lấn, nên dù `intStream(...,true)` chạy song song, `toArray()` vẫn tạo mảng số bình phương theo encounter order: `1,4,9,16,25,36`.
3. Một `RangeSpliterator` **mới** cho phép gọi terminal operation `sum()` độc lập; tổng 1+2+3+4+5+6 bằng `21`. Không dùng lại object đã được pipeline `toArray()` tiêu thụ.
4. Adapter iterator đọc `red` (3 ký tự), `green` (5), `blue` (4), giữ encounter order.
5. Supplier tạo nguồn trễ: trước terminal operation số lần gọi là `0`; khi `toList()` yêu cầu traversal thì gọi supplier một lần và tạo `[ALPHA, BETA]`; sau đó số lần là `1`.
6. `closeable.count()` cho kết quả `2` nhưng **chưa tự close**, nên biến `closed` vẫn là `false` bên trong khối `try`.
7. Khi khối `try-with-resources` kết thúc, `Stream.close()` chạy close handler, nên `closedAfter=true`.

Chương trình không dựa vào số thread, thứ tự xử lý callbacks song song hay tên lớp triển khai của `Spliterator`. Mọi giá trị output đều được bảo đảm bởi dữ liệu và semantics đã chọn.

## 18. Kiểm thử custom Spliterator trước khi bật parallel

Một implementation spliterator tùy biến nên có cả **kiểm thử traversal tuần tự** và **kiểm thử split đệ quy**. Những nhóm test hữu ích:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Khoảng rỗng `[3,3)` | Không có phần tử, `estimateSize()==0`, `trySplit()==null` |
| Một phần tử `[3,4)` | Phát đúng `3` một lần |
| Khoảng có hai phần tử | Split ra hai nhánh không chồng lấn |
| Khoảng có số phần tử lẻ | Hai nhánh cộng size bằng size trước split |
| Khoảng bắt đầu từ số âm | Mỗi phần tử đúng, thứ tự tăng |
| Khoảng trải qua âm/dương lớn | Không overflow khi tính midpoint/remaining |
| Sau khi `tryAdvance` | `estimateSize` giảm đúng một |
| Sau khi `trySplit` | Tổng size các nhánh bằng size ban đầu |
| Duyệt lại các nhánh | Không thiếu hoặc lặp phần tử |
| Chạy parallel | `toArray`/`sum` khớp kết quả sequential |
| `characteristics` | Chỉ báo những tính chất thật |
| Callback gây exception | Không che exception, trạng thái nguồn được quy định |

### Test split thủ công

```java
RangeSpliterator parent = new RangeSpliterator(0, 8);
Spliterator.OfInt prefix = parent.trySplit();

System.out.println(prefix.estimateSize()); // 4
System.out.println(parent.estimateSize()); // 4
```

Đây là đoạn minh họa dùng class ở chương trình trên. Để kiểm tra sâu hơn, hãy duyệt hai nhánh ra mảng và so với `[0,1,2,3,4,5,6,7]`. Kiểm tra **kích thước và thứ tự** riêng biệt: tổng size đúng chưa chứng minh không mất/nhân đôi một phần tử.

### Test những nguồn vốn không có size cố định

Nếu nguồn lấy dữ liệu từ remote cursor chưa biết số lượng chính xác, không kỳ vọng `getExactSizeIfKnown()` trả một số dương. Với spliterator không `SIZED`, API này trả `-1` theo contract. Dùng nguồn giả lập có số phần tử thay đổi để chắc chắn code downstream không dựa vào sizing sai.

## 19. Các lỗi contract phổ biến

### Lỗi 1 — tryAdvance trả true mà không phát phần tử

```java
// PSEUDOCODE SAI:
// boolean tryAdvance(Consumer<T> action) {
//     if (empty) return true; // phải là false
// }
```

Đây là pseudocode. Stream có thể lặp vô tận hoặc trả kết quả không đúng vì implementation tuyên bố còn phần tử nhưng không chuyển phần tử cho consumer.

### Lỗi 2 — trySplit trả nhánh chứa cả dữ liệu của parent

Nếu nhánh trả về và parent đều đọc chung `[0,8)`, mọi phần tử có thể bị nhân đôi ở parallel traversal. Đúng phải **cắt vùng ownership** và cập nhật parent ngay khi split.

### Lỗi 3 — ORDERED nhưng trySplit trả suffix

Đối với ordered source, `trySplit` trả **prefix** theo contract. Nếu implementation trả suffix và giữ prefix ở parent, terminal operation giữ encounter order có thể tạo kết quả không đúng. Kiểm tra split với `toArray`, không chỉ `sum` (tổng có thể che lỗi thứ tự).

### Lỗi 4 — SIZED dựa vào dự đoán

Một nguồn lọc records theo điều kiện không thể báo size chính xác chỉ dựa vào số records trước lọc. `SIZED` sai có thể làm Stream API định trước bộ nhớ hoặc tối ưu hóa không phù hợp.

### Lỗi 5 — Khai SORTED khi không thật sự sorted

`SORTED` là cam kết về thứ tự comparator/natural order. Nếu khai sai, `sorted()` hoặc các thao tác liên quan có thể dựa trên cờ mà bỏ qua việc sắp xếp cần thiết. Khi có `SORTED`, `getComparator()` phải tuân đúng contract.

### Lỗi 6 — Khai IMMUTABLE cho một nguồn mutable thông thường

Array có chiều dài cố định không đồng nghĩa element values bất biến. Nếu một thread khác thay phần tử trong khi traversal, không có nghĩa custom spliterator được phép báo `IMMUTABLE` và coi sự thay đổi là an toàn.

### Lỗi 7 — Sai mask trong Supplier overload

`StreamSupport.stream(supplier,flags,parallel)` dựa vào `flags` được khai báo trước khi supplier tạo nguồn. Nếu giá trị này không phù hợp với spliterator thực, behavior có thể không còn được bảo đảm. Khi không chắc, dùng spliterator có contract rõ, hoặc làm rõ nguồn trước khi xây stream.

### Lỗi 8 — Quên close nguồn I/O

`findFirst()` có thể dừng sớm, nhưng không vì thế mà tự đóng socket/file/cursor. Terminal operation không tự close stream. Gắn `onClose` và yêu cầu try-with-resources, hoặc dùng API chuyên dụng đã quản lý lifetime.

### Lỗi 9 — Sử dụng Stream hai lần

`Stream<T>` sau khi terminal operation được coi là đã tiêu thụ. Nếu muốn duyệt lại source, tạo stream **mới** bằng nguồn có thể tái tạo; iterator/cursor một lần thường không thể tua lại.

### Lỗi 10 — Tạo parallel chỉ bằng boolean true

`true` không biến nguồn thành splittable hiệu quả, thread-safe hoặc nhanh hơn. Hãy kiểm tra `trySplit`, workload, callback side effects và mức độ contention.

### Lỗi 11 — Dùng StreamSupport cho bài toán có API chuẩn tốt hơn

`IntStream.range`, `List.stream` và `Files.lines` thường giảm code và rủi ro hơn nguồn custom. Chỉ đầu tư vào spliterator khi thực sự cần mô hình nguồn mới hoặc đặc tính/tách việc cụ thể.

## 20. Quy trình thiết kế một nguồn Stream tùy biến

1. **Xác định dữ liệu:** hữu hạn/vô hạn, immutable/mutable, có size chính xác không, có thứ tự không?
2. **Xác định ownership:** nguồn có thể được tiêu thụ một lần hay nhiều lần? Ai chịu trách nhiệm đóng?
3. **Chọn kiểu stream:** reference, `IntStream`, `LongStream` hay `DoubleStream`?
4. **Thử adapter có sẵn:** `Collection.stream`, `Arrays.stream`, `IntStream.range`, `Spliterators.spliteratorUnknownSize`.
5. **Định nghĩa traversal:** `tryAdvance` làm gì khi còn/hết phần tử? Chuyển lỗi ra sao?
6. **Định nghĩa splitting:** có thể phân chia không chồng lấn không? Nếu không, cho `trySplit` trả null.
7. **Đặt characteristics tối thiểu đúng:** không báo `SIZED`, `SORTED`, `CONCURRENT` hoặc `IMMUTABLE` khi không chứng minh được.
8. **Xác định late binding:** nên tạo spliterator ngay hay qua supplier khi terminal bắt đầu?
9. **Thiết kế resource lifecycle:** có dùng `onClose` và try-with-resources không? Có short-circuit không?
10. **Kiểm thử correctness:** nguồn rỗng, nguồn nhỏ, biên lớn, split một/nhiều lần, exception, nguồn mutable.
11. **Cân nhắc parallel:** chỉ khi split và downstream operations phù hợp; benchmark nếu hiệu năng quan trọng.
12. **Tài liệu hóa API:** caller có được gọi lại, được sử dụng song song, được mutate source, có phải close không?

### Khi nào không nên biến dữ liệu thành Stream?

Một API remote cần **backpressure, retry, cancellation xuyên hệ thống, timeout hoặc thông báo bất đồng bộ** có thể phù hợp hơn với abstraction chuyên biệt. Java `Stream` là mô hình synchronous pull pipeline; một adapter custom không tự biến nó thành reactive stream. Nếu ép sai mô hình, bạn có thể có code ngắn nhưng quản lý lỗi/tài nguyên kém.

## 21. Bài tập thực hành có đáp án định hướng

**Bài 1 — Adapter iterator.** Có `Iterator<String>` không biết số lượng. Hãy dùng `Spliterators.spliteratorUnknownSize(iterator,Spliterator.ORDERED)` và `StreamSupport.stream(...,false)` rồi đếm những chuỗi không rỗng. **Đáp án:** tạo stream từ adapter, `filter(s -> !s.isEmpty()).count()`; không khai `SIZED`.

**Bài 2 — Primitive stream.** Từ `Spliterator.OfInt`, dùng API nào để có `IntStream`? **Đáp án:** `StreamSupport.intStream(spliterator,false)` hoặc overload supplier tương ứng, không ép thành `Stream<Integer>`.

**Bài 3 — SIZED.** Một nguồn luôn phát đúng 5 phần tử và `estimateSize` giảm 1 sau mỗi `tryAdvance` có thể báo `SIZED` không? **Đáp án:** có nếu đây thật sự là cam kết đúng mọi lần traversal, không bị mutation/interference.

**Bài 4 — SUBSIZED.** Nếu một nhánh split không biết size chính xác, có được báo `SUBSIZED` ở parent không? **Đáp án:** không; cờ này nói về mọi spliterators sau split.

**Bài 5 — ORDERED.** Nguồn `[9,1,7]` có thể báo `ORDERED` không? **Đáp án:** có nếu thứ tự `9,1,7` là encounter order xác định; không vì thế báo `SORTED`.

**Bài 6 — Split.** Với `[0,9)`, chia hai nửa `[0,4)` và `[4,9)`. Chúng có chồng lấn không? Có bao nhiêu phần tử tổng cộng? **Đáp án:** không; 4+5=9.

**Bài 7 — Supplier.** Một `Supplier<Spliterator<String>>` được truyền vào `StreamSupport.stream`. Khi nào supplier được gọi theo contract? **Đáp án:** sau khi terminal operation bắt đầu, không quá một lần; không phải ngay lúc tạo Stream.

**Bài 8 — Resource.** Vì sao `stream.findFirst()` chưa chắc giải phóng cursor? **Đáp án:** terminal operation không tự close Stream. Dùng try-with-resources và close handler/adapter đảm bảo ownership.

**Bài 9 — Parallel.** Một custom spliterator có `trySplit()==null`. `parallel=true` có tự làm nó xử lý hiệu quả trên nhiều cores không? **Đáp án:** không; nguồn không chia việc tốt, nên khả năng parallel hóa có thể rất hạn chế.

**Bài 10 — Distinct flag.** Nếu nguồn có duplicate nhưng khai `DISTINCT`, chuyện gì có thể xảy ra? **Đáp án:** các tối ưu hóa có thể dựa vào lời hứa sai; kết quả không còn đáng tin theo contract.

**Bài 11 — Range overflow.** Tại sao dùng `(long) fence - cursor` thay cho `(long)(fence - cursor)`? **Đáp án:** bản thứ hai có thể overflow ngay ở phép trừ kiểu `int` trước khi cast.

**Bài 12 — Output order.** Một custom spliterator báo `ORDERED` và tách theo prefix/suffix hợp lệ. `parallel().map(...).toArray()` có trả theo thứ tự hoàn tất callbacks không? **Đáp án:** không; output mảng giữ encounter order còn execution order có thể khác.

## 22. Tóm tắt nhanh

- **`StreamSupport` tạo Stream từ `Spliterator`**; nó không tự làm nguồn thread-safe, immutable hay tự đóng.
- **`Spliterator` là hợp đồng traversal + splitting + characteristics**, không chỉ là iterator với tên mới.
- **`tryAdvance`** phát đúng một phần tử khi trả true; **`trySplit`** chia nguồn không mất/nhân đôi phần tử và với ordered source trả prefix.
- Chỉ khai **ORDERED, SIZED, SUBSIZED, DISTINCT, SORTED, IMMUTABLE, CONCURRENT** khi có invariant chứng minh đúng.
- **`stream(supplier,characteristics,parallel)`** trì hoãn tạo spliterator cho tới terminal operation; mask phải nhất quán với spliterator thực.
- **`Spliterators.spliteratorUnknownSize`** là adapter tốt cho Iterator chưa rõ số lượng.
- **`intStream`/`longStream`/`doubleStream`** nhận primitive spliterators, thường tránh boxing khi tính số.
- Parallel execution cần **split đúng** và callbacks an toàn, không chỉ bật cờ `true`.
- **`onClose` + try-with-resources** là mẫu hữu ích nếu nguồn sở hữu file/cursor/socket; terminal operation không tự đóng resource.
- Trước khi viết custom source, kiểm tra xem **`Collection.stream`, `Arrays.stream`, `IntStream.range` hoặc `Files.lines`** đã giải quyết bài toán chưa.

### Tài liệu chính thức

- [Java SE 25 — StreamSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/StreamSupport.html)
- [Java SE 25 — Spliterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html)
- [Java SE 25 — Spliterators](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterators.html)
- [Java SE 25 — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 25 — IntStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html)
- [Java SE 25 — java.util.stream package: non-interference, side effects, parallel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
