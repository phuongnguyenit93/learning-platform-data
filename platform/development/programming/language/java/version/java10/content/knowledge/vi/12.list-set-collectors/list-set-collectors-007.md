# Quy tắc null của `Collectors.toUnmodifiableSet()`

**Chủ đề:** Collector danh sách và tập — Java 10 trở lên.

`Collectors.toUnmodifiableSet()` là collector tạo ra một `Set` **không cho phép sửa đổi** từ các phần tử của `Stream`. Quy tắc rất quan trọng: **collector này không chấp nhận `null` và sẽ ném `NullPointerException` nếu được cung cấp một phần tử `null`**. Điều này vẫn đúng với Java hiện đại, kể cả khi nguồn `Stream`, một lời gọi `map` hay một hàm tra cứu trả về `null` ngoài dự kiến.

Bài học tập trung vào nguồn gốc lỗi null, vị trí xử lý trong pipeline, lựa chọn loại bỏ/thay thế/từ chối null, và các khác biệt dễ nhầm với `Collectors.toSet()`, `Set.of` và `Set.copyOf`. Các ví dụ độc lập được biên dịch và chạy bằng Java 10 source level; không dùng API đã lỗi thời.

## 1. Cơ chế và hợp đồng của `toUnmodifiableSet`

Cách dùng cơ bản:

~~~java
Set<String> tags = Stream.of("java", "api", "java")
        .collect(Collectors.toUnmodifiableSet());
~~~

Đây là **đoạn mã đặt trong một phương thức**, giả sử đã import `java.util.Set`, `java.util.stream.Stream` và `java.util.stream.Collectors`.

Dòng trên tạo một `Set<String>` có hai phần tử phân biệt là `"java"` và `"api"`. Kết quả có các đặc điểm:

- **Unmodifiable:** không thể thêm, xóa hay thay đổi tập hợp thông qua reference kết quả. Thao tác `add` hoặc `remove` không được hỗ trợ và ném `UnsupportedOperationException` trong những tình huống sửa đổi.
- **Non-null:** không có phần tử `null`. Nếu pipeline đưa `null` vào collector, phép thu thập thất bại với `NullPointerException`; collector không tự bỏ qua null.
- **Unique:** phần tử bằng nhau theo `equals` được gộp. Nếu có nhiều đối tượng bằng nhau nhưng khác reference/trạng thái phụ, một phần tử **bất kỳ** trong nhóm trùng có thể được giữ; không có cam kết giữ phần tử đầu tiên hay cuối cùng.
- **Unordered:** collector được đặc tả là *unordered*. Không dựa vào thứ tự xuất hiện, `iterator()`, `forEach` hoặc `toString()` của set để suy ra thứ tự của `Stream` ban đầu.
- **Không deep-copy phần tử:** `Set` không sửa được vẫn có thể chứa object mutable; trạng thái bên trong phần tử không tự được đóng băng.

`Collectors.toUnmodifiableSet()` được giới thiệu trong **Java 10**. Đây là API hiện hành, không phải collector đã bị bỏ hoặc được thay thế vì lỗi thời.

### Lỗi null xảy ra ở bước nào?

Một pipeline có thể chứa `null` mà chưa lỗi ngay khi khai báo. Với Stream, các phép trung gian như `map`, `filter` thường là lazy. Khi chạy terminal operation `collect(Collectors.toUnmodifiableSet())`, collector nhận dữ liệu và phát hiện có `null`, việc thu thập ném `NullPointerException`.

~~~java
Stream<String> stream = Stream.of("a", null, "b");

// Lỗi xuất hiện khi thực thi terminal collect:
Set<String> result = stream.collect(Collectors.toUnmodifiableSet());
~~~

Đây là **đoạn minh họa**; không chạy riêng ngoài class/method. Không nên phụ thuộc vào stack trace cụ thể hay giả định chính xác implementation kiểm tra null ở accumulator hay finisher: **hợp đồng được bảo đảm là collector từ chối null**.

## 2. Null có thể đến từ đâu?

