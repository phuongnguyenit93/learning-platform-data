# Vai trò của `Optional.orElseThrow()` không có đối số trong Java 10+

*Chủ đề cha: `Optional.orElseThrow`. Bài học tập trung vào overload **không có đối số** của `java.util.Optional`, ý nghĩa “lấy giá trị bắt buộc hoặc thất bại”, lỗi khi `Optional` rỗng, cách lựa chọn so với các phương thức thay thế và ứng dụng trong Java hiện đại. Tất cả chương trình hoàn chỉnh tương thích JDK 17 trở lên.*

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích chính xác `Optional<T>.orElseThrow()` trả gì khi có giá trị và ném ngoại lệ gì khi rỗng.
2. Phân biệt **`Optional` rỗng**, **giá trị tham chiếu `null`** và **biến tham chiếu `Optional` tự nó bằng `null`**.
3. Hiểu vì sao overload không có đối số (bổ sung từ Java 10) là cách **unwrap có điều kiện bắt buộc**; biết khi nào dùng nó thể hiện một invariant hay tiền điều kiện rõ.
4. So sánh `orElseThrow()` với `orElseThrow(exceptionSupplier)`, `get()`, `orElse(...)`, `orElseGet(...)`, `ifPresent(...)` và `Optional.stream()`.
5. Hiểu cách `map`, `filter`, `flatMap` và `findFirst` ảnh hưởng tới việc `Optional` có hay không có giá trị trước khi gọi `orElseThrow()`.
6. Sử dụng đúng `OptionalInt`, `OptionalLong`, `OptionalDouble` trong tình huống cần dữ liệu primitive.
7. Viết code Java 17+ chạy được, dự đoán output và kiểm thử cả nhánh có dữ liệu lẫn nhánh vắng mặt.
8. Tránh dùng `orElseThrow()` như “bùa chú” bỏ qua lỗi, và chọn chiến lược xử lý trường hợp không tìm thấy theo hợp đồng nghiệp vụ.

**Quy tắc trung tâm:**

```java
T value = optional.orElseThrow();
```

Nếu `optional` **có giá trị**, phương thức trả giá trị đó với kiểu `T`. Nếu `optional` **rỗng**, nó ném **`java.util.NoSuchElementException`** (unchecked exception). Không trả `null`, không tạo giá trị mặc định, không chờ người gọi kiểm tra lại.

## 2. `Optional` biểu diễn điều gì?

`Optional<T>` là một container có thể chứa **một giá trị khác `null`** hoặc không chứa giá trị nào. Một giá trị có mặt được gọi là *present*; không có giá trị là *empty*.

```java
// Các đoạn minh họa bên trong một method:
var present = java.util.Optional.of("Java");       // Optional<String> có giá trị
var empty = java.util.Optional.<String>empty();    // Optional<String> rỗng

var fromNullable = java.util.Optional.ofNullable(null);
// Optional<Object> rỗng vì không có ngữ cảnh kiểu cụ thể
```

Khi cần định rõ generic type để sử dụng API tiếp theo, viết:

```java
java.util.Optional<String> missingName =
        java.util.Optional.ofNullable(null);
// hoặc
var missingName2 = java.util.Optional.<String>ofNullable(null);
```

Những điểm dễ nhầm:

- `Optional.of(value)` đòi hỏi `value` khác `null`; gọi `Optional.of(null)` ném `NullPointerException` khi tạo Optional.
- `Optional.ofNullable(value)` tạo Optional rỗng nếu `value == null`; nếu không, tạo Optional chứa giá trị.
- `Optional.empty()` là rỗng, không có “một phần tử đang chứa `null`”.
- Dù có thể viết `Optional<String> x = null;` theo kiểu tham chiếu thông thường, **không nên** dùng `null` để biểu diễn Optional vắng mặt. Khi đó lời gọi `x.orElseThrow()` gây `NullPointerException` trước khi API Optional xử lý.
- Kiểu `Optional<String>` không nói rằng giá trị luôn hiện diện. Nó nói rằng **nếu có giá trị**, giá trị sẽ là `String` theo kiểm tra kiểu tĩnh.

`Optional` phù hợp nhất để biểu diễn kết quả một phép tính hoặc lời gọi phương thức có thể không trả dữ liệu. Nó **không bắt mọi người gọi phải unwrap**; nhiều bài toán được giải quyết tốt hơn bằng xử lý Optional trực tiếp hoặc một fallback rõ ràng.

## 3. Chữ ký và hai nhánh hoạt động của overload không đối số

Đọc chữ ký:

```java
public T orElseThrow()
```

Đây là chữ ký method của `Optional<T>` trong API, không phải một chương trình độc lập. `T` là kiểu generic mà Optional đang biểu diễn.

| Trạng thái của Optional | Kết quả `orElseThrow()` | Hệ quả |
| --- | --- | --- |
| Có giá trị `T` | Trả chính giá trị `T` | Chương trình đi tiếp sau lời gọi |
| Rỗng | Ném `NoSuchElementException` | Không có giá trị được trả về |
| Biến tham chiếu Optional bằng `null` | Ném `NullPointerException` khi gọi method | Không phải “empty Optional” |

Ví dụ:

