# Hành vi trên nguồn rỗng và ngoại lệ ở thao tác kết thúc của Stream (Java 8+)

## 1. Hiểu đúng “Stream rỗng” và thao tác kết thúc

Một `Stream<T>` rỗng là luồng không có phần tử nào để xử lý. Trường hợp này xuất hiện khi nguồn ban đầu rỗng (`Collections.emptyList().stream()`, `Stream.empty()`), hoặc khi các thao tác trung gian như `filter` loại bỏ toàn bộ phần tử. Cả hai tình huống đều dẫn đến **cùng quy tắc kết quả** ở thao tác kết thúc (terminal operation).

Pipeline của Stream có dạng:

```text
Nguồn (Collection/array/...) → 0 hoặc nhiều intermediate operations → terminal operation
```

- `filter`, `map`, `sorted`... thường là thao tác trung gian, thực thi lười (lazy).
- `count`, `collect`, `reduce`, `findFirst`, `anyMatch`, `forEach`... là thao tác kết thúc: tạo ra giá trị/kết quả phụ hoặc kích hoạt việc xử lý pipeline.
- **Stream rỗng tự nó không phải lỗi.** Mỗi terminal operation có hợp đồng riêng: có thao tác trả `0`, có thao tác trả tập hợp rỗng, có thao tác trả `Optional.empty()` và có thao tác trả `true` dù không hề có phần tử.
- **Một Stream chỉ dành cho một chuỗi xử lý.** Sau khi đã kết thúc, hãy tạo Stream mới từ nguồn nếu muốn tính tiếp. Không tái sử dụng biến Stream đã được tiêu thụ.

Khác biệt cần giữ rõ: “không có phần tử”, “một phần tử có giá trị `null`” và “biến nguồn bằng `null`” là ba trạng thái khác nhau; chúng không có chung hành vi ngoại lệ.

## 2. Bảng hành vi khi không còn phần tử

Các kết quả sau áp dụng cho Stream tuần tự hoặc song song khi số phần tử thực sự bằng 0, trừ ghi chú riêng.

| Terminal operation | Kết quả với Stream rỗng | Ý nghĩa cần nhớ |
| --- | --- | --- |
| `count()` | `0L` | Đếm phần tử; không trả `Optional`. |
| `toArray()`, `toArray(String[]::new)` | Mảng độ dài 0 | Không chứa phần tử `null` tự sinh. |
| `collect(Collectors.toList())` | `List` rỗng | Không dựa vào kiểu triển khai hay khả năng sửa được của List. |
| `collect(Collectors.toSet())` | `Set` rỗng | Không tự giả định thứ tự. |
| `collect(Collectors.groupingBy(...))` | `Map` rỗng | Không sinh nhóm/khoá giả khi thiếu phần tử. |
| `collect(Collectors.joining(","))` | Chuỗi rỗng `""` | Với `joining(",", "[", "]")`, kết quả là `"[]"`. |
| `findFirst()`, `findAny()` | `Optional.empty()` | Không trả `null` hoặc ném lỗi chỉ vì nguồn rỗng. |
| `min(comparator)`, `max(comparator)` | `Optional.empty()` | Phải xử lý tình huống không có cực trị. |
| `reduce(BinaryOperator)` | `Optional.empty()` | Không có phần tử thì không có kết quả giảm. |
| `reduce(identity, accumulator)` | Chính `identity` | Ví dụ identity `7` thì kết quả là `7`. |
| `anyMatch(predicate)` | `false` | Không tồn tại phần tử thỏa mãn điều kiện. |
| `allMatch(predicate)` | `true` | Không có phần tử nào vi phạm điều kiện. |
| `noneMatch(predicate)` | `true` | Không có phần tử nào thỏa mãn điều kiện. |
| `forEach(action)`, `forEachOrdered(action)` | Không gọi `action` | Trả về `void`, không sinh phần tử hay thông báo mặc định. |
| `IntStream.empty().sum()` | `0` | Giá trị trung hòa của phép cộng. |
| `IntStream.empty().count()` | `0L` | Tương tự `Stream.count()`. |
| `IntStream.empty().min()/max()` | `OptionalInt.empty()` | Không có số nhỏ nhất/lớn nhất. |
| `IntStream.empty().average()` | `OptionalDouble.empty()` | Không thể suy ra trung bình từ 0 phần tử. |

