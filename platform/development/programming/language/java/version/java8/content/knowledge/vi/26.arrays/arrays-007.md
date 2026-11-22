# Arrays.stream và Spliterator: duyệt, chia nguồn và xử lý mảng trong Java

> **Chủ đề:** Java 8 — Mảng. Bài tập trung vào cách tạo Stream bằng `Arrays.stream(...)` và cách nhận, thao tác `Spliterator` từ mảng bằng `Arrays.spliterator(...)`. Các API nêu dưới đây vẫn được hỗ trợ ở Java hiện hành; ví dụ chính biên dịch theo chuẩn Java 8.

## 1. Bức tranh tổng thể

Mảng Java (`T[]`, `int[]`, `long[]`, `double[]`, v.v.) lưu các phần tử có chỉ số từ `0` đến `length - 1`. Từ Java 8, ta có thể tiếp cận nội dung mảng bằng **Stream API** và **Spliterator API**:

- **`Arrays.stream(array)`**: tạo một luồng dữ liệu để viết pipeline như `filter`, `map`, `sum`, `sorted` và `collect`. Stream là giao diện xử lý dữ liệu ở mức cao; các bước trung gian thường lazy.
- **`Arrays.spliterator(array)`**: tạo một đối tượng hỗ trợ **duyệt** và **tách phạm vi phần tử** thành các phần có thể xử lý độc lập; đây là một cơ chế nguồn dữ liệu mà Stream có thể sử dụng.
- **`StreamSupport.stream(...)` / `intStream(...)`**: kết nối Spliterator với Stream, có tham số quyết định chế độ tuần tự hay song song.

Ví dụ khởi đầu:

~~~java
int[] numbers = {3, 1, 4, 1, 5, 9};

int total = Arrays.stream(numbers).sum(); // 23

Spliterator.OfInt source = Arrays.spliterator(numbers);
long size = source.getExactSizeIfKnown(); // 6
~~~

Đây là **đoạn minh họa**, cần `import java.util.Arrays;` và `import java.util.Spliterator;`. `Arrays.stream(numbers)` tạo `IntStream`; `Arrays.spliterator(numbers)` trả `Spliterator.OfInt`. Hai đối tượng phục vụ hai mức trừu tượng khác nhau, không phải hai tên gọi của cùng một object.

~~~text
int[] array
   |
   +-- Arrays.stream(array) --> IntStream --> filter/map/sum/collect
   |
   +-- Arrays.spliterator(array) --> Spliterator.OfInt
                                          |
                                          +-- tryAdvance / forEachRemaining
                                          +-- estimateSize / characteristics
                                          +-- trySplit --> prefix + remainder
                                          |
                                          +-- StreamSupport.intStream(...)
~~~

Sơ đồ mô tả các lối sử dụng API. Nó **không hứa** JVM luôn tạo số lượng task hay dùng một chiến lược phân chia cố định khi chạy parallel.

## 2. Các overload của Arrays.stream

`java.util.Arrays` có các overload sau từ Java 8:

| Đầu vào | Kết quả | Ví dụ |
| --- | --- | --- |
| `T[]` | `Stream<T>` | `Arrays.stream(String[])` |
| `T[], int startInclusive, int endExclusive` | `Stream<T>` | `Arrays.stream(words, 1, 3)` |
| `int[]` | `IntStream` | `Arrays.stream(ints)` |
| `int[], int startInclusive, int endExclusive` | `IntStream` | `Arrays.stream(ints, 1, 4)` |
| `long[]` | `LongStream` | `Arrays.stream(longs)` |
| `long[], int startInclusive, int endExclusive` | `LongStream` | `Arrays.stream(longs, 0, 2)` |
| `double[]` | `DoubleStream` | `Arrays.stream(doubles)` |
| `double[], int startInclusive, int endExclusive` | `DoubleStream` | `Arrays.stream(doubles, 2, 5)` |

Các tên `String[]`, `int[]` trong bảng chỉ là **minh họa kiểu tham số**, không phải biểu thức Java có thể viết trực tiếp như một lời gọi. Điểm cần nhớ là Stream chuyên biệt cho ba kiểu số nguyên thủy `int`, `long`, `double`.

### 2.1. Mảng đối tượng tạo Stream<T>

~~~java
String[] names = {"An", "Binh", "Chi"};

List<String> upper = Arrays.stream(names)
        .map(s -> s.toUpperCase(Locale.ROOT))
        .collect(Collectors.toList());
~~~

Đây là **đoạn minh họa**, cần import `Arrays`, `List`, `Locale` và `Collectors`. Kết quả là `[AN, BINH, CHI]`, không làm thay đổi các chuỗi trong mảng gốc. `Locale.ROOT` giúp ví dụ đổi chữ thường/hoa không phụ thuộc cấu hình locale của máy.

`Stream<T>` hỗ trợ các thao tác như `map`, `flatMap`, `distinct`, `sorted`, `collect`, `toArray`. Chọn terminal operation theo đầu ra mong muốn; không tự suy ra `Arrays.stream` tạo bản sao của mảng.

### 2.2. Mảng int tạo IntStream

~~~java
int[] values = {2, 3, 5, 7};

int sum = Arrays.stream(values).sum();                 // 17
double average = Arrays.stream(values).average()
        .orElse(0.0);                                 // 4.25
long count = Arrays.stream(values).filter(n -> n > 3)
        .count();                                      // 2
~~~

Đây là **đoạn minh họa**. `IntStream` có các terminal operation chuyên biệt như `sum`, `average`, `min`, `max`, `summaryStatistics` và `toArray`; không cần boxing mọi phần tử thành `Integer` chỉ để cộng hay đếm.

**Lưu ý:** `IntStream.average()` trả `OptionalDouble` vì nguồn có thể rỗng. Khi dùng `orElse(0.0)`, giá trị `0.0` là **chính sách fallback của ứng dụng**, không phải trung bình toán học của tập rỗng. Tùy nghiệp vụ có thể giữ `OptionalDouble` và xử lý trường hợp không có dữ liệu rõ ràng.

### 2.3. long[] và double[]

~~~java
long[] milliseconds = {100L, 200L, 300L};
long totalMillis = Arrays.stream(milliseconds).sum(); // 600

double[] readings = {1.5, 2.5};
double readingTotal = Arrays.stream(readings).sum();   // 4.0
~~~

Đây là **đoạn minh họa**. `LongStream`/`DoubleStream` cũng có nhiều phép tổng hợp cho dữ liệu số.

Không giả định tổng `long`/`int` luôn không overflow; phải xem miền giá trị. Với `double`, các phép cộng dấu phẩy động có thể sai khác nhỏ vì làm tròn, nhất là khi sắp xếp lại thứ tự tính hoặc chạy parallel. Nếu xử lý tiền tệ, cân nhắc kiểu số phù hợp thay vì dùng `double` theo thói quen.

### 2.4. Những mảng primitive khác

`Arrays.stream` **không có overload trực tiếp cho** `byte[]`, `short[]`, `char[]`, `float[]` và `boolean[]`. Chẳng hạn:

~~~java
char[] letters = {'A', 'B', 'C'};
int[] codeUnits = IntStream.range(0, letters.length)
        .map(i -> letters[i])
        .toArray();
