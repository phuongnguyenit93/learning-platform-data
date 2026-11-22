# Thiết kế chuỗi xử lý có kiểu và điều kiện biên rõ ràng trong Java

## 1. Tại sao cần thiết kế *pipeline* có kiểu?

Trong ứng dụng Java, một yêu cầu tưởng chừng đơn giản như “nhận dữ liệu người dùng, làm sạch, kiểm tra, tính toán rồi trả kết quả” thường gồm nhiều bước. Nếu nhồi toàn bộ vào một phương thức với nhiều điều kiện lồng nhau, ta dễ gặp lỗi về kiểu dữ liệu, `null`, dữ liệu rỗng, giá trị sát ngưỡng và ngoại lệ.

Một **chuỗi xử lý có kiểu** (typed processing pipeline) chia yêu cầu thành các giai đoạn có hợp đồng rõ ràng:

~~~text
Input thô
   |
   v
Chuẩn hóa          String? -> Optional<String>
   |
   v
Chuyển kiểu         String  -> Optional<Integer>
   |
   v
Kiểm tra miền       Integer -> Optional<Integer>
   |
   v
Biến đổi            Integer -> Integer
   |
   v
Kết quả             Optional<Integer>
~~~

Ký hiệu `String?` ở đây có nghĩa **đầu vào có thể null** để dễ đọc sơ đồ, **không phải cú pháp kiểu nullable của Java**. `Optional<T>` đại diện cho việc một giá trị có thể không tồn tại, nhưng không tự cho biết *vì sao* nó không tồn tại.

Bài học nằm trong nhóm **hàm chuẩn** của Java: tận dụng `Function<T,R>`, `Predicate<T>`, `UnaryOperator<T>`, `Supplier<T>`, `Consumer<T>`, cùng `Optional`, `Stream` và `IntStream` khi phù hợp. Đây đều là các ý tưởng và API tiếp tục có giá trị trên JDK hiện đại.

Mục tiêu thiết kế không phải dùng nhiều lambda nhất có thể. Mục tiêu là:

1. Mỗi bước có **kiểu vào/ra** và trách nhiệm rõ ràng.
2. Phân biệt **lọc điều kiện**, **biến đổi**, **xử lý vắng mặt** và **thực hiện tác động phụ**.
3. Định nghĩa trước các **điều kiện biên** như `null`, trống, sai định dạng, overflow, bằng ngưỡng.
4. Không vô tình làm mất thông tin lỗi hoặc phụ thuộc vào thứ tự thực thi ngẫu nhiên.
5. Dễ kiểm thử từng bước và toàn bộ quy trình.

## 2. Chọn đúng functional interface cho từng giai đoạn

| Hành vi | Functional interface | Phương thức SAM | Đặc trưng |
| --- | --- | --- | --- |
| Biến đổi một giá trị | `Function<T,R>` | `R apply(T value)` | Đầu vào T, đầu ra R |
| Kiểm tra điều kiện | `Predicate<T>` | `boolean test(T value)` | Trả true/false |
| Biến đổi cùng một kiểu | `UnaryOperator<T>` | `T apply(T value)` | Trường hợp đặc biệt của Function |
| Nhận một giá trị và thực hiện hành động | `Consumer<T>` | `void accept(T value)` | Không trả dữ liệu |
| Tạo/cung cấp dữ liệu khi được gọi | `Supplier<T>` | `T get()` | Không nhận tham số |
| Biến đổi số nguyên thủy | `IntUnaryOperator` | `int applyAsInt(int)` | Không boxing Integer |
| Kiểm tra số nguyên thủy | `IntPredicate` | `boolean test(int)` | Không boxing Integer |
| Gộp hai đầu vào | `BiFunction<T,U,R>` | `R apply(T,U)` | Hai tham số, một kết quả |
| Điều kiện hai đầu vào | `BiPredicate<T,U>` | `boolean test(T,U)` | Hai tham số, kết quả boolean |

Ví dụ đơn giản (các đoạn trong phần này là **mảnh mã minh họa**, đặt bên trong phương thức với import phù hợp):

~~~java
Function<String, String> normalize = String::trim;
Function<String, Integer> length = String::length;
Predicate<String> nonEmpty = s -> !s.isEmpty();
UnaryOperator<String> uppercase = String::toUpperCase;
Consumer<String> print = System.out::println;
Supplier<String> defaultName = () -> "Anonymous";
~~~

`normalize` biến `String` thành `String`, `length` biến `String` thành `Integer` (có boxing từ `int`), `nonEmpty` chỉ quyết định đúng/sai. `Consumer` không thay thế `Function` trong bước cần trả giá trị; `Supplier` không nhận đầu vào.

**Hợp đồng kiểu mạnh** giúp trình biên dịch phát hiện việc nối hai giai đoạn không tương thích, chẳng hạn nối một hàm trả `Integer` với hàm chỉ nhận `LocalDate`.

## 3. Nối `Function` đúng kiểu bằng `andThen` và `compose`

Với hai hàm:

~~~text
f : A -> B
g : B -> C
~~~

`f.andThen(g)` tạo hàm `A -> C`, chạy `f` trước rồi `g`. Còn `g.compose(f)` cũng tạo `A -> C`, chạy `f` trước rồi `g`:

~~~java
Function<String, String> trim = String::trim;
Function<String, Integer> length = String::length;

Function<String, Integer> first = trim.andThen(length);
Function<String, Integer> second = length.compose(trim);
~~~

Hai lời nối trên đều hợp kiểu và cùng tính **độ dài chuỗi sau khi trim**. Lưu ý thứ tự viết trong `compose`: `length.compose(trim)` nghĩa là **trim trước**, không phải length trước.

Trường hợp **cố ý không biên dịch**:

~~~java
Function<String, Integer> length = String::length;
Function<java.time.LocalDate, String> yearText =
        date -> date.getYear() + "";

Function<String, String> invalid = length.andThen(yearText);
// Lỗi: length trả Integer, nhưng yearText đòi LocalDate.
~~~

Đây là mảnh mã minh họa lỗi. Không nên cố “chữa” bằng ép kiểu không an toàn. Hãy xem lại hợp đồng hoặc thêm bước chuyển dữ liệu có nghĩa rõ ràng.

### `andThen` có biến đổi dữ liệu ngay không?

Không. Tạo `Function<String,Integer> composed = trim.andThen(length);` mới chỉ **xây hành vi**. Phép biến đổi xảy ra khi gọi `composed.apply(input)`. Đây là điểm phân biệt giữa xây pipeline và chạy pipeline.

### Thêm điều kiện cuối chuỗi

`Function<T,R>` có thể nối tiếp một `Function<R,Boolean>`, nhưng điều kiện thực sự nên có kiểu `Predicate<R>` khi dùng với API lọc:

~~~java
Function<String, Integer> trimmedLength = trim.andThen(length);
Predicate<Integer> atLeastFour = n -> n >= 4;

boolean accepted = atLeastFour.test(trimmedLength.apply(" Java "));
~~~

Tách biến đổi và điều kiện cho phép tái sử dụng mỗi phần, kiểm thử kiểu độc lập và dùng `Predicate` với `Stream.filter`.

## 4. Ví dụ chạy đầy đủ 1: từ các hàm chuẩn đến chuỗi có kiểu

Tạo tệp **TypedPipelineDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.UnaryOperator;
import java.util.stream.Collectors;

