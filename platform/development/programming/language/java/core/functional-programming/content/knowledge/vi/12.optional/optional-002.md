# Optional.empty(), Optional.of() và Optional.ofNullable() trong Java

`java.util.Optional<T>` là một **đối tượng chứa (container) có thể có hoặc không có một giá trị khác `null`**. Optional giúp API diễn đạt rõ rằng kết quả có thể vắng mặt, thay vì buộc người gọi suy luận từ một giá trị trả về `null`. Ba static factory methods quan trọng nhất để tạo Optional là **`empty()`**, **`of(value)`** và **`ofNullable(value)`**.

Chọn đúng factory đặc biệt quan trọng khi dữ liệu đến từ cơ sở dữ liệu, cấu hình, map, phản hồi của API hoặc phương thức cũ có thể trả `null`. Cả ba phương thức đều có thể tạo ra `Optional<T>`, nhưng **chính sách tiếp nhận `null` hoàn toàn khác nhau**.

Sau bài học, bạn sẽ có thể:
- Tạo Optional rỗng, có giá trị và có thể rỗng từ đầu vào nullable.
- Biết chính xác thời điểm `Optional.of(null)` ném `NullPointerException`.
- Phân biệt Optional **không chứa giá trị** với Optional chứa `""`, `0`, `false` hoặc collection rỗng.
- Sử dụng generics và target typing để tạo `Optional<T>` rõ ràng.
- Chọn factory phù hợp khi thiết kế API, tránh null Optional, Optional lồng nhau và thao tác truy cập thiếu an toàn.

## 1. Optional biểu diễn điều gì?

Hãy xem hai trường hợp:

```java
Optional<String> found = Optional.of("Java");
Optional<String> missing = Optional.empty();
```

Đây là **mảnh mã minh họa** cần `import java.util.Optional;` và nằm trong một phương thức hoặc initializer phù hợp.

- `found` **có mặt** một `String` có nội dung `"Java"`.
- `missing` **không có giá trị**.
- `Optional<String>` không cho phép trạng thái “Optional có mặt nhưng phần tử bên trong là `null`”. Đối với `null`, hãy dùng `ofNullable` để tạo Optional **rỗng**.
- `Optional` là kiểu tham chiếu. Bản thân một **biến** có kiểu `Optional<T>` vẫn có thể bị gán `null` nếu bạn cố tình làm vậy; đó là trạng thái nên tránh.

Hãy hiểu Optional như một kết quả có hai nhánh: **có giá trị** hoặc **vắng mặt**. Nó không tự nêu lý do vắng mặt, không thay thế mọi mô hình lỗi và cũng không bảo đảm giá trị bên trong hợp lệ theo các quy tắc nghiệp vụ riêng.

## 2. So sánh nhanh ba factory methods

| Factory | Đầu vào | Nếu giá trị khác null | Nếu giá trị null | Dùng khi |
| --- | --- | --- | --- | --- |
| `Optional.empty()` | Không có đối số | Không áp dụng | Không áp dụng | Biết chắc kết quả vắng mặt. |
| `Optional.of(value)` | Một giá trị bắt buộc khác null | Optional **có giá trị** | **Ném `NullPointerException` ngay** | Giá trị luôn phải tồn tại theo hợp đồng. |
| `Optional.ofNullable(value)` | Một giá trị có thể null | Optional **có giá trị** | Optional **rỗng** | Dữ liệu đến từ nguồn nullable hoặc có thể vắng mặt. |

Cả ba đều là **static methods** trên class `Optional`, thường được gọi bằng `Optional.empty()`, `Optional.of(...)` và `Optional.ofNullable(...)`. Không dùng `new Optional<>()`: Optional không cung cấp public constructor để khởi tạo trực tiếp theo cách đó.

### Quy tắc ghi nhớ

- **Biết không có dữ liệu** → `empty()`.
- **Có dữ liệu và không cho phép null** → `of(value)`.
- **Không chắc dữ liệu có null hay không** → `ofNullable(value)`.

