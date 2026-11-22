# Chuyển kết quả thành mảng bằng toArray

Trong chương **Duyệt, tìm kiếm và đối sánh** của **Java Stream API**, nhiều pipeline bắt đầu từ collection, mảng hoặc nguồn sinh dữ liệu, đi qua các bước `filter`, `map`, `flatMap` rồi cần trả về một kết quả có thể truyền cho API cũ, lưu vào trường dữ liệu hoặc truy cập theo chỉ số. **`toArray` là terminal operation dùng để kết thúc pipeline và thu các phần tử đầu ra vào một mảng.**

Thao tác này có vẻ đơn giản, nhưng có ba điểm dễ nhầm: `Stream.toArray()` không tự tạo mảng có kiểu phần tử như `String[]`; dạng `Stream.toArray(String[]::new)` sử dụng một *array generator* để tạo mảng tham chiếu đúng kiểu; còn `IntStream`, `LongStream` và `DoubleStream` có `toArray()` riêng, trả về mảng nguyên thủy tương ứng.

Bài học giải thích kiểu dữ liệu, cách dùng, các lỗi thường gặp, thứ tự phần tử và chi phí bộ nhớ khi dùng `toArray` trong một pipeline khai báo.

## 1. Khi nào cần chuyển Stream thành mảng?

Giả sử đã lọc một danh sách mã sản phẩm và chuẩn hóa chữ hoa. Một hệ thống bên ngoài yêu cầu tham số kiểu `String[]` thay vì `Stream<String>` hay `List<String>`. Ta có thể hoàn tất pipeline bằng `toArray(String[]::new)`:

~~~java
import java.util.Arrays;
import java.util.List;

public class ToArrayDemo {
    public static void main(String[] args) {
        List<String> codes = Arrays.asList(" pen ", "book", "", "notebook");

        String[] result = codes.stream()
                .map(String::trim)
                .filter(code -> !code.isEmpty())
                .map(String::toUpperCase)
                .toArray(String[]::new);

        System.out.println(Arrays.toString(result));
        // [PEN, BOOK, NOTEBOOK]
    }
}
~~~

Từng phần của pipeline có vai trò riêng:

1. `codes.stream()` tạo một Stream từ danh sách.
2. `map(String::trim)` bỏ khoảng trắng ở đầu và cuối từng mã.
3. `filter` loại mã rỗng.
4. `map(String::toUpperCase)` tạo chuỗi mới theo dạng chữ hoa.
5. `toArray(String[]::new)` **thực thi pipeline** và trả về mảng `String[]`.

Kết quả `result` là một mảng thông thường của Java: có `length`, có thể truy cập `result[0]`, có kích thước cố định sau khi tạo và có thể thay phần tử theo chỉ số nếu muốn.

## 2. Phân biệt ba cách gọi `toArray` quan trọng

| Nguồn | Cách gọi | Kiểu trả về | Mục đích |
| --- | --- | --- | --- |
| `Stream<T>` | `stream.toArray()` | `Object[]` | Khi chỉ cần mảng đối tượng tổng quát. |
| `Stream<T>` | `stream.toArray(T[]::new)` | `T[]` tương ứng với kiểu mảng generator tạo | Khi cần mảng tham chiếu có kiểu cụ thể như `String[]`, `Employee[]`. |
| `IntStream` | `stream.toArray()` | `int[]` | Thu các giá trị `int` mà không cần boxing. |
| `LongStream` | `stream.toArray()` | `long[]` | Thu các giá trị `long`. |
| `DoubleStream` | `stream.toArray()` | `double[]` | Thu các giá trị `double`. |

Với `Stream<T>`, dạng có generator dùng chữ ký khái quát:

~~~java
<A> A[] toArray(java.util.function.IntFunction<A[]> generator)
~~~

Hàm `generator` nhận một kích thước kiểu `int` và tạo ra mảng tương ứng, chẳng hạn `size -> new String[size]`. Dạng này thường được viết gọn thành method reference `String[]::new`.

