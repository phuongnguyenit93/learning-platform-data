# Không trả Optional null hoặc gọi get vô điều kiện trong Java

`Optional<T>` biểu diễn **một kết quả có thể có hoặc không có giá trị**. Khi một phương thức khai báo trả `Optional<User>`, bên gọi kỳ vọng **luôn nhận được một đối tượng Optional hợp lệ**, rồi kiểm tra hoặc xử lý trường hợp rỗng bằng API của Optional. Có hai lỗi cơ bản cần tránh:

1. **`return null` từ phương thức trả `Optional<T>`**: phá vỡ hợp đồng. Bên gọi có thể ném `NullPointerException` ngay khi gọi `map`, `orElse`, `isPresent`...
2. **`optional.get()` mà không chứng minh giá trị tồn tại**: `get()` ném `NoSuchElementException` nếu Optional rỗng. Nếu dữ liệu có thể vắng mặt, đây không phải cách xử lý thiếu dữ liệu.

Các API được đề cập ở đây vẫn áp dụng trong Java hiện đại. `Optional` có từ Java 8; một số API tiện lợi như `Optional.stream`, `ifPresentOrElse` và `or` có từ Java 9; `orElseThrow()` không tham số có từ Java 10; `isEmpty()` có từ Java 11. Chương trình đầy đủ trong bài ưu tiên **JDK 17+**, đồng thời chỉ ra cách áp dụng logic trên Java 8.

## 1. Hiểu đúng hợp đồng của `Optional<T>`

Một đối tượng Optional ở trạng thái **present** có chứa một giá trị **không null**. Optional ở trạng thái **empty** không có giá trị. Nhưng **biến tham chiếu kiểu `Optional<T>` vẫn có thể được gán `null` theo cú pháp Java**; kiểu khai báo không tự ngăn việc đó. Vì vậy quy tắc thiết kế quan trọng là **không dùng `null` để biểu diễn một Optional rỗng**.

| Biểu thức | Giá trị tham chiếu Optional | Ý nghĩa | Kết quả khi gọi `orElse("default")` |
| --- | --- | --- | --- |
| `Optional.of("An")` | Không null, **present** | Có giá trị `"An"` | `"An"` |
| `Optional.empty()` | Không null, **empty** | Không có giá trị | `"default"` |
| `Optional.ofNullable(null)` | Không null, **empty** | Chuyển dữ liệu nullable thành Optional rỗng | `"default"` |
| `Optional.ofNullable("An")` | Không null, **present** | Có giá trị `"An"` | `"An"` |
| `Optional<String> x = null` | **null reference** | Sai hợp đồng sử dụng Optional | **`NullPointerException`** |

So sánh:

```java
Optional<String> correctMissing = Optional.empty();
// correctMissing.orElse("default") == "default"

Optional<String> wrongMissing = null;
// wrongMissing.orElse("default"); // NullPointerException
```

Hai dòng trên là **đoạn mã minh họa**, giả định đã import `java.util.Optional`. Khi một API trả Optional, **vắng mặt là `Optional.empty()`**, không phải `null`. Nếu cần biểu diễn **lỗi truy vấn**, **không có quyền truy cập**, hoặc **không hợp lệ**, đó lại là các trạng thái khác: dùng ngoại lệ, kiểu kết quả chuyên biệt hoặc mô hình domain rõ nghĩa, không lặng lẽ chuyển mọi lỗi thành empty.

### Tại sao không nên viết `Optional.of(null)`?

`Optional.of(value)` **yêu cầu tham số không null**; gọi với `null` ném `NullPointerException` ngay lúc tạo Optional.

- Dùng `Optional.of(value)` khi hợp đồng bảo đảm `value != null`, và vi phạm hợp đồng cần được phát hiện.
- Dùng `Optional.ofNullable(value)` khi giá trị đầu vào **được phép null** và muốn quy đổi null thành absence.
- Dùng `Optional.empty()` khi biết chắc không có kết quả.
- Không viết `return null` trong bất kỳ nhánh trả về nào của phương thức `Optional<T>`.

`Optional.empty()` không phải chỉ là một object mới do ứng dụng tự tạo; không so sánh Optional bằng identity `==` để xác định rỗng, vì hợp đồng không đảm bảo instance nào luôn là singleton. Dùng các phép toán của Optional như `isPresent`, `isEmpty` hoặc xử lý giá trị theo pipeline.

## 2. Mẫu API trả Optional: đúng và sai

Giả sử tầng ứng dụng tìm một người dùng theo ID và **không tìm thấy** là tình huống bình thường.

**Sai — trả `null` thay cho Optional rỗng:**

```java
// Phản ví dụ: không viết như thế này.
Optional<User> findById(String id) {
    User user = lookupNullable(id);
    if (user == null) {
        return null; // Sai hợp đồng Optional<User>.
    }
    return Optional.of(user);
}
```

Đây là ví dụ **độc lập về ý tưởng, không phải chương trình hoàn chỉnh**, vì `User` và `lookupNullable` thuộc domain tùy ứng dụng. Lỗi chính là nhánh `return null`.

**Đúng — chuyển nullable data sang Optional:**

```java
Optional<User> findById(String id) {
    User user = lookupNullable(id);
    return Optional.ofNullable(user);
}
```

