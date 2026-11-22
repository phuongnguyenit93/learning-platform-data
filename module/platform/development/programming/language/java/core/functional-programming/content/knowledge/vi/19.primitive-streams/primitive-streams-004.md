# `OptionalInt`, `OptionalLong` và `OptionalDouble` trong Java

Khi xử lý dữ liệu bằng `IntStream`, `LongStream` và `DoubleStream`, một số phép toán như `min()`, `max()`, `average()`, `findFirst()` và `findAny()` không phải lúc nào cũng có kết quả. Stream có thể **rỗng**, nên Java dùng các kiểu `OptionalInt`, `OptionalLong` và `OptionalDouble` để thể hiện rõ “có một giá trị nguyên thủy” hoặc “không có giá trị”.

Ba kiểu này thuộc package `java.util`, xuất hiện từ Java 8. Chúng giống `Optional<T>` về ý nghĩa biểu diễn tính tùy chọn, nhưng được chuyên biệt cho `int`, `long` và `double`. Bài học trình bày cách tạo, nhận, chuyển và sử dụng các kiểu này an toàn, đặc biệt trong **terminal operation của primitive stream**.

## 1. Tại sao primitive stream trả về Optional nguyên thủy?

Xét các nguồn:

```java
IntStream.of(3, 8, 5).max(); // Có kết quả: 8.
IntStream.empty().max();    // Không có giá trị lớn nhất.
```

Đây là đoạn minh họa cần `import java.util.stream.IntStream;`. Trên stream rỗng, “giá trị lớn nhất” không tồn tại; dùng `0`, `-1` hoặc `Integer.MIN_VALUE` làm kết quả mặc định ngay trong API có thể gây nhầm lẫn, vì chính các số đó cũng có thể là dữ liệu hợp lệ.

`OptionalInt` mang hai trạng thái:

- **Present:** có một giá trị `int` thực sự, kể cả `0`, số âm và `Integer.MIN_VALUE`.
- **Empty:** không có giá trị; không đồng nghĩa với số `0`.

Tương tự, `OptionalLong` mang `long`, còn `OptionalDouble` mang `double`. Một `OptionalDouble` đang present có thể chứa `0.0`, `-0.0`, `Double.NaN` hoặc infinity: chúng vẫn là **giá trị**, không phải trạng thái empty.

| Kiểu | Lưu giá trị kiểu | Lấy giá trị | Tạo present | Tạo empty |
| --- | --- | --- | --- | --- |
| `OptionalInt` | `int` | `getAsInt()` | `OptionalInt.of(10)` | `OptionalInt.empty()` |
| `OptionalLong` | `long` | `getAsLong()` | `OptionalLong.of(10L)` | `OptionalLong.empty()` |
| `OptionalDouble` | `double` | `getAsDouble()` | `OptionalDouble.of(2.5)` | `OptionalDouble.empty()` |

Không có `OptionalFloat`, `OptionalByte`, `OptionalShort` hay `OptionalChar` trong Java SE. Trường hợp cần các kiểu ấy, hãy chọn API và kiểu biểu diễn phù hợp thay vì giả định Java có đủ mọi specialization.

## 2. Các terminal operation tạo ra kiểu nào?

Trên `IntStream`:

| Operation | Kiểu trả về | Khi stream rỗng |
| --- | --- | --- |
| `min()` | `OptionalInt` | Empty |
| `max()` | `OptionalInt` | Empty |
| `findFirst()` | `OptionalInt` | Empty |
| `findAny()` | `OptionalInt` | Empty |
| `average()` | `OptionalDouble` | Empty |
| `sum()` | `int` | `0` |
| `count()` | `long` | `0L` |

`LongStream` có `min()`, `max()`, `findFirst()` và `findAny()` trả `OptionalLong`; `average()` vẫn trả **`OptionalDouble`** vì trung bình có thể có phần thập phân. `DoubleStream` dùng `OptionalDouble` cho cả các phép `min()`, `max()`, `findFirst()`, `findAny()` và `average()`.

`sum()` và `count()` có giá trị trung tính được định nghĩa cho stream rỗng: tổng là 0 và số lượng là 0. Ngược lại, `min()`, `max()` và `average()` không thể chọn một giá trị hữu hạn chung làm “không có kết quả” cho mọi tập dữ liệu.

Ví dụ:

```java
int sum = IntStream.empty().sum();                // 0
long count = IntStream.empty().count();           // 0L
OptionalDouble avg = IntStream.empty().average(); // OptionalDouble.empty()
```

Đây là đoạn minh họa đặt trong phương thức, dùng `java.util.OptionalDouble` và `java.util.stream.IntStream`. Không được nhầm **trung bình của tập rỗng** với `0.0`.

