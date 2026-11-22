# Loại trùng dữ liệu nhưng giữ thứ tự xuất hiện trong Java Collections

## 1. Bài toán và tiêu chí đúng

Cho một dãy phần tử có thể lặp lại, hãy loại các phần tử trùng nhau nhưng **giữ nguyên thứ tự xuất hiện lần đầu** của từng phần tử. Kết quả chứa mỗi giá trị logic đúng một lần, tại vị trí tương ứng với lần đầu giá trị đó xuất hiện trong dữ liệu nguồn.

Ví dụ:

```text
Đầu vào: [Java, SQL, Java, null, Go, SQL, null, Kotlin, Go]
Đầu ra: [Java, SQL, null, Go, Kotlin]
```

Trong ví dụ này, `Java` thứ hai, `SQL` thứ hai, `null` thứ hai và `Go` thứ hai bị bỏ. `null` đầu tiên vẫn tồn tại nếu bộ sưu tập và chính sách nghiệp vụ cho phép giá trị `null`.

Cần phân biệt ba yêu cầu thường bị nhầm lẫn:

- **Không trùng:** mỗi nhóm phần tử được xem là bằng nhau chỉ xuất hiện một lần.
- **Giữ thứ tự:** nếu lần đầu `A` đứng trước lần đầu `B` thì `A` vẫn đứng trước `B` trong kết quả.
- **Giữ bản ghi đầu tiên:** khi hai đối tượng có cùng khóa nhưng thuộc tính khác nhau, kết quả lấy đối tượng xuất hiện trước, trừ khi đề bài yêu cầu quy tắc khác.

Đây là bài thực hành Java Collections. Chọn cấu trúc dữ liệu phụ thuộc vào việc cần trả về `List`, `Set`, có được sửa dữ liệu đầu vào hay không, và khái niệm “trùng” là theo toàn bộ đối tượng hay theo một khóa nghiệp vụ.

## 2. Cách đơn giản: `LinkedHashSet`

`LinkedHashSet` là tập hợp loại bỏ phần tử trùng theo `equals()` và `hashCode()`, đồng thời duy trì **thứ tự chèn** khi duyệt. Khi một phần tử đã có trong tập hợp được thêm lại, tập hợp không tạo phần tử mới và không dời vị trí của phần tử cũ.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;

public class LinkedHashSetDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                "Java", "SQL", "Java", null, "Go",
                "SQL", null, "Kotlin", "Go"
        );

        List<String> unique = new ArrayList<>(new LinkedHashSet<>(input));

        System.out.println("Input : " + input);
        System.out.println("Unique: " + unique);
    }
}
```

Lưu thành `LinkedHashSetDemo.java`; chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 LinkedHashSetDemo.java
java LinkedHashSetDemo
```

Kết quả:

```text
Input : [Java, SQL, Java, null, Go, SQL, null, Kotlin, Go]
Unique: [Java, SQL, null, Go, Kotlin]
```

Giải thích:

1. Bộ khởi tạo `new LinkedHashSet<>(input)` duyệt các phần tử của `input` và lần lượt thử thêm vào tập hợp.
2. Lần đầu gặp một giá trị, tập hợp lưu nó; các lần gặp tiếp theo mà `equals()` xác định bằng nhau sẽ không được thêm.
3. `LinkedHashSet` giữ thứ tự chèn, nên lần duyệt tập hợp cho thứ tự lần đầu xuất hiện.
4. `new ArrayList<>(...)` trả kết quả về kiểu `List` khi cần truy cập theo chỉ số hoặc tương thích API nhận `List`.

Nếu đầu ra có thể là `Set`, chỉ cần giữ `LinkedHashSet`:

```java
LinkedHashSet<String> uniqueSet = new LinkedHashSet<>(input);
```

`LinkedHashSet` cho phép một phần tử `null`; tuy nhiên `List.of(...)` không cho phép phần tử `null` ngay từ lúc khởi tạo. Vì vậy ví dụ dùng `Arrays.asList(...)`. Cách trên tạo một bộ sưu tập mới, không sửa `input`.

### Vì sao không dùng `HashSet` hoặc `TreeSet` để lấy kết quả trực tiếp?

- `HashSet` loại trùng nhưng **không cam kết thứ tự duyệt**. Một kết quả trông như đúng thứ tự trong một lần chạy không phải là bảo đảm của API.
- `TreeSet` sắp xếp theo thứ tự tự nhiên hoặc `Comparator`, không giữ thứ tự gặp đầu tiên. Nó còn có điều kiện bổ sung về khả năng so sánh, và cách nhận diện trùng dựa trên so sánh `compare(...) == 0`.
- `LinkedHashSet` đáp ứng đồng thời yêu cầu không trùng và giữ thứ tự chèn. Đừng dùng mã kiểu `new ArrayList<>(new HashSet<>(input))` nếu đầu ra bắt buộc giữ nguyên thứ tự.