Điểm cốt lõi là **kiểu trả về của `toArray` phụ thuộc vào overload và kiểu Stream**. Việc các phần tử đầu vào “đều là chuỗi” không làm overload không tham số tự suy ra `String[]`.

## 3. `toArray()` không tham số: luôn làm việc với `Object[]`

Với Stream đối tượng, cách viết ngắn nhất là:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Object[] result = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() >= 3)
        .toArray();

System.out.println(Arrays.toString(result)); // [Lan, Minh]
~~~

Dù các phần tử đều là `String`, kết quả của overload này có kiểu mảng runtime `Object[]`. Không được ép kiểu trực tiếp sang `String[]`:

~~~java
Object[] objects = Stream.of("Lan", "Minh").toArray();

// Sai khi chạy: Object[] không phải String[].
String[] names = (String[]) objects; // ClassCastException
~~~

**Cách sửa** là yêu cầu Stream tạo đúng kiểu mảng ngay lúc thu kết quả:

~~~java
String[] names = Stream.of("Lan", "Minh")
        .toArray(String[]::new);
~~~

Nếu đã có `Object[]` hợp lệ và thực sự muốn tạo một mảng chuỗi mới, có thể dùng `Arrays.copyOf(objects, objects.length, String[].class)` khi mọi phần tử đều tương thích; tuy nhiên, trong một pipeline mới, `toArray(String[]::new)` rõ ràng và trực tiếp hơn.

Không nên dùng kiểu ép không an toàn hoặc `@SuppressWarnings` để che giấu lỗi kiểu mảng.

## 4. `toArray(String[]::new)`: mảng đúng kiểu ngay tại điểm kết thúc

Ví dụ với tên người dùng:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

String[] names = Stream.of("An", "Bình", "Chi", "Dũng")
        .filter(name -> name.length() >= 3)
        .toArray(String[]::new);

System.out.println(Arrays.toString(names)); // [Bình, Chi, Dũng]
System.out.println(names.length);            // 3
~~~

`String[]::new` là **tham chiếu đến constructor của mảng**, tương đương về ý nghĩa với:

~~~java
String[] names = Stream.of("Lan", "Minh")
        .toArray(size -> new String[size]);
~~~

Với kiểu tự định nghĩa, có thể dùng cùng một mẫu:

~~~java
record Employee(String id, String department) {}

Employee[] developers = employees.stream()
        .filter(e -> "DEV".equals(e.department()))
        .toArray(Employee[]::new);
~~~

Đoạn cuối giả định `employees` là một collection chứa `Employee`; cú pháp `record` cần Java 16 trở lên. Trên Java 8, thay `record` bằng class thông thường, còn `toArray(Employee[]::new)` vẫn dùng được.

### Generator phải cung cấp mảng phù hợp

`toArray(IntFunction<A[]>)` có thể gọi generator khi cần mảng cho phân đoạn dữ liệu hoặc phục vụ việc ghép kết quả, đặc biệt khi chạy song song. Vì vậy:

- Generator nên chỉ **tạo mảng mới với kích thước được yêu cầu**.
- Không nên giả định generator chỉ được gọi đúng một lần hay lần nào cũng nhận số phần tử cuối cùng của toàn pipeline.
- Không nên ghi log nghiệp vụ, tăng biến đếm dùng chung hoặc trả cùng một mảng chia sẻ để tạo side effect.
- Nên dùng `String[]::new`, `Employee[]::new` hoặc lambda `size -> new MyType[size]` vì ngắn gọn và đúng hợp đồng.

Mảng phải có kiểu runtime tương thích với các phần tử cần lưu. Khi mã khai báo một Stream chứa đối tượng thuộc nhiều kiểu, không nên cố chuyển thành mảng kiểu hẹp chỉ nhờ array generator.

## 5. Ba lỗi kiểu dữ liệu dễ gặp

### 5.1. `ClassCastException` khi ép `Object[]` thành `String[]`

