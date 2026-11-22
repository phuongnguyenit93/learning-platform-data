# `Arrays.stream()` với mảng đối tượng và mảng nguyên thủy trong Java

## 1. Mục tiêu và vấn đề cần giải quyết

Trong Java, mảng như `String[]`, `User[]` hay `int[]` là cấu trúc lưu phần tử có độ dài cố định. Các thao tác xử lý từng phần tử, lọc, ánh xạ, tổng hợp và tính thống kê thường thuận tiện hơn khi được biểu diễn bằng **Stream API**.

Lớp tiện ích `java.util.Arrays` cung cấp `Arrays.stream(...)` để tạo stream từ một mảng đang có. Ví dụ:

~~~java
String[] words = {"Java", "Stream", "Lambda"};
List<String> selected = Arrays.stream(words)
        .filter(s -> s.length() > 4)
        .toList();

System.out.println(selected); // [Stream, Lambda]
~~~

Với mảng nguyên thủy:

~~~java
int[] numbers = {3, 6, 9};
int total = Arrays.stream(numbers).sum();

System.out.println(total); // 18
~~~

Tuy cùng tên `Arrays.stream`, **kiểu kết quả phụ thuộc loại mảng**. Mảng đối tượng tạo `Stream<T>`; mảng số nguyên thủy được hỗ trợ tạo các *primitive stream* chuyên biệt. Hiểu điều này giúp chọn đúng các thao tác như `map`, `mapToInt`, `sum`, `boxed` và `toArray`.

Bài này dùng **Java 17+**. `Arrays.stream` được giới thiệu trong Java 8; `Stream.toList()` xuất hiện từ Java 16, nên toàn bộ ví dụ độc lập bên dưới chạy với JDK 17 trở lên.

## 2. Các overload quan trọng của `Arrays.stream`

Những chữ ký cần nhớ (viết gọn):

~~~java
// Mảng tham chiếu: T có thể là String, User, Integer, ...
static <T> Stream<T> arraysStream(T[] array);
static <T> Stream<T> arraysStream(
        T[] array, int startInclusive, int endExclusive);

// Mảng nguyên thủy được hỗ trợ trực tiếp:
static IntStream arraysStream(int[] array);
static IntStream arraysStream(
        int[] array, int startInclusive, int endExclusive);

static LongStream arraysStream(long[] array);
static LongStream arraysStream(
        long[] array, int startInclusive, int endExclusive);

static DoubleStream arraysStream(double[] array);
static DoubleStream arraysStream(
        double[] array, int startInclusive, int endExclusive);
~~~

**Chú ý:** `arraysStream` bên trên là tên thay thế dùng để trình bày chữ ký; tên API thực tế phải viết **`Arrays.stream`**, không phải `Arrays.arraysStream`. Trong JDK, các overload này thuộc lớp `java.util.Arrays`.

| Đầu vào | Kiểu trả về của `Arrays.stream(...)` | Một số thao tác đặc trưng |
| --- | --- | --- |
| `String[]` | `Stream<String>` | `filter`, `map`, `toList` |
| `User[]` | `Stream<User>` | `filter`, `map(User::name)` |
| `Integer[]` | `Stream<Integer>` | `mapToInt(Integer::intValue)` |
| `int[]` | `IntStream` | `sum`, `average`, `min`, `max`, `mapToObj` |
| `long[]` | `LongStream` | `sum`, `average`, `boxed` |
| `double[]` | `DoubleStream` | `sum`, `average`, `summaryStatistics` |

Không có overload trực tiếp cho `byte[]`, `short[]`, `char[]`, `float[]` hoặc `boolean[]`. `Arrays.stream(new byte[]{1, 2})` sẽ không biên dịch. Khi cần xử lý các loại mảng đó, chọn cách phù hợp như `IntStream.range(0, a.length).map(i -> a[i])` để duyệt mảng `byte[]`/`short[]`/`char[]` dưới dạng giá trị `int`, hoặc tạo luồng qua chỉ số để ánh xạ tới kiểu thích hợp. Không suy ra Java có `ByteStream` hay `FloatStream` chuẩn.

