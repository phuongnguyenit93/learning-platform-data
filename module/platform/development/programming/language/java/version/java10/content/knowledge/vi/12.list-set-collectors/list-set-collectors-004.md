# Quy tắc `null` của `Collectors.toUnmodifiableList()` trong Java 10+

*Chủ đề cha: Collector danh sách và tập. Bài học tập trung vào cách `toUnmodifiableList` xử lý phần tử `null`, mối quan hệ với Stream pipeline, các lựa chọn xử lý dữ liệu và sự khác biệt với những API tạo List hiện đại. Tất cả chương trình hoàn chỉnh chạy với JDK 17 trở lên; nội dung chỉ sử dụng kiến thức và API vẫn áp dụng trong Java hiện đại.*

## 1. Mục tiêu và nguyên tắc quan trọng nhất

Sau bài học, bạn có thể:

1. Giải thích tại sao `stream.collect(Collectors.toUnmodifiableList())` **ném `NullPointerException` nếu bất kỳ phần tử đầu ra nào là `null`**.
2. Phân biệt **Stream tham chiếu chứa phần tử `null`** với **tham chiếu tới chính Stream bằng `null`**, và phân biệt lỗi `null` với việc List kết quả không hỗ trợ sửa.
3. Hiểu `Collectors.toUnmodifiableList()` là **Collector**, được sử dụng bởi terminal operation `collect(...)`; lỗi dữ liệu xuất hiện trong quá trình thực thi pipeline, không phải khi chỉ khai báo một bước trung gian lazy.
4. Biết lọc, thay thế hoặc từ chối `null` **có chủ đích**, không tự động bỏ dữ liệu quan trọng.
5. So sánh `Collectors.toUnmodifiableList()`, `Stream.toList()`, `Collectors.toList()`, `List.copyOf()`, `List.of()` và `toCollection(ArrayList::new)`.
6. Hiểu `unmodifiable` là hợp đồng của cấu trúc List; phần tử mutable bên trong vẫn có thể thay đổi.
7. Đọc đúng generic type, thứ tự phần tử, giá trị trùng và rủi ro tạo thêm `null` trong `map` hoặc downstream collector.

**Quy tắc cần nhớ:** `Collectors.toUnmodifiableList()` tạo List không cho sửa và **không chấp nhận bất kỳ phần tử `null` nào**. Nếu quá trình thu thập có phần tử `null`, operation ném `NullPointerException`; nó không âm thầm bỏ qua `null` và cũng không biến `null` thành chuỗi rỗng.

```java
// Đoạn minh họa trong một phương thức:
var source = java.util.Arrays.asList("A", null, "B");

var valid = source.stream()
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
// valid: List<String> chứa [A, B]

// var invalid = source.stream()
//         .collect(java.util.stream.Collectors.toUnmodifiableList());
// Khi thực thi: NullPointerException vì nguồn có phần tử null.
```

Nguồn dùng `Arrays.asList` vì nó có thể chứa `null`. Không thể dùng `List.of("A", null, "B")` để tạo nguồn trong ví dụ này: `List.of` đã từ chối `null` **ngay tại bước tạo List**, trước khi Stream được hình thành.

## 2. Chữ ký generic: collector tạo ra `List<T>`

Chữ ký API:

```java
public static <T> Collector<T, ?, List<T>> toUnmodifiableList()
```

Đây là chữ ký của phương thức static trong `java.util.stream.Collectors`, không phải đoạn khai báo độc lập để biên dịch như một chương trình. `Collectors.toUnmodifiableList()` đã có từ Java 10.

| Thành phần | Ý nghĩa |
| --- | --- |
| `<T>` | Kiểu phần tử được thu thập |
| `Collector<T, ?, List<T>>` | Collector nhận phần tử kiểu `T` và tạo kết quả `List<T>` |
| `?` | Kiểu tích lũy nội bộ được che giấu; người gọi không cần biết |
| `toUnmodifiableList()` | Factory method trả Collector; **chưa** thực hiện thu thập |
| `stream.collect(...)` | Terminal operation dùng Collector để tạo kết quả |

Ví dụ:

```java
var names = java.util.List.of("An", "Binh");
var result = names.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());
// result có kiểu List<String>
```

Các tham số kiểu vẫn được kiểm tra ở thời điểm biên dịch. `var` chỉ suy luận `List<String>` từ biểu thức `collect(...)`; nó không làm kiểu dynamic, và cũng không tự kiểm tra toàn bộ dữ liệu có `null` trước khi terminal operation chạy.

**Lưu ý:** Một biến kiểu `String` hoặc `List<String>` trong Java không đồng nghĩa mọi giá trị tham chiếu trong đó chắc chắn khác `null`. Hệ kiểu generic cho phép một Stream tham chiếu `Stream<String>` phát ra phần tử `null`; chính collector này áp đặt hợp đồng chặt hơn ở runtime.

## 3. Tại sao `null` xuất hiện trong pipeline?

`null` có thể đến từ nhiều nguồn, không chỉ do người viết cố tình thêm nó vào một List:

- Dữ liệu tải từ cơ sở dữ liệu hoặc API có thuộc tính tùy chọn.
- `Map.get(key)` trả `null` khi không có ánh xạ (hoặc có ánh xạ tới `null` với Map cho phép).
- Một `map` trả `null` nếu biểu thức không tìm được kết quả.
- Một phép chuyển đổi trên dữ liệu đầu vào làm xuất hiện giá trị `null` ở các nhánh điều kiện.
- Danh sách nguồn tạo bằng `Arrays.asList(...)` hay `ArrayList` có thể chứa `null`.
- Một collector downstream như `mapping(...)` có thể đưa giá trị `null` vào `toUnmodifiableList` dù các phần tử nguồn ban đầu đều khác `null`.

Ví dụ về bước chuyển đổi:

```java
// Đoạn minh họa trong một phương thức:
var words = java.util.List.of("java", "unknown");
var transformed = words.stream()
        .map(word -> word.equals("unknown") ? null : word.toUpperCase());
// transformed là Stream<String>; bước map có thể phát ra null

// Dòng sau, nếu thực thi, sẽ ném NullPointerException:
// var result = transformed.collect(Collectors.toUnmodifiableList());
```

Việc `words` được tạo bằng `List.of` chỉ bảo đảm **nguồn ban đầu** không có `null`. Nó **không bảo đảm** các bước `map` hoặc `flatMap` sau đó không phát ra phần tử `null`.

### 3.1. `null` là phần tử hay là chính Stream?

Hai trường hợp khác nhau:

```java
// Có một đối tượng Stream nhưng bên trong có phần tử null:
var streamWithNull = java.util.stream.Stream.of("A", null, "B");

// Biến tham chiếu Stream chính nó bằng null:
java.util.stream.Stream<String> missingStream = null;
```

Với `streamWithNull.collect(Collectors.toUnmodifiableList())`, nguyên nhân là **phần tử `null` bị collector từ chối**. Với `missingStream.collect(...)`, việc gọi method trên tham chiếu `null` gây `NullPointerException` **trước khi Collector được sử dụng**. Tên ngoại lệ giống nhau nhưng vị trí và cách sửa khác nhau.

Tương tự, `Collectors.toUnmodifiableList()` trả một Collector object, không phải một List có thể thêm phần tử. Chỉ tạo Collector rồi chưa gọi `collect` không làm duyệt các phần tử từ Stream.

## 4. Chương trình đầy đủ: từ chối null rồi lọc có chủ đích

Tạo tệp **`NullCollectorDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Collectors;

public class NullCollectorDemo {
    public static void main(String[] args) {
        var raw = Arrays.asList(
                "  An  ", null, "  ", "Binh", "An");

        try {
            raw.stream()
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("raw-rejected=true");
        }

        var cleaned = raw.stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(s -> !s.isBlank())
                .collect(Collectors.toUnmodifiableList());

        System.out.println("cleaned=" + cleaned);
        System.out.println("sourceSize=" + raw.size());

        try {
            cleaned.add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("add-blocked=true");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 NullCollectorDemo.java
java NullCollectorDemo
```

Stdout:

```text
raw-rejected=true
cleaned=[An, Binh, An]
sourceSize=5
add-blocked=true
```

Giải thích theo thứ tự:

1. `Arrays.asList(...)` tạo danh sách nguồn có 5 phần tử, một trong số đó là `null`.
2. `collect(toUnmodifiableList())` đầu tiên **ném `NullPointerException`**, được bắt để chương trình minh họa tiếp tục. Không có List kết quả hợp lệ từ phép thu thập thất bại đó.
3. Với pipeline thứ hai, `filter(Objects::nonNull)` loại phần tử `null` **trước** khi gọi `String::strip`, tránh gọi method trên tham chiếu null.
4. `strip` bỏ khoảng trắng hai đầu; `filter(s -> !s.isBlank())` loại chuỗi chỉ gồm khoảng trắng.
5. List kết quả là `[An, Binh, An]`: hai chuỗi `"An"` được giữ vì **List cho phép giá trị trùng**; collector không tự `distinct()`.
6. `sourceSize=5` cho thấy pipeline không tự sửa danh sách nguồn.
7. `cleaned.add("Chi")` bị từ chối bằng `UnsupportedOperationException`. Đây là lỗi **muốn sửa List không cho sửa**, khác lỗi `null` của collector.

Quan trọng: việc bỏ `null` là **quyết định nghiệp vụ** của ví dụ. Nếu mỗi vị trí tương ứng một bản ghi, một khoản thanh toán hoặc một cột dữ liệu cần bảo toàn, bỏ `null` có thể khiến kết quả bị mất dữ liệu và sai số lượng. Khi đó hãy validate và báo lỗi cụ thể, hoặc biểu diễn trường hợp thiếu dữ liệu rõ ràng hơn.

## 5. Phân biệt với các API tạo List khác

Các API hiện đại đều có thể tạo danh sách, nhưng **hợp đồng với `null` khác nhau**:

| API | Cách sử dụng | `null` phần tử? | Kết quả có cho sửa không? |
| --- | --- | --- | --- |
| `Collectors.toUnmodifiableList()` | `stream.collect(...)` | **Không**; ném `NullPointerException` | Không |
| `Stream.toList()` (Java 16+) | `stream.toList()` | Có thể giữ `null` | Không |
| `List.copyOf(collection)` (Java 10+) | `List.copyOf(source)` | **Không**; ném `NullPointerException` | Không |
| `List.of(...)` (Java 9+) | `List.of("A", "B")` | **Không**; ném `NullPointerException` | Không |
| `Collectors.toList()` | `stream.collect(...)` | Không có quy tắc từ chối `null` như collector ở dòng đầu; đừng dùng để validate | API không đảm bảo tính mutable hay loại List cụ thể |
| `Collectors.toCollection(ArrayList::new)` | `stream.collect(...)` | `ArrayList` cho phép `null` | Có, là `ArrayList` mutable |