## 3. Cách duyệt một lần: `HashSet` đánh dấu + `ArrayList` kết quả

Nếu muốn giải thích rõ thuật toán, hoặc cần điều kiện giữ/bỏ tùy chỉnh, hãy duyệt đầu vào từ trái sang phải, dùng một `Set` để đánh dấu giá trị đã gặp, và chỉ đưa giá trị vào `List` kết quả ở lần xuất hiện đầu tiên.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class SeenSetDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                "Java", "SQL", "Java", null, "Go",
                "SQL", null, "Kotlin", "Go"
        );
        Set<String> seen = new HashSet<>();
        List<String> unique = new ArrayList<>();

        for (String value : input) {
            if (seen.add(value)) {
                unique.add(value);
            }
        }
        System.out.println(unique);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 SeenSetDemo.java
java SeenSetDemo
```

```text
[Java, SQL, null, Go, Kotlin]
```

`Set.add(value)` trả `true` nếu tập hợp thay đổi vì thêm một phần tử chưa có; trả `false` nếu phần tử đã tồn tại. Đây là phép kiểm tra và đánh dấu trong cùng một thao tác, tránh viết thừa `contains(value)` rồi mới `add(value)`.

Lưu ý: `HashSet` ở đây **không** được duyệt để xây dựng kết quả; nó chỉ giữ thông tin “đã thấy”. Chính `ArrayList` được thêm phần tử theo thứ tự vòng lặp mới quyết định thứ tự đầu ra. Vì vậy sử dụng `HashSet` làm bộ đánh dấu vẫn hoàn toàn đáp ứng yêu cầu giữ thứ tự.

Một cách khác để sửa trực tiếp danh sách **có thể thay đổi**:

```java
List<String> mutable = new ArrayList<>(input);
Set<String> seen = new HashSet<>();
mutable.removeIf(value -> !seen.add(value));
```

`removeIf` loại lần xuất hiện thứ hai trở đi và giữ thứ tự tương đối của các phần tử còn lại. Cách này làm thay đổi `mutable`; không áp dụng trực tiếp cho `List.of(...)` hoặc danh sách cố định kích thước do `Arrays.asList(...)` trả về, vì chúng không hỗ trợ thao tác xóa. Ưu tiên tạo danh sách kết quả mới nếu cần giữ đầu vào nguyên vẹn hoặc muốn mã dễ hiểu.

## 4. Stream API với `distinct()`

Với Java Stream, toán tử `distinct()` loại phần tử trùng dựa trên `Object.equals(Object)`. Với stream **có thứ tự** (ordered stream), `distinct()` giữ phần tử đầu tiên trong mỗi nhóm trùng nhau theo encounter order, tức thứ tự mà nguồn dữ liệu đưa phần tử vào stream.

```java
import java.util.Arrays;
import java.util.List;