~~~java
Object[] source = Stream.of("a", "b").toArray();
String[] wrong = (String[]) source; // Sai khi chạy.
~~~

Vấn đề không nằm ở từng phần tử `"a"`, `"b"`, mà ở **kiểu của chính mảng**. Mảng Java có kiểu runtime và không thể biến một `Object[]` đã tạo thành `String[]` bằng cast.

### 5.2. `ArrayStoreException` khi phần tử không khớp kiểu mảng

~~~java
import java.util.stream.Stream;

Stream<Object> mixed = Stream.of("A", 42);

// Có thể biên dịch, nhưng 42 không thể được lưu vào String[].
String[] wrong = mixed.toArray(String[]::new); // ArrayStoreException
~~~

Tham số kiểu `<A>` của overload dùng generator cho phép chọn mảng đầu ra, nhưng **không ép các phần tử thành kiểu `A`**. Nếu mọi phần tử đều phải là chuỗi, hãy tạo `Stream<String>` một cách an toàn, kiểm tra/biến đổi từng phần tử trước khi thu mảng:

~~~java
String[] converted = Stream.<Object>of("A", 42)
        .map(String::valueOf)
        .toArray(String[]::new);

System.out.println(Arrays.toString(converted)); // [A, 42]
~~~

`map(String::valueOf)` ở đây chuyển từng phần tử thành chuỗi. Nếu bài toán yêu cầu loại phần tử không phải chuỗi, thay bằng bước kiểm tra kiểu có chủ đích; hai cách đó có ý nghĩa nghiệp vụ khác nhau.

### 5.3. Mảng có kiểu chung không phải `new T[n]`

Trong phương thức generic, Java không cho tạo trực tiếp mảng `new T[n]` vì *type erasure*. Cách phổ biến là **yêu cầu caller cung cấp generator**:

~~~java
import java.util.Collection;
import java.util.function.IntFunction;
import java.util.function.Predicate;

public static <T> T[] selectToArray(
        Collection<T> source,
        Predicate<? super T> predicate,
        IntFunction<T[]> arrayFactory) {

    return source.stream()
            .filter(predicate)
            .toArray(arrayFactory);
}
~~~

Cách gọi:

~~~java
String[] selected = selectToArray(
        Arrays.asList("Lan", "An", "Minh"),
        name -> name.length() >= 3,
        String[]::new
);

// selected = ["Lan", "Minh"]
~~~

Trong ví dụ này, caller xác định mảng kết quả cần có kiểu runtime `String[]`. Điều đó giúp phương thức tổng quát tránh phải ép kiểu mảng một cách không an toàn.

## 6. Stream số nguyên thủy: `int[]` khác `Integer[]`

Đây là khác biệt rất quan trọng giữa `Stream<Integer>` và `IntStream`.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.Stream;

// Stream đối tượng: trả Integer[] khi dùng generator.
Integer[] boxed = Stream.of(1, 2, 3)
        .toArray(Integer[]::new);

// IntStream: toArray() trả trực tiếp int[].
int[] primitive = IntStream.of(1, 2, 3)
        .toArray();

System.out.println(Arrays.toString(boxed));     // [1, 2, 3]
System.out.println(Arrays.toString(primitive)); // [1, 2, 3]
~~~

Hai mảng in giống nhau nhưng khác kiểu và cách lưu trữ:

| Đặc điểm | `Integer[]` | `int[]` |
| --- | --- | --- |
| Phần tử | Tham chiếu tới đối tượng `Integer` | Giá trị nguyên thủy `int` |
| Chứa `null` | Có thể | Không |
| Dùng cho API yêu cầu `int[]` | Không tương thích trực tiếp | Phù hợp |
| Boxing/unboxing | Có thể phát sinh | Không cần khi làm việc với số nguyên thủy |
| Mức sử dụng bộ nhớ | Thường cao hơn tùy cách cấp phát và chia sẻ đối tượng | Thường gọn hơn |

Chuyển từ `Stream<Integer>` sang `int[]`:

~~~java
import java.util.List;

List<Integer> counts = Arrays.asList(2, 4, 6);

int[] values = counts.stream()
        .mapToInt(Integer::intValue)
        .toArray();
~~~

Nếu dữ liệu có thể chứa `null`, bước `Integer::intValue` sẽ ném `NullPointerException` khi gặp phần tử đó. Cần xác định chính sách lọc hoặc thay thế `null` trước khi unboxing.

Chuyển từ `IntStream` sang `Integer[]`:

~~~java
Integer[] values = IntStream.range(1, 4)
        .boxed()
        .toArray(Integer[]::new);
// [1, 2, 3]
~~~

Tương tự, `LongStream.toArray()` trả về `long[]` và `DoubleStream.toArray()` trả về `double[]`.

> **Không thể** gọi `Stream<Integer>.toArray(int[]::new)` để nhận `int[]`: overload generic của `Stream<T>` dành cho mảng đối tượng (`A[]`), trong khi `int[]` là mảng nguyên thủy. Hãy chuyển sang `IntStream` bằng `mapToInt` rồi gọi `toArray()`.

## 7. `toArray` là terminal operation: thực thi pipeline một lần

`filter`, `map` và nhiều intermediate operation chỉ tạo mô tả cho pipeline. `toArray` **kích hoạt việc duyệt và vật hóa kết quả**:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of("lan", "minh", "an")
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase);

String[] result = pipeline.toArray(String[]::new); // [LAN, MINH]

// Sai: pipeline đã kết thúc, không thể dùng lại đối tượng Stream này.
long count = pipeline.count(); // IllegalStateException (thường gặp)
~~~

Nếu cần vừa mảng vừa một chỉ số khác như số phần tử, có thể lấy thông tin từ kết quả đã thu:

~~~java
String[] result = Stream.of("lan", "minh", "an")
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .toArray(String[]::new);

int count = result.length; // 2
~~~

Đối với nguồn collection có thể duyệt lại, cũng có thể tạo **một Stream mới** cho mỗi phép tính khi cần. Không được gọi nhiều terminal operation trên cùng một đối tượng Stream.

Một khác biệt với các phép tìm kiếm như `findFirst` hoặc đối sánh như `anyMatch` là `toArray` **phải thu toàn bộ kết quả đầu ra**, không tự dừng chỉ vì đã tìm thấy một phần tử thỏa điều kiện. Nếu cần vài phần tử đầu tiên, hãy thêm giới hạn trước `toArray`.

## 8. Thứ tự phần tử trong mảng kết quả

Với Stream có *encounter order* (thứ tự duyệt xác định), `toArray` tạo mảng các phần tử **theo thứ tự gặp được**:

~~~java
import java.util.Arrays;
import java.util.List;

List<Integer> numbers = Arrays.asList(5, 1, 4, 2);

Integer[] selected = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toArray(Integer[]::new);

System.out.println(Arrays.toString(selected)); // [4, 2]
~~~

Phép `filter` không tự sắp xếp dữ liệu. Nếu cần kết quả theo thứ tự tăng dần, sử dụng `sorted()` trước `toArray`:

~~~java
Integer[] ascending = numbers.stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toArray(Integer[]::new);

System.out.println(Arrays.toString(ascending)); // [2, 4]
~~~

Một Stream **song song** nhưng vẫn có encounter order cũng phải giữ thứ tự đó trong kết quả của `toArray`:

~~~java
Integer[] selected = numbers.parallelStream()
        .filter(n -> n > 1)
        .toArray(Integer[]::new);

// Theo encounter order của List: [5, 4, 2]
~~~

Ngược lại, nếu nguồn không có encounter order (ví dụ một số Stream tạo từ `HashSet`) hoặc pipeline cố ý gọi `unordered()`, **không có bảo đảm về thứ tự phần tử**. Tránh suy luận rằng `parallel()` luôn làm đảo thứ tự, hoặc `toArray` sẽ tự sắp xếp các phần tử.

