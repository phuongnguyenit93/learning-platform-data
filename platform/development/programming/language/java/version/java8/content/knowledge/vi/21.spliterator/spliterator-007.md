# Primitive Spliterator và tránh boxing trong Java Stream

## 1. Vì sao Primitive Spliterator quan trọng?

`Spliterator` (splitable iterator) là giao diện **duyệt và phân chia** một nguồn dữ liệu thành những phần nhỏ để xử lý tuần tự hoặc song song. Trong Java, `Spliterator<T>` mô tả phần tử kiểu `T`; với `T` là kiểu tham chiếu như `String`, cách duyệt này phù hợp. Nhưng khi dữ liệu gốc là `int[]`, `long[]` hoặc `double[]`, việc đưa từng giá trị qua kiểu bọc `Integer`, `Long` hoặc `Double` có thể phát sinh **boxing/unboxing** không cần thiết.

Java hỗ trợ ba nhánh primitive specialization của `Spliterator`:

- **`Spliterator.OfInt`**: duyệt giá trị `int` với `IntConsumer`, tạo `IntStream`.
- **`Spliterator.OfLong`**: duyệt giá trị `long` với `LongConsumer`, tạo `LongStream`.
- **`Spliterator.OfDouble`**: duyệt giá trị `double` với `DoubleConsumer`, tạo `DoubleStream`.

Đây là các API có từ Java 8 và vẫn hoạt động trong JDK hiện đại. **Primitive Spliterator giúp pipeline nhận phần tử bằng primitive**, giảm nhu cầu tạo/chuyển đổi wrapper ở đường xử lý dữ liệu. Nó không tự bảo đảm cải thiện tốc độ: JIT có thể tối ưu nhiều phép boxing, và bottleneck có thể nằm ở thuật toán, bộ nhớ, I/O hay phép gộp kết quả.

### 1.1. Cùng dữ liệu, hai đường đi

Với nguồn `int[]`, đường đi ưu tiên thường là:

```text
int[] → Spliterator.OfInt → IntStream → IntConsumer / IntUnaryOperator
      → sum(), average(), summaryStatistics(), ...
```

Khi ép sang stream đối tượng:

```text
int[] → boxing → Stream<Integer> → Function<Integer, ...>
      → có thể phải unboxing khi cộng/số học
```

Không phải mỗi wrapper luôn kéo theo một cấp phát heap thực sự: `Integer` còn có cache cho một số giá trị và JIT có thể khử đối tượng tạm trong những hoàn cảnh phù hợp. Lợi ích chắc chắn về mặt **API** là giảm các lần chuyển đổi *bắt buộc về mặt kiểu* và dễ áp dụng các phép toán số học được thiết kế riêng cho primitive.

## 2. Cấu trúc của Primitive Spliterator

`Spliterator.OfInt` kế thừa `Spliterator<Integer>` và `Spliterator.OfPrimitive<Integer, IntConsumer, Spliterator.OfInt>`, đồng thời cung cấp các phương thức chuyên biệt cho `int`. Tương tự, `OfLong` và `OfDouble` dùng consumer primitive tương ứng.

| Chức năng | `OfInt` | `OfLong` | `OfDouble` |
| --- | --- | --- | --- |
| Dữ liệu duyệt | `int` | `long` | `double` |
| Callback chuyên biệt | `IntConsumer` | `LongConsumer` | `DoubleConsumer` |
| Duyệt từng phần tử | `tryAdvance(IntConsumer)` | `tryAdvance(LongConsumer)` | `tryAdvance(DoubleConsumer)` |
| Duyệt phần còn lại | `forEachRemaining(IntConsumer)` | `forEachRemaining(LongConsumer)` | `forEachRemaining(DoubleConsumer)` |
| Chia nguồn | `Spliterator.OfInt trySplit()` | `Spliterator.OfLong trySplit()` | `Spliterator.OfDouble trySplit()` |
| Tạo Stream | `StreamSupport.intStream(...)` | `StreamSupport.longStream(...)` | `StreamSupport.doubleStream(...)` |

Ba trách nhiệm phổ biến của một implementation tự viết:

1. **`tryAdvance`**: nếu còn phần tử, chuyển đúng một giá trị tới callback và trả `true`; hết dữ liệu trả `false`.
2. **`trySplit`**: nếu có thể, tách một phần **chưa duyệt** thành spliterator mới, đồng thời cập nhật phạm vi của spliterator gốc để không trùng và không mất phần tử; nếu không chia được thì trả `null`.
3. **`estimateSize`** và **`characteristics`**: báo kích thước còn lại cùng những đặc tính mà nguồn thực sự đáp ứng.

