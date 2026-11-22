# Optional: map, flatMap và filter trong Java

## 1. Mục tiêu bài học

`Optional<T>` là một kiểu trong `java.util` biểu diễn **một giá trị kiểu T có thể có hoặc không có**, thay vì bắt mọi nơi xử lý giá trị trả về có thể là `null`. Ba phương thức `map`, `flatMap` và `filter` giúp biến đổi hoặc chọn lọc giá trị **mà không cần liên tục gọi `isPresent()` rồi `get()`**.

Tư duy cần nhớ:

- **`map`:** Có giá trị thì **biến đổi giá trị** thành một giá trị khác; rỗng thì tiếp tục rỗng. Hàm biến đổi trả `U` hoặc `null`.
- **`flatMap`:** Có giá trị thì gọi hàm **đã trả về Optional<U>** và giữ nguyên một lớp `Optional`; rỗng thì tiếp tục rỗng.
- **`filter`:** Có giá trị thì **kiểm tra điều kiện**; giữ lại giá trị cũ khi điều kiện đúng, đổi thành rỗng khi sai.

Ví dụ dòng xử lý dữ liệu người dùng:

```text
Optional<Account>
      |
      | flatMap(Account::profile)     // Account -> Optional<Profile>
      v
Optional<Profile>
      |
      | map(Profile::email)           // Profile -> String
      v
Optional<String>
      |
      | map(String::trim)             // String -> String
      | filter(s -> !s.isBlank())     // giữ email không rỗng
      v
Optional<String>
      |
      | orElse("not available")       // giải quyết nhánh thiếu dữ liệu
      v
String
```

`Optional` cùng ba phương thức trên đã có từ Java 8 và vẫn là API được hỗ trợ trong Java hiện đại. Những ví dụ dùng `String.isBlank()` hoặc `Optional.stream()` sẽ ghi rõ yêu cầu phiên bản; chương trình đầy đủ trong bài ưu tiên JDK 17 trở lên.

> **Nguyên tắc:** Dùng `map` cho hàm trả **giá trị thường**; dùng `flatMap` cho hàm trả **Optional**; dùng `filter` cho một **predicate boolean** quyết định giữ hay bỏ giá trị.

## 2. Nhắc lại Optional có và không có giá trị

`Optional<T>` chỉ có hai trạng thái quan sát được:

1. **Present:** chứa đúng một giá trị không `null`.
2. **Empty:** không chứa giá trị nào.

Các cách tạo thông dụng:

```java
// Đoạn minh họa, import java.util.Optional.
Optional<String> present = Optional.of("Java");
Optional<String> empty = Optional.empty();

String possiblyNull = null;
Optional<String> safe = Optional.ofNullable(possiblyNull);
```

- `Optional.of(value)` yêu cầu `value != null`; truyền `null` sẽ gây `NullPointerException`.
- `Optional.ofNullable(value)` tạo `Optional.empty()` nếu `value == null`.
- `Optional.empty()` tạo một Optional không có giá trị.
- **Bản thân biến Optional không nên là null**. Ví dụ `Optional<String> result = null` làm mất ý nghĩa của API và khiến các lời gọi `map`/`flatMap`/`filter` có thể bị `NullPointerException`.

`Optional` được thiết kế chủ yếu cho **giá trị trả về của phương thức** khi sự vắng mặt là một kết quả hợp lệ. Đừng xem nó là một tập hợp nhiều phần tử hoặc một cơ chế bắt ngoại lệ. Nó không tự thực hiện truy vấn bất đồng bộ, không tự chạy đa luồng và không tự làm cho một phép biến đổi nguy hiểm trở nên an toàn.

## 3. Bảng so sánh map, flatMap và filter

| Phương thức | Hàm truyền vào | Khi Optional có giá trị | Khi Optional rỗng | Kiểu trả về |
| --- | --- | --- | --- | --- |
| `map` | `Function<T,U>` | Gọi hàm, bọc kết quả khác null thành Optional; kết quả null thành rỗng | Không gọi hàm, trả Optional rỗng | `Optional<U>` |
| `flatMap` | `Function<T,Optional<U>>` | Gọi hàm và trả **Optional do hàm sinh ra** | Không gọi hàm, trả Optional rỗng | `Optional<U>` |
| `filter` | `Predicate<T>` | Nếu điều kiện đúng thì giữ giá trị, sai thì rỗng | Không gọi predicate, trả Optional rỗng | `Optional<T>` |

Chữ ký API hiện hành, viết theo dạng tổng quát để học:

```java
<U> Optional<U> map(Function<? super T, ? extends U> mapper);

<U> Optional<U> flatMap(
    Function<? super T, ? extends Optional<? extends U>> mapper
);

Optional<T> filter(Predicate<? super T> predicate);
```

Đây là **trích yếu chữ ký từ giao diện API**, không phải ba method tự do có thể dán vào một chương trình Java độc lập. Các kiểu `Function` và `Predicate` nằm trong `java.util.function`.

Sự khác nhau **không nằm ở việc map chỉ xử lý một phần tử còn flatMap xử lý nhiều phần tử**. Đó là cách giải thích có thể dùng cho `Stream.flatMap`, nhưng với **`Optional.flatMap`**, điều quan trọng là **hàm trả về một Optional khác** và phép gọi loại bỏ lớp bọc Optional dư thừa.

