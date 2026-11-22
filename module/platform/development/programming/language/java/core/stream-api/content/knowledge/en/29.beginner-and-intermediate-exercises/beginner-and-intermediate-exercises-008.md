# Xử lý nguồn rỗng, null và kết quả tìm kiếm vắng mặt

## 1. Mục tiêu của chuỗi bài tập

Trong chương **Bài tập nền tảng và trung cấp** của **JAVA_STREAM_API**, ta đã có thể dùng pipeline khai báo gồm `filter`, `map`, `reduce`, `collect` và những terminal operation tìm kiếm. Tuy nhiên, dữ liệu thực tế không phải lúc nào cũng đầy đủ: có nguồn rỗng, tham chiếu danh sách bằng `null`, phần tử bên trong danh sách bằng `null`, trường của đối tượng bị thiếu hoặc không có phần tử nào thỏa điều kiện tìm kiếm.

Bài này hướng tới kỹ năng **viết pipeline đúng ngữ nghĩa với dữ liệu vắng mặt**, thay vì chỉ làm code không ném ngoại lệ. Sau khi thực hành, người học có thể:

- Phân biệt **Stream rỗng**, **nguồn tham chiếu `null`**, **phần tử `null`** và **`Optional.empty()`**.
- Chọn chính sách phù hợp: bỏ dữ liệu thiếu, trả giá trị mặc định, giữ trạng thái không có kết quả hoặc báo lỗi.
- Dùng `Objects::nonNull`, `Stream.ofNullable`, `Optional.ofNullable` và `Optional.stream` đúng phạm vi.
- Xử lý `findFirst`, `findAny`, `min`, `max`, `average`, `reduce` khi nguồn rỗng.
- Tránh lỗi do `Collectors.toUnmodifiableList`, `toMap` và `groupingBy` khi gặp `null`.
- Thiết kế chương trình nhỏ có thể kiểm thử với dữ liệu đầu vào không hoàn chỉnh.

Các lời giải sử dụng **Java 17+**. `Stream.ofNullable` và `Optional.stream` có từ Java 9; `Stream.toList()` có từ Java 16. Phần lớn ví dụ dùng stream tuần tự để bảo đảm dễ hiểu, sau đó mới giải thích các điểm cần lưu ý khi chạy song song.

### Bốn tình huống không được xem là một

| Tình huống | Ví dụ | Ý nghĩa | Rủi ro điển hình |
| --- | --- | --- | --- |
| **Nguồn rỗng** | `List.<String>of().stream()` | Có nguồn hợp lệ, nhưng không có phần tử | `findFirst()` trả `Optional.empty()` |
| **Tham chiếu nguồn null** | `List<String> names = null` | Chưa có đối tượng nguồn | `names.stream()` ném `NullPointerException` |
| **Phần tử null** | `Arrays.asList("A", null)` | Có nguồn, một phần tử không có giá trị | `map(String::trim)` có thể ném NPE |
| **Kết quả tìm kiếm vắng mặt** | `stream.filter(...).findFirst()` | Không tìm thấy phần tử phù hợp | `Optional.get()` ném `NoSuchElementException` nếu rỗng |

Sơ đồ:

~~~text
Đầu vào
  ├─ source == null ──────────► báo lỗi HOẶC quy ước nguồn rỗng
  └─ source != null
       │
       ▼
     stream()
       │
       ├─ phần tử null? ──────► filter / ofNullable / báo lỗi
       └─ phần tử hợp lệ
             │
             ▼
        filter / map / ...
             │
             ├─ không còn phần tử ─────► Stream rỗng
             │                              │
             │                              ▼
             │                        Optional.empty()
             │
             └─ có phần tử ───────────► Optional chứa giá trị
                                            │
                                orElse / orElseGet / orElseThrow
~~~

**Quy ước trình bày:** Với mỗi bài tập có các phần **Yêu cầu**, **Lời giải**, **Giải thích và trường hợp biên**. Một số snippet ngắn dùng biến đã được định nghĩa ở ngay trước đó; các chương trình có `public class` là ví dụ độc lập và có thể lưu thành file trùng tên lớp để biên dịch bằng `javac`.

## 2. Kiến thức nền: terminal operation trên Stream rỗng

Trước khi giải bài tập, hãy dự đoán các kết quả sau:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class EmptyStreamBasics {
    public static void main(String[] args) {
        Stream<String> empty = Stream.empty();
        System.out.println(empty.count()); // 0

        System.out.println(List.<String>of().stream().toList()); // []
        System.out.println(List.<String>of().stream().findFirst()); // Optional.empty
        System.out.println(List.<String>of().stream().reduce(String::concat));
        // Optional.empty

        System.out.println(IntStream.empty().sum()); // 0
        System.out.println(IntStream.empty().average()); // OptionalDouble.empty
    }
}
~~~

Không được dùng lại một Stream sau khi đã chạy terminal operation. Các lời gọi trên tạo Stream mới từ nguồn ở từng biểu thức.

| Terminal operation | Nguồn rỗng trả gì? | Ghi chú |
| --- | --- | --- |
| `count()` | `0L` | Không cần Optional |
| `toList()` | List rỗng | List từ `Stream.toList()` không sửa đổi được |
| `collect(Collectors.toList())` | List rỗng | Không cam kết kiểu List/mutability |
| `findFirst()` hoặc `findAny()` | `Optional.empty()` | Đừng gọi `get()` trực tiếp |
| `min(comparator)` / `max(comparator)` | `Optional.empty()` | Không có phần tử để so sánh |
| `reduce(operator)` | `Optional.empty()` | Dạng không identity |
| `reduce(identity, op)` | `identity` | Phải chọn identity hợp lệ |
| `IntStream.sum()` | `0` | Có thể tràn khi tổng dữ liệu lớn |
| `IntStream.average()` | `OptionalDouble.empty()` | Không nhầm với trung bình bằng 0 |
| `anyMatch(predicate)` | `false` | Không có phần tử thỏa |
| `allMatch(predicate)` | `true` | Đúng theo logic mệnh đề trên tập rỗng |
| `noneMatch(predicate)` | `true` | Không có phần tử vi phạm |