~~~

Đây là **đoạn minh họa** cần `java.util.stream.IntStream`. `codeUnits` là `int[]` có giá trị `[65, 66, 67]` tương ứng với **UTF-16 code units** của ba ký tự ASCII. Với Unicode nằm ngoài BMP, một ký tự có thể gồm **hai `char` surrogate**, nên duyệt `char[]` không tự động duyệt Unicode code point.

Với `float[]` có thể dùng `IntStream.range(0, a.length).mapToDouble(i -> a[i])` nếu việc chuyển sang `double` phù hợp; với `boolean[]` có thể duyệt chỉ số hoặc tạo `Stream<Boolean>` nếu cần, nhưng phải cân nhắc boxing. Không tự gọi `Arrays.stream(booleanArray)` vì **không có overload**.

## 3. Mảng con: startInclusive và endExclusive

Các overload nhận phạm vi xử lý đoạn **[startInclusive, endExclusive)** theo **chỉ số mảng gốc**.

~~~java
int[] numbers = {10, 20, 30, 40, 50};

int sum = Arrays.stream(numbers, 1, 4).sum();
// Các chỉ số được duyệt: 1, 2, 3.
// Các giá trị: 20, 30, 40.
// sum == 90.
~~~

Ý nghĩa chính xác:

- `startInclusive` **được tính** nếu nhỏ hơn end.
- `endExclusive` **không được tính**.
- `Arrays.stream(a, 0, a.length)` tương đương tạo Stream bao phủ toàn mảng.
- `Arrays.stream(a, i, i)` tạo Stream rỗng nếu `i` là chỉ số biên hợp lệ.
- Phạm vi **không tạo mảng mới**; Stream đọc các phần tử từ **mảng nguồn**, trong phạm vi chỉ số được yêu cầu.

| Array | Chỉ số chọn | Kết quả |
| --- | --- | --- |
| `[10,20,30,40,50]` | `(0,5)` | `[10,20,30,40,50]` |
| `[10,20,30,40,50]` | `(1,4)` | `[20,30,40]` |
| `[10,20,30,40,50]` | `(2,2)` | Rỗng |
| `[10,20,30,40,50]` | `(5,5)` | Rỗng, hợp lệ |
| `[10,20,30,40,50]` | `(4,2)` | Lỗi vì from > to |
| `[10,20,30,40,50]` | `(-1,2)` hoặc `(1,6)` | Lỗi vì chỉ số vượt giới hạn |

Theo hợp đồng kiểm tra phạm vi của `Arrays.stream(array,startInclusive,endExclusive)`, `startInclusive > endExclusive` dẫn đến `IllegalArgumentException`; giá trị `startInclusive < 0` hoặc `endExclusive > array.length` dẫn đến `ArrayIndexOutOfBoundsException`. Phân biệt hai trường hợp để không dùng exception làm điều khiển luồng thông thường.

### 3.1. Khác với copyOfRange

~~~java
int[] source = {1, 2, 3, 4, 5};

int[] copied = Arrays.copyOfRange(source, 1, 4);
int[] streamed = Arrays.stream(source, 1, 4).toArray();
~~~

Đây là **đoạn minh họa**. Cả hai cho một `int[]` mới chứa `[2,3,4]`, nhưng cách thực hiện khác:

- `Arrays.copyOfRange` trực tiếp tạo bản sao phạm vi.
- `Arrays.stream(source,1,4)` **chỉ tạo pipeline/spliterator bao phủ đoạn**; đến `toArray()` mới tạo mảng kết quả từ Stream.
- Nếu chỉ cần tính `sum()` của đoạn, `Arrays.stream(...).sum()` có thể làm việc mà không cần tạo mảng trung gian.

Không nhầm “tạo Stream từ mảng” với “sao chép mảng”.

### 3.2. Phạm vi tác động tới encounter order

Với `int[] {10,20,30,40,50}`, `Arrays.stream(a,1,4)` có encounter order `20` → `30` → `40`. `parallel()` có thể làm các tác vụ chạy khác thứ tự thời gian, nhưng những thao tác đầu ra có hợp đồng bảo toàn order vẫn phải tôn trọng encounter order trong phạm vi.

## 4. Arrays.stream khác Stream.of và Arrays.asList

### 4.1. Primitive array: lỗi rất thường gặp

~~~java
int[] numbers = {3, 1, 4};

long countA = Arrays.stream(numbers).count(); // 3
long countB = Stream.of(numbers).count();     // 1
~~~

Đây là **đoạn minh họa**, cần `java.util.stream.Stream` và `Arrays`.

- `Arrays.stream(numbers)` tạo `IntStream` với **ba phần tử số nguyên**.
- `Stream.of(numbers)` tạo `Stream<int[]>` chứa **một phần tử là cả đối tượng mảng**.

Bởi vậy, viết:

~~~java
Stream.of(new int[] {1, 2, 3})
        .mapToInt(Integer::intValue); // KHÔNG BIÊN DỊCH
~~~

là sai về kiểu: phần tử Stream là `int[]`, không phải `Integer`. Khi cần pipeline trên các số `int`, dùng `Arrays.stream(intArray)` hoặc `IntStream.of(intArray)`.

### 4.2. Object array: Stream.of có hành vi varargs khác primitive

~~~java
String[] words = {"red", "green"};

long a = Arrays.stream(words).count(); // 2
long b = Stream.of(words).count();     // 2
long c = Stream.of((Object) words).count(); // 1
~~~

Đây là đoạn minh họa. Với `String[]` truyền thẳng vào varargs `Stream.of(T... values)`, các phần tử String được coi là phần tử Stream. Khi ép thành `Object`, argument là một **phần tử đối tượng mảng**. Để API và ý định rõ ràng nhất khi nguồn là một mảng đã có sẵn, **ưu tiên `Arrays.stream(array)`**.

### 4.3. Arrays.asList không phải Stream

`Arrays.asList(T... a)` trả về một `List` được backed bởi mảng được truyền vào; kích thước List cố định, thao tác `set` có thể phản ánh lên mảng. Nó không phải `Stream` và không giống tạo bản sao `new ArrayList<>(...)`.

Với `int[]`, `Arrays.asList(intArray)` tạo một `List<int[]>` có **một phần tử là mảng nguyên thủy**, không phải `List<Integer>`. Dùng:

~~~java
List<Integer> boxedNumbers = Arrays.stream(numbers)
        .boxed()
        .collect(Collectors.toList());
~~~

Đây là **đoạn minh họa** yêu cầu `numbers` là `int[]`, cần import `List` và `Collectors`. `boxed()` chuyển các giá trị primitive thành wrapper `Integer`; có thể tốn boxing/bộ nhớ nên chỉ dùng khi API thực sự cần object/List.

## 5. Spliterator là gì và tại sao mảng chia được tốt?

`Spliterator<T>` hỗ trợ **duyệt các phần tử** giống một iterator ở mức trừu tượng cao hơn, đồng thời cho phép **tách phạm vi duyệt**. Tên gọi nhắc tới **split + iterator**.

Một số phương thức cốt lõi:

| Phương thức | Vai trò |
| --- | --- |
| `tryAdvance(Consumer<? super T>)` | Nếu có phần tử kế tiếp, chuyển nó vào action và trả `true`; nếu hết, trả `false` |
| `forEachRemaining(Consumer<? super T>)` | Duyệt toàn bộ phần tử còn lại vào action |
| `trySplit()` | Cố tách ra một Spliterator mới bao phủ một phần dữ liệu và điều chỉnh Spliterator hiện tại |
| `estimateSize()` | Ước lượng số phần tử còn lại |
| `getExactSizeIfKnown()` | Trả kích thước chính xác theo `SIZED` nếu biết; nếu không, trả `-1` |
| `characteristics()` | Trả tập bit flags mô tả hợp đồng của Spliterator |
| `hasCharacteristics(flags)` | Kiểm tra có đủ các cờ yêu cầu không |

Với **mảng có chiều dài cố định**, implementation có thể biết phạm vi chỉ số và chia thành các khoảng không giao nhau hiệu quả. Do đó, Spliterator do `Arrays.spliterator` cung cấp có các cờ quan trọng `ORDERED`, `SIZED` và `SUBSIZED`.

~~~java
int[] data = {10, 20, 30, 40, 50};
Spliterator.OfInt sp = Arrays.spliterator(data);

System.out.println(sp.estimateSize());        // 5
System.out.println(sp.getExactSizeIfKnown()); // 5
System.out.println(sp.hasCharacteristics(
        Spliterator.ORDERED | Spliterator.SIZED
                | Spliterator.SUBSIZED));      // true
~~~

Đây là **đoạn minh họa**, với import `Arrays`, `Spliterator`.

**Không suy ra** từ `SIZED` hoặc `SUBSIZED` rằng nội dung mảng bất biến, mọi phần tử không null, không có trùng lặp hoặc đã sắp xếp. Một mảng đối tượng có thể chứa null; nội dung mảng có thể được gán lại bằng mã ứng dụng, dù chiều dài cố định.

### 5.1. Đặc tính ORDERED

`ORDERED` nghĩa nguồn có encounter order, với mảng là **theo chỉ số tăng dần** trong phạm vi đã chọn. Khi `trySplit()` thành công trên Spliterator ordered, Spliterator được trả về bao phủ **prefix** (đoạn đầu) của phần chưa duyệt, phần còn lại nằm ở Spliterator gốc.

Do đó, nếu tách rồi duyệt **prefix trước, phần còn lại sau**, ta tái tạo đúng thứ tự mảng.

### 5.2. Đặc tính SIZED và SUBSIZED

- `SIZED`: Spliterator mới (trong điều kiện hợp đồng, không có thay đổi cấu trúc nguồn trái phép) biết chính xác **kích thước hữu hạn**.
- `SUBSIZED`: các Spliterator con tạo sau `trySplit()` cũng có `SIZED` và `SUBSIZED`; khi chia thành công, kích thước ước tính hai phần cộng lại bằng kích thước trước đó.

Ví dụ một mảng có sáu phần tử:

~~~text
[10, 20, 30, 40, 50, 60]  size = 6
             |
          trySplit
          /       \
  prefix [10,20,30]    remainder [40,50,60]
    size = 3                size = 3
~~~

**Lưu ý:** Sơ đồ là một trường hợp minh họa. Hợp đồng không hứa mọi Spliterator đều chia đôi bằng nhau hoặc lần nào `trySplit` cũng trả khác `null`. `SUBSIZED` cam kết tính chính xác/tổng kích thước khi tách, **không phải** một sơ đồ phân hoạch cố định.

### 5.3. Primitive spliterators tránh boxing

Với số nguyên thủy, các interface chuyên biệt là:

- `Spliterator.OfInt`, có thể nhận `IntConsumer`.
- `Spliterator.OfLong`, có thể nhận `LongConsumer`.
- `Spliterator.OfDouble`, có thể nhận `DoubleConsumer`.

Dùng action với kiểu primitive:

~~~java
Spliterator.OfInt sp = Arrays.spliterator(new int[] {1, 2, 3});
sp.forEachRemaining((int value) -> System.out.println(value));
~~~

Đây là **đoạn minh họa**, in lần lượt `1`, `2`, `3`. Kiểu lambda ghi rõ `int` để lựa chọn overload chuyên biệt, tránh boxing không cần thiết.

## 6. Arrays.spliterator: overload toàn mảng và theo phạm vi

`Arrays.spliterator` cũng có những overload tương ứng cho:

| Đầu vào | Kiểu trả về |
| --- | --- |
| `T[]` hoặc `T[], from, to` | `Spliterator<T>` |
| `int[]` hoặc `int[], from, to` | `Spliterator.OfInt` |
| `long[]` hoặc `long[], from, to` | `Spliterator.OfLong` |
| `double[]` hoặc `double[], from, to` | `Spliterator.OfDouble` |

Ví dụ:

~~~java
String[] cities = {"Ha Noi", "Da Nang", "Can Tho"};
Spliterator<String> all = Arrays.spliterator(cities);
Spliterator<String> subset = Arrays.spliterator(cities, 1, 3);
~~~

Đây là **đoạn minh họa**. `all` duyệt cả ba thành phố; `subset` chỉ bao phủ `"Da Nang"` và `"Can Tho"`. Tạo hai Spliterator từ cùng mảng không tạo hai bản sao mảng.

**Không dùng chung một Spliterator cho hai pipeline terminal operation**. Muốn duyệt lại, tạo Spliterator mới bằng `Arrays.spliterator(array)`, nếu mảng vẫn hợp lệ.

### 6.1. Phương thức tryAdvance

~~~java
int[] values = {10, 20};
Spliterator.OfInt sp = Arrays.spliterator(values);

boolean first = sp.tryAdvance((int n) ->
        System.out.println("value = " + n));
boolean second = sp.tryAdvance((int n) ->
        System.out.println("value = " + n));
boolean third = sp.tryAdvance((int n) ->
        System.out.println("value = " + n));
~~~

Đây là đoạn minh họa; stdout là `value = 10` rồi `value = 20`, còn các boolean lần lượt `true`, `true`, `false`. Phần tử đã chuyển vào action được coi như đã duyệt; các lần gọi tiếp theo chuyển sang phần tử còn lại.

### 6.2. forEachRemaining

~~~java
int[] values = {10, 20, 30};
Spliterator.OfInt sp = Arrays.spliterator(values);

sp.tryAdvance((int n) -> System.out.println(n));
sp.forEachRemaining((int n) -> System.out.println(n));
~~~

Đây là **đoạn minh họa**; in `10` ở lần gọi đầu, rồi `20` và `30` từ phần còn lại. Không dùng `forEachRemaining` trên chính Spliterator đã cạn nếu mong lặp lại từ đầu.

## 7. trySplit: chia nguồn, không làm trùng hoặc mất phần tử

Để tự quan sát hợp đồng chia nguồn:

~~~java
int[] data = {1, 2, 3, 4, 5, 6};
Spliterator.OfInt remainder = Arrays.spliterator(data);
long initial = remainder.estimateSize();

