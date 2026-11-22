# Optional trong Java: Biểu diễn kết quả có thể không tồn tại

**Chủ đề cha:** Optional (Java 8 và các JDK hiện đại). Bài học giải thích cách trả về một **giá trị có thể tồn tại hoặc không tồn tại** bằng `java.util.Optional<T>`, phân biệt dữ liệu vắng mặt với giá trị hợp lệ, và xử lý kết quả mà không phải truyền `null` qua nhiều tầng chương trình.

**Phạm vi phiên bản:** `Optional` có từ Java 8 và vẫn được áp dụng rộng rãi. Những API như `ifPresentOrElse`, `or`, `stream` có từ Java 9; `orElseThrow()` không tham số có từ Java 10; `isEmpty()` có từ Java 11. Các ví dụ Java hoàn chỉnh ở dưới sử dụng **Java 17+**, không dựa vào cơ chế đã lỗi thời.

## 1. Bài toán: Một phép tìm kiếm không phải lúc nào cũng có kết quả

Giả sử chúng ta tìm người dùng theo ID. Có hai kết quả hợp lệ:

1. Tìm thấy một người dùng.
2. Không tìm thấy người dùng nào.

Nếu chỉ trả về `User` và dùng `null` cho trường hợp không tìm thấy, chữ ký phương thức không cho người đọc thấy rõ quy ước thiếu dữ liệu:

```java
// Đoạn minh họa API truyền thống, không phải chương trình độc lập:
User findUser(String id); // có thể trả null, nếu hợp đồng phương thức nói vậy
```

Một lời gọi thiếu kiểm tra có thể gây `NullPointerException`:

```java
// Đoạn minh họa lỗi, không nên sao chép để chạy:
String name = findUser("missing").name(); // NPE nếu kết quả null
```

Với `Optional`, chữ ký thể hiện rõ khả năng vắng mặt:

```java
// Khai báo phương thức minh họa:
Optional<User> findUser(String id);
```

Người gọi biết cần quyết định cách xử lý khi `Optional` rỗng: cung cấp mặc định, báo lỗi, thử nguồn dữ liệu dự phòng, hoặc tiếp tục lan truyền trạng thái không tìm thấy.

**Optional không phải một giá trị mặc định và không phải cơ chế bắt lỗi.** Nó là một container có **0 hoặc 1 giá trị không null**. Khi rỗng, container vẫn tồn tại dưới dạng một đối tượng `Optional.empty()`; không được đặt chính biến `Optional` thành `null`.

## 2. Hai trạng thái: present và empty

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Present** | Đang chứa đúng một giá trị khác `null` | `Optional.of("Lan")` |
| **Empty** | Không chứa giá trị nào | `Optional.empty()` |

Những trường hợp quan trọng:

- `Optional.of(0)` **có giá trị**: số 0 là dữ liệu hợp lệ, không phải “không tồn tại”.
- `Optional.of(false)` **có giá trị**: boolean false không phải empty.
- `Optional.of("")` **có giá trị**: chuỗi rỗng không tự động có nghĩa thiếu dữ liệu. Nếu nghiệp vụ coi chuỗi rỗng hoặc toàn khoảng trắng là thiếu, phải áp dụng quy tắc rõ ràng bằng `filter(...)`.
- `Optional.ofNullable(null)` **rỗng**: không đại diện cho một “giá trị null được chứa bên trong”.
- `Optional.empty()` là **trạng thái không có kết quả**, không nhất thiết là lỗi. “Không tìm thấy sản phẩm tùy chọn” khác với “ID đầu vào không hợp lệ” hoặc “cơ sở dữ liệu không kết nối được”.

Vì vậy đừng mã hóa “không tìm thấy” bằng một giá trị giả như `0`, `-1`, `""` hoặc đối tượng `User` rỗng khi những giá trị ấy có thể mang nghĩa nghiệp vụ. `Optional<T>` giúp giữ ranh giới giữa “giá trị thực sự bằng X” và “không có giá trị”.

### 2.1. Vì sao Optional được gọi là value-based class?

Theo tài liệu Java, `Optional` là một **value-based class**. Những instance có giá trị bằng nhau có thể được xem như tương đương; không dựa vào **object identity** của chúng, không so sánh bằng `==` để kiểm tra empty, và không dùng `Optional` làm monitor cho `synchronized`. Dùng `isPresent()`/`isEmpty()` khi cần kiểm tra trạng thái, và `equals()` nếu thực sự cần so sánh nội dung hai Optional.