`allMatch` và `noneMatch` trả `true` trên nguồn rỗng không phải lỗi. Chúng biểu diễn quy tắc *đúng một cách rỗng* (*vacuous truth*). Nếu nghiệp vụ yêu cầu **phải có ít nhất một phần tử** mới được chấp nhận, hãy kiểm tra điều kiện tồn tại một cách tường minh.

## 3. Bài tập 1 — Nguồn List bị null và nguồn rỗng

**Mức độ:** Nền tảng.

**Yêu cầu:** Viết hàm `normalize(List<String> source)` trả về một danh sách tên đã bỏ khoảng trắng thừa ở hai đầu. Quy tắc của bài tập: nếu tham chiếu nguồn là `null`, xem như **không có dữ liệu** và trả danh sách rỗng. Nếu List hợp lệ nhưng rỗng, cũng trả danh sách rỗng. Bài này giả định **các phần tử chưa bị null**; bài 2 sẽ xử lý trường hợp đó.

**Lời giải:**

~~~java
import java.util.List;
import java.util.Optional;

public class NullListExercise {
    static List<String> normalize(List<String> source) {
        return Optional.ofNullable(source)
            .orElseGet(List::of)
            .stream()
            .map(String::strip)
            .toList();
    }

    public static void main(String[] args) {
        System.out.println(normalize(null)); // []
        System.out.println(normalize(List.of())); // []
        System.out.println(normalize(List.of(" An ", " Bình ")));
        // [An, Bình]
    }
}
~~~

**Giải thích:**

- `Optional.ofNullable(source)` trả `Optional.empty()` khi nguồn bằng `null`.
- `orElseGet(List::of)` tạo List rỗng khi không có nguồn.
- `stream()` duyệt danh sách hợp lệ.
- `map(String::strip)` làm sạch từng tên.
- `toList()` trả List không sửa đổi được và giữ encounter order của List đầu vào.

**Trường hợp biên:** nếu một phần tử của danh sách bằng `null`, `String::strip` vẫn ném `NullPointerException`. Không được hiểu rằng kiểm tra `source != null` tự xử lý cả những phần tử null.

### Khi nào không nên coi nguồn null như nguồn rỗng?

Trong ứng dụng thực, `null` có thể mang nghĩa **lỗi tích hợp, thiếu dữ liệu bắt buộc hoặc chưa tải dữ liệu**. Nếu đó là hợp đồng, nên báo lỗi thay vì âm thầm trả danh sách rỗng:

~~~java
import java.util.List;
import java.util.Objects;

static List<String> normalizeStrict(List<String> source) {
    Objects.requireNonNull(source, "source không được null");
    return source.stream().map(String::strip).toList();
}
~~~

Đây là một **chính sách khác**, không phải câu trả lời duy nhất cho mọi bài toán. Hãy quyết định dựa trên hợp đồng đầu vào.

## 4. Bài tập 2 — Lọc phần tử null trước khi gọi method

**Mức độ:** Nền tảng.

**Yêu cầu:** Danh sách nhận từ hệ thống cũ có thể chứa phần tử `null`. Hãy làm sạch, loại tên null và tên trắng/rỗng, rồi chuyển thành chữ hoa để hiển thị. Giữ thứ tự ban đầu.

**Lời giải:**

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class NullableElementsExercise {
    public static void main(String[] args) {
        List<String> raw = Arrays.asList(
            " an ", null, "", "   ", " Bình ", "chi"
        );

        List<String> cleaned = raw.stream()
            .filter(Objects::nonNull)
            .map(String::strip)
            .filter(name -> !name.isEmpty())
            .map(name -> name.toUpperCase(Locale.ROOT))
            .toList();

        System.out.println(cleaned); // [AN, BÌNH, CHI]
    }
}
~~~

**Giải thích và trường hợp biên:**

- `Arrays.asList(...)` có thể chứa `null`; `List.of(...)` **không cho phép** phần tử null.
- `filter(Objects::nonNull)` phải đứng **trước** `String::strip`.
- `String::strip` bỏ khoảng trắng đầu/cuối theo định nghĩa Unicode của Java.
- `filter(name -> !name.isEmpty())` bỏ các chuỗi rỗng sau khi strip.
- `Locale.ROOT` tránh phụ thuộc vào locale mặc định của máy khi chuẩn hóa chữ hoa.
- `toList()` giữ thứ tự phần tử còn lại nếu nguồn có encounter order.

**Lỗi dễ gặp:**

~~~java
// Sai thứ tự: String::strip nhận null và ném NPE.
// raw.stream().map(String::strip).filter(Objects::nonNull).toList();
~~~

Việc `filter` xuất hiện sau `map` là **quá muộn** nếu method trong `map` đã bị gọi với null.

## 5. Bài tập 3 — Phân biệt Stream.ofNullable và Stream.of

**Mức độ:** Nền tảng.

**Yêu cầu:** Với một `String` có thể bằng `null`, tạo Stream chứa **0 hoặc 1 phần tử không null** để tiếp tục xử lý. So sánh với `Stream.of(...)`.

**Lời giải:**

~~~java
import java.util.List;
import java.util.stream.Stream;

public class OfNullableExercise {
    public static void main(String[] args) {
        String missing = null;
        String present = "Java";

        List<String> a = Stream.ofNullable(missing).toList();
        List<String> b = Stream.ofNullable(present).toList();

        System.out.println(a); // []
        System.out.println(b); // [Java]

        // Có một phần tử null (không phải Stream rỗng):
        List<String> c = Stream.of((String) null).toList();
        System.out.println(c); // [null]

        System.out.println(Stream.ofNullable(null).count()); // 0
        System.out.println(Stream.of((String) null).count()); // 1
    }
}
~~~

`Stream.ofNullable(x)` (Java 9+) tạo Stream rỗng khi `x == null`; nếu khác null, Stream chứa đúng một phần tử. `Stream.of((String) null)` lại tạo Stream có **một phần tử null**. Cast `(String) null` trong ví dụ giúp thể hiện ý định sử dụng overload một phần tử, tránh sự mơ hồ với overload varargs trong các cách viết khác.

### Khi một trường object có thể null

~~~java
import java.util.List;
import java.util.stream.Stream;

record Customer(String id, String email) {}

List<Customer> customers = List.of(
    new Customer("C1", "a@example.com"),
    new Customer("C2", null),
    new Customer("C3", "b@example.com")
);