Không dùng `ofNullable` để che đi một lỗi null trái hợp đồng nếu API phải từ chối null. Khi null là lỗi lập trình cần phát hiện sớm, `of` phù hợp hơn.

## 3. Optional.empty(): tạo kết quả vắng mặt

`Optional.empty()` tạo một Optional **không chứa giá trị**. Ví dụ:

```java
Optional<String> noName = Optional.empty();
Optional<Integer> noAge = Optional.empty();

boolean missingName = noName.isEmpty();  // true
boolean hasAge = noAge.isPresent();       // false
```

Đây là mảnh mã minh họa, cần import `java.util.Optional`. `isEmpty()` có từ Java 11; JDK 17 hỗ trợ đầy đủ. `isPresent()` trả true chỉ khi có giá trị; `isEmpty()` trả true chỉ khi vắng mặt.

### Generic type của empty()

`empty()` là static generic method có dạng khái niệm:

```java
public static <T> Optional<T> empty()
```

Khi viết `Optional<String> noName = Optional.empty();`, Java dùng target type ở vế trái để suy luận `T` là `String`. Nếu cần làm rõ trong ngữ cảnh khác, có thể viết:

```java
Optional<String> none = Optional.<String>empty();
```

Dấu `<String>` ở sau tên class là **type witness**, chỉ định tham số kiểu `T` cho lời gọi generic method. Hai cách đều tạo một Optional không có giá trị, không phải giá trị `null` của `String`.

**Lưu ý identity:** Optional là một **value-based class**. Không được dùng `==`, `System.identityHashCode`, khóa đồng bộ trên Optional hoặc giả định rằng mọi lần gọi `empty()` bắt buộc trả về cùng một instance. Kiểm tra trạng thái bằng `isEmpty()` hoặc so sánh ngữ nghĩa bằng `equals` khi phù hợp.

## 4. Optional.of(value): từ chối null ngay lúc tạo

`Optional.of(value)` dùng khi giá trị **bắt buộc phải khác null**:

```java
Optional<String> language = Optional.of("Java");
Optional<Integer> quantity = Optional.of(0);
Optional<Boolean> enabled = Optional.of(false);
```

Cả `0` và `false` được autobox thành `Integer` và `Boolean` tương ứng và đều là **giá trị có mặt**. Tương tự, `Optional.of("")` chứa một chuỗi rỗng nhưng Optional vẫn **có giá trị**.

Ví dụ sai được đánh dấu rõ:

```java
// CỐ Ý GÂY NGOẠI LỆ LÚC CHẠY:
Optional<String> invalid = Optional.of(null);
// Ném NullPointerException ngay tại lời gọi of(null).
```

Lời gọi `of(null)` vẫn có thể **biên dịch** trong ngữ cảnh có kiểu hợp lệ, nhưng không tạo ra Optional rỗng: nó ném `NullPointerException`. Không có đối tượng Optional nào được trả về từ lời gọi thất bại đó.

Đây có thể là hành vi **đúng theo thiết kế** nếu dữ liệu buộc phải tồn tại: lỗi được phát hiện ngay nơi vi phạm hợp đồng thay vì lặng lẽ chuyển thành “không tìm thấy”.

## 5. Optional.ofNullable(value): chuyển null thành empty

Khi một nguồn dữ liệu có thể trả `null`, `Optional.ofNullable(value)` giúp biểu diễn hai trường hợp:

```java
String found = "Kotlin";
String absent = null;

Optional<String> a = Optional.ofNullable(found);  // có "Kotlin"
Optional<String> b = Optional.ofNullable(absent); // rỗng
```

`ofNullable` có chức năng tương đương về kết quả với logic sau, nhưng rõ ràng và ngắn gọn hơn:

```java
static <T> Optional<T> fromNullable(T value) {
    return value == null ? Optional.empty() : Optional.of(value);
}
```