Đặc biệt, `IntStream.empty().summaryStatistics()` vẫn tạo đối tượng thống kê với `count = 0`, `sum = 0`, `average = 0.0`, nhưng `min = Integer.MAX_VALUE` và `max = Integer.MIN_VALUE` là các giá trị khởi tạo. Vì vậy **hãy kiểm tra `getCount() > 0` trước khi sử dụng min/max của summary statistics**. Ngược lại, `IntStream.min()` và `max()` trả `OptionalInt`, thể hiện thiếu kết quả rõ hơn.

### Vì sao `allMatch` và `noneMatch` là `true`?

Các phép kiểm tra này tuân theo logic định lượng:

- `anyMatch(P)` hỏi: “Có **ít nhất một** phần tử thỏa P không?”. Tập rỗng: **không** → `false`.
- `allMatch(P)` hỏi: “Có phần tử **nào không thỏa** P không?”. Không có phản ví dụ → `true` (chân lý đúng một cách rỗng, *vacuous truth*).
- `noneMatch(P)` hỏi: “Có phần tử nào thỏa P không?”. Không có → `true`.

Trên Stream rỗng, cả ba thao tác **không gọi predicate**. Trong nghiệp vụ yêu cầu “phải có ít nhất một mục và mọi mục hợp lệ”, chỉ dùng `allMatch` là chưa đủ:

```java
List<String> codes = Collections.emptyList();
boolean valid = !codes.isEmpty()
        && codes.stream().allMatch(code -> code.length() >= 3);
// valid == false, đúng yêu cầu "có dữ liệu và mọi mục hợp lệ"
```

Đây là đoạn mã minh họa đặt trong phương thức có import `java.util.*`; kiểm tra kích thước trên `List` trước khi tạo Stream. Đừng gọi `count()` rồi `allMatch()` trên **cùng một đối tượng Stream**: terminal thứ nhất đã tiêu thụ nó.

## 3. Ví dụ Java 8 chạy được: tất cả kết quả trên nguồn rỗng

