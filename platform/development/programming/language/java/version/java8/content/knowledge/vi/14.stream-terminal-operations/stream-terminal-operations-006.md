# anyMatch, allMatch và noneMatch trong Java Stream

## 1. Ba phép kiểm tra điều kiện trên Stream

Trong Java, `anyMatch`, `allMatch` và `noneMatch` là ba **terminal operations** (thao tác kết thúc) của `java.util.stream.Stream`. Chúng trả về một giá trị `boolean` sau khi kiểm tra các phần tử bằng một `Predicate` (hàm nhận một phần tử và trả về `true`/`false`). Ba phương thức có từ Java 8 và vẫn là API hiện hành trong Java hiện đại.

Mục đích của chúng là trả lời ba câu hỏi khác nhau:

| Phương thức | Câu hỏi | Kết quả `true` khi... | Điều kiện có thể dừng sớm |
| --- | --- | --- | --- |
| `anyMatch(p)` | Có **ít nhất một** phần tử thỏa `p` không? | Tìm thấy ≥ 1 phần tử thỏa | Gặp phần tử đầu tiên cho `p(x) == true` |
| `allMatch(p)` | Có phải **mọi** phần tử đều thỏa `p`? | Không có phần tử nào vi phạm | Gặp phần tử đầu tiên cho `p(x) == false` |
| `noneMatch(p)` | Có phải **không phần tử nào** thỏa `p`? | Không tìm thấy phần tử thỏa | Gặp phần tử đầu tiên cho `p(x) == true` |

Cú pháp:

```java
boolean found = stream.anyMatch(element -> condition);
boolean allValid = stream.allMatch(element -> condition);
boolean noneInvalid = stream.noneMatch(element -> condition);
```

- `p` là `java.util.function.Predicate<? super T>` đối với `Stream<T>`. Có thể truyền lambda (`x -> x > 0`), method reference (`Objects::nonNull`), hoặc một `Predicate` được khai báo riêng.
- Ba phép kiểm tra **không tạo Stream kết quả** và **không trả về phần tử phù hợp**. Nếu cần lấy phần tử, cân nhắc `findFirst`/`findAny` và xử lý `Optional`.
- Vì là terminal operation, chúng kích hoạt thực thi pipeline (ví dụ `filter`, `map` ở phía trước) và tiêu thụ Stream. Muốn kiểm tra lần khác, phải tạo Stream mới từ nguồn.

## 2. Phân biệt chính xác, đặc biệt với Stream rỗng

Giả sử `p(x)` là “`x` là số chẵn”:

| Dữ liệu đầu vào | `anyMatch(p)` | `allMatch(p)` | `noneMatch(p)` | Giải thích |
| --- | --- | --- | --- | --- |
| `[2, 4, 6]` | `true` | `true` | `false` | Tất cả chẵn |
| `[2, 3, 6]` | `true` | `false` | `false` | Vừa có chẵn, vừa có lẻ |
| `[1, 3, 5]` | `false` | `false` | `true` | Không có số chẵn |
| `[]` | `false` | `true` | `true` | Trường hợp Stream rỗng |

**Quy tắc rỗng dễ bị bỏ sót:**

- `Stream.empty().anyMatch(p)` luôn `false`.
- `Stream.empty().allMatch(p)` luôn `true`.
- `Stream.empty().noneMatch(p)` luôn `true`.
- Không phép nào gọi `p` khi Stream rỗng.

`allMatch` và `noneMatch` trả về `true` trên tập rỗng theo logic “mọi phần tử đều thỏa” (vacuous truth): không tồn tại phần tử phản ví dụ. Điều này **không** có nghĩa là Stream đã có ít nhất một phần tử hợp lệ.

Ví dụ, nếu quy tắc nghiệp vụ yêu cầu danh sách mã sản phẩm **không rỗng** và mọi mã đều hợp lệ, phải kiểm tra cả hai điều kiện:

```java
List<String> codes = List.of("A01", "B02");
boolean valid = !codes.isEmpty()
        && codes.stream().allMatch(code -> code != null && !code.isBlank());
```