Không giả định `Optional.empty()` phải là singleton ở mọi bản cài đặt: `optional == Optional.empty()` không phải phép kiểm tra trạng thái được khuyến nghị.

## 3. Tạo Optional bằng `of`, `ofNullable` và `empty`

Ba factory cơ bản:

```java
Optional<String> name = Optional.of("Lan");
Optional<String> missing = Optional.empty();
Optional<String> maybeEmail = Optional.ofNullable(emailFromLegacyApi);
```

Đây là **các dòng đặt trong một phương thức** có import `java.util.Optional`; biến `emailFromLegacyApi` là `String` có thể null từ API cũ.

| Factory | Đầu vào | Kết quả |
| --- | --- | --- |
| `Optional.of(value)` | `value != null` | Present |
| `Optional.of(null)` | `null` | Ném `NullPointerException` |
| `Optional.ofNullable(value)` | Khác `null` | Present |
| `Optional.ofNullable(null)` | `null` | Empty |
| `Optional.empty()` | Không tham số | Empty |

**Khi nào dùng?** Nếu tại điểm tạo bạn có thể **khẳng định** giá trị không null theo hợp đồng, dùng `of`. Nếu đang đi qua ranh giới API cho phép null (mã cũ, dữ liệu bên ngoài, thư viện có hợp đồng trả null), dùng `ofNullable`. Nếu không tìm thấy kết quả, trả `Optional.empty()` trực tiếp.

Không dùng `Optional.ofNullable(value)` để che giấu vi phạm invariant: khi hệ thống **bắt buộc** phải có giá trị, hãy kiểm tra và báo lỗi rõ ràng thay vì âm thầm biến dữ liệu lỗi thành empty.

## 4. Ví dụ đầy đủ: Repository trả về Optional thay vì null

Tạo file **`OptionalLookupDemo.java`**:

```java
import java.util.List;
import java.util.Optional;

public class OptionalLookupDemo {
    record User(String id, String name, String email) {}

    private static final List<User> USERS = List.of(
            new User("u1", "Lan", "lan@example.com"),
            new User("u2", "Minh", null)
    );

    static Optional<User> findUser(String id) {
        return USERS.stream()
                .filter(user -> user.id().equals(id))
                .findFirst();
    }

    static Optional<String> findEmail(String id) {
        return findUser(id)
                .map(User::email)
                .map(String::trim)
                .filter(email -> !email.isEmpty());
    }

    public static void main(String[] args) {
        String firstName = findUser("u1")
                .map(User::name)
                .orElse("Not found");

        String missingName = findUser("u404")
                .map(User::name)
                .orElse("Not found");

        String missingEmail = findEmail("u2")
                .orElse("No email");

        System.out.println("User u1: " + firstName);
        System.out.println("User u404: " + missingName);
        System.out.println("Email u2: " + missingEmail);
        System.out.println("Missing user: " + findUser("u404").isEmpty());
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 OptionalLookupDemo.java
java OptionalLookupDemo
```

**Stdout chính xác:**

```text
User u1: Lan
User u404: Not found
Email u2: No email
Missing user: true
```

**Giải thích cơ chế:**

1. `findUser` gọi `findFirst()` trên stream; phương thức này đã trả `Optional<User>` để biểu diễn có/không tìm thấy, không cần viết `return null`.
2. `findUser("u1")` present; `map(User::name)` biến giá trị `User` thành tên rồi `orElse(...)` lấy tên.
3. `findUser("u404")` empty; `map(...)` **không gọi mapper** khi Optional rỗng, `orElse(...)` trả chuỗi dự phòng.
4. Ví dụ cố tình nhận `email == null` ở ranh giới dữ liệu cũ để diễn giải cơ chế: `Optional.map(User::email)` biến kết quả null của mapper thành Optional rỗng; các bước tiếp theo không gọi `String::trim` trên null.
5. `filter(email -> !email.isEmpty())` thể hiện **quy tắc nghiệp vụ**: sau khi trim, chuỗi rỗng được coi là email không sử dụng được. Optional **không tự loại chuỗi rỗng**.
6. `Optional.isEmpty()` có từ Java 11; đây là lý do ví dụ yêu cầu Java 17+. Mã thực tế có thể không muốn đưa các field nullable vào domain record; nếu dữ liệu luôn hợp lệ, hãy kiểm soát tại lớp nhận dữ liệu, tránh lan truyền null vào sâu chương trình.