## 3. Với mảng đối tượng: `T[] -> Stream<T>`

Một mảng đối tượng là mảng có các phần tử thuộc **reference type**, như `String`, `Integer`, `Person` hoặc `String[]`. `Arrays.stream(T[])` tạo một `Stream<T>` có cùng phần tử và thứ tự xuất hiện của mảng nguồn.

~~~java
String[] names = {"An", "Binh", "Chi"};

List<String> upperNames = Arrays.stream(names)
        .map(String::toUpperCase)
        .toList();

System.out.println(upperNames); // [AN, BINH, CHI]
~~~

`Arrays.stream(names)` không tạo sẵn một danh sách kết quả; nó tạo **pipeline nguồn** từ mảng. `map(String::toUpperCase)` là thao tác trung gian; `toList()` kích hoạt duyệt và thu thập kết quả.

### 3.1. Làm việc với kiểu record hoặc lớp do ứng dụng định nghĩa

Giả sử:

~~~java
record Person(String name, int age) {}

Person[] people = {
    new Person("An", 20),
    new Person("Binh", 17),
    new Person("Chi", 25)
};

List<String> adults = Arrays.stream(people)
        .filter(person -> person.age() >= 18)
        .map(Person::name)
        .toList();

System.out.println(adults); // [An, Chi]
~~~

Kiểu tiến triển lần lượt:

~~~text
Person[] -> Stream<Person>
         -> filter(...) : Stream<Person>
         -> map(Person::name) : Stream<String>
         -> toList() : List<String>
~~~

`Arrays.stream` không tự biến từng đối tượng thành thuộc tính của đối tượng; `map` là bước quyết định thay đổi kiểu từ `Person` sang `String`.

### 3.2. Với mảng wrapper như `Integer[]`

`Integer[]` là mảng **đối tượng**, không phải mảng `int`, nên:

~~~java
Integer[] boxedNumbers = {2, 4, 6};

Stream<Integer> objects = Arrays.stream(boxedNumbers);
int total = Arrays.stream(boxedNumbers)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 12
~~~

`Stream<Integer>` không có phương thức `sum()` trực tiếp. Muốn tính tổng theo primitive, cần `mapToInt` hoặc `Collectors.summingInt` phù hợp. Nếu `Integer[]` có phần tử `null`, `Integer::intValue` sẽ gây `NullPointerException` khi gặp phần tử đó, trừ khi lọc/xử lý null trước.

## 4. Với `int[]`: tạo `IntStream`, không phải `Stream<Integer>`

`Arrays.stream(int[])` tạo **`java.util.stream.IntStream`**. Một `IntStream` giữ giá trị `int` theo ngữ nghĩa primitive, có các phương thức tổng hợp như `sum`, `average`, `min`, `max` và `summaryStatistics` mà không phải boxing từng phần tử vào `Integer` trong pipeline primitive.

~~~java
int[] values = {2, 5, 8, 11};

int sum = Arrays.stream(values).sum();
long count = Arrays.stream(values).filter(n -> n % 2 != 0).count();
int maximum = Arrays.stream(values).max().orElseThrow();

System.out.println(sum);     // 26
System.out.println(count);   // 2
System.out.println(maximum); // 11
~~~

Vì `IntStream` là stream primitive, các API chuyển đổi thường dùng gồm:

~~~java
int[] source = {1, 2, 3};

IntStream primitiveStream = Arrays.stream(source);
List<Integer> asList = Arrays.stream(source).boxed().toList();
List<String> labels = Arrays.stream(source)
        .mapToObj(i -> "N" + i)
        .toList();

System.out.println(asList);  // [1, 2, 3]
System.out.println(labels);  // [N1, N2, N3]
~~~