Nguồn phổ biến trong chương trình thật:

| Nguồn dữ liệu | Ví dụ | Rủi ro |
| --- | --- | --- |
| Collection có phần tử null | `Arrays.asList("java", null, "api").stream()` | Collector gặp null dù source collection chấp nhận nó |
| `Stream.of` với null | `Stream.of("a", null, "b")` | `Stream.of` không tự loại null |
| Mapper trả null | `stream.map(x -> lookup(x))`, trong đó `lookup` có thể trả null | Dữ liệu nguồn ban đầu hợp lệ nhưng pipeline tạo null ở giữa |
| Kết quả tra cứu không tìm thấy | `map.get(key)` có thể trả `null` khi thiếu key | Null đi tiếp vào collector nếu không được xử lý |
| Dữ liệu bên ngoài chưa chuẩn hóa | Giá trị trường tùy chọn từ JSON, database, form | Có thể có null dù mô hình nghiệp vụ mong đợi tập hợp toàn giá trị |
| Branch của biểu thức điều kiện | `map(x -> valid(x) ? x : null)` | Không phải filter: nhánh else **đưa null** xuống dưới |

Điểm dễ bỏ sót: **lọc null trước `map` chưa chắc đủ**. Nếu `map` có thể tạo null, cần lọc sau mapper hoặc xử lý null ngay trong mapper.

Ví dụ:

~~~java
// Chưa đủ nếu lookupNullable có thể trả null:
source.stream()
        .filter(Objects::nonNull)
        .map(this::lookupNullable)
        .collect(Collectors.toUnmodifiableSet());

// Đúng hơn nếu chính mapper có thể trả null:
source.stream()
        .filter(Objects::nonNull)
        .map(this::lookupNullable)
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableSet());
~~~

Hai pipeline là **mã minh họa bên trong instance method** với `source` và `lookupNullable` được định nghĩa trong ứng dụng. `this::lookupNullable` không phải method có sẵn của Java. Hãy đặt bước xử lý null **sau bước cuối cùng có thể tạo null**, hoặc thay thiết kế để mapper không trả null.

## 3. Chương trình chạy được: collector từ chối null

Lưu đúng tên **`NullRejectDemo.java`**:

~~~java
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NullRejectDemo {
    static void test(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=accepted");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        test("source-null", () ->
                Stream.of("java", null, "api")
                        .collect(Collectors.toUnmodifiableSet()));

        test("mapped-null", () ->
                Stream.of("java", "bad")
                        .map(x -> "bad".equals(x) ? null : x)
                        .collect(Collectors.toUnmodifiableSet()));

        test("single-null", () ->
                Stream.<String>of((String) null)
                        .collect(Collectors.toUnmodifiableSet()));

        Set<String> empty = Stream.<String>empty()
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("empty-size=" + empty.size());

        Set<String> safe = Stream.of("java", "api")
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("safe-size=" + safe.size());

        try {
            safe.add("extra");
        } catch (UnsupportedOperationException expected) {
            System.out.println("add=UnsupportedOperationException");
        }
    }
}
~~~

Biên dịch và chạy bằng một JDK hỗ trợ `--release 10`:

~~~bash
javac --release 10 NullRejectDemo.java
java NullRejectDemo
~~~

**Stdout chính xác:**

~~~text
source-null=NullPointerException
mapped-null=NullPointerException
single-null=NullPointerException
empty-size=0
safe-size=2
add=UnsupportedOperationException
~~~

Điểm rút ra:

1. `source-null`: trong `Stream.of("java", null, "api")` đã có một phần tử null; collector ném `NullPointerException`.
2. `mapped-null`: dữ liệu ban đầu toàn chuỗi khác null, nhưng biểu thức `map` trả null cho `"bad"`; collector vẫn từ chối.
3. `single-null`: ngay cả khi toàn bộ stream chỉ có một null, không có ngoại lệ “tập chỉ có một phần tử”; kết quả vẫn là `NullPointerException`.
4. `empty`: không có phần tử thì không có null để từ chối. Kết quả là set rỗng, kích thước 0.
5. `safe`: các chuỗi hợp lệ được thu thành set không sửa được. Thử thêm qua `add` ném **`UnsupportedOperationException`**, đây là ngoại lệ khác với lỗi null khi thu thập.