Lưu thành `EmptyTerminalDemo.java`:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class EmptyTerminalDemo {
    public static void main(String[] args) {
        List<String> source = Collections.emptyList();

        System.out.println("count = " + source.stream().count());
        System.out.println("collect = " + source.stream().collect(Collectors.toList()));
        System.out.println("array = " + Arrays.toString(source.stream().toArray(String[]::new)));
        System.out.println("findFirst = " + source.stream().findFirst());
        System.out.println("reduce no identity = "
                + Stream.<Integer>empty().reduce(Integer::sum));
        System.out.println("reduce identity = "
                + Stream.<Integer>empty().reduce(7, Integer::sum));
        System.out.println("min = " + IntStream.empty().min());
        System.out.println("sum = " + IntStream.empty().sum());
        System.out.println("average = " + IntStream.empty().average());
        System.out.println("anyMatch = "
                + source.stream().anyMatch(s -> s.length() >= 3));
        System.out.println("allMatch = "
                + source.stream().allMatch(s -> s.length() >= 3));
        System.out.println("noneMatch = "
                + source.stream().noneMatch(s -> s.length() >= 3));
        source.stream().forEach(System.out::println);
    }
}
```

Biên dịch và chạy (JDK 8 trở lên):

```bash
javac -encoding UTF-8 EmptyTerminalDemo.java
java EmptyTerminalDemo
```

Kết quả chuẩn:

```text
count = 0
collect = []
array = []
findFirst = Optional.empty
reduce no identity = Optional.empty
reduce identity = 7
min = OptionalInt.empty
sum = 0
average = OptionalDouble.empty
anyMatch = false
allMatch = true
noneMatch = true
```

Mỗi lần gọi `source.stream()` đều tạo một Stream mới từ cùng `List`; đây là cách hợp lệ để chạy nhiều terminal operation trên dữ liệu ban đầu. `forEach` không in thêm dòng vì không có phần tử.

Với Stream không rỗng nhưng bị lọc hết, kết quả vẫn như vậy. Ví dụ `Stream.of(1, 2, 3).filter(x -> x > 10).findFirst()` cho `Optional.empty()`.

## 4. Ngoại lệ xảy ra ở đâu?

Cần phân biệt **kết quả hợp lệ khi rỗng** với **lỗi do cách dùng kết quả, trạng thái Stream, phần tử hoặc lambda**:

| Tình huống | Ngoại lệ/hành vi | Giải thích và cách xử lý |
| --- | --- | --- |
| `Stream.empty().findFirst()` | Không lỗi; `Optional.empty()` | Đây là kết quả terminal hợp lệ. |
| Gọi `get()` trên `Optional.empty()` | `NoSuchElementException` | Lỗi xảy ra **khi lấy giá trị từ Optional**, không phải ở `findFirst`. Ưu tiên `orElse`, `orElseGet`, `ifPresent` hoặc `orElseThrow(supplier)` theo yêu cầu nghiệp vụ. |
| Gọi terminal lần hai trên cùng Stream đã tiêu thụ | Sử dụng Stream sai hợp đồng; thường `IllegalStateException` khi được phát hiện | Tạo Stream mới từ nguồn. API không bảo đảm mọi lần tái sử dụng sai đều được phát hiện. |
| Thao tác trên Stream đã `close()` | `IllegalStateException` | Không dùng tiếp Stream đóng; với Stream từ I/O, quản lý bằng try-with-resources. |
| `findFirst()/findAny()` chọn phần tử `null` | `NullPointerException` | `Optional` kết quả không biểu diễn một giá trị `null` được chọn. Lọc `null` trước, hoặc ngăn `null` xuất hiện trong nguồn. |
| `min()/max()` có phần tử `null` được chọn hoặc bộ so sánh không xử lý được phần tử | Có thể `NullPointerException` | Làm sạch phần tử và thiết kế `Comparator` phù hợp. Stream rỗng tự nó vẫn trả Optional rỗng. |
| `collect(Collectors.toMap(keyMapper, valueMapper))` gặp khóa trùng | `IllegalStateException` | Dùng overload có `mergeFunction` hoặc `groupingBy` khi nhiều giá trị có cùng khóa. |
| Lambda trong `map`, `filter`, `reduce`, `forEach`... tự ném lỗi | Ngoại lệ tương ứng, ví dụ `ArithmeticException` | Pipeline lazy có thể chỉ phát lộ lỗi khi terminal kích hoạt đoạn xử lý đó. Stream không tự đổi ngoại lệ thành kết quả rỗng. |
| Truyền tham số bắt buộc không được `null` (như predicate/comparator) | Thường `NullPointerException` | Kiểm tra tham số; đừng suy luận “nguồn rỗng nên callback sai sẽ được bỏ qua”. |

Một nguồn rỗng **không làm cho `Optional.get()` an toàn**. Ngược lại, ngay cả nguồn có phần tử vẫn có thể phát sinh ngoại lệ do khóa trùng, `null` hoặc mã trong lambda.

### Ví dụ Java 8 chạy được: quan sát ngoại lệ mà không phụ thuộc thông báo JDK

Lưu thành `TerminalFailureDemo.java`:

```java
import java.util.NoSuchElementException;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class TerminalFailureDemo {
    public static void main(String[] args) {
        try {
            Stream.<String>empty().findFirst().get();
        } catch (NoSuchElementException e) {
            System.out.println("NoSuchElementException: empty Optional");
        }

        Stream<Integer> numbers = Stream.of(1, 2, 3);
        numbers.count();
        try {
            numbers.findFirst();
        } catch (IllegalStateException e) {
            System.out.println("IllegalStateException: reused Stream");
        }

        try {
            Stream.of("a", "b")
                    .collect(Collectors.toMap(String::length, Function.identity()));
        } catch (IllegalStateException e) {
            System.out.println("IllegalStateException: duplicate map key");
        }

        try {
            Stream.of((String) null).findFirst();
        } catch (NullPointerException e) {
            System.out.println("NullPointerException: selected null");
        }

        try {
            IntStream.of(4, 0).map(x -> 10 / x).sum();
        } catch (ArithmeticException e) {
            System.out.println("ArithmeticException: division by zero");
        }
    }
}
```

```bash
javac -encoding UTF-8 TerminalFailureDemo.java
java TerminalFailureDemo
```

Kết quả (chỉ in tên ngoại lệ và ý nghĩa do chương trình tự định nghĩa, không in `e.getMessage()` vì thông báo JDK có thể khác nhau):

```text
NoSuchElementException: empty Optional
IllegalStateException: reused Stream
IllegalStateException: duplicate map key
NullPointerException: selected null
ArithmeticException: division by zero
```

Đọc từng trường hợp:
1. `findFirst` trả Optional rỗng đúng hợp đồng; chính `get` gây lỗi.
2. `count` là terminal đầu tiên; `findFirst` sau đó cố sử dụng lại Stream đã tiêu thụ.
3. `"a"` và `"b"` đều có độ dài `1`, nên `toMap(String::length, ...)` tạo khóa trùng.
4. `Stream.of((String) null)` có **một phần tử `null`**, không phải Stream rỗng; `findFirst` chọn phần tử đó và không thể đóng gói thành Optional có giá trị.
5. `map(x -> 10 / x)` được thiết lập trước, nhưng phép chia cho 0 xảy ra trong lúc `sum()` tiêu thụ pipeline.

Các ví dụ dùng Stream tuần tự và catch theo từng loại lỗi để đầu ra xác định; **không** nên biến cách catch rộng, bỏ qua lỗi thành giải pháp nghiệp vụ mặc định.

## 5. Cách xử lý kết quả rỗng đúng mục đích

### 5.1. Dùng `Optional` để diễn đạt “có thể không có kết quả”

`findFirst`, `findAny`, `min`, `max`, và `reduce` không có identity trả về `Optional<T>`. Chọn chính sách rõ ràng:

```java
List<String> names = Collections.emptyList();