**Hợp đồng tốt hơn:** “Tìm ID không tồn tại” thường là kết quả empty, còn “ID đầu vào sai cấu trúc” có thể là lỗi kiểm tra dữ liệu; “truy vấn thất bại” là ngoại lệ/sự kiện lỗi khác. Optional chỉ mô tả **có hay không có kết quả**, không giải thích nguyên nhân lỗi.

## 5. Xử lý kết quả: Chọn một trong bốn hướng

### 5.1. Lấy giá trị mặc định: `orElse`

```java
String displayName = findUser("u404")
        .map(User::name)
        .orElse("Guest");
```

Đoạn mã đặt **trong `OptionalLookupDemo.main`**, có sẵn `findUser` và `User` ở mục 4. Nếu tìm thấy tên, dùng tên; nếu không, dùng `"Guest"`. Đảm bảo default mang ý nghĩa đúng: tên hiển thị có thể mặc định, nhưng một kết quả như “đã xác thực danh tính” không nên được mặc định thành true.

### 5.2. Tạo fallback khi cần: `orElseGet`

```java
String displayName = findUser("u404")
        .map(User::name)
        .orElseGet(() -> loadGuestName());
```

Đây là **đoạn mã minh họa**, với `loadGuestName()` là một phương thức do ứng dụng cung cấp. `orElseGet(Supplier<T>)` chỉ gọi supplier **khi Optional rỗng**, phù hợp nếu tạo giá trị dự phòng tốn chi phí hoặc có side effect.

Quan trọng: `orElse(loadGuestName())` gọi `loadGuestName()` **ngay khi biểu thức tham số được đánh giá**, kể cả khi Optional đã có giá trị. Đây là khác biệt **eager** (`orElse`) và **lazy** (`orElseGet`) rất dễ bị bỏ qua.

### 5.3. Bắt buộc có giá trị: `orElseThrow`

```java
User existing = findUser("u1")
        .orElseThrow(() ->
                new IllegalArgumentException("User does not exist"));
```

Đây là đoạn trong một phương thức. Nếu không tồn tại người dùng, exception được tạo và ném. `orElseThrow(Supplier<? extends Throwable>)` cho phép diễn đạt rõ tình huống “không có kết quả là không thể chấp nhận ở bước này”. Nếu không cung cấp supplier, `orElseThrow()` (Java 10+) ném `NoSuchElementException` cho Optional rỗng. Cân nhắc kiểu lỗi phù hợp với domain/API, ví dụ ở lớp HTTP có thể chuyển lỗi không tìm thấy thành mã phản hồi thích hợp.

### 5.4. Giữ trạng thái rỗng và chuyển tiếp

Không phải mọi tầng đều cần unwrap. Phương thức cấp giữa có thể giữ nguyên `Optional<T>` hoặc biến đổi nó bằng `map/flatMap/filter` rồi chuyển cho tầng quyết định fallback cuối cùng. Điều này tránh làm mất ý nghĩa “chưa tìm thấy” quá sớm.

Ví dụ:

```java
Optional<String> maybeName = findUser("u1").map(User::name);
```

Đoạn mã trên **chưa cần quyết định** khi không có tên; người gọi có thể lựa chọn tiếp.

## 6. `orElse` và `orElseGet`: ví dụ xác minh eager/lazy

Tạo file **`OptionalFallbackDemo.java`**:

```java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalFallbackDemo {
    private static String fallback(AtomicInteger calls) {
        calls.incrementAndGet();
        return "backup";
    }

    public static void main(String[] args) {
        AtomicInteger calls = new AtomicInteger();
        Optional<String> present = Optional.of("cached");

        String eager = present.orElse(fallback(calls));
        String lazy = present.orElseGet(() -> fallback(calls));
        String absent = Optional.<String>empty()
                .orElseGet(() -> fallback(calls));

        System.out.println("Eager: " + eager);
        System.out.println("Lazy: " + lazy);
        System.out.println("Absent: " + absent);
        System.out.println("Fallback calls: " + calls.get());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 OptionalFallbackDemo.java
java OptionalFallbackDemo
```

Kết quả:

```text
Eager: cached
Lazy: cached
Absent: backup
Fallback calls: 2
```