`Stream.<String>of((String) null)` chủ động chỉ rõ kiểu `String` và ép đối số null để tránh nhầm lẫn với các cách gọi varargs. Trong thực tế, nên tránh nguồn null hoặc xử lý nó theo hợp đồng dữ liệu.

## 4. Ba chiến lược xử lý null trước `collect`

Không có một cách xử lý duy nhất cho mọi ứng dụng. Quyết định **ý nghĩa nghiệp vụ** của null trước:

- Null nghĩa là “không có phần tử” → **lọc bỏ**.
- Null nghĩa là “thiếu dữ liệu nhưng có giá trị thay thế hợp lệ” → **đưa về mặc định**.
- Null biểu thị dữ liệu không hợp lệ → **từ chối rõ ràng**, để lỗi không bị che mất.

### A. Bỏ các phần tử null

~~~java
Set<String> result = source.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableSet());
~~~

Đây là đoạn minh họa; giả sử `source` là `Collection<String>` hoặc `List<String>`, đã import `Set`, `Objects` và `Collectors`. `Objects::nonNull` chỉ giữ giá trị khác null; kết quả `Set` sẽ không chứa null. Thích hợp với các giá trị *optional* mà việc vắng mặt hoàn toàn được chấp nhận.

Nếu cần chuẩn hóa chuỗi, đặt thao tác an toàn sau khi lọc:

~~~java
Set<String> normalized = source.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(text -> !text.isEmpty())
        .collect(Collectors.toUnmodifiableSet());
~~~

`String::trim` sẽ ném `NullPointerException` nếu được gọi trên null; đặt `filter(Objects::nonNull)` trước bước đó giúp tránh lỗi. Lọc chuỗi rỗng là quy tắc nghiệp vụ bổ sung, không phải yêu cầu của collector.

### B. Thay null bằng giá trị mặc định

~~~java
Set<String> result = source.stream()
        .map(value -> Objects.requireNonNullElse(value, "unknown"))
        .collect(Collectors.toUnmodifiableSet());
~~~

`Objects.requireNonNullElse` có từ Java 9; nếu `value` null thì dùng `"unknown"`. Giá trị mặc định cũng **phải khác null**. Khi nhiều phần tử null được thay bằng cùng một chuỗi, `Set` sẽ gộp các giá trị `"unknown"` trùng nhau.

Chỉ dùng phương án này nếu giá trị mặc định có ý nghĩa. Nếu `null` phản ánh dữ liệu chưa được xác minh, thay bằng một tag hợp lệ có thể làm sai dữ liệu.

### C. Báo lỗi rõ và sớm

~~~java
Set<String> result = source.stream()
        .map(value -> Objects.requireNonNull(value, "tag must not be null"))
        .collect(Collectors.toUnmodifiableSet());
~~~

Nếu gặp null, `Objects.requireNonNull` ném `NullPointerException` có thông báo rõ do chương trình cung cấp. Cách này phù hợp khi dữ liệu không được phép thiếu và nhà phát triển muốn chỉ ra invariant bị vi phạm ngay trong pipeline.

Nếu cần thông báo có ID, vị trí hoặc mã lỗi domain, dùng vòng lặp kiểm tra đầu vào trước khi stream, hoặc một lớp exception domain thích hợp. Không nhất thiết phải đợi collector ném lỗi chung mới chẩn đoán.

### D. Khi mapper trả null, lọc ở phía sau

~~~java
Set<String> result = Stream.of("ok", "missing")
        .map(s -> "missing".equals(s) ? null : s)
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableSet());
~~~

Đoạn này hợp lệ trong phương thức với các import tương ứng. Kết quả chứa đúng `"ok"` và không lỗi, vì null do `map` tạo đã bị loại trước khi collector nhận nó.