Một implementation nên bảo đảm cả duyệt tuần tự lẫn phân chia nhiều lần đều giữ nguyên tập phần tử và số lượng. `trySplit()` **không** nhất thiết chia đúng một nửa trong mọi nguồn; chia cân bằng là mục tiêu hiệu năng, còn không trùng/mất phần tử là yêu cầu tính đúng.

### 2.1. Dùng đúng overload primitive của `tryAdvance`

`OfInt` có overload nhận `IntConsumer`. Để chỉ rõ API primitive, có thể viết:

```java
Spliterator.OfInt spliterator =
    java.util.Spliterators.spliterator(new int[] {7, 8},
        Spliterator.ORDERED);
spliterator.tryAdvance((java.util.function.IntConsumer) value ->
    System.out.println(value));  // 7
```

Đoạn này là snippet cần các import `java.util.Spliterator`, hoặc dùng tên lớp đầy đủ như trên. `IntConsumer.accept(int)` nhận **`int` trực tiếp**.

Do `OfInt` vẫn là `Spliterator<Integer>`, nó cũng có overload kế thừa `tryAdvance(Consumer<? super Integer>)`. Theo đặc tả JDK, cầu nối này có thể thích ứng một `Consumer<Integer>` bằng cách **boxing giá trị `int`**. Khi tự triển khai, hãy override `tryAdvance(IntConsumer)` (và có thể `forEachRemaining(IntConsumer)`); khi gọi, chọn callback primitive nếu muốn tránh đường boxing đó.

Ví dụ ngắn với hai đường truyền khác nhau:

```java
IntConsumer primitiveAction = (int value) -> System.out.println(value);
Consumer<Integer> objectAction = (Integer value) -> System.out.println(value);

// Hai dòng sau dùng hai spliterator khác nhau vì mỗi spliterator bị tiêu thụ.
Spliterator.OfInt primitive = Spliterators.spliterator(new int[] {3},
    Spliterator.ORDERED);
primitive.tryAdvance(primitiveAction);

Spliterator.OfInt boxedBridge = Spliterators.spliterator(new int[] {3},
    Spliterator.ORDERED);
boxedBridge.tryAdvance(objectAction);
```

`IntConsumer` và `Consumer<Integer>` khác nhau về hợp đồng kiểu dữ liệu, dù hai phép gọi có thể in cùng số `3`. Các snippet này cần import `java.util.*` và `java.util.function.*`; ví dụ chạy độc lập nằm ở mục 6.

## 3. Lấy Primitive Spliterator có sẵn thay vì tự viết

Hầu hết code ứng dụng không cần tự cài đặt spliterator: `IntStream`, `LongStream`, `DoubleStream`, các array và bộ tiện ích `Spliterators` đã cung cấp đường đi primitive.

### 3.1. Array primitive và các khoảng số

```java
int[] values = {2, 3, 4, 5};

int sum = Arrays.stream(values).sum();              // 14
int evenSum = Arrays.stream(values)
    .filter(n -> n % 2 == 0)
    .sum();                                          // 6

int rangeSum = IntStream.rangeClosed(1, 4).sum();    // 10
long largeRangeSum = LongStream.rangeClosed(1, 4)
    .sum();                                          // 10L
```

`Arrays.stream(int[])` trả `IntStream`; `IntStream.range` và `rangeClosed` tạo nguồn số nguyên biết rõ phạm vi. Những nguồn này có cấu trúc thuận lợi cho việc chia theo khoảng, nhưng có nhanh hơn song song hay không vẫn phụ thuộc công việc mỗi phần tử.

### 3.2. `Spliterators.spliterator` cho primitive array

```java
int[] values = {2, 3, 4, 5};

Spliterator.OfInt cursor =
    Spliterators.spliterator(values, Spliterator.ORDERED);

int sum = StreamSupport.intStream(cursor, false).sum(); // 14
```

`Spliterators.spliterator(int[], int additionalCharacteristics)` trả về `Spliterator.OfInt`. Bên cạnh các đặc tính được truyền hợp lệ, nó có những đặc tính kích thước tương ứng với nguồn array. `StreamSupport.intStream(cursor, false)` tạo `IntStream` tuần tự; truyền `true` để tạo stream ở chế độ song song.

**Mỗi spliterator/stream chỉ nên dùng cho một lượt duyệt**. Sau khi gọi `sum()`, hãy tạo lại spliterator nếu cần phép tổng hợp khác. Nếu dữ liệu là array thông thường và không cần điều chỉnh cách chia, `Arrays.stream(values)` dễ đọc hơn.

### 3.3. Dùng các primitive stream khác