Nếu repository trả Optional ngay từ đầu, hãy **trả Optional đó** và bảo đảm repository tuân thủ hợp đồng; không bao nó bằng `Optional.ofNullable` thêm lần nữa, vì sẽ tạo ra kiểu `Optional<Optional<User>>` không đúng ý định.

**Đúng — truy vấn bằng Stream và trả kết quả của terminal operation:**

```java
Optional<User> findById(String id) {
    return users.stream()
            .filter(u -> u.id().equals(id))
            .findFirst();
}
```

`findFirst()` trả `Optional.empty()` nếu Stream không có phần tử phù hợp; không cần tự viết `if (...) return null`. Với Stream có thứ tự, `findFirst` lấy phần tử đầu tiên theo encounter order. Đoạn minh họa giả định `users` là một collection có các phần tử `User` hợp lệ, và mã đang nằm trong class có thể truy cập nó.

### Ranh giới trách nhiệm

Một phương thức khai báo trả `Optional<T>` đang đưa ra **hợp đồng cho bên gọi**: hoặc present, hoặc empty; **không có trạng thái thứ ba là Optional tham chiếu null**. Điều này rất quan trọng khi API được gọi ở nhiều lớp:

```text
Repository.findById(id) -> Optional<User>
        ↓
Service xử lý present/empty
        ↓
Controller trả dữ liệu/404 hoặc trạng thái phù hợp
```

Chỉ một nhánh `return null` ở repository có thể khiến tất cả bên gọi phụ thuộc vào API này gặp `NullPointerException`, bất kể họ đã viết `orElse` hay `map` đúng cách.

## 3. Vì sao `get()` vô điều kiện nguy hiểm?

`Optional.get()` trả giá trị nếu present; nếu empty, nó ném `NoSuchElementException`.

```java
Optional<String> result = Optional.empty();
// String value = result.get(); // Ném NoSuchElementException.
```

Trường hợp này đặc biệt dễ xảy ra khi lấy kết quả từ `findFirst`, `min`, `max`, tìm kiếm database, đọc cấu hình tùy chọn hoặc chuyển đổi dữ liệu có thể thất bại.

**`get()` hiện vẫn tồn tại trong Java API**, không phải “đã bị xóa”. Vấn đề là **gọi vô điều kiện** khi có thể empty. Nếu đã kiểm tra `isPresent()` ngay trong cùng luồng điều khiển thì `get()` có thể dùng an toàn, nhưng thường **dài và khó biểu đạt mục đích** hơn `map`, `ifPresent`, `orElseThrow` hay `orElseGet`.

Ví dụ:

```java
// Có kiểm tra nên không ném do Optional rỗng,
// nhưng thường không diễn đạt ý định gọn bằng cách bên dưới.
if (result.isPresent()) {
    System.out.println(result.get());
}

// Rõ ràng hơn nếu chỉ muốn thực hiện hành động khi có giá trị:
result.ifPresent(System.out::println);
```

Đoạn trên giả định `result` là một Optional **khác null** và đang ở trong một phương thức hợp lệ. Trên Java 11+, khi phải kiểm tra absence bằng điều kiện, có thêm `result.isEmpty()`; trên Java 8 dùng `!result.isPresent()`.

### Chọn cách lấy giá trị theo ngữ nghĩa

| Ý định | API | Khi empty |
| --- | --- | --- |
| Có giá trị thì thực hiện một hành động | `ifPresent(Consumer)` | Không làm gì |
| Có thì làm A, không có làm B (Java 9+) | `ifPresentOrElse(Consumer, Runnable)` | Chạy B |
| Có thì biến đổi, không có tiếp tục rỗng | `map(Function)` | Trả Optional rỗng |
| Giá trị dự phòng đã có sẵn và rẻ | `orElse(fallback)` | Trả fallback |
| Dự phòng tạo tốn chi phí/có side effect | `orElseGet(Supplier)` | Gọi supplier khi cần |
| Thiếu giá trị là lỗi nghiệp vụ | `orElseThrow(() -> new DomainException(...))` | Ném ngoại lệ đã chọn |
| Thiếu giá trị là lỗi và không cần custom message (Java 10+) | `orElseThrow()` | Ném `NoSuchElementException` |
| Chuỗi thao tác Optional khác | `flatMap(Function<T,Optional<U>>)` | Vẫn rỗng nếu nguồn rỗng |

Điểm mấu chốt không phải “luôn chọn một phương thức”, mà là **quyết định ý nghĩa của trường hợp empty trước khi gọi**.

## 4. Ví dụ đầy đủ: repository không trả Optional null

Tạo tệp `OptionalContractDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class OptionalContractDemo {
    record User(String id, String name) {}

    static final List<User> DB = List.of(
            new User("u1", "An"),
            new User("u2", "Binh"));

    static Optional<User> findUser(String id) {
        return DB.stream()
                .filter(u -> u.id().equals(id))
                .findFirst();
    }

    static Optional<String> nickname(String raw) {
        return Optional.ofNullable(raw)
                .map(String::trim)
                .filter(s -> !s.isEmpty());
    }

    public static void main(String[] args) {
        System.out.println("found = "
                + findUser("u1").map(User::name).orElse("(none)"));
        System.out.println("missing present = "
                + findUser("u9").isPresent());

        System.out.println("null input = " + nickname(null));
        System.out.println("blank input = " + nickname("  "));
        System.out.println("trimmed input = " + nickname("  Chi  "));

        try {
            findUser("u9").orElseThrow(
                    () -> new IllegalArgumentException("User not found"));
        } catch (IllegalArgumentException ex) {
            System.out.println("missing error = " + ex.getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 OptionalContractDemo.java
java OptionalContractDemo
```