List<String> emails = customers.stream()
    .flatMap(c -> Stream.ofNullable(c.email()))
    .toList();

System.out.println(emails); // [a@example.com, b@example.com]
~~~

`flatMap` làm phẳng các Stream 0/1 phần tử thành một Stream email duy nhất. Giải pháp tương đương, thường ngắn hơn khi trường đã được ánh xạ sang `String`:

~~~java
List<String> emails = customers.stream()
    .map(Customer::email)
    .filter(java.util.Objects::nonNull)
    .toList();
~~~

**Phân biệt:** `Stream.ofNullable` xử lý **một giá trị nullable**, không tự bảo vệ khi chính danh sách nguồn hoặc chính phần tử `Customer` bị null. Nếu có cả hai, cần kết hợp với bài 1 và bài 2.

## 6. Bài tập 4 — Tìm phần tử đầu tiên và xử lý Optional.empty

**Mức độ:** Nền tảng.

**Yêu cầu:** Viết hàm lấy tên đầu tiên có độ dài ít nhất 4 ký tự. Nếu không tìm thấy, trả chuỗi `"KHONG_CO"`; nếu danh sách chứa phần tử null, bỏ qua phần tử đó.

**Lời giải:**

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class FindFirstExercise {
    static String firstLongName(List<String> names) {
        Objects.requireNonNull(names, "names");

        return names.stream()
            .filter(Objects::nonNull)
            .filter(name -> name.length() >= 4)
            .findFirst()
            .orElse("KHONG_CO");
    }

    public static void main(String[] args) {
        System.out.println(firstLongName(
            Arrays.asList(null, "An", "Bình", "Châu")
        )); // Bình

        System.out.println(firstLongName(
            Arrays.asList(null, "An", "Vy")
        )); // KHONG_CO

        System.out.println(firstLongName(List.of())); // KHONG_CO
    }
}
~~~

Ở đây `findFirst()` trả `Optional<String>`, bởi một Stream sau lọc có thể không còn phần tử nào. `orElse(...)` biến Optional thành giá trị `String` theo chính sách đề bài.

### Bẫy quan trọng: findFirst có tự bỏ qua null không?

**Không.** `findFirst()` và `findAny()` có thể ném `NullPointerException` nếu phần tử được chọn là null. Không xem `Optional.empty()` như cách Stream tự mã hóa một phần tử null.

~~~java
import java.util.Arrays;

// Có thể ném NPE: phần tử đầu của Stream là null.
// Arrays.<String>asList(null, "A").stream().findFirst();

// Tránh điều đó nếu quy tắc nghiệp vụ là bỏ null:
var first = Arrays.<String>asList(null, "A")
    .stream()
    .filter(java.util.Objects::nonNull)
    .findFirst();

System.out.println(first); // Optional[A]
~~~

Bài tập này chọn chính sách **lọc null** trước tìm kiếm. Trong bài toán cần phát hiện dữ liệu bẩn, thay bằng kiểm tra/báo lỗi có chủ đích, không tự động bỏ qua.

## 7. Bài tập 5 — orElse và orElseGet khi giá trị dự phòng tốn kém

**Mức độ:** Nền tảng → Trung cấp.

**Yêu cầu:** Sau `findFirst`, chương trình có thể phải tải giá trị mặc định từ nguồn khác. Hãy làm sao để **chỉ tải giá trị dự phòng khi không tìm thấy**.

**Lời giải:**

~~~java
import java.util.List;
import java.util.Optional;

public class LazyFallbackExercise {
    static String loadFallback() {
        System.out.println("Đang tải giá trị dự phòng");
        return "KHACH_MAC_DINH";
    }

    public static void main(String[] args) {
        Optional<String> found = List.of("An", "Bình")
            .stream()
            .filter(name -> name.startsWith("B"))
            .findFirst();

        String eager = found.orElse(loadFallback());
        System.out.println("orElse: " + eager);

        String lazy = found.orElseGet(
            LazyFallbackExercise::loadFallback
        );
        System.out.println("orElseGet: " + lazy);
    }
}
~~~

Kết quả:

~~~text
Đang tải giá trị dự phòng
orElse: Bình
orElseGet: Bình
~~~

**Giải thích:** `orElse(loadFallback())` tính đối số trước lời gọi, nên `loadFallback()` vẫn chạy ngay cả khi Optional có giá trị. `orElseGet(supplier)` chỉ gọi thân Supplier nếu Optional rỗng.

Trường hợp không tìm thấy:

~~~java
String value = List.of("An", "Vy")
    .stream()
    .filter(name -> name.startsWith("B"))
    .findFirst()
    .orElseGet(LazyFallbackExercise::loadFallback);

// In log tải dự phòng, value == "KHACH_MAC_DINH".
~~~

**Chính sách:** Nếu fallback chỉ là một hằng số như `"KHONG_CO"`, `orElse` đơn giản hơn. Nếu fallback cần tính toán, tạo object lớn hoặc thực hiện I/O, `orElseGet` thường phù hợp. Nó không tự xử lý lỗi mạng, transaction hay retry bên trong fallback.

## 8. Bài tập 6 — Thiếu kết quả là lỗi nghiệp vụ: orElseThrow

**Mức độ:** Trung cấp.

**Yêu cầu:** Danh sách mã giao dịch chứa các mã hợp lệ. Một giao dịch phải được tìm thấy theo ID bắt buộc; nếu thiếu, hãy báo lỗi thay vì tạo giá trị giả.

**Lời giải:**

~~~java
import java.util.List;
import java.util.Objects;

public class RequiredTransactionExercise {
    record Transaction(String id, long amount) {}

    static Transaction requireById(
        List<Transaction> transactions,
        String id
    ) {
        Objects.requireNonNull(transactions, "transactions");
        Objects.requireNonNull(id, "id");

        return transactions.stream()
            .filter(Objects::nonNull)
            .filter(t -> id.equals(t.id()))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy giao dịch: " + id
            ));
    }

    public static void main(String[] args) {
        List<Transaction> transactions = List.of(
            new Transaction("T01", 100L),
            new Transaction("T02", 200L)
        );

        System.out.println(
            requireById(transactions, "T02").amount()
        ); // 200

        // requireById(transactions, "T99");
        // Ném IllegalArgumentException với thông báo rõ ràng.
    }
}
~~~

