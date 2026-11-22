# Kết hợp Optional và Stream mà không gọi get() tùy tiện

Trong Java, `Optional<T>` diễn đạt **một kết quả có thể có hoặc vắng mặt**, còn `Stream<T>` biểu diễn **một chuỗi xử lý phần tử**. Hai API kết hợp rất tự nhiên khi cần biến đổi dữ liệu, tìm kiếm, lọc hoặc bỏ qua các kết quả không tồn tại. Cách tiếp cận quan trọng là **mô tả quá trình xử lý sự hiện diện/vắng mặt bằng các phép toán của Optional và Stream**, thay vì gọi `get()` trên Optional mà chưa chắc chắn có giá trị.

Ví dụ, nếu một repository trả `Optional<User>` cho mỗi mã người dùng, bạn có thể biến `Stream<Optional<User>>` thành `Stream<User>` bằng `flatMap(Optional::stream)`. Các mã không tìm thấy sẽ tự biến thành **không phần tử**, còn kết quả tìm thấy trở thành **một phần tử**. Như vậy không cần `isPresent()` rồi `get()` cho từng mục.

Các kỹ thuật chính trong bài:

- `Optional.map`, `filter`, `flatMap` để xử lý một giá trị có thể thiếu.
- `Optional.stream()` (Java 9+) để chuyển Optional thành Stream **0 hoặc 1 phần tử**.
- `Stream.map(...)` kết hợp `Stream.flatMap(Optional::stream)` để bỏ các kết quả vắng mặt và tiếp tục pipeline.
- `Stream.findFirst()`/`findAny()` trả Optional; kết thúc bằng `ifPresent`, `orElse`, `orElseGet`, `or`, `orElseThrow` theo hợp đồng nghiệp vụ.
- Xử lý null ở ranh giới dữ liệu, tránh Optional lồng nhau và tránh side effect không cần thiết.

Các ví dụ hoàn chỉnh sử dụng **Java 17+**, có lệnh `javac`/`java` và stdout xác định.

## 1. Vì sao gọi get() tùy tiện là nguy hiểm?

Một `Optional<T>` có hai trạng thái: **có giá trị khác null** hoặc **rỗng**. `Optional.get()` trả giá trị khi có mặt, nhưng **ném `NoSuchElementException` nếu Optional rỗng**.

Đây là mẫu dễ lỗi:

```java
Optional<String> value = Optional.empty();
String text = value.get(); // ném NoSuchElementException
```

Đây là **mảnh mã cố ý gây ngoại lệ khi chạy**, không phải phương án khuyến nghị.

Một mẫu khác biên dịch được nhưng dễ khiến code lặp lại:

```java
String display;
if (value.isPresent()) {
    display = value.get();
} else {
    display = "Không có";
}
```

Đây là mảnh mã minh họa, với `value` kiểu `Optional<String>` đã có. Cách viết không sai về logic trong phạm vi đơn giản này, nhưng có thể gọn và trực tiếp hơn:

```java
String display = value.orElse("Không có");
```

**Không phải mọi lời gọi `get()` đều sai.** Khi đã chứng minh chắc chắn Optional có giá trị trong một ngữ cảnh cụ thể, `get()` có thể hợp lệ. Tuy nhiên, khi xử lý pipeline hoặc API có thể trả rỗng, các phép toán như `map`, `flatMap`, `ifPresent` và `orElseThrow` thường truyền đạt ý định tốt hơn, tránh việc kiểm tra và bóc giá trị thủ công ở từng bước.

## 2. Phân biệt map, flatMap và filter trên Optional

Giả sử:

```java
Optional<String> name = Optional.of("  Lan  ");
```

Đoạn này cần `import java.util.Optional;`.

### Optional.map: chuyển giá trị nếu có

```java
Optional<String> trimmed = name.map(String::strip);
// Optional chứa "Lan"
```

`map` chỉ gọi hàm biến đổi khi Optional có giá trị. Khi Optional rỗng, kết quả vẫn rỗng. Nếu mapper trả `null`, `Optional.map` tạo Optional rỗng cho kết quả đó; nó không tạo Optional có mặt chứa null.

### Optional.filter: giữ hoặc bỏ theo điều kiện

```java
Optional<String> nonBlank = trimmed.filter(s -> !s.isEmpty());
// Có "Lan" vì "Lan" không rỗng.
```

`filter` giữ Optional ban đầu nếu điều kiện đúng, trả Optional rỗng nếu sai; với Optional vốn đã rỗng, predicate không được gọi.

### Optional.flatMap: tránh Optional lồng nhau

