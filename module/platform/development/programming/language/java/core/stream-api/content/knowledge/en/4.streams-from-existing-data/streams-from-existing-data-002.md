# Tạo Stream từ mảng bằng `Arrays.stream`

Trong chương **Tạo Stream từ dữ liệu có sẵn** của **JAVA_STREAM_API**, `Arrays.stream` là cách trực tiếp để đưa dữ liệu đang nằm trong mảng Java vào một pipeline xử lý khai báo. Thay vì tự viết vòng lặp để lọc, biến đổi hoặc tổng hợp phần tử, ta có thể tạo Stream từ mảng rồi kết hợp các thao tác `filter`, `map`, `reduce`, `collect` và các terminal operation khác.

Điểm cần hiểu rõ là **mảng là nguồn dữ liệu**, còn **Stream là đối tượng mô tả một lần xử lý dữ liệu đó**. `Arrays.stream` không biến mảng thành collection và không tạo bản sao toàn bộ mảng ngay khi được gọi. Stream tạo ra có cơ chế xử lý lazy, đồng thời tuân thủ quy tắc mỗi Stream chỉ được sử dụng cho một pipeline.

## 1. `Arrays.stream` hoạt động như thế nào?

`Arrays` là lớp tiện ích trong `java.util`. Các phương thức `stream` nhận một mảng hoặc một đoạn chỉ số của mảng và trả về Stream tuần tự (*sequential stream*) với phần tử đến từ mảng đó.

Ví dụ dưới đây là chương trình Java hoàn chỉnh:

~~~java
import java.util.Arrays;
import java.util.List;

public class ArraysStreamDemo {
    public static void main(String[] args) {
        String[] names = {"Lan", "Minh", "Linh", "An"};

        List<String> result = Arrays.stream(names)
                .filter(name -> name.length() >= 4)
                .map(String::toUpperCase)
                .sorted()
                .toList();

        System.out.println(result); // [LINH, MINH]
    }
}
~~~

Đường đi của dữ liệu:

~~~text
String[] names
      |
      v
Arrays.stream(names)  -> Stream<String>
      |
      v
filter(length >= 4)   -> "Minh", "Linh"
      |
      v
map(toUpperCase)      -> "MINH", "LINH"
      |
      v
sorted()              -> "LINH", "MINH"
      |
      v
toList()              -> List<String>
~~~

`filter`, `map` và `sorted` là các thao tác trung gian; `toList` là terminal operation kích hoạt xử lý và tạo kết quả. `Stream.toList()` có từ Java 16 và tạo danh sách không cho phép sửa đổi. Nếu học trên Java 8–15, có thể thay `.toList()` bằng `.collect(Collectors.toList())`; cần `import java.util.stream.Collectors;` và không nên mặc định kết quả collector này luôn có tính thay đổi được.

## 2. Các dạng `Arrays.stream` phổ biến

API hỗ trợ riêng mảng đối tượng và ba kiểu mảng nguyên thủy: `int[]`, `long[]`, `double[]`.

| Dữ liệu đầu vào | Ví dụ | Kiểu Stream trả về |
| --- | --- | --- |
| Mảng tham chiếu `T[]` | `Arrays.stream(new String[]{"A", "B"})` | `Stream<String>` |
| Mảng `int[]` | `Arrays.stream(new int[]{1, 2})` | `IntStream` |
| Mảng `long[]` | `Arrays.stream(new long[]{1L, 2L})` | `LongStream` |
| Mảng `double[]` | `Arrays.stream(new double[]{1.5, 2.5})` | `DoubleStream` |
| Một đoạn của `T[]` | `Arrays.stream(items, from, to)` | `Stream<T>` |
| Một đoạn của `int[]`, `long[]`, `double[]` | `Arrays.stream(numbers, from, to)` | `IntStream`, `LongStream`, `DoubleStream` tương ứng |

Các chữ ký tiêu biểu:

~~~java
static <T> Stream<T> stream(T[] array)
static <T> Stream<T> stream(T[] array, int startInclusive, int endExclusive)

static IntStream stream(int[] array)
static IntStream stream(int[] array, int startInclusive, int endExclusive)

static LongStream stream(long[] array)
static LongStream stream(long[] array, int startInclusive, int endExclusive)

