# Tránh `Optional.get()` không kiểm tra và hiểu đúng `null` trong Java

## 1. Vấn đề: có thể không có giá trị

Trong Java, một phương thức tìm dữ liệu đôi khi không có kết quả. Trước đây, nhiều API trả về `null` để biểu thị “không tìm thấy”:

```java
User user = findUser("missing");  // Có thể trả null.
System.out.println(user.name()); // NullPointerException nếu user == null.
```

`User` và `findUser` ở đây chỉ là tên minh họa, chưa phải chương trình độc lập. `java.util.Optional<T>` biểu diễn rõ hơn **một kết quả có thể hiện diện hoặc vắng mặt**. Một `Optional<T>` có hai trạng thái về mặt hợp đồng:

- **Có giá trị:** `Optional.of(value)` với `value != null`.
- **Rỗng:** `Optional.empty()`, hoặc `Optional.ofNullable(null)`.

Điểm mấu chốt: **`Optional` không chứa một “giá trị `null`” như trường hợp có giá trị thứ ba.** Nếu dữ liệu cung cấp là `null`, dùng `ofNullable` sẽ tạo `Optional.empty()`. Nhưng một **biến tham chiếu kiểu `Optional<T>`** vẫn có thể bị gán `null` nếu code khác vi phạm hợp đồng; khi đó gọi `isPresent()`, `map()` hay `orElse()` trên tham chiếu ấy vẫn gây `NullPointerException`.

Một lỗi khác là gọi `optional.get()` mà không chắc chắn có giá trị. `get()` sẽ ném `NoSuchElementException` nếu `Optional` rỗng. Bài này hướng tới cách lập trình an toàn, dễ đọc và biểu đạt đúng ngữ nghĩa thiếu dữ liệu.

## 2. Cách khởi tạo: `of`, `ofNullable`, `empty`

| Cách tạo | Đầu vào | Kết quả |
| --- | --- | --- |
| `Optional.of("Java")` | Khác `null` | `Optional` chứa `"Java"` |
| `Optional.of(null)` | `null` | Ném `NullPointerException` ngay khi tạo |
| `Optional.ofNullable("Java")` | Khác `null` | `Optional` chứa `"Java"` |
| `Optional.ofNullable(null)` | `null` | `Optional.empty()` |
| `Optional.empty()` | Không có đầu vào | `Optional` rỗng |

Ví dụ:

```java
import java.util.Optional;

Optional<String> known = Optional.of("Java");
Optional<String> missing = Optional.ofNullable(null);
Optional<String> alsoMissing = Optional.empty();

System.out.println(known.isPresent());   // true
System.out.println(missing.isEmpty());    // true
System.out.println(alsoMissing.isEmpty()); // true
```

Đây là đoạn đặt trong một phương thức hoặc `jshell`. `isEmpty()` có từ Java 11, vì vậy chương trình Java 17+ có thể dùng bình thường.

**Chọn `of` khi giá trị theo hợp đồng bắt buộc khác `null`.** Nếu nhận `null` là bug, `Optional.of(value)` giúp phát hiện lỗi sớm. **Chọn `ofNullable` khi nguồn dữ liệu được phép trả `null`**, ví dụ API cũ, trường tùy chọn từ DTO hoặc phản hồi bên ngoài. Đừng dùng `ofNullable` vô điều kiện để che lỗi dữ liệu bắt buộc.

### Phân biệt ba tình huống rất dễ nhầm

```java
Optional<String> a = Optional.empty();            // Đúng: một Optional rỗng.
Optional<String> b = Optional.ofNullable(null);   // Đúng: cũng rỗng.
Optional<String> c = null;                        // Sai về thiết kế API.
```

`a` và `b` là **đối tượng Optional** hợp lệ, có thể gọi `isEmpty()`. `c` không phải đối tượng Optional; `c.isEmpty()` ném `NullPointerException`. Do đó, phương thức khai báo trả `Optional<T>` nên trả **`Optional.empty()`**, không trả `null`:

```java
// NÊN:
Optional<String> findCode(boolean found) {
    return found ? Optional.of("A01") : Optional.empty();
}

// KHÔNG NÊN:
Optional<String> brokenFindCode(boolean found) {
    return found ? Optional.of("A01") : null;
}
```

Hai đoạn là phương thức minh họa; cần đặt bên trong một lớp và import `Optional`. Một caller tin rằng `Optional` luôn khác `null` sẽ thất bại với `brokenFindCode(false)`.

## 3. Vì sao `get()` không kiểm tra nguy hiểm?

`Optional.get()` có hợp đồng: **trả giá trị nếu hiện diện; nếu rỗng, ném `NoSuchElementException`**.

```java
Optional<String> maybeName = Optional.empty();
// String name = maybeName.get(); // NoSuchElementException.
```

Compiler **không cảnh báo lỗi** cho lời gọi trên, vì `get()` tồn tại trong API và `NoSuchElementException` là unchecked exception. Lỗi chỉ phát sinh khi thực thi với dữ liệu rỗng.

Cách kiểm tra thủ công sau hợp lệ:

```java
Optional<String> maybeName = Optional.of("Lan");
if (maybeName.isPresent()) {
    System.out.println(maybeName.get());
}
```

Nhưng cách này thường không phải lựa chọn dễ đọc nhất. Khi mỗi đoạn code phải nhớ gọi `isPresent()` trước `get()`, rất dễ bỏ sót đường rẽ nhánh hoặc thay đổi code làm mất tính an toàn. Đa số trường hợp nên thể hiện trực tiếp mục đích bằng các phép xử lý của Optional: `map`, `flatMap`, `filter`, `ifPresent`, `ifPresentOrElse`, `orElse`, `orElseGet` hoặc `orElseThrow`.

> `get()` không bị cấm tuyệt đối. Nếu **đã có một bất biến được xác minh** rằng Optional chắc chắn có giá trị, `get()` có thể hợp lệ về chức năng. Tuy nhiên `orElseThrow()` (không tham số, Java 10+) biểu đạt rõ ý định “phải có giá trị, nếu không thì lỗi” và thường là lựa chọn dễ hiểu hơn.

## 4. Chọn API truy cập theo đúng nghiệp vụ

| Nhu cầu | Cách dùng | Điều xảy ra nếu rỗng |
| --- | --- | --- |
| Có giá trị thì chạy hành động | `ifPresent(value -> ...)` | Không chạy hành động |
| Có giá trị làm A, rỗng làm B | `ifPresentOrElse(action, emptyAction)` | Chạy `emptyAction` |
| Lấy giá trị hoặc một hằng số | `orElse("UNKNOWN")` | Trả `"UNKNOWN"` |
| Chỉ tính giá trị dự phòng khi rỗng | `orElseGet(() -> computeFallback())` | Gọi supplier rồi trả kết quả |
| Bắt buộc phải có giá trị | `orElseThrow()` | Ném `NoSuchElementException` |
| Thiếu dữ liệu phải ném lỗi nghiệp vụ | `orElseThrow(() -> new IllegalArgumentException(...))` | Ném exception do supplier tạo |
| Biến đổi nếu có giá trị | `map(Function)` | Giữ `Optional.empty()` |
| Biến đổi bằng hàm đã trả Optional | `flatMap(Function)` | Giữ `Optional.empty()` |
| Chỉ giữ giá trị thỏa điều kiện | `filter(Predicate)` | Giữ trạng thái rỗng |
| Chọn một Optional thay thế | `or(() -> alternateOptional())` | Dùng Optional từ supplier |
| Chuyển thành stream 0 hoặc 1 phần tử | `stream()` | Stream rỗng |

Ví dụ:

```java
Optional<String> maybe = Optional.ofNullable(null);

String display = maybe.orElse("N/A"); // "N/A"
String lazy = maybe.orElseGet(() -> "N/A"); // "N/A"

maybe.ifPresent(System.out::println); // Không in gì.
maybe.ifPresentOrElse(
        System.out::println,
        () -> System.out.println("No value")
); // In "No value".
```