Đầu ra chính xác:

```text
found = An
missing present = false
null input = Optional.empty
blank input = Optional.empty
trimmed input = Optional[Chi]
missing error = User not found
```

Giải thích:
- `findUser("u1")` là present nên `map(User::name)` nhận tên `"An"`.
- `findUser("u9")` không khớp dữ liệu; `findFirst()` trả `Optional.empty()`, không phải `null`.
- `nickname(null)` dùng `ofNullable` nên vẫn có đối tượng Optional hợp lệ, rỗng.
- `nickname("  ")` qua `trim` thành chuỗi trống và bị `filter` loại, cũng là Optional rỗng.
- `nickname("  Chi  ")` qua `trim` thành `"Chi"` và giữ present.
- `orElseThrow` với supplier truyền ngoại lệ nghiệp vụ khi người dùng được yêu cầu nhưng không tìm thấy.

Ví dụ dùng `record` và `List.of`, do đó yêu cầu JDK 17+; thiết kế API Optional vẫn dùng được trên Java 8 với class `User` thông thường và `Arrays.asList`.

## 5. `orElse` và `orElseGet`: bẫy đánh giá eager/lazy

Hai phương thức sau **khác nhau** ngay cả khi Optional đã có giá trị:

```java
String a = optional.orElse(createFallback());
String b = optional.orElseGet(() -> createFallback());
```

Đối số của `orElse` là một biểu thức Java bình thường. Java đánh giá `createFallback()` **trước khi gọi `orElse`**, bất kể Optional có present hay không. `orElseGet` nhận `Supplier` và **chỉ gọi supplier nếu Optional rỗng**.

Nếu dự phòng là hằng `"unknown"`, `orElse("unknown")` rất rõ ràng. Nếu dự phòng phải gọi database, cấp mã mới hoặc có side effect, dùng `orElseGet` để tránh thực thi thừa.

Tạo tệp `OptionalChoiceDemo.java`:

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalChoiceDemo {
    static String fallback(AtomicInteger hits) {
        hits.incrementAndGet();
        return "generated";
    }

    public static void main(String[] args) {
        AtomicInteger hits = new AtomicInteger();
        Optional<String> present = Optional.of("real");

        System.out.println("orElse = "
                + present.orElse(fallback(hits)));
        System.out.println("hits after orElse = " + hits.get());

        System.out.println("orElseGet = "
                + present.orElseGet(() -> fallback(hits)));
        System.out.println("hits after orElseGet = " + hits.get());

        System.out.println("empty default = "
                + Optional.<String>empty()
                        .orElseGet(() -> fallback(hits)));
        System.out.println("hits final = " + hits.get());
    }
}
```

```bash
javac -encoding UTF-8 OptionalChoiceDemo.java
java OptionalChoiceDemo
```

```text
orElse = real
hits after orElse = 1
orElseGet = real
hits after orElseGet = 1
empty default = generated
hits final = 2
```

`orElse` đã tạo fallback một lần **dù trả về `"real"`**; `orElseGet` không gọi fallback khi present, nhưng gọi khi empty. Đây là khác biệt về thực thi, không phải chỉ là phong cách đặt tên.

`orElseThrow(() -> new IllegalStateException("missing"))` cũng dùng supplier: ngoại lệ chỉ được tạo và ném khi Optional rỗng. Trái lại, `orElseThrow()` không đối số (Java 10+) ném `NoSuchElementException` khi rỗng; nó không mô tả lỗi domain cụ thể.

## 6. Biến đổi Optional thay vì tách ra rồi tự kiểm tra null

Optional được thiết kế để xử lý theo chuỗi: `map`, `filter`, `flatMap`, rồi một thao tác lấy kết quả ở biên.

### `map` và `filter`

```java
String displayName = Optional.ofNullable(input)
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .map(String::toUpperCase)
        .orElse("NO_NAME");
```

Đoạn mã minh họa đặt trong phương thức có khai báo `input`. Nếu `input == null` hoặc sau `trim` thành chuỗi rỗng, kết quả `"NO_NAME"`; nếu có tên hợp lệ thì tạo chuỗi in hoa.

- `map` biến đổi **giá trị hiện diện**; nếu nguồn empty, hàm không được gọi.
- `filter` giữ present khi predicate đúng và trả empty khi predicate sai.
- `flatMap` dùng khi mapper **đã trả về Optional**; nó tránh tạo Optional lồng nhau.

### `map` khác `flatMap` ở cách xử lý null

Theo hợp đồng Java Optional:

```java
Optional<String> x = Optional.of("a")
        .map(s -> (String) null);
// x là Optional.empty()