## 5. Chương trình chạy được: lọc, thay thế và validate

Lưu đúng tên **`NullHandlingDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NullHandlingDemo {
    public static void main(String[] args) {
        List<String> raw = Arrays.asList("  java  ", null, "api", " java ", " ");

        Set<String> cleaned = raw.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("cleaned=" + new TreeSet<>(cleaned));

        Set<String> fallback = Stream.of("java", null, "api", null)
                .map(s -> Objects.requireNonNullElse(s, "unknown"))
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("fallback=" + new TreeSet<>(fallback));

        try {
            raw.stream()
                    .map(s -> Objects.requireNonNull(s, "tag must not be null"))
                    .collect(Collectors.toUnmodifiableSet());
        } catch (NullPointerException expected) {
            System.out.println("validate=" + expected.getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 NullHandlingDemo.java
java NullHandlingDemo
~~~

**Stdout chính xác:**

~~~text
cleaned=[api, java]
fallback=[api, java, unknown]
validate=tag must not be null
~~~

Giải thích:

- `cleaned` loại null, bỏ khoảng trắng thừa, bỏ chuỗi rỗng và gộp hai giá trị `"java"` thành một phần tử.
- `fallback` biến hai null thành cùng `"unknown"`; vì đây là Set, chỉ còn một `"unknown"`.
- `validate` không âm thầm bỏ dữ liệu thiếu mà ném ngoại lệ có thông điệp do người viết xác định.
- Để có stdout **ổn định**, chương trình bọc set thành `new TreeSet<>(...)` **chỉ khi in**. Điều này **không** có nghĩa kết quả của `toUnmodifiableSet` đã được sắp xếp hoặc có thứ tự duyệt được bảo đảm. Không dùng thứ tự `Set` nguyên gốc làm tiêu chí kiểm thử.

## 6. Phân biệt `toUnmodifiableSet` với các factory và collector liên quan

Các API dưới đây có thể cùng tạo ra `Set`, nhưng **quy tắc null, phần tử trùng và khả năng sửa đổi** không giống nhau:

| API | Phần tử null | Phần tử trùng theo `equals` | Có cho phép sửa kết quả không? |
| --- | --- | --- | --- |
| `Collectors.toUnmodifiableSet()` (Java 10+) | **Ném `NullPointerException`** khi collector nhận null | Gộp; giữ một phần tử bất kỳ của nhóm trùng | Không |
| `Set.of(...)` (Java 9+) | **Ném `NullPointerException`** | **Ném `IllegalArgumentException`** khi tạo từ các đối số trùng | Không |
| `Set.copyOf(collection)` (Java 10+) | **Ném `NullPointerException`** khi collection có null | Gộp; giữ phần tử bất kỳ trong các phần tử bằng nhau | Không |
| `Collectors.toSet()` | Không có bảo đảm giống `toUnmodifiableSet` về việc cho phép null | Gộp theo hợp đồng Set | Không bảo đảm mutability hoặc lớp triển khai |
| `Collectors.toCollection(HashSet::new)` | `HashSet` chấp nhận một phần tử null | Gộp theo `HashSet` | Có thể sửa vì kết quả cụ thể là `HashSet` |
| `Collectors.toUnmodifiableList()` (Java 10+) | **Ném `NullPointerException`** | Vẫn giữ các phần tử trùng trong List | Không |
| `Collections.unmodifiableSet(existing)` | Có thể bao bọc set vốn chứa null; không tự loại null | Phụ thuộc backing Set | Không sửa qua view, nhưng source có thể thay đổi |

**Không dùng `Collectors.toSet()` như một “lối tắt chắc chắn chấp nhận null”.** Đặc tả của `toSet` không hứa kiểu `Set` cụ thể, tính sửa đổi, khả năng tuần tự hóa hoặc an toàn luồng; không dựa vào tình cờ implementation hiện tại sử dụng `HashSet`. Nếu nghiệp vụ **chủ động yêu cầu** set mutable có thể chứa null, `Collectors.toCollection(HashSet::new)` diễn đạt lựa chọn implementation rõ ràng hơn. Nếu muốn set bất biến và không nhận null, `toUnmodifiableSet` chính là lựa chọn thích hợp.

### Phần tử trùng không phải `null`

Với dữ liệu hợp lệ:

~~~java
Set<String> values = Stream.of("alpha", "alpha", "beta")
        .collect(Collectors.toUnmodifiableSet());
~~~

kết quả có **hai** phần tử phân biệt. Đây là thao tác dedup bình thường, không ném `IllegalArgumentException` như `Set.of("alpha", "alpha")`.

Nếu các object khác reference nhưng `equals` trả `true`, một object bất kỳ trong nhóm có thể được giữ. Không dựa vào “giữ lần xuất hiện đầu tiên”, đặc biệt khi stream có xử lý song song hoặc các object bằng nhau theo khóa định danh nhưng có payload khác. Nếu cần quy tắc ưu tiên chính xác, dùng giải pháp gom nhóm/merge có hợp đồng rõ ràng.

### Chú ý với cấu trúc dữ liệu mutable

Kết quả của `toUnmodifiableSet` không cho `add`/`remove`, nhưng các phần tử là object mutable vẫn có thể bị thay đổi từ bên ngoài. Nếu `equals` hoặc `hashCode` của phần tử phụ thuộc vào trạng thái có thể sửa, hành vi membership/lookup của Set có thể không còn như mong muốn. Nên ưu tiên phần tử có định danh ổn định hoặc immutable value object.

## 7. Ví dụ chạy được: so sánh duplicate/null giữa các API

Lưu tên **`SetFactoryContrastDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class SetFactoryContrastDemo {
    static void test(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=accepted");
        } catch (RuntimeException expected) {
            System.out.println(label + "=" + expected.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Set<String> collected = Stream.of("alpha", "alpha", "beta")
                .collect(Collectors.toUnmodifiableSet());
        System.out.println("dedup-size=" + collected.size());
        System.out.println("contains-alpha=" + collected.contains("alpha"));

        test("Set.of-duplicate", () -> Set.of("a", "a"));
        test("Set.of-null", () -> Set.of((String) null));
        test("Set.copyOf-null", () -> Set.copyOf(Arrays.asList("a", null)));
        System.out.println("copyOf-duplicate-size=" +
                Set.copyOf(Arrays.asList("a", "a")).size());

        Set<String> nullableMutable = Stream.of("a", null)
                .collect(Collectors.toCollection(HashSet::new));
        System.out.println("explicit-null=" + nullableMutable.contains(null));
        nullableMutable.add("b");
        System.out.println("explicit-size=" + nullableMutable.size());
    }
}
~~~

Chạy:

~~~bash
javac --release 10 SetFactoryContrastDemo.java
java SetFactoryContrastDemo
~~~

Stdout:

~~~text
dedup-size=2
contains-alpha=true
Set.of-duplicate=IllegalArgumentException
Set.of-null=NullPointerException
Set.copyOf-null=NullPointerException
copyOf-duplicate-size=1
explicit-null=true
explicit-size=3
~~~

Chương trình phân biệt rõ bốn vấn đề:

1. `toUnmodifiableSet` **gộp** các chuỗi trùng `"alpha"`; không ném lỗi vì duplicate.
2. `Set.of("a", "a")` **từ chối phần tử trùng** bằng `IllegalArgumentException` ngay khi tạo.
3. `Set.of` và `Set.copyOf` cũng **từ chối null** bằng `NullPointerException`.
4. `Set.copyOf(Arrays.asList("a", "a"))` **gộp phần tử trùng**, kích thước 1. Cách xử lý duplicate này gần với collector hơn so với `Set.of`.
5. `toCollection(HashSet::new)` tạo ra set mutable cụ thể. `HashSet` chấp nhận một `null` và cho phép thêm `"b"`, nhưng **không phải** thay thế tương đương cho một set không sửa được, non-null.

Lưu ý: các kiểm thử cố ý in kích thước và `contains`, không dựa vào thứ tự duyệt từ `toUnmodifiableSet`, `Set.copyOf` hay `Set.of`.

## 8. Lỗi thường gặp khi xử lý null trong pipeline

### Lỗi A — Nghĩ collector tự bỏ qua null

~~~java
// SAI nếu dữ liệu có null:
var tags = values.stream()
        .collect(Collectors.toUnmodifiableSet());
~~~

Nếu `values` là `List` chứa null, kết quả không phải set đã loại null; phép `collect` ném `NullPointerException`. Muốn bỏ null cần viết rõ `filter(Objects::nonNull)`.

### Lỗi B — Chỉ lọc null trước một mapper có thể trả null

~~~java
// Chưa an toàn khi resolve có thể trả null:
var tags = values.stream()
        .filter(Objects::nonNull)
        .map(this::resolve)
        .collect(Collectors.toUnmodifiableSet());
~~~

`resolve` là **phương thức giả định của ứng dụng**, không có sẵn trong Java. Nếu nó trả null khi không tìm thấy dữ liệu, collector vẫn lỗi. Lọc null **sau `map`** hoặc thiết kế `resolve` trả về kiểu/giá trị có hợp đồng non-null.

### Lỗi C — Dùng `distinct()` rồi nghĩ null biến mất

`distinct()` chỉ loại các phần tử trùng theo `equals`; nếu stream có null thì null vẫn có thể còn một phần tử. Ví dụ:

~~~java
// Vẫn có null sau distinct:
Stream.of("a", null, null).distinct()
        .collect(Collectors.toUnmodifiableSet()); // NullPointerException
~~~

Là đoạn minh họa. **Deduplicate không đồng nghĩa với filter non-null**. Muốn bỏ null thì dùng `filter(Objects::nonNull)`.

### Lỗi D — Thay thế null bằng chuỗi rỗng rồi mặc định coi hợp lệ

~~~java
var tags = values.stream()
        .map(value -> Objects.requireNonNullElse(value, ""))
        .collect(Collectors.toUnmodifiableSet());
~~~

Đoạn này không còn null nên có thể thu thập thành công, nhưng có thể tạo **một tag rỗng**, làm sai mô hình dữ liệu. Hãy xác định “không có giá trị” nên **bị loại**, **được biểu diễn bằng giá trị mặc định có nghĩa**, hay **phải báo lỗi**.

### Lỗi E — Nhầm `UnsupportedOperationException` với `NullPointerException`

- `NullPointerException` khi collector gặp phần tử `null`: **đầu vào không hợp lệ** đối với `toUnmodifiableSet`.
- `UnsupportedOperationException` khi cố sửa set kết quả: **thao tác không hỗ trợ** của một unmodifiable set đã được tạo thành công.
- `IllegalArgumentException` từ `Set.of` khi truyền phần tử trùng: **quy tắc riêng của factory `Set.of`**, không phải quy tắc duplicate của `toUnmodifiableSet`.

Bắt nhầm một ngoại lệ khác để “xử lý null” không có tác dụng. Cần kiểm tra đúng bước và đúng API sinh lỗi.

### Lỗi F — Cho rằng set kết quả có thứ tự

Kể cả khi stream ban đầu có encounter order ổn định, `toUnmodifiableSet` là *unordered Collector*. Không dùng `toString()` trực tiếp của Set để viết unit test so sánh chuỗi, vì thứ tự không được bảo đảm. Nếu cần kiểm thử nội dung, so sánh set theo `equals` hoặc kiểm tra `size`/`contains`. Nếu phải in nhất quán, dùng `new TreeSet<>(result)` với phần tử hỗ trợ sắp xếp.

## 9. Cách chọn giải pháp theo yêu cầu ứng dụng

| Yêu cầu thực tế | Cách xử lý gợi ý | Cần chú ý |
| --- | --- | --- |
| Trường dữ liệu null nghĩa là “không có tag” | `filter(Objects::nonNull)` trước `toUnmodifiableSet` | Nếu mapper ở sau còn sinh null thì lọc sau mapper |
| Null là lỗi hợp đồng dữ liệu | `Objects.requireNonNull(value, "...")` hoặc validation đầu vào | Tránh âm thầm bỏ dữ liệu thiếu |
| Null cần thay bằng tag mặc định có nghĩa | `Objects.requireNonNullElse(value, defaultTag)` | Tag mặc định phải non-null, hợp lệ theo domain; các giá trị trùng sẽ gộp |
| Cần Set không sửa được và không chứa null | `collect(Collectors.toUnmodifiableSet())` | Collector vẫn từ chối null; cần chuẩn hóa upstream |
| Cần set có thể thêm/xóa và cố ý cho phép null | `collect(Collectors.toCollection(HashSet::new))` | Kết quả mutable, khác hợp đồng `toUnmodifiableSet` |
| Có collection sẵn, muốn set không sửa được | `Set.copyOf(collection)` | Vẫn ném NPE nếu nguồn có null; gộp duplicate |
| Biết sẵn các phần tử không trùng tại code | `Set.of(a, b, ...)` | Null bị từ chối; duplicate ném IAE |
| Cần giữ thứ tự và giữ duplicate | Xem `List` và collector phù hợp | `toUnmodifiableList` cũng từ chối null nhưng giữ duplicate và encounter order |
| Cần quy tắc cụ thể để chọn object trong nhóm bằng nhau | Thiết kế bước merge/chọn rõ ràng | `toUnmodifiableSet` không hứa giữ phần tử đầu/cuối |

Một pipeline thực tế nên đọc được như một **hợp đồng dữ liệu**: lấy nguồn → chuẩn hóa → xác định cách xử lý null → lọc giá trị không hợp lệ → thu thành tập không sửa được.

Ví dụ cho danh sách tag nhập từ bên ngoài:

~~~java
Set<String> tags = rawTags.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toUnmodifiableSet());
~~~