Đây là đoạn minh họa trong một phương thức. Cả `orElse` và `orElseGet` đều cung cấp phương án thay thế; khác biệt là **thời điểm tính fallback**, phân tích ở phần sau. `orElseThrow` phù hợp khi sự vắng mặt là lỗi cần xử lý rõ ràng, còn `ifPresent` phù hợp với hành động tùy chọn.

### `orElseThrow` báo lỗi đúng ngữ cảnh

```java
String email = findEmail(userId)
        .orElseThrow(() ->
                new IllegalArgumentException("Email not found: " + userId));
```

`findEmail` và `userId` trong đoạn này là các biến/phương thức minh họa. Cách viết nói rõ **sự vắng mặt không được chấp nhận** đối với yêu cầu này; nó không lặng lẽ dùng `null` hay chuỗi trống làm email giả.

Nếu `findEmail` có thể trả một tham chiếu `Optional` bằng `null` (vi phạm hợp đồng), `orElseThrow` vẫn có thể gây `NullPointerException`. Hãy sửa nguồn trả `Optional` trước thay vì chồng các phép gọi `Optional.ofNullable(optional)` ở khắp nơi.

## 5. Ví dụ Java 17 hoàn chỉnh và stdout xác định

Bài toán: giả lập tìm người dùng; có người có email, có người có hồ sơ nhưng email bằng `null`, có ID không tồn tại. Chương trình biểu diễn Optional đúng, xử lý null ở ranh giới và đối chiếu các phương thức truy cập.

Tạo tệp **`OptionalSafetyDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class OptionalSafetyDemo {
    record User(String id, String email) {}

    static Optional<User> findUser(String id) {
        return switch (id) {
            case "u1" -> Optional.of(
                    new User("u1", "  Lan@Example.com  "));
            case "u2" -> Optional.of(new User("u2", null));
            default -> Optional.empty();
        };
    }

    static Optional<String> normalizedEmail(User user) {
        return Optional.ofNullable(user.email())
                .map(String::trim)
                .filter(value -> !value.isEmpty())
                .map(value -> value.toLowerCase(Locale.ROOT));
    }

    static String expensiveFallback() {
        System.out.println("Fallback computed");
        return "fallback";
    }

    public static void main(String[] args) {
        System.out.println("Known: "
                + findUser("u1").map(User::id).orElse("missing"));

        System.out.println("Email u1: "
                + findUser("u1")
                    .flatMap(OptionalSafetyDemo::normalizedEmail)
                    .orElse("none"));

        System.out.println("Email u2: "
                + findUser("u2")
                    .flatMap(OptionalSafetyDemo::normalizedEmail)
                    .orElse("none"));

        System.out.println("Email u3: "
                + findUser("u3")
                    .flatMap(OptionalSafetyDemo::normalizedEmail)
                    .orElse("none"));

        String raw = null;
        System.out.println("ofNullable(null) empty: "
                + Optional.ofNullable(raw).isEmpty());

        try {
            Optional.of(raw);
        } catch (NullPointerException ex) {
            System.out.println("of(null): NullPointerException");
        }

        try {
            Optional.<String>empty().get();
        } catch (NoSuchElementException ex) {
            System.out.println("empty.get(): NoSuchElementException");
        }

        try {
            Optional.<String>empty().orElseThrow(
                    () -> new IllegalStateException("not found"));
        } catch (IllegalStateException ex) {
            System.out.println("orElseThrow: " + ex.getMessage());
        }

        findUser("u1").ifPresentOrElse(
                user -> System.out.println("Found: " + user.id()),
                () -> System.out.println("No user"));
        findUser("unknown").ifPresentOrElse(
                user -> System.out.println("Found: " + user.id()),
                () -> System.out.println("No user"));

        System.out.println("map null -> empty: "
                + Optional.of("x")
                    .map(value -> (String) null)
                    .isEmpty());

        try {
            Optional.of("x")
                    .flatMap(value -> (Optional<String>) null);
        } catch (NullPointerException ex) {
            System.out.println("flatMap null: NullPointerException");
        }

        String eager = Optional.of("READY")
                .orElse(expensiveFallback());
        String lazy = Optional.of("READY")
                .orElseGet(OptionalSafetyDemo::expensiveFallback);
        System.out.println("Eager: " + eager + ", lazy: " + lazy);

        List<String> ids = Stream.of("u1", "u2", "u3")
                .map(OptionalSafetyDemo::findUser)
                .flatMap(Optional::stream)
                .map(User::id)
                .toList();
        System.out.println("Found IDs: " + ids);

        OptionalInt zero = OptionalInt.of(0);
        System.out.println("OptionalInt zero present: "
                + zero.isPresent());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 OptionalSafetyDemo.java
java OptionalSafetyDemo
```