Nếu thứ tự là một phần của hợp đồng API, hãy bảo đảm nguồn có thứ tự hoặc dùng phép `sorted` phù hợp với khóa nghiệp vụ.

## 9. Mảng rỗng, `null` và các dạng dữ liệu khác

### 9.1. Khi không có phần tử thỏa bộ lọc

~~~java
String[] empty = Stream.of("A", "B")
        .filter(text -> text.length() > 5)
        .toArray(String[]::new);

System.out.println(empty.length); // 0
~~~

Kết quả là **một mảng có độ dài 0**, không phải `null`. Caller có thể duyệt an toàn bằng vòng lặp hoặc `Arrays.stream(empty)` mà không phải kiểm tra xem bản thân mảng có tồn tại hay không.

### 9.2. Phần tử `null` có thể được giữ lại

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

String[] names = Stream.of("Lan", null, "Minh")
        .toArray(String[]::new);

System.out.println(Arrays.toString(names)); // [Lan, null, Minh]
~~~

`toArray` không loại `null`. Nếu downstream không chấp nhận phần tử `null`, cần xử lý có chủ đích:

~~~java
import java.util.Objects;

String[] nonNull = Stream.of("Lan", null, "Minh")
        .filter(Objects::nonNull)
        .toArray(String[]::new);
~~~

Lưu ý: nếu gọi `map(String::trim)` trước bước loại `null`, chương trình sẽ lỗi ngay trong phép `map`.

### 9.3. Mảng hai chiều từ dữ liệu lồng nhau

Có thể dùng `toArray` ở cả Stream bên trong và bên ngoài:

~~~java
import java.util.Arrays;
import java.util.List;

List<List<String>> groups = Arrays.asList(
        Arrays.asList("a", "b"),
        Arrays.asList("c")
);

String[][] matrix = groups.stream()
        .map(group -> group.stream()
                .map(String::toUpperCase)
                .toArray(String[]::new))
        .toArray(String[][]::new);

System.out.println(Arrays.deepToString(matrix)); // [[A, B], [C]]
~~~

Vì dùng `map` ở tầng ngoài, mỗi nhóm vẫn là một hàng riêng. Nếu thay bằng `flatMap`, các giá trị có thể được gộp thành một mảng một chiều; chọn cấu trúc dựa trên việc có cần giữ ranh giới nhóm hay không.

## 10. Phân biệt `Stream.toArray` và `Collection.toArray`

Java có nhiều API cùng tên `toArray` nhưng nhận đối số khác nhau:

~~~java
import java.util.Arrays;
import java.util.List;

List<String> names = Arrays.asList("Lan", "Minh");

// Chuyển trực tiếp từ Collection sang mảng (API Collection).
String[] fromCollection = names.toArray(new String[0]);

// Chuyển kết quả pipeline Stream sang mảng (API Stream).
String[] fromStream = names.stream()
        .filter(name -> name.length() > 3)
        .toArray(String[]::new);
~~~

Không thể áp dụng cú pháp `stream.toArray(new String[0])` cho `Stream<String>` vì overload của Stream nhận **`IntFunction<A[]>`**, không nhận một đối tượng mảng đã tạo sẵn. Còn `Collection.toArray(T[])` là overload nhận mảng của Collection.

Từ Java 11, `Collection` cũng có overload `toArray(IntFunction<T[]>)` nên có thể thấy `names.toArray(String[]::new)`; điều đó không làm hai API có cùng hợp đồng xử lý pipeline.

Nếu dữ liệu đã là collection và chỉ cần sao chép trực tiếp sang mảng, dùng API của collection có thể đơn giản hơn. Khi cần `filter`, `map`, `flatMap` hoặc các phép biến đổi khai báo trước khi lấy mảng, sử dụng `Stream.toArray`.

## 11. `toArray` hay `collect` / `toList`?

Cả `toArray` lẫn các terminal operation thu collection đều **vật hóa** dữ liệu đầu ra, nhưng kiểu dữ liệu nhận được khác nhau.