## 4. map: biến đổi giá trị bên trong Optional

### 4.1. Định nghĩa

`Optional.map(mapper)` kiểm tra trạng thái của Optional:

- Nếu **present**, áp dụng `mapper` lên giá trị `T` rồi trả `Optional<U>`. Nếu mapper trả `null`, kết quả sẽ là `Optional.empty()`, tương đương bọc mapper result bằng `Optional.ofNullable`.
- Nếu **empty**, không chạy mapper và trả Optional rỗng.

Ví dụ:

```java
// Mã minh họa.
Optional<String> name = Optional.of("  java  ");

Optional<String> normalized = name
    .map(String::trim)
    .map(String::toUpperCase);

// normalized là Optional[JAVA].
```

Với `String::trim`, kiểu nhận vào và trả về đều là `String`. Nhưng `map` cũng có thể **thay đổi kiểu**:

```java
// Mã minh họa.
Optional<Integer> length = Optional.of("Java")
    .map(String::length);

// length chứa số 4 (Optional<Integer>).
```

Nếu không có giá trị, không cần câu lệnh `if (name != null)` ở từng bước: cả chuỗi biến đổi được **bỏ qua** theo trạng thái empty.

### 4.2. Ví dụ đầy đủ — OptionalMapDemo.java

Tạo file **OptionalMapDemo.java**:

```java
import java.util.Optional;

public class OptionalMapDemo {
    public static void main(String[] args) {
        Optional<String> input = Optional.of("  java  ");

        System.out.println("mapped=" +
            input.map(String::trim)
                 .map(String::toUpperCase)
                 .orElse("MISSING"));

        System.out.println("filtered=" +
            input.map(String::trim)
                 .filter(s -> s.length() >= 5)
                 .orElse("MISSING"));

        System.out.println("empty=" +
            Optional.<String>empty()
                .map(String::toUpperCase));

        System.out.println("nullMapper=" +
            Optional.of("abc")
                .map(s -> (String) null));
    }
}
```

Biên dịch và chạy:

```bash
javac OptionalMapDemo.java
java OptionalMapDemo
```

Đầu ra xác định:

```text
mapped=JAVA
filtered=MISSING
empty=Optional.empty
nullMapper=Optional.empty
```

**Giải thích:**

1. `map(String::trim)` chuyển `"  java  "` thành `"java"`; `map(String::toUpperCase)` chuyển tiếp thành `"JAVA"`.
2. Giá trị sau trim dài 4 ký tự nên `filter(s -> s.length() >= 5)` loại bỏ nó; `orElse("MISSING")` chọn giá trị dự phòng.
3. `Optional.empty().map(...)` không gọi mapper, không tạo một `String` giả để xử lý.
4. Mapper trả `null` không tạo `Optional.of(null)` và không tự ném `NullPointerException`: theo hợp đồng `map`, kết quả là `Optional.empty()`.

**Lưu ý:** Nếu chính mapper gọi một phương thức trên đối tượng null **trong quá trình tính toán**, nó vẫn có thể ném `NullPointerException`; `map` chỉ biến **kết quả trả về null** thành Optional rỗng, chứ không tự bắt mọi ngoại lệ từ mapper.

## 5. flatMap: tránh Optional lồng Optional

### 5.1. Tại sao map chưa đủ?

Xét hàm đã trả về Optional:

```java
// Đoạn minh họa; phương thức có thể được đặt trong một lớp.
static Optional<String> domain(String email) {
    int at = email.indexOf("@");
    return at >= 0 && at + 1 < email.length()
        ? Optional.of(email.substring(at + 1))
        : Optional.empty();
}
```

Khi viết:

```java
// Đoạn minh họa.
Optional<Optional<String>> nested = Optional.of("ana@example.com")
    .map(MyClass::domain);
```

vì `domain(...)` **đã trả `Optional<String>`**, `map` bọc nó thêm một lớp, tạo `Optional<Optional<String>>`. Biến `MyClass` ở đây biểu thị lớp chứa hàm `domain`, không phải lớp được định nghĩa trong ví dụ độc lập.

Thay `map` bằng `flatMap`:

```java
// Đoạn minh họa.
Optional<String> flat = Optional.of("ana@example.com")
    .flatMap(MyClass::domain);
```

Ta chỉ còn **một** `Optional<String>`. Cách này rất hữu ích khi kết nối các phương thức *lookup* hoặc *truy xuất* mà mỗi bước đều có thể không tìm được kết quả.

### 5.2. Ví dụ đầy đủ — OptionalFlatMapDemo.java

Tạo file **OptionalFlatMapDemo.java**:

```java
import java.util.Optional;

public class OptionalFlatMapDemo {
    static Optional<String> domain(String email) {
        int pos = email.indexOf("@");

        return pos >= 0 && pos + 1 < email.length()
            ? Optional.of(email.substring(pos + 1))
            : Optional.empty();
    }

    public static void main(String[] args) {
        String input = "ana@example.com";

        Optional<Optional<String>> nested =
            Optional.of(input).map(OptionalFlatMapDemo::domain);

        Optional<String> flat =
            Optional.of(input).flatMap(OptionalFlatMapDemo::domain);

        System.out.println("nested=" + nested);
        System.out.println("flat=" + flat);
        System.out.println("notEmail=" +
            Optional.of("invalid")
                .flatMap(OptionalFlatMapDemo::domain));
    }
}
```