Đoạn thứ hai là một method demo độc lập; trong code ứng dụng thông thường nên gọi API chuẩn `Optional.ofNullable(value)` thay vì định nghĩa lại.

Những nguồn dữ liệu thường có khả năng null:
- `Map.get(key)` nếu khóa không có trong map, hoặc có ánh xạ giá trị null trong các triển khai cho phép.
- Phương thức legacy khai báo trả `String`, `User` nhưng có thể trả null.
- Tham số tùy chọn từ lớp tương tác với thư viện cũ.
- Kết quả từ một API bên ngoài có quy ước “null nghĩa là không có dữ liệu”.

**Quan trọng:** một `Optional.empty()` được tạo từ `Map.get(key)` không phân biệt được “khóa không tồn tại” và “khóa tồn tại nhưng giá trị null”. Nếu nghiệp vụ cần phân biệt, hãy kiểm tra `containsKey` hoặc dùng một kiểu kết quả chi tiết hơn.

## 6. Chương trình Java 17: đối chiếu trực tiếp ba factory

Tạo tệp **`OptionalFactoriesDemo.java`**:

```java
import java.util.Optional;

public class OptionalFactoriesDemo {
    public static void main(String[] args) {
        Optional<String> empty = Optional.empty();
        Optional<String> strict = Optional.of("Java");
        Optional<String> nullableMissing = Optional.ofNullable(null);
        Optional<String> nullableValue = Optional.ofNullable("Kotlin");

        Optional<String> blankString = Optional.of("");
        Optional<Integer> zero = Optional.of(0);
        Optional<Boolean> disabled = Optional.of(false);

        System.out.println("empty present=" + empty.isPresent());
        System.out.println("of value=" + strict.orElse("fallback"));
        System.out.println("nullable(null) empty=" + nullableMissing.isEmpty());
        System.out.println("nullable(value)=" + nullableValue.orElse("fallback"));
        System.out.println("empty string present=" + blankString.isPresent());
        System.out.println("zero present=" + zero.isPresent());
        System.out.println("false present=" + disabled.isPresent());
        System.out.println("same empty meaning=" + empty.equals(nullableMissing));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 OptionalFactoriesDemo.java
java OptionalFactoriesDemo
```

**Stdout chính xác:**

```text
empty present=false
of value=Java
nullable(null) empty=true
nullable(value)=Kotlin
empty string present=true
zero present=true
false present=true
same empty meaning=true
```

Giải thích:
1. `empty` và `nullableMissing` đều không có giá trị dù cách tạo khác nhau.
2. `strict` và `nullableValue` chứa `String` khác null.
3. Chuỗi `""`, số `0` và boolean `false` **không đồng nghĩa với vắng mặt**.
4. `equals` so sánh ngữ nghĩa của Optional; không dùng `==` để so sánh hai Optional rỗng.

Hàm `orElse("fallback")` trong ví dụ chỉ cung cấp một giá trị mặc định nếu Optional rỗng; nó không làm thay đổi Optional ban đầu.

## 7. Chương trình Java 17: of(null) và ofNullable(null) khác nhau thế nào?

Lưu thành **`OptionalNullDemo.java`**:

```java
import java.util.Optional;

public class OptionalNullDemo {
    static Optional<String> strict(String input) {
        return Optional.of(input);
    }

    static Optional<String> tolerant(String input) {
        return Optional.ofNullable(input);
    }

    public static void main(String[] args) {
        System.out.println("of(Java) present=" + strict("Java").isPresent());
        System.out.println("ofNullable(null) empty=" + tolerant(null).isEmpty());

        try {
            strict(null);
            System.out.println("Không chạy tới đây");
        } catch (NullPointerException ex) {
            System.out.println("of(null): NullPointerException");
        }

        Optional<String> noValue = Optional.empty();
        System.out.println("empty fallback=" + noValue.orElse("anonymous"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 OptionalNullDemo.java
java OptionalNullDemo
```

**Stdout chính xác:**