static DoubleStream stream(double[] array)
static DoubleStream stream(double[] array, int startInclusive, int endExclusive)
~~~

Không có overload `Arrays.stream(byte[])`, `Arrays.stream(short[])`, `Arrays.stream(char[])`, `Arrays.stream(float[])` hoặc `Arrays.stream(boolean[])`. Cần dùng giải pháp khác nếu đầu vào có những kiểu này; xem mục 8.

## 3. Tạo `Stream<T>` từ mảng đối tượng

Mảng `String[]`, `Integer[]`, `Customer[]` hay bất kỳ mảng kiểu tham chiếu nào đều có thể tạo `Stream<T>`. Từ đây, các thao tác như `map`, `filter`, `distinct`, `sorted` và `collect` được ghép như với Stream từ Collection.

Giả sử mảng ghi nhận tên sản phẩm bán ra, có phần tử thừa khoảng trắng hoặc lặp lại:

~~~java
import java.util.Arrays;
import java.util.List;

String[] soldProducts = {"  Bút", "Sổ", "Bút", " ", "Sách", "  Sổ"};

List<String> uniqueNames = Arrays.stream(soldProducts)
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .distinct()
        .sorted()
        .toList();

System.out.println(uniqueNames); // [Bút, Sách, Sổ]
~~~

Trong pipeline này, `map` chuẩn hóa chuỗi, `filter` loại chuỗi rỗng, `distinct` loại phần tử trùng và `sorted` sắp xếp. Các thao tác trung gian không trả về một mảng mới; chúng mô tả cách dữ liệu sẽ được xử lý khi terminal operation `toList` chạy.

Nếu mục tiêu là **đếm số lần xuất hiện** thay vì loại trùng, có thể đưa Stream từ mảng vào collector:

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

String[] states = {"new", "done", "new", "waiting", "done", "new"};

Map<String, Long> counts = Arrays.stream(states)
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(counts.get("new"));     // 3
System.out.println(counts.get("done"));    // 2
System.out.println(counts.get("waiting")); // 1
~~~

Đây là ví dụ nối `Arrays.stream` với `collect` và `groupingBy`. Không nên phụ thuộc vào thứ tự duyệt các khóa trong kết quả `Map` mặc định của `groupingBy`.

### Xử lý phần tử `null` trong mảng tham chiếu

Bản thân mảng có thể chứa phần tử `null`; điều đó không ngăn việc tạo Stream. Nhưng các phép như `String::trim` hoặc `String::length` sẽ lỗi nếu nhận giá trị `null`.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

String[] labels = {"java", null, "stream"};

List<String> upper = Arrays.stream(labels)
        .filter(Objects::nonNull)
        .map(String::toUpperCase)
        .toList();

System.out.println(upper); // [JAVA, STREAM]
~~~

Phân biệt rõ **mảng có phần tử `null`** và **biến tham chiếu mảng chính là `null`**. Ví dụ `Arrays.stream((String[]) null)` ném `NullPointerException` ngay khi tạo Stream.

## 4. Chỉ Stream một phần mảng với `startInclusive` và `endExclusive`

Khi chỉ cần một đoạn phần tử, có thể truyền hai chỉ số vào `Arrays.stream(array, startInclusive, endExclusive)`. Đoạn này có dạng **[startInclusive, endExclusive)**:

- Bao gồm phần tử tại `startInclusive`.
- Không bao gồm phần tử tại `endExclusive`.
- Đếm số phần tử bằng `endExclusive - startInclusive` khi khoảng hợp lệ.
- Chỉ số hợp lệ thỏa `0 <= startInclusive <= endExclusive <= array.length`.

Ví dụ:

~~~java
import java.util.Arrays;

int[] dailyOrders = {4, 8, 3, 10, 5};

// Chỉ lấy các phần tử ở index 1, 2, 3.
int subtotal = Arrays.stream(dailyOrders, 1, 4).sum();

System.out.println(subtotal); // 21 = 8 + 3 + 10
~~~

Bảng chỉ số:

| Index | 0 | 1 | 2 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Giá trị | 4 | **8** | **3** | **10** | 5 |
| `Arrays.stream(dailyOrders, 1, 4)` | Bỏ | Lấy | Lấy | Lấy | Bỏ |