Đây là đoạn trong phương thức với `rawTags` là `Collection<String>`. Kết quả không chứa null, không chứa tag rỗng, và không cho thêm/xóa phần tử qua reference trả về. Nếu cần so sánh tag **không phân biệt hoa thường**, thêm bước `map(s -> s.toLowerCase(Locale.ROOT))` với import `Locale`; đó là một quyết định domain riêng, không phải quy tắc của collector.

### Khi nào không nên bỏ null?

Đừng tự động gọi `filter(Objects::nonNull)` trong mọi trường hợp:

- Nếu một mã sản phẩm được phép vắng mặt, việc bỏ null có thể phù hợp.
- Nếu một bản ghi bắt buộc có mã sản phẩm nhưng source lại trả null, việc bỏ nó âm thầm sẽ làm **mất dữ liệu và che lỗi**; nên validation.
- Nếu null mang ý nghĩa riêng (ví dụ “không xác định”), có thể dùng một **giá trị mô hình rõ ràng** hoặc kiểu `Optional` tại boundary phù hợp, thay vì đẩy null thẳng vào collector non-null.

Điểm cần kiểm soát là **ngữ nghĩa dữ liệu**; `toUnmodifiableSet` chỉ thực thi một quy tắc kỹ thuật: không chấp nhận phần tử null.