// Phản ví dụ: mapper cho flatMap không được trả null.
// Optional.of("a").flatMap(s -> (Optional<String>) null);
// NullPointerException
```

`map` chuyển kết quả mapper null thành Optional rỗng, nhưng **không nên lạm dụng** để che lỗi từ mapper vô tình trả null: hãy xác định null có thật sự nghĩa là “không có giá trị” hay không. `flatMap` yêu cầu mapper trả một **Optional không null**; nếu mapper trả `null` thì `NullPointerException`. Hợp đồng “không trả Optional null” áp dụng cả với hàm mapper của `flatMap` và supplier của `Optional.or`.

### `map` không nuốt ngoại lệ

Nếu callback ném `NumberFormatException`, `NullPointerException` hoặc ngoại lệ khác, Optional **không tự bắt rồi đổi tất cả thành empty**. Muốn coi dữ liệu không hợp lệ là absence, hãy chuyển đổi theo một chính sách được viết rõ; nếu lỗi bất thường, để ngoại lệ được xử lý ở nơi có trách nhiệm.

## 7. Ví dụ đầy đủ: `map`, `flatMap`, Optional rỗng và các ngoại lệ

Tạo tệp `OptionalFlowDemo.java`:

```java
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.stream.Stream;

public class OptionalFlowDemo {
    static Optional<String> normalize(String text) {
        return Optional.ofNullable(text)
                .map(String::trim)
                .filter(s -> !s.isEmpty());
    }

    static Optional<Integer> parsePositiveInt(String s) {
        try {
            int value = Integer.parseInt(s);
            return value > 0 ? Optional.of(value) : Optional.empty();
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        System.out.println("map/filter = "
                + normalize("  An ").map(String::toUpperCase)
                        .orElse("NO_NAME"));

        System.out.println("flatMap = "
                + normalize(" 25 ")
                        .flatMap(OptionalFlowDemo::parsePositiveInt));
        System.out.println("invalid parse = "
                + normalize("abc")
                        .flatMap(OptionalFlowDemo::parsePositiveInt));

        System.out.println("map null = "
                + Optional.of("x").map(s -> (String) null));

        System.out.println("stream values = "
                + Stream.of(
                                Optional.of("A"),
                                Optional.<String>empty(),
                                Optional.of("B"))
                        .flatMap(Optional::stream)
                        .toList());

        System.out.println("empty stream = "
                + Stream.<String>empty().findFirst());

        try {
            Optional.<String>empty().get();
        } catch (NoSuchElementException ex) {
            System.out.println("unsafe get = NoSuchElementException");
        }

        try {
            Optional.of(null);
        } catch (NullPointerException ex) {
            System.out.println("of null = NullPointerException");
        }

        try {
            Optional.of("ok")
                    .flatMap(s -> (Optional<String>) null);
        } catch (NullPointerException ex) {
            System.out.println("flatMap null = NullPointerException");
        }
    }
}
```

```bash
javac -encoding UTF-8 OptionalFlowDemo.java
java OptionalFlowDemo
```

```text
map/filter = AN
flatMap = Optional[25]
invalid parse = Optional.empty
map null = Optional.empty
stream values = [A, B]
empty stream = Optional.empty
unsafe get = NoSuchElementException
of null = NullPointerException
flatMap null = NullPointerException
```

Các điểm quan trọng:
- `normalize(" 25 ")` trả Optional present sau `trim`; `flatMap(parsePositiveInt)` tạo `Optional[25]` chứ không phải `Optional[Optional[25]]`.
- `parsePositiveInt` coi chuỗi sai định dạng hoặc giá trị không dương là “không có số hợp lệ”. Đây là **quyết định nghiệp vụ của ví dụ**; trong ứng dụng khác, sai định dạng có thể cần thông báo lỗi thay vì empty.
- `Optional.stream()` (Java 9+) biến present thành Stream một phần tử, empty thành Stream rỗng. `flatMap(Optional::stream)` gộp danh sách các Optional. `Stream.toList()` là API Java 16+.
- `Optional.get()` trên empty gây `NoSuchElementException`, trong khi `Optional.of(null)` hoặc mapper `flatMap` trả null gây `NullPointerException`. Hai loại lỗi cho thấy các hợp đồng khác nhau.
- Việc `map(s -> null)` trả empty không nên được coi là cách che giấu mọi bug null trong business logic.

## 8. Xử lý present và empty không cần gọi `get`

Nếu chỉ muốn thực hiện một hành động khi có giá trị, dùng `ifPresent`:

```java
Optional.of("An").ifPresent(System.out::println); // in An
Optional.<String>empty().ifPresent(System.out::println); // không in
```

Nếu cần cả hai nhánh (Java 9+):

```java
Optional.of("An").ifPresentOrElse(
        name -> System.out.println("Hello " + name),
        () -> System.out.println("No name"));

Optional.<String>empty().ifPresentOrElse(
        name -> System.out.println("Hello " + name),
        () -> System.out.println("No name"));
```

Đoạn minh họa giả định đã import `Optional`. `ifPresent`/`ifPresentOrElse` phù hợp với hành động (logging, UI display, emit event...) cần quản lý rõ ràng; không được suy ra việc sử dụng side effect trong Optional luôn tốt hơn trả về một giá trị từ `map`.

### Ví dụ đầy đủ: API bổ sung của Java hiện đại

Tạo tệp `OptionalCurrentApiDemo.java`:

```java
import java.util.NoSuchElementException;
import java.util.Optional;

public class OptionalCurrentApiDemo {
    public static void main(String[] args) {
        System.out.println("isEmpty = "
                + Optional.<String>empty().isEmpty());

        System.out.println("or = "
                + Optional.<String>empty()
                        .or(() -> Optional.of("fallback")));

        Optional.of("An").ifPresentOrElse(
                s -> System.out.println("present action = " + s),
                () -> System.out.println("empty action"));

        Optional.<String>empty().ifPresentOrElse(
                s -> System.out.println("present action = " + s),
                () -> System.out.println("empty action"));

        try {
            Optional.<String>empty().orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println(
                    "orElseThrow empty = NoSuchElementException");
        }

        Optional.of("present").ifPresent(
                x -> System.out.println("ifPresent = " + x));
    }
}
```

```bash
javac -encoding UTF-8 OptionalCurrentApiDemo.java
java OptionalCurrentApiDemo
```

```text
isEmpty = true
or = Optional[fallback]
present action = An
empty action
orElseThrow empty = NoSuchElementException
ifPresent = present
```

Phân biệt:
- `isEmpty()` (Java 11+) hỏi có thiếu giá trị hay không.
- `or(() -> Optional.of("fallback"))` (Java 9+) trả **Optional thay thế** khi rỗng, khác `orElse` trả `T`. Supplier của `or` phải trả Optional hợp lệ, không null.
- `ifPresentOrElse` (Java 9+) chạy đúng một nhánh.
- `orElseThrow()` không tham số (Java 10+) mô tả rõ rằng bắt buộc phải có giá trị, nếu không thì ném `NoSuchElementException`. Nếu muốn ngoại lệ có ý nghĩa nghiệp vụ, truyền supplier từ Java 8.
- Không cần thay `Optional.get()` bằng `orElseThrow()` một cách máy móc mà bỏ qua yêu cầu empty có phải lỗi hay không.

## 9. Optional rỗng khác với giá trị có cấu trúc nhưng rỗng

Một tình huống dễ nhầm khác là `Optional<List<T>>`:
- `Optional.empty()`: **không có đối tượng List** được trả về.
- `Optional.of(List.of())`: **có List**, nhưng List không có phần tử.
- `Optional.ofNullable(nullableList)`: có thể chứa một List (kể cả List rỗng), hoặc không có List nếu nguồn null.

Đừng mặc định hai trạng thái này giống nhau. Trong một API, “chưa có kết quả truy vấn” và “truy vấn thành công nhưng tập kết quả rỗng” có thể mang ý nghĩa khác nhau. Nếu phương thức chỉ trả **danh sách những phần tử tìm thấy**, có khi trả `List.of()` trực tiếp rõ hơn `Optional<List<T>>`; nếu absence của chính danh sách có nghĩa nghiệp vụ riêng, Optional có thể phù hợp.

Tạo tệp `OptionalSemanticsDemo.java`:

```java
import java.util.List;
import java.util.Optional;

public class OptionalSemanticsDemo {
    // Phản ví dụ cố ý để chứng minh hậu quả.
    static Optional<String> broken() {
        return null;
    }