```bash
javac OptionalFlatMapDemo.java
java OptionalFlatMapDemo
```

Đầu ra:

```text
nested=Optional[Optional[example.com]]
flat=Optional[example.com]
notEmail=Optional.empty
```

**Phân tích:**

- `nested` có hai lớp Optional. Lớp ngoài là Optional của kết quả do `domain` trả ra; lớp trong chứa `"example.com"`.
- `flat` chỉ có một lớp vì `flatMap` trả kết quả Optional do `domain` tạo.
- `domain("invalid")` trả `Optional.empty()` khi không thấy dấu `@`, nên `flatMap` cũng trả rỗng.

Hàm kiểm tra domain ở đây chỉ là ví dụ đơn giản về `Optional`, **không phải bộ kiểm tra email chuẩn**. Trong ứng dụng thật, cần validation phù hợp với yêu cầu nghiệp vụ.

### 5.3. Quy tắc quan trọng về null của flatMap

`flatMap` yêu cầu mapper **trả về đối tượng Optional không null**. Nếu mapper trả `null`, nó ném `NullPointerException`. Điều này **khác `map`**.

Đúng:

```java
// Mã minh họa.
Optional<String> result = Optional.of("value")
    .flatMap(v -> Optional.empty());
```

Sai:

```java
// SAI: mapper trả null thay vì Optional.empty().
Optional<String> result = Optional.of("value")
    .flatMap(v -> (Optional<String>) null);
```

Nếu phương thức hiện tại trả `U` hoặc `null` chứ **không trả Optional**, nên dùng `map`. Nếu phương thức trả `Optional<U>`, dùng `flatMap`. Trường hợp một API bên ngoài **được thiết kế sai** và trả null thay cho Optional, nên sửa contract API ở nguồn thay vì coi null là một trạng thái Optional hợp lệ.

## 6. filter: giữ hoặc bỏ giá trị theo predicate

`Optional.filter(predicate)` trả:

- **Optional chứa giá trị gốc** nếu đang present và predicate trả `true`.
- **Optional.empty()`** nếu predicate trả `false` hoặc Optional ban đầu rỗng.

Kiểu đầu vào và đầu ra giữ nguyên `Optional<T>`. Khác `map`, `filter` **không biến đổi phần tử thành một kiểu khác**, và không trả về Optional chứa boolean.

Ví dụ:

```java
// Đoạn minh họa.
Optional<Integer> score = Optional.of(85);

Optional<Integer> accepted = score.filter(n -> n >= 60);
// accepted = Optional[85]

Optional<Integer> rejected = score.filter(n -> n >= 90);
// rejected = Optional.empty
```

Predicate `n -> n >= 60` không đưa `true` vào Optional; nó **quyết định giữ hay loại bỏ số 85**.

### 6.1. Điều kiện sau map

Thứ tự pipeline có thể quan trọng:

```java
// Mã minh họa, giá trị String ban đầu có khoảng trắng.
Optional<String> input = Optional.of("   Ana   ");

Optional<String> result = input
    .map(String::trim)
    .filter(s -> s.length() >= 3)
    .map(String::toUpperCase);
// result chứa "ANA".
```

Nếu đặt `filter(s -> s.length() >= 3)` **trước** `trim`, predicate kiểm tra cả khoảng trắng. Khi đó kết quả có thể khác nếu logic yêu cầu độ dài của tên đã chuẩn hóa. Một cách tốt là chuẩn hóa trước, xác thực sau, rồi thực hiện biến đổi cuối.

### 6.2. Khi nào dùng filter?

Những ví dụ thực tế:

- `filter(s -> !s.isBlank())` — bỏ chuỗi rỗng hoặc chỉ gồm khoảng trắng (Java 11+).
- `filter(n -> n > 0)` — chỉ chấp nhận giá trị dương.
- `filter(user -> user.isActive())` — chỉ giữ user đang hoạt động.
- `filter(email -> email.contains("@"))` — minh họa điều kiện đơn giản, không phải validation email đầy đủ.
- `filter(path -> Files.isRegularFile(path))` — chỉ giữ đường dẫn đang trỏ đến file thường; cần suy xét race giữa lúc kiểm tra và lúc sử dụng.

Không nên làm side effect bất ngờ trong predicate. Predicate có ý nghĩa là **kiểm tra và trả boolean**; việc sửa trạng thái ngoài làm code khó kiểm thử và khó giải thích.

## 7. Ví dụ nghiệp vụ — ghép flatMap, map và filter

Giả sử hệ thống có tài khoản `Account`, nhưng tài khoản có thể không có `Profile`; profile có thể thiếu email hoặc email chứa khoảng trắng. Ta muốn trả một email chữ thường, đã trim, và không rỗng. Nếu ở bất cứ bước nào dữ liệu không có, trả `"not available"`.

Tạo file **OptionalProfileDemo.java**:

```java
import java.util.Locale;
import java.util.Optional;

public class OptionalProfileDemo {
    static final class Profile {
        private final String email;