```text
of(Java) present=true
ofNullable(null) empty=true
of(null): NullPointerException
empty fallback=anonymous
```

Ở `strict(null)`, `Optional.of(input)` ném lỗi trước khi phương thức trả một Optional. Chương trình bắt đúng `NullPointerException` để minh họa, nên dòng tiếp theo trong khối `try` không được in. `tolerant(null)` lại trả `Optional.empty()`, không ném lỗi.

**Đừng bắt `NullPointerException` để biến mọi lỗi thành Optional rỗng.** Ví dụ chỉ minh họa sự khác biệt giữa hai factory. Trong ứng dụng thật, nên chọn `ofNullable` khi null là khả năng hợp lệ, và `of` khi null trái hợp đồng.

## 8. Thiết kế API: trả Optional thay vì trả null

Giả sử một repository nhỏ trả `null` nếu không tìm thấy tên:

```java
static String legacyFindName(java.util.Map<String, String> names, String id) {
    return names.get(id); // có thể null
}
```

Để API mới thể hiện rõ khả năng vắng mặt:

```java
static Optional<String> findName(java.util.Map<String, String> names,
                                 String id) {
    return Optional.ofNullable(names.get(id));
}
```

Hai đoạn này là mảnh mã khai báo phương thức; cần import `java.util.Optional` hoặc ghi tên đầy đủ. Caller không cần tự kiểm tra null trước khi sử dụng container:

```java
String display = findName(names, "unknown").orElse("Ẩn danh");
```

Ví dụ `names` là một `Map<String,String>` đã có. `ofNullable` là lựa chọn thích hợp ở ranh giới với API có thể trả null; ngược lại, không nên vô điều kiện dùng `ofNullable` cho một phương thức mà `null` là lỗi nghiêm trọng cần phát hiện.

### Khi chính API biết chắc không có dữ liệu

```java
static Optional<String> lookup(boolean available) {
    if (!available) {
        return Optional.empty();
    }
    return Optional.of("Java");
}
```

Dùng `empty()` ngay khi nhánh điều kiện xác định rằng giá trị vắng mặt. Dùng `of("Java")` ở nhánh biết chắc giá trị phải tồn tại. Không cần tạo biến null trung gian chỉ để gọi `ofNullable`.

## 9. Ví dụ Java 17: dùng Optional với Map và thao tác tiếp theo

Tạo tệp **`OptionalLookupDemo.java`**:

```java
import java.util.Map;
import java.util.Optional;

public class OptionalLookupDemo {
    static Optional<String> findName(Map<String, String> names, String id) {
        return Optional.ofNullable(names.get(id));
    }

    public static void main(String[] args) {
        Map<String, String> names = Map.of(
                "u1", "Lan",
                "u2", "Mai"
        );

        Optional<String> found = findName(names, "u1");
        Optional<String> missing = findName(names, "u9");

        System.out.println("found=" + found.orElse("Ẩn danh"));
        System.out.println("missing=" + missing.orElse("Ẩn danh"));
        System.out.println("found present=" + found.isPresent());
        System.out.println("missing empty=" + missing.isEmpty());

        String upper = found.map(String::toUpperCase)
                .orElse("UNKNOWN");
        System.out.println("upper=" + upper);
    }
}
```

Biên dịch/chạy với JDK 17:

```bash
javac -encoding UTF-8 OptionalLookupDemo.java
java OptionalLookupDemo
```

**Stdout chính xác:**

```text
found=Lan
missing=Ẩn danh
found present=true
missing empty=true
upper=LAN
```

`findName` bọc kết quả `Map.get` bằng `ofNullable`. Khi khóa có giá trị, Optional có mặt; khi thiếu khóa, Optional rỗng. `map(String::toUpperCase)` chỉ thực hiện chuyển đổi khi có giá trị bên trong; nếu rỗng, kết quả vẫn rỗng. `orElse` ở cuối nhận giá trị mặc định.