    public static void main(String[] args) {
        Optional<List<String>> absent = Optional.empty();
        Optional<List<String>> presentEmpty = Optional.of(List.of());

        System.out.println("absent list present = "
                + absent.isPresent());
        System.out.println("present empty list present = "
                + presentEmpty.isPresent());
        System.out.println("present empty list size = "
                + presentEmpty.orElseThrow().size());
        System.out.println("absent list fallback = "
                + absent.orElseGet(List::of).size());

        try {
            broken().orElse("default");
        } catch (NullPointerException ex) {
            System.out.println(
                    "null Optional = NullPointerException");
        }
    }
}
```

```bash
javac -encoding UTF-8 OptionalSemanticsDemo.java
java OptionalSemanticsDemo
```

```text
absent list present = false
present empty list present = true
present empty list size = 0
absent list fallback = 0
null Optional = NullPointerException
```

Trong ví dụ này `broken()` **cố tình sai hợp đồng** nhưng được bắt ngoại lệ để chương trình vẫn hoàn tất. Hai danh sách đều có kích thước `0` khi lấy ra, nhưng trạng thái present khác nhau. Kết quả của `broken().orElse("default")` chứng minh `orElse` **không sửa được** phương thức trả tham chiếu Optional bằng `null`.

## 10. Tích hợp với API cũ trả nullable value: chuyển tại ranh giới

Không phải mọi thư viện đều trả Optional. Một API có thể trả `User` hoặc `null` khi không tìm thấy; khi xây lớp adapter mới trả Optional, chuyển **giá trị nullable** một lần:

```java
// Đặt trong lớp có phương thức legacyLookup(id) trả User hoặc null.
Optional<User> findFromLegacy(String id) {
    User user = legacyLookup(id);
    return Optional.ofNullable(user);
}
```

**Không viết:**

```java
// Nếu modernFind(id) đã có kiểu Optional<User>,
// code dưới sẽ ra Optional<Optional<User>>.
Optional<Optional<User>> nested = Optional.ofNullable(modernFind(id));
```

Đoạn trên minh họa sai thiết kế, không phải chương trình độc lập. `ofNullable` chỉ đổi **tham chiếu đầu vào nullable** thành Optional, không “sửa” Optional vốn đã có hợp đồng riêng.

Nếu một dependency **cam kết trả Optional nhưng thực tế trả null**, đây là **lỗi hợp đồng**. Có thể phát hiện sớm bằng:

```java
Optional<User> result = Objects.requireNonNull(
        service.findById(id), "findById returned null Optional");
```

Đoạn này giả định đã import `java.util.Objects` và có sẵn `service`, `id`, `User`. `requireNonNull` không chữa lỗi nhưng tạo điểm báo lỗi rõ hơn. **Không tự động biến Optional null từ một API đã cam kết thành Optional.empty()** nếu điều đó làm che giấu bug hoặc dẫn đến hiểu sai “không tìm thấy”.

Nếu cần chuẩn hóa dữ liệu từ hệ thống legacy, nên phân biệt rõ:
- Giá trị `T == null` theo hợp đồng cũ có nghĩa là **not found** ⇒ `Optional.ofNullable(value)`.
- Lỗi network/DB/permission ⇒ theo quy ước lỗi của tầng ứng dụng, **không mặc định `Optional.empty()`**.
- Một phương thức đã khai báo `Optional<T>` lại trả `null` ⇒ **vi phạm hợp đồng**; nên sửa tại nguồn và bổ sung test.

## 11. Không dùng Optional thay cơ chế báo lỗi

`Optional.empty()` nói “không có giá trị”, nhưng **không giải thích tại sao**. Nó phù hợp với tìm kiếm không có kết quả, tham số không bắt buộc, lựa chọn có thể bỏ trống. Nó không phù hợp khi bên gọi cần phân biệt nhiều nguyên nhân.

Ví dụ, một hàm parse số dương có thể chọn chính sách:
- Chuỗi không phải số hoặc giá trị không dương ⇒ empty vì không có **số dương hợp lệ**.
- Một lỗi nghiêm trọng không liên quan đầu vào (cấu hình sai, database hỏng, kiểm tra bảo mật thất bại) ⇒ xử lý/đẩy lên ngoại lệ hoặc kiểu kết quả mô tả rõ lỗi.

Không viết một `catch (Exception e) { return Optional.empty(); }` bao mọi loại ngoại lệ chỉ để tránh xử lý lỗi. Cách đó có thể che mất vấn đề vận hành và biến “hệ thống thất bại” thành “không tìm thấy”.

Một cách an toàn trong ứng dụng là đặt tên method biểu thị nghĩa absence, ví dụ `findUser` trả Optional, còn `requireUser` trả User và ném ngoại lệ cụ thể khi không tồn tại:

```java
// Đoạn mã minh họa trong class có phương thức findUser(id).
User requireUser(String id) {
    return findUser(id).orElseThrow(
            () -> new IllegalArgumentException(
                    "User does not exist: " + id));
}
```

Ở đây **thiếu User bị xem là lỗi** trong thao tác `requireUser`, nên ngoại lệ được chỉ rõ. Nhưng `findUser` vẫn có quyền trả empty bình thường. Cả hai cách đúng tùy **hợp đồng nghiệp vụ**, không phải do sự tồn tại của một API duy nhất.

## 12. Optional và Stream: tránh `get()` khi lọc dữ liệu

Các terminal operation của Stream như `findFirst`, `findAny`, `min`, `max` có thể trả Optional vì đầu vào có thể rỗng. Tránh kiểu:

```java
String first = names.stream()
        .filter(s -> s.startsWith("A"))
        .findFirst()
        .get(); // Có thể ném NoSuchElementException.
```

Đoạn minh họa giả định đã có `names`. Thay thế đúng phụ thuộc yêu cầu:

```java
String display = names.stream()
        .filter(s -> s.startsWith("A"))
        .findFirst()
        .orElse("No matching name");

String required = names.stream()
        .filter(s -> s.startsWith("A"))
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("No name beginning with A"));
```

Khi muốn giữ kết quả có thể thiếu để lớp sau quyết định, **đừng ép lấy giá trị ngay**:

```java
Optional<String> match = names.stream()
        .filter(s -> s.startsWith("A"))
        .findFirst();