Khi hàm biến đổi đã trả về `Optional<R>`, dùng `flatMap` thay cho `map` nếu muốn kết quả `Optional<R>`:

```java
static Optional<Integer> parseInteger(String raw) {
    try {
        return Optional.of(Integer.parseInt(raw));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
```

Đây là **mảnh phương thức minh họa** cần `import java.util.Optional;` và thuộc một class. Khi dùng:

```java
Optional<Optional<Integer>> nested =
        Optional.of("42").map(MyClass::parseInteger);
Optional<Integer> flat =
        Optional.of("42").flatMap(MyClass::parseInteger);
```

`MyClass` trong mảnh minh họa là tên class chứa `parseInteger`, cần đổi thành tên class thực tế. `map` bọc kết quả đã là Optional vào một lớp Optional nữa; `flatMap` trả trực tiếp Optional do mapper tạo ra. **Khác với `map`, hàm được truyền vào `Optional.flatMap` không được trả null**: nếu mapper trả null, Java ném `NullPointerException`.

## 3. Optional.stream(): cầu nối 0 hoặc 1 phần tử

Từ Java 9, `Optional<T>` có phương thức `Stream<T> stream()`:

| Trạng thái Optional | `optional.stream()` tạo ra |
| --- | --- |
| `Optional.of("Java")` | Stream có đúng một phần tử `"Java"` |
| `Optional.empty()` | Stream rỗng |
| `Optional.ofNullable(null)` | Stream rỗng |

Như vậy bạn không cần tự kiểm tra Optional rồi tạo `Stream.of(value)` hoặc `Stream.empty()`.

```java
List<Optional<String>> maybeNames = List.of(
        Optional.of("Lan"),
        Optional.empty(),
        Optional.of("Mai")
);

List<String> names = maybeNames.stream()
        .flatMap(Optional::stream)
        .toList();
// [Lan, Mai]
```

Đây là mảnh mã cần `import java.util.List;` và `import java.util.Optional;`; `Stream.toList()` có từ Java 16. `flatMap(Optional::stream)` chuyển mỗi Optional thành Stream 0/1 phần tử rồi **ghép các Stream con** thành một Stream đầu ra.

Không nhầm với:

```java
Stream<Stream<String>> nestedStreams =
        maybeNames.stream().map(Optional::stream);
```

Khi dùng `map`, mỗi phần tử Optional được chuyển thành **một Stream con**, nên kiểu đầu ra là `Stream<Stream<String>>`. Khi dùng `flatMap`, các phần tử của Stream con được trải phẳng thành `Stream<String>`.

**Lưu ý:** `Optional.stream()` không kiểm tra tính hợp lệ nghiệp vụ của giá trị bên trong; nó chỉ chuyển trạng thái có/rỗng thành 1/0 phần tử. Muốn loại chuỗi trắng hoặc trùng, tiếp tục dùng `filter`, `map`, `distinct`.

## 4. Chương trình Java 17: từ danh sách Optional thành danh sách giá trị

Lưu thành **`OptionalStreamBasicsDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.Optional;

public class OptionalStreamBasicsDemo {
    public static void main(String[] args) {
        List<Optional<String>> values = List.of(
                Optional.of(" Java "),
                Optional.empty(),
                Optional.of("Kotlin"),
                Optional.of("Java"),
                Optional.of("   ")
        );

        List<String> cleaned = values.stream()
                .flatMap(Optional::stream)
                .map(String::strip)
                .filter(s -> !s.isBlank())
                .map(s -> s.toUpperCase(Locale.ROOT))
                .distinct()
                .toList();

        System.out.println("cleaned=" + cleaned);
        System.out.println("presentCount=" + values.stream()
                .flatMap(Optional::stream)
                .count());
        System.out.println("emptyAsStream="
                + Optional.<String>empty().stream().count());
        System.out.println("singleAsStream="
                + Optional.of("Java").stream().count());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 OptionalStreamBasicsDemo.java
java OptionalStreamBasicsDemo
```

**Stdout chính xác:**

```text
cleaned=[JAVA, KOTLIN]
presentCount=4
emptyAsStream=0
singleAsStream=1
```

Giải thích:
1. Năm Optional ban đầu gồm **bốn Optional có giá trị** và một Optional rỗng. Vì thế `presentCount` là 4, kể cả chuỗi chỉ chứa khoảng trắng.
2. `flatMap(Optional::stream)` loại Optional rỗng khỏi luồng kết quả mà không gọi `get()`.
3. `strip`, `filter`, `toUpperCase` và `distinct` tạo hai giá trị duy nhất `JAVA`, `KOTLIN` theo thứ tự gặp đầu tiên của nguồn List.
4. `Optional.empty().stream().count()` bằng 0; Optional có giá trị tạo Stream có đúng 1 phần tử.