Hai trường hợp biên thường dùng:

~~~java
long emptyCount = Arrays.stream(dailyOrders, 2, 2).count(); // 0
int allSum = Arrays.stream(dailyOrders, 0, dailyOrders.length).sum(); // 30
~~~

Nếu chỉ số âm, vượt chiều dài mảng hoặc `startInclusive > endExclusive`, phương thức sẽ ném ngoại lệ kiểm tra phạm vi. **Không được hiểu tham số thứ ba là số phần tử cần lấy**: `Arrays.stream(array, 1, 4)` chọn đến trước chỉ số 4, không phải bốn phần tử tính từ vị trí 1.

Đoạn Stream phù hợp khi xử lý một cửa sổ đã biết chỉ số trong mảng. Nó khác `skip`/`limit` ở chỗ phạm vi được xác định ngay khi tạo Stream từ nguồn.

## 5. `IntStream`, `LongStream`, `DoubleStream` và lợi ích của primitive stream

Với mảng số nguyên thủy, `Arrays.stream` trả về **primitive stream** phù hợp; từng phần tử không phải tự động đóng gói thành `Integer`, `Long` hay `Double` chỉ để đi qua pipeline.

Ví dụ:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;

int[] prices = {120, 80, 200, 100};

// Chỉ tính giá >= 100, rồi lấy 10% giá trị mỗi phần tử.
int discountedUnits = Arrays.stream(prices)
        .filter(price -> price >= 100)
        .map(price -> price / 10)
        .sum();

IntSummaryStatistics stats = Arrays.stream(prices)
        .summaryStatistics();

System.out.println(discountedUnits); // 42
System.out.println(stats.getCount()); // 4
System.out.println(stats.getSum());   // 500
System.out.println(stats.getMin());   // 80
System.out.println(stats.getMax());   // 200
System.out.println(stats.getAverage()); // 125.0
~~~

Mỗi lời gọi `Arrays.stream(prices)` tạo **một Stream mới**, nên việc tính `discountedUnits` và `stats` thành hai pipeline riêng biệt là hợp lệ. Cùng một biến `IntStream` không được chạy hai terminal operation.

Các primitive stream cung cấp nhiều phép tổng hợp trực tiếp:

| Kiểu Stream | Ví dụ terminal operation hữu ích |
| --- | --- |
| `IntStream` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |
| `LongStream` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |
| `DoubleStream` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |

`average()` trả về `OptionalDouble` vì mảng rỗng không có giá trị trung bình:

~~~java
double average = Arrays.stream(new double[]{8.0, 9.5, 7.0})
        .average()
        .orElse(0.0);

double emptyAverage = Arrays.stream(new double[0])
        .average()
        .orElse(Double.NaN);
~~~

Chọn giá trị dự phòng như `0.0` hay `Double.NaN` là quyết định nghiệp vụ. Cũng cần chú ý `sum()` trên `int`/`long` có thể tràn số khi tổng vượt phạm vi kiểu, còn phép tính `double` chịu sai số dấu phẩy động.

### Khi nào cần `boxed()`?

Nếu muốn dùng một collector thao tác trên đối tượng, có thể chuyển `IntStream` thành `Stream<Integer>` qua `boxed()`:

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

int[] ages = {16, 18, 21, 17, 25};

Map<Boolean, Long> adultCounts = Arrays.stream(ages)
        .boxed()
        .collect(Collectors.partitioningBy(
                age -> age >= 18,
                Collectors.counting()
        ));

System.out.println(adultCounts.get(true));  // 3
System.out.println(adultCounts.get(false)); // 2
~~~

Việc boxing tạo các đối tượng bọc cho giá trị nguyên thủy trong quá trình xử lý và có thể tăng chi phí phân bổ/bộ nhớ. Với bài toán chỉ cần tổng, min, max hoặc trung bình, nên ưu tiên trực tiếp `IntStream`/`LongStream`/`DoubleStream`.

## 6. Mảng nhiều chiều: Stream của các hàng trước

Với `int[][]`, kiểu dữ liệu ở mức phần tử của mảng ngoài là `int[]`. Vì vậy:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

int[][] batches = {
        {2, 4},
        {5},
        {6, 8}
};

Stream<int[]> rows = Arrays.stream(batches); // Stream của từng mảng con
~~~