Một lưu ý riêng với `Stream.toList()`: nó là **method của Stream**, không phải `Collectors.toList()`. Chúng khác API, thời điểm ra đời và hợp đồng của List trả về. `Stream.toList()` không cho sửa danh sách kết quả; `Collectors.toList()` không cam kết cụ thể danh sách kết quả có cho sửa hay không. Đừng suy luận hai thứ giống nhau chỉ vì cùng đọc là “to list”.

### 5.1. Chương trình so sánh null policy

Tạo **`CollectorComparisonDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class CollectorComparisonDemo {
    public static void main(String[] args) {
        var source = Arrays.asList("A", null, "B");

        var streamList = source.stream().toList();
        System.out.println("stream-toList=" + streamList);

        try {
            source.stream()
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("collector-rejects-null=true");
        }

        try {
            List.copyOf(streamList);
        } catch (NullPointerException ex) {
            System.out.println("copyOf-rejects-null=true");
        }

        var filtered = source.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.toUnmodifiableList());
        System.out.println("filtered=" + filtered);

        var replaced = source.stream()
                .map(value -> Objects.requireNonNullElse(
                        value, "UNKNOWN"))
                .collect(Collectors.toUnmodifiableList());
        System.out.println("replaced=" + replaced);
    }
}
```

Chạy:

```bash
javac --release 17 CollectorComparisonDemo.java
java CollectorComparisonDemo
```

Stdout:

```text
stream-toList=[A, null, B]
collector-rejects-null=true
copyOf-rejects-null=true
filtered=[A, B]
replaced=[A, UNKNOWN, B]
```

Từ kết quả:

- `Stream.toList()` cho phép tạo List không sửa được chứa `null` trong ví dụ.
- `Collectors.toUnmodifiableList()` từ chối phần tử `null`.
- `List.copyOf(...)` cũng từ chối phần tử `null`, kể cả khi danh sách nguồn đã không cho sửa.
- `filter(Objects::nonNull)` **làm giảm số lượng phần tử** từ 3 xuống 2.
- `Objects.requireNonNullElse(value, "UNKNOWN")` **giữ số lượng và vị trí**, thay `null` bằng một giá trị đã được chọn. Giá trị dự phòng truyền vào `requireNonNullElse` cũng phải khác `null`.

Đừng coi việc thay bằng `"UNKNOWN"` là mặc định đúng trong mọi domain. Trong hệ thống nghiệp vụ, một giá trị mặc định phải hợp lệ và không được che giấu lỗi dữ liệu.

### 5.2. Vì sao phải gọi lại `source.stream()`?

Trong chương trình so sánh, mỗi phép thu thập gọi `source.stream()` **mới**. Java Stream thuộc về một pipeline và không dùng lại sau terminal operation. Không viết:

```java
// Sai cách dùng:
var stream = source.stream();
var first = stream.toList();
// var second = stream.collect(Collectors.toUnmodifiableList());
// Stream đã được tiêu thụ ở bước toList().
```

Cùng một collection nguồn có thể tạo nhiều Stream độc lập, nhưng một đối tượng Stream không nên được tiêu thụ lần hai. Ngay cả khi lần thu thập đầu ném ngoại lệ, không tái sử dụng Stream đã bắt đầu vận hành.

## 6. Ba chiến lược xử lý null: bỏ, thay hoặc từ chối

**Không có một chiến lược đúng cho mọi bài toán.** Quy tắc của collector nói rằng kết quả không được chứa `null`, nhưng ứng dụng phải quyết định cần xử lý dữ liệu thiếu theo cách nào.

### 6.1. Bỏ phần tử null khi nghiệp vụ cho phép

```java
var nonNullNames = rawNames.stream()
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Đây là **đoạn minh họa** trong một phương thức, với `rawNames` là một `Collection<String>` có sẵn. Chỉ dùng khi sự vắng mặt được phép bị loại bỏ và không cần giữ số vị trí ban đầu. Ví dụ danh sách từ khóa tùy chọn có thể bỏ giá trị rỗng theo định nghĩa nghiệp vụ.

Nếu muốn loại cả chuỗi rỗng/trắng, cần thêm điều kiện riêng:

```java
var validNames = rawNames.stream()
        .filter(java.util.Objects::nonNull)
        .map(String::strip)
        .filter(s -> !s.isBlank())
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

`null` và `""` không giống nhau; `Objects::nonNull` chỉ loại `null`. `String::strip` được gọi **sau** bước lọc null để tránh `NullPointerException` ngay trong `map`.

### 6.2. Thay null bằng giá trị hợp lệ

Khi cần giữ mỗi vị trí phần tử và domain có một giá trị mặc định rõ:

```java
var normalizedNames = rawNames.stream()
        .map(name -> java.util.Objects.requireNonNullElse(
                name, "UNKNOWN"))
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Đây là các đoạn minh họa cần biến `rawNames`. Mọi phần tử sau `map` đều khác `null` nếu fallback khác `null`. Không nên dùng chuỗi `"UNKNOWN"` như giá trị giả khi hệ thống phải phân biệt “thiếu thông tin” với “có giá trị thật”.

Trong một domain phù hợp, có thể dùng một record/enum biểu diễn trạng thái thiếu dữ liệu thay vì `null`:

```java
// Minh họa thiết kế dữ liệu:
enum NameStatus { PRESENT, MISSING }
```

Nhưng chỉ thêm đối tượng đánh dấu nếu nó phù hợp hợp đồng API; đừng biến mọi phép xử lý nhỏ thành hệ thống trạng thái không cần thiết.

### 6.3. Từ chối dữ liệu null và cung cấp ngữ cảnh lỗi

`Collectors.toUnmodifiableList()` đã từ chối null, nhưng `NullPointerException` cuối pipeline có thể không cho biết **vị trí dữ liệu đầu vào nào** sai. Nếu thiếu tên là lỗi nghiệp vụ, validate tại biên đọc dữ liệu hoặc ngay tại bước chuyển đổi:

```java
// Đoạn minh họa trong một phương thức:
var checkedNames = rawNames.stream()
        .map(name -> java.util.Objects.requireNonNull(
                name, "name must not be null"))
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

`Objects.requireNonNull` trả chính tham chiếu nếu hợp lệ; nếu bằng `null`, nó ném `NullPointerException` với thông điệp chỉ định. Điều này khiến hợp đồng được kiểm tra **trước đầu ra Collector** và biểu đạt rõ ý định. Nếu cần biết số thứ tự dòng, ID bản ghi hoặc trường cụ thể, hãy validate với ngữ cảnh đó thay vì đặt toàn bộ trách nhiệm vào collector.

Trong API ứng dụng, có thể chuyển lỗi input thành một ngoại lệ phù hợp ở **ranh giới validate**, nhưng không nên bắt rồi nuốt tất cả `NullPointerException`: ngoại lệ này có thể đến từ những lỗi lập trình khác, không chỉ từ dữ liệu người dùng.

### 6.4. Dùng `Stream.ofNullable` khi vắng mặt tương ứng 0 hoặc 1 phần tử

`Stream.ofNullable(value)` (Java 9+) trả Stream rỗng nếu `value == null`, hoặc Stream chứa đúng một phần tử nếu khác null. Nó hữu ích khi muốn **bỏ các giá trị vắng mặt có chủ đích**:

```java
var names = java.util.Arrays.asList("A", null, "B");

var nonNull = names.stream()
        .flatMap(java.util.stream.Stream::ofNullable)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
// [A, B]
```

Đây là một cách diễn đạt khác của `filter(Objects::nonNull)` trong trường hợp mỗi phần tử nguồn được chuyển thành 0 hoặc 1 phần tử đầu ra. Nó không phải phương thức xử lý lỗi thay cho validation.

## 7. Thứ tự đặt filter rất quan trọng: `map` có thể tạo lại null

Đừng cho rằng `filter(Objects::nonNull)` một lần ở đầu pipeline bảo đảm các bước sau không bao giờ sinh null:

```java
// Dữ liệu nguồn không có null:
var source = java.util.List.of("A", "B");

var transformed = source.stream()
        .filter(java.util.Objects::nonNull)
        .map(s -> s.equals("B") ? null : s);
// transformed có thể phát ra null từ bước map.
```

Nếu thu thập bằng `toUnmodifiableList`, kết quả lỗi. Trong trường hợp muốn bỏ phần tử thiếu sau `map`, phải lọc **sau bước tạo null**:

```java
var safe = source.stream()
        .map(s -> s.equals("B") ? null : s)
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
// [A]
```

Tạo file **`NullAfterMapDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class NullAfterMapDemo {
    public static void main(String[] args) {
        var source = List.of("A", "B");

        try {
            source.stream()
                    .filter(Objects::nonNull)
                    .map(s -> s.equals("B") ? null : s)
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("mapping-can-reintroduce-null=true");
        }

        var fixed = source.stream()
                .map(s -> s.equals("B") ? null : s)
                .filter(Objects::nonNull)
                .collect(Collectors.toUnmodifiableList());

        System.out.println("final=" + fixed);
    }
}
```

Chạy:

```bash
javac --release 17 NullAfterMapDemo.java
java NullAfterMapDemo
```

Stdout:

```text
mapping-can-reintroduce-null=true
final=[A]
```

**Bài học:** ràng buộc “phần tử đưa vào `toUnmodifiableList` không được null” phải đúng ở **đầu ra của toàn bộ pipeline**, không chỉ tại nguồn ban đầu. Khi có `mapping` downstream collector hoặc các bước ghép dữ liệu phức tạp, cũng phải xét phần tử thực sự đến collector cuối.

## 8. Lazy evaluation, terminal operation và thời điểm ném ngoại lệ

`filter`, `map`, `flatMap` và nhiều thao tác trên Stream là **intermediate operations**, thường lazy. Chúng xây dựng pipeline, nhưng chưa bắt đầu duyệt các phần tử. `collect(...)` là **terminal operation** kích hoạt việc xử lý.