## 10. Thiết kế kiểm thử cho `toUnmodifiableSet`

Để bảo vệ mã trước regression khi dữ liệu/mapper thay đổi, kiểm thử ít nhất:

1. **Dữ liệu bình thường:** có 2–3 chuỗi khác nhau → set có đúng các phần tử, không cần dựa vào iteration order.
2. **Null từ nguồn:** `Stream` có một null → `collect` phải ném `NullPointerException`.
3. **Null do mapper tạo:** nguồn không có null nhưng mapper trả null → vẫn ném `NullPointerException`.
4. **Xử lý null đã chọn:** `filter` bỏ null hoặc `requireNonNullElse` thay null → không còn null trong set; kiểm tra nội dung bằng membership.
5. **Phần tử trùng:** chuỗi xuất hiện nhiều lần → đúng một phần tử theo `equals`; không mong ném `IllegalArgumentException`.
6. **Unmodifiable:** thử `add`/`remove` để xác nhận thao tác không được hỗ trợ.
7. **Input rỗng:** `Stream.empty()` → set rỗng, không phát sinh NPE.
8. **Thứ tự không cố định:** không assert trực tiếp chuỗi được tạo từ `Set.toString()` nếu chứa nhiều phần tử.
9. **Giá trị domain không hợp lệ:** nếu dữ liệu không cho phép chuỗi rỗng, khoảng trắng hoặc mã chưa chuẩn hóa, kiểm tra bước làm sạch riêng thay vì đổ hết trách nhiệm cho collector.