Đoạn trên chưa phải `IntStream` gồm các số 2, 4, 5, 6, 8. Muốn trải phẳng (*flatten*) các hàng thành một dòng số, dùng `flatMapToInt`:

~~~java
int total = Arrays.stream(batches)
        .flatMapToInt(Arrays::stream)
        .sum();

System.out.println(total); // 25
~~~

`Arrays::stream` ở đây nhận từng `int[]` và tạo `IntStream` của hàng đó. `flatMapToInt` ghép các Stream con theo thứ tự encounter order, rồi `sum` thực hiện phép tổng hợp.

Với `String[][]`, các hàng tạo `Stream<String[]>` và có thể trải phẳng bằng `flatMap`:

~~~java
String[][] teams = {
        {"Lan", "An"},
        {"Minh", "Linh"}
};

long people = Arrays.stream(teams)
        .flatMap(Arrays::stream)
        .count();

System.out.println(people); // 4
~~~

Nếu có hàng `null`, cần loại hoặc xử lý hàng đó trước khi gọi `Arrays.stream` trên từng hàng.

## 7. `Arrays.stream` và `Stream.of` khác nhau ở đâu?

Đối với mảng tham chiếu như `String[]`, cả hai cách dưới đây đều có thể tạo `Stream<String>` duyệt các phần tử mảng:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

String[] values = {"A", "B", "C"};

Stream<String> first = Arrays.stream(values);
Stream<String> second = Stream.of(values);
~~~

Nhưng **với mảng nguyên thủy**, kết quả khác biệt rất quan trọng:

~~~java
int[] numbers = {10, 20, 30};

int total = Arrays.stream(numbers).sum();    // IntStream -> 60

long arrays = Stream.of(numbers).count();    // Stream<int[]> -> 1
~~~

`Stream.of(numbers)` trong trường hợp này nhận **một đối tượng `int[]`** làm phần tử, không trải các số 10, 20, 30 thành ba phần tử riêng lẻ. Nếu muốn làm việc với từng số của `int[]`, dùng `Arrays.stream(numbers)` hoặc `IntStream.of(numbers)`.

Một số điểm chọn API:

| Mục tiêu | Cách phù hợp |
| --- | --- |
| Có sẵn `String[]` và muốn `Stream<String>` | `Arrays.stream(strings)` |
| Có sẵn `int[]` và muốn `IntStream` | `Arrays.stream(ints)` |
| Chỉ lấy đoạn chỉ số của mảng | `Arrays.stream(array, from, to)` |
| Muốn Stream từ vài phần tử rời (không có mảng nguồn) | `Stream.of(x, y, z)` |
| Muốn một `Stream<int[]>` chứa nguyên mảng `int[]` | `Stream.of(ints)` |

Việc giữ nguyên mảng thành một phần tử có thể có ích trong một số cấu trúc dữ liệu lồng nhau, nhưng không phù hợp nếu mục tiêu là xử lý từng số.

## 8. Các kiểu mảng nguyên thủy không có overload

`Arrays.stream` chỉ hỗ trợ trực tiếp `int[]`, `long[]` và `double[]` trong nhóm primitive. Đối với `byte[]`, `short[]` và `char[]`, có thể lấy các phần tử thông qua chỉ số bằng `IntStream.range`:

~~~java
import java.util.stream.IntStream;

byte[] bytes = {1, 2, 3};

int byteSum = IntStream.range(0, bytes.length)
        .map(index -> bytes[index])  // byte được nâng kiểu thành int
        .sum();

System.out.println(byteSum); // 6
~~~

Mẫu tương tự dùng được cho `short[]` và `char[]` khi muốn xử lý giá trị như số nguyên. Với `char[]`, cần nhớ `char` là đơn vị mã UTF-16; một ký tự Unicode ngoài Basic Multilingual Plane có thể gồm hai `char`. Nếu dữ liệu gốc là `String` và mục tiêu là xử lý Unicode code point, cân nhắc `String.codePoints()` thay vì duyệt từng `char`.

`float[]` có thể chuyển từng phần tử sang `double`:

~~~java
float[] measures = {1.5f, 2.5f};

double sum = IntStream.range(0, measures.length)
        .mapToDouble(index -> measures[index])
        .sum();