Vì `List.of` không cho phần tử null, ví dụ dùng **`Optional.empty()` làm phần tử** thay cho null. Tránh tạo một `List<Optional<T>>` chứa **tham chiếu Optional null**: lời gọi `Optional::stream` trên tham chiếu null sẽ ném ngoại lệ.

## 5. Stream.map(repository::find) rồi flatMap(Optional::stream)

Một tình huống thực tế: với mỗi mã ID, repository trả `Optional<User>`; không phải mã nào cũng tồn tại.

Mẫu pipeline:

```java
List<User> users = ids.stream()
        .map(repository::findById)   // Stream<Optional<User>>
        .flatMap(Optional::stream)   // Stream<User>
        .toList();
```

Đây là mảnh mã minh họa: `ids`, `repository`, `User` cần được khai báo trong ứng dụng; `repository.findById` phải có kiểu kết quả `Optional<User>`.

Tại mỗi bước:
- `ids.stream()` phát các ID.
- `map(repository::findById)` gọi repository cho từng ID, kết quả mỗi lần là một Optional.
- `flatMap(Optional::stream)` **bỏ qua** Optional rỗng và **giữ lại** các User tìm thấy.
- `toList()` tạo danh sách kết quả. Nếu Stream có encounter order (ví dụ nguồn List), kết quả giữ thứ tự gặp của những User có mặt.

Không nên viết:

```java
// CỐ Ý SAI: mã vắng mặt sẽ gây NoSuchElementException.
List<User> users = ids.stream()
        .map(repository::findById)
        .map(Optional::get)
        .toList();
```

Ngoài việc dễ lỗi, đoạn trên còn lẫn trách nhiệm “tìm kiếm có thể thất bại” với “bóc dữ liệu chắc chắn có” trong pipeline. Trường hợp cần **báo lỗi ngay** khi một ID không tồn tại thì có thể dùng `orElseThrow` với thông báo theo ID; trường hợp muốn **bỏ qua ID không tồn tại** thì `flatMap(Optional::stream)` phù hợp hơn.

## 6. Chương trình Java 17: repository trả Optional và Stream lọc dữ liệu

Tạo tệp **`OptionalStreamRepositoryDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class OptionalStreamRepositoryDemo {
    record User(String id, String name, boolean active) {}

    private static final Map<String, User> USERS = Map.of(
            "u1", new User("u1", "Lan", true),
            "u2", new User("u2", "Minh", false),
            "u3", new User("u3", "Mai", true)
    );

    static Optional<User> findById(String id) {
        return Optional.ofNullable(USERS.get(id));
    }

    public static void main(String[] args) {
        List<String> ids = List.of("u1", "missing", "u2", "u3", "u1");

        List<String> activeNames = ids.stream()
                .map(OptionalStreamRepositoryDemo::findById)
                .flatMap(Optional::stream)
                .filter(User::active)
                .map(User::name)
                .distinct()
                .toList();

        long foundCount = ids.stream()
                .map(OptionalStreamRepositoryDemo::findById)
                .flatMap(Optional::stream)
                .count();

        String firstFoundName = ids.stream()
                .map(OptionalStreamRepositoryDemo::findById)
                .flatMap(Optional::stream)
                .map(User::name)
                .findFirst()
                .orElse("Không có");

        String missingName = findById("missing")
                .map(User::name)
                .orElse("Khách");

        System.out.println("activeNames=" + activeNames);
        System.out.println("foundCount=" + foundCount);
        System.out.println("firstFound=" + firstFoundName);
        System.out.println("missingName=" + missingName);
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 OptionalStreamRepositoryDemo.java
java OptionalStreamRepositoryDemo
```

**Stdout chính xác:**

```text
activeNames=[Lan, Mai]
foundCount=4
firstFound=Lan
missingName=Khách
```

Giải thích:
1. `Map.get` có thể trả null khi ID không tồn tại; `Optional.ofNullable` chuyển kết quả đó thành Optional rỗng.
2. Nguồn `ids` có năm mục. ID `"missing"` không tìm được, nhưng `"u1"` xuất hiện hai lần; tổng số lần tìm thấy là **4**.
3. Lọc `active` bỏ User `"Minh"`; `distinct` sau `map(User::name)` loại tên `"Lan"` lặp lại, nên kết quả là `[Lan, Mai]`.
4. `findFirst()` trả Optional dựa trên kết quả đầu tiên của Stream có thứ tự; `orElse("Không có")` bảo đảm luôn trả một String dù không có User nào.
5. Với một Optional riêng lẻ, `findById("missing").map(User::name).orElse("Khách")` đơn giản hơn việc tạo cả Stream.