```java
long[] counters = {5L, 7L, 9L};
double[] rates = {1.5, 2.5};

long totalCount = Arrays.stream(counters).sum();          // 21L
double average = Arrays.stream(rates).average()
    .orElse(Double.NaN);                                  // 2.0

Spliterator.OfLong longSource =
    Spliterators.spliterator(counters, Spliterator.ORDERED);
Spliterator.OfDouble doubleSource =
    Spliterators.spliterator(rates, Spliterator.ORDERED);

long fromLongSource =
    StreamSupport.longStream(longSource, false).sum();     // 21L
double fromDoubleSource =
    StreamSupport.doubleStream(doubleSource, false).sum(); // 4.0
```

`IntStream`, `LongStream`, `DoubleStream` đều có sẵn `sum`, `average`, `summaryStatistics` và các phép tính liên quan. `average()` trả `OptionalDouble` để xử lý tập rỗng, không phải luôn trả một `double` hợp lệ.

## 4. Boxing và unboxing xảy ra khi nào?

**Boxing** là chuyển một primitive thành object wrapper: `int → Integer`. **Unboxing** là lấy lại primitive: `Integer → int`. Trong Stream API, chuyển đổi kiểu rất dễ xảy ra khi đi qua các ranh giới giữa `Stream<Integer>` và `IntStream`.

### 4.1. Đặt hai pipeline cạnh nhau

```java
int[] numbers = {1, 2, 3, 4};

// Đường đi primitive từ nguồn đến phép cộng.
int primitiveSum = Arrays.stream(numbers)
    .map(value -> value * 2)
    .sum(); // 20

// boxed() cố ý chuyển từ IntStream sang Stream<Integer>.
List<Integer> boxedValues = Arrays.stream(numbers)
    .boxed()
    .collect(Collectors.toList()); // [1, 2, 3, 4]

// mapToInt() chuyển giá trị Integer thành int tại ranh giới.
int fromBoxedList = boxedValues.stream()
    .mapToInt(Integer::intValue)
    .sum(); // 10
```

Các snippet trong mục này cần những import thích hợp (`Arrays`, `List`, `Collectors`). Dùng `.boxed()` khi **cần kết quả object**, ví dụ API nhận `List<Integer>`, chứ không làm bước chuyển đổi chỉ để tiếp tục tính số học.

### 4.2. `mapToInt` không xóa được boxing đã tồn tại ở nguồn

Với một `List<Integer>` đã được tạo sẵn:

```java
List<Integer> values = Arrays.asList(1, 2, 3, 4);
int sum = values.stream()
    .mapToInt(Integer::intValue)
    .sum(); // 10
```

Dạng này giúp **các bước phía sau `mapToInt`** xử lý `int`, nhưng các phần tử trong `List<Integer>` vẫn là những đối tượng wrapper. Nó không biến `List<Integer>` thành `int[]` hoặc giảm dung lượng của nguồn đã tồn tại.

Đối với danh sách bản ghi nghiệp vụ, đầu vào có thể tự nhiên là object: khi đó `stream().mapToInt(Order::quantity).sum()` là lựa chọn rõ nghĩa. Không nên thay mọi cấu trúc object thành primitive array nếu làm mô hình dữ liệu khó hiểu.

### 4.3. Chi phí thực tế và giới hạn của tối ưu

- Boxing/unboxing có thể thêm thao tác chuyển kiểu, đối tượng trung gian và áp lực garbage collector, **nhưng** JIT có thể tối ưu một số trường hợp; số object thực tế cần đo bằng profiler/benchmark.
- Kiểu generic trong Java dùng kiểu tham chiếu, nên `List<int>` không hợp lệ; `List<Integer>` cần wrapper. Nếu chỉ tính toán số học hoặc truyền lượng lớn dữ liệu primitive, `int[]` / `IntStream` thường là điểm bắt đầu hợp lý.
- `IntStream.sum()` dùng `int` và **có thể tràn số** theo quy tắc số nguyên Java; nếu giá trị có thể lớn, dùng `LongStream` hoặc chuyển bằng `mapToLong`; nếu cần phát hiện tràn, thiết kế thuật toán dùng `Math.addExact` phù hợp.
- `DoubleStream` tránh boxing `Double` nhưng vẫn chịu sai số biểu diễn dấu phẩy động; tiền tệ không nên dùng `double` chỉ vì có primitive specialization.
- `Stream<Integer>` không phải API lỗi thời; khi cần object hoặc cấu trúc generic, dùng nó là hoàn toàn hợp lệ. Tối ưu có ý nghĩa khi phù hợp kiểu dữ liệu và phép đo.

## 5. Những đặc tính ảnh hưởng tới cách chia

`Spliterator.characteristics()` trả một tập cờ bit thể hiện **hợp đồng nguồn**, không phải tùy chọn “gợi ý tối ưu bằng mọi giá”.