- `boxed()` biến mỗi `int` thành `Integer` và trả `Stream<Integer>`.
- `mapToObj(...)` chuyển mỗi `int` sang một đối tượng bất kỳ, chẳng hạn `String`.
- `IntStream.toArray()` tạo `int[]` mới, không phải `Integer[]`.
- `map(...)` ngay trên `IntStream` vẫn trả một `IntStream` khi mapper là `IntUnaryOperator`.

Có thể dùng `IntStream.range(0, array.length)` nếu cần **chỉ số** của phần tử thay vì chỉ giá trị của nó.

## 5. Với `long[]` và `double[]`

### 5.1. `long[] -> LongStream`

~~~java
long[] fileSizes = {10L, 20L, 35L};

long total = Arrays.stream(fileSizes).sum();
long count = Arrays.stream(fileSizes).count();

System.out.println(total); // 65
System.out.println(count); // 3
~~~

`LongStream` có các thao tác như `mapToObj`, `boxed`, `sum`, `average`, `min` và `max`. `average()` trả về **`OptionalDouble`**, bởi mảng có thể rỗng và phép tính trung bình không có kết quả trong trường hợp đó.

### 5.2. `double[] -> DoubleStream`

~~~java
double[] temperatures = {2.5, 3.5, 4.0};

double total = Arrays.stream(temperatures).sum();
double average = Arrays.stream(temperatures).average().orElseThrow();

System.out.println(total); // 10.0
System.out.println(average > 3.0); // true
~~~

`DoubleStream` có `summaryStatistics()` trả `DoubleSummaryStatistics` với số phần tử, tổng, min, max và trung bình. Tính toán dấu phẩy động có thể có sai số biểu diễn; các giá trị như `NaN` và vô cực cũng ảnh hưởng các phép tổng hợp. Trong những nghiệp vụ yêu cầu độ chính xác thập phân cố định (ví dụ tiền tệ), không nên dùng `double` tùy tiện; cần chọn mô hình số phù hợp.

### 5.3. Vì sao Java không có primitive stream cho mọi primitive?

JDK chuẩn chỉ cung cấp ba specialized primitive streams: `IntStream`, `LongStream` và `DoubleStream`. Có thể chuyển các loại số nhỏ như `byte`, `short`, `char` lên `int` thông qua numeric promotion khi ánh xạ, nhưng `boolean[]` cần một cách mô hình hóa rõ ràng khác (chẳng hạn duyệt chỉ số và dùng `mapToObj(i -> flags[i])`). Không có `BooleanStream` trong Stream API chuẩn.

## 6. Lấy một phần mảng bằng `Arrays.stream(array, startInclusive, endExclusive)`

Tất cả bốn họ overload ở phần 2 đều có dạng nhận chỉ số bắt đầu/kết thúc. Khoảng lấy ra là:

\[
[\text{startInclusive}, \text{endExclusive})
\]

Tức **lấy phần tử ở chỉ số bắt đầu, không lấy phần tử ở chỉ số kết thúc**.

~~~java
String[] names = {"A", "B", "C", "D"};

List<String> slice = Arrays.stream(names, 1, 3).toList();
System.out.println(slice); // [B, C]
~~~

Mảng nguyên thủy tương tự:

~~~java
int[] numbers = {10, 20, 30, 40};

int[] slice = Arrays.stream(numbers, 1, 3).toArray();
System.out.println(Arrays.toString(slice)); // [20, 30]
~~~

Với mảng dài `n`, khoảng hợp lệ có `0 <= startInclusive <= endExclusive <= n`. Khoảng `[k,k)` có 0 phần tử. Các chỉ số sai phạm vi hoặc thứ tự gây lỗi kiểm tra chỉ số thay vì âm thầm lấy phần “còn lại”.

Lợi ích của overload này: có thể tạo luồng trực tiếp cho một **vùng liên tiếp** của mảng mà không bắt buộc sao chép vùng đó sang một mảng mới trước. Tuy nhiên, kết quả từ một terminal như `toArray()` hoặc `toList()` là kết quả được tạo riêng; đừng nhầm nguồn stream với cấu trúc đầu ra đã materialize.