**Chọn rõ ngữ nghĩa:** `flatMap(Optional::stream)` **bỏ qua** kết quả thiếu. Nếu thiếu ID là lỗi dữ liệu cần biết, không nên im lặng bỏ qua; hãy dùng API kết quả có thông tin lỗi hoặc `orElseThrow` theo yêu cầu nghiệp vụ.

## 7. findFirst, findAny và quy trình trả Optional

Các terminal operations `findFirst()` và `findAny()` trả về `Optional<T>`. Điều này nhắc người gọi rằng nguồn có thể rỗng hoặc không tìm được giá trị.

```java
Optional<String> first = List.of("Java", "Kotlin")
        .stream()
        .filter(s -> s.startsWith("K"))
        .findFirst();
```

Đoạn mã minh họa cần `import java.util.List;` và `import java.util.Optional;`. Trong ví dụ, `first` chứa `"Kotlin"`. Nếu đổi điều kiện thành `startsWith("Z")`, kết quả rỗng.

Bạn có thể kết thúc theo nhu cầu:

```java
first.ifPresent(System.out::println);
String display = first.orElse("Không tìm thấy");
String strict = first.orElseThrow(
        () -> new IllegalStateException("Yêu cầu có kết quả"));
```

Những mảnh mã này giả định `first` có giá trị như ví dụ trước; vì vậy `ifPresent` in `Kotlin`, `display` và `strict` nhận `"Kotlin"`. Khi Optional rỗng, `ifPresent` không thực hiện action, `orElse` trả fallback và `orElseThrow` ném exception do supplier tạo ra.

Trên Stream có encounter order, `findFirst()` phải tôn trọng thứ tự gặp; `findAny()` có thể trả bất kỳ phần tử phù hợp, đặc biệt hữu ích khi chạy song song và **không cần phần tử đầu tiên**.

**Chú ý null:** `findFirst()`/`findAny()` có thể ném `NullPointerException` nếu phần tử được chọn là null, bởi Optional không thể chứa giá trị null. Nếu Stream có thể chứa null, hãy lọc bằng `filter(Objects::nonNull)` trước khi dùng các terminal trả Optional.

## 8. Optional.map và flatMap khác Stream.map và flatMap như thế nào?

| API | Đối tượng đầu vào | Hàm được truyền vào | Kết quả |
| --- | --- | --- | --- |
| `Optional<T>.map(f)` | Optional có 0/1 giá trị | `T -> R` | `Optional<R>` |
| `Optional<T>.flatMap(f)` | Optional có 0/1 giá trị | `T -> Optional<R>` | `Optional<R>` |
| `Stream<T>.map(f)` | Stream có 0..n phần tử | `T -> R` | `Stream<R>` |
| `Stream<T>.flatMap(f)` | Stream có 0..n phần tử | `T -> Stream<R>` | `Stream<R>` |
| `Optional<T>.stream()` | Optional có 0/1 giá trị | Không có đối số hàm | `Stream<T>` chứa 0/1 phần tử |

Dấu `flatMap` trong Optional và Stream có ý tưởng chung là “trải phẳng lớp container do mapper trả về”, nhưng **kiểu container khác nhau**. Một số cặp hợp lệ điển hình:

```java
Optional<String> normalized =
        Optional.of(" java ").map(String::strip);

Stream<String> found =
        Stream.of(Optional.of("A"), Optional.empty())
                .flatMap(Optional::stream);
```

Đây là các mảnh minh họa cần import `Optional` và `Stream`. Trong `Optional.flatMap`, mapper phải trả Optional không null; trong `Stream.flatMap`, mapper phải trả Stream (theo hợp đồng API; với kết quả null, Stream coi như một Stream rỗng). Tránh trộn chúng như thể cùng một loại hàm.

### Khi cần trả nhiều giá trị từ một Optional

`Optional.stream()` chỉ có **0 hoặc 1 giá trị**. Nếu một giá trị bên trong có thể biến thành nhiều giá trị, hãy chuyển nó thành Stream rồi dùng `Stream.flatMap` tương ứng:

```java
List<String> words = Optional.of("Java Kotlin")
        .stream()
        .flatMap(s -> java.util.Arrays.stream(s.split(" ")))
        .toList();
// [Java, Kotlin]
```