## 3. Chương trình Java 17+ có thể biên dịch và chạy

Lưu thành `PrimitiveOptionalDemo.java`:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveOptionalDemo {
    public static void main(String[] args) {
        OptionalInt max = IntStream.of(12, 7, 19).max();
        OptionalLong first = LongStream.empty().findFirst();
        OptionalDouble average =
                DoubleStream.of(2.0, 4.0, 6.0).average();

        System.out.println("max present = " + max.isPresent());
        System.out.println("max = " + max.orElse(-1));
        System.out.println("first present = " + first.isPresent());
        System.out.println("first fallback = " + first.orElse(100L));
        System.out.println("average = " + average.orElseThrow());

        OptionalDouble intAverage = IntStream.of(1, 2).average();
        System.out.println("int average = " + intAverage.orElseThrow());

        OptionalInt noMinimum = IntStream.empty().min();
        System.out.println("empty fallback = " + noMinimum.orElse(99));

        max.ifPresent(n -> System.out.println("ifPresent = " + n));

        noMinimum.ifPresentOrElse(
                n -> System.out.println("minimum = " + n),
                () -> System.out.println("minimum absent")
        );

        System.out.println("mapped stream = " +
                max.stream()
                        .map(n -> n * 2)
                        .boxed()
                        .toList());

        OptionalDouble nanValue =
                DoubleStream.of(Double.NaN).findFirst();
        System.out.println("NaN present = " + nanValue.isPresent());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

Stdout **xác định**:

```text
max present = true
max = 19
first present = false
first fallback = 100
average = 4.0
int average = 1.5
empty fallback = 99
ifPresent = 19
minimum absent
mapped stream = [38]
NaN present = true
```

Giải thích từng điểm:

1. `max()` tìm thấy số nguyên lớn nhất `19`, nên `OptionalInt` đang present và `orElse(-1)` trả `19`.
2. `LongStream.empty().findFirst()` không có phần tử: `OptionalLong` empty, `isPresent()` là `false`, `orElse(100L)` cung cấp giá trị dự phòng.
3. `DoubleStream.average()` của `2.0, 4.0, 6.0` là `4.0`; `IntStream.average()` của `1, 2` là `1.5`, vì kết quả trung bình là `double`.
4. `noMinimum` empty nên `orElse(99)` trả `99`; `ifPresentOrElse` chạy nhánh `Runnable` thứ hai.
5. `max.stream()` chuyển một `OptionalInt` present thành `IntStream` một phần tử. `map(n -> n * 2)` tạo `38`, `boxed()` đổi sang `Stream<Integer>`, và `toList()` chứa `[38]`.
6. `Double.NaN` là **một giá trị `double` có mặt**, nên `OptionalDouble.of(Double.NaN)` hoặc kết quả `findFirst()` tương ứng vẫn `isPresent() == true`.

## 4. Cách lấy giá trị an toàn

Các phương thức chính:

| API | Hành vi khi present | Hành vi khi empty |
| --- | --- | --- |
| `isPresent()` | `true` | `false` |
| `isEmpty()` (Java 11+) | `false` | `true` |
| `getAsInt()`, `getAsLong()`, `getAsDouble()` | Trả primitive tương ứng | Ném `NoSuchElementException` |
| `orElse(defaultValue)` | Trả giá trị hiện có | Trả giá trị dự phòng |
| `orElseGet(supplier)` | Trả giá trị hiện có | Gọi supplier để tạo giá trị |
| `orElseThrow()` (Java 10+) | Trả giá trị hiện có | Ném `NoSuchElementException` |
| `orElseThrow(exceptionSupplier)` | Trả giá trị hiện có | Ném ngoại lệ do supplier tạo |
| `ifPresent(action)` | Gọi action với giá trị | Không làm gì |
| `ifPresentOrElse(action, emptyAction)` (Java 9+) | Gọi action | Gọi emptyAction |
| `stream()` (Java 9+) | Stream primitive có một phần tử | Stream primitive rỗng |

Với `OptionalLong` và `OptionalDouble`, các supplier/action có kiểu primitive tương ứng, ví dụ `LongSupplier`, `DoubleSupplier`, `LongConsumer`, `DoubleConsumer`. Nhờ đó API không phải dùng `Long`/`Double` wrapper chỉ để truyền giá trị.

### Đừng gọi `getAsX()` mà chưa kiểm tra

```java
OptionalInt count = OptionalInt.empty();
int value = count.getAsInt(); // Ném NoSuchElementException!
```

Đây là đoạn minh họa **lỗi cần tránh**, dùng `import java.util.OptionalInt;`. Không dùng `getAsInt()` chỉ vì nghĩ “có thể mặc định bằng 0”. Nếu thiếu dữ liệu là một trường hợp hợp lệ, chọn `orElse`, `orElseGet` hoặc `ifPresentOrElse`; nếu thiếu dữ liệu là một lỗi, `orElseThrow` phù hợp hơn.

### `orElse` khác `orElseGet`

```java
OptionalInt found = OptionalInt.of(10);

int a = found.orElse(0);       // 10
int b = found.orElseGet(() -> computeDefault()); // 10
```

Đoạn trên là **mã minh họa** trong phương thức có `computeDefault()` trả `int`. Với `orElseGet`, supplier chỉ được gọi khi optional empty. Với `orElse(value)`, **biểu thức tính tham số value được đánh giá trước khi gọi method**, dù optional đang present.

Ví dụ sự khác biệt:

```java
int first = found.orElse(expensiveFallback());
int second = found.orElseGet(() -> expensiveFallback());
```

Nếu `found` đang present, lời gọi `expensiveFallback()` trong biểu thức thứ nhất **vẫn chạy**; ở biểu thức thứ hai nó **không chạy**. Đây là lý do thường chọn `orElseGet` khi fallback tốn công, có I/O hoặc tác dụng phụ. Với một hằng số như `0`, `-1` hoặc `0.0`, `orElse` đơn giản và rõ ràng.

### Chỉ định lỗi đúng ngữ cảnh bằng `orElseThrow`

```java
int largest = IntStream.of(4, 9, 2)
        .max()
        .orElseThrow(() -> new IllegalStateException("Không có dữ liệu"));
```

Đây là đoạn minh họa trong phương thức có `import java.util.stream.IntStream;`. Nếu không có phần tử, caller nhận một ngoại lệ rõ nghĩa. Nếu dữ liệu có thể rỗng theo nghiệp vụ, đừng biến trạng thái empty thành lỗi không cần thiết.

## 5. “Không có giá trị” khác với “giá trị bằng 0”

Một lỗi thiết kế phổ biến là dùng **sentinel** làm dấu hiệu vắng mặt:

```java
// Dễ nhầm: -1 có thể là giá trị thực của dữ liệu!
int smallest = IntStream.of(-1, 0, 3).min().orElse(-1);
```

Đoạn trên là minh họa; cả trường hợp **có kết quả `-1`** và **không có kết quả** đều có thể cho biến `smallest` bằng `-1`. Nếu ứng dụng cần phân biệt, giữ `OptionalInt`:

```java
OptionalInt smallest = IntStream.of(-1, 0, 3).min();

if (smallest.isPresent()) {
    System.out.println("min = " + smallest.getAsInt());
} else {
    System.out.println("Không có phần tử");
}
```

Đây là đoạn minh họa với `import java.util.OptionalInt;` và `java.util.stream.IntStream;`. `getAsInt()` trong nhánh `if` là an toàn vì đã kiểm tra `isPresent()`.

Với số thực, không nên dùng `Double.NaN` làm dấu hiệu “không có kết quả” một cách ngầm định: `NaN` là một giá trị thực sự có thể xuất hiện trong `DoubleStream`. `OptionalDouble.empty()` biểu diễn vắng mặt rõ ràng, còn `OptionalDouble.of(Double.NaN)` là present.

## 6. `OptionalDouble` đặc biệt hữu ích cho trung bình

Đây là trường hợp thường dễ nhầm nhất:

```java
OptionalDouble average = IntStream.of(1, 2, 3, 4).average();
// present, giá trị 2.5
```

Dù nguồn là `IntStream`, trung bình cần chứa phần thập phân nên kiểu kết quả là `OptionalDouble`. Tương tự:

```java
OptionalDouble longAverage = LongStream.of(10L, 11L).average();
// present, giá trị 10.5

OptionalDouble absentAverage = DoubleStream.empty().average();
// empty, KHÔNG phải 0.0
```

Đây là các đoạn minh họa cần import `java.util.OptionalDouble`, `java.util.stream.IntStream`, `java.util.stream.LongStream` và `java.util.stream.DoubleStream`.

Với dữ liệu cực lớn, phép tính trung bình trên primitive stream vẫn phải tuân theo đặc tính số học của Java, bao gồm giới hạn độ chính xác của `double`; kết quả không phải lúc nào cũng thể hiện chính xác mọi phân số. Nếu tính toán tiền tệ cần độ chính xác thập phân theo quy tắc nghiệp vụ, cân nhắc `BigDecimal` với chính sách scale/rounding phù hợp thay vì mặc định `DoubleStream.average()`.

## 7. Chuyển Optional nguyên thủy trở lại stream

Ba kiểu có các phương thức:

- `OptionalInt.stream()` trả `IntStream` với 0 hoặc 1 phần tử.
- `OptionalLong.stream()` trả `LongStream` với 0 hoặc 1 phần tử.
- `OptionalDouble.stream()` trả `DoubleStream` với 0 hoặc 1 phần tử.

Ví dụ sử dụng khi muốn nối kết quả tùy chọn vào pipeline:

```java
List<Integer> presentValues = List.of(
        OptionalInt.of(3),
        OptionalInt.empty(),
        OptionalInt.of(8)
).stream()
        .flatMapToInt(OptionalInt::stream)
        .boxed()
        .toList();
// [3, 8]
```

Đây là snippet đặt trong phương thức, cần `import java.util.List;`, `java.util.OptionalInt;`. `flatMapToInt` làm phẳng ba `IntStream` con (mỗi stream có 0 hoặc 1 phần tử), bỏ các trường hợp empty mà không dùng `null`.

Nếu chỉ xử lý một `OptionalInt`, có thể tiếp tục bằng primitive stream:

```java
int doubled = OptionalInt.of(9)
        .stream()
        .map(n -> n * 2)
        .findFirst()
        .orElseThrow();
// 18
```

Đây là đoạn minh họa Java 17 hợp lệ. Điểm đáng chú ý là `OptionalInt` **không có** các phương thức `map`, `filter` và `flatMap` đầy đủ như `Optional<Integer>`; khi muốn dùng các phép biến đổi kiểu Stream có thể chuyển qua `.stream()` hoặc viết logic rõ ràng bằng `isPresent`/`ifPresent`.

### `OptionalInt` khác `Optional<Integer>`

`OptionalInt` chứa **primitive `int`**, trong khi `Optional<Integer>` chứa **wrapper `Integer`**. Ví dụ:

```java
OptionalInt primitive = OptionalInt.of(7);
java.util.Optional<Integer> boxed =
        primitive.isPresent()
                ? java.util.Optional.of(primitive.getAsInt())
                : java.util.Optional.empty();
```

Đoạn minh họa dùng `import java.util.OptionalInt;`. Cách chuyển sang generic optional cần boxing. Generic `Optional<Integer>` linh hoạt hơn về `map`, `filter` và `flatMap`, nhưng phải dùng wrapper; primitive optional giúp tránh boxing **ở chính giá trị tùy chọn được chứa** và tương thích trực tiếp với primitive stream.

Không nên suy ra rằng primitive optional luôn nhanh hơn trong mọi ngữ cảnh. Các wrapper vẫn có thể xuất hiện khi lưu trong generic collections, khi boxing qua `boxed()`, hoặc khi gọi API nhận object. Chọn kiểu theo hợp đồng và tính rõ ràng trước, rồi đo hiệu năng nếu cần.

## 8. `findFirst()`, `findAny()` và thứ tự của nguồn

Một `OptionalInt` từ `findFirst()` biểu diễn **phần tử đầu theo encounter order**, khi stream có thứ tự. Ví dụ:

```java
OptionalInt first = IntStream.of(5, 2, 9)
        .parallel()
        .findFirst();
// present, giá trị 5.
```

Đây là snippet bên trong phương thức, cần `import java.util.OptionalInt;` và `java.util.stream.IntStream;`.

Ngược lại, `findAny()` cho phép chọn một phần tử bất kỳ để hỗ trợ thực thi song song. Nếu viết:

```java
OptionalInt any = IntStream.of(5, 2, 9)
        .parallel()
        .findAny();
```

`any` có giá trị present vì nguồn không rỗng, nhưng **không được cam kết** luôn là `5`. Không nên viết assertion đòi hỏi một số cụ thể từ `findAny()`.

Ở nguồn rỗng, cả `findFirst()` lẫn `findAny()` đều tạo optional empty. Trạng thái present/empty độc lập với việc stream chạy tuần tự hay song song.

## 9. Các lỗi và bẫy thường gặp

1. **Gọi `getAsInt()`/`getAsLong()`/`getAsDouble()` trên empty:** sẽ ném `NoSuchElementException`. Ưu tiên `orElse`, `orElseGet`, `orElseThrow` hoặc `ifPresentOrElse` theo chính sách nghiệp vụ.
2. **Hiểu empty là 0:** `OptionalInt.empty()` khác `OptionalInt.of(0)`. `OptionalDouble.empty()` cũng khác `OptionalDouble.of(0.0)`.
3. **Nhầm kiểu `IntStream.average()`:** nó trả `OptionalDouble`, không phải `OptionalInt`.
4. **Tưởng mọi terminal operation trả Optional:** `sum()` trả primitive và `count()` trả `long`. `min()`, `max()`, `average()` và `findFirst()/findAny()` mới là các ví dụ Optional thường gặp.
5. **Dùng sentinel có thể là giá trị hợp lệ:** `orElse(-1)` chỉ an toàn nếu nghiệp vụ quy định `-1` là đại diện được chấp nhận cho trường hợp empty.
6. **Gọi fallback tốn kém trong `orElse(f())`:** đối số `f()` được đánh giá kể cả khi optional present. Chọn `orElseGet(() -> f())` nếu chỉ muốn tính khi empty.
7. **Tìm `map` trực tiếp trên `OptionalInt`:** API primitive optional không có hệ thống `map/filter/flatMap` như generic `Optional<T>`. Dùng `.stream()` hoặc logic tường minh.
8. **Đồng nhất `NaN` với empty:** `OptionalDouble.of(Double.NaN).isPresent()` là `true`.
9. **Nhầm `OptionalInt` với `IntStream`:** optional có tối đa một giá trị; stream có thể có 0, 1 hoặc nhiều giá trị. `stream()` trên optional đổi sang stream 0/1 phần tử.
10. **Dùng `findAny()` để chọn phần tử đầu chắc chắn:** không có bảo đảm ấy, đặc biệt khi chạy song song.
11. **Truy cập `Optional` như object định danh:** các kiểu Optional là *value-based classes*; tránh dùng `==` hay khóa đồng bộ trên đối tượng Optional. So sánh bằng `equals` khi cần xét trạng thái và giá trị.
12. **Bỏ qua xử lý trường hợp rỗng trong giao diện API:** nếu dữ liệu có thể rỗng theo hợp đồng, hãy quyết định rõ trả empty, dùng fallback hay báo lỗi. Không “ép” có giá trị bằng `getAsX()` rồi hy vọng nguồn không bao giờ rỗng.

## 10. Tự kiểm tra kiến thức

**Câu 1.** `IntStream.empty().max().orElse(0)` cho số nào? Có đồng nghĩa với việc stream có số lớn nhất bằng `0` không?

**Đáp án:** Trả `0` do fallback. Stream ban đầu **rỗng**; không tồn tại số lớn nhất. Nếu cần phân biệt, giữ `OptionalInt` và kiểm tra presence.

**Câu 2.** `LongStream.of(1L, 2L).average()` trả `OptionalLong` hay `OptionalDouble`?

**Đáp án:** `OptionalDouble`, với giá trị hiện diện là `1.5`.

**Câu 3.** Có thể dùng `OptionalInt.of(0).isPresent()` để kiểm tra giá trị 0 không?

**Đáp án:** `true`. Presence cho biết **có giá trị**, bất kể giá trị bằng bao nhiêu.

**Câu 4.** `OptionalInt.empty().stream().count()` bằng bao nhiêu?

**Đáp án:** `0`. Optional empty tạo `IntStream` không có phần tử.

**Câu 5.** `OptionalDouble.of(Double.NaN).isPresent()` là gì?

**Đáp án:** `true`. NaN không phải trạng thái empty.

**Câu 6.** Khi `OptionalInt` empty, `orElseGet(supplier)` và `orElse(defaultValue)` đều có thể cho một giá trị dự phòng. Khác biệt quan trọng nhất là gì?

**Đáp án:** `orElseGet` chỉ gọi supplier khi empty; đối số truyền vào `orElse` đã được tính trước khi phương thức chạy.

## Ghi nhớ

- `OptionalInt`, `OptionalLong`, `OptionalDouble` biểu diễn **một giá trị primitive có mặt hoặc không có mặt**, không dùng `null`.
- `min`, `max`, `findFirst`, `findAny` của primitive stream thường trả optional tương ứng; `average()` trả **`OptionalDouble`**.
- Với empty, `getAsInt`/`getAsLong`/`getAsDouble` ném `NoSuchElementException`; hãy chọn cách xử lý theo hợp đồng nghiệp vụ.
- `orElse` dùng cho fallback đơn giản, `orElseGet` dùng để tính fallback khi cần, `orElseThrow` dùng khi thiếu kết quả là lỗi.
- `stream()` của primitive optional tạo stream primitive 0 hoặc 1 phần tử, thuận tiện để nối pipeline.
- **Giá trị 0 hoặc NaN vẫn là present**. Không dùng sentinel khi cần phân biệt thật sự giữa vắng mặt và giá trị hợp lệ.