Nếu cần lấy các phần tử theo **điều kiện**, dùng `filter`; nếu cần **vùng chỉ số** đã biết, overload nhận `start/end` diễn đạt ý định rõ hơn.

## 7. Phân biệt với `Stream.of(array)` và `Arrays.asList(array).stream()`

Đây là nhóm lỗi rất thường gặp, nhất là khi đổi từ mảng đối tượng sang mảng nguyên thủy.

### 7.1. Mảng đối tượng `String[]`

~~~java
String[] words = {"a", "b"};

Stream<String> a = Arrays.stream(words);
Stream<String> b = Stream.of(words);
Stream<String> c = Arrays.asList(words).stream();
~~~

Trong trường hợp này, cả ba đều duyệt hai phần tử `"a"` và `"b"`. `Stream.of(words)` dùng overload varargs với `String[]` và coi các phần tử của mảng là các phần tử stream. `Arrays.asList(words)` cho một danh sách kích thước cố định dựa trên mảng, sau đó `stream()` tạo luồng từ danh sách đó.

Dù các pipeline có thể cho cùng giá trị, chúng không phải cùng một cấu trúc trung gian: `Arrays.stream` là cách trực tiếp từ mảng, không cần tạo `List` trung gian.

### 7.2. Mảng nguyên thủy `int[]`: khác biệt quan trọng

~~~java
int[] nums = {1, 2, 3};

IntStream a = Arrays.stream(nums);
Stream<int[]> b = Stream.of(nums);

System.out.println(a.count()); // 3
System.out.println(b.count()); // 1
~~~

`Arrays.stream(nums)` thấy **ba số `int`**; `Stream.of(nums)` thấy **một phần tử là chính mảng `int[]`**. Tương tự:

~~~java
List<int[]> oneArray = Arrays.asList(nums);
System.out.println(oneArray.size()); // 1
~~~

`Arrays.asList(int[])` không tự boxing mỗi số thành `Integer`. Để có `List<Integer>`, sử dụng:

~~~java
List<Integer> boxed = Arrays.stream(nums).boxed().toList();
System.out.println(boxed); // [1, 2, 3]
~~~

Vì vậy, nếu nguồn là `int[]`, đừng thay `Arrays.stream(ints)` bằng `Stream.of(ints)` mà không xét kiểu.

### 7.3. `Arrays.stream` so với `IntStream.of`

Nếu chỉ cần tạo primitive stream từ mảng `int[]`, `IntStream.of(nums)` cũng có overload varargs nhận `int...` và cho các giá trị tương tự `Arrays.stream(nums)`. Nhưng `Arrays.stream(nums, from, to)` là API trực tiếp để giới hạn **vùng chỉ số** mảng.

## 8. Mảng nhiều chiều và cách làm phẳng

Một mảng hai chiều Java thực chất là **mảng chứa các mảng**. Ví dụ `String[][]` là mảng mà mỗi phần tử có kiểu `String[]`.

~~~java
String[][] blocks = {
    {"A", "B"},
    {"C"}
};

Stream<String[]> rows = Arrays.stream(blocks);
List<String> flat = Arrays.stream(blocks)
        .flatMap(Arrays::stream)
        .toList();

System.out.println(flat); // [A, B, C]
~~~

`Arrays.stream(blocks)` trả `Stream<String[]>`, không tự flatten thành `Stream<String>`. `flatMap(Arrays::stream)` lần lượt biến mỗi `String[]` thành `Stream<String>` rồi nối chúng. Nếu muốn giữ cấu trúc hàng/cột, không flatten; hãy xử lý từng hàng theo chủ đích.

Với `int[][]`:

~~~java
int[][] matrix = {{1, 2}, {3, 4}};

int total = Arrays.stream(matrix)
        .flatMapToInt(Arrays::stream)
        .sum();

System.out.println(total); // 10
~~~

`Arrays.stream(matrix)` trả `Stream<int[]>`. Dùng `flatMapToInt` bởi mỗi `Arrays.stream(int[])` là một **`IntStream`**, không phải `Stream<Integer>`.