Spliterator.OfInt prefix = remainder.trySplit();
long leftSize = prefix == null ? 0L : prefix.estimateSize();
long rightSize = remainder.estimateSize();

System.out.println(initial == leftSize + rightSize); // true
~~~

Đây là **đoạn minh họa**. Với mảng có `SUBSIZED`, khi tách thành công tổng kích thước hai phần đúng bằng kích thước ban đầu. Nếu `trySplit()` trả `null`, phần toàn bộ vẫn do `remainder` giữ; phép kiểm tra cũng đúng.

Sau đó có thể duyệt hai phần bằng thứ tự prefix rồi remainder:

~~~java
List<Integer> joined = new ArrayList<>();
if (prefix != null) {
    prefix.forEachRemaining((int n) -> joined.add(n));
}
remainder.forEachRemaining((int n) -> joined.add(n));

System.out.println(joined);
// [1, 2, 3, 4, 5, 6]
~~~

Đây là **đoạn minh họa tiếp nối đoạn code trước**, cần import `List` và `ArrayList`. `joined` là List được cập nhật **tuần tự**; ví dụ này không đòi ArrayList thread-safe.

**Tách được nguồn không có nghĩa mỗi nhánh chạy ngay trên một thread riêng**. Parallel Stream là mô hình có thể chia tác vụ và gộp kết quả; số task, kích thước nhánh và lịch thread do runtime quyết định. `Spliterator.trySplit` không phải API để đặt tên thread hoặc cam kết mức parallelism.

### 7.1. Không cùng duyệt một Spliterator trên nhiều thread

Spliterator không mặc định thread-safe. Tránh hai worker cùng gọi `tryAdvance`/`trySplit` trên **cùng một instance** trừ khi implementation nêu rõ bảo đảm. Khi cần xử lý song song, cách thông thường là tách thành **những Spliterator khác nhau**, mỗi tác vụ sở hữu phần dữ liệu của nó.

### 7.2. Mảng nguồn bị chỉnh sửa trong lúc duyệt

Chiều dài mảng cố định, nhưng phần tử vẫn có thể được sửa:

~~~java
int[] values = {1, 2, 3};
values[1] = 99; // Hợp lệ khi chưa chạy pipeline.
~~~

Với Stream/Spliterator trên mảng, không nên chỉnh sửa các phần tử nguồn trong khi đang thực hiện traversal/reduction nếu không có bảo đảm về đồng bộ và tính nhất quán. Stream yêu cầu các callback thông thường **non-interfering** và **stateless**; thay mảng gốc đồng thời với việc duyệt có thể khiến kết quả không đáng tin, nhất là khi chạy song song.

Để xử lý snapshot, có thể tạo bản sao **trước** khi tạo Stream/Spliterator:

~~~java
int[] snapshot = Arrays.copyOf(values, values.length);
int sum = Arrays.stream(snapshot).sum();
~~~

Đây là đoạn minh họa. Nếu nguồn đang được sửa bởi thread khác, bản thân thao tác sao chép cũng cần chính sách đồng bộ/snapshot phù hợp; `Arrays.copyOf` không tự bảo đảm snapshot nhất quán với những thay đổi đồng thời.

## 8. Từ Spliterator sang Stream với StreamSupport

`Arrays.stream(array)` là lựa chọn trực tiếp khi chỉ cần xử lý phần tử. Nếu đã có Spliterator hoặc muốn quyết định chế độ parallel tại điểm tạo Stream, dùng `StreamSupport`:

~~~java
int[] numbers = {3, 1, 4, 1, 5, 9};
Spliterator.OfInt sp = Arrays.spliterator(numbers);

IntStream stream = StreamSupport.intStream(sp, false);
int sum = stream.sum(); // 23
~~~

Đây là **đoạn minh họa**, với `java.util.stream.IntStream`, `java.util.stream.StreamSupport` và các import cho `Arrays`/`Spliterator`.

Đối với mảng đối tượng:

~~~java
String[] words = {"Java", "Stream"};
Spliterator<String> sp = Arrays.spliterator(words);

Stream<String> stream = StreamSupport.stream(sp, false);
List<Integer> lengths = stream.map(String::length)
        .collect(Collectors.toList());
// [4, 6]
~~~

Đây là **đoạn minh họa** (cần import `Stream`, `List`, `Collectors`). Lưu ý String `"Stream"` có **sáu** ký tự ASCII. Không phải dùng `StreamSupport` để tạo Stream từ mảng thông thường: `Arrays.stream(words)` ngắn và dễ hiểu hơn.

### 8.1. Các phương thức StreamSupport tương ứng

| Spliterator đầu vào | Factory StreamSupport |
| --- | --- |
| `Spliterator<T>` | `StreamSupport.stream(spliterator, parallel)` |
| `Spliterator.OfInt` | `StreamSupport.intStream(spliterator, parallel)` |
| `Spliterator.OfLong` | `StreamSupport.longStream(spliterator, parallel)` |
| `Spliterator.OfDouble` | `StreamSupport.doubleStream(spliterator, parallel)` |

`parallel` là boolean chọn **chế độ**. `false` nghĩa sequential; `true` nghĩa parallel. Nó không bảo đảm phải dùng một số thread cụ thể, không làm lambda chứa state trở nên thread-safe.

### 8.2. Một Spliterator không tự dùng lại được

~~~java
Spliterator.OfInt sp = Arrays.spliterator(numbers);
int sum = StreamSupport.intStream(sp, false).sum();

// Không tái dùng sp như thể chưa được duyệt.
// Tạo nguồn mới nếu muốn tính kết quả khác.
int max = Arrays.stream(numbers).max().orElseThrow(
        IllegalStateException::new);
~~~

Đây là **đoạn minh họa**. Dạng `OptionalInt.orElseThrow(Supplier)` có từ Java 8; không dùng overload `orElseThrow()` không đối số khi muốn biên dịch target Java 8.

**Stream chỉ dùng cho một lần terminal operation.** Nếu muốn tính tổng, đếm, max từ cùng dữ liệu, tạo các Stream mới hoặc dùng terminal `summaryStatistics` để tổng hợp nhiều chỉ số trong một lần duyệt.

## 9. Chạy parallel từ mảng

Hai cách dễ đọc:

~~~java
int[] values = {1, 2, 3, 4, 5, 6};

int a = Arrays.stream(values).parallel().sum();

int b = StreamSupport.intStream(
        Arrays.spliterator(values), true).sum();

// a == 21, b == 21
~~~

Đây là **đoạn minh họa**. Hai biểu thức đều thực hiện parallel pipeline trên nguồn mảng có thể chia, nhưng runtime có thể chọn cách chia tác vụ khác nhau. Không viết logic giả định số task bằng số phần tử.

### 9.1. Vì sao mảng thường thuận lợi cho parallel?

Mảng có thể truy cập ngẫu nhiên theo chỉ số và có kích thước đã biết. Spliterator của mảng báo `SIZED` và `SUBSIZED`, hỗ trợ tạo những phần có kích thước biết trước. Việc chia nguồn thường rẻ hơn so với một nguồn phải tuần tự đọc dữ liệu hoặc khó ước lượng kích thước.

Tuy vậy, hiệu năng còn phụ thuộc:

- Kích thước mảng có đủ lớn không?
- Xử lý mỗi phần tử có đủ tốn CPU để bù overhead không?
- Phép gộp có kết hợp được và ít contention không?
- Có yêu cầu giữ encounter order trong terminal operation không?
- Các thread khác có đang tranh CPU/bộ nhớ không?

Parallel không đồng nghĩa nhanh hơn; đo với dữ liệu và workload đại diện trước khi áp dụng vào production.

### 9.2. Parallel forEach và ordering

~~~java
Arrays.stream(values)
        .parallel()
        .forEach(System.out::println);
~~~

Đây là **đoạn minh họa**: không cam kết thứ tự in khi chạy parallel. Nếu cần thứ tự encounter order của mảng, dùng:

~~~java
Arrays.stream(values)
        .parallel()
        .forEachOrdered(System.out::println);
~~~

`forEachOrdered` bảo đảm thứ tự action với nguồn ordered, nhưng có thể làm giảm cơ hội tối ưu parallel. Không kết luận tất cả callback `map`/`filter` cũng chạy theo đúng thứ tự thời gian từ đầu đến cuối; điều được bảo đảm là thứ tự action của terminal operation.

### 9.3. Reduction đúng hợp đồng

~~~java
int total = Arrays.stream(values)
        .parallel()
        .reduce(0, Integer::sum);
~~~

Đây là **đoạn minh họa**. Phép cộng nguyên với ví dụ giá trị nhỏ và không tràn có identity `0`, có thể tính trên nhiều phần rồi gộp hợp lệ. Nếu dùng phép trừ hoặc accumulator có shared mutable state, kết quả có thể phụ thuộc cách phân nhóm. `parallel()` không sửa giúp một reduction không kết hợp được.

### 9.4. Kết quả sorted và mảng gốc

~~~java
int[] sorted = Arrays.stream(values)
        .parallel()
        .sorted()
        .toArray();
~~~

Đây là **đoạn minh họa**. Mảng `sorted` là kết quả mới, không làm thay đổi mảng nguồn. Muốn sắp xếp **tại chỗ**, dùng `Arrays.sort(values)` hoặc `Arrays.parallelSort(values)` khi có lý do phù hợp. Đây là những API khác nhau về side effect.

## 10. Mảng nhiều chiều: stream trên các hàng, flatMap để làm phẳng

Một mảng `int[][]` là một **mảng các mảng `int[]`**, không phải cấu trúc 2D được Java Stream tự động duyệt sâu.

~~~java
int[][] matrix = {
        {1, 2},
        {3},
        {4, 5}
};

long rows = Arrays.stream(matrix).count(); // 3
int total = Arrays.stream(matrix)
        .flatMapToInt(Arrays::stream)
        .sum(); // 15
~~~

Đây là **đoạn minh họa**. `Arrays.stream(matrix)` có kiểu `Stream<int[]>` nên số phần tử là **ba hàng**. `flatMapToInt(Arrays::stream)` biến từng `int[]` thành `IntStream` rồi làm phẳng thành chuỗi số nguyên để tính tổng cả ma trận.

### 10.1. Duyệt hàng và chỉ số

~~~java
int[][] matrix = {{1, 2}, {3}, {4, 5}};

List<Integer> rowSums = Arrays.stream(matrix)
        .map(row -> Arrays.stream(row).sum())
        .collect(Collectors.toList());
// [3, 3, 9]
~~~

Đây là **đoạn minh họa**. Với ma trận ragged (các hàng không cùng độ dài), cách dùng `Arrays.stream(row)` vẫn hoạt động miễn mỗi hàng khác null. Nếu có hàng null, phải định nghĩa chính sách xử lý rõ ràng (bỏ qua, coi như rỗng, hay báo lỗi), không tự giả định mọi hàng luôn tồn tại.

### 10.2. Đừng nhầm với deepToString

`Arrays.toString(int[])` in nội dung một mảng primitive. Với `int[][]`, `Arrays.toString(matrix)` không phải cách hiển thị lồng nhau theo nội dung; dùng `Arrays.deepToString(matrix)` nếu muốn chuỗi thể hiện các hàng. Đây là chuyện **hiển thị**, không thay đổi cách `Arrays.stream` xác định phần tử.

## 11. Null, nguồn rỗng và những ngoại lệ cần biết

### 11.1. Bản thân mảng null

~~~java
int[] data = null;
Arrays.stream(data); // Ném NullPointerException.
~~~

Đây là **đoạn minh họa**. `Arrays.stream` yêu cầu tham chiếu mảng hợp lệ. Không tự tạo một Stream rỗng khi người gọi truyền null.

Nếu nghiệp vụ coi null là mảng rỗng, phải quyết định điều đó một cách tường minh:

~~~java
int[] safe = data == null ? new int[0] : data;
int total = Arrays.stream(safe).sum();
~~~

Đây là **đoạn minh họa**. Quy tắc null → rỗng là lựa chọn ở **tầng ứng dụng**, không phải hành vi tự động của API.

### 11.2. Phần tử null trong T[]

~~~java
String[] values = {"A", null, "BB"};

List<Integer> lengths = Arrays.stream(values)
        .filter(Objects::nonNull)
        .map(String::length)
        .collect(Collectors.toList());
// [1, 2]
~~~

Đây là **đoạn minh họa**, cần import `Objects`, `List`, `Collectors`. `Arrays.stream(values)` có thể chứa phần tử null; nếu viết `map(String::length)` mà không kiểm tra null, một phần tử null có thể gây `NullPointerException`.

**Không đánh đồng `Spliterator.NONNULL` với việc mảng tham chiếu không chứa null.** Mảng `T[]` có thể chứa null, và đặc tính báo cáo của Spliterator phải được hiểu theo hợp đồng của chính nguồn.

### 11.3. Mảng rỗng và Optional

~~~java
int[] empty = {};
long count = Arrays.stream(empty).count(); // 0
int sum = Arrays.stream(empty).sum();       // 0

OptionalInt min = Arrays.stream(empty).min();
System.out.println(min.isPresent());        // false
~~~

Đây là **đoạn minh họa**. `min()` trả `OptionalInt` rỗng, không trả một giá trị `int` bịa ra. `sum()` có identity `0` nhưng trong nhiều nghiệp vụ tổng bằng 0 và không có dữ liệu là hai tình huống cần phân biệt.

### 11.4. Không tự kiểm soát size bằng length trong pipeline đã lọc

`length` và `Arrays.spliterator(a).estimateSize()` cho biết số phần tử nguồn trong phạm vi, **không phải** số lượng kết quả sau `filter`/`flatMap`. Nếu cần số lượng sau điều kiện, dùng terminal `count()` trên pipeline.

Một số pipeline có kích thước đã biết cho phép `count()` tối ưu mà không gọi mọi callback `peek`/`map` không ảnh hưởng kết quả. Do đó **không đặt side effect bắt buộc trong callback trung gian** chỉ để dựa vào số lần chúng được gọi.

## 12. Chương trình hoàn chỉnh và stdout xác định