public class StreamDistinctDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                "Java", "SQL", "Java", null, "Go",
                "SQL", null, "Kotlin", "Go"
        );

        List<String> unique = input.stream()
                .distinct()
                .toList();

        System.out.println(unique);
    }
}
```

```bash
javac -encoding UTF-8 StreamDistinctDemo.java
java StreamDistinctDemo
```

```text
[Java, SQL, null, Go, Kotlin]
```

Các điểm cần nhớ:

- `List.stream()` là stream có thứ tự theo trình tự duyệt danh sách. Với nguồn này, `distinct()` giữ lần xuất hiện đầu.
- `Stream.toList()` có từ Java 16 và trả về `List` **không thể sửa**; gọi `add` hoặc `remove` trên kết quả sẽ ném `UnsupportedOperationException`. Nếu cần danh sách thay đổi được, dùng `new ArrayList<>(input.stream().distinct().toList())` hoặc `collect(Collectors.toCollection(ArrayList::new))`.
- `stream().unordered()` bỏ yêu cầu bảo toàn encounter order. Trên stream không có thứ tự, đừng dựa vào việc phần tử nào được giữ trong một nhóm trùng hoặc thứ tự đầu ra.
- `parallelStream().distinct()` trên stream có thứ tự vẫn phải bảo đảm tính ổn định của `distinct`, nhưng việc phối hợp để giữ thứ tự có thể tốn bộ nhớ và chi phí đồng bộ; không mặc định song song sẽ nhanh hơn.
- `distinct()` không nhận hàm trích xuất khóa. Nếu “trùng” dựa trên `id`, `email` hoặc quy tắc chuẩn hóa riêng thì cần thuật toán theo khóa như phần tiếp theo.

## 5. Trùng đối tượng: `equals()`, `hashCode()` và khóa nghiệp vụ

Với phần tử kiểu đối tượng, “trùng” phụ thuộc vào cách định nghĩa sự bằng nhau. `HashSet`, `LinkedHashSet` dùng `equals()` và `hashCode()`: nếu hai đối tượng bằng nhau theo `equals()`, chúng **phải** có cùng `hashCode()`. Nếu lớp tự định nghĩa một trong hai phương thức mà không tuân thủ hợp đồng chung, bộ sưu tập dựa trên hash có thể hoạt động sai.

Ví dụ `record` trong Java tự sinh `equals()` và `hashCode()` dựa trên các thành phần khai báo. Hai `Employee` có cùng `id` nhưng khác `name` vẫn **khác nhau** nếu dùng bình đẳng mặc định của record. Để loại trùng theo `id` mà vẫn giữ bản ghi đầu tiên, hãy tách rõ khóa nghiệp vụ khỏi bình đẳng của toàn đối tượng.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.function.Function;

public class DistinctByKeyDemo {
    record Employee(long id, String name) {}

    static <T, K> List<T> distinctByKey(
            Iterable<T> items,
            Function<? super T, ? extends K> keyExtractor) {
        Objects.requireNonNull(items, "items");
        Objects.requireNonNull(keyExtractor, "keyExtractor");

        Set<K> seenKeys = new HashSet<>();
        List<T> result = new ArrayList<>();

        for (T item : items) {
            K key = keyExtractor.apply(item);
            if (seenKeys.add(key)) {
                result.add(item);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee(1, "An"),
                new Employee(2, "Bình"),
                new Employee(1, "An cập nhật"),
                new Employee(3, "Chi"),
                new Employee(2, "Bình mới")
        );

        System.out.println(distinctByKey(employees, Employee::id));
    }
}
```

```bash
javac -encoding UTF-8 DistinctByKeyDemo.java
java DistinctByKeyDemo
```

```text
[Employee[id=1, name=An], Employee[id=2, name=Bình], Employee[id=3, name=Chi]]
```

Thuật toán giữ chính đối tượng đầu tiên của mỗi `id`; bản ghi có cùng `id` nhưng xuất hiện sau bị bỏ dù `name` khác. Hàm nhận `Iterable<T>`, nên cũng dùng được cho `List<T>` hoặc một nguồn có thể duyệt theo thứ tự xác định.

Một số quyết định cần làm rõ trước khi áp dụng:

- **Khóa nào định nghĩa trùng?** Toàn đối tượng, `id`, email đã chuẩn hóa, hay tổ hợp nhiều thuộc tính? Hai quy tắc khác nhau có thể cho kết quả khác nhau.
- **Giữ bản ghi nào?** Bài này giữ **bản ghi đầu tiên**. Nếu yêu cầu giữ bản ghi cuối hoặc gộp thông tin, phải thay đổi thuật toán và nêu rõ thứ tự đầu ra mong muốn.
- **Khóa `null` có hợp lệ không?** `HashSet` chấp nhận một `null`, nên toàn bộ phần tử có khóa `null` sẽ rơi vào cùng một nhóm; hãy kiểm tra/từ chối khóa rỗng trước khi thêm nếu nghiệp vụ không cho phép.
- **Khóa có ổn định không?** Tránh sửa các thuộc tính tham gia `equals()/hashCode()` khi đối tượng đang nằm trong `HashSet`/`LinkedHashSet`. Việc thay đổi hash hoặc bình đẳng sau khi chèn có thể khiến tìm kiếm/loại trùng không còn đúng.
- **Thứ tự nguồn có xác định không?** Nếu duyệt từ một `HashSet` đầu vào, nguồn vốn không cam kết thứ tự; thuật toán chỉ giữ thứ tự mà iterator thực sự cung cấp, không thể khôi phục thứ tự chèn đã mất.

## 6. Chuẩn hóa trước khi xét trùng