Mảng có hàng `null` cần xử lý riêng; `Arrays.stream(null)` không tạo Stream rỗng và sẽ gây lỗi. Trường hợp dữ liệu thực sự có hàng null, có thể cân nhắc lọc `Objects::nonNull` trước khi flatten.

## 9. Nguồn dữ liệu, tính lazy và khả năng thay đổi mảng

### 9.1. Các thao tác trung gian là lazy

~~~java
String[] words = {"a", "bbb"};

Stream<Integer> lengths = Arrays.stream(words)
        .map(s -> s.length()); // Pipeline được thiết lập.

List<Integer> result = lengths.toList(); // Bắt đầu duyệt và thu thập.
System.out.println(result); // [1, 3]
~~~

`map` không tính sẵn tất cả chiều dài lúc khai báo `lengths`. Các thao tác trung gian thường chỉ được thực hiện khi một terminal operation tiêu thụ pipeline. Không gọi `toList()` rồi sau đó `count()` trên cùng biến `lengths`: một Stream chỉ được tiêu thụ một lần.

Một số terminal có thể tối ưu không duyệt mọi phần tử nếu đã biết kích thước và các yêu cầu của pipeline cho phép; không dựa vào side effect trong `map` để chứng minh công việc đã chạy.

### 9.2. `Arrays.stream` không tự sao chép mảng nguồn

`Arrays.stream(array)` tạo stream từ **mảng gốc**, không biến nó thành một bản sao bất biến. Điều này có hai hệ quả:

- Tạo một `Stream` không có nghĩa mọi giá trị đã được “chụp lại”. Thay đổi mảng nguồn khi pipeline đang được sử dụng có thể ảnh hưởng quan sát và vi phạm yêu cầu **non-interference**; hãy tránh sửa nguồn trong lúc duyệt.
- Với mảng các đối tượng mutable, những tham chiếu phần tử nhận được là tham chiếu tới các đối tượng gốc. Một `map` trả lại đối tượng hoặc `toList()` chứa các tham chiếu đó **không phải deep copy**.

Ví dụ an toàn:

~~~java
String[] names = {"An", "Binh"};
List<String> snapshot = Arrays.stream(names).toList();

names[0] = "Chi";
System.out.println(snapshot); // [An, Binh]
~~~

`snapshot` là danh sách kết quả đã thu thập xong và chứa các tham chiếu `String` ban đầu; việc thay phần tử ở vị trí 0 trong mảng sau khi thu thập không thay đổi phần tử tương ứng của danh sách. Với đối tượng mutable được chia sẻ, thay **trạng thái đối tượng** lại là trường hợp khác. `Stream.toList()` trả về danh sách unmodifiable theo hợp đồng, còn việc các đối tượng phần tử có mutable hay không là vấn đề riêng.

### 9.3. Null: mảng null khác phần tử null

~~~java
String[] words = {"a", null, "c"};

List<String> safe = Arrays.stream(words)
        .filter(java.util.Objects::nonNull)
        .map(String::toUpperCase)
        .toList();

System.out.println(safe); // [A, C]
~~~

Mảng có thể chứa phần tử `null`; `Arrays.stream(words)` vẫn tạo Stream, nhưng method reference `String::toUpperCase` sẽ ném `NullPointerException` nếu gặp phần tử null chưa được xử lý.

Ngược lại, nếu biến mảng tự nó bằng `null`:

~~~java
String[] missing = null;
// Arrays.stream(missing); // Ném NullPointerException.
~~~

`Arrays.stream` không có quy tắc tự hiểu **mảng null** là mảng rỗng. Nếu dữ liệu nguồn tùy chọn, hãy kiểm tra và tạo `Stream.empty()` hoặc định nghĩa hợp đồng đầu vào không null rõ ràng.

## 10. Kết hợp primitive stream với các phép tổng hợp

Với mảng `int[]`, dùng trực tiếp `IntStream` để thu được thống kê:

~~~java
int[] samples = {3, 7, 10};

int sum = Arrays.stream(samples).sum();
double average = Arrays.stream(samples).average().orElse(0.0);
int max = Arrays.stream(samples).max().orElseThrow();

System.out.println(sum);      // 20
System.out.println(average > 6); // true
System.out.println(max);      // 10
~~~

**Tại sao đọc mảng ba lần?** Mỗi terminal operation tiêu thụ stream; để thực hiện các terminal độc lập, ta tạo stream mới. Khi muốn nhiều thống kê trong một lần duyệt, dùng `summaryStatistics()`:

~~~java
IntSummaryStatistics stats = Arrays.stream(samples)
        .summaryStatistics();

System.out.println(stats.getCount()); // 3
System.out.println(stats.getSum());   // 20
System.out.println(stats.getMin());   // 3
System.out.println(stats.getMax());   // 10
~~~

Phải import `java.util.IntSummaryStatistics` khi dùng ví dụ riêng.

`min()`, `max()` và `average()` trên Stream nguyên thủy trả `OptionalInt`, `OptionalLong` hoặc `OptionalDouble` tùy phương thức. Không gọi `getAsInt()`/`getAsDouble()` một cách mù quáng trên mảng có thể rỗng; hãy dùng `orElse`, `orElseThrow` với thông báo thích hợp hoặc kiểm tra `isPresent`.

## 11. Ví dụ Java 17+ độc lập, có stdout xác định