Ở lệnh `present.orElse(fallback(calls))`, giá trị `present` đã có nhưng Java **vẫn đánh giá tham số** `fallback(calls)`, nên bộ đếm tăng 1. `present.orElseGet(...)` bỏ qua supplier vì Optional không rỗng. Lần gọi với Optional rỗng thực thi supplier, khiến tổng số lần fallback bằng 2.

**Chọn đúng:** `orElse("constant")` đơn giản và phù hợp khi default đã có sẵn. `orElseGet(this::lookupFallback)` phù hợp khi fallback cần truy vấn, tính toán hoặc cấp phát tốn chi phí.

`orElseGet` không làm phép tính bất đồng bộ; supplier vẫn chạy đồng bộ trên thread đang xử lý. “Lazy” ở đây chỉ có nghĩa **chỉ gọi khi cần**.

## 7. Biến đổi mà không cần `if (isPresent())`: `map`, `filter`, `flatMap`

### 7.1. `map`: giá trị có mặt thì biến đổi

`Optional<T>.map(Function<T,U>)` trả `Optional<U>`. Nếu đầu vào empty, mapper không chạy. Nếu mapper trả `null`, kết quả của `map` là empty (về mặt ngữ nghĩa như `ofNullable`).

```java
Optional<String> trimmed = Optional.of(" Lan ")
        .map(String::trim); // Có "Lan"
Optional<Integer> size = trimmed.map(String::length); // Có 3
```

Các dòng trên là **đoạn mã trong phương thức** với import `java.util.Optional`. `map` không trả thẳng `String` hay `int`; nó vẫn giữ ý nghĩa có/không có giá trị.

### 7.2. `filter`: điều kiện không đạt thì empty

```java
Optional<String> useful = Optional.of("  ")
        .map(String::trim)
        .filter(s -> !s.isEmpty()); // Optional.empty()
```

Đây là đoạn mã trong phương thức. `filter` không phải cơ chế bắt ngoại lệ của predicate; nếu predicate ném exception, ngoại lệ vẫn được truyền ra. Hãy dùng `filter` cho tiêu chí hợp lệ rõ ràng thay vì nuốt lỗi ngoài ý muốn.

### 7.3. `flatMap`: khi mapper **đã trả Optional**

Giả sử một phương thức `normalize(String)` trả `Optional<String>`, vì chuỗi có thể toàn khoảng trắng và không có kết quả. Nếu gọi `map(OptionalFlowDemo::normalize)` thì kiểu sẽ là `Optional<Optional<String>>` — hai lớp lồng nhau. `flatMap(...)` giữ một lớp `Optional<String>`.

Tạo file **`OptionalFlowDemo.java`**:

```java
import java.util.List;
import java.util.Optional;

public class OptionalFlowDemo {
    static Optional<String> normalize(String text) {
        return Optional.ofNullable(text)
                .map(String::trim)
                .filter(s -> !s.isEmpty());
    }

    public static void main(String[] args) {
        Optional<Optional<String>> nested = Optional.of(" Lan ")
                .map(OptionalFlowDemo::normalize);

        Optional<String> flat = Optional.of(" Lan ")
                .flatMap(OptionalFlowDemo::normalize);

        List<Optional<String>> labels = List.of(
                Optional.of("A"),
                Optional.empty(),
                Optional.of("B")
        );

        List<String> presentLabels = labels.stream()
                .flatMap(Optional::stream)
                .toList();

        System.out.println("Nested outer present: " + nested.isPresent());
        System.out.println("Flat value: " + flat.orElse("none"));
        System.out.println("Blank is absent: " + normalize(" ").isEmpty());
        System.out.println("Present labels: " + presentLabels);
    }
}
```

Chạy:

```bash
javac --release 17 OptionalFlowDemo.java
java OptionalFlowDemo
```

**Stdout:**

```text
Nested outer present: true
Flat value: Lan
Blank is absent: true
Present labels: [A, B]
```

**Lưu ý quan trọng:**

- `flatMap` kỳ vọng mapper trả một đối tượng `Optional` **không null**. Nếu mapper trả `null` thay vì `Optional.empty()`, nó ném `NullPointerException`.
- `Optional.stream()` có từ **Java 9**: trả stream 1 phần tử nếu present, hoặc stream rỗng nếu empty. Nhờ đó `flatMap(Optional::stream)` lấy các giá trị present từ `Stream<Optional<T>>`.
- `Stream.toList()` có từ **Java 16** và trả list không sửa được. Nếu dự án dùng phiên bản thấp hơn, cần chọn collector tương thích; các ví dụ dùng Java 17+.
- Nếu muốn bỏ Optional rỗng nhưng giữ giá trị như 0, false hoặc chuỗi rỗng, `Optional::stream` vẫn giữ các giá trị đó nếu chúng present.