Sử dụng `id.equals(t.id())` để tránh gọi method trên `t.id()` nếu trường đó null. Một giao dịch có `id == null` sẽ không khớp ID yêu cầu đã được kiểm tra khác null.

### orElseThrow và get khác nhau thế nào?

`Optional.get()` trên Optional rỗng ném `NoSuchElementException`, nhưng khó diễn đạt **vì sao đây là lỗi nghiệp vụ**. `orElseThrow(() -> new ...)` cho phép nêu lỗi cụ thể. Nếu chỉ cần exception mặc định, `orElseThrow()` (không đối số) cũng có thể dùng.

**Quyết định quan trọng:** Không tìm thấy người dùng ở một màn hình tra cứu có thể là trạng thái bình thường; không tìm thấy giao dịch bắt buộc để ghi sổ lại có thể là lỗi. Cùng một `Optional.empty()` nhưng chính sách xử lý khác nhau.

## 9. Bài tập 7 — Tính trung bình, min/max trên Stream nguyên thủy rỗng

**Mức độ:** Nền tảng → Trung cấp.

**Yêu cầu:** Có danh sách điểm số; chỉ các điểm từ 0 đến 100 hợp lệ. Tính điểm trung bình; nếu không có điểm hợp lệ, giữ thông tin **không có kết quả** thay vì tự thay bằng 0. Đồng thời in min/max khi có dữ liệu.

**Lời giải:**

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;

public class PrimitiveOptionalExercise {
    static int[] validScores(List<Integer> source) {
        return source.stream()
            .filter(java.util.Objects::nonNull)
            .mapToInt(Integer::intValue)
            .filter(score -> score >= 0 && score <= 100)
            .toArray();
    }

    public static void main(String[] args) {
        List<Integer> raw = Arrays.asList(
            null, -5, 80, 100, 120
        );

        int[] scores = validScores(raw);

        OptionalDouble average =
            Arrays.stream(scores).average();
        OptionalInt minimum =
            Arrays.stream(scores).min();
        OptionalInt maximum =
            Arrays.stream(scores).max();

        System.out.println(average.orElseThrow()); // 90.0
        System.out.println(minimum.orElseThrow()); // 80
        System.out.println(maximum.orElseThrow()); // 100

        int[] emptyScores = validScores(
            Arrays.asList(null, -1, 200)
        );

        OptionalDouble noAverage =
            Arrays.stream(emptyScores).average();

        System.out.println(noAverage); // OptionalDouble.empty
    }
}
~~~

Các phương thức `IntStream.min()`, `max()` trả `OptionalInt`; `average()` trả `OptionalDouble`. Đây là cách biểu diễn đúng trạng thái không có số liệu.

### Vì sao không nên luôn dùng average().orElse(0.0)?

Kết quả **không có dữ liệu** và **trung bình thực sự bằng 0.0** có thể khác nhau về nghiệp vụ. Nếu màn hình muốn hiển thị `"Chưa có điểm"`, hãy giữ Optional đến tầng hiển thị:

~~~java
OptionalDouble avg = Arrays.stream(emptyScores).average();

String label = avg.isPresent()
    ? String.format(java.util.Locale.ROOT, "%.1f", avg.getAsDouble())
    : "Chưa có điểm";

System.out.println(label); // Chưa có điểm
~~~

`getAsDouble()` chỉ được gọi sau khi đã kiểm tra `isPresent()`. Nếu không thể có điểm thiếu mà vẫn được chấp nhận, hãy báo lỗi thay vì ép `0.0`.

**Lưu ý:** `Arrays.stream(scores)` tạo một IntStream mới ở mỗi lần tính vì Stream đã dùng terminal không được tái sử dụng. Nếu chỉ cần thống kê chuẩn trong một lần duyệt, có thể dùng `summaryStatistics()`.

## 10. Bài tập 8 — reduce trên nguồn rỗng và identity

**Mức độ:** Trung cấp.

**Yêu cầu:** Từ một danh sách số nguyên, tính tổng hai cách: (1) dùng `reduce(Integer::sum)`, (2) dùng `reduce(0, Integer::sum)`. Giải thích kết quả khi danh sách rỗng.

**Lời giải:**

~~~java
import java.util.List;
import java.util.Optional;

public class ReduceEmptyExercise {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 3, 5);

        Optional<Integer> optionalSum =
            numbers.stream().reduce(Integer::sum);

        int sumWithIdentity =
            numbers.stream().reduce(0, Integer::sum);

        System.out.println(optionalSum); // Optional[10]
        System.out.println(sumWithIdentity); // 10

        List<Integer> empty = List.of();

        System.out.println(
            empty.stream().reduce(Integer::sum)
        ); // Optional.empty

        System.out.println(
            empty.stream().reduce(0, Integer::sum)
        ); // 0
    }
}
~~~

**Giải thích:**

- `reduce(BinaryOperator)` không có identity nên trả Optional, rỗng nếu không có phần tử.
- `reduce(identity, BinaryOperator)` có kết quả ban đầu. Với nguồn rỗng, trả đúng identity.
- `0` là identity hợp lệ cho phép cộng vì `0 + x = x + 0 = x`.
- `10` không phải identity của phép cộng. `reduce(10, Integer::sum)` trên nguồn `[2,3,5]` sẽ thành `20` ở chế độ tuần tự; đó không phải tổng đơn thuần.

### Vấn đề null trong reduce

~~~java
import java.util.Arrays;
import java.util.Objects;

List<Integer> values = Arrays.asList(2, null, 3);

int sum = values.stream()
    .filter(Objects::nonNull)
    .reduce(0, Integer::sum);

System.out.println(sum); // 5
~~~

Không để `Integer::sum` nhận null. Đồng thời, `reduce(BinaryOperator)` không thể dùng một giá trị kết quả `null` để thay thế trạng thái Optional rỗng; phép rút gọn có thể ném `NullPointerException` nếu kết quả gộp là null.

Đối với số lượng lớn, ưu tiên `mapToLong(...).sum()` khi tổng có thể vượt miền `int`; `long` vẫn có giới hạn và cần kiểm tra theo quy mô thực tế.

## 11. Bài tập 9 — Gom nhiều Optional thành một Stream hợp lệ

**Mức độ:** Trung cấp.