| Cờ | Ý nghĩa | Khi nào khai báo |
| --- | --- | --- |
| `ORDERED` | Có encounter order có nghĩa | Nguồn là dãy có thứ tự, ví dụ array theo chỉ số. |
| `SIZED` | Số phần tử còn lại xác định đúng theo đặc tả trong điều kiện thích hợp | Biết chính xác `fence - index` với nguồn không thay cấu trúc. |
| `SUBSIZED` | Các spliterator được chia từ nguồn cũng có `SIZED`, `SUBSIZED` | Chia thành những đoạn mà số phần tử của từng đoạn được biết chính xác. |
| `NONNULL` | Mỗi phần tử không phải `null` | Primitive specialization luôn đưa giá trị primitive. |
| `IMMUTABLE` | Nguồn không thể bị thay đổi theo ý nghĩa hợp đồng spliterator | Không đánh dấu chỉ vì đang đọc từ một `int[]` có thể bị sửa bởi mã khác. |
| `CONCURRENT` | Cho phép nguồn được thay đổi an toàn đồng thời theo hợp đồng riêng | Không đánh dấu cho array và bộ đọc thủ công thông thường. |
| `DISTINCT` | Các phần tử không trùng nhau theo ý nghĩa quy định | Không đánh dấu nếu có thể lặp số. |
| `SORTED` | Các phần tử có thứ tự sắp xếp theo comparator hoặc tự nhiên | Chỉ đánh dấu khi thật sự đã sắp; nếu `SORTED`, `getComparator` phải đúng hợp đồng. |

Đối với `int[]` có thể chứa số lặp, không được tự gắn `DISTINCT`. Một array chưa sắp không được gắn `SORTED`. Cờ sai có thể khiến pipeline bỏ bớt một số phép toán hoặc đưa ra tối ưu không hợp lệ, dẫn tới đáp án sai.

### 5.1. `estimateSize()` và `trySplit()` phải nhất quán

Giả sử còn tám phần tử, việc chia thành hai đoạn bốn phần tử nên cho phép tính:

```text
Trước split: estimateSize = 8
Sau split:
  phần tách ra: estimateSize = 4
  phần còn lại: estimateSize = 4

Hai phần không giao nhau; hợp lại bao phủ đúng 8 phần tử.
```

Nếu khai báo `SIZED` và `SUBSIZED`, số lượng ước tính phải tuân theo hợp đồng tương ứng. Không đánh dấu `SIZED` cho một nguồn sinh vô hạn hoặc nguồn có kích thước không biết chính xác. Điều này tác động cả **tính đúng đắn** và việc chia để parallel xử lý.

### 5.2. `Spliterator` có phải an toàn đa luồng?

`Spliterator` nhìn chung **không đòi hỏi thread-safe**. Trong một thuật toán song song đúng, mỗi spliterator con được chuyển giao để duyệt riêng; không để hai thread cùng gọi `tryAdvance`/`trySplit` trên **cùng đối tượng** một cách tùy tiện.

Với primitive array cũng cần tránh sửa nội dung array trong khi stream đang đọc, vì việc cập nhật đồng thời có thể khiến dữ liệu quan sát được không xác định. `OfInt` không tự bảo vệ array khỏi thay đổi; muốn dữ liệu thực sự bất biến đối với một lượt xử lý, hãy sở hữu riêng hoặc sao chép snapshot phù hợp trước khi xử lý.

## 6. Ví dụ đầy đủ: tự viết `Spliterator.OfInt` cho một lát cắt của `int[]`

Khi dữ liệu đến từ nguồn tùy biến, cần kiểm soát cách duyệt/chia hoặc muốn hiểu cơ chế, ta có thể tự cài đặt `Spliterator.OfInt`. Ví dụ dưới đây dùng một mảng `int[]` và chia theo **khoảng chỉ số [index, fence)**.

Đối với array bình thường, code thực tế nên ưu tiên `Arrays.stream(array)` hoặc `Spliterators.spliterator(array, ...)`; bản tự viết dùng để thấy rõ ba điều kiện: **không boxing khi duyệt primitive, không bỏ/trùng phần tử khi split và đúng characteristics**.

Lưu toàn bộ vào tệp **PrimitiveSpliteratorDemo.java** (Java 8 API, biên dịch/chạy được bằng JDK 17+):

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.function.IntConsumer;
import java.util.stream.StreamSupport;

public class PrimitiveSpliteratorDemo {
    static final class IntArraySlice implements Spliterator.OfInt {
        private final int[] data;
        private int index;
        private final int fence;

        IntArraySlice(int[] data, int index, int fence) {
            this.data = Objects.requireNonNull(data, "data");
            if (index < 0 || index > fence || fence > data.length) {
                throw new IndexOutOfBoundsException("Invalid slice");
            }
            this.index = index;
            this.fence = fence;
        }