Đôi khi `"Java"` và `"java"` được xem là trùng nhau, nhưng vẫn phải giữ đúng cách viết của **lần xuất hiện đầu tiên**. Không cần biến đổi phần tử đưa vào kết quả; chỉ chuẩn hóa **khóa** để so sánh.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class CaseInsensitiveDemo {
    public static void main(String[] args) {
        List<String> input = List.of("Java", "java", "GO", "go", "SQL");

        Set<String> seenKeys = new HashSet<>();
        List<String> unique = new ArrayList<>();

        for (String value : input) {
            String key = value.toLowerCase(Locale.ROOT);
            if (seenKeys.add(key)) {
                unique.add(value);
            }
        }
        System.out.println(unique);
    }
}
```

```bash
javac -encoding UTF-8 CaseInsensitiveDemo.java
java CaseInsensitiveDemo
```

```text
[Java, GO, SQL]
```

`Locale.ROOT` tạo quy tắc lowercase ít phụ thuộc ngôn ngữ/địa phương khi xử lý khóa kỹ thuật. Tuy nhiên việc chuyển sang chữ thường đơn thuần **không phải** chuẩn hóa Unicode hoàn chỉnh cho mọi ngôn ngữ. Nếu dữ liệu có dấu, ký tự tổ hợp, khoảng trắng hoặc email, hãy định nghĩa rõ quy tắc tương đương; tùy yêu cầu có thể cần `trim()`, `Normalizer`, hoặc quy tắc theo miền nghiệp vụ. Đừng tự loại dấu hay bỏ khoảng trắng nếu bài toán không yêu cầu vì có thể gộp nhầm các giá trị khác nhau.

Đầu vào có thể có `null` thì phải đặt chính sách trước khi gọi phương thức trên phần tử, chẳng hạn giữ một `null` riêng hoặc bỏ `null`. Ví dụ trên dùng `List.of` và chỉ chứa chuỗi khác `null`.

## 7. Độ phức tạp và cách chọn

Gọi `n` là số phần tử đầu vào và `u` là số giá trị/khóa khác nhau (`u ≤ n`).

| Phương án | Giữ thứ tự lần đầu? | Thời gian dự kiến | Bộ nhớ phụ | Đặc điểm |
| --- | --- | --- | --- | --- |
| `LinkedHashSet` rồi chuyển `ArrayList` | Có | Trung bình `O(n)` | `O(u)` | Ngắn gọn, giữ nguyên đầu vào, mặc định so theo toàn đối tượng |
| `HashSet` + `ArrayList` khi duyệt | Có | Trung bình `O(n)` | `O(u)` | Linh hoạt về khóa/điều kiện; dễ thấy quy tắc giữ lần đầu |
| `stream().distinct().toList()` trên stream có thứ tự | Có | Thường gần `O(n)` | Phụ thuộc triển khai và số phần tử khác nhau | Diễn đạt gọn; `toList()` không thể sửa |
| Duyệt rồi dùng `result.contains(value)` | Có | Tệ nhất `O(n²)` | `O(u)` | Dễ viết nhưng không phù hợp dữ liệu lớn |

Các ước lượng hash giả định `hashCode()` phân bố đủ tốt và phép tính hash/`equals()` có chi phí hợp lý; không có cam kết rằng mọi đầu vào đều đạt `O(n)` trong mọi tình huống. Bộ nhớ phụ chưa tính bản thân đầu vào, và kết quả `List` có thể tốn thêm `O(u)` ngoài cấu trúc đánh dấu.

Không thể suy ra rằng `LinkedHashSet` luôn nhanh hơn Stream cho mọi cỡ dữ liệu hoặc môi trường; nếu hiệu năng là yêu cầu quan trọng, hãy đo bằng dữ liệu đại diện. Còn trong bài toán thường gặp, `LinkedHashSet` là lựa chọn trực tiếp nhất; khi cần loại trùng **theo khóa nghiệp vụ**, dùng vòng lặp với `seenKeys` và `result`.

## 8. Những lỗi dễ gặp

1. **Dùng `HashSet` làm đầu ra rồi tưởng rằng vẫn giữ thứ tự.** API không đảm bảo điều đó, kể cả khi vài bộ dữ liệu thử cho kết quả “đúng”.
2. **Dùng `TreeSet` trong khi yêu cầu giữ lần xuất hiện đầu.** Thứ tự sắp xếp không phải thứ tự xuất hiện; một `Comparator` trả 0 cho hai đối tượng còn có thể khiến chúng bị xem là trùng.
3. **Không định nghĩa thế nào là “trùng”.** Hai record có cùng `id` nhưng tên khác nhau sẽ không trùng theo `equals` mặc định; đôi khi cần khóa thay vì toàn đối tượng.
4. **Bỏ yêu cầu thứ tự của Stream.** Với `unordered()`, không có bảo đảm giữ phần tử gặp đầu tiên.
5. **Làm biến đổi đầu vào ngoài ý muốn.** `removeIf` là phép sửa danh sách; chỉ dùng khi được phép và danh sách hỗ trợ xóa.
6. **Cố sửa danh sách từ `Stream.toList()`.** Danh sách này không thể thay đổi; tạo `ArrayList` mới nếu cần thao tác tiếp.
7. **Quên xử lý `null`.** `List.of` không chứa được `null`; hàm chuẩn hóa kiểu `value.toLowerCase(...)` cũng không gọi được trên `null`.
8. **Dựa vào thứ tự của nguồn vốn không có thứ tự.** Nếu đầu vào là `HashSet`, không thể khẳng định kết quả giữ “thứ tự ban đầu” theo nghĩa thứ tự dữ liệu được thêm trước đó.
9. **Sử dụng trạng thái `seen` dùng chung giữa nhiều lần gọi.** Nếu không xóa đúng lúc, các lần xử lý sau sẽ mất phần tử hợp lệ; mỗi lượt khử trùng thường cần tập `seen` riêng.
10. **Chạy nhiều luồng cùng thêm vào `HashSet`/`ArrayList` không đồng bộ.** Các bộ sưu tập này không thread-safe. Khi cần xử lý đồng thời, phải thiết kế riêng cách đồng bộ và thứ tự kết quả; không chia vòng lặp tùy tiện.

## 9. Tự kiểm tra bằng ca thử

Một lời giải tốt cần vượt qua nhiều loại đầu vào, không chỉ ví dụ có vài chuỗi:

| Đầu vào | Kết quả cần đạt | Mục đích |
| --- | --- | --- |
| `[]` | `[]` | Danh sách rỗng |
| `[A]` | `[A]` | Một phần tử |
| `[A, A, A]` | `[A]` | Mọi phần tử trùng nhau |
| `[B, A, B, C, A]` | `[B, A, C]` | Không sắp xếp lại |
| `[null, A, null]` | `[null, A]` | Chấp nhận một `null` nếu chính sách cho phép |
| `[Java, java, JAVA]` | `[Java, java, JAVA]` | So sánh chuỗi mặc định có phân biệt hoa/thường |
| `[Java, java, JAVA]` với khóa lowercase | `[Java]` | Trùng theo khóa, giữ cách viết đầu tiên |

Bạn có thể viết phương thức tái sử dụng đơn giản để tự kiểm tra:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;

public class UniqueInOrder {
    static <T> List<T> uniqueInOrder(Collection<? extends T> input) {
        return new ArrayList<>(new LinkedHashSet<>(input));
    }

    public static void main(String[] args) {
        System.out.println(uniqueInOrder(List.of("B", "A", "B", "C", "A")));
        System.out.println(uniqueInOrder(List.<String>of()));
    }
}
```