**Yêu cầu:** Một danh sách kết quả tra cứu ở dạng `List<Optional<String>>`. Hãy lấy ra các giá trị thực sự có mặt, giữ thứ tự và không gọi `get()` trên Optional rỗng.

**Lời giải:**

~~~java
import java.util.List;
import java.util.Optional;

public class FlattenOptionalExercise {
    public static void main(String[] args) {
        List<Optional<String>> lookups = List.of(
            Optional.of("An"),
            Optional.empty(),
            Optional.of("Bình"),
            Optional.empty(),
            Optional.of("Chi")
        );

        List<String> names = lookups.stream()
            .flatMap(Optional::stream)
            .toList();

        System.out.println(names); // [An, Bình, Chi]
    }
}
~~~

`Optional.stream()` tạo Stream 0 phần tử nếu Optional rỗng, hoặc một phần tử nếu Optional có giá trị. `flatMap(Optional::stream)` làm phẳng toàn bộ kết quả mà không cần `isPresent()` + `get()`.

Một cách khác trên Java 8 là:

~~~java
List<String> names = lookups.stream()
    .filter(Optional::isPresent)
    .map(Optional::get)
    .toList();
~~~

Cách sau biên dịch với Java 17+, nhưng `Optional::stream` thường súc tích hơn và tránh gọi `get()` trực tiếp. `Stream.toList()` chỉ có từ Java 16, nên với Java 8 cần thay terminal bằng collector tương thích.

### Nếu List có thể chứa chính đối tượng Optional null?

Hãy lọc chính đối tượng Optional trước:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.Optional;

List<Optional<String>> raw = Arrays.asList(
    Optional.of("A"), null, Optional.empty()
);

List<String> valid = raw.stream()
    .filter(Objects::nonNull)
    .flatMap(Optional::stream)
    .toList();

System.out.println(valid); // [A]
~~~

`Optional.empty()` là một đối tượng hợp lệ; một biến `Optional` bằng `null` lại là **vi phạm quy ước thiết kế Optional**. Thông thường hãy sửa nguồn phát sinh Optional null, thay vì dựa mãi vào việc lọc nó ở downstream.

## 12. Bài tập 10 — Null trong kết quả collect và chính sách dữ liệu

**Mức độ:** Trung cấp.

**Yêu cầu:** Một Stream có thể chứa phần tử null. So sánh hai cách tạo List không sửa đổi được và đề xuất cách không cho null đi vào kết quả.

**Lời giải:**

~~~java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectNullExercise {
    public static void main(String[] args) {
        List<String> acceptsNull = Stream.of("A", null, "B")
            .toList();

        System.out.println(acceptsNull); // [A, null, B]

        // Đoạn dưới ném NullPointerException:
        // List<String> fails = Stream.of("A", null, "B")
        //     .collect(Collectors.toUnmodifiableList());

        List<String> cleaned = Stream.of("A", null, "B")
            .filter(Objects::nonNull)
            .collect(Collectors.toUnmodifiableList());

        System.out.println(cleaned); // [A, B]
    }
}
~~~

Hai lời gọi `Stream.toList()` và `Collectors.toUnmodifiableList()` **đều trả List không sửa đổi được**, nhưng **khác nhau về null**:

| Cách thu thập | List sửa được? | Có thể chứa phần tử null? |
| --- | --- | --- |
| `Stream.toList()` | Không | Có |
| `Collectors.toUnmodifiableList()` | Không | Không; ném NPE |
| `Collectors.toCollection(ArrayList::new)` | Có | Có, theo hợp đồng của ArrayList |
| `Collectors.toList()` | Không cam kết | Không nên dựa vào đặc điểm triển khai khi chính sách null là yêu cầu cốt lõi |

**Đừng đánh đồng List không sửa đổi được với List không chứa null.** Nếu muốn phát hiện null như một lỗi dữ liệu, việc collector ném NPE có thể là một tín hiệu nhưng thường nên đưa ra thông báo lỗi nghiệp vụ rõ hơn.

### Kiểm thử đúng theo quy tắc

~~~java
List<String> noNulls = Stream.of("A", null, "B")
    .filter(Objects::nonNull)
    .toList();

if (noNulls.size() != 2 || noNulls.contains(null)) {
    throw new AssertionError("Không được giữ null");
}
~~~

Ở đây đầu ra là danh sách không sửa đổi được, thứ tự `A` trước `B` được giữ vì nguồn Stream có encounter order.

## 13. Bài tập 11 — groupingBy và toMap khi khóa hoặc giá trị có thể null

**Mức độ:** Trung cấp.

**Yêu cầu:** Mỗi bản ghi nhân viên có tên và phòng ban, nhưng phòng ban có thể null. Hãy đếm nhân viên theo phòng ban, đưa phòng ban thiếu vào nhóm `"CHUA_XAC_DINH"`. Sau đó tạo Map tra cứu theo tên, loại những bản ghi không có tên.

**Lời giải:**

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class NullableKeysExercise {
    record Employee(String name, String department) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
            new Employee("An", "Engineering"),
            new Employee("Bình", null),
            new Employee("Chi", "Engineering"),
            new Employee(null, "Finance")
        );

        Map<String, Long> countByDepartment = employees.stream()
            .collect(Collectors.groupingBy(
                e -> e.department() == null
                    ? "CHUA_XAC_DINH"
                    : e.department(),
                TreeMap::new,
                Collectors.counting()
            ));

        System.out.println(countByDepartment.get("Engineering")); // 2
        System.out.println(countByDepartment.get("CHUA_XAC_DINH")); // 1
        System.out.println(countByDepartment.get("Finance")); // 1

        Map<String, String> byName = employees.stream()
            .filter(e -> e.name() != null)
            .collect(Collectors.toMap(
                Employee::name,
                e -> e.department() == null
                    ? "CHUA_XAC_DINH"
                    : e.department()
            ));

        System.out.println(byName.get("Bình")); // CHUA_XAC_DINH
    }
}
~~~

`groupingBy` trong Java chuẩn hiện hành **không chấp nhận classifier trả null**; nó có thể ném `NullPointerException`. Mẫu trên thay thế bằng khóa tường minh trước khi dữ liệu đi vào Map. Trong hệ thống có phòng ban tên thật bằng `"CHUA_XAC_DINH"`, nên dùng enum hoặc kiểu khóa có trạng thái rõ ràng để tránh nhập nhằng với sentinel.