        Profile(String email) {
            this.email = email;
        }

        String email() {
            return email;
        }
    }

    static final class Account {
        private final Profile profile;

        Account(Profile profile) {
            this.profile = profile;
        }

        Optional<Profile> profile() {
            return Optional.ofNullable(profile);
        }
    }

    static Optional<Account> find(String id) {
        if ("a1".equals(id)) {
            return Optional.of(
                new Account(new Profile("  ANA@EXAMPLE.COM  "))
            );
        }

        if ("a2".equals(id)) {
            return Optional.of(new Account(null));
        }

        return Optional.empty();
    }

    static String verifiedEmail(String id) {
        return find(id)
            .flatMap(Account::profile)
            .map(Profile::email)
            .map(String::trim)
            .filter(s -> !s.isBlank())
            .map(s -> s.toLowerCase(Locale.ROOT))
            .orElse("not available");
    }

    public static void main(String[] args) {
        System.out.println("a1=" + verifiedEmail("a1"));
        System.out.println("a2=" + verifiedEmail("a2"));
        System.out.println("missing=" + verifiedEmail("missing"));
    }
}
```

```bash
javac OptionalProfileDemo.java
java OptionalProfileDemo
```

Đầu ra xác định:

```text
a1=ana@example.com
a2=not available
missing=not available
```

**Diễn giải từng bước:**

1. `find(id)` trả `Optional<Account>`. Nếu ID không tồn tại, trả `Optional.empty()`.
2. `flatMap(Account::profile)` được chọn vì `profile()` đã trả về `Optional<Profile>`. Nếu tài khoản không có Profile, chuỗi chuyển thành rỗng mà không cần `get()`.
3. `map(Profile::email)` được chọn vì `email()` trả `String`, có thể null. Nếu null, `map` chuyển thành Optional rỗng.
4. `map(String::trim)` xóa khoảng trắng ở hai đầu; nếu Optional đang empty, mapper không chạy.
5. `filter(s -> !s.isBlank())` bỏ email rỗng. `String.isBlank()` có từ Java 11 và vẫn dùng tốt trong Java 17+.
6. `map(s -> s.toLowerCase(Locale.ROOT))` tạo dạng chữ thường không phụ thuộc locale mặc định của máy.
7. `orElse("not available")` biến Optional cuối thành `String` thông thường để hiển thị.

**Chú ý ranh giới phạm vi:** Ví dụ minh họa **chuyển đổi dữ liệu và xử lý thiếu dữ liệu**, không kiểm tra cú pháp email hoàn chỉnh, không thực hiện truy vấn database, và không khẳng định hai trạng thái “không có tài khoản” và “không có profile” phải có cùng thông báo trong mọi nghiệp vụ. Nếu cần biết nguyên nhân cụ thể, `Optional.empty()` một mình có thể không đủ; phải dùng kiểu kết quả biểu đạt thêm mã lỗi/nguyên nhân.

## 8. Ví dụ kết hợp filter với map và Stream

### 8.1. Điểm số: đỗ, không đỗ và không có điểm

`filter` rất phù hợp để biểu diễn việc giá trị có đáp ứng điều kiện nhận hay không:

```java
// Đoạn minh họa.
String outcome = Optional.of(85)
    .filter(n -> n >= 60)
    .map(n -> "PASS:" + n)
    .orElse("FAIL");
// "PASS:85"
```

Tuy nhiên, công thức dùng `orElse("FAIL")` ở đây **gộp cả hai trường hợp “điểm thấp” và “không có điểm”** thành một chuỗi. Trong hệ thống đánh giá thật, “chưa có điểm” có thể cần trạng thái riêng thay vì `FAIL`. Một pipeline Optional thường diễn đạt rất tốt **có/không**, nhưng không tự phân biệt tất cả các lý do không có dữ liệu.

### 8.2. Optional.stream() trong Stream lớn

Từ Java 9, `Optional.stream()` chuyển:

- `Optional.of(value)` thành Stream có **một** phần tử.
- `Optional.empty()` thành Stream **rỗng**.

Từ đó có thể chuyển `Stream<Optional<T>>` thành `Stream<T>` bằng `flatMap(Optional::stream)`.

Tạo file **OptionalStreamDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class OptionalStreamDemo {
    public static void main(String[] args) {
        List<Optional<String>> values = Arrays.asList(
            Optional.of("A"),
            Optional.empty(),
            Optional.of("B")
        );

        List<String> present = values.stream()
            .flatMap(Optional::stream)
            .collect(Collectors.toList());

        System.out.println("present=" + present);

        System.out.println("passing=" +
            Optional.of(85)
                .filter(n -> n >= 60)
                .map(n -> "PASS:" + n)
                .orElse("FAIL"));

        System.out.println("failing=" +
            Optional.of(45)
                .filter(n -> n >= 60)
                .map(n -> "PASS:" + n)
                .orElse("FAIL"));

        System.out.println("noScore=" +
            Optional.<Integer>empty()
                .filter(n -> n >= 60)
                .map(n -> "PASS:" + n)
                .orElse("FAIL"));
    }
}
```

```bash
javac OptionalStreamDemo.java
java OptionalStreamDemo
```

Đầu ra:

```text
present=[A, B]
passing=PASS:85
failing=FAIL
noScore=FAIL
```

**Phân biệt hai flatMap khác nhau:**

- `Optional.flatMap(fn)` yêu cầu `fn: T -> Optional<U>` và làm phẳng **một lớp Optional**.
- `Stream.flatMap(fn)` yêu cầu `fn: T -> Stream<U>` và hợp nhất **các Stream con** vào Stream kết quả. Ở đây mỗi Optional chuyển thành một Stream 0 hoặc 1 phần tử bằng `Optional::stream`.

Đừng nhầm `Stream.flatMap` với `Optional.flatMap` chỉ vì trùng tên. Cả hai đều thực hiện ý tưởng “làm phẳng cấu trúc chứa”, nhưng **kiểu dữ liệu và cardinality** của chúng khác nhau.

Với dự án bắt buộc chỉ dùng Java 8, `Optional.stream()` **chưa tồn tại** trong API Java 8; có thể dùng `filter(Optional::isPresent).map(Optional::get)` trên Stream với kiểm tra rõ ràng, hoặc dùng `flatMap(o -> o.isPresent() ? Stream.of(o.get()) : Stream.empty())`. Nhưng với Java 17+, `flatMap(Optional::stream)` ngắn gọn và rõ ràng hơn.

## 9. Các trường hợp null, rỗng và ngoại lệ

Đây là phần dễ gây lỗi nhất khi chuyển từ code dùng `null` sang Optional.

### 9.1. map nhận mapper trả null

```java
Optional<String> result = Optional.of("value")
    .map(v -> (String) null);
// Optional.empty
```

Cách gọi này **hợp lệ** theo contract: `map` tự xử lý kết quả mapper bằng ngữ nghĩa `ofNullable`. Nhưng đừng lợi dụng `null` làm kiểu dữ liệu nghiệp vụ mặc định nếu có thể trả một giá trị rõ ràng hoặc thiết kế API trả `Optional`.

### 9.2. flatMap nhận mapper trả null

```java
// SAI; đoạn minh họa này ném NullPointerException khi có giá trị.
Optional<String> result = Optional.of("value")
    .flatMap(v -> (Optional<String>) null);
```

Khi muốn chỉ ra không có kết quả, mapper của `flatMap` phải trả **`Optional.empty()`**, không trả `null`.

### 9.3. filter có predicate false

```java
Optional<String> result = Optional.of("value")
    .filter(v -> false);
// Optional.empty
```

`filter` không chứa `false` trong Optional: nó **loại bỏ giá trị**. Predicate nên thực hiện kiểm tra và trả boolean, không sửa nguồn dữ liệu bất ngờ.

### 9.4. Nếu Optional đầu vào rỗng

`map`, `flatMap` và `filter` **không gọi hàm được truyền vào** nếu không có giá trị. Có thể ghép chúng mà không phải thêm một nhánh `if` cho mỗi lần duyệt:

```java
Optional<String> result = Optional.<String>empty()
    .map(String::trim)
    .filter(v -> true);
// Optional.empty
```

**Ngoại lệ do hàm ném ra không được Optional tự hấp thụ:** nếu mapper/predicate được chạy và ném `IllegalArgumentException`, `NullPointerException` hay ngoại lệ runtime khác, ngoại lệ được truyền lên caller. `Optional.empty()` không phải cơ chế `try/catch`.

### 9.5. Ví dụ đầy đủ — OptionalNullContractDemo.java

Tạo file **OptionalNullContractDemo.java**:

```java
import java.util.Optional;

public class OptionalNullContractDemo {
    public static void main(String[] args) {
        System.out.println("mapNull=" +
            Optional.of("value")
                .map(v -> (String) null));

        try {
            Optional.of("value")
                .flatMap(v -> (Optional<String>) null);
        } catch (NullPointerException expected) {
            System.out.println("flatMapNull=NPE");
        }

        System.out.println("filterFalse=" +
            Optional.of("value").filter(v -> false));

        System.out.println("emptyChain=" +
            Optional.<String>empty()
                .map(String::trim)
                .filter(v -> true));
    }
}
```

```bash
javac OptionalNullContractDemo.java
java OptionalNullContractDemo
```

Đầu ra:

```text
mapNull=Optional.empty
flatMapNull=NPE
filterFalse=Optional.empty
emptyChain=Optional.empty
```

Qua ví dụ này, có thể phân biệt rõ:

| Tình huống | Kết quả |
| --- | --- |
| `Optional.of("x").map(v -> null)` | `Optional.empty()` |
| `Optional.of("x").flatMap(v -> null)` | Ném `NullPointerException` |
| `Optional.of("x").filter(v -> false)` | `Optional.empty()` |
| `Optional.empty().map(...)` | Rỗng, mapper không chạy |
| `Optional.empty().flatMap(...)` | Rỗng, mapper không chạy |
| `Optional.empty().filter(...)` | Rỗng, predicate không chạy |

**Cảnh báo:** Không dựa vào `toString()` của Optional như một định dạng trao đổi dữ liệu chính thức. Chuỗi `Optional[foo]` và `Optional.empty` trong ví dụ hữu ích để học/debug, nhưng khi thiết kế JSON/API, hãy chủ động chuyển Optional sang định dạng rõ ràng.