```bash
javac -encoding UTF-8 UniqueInOrder.java
java UniqueInOrder
```

```text
[B, A, C]
[]
```

`Collection` phù hợp khi đầu vào đã là một bộ sưu tập; tham số `Collection<? extends T>` nhận cả tập phần tử kiểu con của `T`. Kết quả `ArrayList` có thể sửa được. Nếu đối số đầu vào `null`, bộ khởi tạo `LinkedHashSet` sẽ ném `NullPointerException`; tùy yêu cầu API mà chủ động kiểm tra và báo lỗi rõ ràng trước khi gọi.

## 10. Bài tập mở rộng và kết luận

1. Với `List<Integer> [4, 2, 4, 1, 2, 5]`, tạo kết quả `[4, 2, 1, 5]` bằng cả `LinkedHashSet` và vòng lặp dùng `seen`. Giải thích vì sao không cần sắp xếp.
2. Với các bản ghi `(id=1, tên=An)`, `(id=2, tên=Bình)`, `(id=1, tên=An mới)`, loại theo `id` và nêu rõ vì sao vẫn giữ bản ghi `An` đầu tiên.
3. Với dữ liệu văn bản hỗn hợp chữ hoa/thường, định nghĩa hàm chuẩn hóa khóa, rồi chứng minh rằng phần tử được đưa vào kết quả vẫn là bản gốc của lần xuất hiện đầu.

**Quy tắc cốt lõi:** duyệt dữ liệu theo thứ tự đã cho; lần đầu thấy một giá trị hoặc khóa thì giữ, những lần sau thì bỏ. `LinkedHashSet` đóng gói quy tắc này cho bình đẳng mặc định, còn `Set` đánh dấu kết hợp `List` kết quả cho phép áp dụng quy tắc trùng tùy chỉnh mà vẫn giữ thứ tự lần đầu xuất hiện.