Lưu thành tệp **ArraysStreamSpliteratorDemo.java**. Tất cả API và cú pháp của chương trình đều tương thích **Java 8**. Chương trình cố ý không in kích thước cụ thể sau `trySplit()`, vì kích thước nhánh là chi tiết triển khai.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Spliterator;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public class ArraysStreamSpliteratorDemo {
    public static void main(String[] args) {
        int[] numbers = {3, 1, 4, 1, 5, 9};

        System.out.println("sum = "
                + Arrays.stream(numbers).sum());
        System.out.println("range [1,5) = "
                + Arrays.stream(numbers, 1, 5)
                        .boxed().collect(Collectors.toList()));
        System.out.println("even count = "
                + Arrays.stream(numbers)
                        .filter(n -> n % 2 == 0).count());
        System.out.println("sorted stream = "
                + Arrays.stream(numbers)
                        .sorted().boxed().collect(Collectors.toList()));
        System.out.println("source unchanged = "
                + Arrays.toString(numbers));

        System.out.println("Stream.of(int[]) count = "
                + Stream.of(numbers).count());
        System.out.println("Arrays.stream(int[]) count = "
                + Arrays.stream(numbers).count());

        String[] names = {"An", "Binh", "Chi"};
        System.out.println("uppercase = "
                + Arrays.stream(names)
                        .map(s -> s.toUpperCase(Locale.ROOT))
                        .collect(Collectors.toList()));
        System.out.println("name lengths = "
                + Arrays.stream(names).mapToInt(String::length)
                        .boxed().collect(Collectors.toList()));

        String[] nullable = {"An", null, "Chi"};
        System.out.println("non-null names = "
                + Arrays.stream(nullable)
                        .filter(Objects::nonNull)
                        .collect(Collectors.toList()));

        Spliterator.OfInt remainder = Arrays.spliterator(numbers);
        System.out.println("spliterator ordered/sized/subsized = "
                + remainder.hasCharacteristics(
                        Spliterator.ORDERED | Spliterator.SIZED
                                | Spliterator.SUBSIZED));
        long beforeSplit = remainder.estimateSize();
        System.out.println("estimate initially = " + beforeSplit);
        System.out.println("exact initially = "
                + remainder.getExactSizeIfKnown());

        Spliterator.OfInt prefix = remainder.trySplit();
        long prefixSize = prefix == null
                ? 0L : prefix.estimateSize();
        long remainderSize = remainder.estimateSize();
        System.out.println("sizes rejoin = "
                + (beforeSplit == prefixSize + remainderSize));

        List<Integer> reconstructed = new ArrayList<>();
        if (prefix != null) {
            prefix.forEachRemaining(
                    (int n) -> reconstructed.add(n));
        }
        remainder.forEachRemaining(
                (int n) -> reconstructed.add(n));
        System.out.println("reconstructed = " + reconstructed);

        Spliterator.OfInt sub = Arrays.spliterator(numbers, 1, 5);
        System.out.println("subrange exact = "
                + sub.getExactSizeIfKnown());

        int supportSum = StreamSupport.intStream(
                Arrays.spliterator(numbers), false).sum();
        int parallelSum = StreamSupport.intStream(
                Arrays.spliterator(numbers), true).sum();
        System.out.println("StreamSupport sequential sum = "
                + supportSum);
        System.out.println("StreamSupport parallel sum = "
                + parallelSum);

        long[] timeMs = {100L, 200L, 300L};
        System.out.println("long sum = "
                + Arrays.stream(timeMs).sum());

        double[] measurements = {1.5, 2.5};
        System.out.println("double sum = "
                + Arrays.stream(measurements).sum());

        int[][] matrix = {{1, 2}, {3}, {4, 5}};
        System.out.println("matrix row count = "
                + Arrays.stream(matrix).count());
        System.out.println("matrix flat sum = "
                + Arrays.stream(matrix)
                        .flatMapToInt(Arrays::stream).sum());
    }
}
~~~

Lệnh biên dịch/chạy khi có JDK 17+ (vẫn kiểm tra giới hạn ngôn ngữ và API Java 8):

~~~bash
javac --release 8 ArraysStreamSpliteratorDemo.java
java ArraysStreamSpliteratorDemo
~~~

**Stdout kỳ vọng chính xác:**

~~~text
sum = 23
range [1,5) = [1, 4, 1, 5]
even count = 1
sorted stream = [1, 1, 3, 4, 5, 9]
source unchanged = [3, 1, 4, 1, 5, 9]
Stream.of(int[]) count = 1
Arrays.stream(int[]) count = 6
uppercase = [AN, BINH, CHI]
name lengths = [2, 4, 3]
non-null names = [An, Chi]
spliterator ordered/sized/subsized = true
estimate initially = 6
exact initially = 6
sizes rejoin = true
reconstructed = [3, 1, 4, 1, 5, 9]
subrange exact = 4
StreamSupport sequential sum = 23
StreamSupport parallel sum = 23
long sum = 600
double sum = 4.0
matrix row count = 3
matrix flat sum = 15
~~~

### 12.1. Vì sao kết quả đáng tin?

1. Mảng `numbers` có `6` phần tử. Tổng `3+1+4+1+5+9 = 23`, chỉ có một số chẵn `4`.
2. `Arrays.stream(numbers,1,5)` bao phủ chỉ số `1,2,3,4` nên tạo `[1,4,1,5]`.
3. `sorted()` sắp xếp các giá trị trong **Stream**, còn `Arrays.toString(numbers)` vẫn in mảng gốc theo thứ tự ban đầu; không có callback sửa mảng.
4. `Stream.of(numbers)` có một phần tử kiểu `int[]`, còn `Arrays.stream(numbers)` có sáu phần tử `int`.
5. `Locale.ROOT` giúp kết quả uppercase ổn định; `String::length` đếm ký tự ASCII trong các tên này: `2,4,3`.
6. Spliterator của mảng báo cả `ORDERED`, `SIZED`, `SUBSIZED`. Giá trị kích thước ban đầu bằng sáu.
7. Với đặc tính `SUBSIZED`, tổng hai phạm vi sau split bằng phạm vi trước split. Nếu không split, toàn bộ phần tử vẫn trong `remainder` và phép kiểm tra cũng đúng.
8. `trySplit` trên Spliterator ordered trả prefix; duyệt prefix trước remainder tái dựng mảng theo encounter order mà không phải dựa vào số phần tử mỗi nhánh.
9. Phạm vi `[1,5)` có đúng bốn phần tử nên `getExactSizeIfKnown()` trả `4`.
10. `StreamSupport` với `parallel=false/true` đều tính tổng hợp lệ; các số nhỏ nên không có overflow và không cần suy đoán lịch thread.
11. `long[]` tính `600`, `double[]` tính `4.0`, còn `int[][]` có ba **hàng** nhưng tổng phẳng của tất cả số là `15`.

Trong bài này, mọi stdout quan trọng đều **không phụ thuộc số thread, thứ tự in `forEach` parallel hay hình dạng nhánh sau `trySplit`**.

## 13. Lỗi thường gặp và cách khắc phục

### Lỗi 1 — Gọi Arrays.stream trên kiểu mảng không có overload

~~~java
boolean[] flags = {true, false};
// Arrays.stream(flags); // Không có overload boolean[].
~~~