| Tiêu chí | `toArray(String[]::new)` | `collect(Collectors.toList())` | `Stream.toList()` (Java 16+) |
| --- | --- | --- | --- |
| Kết quả | Mảng `String[]` | `List<String>` | `List<String>` |
| Kích thước sau khi tạo | Độ dài cố định | Tùy implementation, thường có thể thay đổi khi dùng `Collectors.toList()` nhưng không được API bảo đảm kiểu collection cụ thể | Danh sách không sửa đổi được |
| Truy cập theo chỉ số | `array[i]` | `list.get(i)` | `list.get(i)` |
| Phù hợp với API yêu cầu mảng | Có | Cần chuyển đổi thêm | Cần chuyển đổi thêm |
| API từ Java | Java 8 | Java 8 | Java 16 |

**Chọn mảng** khi giao diện tích hợp yêu cầu mảng, cần thao tác trực tiếp với `int[]` / `long[]` / `double[]`, hoặc cần cấu trúc kết quả có độ dài cố định. **Chọn List** khi xử lý theo contract collection, cần các phương thức collection, hoặc muốn truyền dữ liệu theo kiểu `List<T>`.

Cả hai cách đều có chi phí lưu toàn bộ đầu ra. Một Stream vốn *lazy* sẽ mất ưu thế xử lý từng phần tử khi đã gom mọi kết quả vào một mảng lớn.

## 12. Giới hạn nguồn và chi phí bộ nhớ

Mảng Java có độ dài kiểu `int` và phải cấp phát bộ nhớ đủ chứa các phần tử hoặc tham chiếu tới chúng. Vì vậy, `toArray` không thích hợp để thu **nguồn vô hạn không được giới hạn**.

Ví dụ có thể kết thúc:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Integer[] firstFive = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toArray(Integer[]::new);

System.out.println(Arrays.toString(firstFive)); // [0, 1, 2, 3, 4]
~~~

Ví dụ nguy hiểm:

~~~java
// Không chạy mẫu này: Stream không có điểm kết thúc tự nhiên.
Object[] forever = Stream.generate(() -> "event")
        .toArray();
~~~

Pipeline trên cố thu mọi phần tử của nguồn không giới hạn. Nó sẽ không thể tạo mảng kết quả hữu hạn bình thường; chương trình có thể chạy mãi hoặc hết tài nguyên trước khi hoàn tất.

Những lưu ý quan trọng về chi phí:

- **Thời gian:** thông thường phải xử lý các phần tử đầu ra của pipeline, cùng chi phí của `filter`, `map`, `sorted` và các thao tác trước đó.
- **Bộ nhớ:** cần nơi giữ mảng kết quả; một số pipeline, nhất là khi dùng `sorted`, `distinct` hoặc xử lý song song, còn có thể cần bộ đệm trung gian.
- **Không biết trước kích thước:** nếu bộ lọc loại nhiều phần tử hoặc nguồn không báo kích thước, runtime có thể cần tích lũy và cấp phát trước khi tạo mảng cuối. Không nên xây logic dựa trên số lần generator được gọi.
- **Độ lớn dữ liệu:** `toArray` có thể ném `OutOfMemoryError` hoặc các lỗi giới hạn kích thước mảng khi nguồn lớn hơn khả năng biểu diễn/cấp phát. Đừng dùng `toArray` để gom toàn bộ tệp nhật ký hoặc dữ liệu không có giới hạn rõ ràng.
- **Song song:** `parallel()` không bảo đảm nhanh hơn. Thu một kết quả theo thứ tự có thể đòi hỏi chia lô và ghép lại; chỉ chọn xử lý song song khi công việc đủ lớn, các hàm độc lập và đã đo hiệu năng thực tế.
- **Nguồn I/O:** nếu Stream gắn với tài nguyên như `Files.lines`, phải quản lý đóng nguồn bằng `try-with-resources`. `toArray` không tự động thay thế việc đóng tài nguyên I/O.