`Collectors.toMap(keyMapper, valueMapper)` ném `IllegalStateException` khi khóa trùng; ở đây tên được giả định duy nhất để minh họa. Nó cũng không phải công cụ để lưu giá trị null tùy ý; mẫu đã chuyển trường department null thành chuỗi hợp lệ.

### Trường hợp nguồn chứa phần tử Employee null

Nếu bản thân List có phần tử null, phải thêm `filter(Objects::nonNull)` trước `Employee::name` hoặc `Employee::department`. `List.of(...)` không cho tạo một phần tử null; `Arrays.asList(...)` hoặc nguồn bên ngoài có thể chứa null.

**Bài thử mở rộng:** Nếu một nhân viên có `name == null` mà nghiệp vụ không cho phép bỏ qua, hãy thay `filter` bằng bước kiểm tra và ném exception có thông tin vị trí/dòng dữ liệu.

## 14. Bài tập 12 — Quy tắc tìm kiếm có thứ tự và nguồn trống

**Mức độ:** Trung cấp.

**Yêu cầu:** Một danh sách tác vụ được sắp theo thứ tự ưu tiên. Viết hàm tìm tác vụ đầu tiên có `priority >= 5` và trả `Optional<Task>`. Đảm bảo kết quả có thể vắng mặt; không tự biến nó thành một tác vụ giả.

**Lời giải:**

~~~java
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class OptionalTaskExercise {
    record Task(String code, int priority) {}

    static Optional<Task> firstHighPriority(List<Task> tasks) {
        Objects.requireNonNull(tasks, "tasks");

        return tasks.stream()
            .filter(Objects::nonNull)
            .filter(task -> task.priority() >= 5)
            .findFirst();
    }

    public static void main(String[] args) {
        List<Task> tasks = List.of(
            new Task("A", 2),
            new Task("B", 8),
            new Task("C", 9)
        );

        System.out.println(
            firstHighPriority(tasks).map(Task::code)
        ); // Optional[B]

        System.out.println(
            firstHighPriority(List.of())
        ); // Optional.empty
    }
}
~~~

Với `List.stream()`, encounter order phản ánh thứ tự danh sách. `findFirst` chọn tác vụ phù hợp đầu tiên **theo thứ tự đầu vào**. Nếu danh sách chưa được sắp theo tiêu chí ưu tiên mong muốn, `findFirst` không tự thực hiện sắp xếp.

Để tìm **tác vụ ưu tiên cao nhất** thay vì **đầu tiên vượt ngưỡng**, phải dùng `max(Comparator.comparingInt(Task::priority))` hoặc sắp xếp có quy tắc:

~~~java
Optional<Task> highest = tasks.stream()
    .filter(Objects::nonNull)
    .max(java.util.Comparator.comparingInt(Task::priority));

// Trong dữ liệu mẫu: Optional[Task[code=C, priority=9]].
~~~

### Song song có làm thay đổi câu trả lời không?

`parallelStream().findFirst()` vẫn phải tôn trọng encounter order nếu nguồn có thứ tự. `parallelStream().findAny()` được phép chọn bất kỳ phần tử phù hợp nào; không dùng `findAny` nếu yêu cầu là “đầu tiên”.

Nếu source đã `unordered()` hoặc là nguồn không có encounter order, `findFirst` không đảm bảo trả “đầu tiên trong danh sách gốc”. Để xử lý kết quả không có phần tử, cả `findFirst` và `findAny` đều trả Optional rỗng; không tự phát ra null.

## 15. Bài tập tổng hợp — Báo cáo đơn hàng từ dữ liệu không hoàn chỉnh

**Mức độ:** Trung cấp.

**Đề bài thực tế:** Một API trả danh sách đơn hàng; đôi khi tham chiếu danh sách là null. Bên trong có thể có phần tử Order null, mã đơn thiếu, khu vực thiếu hoặc giá trị tiền thiếu. Hệ thống cần:

1. Nếu nguồn là null, theo quy ước **không có dữ liệu để báo cáo**; trả kết quả rỗng.
2. Loại đối tượng null, mã null/trắng và đơn không có giá trị tiền.
3. Thay khu vực null/trắng bằng nhóm `"UNKNOWN"`.
4. Tính số đơn hợp lệ và tổng tiền `long` theo khu vực; sắp xếp các khóa để báo cáo dễ đọc.
5. Tìm **mã của đơn hợp lệ đầu tiên** có tiền từ 150 trở lên, giữ kết quả ở dạng Optional.
6. Không sửa nguồn, không dùng biến đếm chia sẻ và không tái sử dụng Stream sau terminal.

**Lời giải đầy đủ:**

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class IncompleteOrdersReport {
    record Order(String id, String region, Long amount) {}

    record Report(
        long validCount,
        Map<String, Long> amountByRegion,
        Optional<String> firstLargeOrderId
    ) {}

    static Report analyze(List<Order> source) {
        // Quy ước riêng của đề bài: null source == nguồn rỗng.
        List<Order> valid = Optional.ofNullable(source)
            .orElseGet(List::of)
            .stream()
            .filter(Objects::nonNull)
            .filter(o -> o.id() != null && !o.id().isBlank())
            .filter(o -> o.amount() != null)
            .toList();

        Map<String, Long> totals = valid.stream()
            .collect(Collectors.groupingBy(
                o -> o.region() == null || o.region().isBlank()
                    ? "UNKNOWN"
                    : o.region().strip(),
                TreeMap::new,
                Collectors.summingLong(Order::amount)
            ));

        Optional<String> firstLargeId = valid.stream()
            .filter(o -> o.amount() >= 150L)
            .map(Order::id)
            .findFirst();

        // Chỉ công bố một view không cho sửa cấu trúc Map.
        return new Report(
            valid.size(),
            Collections.unmodifiableMap(totals),
            firstLargeId
        );
    }

    public static void main(String[] args) {
        List<Order> raw = Arrays.asList(
            new Order("O1", "Nam", 120L),
            null,
            new Order(" ", "Bắc", 50L),
            new Order("O2", null, 75L),
            new Order("O3", "Nam", null),
            new Order("O4", "Nam", 200L)
        );

        Report report = analyze(raw);

        System.out.println(report.validCount()); // 3
        System.out.println(report.amountByRegion());
        // {Nam=320, UNKNOWN=75}
        System.out.println(report.firstLargeOrderId());
        // Optional[O4]

        Report empty = analyze(null);
        System.out.println(empty.validCount()); // 0
        System.out.println(empty.amountByRegion()); // {}
        System.out.println(empty.firstLargeOrderId());
        // Optional.empty
    }
}
~~~