`Map.of` tạo map không cho phép khóa hoặc giá trị null. Ví dụ này dùng đầu vào hợp lệ và một khóa thiếu để minh họa; với các triển khai Map khác có thể lưu giá trị null, `findName` sẽ gộp cả “không có khóa” lẫn “giá trị null” thành Optional rỗng.

## 10. Đọc kết quả Optional một cách an toàn

Sau khi tạo Optional, người gọi thường muốn tiếp tục xử lý giá trị hoặc dùng mặc định. Một số API quan trọng:

| API | Khi có giá trị | Khi rỗng |
| --- | --- | --- |
| `isPresent()` | `true` | `false` |
| `isEmpty()` | `false` | `true` |
| `ifPresent(consumer)` | Thực thi hành động | Không làm gì |
| `map(function)` | Chuyển đổi giá trị, bọc kết quả nullable thành Optional | Vẫn rỗng |
| `filter(predicate)` | Giữ giá trị nếu điều kiện đúng | Vẫn rỗng |
| `orElse(value)` | Trả giá trị hiện có | Trả fallback |
| `orElseGet(supplier)` | Trả giá trị hiện có | Gọi supplier để tạo fallback |
| `orElseThrow()` | Trả giá trị hiện có | Ném `NoSuchElementException` |

Có thể gọi `get()` trên Optional có giá trị, nhưng gọi `get()` khi rỗng sẽ ném `NoSuchElementException`. Trong hầu hết logic ứng dụng, nên cân nhắc `orElse`, `orElseGet`, `ifPresent`, `map`, `flatMap` hoặc `orElseThrow` với điều kiện và thông báo phù hợp, thay vì lặp mẫu `isPresent()` rồi `get()` không cần thiết.

Đừng xem một Optional rỗng là một exception. **`empty()` và `ofNullable(null)` không ném exception**; exception chỉ xuất hiện nếu bạn thực hiện thao tác không được phép như `get()` trên Optional rỗng hoặc dùng `of(null)`.

### Khác nhau giữa orElse và orElseGet

Nếu fallback tốn kém hoặc có side effect, `orElseGet` hữu ích vì chỉ gọi supplier khi Optional rỗng. Ngược lại, **biểu thức đối số của `orElse` được tính ngay theo quy tắc Java**, kể cả Optional đang có giá trị.

Ví dụ:

```java
static String createFallback() {
    System.out.println("Tạo fallback");
    return "ẩn danh";
}

// Bên trong phương thức:
Optional<String> present = Optional.of("Lan");
String a = present.orElse(createFallback()); // vẫn in "Tạo fallback"
String b = present.orElseGet(() -> createFallback()); // không in
```

Đây là các mảnh mã minh họa, không phải một tệp Java đầy đủ. Trong khi lựa chọn factory của Optional quyết định trạng thái có/rỗng, lựa chọn `orElse` hoặc `orElseGet` quyết định **cách tính fallback**.

## 11. Những điểm dễ nhầm về generic, null và empty

### 11.1. Optional.empty() không phải null

```java
Optional<String> empty = Optional.empty();
Optional<String> invalid = null; // không khuyến khích
```

Dòng thứ hai hợp lệ về kiểu Java, nhưng làm mất ý nghĩa của API trả Optional: caller có thể gặp `NullPointerException` ngay khi gọi `invalid.isEmpty()`. Một phương thức khai báo trả `Optional<T>` nên trả một đối tượng Optional **không null**, dùng `Optional.empty()` nếu không có dữ liệu.

### 11.2. Optional.of("") khác Optional.empty()

```java
Optional<String> blank = Optional.of("");
Optional<String> missing = Optional.empty();

boolean a = blank.isPresent();  // true
boolean b = missing.isPresent(); // false
```

Chuỗi rỗng `""` vẫn là một `String` khác null. Tương tự, `Optional.ofNullable("")` vẫn **có giá trị**. Nếu nghiệp vụ coi chuỗi rỗng hoặc chuỗi toàn khoảng trắng là “không có dữ liệu”, cần **chuẩn hóa hoặc lọc riêng**, ví dụ:

```java
Optional<String> normalized = Optional.ofNullable(input)
        .map(String::strip)
        .filter(value -> !value.isEmpty());
```

Đây là mảnh mã minh họa có biến `input` kiểu `String` từ ngữ cảnh. Với null, kết quả rỗng; với `"   "`, sau `strip()` và `filter` cũng rỗng; với `" Java "`, kết quả chứa `"Java"`.

### 11.3. Optional.ofNullable(Optional<T>) tạo Optional lồng nhau

Ví dụ:

```java
Optional<String> inner = Optional.of("Java");
Optional<Optional<String>> nested = Optional.ofNullable(inner);
```

`nested` là `Optional<Optional<String>>`, không phải `Optional<String>`. `ofNullable` bọc **chính đối tượng được truyền vào** khi đối tượng đó khác null; nó không tự “làm phẳng” Optional. Nếu một phép biến đổi đã trả Optional, cân nhắc `flatMap` thay vì `map` trong pipeline phù hợp.

### 11.4. Optional<Integer> và OptionalInt

`Optional<T>` dùng generic reference type, nên `Optional<Integer>` bọc `Integer`:

```java
Optional<Integer> number = Optional.of(7);
java.util.OptionalInt primitive = java.util.OptionalInt.of(7);
java.util.OptionalInt noPrimitive = java.util.OptionalInt.empty();
```

`OptionalInt`, `OptionalLong`, `OptionalDouble` là các dạng chuyên biệt cho primitive. Chúng có `of` và `empty`, nhưng **không có static `ofNullable` tương ứng**. Nếu nguồn ban đầu là `Integer` nullable và bạn muốn `OptionalInt`, phải chuyển đổi có điều kiện.

## 12. Chọn factory theo hợp đồng API, không chỉ theo cú pháp

| Tình huống | Chọn | Giải thích |
| --- | --- | --- |
| Không tìm thấy kết quả | `Optional.empty()` | Trạng thái vắng mặt đã được xác định. |
| Giá trị hard-coded chắc chắn khác null | `Optional.of("Java")` | Nếu giá trị null sẽ là lỗi hợp đồng. |
| `Map.get(key)` có thể null | `Optional.ofNullable(map.get(key))` | Biến null thành vắng mặt. |
| Phương thức legacy nullable | `Optional.ofNullable(legacy())` | Thể hiện hợp đồng trả kết quả có thể thiếu. |
| Giá trị bắt buộc có, null là lỗi | `Optional.of(required)` | Fail-fast tại điểm tạo Optional. |
| Chuỗi `""` là giá trị hợp lệ | `Optional.of("")` hoặc `ofNullable("")` | Optional vẫn có giá trị. |
| Chuỗi trắng bị coi là không có dữ liệu | `ofNullable(...).map(...).filter(...)` | Cần quy tắc nghiệp vụ ngoài kiểm tra null. |

Một số nguyên tắc thiết kế:
- Trong API Java, Optional thường phù hợp làm **kiểu trả về** khi một phương thức có thể không tìm thấy kết quả. Không nhất thiết thay mọi tham số hoặc field bằng Optional.
- Optional không phải cơ chế lưu trữ, đồng bộ hay cache. Nó là cách diễn đạt khả năng vắng mặt ở cấp API.
- Nếu cần phân biệt nhiều lý do thất bại, dùng kết quả dạng enum/record hoặc kiểu kết quả chi tiết hơn; một Optional rỗng không chứa thông tin nguyên nhân.
- Không cần gọi `Optional.ofNullable` trong mọi tình huống chỉ để “cho chắc”: null vi phạm hợp đồng nên được phát hiện rõ ràng thay vì bị che giấu.

## 13. Lỗi thường gặp