System.out.println(sum); // 4.0
~~~

`boolean[]` không có primitive stream dành riêng cho boolean. Có thể duyệt bằng chỉ số để `filter`/`count`, hoặc ánh xạ thành kiểu phù hợp với nhu cầu:

~~~java
boolean[] active = {true, false, true, true};

long activeCount = IntStream.range(0, active.length)
        .filter(index -> active[index])
        .count();

System.out.println(activeCount); // 3
~~~

Những cách trên là **chiến lược thay thế**, không phải overload được `Arrays.stream` cung cấp.

## 9. Tính lazy, vòng đời và việc thay đổi mảng nguồn

### Stream chỉ dùng một lần

Mảng vẫn tồn tại sau khi pipeline kết thúc; đối tượng Stream đã thực hiện terminal operation thì không sử dụng lại được.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] values = {3, 5, 7};

IntStream first = Arrays.stream(values);
long count = first.count(); // 3

// Sai: first.sum(); // Có thể ném IllegalStateException

int sum = Arrays.stream(values).sum(); // Đúng: Stream mới, kết quả 15
~~~

Muốn tính nhiều chỉ số trong một lượt, `summaryStatistics` hoặc collector tổng hợp phù hợp có thể giảm việc duyệt lặp. Nếu nguồn là mảng đọc lại được, việc gọi lại `Arrays.stream(array)` để tạo pipeline khác là hợp lệ.

### Tính lazy không có nghĩa là mảng được sao chép

~~~java
int[] values = {1, 2, 3};

int answer = Arrays.stream(values)
        .filter(value -> value > 1)
        .map(value -> value * 10)
        .sum();

System.out.println(answer); // 50
~~~

`filter` và `map` mô tả phép biến đổi; phần tử được xử lý khi `sum` kích hoạt pipeline. `Arrays.stream` sử dụng nguồn mảng có sẵn, không tự tạo một snapshot độc lập lúc khởi tạo.

Do đó, **không sửa mảng nguồn trong khi pipeline đang thực thi**, đặc biệt khi chạy song song. Nguyên tắc *non-interference* của Stream yêu cầu các hàm trong pipeline không can thiệp vào nguồn dữ liệu. Việc mảng có thể bị sửa không tạo ra quyền thay đổi nó tùy ý trong lúc Stream đang duyệt.

Nếu phải xử lý một trạng thái ổn định khi nơi khác có thể chỉnh sửa mảng, có thể tạo bản sao trước:

~~~java
int[] snapshot = Arrays.copyOf(values, values.length);
int stableSum = Arrays.stream(snapshot).sum();
~~~

Đổi lại, việc sao chép tốn thêm bộ nhớ và thời gian tỉ lệ với chiều dài mảng.

### Đóng tài nguyên và xử lý song song

Stream từ mảng nằm trong bộ nhớ thông thường không nắm giữ tệp hay kết nối I/O nên không cần `try-with-resources` như `Files.lines`. Tuy nhiên, quy tắc **một Stream cho một pipeline** vẫn áp dụng.

Mảng có kích thước đã biết nên `Spliterator` tạo từ nó có thể hỗ trợ chia vùng duyệt hiệu quả; khi dữ liệu và phép tính đủ lớn, có thể thử `parallel()`:

~~~java
long count = Arrays.stream(new int[]{1, 2, 3, 4, 5, 6})
        .parallel()
        .filter(n -> n % 2 == 0)
        .count();

System.out.println(count); // 3
~~~

`parallel()` không bảo đảm nhanh hơn: dữ liệu nhỏ có thể chậm hơn vì chi phí phân chia và phối hợp luồng. Các hàm trong pipeline cần không chia sẻ trạng thái thay đổi không an toàn; phép gộp kết quả phải tuân thủ điều kiện kết hợp thích hợp. Những thao tác nâng cao như collector tùy chỉnh hoặc Stream Gatherers ở JDK hỗ trợ chúng cũng tuân thủ vòng đời Stream và các ràng buộc về trạng thái, hiệu năng.

## 10. Lỗi thường gặp và cách tránh