### Vì sao lời giải đáp ứng yêu cầu?

- `Optional.ofNullable(source).orElseGet(List::of)` chỉ chuyển **tham chiếu nguồn null** thành List rỗng theo đúng quy ước đề bài.
- `filter(Objects::nonNull)` loại **đối tượng Order null** trước khi truy cập trường.
- Hai điều kiện tiếp theo loại ID thiếu/trắng và amount thiếu; không dùng `null` như giá trị tiền bằng 0.
- `groupingBy(..., TreeMap::new, summingLong(...))` tạo báo cáo với khóa có thứ tự; classifier luôn trả khóa không null.
- `findFirst()` trả `Optional<String>` khi không có đơn nào đủ ngưỡng. Không có mã giả kiểu `"NONE"` dễ bị nhầm với ID thực.
- Dùng `valid.stream()` **hai lần**, tức mỗi lần là một Stream mới trên một List đã materialize, chứ không chạy terminal hai lần trên cùng Stream.
- `Collections.unmodifiableMap(totals)` chặn sửa Map qua kết quả `Report`. Map nguồn `totals` không bị trả ra bằng tham chiếu khác trong ví dụ; `Order` cũng là record chỉ chứa các trường bất biến (`String` và `Long`). Đây vẫn là **view không sửa cấu trúc**, không phải lời hứa bất biến sâu cho mọi kiểu object.

### Những chính sách khác cũng có thể hợp lệ

Bài chọn **bỏ bản ghi không có ID hoặc amount**. Trong quy trình thanh toán thật, đây có thể là lỗi dữ liệu nghiêm trọng, phải **giữ lại danh sách bản ghi lỗi** hoặc chấm dứt xử lý. Tương tự, amount có thể âm để biểu diễn hoàn tiền; không được tự loại số âm nếu chưa có yêu cầu. `Collectors.summingLong` có thể tràn `long`; với dữ liệu tài chính lớn cần giới hạn hoặc kiểu số có kiểm soát.

Nếu yêu cầu là **tránh giữ danh sách trung gian**, có thể dùng collector tùy chỉnh hoặc các phép thống kê ghép, nhưng lời giải ở đây ưu tiên tính rõ ràng và an toàn cho cấp độ trung cấp.

## 16. Checklist kiểm thử các trường hợp biên

Với mỗi pipeline xử lý dữ liệu không hoàn chỉnh, nên xác minh tối thiểu các trường hợp sau. Không cần làm tất cả bằng một hàm khổng lồ; tách kiểm thử theo hợp đồng đầu vào và đầu ra:

| Tình huống thử | Điều mong đợi |
| --- | --- |
| Nguồn `null` | Theo chính sách đã định: báo lỗi hoặc coi rỗng |
| Nguồn `List.of()` | Kết quả rỗng / Optional rỗng, không NPE |
| List chỉ có phần tử null | Lọc đúng hoặc báo lỗi; không gọi method trên null |
| Có null xen giữa phần tử hợp lệ | Phần tử hợp lệ vẫn được giữ theo quy tắc |
| Trường nullable bên trong record | Chuẩn hóa hoặc đưa sang nhánh lỗi trước collector |
| `findFirst` không có phần tử phù hợp | `Optional.empty()` hoặc fallback rõ ràng |
| `findFirst` gặp phần tử null | Không để null được chọn trực tiếp |
| `average` trên IntStream rỗng | `OptionalDouble.empty()` |
| `reduce` không identity trên nguồn rỗng | `Optional.empty()` |
| `reduce` có identity trên nguồn rỗng | Identity, ví dụ `0` cho phép cộng |
| `allMatch` trên nguồn rỗng | `true`; nếu cần không rỗng, kiểm tra thêm |
| `toUnmodifiableList` gặp null | NPE; phải lọc hoặc chủ động báo lỗi |
| `groupingBy` classifier trả null | NPE; phải dùng khóa thay thế hợp lệ hoặc báo lỗi |
| `toMap` gặp khóa trùng | Ném `IllegalStateException` nếu không có merge function |
| Phép cộng số lớn | Không bỏ qua rủi ro overflow |
| Parallel có tác dụng phụ | Không dựa vào thứ tự callback hoặc state dùng chung |

### Một bộ kiểm tra nhỏ không cần thư viện ngoài

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class MissingDataChecks {
    static Optional<String> firstValid(List<String> source) {
        return Optional.ofNullable(source)
            .orElseGet(List::of)
            .stream()
            .filter(Objects::nonNull)
            .map(String::strip)
            .filter(s -> !s.isEmpty())
            .findFirst();
    }

    public static void main(String[] args) {
        if (firstValid(null).isPresent()) {
            throw new AssertionError("Null source phải trả empty");
        }

        if (firstValid(List.of()).isPresent()) {
            throw new AssertionError("List rỗng phải trả empty");
        }

        if (firstValid(Arrays.asList(null, "  ", " An "))
                .filter("An"::equals)
                .isEmpty()) {
            throw new AssertionError("Đã bỏ mất phần tử hợp lệ");
        }

        System.out.println("PASS");
    }
}
~~~

Kiểm thử trên kiểm tra ba tình huống: không có đối tượng nguồn, nguồn hợp lệ nhưng rỗng và dữ liệu có null/trắng xen kẽ. Khi bài toán phức tạp hơn, nên đặt tên ca kiểm thử theo từng quy tắc nghiệp vụ và thêm trường hợp đầu ra bị trùng, độ lớn vượt kiểu số hoặc thứ tự nguồn thay đổi.

## 17. Những cách viết nên tránh

### 17.1. Gọi stream() trực tiếp trên nguồn nullable

~~~java
List<String> source = null;

// source.stream().count(); // NullPointerException.
~~~

Nếu null hợp lệ theo hợp đồng, thay bằng cách chuyển nó thành List/Stream rỗng. Nếu null là lỗi, dùng `Objects.requireNonNull` với thông báo rõ ràng.