```java
var source = java.util.Arrays.asList("A", null, "B");

var pipeline = source.stream()
        .map(s -> s == null ? null : s.toLowerCase());
// Đến đây chưa nhất thiết duyệt phần tử.

// Khi chạy dòng sau, pipeline có thể phát ra null và collector từ chối:
// var names = pipeline.collect(Collectors.toUnmodifiableList());
```

Có hai kiểu lỗi `NullPointerException` có thể quan sát:

1. Lỗi **bên trong intermediate operation**, chẳng hạn `.map(String::trim)` nhận `null` rồi gọi method trên nó.
2. Lỗi **do Collector từ chối phần tử null**, dù những thao tác trước đó có thể xử lý `null` mà không gọi method trên nó.

Không phụ thuộc vào thời điểm chính xác của bước nội bộ tạo/lưu/trả kết quả để viết logic; collector có thể sử dụng cơ chế tích lũy, kết hợp và hoàn thiện khác nhau. Hợp đồng quan trọng là **không thể có kết quả `toUnmodifiableList` thành công nếu đầu ra có phần tử null**.

Đặc biệt với parallel Stream, đừng giả định các phần tử được xử lý theo một thứ tự thực thi cố định hay lỗi luôn chỉ ra phần tử null nào trước. Nếu cần báo lỗi dữ liệu theo ID/vị trí xác định, validate và tạo thông điệp tại ranh giới dữ liệu, có chiến lược xử lý nhất quán.

### 8.1. Lỗi có thể xảy ra dù danh sách nguồn không null

Ví dụ:

```java
var source = java.util.List.of("first", "missing");

var nullableValues = source.stream()
        .map(s -> s.equals("missing") ? null : s);
// Stream<String> có thể phát ra phần tử null.
```

Trong ví dụ này, collection nguồn, chính Stream và cả các chuỗi nguồn đều khác null; nhưng lambda tạo null có chủ đích. Khi debug lỗi, hãy theo dõi **kiểu và giá trị sau từng bước chuyển đổi** chứ không chỉ nhìn điều kiện của collection nguồn.

## 9. Unmodifiable không đồng nghĩa immutable sâu

Kết quả của `toUnmodifiableList` không hỗ trợ `add`, `remove`, `set`. Tuy nhiên, nó vẫn giữ các tham chiếu đến đối tượng phần tử hiện có.

```java
var value = new StringBuilder("draft");

var list = java.util.stream.Stream.of(value)
        .collect(java.util.stream.Collectors.toUnmodifiableList());

value.append("-edited");
System.out.println(list.get(0)); // draft-edited
```

Danh sách không bị thêm/xóa phần tử, nhưng nội dung `StringBuilder` thay đổi qua cùng tham chiếu. Đây là **shallow immutability của cấu trúc**, không phải deep freeze.

Nếu phần tử cần bất biến về mặt nghiệp vụ, hãy dùng loại giá trị bất biến hoặc sao chép các phần tử mutable theo hợp đồng ứng dụng trước khi thu thập. Nếu phần tử là `String`, chúng bất biến nên phần này đơn giản hơn.

`final var list = ...` chỉ không cho **gán lại biến** `list`; nó không làm các đối tượng bên trong immutable. Tương tự, các List kết quả không được tự động an toàn cho mọi thao tác đồng thời lên các object phần tử.

## 10. Encounter order, phần tử trùng và Stream song song

`Collectors.toUnmodifiableList` thu thập các phần tử theo **encounter order** nếu Stream có thứ tự duyệt được xác định. Nó **không loại phần tử trùng**:

```java
var result = java.util.List.of("A", "B", "A").stream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());
// [A, B, A]
```

Nếu nghiệp vụ cần bỏ trùng, dùng `distinct()` trước terminal operation. Nhưng phải hiểu `distinct()` dựa trên quan hệ `equals` và có thể ảnh hưởng hiệu năng/thứ tự, đặc biệt trên nguồn song song.

Không có thứ tự xác định ở nguồn thì không được kỳ vọng danh sách có một thứ tự cụ thể. `unordered()` hoặc một số collection nguồn không có encounter order có thể dẫn đến kết quả theo thứ tự không ổn định.

Với Stream song song **có encounter order**, collector vẫn tạo List theo thứ tự của nguồn. Ví dụ:

```java
var ordered = java.util.stream.IntStream.range(0, 5)
        .parallel()
        .mapToObj(n -> "v" + n)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
// [v0, v1, v2, v3, v4]
```

Đừng dựa vào thứ tự **thực thi lambda** để suy ra thứ tự của danh sách kết quả. Khi xử lý song song, không dùng side effect tùy tiện trong `map`, `filter`, `peek` để cập nhật danh sách dùng chung. Và dù xử lý song song hay tuần tự, phần tử `null` vẫn bị `toUnmodifiableList` từ chối.

### 10.1. Collector cho Set không có cùng ý nghĩa trùng lặp với List

`Collectors.toUnmodifiableSet()` cũng thuộc nhóm Collector không cho sửa và từ chối phần tử `null`, nhưng **Set** không chứa duplicate theo `equals`. Với các phần tử trùng, không nên giả định đại diện cụ thể nào được giữ, và không có thứ tự Set được bảo đảm.