Ví dụ trên dùng `Optional.stream()` để bắt đầu với 0/1 chuỗi, rồi `Stream.flatMap` trải danh sách từ được tách. Nếu Optional rỗng, pipeline đương nhiên tạo danh sách rỗng.

## 9. Đừng dùng get() khi xử lý dữ liệu nullable: Optional.ofNullable và Stream.ofNullable

Khi đầu vào là **tham chiếu `T` có thể null**, không phải `Optional<T>`, có hai cách tạo Stream 0/1 phần tử trong Java 9+:

```java
Stream<String> a = Optional.ofNullable(value).stream();
Stream<String> b = Stream.ofNullable(value);
```

Đây là mảnh mã minh họa có `value` kiểu `String` và import `Optional`, `Stream`. Cả hai đều tạo Stream rỗng nếu `value == null`, hoặc Stream một phần tử nếu khác null.

- Dùng **`Optional.ofNullable(value)`** khi muốn thể hiện việc vắng mặt trong API hoặc còn các bước xử lý Optional.
- Dùng **`Stream.ofNullable(value)`** khi chỉ muốn đưa một giá trị nullable vào Stream mà không cần tạo Optional như một bước dữ liệu biểu đạt.

Ví dụ làm sạch chuỗi nullable:

```java
List<String> cleaned = Stream.ofNullable(raw)
        .map(String::strip)
        .filter(s -> !s.isBlank())
        .toList();
```

Với `raw == null`, kết quả là danh sách rỗng; vì không có phần tử, `String::strip` không chạy nên không ném NullPointerException. Với `raw = " Java "`, kết quả là `[Java]`. Với `raw = "   "`, kết quả rỗng vì `filter`.

**Cẩn thận khi dùng `Stream.of(value)`:** với một biến tham chiếu nullable, `Stream.of(value)` có thể tạo Stream chứa một **phần tử null** thay vì Stream rỗng. Lúc ấy `map(String::strip)` sẽ ném lỗi. `Stream.ofNullable` đúng hơn nếu ý định là bỏ null.

## 10. Tránh Optional lồng nhau khi kết hợp nhiều bước

Giả sử một hàm trả Optional vì việc parse có thể thất bại:

```java
static Optional<Integer> parsePositive(String raw) {
    try {
        int number = Integer.parseInt(raw);
        return number > 0 ? Optional.of(number) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
```

Đây là phương thức minh họa cần `import java.util.Optional;`.

Nếu viết:

```java
Optional<Optional<Integer>> nested =
        Optional.of("12").map(MyClass::parsePositive);
```

bạn tạo **Optional lồng Optional**. Tại đây `MyClass` là tên class chứa `parsePositive`; thay bằng tên class thực tế. Để kết quả là `Optional<Integer>`, dùng:

```java
Optional<Integer> number =
        Optional.of("12").flatMap(MyClass::parsePositive);
```

Với nhiều chuỗi trong Stream:

```java
List<Integer> numbers = List.of("12", "bad", "-2", "5")
        .stream()
        .map(MyClass::parsePositive)
        .flatMap(Optional::stream)
        .toList();
// [12, 5]
```

Đây là ba **mảnh minh họa**, không phải tệp độc lập; chỉ cần chọn đúng tên class chứa `parsePositive`.

- `Optional.flatMap` hợp với **một Optional đầu vào** và hàm trả Optional.
- `Stream.map(...).flatMap(Optional::stream)` hợp với **nhiều phần tử** và hàm trả Optional.
- `Stream.filter(Optional::isPresent).map(Optional::get)` có thể hoạt động khi lập trình đúng và không có Optional null; tuy nhiên `flatMap(Optional::stream)` ngắn gọn hơn, không bóc Optional thủ công, và mô tả rõ ý định bỏ giá trị rỗng.

## 11. Chương trình Java 17: parse dữ liệu có thể lỗi, không gọi get

Lưu thành **`OptionalParsePipelineDemo.java`**:

```java
import java.util.List;
import java.util.Optional;

public class OptionalParsePipelineDemo {
    static Optional<Integer> parsePositive(String raw) {
        if (raw == null) {
            return Optional.empty();
        }

        try {
            int number = Integer.parseInt(raw.strip());
            return number > 0
                    ? Optional.of(number)
                    : Optional.empty();
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> input = List.of("12", "bad", "-2", "5", "20", " 7 ");

        List<Integer> parsed = input.stream()
                .map(OptionalParsePipelineDemo::parsePositive)
                .flatMap(Optional::stream)
                .toList();

        List<Integer> evens = input.stream()
                .map(OptionalParsePipelineDemo::parsePositive)
                .flatMap(Optional::stream)
                .filter(value -> value % 2 == 0)
                .toList();

        Optional<Optional<Integer>> nested =
                Optional.of("12").map(OptionalParsePipelineDemo::parsePositive);

        Optional<Integer> flattened =
                Optional.of("12").flatMap(OptionalParsePipelineDemo::parsePositive);

        System.out.println("parsed=" + parsed);
        System.out.println("evens=" + evens);
        System.out.println("nestedPresent=" + nested.isPresent());
        System.out.println("flattened=" + flattened.orElse(-1));
        System.out.println("invalid="
                + parsePositive("bad").orElse(-1));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OptionalParsePipelineDemo.java
java OptionalParsePipelineDemo
```

**Stdout chính xác:**

```text
parsed=[12, 5, 20, 7]
evens=[12, 20]
nestedPresent=true
flattened=12
invalid=-1
```

Trong danh sách `input`, `"bad"` không parse thành số và `"-2"` không thỏa quy tắc dương, nên cả hai được biến thành Optional rỗng. `" 7 "` được `strip` rồi parse thành `7`. Chuỗi `"12"` thành công; `map` tạo Optional lồng nhau, còn `flatMap` làm phẳng theo mong muốn.

**Giới hạn minh họa:** hàm `parsePositive` coi “không phải số” và “số không dương” đều là vắng mặt. Trong ứng dụng cần thông báo lỗi chi tiết, một kiểu kết quả có lý do thất bại thường tốt hơn việc xóa toàn bộ nguyên nhân bằng `Optional.empty()`.

## 12. Kết thúc Optional bằng orElse, orElseGet, or và orElseThrow

Khi đã có `Optional<T>`, bạn có nhiều cách xử lý thay `get()`:

| Phương thức | Khi Optional có giá trị | Khi Optional rỗng |
| --- | --- | --- |
| `ifPresent(action)` | Chạy action với giá trị | Không thực hiện action |
| `ifPresentOrElse(action, emptyAction)` | Chạy action | Chạy emptyAction |
| `orElse(value)` | Trả giá trị bên trong | Trả fallback đã đưa vào |
| `orElseGet(supplier)` | Trả giá trị bên trong | Gọi supplier rồi trả kết quả |
| `or(supplierOfOptional)` | Giữ Optional hiện có | Gọi supplier và lấy Optional dự phòng |
| `orElseThrow()` | Trả giá trị bên trong | Ném `NoSuchElementException` |
| `orElseThrow(exceptionSupplier)` | Trả giá trị bên trong | Ném exception do supplier tạo |
| `stream()` | Tạo Stream một phần tử | Tạo Stream rỗng |

**Phân biệt đánh giá fallback:** biểu thức đối số `orElse(fallback())` được tính trước khi gọi phương thức, kể cả khi Optional đang có giá trị. `orElseGet(() -> fallback())` chỉ gọi fallback khi Optional rỗng. `or` (Java 9+) trả **Optional**, không trả giá trị thô; supplier của `or` phải trả một Optional **không null**.

Dùng `orElseThrow` khi **vắng mặt là lỗi cần báo rõ**. Đó là cách chủ ý thiết lập một điều kiện bắt buộc, khác với `get()` thiếu kiểm tra hoặc thông báo.

## 13. Chương trình Java 17: fallback có kiểm soát

Tạo tệp **`OptionalFallbackDemo.java`**:

```java
import java.util.Optional;

public class OptionalFallbackDemo {
    static String fallback() {
        System.out.println("Tính fallback");
        return "guest";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("Lan");

        System.out.println("orElse=" + present.orElse(fallback()));
        System.out.println("orElseGet="
                + present.orElseGet(OptionalFallbackDemo::fallback));

        Optional<String> missing = Optional.empty();
        System.out.println("missing="
                + missing.orElseGet(OptionalFallbackDemo::fallback));

        Optional<String> recovered = Optional.<String>empty()
                .or(() -> Optional.of("backup"));
        System.out.println("recovered=" + recovered.orElse("none"));

        try {
            Optional.<String>empty()
                    .orElseThrow(() -> new IllegalArgumentException("missing"));
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OptionalFallbackDemo.java
java OptionalFallbackDemo
```

**Stdout chính xác:**

```text
Tính fallback
orElse=Lan
orElseGet=Lan
Tính fallback
missing=guest
recovered=backup
error=missing
```