### 17.2. Gọi method trên phần tử trước khi lọc null

~~~java
// Sai nếu có phần tử null:
// source.stream().map(String::strip).filter(Objects::nonNull);
~~~

Lọc `null` trước method có thể ném NPE, hoặc dùng `flatMap(x -> Stream.ofNullable(x))` ở vị trí phù hợp.

### 17.3. Ép Optional rỗng thành giá trị thật mà không cân nhắc nghiệp vụ

~~~java
double average = java.util.stream.IntStream.empty()
    .average()
    .orElse(0.0);

// Giá trị 0.0 ở đây là fallback, không phải trung bình đo được.
~~~

Khi hai trạng thái cần phân biệt, giữ `OptionalDouble` tới khi trình bày kết quả.

### 17.4. Tin rằng findAny và findFirst tự bỏ qua null

~~~java
// Có thể ném NPE khi giá trị được chọn là null:
// java.util.stream.Stream.of((String) null).findAny();
~~~

Nếu chính sách là bỏ null, dùng `filter(Objects::nonNull)` trước terminal tìm kiếm.

### 17.5. Dùng orElse với lời gọi tốn kém

~~~java
// loadFromNetwork() chạy ngay cả khi Optional có giá trị:
// String value = found.orElse(loadFromNetwork());

// Trì hoãn fallback:
// String value = found.orElseGet(() -> loadFromNetwork());
~~~

`orElseGet` chỉ trì hoãn **thân Supplier**. Nếu tạo kết quả dự phòng ở một biến trước lambda, công việc vẫn được thực hiện sớm.

### 17.6. Tái sử dụng Stream sau terminal

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<String> once = List.of("A", "B").stream();
long count = once.count();

// once.findFirst(); // Không được dùng lại Stream đã tiêu thụ.
~~~

Mỗi yêu cầu terminal độc lập thường cần một Stream mới từ nguồn hoặc một `Supplier<Stream<T>>` tạo Stream hợp lệ.

## 18. Câu hỏi tự kiểm tra và bài mở rộng

1. **Nguồn List rỗng có giống tham chiếu List bằng null không?** Không. List rỗng là đối tượng hợp lệ; gọi `stream()` trên null ném NPE.
2. **`Stream.ofNullable(null)` tạo bao nhiêu phần tử?** 0 phần tử.
3. **`Stream.of((String) null)` tạo bao nhiêu phần tử?** 1 phần tử, và phần tử đó bằng null.
4. **Tại sao phải `filter(Objects::nonNull)` trước `map(String::strip)`?** Vì `String::strip` không được gọi trên tham chiếu null.
5. **`findFirst()` có trả null khi không tìm thấy không?** Không; trả `Optional.empty()`.
6. **`findFirst()` có an toàn nếu phần tử đầu tiên bằng null không?** Không; có thể ném NPE nếu chọn null.
7. **`Optional.ofNullable(value)` khác `Optional.of(value)` khi `value == null`?** `ofNullable` trả Optional rỗng; `of` ném NPE.
8. **`orElse(default())` khác `orElseGet(() -> default())` thế nào?** Cách đầu tính đối số trước lời gọi; cách sau chỉ chạy Supplier khi Optional rỗng.
9. **Khi thiếu dữ liệu bắt buộc, nên trả chuỗi "UNKNOWN" hay báo lỗi?** Chọn theo hợp đồng; nếu bắt buộc có dữ liệu, thường dùng `orElseThrow` hoặc mô hình lỗi rõ ràng.
10. **`IntStream.empty().average()` trả gì?** `OptionalDouble.empty()`.
11. **`IntStream.empty().sum()` trả gì?** `0`.
12. **Vì sao `allMatch` trên Stream rỗng trả true?** Vì không có phần tử nào phản ví dụ.
13. **`flatMap(Optional::stream)` có tác dụng gì?** Biến mỗi Optional thành Stream 0/1 phần tử rồi gộp lại.
14. **`toList()` và `toUnmodifiableList()` có cùng chính sách null không?** Không. `toList()` có thể chứa null, `toUnmodifiableList()` cấm null.
15. **`groupingBy` có tự tạo nhóm cho classifier trả null không?** Không; Java chuẩn hiện hành ném NPE.
16. **`findAny` trên parallel stream có bảo đảm phần tử đầu tiên không?** Không; có thể chọn bất kỳ phần tử phù hợp.
17. **Khi cần tính trung bình trên tập không có dữ liệu, tại sao Optional có ích?** Nó giữ khác biệt giữa “không có số liệu” và “trung bình thật bằng 0”.
18. **Một pipeline đã gọi `count()` có dùng lại để gọi `findFirst()` được không?** Không; phải tạo Stream mới.

**Bài mở rộng A:** Sửa bài tổng hợp đơn hàng để trả thêm một `List<String> invalidIds` ghi nhận các ID lỗi, thay vì âm thầm loại tất cả bản ghi thiếu dữ liệu. Chú ý phân biệt bản ghi null với bản ghi có `id == null`.

**Bài mở rộng B:** Thêm trường `currency` vào đơn hàng. Không cộng các amount khác đơn vị nếu không có phép quy đổi hợp lệ. Thiết kế một Map theo (region, currency) hoặc nhóm lồng nhau để tránh tổng sai nghiệp vụ.

**Bài mở rộng C:** Viết hàm `Optional<String> findNormalizedEmail(List<Customer>)` có thể nhận danh sách null, phần tử Customer null, email null/trắng. Khi không có email hợp lệ phải trả Optional.empty, không trả null hoặc chuỗi giả.

**Ghi nhớ:** Stream API không tự sửa dữ liệu thiếu. Hãy đặt **chính sách rõ ràng cho từng tầng**: nguồn null, phần tử null, trường nullable, Stream rỗng và kết quả Optional rỗng. `filter`, `Stream.ofNullable` và `Optional.stream` giúp biểu diễn “bỏ giá trị vắng mặt”; `orElse`, `orElseGet` và `orElseThrow` giúp biểu diễn “thay thế hoặc báo lỗi”. Một pipeline tốt phải đúng với cả dữ liệu thường lẫn các trường hợp biên, không chỉ là pipeline không ném exception trên bộ dữ liệu đẹp.