**Stdout chính xác:**

```text
Known: u1
Email u1: lan@example.com
Email u2: none
Email u3: none
ofNullable(null) empty: true
of(null): NullPointerException
empty.get(): NoSuchElementException
orElseThrow: not found
Found: u1
No user
map null -> empty: true
flatMap null: NullPointerException
Fallback computed
Eager: READY, lazy: READY
Found IDs: [u1, u2]
OptionalInt zero present: true
```

Đối chiếu:

1. `findUser("u1")` trả Optional chứa User; `map(User::id)` cho `"u1"`.
2. `normalizedEmail` lấy email qua `ofNullable`, bỏ khoảng trắng và chuyển về chữ thường bằng `Locale.ROOT`, nên `"  Lan@Example.com  "` thành `"lan@example.com"`.
3. `u2` có User nhưng email là `null`. `Optional.ofNullable(user.email())` tạo Optional rỗng; `flatMap` ghép với Optional của User thành Optional email rỗng; `orElse("none")` trả `"none"`. `u3` thì không có User, cũng ra `"none"`. **Hai tình huống khác nhau có thể cùng kết quả hiển thị**, nên nếu nghiệp vụ cần phân biệt “không có user” và “user không có email”, phải giữ thêm trạng thái lỗi hoặc kiểm tra theo từng tầng.
4. `Optional.of(raw)` với `raw == null` ném `NullPointerException` ngay khi tạo. `Optional.empty().get()` ném `NoSuchElementException`, được bắt và in tên lỗi.
5. `map(value -> (String) null)` biến Optional có giá trị thành Optional rỗng. `flatMap` không chấp nhận mapper trả **tham chiếu Optional bằng `null`**, nên ném `NullPointerException`.
6. `orElse(expensiveFallback())` đánh giá tham số trước khi gọi `orElse`, nên in `Fallback computed` dù Optional đã có `"READY"`. `orElseGet` chỉ gọi supplier khi Optional rỗng, nên không in dòng thứ hai.
7. `Optional.stream()` trả stream 1 phần tử nếu có giá trị, hoặc stream rỗng nếu vắng mặt. Vì thế trong danh sách `u1,u2,u3`, chỉ có hai User đầu tiên được đưa vào `ids` theo encounter order.
8. `OptionalInt.of(0)` **có giá trị** là số 0, vì 0 không phải ký hiệu vắng mặt; `isPresent()` là `true`.

> Ví dụ cố ý có `User.email() == null` để thể hiện cách chuyển dữ liệu legacy sang `Optional` tại ranh giới đọc. Không nên dùng `null` cho các thuộc tính bắt buộc và mặc định xem mọi lỗi dữ liệu là thiếu thông tin hợp lệ.

## 6. `map` và `flatMap` xử lý `null` khác nhau

### `Optional.map`: đầu ra mapper bằng `null` trở thành rỗng

`Optional.map` biến đổi giá trị đang có bằng một `Function<T,U>`. Nếu Optional đầu vào rỗng, mapper không được gọi. Nếu mapper trả `null`, kết quả `map` là `Optional.empty()` theo hợp đồng giống `ofNullable` đối với kết quả mapper.

```java
Optional<String> code = Optional.of("A01");
Optional<Integer> length = code.map(String::length); // Có 3.

Optional<String> absent = code.map(value -> null);
System.out.println(absent.isEmpty()); // true
```