// Có giá trị mặc định hợp lệ về nghiệp vụ:
String display = names.stream().findFirst().orElse("(không có)");

// Tạo giá trị mặc định khi thật sự cần tính toán:
String lazyDefault = names.stream().findFirst()
        .orElseGet(() -> "(không có)");

// Nếu dữ liệu là bắt buộc, ném lỗi với thông điệp có ý nghĩa:
String required = names.stream().findFirst()
        .orElseThrow(() -> new IllegalArgumentException("Danh sách tên bắt buộc có phần tử"));
```

Đây là các đoạn minh họa độc lập với ví dụ `main` phía trên; lệnh cuối **cố ý ném ngoại lệ** vì danh sách rỗng. `orElse(value)` đánh giá đối số ngay cả khi Optional có giá trị; `orElseGet(supplier)` chỉ gọi supplier khi rỗng. Không chọn mặc định `0`, chuỗi rỗng hoặc `-1` một cách máy móc nếu chúng có thể che khuất dữ liệu bị thiếu.

### 5.2. Chọn identity cho `reduce` đúng đại số và quy tắc nghiệp vụ

`Stream.<Integer>empty().reduce(0, Integer::sum)` trả `0`, vì `0` là phần tử trung hòa của phép cộng. `Stream.<Integer>empty().reduce(1, (a, b) -> a * b)` trả `1`, vì `1` là phần tử trung hòa của phép nhân. Nếu không có identity, bản overload nhận một `BinaryOperator` trả `Optional.empty()` khi không có phần tử.

Đối với `parallelStream`, hàm giảm phải tuân theo yêu cầu kết hợp (*associative*) và identity phải trung hòa. Ví dụ trừ hoặc chia số theo thứ tự bất kỳ không là cách giảm song song an toàn. Đừng chọn identity chỉ để ép hết trạng thái rỗng nếu đầu ra cần phân biệt “không có dữ liệu” với một kết quả số thực sự.

### 5.3. Phân biệt “không có dữ liệu” với “dữ liệu không hợp lệ”

Khi có yêu cầu tất cả phần tử hợp lệ **và** bắt buộc danh sách không rỗng, ghép `!list.isEmpty()` với `allMatch`. Khi tìm cực trị trên dữ liệu có thể có `null`, lọc `null` và dùng `OptionalInt`/`Optional`.

Lưu thành `SafeTerminalDemo.java`:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class SafeTerminalDemo {
    public static void main(String[] args) {
        List<Integer> data = Arrays.asList(null, -2, 0);
        OptionalInt maxPositive = data.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .filter(x -> x > 0)
                .max();
        System.out.println("max present = " + maxPositive.isPresent());
        System.out.println("max fallback = " + maxPositive.orElse(-1));

        List<String> codes = Collections.emptyList();
        boolean nonemptyAndValid = !codes.isEmpty()
                && codes.stream().allMatch(code -> code.length() >= 3);
        System.out.println("nonempty and valid = " + nonemptyAndValid);

        Map<Integer, String> byLength = Stream.of("a", "b")
                .collect(Collectors.toMap(
                        String::length,
                        Function.identity(),
                        (first, next) -> first));
        System.out.println("distinct keys = " + byLength.size());
    }
}
```

