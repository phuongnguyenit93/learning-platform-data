# Kết hợp `Predicate.not` với `Stream.filter` — Java 11 trở lên

## Mục tiêu bài học

Khi xử lý dữ liệu bằng Stream, bạn thường cần giữ những phần tử **không** thỏa điều kiện: chuỗi không rỗng/trắng, bản ghi chưa bị vô hiệu hóa, dữ liệu không thuộc nhóm cần loại trừ. Từ Java 11, phương thức `Predicate.not(...)` cho phép phủ định một `Predicate` ngay tại nơi dùng, đặc biệt gọn khi kết hợp với method reference trong `Stream.filter(...)`.

Sau bài này, bạn có thể:

- Giải thích tại sao `filter` giữ phần tử có điều kiện trả về `true`, và `Predicate.not` đảo điều kiện đó.
- Viết đúng `.filter(Predicate.not(String::isBlank))`, phân biệt với `.filter(String::isBlank)`.
- Kết hợp loại bỏ `null`, chuẩn hóa chuỗi, loại dòng trắng và nhiều tiêu chí lọc.
- So sánh `Predicate.not(p)`, `p.negate()` và lambda `value -> !p.test(value)`.
- Tránh các lỗi về null, thứ tự xử lý, phép logic và tính lazy của Stream.

**Phiên bản:** `Predicate.not` có từ **Java 11** và vẫn là API được hỗ trợ trong Java hiện đại. Các ví dụ chính biên dịch với Java 11, do đó cũng phù hợp các dự án hiện đang chạy Java 17/21/25 hoặc JDK mới hơn tương thích.

## 1. Hai mảnh ghép: `Predicate<T>` và `Stream.filter`

`Predicate<T>` là functional interface trong `java.util.function`. Phương thức cốt lõi:

```java
boolean test(T value);
```

Một `Predicate<String>` có thể kiểm tra xem chuỗi có trắng không:

```java
Predicate<String> blank = String::isBlank;
```

Đây là **đoạn minh họa** cần `import java.util.function.Predicate;` và ngữ cảnh khai báo phù hợp. `String.isBlank()`, có từ Java 11, trả về `true` khi chuỗi rỗng hoặc chỉ chứa các ký tự được `Character.isWhitespace(...)` nhận diện là khoảng trắng.

`Stream.filter(predicate)` là thao tác trung gian giữ lại phần tử nếu `predicate.test(element)` là `true`:

| Giá trị | `String.isBlank()` | `filter(String::isBlank)` | `filter(Predicate.not(String::isBlank))` |
| --- | --- | --- | --- |
| `"Java"` | `false` | Loại | Giữ |
| `""` | `true` | Giữ | Loại |
| `"   "` | `true` | Giữ | Loại |
| `"\t"` (tab) | `true` | Giữ | Loại |

**Ý nghĩa của phủ định:** từ Java 11, `Predicate.not(p)` tạo một predicate trả về kết quả **ngược lại** với `p`. Nếu `p.test(x)` là `true` thì `Predicate.not(p).test(x)` là `false`, và ngược lại.

Khái niệm trong JDK được thể hiện bằng chữ ký:

```java
static <T> Predicate<T> not(Predicate<? super T> target)
```

Đây là **chữ ký API để đọc hiểu**, không phải khai báo độc lập cần chép vào lớp. JDK thực hiện phủ định thông qua `target.negate()`. `Predicate.not` không sửa đối tượng predicate ban đầu và không tác động trực tiếp vào collection nguồn.

## 2. Tại sao kết hợp với method reference lại hữu ích?

Ví dụ nhu cầu: “Giữ các dòng không chỉ chứa khoảng trắng.”

Có ba cách hợp lệ, tương đương về ý nghĩa trên dữ liệu `String` không `null`:

```java
// Lambda phủ định trực tiếp
.filter(text -> !text.isBlank())

// Predicate.not + method reference (Java 11+)
.filter(Predicate.not(String::isBlank))

// Predicate đã đặt tên rồi phủ định
.filter(notBlank)
```

Dòng cuối giả định bạn đã khai báo:

```java
Predicate<String> notBlank = Predicate.not(String::isBlank);
```

Dạng thứ hai thường phù hợp khi một method reference mô tả điều kiện dương rõ ràng (`String::isBlank`), còn `Predicate.not(...)` thể hiện hành động **loại điều kiện đó**. Với điều kiện phức tạp, một lambda hoặc predicate có tên nghiệp vụ có thể dễ đọc hơn; không cần cố dùng `Predicate.not` trong mọi trường hợp.