## 8. Khi có nhiều nguồn tìm kiếm: `or` và thứ tự fallback

`Optional.or(Supplier<Optional<T>>)` (từ **Java 9**) cho phép thử nguồn thứ hai khi nguồn đầu **không có kết quả**, đồng thời vẫn trả một `Optional<T>`:

```java
Optional<String> selected = findLocal("key")
        .or(() -> findRemote("key"));
```

Đây là **đoạn minh họa**: `findLocal` và `findRemote` là hai phương thức giả định đều trả `Optional<String>`. Supplier chỉ được gọi khi nguồn đầu empty; nếu remote cũng empty thì kết quả vẫn empty.

Khác biệt chính:

| Phương thức | Khi present | Khi empty | Kiểu kết quả |
| --- | --- | --- | --- |
| `orElse(value)` | Giữ giá trị có sẵn; biểu thức tham số đã được đánh giá | Lấy value | `T` |
| `orElseGet(supplier)` | Không gọi supplier | Gọi supplier trả `T` | `T` |
| `or(supplier)` | Không gọi supplier | Gọi supplier trả `Optional<T>` | `Optional<T>` |
| `orElseThrow(supplier)` | Trả `T` | Ném exception do supplier tạo | `T` hoặc exception |

`or(...)` không phải toán tử “OR boolean”. Nó biểu diễn tuyến tìm kiếm dự phòng **vẫn có khả năng không tìm thấy**. Nhà cung cấp fallback **không được trả null Optional**; nếu không có dữ liệu hãy trả `Optional.empty()`.

## 9. Optional trong Java Stream và các phép truy vấn

Các terminal operation thường trả Optional vì có thể không có phần tử phù hợp:

- `Stream<T>.findFirst()` trả `Optional<T>`: nếu stream rỗng thì empty.
- `Stream<T>.findAny()` trả `Optional<T>`: cũng có thể empty; với parallel stream, không mặc định là “phần tử đầu tiên”.
- `Stream<T>.min(...)`, `max(...)` và `reduce(BinaryOperator<T>)` trả `Optional<T>` khi có khả năng nguồn rỗng.
- `IntStream.findFirst()` trả `OptionalInt`; `LongStream.findFirst()` trả `OptionalLong`; `DoubleStream.average()` trả `OptionalDouble`.

Ví dụ **đoạn mã trong phương thức**, với import `java.util.stream.IntStream`:

```java
int firstEven = IntStream.of(1, 3, 4, 6)
        .filter(n -> n % 2 == 0)
        .findFirst()
        .orElse(-1); // 4

boolean averagePresent = IntStream.empty()
        .average()
        .isPresent(); // false
```

`findFirst` không cần một “giá trị giả” để biểu diễn khi không tìm thấy; quyết định dùng `-1` chỉ diễn ra **ở ranh giới người gọi**. Nếu `-1` cũng có thể là kết quả hợp lệ, nên tiếp tục giữ `OptionalInt` thay vì unwrap bằng giá trị đó.

Nếu một pipeline có `Optional<T>` lồng bên trong stream, dùng `flatMap(Optional::stream)` như mục 7 để gom dữ liệu có mặt. Không giả định `Optional.stream()` là phương thức có từ Java 8; nó có từ Java 9.

## 10. `OptionalInt`, `OptionalLong` và `OptionalDouble`

Các phiên bản chuyên biệt tránh boxing cho giá trị số nguyên thủy:

| Kiểu | Giá trị có mặt | Trường hợp rỗng | Phương thức lấy giá trị |
| --- | --- | --- | --- |
| `Optional<T>` | Đối tượng `T` không null | `Optional.empty()` | `orElse`, `orElseThrow`, `get()` |
| `OptionalInt` | `int` | `OptionalInt.empty()` | `orElse`, `orElseThrow`, `getAsInt()` |
| `OptionalLong` | `long` | `OptionalLong.empty()` | `orElse`, `orElseThrow`, `getAsLong()` |
| `OptionalDouble` | `double` | `OptionalDouble.empty()` | `orElse`, `orElseThrow`, `getAsDouble()` |