public class TypedPipelineDemo {
    public static void main(String[] args) {
        UnaryOperator<String> trim = String::trim;
        Function<String, Integer> length = String::length;
        Predicate<Integer> atLeastFour = value -> value >= 4;

        Function<String, Integer> trimmedLength =
                trim.andThen(length);
        Function<String, Integer> lengthByCompose =
                length.compose(trim);

        System.out.println(trimmedLength.apply("  Java  "));
        System.out.println(lengthByCompose.apply("  ab  "));
        System.out.println(
                atLeastFour.test(trimmedLength.apply("  ab  "))
        );

        Predicate<String> usable =
                text -> text != null && !text.trim().isEmpty();

        List<String> raw = Arrays.asList(
                " Java ", null, "  ", " go ", " Lambda ");
        List<String> accepted = raw.stream()
                .filter(usable)
                .map(trim)
                .filter(text -> text.length() >= 4)
                .collect(Collectors.toList());

        System.out.println(accepted);
        System.out.println(raw.size());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ (đoạn chương trình dùng API có từ Java 8):

~~~bash
javac TypedPipelineDemo.java
java TypedPipelineDemo
~~~

**Stdout chính xác:**

~~~text
4
2
false
[Java, Lambda]
5
~~~

Giải thích:

1. `trim.andThen(length)` nhận `String`, trả `Integer`: `"  Java  "` được trim thành `"Java"`, độ dài là 4.
2. `length.compose(trim)` cũng trim trước, nên `"  ab  "` có độ dài 2.
3. `atLeastFour` kiểm tra `2 >= 4`, trả `false`.
4. `filter(usable)` loại `null` và chuỗi rỗng sau khi trim **trước** khi chạy `map(trim)`. Nhờ vậy `trim` không nhận null.
5. `map(trim)` giữ kiểu phần tử là `String` nhưng chuẩn hóa nội dung; `filter(text -> text.length() >= 4)` tiếp tục giữ những chuỗi đủ dài.
6. `raw` vẫn có 5 phần tử, vì pipeline tạo danh sách kết quả mới thay vì sửa danh sách nguồn.

Đặt tên các giai đoạn giúp người đọc kiểm tra hợp đồng: tại điểm `map(trim)`, dữ liệu đã được lọc null; tại điểm kiểm tra `length()`, dữ liệu đã được chuẩn hóa.

## 5. Ranh giới của từng API: `filter`, `map`, `flatMap` và terminal operation

Trong Stream:

- `filter(Predicate<? super T>)`: kiểm tra điều kiện và giữ/bỏ phần tử; **không thay kiểu phần tử**.
- `map(Function<? super T,? extends R>)`: biến đổi một phần tử T thành một giá trị R; **có thể thay kiểu**.
- `flatMap(...)`: mỗi phần tử có thể tạo ra một luồng kết quả; flatten các luồng con thành một luồng kết quả.
- `collect`, `toList`, `count`, `findFirst`, `forEach`... là terminal operations; tùy mục tiêu, chúng thu thập hoặc tiêu thụ kết quả.

Ví dụ biểu đồ kiểu:

~~~text
Stream<String>
  .filter(Predicate<String>)
         -> Stream<String>
  .map(Function<String,Integer>)
         -> Stream<Integer>
  .filter(Predicate<Integer>)
         -> Stream<Integer>
  .mapToInt(Integer::intValue)
         -> IntStream
  .sum() -> int
~~~

Khi đọc chuỗi từ trái sang phải, hãy hỏi **đầu ra của bước này có chính là đầu vào được bước sau chấp nhận không?**

### `map` hay `flatMap` với kết quả có thể thiếu?

Nếu hàm `parse(String)` trả về `Optional<Integer>`:

~~~java
Stream<String> source = java.util.stream.Stream.of("1", "2");
Stream<Optional<Integer>> nested = source.map(MyClass::parse);
~~~

Đây là **mảnh mã minh họa** (cần định nghĩa `MyClass.parse`). `map` ở đây tạo `Stream<Optional<Integer>>`, không tự bỏ các `Optional.empty()`.

Với JDK 9+ có thể viết:

~~~java
Stream<Integer> values = nested.flatMap(Optional::stream);
~~~

`Optional::stream` đưa `Optional.of(v)` thành luồng 1 phần tử và `Optional.empty()` thành luồng rỗng. Nếu cần hỗ trợ chính xác JDK 8, có thể dùng một `flatMap` trả `Stream.of(v)` hoặc `Stream.empty()` theo `isPresent`; không có `Optional.stream()` trong JDK 8. Trong dự án mới dùng JDK 17+, `Optional::stream` là API được hỗ trợ và diễn đạt rất rõ ý nghĩa.

### Pipeline Stream có đặc tính lazy

Các bước `filter`, `map`, `flatMap` là **intermediate operations**. Chúng thường thực thi khi có terminal operation. Một số terminal operations có thể dừng sớm (`findFirst`, `anyMatch`); Stream song song còn có thể thay đổi thứ tự thực thi callback.

Vì vậy không được xây logic nghiệp vụ dựa trên số lần `Predicate.test`, `Function.apply` được gọi, hoặc dựa trên side effect của `peek`. Hãy diễn đạt mục tiêu bằng các phép biến đổi và một kết quả cuối rõ ràng.

## 6. Điều kiện biên là một phần của hợp đồng, không phải phần sửa lỗi về sau

Trước khi viết pipeline, xác định rõ chính sách cho các nhóm đầu vào sau:

| Tình huống | Câu hỏi bắt buộc | Ví dụ hợp đồng |
| --- | --- | --- |
| `null` | Thiếu dữ liệu có được chấp nhận không? | Từ chối với lỗi `MISSING` hoặc trả kết quả vắng mặt |
| Chuỗi rỗng `""` | Được dùng làm giá trị thật hay coi là thiếu? | Từ chối với lỗi `BLANK` |
| Chỉ chứa ký tự trắng | Trim/strip rồi mới kiểm tra hay giữ nguyên? | `"   "` thành rỗng sau chuẩn hóa |
| Sai định dạng | Cho phép dấu `+`, dấu `-`, dấu phẩy, dấu chấm? | Chỉ chấp nhận định dạng số nguyên thập phân do `Integer.parseInt` hiểu |
| Giá trị nhỏ hơn ngưỡng | Ngưỡng có bao gồm đầu mút không? | `value >= 0` |
| Giá trị lớn hơn ngưỡng | Giới hạn trên là `<` hay `<=`? | `value <= 100` |
| Số vượt giới hạn của kiểu | Cần thông báo gì khi overflow? | `Integer.parseInt` báo `NumberFormatException` |
| Danh sách rỗng | Trả danh sách rỗng, giá trị mặc định, hay lỗi? | Trả danh sách rỗng, không gọi mapper |
| Trùng dữ liệu | Giữ thứ tự và các phần tử trùng hay khử trùng? | Giữ nguyên trừ khi có yêu cầu `distinct()` |
| Dữ liệu bị sửa đồng thời | Có snapshot, immutability hay đồng bộ hóa không? | Dùng snapshot nếu cần kết quả nhất quán |

**Quan trọng:** dùng `value > 0` hay `value >= 0` không phải khác biệt hình thức. Đây là khác biệt nghiệp vụ cần được chốt trước khi coding. Với miền `0..100` bao gồm đầu mút, cả `0` lẫn `100` phải hợp lệ; `-1` và `101` phải không hợp lệ.

### `trim()` và `strip()`

`String.trim()` có từ Java rất lâu và vẫn dùng được, nhưng cách nhận diện khoảng trắng dựa trên ký tự có mã nhỏ hơn hoặc bằng U+0020. `String.strip()` có từ Java 11 và dựa trên `Character.isWhitespace`. Hai phương thức không hoàn toàn giống nhau với các ký tự Unicode; muốn chấp nhận “khoảng trắng” theo ngôn ngữ/nghiệp vụ cụ thể phải định nghĩa và kiểm thử.

Ví dụ ở phần tiếp theo dành cho **JDK 17+**, dùng `strip()` để thể hiện chủ ý chuẩn hóa chuỗi hiện đại. Không suy ra `strip()` xử lý mọi ký tự Unicode trông giống dấu cách theo cách người dùng mong muốn.

## 7. Ví dụ chạy đầy đủ 2: pipeline có Optional và kiểm tra giới hạn

Giả sử ứng dụng nhận một chuỗi, cần:

1. Từ chối `null`, chuỗi trống hoặc chỉ có khoảng trắng.
2. Chuyển thành **số nguyên thập phân**.
3. Chỉ giữ số trong miền **0 đến 100, bao gồm hai đầu mút**.
4. Nhân đôi kết quả hợp lệ.
5. Trả kết quả vắng mặt khi bước nào đó không hợp lệ.

`Optional` phù hợp khi người gọi chỉ cần biết “có giá trị hay không”; nếu cần phân biệt lý do bị từ chối, ta sẽ dùng một kiểu kết quả có lỗi rõ ràng ở phần sau.

Tạo tệp **BoundaryPipelineDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class BoundaryPipelineDemo {
    static Optional<String> normalize(String raw) {
        return Optional.ofNullable(raw)
                .map(String::strip)
                .filter(text -> !text.isEmpty());
    }

    static Optional<Integer> parseInt(String text) {
        try {
            return Optional.of(Integer.parseInt(text));
        } catch (NumberFormatException invalidInteger) {
            return Optional.empty();
        }
    }

    static Optional<Integer> inRange(Integer value) {
        return value >= 0 && value <= 100
                ? Optional.of(value)
                : Optional.empty();
    }

    static Optional<Integer> process(String raw) {
        return normalize(raw)
                .flatMap(BoundaryPipelineDemo::parseInt)
                .flatMap(BoundaryPipelineDemo::inRange)
                .map(value -> value * 2);
    }

    public static void main(String[] args) {
        List<String> raw = Arrays.asList(
                " 42 ", "", " 9 ", "oops", null,
                "120", " 0 ", "-5", "100", "2147483648"
        );

        List<Integer> accepted = raw.stream()
                .map(BoundaryPipelineDemo::process)
                .flatMap(Optional::stream)
                .collect(Collectors.toList());

        System.out.println(accepted);
        System.out.println(process(null).isPresent());
        System.out.println(process("  ").isPresent());
        System.out.println(process("101").isPresent());
        System.out.println(process("100").orElse(-1));
        System.out.println(process(" +0 ").orElse(-1));
        System.out.println(process("001").orElse(-1));
        System.out.println(process("1.5").isPresent());
    }
}
~~~

Biên dịch/chạy bằng **JDK 17+** (`String.strip` cần Java 11+, `Optional.stream` cần Java 9+):

~~~bash
javac BoundaryPipelineDemo.java
java BoundaryPipelineDemo
~~~

**Stdout chính xác:**

~~~text
[84, 18, 0, 200]
false
false
false
200
0
2
false
~~~

Giải thích theo từng bước:

- `normalize(null)` trả `Optional.empty()`; `normalize("  ")` cũng rỗng sau `strip` và `filter`. Các giai đoạn sau **không chạy** với giá trị vắng mặt.
- `parseInt("oops")` trả Optional rỗng vì bắt `NumberFormatException`. Chuỗi `"2147483648"` vượt miền của `int` cũng tạo `NumberFormatException`.
- `inRange` chấp nhận `0` và `100` (giới hạn **bao gồm**), loại `-5` và `120`.
- Sau cùng, `42 -> 84`, `9 -> 18`, `0 -> 0`, `100 -> 200`. `flatMap(Optional::stream)` lấy riêng các kết quả tồn tại và giữ thứ tự gặp của Stream tuần tự.
- `Integer.parseInt("+0")` trả 0; `parseInt("001")` trả 1; sau khi nhân đôi, kết quả tương ứng là 0 và 2.
- `Integer.parseInt("1.5")` không nhận chuỗi số thập phân có dấu chấm; kết quả là Optional rỗng theo hợp đồng đã chọn.

**Tại sao dùng `flatMap` thay vì `map` liên tục trên Optional?** `normalize` trả `Optional<String>`, trong khi `parseInt` trả `Optional<Integer>`. Nếu viết `normalize(raw).map(BoundaryPipelineDemo::parseInt)` thì nhận `Optional<Optional<Integer>>`. `flatMap` tránh lớp Optional lồng nhau và truyền trạng thái “vắng mặt” xuyên suốt chuỗi.

### Ranh giới cần nhớ khi dùng Optional

- `Optional.ofNullable(null)` -> empty; `Optional.of(null)` -> `NullPointerException`.
- `map` dùng hàm biến đổi; nếu mapper trả `null`, Optional kết quả là empty.
- `flatMap` yêu cầu mapper trả một **Optional không null**; trả chính `null` sẽ gây lỗi.
- `filter` giữ giá trị khi predicate đúng, trả empty khi sai; với Optional rỗng, predicate không chạy.
- `get()` trên Optional rỗng ném `NoSuchElementException`. Ưu tiên `orElse`, `orElseGet`, `orElseThrow` hoặc xử lý theo hợp đồng.
- `orElse(defaultValue)` đánh giá đối số trước khi gọi; `orElseGet(supplier)` chỉ gọi supplier khi rỗng. Với fallback tốn kém hoặc có side effect, chọn đúng phương thức.
- Optional chỉ mô tả **có/không có giá trị**, không tự thể hiện nhiều loại lỗi. Đừng “làm sạch” mọi exception thành `Optional.empty()` khi caller cần biết nguyên nhân.

## 8. Khi Optional không đủ: trả kết quả có kiểu lỗi rõ ràng

Trong API nghiệp vụ, việc coi `null`, chuỗi trống, sai định dạng và ngoài ngưỡng là cùng một trạng thái “không có giá trị” có thể làm mất thông tin cần thiết. Để làm rõ **điều kiện biên**, ta có thể trả một kết quả mang mã lỗi.

Trên JDK 17, `record` phù hợp để biểu diễn dữ liệu kết quả gọn và bất biến theo các trường. Ví dụ sau dùng `record` như một kiểu dữ liệu nội bộ, không yêu cầu thư viện bên ngoài.

Tạo tệp **ExplicitOutcomeDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;

public class ExplicitOutcomeDemo {
    record Outcome(Integer doubled, String errorCode) {
        boolean isSuccess() {
            return errorCode == null;
        }
    }

    static Outcome evaluate(String raw) {
        if (raw == null) {
            return new Outcome(null, "MISSING");
        }

        String text = raw.strip();
        if (text.isEmpty()) {
            return new Outcome(null, "BLANK");
        }

        final int parsed;
        try {
            parsed = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            return new Outcome(null, "INVALID_INTEGER");
        }

        if (parsed < 0 || parsed > 100) {
            return new Outcome(null, "OUT_OF_RANGE");
        }
        return new Outcome(parsed * 2, null);
    }

    public static void main(String[] args) {
        List<String> inputs =
                Arrays.asList(null, " ", "oops", "-1", "100", "25");

        for (String input : inputs) {
            Outcome result = evaluate(input);
            if (result.isSuccess()) {
                System.out.println("OK:" + result.doubled());
            } else {
                System.out.println("ERROR:" + result.errorCode());
            }
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ (record chuẩn hóa từ Java 16, `strip` từ Java 11):

~~~bash
javac ExplicitOutcomeDemo.java
java ExplicitOutcomeDemo
~~~

Stdout:

~~~text
ERROR:MISSING
ERROR:BLANK
ERROR:INVALID_INTEGER
ERROR:OUT_OF_RANGE
OK:200
OK:50
~~~

Ví dụ này diễn đạt riêng từng **trường hợp biên**. Người gọi không phải đoán ý nghĩa của Optional rỗng. Đây là bước tiến về hợp đồng API khi cần hiển thị thông báo lỗi, ghi thống kê hoặc phân biệt dữ liệu sai với trường hợp vắng mặt hợp lệ.

Trong một hệ thống lớn, nên tránh mô hình luôn dùng `null` để đánh dấu một trong hai field của `Outcome`: có thể dùng kiểu kết quả phân biệt hai nhánh thành công/thất bại (chẳng hạn sealed interface và record trên JDK 17+) để tránh trạng thái không hợp lệ như cả `doubled` và `errorCode` cùng có giá trị. Ở ví dụ ngắn này, factory `evaluate` là nơi đảm bảo chỉ tạo hai dạng hợp lệ.

**Không bắt tất cả `RuntimeException` để trả “INVALID_INPUT”.** Chỉ bắt ngoại lệ đúng với lỗi dữ liệu mình chủ động phân loại; những lỗi lập trình như `NullPointerException` ngoài dự kiến cần được phát hiện và xử lý khác với nhập sai số.

## 9. Chọn cách tổ hợp nào khi lỗi có ý nghĩa?

Có hai cách diễn đạt pipeline phổ biến:

**A. Pipeline theo *vắng mặt*:**

~~~text
String -> Optional<String>
       -> Optional<Integer>
       -> Optional<Integer>
       -> Optional<Integer>
~~~

Phù hợp với các hoạt động chọn lọc, tìm kiếm, kiểm tra tùy chọn, hoặc khi caller chỉ cần giá trị hợp lệ cuối cùng.

**B. Pipeline theo *kết quả có lỗi*:**

~~~text
String -> Result<Integer, ErrorCode>
~~~

Phù hợp khi phải phân biệt `MISSING`, `INVALID_INTEGER`, `OUT_OF_RANGE`, xung đột nghiệp vụ, và đưa ra hành động khắc phục. Java không có sẵn một kiểu `Result<T,E>` chuẩn trong `java.util.function`; có thể thiết kế kiểu riêng phù hợp, sử dụng record/sealed type hoặc thư viện đã được chấp thuận trong dự án.

Một quy tắc thực tế: **đừng để việc muốn viết nhiều `map` đẹp mắt quyết định hình dạng dữ liệu lỗi**. Hãy chọn hợp đồng lỗi trước, rồi chọn cách tổ hợp giai đoạn tương ứng.

## 10. Kiểu generic và tính tái sử dụng của bước xử lý

Khi viết một utility cho danh sách:

~~~java
static <T, R> List<R> transform(
        List<T> input, Function<? super T, ? extends R> mapper) {
    return input.stream()
            .map(mapper)
            .collect(java.util.stream.Collectors.toList());
}
~~~

Đây là **mảnh mã minh họa đặt trong một lớp**. Tham số generic `T` là kiểu phần tử đầu vào, `R` là kiểu đầu ra. Wildcard `? super T` cho phép mapper nhận T hoặc kiểu cha; `? extends R` cho phép trả R hoặc kiểu con. Cách khai báo này giúp API dùng được với nhiều kiểu mà không phải ép kiểu bằng tay.

Nhưng một API generic không tự làm mọi biến đổi an toàn. Đầu vào phải phù hợp hợp đồng, mapper không được giả định dữ liệu không null nếu danh sách có null, và cách trả lỗi cần được xác định. Nếu mapper có thể trả null, cần quyết định **giữ null**, **loại null**, hay **báo lỗi** thay vì để hành vi bất ngờ lan tới giai đoạn kế tiếp.

### Tránh kiểu quá rộng

Các kiểu như `Function<Object,Object>`, `List<Object>` hoặc ép kiểu `(T)` tùy tiện làm trình biên dịch mất khả năng kiểm tra giai đoạn. Hãy giữ kiểu thực `Function<String,Integer>`, `Predicate<Integer>`, `List<Integer>` càng lâu càng tốt. Việc suy luận kiểu của lambda và method reference dựa trên *target type*; khai báo kiểu rõ ràng giúp thông báo lỗi biên dịch hữu ích hơn.

Khi thao tác dữ liệu số lớn, cân nhắc `IntStream`, `IntPredicate`, `IntUnaryOperator` để giảm boxing/unboxing. Tuy nhiên, ưu tiên hợp đồng đúng trước rồi tối ưu hóa dựa trên đo đạc.

## 11. Những nguyên tắc thiết kế giúp pipeline dễ bảo trì

### 11.1. Một giai đoạn, một trách nhiệm

Nên tách `normalize`, `parse`, `inRange`, `transform`. Điều đó giúp viết unit test riêng: kiểm tra chuẩn hóa Unicode, kiểm tra số nguyên, kiểm tra hai đầu mút, kiểm tra overflow. Một lambda dài vừa sửa dữ liệu, vừa gọi database, vừa bắt lỗi rất khó kiểm thử.

### 11.2. Ưu tiên bước biến đổi thuần, hạn chế side effect

Một `Function` không bắt buộc thuần về mặt ngôn ngữ, nhưng trong pipeline nó nên tránh sửa trạng thái ngoài. `Stream.filter`, `map` và terminal operations có thể phối hợp lười và short-circuit; callback side effect có thể chạy số lần khác dự đoán. Với Stream song song, dữ liệu mutable còn có nguy cơ data race.

Dùng `Consumer` tại **ranh giới thực hiện hành động có chủ ý**, ví dụ ghi kết quả sau khi tính toán, thay vì dùng nó giả dạng giai đoạn trả dữ liệu. `peek` phù hợp nhất với chẩn đoán có kiểm soát, không phải nơi triển khai quy tắc nghiệp vụ bắt buộc.

### 11.3. Không lạm dụng `Optional`

`Optional` rất hữu ích cho giá trị **có thể thiếu** khi trả về từ phương thức. Không nên mặc định đổi mọi field/entity thành `Optional`, hoặc dùng Optional để thay thế toàn bộ ngoại lệ, lỗi validation hay collection rỗng. Nếu một phương thức trả danh sách kết quả, **danh sách rỗng** thường là hợp đồng rõ hơn `Optional<List<T>>`, trừ khi nghiệp vụ thật sự cần phân biệt “không có danh sách” với “danh sách rỗng”.

### 11.4. Giữ rõ ranh giới mutable/immutable

`collect(Collectors.toList())` không hứa hẹn về loại List cụ thể hoặc khả năng sửa đổi theo đặc tả. `Stream.toList()` (Java 16+) trả danh sách không cho sửa đổi. Nếu cần một `ArrayList` có thể thêm/xóa, dùng:

~~~java
List<String> editable = source.stream()
        .map(String::trim)
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new
        ));
~~~

Đây là mã minh họa cần khai báo `source`. Phân biệt kết quả có thể sửa đổi với bất biến là một **điều kiện biên của API**, không chỉ là chi tiết triển khai.

### 11.5. Xử lý lỗi tại nơi có đủ ngữ cảnh

`Function.apply`, `Predicate.test`, `Consumer.accept`, `Supplier.get` không khai báo checked exception. Nếu một bước cần thực hiện I/O và có thể ném `IOException`, phải xử lý, chuyển thành kiểu kết quả lỗi hoặc thiết kế functional interface có `throws` phù hợp. Không lặng lẽ nuốt ngoại lệ khiến pipeline trả tập kết quả thiếu mà không ai biết lý do.

### 11.6. Không biến null thành hợp đồng ngầm

Java không tự kiểm tra null cho `Function<T,R>`: mapper có thể nhận null và ném NPE. Nếu null là dữ liệu được cho phép, từng stage cần định nghĩa cách xử lý; nếu null bị cấm, kiểm tra ở **ranh giới hệ thống** bằng `Objects.requireNonNull` hoặc bước xác thực đầu vào. Ranh giới rõ ràng tốt hơn chuỗi `filter(Objects::nonNull)` đặt tùy tiện chỉ để hết lỗi.

## 12. Ma trận test cho điều kiện biên

Với hàm `BoundaryPipelineDemo.process` có miền `0..100` và phép biến đổi nhân hai, bộ test tối thiểu nên có:

| Input | Nhóm | Kết quả mong đợi |
| --- | --- | --- |
| `null` | Vắng mặt | Empty |
| `""` | Rỗng | Empty |
| `"  "` | Chỉ trắng | Empty |
| `"abc"` | Sai định dạng | Empty |
| `"1.5"` | Không phải số nguyên | Empty |
| `"-1"` | Ngay dưới cận dưới | Empty |
| `"0"` | Đúng cận dưới | `0` |
| `"1"` | Trong miền | `2` |
| `"99"` | Trong miền | `198` |
| `"100"` | Đúng cận trên | `200` |
| `"101"` | Ngay trên cận trên | Empty |
| `"2147483648"` | Overflow của `int` | Empty |
| `" +0 "` | Dấu +, có khoảng trắng | `0` |
| `"001"` | Dẫn số 0 | `2` |

Nên kiểm thử thêm: input gồm ký tự Unicode trắng mà `strip` nhận/không nhận, tập đầu vào rỗng, dữ liệu có `null` lẫn số hợp lệ, phần tử lặp, tính ổn định thứ tự kết quả của Stream tuần tự, và lỗi từ các dịch vụ bên ngoài nếu pipeline tích hợp I/O.

### Hai chiến lược test bổ sung

1. **Test từng hàm:** `normalize(null)`, `parseInt("oops")`, `inRange(0)`, `inRange(100)`, `inRange(101)`. Lỗi được định vị tại bước hẹp.
2. **Test end-to-end:** đưa danh sách input hỗn hợp qua `process`, so sánh danh sách kết quả có thứ tự và kiểm tra dữ liệu gốc không bị sửa.

Với quy tắc tổng quát, có thể dùng property-based testing để kiểm tra bất biến như “mọi kết quả hiện diện đều là số chẵn trong miền `0..200`”, nhưng test biên cụ thể vẫn rất cần thiết.

## 13. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt `map(String::trim)` trước khi kiểm tra null | Có thể NPE | Kiểm tra null, hoặc dùng `Optional.ofNullable` |
| Nối `Function<A,B>` với `Function<C,D>` dù B không tương thích C | Lỗi biên dịch hoặc phải ép kiểu nguy hiểm | Thiết kế kiểu trung gian đúng |
| Dùng `map` khi hàm trả `Optional<R>` rồi tưởng đã unwrap | Tạo `Optional<Optional<R>>` hoặc `Stream<Optional<R>>` | Dùng `flatMap` phù hợp |
| Viết `x > 0 && x < 100` khi yêu cầu bao gồm cận | Loại nhầm 0,100 | Dùng `>=`, `<=` và test hai đầu mút |
| Bắt mọi ngoại lệ thành `Optional.empty()` | Che giấu lỗi hệ thống | Phân loại đúng lỗi nhập liệu, dùng outcome có mã lỗi |
| Dùng `Optional.get()` không kiểm tra | Có thể `NoSuchElementException` | `orElse`, `orElseGet`, `orElseThrow` theo hợp đồng |
| Trông chờ side effect trong `Stream.peek` | Không đảm bảo điểm thực thi cho nghiệp vụ | Dời tác động ra biên, dùng terminal operation có chủ đích |
| Giả định `Collectors.toList()` luôn tạo `ArrayList` sửa được | Phụ thuộc triển khai | Dùng `toCollection(ArrayList::new)` nếu cần |
| Dùng `trim` và `strip` như hoàn toàn tương đương | Sai quy tắc khoảng trắng Unicode | Xác định chuẩn hóa đầu vào và test |
| Để API trả `null` hoặc empty không được giải thích | Caller không biết nguyên nhân | Định nghĩa rõ hợp đồng kết quả/lỗi |
| Bỏ qua giới hạn số khi parse | `NumberFormatException` ở dữ liệu lớn | Bắt đúng lỗi, kiểm tra miền trước biến đổi |
| Trộn xử lý I/O, ghi log, mutation vào predicate/map | Khó test, dễ lỗi khi short-circuit/song song | Tách lớp biên và hàm biến đổi thuần |

## 14. Bài tập thực hành

**Bài 1 — Vẽ luồng kiểu.** Cho `Function<String,Integer> count = String::length`, `Predicate<Integer> large = n -> n >= 5`, `Function<Integer,String> label = n -> "L=" + n`. Vẽ `String -> Integer -> boolean` cho nhánh kiểm tra và `String -> Integer -> String` cho nhánh biến đổi; giải thích tại sao `count.andThen(label)` hợp lệ, còn `count.andThen(String::trim)` không hợp lệ.

**Bài 2 — Sửa pipeline có null.** Một danh sách có `null`, `""`, `"  Java  "`. Hãy chọn thứ tự `filter`, `map(String::trim)`, `filter` để loại null, bỏ chuỗi rỗng và giữ chuỗi dài ít nhất 4 sau trim. Test kết quả.

**Bài 3 — Thêm điều kiện biên.** Đổi miền số từ `0..100` thành `10..90` nhưng vẫn bao gồm hai đầu mút. Viết các test `9`, `10`, `90`, `91`; giải thích kết quả sau phép nhân đôi.

**Bài 4 — Báo lỗi thay vì empty.** Sửa `ExplicitOutcomeDemo` để trả mã `TOO_SMALL` khi giá trị âm và `TOO_LARGE` khi vượt 100, vẫn giữ `MISSING`, `BLANK`, `INVALID_INTEGER`. Viết test cho tất cả các nhánh.

**Bài 5 — So sánh `map`/`flatMap`.** Viết hàm `parse(String)` trả `Optional<Integer>` và truyền nó qua `Stream<String>`. Xác định kiểu kết quả của `map(parse)` và `flatMap(Optional::stream)`. Nêu phiên bản JDK tối thiểu cho `Optional.stream`.

**Bài 6 — Thiết kế API thực tế.** Một hệ thống nhận danh sách email người dùng: có `null`, khoảng trắng, giá trị trùng, và địa chỉ không hợp lệ. Hãy định nghĩa hợp đồng cho chuẩn hóa, validation, duplicate handling, thứ tự kết quả và báo lỗi. Không chỉ viết regex rồi coi mọi lỗi là `false`; hãy đưa ra quy tắc rõ ràng, có thể kiểm thử, và nêu trách nhiệm của bước xác thực thực tế.

## 15. Checklist triển khai

Trước khi giao một pipeline vào sử dụng, tự hỏi:

- **Kiểu:** Input, output của từng giai đoạn đã rõ chưa? Có generic wildcard đúng phạm vi chưa?
- **Thiếu dữ liệu:** `null`, chuỗi rỗng, Optional rỗng và collection rỗng được xử lý thế nào?
- **Biên:** Có bao gồm ngưỡng? Có xử lý overflow, dữ liệu sai định dạng, ký tự trắng đặc biệt?
- **Lỗi:** Caller cần biết “không có kết quả” hay cần phân biệt nguyên nhân? Ngoại lệ checked/unchecked được xử lý ra sao?
- **Thực thi:** Pipeline lazy hay eager? Có short-circuit hoặc dùng parallel stream? Có phụ thuộc side effect không?
- **Kết quả:** Danh sách trả về có sửa được không? Có giữ thứ tự/trùng lặp không?
- **Test:** Đã có happy path, sát hai cận, null/blank, sai định dạng, overflow và danh sách rỗng chưa?

## 16. Tóm tắt

Thiết kế **chuỗi xử lý có kiểu và điều kiện biên rõ ràng** không phải chỉ là nối nhiều lambda. Đó là việc biến yêu cầu nghiệp vụ thành chuỗi hợp đồng tường minh: `Function` cho biến đổi, `Predicate` cho điều kiện, `Optional` cho vắng mặt, kiểu kết quả có lỗi khi cần giải thích thất bại, và `Stream` cho việc xử lý tập dữ liệu.

`andThen`/`compose` giúp nối các `Function` có kiểu đầu ra/đầu vào tương thích. `map` và `flatMap` giải quyết các tầng kết quả khác nhau; `filter` chỉ giữ/bỏ phần tử. Ranh giới `null`, blank, số âm, giá trị bằng ngưỡng, overflow và checked exception phải được định nghĩa và kiểm thử từ đầu.

Hãy ưu tiên **hợp đồng đúng, hàm nhỏ, kiểu rõ, lỗi không bị che giấu và test biên có hệ thống**. Các nguyên tắc này là nền tảng bền vững của lập trình Java hiện đại.