```java
var present = java.util.Optional.of("Lan");
String value = present.orElseThrow(); // "Lan"

var absent = java.util.Optional.<String>empty();
// String missing = absent.orElseThrow(); // Runtime: NoSuchElementException
```

Trong nhánh có dữ liệu, `orElseThrow()` không tạo một bản sao của đối tượng `T`. Nếu `T` là mutable, tham chiếu trả về vẫn trỏ tới đối tượng mà Optional chứa. Trong nhánh rỗng, việc thất bại là **hành vi chủ đích được API định nghĩa**, khác với lỗi compile-time.

`NoSuchElementException` là unchecked exception kế thừa `RuntimeException`, nên code gọi không phải khai báo `throws` hoặc bắt buộc `catch` chỉ để biên dịch. Tuy vậy, một exception không được xử lý sẽ làm luồng điều khiển thoát lên caller và có thể dẫn tới kết thúc xử lý hiện tại.

### 3.1. Vì sao gọi là “lấy giá trị bắt buộc”?

Tên `orElseThrow` diễn đạt một hợp đồng đơn giản: “hoặc trả phần tử hiện có, hoặc ném ngoại lệ”. Overload không đối số dùng ngoại lệ chuẩn `NoSuchElementException`, không cần bạn truyền một supplier tạo ngoại lệ.

Nó thích hợp khi **một Optional rỗng thật sự vi phạm tiền điều kiện hoặc invariant tại vị trí gọi**. Ví dụ:

- Dữ liệu đã được validate ở bước trước và code có lý do rõ để đảm bảo hiện diện.
- Một kết quả trung gian trong thuật toán phải có ít nhất một phần tử mới thỏa quy tắc.
- Một test cần yêu cầu có kết quả thay vì âm thầm dùng giá trị giả.
- Một bước xử lý nội bộ mà trường hợp rỗng là lỗi logic đáng để fail fast.

Không nên mặc định dùng `orElseThrow()` cho mọi kết quả tìm kiếm thông thường. Với phép tìm người dùng theo ID, “không tìm thấy” có thể là một kết quả hợp lệ của domain; ở ranh giới API có thể cần trả Optional tiếp, trả mã HTTP 404, dùng giá trị mặc định hoặc ném ngoại lệ domain cụ thể tùy thiết kế.

## 4. Chương trình hoàn chỉnh: có giá trị và rỗng

Tạo file **`NoArgOrElseThrowDemo.java`**:

```java
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;

public class NoArgOrElseThrowDemo {
    static Optional<String> findDisplayName(
            Map<String, String> names, String id) {
        return Optional.ofNullable(names.get(id));
    }

    public static void main(String[] args) {
        var namesById = Map.of("u1", "Lan");

        var found = findDisplayName(namesById, "u1");
        System.out.println("found=" + found.orElseThrow());

        var missing = findDisplayName(namesById, "u9");

        try {
            missing.orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println("missing-exception="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("missing-still-empty=" + missing.isEmpty());

        var first = OptionalInt.of(7).orElseThrow();
        var second = OptionalLong.of(12L).orElseThrow();
        var third = OptionalDouble.of(2.5).orElseThrow();

        System.out.println("primitives="
                + first + "," + second + "," + third);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 NoArgOrElseThrowDemo.java
java NoArgOrElseThrowDemo
```

Stdout chính xác:

```text
found=Lan
missing-exception=NoSuchElementException
missing-still-empty=true
primitives=7,12,2.5
```

Phân tích:

1. `findDisplayName` khai báo trả `Optional<String>`. Khi Map có `"u1"`, kết quả Optional chứa `"Lan"`.
2. `found.orElseThrow()` trả `"Lan"`; chương trình in `found=Lan`.
3. Với `"u9"`, `Map.get` không tìm được mapping nên `Optional.ofNullable` tạo Optional rỗng.
4. `missing.orElseThrow()` ném `NoSuchElementException`. Ví dụ bắt đúng loại ngoại lệ, in **tên lớp**, không phụ thuộc thông điệp mặc định của từng JDK.
5. Sau khi bắt ngoại lệ, `missing.isEmpty()` vẫn là `true`. `orElseThrow` không “tiêu thụ” hay thay đổi Optional.
6. Các Optional dạng primitive cũng có overload không đối số và trả `int`, `long`, `double` tương ứng khi có giá trị.

Không nên bắt `NoSuchElementException` quanh toàn bộ chương trình chỉ để che giấu lỗi. Ví dụ bắt ngoại lệ một cách có chủ đích nhằm minh họa cả hai nhánh của API.

## 5. Khác biệt giữa `orElseThrow()` và `get()`

`Optional.get()` **vẫn tồn tại** trong Java hiện đại; không được gọi nó là API đã bị loại bỏ hoặc deprecated nếu không có bằng chứng cụ thể. Về hành vi cốt lõi:

| Phương thức | Optional có giá trị | Optional rỗng |
| --- | --- | --- |
| `get()` | Trả `T` | Ném `NoSuchElementException` |
| `orElseThrow()` | Trả `T` | Ném `NoSuchElementException` |

Vậy tại sao `orElseThrow()` được bổ sung trong Java 10 và thường dễ đọc hơn `get()`?