Ví dụ này đặt trong phương thức có import `Optional`. Dùng `map` rất tiện khi nối chuỗi các phép biến đổi có thể nhận/cho giá trị nullable:

```java
Optional<String> city = Optional.ofNullable(customer)
        .map(Customer::getAddress)
        .map(Address::getCity)
        .filter(s -> !s.isBlank());
```

`Customer`, `Address` và `customer` là kiểu/biến minh họa trong ứng dụng; đoạn này không phải chương trình độc lập. Nếu `customer` hoặc `address` hoặc `city` là null, kết quả dừng ở trạng thái rỗng theo contract của `map`. Tuy nhiên, nó **không xử lý ngoại lệ khác** từ getter hoặc `filter`; chúng vẫn truyền ra bình thường.

### `Optional.flatMap`: mapper phải trả một Optional thật

Khi hàm biến đổi đã trả `Optional<U>`, hãy dùng `flatMap`:

```java
Optional<User> user = findUser("u1");

Optional<String> email =
        user.flatMap(OptionalSafetyDemo::normalizedEmail);
```

Vì `normalizedEmail` trả `Optional<String>`, `flatMap` tránh kiểu lồng `Optional<Optional<String>>`. Nhưng mapper phải trả một **đối tượng Optional không null**:

```java
// SAI: mapper tự trả tham chiếu Optional bằng null.
Optional<String> broken = Optional.of("x")
        .flatMap(value -> (Optional<String>) null);
```

Đoạn này **biên dịch được nhưng ném `NullPointerException` khi thực thi**. Tránh bằng cách tuân thủ hợp đồng: trả `Optional.empty()` khi vắng mặt, không trả `null`. `Optional.or(Supplier<Optional<T>>)` cũng yêu cầu supplier cung cấp một Optional hợp lệ (không null).

### `filter` chỉ giữ hoặc bỏ giá trị

```java
Optional<String> valid =
        Optional.of("  ")
                .map(String::trim)
                .filter(s -> !s.isEmpty());

System.out.println(valid.isEmpty()); // true
```

`filter` gọi `Predicate` chỉ khi có giá trị. Nếu predicate trả `false`, Optional rỗng; nếu trả `true`, giữ nguyên giá trị. `filter` không biến `null` thành giá trị mới hay tự tạo thông báo lỗi.

## 7. Vì sao `orElse` đôi khi gây tác dụng phụ ngoài mong muốn?

Hai đoạn sau có thể **trả cùng kết quả nhưng thực hiện khác nhau**:

```java
String a = Optional.of("READY").orElse(expensiveFallback());
String b = Optional.of("READY").orElseGet(
        OptionalSafetyDemo::expensiveFallback);
```

Giả định `expensiveFallback()` như trong chương trình hoàn chỉnh. Ở dòng `a`, Java **đánh giá đối số** `expensiveFallback()` trước khi gọi `orElse`; kết quả tính toán bị bỏ vì Optional đã có giá trị. Ở dòng `b`, `orElseGet` nhận một `Supplier<String>`, chỉ chạy supplier nếu Optional rỗng.

Nếu fallback phải gọi API, query database, đọc file, khởi tạo đối tượng lớn hoặc ghi log, sử dụng `orElseGet` để tránh chi phí/tác dụng phụ khi đã có kết quả.

```java
String cached = maybeCode.orElseGet(() -> loadDefaultCode());
```

Đây là đoạn minh họa với `maybeCode` và `loadDefaultCode` được khai báo bên ngoài. **Không được mặc định supplier sẽ thành công**: nếu fallback ném exception hoặc trả `null`, hành vi tương ứng vẫn ảnh hưởng tới caller. `orElse(null)` là hợp lệ về mặt API và có thể trả `null` **ra ngoài Optional**; nếu muốn đầu ra không null, hãy chọn fallback và hợp đồng rõ ràng.

## 8. `orElseThrow`: khi thiếu dữ liệu là lỗi nghiệp vụ

Có những yêu cầu không thể tiếp tục nếu dữ liệu vắng mặt, ví dụ xử lý thanh toán cần tìm được đơn hàng. Khi đó không nên chọn fallback giả như `"UNKNOWN"`. Dùng:

```java
Order order = findOrder(id).orElseThrow(
        () -> new IllegalArgumentException("Order not found: " + id));
```

`Order`, `findOrder` và `id` là các tên miền nghiệp vụ minh họa. Lời gọi sẽ trả `Order` khi có, hoặc ném đúng exception đã chỉ định khi rỗng. Nếu chọn `orElseThrow()` không tham số, exception mặc định là `NoSuchElementException`.

Trong code nghiệp vụ, kiểu exception và message nên phù hợp cách tầng ngoài xử lý lỗi: API REST có thể cần chuyển “không tìm thấy” thành HTTP 404, nhưng bản thân `Optional` không tự quyết định HTTP status. Không chuyển mọi trường hợp thiếu dữ liệu thành `NullPointerException` hay `NoSuchElementException` khi domain cần thông tin khác.

### `ifPresentOrElse` để thực hiện hành động ở cả hai nhánh

```java
findUser("u1").ifPresentOrElse(
        user -> System.out.println(user.id()),
        () -> System.out.println("No user"));
```

`ifPresentOrElse` không trả một giá trị để gán. Nếu bạn **cần tính ra một giá trị** dùng tiếp, chọn `map`/`orElseGet`/`orElseThrow`; tránh dùng một biến mutable ở ngoài lambda làm nơi chứa kết quả.

## 9. Không dùng `Optional` để giấu lỗi dữ liệu

Trạng thái **không tìm thấy** khác trạng thái **truy vấn thất bại**:

- Không có User với ID đã cho: `Optional.empty()` có thể đúng.
- Database timeout hoặc lỗi network: không nên trả `Optional.empty()` và giả vờ “không có User”.
- Có User nhưng email trống: có thể trả `Optional.empty()` cho email nếu email được phép thiếu; cần phân biệt với lỗi nhập dữ liệu nếu email là trường bắt buộc.
- Nội dung đầu vào sai định dạng: nên xác thực và báo lỗi theo chính sách, không tự chuyển mọi lỗi thành Optional rỗng.

`Optional` diễn đạt **có hoặc không có giá trị**, không tự mang nguyên nhân thất bại. Nếu cần trả nhiều trạng thái (thành công, không tìm thấy, bị từ chối, tạm thời lỗi), có thể dùng sealed interface/record Result, exception hoặc kiểu trả về khác rõ ràng hơn.

Ví dụ:

```java
sealed interface LookupResult
        permits Found, NotFound, Failed {}

record Found(User value) implements LookupResult {}
record NotFound() implements LookupResult {}
record Failed(String message) implements LookupResult {}
```

Đây là ví dụ về **khai báo kiểu** cho ứng dụng Java 17 (cần có `User` được khai báo phù hợp). Những kiểu này giúp caller phân biệt “không có” với “không truy cập được nguồn”, trong khi một `Optional.empty()` duy nhất không cung cấp được.

## 10. `Optional` không nên là một tham chiếu `null`

Một phương thức có chữ ký:

```java
Optional<User> findUserById(String id)
```

thường có **hợp đồng ngầm** rằng kết quả gọi **không bao giờ là tham chiếu `null`**. Nếu không có User, trả `Optional.empty()`. Khi client gọi `findUserById(id).map(...)`, nó có thể tin rằng đối tượng Optional tồn tại. Trả `null` từ phương thức như vậy xóa bỏ lợi ích chính của Optional.

Đặc biệt nguy hiểm với:

```java
// Đây là API broken, không phải cách thực hành.
Optional<String> broken() {
    return null;
}

// broken().orElse("fallback") vẫn ném NullPointerException.
```

Để tích hợp với API cũ có thể trả null, **chuyển đổi ngay tại ranh giới**:

```java
String legacyValue = legacyService.getCode(); // Có thể null.
Optional<String> safe = Optional.ofNullable(legacyValue);
```

Nếu chính API cũ trả `Optional<String>` nhưng đôi khi trả `null`, hãy **sửa API cũ** để luôn trả một Optional hợp lệ. Khi chưa sửa được, có thể dùng tạm:

```java
Optional<String> normalized =
        Optional.ofNullable(legacyOptional)
                .orElseGet(Optional::empty);
```

`legacyOptional` là biến có kiểu `Optional<String>` có thể đang bằng null; đây là giải pháp tương thích tại **một ranh giới**, không phải lý do để thiết kế hàm trả null Optional trong code mới.

## 11. Nên đặt `Optional` ở đâu trong API?

Theo cách dùng phổ biến của JDK, `Optional<T>` phù hợp nhất là **kiểu trả về** khi có lý do rõ ràng để một phương thức không trả kết quả. Một số hướng dẫn thực tế:

| Vị trí | Gợi ý |
| --- | --- |
| Return type của `findById` / `lookup` | Thường phù hợp nếu “không tìm thấy” là kết quả bình thường |
| Biến cục bộ để xử lý nhiều bước | Hợp lý khi dùng `map`, `flatMap`, `orElse...` |
| Tham số phương thức | Thường không cần thiết; xem xét overload hoặc contract rõ hơn |
| Field của entity/DTO | Thường ưu tiên mô hình dữ liệu/validation phù hợp, tránh gây khó tương thích serializer/ORM |
| Collection chứa `Optional<T>` | Chỉ khi cần phân biệt trạng thái từng phần tử; nhiều trường hợp có cách biểu diễn rõ hơn |
| Kiểu nguyên thủy tùy chọn | `OptionalInt`, `OptionalLong`, `OptionalDouble` để tránh boxing khi phù hợp |

`Optional` là một **value-based class**; không nên dựa vào identity `==`, `System.identityHashCode` hay khóa đồng bộ trên instance Optional. Dùng `isPresent`/`isEmpty` và các phép biến đổi thay vì phụ thuộc object identity.

### `OptionalInt` và giá trị bằng 0

`OptionalInt.of(0)` có giá trị 0, không phải trạng thái thiếu dữ liệu. `OptionalInt.empty()` mới là không có `int`. Tương tự, `Optional<Boolean>` có thể chứa `false` và vẫn `isPresent() == true`. Đừng dùng giá trị mặc định như 0, `false` hoặc chuỗi rỗng làm dấu hiệu “không có” nếu chúng cũng là dữ liệu hợp lệ.

## 12. Những lỗi thường gặp và cách sửa

| Cách viết / suy luận | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| `optional.get()` ngay sau khi nhận dữ liệu | Có thể ném `NoSuchElementException` | Dùng `orElse`/`orElseGet`/`orElseThrow`, `map` hoặc kiểm tra rõ |
| `Optional.of(nullableValue)` | Ném `NullPointerException` khi null | Dùng `ofNullable` nếu null được phép; giữ `of` nếu null là bug |
| `Optional.ofNullable(null).get()` | Vẫn ném `NoSuchElementException` | `ofNullable` không đảm bảo có giá trị |
| Phương thức trả `Optional<T>` nhưng trả `null` | Caller mất an toàn và có thể NPE | Trả `Optional.empty()` |
| `optional.map(x -> null)` với kỳ vọng Optional “chứa null” | `map` tạo Optional rỗng | Thiết kế mapper/kiểu kết quả rõ |
| `optional.flatMap(x -> null)` | Ném `NullPointerException` | Mapper phải trả `Optional.empty()` hoặc `Optional.of(...)` |
| `optional.or(() -> null)` | Supplier trả null, không hợp lệ | Supplier phải trả Optional hợp lệ |
| `orElse(expensive())` khi Optional có giá trị | `expensive()` vẫn bị gọi | `orElseGet(this::expensive)` nếu muốn lazy |
| Dùng `orElse(null)` rồi gọi phương thức trên kết quả | Có thể gây NPE sau khi unwrapping | Chọn fallback khác null hoặc xử lý thiếu |
| Trả `Optional.empty()` khi database timeout | Giấu nguyên nhân lỗi | Ném lỗi phù hợp hoặc trả Result có trạng thái lỗi |
| Chuyển mọi giá trị null thành empty vô điều kiện | Có thể che lỗi trường bắt buộc | Xác định hợp đồng dữ liệu và validate sớm |
| So sánh `optional == Optional.empty()` | Phụ thuộc identity không được đảm bảo | Dùng `isEmpty()` |
| Dùng `get()` trên `OptionalInt.empty()` qua `getAsInt()` | Vẫn ném `NoSuchElementException` | Dùng `orElse`/`orElseThrow` hoặc kiểm tra |