So sánh trực tiếp:

```java
.filter(String::isBlank)                // Chỉ giữ chuỗi trắng
.filter(Predicate.not(String::isBlank)) // Chỉ giữ chuỗi không trắng
```

Hai dòng cho hai tập kết quả đối lập; bỏ sót chữ `not` sẽ đổi hẳn nghiệp vụ.

## 3. Chương trình chạy được: làm sạch danh sách chuỗi

Ví dụ này mô phỏng dữ liệu đến từ một nguồn có thể chứa khoảng trắng thừa, chuỗi trống và `null`. Ta chuẩn hóa chuỗi rồi dùng `Predicate.not` để loại dữ liệu không có nội dung.

**Tệp: `PredicateNotDemo.java`** — biên dịch/chạy từ **Java 11+**.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PredicateNotDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                "  alpha  ", "", " \t ", null, "beta", " gamma ");

        List<String> cleaned = input.stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(Predicate.not(String::isBlank))
                .collect(Collectors.toList());

        Predicate<String> longerThanFour =
                value -> value.length() > 4;
        List<String> shortValues = cleaned.stream()
                .filter(Predicate.not(longerThanFour))
                .collect(Collectors.toList());

        long rawBlanks = input.stream()
                .filter(Objects::nonNull)
                .filter(String::isBlank)
                .count();

        System.out.println("Cleaned: " + cleaned);
        System.out.println("Length <= 4: " + shortValues);
        System.out.println("Raw blanks: " + rawBlanks);
    }
}
```

Lệnh chạy trong thư mục chứa tệp:

```bash
javac PredicateNotDemo.java
java PredicateNotDemo
```

Hoặc trên JDK 11+ chạy trực tiếp mã nguồn:

```bash
java PredicateNotDemo.java
```

**Stdout chính xác của cả hai cách:**

```text
Cleaned: [alpha, beta, gamma]
Length <= 4: [beta]
Raw blanks: 2
```

Ví dụ được kiểm tra biên dịch với chế độ tương thích nguồn/API Java 11 (`javac --release 11`) và chạy ra đúng các dòng trên.

**Diễn giải từng bước:**

1. `Arrays.asList(...)` được chọn vì dữ liệu giả lập chứa `null`. `List.of(...)` không chấp nhận `null` và sẽ lỗi ngay khi tạo danh sách.
2. `input.stream()` tạo Stream từ danh sách; `filter(Objects::nonNull)` giữ phần tử có giá trị thực.
3. `map(String::strip)` bỏ khoảng trắng ở đầu/cuối từng chuỗi. `strip()` là API Java 11, hữu ích khi chuẩn hóa dữ liệu văn bản.
4. `filter(Predicate.not(String::isBlank))` loại `""` và các chuỗi trở thành rỗng sau `strip()`, giữ `alpha`, `beta`, `gamma`.
5. `collect(Collectors.toList())` là terminal operation tạo danh sách kết quả. API này vẫn được sử dụng bình thường trong Java hiện đại.
6. `longerThanFour` là predicate `value.length() > 4`. `Predicate.not(longerThanFour)` giữ giá trị dài **không quá 4**: chỉ còn `beta`.
7. Đếm `rawBlanks` dùng `filter(String::isBlank)` theo chiều **dương** để đếm hai chuỗi trắng ban đầu.

**Thứ tự rất quan trọng:** nếu đặt `map(String::strip)` hoặc `filter(Predicate.not(String::isBlank))` trước `filter(Objects::nonNull)` trên dữ liệu này, khi chạm `null` sẽ phát sinh `NullPointerException`. Bản thân `Predicate.not` không biến một predicate thành “null-safe”.

## 4. Ba mẫu sử dụng thường gặp

### 4.1. Loại chuỗi rỗng hoặc trắng khỏi danh sách

Nếu dữ liệu bảo đảm không có `null` và chỉ cần giữ phần tử có nội dung:

```java
List<String> source = List.of("one", " ", "", "two");

List<String> result = source.stream()
        .filter(Predicate.not(String::isBlank))
        .collect(Collectors.toList());
// result: [one, two]
```

Đây là **đoạn code minh họa** cần các import cho `List`, `Predicate` và `Collectors`. Khác với `String.isEmpty()` chỉ kiểm tra độ dài bằng 0, `String.isBlank()` cũng nhận diện chuỗi chỉ chứa khoảng trắng theo quy tắc đã nêu.

Muốn xóa khoảng trắng ở hai đầu các chuỗi **được giữ lại**, thêm `.map(String::strip)` trước `filter`.

### 4.2. Phủ định một điều kiện nghiệp vụ đã đặt tên

```java
Predicate<String> isTemporary =
        id -> id.startsWith("tmp-");