- Tên `get` đơn giản nhưng **không nói rõ nhánh thất bại**.
- Tên `orElseThrow` làm lựa chọn “không có fallback; rỗng là ngoại lệ” hiện ngay tại điểm gọi.
- Nó thống nhất ý tưởng với overload nhận `exceptionSupplier`, đồng thời giảm nhu cầu giải thích “nếu empty thì get ném gì”.

`Optional` Javadoc hướng người đọc đến `orElseThrow()` như lựa chọn rõ ràng hơn khi muốn lấy giá trị mà không có fallback. Tuy nhiên, đây là **khuyến nghị về cách diễn đạt**, không phải bằng chứng `get()` đã ngừng hoạt động. Khi bảo trì code cũ đang dùng `get()`, cần xem hợp đồng xử lý trường hợp empty trước khi sửa; không đổi chỉ vì muốn giảm warning một cách máy móc.

Ví dụ:

```java
var maybeResult = java.util.Optional.of("ready");
var value = maybeResult.orElseThrow(); // String "ready"
```

Người đọc hiểu rằng code đang yêu cầu một kết quả bắt buộc. Nếu vắng mặt là hoàn toàn bình thường, một phương thức khác phù hợp hơn sẽ rõ nghĩa và ít ngoại lệ không cần thiết.

## 6. So sánh các cách xử lý Optional

| API | Khi có giá trị | Khi rỗng | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `orElseThrow()` | Trả `T` | Ném `NoSuchElementException` | Rỗng là vi phạm tiền điều kiện |
| `orElseThrow(() -> new X(...))` | Trả `T` | Ném ngoại lệ `X` được supplier tạo | Cần mô tả lỗi domain cụ thể |
| `orElse(fallback)` | Trả `T` | Trả `fallback` | Có giá trị dự phòng đơn giản |
| `orElseGet(() -> fallback())` | Trả `T` | Gọi supplier rồi trả kết quả | Fallback tính toán tốn công hoặc lazy |
| `ifPresent(action)` | Thực thi action | Không làm gì | Chỉ muốn side effect khi có giá trị |
| `ifPresentOrElse(action, emptyAction)` | Thực thi action | Thực thi emptyAction | Có hai nhánh hành động rõ |
| `map(function)` | Biến đổi thành Optional kết quả | Giữ rỗng | Muốn tiếp tục tính toán mà chưa unwrap |
| `filter(predicate)` | Giữ hoặc chuyển thành rỗng | Giữ rỗng | Áp điều kiện trước xử lý |
| `stream()` | Stream chứa một phần tử | Stream rỗng | Kết hợp nhiều Optional với pipeline Stream |

### 6.1. `orElseThrow()` khác overload có supplier

Hai lời gọi:

```java
var value1 = optional.orElseThrow();

var value2 = optional.orElseThrow(
        () -> new IllegalArgumentException("invalid id"));
```

đều trả giá trị khi present. Nhưng khi empty:

- Không đối số: **`NoSuchElementException`** tiêu chuẩn.
- Có supplier: dùng ngoại lệ do supplier tạo (ví dụ `IllegalArgumentException`); supplier **chỉ được gọi khi empty**.

Chữ ký overload có supplier:

```java
public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
```

Overload này có từ trước Java 10; còn bài học này tập trung vào overload **không có đối số** được bổ sung ở Java 10. Một ngoại lệ checked type có thể yêu cầu khai báo `throws` hoặc xử lý tại caller, tùy kiểu `X`; ví dụ `IllegalArgumentException` và `NoSuchElementException` đều unchecked.

Nếu lỗi domain quan trọng, hãy chọn overload có supplier để mô tả chính xác điều kiện thất bại (ID không tồn tại, khóa cấu hình thiếu, kết quả vi phạm invariant) thay vì buộc caller đoán nghĩa từ `NoSuchElementException` mặc định.

### 6.2. `orElse` không lazy theo đối số

Xét:

```java
var name = optional.orElse(createFallback());
```

Java đánh giá **đối số phương thức** trước khi gọi `orElse`. Vì vậy `createFallback()` vẫn được chạy ngay cả khi `optional` đã có giá trị, dù giá trị fallback không được chọn.

Còn:

```java
var name = optional.orElseGet(() -> createFallback());
```

supplier chỉ chạy khi `optional` empty. Với một constant rẻ và không có side effect, `orElse("Guest")` thường đơn giản. Với thao tác tốn thời gian, truy vấn tài nguyên hoặc sinh dữ liệu, `orElseGet` tránh xử lý vô ích.

`orElseThrow()` không tạo fallback nên không có khác biệt eager/lazy kiểu đó; nó chỉ trả giá trị hiện diện hoặc ném.

## 7. Chương trình hoàn chỉnh so sánh fallback và ngoại lệ