```bash
javac -encoding UTF-8 SafeTerminalDemo.java
java SafeTerminalDemo
```

```text
max present = false
max fallback = -1
nonempty and valid = false
distinct keys = 1
```

`-1` chỉ là giá trị dự phòng **minh họa** cho kết quả đã lọc `x > 0`; trong hệ thống thực tế, nếu cần bảo toàn sự khác biệt giữa thiếu dữ liệu và số âm hợp lệ, hãy giữ `OptionalInt` thay vì chèn sentinel. Overload `toMap` có hàm gộp giải quyết khóa trùng có chủ đích.

## 6. Những bẫy quan trọng khi chạy trên Java hiện nay

1. **Stream rỗng khác phần tử `null`.** `Stream.<String>empty().count()` là `0`; `Stream.of((String) null).count()` là `1`. Nếu gọi `findFirst()` trên trường hợp thứ hai, có thể nhận `NullPointerException` vì phần tử được chọn là `null`. Nếu chính biến `List` bằng `null`, gọi `list.stream()` gây lỗi **trước khi có Stream**. Dùng nguồn không null và lọc phần tử null khi cần.
2. **Không dùng side effect trong `map`/`peek` để dự đoán số lần gọi.** Terminal dạng ngắn mạch (`findFirst`, `anyMatch`...) có thể dừng sớm. Ngay cả `count()` trên nguồn có kích thước biết trước cũng có thể tính trực tiếp, bỏ qua việc duyệt và callback trung gian nếu không ảnh hưởng kết quả; tối ưu hóa này được tài liệu Java hiện hành cho phép. Muốn tác động phụ có chủ đích, đánh giá yêu cầu và chọn thao tác thích hợp; không lạm dụng Stream để thay thế vòng lặp.
3. **`findAny` không bảo đảm phần tử đầu; `forEach` trên Stream song song không bảo đảm thứ tự.** Nếu cần phần tử đầu theo encounter order, dùng `findFirst` với nguồn có thứ tự; nếu cần duy trì thứ tự khi xuất kết quả, cân nhắc `forEachOrdered`, hiểu chi phí thực thi.
4. **Không tái sử dụng Stream đã kết thúc hoặc đóng.** Với nguồn `List`, gọi `list.stream()` mỗi lần cần pipeline mới. Với nguồn I/O như `Files.lines(path)`, dùng `try (Stream<String> lines = Files.lines(path)) { ... }` để đóng tài nguyên sau terminal; stream đọc file có thể ném ngoại lệ I/O khi tạo/đọc nguồn theo hợp đồng API liên quan.
5. **Không giả định collector trả collection thay đổi được.** `Collectors.toList()` không cam kết kiểu hay tính sửa được; từ Java 16, `Stream.toList()` trả danh sách không sửa được. Hai API không đồng nghĩa về hợp đồng tính sửa được. Mẫu code chạy Java 8 trong bài dùng `Collectors.toList()`.
6. **API hiện đại xử lý nullable có điều kiện phiên bản.** Từ Java 9, `Stream.ofNullable(value)` tạo Stream rỗng khi `value == null`. Mã phải tương thích Java 8 có thể dùng `value == null ? Stream.empty() : Stream.of(value)`; không dùng `Stream.of((T) null)` rồi kỳ vọng nó rỗng.