Đây là đoạn minh họa trong một ngữ cảnh đã có `List`. `String.isBlank()` dùng được từ Java 11; với chương trình Java 17+ như ví dụ này, cách kiểm tra vẫn hiện hành. `List.of` không cho phép phần tử `null`, nhưng điều kiện phòng vệ `code != null` hữu ích khi dữ liệu đến từ nguồn có thể chứa `null`.

## 3. Ví dụ hoàn chỉnh chạy được bằng Java 17+

Lưu thành tệp **`StreamMatchDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public class StreamMatchDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(4, 7, 10);

        System.out.println("any > 8: "
                + numbers.stream().anyMatch(n -> n > 8));
        System.out.println("all > 0: "
                + numbers.stream().allMatch(n -> n > 0));
        System.out.println("none < 0: "
                + numbers.stream().noneMatch(n -> n < 0));

        List<String> empty = List.of();
        System.out.println("empty any: "
                + empty.stream().anyMatch(s -> s.length() > 0));
        System.out.println("empty all: "
                + empty.stream().allMatch(s -> s.length() > 0));
        System.out.println("empty none: "
                + empty.stream().noneMatch(s -> s.length() > 0));

        boolean hasNull = Stream.of("A", null).anyMatch(Objects::isNull);
        System.out.println("hasNull: " + hasNull);
    }
}
```

Biên dịch và chạy:

```bash
javac StreamMatchDemo.java
java StreamMatchDemo
```

Kết quả chuẩn:

```text
any > 8: true
all > 0: true
none < 0: true
empty any: false
empty all: true
empty none: true
hasNull: true
```

Giải thích:

1. Với `[4, 7, 10]`, `anyMatch(n -> n > 8)` đúng vì có `10`; `allMatch(n -> n > 0)` đúng vì cả ba số dương; `noneMatch(n -> n < 0)` đúng vì không có số âm.
2. Ba lệnh kiểm tra trên danh sách rỗng cho ra `false`, `true`, `true` theo quy tắc ở mục 2.
3. `Objects::isNull` là predicate an toàn khi Stream có phần tử `null`. Kết quả `hasNull` là `true`.
4. Mỗi phép kiểm tra dùng `numbers.stream()` hoặc `empty.stream()` **mới**, vì một đối tượng Stream chỉ được dùng cho một pipeline đã kết thúc. `List.of` có từ Java 9; bản thân ba phương thức `*Match` đã có từ Java 8 và tiếp tục dùng như cũ.

## 4. Short-circuiting: dừng khi đã đủ thông tin

Cả ba là **short-circuiting terminal operations**. Chúng có thể ngừng duyệt ngay khi kết quả đã được quyết định:

- `anyMatch`: chỉ cần **một** `true` để trả `true`; nếu không có, phải xét hết Stream hữu hạn để trả `false`.
- `allMatch`: chỉ cần **một** `false` để trả `false`; nếu không có, phải xét hết Stream hữu hạn để trả `true`.
- `noneMatch`: chỉ cần **một** `true` để trả `false`; nếu không có, phải xét hết Stream hữu hạn để trả `true`.

Ví dụ (đoạn mã minh họa):

```java
List<Integer> values = List.of(1, 2, 3, 4, 5);

boolean hasLargeNumber = values.stream().anyMatch(n -> n >= 3);
// true: một phần tử đủ lớn đã chứng minh được điều kiện tồn tại.

boolean everyPositive = values.stream().allMatch(n -> n > 0);
// true: phải xác minh không có phần tử vi phạm.

boolean noNegative = values.stream().noneMatch(n -> n < 0);
// true: phải xác minh không có phần tử âm.
```

Lưu ý về hiệu năng và tính đúng đắn:

- Trên Stream hữu hạn và predicate đơn giản, mỗi phép kiểm tra có thể cần duyệt tối đa `n` phần tử: độ phức tạp xét phần tử thường là `O(n)` trong trường hợp xấu nhất. Nhờ dừng sớm, một số trường hợp xét ít hơn rất nhiều.
- **Không dựa vào số lần gọi predicate, thứ tự log hoặc side effect** để xây dựng logic. Với `parallelStream()`, nhiều tác vụ có thể đã chạy đồng thời trước khi một tác vụ tìm ra kết quả. Thao tác trước đó như `sorted()` hoặc `distinct()` cũng có thể ảnh hưởng đến khối lượng xử lý.
- Short-circuit không bảo đảm mọi pipeline vô hạn sẽ hoàn tất. Chẳng hạn, kiểm tra “tất cả số đều dương” trên Stream vô hạn chỉ sinh ra số dương không thể tìm ra phản ví dụ để kết thúc bình thường.
- Trong tác vụ chỉ cần biết “có tồn tại hay không”, `anyMatch(p)` diễn đạt ý định rõ hơn việc lấy `filter(p).count() > 0` và cho phép dừng sớm; không nên tự suy ra một mức tăng tốc cố định cho mọi nguồn dữ liệu.

## 5. Các quan hệ logic hữu ích

Đối với **cùng tập dữ liệu ổn định** và predicate thuần, không làm thay đổi trạng thái:

```text
noneMatch(p)  == !anyMatch(p)
allMatch(p)   == noneMatch(p.negate())
allMatch(p)   == !anyMatch(p.negate())
anyMatch(p)   == !allMatch(p.negate())
```

Ví dụ (đoạn mã minh họa; tạo Stream mới cho từng phép kiểm tra):

```java
List<Integer> nums = List.of(2, 4, 6);
java.util.function.Predicate<Integer> even = n -> n % 2 == 0;

boolean allEven = nums.stream().allMatch(even);
boolean noOdd = nums.stream().noneMatch(even.negate());
// Cả hai đều true.
```

Không nhầm `noneMatch(p)` với `!allMatch(p)`. Với `[2, 3]` và `p(x) = x % 2 == 0`, cả `anyMatch(p)` và `!allMatch(p)` đều đúng, nhưng `noneMatch(p)` lại sai. Trên Stream rỗng, `!allMatch(p)` là `false` còn `noneMatch(p)` là `true`.

## 6. Áp dụng trong kiểm tra dữ liệu và nghiệp vụ

### Kiểm tra có lỗi hay không

```java
List<String> statuses = List.of("OK", "WARN", "ERROR");

boolean hasError = statuses.stream().anyMatch("ERROR"::equals);
boolean noError = statuses.stream().noneMatch("ERROR"::equals);
// hasError == true; noError == false.
```

`"ERROR"::equals` là method reference dùng chuỗi cố định làm vế so sánh; nó cũng không gây `NullPointerException` nếu phần tử đang xét là `null`.

### Bảo đảm tất cả giá trị đáp ứng điều kiện

```java
List<Integer> quantities = List.of(2, 5, 1);

boolean allPositive = !quantities.isEmpty()
        && quantities.stream().allMatch(q -> q > 0);
// true
```

Chỉ thêm `!quantities.isEmpty()` khi nghiệp vụ thực sự đòi hỏi có ít nhất một phần tử. Nếu danh sách rỗng là trường hợp hợp lệ, `allMatch` đơn lẻ có thể đúng ý nghĩa hơn.

### Kiểm tra phần tử không hợp lệ hoặc null

```java
List<String> names = java.util.Arrays.asList("An", null, "Binh");

boolean hasNull = names.stream().anyMatch(Objects::isNull);       // true
boolean noNull = names.stream().noneMatch(Objects::isNull);       // false
boolean allNamed = names.stream()
        .allMatch(name -> name != null && !name.isBlank());      // false
```

`Objects::isNull`/`Objects::nonNull` giúp biểu đạt rõ yêu cầu về null. Khi predicate gọi phương thức của phần tử (chẳng hạn `name.isBlank()`), cần xử lý null nếu nguồn có thể chứa null. Phép `&&` trong ví dụ bảo đảm không gọi `isBlank()` khi `name == null`.

### Dùng trên primitive streams

Các phương thức tương đương cũng tồn tại ở `IntStream`, `LongStream` và `DoubleStream`, với tham số lần lượt là `IntPredicate`, `LongPredicate` và `DoublePredicate`:

```java
boolean hasEven = java.util.stream.IntStream.of(3, 8, 13)
        .anyMatch(n -> n % 2 == 0);  // true
```