Nếu bạn cần giữ duplicate và thứ tự, dùng collector cho List; nếu cần tập hợp các giá trị phân biệt, dùng Set theo hợp đồng của bài toán. **Không đổi từ List sang Set chỉ để tránh xử lý null**: cả hai collector không cho sửa đều từ chối null.

## 11. Ví dụ hoàn chỉnh: phần tử mutable, thứ tự và dữ liệu rỗng

Tạo **`ShallowAndOrderDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ShallowAndOrderDemo {
    public static void main(String[] args) {
        var element = new StringBuilder("draft");
        var frozen = Stream.of(element)
                .collect(Collectors.toUnmodifiableList());

        element.append("-edited");
        System.out.println("element=" + frozen.get(0));

        var ordered = IntStream.range(0, 5)
                .parallel()
                .mapToObj(n -> "v" + n)
                .collect(Collectors.toUnmodifiableList());

        System.out.println("parallel-ordered=" + ordered);

        var empty = Stream.<String>empty()
                .collect(Collectors.toUnmodifiableList());
        System.out.println("empty=" + empty);

        var nullable = Arrays.asList("A", null, "B");
        var withoutNull = nullable.stream()
                .flatMap(Stream::ofNullable)
                .collect(Collectors.toUnmodifiableList());

        System.out.println("ofNullable=" + withoutNull);
    }
}
```

Chạy:

```bash
javac --release 17 ShallowAndOrderDemo.java
java ShallowAndOrderDemo
```

Stdout:

```text
element=draft-edited
parallel-ordered=[v0, v1, v2, v3, v4]
empty=[]
ofNullable=[A, B]
```

Các quan sát:

- List kết quả không cho sửa cấu trúc, nhưng `StringBuilder` được chia sẻ.
- `IntStream.range(0, 5)` có encounter order; thu thập song song vẫn giữ thứ tự này trong List.
- Stream rỗng **không có phần tử `null`**, nên `toUnmodifiableList` trả danh sách rỗng hợp lệ.
- `Stream.ofNullable` cho 0 hoặc 1 phần tử mỗi lần gọi; `flatMap` giúp loại bỏ những giá trị null theo quyết định thiết kế.

## 12. Tích hợp vào code nghiệp vụ: chọn hợp đồng trước Collector

Một pipeline nghiệp vụ thường có nhiều bước: tải dữ liệu, chuẩn hóa, validate, biến đổi, rồi tạo kết quả. Khi chọn `toUnmodifiableList`, hãy xác định **một chính sách null rõ ràng ở ranh giới API**:

| Bối cảnh | Chính sách gợi ý | Lý do |
| --- | --- | --- |
| Danh sách thẻ gợi ý tùy chọn | Có thể lọc `null` | Bỏ giá trị vắng mặt không làm mất bản ghi bắt buộc |
| Mã định danh đơn hàng bắt buộc | Từ chối và báo lỗi | Không được âm thầm bỏ đơn hàng |
| Tên hiển thị có fallback quy định | Thay `null` bằng giá trị hợp lệ | Giữ số bản ghi và cung cấp tên để hiển thị |
| Trường có thể vắng mặt là ý nghĩa nghiệp vụ | Xem xét `Optional` hoặc mô hình trạng thái | Tránh ngầm biến “chưa biết” thành một chuỗi giả |
| Dữ liệu cần phân biệt `null` với giá trị thực | Chọn API/mô hình cho phép điều đó, không dùng collector này trực tiếp | `toUnmodifiableList` không chấp nhận null |
| Kết quả phải độc lập với thao tác thêm/xóa của caller | Dùng List không cho sửa với phần tử đã chuẩn hóa | Hợp đồng cấu trúc rõ ràng |

Ví dụ một phương thức chỉ nhận các mã hợp lệ:

```java
// Đoạn minh họa bên trong một lớp:
static java.util.List<String> normalizeRequiredCodes(
        java.util.Collection<String> source) {
    java.util.Objects.requireNonNull(source, "source");

    return source.stream()
            .map(code -> java.util.Objects.requireNonNull(
                    code, "code is required").strip())
            .filter(code -> !code.isBlank())
            .collect(java.util.stream.Collectors.toUnmodifiableList());
}
```

Ở đây `null` bị từ chối, còn chuỗi blank bị loại; **đây là hai quyết định khác nhau**. Nếu cả chuỗi blank cũng là lỗi thay vì giá trị tùy chọn, không nên dùng `filter`, mà cần validate blank rồi ném một ngoại lệ phù hợp. Nhớ kiểm tra thêm giới hạn độ dài, cú pháp hoặc uniqueness nếu hợp đồng domain yêu cầu; `toUnmodifiableList` không tự validate chúng.

### 12.1. Null của một thuộc tính và null của cả đối tượng

Giả sử có `Order` với thuộc tính `referenceCode()`. Dù mọi `Order` trong Stream đều khác null, thuộc tính có thể vắng mặt:

```java
// Đoạn minh họa: orders là Collection<Order> phù hợp
var codes = orders.stream()
        .map(Order::referenceCode)
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Nếu mã tham chiếu là bắt buộc, việc `filter` sẽ che mất lỗi dữ liệu; thay bằng validation có ngữ cảnh:

```java
var codes = orders.stream()
        .map(order -> java.util.Objects.requireNonNull(
                order.referenceCode(), "missing reference code"))
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Hai đoạn chỉ minh họa trong lớp/method có `Order` phù hợp. Cách dùng đúng phụ thuộc hợp đồng nghiệp vụ: **loại bỏ hay báo lỗi** là một lựa chọn thiết kế, không phải thay thế cú pháp đơn thuần.