List<String> ids = List.of("tmp-1", "user-2", "tmp-3", "user-4");
List<String> persistentIds = ids.stream()
        .filter(Predicate.not(isTemporary))
        .collect(Collectors.toList());
// persistentIds: [user-2, user-4]
```

Cách đặt tên `isTemporary` giúp người đọc hiểu chính xác điều kiện bị phủ định. Khi predicate có nhiều quy tắc và xuất hiện ở nhiều nơi, việc đặt tên thường tốt hơn nhét logic dài vào trong `filter`.

### 4.3. Lọc dữ liệu từ tệp theo từng dòng

Nếu đang đọc tệp văn bản với `Files.lines(...)`, có thể loại dòng trắng mà không phải nạp toàn bộ tệp vào RAM. Đây là **mẫu minh họa phần xử lý**, không phải chương trình độc lập vì phụ thuộc `path` và việc xử lý `IOException` ở phạm vi gọi:

```java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long meaningfulLines = lines
            .filter(Predicate.not(String::isBlank))
            .count();
    System.out.println(meaningfulLines);
}
```

Các import cần có: `java.util.stream.Stream`, `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets` và `java.util.function.Predicate`.

**Đóng stream là cần thiết đối với stream mở từ I/O**: `try-with-resources` giải phóng tài nguyên tệp kể cả khi xử lý lỗi. Stream thông thường lấy từ `List.stream()` không cần đóng như một file stream.

## 5. `Predicate.not(p)` và `p.negate()` giống và khác ở đâu?

`Predicate.negate()` là instance method đã được hỗ trợ từ Java 8. `Predicate.not(...)` là static method có từ Java 11; cả hai đều tạo predicate đảo kết quả.

```java
Predicate<String> isBlank = String::isBlank;

Predicate<String> a = isBlank.negate();
Predicate<String> b = Predicate.not(isBlank);

// a.test("abc") == true
// b.test("abc") == true
```

Khi đã có biến `isBlank`, `isBlank.negate()` rất tự nhiên. Khi muốn phủ định **method reference ngay trong lời gọi**, `Predicate.not(String::isBlank)` thường gọn và rõ hơn cách viết lambda phủ định thủ công.

Bạn cũng có thể dùng `.filter(text -> !text.isBlank())` nếu thấy nó dễ hiểu hơn. Đừng thêm tầng trừu tượng chỉ để sử dụng một API mới.

**Điều cần nhớ:** `Predicate.not(null)` ném `NullPointerException` khi bạn cố tạo predicate phủ định, vì tham số `target` phải khác `null`. Đây là lỗi *predicate bị null*, khác với việc stream **chứa phần tử null**. Trong trường hợp thứ hai, hãy xử lý từng phần tử null bằng quy tắc phù hợp, chẳng hạn `Objects::nonNull`.

## 6. Ghép `Predicate.not` với nhiều điều kiện

Một pipeline có thể có nhiều lần `filter`:

```java
Predicate<String> isTemporary =
        id -> id.startsWith("tmp-");
Predicate<String> isDisabled =
        id -> id.endsWith("-disabled");

List<String> accepted = List.of(
        "tmp-a", "user-b", "user-c-disabled", "user-d")
        .stream()
        .filter(Predicate.not(isTemporary))
        .filter(Predicate.not(isDisabled))
        .collect(Collectors.toList());
// accepted: [user-b, user-d]
```

Dòng thứ nhất loại phần tử tạm thời, dòng thứ hai loại phần tử đã vô hiệu hóa. Với từng phần tử, hai điều kiện đều phải trả về `true` để được giữ lại. Có thể biểu đạt tương đương dưới dạng phủ định của phép OR:

```java
.filter(Predicate.not(isTemporary.or(isDisabled)))
```

Lưu ý đây là **đoạn thay thế cho hai dòng `filter`**, giả định các predicate trên đã được khai báo.

**Quy tắc logic cần nhớ:**

- `!A && !B` tương đương `!(A || B)`.
- `!A || !B` tương đương `!(A && B)`.
- `Predicate.not(a.and(b))` giữ cả trường hợp chỉ một trong hai điều kiện sai, nên **không** thay thế cho việc lần lượt `filter(Predicate.not(a))` và `filter(Predicate.not(b))`.

Ví dụ nếu một ID **không** tạm thời nhưng **có** hậu tố `-disabled`, `Predicate.not(isTemporary.and(isDisabled))` sẽ trả `true`, làm lọt ID đã vô hiệu hóa. Vì thế phải chọn đúng toán tử ghép cho điều kiện nghiệp vụ.

## 7. Cơ chế thực thi của Stream và hiệu năng

`Stream.filter(...)` là **intermediate operation, lazy**. Tạo pipeline chưa duyệt dữ liệu ngay:

```java
Stream<String> pipeline = List.of("", "java", " ")
        .stream()
        .filter(Predicate.not(String::isBlank));