Nếu chỉ cần kiểm tra một điều kiện, phép đối sánh như `anyMatch` có thể tránh tạo mảng; nếu chỉ cần vài phần tử đầu tiên, dùng `limit(n)` trước `toArray`. Nếu cần tổng hợp một con số, `count`, `sum`, `reduce` hoặc `collect` với collector phù hợp có thể tránh phải giữ mọi phần tử.

## 13. Trường hợp thực tế: lọc bản ghi trước khi gọi API cũ

Giả sử một thư viện cũ có phương thức:

~~~java
void submitUserIds(String[] ids);
~~~

Dữ liệu ứng dụng đang ở dạng `List<User>` với trường `active`. Ta cần gửi mã những người dùng đang hoạt động, giữ thứ tự đầu vào và không gửi mã rỗng.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class UserExportDemo {

    static class User {
        private final String id;
        private final boolean active;

        User(String id, boolean active) {
            this.id = id;
            this.active = active;
        }

        String getId() { return id; }
        boolean isActive() { return active; }
    }

    static void submitUserIds(String[] ids) {
        System.out.println(Arrays.toString(ids));
    }

    public static void main(String[] args) {
        List<User> users = Arrays.asList(
                new User("U-10", true),
                new User("U-20", false),
                new User(null, true),
                new User("U-30", true)
        );

        String[] ids = users.stream()
                .filter(User::isActive)
                .map(User::getId)
                .filter(Objects::nonNull)
                .filter(id -> !id.isEmpty())
                .toArray(String[]::new);

        submitUserIds(ids); // [U-10, U-30]
    }
}
~~~

Ở đây `toArray(String[]::new)` thể hiện rõ hợp đồng với API bên ngoài. Bộ lọc chạy **trước khi** tạo mảng nên không cần giữ bản ghi không phù hợp. Nguồn là `List` có encounter order, vì vậy mã `U-10` vẫn đứng trước `U-30`.

Nếu dữ liệu từ database lớn, không nên giả định rằng `users.stream()` là phép truy vấn phát trực tiếp từ database: ví dụ đang làm việc trên một `List<User>` đã có trong bộ nhớ. Khi xử lý lượng dữ liệu lớn, cân nhắc phân trang, giới hạn số ID hoặc thiết kế API nhận từng lô.

## 14. Bảng tra cứu nhanh khi gặp lỗi

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `ClassCastException: [Ljava.lang.Object; ...` | Ép kết quả `Stream.toArray()` từ `Object[]` sang `String[]` | Gọi `toArray(String[]::new)` ngay từ Stream. |
| `ArrayStoreException` | Generator tạo mảng có kiểu phần tử không chứa được một số giá trị | Đảm bảo kiểu mảng khớp các phần tử thực hoặc biến đổi từng phần tử trước khi thu. |
| `NullPointerException` khi chuyển `Integer` sang `int` | Unboxing một phần tử `null` trong `mapToInt` | Xử lý `null` trước khi unboxing. |
| Không biên dịch với `toArray(new String[0])` trên Stream | Nhầm overload của Collection với Stream | Dùng `toArray(String[]::new)`. |
| Không biên dịch với `toArray(int[]::new)` trên `Stream<Integer>` | Dạng generic của Stream không tạo mảng primitive | Dùng `mapToInt(...).toArray()`. |
| `IllegalStateException` khi gọi terminal operation tiếp theo | Tái sử dụng cùng đối tượng Stream đã chạy `toArray` | Tạo Stream mới từ nguồn có thể duyệt lại, hoặc dùng chính mảng đã thu. |
| Kết quả chiếm quá nhiều RAM | `toArray` thu hết dữ liệu và có thể có bộ đệm trung gian | Hạn chế đầu vào, thu theo lô hoặc dùng terminal operation tổng hợp. |
| Thứ tự đầu ra không đúng mong đợi | Nguồn không có encounter order hoặc thay đổi thứ tự pipeline | Xác định hợp đồng nguồn; nếu cần, dùng `sorted` theo khóa rõ ràng. |