## 13. Debugging khi nhận `NullPointerException` ở `collect`

Khi stack trace nhắc tới Collector hoặc `toUnmodifiableList`:

1. **Xem đúng collector đang dùng.** `toUnmodifiableList` khác `toList`; chỉ nhìn tên “to list” trong tài liệu có thể gây nhầm.
2. **Phân biệt tham chiếu Stream null và phần tử null.** Nếu Stream null, lời gọi method thất bại ngay; nếu chỉ có một phần tử null, pipeline có thể chạy đến terminal rồi collector từ chối.
3. **Kiểm tra từng phép `map`/`flatMap`.** Một nguồn không chứa null không bảo đảm đầu ra của lambda khác null.
4. **Xác định chính sách nghiệp vụ.** Null là hợp lệ cần bỏ, có fallback hay phải báo lỗi?
5. **Validate với ngữ cảnh trước collector.** Nếu cần biết ID/dòng dữ liệu nào sai, đưa ID vào thông báo ở vị trí chuyển đổi phù hợp.
6. **Đừng phụ thuộc side effect trong `peek` để chứng minh mọi phần tử đã chạy.** Một số tối ưu và short-circuit operation có thể bỏ qua xử lý không cần thiết; parallel stream không hứa thứ tự thực thi cố định.
7. **Kiểm tra collector lồng nhau.** `Collectors.mapping(mapper, Collectors.toUnmodifiableList())` vẫn từ chối null nếu `mapper` đưa ra null.
8. **Không dùng danh sách từ một lần collect thất bại.** Terminal operation không trả một kết quả List hoàn chỉnh; tạo Stream mới từ nguồn sau khi xử lý lỗi dữ liệu.

### 13.1. Collector lồng nhau không bỏ qua quy tắc null

Ví dụ:

```java
// Đoạn minh họa trong một phương thức:
var source = java.util.List.of("a", "missing");

var result = source.stream().collect(
        java.util.stream.Collectors.mapping(
                s -> s.equals("missing") ? null : s,
                java.util.stream.Collectors.toUnmodifiableList()));
// Khi thực thi: NullPointerException
```

`Collectors.mapping` chỉ chuyển đổi phần tử trước khi chuyển sang downstream collector. Quy tắc của `toUnmodifiableList` vẫn có hiệu lực. Nếu muốn loại bỏ kết quả mapping bằng null, đặt một bước lọc phù hợp trong Stream trước khi collect hoặc chọn downstream collector khác nếu chính sách yêu cầu.

## 14. Những lỗi hiểu nhầm cần tránh

| Hiểu nhầm | Quy tắc chính xác |
| --- | --- |
| “`toUnmodifiableList` tự bỏ các phần tử `null`.” | Không; nó ném `NullPointerException` |
| “Danh sách không cho sửa thì không thể chứa `null`.” | Không đúng chung: `Stream.toList()` có thể giữ null và vẫn không cho sửa |
| “`List.of("A", null)` là nguồn tốt để thử collector.” | Sai: `List.of` đã ném NPE khi tạo nguồn |
| “`filter(Objects::nonNull)` ở đầu bảo đảm an toàn toàn pipeline.” | Các bước sau như `map` có thể tạo lại null |
| “Nếu dùng `var`, Java sẽ hiểu phần tử chắc chắn không null.” | Sai: `var` chỉ suy luận kiểu tĩnh |
| “`Collectors.toList()` trả List mutable theo hợp đồng.” | Không có bảo đảm loại/mutability cụ thể |
| “`toUnmodifiableList` tự khử trùng.” | Không; List giữ duplicate và encounter order nếu có |
| “Dùng `collect` song song sẽ chọn phần tử null gây lỗi theo đúng thứ tự nguồn.” | Không được dựa vào thứ tự thực thi hoặc thời điểm phát hiện lỗi |
| “`UnsupportedOperationException` khi `add` là cùng lỗi với NPE khi collect.” | Hai hợp đồng khác nhau: sửa List và tính hợp lệ phần tử |
| “List unmodifiable là deep immutable.” | Phần tử mutable vẫn có thể bị sửa qua tham chiếu khác |
| “Bắt NPE rồi bỏ qua kết quả collect là đủ.” | Phải xử lý dữ liệu đầu vào, tránh nuốt lỗi sai hợp đồng |
| “`Stream.toList` và `Collectors.toUnmodifiableList` giống nhau vì đều unmodifiable.” | Chúng khác quy tắc null; chọn theo yêu cầu dữ liệu |

## 15. Bài tập có đáp án

### Bài 1 — Dự đoán ngoại lệ