Dùng primitive stream khi dữ liệu vốn là kiểu số nguyên thủy có thể tránh boxing/unboxing không cần thiết. Không phải chuyển sang `Stream<Integer>` chỉ để kiểm tra điều kiện.

## 7. Các lỗi thường gặp

**Lỗi 1: Dùng lại cùng đối tượng Stream sau terminal operation.**

```java
Stream<Integer> s = Stream.of(1, 2, 3);
boolean hasTwo = s.anyMatch(n -> n == 2);
boolean allPositive = s.allMatch(n -> n > 0); // Sai: Stream đã tiêu thụ.
```

Dòng thứ hai sử dụng lại Stream là không hợp lệ, thường gây `IllegalStateException`. Cách đúng là gọi `numbers.stream()` lại từ collection hoặc dùng một `Supplier<Stream<T>>` để tạo Stream mới; đừng giả định một Stream có thể duyệt lại.

**Lỗi 2: Hiểu nhầm `allMatch` trên danh sách rỗng.** `allMatch` trả `true` ngay cả khi chưa kiểm tra phần tử nào. Thêm điều kiện không rỗng khi bắt buộc phải có ít nhất một giá trị.

**Lỗi 3: Đảo ngược ý nghĩa `noneMatch`.** `noneMatch(isInvalid)` có nghĩa “không có phần tử không hợp lệ”, thường tương đương với `allMatch(isValid)` nếu `isValid` thực sự là phủ định logic của `isInvalid`.

**Lỗi 4: Gây side effect trong predicate.** Tránh sửa nguồn dữ liệu, tăng bộ đếm toàn cục, gọi dịch vụ làm phát sinh thay đổi, hay phụ thuộc vào biến mutable khi dùng `*Match`. Stream yêu cầu predicate không can thiệp vào nguồn (**non-interfering**) và thông thường phải **stateless**; short-circuit và parallel có thể khiến hành vi phụ thay đổi theo lần chạy. Nếu cần ghi nhận từng phần tử, tổ chức thao tác đó rõ ràng bên ngoài phép kiểm tra tồn tại.

**Lỗi 5: Kỳ vọng `null` luôn an toàn.** Một Stream có thể chứa phần tử `null` nếu nguồn cho phép, nhưng `s -> s.length() > 0` sẽ ném `NullPointerException` khi đụng `null`. Dùng predicate an toàn như `s -> s != null && !s.isBlank()`, hoặc xử lý/null-filter trước. Đối số predicate bản thân nó cũng phải khác `null`.

**Lỗi 6: Lạm dụng parallel vì nghĩ luôn nhanh.** `parallelStream().anyMatch(...)` giữ nguyên kết quả logic với predicate thuần, nhưng chi phí chia việc, lượng dữ liệu và bản chất nguồn có thể khiến nó chậm hơn tuần tự. Đo hiệu năng trên dữ liệu thật rồi mới chọn.

## 8. Tự kiểm tra nhanh

Cho predicate `p(n) = n % 2 == 0` (số chẵn). Hãy dự đoán bộ ba kết quả theo thứ tự `anyMatch / allMatch / noneMatch`:

1. `List.of(2, 4, 6)`
2. `List.of(2, 3, 6)`
3. `List.of(1, 3, 5)`
4. `List.<Integer>of()`

Đáp án:

| Dữ liệu | `anyMatch` | `allMatch` | `noneMatch` |
| --- | --- | --- | --- |
| `[2, 4, 6]` | `true` | `true` | `false` |
| `[2, 3, 6]` | `true` | `false` | `false` |
| `[1, 3, 5]` | `false` | `false` | `true` |
| `[]` | `false` | `true` | `true` |

**Ghi nhớ khi chọn API:** “Có ít nhất một?” → `anyMatch`; “Tất cả đều?” → `allMatch`; “Không có cái nào?” → `noneMatch`. Sau khi chọn đúng câu hỏi, luôn xét thêm quy tắc Stream rỗng, tính thuần của predicate và khả năng dừng sớm.

## Tài liệu tham khảo

- [JDK 26: Stream API — anyMatch, allMatch, noneMatch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
- [JDK 25: java.util.stream — stream pipelines, short-circuiting và non-interference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html)