`OptionalInt.of(0)` là **present**, không phải empty; tương tự `OptionalDouble.of(0.0)`. Các kiểu primitive Optional có API gọn hơn `Optional<T>`: không có cùng tập `map`/`flatMap` như `Optional<T>`, vì thế không cố viết `OptionalInt.map(...)` nếu phương thức đó không tồn tại. Nếu cần biến đổi primitive, cân nhắc dùng `OptionalInt.stream()` (Java 9+) hoặc chuyển kiểu/đặt logic riêng phù hợp.

Không thay `OptionalInt` thành `Optional<Integer>` chỉ để bỏ qua các hạn chế kiểu mà không cân nhắc boxing. Khi một API yêu cầu generic object `Optional<T>`, có thể phải chuyển ở ranh giới thích hợp.

## 11. `ifPresent` và `ifPresentOrElse`: xử lý side effect có chủ đích

`ifPresent(Consumer<T>)` chỉ thực thi hành động khi có giá trị; `ifPresentOrElse(Consumer<T>, Runnable)` (Java 9+) định nghĩa hai nhánh:

```java
Optional.of("Lan")
        .ifPresent(name -> System.out.println("Hello " + name));

Optional.<String>empty()
        .ifPresentOrElse(
                name -> System.out.println("Hello " + name),
                () -> System.out.println("No user")
        );
```

Đây là các đoạn mã có thể đặt trong phương thức. Stdout là:

```text
Hello Lan
No user
```

`ifPresent` và `ifPresentOrElse` trả `void`, thích hợp cho cập nhật UI, gửi thông báo hoặc logging có chủ đích; khi cần **tạo giá trị trả về**, `map`/`flatMap`/`orElse` thường rõ ràng hơn. Không dùng `ifPresent` chỉ để ghi vào biến mutable bên ngoài rồi trả kết quả ở cuối, trừ khi có lý do thiết kế cụ thể.

## 12. Optional không thay thế việc phân loại lỗi

Trạng thái **empty** nói rằng “không có giá trị”, không trả lời “vì sao không có”. Khi thiết kế API, nên phân biệt:

| Tình huống | Hướng thiết kế |
| --- | --- |
| Tìm một phần tử theo key nhưng không thấy | `Optional<Entity>` |
| Tìm số lớn nhất trong tập có thể rỗng | `OptionalInt` / `Optional<T>` |
| Danh sách tìm kiếm không có kết quả nào | Collection rỗng thay vì `Optional<List<T>>` trong đa số trường hợp |
| Tham số đầu vào không hợp lệ | Kiểm tra và báo lỗi rõ ràng, ví dụ `IllegalArgumentException` |
| Không kết nối được cơ sở dữ liệu | Exception hoặc mô hình kết quả phân biệt lỗi và thành công |
| Cần biết *không tìm thấy*, *không có quyền*, *đã khóa* | Một kiểu kết quả domain có nhiều trạng thái thay vì chỉ Optional |
| Một giá trị bắt buộc phải hiện diện theo invariant | Kiểm tra/`requireNonNull`/throw, không tự động biến thành empty |

**Không biến lỗi thành “không có kết quả” bằng cách catch mọi exception rồi `return Optional.empty()`.** Làm vậy có thể che giấu hỏng dữ liệu, lỗi mạng hoặc lỗi lập trình; người gọi không thể phân biệt “không tìm thấy” với “truy vấn thất bại”.

Trạng thái empty có thể hợp lý khi tra cứu không thấy đối tượng và đó là outcome bình thường. Nếu “không có kết quả” là lỗi ở tầng API cao hơn, tầng gọi có thể dùng `orElseThrow` để chuyển thành một exception có ngữ nghĩa rõ ràng.

## 13. Nên đặt Optional ở đâu trong API?

Tài liệu chuẩn nhấn mạnh `Optional<T>` **chủ yếu được thiết kế làm kiểu trả về phương thức** khi cần thể hiện không có kết quả và `null` dễ gây lỗi.

### Nên

```java
Optional<User> findById(String id);
OptionalInt indexOf(String keyword);
```

Hai chữ ký là **minh họa thiết kế API**, với `User` là kiểu domain của ứng dụng. Người gọi thấy ngay khả năng không có kết quả và chủ động chọn cách xử lý.

### Cân nhắc, không lạm dụng