Tạo tệp **`ArraysStreamDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ArraysStreamDemo {
    record Person(String name, int age) {}

    public static void main(String[] args) {
        String[] words = {" Java ", "API", "Stream"};
        List<String> trimmed = Arrays.stream(words)
                .map(String::trim)
                .toList();
        System.out.println("objects=" + trimmed);

        List<String> slice = Arrays.stream(words, 1, 3)
                .map(String::trim)
                .toList();
        System.out.println("slice=" + slice);

        Person[] people = {
                new Person("An", 20),
                new Person("Binh", 17),
                new Person("Chi", 25)
        };
        List<String> adults = Arrays.stream(people)
                .filter(p -> p.age() >= 18)
                .map(Person::name)
                .toList();
        System.out.println("adults=" + adults);

        int[] values = {2, 5, 8, 11};
        IntSummaryStatistics stats = Arrays.stream(values)
                .summaryStatistics();
        System.out.println("intSum=" + stats.getSum());
        System.out.println("oddCount=" + Arrays.stream(values)
                .filter(n -> n % 2 != 0).count());
        System.out.println("boxed=" + Arrays.stream(values)
                .boxed().toList());
        System.out.println("intSlice=" + Arrays.toString(
                Arrays.stream(values, 1, 3).toArray()));

        System.out.println("ofPrimitiveCount=" + Stream.of(values).count());
        System.out.println("arrayPrimitiveCount=" + Arrays.stream(values).count());

        long[] longs = {10L, 20L, 35L};
        System.out.println("longSum=" + Arrays.stream(longs).sum());

        double[] doubles = {2.5, 3.5, 4.0};
        System.out.println("doubleSum=" + Arrays.stream(doubles).sum());

        String[][] blocks = {{"A", "B"}, {"C"}};
        System.out.println("flatObjects=" + Arrays.stream(blocks)
                .flatMap(Arrays::stream).toList());

        int[][] matrix = {{1, 2}, {3, 4}};
        System.out.println("flatIntSum=" + Arrays.stream(matrix)
                .flatMapToInt(Arrays::stream).sum());

        String[] nullable = {"a", null, "c"};
        System.out.println("nonNull=" + Arrays.stream(nullable)
                .filter(Objects::nonNull)
                .toList());

        int[] empty = {};
        System.out.println("emptyAverage=" + Arrays.stream(empty)
                .average().orElse(0.0));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ArraysStreamDemo.java
java ArraysStreamDemo
~~~

Stdout dự kiến:

~~~text
objects=[Java, API, Stream]
slice=[API, Stream]
adults=[An, Chi]
intSum=26
oddCount=2
boxed=[2, 5, 8, 11]
intSlice=[5, 8]
ofPrimitiveCount=1
arrayPrimitiveCount=4
longSum=65
doubleSum=10.0
flatObjects=[A, B, C]
flatIntSum=10
nonNull=[a, c]
emptyAverage=0.0
~~~

Các kết quả có thứ tự xác định vì mọi nguồn ở đây là mảng có thứ tự, pipeline tuần tự và không dùng callback chạy bất đồng bộ. `Arrays.stream` tạo nguồn stream riêng cho mỗi terminal operation; các trường hợp cần nhiều phép tính như `sum` và `count` có thể tạo luồng mới hoặc dùng thống kê tổng hợp.

## 12. Parallel stream và lựa chọn khi tối ưu hiệu năng

Stream tạo từ `Arrays.stream(array)` thông thường là **sequential**:

~~~java
int[] numbers = {1, 2, 3, 4};
int total = Arrays.stream(numbers).parallel().sum();
System.out.println(total); // 10
~~~

`parallel()` thay đổi cách pipeline có thể được thực thi, không thay kiểu từ `IntStream` sang `Stream<Integer>`. Các phép tổng hợp được thiết kế phù hợp như `sum` thường thuận tiện với parallel, nhưng **không mặc định parallel nhanh hơn**: chi phí phân chia, kết hợp, kích thước mảng, công việc mỗi phần tử và môi trường chạy quyết định hiệu quả.

Nếu cần thứ tự khi thực hiện side effect, `forEach` trên parallel stream không bảo đảm thứ tự encounter order. `forEachOrdered` có ràng buộc thứ tự nhưng có thể giảm lợi ích song song:

~~~java
Arrays.stream(new String[]{"A", "B", "C"})
        .parallel()
        .forEachOrdered(System.out::println);
~~~

Với xử lý số liệu kinh doanh, ưu tiên `map`/`reduce`/`collect` thuần khiết và không sửa mảng nguồn trong lúc duyệt. Đối với `double`, kết quả của các phép toán dấu phẩy động có thể chịu ảnh hưởng của thứ tự cộng và quy tắc làm tròn; không tự giả định mọi pipeline số thực đều cho kết quả bitwise giống nhau dưới mọi cách thực thi.

## 13. Lỗi thường gặp và cách sửa

| Sai lầm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Gán `Arrays.stream(intArray)` vào `Stream<Integer>` | Kết quả là `IntStream`, không phải `Stream<Integer>` | Dùng `IntStream` hoặc `.boxed()` |
| Viết `Arrays.stream(new byte[]{1,2})` | Không có overload cho `byte[]` | Duyệt chỉ số bằng `IntStream.range` và ánh xạ |
| Dùng `Stream.of(intArray)` rồi tưởng có một stream các `int` | Nó có một phần tử kiểu `int[]` | Dùng `Arrays.stream(intArray)` hoặc `IntStream.of` |
| Gọi `sum()` trên `Stream<Integer>` | Reference stream không có `sum()` | Dùng `mapToInt(Integer::intValue).sum()` |
| Hiểu `endExclusive` là chỉ số cuối được lấy | Khoảng là nửa mở | `Arrays.stream(a, 1, 3)` lấy chỉ số 1, 2 |
| Tưởng `Arrays.stream(matrix)` tự làm phẳng mảng hai chiều | Mỗi phần tử của source là một mảng con | `flatMap(Arrays::stream)` hoặc `flatMapToInt` |
| Tưởng `Arrays.stream(array)` sao chép mảng ngay | Stream đọc dữ liệu từ nguồn mảng, không snapshot ngay | Tránh sửa nguồn khi duyệt; copy rõ ràng nếu cần |
| Truyền biến mảng `null` | Ném `NullPointerException` | Kiểm tra mảng hoặc thiết kế đầu vào non-null |
| Gọi `String::trim` trên phần tử null | Method reference cần receiver khác null | `filter(Objects::nonNull)` trước |
| Tái sử dụng cùng một Stream sau terminal | Stream dùng một lần | Tạo stream mới hoặc tổng hợp một lần |
| Gọi `average().getAsDouble()` trên mảng rỗng | Không có trung bình | Dùng `orElse`/`orElseThrow` phù hợp |
| Mặc định `parallel()` nhanh hơn | Có chi phí scheduling và phụ thuộc workload | Đo và kiểm tra tính đúng trước khi tối ưu |

## 14. Bài tập tự kiểm tra

**Bài 1.** Cho `int[] numbers = {4, 8, 12};`. `Arrays.stream(numbers)` trả kiểu gì? `Stream.of(numbers)` trả kiểu gì?

**Đáp án:** `Arrays.stream(numbers)` trả `IntStream` gồm 3 số; `Stream.of(numbers)` là `Stream<int[]>` gồm 1 phần tử là mảng.

**Bài 2.** Với `String[] colors = {"red", "green", "blue", "white"};`, kết quả `Arrays.stream(colors, 1, 3).toList()`?

**Đáp án:** `[green, blue]`; chỉ số 3 không được lấy.

**Bài 3.** Muốn biến `int[]` thành `List<Integer>` thì dùng gì?

**Đáp án:** `Arrays.stream(array).boxed().toList()`. `boxed()` chuyển `IntStream` thành `Stream<Integer>`.

**Bài 4.** Cho `Integer[] values = {1, 2, 3};`. Tại sao không thể gọi `Arrays.stream(values).sum()`?

**Đáp án:** `Integer[]` là mảng tham chiếu nên cho `Stream<Integer>`, không có `sum()`. Dùng `Arrays.stream(values).mapToInt(Integer::intValue).sum()`.

**Bài 5.** Muốn tính tổng `int[][]` thì dùng `flatMap` hay `flatMapToInt`?

**Đáp án:** `Arrays.stream(matrix).flatMapToInt(Arrays::stream).sum()`. Mapper trả `IntStream` nên cần `flatMapToInt`.

**Bài 6.** Nếu có `String[] a = null;`, `Arrays.stream(a)` có trở thành Stream rỗng không?

**Đáp án:** Không. Truyền mảng null gây `NullPointerException`; phải kiểm tra hoặc thay bằng mảng rỗng theo chính sách API.

**Bài 7.** `Arrays.stream(new int[0]).average()` trả gì?

**Đáp án:** Một `OptionalDouble` rỗng. Không có giá trị trung bình; có thể dùng `orElse(0.0)` nếu 0 là giá trị mặc định phù hợp nghiệp vụ.

## Ghi nhớ

**`Arrays.stream` chuyển mảng có sẵn thành một Stream để dùng với Stream API.** Kiểu mảng quyết định kiểu Stream:

- `T[] -> Stream<T>` cho mảng đối tượng.
- `int[] -> IntStream`, `long[] -> LongStream`, `double[] -> DoubleStream` cho ba loại primitive được hỗ trợ trực tiếp.
- Dạng `Arrays.stream(array, startInclusive, endExclusive)` chỉ duyệt một đoạn chỉ số nửa mở `[start, end)`.
- `boxed()` chuyển primitive stream thành reference stream; `mapToInt` và các biến thể giúp chuyển ngược khi cần phép toán primitive.
- `Stream.of(intArray)` không tương đương `Arrays.stream(intArray)` về kiểu hay số lượng phần tử; mảng nhiều chiều cần `flatMap` tường minh.
- Stream là pipeline tiêu thụ một lần, không tự copy toàn bộ mảng nguồn, và cần xử lý đúng null cũng như tránh can thiệp nguồn khi đang duyệt.

Nắm rõ kiểu đầu ra của từng overload là chìa khóa để kết hợp mảng với `filter`, `map`, `flatMap`, `sum`, `collect` và các phép thống kê một cách an toàn.