Lần đầu `fallback()` chạy ngay vì là đối số của `orElse`. `orElseGet` với Optional có `"Lan"` **không** gọi supplier. Với Optional rỗng, supplier được gọi để trả `"guest"`. `or` dùng Optional dự phòng, còn `orElseThrow` báo lỗi có chủ đích.

Nếu không cần fallback đắt đỏ, `orElse("Khách")` là cách rõ ràng và hợp lý. Không nhất thiết thay mọi lời gọi `orElse` bằng `orElseGet`.

## 14. Chú ý null, Optional null và lỗi trong pipeline

**Optional không chứa null**, nhưng một biến kiểu `Optional<T>` vẫn có thể bị gán tham chiếu `null`. Khi dùng:

```java
List<Optional<String>> values = List.of(
        Optional.of("A"),
        Optional.empty()
);
```

bạn có danh sách không chứa tham chiếu Optional null. Nếu nguồn từ API cũ có thể đưa vào `null` thay vì `Optional.empty()`, thì `flatMap(Optional::stream)` sẽ ném `NullPointerException` khi gặp phần tử null. Hãy chuẩn hóa dữ liệu hoặc sửa API nguồn để không trả null thay cho Optional rỗng.

**Đừng nhầm Optional rỗng với exception.** Một Optional không tìm thấy là trạng thái dự kiến nếu hợp đồng nghiệp vụ cho phép; kết quả parse thất bại hoặc truy vấn bị lỗi hệ thống có thể cần thông báo lỗi đầy đủ. Nếu bắt mọi exception rồi trả `Optional.empty()`, bạn có thể che giấu sự cố thật.

**Map không đồng nghĩa flatMap:** `Optional.map` bọc kết quả khác null trong Optional; `Optional.flatMap` đòi mapper trả Optional không null. `Stream.flatMap(Optional::stream)` chỉ áp dụng trực tiếp cho Stream **các Optional**, không phải Stream các đối tượng thường.

**Không nên tự sửa nguồn trong lambda:** với Stream, ưu tiên các hàm stateless và non-interfering. Việc map một ID sang repository có I/O có thể cần quản lý lỗi, timeout và hiệu năng; dùng Stream không tự đem lại xử lý bất đồng bộ hoặc cơ chế retry.

## 15. Tính thứ tự, hiệu năng và xử lý song song

Với một `List` có encounter order, pipeline:

```java
List<String> results = ids.stream()
        .map(repository::findById)
        .flatMap(Optional::stream)
        .map(User::name)
        .toList();
```

giữ thứ tự các kết quả có mặt theo ID nguồn (nếu không có bước phá encounter order). Đây là **mảnh mã minh họa** với `ids`, `repository`, `User` được khai báo trong ứng dụng.

Với `parallelStream()`, các lời gọi mapper có thể thực hiện trên nhiều thread, nhưng `toList()` trên Stream có encounter order vẫn giữ thứ tự kết quả. Điều đó **không đảm bảo repository an toàn luồng**, không bảo đảm thứ tự gọi dữ liệu bên ngoài, và không làm I/O tự nhanh hơn. Tránh đưa một client không thread-safe hoặc shared mutable state vào parallel pipeline.

Nếu danh sách lớn và phần lớn Optional rỗng, `flatMap(Optional::stream)` tạo kết quả đúng theo nghĩa bỏ vắng mặt, nhưng không phải cam kết hiệu năng tối ưu cho mọi workload. Hãy đo trong bối cảnh thực tế thay vì mặc định rằng các toán tử này luôn nhanh hơn vòng lặp.

## 16. Mẫu quyết định nhanh

| Nhu cầu | Mẫu dùng |
| --- | --- |
| Có một Optional, muốn biến đổi giá trị nếu có | `optional.map(f)` |
| Có một Optional, hàm xử lý trả Optional | `optional.flatMap(f)` |
| Có một Optional, muốn lọc theo điều kiện | `optional.filter(p)` |
| Có nhiều Optional, muốn bỏ các Optional rỗng | `optionals.stream().flatMap(Optional::stream)` |
| Mỗi đối tượng có thể tìm ra Optional từ repository | `ids.stream().map(repo::find).flatMap(Optional::stream)` |
| Stream có thể không có phần tử, muốn lấy giá trị đầu tiên hoặc mặc định | `stream.findFirst().orElse(defaultValue)` |
| Vắng mặt là lỗi nghiệp vụ | `optional.orElseThrow(() -> new ...)` |
| Fallback cần tính lười | `optional.orElseGet(() -> createFallback())` |
| Muốn Optional dự phòng | `optional.or(() -> otherOptional())` |
| Có giá trị nullable muốn đưa vào Stream | `Stream.ofNullable(value)` |