1. **Dùng `Optional.of(null)` để tạo Optional rỗng:** sai, phương thức ném `NullPointerException`.
2. **Trả `null` từ phương thức có kiểu `Optional<T>`:** làm caller mất cơ chế xử lý nhất quán.
3. **Nhầm `Optional.empty()` với `Optional.of("")`:** có giá trị chuỗi rỗng không đồng nghĩa không có giá trị.
4. **Dùng `==` để so sánh hai Optional:** Optional là value-based class; dùng `equals` hoặc kiểm tra trạng thái.
5. **Gọi `get()` khi chưa chắc có giá trị:** Optional rỗng gây `NoSuchElementException`.
6. **Dùng `ofNullable` che lỗi null trái hợp đồng:** có thể làm bug nghiêm trọng trở thành “không tìm thấy”.
7. **Cho rằng `ofNullable(value)` kiểm tra chuỗi trống:** nó chỉ kiểm tra **null**, không kiểm tra `""` hay whitespace.
8. **Đưa Optional vào Optional:** `Optional.of(innerOptional)` tạo `Optional<Optional<T>>`.
9. **Dùng `Optional<Integer>` như một primitive:** nó vẫn dùng `Integer` wrapper; cân nhắc `OptionalInt` khi phù hợp.
10. **Nhầm `orElse` với `orElseGet`:** đối số `orElse` được đánh giá trước khi gọi, còn supplier của `orElseGet` chỉ chạy khi rỗng.
11. **Cho rằng Optional chứa null bên trong:** các factory chuẩn chỉ tạo Optional có **giá trị khác null** hoặc Optional rỗng.
12. **Bọc dữ liệu nullable mà không mô tả ngữ nghĩa:** người dùng API cần biết null là “không tìm thấy”, “chưa tải” hay lỗi cần xử lý.

## 14. Tự kiểm tra

**Câu 1.** Chọn factory để tạo một Optional chắc chắn không chứa giá trị.

**Đáp án:** `Optional.empty()`.

**Câu 2.** `Optional.of(null)` cho kết quả gì?

**Đáp án:** Ném `NullPointerException` ngay lúc thực thi lời gọi; không trả `Optional.empty()`.

**Câu 3.** `Optional.ofNullable(null).isEmpty()` trả gì?

**Đáp án:** `true`, vì null được chuyển thành Optional rỗng.

**Câu 4.** `Optional.of("").isPresent()` và `Optional.of(0).isPresent()` trả gì?

**Đáp án:** Cả hai đều `true`. Chuỗi rỗng và số 0 không phải null.

**Câu 5.** Phương thức `String find(String key)` có thể trả null. Nếu muốn caller nhìn thấy khả năng vắng mặt qua kiểu trả về, nên viết thế nào?

```java
static Optional<String> findOptional(String key) {
    return Optional.ofNullable(find(key));
}
```

Đây là mảnh mã trong class có sẵn phương thức `find(String)`. Chọn `ofNullable` vì null là một kết quả có thể xảy ra.

**Câu 6.** Khi nào nên dùng `of` thay vì `ofNullable`?

**Đáp án:** Khi `null` phải được xem là vi phạm hợp đồng dữ liệu và cần **fail-fast** bằng `NullPointerException`.

**Câu 7.** Có nên viết `optional == Optional.empty()` để kiểm tra vắng mặt?

**Không.** Dùng `optional.isEmpty()` (Java 11+) hoặc `!optional.isPresent()`.

**Câu 8.** `Optional.ofNullable("  ").isEmpty()` trả gì?

**Đáp án:** `false`, vì `"  "` là chuỗi khác null. Muốn xem khoảng trắng là không có dữ liệu, cần quy tắc `strip`/`filter` riêng.

**Ghi nhớ:** **`empty()` = cố ý không có giá trị; `of(x)` = bắt buộc có giá trị, null gây lỗi; `ofNullable(x)` = có nếu x khác null, rỗng nếu x null.** Chọn factory theo hợp đồng dữ liệu thay vì chọn theo thói quen.