| Triệu chứng hoặc cách viết | Vấn đề | Cách xử lý |
| --- | --- | --- |
| `Arrays.stream((int[]) null)` | Tham chiếu mảng là `null` | Kiểm tra đầu vào hoặc dùng quy ước mảng rỗng trước khi gọi. |
| `Arrays.stream(new byte[]{1, 2})` | Không có overload cho `byte[]` | Dùng `IntStream.range` theo chỉ số hoặc chuyển dữ liệu sang kiểu phù hợp. |
| `Stream.of(intArray).count() == 1` | Một phần tử của Stream là nguyên cả `int[]` | Dùng `Arrays.stream(intArray)` nếu muốn từng số. |
| `Arrays.stream(arr, 2, 5)` rồi nghĩ sẽ lấy 5 phần tử | Nhầm chỉ số cuối với số lượng | Xác định khoảng [2, 5), chỉ có 3 phần tử. |
| Gọi `count()` rồi `sum()` trên cùng `IntStream` | Tái sử dụng Stream đã kết thúc | Tạo Stream mới từ mảng hoặc tổng hợp chung trong một lượt. |
| `Arrays.stream(matrix).count()` với `int[][]` | Đếm số hàng, không đếm tất cả số bên trong | `flatMapToInt(Arrays::stream).count()`. |
| `map(String::length)` khi mảng có `null` | Gọi phương thức trên `null` | Dùng `filter(Objects::nonNull)` hoặc quy ước xử lý thiếu dữ liệu. |
| Sửa phần tử mảng từ tác vụ khác khi duyệt song song | Can thiệp nguồn, có thể dẫn tới kết quả sai hoặc không ổn định | Không sửa nguồn khi duyệt; dùng bản sao nếu cần. |

Khi chọn Stream từ mảng trong ứng dụng thực tế, hãy xác định trước **kiểu mảng**, **cần xử lý toàn bộ hay một đoạn**, **terminal operation mong muốn** và **mức chi phí chấp nhận được**. Bốn yếu tố này thường đủ để chọn giữa `Arrays.stream`, `IntStream.range`, việc tổng hợp trong một lượt hay lưu snapshot.

## 11. Bài tập tự kiểm tra

**Bài 1.** Dự đoán kết quả và giải thích vì sao:

~~~java
String[] colors = {"đỏ", "xanh", "vàng", "tím"};
long n = Arrays.stream(colors, 1, 3).count();
System.out.println(n);
~~~

**Đáp án:** `2`, vì khoảng chỉ số là [1, 3), tức phần tử ở vị trí 1 và 2: "xanh", "vàng".

**Bài 2.** Với mảng `int[]` sau, viết pipeline tính tổng các số chẵn lớn hơn 10:

~~~java
int[] nums = {8, 12, 15, 20, 24, 9};
~~~

**Gợi ý lời giải:**

~~~java
int result = Arrays.stream(nums)
        .filter(n -> n > 10 && n % 2 == 0)
        .sum();

System.out.println(result); // 56 = 12 + 20 + 24
~~~

**Bài 3.** Vì sao hai biểu thức dưới đây khác nhau?

~~~java
int[] values = {1, 2, 3};

long a = Arrays.stream(values).count();
long b = java.util.stream.Stream.of(values).count();
~~~

**Đáp án:** `a == 3` vì `Arrays.stream(values)` là `IntStream` của ba số; `b == 1` vì `Stream.of(values)` là Stream có duy nhất một phần tử kiểu `int[]`.

**Bài 4.** Cho mảng nhiều chiều; hãy tính tổng tất cả phần tử mà không viết vòng lặp lồng nhau:

~~~java
int[][] matrix = {{1, 2}, {3, 4}, {5}};
~~~

**Lời giải:**

~~~java
int total = Arrays.stream(matrix)
        .flatMapToInt(Arrays::stream)
        .sum();

System.out.println(total); // 15
~~~

**Ghi nhớ:** Dùng `Arrays.stream(array)` để bắt đầu một pipeline từ mảng có sẵn; mảng tham chiếu tạo `Stream<T>`, còn `int[]`/`long[]`/`double[]` tạo primitive stream tương ứng. Dùng overload [startInclusive, endExclusive) để chọn đoạn, `flatMapToInt` hoặc `flatMap` để trải mảng nhiều chiều, và tạo Stream mới từ mảng mỗi khi cần một lượt xử lý khác.