```java
var values = java.util.Arrays.asList("A", null, "B");
var result = values.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

**Đáp án:** `collect(...)` ném `NullPointerException` vì phần tử `null`. Không tạo được `result` chứa `[A, null, B]` như một List hợp lệ từ collector này.

### Bài 2 — Cùng nguồn, API khác nhau

```java
var values = java.util.Arrays.asList("A", null, "B");
var a = values.stream().toList();
// var b = values.stream()
//         .collect(Collectors.toUnmodifiableList());
```

**Đáp án:** `a` là danh sách `[A, null, B]` không cho sửa; nếu bỏ chú thích phần `b`, terminal operation đó ném `NullPointerException`. Cả hai đều có kiểu tĩnh `List<String>`, nên chỉ nhìn kiểu không đủ để suy ra chính sách null.

### Bài 3 — Lọc trước hay sau `map`?

```java
var names = java.util.List.of("A", "B");
var result = names.stream()
        .filter(java.util.Objects::nonNull)
        .map(s -> s.equals("B") ? null : s)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

**Đáp án:** vẫn ném `NullPointerException`. `map` tạo null **sau** bước lọc. Nếu chính sách cho phép bỏ B, lọc null sau `map`; nếu B là dữ liệu bắt buộc, validate và báo lỗi.

### Bài 4 — Giữ nguyên số vị trí

Muốn `["A", null, "B"]` thành `["A", "UNKNOWN", "B"]` và kết quả không cho sửa, viết gì?

**Đáp án:**

```java
var result = values.stream()
        .map(v -> java.util.Objects.requireNonNullElse(v, "UNKNOWN"))
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

Giá trị fallback phải phù hợp nghiệp vụ và khác null.

### Bài 5 — Danh sách kết quả và phần tử mutable

```java
var builder = new StringBuilder("a");
var result = java.util.stream.Stream.of(builder)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
builder.append("b");
```

`result.get(0).toString()` là gì? **Đáp án:** `"ab"`, vì collector không sao chép sâu đối tượng `StringBuilder`. Nhưng `result.add(new StringBuilder("c"))` ném `UnsupportedOperationException`.

### Bài 6 — Tập hợp trùng lặp

```java
var result = java.util.List.of("A", "B", "A")
        .stream()
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

**Đáp án:** `result` là `[A, B, A]`; List giữ hai chữ A. Nếu cần loại trùng, dùng `distinct()` hoặc cân nhắc `Set` và xem lại yêu cầu thứ tự.

### Bài 7 — Stream rỗng

```java
var result = java.util.stream.Stream.<String>empty()
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

**Đáp án:** trả List rỗng `[]` không cho sửa. **Stream rỗng** khác **Stream có một phần tử `null`**.

### Bài 8 — Collector lồng nhau

```java
var result = java.util.List.of("ok", "missing").stream()
        .collect(java.util.stream.Collectors.mapping(
                s -> s.equals("missing") ? null : s,
                java.util.stream.Collectors.toUnmodifiableList()));
```

**Đáp án:** NPE từ việc downstream `toUnmodifiableList` nhận null. `mapping` không tự lọc giá trị vắng mặt.

## 16. Checklist trước khi dùng trong dự án

1. **Nguồn có thể chứa null không?** Kiểm tra List/Map/API thực tế thay vì dựa vào kiểu `String` hoặc `List<T>`.
2. **Các bước `map`/`flatMap` có tạo null không?** Kiểm tra cả downstream `mapping`.
3. **Chính sách null là gì?** Bỏ, thay hoặc từ chối; xác định trước khi viết filter.
4. **Có mất số bản ghi hoặc ý nghĩa vị trí khi bỏ null không?** Nếu có, không tự động lọc.
5. **Cần thông báo lỗi với ID/trường dữ liệu cụ thể không?** Validate trước collector.
6. **Cần danh sách không sửa và cũng không chứa null?** `Collectors.toUnmodifiableList()` phù hợp khi dữ liệu đã tuân theo hợp đồng.
7. **Có cần giữ null trong một danh sách không sửa?** Xem xét `Stream.toList()` hoặc mô hình dữ liệu khác phù hợp thay vì collector này.
8. **Có cần thêm/xóa phần tử kết quả?** Chọn `toCollection(ArrayList::new)` hoặc cấu trúc mutable phù hợp.
9. **Có cần giữ phần tử trùng và thứ tự?** List giữ duplicate, encounter order tùy nguồn; Set có hợp đồng khác.
10. **Phần tử có thể bị sửa không?** List không cho sửa chưa đóng băng object phần tử.
11. **Có dùng parallel Stream không?** Không phụ thuộc thứ tự thực thi của lambda; kết quả có encounter order theo nguồn có thứ tự.
12. **Có đang tái sử dụng một Stream đã collect không?** Nếu có, tạo Stream mới từ nguồn.
13. **Có viết test cho null và danh sách rỗng không?** Kiểm tra cả trường hợp map làm phát sinh null, thao tác sửa List và thứ tự dữ liệu.

**Tóm tắt:** `Collectors.toUnmodifiableList()` (Java 10+) tạo `List<T>` không cho sửa và **từ chối mọi phần tử `null`**. Nó khác `Stream.toList()` ở hợp đồng null, khác `Collectors.toList()` ở bảo đảm unmodifiable, và khác `List.copyOf()` ở hình thức đầu vào Collector/Stream so với Collection. Xử lý null đúng là **quyết định về dữ liệu**: chọn bỏ, thay hoặc báo lỗi theo nghiệp vụ, kiểm soát cả các bước biến đổi trước terminal operation, và không nhầm tính không cho sửa của List với tính bất biến sâu của phần tử.