**Sửa:** Duyệt chỉ số hoặc sử dụng API thích hợp; nếu cần object stream, có thể ánh xạ sang `Boolean` có chủ đích.

### Lỗi 2 — Dùng Stream.of(int[]) rồi tưởng nhận IntStream

~~~java
int[] values = {1, 2, 3};
Stream<int[]> oneArray = Stream.of(values);
IntStream numbers = Arrays.stream(values);
~~~

**Sửa:** Khi mục tiêu là tính toán trên từng `int`, chọn `Arrays.stream(int[])` hoặc `IntStream.of(int[])`.

### Lỗi 3 — Nhầm endExclusive là chỉ số cuối được lấy

`Arrays.stream(values,1,4)` chỉ đọc các vị trí `1,2,3`, không đọc vị trí `4`. **Sửa:** dùng quy tắc `[start,end)`, xác minh biên `0` và `length`.

### Lỗi 4 — Tưởng Arrays.stream tự copy mảng

Tạo Stream không nhất thiết tạo bản sao dữ liệu. **Sửa:** tạo `Arrays.copyOf` nếu cần snapshot và đảm bảo nguồn không thay đổi trái hợp đồng trong quá trình duyệt.

### Lỗi 5 — Nhầm Spliterator với Collection

`Spliterator` chỉ là công cụ duyệt/chia, không có API `add`/`remove` như `Collection`. **Sửa:** để xử lý dữ liệu trong pipeline dùng `Stream`; để quản lý dữ liệu nguồn, thao tác trên mảng hoặc collection đúng cách.

### Lỗi 6 — Tái dùng Stream hoặc Spliterator đã tiêu thụ

`Stream` chỉ có một terminal operation trên mỗi instance. **Sửa:** tạo Stream/Spliterator mới từ mảng khi cần chạy lại, không cố gọi tiếp một nguồn đã cạn.

### Lỗi 7 — Cho rằng trySplit luôn chia đôi và luôn thành công

`trySplit` có thể trả `null` và không hứa kích thước cố định. **Sửa:** kiểm tra null, tuân thủ hợp đồng `ORDERED`/`SUBSIZED` thay vì dựa vào hình dạng cụ thể.

### Lỗi 8 — Dùng chung một ArrayList ngoài trong parallel forEach

~~~java
List<Integer> results = new ArrayList<>();
Arrays.stream(values).parallel().forEach(results::add);
~~~

Đây là **đoạn phản ví dụ**; `ArrayList.add` không thread-safe. **Sửa:**

~~~java
List<Integer> results = Arrays.stream(values).parallel()
        .boxed().collect(Collectors.toList());
~~~

Collector được framework quản lý theo hợp đồng reduction, thay vì nhiều tác vụ cùng sửa một List bên ngoài. Nếu cần bảo toàn encounter order, `collect(toList())` trên ordered stream cung cấp kết quả theo thứ tự.

### Lỗi 9 — Nhầm forEach với forEachOrdered

`parallel().forEach` không cam kết thứ tự action; `forEachOrdered` giữ thứ tự action cho nguồn ordered nhưng có thể giảm hiệu năng. **Sửa:** chọn dựa vào yêu cầu thực tế, không suy luận từ một lần chạy.

### Lỗi 10 — Tính hash/null/size sai khi có phần tử null

`Arrays.stream(T[])` có thể chứa null. **Sửa:** dùng `filter(Objects::nonNull)` hoặc logic null phù hợp trước khi gọi method trên từng phần tử.

### Lỗi 11 — Dùng getExactSizeIfKnown làm kết quả sau filter

Kích thước mảng gốc không cho biết sẽ có bao nhiêu phần tử thỏa predicate. **Sửa:** dùng `filter(...).count()` hoặc một reduction thích hợp.

### Lỗi 12 — Dùng Stream.sorted rồi kỳ vọng mảng nguồn bị sắp xếp

`Arrays.stream(values).sorted()` chỉ tạo bước pipeline; terminal `toArray()` tạo kết quả mới. **Sửa:** dùng `Arrays.sort(values)` nếu muốn sửa ngay mảng gốc.

### Lỗi 13 — Nghĩ parallel luôn nhanh hơn

Chia tác vụ, scheduling, gộp kết quả và contention có overhead. **Sửa:** ưu tiên correctness; benchmark cả sequential và parallel với kích thước mảng đại diện.

### Lỗi 14 — Duyệt char[] rồi tưởng đang duyệt Unicode code point

`char` là UTF-16 code unit, không nhất thiết tương đương ký tự Unicode hoàn chỉnh. **Sửa:** nếu đầu vào thực sự là văn bản và cần code point, cân nhắc `String.codePoints()` thay vì chia/duyệt `char[]` như code points.

### Lỗi 15 — Thay đổi nguồn trong lúc Stream đang xử lý

Lambda sửa dữ liệu của chính mảng đang được duyệt có thể vi phạm non-interference. **Sửa:** dùng hàm thuần và thu kết quả riêng; nếu thay đổi nguồn là yêu cầu nghiệp vụ, thiết kế thuật toán và đồng bộ ngoài pipeline.

### Lỗi 16 — Lưu state vào một Spliterator rồi chạy trên nhiều thread

Không mặc định cùng một Spliterator có thể bị duyệt/tách đồng thời. **Sửa:** để framework quản lý parallel pipeline hoặc tách các instance riêng biệt; không tự phát minh bảo đảm thread safety.

## 14. Lựa chọn API trong công việc thực tế

| Mục tiêu | API ưu tiên | Lưu ý |
| --- | --- | --- |
| Cộng, lọc, tổng hợp phần tử `int[]` | `Arrays.stream(intArray)` | Trả `IntStream`, không cần boxing |
| Xử lý object `T[]` | `Arrays.stream(objectArray)` | Trả `Stream<T>` |
| Chỉ xử lý một đoạn mảng | `Arrays.stream(array,from,to)` | Đoạn `[from,to)`, không copy mảng |
| Duyệt/chia nguồn ở tầng thấp | `Arrays.spliterator(array)` | Cờ `ORDERED/SIZED/SUBSIZED` |
| Tạo Stream từ Spliterator có sẵn | `StreamSupport.stream(spliterator,false)` | Với primitive chọn overload chuyên biệt |
| Xử lý mảng lớn trên nhiều CPU | `Arrays.stream(array).parallel()` | Đo hiệu năng; callback không side effect |
| Thu kết quả primitive thành mảng | `IntStream.toArray()` | Trả `int[]` mới |
| Thu primitive thành List wrapper | `boxed().collect(toList())` | Có boxing, chi phí bộ nhớ |
| Sắp mảng nguồn ngay tại chỗ | `Arrays.sort(array)` | Thay đổi mảng gốc |
| Làm phẳng `int[][]` | `Arrays.stream(matrix).flatMapToInt(Arrays::stream)` | Mỗi phần tử nguồn là một `int[]` |
| Chụp dữ liệu trước khi xử lý | `Arrays.copyOf(array,array.length)` | Cần đồng bộ nếu nguồn đang bị sửa đồng thời |

### 14.1. Một vài checklist trước khi đưa vào production