Với unit test dùng JUnit, có thể dùng `assertThrows(NullPointerException.class, () -> stream.collect(Collectors.toUnmodifiableSet()))`; đoạn này cần thêm thư viện JUnit tương ứng. Các chương trình trong bài dùng Java thuần để có thể chạy mà không cần dependency ngoài.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `Stream.of("a", null, "b").collect(Collectors.toUnmodifiableSet())` trả set chứa gì?

**Câu 2.** `Stream.of("a", "a").collect(Collectors.toUnmodifiableSet())` ném `IllegalArgumentException` hay cho một phần tử?

**Câu 3.** Lọc null trước một mapper có thể trả null đã đủ bảo đảm không lỗi chưa?

**Câu 4.** Nếu việc null xảy ra là lỗi nghiệp vụ, nên dùng `filter(Objects::nonNull)` hay validation?

**Câu 5.** `Collectors.toSet()` có hứa kết quả luôn là `HashSet` có thể chứa null và sửa được không?

**Câu 6.** `Set.of("a", "a")` khác `toUnmodifiableSet` xử lý duplicate như thế nào?

**Câu 7.** Với `Stream.of("a", null, null).distinct()`, gọi `collect(Collectors.toUnmodifiableSet())` có an toàn không?

**Câu 8.** Nếu nhiều null được chuyển thành `"unknown"` trước khi collect, trong set có bao nhiêu phần tử `"unknown"`?