## 15. Bài tập tự kiểm tra

**Bài 1.** Phân biệt kiểu mảng và kết quả:

~~~java
Object[] a = Stream.of("x", "y").toArray();
String[] b = Stream.of("x", "y").toArray(String[]::new);
int[] c = IntStream.of(1, 2).toArray();
~~~

**Đáp án:** `a` là `Object[]`, `b` là `String[]`, `c` là `int[]`. Nội dung `a` và `b` giống nhau nhưng kiểu runtime của hai mảng khác nhau.

**Bài 2.** Sửa đoạn mã sau để tạo `int[]`:

~~~java
List<Integer> values = Arrays.asList(3, 5, 7);
Integer[] result = values.stream().toArray(Integer[]::new);
~~~

**Đáp án:** Dùng `mapToInt` để chuyển từ Stream đối tượng sang IntStream:

~~~java
int[] result = values.stream()
        .mapToInt(Integer::intValue)
        .toArray();
~~~

**Bài 3.** Với `Stream.of("abc", "x", "de", "four")`, kết quả sau là gì?

~~~java
String[] result = Stream.of("abc", "x", "de", "four")
        .filter(s -> s.length() >= 3)
        .map(String::toUpperCase)
        .toArray(String[]::new);
~~~

**Đáp án:** Mảng `["ABC", "FOUR"]` vì `filter` chỉ giữ `"abc"` và `"four"`, còn `map` biến đổi chúng thành chữ hoa. `toArray` thu đúng các phần tử sau biến đổi, theo encounter order.

**Bài 4.** Vì sao đoạn này không hoàn tất bình thường?

~~~java
String[] result = Stream.generate(() -> "OK")
        .toArray(String[]::new);
~~~

**Đáp án:** `generate` tạo nguồn không giới hạn; `toArray` muốn thu hết luồng nên không có ranh giới kết thúc. Nếu chỉ cần 100 phần tử, thêm `limit(100)` trước `toArray(String[]::new)`.

**Bài 5.** `Stream.toArray(String[]::new)` có bảo đảm array generator chỉ được gọi một lần không?

**Đáp án:** Không. Generator có thể được gọi theo nhu cầu để tạo các mảng phục vụ phân đoạn hoặc ghép kết quả. Vì thế `String[]::new` là cách diễn đạt an toàn; không dùng generator để ghi nhận số lần duyệt hoặc cập nhật trạng thái chia sẻ.

## 16. Ghi nhớ

- `Stream.toArray()` trả về `Object[]`; không ép kiểu kết quả này thành mảng cụ thể bằng cast.
- `Stream.toArray(String[]::new)` hoặc `toArray(size -> new String[size])` tạo mảng có kiểu phù hợp; các phần tử vẫn phải tương thích với kiểu mảng được yêu cầu.
- `IntStream.toArray()`, `LongStream.toArray()`, `DoubleStream.toArray()` tạo `int[]`, `long[]`, `double[]`; muốn dùng chúng cần pipeline của primitive stream tương ứng.
- `toArray` là terminal operation, kích hoạt và kết thúc một pipeline, thu toàn bộ kết quả hữu hạn vào mảng; nó không có cơ chế tự dừng trên nguồn vô hạn.
- Giữ đúng hợp đồng về **kiểu dữ liệu**, **thứ tự**, **số lượng phần tử**, **vòng đời Stream** và **bộ nhớ** khi quyết định biến kết quả thành mảng.

**Ý chính:** Khi kết quả phải là mảng, chọn overload `toArray` theo **kiểu mảng cần nhận**, thay vì dựa vào kiểu phần tử suy đoán. Với Stream đối tượng, cách viết `toArray(MyType[]::new)` rõ ràng và an toàn; với Stream số nguyên thủy, dùng overload `toArray()` của `IntStream`, `LongStream` hoặc `DoubleStream`.