// Terminal operation bắt đầu tính toán:
long count = pipeline.count(); // 1
```

Đây là đoạn minh họa cần import `Stream`, `List`, `Predicate`.

Trong pipeline này:

- Khi terminal operation bắt đầu, stream duyệt các phần tử cần thiết, gọi predicate và chỉ cho phần tử đạt điều kiện đi tiếp.
- `Predicate.not` chỉ đổi kết quả `boolean` của predicate; nó **không tạo thêm một lượt duyệt collection**.
- Stream thường không biến đổi collection nguồn. Muốn dữ liệu gốc thay đổi, phải có thao tác riêng được thiết kế cho mục đích đó.
- Một stream đã được tiêu thụ không được chạy terminal operation lần thứ hai; hãy gọi `source.stream()` tạo pipeline mới nếu cần kết quả khác.
- `filter` không bảo đảm luôn duyệt hết phần tử: các terminal operation như `findFirst()`, `anyMatch()` có thể dừng sớm. Java cũng có thể tối ưu pipeline, nên không dùng side effect bên trong predicate để đếm log hoặc thay đổi trạng thái ngoài pipeline.

Hãy giữ predicate **không sửa nguồn (non-interfering)** và phần lớn là **không phụ thuộc trạng thái biến đổi (stateless)**. Ví dụ sai về thiết kế là trong predicate vừa kiểm tra điều kiện vừa thêm/xóa phần tử của danh sách đang được stream xử lý.

Về hiệu năng, ưu tiên tính đúng và dễ đọc. Dùng `Predicate.not(String::isBlank)` hay `text -> !text.isBlank()` không mang một bảo đảm hiệu năng hơn kém nào từ ngôn ngữ; chỉ benchmark khi có yêu cầu thực tế.

## 8. Xử lý `null` và kiểu dữ liệu đúng cách

`Predicate.not(String::isBlank)` yêu cầu phần tử là `String` khác `null`. Không dùng trực tiếp trên `Stream<String>` có thể chứa `null`.

```java
// Đúng khi dữ liệu có thể null:
stream
    .filter(Objects::nonNull)
    .filter(Predicate.not(String::isBlank))
```

Đây là pipeline **minh họa** với biến `stream` đã tồn tại và import phù hợp. `Objects::nonNull` diễn đạt trực tiếp ý “giữ phần tử không null”; `Predicate.not(Objects::isNull)` cũng có thể biểu đạt logic tương đương nhưng thường dài hơn.

Nếu dữ liệu cho phép chuỗi null **có ý nghĩa riêng**, bạn cần quyết định rõ cần loại bỏ, chuyển thành giá trị mặc định hay báo lỗi; không áp dụng quy tắc loại null một cách mù quáng.

Với Stream của kiểu khác, chọn predicate đúng kiểu đó. `String::isBlank` không thể được áp dụng tùy tiện cho `Stream<Integer>` hoặc `Stream<SomeRecord>`. Với object có trạng thái, bạn có thể dùng method reference kiểu `RecordType::isArchived` **nếu thực sự có phương thức tương ứng**, rồi `filter(Predicate.not(RecordType::isArchived))`.

Khi trình biên dịch báo không suy luận được kiểu cho method reference/lambda phức tạp, hãy làm rõ type của stream hoặc đặt tên predicate có kiểu cụ thể, thay vì ép kiểu tùy tiện.

## 9. Lựa chọn terminal operation trên JDK hiện đại

Trong ví dụ chính dùng:

```java
.collect(Collectors.toList())
```

Cách này **vẫn được hỗ trợ**, kể cả trên Java mới. Nó chạy trên Java 11 và không cam kết cụ thể kiểu triển khai hay tính có thể thay đổi của danh sách kết quả.

Từ Java 16 có thêm `Stream.toList()`, thường phù hợp khi chỉ cần danh sách kết quả **không thể thay đổi qua các thao tác như `add/remove`**:

```java
// Chỉ yêu cầu Java 16+; không biên dịch được trên JDK 11:
List<String> values = List.of("java", " ", "stream")
        .stream()
        .filter(Predicate.not(String::isBlank))
        .toList();