## 10. Chuỗi biến đổi: chọn đúng bước và thứ tự

Một pipeline phổ biến:

```java
// Đoạn minh họa, input có kiểu Optional<String>.
Optional<Integer> normalizedLength = input
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .map(String::length)
    .filter(length -> length <= 100);
```

Sự thay đổi kiểu:

```text
Optional<String>
 -> map(trim)              Optional<String>
 -> filter(nonEmpty)       Optional<String>
 -> map(length)            Optional<Integer>
 -> filter(length <= 100)  Optional<Integer>
```

**Chọn `map` ở đây:** `String::length` trả `int`; do autoboxing, kết quả trong Optional là `Integer`. Không dùng `flatMap` vì `String::length` **không trả Optional<Integer>`.

Nếu một phương thức trả `Optional<Integer>`, ví dụ `lookupPort(String)` có thể không tìm được cổng dịch vụ, dùng:

```java
// Đoạn minh họa, trong ngữ cảnh có method:
// Optional<Integer> lookupPort(String service)
Optional<Integer> port = serviceName
    .flatMap(this::lookupPort)
    .filter(p -> p >= 1 && p <= 65535);
```

`serviceName` được hiểu là `Optional<String>`. Nếu `lookupPort` trả Optional rỗng, chuỗi dừng về mặt kết quả ở đó. Đây là một pipeline **có thể hoàn toàn chạy tuần tự trong thread hiện tại**, không có hành vi song song tự phát.

### 10.1. Đặt filter trước hay sau map?

- `filter` **trước map** khi điều kiện liên quan đến dữ liệu đầu vào: ví dụ bỏ user không active rồi mới lấy email.
- `filter` **sau map** khi điều kiện liên quan đến giá trị đã biến đổi: ví dụ trim chuỗi rồi bỏ nếu rỗng.
- Nếu một hàm biến đổi có chi phí lớn, lọc bỏ các trường hợp không cần thiết trước khi gọi nó thường tốt hơn.

Tuy nhiên, **không tự ý đổi thứ tự** nếu hai predicate dùng hai đại diện dữ liệu khác nhau; kết quả nghiệp vụ có thể thay đổi.

### 10.2. Một Optional không phải danh sách nhiều kết quả

`Optional<T>` chỉ có 0 hoặc 1 giá trị `T`. `filter` không biến nó thành danh sách; `map` không tự tạo một tập giá trị. Nếu cần xử lý nhiều item, dùng `Stream<T>` hoặc collection. `Optional` thường mô tả **kết quả có thể vắng mặt của một bước đơn lẻ**.

## 11. Kết thúc pipeline đúng cách

`map`, `flatMap` và `filter` đều **trả Optional**. Đến ranh giới hiển thị, trả dữ liệu ra API hoặc thực hiện một tác vụ, chương trình thường cần giải quyết giá trị absent:

### orElse

```java
// Mã minh họa.
String name = maybeName
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .orElse("Anonymous");
```

`orElse("Anonymous")` trả giá trị dự phòng nếu rỗng. Nếu biểu thức tạo giá trị dự phòng có side effect/chi phí, nó sẽ được đánh giá khi gọi phương thức, kể cả khi Optional có giá trị.

### orElseGet

```java
// Đoạn minh họa.
String name = maybeName.orElseGet(
    () -> loadFallbackName()
);
```

`loadFallbackName()` là method giả định được khai báo trong ứng dụng. `orElseGet` chỉ gọi supplier khi Optional rỗng, nên phù hợp cho fallback tốn chi phí hoặc có side effect được kiểm soát.

### orElseThrow

```java
// Mã minh họa.
String name = maybeName.orElseThrow(
    () -> new IllegalStateException("Name is required")
);
```

Phù hợp khi thiếu dữ liệu là tình huống phải báo lỗi. Đừng dùng `get()` bừa bãi vì nó ném `NoSuchElementException` khi rỗng, làm mất lợi ích của việc mô tả nhánh vắng mặt rõ ràng. `get()` vẫn tồn tại trong API; nó chỉ thường là lựa chọn kém rõ ràng hơn `orElseThrow(...)` hoặc các operation chuyên biệt.

### Giữ Optional thay vì ép về String

Không bắt buộc phải `orElse(...)` ở mọi bước. Nếu hàm của bạn chủ động trả về `Optional<String>`, có thể giữ nguyên toàn bộ pipeline:

```java
// Đoạn minh họa; caller tự xử lý empty theo nhu cầu.
Optional<String> normalized = maybeName
    .map(String::trim)
    .filter(s -> !s.isBlank());