## 13. Bài tập luyện tập

1. Giải thích vì sao `Optional.ofNullable(null).isEmpty()` là `true`, còn `Optional.of(null)` ném `NullPointerException`.
2. Viết `Optional<String> code = Optional.empty();` rồi thử `code.get()`. Xác định exception và sửa bằng `orElse("UNKNOWN")`.
3. Tạo `Optional<User>` có User với email bằng null. Dùng `flatMap` với `normalizedEmail` để trả Optional email rỗng mà không ném exception.
4. Thử `Optional.of("x").map(value -> (String) null)` và `Optional.of("x").flatMap(value -> (Optional<String>) null)`. Dự đoán khác biệt và giải thích.
5. Thêm một phương thức fallback in `"fetching..."` trước khi trả kết quả. So sánh `orElse(fallback())` và `orElseGet(() -> fallback())` khi Optional đã có giá trị.
6. Viết `findOrder(id).orElseThrow(() -> new IllegalArgumentException("not found"))`. Phân biệt lỗi thiếu Order với trường hợp database query thất bại.
7. Từ danh sách ID, dùng `map(this::findUser).flatMap(Optional::stream)` để lấy danh sách User tồn tại. Vì sao số phần tử kết quả có thể nhỏ hơn số ID đầu vào?
8. Giả sử một API cũ trả `Optional<String>` hoặc `null`. Viết adapter ở ranh giới để tạo Optional luôn hợp lệ, sau đó nêu vì sao cần sửa API gốc.
9. Tạo `OptionalInt.of(0)` và `OptionalInt.empty()`. Kiểm tra `isPresent` của từng trường hợp. Vì sao 0 không phải “thiếu”?
10. Thử mô hình Result với ba trường hợp “tìm thấy”, “không có dữ liệu”, “lỗi nguồn dữ liệu”. Vì sao một `Optional<User>` duy nhất không đủ mang tất cả trạng thái đó?

## 14. Checklist an toàn cho `Optional`

- Phương thức trả `Optional<T>` có **luôn trả một đối tượng Optional** thay vì trả `null` không?
- Dữ liệu đầu vào nullable đã được đưa qua `ofNullable` ở **đúng ranh giới** chưa?
- Có chỗ nào gọi `get()` mà chưa chứng minh dữ liệu chắc chắn hiện diện không?
- Khi thiếu dữ liệu, có chính sách rõ: bỏ qua, fallback, báo lỗi hay trả Result không?
- Khi dùng `map`/`flatMap`, mapper có đúng kiểu trả về và có thể trả null hay không?
- Fallback có tốn tài nguyên hoặc side effect không; có nên dùng `orElseGet` để tính lười không?
- “Không có dữ liệu” có bị nhầm với “lỗi khi đọc dữ liệu” không?
- Có phụ thuộc object identity của Optional, hay dùng giá trị giả như 0/`false` để chỉ sự vắng mặt không?
- Đã kiểm tra các trường hợp **có giá trị, rỗng, null tại ranh giới, fallback lỗi, mapper lỗi** chưa?

**Ghi nhớ:** `Optional` biểu diễn có hoặc không có giá trị, không phải một hộp có thể “chứa null” như phần tử hợp lệ. `Optional.get()` không kiểm tra có thể ném `NoSuchElementException`; `Optional.of(null)` ném `NullPointerException`; `ofNullable(null)` và `map` trả null tạo Optional rỗng; `flatMap` yêu cầu mapper trả một Optional **không null**. Chọn `map`, `flatMap`, `orElseGet` và `orElseThrow` theo đúng ngữ nghĩa sẽ giúp API rõ ràng hơn và giảm lỗi runtime.