Các tên `f`, `p`, `repo`, `otherOptional` và `createFallback` là **mẫu mô tả**, cần khai báo phù hợp trong code thực tế. Mục tiêu là chọn toán tử biểu thị đúng ý định, không ép mọi bài toán thành một pipeline dài khó đọc.

## 17. Lỗi thường gặp và bài tập

Những lỗi thường gặp:

1. **Gọi `get()` ngay sau `findFirst()`** mà không xử lý Stream rỗng.
2. **Gọi `map(Optional::get)`** trên Stream chứa Optional rỗng.
3. **Dùng `map(Optional::stream)` rồi quên làm phẳng**, tạo Stream của Stream.
4. **Dùng `Optional.map` khi hàm trả Optional**, tạo `Optional<Optional<R>>` không cần thiết.
5. **Cho rằng Optional.stream trả luôn nhiều phần tử**; nó chỉ tạo 0 hoặc 1 phần tử.
6. **Dùng `orElse(expensiveFallback())` và tin fallback chỉ chạy khi rỗng**.
7. **Cho rằng `orElseGet` trả Optional**; thực ra trả giá trị `T`; `or` mới trả Optional.
8. **Cho rằng Stream.of(null) tương đương Stream.ofNullable(null)**; một cái có thể chứa phần tử null, một cái trả Stream rỗng.
9. **Cho rằng Optional của repository rỗng nghĩa là có lỗi hệ thống**; có thể chỉ là không tìm thấy, tùy hợp đồng.
10. **Bỏ qua lỗi nghiệp vụ bằng flatMap(Optional::stream)** trong khi yêu cầu bắt buộc tất cả ID phải tồn tại.
11. **Dùng parallel stream với repository không thread-safe** hoặc dựa vào thứ tự side effect.
12. **Cho rằng List<Optional<T>> là bắt buộc**; đôi khi API trả `Stream<T>` hoặc một tập kết quả giàu thông tin sẽ phù hợp hơn.

**Câu 1.** `Optional.empty().stream().count()` bằng bao nhiêu?

**Đáp án:** `0`.

**Câu 2.** `List.of(Optional.of("A"), Optional.empty(), Optional.of("B")).stream().flatMap(Optional::stream).toList()` cho kết quả gì?

**Đáp án:** `[A, B]`; Optional rỗng không tạo phần tử.

**Câu 3.** Khi `findById` trả `Optional<User>`, nên dùng `map(Optional::get)` hay `flatMap(Optional::stream)` nếu mục tiêu là bỏ ID không tồn tại?

**Đáp án:** `flatMap(Optional::stream)`, vì nó chuyển Optional rỗng thành Stream rỗng, không ném ngoại lệ do `get()`.

**Câu 4.** Nếu vắng mặt là lỗi bắt buộc phải biết, có nên dùng `flatMap(Optional::stream)` không?

Không nên âm thầm bỏ qua. Có thể dùng `orElseThrow` với thông báo chứa ID hoặc kiểu kết quả thể hiện thất bại.

**Câu 5.** Với `Optional.of("12")` và `parsePositive(String)` trả `Optional<Integer>`, nên dùng `map` hay `flatMap` để nhận `Optional<Integer>`?

**Đáp án:** `flatMap`, vì `map` sẽ tạo Optional lồng nhau.

**Câu 6.** `Stream.ofNullable(null).count()` bằng bao nhiêu?

**Đáp án:** `0`; không có phần tử null được đưa vào Stream.

**Câu 7.** `orElse` khác `orElseGet` thế nào khi fallback có side effect?

`orElse(f())` đánh giá `f()` trước khi gọi, kể cả Optional có giá trị. `orElseGet(() -> f())` chỉ gọi `f()` nếu Optional rỗng.

**Câu 8.** Vì sao `findFirst()` có thể vẫn ném `NullPointerException` dù trả Optional?

Vì Optional không chứa null; nếu Stream chứa null và phần tử được chọn là null, terminal không thể tạo một Optional có mặt hợp lệ. Lọc null trước khi dùng terminal.

**Ghi nhớ:** Với **một Optional**, dùng `map`/`filter`/`flatMap` và kết thúc bằng `orElse`, `orElseGet`, `or` hoặc `orElseThrow` theo ý nghĩa nghiệp vụ. Với **Stream các Optional**, dùng **`flatMap(Optional::stream)`** để biến “có hoặc không có” thành “một hoặc không phần tử”, tránh gọi `get()` tùy tiện.