- **Field trong entity/DTO:** `Optional` không được thiết kế chủ yếu để làm field; bản thân `Optional` không triển khai `Serializable`. Các framework ORM, serializer hoặc công cụ mapping có thể cần cấu hình riêng. Với field không bắt buộc, hãy tuân thủ quy ước dữ liệu của framework/domain và quy định nullability rõ ràng.
- **Tham số phương thức:** `Optional<T>` làm tham số thường khiến API khó gọi hơn; overload hoặc tham số nullable có hợp đồng rõ ràng, cấu trúc request riêng hay kiểu domain có thể phù hợp hơn. Đây là hướng dẫn thiết kế, không phải luật cấm tuyệt đối.
- **Collection chứa nhiều kết quả:** dùng `List<T>` hoặc `Set<T>` rỗng khi có 0 phần tử, thay vì `Optional<List<T>>` nếu không có sự phân biệt nghiệp vụ giữa “không chạy truy vấn” và “truy vấn trả 0 bản ghi”.
- **Getter đơn giản:** không tạo `Optional` cho mọi thuộc tính bắt buộc đã được bảo vệ bởi invariant của object.
- **Chuyển đổi JSON/HTTP:** API công khai cần biểu diễn trạng thái thiếu dữ liệu theo contract của giao thức; `Optional` là chi tiết Java, không tự bảo đảm serializer hiểu ý nghĩa đó.

**Quy tắc cơ bản:** Optional làm cho một trạng thái *đã có thể xảy ra* trở thành rõ ràng trong chữ ký phương thức; nó không khiến mọi API đều cần Optional.

## 14. Những lỗi phổ biến khi dùng Optional

1. **Trả `null` thay vì `Optional.empty()`:** người gọi mất an toàn và có thể NPE ngay khi gọi `map`/`orElse`.
2. **Gọi `Optional.of(nullable)`:** nếu đầu vào null, ném `NullPointerException`; tại ranh giới dữ liệu nullable, dùng `ofNullable`.
3. **Gọi `get()` hoặc `getAsInt()` mà chưa có bảo đảm:** Optional rỗng ném `NoSuchElementException`. Ưu tiên `orElse`, `orElseGet` hoặc `orElseThrow` với hợp đồng rõ ràng.
4. **Viết quá nhiều `if (optional.isPresent()) { optional.get() }`:** không sai tuyệt đối nhưng hay làm mất lợi ích của `map`/`flatMap`/`filter`. Chỉ dùng nhánh điều khiển khi thực sự dễ hiểu hơn.
5. **Nghĩ `Optional.of(0)` là empty:** sai; 0, false và chuỗi rỗng vẫn là các giá trị present.
6. **Nhầm `map` với `flatMap`:** nếu mapper đã trả Optional, dùng `flatMap` để không có `Optional<Optional<T>>`.
7. **Trả null từ mapper của `flatMap` hoặc `or`:** các hàm này yêu cầu trả Optional hợp lệ; null có thể gây NPE.
8. **Viết `orElse(expensiveCall())` và tưởng chỉ gọi khi rỗng:** tham số được tính ngay; dùng `orElseGet(() -> expensiveCall())` nếu muốn lazy.
9. **Nuốt mọi lỗi bằng `Optional.empty()`:** làm mất thông tin lỗi nghiệp vụ/hạ tầng, không thể khắc phục đúng ở tầng gọi.
10. **Trả `Optional<List<T>>` cho mọi truy vấn nhiều kết quả:** một list rỗng thường thể hiện 0 bản ghi rõ hơn, trừ khi có trạng thái nghiệp vụ riêng.
11. **So sánh Optional bằng `==` hoặc dùng làm lock:** Optional là value-based class, không có cam kết identity/singleton.
12. **Cho rằng Optional tự động kiểm tra chuỗi blank hoặc object không hợp lệ:** Optional chỉ biết có/không có giá trị **khác null**; quy tắc validate phải được viết tường minh.
13. **Tạo `Optional<T>` rồi lại trả `optional.orElse(null)` qua nhiều tầng:** vô tình đưa null quay lại thiết kế; chỉ unwrap về null khi API bắt buộc và hợp đồng cho phép.
14. **Tưởng Optional thay thế exception hoặc mô hình Result đa trạng thái:** Optional chỉ mã hóa 0/1 giá trị, không mang thông tin lỗi.
15. **Gọi `Stream.toList()` trong code cần Java 8:** phương thức có từ Java 16; nếu dự án cần chạy bản cũ, chọn collector tương thích. Đừng nhầm “Optional xuất hiện từ Java 8” với “mọi method trong ví dụ đều có từ Java 8”.