        @Override
        public boolean tryAdvance(IntConsumer action) {
            Objects.requireNonNull(action, "action");
            if (index >= fence) {
                return false;
            }
            action.accept(data[index++]);
            return true;
        }

        @Override
        public void forEachRemaining(IntConsumer action) {
            Objects.requireNonNull(action, "action");
            while (index < fence) {
                action.accept(data[index++]);
            }
        }

        @Override
        public Spliterator.OfInt trySplit() {
            int lo = index;
            int mid = lo + ((fence - lo) >>> 1);
            if (mid <= lo) {
                return null;
            }
            index = mid;
            return new IntArraySlice(data, lo, mid);
        }

        @Override
        public long estimateSize() {
            return fence - index;
        }

        @Override
        public int characteristics() {
            return Spliterator.ORDERED
                | Spliterator.SIZED
                | Spliterator.SUBSIZED
                | Spliterator.NONNULL;
        }
    }

    public static void main(String[] args) {
        int[] values = {1, 2, 3, 4, 5, 6, 7, 8};

        Spliterator.OfInt right =
            new IntArraySlice(values, 0, values.length);
        System.out.println("Nguon SIZED: "
            + right.hasCharacteristics(Spliterator.SIZED));
        System.out.println("Nguon SUBSIZED: "
            + right.hasCharacteristics(Spliterator.SUBSIZED));

        Spliterator.OfInt left = right.trySplit();
        System.out.println("Do dai nua trai: " + left.estimateSize());
        System.out.println("Do dai nua phai: " + right.estimateSize());

        int leftSum = StreamSupport.intStream(left, false).sum();
        int rightSum = StreamSupport.intStream(right, false).sum();
        System.out.println("Tong hai nua: " + leftSum
            + " + " + rightSum + " = " + (leftSum + rightSum));

        int squaredEvens = StreamSupport.intStream(
                new IntArraySlice(values, 0, values.length), true)
            .filter(value -> value % 2 == 0)
            .map(value -> value * value)
            .sum();
        System.out.println("Tong binh phuong so chan: " + squaredEvens);

        int arraySum = Arrays.stream(values).sum();
        System.out.println("Arrays.stream(int[]) tong: " + arraySum);

        int fromBoxed = Arrays.asList(1, 2, 3, 4, 5, 6, 7, 8)
            .stream()
            .mapToInt(Integer::intValue)
            .sum();
        System.out.println("List<Integer> -> mapToInt: " + fromBoxed);

        Spliterator.OfInt builtIn =
            Spliterators.spliterator(values, Spliterator.ORDERED);
        int utilitySum = StreamSupport.intStream(builtIn, false).sum();
        System.out.println("Spliterators.spliterator: " + utilitySum);
    }
}
```

Trong thư mục chứa tệp, chạy:

```bash
javac -encoding UTF-8 PrimitiveSpliteratorDemo.java
java PrimitiveSpliteratorDemo
```

**Stdout dự kiến (độc lập với thời gian chạy):**

```text
Nguon SIZED: true
Nguon SUBSIZED: true
Do dai nua trai: 4
Do dai nua phai: 4
Tong hai nua: 10 + 26 = 36
Tong binh phuong so chan: 120
Arrays.stream(int[]) tong: 36
List<Integer> -> mapToInt: 36
Spliterators.spliterator: 36
```

### 6.1. Vì sao từng phần chạy đúng?

1. **`tryAdvance(IntConsumer)`** chuyển `data[index]` trực tiếp tới callback, sau đó dịch `index`. `forEachRemaining(IntConsumer)` xử lý liên tiếp phần còn lại, không cần biến thành `Integer`.
2. **`trySplit()`** tách khoảng `[0,8)` thành hai khoảng `[0,4)` và `[4,8)`. Chúng không trùng chỉ số, vì `fence` của phần trái được giữ bằng `mid` và `index` của phần phải được cập nhật thành `mid`. Nếu còn ít hơn hai phần tử, trả `null`.
3. **`estimateSize()`** trả `fence - index` chính xác cho từng lát cắt; nên `SIZED` và `SUBSIZED` là những đặc tính hợp lệ. `ORDERED` là thứ tự chỉ số, `NONNULL` là vì giá trị primitive không thể là `null`.
4. **Không gắn `IMMUTABLE`** vì `int[]` có thể bị thay đổi từ bên ngoài. Không gắn `SORTED` hoặc `DISTINCT` vì ví dụ không chứng minh những đặc tính đó cho mọi input.
5. Hai nhánh tạo từ một phép split được tiêu thụ độc lập; phần trái tổng `1+2+3+4 = 10`, phần phải tổng `5+6+7+8 = 26`. Mỗi stream chỉ chạy terminal operation một lần.
6. Pipeline song song `StreamSupport.intStream(..., true)` vẫn có đường đi primitive; `filter` loại số lẻ, `map` bình phương số chẵn `2,4,6,8` rồi `sum` tạo `4+16+36+64 = 120`. Ví dụ chỉ kiểm tra **tính đúng đắn**, không chứng minh song song nhanh hơn.
7. `Arrays.stream(values)` và tiện ích `Spliterators.spliterator(values, ...)` là các lựa chọn sẵn có cho array. Nguồn `Arrays.asList(...)` đã dùng wrapper từ đầu nên `mapToInt` chỉ giảm chuyển đổi trong các bước về sau.

## 7. Khi tự xây primitive spliterator cần giữ đúng hợp đồng

### 7.1. Lỗi mất và lặp phần tử khi chia

Giả sử một nguồn có khoảng `[0,100)`. Nếu `trySplit` trả spliterator mới cho `[0,50)` **nhưng không cập nhật spliterator gốc** vẫn ở `[0,100)`, các phần tử đầu bị duyệt hai lần. Nếu lại đổi gốc thành `[51,100)` thì phần tử `50` bị bỏ mất.

Cách tiếp cận đúng trong ví dụ:

```java
int lo = index;
int mid = lo + ((fence - lo) >>> 1);
if (mid <= lo) {
    return null;
}
index = mid;
return new IntArraySlice(data, lo, mid);
```

Đây là snippet bên trong `IntArraySlice.trySplit()`, không phải chương trình độc lập.

### 7.2. Lỗi báo đặc tính không đúng

Nếu nguồn vừa lọc vừa sinh dữ liệu bất định mà lại khai báo `SIZED` với số lượng gốc chưa lọc, các thuật toán tối ưu theo kích thước có thể đưa ra hành vi không đúng. Nếu nguồn có phần tử lặp nhưng khai báo `DISTINCT`, downstream có thể bỏ qua bước `distinct()` mà đáng lẽ phải chạy.

Hãy xem `characteristics` là **lời cam kết**; chỉ gắn khi bảo đảm đúng trong tất cả trạng thái hợp lệ của implementation. Đối với source mutable hoặc external iterator, việc binding, thread-safety và kiểm soát thay đổi nguồn cần thiết kế riêng.

### 7.3. Lỗi dùng callback kiểu wrapper không cần thiết

`IntConsumer` được thiết kế cho `int`. Nếu xử lý qua `Consumer<Integer>` trong mọi bước, bridge có thể tạo wrapper. Với callback số học hoặc thống kê, ưu tiên `IntConsumer` và `IntStream`. Chỉ dùng `boxed()` hoặc collector generic khi đầu ra cần object.

### 7.4. Lỗi cho nhiều thread thao tác cùng một instance

Primitive spliterator **không đồng nghĩa thread-safe**. `parallelStream()` hoạt động theo cách chia/ủy quyền phần nguồn; nó không cho phép ta gọi `tryAdvance` đồng thời trên một instance tự viết nếu instance không hỗ trợ đồng bộ. Đừng gửi cùng một `IntArraySlice` tới nhiều thread rồi tăng `index` không khóa.

## 8. Tránh boxing trong xử lý và tổng hợp

Sau khi đã có `IntStream`, nên duy trì pipeline primitive đến terminal operation nếu nhu cầu là phép tính số:

| Nhu cầu | API primitive | Lợi ích về kiểu |
| --- | --- | --- |
| Lọc số | `IntStream.filter(IntPredicate)` | `int` vào predicate |
| Biến đổi số | `IntStream.map(IntUnaryOperator)` | `int` vào và ra |
| Chuyển sang số dài | `IntStream.mapToLong(IntToLongFunction)` | `int → long` không qua wrapper |
| Tổng | `IntStream.sum()` | Trả `int` |
| Đếm | `IntStream.count()` | Trả `long` |
| Cực đại/cực tiểu | `IntStream.max()/min()` | Trả `OptionalInt` |
| Trung bình | `IntStream.average()` | Trả `OptionalDouble` |
| Thống kê | `IntStream.summaryStatistics()` | Trả `IntSummaryStatistics` |
| Gom vào đối tượng generic | `IntStream.boxed()` rồi `collect(...)` | Boxing cần thiết tại ranh giới object |

### 8.1. Dùng `IntStream.collect` để tích lũy vào object một cách có chủ đích

`IntStream` có overload `collect(Supplier<R>, ObjIntConsumer<R>, BiConsumer<R,R>)`. Callback `ObjIntConsumer` nhận **object tích lũy** và **giá trị `int`**, nên không cần boxing từng phần tử để gọi accumulator:

```java
int[] numbers = {2, 4, 6};
int[] total = Arrays.stream(numbers).collect(
    () -> new int[1],
    (accumulator, number) -> accumulator[0] += number,
    (left, right) -> left[0] += right[0]
);
// total[0] == 12
```

Đây là snippet hoàn chỉnh trong ngữ cảnh có `import java.util.Arrays;`. `int[1]` là vùng chứa mới cho mỗi nhánh, combiner cộng tổng khi hợp nhất; ví dụ chỉ minh họa primitive accumulator, còn bài toán cộng thuần túy nên dùng `sum()` rõ ràng hơn. Không dùng một mảng `total` chung làm supplier cho nhiều nhánh.

### 8.2. Chọn kiểu dữ liệu phù hợp

- **Tổng có nguy cơ tràn `int`:** chuyển sang `long` bằng `mapToLong` nếu miền giá trị đủ; việc chuyển kiểu không tự ngăn tràn `long`.
- **Tính tiền:** dùng `BigDecimal` khi cần quy tắc thập phân chính xác, dù điều này đòi hỏi object. “Tránh boxing” không phải ưu tiên cao hơn **đúng nghiệp vụ**.
- **Dữ liệu doanh nghiệp là object:** `orders.stream().mapToLong(Order::amountInCents).sum()` giữ object ở nguồn nhưng dùng primitive cho bước tính số.
- **Đầu ra cần object:** `boxed()` là chuyển đổi hợp lệ, chẳng hạn cần `List<Integer>` để gọi API; lúc đó không còn lợi thế không boxing từ đầu đến cuối.
- **Vùng chứa có thể thay đổi:** không dùng `reduce` trên cùng một `ArrayList` chia sẻ; dùng `collect` theo đúng hợp đồng.

## 9. Hiệu năng: primitive không đồng nghĩa luôn nhanh

Ba yếu tố cần đánh giá riêng biệt:

1. **Chi phí boxing/unboxing:** tăng chuyển đổi kiểu và có thể tăng allocation/GC khi pipeline tạo nhiều wrapper.
2. **Chi phí chia nguồn:** `trySplit` càng rẻ và cân bằng thì song song càng có cơ hội; một spliterator primitive vẫn có thể chia rất chậm nếu nguồn tự viết phụ thuộc một iterator tuần tự.
3. **Chi phí xử lý và ghép kết quả:** nếu phép toán chỉ cộng vài chục số thì thời gian quá nhỏ để overhead parallel được bù lại.

Ví dụ `Arrays.stream(intArray).parallel().sum()` vẫn có thể chậm hơn `Arrays.stream(intArray).sum()` trên đầu vào nhỏ hoặc workload nhẹ, mặc dù cả hai đều primitive. Chỉ bật song song khi có ích cho bài toán cụ thể.

### 9.1. Đo bằng phương pháp đúng

Khi thực sự cần tối ưu, hãy so sánh các pipeline trên tập dữ liệu đại diện:

- Dùng cùng dữ liệu và xác nhận **kết quả giống nhau**.
- Warm-up JVM, chạy nhiều lần và đo throughput hoặc latency; không kết luận từ một lần `System.nanoTime()`.
- Nếu là microbenchmark, dùng **JMH** với warmup, forks, measurement và tránh compiler loại bỏ phép tính.
- Quan sát allocation rate, GC, CPU và contention, thay vì chỉ đo wall-clock time.
- Không đổi array/collector để “tăng tốc” khi bottleneck thực sự nằm ở đọc dữ liệu, network hoặc thao tác nghiệp vụ khác.

Lưu ý `parallel` không được thiết kế để làm cơ chế giới hạn đồng thời của các tác vụ I/O. Primitive specialization chủ yếu giải quyết **dạng dữ liệu và callback primitive**, không phải một giải pháp chung cho mọi vấn đề hiệu năng.

## 10. Bảng quyết định áp dụng

| Tình huống | Hướng làm phù hợp |
| --- | --- |
| Đã có `int[]` và chỉ cần tổng/lọc/thống kê | `Arrays.stream(int[])` với `IntStream` |
| Sinh dãy số nguyên tuần tự theo khoảng | `IntStream.range/rangeClosed` |
| Cần tạo Stream từ primitive source tùy biến | Tự cài `Spliterator.OfInt` khi cần; dùng `StreamSupport.intStream` |
| Đã có `long[]`, `double[]` | `LongStream`, `DoubleStream` hoặc `Spliterator.OfLong/OfDouble` |
| Đã có `List<Integer>` và cần tính số | `list.stream().mapToInt(Integer::intValue)` |
| Cần `List<Integer>` kết quả | `IntStream.boxed().collect(Collectors.toList())` hoặc phương án object phù hợp |
| Muốn tính trung bình/đếm trên primitive | `average()`, `count()`, `summaryStatistics()` |
| Muốn parallel | Trước hết bảo đảm `trySplit` đúng, dữ liệu chia tốt, phép xử lý đủ nặng; sau đó benchmark |
| Nguồn object chứa các trường số | Giữ mô hình object, chuyển sang primitive ở bước `mapToInt/Long/Double` phù hợp |
| Nguồn mutable hoặc thay đổi đồng thời | Sở hữu snapshot hoặc thiết kế binding/interference đúng, không tự khai báo `IMMUTABLE/CONCURRENT` |

## 11. Tự kiểm tra và lỗi thường gặp

**Câu hỏi 1:** Vì sao `Spliterator.OfInt` vẫn mở rộng `Spliterator<Integer>` nhưng có thể tránh boxing?

**Trả lời:** nó cung cấp `tryAdvance(IntConsumer)`, `forEachRemaining(IntConsumer)` và `trySplit()` chuyên biệt. `IntConsumer.accept(int)` nhận primitive; chỉ khi đi qua callback `Consumer<Integer>` hoặc API object thì boxing mới trở thành vấn đề tương ứng.

**Câu hỏi 2:** Với `int[] {1,2,3,4}`, sau `trySplit()` phần trái nhận `[1,2]`, phần phải nhận `[3,4]`. Hai kết quả `sum` phải là gì?

**Trả lời:** `3` và `7`, gộp lại `10`. Nếu tổng không bằng tổng nguồn, cần kiểm tra thiếu/trùng vùng chỉ số khi chia.

**Câu hỏi 3:** Nếu đã có `List<Integer>`, gọi `mapToInt` có biến nguồn thành array primitive không?

**Trả lời:** không. Nó chuyển từng `Integer` thành `int` cho pipeline phía sau; các wrapper của nguồn vẫn tồn tại.

**Câu hỏi 4:** Có nên đánh dấu `IMMUTABLE` cho một spliterator đọc từ `int[]` nếu các phương thức của spliterator không sửa phần tử?

**Trả lời:** không tự động. Dữ liệu mảng có thể bị sửa từ bên ngoài; chỉ dùng `IMMUTABLE` khi nguồn thực sự đáp ứng hợp đồng.

**Câu hỏi 5:** Khi nào nên tự viết `OfInt` thay vì dùng `Arrays.stream`?

**Trả lời:** khi cần nguồn primitive hoặc cách phân chia đặc thù mà các API sẵn có không đáp ứng, và có thể giữ đúng các luật về phạm vi, đặc tính và tình trạng thay đổi nguồn.

**Câu hỏi 6:** Nếu chuyển sang `IntStream` mà code vẫn chậm, có chắc vấn đề không phải boxing?

**Trả lời:** không. Cần profile/benchmark để xác định chi phí thực sự; có thể bottleneck ở thuật toán, bộ nhớ, I/O, phân chia hoặc phép tổng hợp.

**Những lỗi cần tránh:**

- Tự động `boxed()` chỉ để tiếp tục `map`/`filter` bằng số nguyên.
- Cho rằng mọi `Integer` đều được cấp phát mới trên heap.
- Ghi sai `SIZED`, `SUBSIZED`, `SORTED`, `DISTINCT` hoặc `IMMUTABLE`.
- Trả hai spliterator con duyệt chồng lấn hoặc bỏ sót phần tử.
- Dùng một spliterator đồng thời ở nhiều thread.
- Tái sử dụng stream sau terminal operation.
- Nhầm “đã gọi `parallel()`” với “chắc chắn nhanh hơn”.
- Bỏ qua tràn số, sai số thập phân và đúng/sai nghiệp vụ khi tối ưu.

## 12. Tài liệu API chính thức (đang được duy trì)

Các giao diện dưới đây là một phần của Java Stream/Spliterator API từ Java 8 và tiếp tục được hỗ trợ trong JDK hiện đại:

- [`Spliterator.OfInt` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.OfInt.html): overload primitive, callback bridge và cách duyệt.
- [`Spliterator` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html): `trySplit`, `estimateSize`, đặc tính và hạn chế thread-safety.
- [`Spliterators` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterators.html): các phương thức tạo `OfInt/OfLong/OfDouble` từ array/iterator primitive.
- [`StreamSupport` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/StreamSupport.html): tạo `IntStream`, `LongStream` và `DoubleStream` từ primitive spliterator.
- [`IntStream` — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html): `map`, `mapToLong`, `boxed`, `summaryStatistics`, `collect`.
- [JMH — OpenJDK Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): phương pháp đo microbenchmark.