// values: [java, stream], danh sách trả về không thể sửa đổi.
```

Không coi hai API hoàn toàn tương đương về hợp đồng mutability; chọn theo yêu cầu thực tế và JDK tối thiểu của dự án. Khác biệt nằm ở terminal operation, **không làm thay đổi cách `Predicate.not` hoạt động**.

## 10. Lỗi phổ biến cần tránh

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `filter(String::isBlank)` khi muốn loại chuỗi trắng | Kết quả chỉ còn chuỗi trắng | Dùng `filter(Predicate.not(String::isBlank))` |
| Có `null` nhưng lọc `isBlank` trước | Có thể gặp `NullPointerException` | Xử lý null trước, ví dụ `Objects::nonNull` |
| Dùng `isEmpty` thay `isBlank` mà không cân nhắc | Chuỗi chỉ gồm dấu cách vẫn được giữ | Chọn `isBlank` khi mục tiêu là “chỉ chứa khoảng trắng” |
| Nghĩ `filter` cũng cắt khoảng trắng đầu/cuối | Dữ liệu được giữ có thể còn dư khoảng trắng | Kết hợp `map(String::strip)` khi cần chuẩn hóa |
| Nhầm `not(a.and(b))` với `not(a).and(not(b))` | Có thể giữ phần tử cần loại | Kiểm tra logic bằng bảng chân trị hoặc input ví dụ |
| Dùng cùng một Stream đã chạy terminal operation | Không thể tái sử dụng stream đã tiêu thụ | Tạo stream mới từ nguồn |
| Cho predicate sửa collection nguồn | Dễ có kết quả sai/lỗi, đặc biệt với parallel stream | Viết predicate thuần, không thay đổi nguồn |
| Dùng `Stream.toList()` rồi gọi `add(...)` | Ném `UnsupportedOperationException` | Chọn hợp đồng collection phù hợp |
| Chạy `Predicate.not` trên JDK 8 | Không biên dịch vì API chưa tồn tại | Cấu hình JDK tối thiểu 11+ hoặc dùng `p.negate()` trên mã buộc chạy Java 8 |

Dòng cuối chỉ là lưu ý **tương thích phiên bản**, không phải khuyến nghị chọn Java 8 cho dự án mới.

## 11. Bài tập và câu hỏi kiểm tra

**Bài 1.** Với `List.of("", "  ", "A", " B ")`, dự đoán kết quả của:

```java
items.stream()
    .filter(Predicate.not(String::isBlank))
    .collect(Collectors.toList())
```

Khi `items` là danh sách đã nêu, kết quả là `[A,  B ]` (chuỗi thứ hai vẫn giữ dấu cách ở đầu/cuối). Hãy thêm `map(String::strip)` trước filter để thu được `[A, B]`.

**Bài 2.** Vì sao pipeline sau không an toàn nếu chứa null?

```java
input.stream()
     .filter(Predicate.not(String::isBlank))
     .filter(Objects::nonNull)
```

Trả lời: `String::isBlank` có thể bị gọi trên null ở bước đầu, gây `NullPointerException` trước khi đến bước thứ hai.

**Bài 3.** Hai cách viết sau có cùng ý nghĩa hay không?

```java
.filter(Predicate.not(a))
.filter(Predicate.not(b))
```

và

```java
.filter(Predicate.not(a.or(b)))
```

Có, nếu `a` và `b` là các predicate đúng kiểu, xác định và không gây side effect: cả hai đều chỉ giữ phần tử không thỏa `a` lẫn `b`.

**Bài 4.** Hãy viết predicate `isDisabled` kiểm tra mã có hậu tố `"-disabled"`, sau đó viết `.filter(Predicate.not(isDisabled))`. Tự bổ sung ít nhất một ID thường và một ID bị vô hiệu hóa, chạy thử và so kết quả với dự đoán.

## Tài liệu chính thức

- [Oracle Java SE 11 — Predicate.not](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/function/Predicate.html#not(java.util.function.Predicate)): chữ ký, phủ định và điều kiện không null; API xuất hiện từ Java 11.
- [Oracle Java SE 25 — Predicate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Predicate.html): xác nhận API vẫn hiện diện trên JDK hiện đại.
- [Oracle Java SE 25 — Stream.filter và Stream.toList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): lọc, tính lazy, hợp đồng danh sách kết quả.
- [Oracle Java SE 11 — String.isBlank](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html#isBlank()): xác định chuỗi trắng theo định nghĩa của Java.