## 15. Checklist thiết kế phương thức có thể không trả kết quả

Trước khi chọn `Optional`, hãy hỏi:

1. **Vắng mặt có phải outcome bình thường không?** Nếu đúng, `Optional<T>` thường phù hợp với một kết quả tùy chọn; nếu là lỗi, đưa lỗi vào contract.
2. **Dữ liệu trả về là 0–1 hay 0–n phần tử?** 0–1 → Optional; 0–n → collection rỗng.
3. **Có phải tất cả giá trị hợp lệ đều khác `null`?** `Optional<T>` không chứa được null; có thể cần làm sạch dữ liệu đầu vào.
4. **Tầng nào nên quyết định fallback?** Đừng thay mọi empty bằng giá trị giả ngay trong repository, khiến tầng nghiệp vụ không biết kết quả thực sự vắng mặt.
5. **Có phí cho fallback không?** Dùng `orElseGet`/`or` khi muốn chỉ truy cập nguồn dự phòng nếu cần.
6. **Có chuỗi các bước tìm kiếm tùy chọn không?** Dùng `map`, `flatMap`, `filter`, `or` để truyền trạng thái empty một cách rõ ràng.
7. **Có yêu cầu phân biệt nhiều nguyên nhân thất bại không?** Khi có, cần một kiểu kết quả có thông tin trạng thái hoặc exception thích hợp, không gộp hết thành empty.
8. **Có đang dựa vào bản Java nào?** Dùng `ifPresentOrElse`/`or`/`stream` từ Java 9, `orElseThrow()` không tham số từ Java 10, `isEmpty` từ Java 11 và `Stream.toList` từ Java 16 khi dự án cho phép.

## 16. Bài tập tự kiểm tra

1. `Optional.of(0).isPresent()` trả gì? `Optional.of("").isEmpty()` trả gì?
2. Vì sao `Optional.of(null)` khác `Optional.ofNullable(null)`?
3. Tại sao `Optional.of("cached").orElse(fetch())` có thể gọi `fetch()` dù cache có dữ liệu? Nên sửa thế nào nếu `fetch()` tốn thời gian?
4. Một phương thức `findManager(User)` đã trả `Optional<User>`. Nếu dùng `map(this::findManager)` trên `Optional<User>`, kiểu kết quả ra sao? Thay `map` bằng gì?
5. Vì sao phương thức `List<Order> findOrders(...)` thường tốt hơn `Optional<List<Order>>` khi không có đơn hàng?
6. Tìm bản ghi không tồn tại và mất kết nối DB có nên cùng trả `Optional.empty()` không?
7. `Stream<Optional<String>>` muốn loại bỏ empty nhưng giữ mọi chuỗi present (kể cả `""`) nên dùng gì trong Java 9+?
8. Nếu Optional rỗng nhưng `get()` bị gọi, Java ném lỗi gì?

**Đáp án gợi ý:** (1) true và false; (2) `of` không chấp nhận null, `ofNullable` trả empty; (3) đối số `orElse` eager, dùng `orElseGet(() -> fetch())`; (4) `Optional<Optional<User>>`, dùng `flatMap`; (5) collection rỗng thể hiện 0 phần tử; (6) không, cần phân biệt outcome và lỗi; (7) `flatMap(Optional::stream)`; (8) `NoSuchElementException`.

**Ghi nhớ:** `Optional<T>` là cách **biểu diễn bằng kiểu dữ liệu** rằng một phép tính có thể không tạo ra giá trị. Nó giảm sự mơ hồ của `null`, giữ được giá trị hợp lệ như 0/false/chuỗi rỗng và buộc tầng gọi chủ động quyết định fallback, lỗi hoặc chuyển tiếp. Hãy dùng Optional đúng ranh giới, không lạm dụng nó làm field/collection nhiều phần tử, và không biến exception thành empty một cách tùy tiện.

## Tài liệu Java chính thức — API vẫn được áp dụng

- `java.util.Optional<T>` — mô tả, `of`, `ofNullable`, `map`, `flatMap`, `filter`, `orElse`, `orElseGet`, `or`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html
- `OptionalInt`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalInt.html
- `OptionalLong`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalLong.html
- `OptionalDouble`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalDouble.html
- `Stream<T>` — `findFirst`, `findAny`, `min`, `max`, `toList`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