```

`Optional.stream()` (Java 9+) còn giúp xử lý nhiều Optional thành Stream giá trị present:

```java
List<String> presentNames = Stream.of(
                Optional.of("An"),
                Optional.<String>empty(),
                Optional.of("Binh"))
        .flatMap(Optional::stream)
        .toList(); // [An, Binh] — Java 16+ toList().
```

Ví dụ trên là **đoạn mã đặt trong phương thức** sau khi import `List`, `Optional`, `Stream`. Với Java 8, thay `Optional::stream` bằng cách `filter(Optional::isPresent).map(Optional::get)` nếu thật sự cần ghép nhiều Optional (ở đây `get` an toàn nhờ kiểm tra trước, nhưng cần giữ bước lọc). Khi dùng API từ Java 9+, `flatMap(Optional::stream)` rõ hơn và không phải tự gọi `get`.

Các primitive Optional như `OptionalInt`, `OptionalLong` và `OptionalDouble` cũng có khái niệm present/empty. `getAsInt()`/`getAsLong()`/`getAsDouble()` **không nên gọi vô điều kiện** khi kết quả có thể rỗng; dùng `orElse`, `ifPresent`, `orElseThrow` hoặc kiểm tra presence theo API của phiên bản đang chạy.

## 13. Đặt Optional ở đâu cho hợp lý?

Theo tài liệu API, `Optional` **chủ yếu được thiết kế để làm kiểu trả về của phương thức**, nơi có nhu cầu rõ ràng về “không có kết quả”. Đây là khuyến nghị thiết kế, không phải quy tắc cú pháp cấm dùng ở nơi khác.

Hãy cân nhắc trước khi đặt Optional trong mọi field/parameter:

- **Return type:** `Optional<User> findById(...)` giúp bắt người gọi quyết định về not found.
- **Tham số:** thường dễ dùng overload hoặc nullable hợp đồng rõ ràng hơn, tùy API. `Optional<T>` làm tham số không tự ngăn người dùng truyền `null` làm chính Optional, do đó vẫn cần quy ước.
- **Field/DTO/JPA entity:** cân nhắc framework mapping/serialization và semantics của “không đặt” so với “đặt null”. Không giả định mọi thư viện serialize Optional như nhau; dùng cấu trúc được framework hỗ trợ và thống nhất với hợp đồng API.
- **Collection:** một collection rỗng thường đủ diễn đạt “không có phần tử”, tránh `Optional<List<T>>` nếu không có thêm ý nghĩa nghiệp vụ phân biệt.
- **Side effect:** `Optional` không phải công cụ tự động đảm bảo thread-safety; lambda vẫn có các quy tắc về trạng thái và ngoại lệ.

`Optional` là lớp **value-based**. Tránh dùng identity `==`, identity hash code, hoặc `synchronized(optional)` làm khóa, vì không nên gắn ngữ nghĩa nhận diện object vào các instance của nó. So sánh giá trị Optional có thể dùng `equals`, hoặc xử lý present/empty thông qua API; **không so sánh identity** để kiểm tra Optional rỗng.

## 14. Các lỗi phổ biến và cách sửa

| Lỗi | Tại sao sai | Cách làm đúng hơn |
| --- | --- | --- |
| `Optional<T> find() { return null; }` | Bên gọi nhận tham chiếu null và gặp `NullPointerException` | `return Optional.empty();` hoặc `ofNullable(value)` |
| `Optional.of(nullableValue)` khi có thể null | Ném `NullPointerException` ngay khi tạo | `Optional.ofNullable(nullableValue)` nếu null là absence |
| `optional.get()` không kiểm tra | `NoSuchElementException` khi empty | `orElse`, `orElseGet`, `orElseThrow`, `ifPresent`, `map` |
| `optional.orElse(expensiveCall())` | Gọi fallback kể cả khi present | `orElseGet(() -> expensiveCall())` |
| `optional.map(x -> otherOptional(x))` khi mapper trả Optional | Tạo `Optional<Optional<T>>` | `flatMap(x -> otherOptional(x))` |
| `flatMap(x -> null)` | Mapper vi phạm hợp đồng; NPE | Trả `Optional.empty()` nếu đúng nghĩa absence |
| `catch (Exception) { return Optional.empty(); }` | Che lỗi thật thành “not found” | Phân biệt absence và failure |
| `Optional<List<T>>` không rõ nghĩa | Khó phân biệt absent với collection rỗng | Xác định rõ trạng thái, hoặc trả collection rỗng trực tiếp |
| `optional.get()` ngay sau `findFirst()` | Input/predicate có thể tạo Stream rỗng | Dùng `orElseThrow` có message hoặc giữ Optional |
| `optional == Optional.empty()` | Dựa vào identity không được hứa | `isEmpty()` (Java 11+) hoặc `!isPresent()` |
| `Optional.or(() -> null)` | Supplier phải trả Optional hợp lệ | `or(() -> Optional.empty())` hoặc Optional fallback |
| `optional.orElse(null)` không kiểm soát | Đưa nullable value quay lại API, dễ NPE về sau | Giữ Optional hoặc quy ước boundary rõ ràng |

**Lưu ý:** `orElse(null)` là cú pháp hợp lệ và đôi khi được dùng khi một API bắt buộc nhận nullable value, nhưng khi làm vậy bạn **đã rời khỏi hợp đồng Optional**. Không coi đó là cách mặc định để xử lý absence.

## 15. Quy trình quyết định nhanh

1. **Phương thức có thật sự có thể không có kết quả không?** Nếu có, `Optional<T>` thường phù hợp cho return type; không return `null`.
2. **Đang tạo Optional từ nguồn nào?** Giá trị chắc chắn non-null ⇒ `of`; giá trị nullable theo hợp đồng ⇒ `ofNullable`; không có kết quả ⇒ `empty`.
3. **Ở bên gọi, empty có nghĩa gì?**
   - Là chuyện bình thường ⇒ `ifPresent`, `map`, `orElse`, `orElseGet` hoặc giữ Optional.
   - Là lỗi cần mô tả ⇒ `orElseThrow(() -> new DomainException(...))`.
   - Là nhiều trạng thái khác nhau ⇒ kiểu kết quả/domain hoặc ngoại lệ phù hợp, không thu gọn hết thành empty.
4. **Có đang gọi `get` không?** Nếu không có kiểm tra presence và không thể bảo đảm present, thay bằng cách giải thích rõ ý định empty.
5. **Fallback có chi phí/side effect?** Dùng `orElseGet` thay vì tính fallback eager trong `orElse`.
6. **Mapper có thể trả null?** `map` sẽ tạo empty; `flatMap` yêu cầu Optional không null. Xem null có phải absence hợp lệ hay là bug.
7. **Có đang dùng API bổ sung sau Java 8?** `or`/`stream`/`ifPresentOrElse` Java 9; `orElseThrow()` Java 10; `isEmpty` Java 11; `Stream.toList` Java 16. Chọn theo phiên bản JDK tối thiểu của dự án.
8. **Đã có test cho cả present và empty chưa?** Test thêm giá trị null từ nguồn, chuỗi trống, lỗi dữ liệu và nhánh ngoại lệ có ý nghĩa.

### Test tối thiểu cho phương thức trả Optional

Một test suite tốt nên kiểm tra:
- Trường hợp có giá trị ⇒ Optional khác null và present, dữ liệu đúng.
- Trường hợp không tìm thấy ⇒ Optional khác null và empty.
- Các nhánh dữ liệu nullable/blank ⇒ không bao giờ trả null Optional.
- Bên gọi có fallback ⇒ nhận đúng fallback khi empty.
- Bên gọi yêu cầu kết quả ⇒ nhận đúng loại ngoại lệ và message khi empty.
- Fallback tốn chi phí ⇒ không được gọi khi Optional present nếu dùng `orElseGet`.
- Mapper `flatMap` ⇒ luôn trả một Optional hợp lệ.

Đây là các **tiêu chí kiểm thử**, không gắn cứng vào JUnit phiên bản nào. Chúng áp dụng cho test framework đang được dự án sử dụng.

## 16. Bài tập tự kiểm tra

**Câu 1.** Một phương thức khai báo `Optional<String> readConfig()` không tìm thấy cấu hình. Nên trả gì?  
**Đáp án:** `Optional.empty()`, không phải `null`. Nếu cấu hình bắt buộc, có thể ném ngoại lệ tại tầng gọi yêu cầu cấu hình, tùy hợp đồng.

**Câu 2.** `Optional.<String>empty().get()` xảy ra điều gì?  
**Đáp án:** Ném `NoSuchElementException` vì Optional rỗng.

**Câu 3.** Có thể dùng `Optional.of(null)` để biểu diễn không có giá trị không?  
**Đáp án:** Không; ném `NullPointerException`. Dùng `Optional.empty()` hoặc `ofNullable(null)`.

**Câu 4.** Optional đã chứa `"A"`. `optional.orElse(createFallback())` có gọi `createFallback()` không?  
**Đáp án:** Có, vì Java đánh giá đối số trước lời gọi method. `orElseGet(() -> createFallback())` mới trì hoãn supplier.

**Câu 5.** `Optional.of("x").map(x -> null)` và `flatMap(x -> null)` khác nhau thế nào?  
**Đáp án:** `map` trả Optional rỗng; `flatMap` ném `NullPointerException` vì mapper không trả Optional hợp lệ.

**Câu 6.** Một phương thức đã khai báo trả `Optional<User>` nhưng lại trả `null`. Bên gọi `orElse(...)` có giúp biến thành giá trị mặc định không?  
**Đáp án:** Không. Null reference khiến việc gọi `orElse` ném `NullPointerException` trước khi áp dụng quy tắc empty.

**Câu 7.** Nếu API trả `Optional.of(List.of())`, có giống `Optional.empty()` không?  
**Đáp án:** Không. Trường hợp đầu present với một danh sách rỗng; trường hợp sau không có List.

**Câu 8.** Dùng `orElseThrow()` không đối số trên Java 8 được không?  
**Đáp án:** Không. Overload không đối số có từ Java 10; Java 8 dùng `orElseThrow(() -> new NoSuchElementException(...))` hoặc loại ngoại lệ nghiệp vụ thích hợp.

**Câu 9.** `Stream.of(Optional.of("A"), Optional.empty())` cần trích các giá trị present trên Java 9+ thế nào?  
**Đáp án:** `flatMap(Optional::stream)`, sau đó dùng terminal operation theo nhu cầu.

**Câu 10.** Khi nào “trả empty” là quyết định tồi?  
**Đáp án:** Khi nó che một lỗi vận hành hoặc dữ liệu nghiêm trọng mà bên gọi cần phát hiện/phân biệt, như lỗi DB, permission, hay timeout.

## 17. Ghi nhớ

- **Không bao giờ `return null` từ phương thức cam kết trả `Optional<T>`.** Không có dữ liệu ⇒ `Optional.empty()`; nguồn nullable ⇒ `Optional.ofNullable(value)`.
- **Không gọi `get()` vô điều kiện** khi Optional có thể rỗng. `get` không phải API đã bị xóa, nhưng gọi trên empty ném `NoSuchElementException`.
- Dùng `map`/`filter`/`flatMap` để mô tả luồng giá trị; `ifPresent` cho hành động; `orElse`/`orElseGet` cho fallback; `orElseThrow` khi thiếu giá trị là lỗi.
- **`orElse` eager, `orElseGet` lazy** trong việc tạo giá trị fallback.
- `Optional.map` có thể biến mapper trả null thành empty; `Optional.flatMap` không chấp nhận mapper trả null Optional.
- **Optional rỗng khác với null Optional**, và khác với **Optional present chứa một collection rỗng**.
- Optional mô tả **absence của một giá trị**, không phải bộ khung xử lý mọi lỗi, không tự giải quyết null ở dependency vi phạm hợp đồng.
- Xác định phiên bản Java tối thiểu trước khi dùng những API Optional được bổ sung sau Java 8.

### Tài liệu Java API chính thức (vẫn áp dụng)

- [`java.util.Optional`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): hợp đồng return type, `empty`, `of`, `ofNullable`, `get`, `map`, `flatMap`, `orElse`, `orElseGet`, `orElseThrow`, `or`, `stream`, `ifPresentOrElse`, `isEmpty`.
- [`java.util.stream.Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `findFirst`, `findAny` và các terminal operation trả Optional.
- [`OptionalInt`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html), [`OptionalLong`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalLong.html), [`OptionalDouble`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalDouble.html): Optional cho primitive, presence và giá trị mặc định.