## 7. Tự kiểm tra nhanh

**Câu 1.** `Stream.of(1, 2).filter(x -> x > 10).allMatch(x -> x > 0)` trả gì?  
**Đáp án:** `true`, vì `filter` loại hết phần tử; `allMatch` đúng một cách rỗng. Nếu nghiệp vụ cần ít nhất một phần tử, kiểm tra điều kiện tồn tại riêng.

**Câu 2.** `Stream.<Integer>empty().reduce(5, Integer::sum)` và `Stream.<Integer>empty().reduce(Integer::sum)` khác gì?  
**Đáp án:** Lần lượt trả `5` và `Optional.empty()`. Overload có identity cho ra identity khi không có phần tử.

**Câu 3.** `Stream.of("x", "y").collect(Collectors.toMap(String::length, Function.identity()))` có thể lỗi không?  
**Đáp án:** Có, `IllegalStateException` vì hai phần tử cùng tạo khóa `1`. Thêm merge function hoặc đổi cách nhóm dữ liệu.

**Câu 4.** Một thao tác trung gian tạo phép chia cho 0 nhưng terminal `findFirst()` lấy được phần tử đứng trước lỗi: liệu lần nào cũng có ngoại lệ?  
**Đáp án:** Không; terminal dạng ngắn mạch có thể không duyệt phần tử sau. Tuy nhiên không nên dựa vào side effect, ngoại lệ hay thứ tự duyệt để làm logic nghiệp vụ; đường đi thực tế phụ thuộc pipeline và chế độ thực thi.

## 8. Ghi nhớ khi thiết kế API dùng Stream

- Dữ liệu rỗng là kết quả bình thường: dùng `Optional`/`OptionalInt` khi không có kết quả là trạng thái cần diễn đạt; chỉ dùng identity/default khi đã định nghĩa ý nghĩa nghiệp vụ.
- `allMatch() == true` không chứng minh có phần tử.
- Ngoại lệ thường bắt nguồn từ `Optional.get()`, tái sử dụng Stream, dữ liệu `null`, khóa trùng hoặc callback; xác định đúng nơi phát sinh để sửa nguyên nhân.
- Chỉ quyết định lỗi hoặc mặc định sau khi biết ứng dụng mong đợi dữ liệu **bắt buộc** hay **tùy chọn**. Không nuốt mọi ngoại lệ và coi đó là Stream rỗng.

### Tài liệu API chính thức để đối chiếu hợp đồng hiện hành

- [Java Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): terminal operations, empty/match/short-circuit, stream single-use và lưu ý tối ưu hóa `count`.
- [Java Collectors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): `toList`, `groupingBy`, `joining`, `toMap` và xử lý khóa trùng.
- [Java Optional](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): xử lý kết quả vắng mặt, `orElse`/`orElseGet`/`orElseThrow`.
- [Java IntStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html): `sum`, `min`, `max`, `average`, `summaryStatistics`.