```

Đây thường là cách tốt để duy trì thông tin **có hay không có giá trị** trong chữ ký của method.

## 12. Thực hành an toàn và các giới hạn của Optional

### 12.1. Đừng trả null cho method khai báo Optional

Sai:

```java
// SAI: phương thức nói sẽ trả Optional nhưng thực tế trả null.
Optional<User> findUser(String id) {
    return null;
}
```

Đúng:

```java
// Mã minh họa: User là lớp nghiệp vụ.
Optional<User> findUser(String id) {
    return Optional.empty(); // Khi không tìm thấy.
}
```

Nếu dữ liệu đến từ API cũ trả `User` hoặc `null`, lớp adapter có thể dùng `Optional.ofNullable(...)`. Việc này làm hợp đồng hàm có thể vắng mặt được thể hiện trong kiểu trả về.

### 12.2. Optional không tự xử lý exception

`Optional.map` và `flatMap` không tự bắt `IOException`, lỗi database hay lỗi validation. Nếu muốn biểu diễn cả **thành công**, **không có dữ liệu** và **thất bại có lý do**, nên dùng một mô hình kết quả phù hợp hơn chỉ `Optional.empty()`. Đừng che lỗi hệ thống thành “không tìm thấy” khi đó là hai trường hợp khác nhau.

### 12.3. Tránh side effect trong mapper và predicate

`Optional` thường chỉ gọi function khi có giá trị, nhưng pipeline rõ ràng nhất khi các hàm **không thay đổi state ngoài**. Ví dụ mapper tự cập nhật database trong lúc chuẩn hóa tên khiến việc kiểm thử và tái sử dụng khó khăn. Tách việc biến đổi dữ liệu và hành động có side effect, chỉ thực hiện side effect ở ranh giới đã rõ.

### 12.4. Optional không nên được so sánh bằng ==

`Optional` là **value-based class** theo Javadoc. Không dùng `==` để so sánh ngữ nghĩa hai giá trị Optional hoặc dùng đối tượng Optional làm khóa để đồng bộ hóa. Khi cần so sánh giá trị, dùng `equals`/các giá trị bên trong theo hợp đồng.

### 12.5. Dữ liệu collection và Optional

`Optional<List<T>>` đôi khi có ý nghĩa để phân biệt “danh sách không tồn tại” với “danh sách tồn tại nhưng rỗng”, nhưng không phải mặc định luôn tốt hơn `List<T>`. Nếu “không có phần tử” đã được biểu diễn đầy đủ bằng danh sách rỗng, chỉ cần `List<T>`. Đặt Optional đúng ranh giới giúp API dễ dùng hơn.

### 12.6. Kiểu primitive

Nếu một phương thức có thể trả một số nguyên hoặc không có số nào, Java cung cấp `OptionalInt`, `OptionalLong`, `OptionalDouble`. Tuy nhiên **API của chúng không giống hoàn toàn** `Optional<T>`: đừng giả định chúng đều có `map`, `flatMap` và `filter` theo cùng chữ ký. Bài này đang nói về **`Optional<T>` kiểu tham chiếu**.

## 13. Lỗi thường gặp

1. **Dùng `map` cho hàm đã trả `Optional<U>`.** Kết quả trở thành `Optional<Optional<U>>` không mong muốn. Đổi sang `flatMap` nếu muốn làm phẳng một lớp.
2. **Dùng `flatMap` cho hàm trả `String`/`Integer` thông thường.** Sai kiểu hàm; dùng `map` thay thế.
3. **Để mapper của `flatMap` trả `null`.** Ném `NullPointerException`; khi không có giá trị phải trả `Optional.empty()`.
4. **Nghĩ `map` bắt mọi NullPointerException.** Nó chỉ chuyển **kết quả mapper null** thành empty; nếu mapper tự ném ngoại lệ thì vẫn lỗi.
5. **Nghĩ `filter` trả `Optional<Boolean>`.** Nó giữ lại giá trị gốc hoặc loại thành empty. Muốn tạo boolean, cần phép biến đổi phù hợp hoặc `isPresent()` khi nghiệp vụ chỉ hỏi có kết quả hay không.
6. **Dùng `isPresent()` và `get()` ở từng bước.** Dễ gây logic lặp lại và lỗi khi empty. Hãy thử biểu diễn bằng `map`/`flatMap`/`filter` rồi xử lý absent ở cuối.
7. **Trộn lẫn “không có dữ liệu” với “không hợp lệ”.** Sau `filter` thất bại, bạn chỉ còn empty; nếu cần chi tiết nguyên nhân, phải thiết kế kiểu kết quả giàu thông tin hơn.
8. **Trả `null` thay cho Optional.empty().** Phá contract API và làm mọi pipeline phía gọi có nguy cơ NPE.
9. **Gọi `Optional.stream()` rồi nghĩ có trong Java 8.** Method này được bổ sung từ Java 9; với code base Java 17+ có thể dùng bình thường.
10. **Nhầm `Optional.flatMap` với `Stream.flatMap`.** Một bên nhận function trả `Optional<U>`, một bên nhận function trả `Stream<U>`.
11. **Dùng `String.isBlank()` nhưng biên dịch trên Java 8.** Method này có từ Java 11. Nếu phải tương thích Java 8, có thể dùng quy tắc tương ứng theo yêu cầu như `!s.trim().isEmpty()` (khác `isBlank` ở một số khoảng trắng Unicode).
12. **Gọi `orElse(expensive())` và tưởng chạy lazy.** Biểu thức tham số được đánh giá trước khi gọi method; nếu chỉ muốn tạo fallback khi empty, dùng `orElseGet(() -> expensive())`.
13. **Dùng Optional như trường dữ liệu nullable, rồi kiểm tra cả Optional == null.** Tạo thêm tầng không chắc chắn; method trả Optional phải trả một instance Optional có nghĩa, không trả null.
14. **Cho rằng Optional tự bảo đảm thread-safety của đối tượng chứa bên trong.** Optional không làm đối tượng mutable chứa trong nó trở thành thread-safe; các quy tắc về đồng thời của đối tượng vẫn áp dụng.

## 14. Checklist khi review một pipeline Optional

Trước khi chấp nhận code:

1. Giá trị đầu tiên đã được tạo bằng `Optional.of` khi chắc chắn non-null, hoặc `Optional.ofNullable` khi nguồn có thể null?
2. Mỗi `map` có dùng hàm trả `U` (không phải `Optional<U>`) không?
3. Mỗi `flatMap` có dùng hàm trả **Optional không null** không?
4. Mỗi `filter` có kiểm tra đúng trạng thái **trước hoặc sau chuẩn hóa** theo nghiệp vụ?
5. Khi một bước trả empty, các bước sau có bỏ qua mapper/predicate đúng như dự kiến?
6. Có xử lý trường hợp không có dữ liệu ở ranh giới bằng `orElse`, `orElseGet`, `orElseThrow` hoặc tiếp tục trả Optional?
7. Có phân biệt lỗi hệ thống với “không có giá trị” khi nghiệp vụ cần thông tin này?
8. Có tránh `get()` khi không chứng minh được Optional có giá trị?
9. Có tránh side effect, dữ liệu mutable chia sẻ và phép biến đổi gây ngoại lệ bất ngờ?
10. Các method sử dụng như `Optional.stream()` (Java 9+) và `String.isBlank()` (Java 11+) có phù hợp với JDK được dự án hỗ trợ?

## 15. Tự kiểm tra kiến thức

**Câu 1.** `Optional.of(" Java ").map(String::trim)` trả về kiểu và giá trị nào?

**Đáp án:** `Optional<String>` chứa `"Java"`.

**Câu 2.** `Optional.of("x").map(s -> Optional.of(s.toUpperCase()))` tạo kiểu gì?

**Đáp án:** `Optional<Optional<String>>`. Nếu mục tiêu là `Optional<String>`, dùng `flatMap(s -> Optional.of(s.toUpperCase()))`.

**Câu 3.** `Optional.of(42).filter(n -> n > 100)` cho kết quả nào?

**Đáp án:** `Optional.empty()`, không phải `Optional[false]`.

**Câu 4.** Nếu `Optional.empty().map(...)`, mapper có được gọi không?

**Đáp án:** Không. Optional không có giá trị nên mapper được bỏ qua.

**Câu 5.** `Optional.of("value").map(x -> null)` khác `flatMap(x -> null)` như thế nào?

**Đáp án:** `map` trả Optional rỗng; `flatMap` ném `NullPointerException` khi mapper trả null.

**Câu 6.** Trong pipeline `find(id).flatMap(Account::profile).map(Profile::email)`, vì sao `flatMap` được dùng cho `profile()`?

**Đáp án:** Vì `profile()` trả `Optional<Profile>`, và ta không muốn có `Optional<Optional<Profile>>`.

**Câu 7.** Có thể thay `filter(s -> !s.isBlank())` bằng `map(s -> !s.isBlank())` mà giữ cùng ý nghĩa không?

**Đáp án:** Không. `filter` giữ hoặc bỏ `String`; `map` chuyển thành `Optional<Boolean>`. Hai operation có mục tiêu và kiểu kết quả khác nhau.

**Câu 8.** `Stream<Optional<String>>` thành `Stream<String>` trong Java 17+ nên viết như thế nào?

**Đáp án:** `stream.flatMap(Optional::stream)`.

**Câu 9.** Nên chọn `orElse` hay `orElseGet` khi fallback cần truy vấn tốn chi phí?

**Đáp án:** `orElseGet`, vì supplier chỉ được gọi khi Optional rỗng.

**Câu 10.** Khi cần thông báo chính xác “không tồn tại tài khoản”, “tài khoản bị khóa” và “lỗi máy chủ”, có nên dùng chỉ `Optional.empty()` cho cả ba không?

**Đáp án:** Không nên nếu nghiệp vụ cần phân biệt. Optional chỉ mô tả có/không có giá trị, không mang nguyên nhân chi tiết.

## 16. Tài liệu API chính thức đang áp dụng

- [Oracle Java SE 25 — Optional](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html): hợp đồng `map`, `flatMap`, `filter`, `ofNullable`, `orElse`, `orElseGet`, `stream` và các trường hợp `null`.
- [Oracle Java SE 25 — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): sự khác nhau giữa `Stream.map` và `Stream.flatMap` khi làm việc với nhiều phần tử.
- [Oracle Java SE 25 — Function](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html) và [Predicate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Predicate.html): các functional interface được `Optional` sử dụng.

**Kết luận:** `Optional.map` biến đổi một giá trị nếu có; `Optional.flatMap` gọi một hàm đã trả Optional để tránh lồng nhiều lớp; `Optional.filter` kiểm tra và giữ hoặc loại bỏ giá trị đang có. Kết hợp chúng thành pipeline ngắn, dễ đọc và không dùng `get()` bừa bãi; xử lý trường hợp absent một cách rõ ràng ở ranh giới ứng dụng.