Tạo file **`OptionalAlternativesDemo.java`**:

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalAlternativesDemo {
    static String fallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "generated";
    }

    public static void main(String[] args) {
        var calls = new AtomicInteger();
        var present = Optional.of("ready");

        var eager = present.orElse(fallback(calls));
        System.out.println("eager=" + eager + ",calls=" + calls.get());

        var lazy = present.orElseGet(() -> fallback(calls));
        System.out.println("lazy=" + lazy + ",calls=" + calls.get());

        var absent = Optional.<String>empty();
        var generated = absent.orElseGet(() -> fallback(calls));
        System.out.println("missing-fallback="
                + generated + ",calls=" + calls.get());

        var required = absent.orElse("Guest");
        System.out.println("constant-fallback=" + required);

        try {
            absent.orElseThrow(
                    () -> new IllegalArgumentException("user not found"));
        } catch (IllegalArgumentException ex) {
            System.out.println("custom-exception="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 OptionalAlternativesDemo.java
java OptionalAlternativesDemo
```

Stdout:

```text
eager=ready,calls=1
lazy=ready,calls=1
missing-fallback=generated,calls=2
constant-fallback=Guest
custom-exception=IllegalArgumentException
```

Giải thích: dù `present` đã chứa `"ready"`, `fallback(calls)` trong `orElse(...)` vẫn chạy nên `calls` tăng lên 1. `orElseGet(...)` trên Optional có giá trị không gọi supplier, nên số lần vẫn 1. Chỉ khi `absent` rỗng thì supplier chạy thêm một lần và `calls` thành 2.

Đây là ví dụ ngắn để **chứng minh thời điểm gọi fallback**, không phải khuyến nghị dùng side effect trong mọi hàm. Code nghiệp vụ nên tránh sinh dữ liệu ngoài ý muốn khi chỉ cần một giá trị dự phòng.

## 8. Kết hợp `map`, `filter` và `orElseThrow()`

### 8.1. `map` có thể khiến Optional trở thành rỗng

`Optional.map(mapper)` trả một Optional mô tả kết quả biến đổi; nếu mapper trả `null`, Optional kết quả là **empty** (theo ngữ nghĩa `ofNullable`), không phải Optional chứa null.

```java
// Đoạn minh họa trong một lớp có record Profile:
record Profile(String name, String nickname) {}

var profile = java.util.Optional.of(new Profile("Lan", null));
var maybeNickname = profile.map(Profile::nickname);
// maybeNickname: Optional<String> rỗng

// var nickname = maybeNickname.orElseThrow();
// Runtime: NoSuchElementException
```

Dữ liệu ban đầu `profile` **present**, nhưng kết quả `map` **empty** vì thuộc tính trả null. Vì vậy gọi `orElseThrow()` ở cuối pipeline đòi hỏi **kết quả cuối cùng** phải có giá trị, không chỉ Optional gốc.

### 8.2. `filter` có thể loại bỏ giá trị

```java
var maybeToken = java.util.Optional.of("   ");
var nonBlank = maybeToken.filter(s -> !s.isBlank());
// nonBlank là Optional<String> rỗng
```

Khi `filter` không đạt predicate, nó tạo kết quả empty. `nonBlank.orElseThrow()` sẽ ném `NoSuchElementException`. Điều này có thể là chủ đích khi một chuỗi blank là trạng thái không được phép; nhưng nếu token rỗng là dữ liệu người dùng sai, một ngoại lệ có thông điệp cụ thể có thể hữu ích hơn.

### 8.3. `flatMap` khác với `map` về kiểu kết quả

Nếu một phương thức đã trả `Optional<U>`, dùng `flatMap` để tránh Optional lồng nhau:

```java
// Đoạn minh họa trong method:
var input = java.util.Optional.of("U1");

var userId = input
        .flatMap(id -> lookupActiveUserId(id))
        .orElseThrow();
```

`lookupActiveUserId` ở đây là **API minh họa** có chữ ký `Optional<String> lookupActiveUserId(String id)`, không phải hàm Java có sẵn; nó cần được định nghĩa trong chương trình thật. `flatMap` trả một Optional được làm phẳng. Nếu mapper của `flatMap` trả **tham chiếu Optional bằng null**, `flatMap` ném `NullPointerException`; nó không coi điều đó là Optional.empty. Đừng nhầm loại lỗi đó với `NoSuchElementException` ở `orElseThrow()`.

## 9. Chương trình hoàn chỉnh về Optional pipeline

Tạo **`OptionalPipelineDemo.java`**:

```java
import java.util.NoSuchElementException;
import java.util.Optional;

public class OptionalPipelineDemo {
    record Profile(String name, String nickname) {}

    public static void main(String[] args) {
        var profile = Optional.of(new Profile("Lan", null));

        var nickname = profile.map(Profile::nickname);
        System.out.println("nickname-empty=" + nickname.isEmpty());

        try {
            nickname.orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println("nickname-missing="
                    + ex.getClass().getSimpleName());
        }

        var filtered = Optional.of("  ")
                .filter(s -> !s.isBlank());
        System.out.println("filtered-empty=" + filtered.isEmpty());

        System.out.println("empty-stream-count="
                + Optional.<String>empty().stream().count());

        try {
            Optional.of(null);
        } catch (NullPointerException ex) {
            System.out.println("of-null="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 OptionalPipelineDemo.java
java OptionalPipelineDemo
```

Stdout:

```text
nickname-empty=true
nickname-missing=NoSuchElementException
filtered-empty=true
empty-stream-count=0
of-null=NullPointerException
```

Chú ý:

- `Optional.of(new Profile(...))` có giá trị `Profile`, nhưng `map(Profile::nickname)` thành empty vì nickname bằng null.
- `orElseThrow()` ném `NoSuchElementException` chỉ khi Optional sau `map` rỗng.
- `filter` với chuỗi blank tạo empty; hành vi tương tự xảy ra khi predicate trả false.
- `Optional.empty().stream()` tạo Stream không có phần tử; `count()` trả 0. Chuyển thành Stream để xử lý tập dữ liệu khác với yêu cầu unwrap một giá trị.
- `Optional.of(null)` ném `NullPointerException` **ngay khi tạo Optional**; đó không phải ngoại lệ do `orElseThrow()`.

## 10. `Stream.findFirst()` và `orElseThrow()`

Một tình huống quen thuộc:

```java
var first = names.stream()
        .filter(name -> name.startsWith("A"))
        .findFirst()
        .orElseThrow();
```

`findFirst()` là terminal operation trả `Optional<String>`: có phần tử đầu tiên thỏa điều kiện, hoặc empty nếu không có. `orElseThrow()` biến kết quả tùy chọn thành một **yêu cầu bắt buộc có phần tử**.

Tạo file **`FirstMatchDemo.java`**:

```java
import java.util.List;
import java.util.NoSuchElementException;

public class FirstMatchDemo {
    public static void main(String[] args) {
        var values = List.of("zero", "one", "two");

        var first = values.stream()
                .filter(v -> v.startsWith("o"))
                .findFirst()
                .orElseThrow();
        System.out.println("first=" + first);

        try {
            values.stream()
                    .filter(v -> v.startsWith("X"))
                    .findFirst()
                    .orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println("no-match="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy:

```bash
javac --release 17 FirstMatchDemo.java
java FirstMatchDemo
```

Stdout:

```text
first=one
no-match=NoSuchElementException
```

Hai điểm thiết kế:

1. Với `List.of("zero","one","two")`, encounter order xác định và `findFirst()` tìm `"one"`. Nếu Stream nguồn không có encounter order, “phần tử đầu” không nhất thiết biểu thị thứ tự nghiệp vụ.
2. Nếu không có phần tử thỏa điều kiện, `findFirst()` trả empty; **ngoại lệ là do `orElseThrow()` khi đọc kết quả empty**. Nếu trường hợp không tìm thấy là bình thường, có thể trả lại Optional hoặc dùng fallback thay vì ném ngoại lệ.

Ngoài ra, `findFirst()` không được bảo đảm có thể nhận **phần tử null**; nếu phần tử được chọn là `null`, chính `findFirst()` có thể ném `NullPointerException`. Đừng gộp mọi NPE xuất hiện trong Stream vào lỗi `orElseThrow`.

## 11. Kiểu primitive: `OptionalInt`, `OptionalLong`, `OptionalDouble`

Ngoài `Optional<T>` dùng cho đối tượng, Java có các kiểu chuyên biệt:

| Kiểu | Tạo present | Lấy bắt buộc không đối số | Kiểu trả |
| --- | --- | --- | --- |
| `OptionalInt` | `OptionalInt.of(7)` | `orElseThrow()` | `int` |
| `OptionalLong` | `OptionalLong.of(12L)` | `orElseThrow()` | `long` |
| `OptionalDouble` | `OptionalDouble.of(2.5)` | `orElseThrow()` | `double` |

Ví dụ:

```java
var maybeCount = java.util.OptionalInt.of(7);
int count = maybeCount.orElseThrow();

var noAverage = java.util.OptionalDouble.empty();
// double average = noAverage.orElseThrow();
// Runtime: NoSuchElementException
```

Các kiểu Optional primitive hữu ích với API như `IntStream.min()`, `max()`, `average()` và các phép tổng hợp có thể vắng kết quả. `IntStream.average()` chẳng hạn trả `OptionalDouble`, vì Stream rỗng không có giá trị trung bình.

Không nên bọc lại thành `Optional<Integer>` chỉ để dùng `orElseThrow()`; loại primitive phù hợp thường tránh boxing không cần thiết. Khi báo cáo hoặc xử lý kết quả rỗng, hãy cân nhắc liệu không có số liệu là lỗi, hay nên hiển thị “chưa có dữ liệu” theo domain.

## 12. Ngoại lệ nào đến từ đâu?

Nhìn vào bảng sau giúp debug chính xác:

| Đoạn code | Tình huống | Ngoại lệ / hành vi |
| --- | --- | --- |
| `Optional.<String>empty().orElseThrow()` | Optional rỗng | `NoSuchElementException` |
| `Optional.of("ok").orElseThrow()` | Có giá trị | Trả `"ok"` |
| `Optional.of(null)` | Truyền null khi tạo | `NullPointerException` |
| `Optional.ofNullable(null).orElseThrow()` | Tạo empty, sau đó unwrap | `NoSuchElementException` |
| `Optional<String> x = null; x.orElseThrow();` | Chính biến Optional là null | `NullPointerException` |
| `Optional.of("x").map(s -> (String) null).orElseThrow()` | Mapper trả null khiến Optional thành empty | `NoSuchElementException` |
| `Optional.empty().orElse("default")` | Có fallback | Trả `"default"` |
| `Optional.empty().orElseGet(() -> "lazy")` | Có fallback lazy | Trả `"lazy"` |
| `Optional.empty().orElseThrow(() -> new IllegalStateException())` | Supplier tạo ngoại lệ khác | `IllegalStateException` |

**Đừng tự kiểm tra bằng `getClass()` trên một tham chiếu đang null**. Nếu muốn tìm nguồn lỗi, xem stack trace và dòng code: `Optional.of(null)`, `findFirst` trên null element, lambda ném lỗi hoặc `orElseThrow` trên Optional empty là những điểm khác nhau.

### 12.1. Thông điệp ngoại lệ

JDK có thể tạo thông điệp mặc định cho `NoSuchElementException` khi Optional rỗng, nhưng **đừng viết code nghiệp vụ hay test dựa vào một chuỗi message cụ thể** nếu API không xem message đó là hợp đồng ổn định. Bài này kiểm tra *loại ngoại lệ*, và khuyên dùng overload có supplier khi cần một message/domain exception cụ thể.

### 12.2. Exception không thay thế validation

`orElseThrow()` chỉ biết Optional present hay empty. Nó **không** biết một String có blank không, một đơn hàng có hợp lệ không, hay quyền truy cập có đầy đủ không.

```java
var value = java.util.Optional.of("   ");
var result = value.orElseThrow(); // Trả chuỗi chỉ có khoảng trắng
```

Nếu yêu cầu dữ liệu phải không blank, phải validate bằng `filter`, kiểm tra trực tiếp hoặc một loại kết quả có lỗi cụ thể. Không trông chờ `orElseThrow` tự thực hiện validation nghiệp vụ.

## 13. Khi nào nên dùng overload không có đối số?

### 13.1. Dùng khi sự hiện diện là một invariant đáng tin

Ví dụ thuật toán cần phần tử đầu tiên của một tập đã được đảm bảo không rỗng theo tiền điều kiện:

```java
// Đoạn minh họa trong một phương thức:
if (candidates.isEmpty()) {
    throw new IllegalArgumentException("candidates must not be empty");
}
var best = candidates.stream()
        .max(comparator)
        .orElseThrow();
```

`candidates` và `comparator` ở đây là các biến đã được định nghĩa trong ngữ cảnh. Việc validate trước giúp thể hiện tiền điều kiện; `orElseThrow()` cuối cùng nhấn mạnh kết quả tối đa phải tồn tại. Nhưng đừng lặp lại validation không cần thiết trong code ngắn nếu API đã có cách xử lý rõ hơn.

### 13.2. Không dùng mặc định khi “không tìm thấy” là bình thường

Ví dụ:

```java
static java.util.Optional<String> findName(
        java.util.Map<String, String> namesById, String id) {
    return java.util.Optional.ofNullable(namesById.get(id));
}
```

Nếu chức năng tìm kiếm cho phép không có kết quả, nên để caller quyết định:

```java
var maybeName = findName(namesById, userId);

var displayName = maybeName.orElse("Guest");
// Hoặc phản hồi trường hợp thiếu một cách có cấu trúc.
```

Các biến `namesById` và `userId` ở đoạn này là ví dụ trong method đã có ngữ cảnh. Việc chọn fallback `"Guest"` chỉ phù hợp với chức năng hiển thị; nếu là xác thực hay dữ liệu bắt buộc, gán một giá trị giả có thể làm sai nghiệp vụ.

### 13.3. Dùng supplier exception khi caller cần ý nghĩa lỗi

```java
var user = findUser(userId)
        .orElseThrow(() -> new IllegalArgumentException(
                "Unknown user id: " + userId));
```

`findUser` và `userId` là API/biến ví dụ, không phải chương trình độc lập. Dùng ngoại lệ có message domain nếu tầng xử lý cần phân biệt lỗi định danh không tồn tại với lỗi logic “đáng ra phải có kết quả”.

Không tiết lộ thông tin nhạy cảm (ID riêng tư, token bí mật, dữ liệu truy cập) trong message exception/log chỉ để tăng khả năng debug; tùy domain, có thể dùng mã lỗi an toàn thay vì in dữ liệu đầu vào.

## 14. `orElseThrow` có “tiêu thụ” Optional không?

Không. `Optional` là container giá trị; gọi `orElseThrow()` khi present không xóa phần tử, và gọi ở trạng thái empty không tự làm Optional trở nên present.

```java
var value = java.util.Optional.of("ready");

System.out.println(value.orElseThrow()); // ready
System.out.println(value.orElseThrow()); // ready
System.out.println(value.isPresent());   // true
```

Điều này **khác với Stream**. Một Stream thường chỉ được sử dụng cho một pipeline và không được dùng lại sau terminal operation; `Optional` không phải Stream và không có hạn chế “unwrap một lần”.

`Optional` cũng không có ý nghĩa rằng lời gọi lookup bên ngoài được thực thi lại mỗi khi gọi `orElseThrow()`. Nếu `Optional` được tạo từ một lần gọi phương thức trước đó, nó biểu diễn kết quả tại thời điểm tạo; không tự tải lại dữ liệu khi unwrap.

Điều này hữu ích trong review code: nếu hai lần gọi `orElseThrow()` trả khác nhau, nguyên nhân có thể nằm ở **đối tượng mutable được chứa** và cách code quan sát nó, không phải Optional tự đổi tham chiếu trong container.

## 15. Kiểm thử đúng hai nhánh, đừng chỉ test happy path

Với `orElseThrow()`, test nên bao gồm:

1. **Present:** kết quả trả đúng giá trị mong muốn.
2. **Empty:** ném đúng `NoSuchElementException`.
3. **Chuỗi biến đổi:** `map` hoặc `filter` có thể biến một Optional present thành empty; kiểm tra hậu quả.
4. **Ngoại lệ tùy chỉnh:** nếu dùng overload có supplier, test loại/message phù hợp nghiệp vụ thay vì kỳ vọng loại mặc định.
5. **Fallback:** nếu dùng `orElseGet`, xác nhận supplier không chạy khi present và có chạy khi empty nếu điều này ảnh hưởng hành vi/hiệu năng.
6. **Primitive Optional:** kiểm tra đúng kiểu primitive và empty path.
7. **Null sai tầng:** phân biệt lỗi `Optional.of(null)` và Optional tham chiếu bằng null với empty Optional.

Có thể viết test bằng JUnit trong dự án; ví dụ bên dưới là **minh họa cú pháp JUnit 5** và cần dependency phù hợp, không phải một chương trình Java SE tự chạy:

```java
import static org.junit.jupiter.api.Assertions.*;

assertEquals("A", java.util.Optional.of("A").orElseThrow());
assertThrows(
        java.util.NoSuchElementException.class,
        () -> java.util.Optional.<String>empty().orElseThrow());
```

Nếu không muốn phụ thuộc framework, có thể dùng các chương trình `main` đã trình bày ở trên: bắt ngoại lệ đúng kiểu và in kết quả xác định.

Không viết test mong `orElseThrow()` trả `null` cho Optional empty. Đó là điều API cố ý không làm.

## 16. Các nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`orElseThrow()` trả `null` nếu Optional empty.” | Sai: ném `NoSuchElementException` |
| “`orElseThrow()` luôn ném exception.” | Sai: khi present, nó trả giá trị `T` |
| “Nó là cách lấy dữ liệu không khác gì `orElse(null)`.” | Sai: một bên ném, một bên trả fallback null |
| “`orElseThrow()` tự tạo message nghiệp vụ.” | Không; dùng overload nhận supplier nếu cần exception/message rõ |
| “`get()` đã bị xóa khỏi Java 17.” | Sai: `get()` vẫn có, nhưng `orElseThrow()` có tên biểu đạt nhánh lỗi rõ hơn |
| “`Optional.of(null).orElseThrow()` ném `NoSuchElementException`.” | Sai: `Optional.of(null)` ném `NullPointerException` trước |
| “`map` trả null thì Optional chứa null.” | Sai: `Optional.map` tạo empty khi mapper trả null |
| “`filter` chỉ giữ nguyên trạng thái present.” | Sai: predicate false chuyển thành empty |
| “`orElseGet` luôn gọi supplier.” | Sai: chỉ gọi khi Optional rỗng |
| “`orElse(expensive())` chỉ chạy expensive khi rỗng.” | Sai: Java đánh giá đối số trước khi gọi `orElse` |
| “`orElseThrow()` gọi xong Optional bị tiêu thụ.” | Sai: Optional không có semantics tiêu thụ một lần như Stream |
| “Khi không tìm thấy người dùng, luôn nên ném `NoSuchElementException`.” | Tùy hợp đồng; trường hợp vắng mặt có thể bình thường |
| “`Optional<String>` không bao giờ có thể empty.” | Generic type quy định kiểu khi có giá trị, không bảo đảm present |
| “`orElseThrow()` tự xác thực dữ liệu đúng nghiệp vụ.” | Nó chỉ kiểm tra present/empty |
| “Tất cả `NullPointerException` quanh Optional đều từ `orElseThrow`.” | Kiểm tra `Optional.of`, tham chiếu null, mapper và API trước đó |
| “`orElseThrow()` là tính năng chỉ dành cho Java 10, không dùng hiện nay.” | Đây là API hiện đại vẫn được hỗ trợ đầy đủ từ Java 10 trở đi |

## 17. Bài tập thực hành có đáp án

### Bài 1 — Có giá trị

```java
var optional = java.util.Optional.of("Java");
var value = optional.orElseThrow();
System.out.println(value);
```

**Đáp án:** in `Java`. `value` là `String`. Không có ngoại lệ vì Optional chứa giá trị.

### Bài 2 — Empty

```java
var optional = java.util.Optional.<Integer>empty();
var value = optional.orElseThrow();
```

**Đáp án:** ném `NoSuchElementException` khi thực thi dòng cuối. Không có `Integer` hoặc giá trị `0` nào được tự tạo.

### Bài 3 — `ofNullable` và null

```java
var optional = java.util.Optional.ofNullable(null);
optional.orElseThrow();
```

**Đáp án:** `ofNullable(null)` tạo Optional empty; `orElseThrow()` ném `NoSuchElementException`. Đừng nhầm với `Optional.of(null)`, vốn ném `NullPointerException` ngay khi tạo.

### Bài 4 — Chọn fallback

Bạn cần tên hiển thị `"Guest"` khi không có tên, và đây là một trường hợp hợp lệ. Nên dùng `orElseThrow()` không?

**Đáp án:** thông thường không. `maybeName.orElse("Guest")` rõ ý định hơn. Nếu fallback là phép tính tốn kém, cân nhắc `orElseGet(supplier)`.

### Bài 5 — `map` làm mất giá trị

```java
var text = java.util.Optional.of("A");
var transformed = text.map(s -> (String) null);
transformed.orElseThrow();
```

**Đáp án:** `transformed` rỗng vì mapper trả `null`; `orElseThrow()` ném `NoSuchElementException` dù `text` ban đầu present.

### Bài 6 — `filter`

```java
var result = java.util.Optional.of(5)
        .filter(n -> n > 10)
        .orElseThrow();
```

**Đáp án:** predicate false nên Optional sau filter empty; dòng cuối ném `NoSuchElementException`.

### Bài 7 — `findFirst` không có phần tử

```java
var first = java.util.List.of("A", "B")
        .stream()
        .filter(s -> s.equals("C"))
        .findFirst()
        .orElseThrow();
```

**Đáp án:** không có kết quả khớp nên `findFirst()` empty; `orElseThrow()` ném `NoSuchElementException`. Nếu không tìm thấy là bình thường, đừng unwrap bắt buộc.

### Bài 8 — Supplier có chạy khi present?

```java
var optional = java.util.Optional.of("real");
var value = optional.orElseGet(() -> "fallback");
```

**Đáp án:** `value` bằng `"real"`; supplier không được gọi vì Optional đã present. Với `orElse("fallback")` kết quả cũng là `"real"`, nhưng biểu thức đối số được đánh giá theo cú pháp gọi phương thức Java.

### Bài 9 — Ngoại lệ tùy chỉnh

```java
var absent = java.util.Optional.<String>empty();
var name = absent.orElseThrow(
        () -> new IllegalArgumentException("name is required"));
```

**Đáp án:** ném `IllegalArgumentException` với thông điệp được chỉ định, không phải `NoSuchElementException`. Đây là overload nhận supplier, khác overload không đối số.

### Bài 10 — Optional nguyên thủy

```java
var maybeMaximum = java.util.OptionalInt.of(42);
var maximum = maybeMaximum.orElseThrow();
```

**Đáp án:** `maximum` có kiểu `int` và giá trị `42`. Với `OptionalInt.empty()`, overload không đối số ném `NoSuchElementException`.

## 18. Checklist áp dụng trong dự án

Trước khi viết `orElseThrow()` không đối số, hãy xác định:

1. **Optional có thể empty một cách hợp lệ không?** Nếu có, việc ném ngoại lệ có đúng hợp đồng chức năng không?
2. **Lý do hiện diện là gì?** Có validation, invariant hoặc tiền điều kiện bảo đảm không?
3. **Khi empty, caller cần lỗi domain riêng không?** Nếu có, dùng overload supplier với exception có thông tin phù hợp.
4. **Có fallback hợp lệ không?** Xem `orElse` hoặc `orElseGet` thay cho ném.
5. **Có cần xử lý giá trị tiếp trong Optional không?** `map`, `flatMap`, `filter` có thể gọn hơn unwrap rồi kiểm tra null.
6. **Optional được tạo từ `ofNullable` hay một phép `findFirst`?** Theo dõi nguồn gốc trạng thái empty.
7. **Có mapper/predicate làm Optional thành empty không?** Kiểm tra pipeline cuối, không chỉ Optional ban đầu.
8. **Có thể nhầm NPE với NoSuchElementException không?** Nhớ `Optional.of(null)` và biến Optional null gây lỗi khác.
9. **Đang dùng kiểu primitive Optional?** `OptionalInt`/`OptionalLong`/`OptionalDouble` đều có phương thức tương ứng.
10. **Có test nhánh empty không?** Nên kiểm thử cả present và empty, không chỉ happy path.
11. **Có đang bắt rồi bỏ qua ngoại lệ?** Không nuốt lỗi nhằm che giấu tiền điều kiện bị vi phạm.
12. **Code và thông điệp có làm lộ dữ liệu nhạy cảm không?** Tránh đưa token/ID bí mật vào exception hoặc log.
13. **Java language level của dự án là gì?** Overload không đối số của `Optional` có từ Java 10; các ví dụ biên dịch bằng JDK 17+.

**Tóm tắt:** `Optional.orElseThrow()` không đối số được bổ sung trong Java 10 và vẫn là API chuẩn trong Java hiện đại. Nó **trả giá trị `T` khi present, ném `NoSuchElementException` khi empty**. So với `get()`, tên này diễn đạt rõ nhánh thất bại; so với `orElse(...)`/`orElseGet(...)`, nó không dùng fallback; so với overload có exception supplier, nó luôn chọn loại ngoại lệ mặc định. Hãy dùng khi việc thiếu giá trị thực sự là lỗi cần fail fast, và giữ Optional hoặc chọn cách xử lý khác khi “không có kết quả” là một trạng thái bình thường của nghiệp vụ.