1. **Kiểu mảng nào?** `T[]` hay một trong `int[]`/`long[]`/`double[]`? Nếu là `char[]`/`boolean[]` thì thiết kế nguồn khác.
2. **Có chỉ cần một đoạn không?** Xác minh `startInclusive` và `endExclusive`, xử lý biên.
3. **Mảng có thể null?** Xác định chính sách null → lỗi hoặc rỗng; đừng để bug âm thầm.
4. **Phần tử có thể null?** Nếu là `T[]` thì xử lý trước khi dereference.
5. **Cần tạo bản sao hay chỉ xử lý?** `stream`/`spliterator` không phải phép copy.
6. **Dùng chung dữ liệu giữa thread?** Không chỉnh sửa nguồn trái hợp đồng khi chạy.
7. **Có yêu cầu thứ tự?** Phân biệt encounter order với lịch thread/`forEach`.
8. **Terminal operation là gì?** Stream lazy, cần terminal để tính; Stream không dùng lại.
9. **Dữ liệu có lớn và CPU-bound không?** Chỉ khi phù hợp mới cân nhắc `parallel`.
10. **Sử dụng primitive specialization?** Tránh boxing không cần thiết, kiểm tra overflow/precision.

## 15. Bài tập và đáp án

**Câu 1.** `Arrays.stream(new int[]{2,4,6}).count()` và `Stream.of(new int[]{2,4,6}).count()` trả gì?

**Đáp án:** Lần lượt `3` và `1`. Trường hợp đầu là `IntStream` gồm ba số; trường hợp sau là `Stream<int[]>` gồm một mảng.

**Câu 2.** Với `int[] a={10,20,30,40,50}`, `Arrays.stream(a,1,4).sum()` bằng mấy?

**Đáp án:** `90`, vì chỉ lấy chỉ số `1`, `2`, `3` tương ứng `20`, `30`, `40`.

**Câu 3.** `Arrays.stream(a,2,2)` có lỗi không nếu mảng có ít nhất hai phần tử?

**Đáp án:** Không, miễn chỉ số biên hợp lệ; tạo Stream rỗng. Mốc `endExclusive` bằng `startInclusive` là hợp lệ.

**Câu 4.** `Arrays.spliterator(new int[]{1,2,3})` có thể cho biết kích thước chính xác không?

**Đáp án:** Có. Spliterator mảng có `SIZED`, ban đầu `getExactSizeIfKnown()` trả `3`.

**Câu 5.** `trySplit()` của Spliterator `ORDERED` trả về phần nào?

**Đáp án:** Nếu tách được, trả Spliterator bao phủ **prefix** của phần chưa duyệt; phần còn lại giữ trong Spliterator cũ.

**Câu 6.** Vì sao hai phần sau split có tổng số lượng bằng trước split với mảng?

**Đáp án:** Spliterator mảng báo `SUBSIZED`, bảo đảm các nhánh cũng biết kích thước chính xác và phép tách bảo toàn tổng kích thước.

**Câu 7.** Khi cần tạo Stream từ `Spliterator.OfInt` thì dùng `StreamSupport.stream` hay `StreamSupport.intStream`?

**Đáp án:** `StreamSupport.intStream`, để nhận `IntStream` và thao tác primitive chuyên biệt.

**Câu 8.** `Arrays.stream(matrix)` với `matrix` kiểu `int[][]` tạo Stream chứa cái gì?

**Đáp án:** Tạo `Stream<int[]>`, mỗi phần tử là một hàng. Dùng `flatMapToInt(Arrays::stream)` nếu muốn chuỗi các `int` ở mọi hàng.

**Câu 9.** `Arrays.stream(a).sorted().toArray()` có thay đổi `a` không?

**Đáp án:** Không. Nó tạo mảng kết quả mới; muốn thay mảng nguồn thì dùng `Arrays.sort(a)` hoặc thuật toán phù hợp.

**Câu 10.** Có thể gọi `Arrays.stream(char[])` hoặc `Arrays.stream(boolean[])` trong Java 8 không?

**Đáp án:** Không, hai overload này không tồn tại. Sử dụng cơ chế duyệt chỉ số hoặc chuyển đổi rõ ràng theo nhu cầu.

**Câu 11.** Với mảng tham chiếu có phần tử null, gọi `Arrays.stream(values).map(String::length)` luôn an toàn không?

**Đáp án:** Không. Khi gặp null, `String::length` có thể ném NPE. Kiểm tra/lọc null trước nếu nghiệp vụ cho phép.

**Câu 12.** Vì sao `Arrays.stream(a).parallel()` không tự bảo đảm nhanh hơn?

**Đáp án:** Vì overhead phân chia, scheduling, gộp và giới hạn phần cứng có thể vượt chi phí tính toán. Cần workload đủ lớn, độc lập và benchmark đáng tin.

## 16. Tổng kết

- `Arrays.stream` tạo Stream từ **mảng đối tượng**, hoặc primitive Stream từ **`int[]`/`long[]`/`double[]`**; không có overload `boolean[]`, `char[]`, `float[]` và các mảng primitive khác.
- Các overload phạm vi sử dụng **`[startInclusive, endExclusive)`**, không tự sao chép mảng.
- `Arrays.spliterator` cung cấp đối tượng **duyệt và tách phạm vi**; với mảng nó báo `ORDERED`, `SIZED`, `SUBSIZED`.
- `trySplit()` có thể trả prefix; Spliterator mảng cho phép biết kích thước nhánh, nhưng không bắt buộc luôn chia đôi theo một lịch cố định.
- `StreamSupport.stream/intStream/longStream/doubleStream` nối một Spliterator với Stream và chọn chế độ sequential/parallel.
- **`Arrays.stream(int[])` khác `Stream.of(int[])`:** trường hợp đầu duyệt các số, trường hợp sau chứa một phần tử là cả mảng.
- Stream là lazy ở các bước trung gian, tiêu thụ bằng terminal operation và không được tái sử dụng; đừng phụ thuộc side effect của `peek`/`map`.
- **Không thay đổi mảng nguồn trong quá trình duyệt** nếu không có thiết kế đồng bộ và nhất quán thích hợp; đừng chia sẻ một List mutable qua `parallel().forEach`.
- Các API chính đã có từ **Java 8** và vẫn là cách xử lý mảng hiện hành.

### Tài liệu tham khảo chính thức

- [Oracle Java SE 8 — Arrays: stream và spliterator](https://docs.oracle.com/javase/8/docs/api/java/util/Arrays.html)
- [Oracle Java SE 26 — Arrays](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
- [Oracle Java SE 8 — Spliterator và các đặc tính](https://docs.oracle.com/javase/8/docs/api/java/util/Spliterator.html)
- [Oracle Java SE 26 — Spliterator: trySplit, SIZED, SUBSIZED](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Spliterator.html)
- [Oracle Java SE 8 — StreamSupport](https://docs.oracle.com/javase/8/docs/api/java/util/stream/StreamSupport.html)
- [Oracle Java SE 8 — IntStream](https://docs.oracle.com/javase/8/docs/api/java/util/stream/IntStream.html)
- [Oracle Java SE 26 — Stream API và tác vụ terminal](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