**Đáp án:**

1. Không trả set; ném `NullPointerException` vì collector nhận null.
2. Một phần tử `"a"`; duplicates được gộp.
3. Chưa; cần bảo đảm đầu ra cuối cùng trước collector non-null, có thể lọc hoặc validate sau mapper.
4. Validation rõ ràng, tránh làm mất dữ liệu không hợp lệ.
5. Không; đặc tả không bảo đảm kiểu triển khai hay mutability của `toSet`.
6. `Set.of` ném `IllegalArgumentException` khi nhận phần tử trùng, còn `toUnmodifiableSet` gộp trùng.
7. Không; `distinct` không loại tất cả null, collector vẫn ném NPE.
8. Một phần tử `"unknown"` vì Set chỉ giữ một giá trị cho các phần tử bằng nhau.

## 12. Tài liệu đặc tả hiện hành

- **Oracle Javadoc `Collectors.toUnmodifiableSet` (Java 26):** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableSet()
- **Oracle Javadoc `Collectors.toSet` và `toCollection`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html
- **Oracle Javadoc `Set`, `Set.of` và `Set.copyOf`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html
- **Oracle Java Collections Guide — Unmodifiable Collections:** https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html
- **Java 10 Javadoc `Collectors.toUnmodifiableSet` (mốc giới thiệu):** https://docs.oracle.com/javase/10/docs/api/java/util/stream/Collectors.html

**Ghi nhớ:** `Collectors.toUnmodifiableSet()` **không bỏ qua null**. Nếu bất kỳ phần tử nào đi tới collector là null — ngay từ nguồn hoặc do mapper tạo ra — phép thu thập ném `NullPointerException`. Hãy quyết định **lọc bỏ, thay thế hay báo lỗi** dựa trên hợp đồng dữ liệu, rồi mới thu về một set không sửa được; đừng nhầm null với duplicate hay với thao tác sửa `Set` sau khi tạo.