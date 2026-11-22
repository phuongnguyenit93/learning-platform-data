# Optional.orElseThrow với Supplier ngoại lệ

> **Chủ đề:** Java 8 — Optional. Trọng tâm là `Optional<T>.orElseThrow(Supplier<? extends X>)`: trả giá trị khi có, hoặc tạo và ném ngoại lệ phù hợp khi không có. API này ra đời từ Java 8 và vẫn được khuyến nghị sử dụng khi ứng dụng cần một thông báo lỗi/loại ngoại lệ có ý nghĩa.

## 1. Khi nào dùng orElseThrow?

Giả sử có hàm tìm người dùng theo mã định danh:

~~~java
Optional<User> findUserById(long id)
~~~

Đây là **chữ ký minh họa** của một hàm thuộc ứng dụng, không phải phương thức sẵn có của Java. Kết quả có thể chứa `User` hoặc rỗng nếu không tìm được.

Trong một luồng xử lý:

- **Không tìm thấy người dùng là bình thường** (chẳng hạn tìm kiếm gợi ý): caller có thể giữ nguyên `Optional`, dùng `ifPresent` hoặc chọn giá trị dự phòng.
- **Bắt buộc phải có người dùng** để tiếp tục tạo giao dịch: caller cần dừng nhánh xử lý và báo lý do cụ thể. Lúc này `orElseThrow` phù hợp.

~~~java
User user = findUserById(42L)
        .orElseThrow(() ->
                new NoSuchElementException("User 42 not found"));
~~~

Đây là **đoạn minh họa** giả định có `User` và `findUserById` trong ứng dụng, cùng import `java.util.NoSuchElementException`.

Khi tìm thấy `User`, kết quả `orElseThrow` chính là đối tượng `User` bên trong; biểu thức tạo ngoại lệ **không chạy**. Khi `Optional` rỗng, lambda mới tạo `NoSuchElementException` và phương thức ném ngoại lệ đó để kết thúc đường thực thi bình thường.

**Điểm cốt lõi:** `orElseThrow` không tìm dữ liệu thay bạn, không tự quyết định loại lỗi và không “đổi Optional thành một giá trị mặc định”. Nó diễn đạt ranh giới nghiệp vụ: **đến đây, giá trị bắt buộc phải tồn tại, nếu không phải báo lỗi**.

## 2. Hiểu đúng chữ ký generic

Trong `java.util.Optional<T>`, chữ ký hiện hành:

~~~java
public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
~~~

Đây là **chữ ký API**, không phải chương trình Java độc lập để biên dịch.

| Thành phần | Ý nghĩa |
| --- | --- |
| `T` | Kiểu giá trị mà `Optional<T>` chứa, chẳng hạn `User`, `String` hoặc `Order`. |
| `X extends Throwable` | Kiểu ngoại lệ mà nhánh rỗng có thể ném. Bao gồm cả checked exception và unchecked exception. |
| `Supplier<? extends X>` | Hàm **không nhận tham số**, khi được gọi sẽ trả về một đối tượng ngoại lệ kiểu `X` (hoặc kiểu con của `X`). |
| `throws X` | Khai báo ngoại lệ kiểu `X`. Nếu `X` là checked exception, caller phải bắt hoặc tiếp tục khai báo `throws`. |
| Giá trị trả về `T` | Chỉ xảy ra khi `Optional` có giá trị. Trường hợp rỗng không trả `null` hoặc `Optional.empty()`, mà ném ngoại lệ. |

`Supplier<T>` là một functional interface trong `java.util.function`, có phương thức trừu tượng `T get()`. Ở đây tham số generic của Supplier là **kiểu ngoại lệ**, không phải kiểu giá trị đang được tìm.

~~~java
Supplier<IllegalArgumentException> exceptionSupplier =
        () -> new IllegalArgumentException("Invalid identifier");

String value = Optional.of("OK")
        .orElseThrow(exceptionSupplier); // Trả "OK".
~~~

Đây là **đoạn minh họa** dùng `java.util.Optional` và `java.util.function.Supplier`. Không có exception được ném vì Optional chứa `"OK"`. Supplier cũng không được gọi.

### 2.1. Supplier tạo ngoại lệ, không phải ném ngoại lệ từ lambda

Cách thông thường:

~~~java
.orElseThrow(() -> new IllegalStateException("State missing"))
~~~

Lambda **trả về một đối tượng exception**; `orElseThrow` chịu trách nhiệm ném đối tượng đó. Cách viết này làm rõ kiểu `Supplier<IllegalStateException>`.

Không nhầm với:

~~~java
// Sai về kiểu hàm cần thiết ở đây: lambda không thể tạo Supplier
// bằng một lệnh throw mà không có giá trị exception để cung cấp.
.orElseThrow(() -> { throw new IllegalStateException("missing"); })
~~~

**Chú ý:** Về Java type system, lambda dạng block luôn ném mà không return *vẫn có thể hợp lệ* trong một số ngữ cảnh functional interface có kết quả nhờ quy tắc value-compatible. Tuy nhiên, không nên viết theo kiểu này cho `orElseThrow`: nó khiến Supplier tự ném thay vì trả một ngoại lệ theo ý nghĩa API, khó đọc và không đem lại lợi ích. Cách chuẩn là `() -> new ...`.

### 2.2. Method reference thay lambda

Nếu lớp ngoại lệ có constructor không tham số, có thể dùng method reference:

~~~java
String value = Optional.of("Ready")
        .orElseThrow(IllegalStateException::new);
~~~

Khi cần thông báo chi tiết hay tham số nghiệp vụ, dùng lambda:

~~~java
String value = Optional.of("Ready")
        .orElseThrow(() -> new IllegalStateException("Required state absent"));
~~~

Cả hai đoạn đều là minh họa. Constructor reference `IllegalStateException::new` tạo một exception **không có thông báo tùy biến**; phiên bản lambda tạo thông báo `"Required state absent"` khi rỗng.

Nếu muốn dùng method reference của constructor nhận chuỗi mà không lambda, vẫn cần có cơ chế cung cấp đối số. Bản thân `IllegalStateException::new` trong ngữ cảnh `Supplier<...>` sẽ chọn constructor **không tham số**, không tự biết chuỗi thông báo nào nên truyền.

## 3. Lazy evaluation: Supplier chỉ chạy khi Optional rỗng

### 3.1. Trường hợp có giá trị

~~~java
Optional<String> present = Optional.of("Java");

String value = present.orElseThrow(() -> {
    System.out.println("Creating exception");
    return new IllegalStateException("Missing value");
});

System.out.println(value);
~~~

Đây là **đoạn minh họa**, với import `java.util.Optional`. Kết quả in **chỉ một dòng**:

~~~text
Java
~~~

Lambda hoàn toàn **không được gọi**. Vì vậy, dòng `"Creating exception"` không xuất hiện, và exception cũng không được tạo.

### 3.2. Trường hợp rỗng

~~~java
Optional<String> absent = Optional.empty();

String value = absent.orElseThrow(
        () -> new IllegalStateException("Missing value"));
~~~

Đây là đoạn minh họa. Khi `absent` rỗng, Supplier trả exception và `orElseThrow` ném nó. Lệnh gán cho `value` không hoàn thành bình thường; các câu lệnh sau đó không được chạy trừ khi có xử lý ngoại lệ thích hợp.

Ví dụ:

~~~java
try {
    Optional.<String>empty()
            .orElseThrow(() -> new IllegalStateException("Missing value"));
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
}
~~~

Stdout:

~~~text
Missing value
~~~

### 3.3. Cái gì thực sự là “lazy”?

Ở mã sau, biểu thức lambda được tạo ở thời điểm gọi phương thức, nhưng **thân Supplier** (ví dụ `new IllegalStateException(...)`) chỉ được thực thi khi Optional rỗng:

~~~java
String value = present.orElseThrow(
        () -> new IllegalStateException(buildMessage()));
~~~

Đây là đoạn minh họa. Nếu `present` chứa giá trị, `buildMessage()` **không** chạy, vì nó nằm **bên trong lambda**. Điều này giúp tránh xây thông báo dài, truy vấn metadata không cần thiết hoặc tạo exception khi không có lỗi.

Tuy nhiên, điều này **không có nghĩa tất cả biểu thức bên ngoài lambda đều lazy**. Ví dụ:

~~~java
String message = buildMessage();  // Được tính ngay.
String value = present.orElseThrow(
        () -> new IllegalStateException(message));
~~~

Ở đây `buildMessage()` đã được gọi **trước** khi `orElseThrow` được thực hiện. Nếu muốn chỉ tính thông báo khi thiếu dữ liệu, đặt phép xây thông báo trong Supplier.

> **Không đặt side effect nghiệp vụ bắt buộc trong exceptionSupplier**. Khi Optional có giá trị, Supplier không chạy; khi rỗng, lời gọi phương thức kết thúc bằng exception. Supplier chỉ nên dùng để **tạo một ngoại lệ mô tả lỗi**.

## 4. Đối chiếu orElse, orElseGet và orElseThrow

Ba API đều có từ Java 8 nhưng phản ánh những quyết định khác nhau:

| API | Khi có giá trị | Khi rỗng | Supplier có chạy khi có giá trị? |
| --- | --- | --- | --- |
| `orElse(T other)` | Trả giá trị trong Optional | Trả `other` | Không nhận Supplier; biểu thức tạo `other` được Java đánh giá trước khi gọi hàm |
| `orElseGet(Supplier<? extends T>)` | Trả giá trị trong Optional | Gọi Supplier lấy **giá trị thay thế** | Không |
| `orElseThrow(Supplier<? extends X>)` | Trả giá trị trong Optional | Gọi Supplier lấy **ngoại lệ**, rồi ném | Không |

### 4.1. orElse có thể tính fallback không cần thiết

~~~java
static String makeFallback() {
    System.out.println("fallback evaluated");
    return "DEFAULT";
}

// Biểu thức makeFallback() chạy trước khi gọi orElse:
String result = Optional.of("PRIMARY").orElse(makeFallback());
~~~

Đây là **mã minh họa trong một lớp Java**, không phải chương trình độc lập. Dù Optional có `"PRIMARY"`, Java vẫn phải đánh giá tham số `makeFallback()` trước khi gọi `orElse`; hàm in `"fallback evaluated"`.

Với `orElseGet`:

~~~java
String result = Optional.of("PRIMARY")
        .orElseGet(() -> makeFallback());
~~~

Hàm `makeFallback()` không chạy, vì chỉ được gọi trong nhánh rỗng. Tương tự, `orElseThrow(() -> new MyException(...))` chỉ xây exception khi rỗng.

**Không kết luận `orElse` luôn chậm hoặc luôn sai**: khi `other` là hằng số rẻ như `"UNKNOWN"`, `orElse("UNKNOWN")` là lựa chọn rõ ràng. Vấn đề là lựa chọn đúng ý nghĩa nghiệp vụ và chi phí tính toán.

### 4.2. Phân biệt fallback với lỗi

Chỉ cần tên mặc định:

~~~java
String displayName = userNameOptional.orElse("Anonymous");
~~~

Đây là đoạn minh họa; nếu `userNameOptional` rỗng, việc hiển thị `"Anonymous"` là quy tắc hợp lệ.

Cần lấy giá trị từ nguồn dự phòng:

~~~java
String displayName = userNameOptional.orElseGet(
        () -> loadFallbackDisplayName());
~~~

Đây là đoạn minh họa; `loadFallbackDisplayName` là hàm ứng dụng giả định.

Bắt buộc có dữ liệu, không được âm thầm tiếp tục:

~~~java
String displayName = userNameOptional.orElseThrow(
        () -> new IllegalStateException("Display name is required"));
~~~

Ba đoạn không thể hoán đổi tùy tiện. `orElseThrow` thể hiện rõ bất biến: **không có giá trị thì không thể hoàn thành thành công thao tác này**.

### 4.3. So sánh với kiểm tra isPresent() thủ công

Cách dài dòng:

~~~java
if (optional.isPresent()) {
    return optional.get();
}
throw new IllegalArgumentException("Missing input");
~~~

Đây là mã minh họa **trong một phương thức có kiểu trả về phù hợp**, không phải một chương trình độc lập. Với trường hợp bắt buộc có giá trị, có thể viết trực tiếp:

~~~java
return optional.orElseThrow(
        () -> new IllegalArgumentException("Missing input"));
~~~

Cách thứ hai gọn hơn, tránh tách bước kiểm tra và lấy giá trị và tự thể hiện loại lỗi tại chỗ. **Ở Java hiện đại, Javadoc của `Optional.get()` còn khuyến nghị `orElseThrow()` không tham số khi muốn ném `NoSuchElementException` mặc định.** Với thông điệp hay kiểu ngoại lệ cụ thể, chọn overload nhận Supplier.

## 5. Chọn loại ngoại lệ theo ý nghĩa nghiệp vụ

`orElseThrow` không có “loại ngoại lệ chuẩn” cho mọi ngữ cảnh. Chọn exception có ý nghĩa với caller:

| Tình huống | Ví dụ ngoại lệ hợp lý | Ghi chú |
| --- | --- | --- |
| Một tham số bắt buộc không hợp lệ hoặc thiếu | `IllegalArgumentException` | Thường là lỗi input/contract của method |
| Trạng thái đối tượng không đáp ứng điều kiện tiếp tục | `IllegalStateException` | Thể hiện trạng thái ứng dụng không hợp lệ |
| Truy cập một mục theo khóa nhưng không tồn tại | `NoSuchElementException` | Hữu ích cho tra cứu nội bộ theo khóa |
| Không tìm thấy một tài nguyên cần phải đọc theo hợp đồng I/O | `FileNotFoundException` hoặc một checked exception phù hợp | Phải cân nhắc trách nhiệm caller và `throws` |
| Lỗi domain đặc thù | `OrderNotFoundException`, `UserNotFoundException` do ứng dụng tự định nghĩa | Chỉ dùng khi thực sự có ý nghĩa nghiệp vụ và được xử lý nhất quán |

**Không dùng mọi trường hợp “không tìm thấy” để ném `NullPointerException`.** NPE thường chỉ ra việc sử dụng tham chiếu null không đúng; ném NPE cho một điều kiện domain thông thường có thể làm thông điệp khó hiểu.

**Không ném Exception/RuntimeException chung chung** nếu một loại cụ thể giúp caller xử lý hoặc giải thích lỗi tốt hơn.

Nếu đây là service web, việc chuyển `UserNotFoundException` thành HTTP 404 thuộc **tầng xử lý lỗi/API** của ứng dụng, không phải `Optional.orElseThrow` tự tạo HTTP response. Phân biệt rõ trách nhiệm để tránh gắn API Java vào một framework cụ thể.

### 5.1. Exception message nên có thông tin vừa đủ

Ví dụ:

~~~java
User user = repository.findById(userId)
        .orElseThrow(() ->
                new UserNotFoundException("User " + userId + " not found"));
~~~

Đây là **mã minh họa**, giả định repository và lớp exception thuộc ứng dụng. Message nên giúp debug mà không lộ password, token, secret, số định danh nhạy cảm hoặc dữ liệu người dùng không cần thiết. Khi xuất lỗi ra người dùng cuối, thông báo có thể được chuẩn hóa hoặc ẩn bớt ở tầng giao diện/API.

### 5.2. Constructor reference hoặc lambda?

~~~java
optional.orElseThrow(IllegalStateException::new);
optional.orElseThrow(() ->
        new IllegalStateException("Required data missing"));
~~~

Dùng constructor reference nếu không cần tham số và kiểu exception đủ mô tả lỗi. Dùng lambda nếu cần message, error code, cause hoặc giá trị ngữ cảnh. Cả hai đều **lười tạo exception** khi Optional có giá trị.

## 6. Unchecked exception và checked exception

### 6.1. Unchecked exception

Các ngoại lệ con của `RuntimeException` (ví dụ `IllegalStateException`, `IllegalArgumentException`, `NoSuchElementException`) không bắt buộc khai báo `throws` hoặc `catch`.

~~~java
String requireCode(Optional<String> code) {
    return code.orElseThrow(
            () -> new IllegalArgumentException("Code required"));
}
~~~

Đây là **phương thức minh họa** trong một lớp. Compiler cho phép không khai báo `throws IllegalArgumentException`, dù exception vẫn có thể xảy ra khi runtime.

### 6.2. Checked exception: kiểu X được compiler kiểm tra

Với checked exception như `IOException`, generic `X extends Throwable` cho phép `orElseThrow` ném chính checked exception đó:

~~~java
import java.io.IOException;
import java.util.Optional;

class Config {
    static String requireEndpoint(String raw) throws IOException {
        return Optional.ofNullable(raw)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .orElseThrow(() ->
                        new IOException("Endpoint configuration is missing"));
    }
}
~~~

Đây là **một lớp ví dụ có thể biên dịch độc lập**, nhưng chưa có `main` để chạy. Kiểu giá trị là `String`, kiểu ngoại lệ `X` được suy ra là `IOException`. Vì `IOException` là checked exception, `requireEndpoint` khai báo `throws IOException`.

Một caller có thể:

- Gọi trong phương thức cũng khai báo `throws IOException`.
- Hoặc bắt `IOException` bằng `try/catch` để xử lý/biến đổi thành lỗi tầng trên.

**Điểm dễ nhầm:** bản thân `Supplier.get()` không khai báo `throws IOException`. Lambda `() -> new IOException(...)` chỉ **tạo** đối tượng exception; chính `orElseThrow` mới **ném** đối tượng này. Vì vậy cách viết trên hợp lệ và compiler vẫn thực thi quy tắc checked exception ở bên gọi.

### 6.3. Cần biên dịch với loại checked exception cụ thể

Đoạn sau **không biên dịch** nếu method chứa nó không bắt/khai báo `IOException`:

~~~java
String endpoint = Optional.<String>empty()
        .orElseThrow(() -> new IOException("missing endpoint"));
~~~

Đây là **ví dụ phản ví dụ**: compiler yêu cầu xử lý checked exception. Có thể sửa bằng `throws IOException`, `try/catch` hoặc chọn một unchecked exception phù hợp **với hợp đồng API**.

**Không** đổi một checked exception thành unchecked chỉ để bỏ qua compiler mà không cân nhắc caller có cần xử lý lỗi có thể khôi phục hay không.

### 6.4. Bắt đúng ngoại lệ, đừng bắt Throwable

`X extends Throwable` là giới hạn kiểu tổng quát của Java API. Nó **không có nghĩa** ứng dụng nên tùy tiện tạo các subclass của `Error` hoặc viết `catch (Throwable)` để xử lý mọi sự cố. Thực tế hãy chọn subclass của `Exception` hoặc `RuntimeException` theo tình huống.

## 7. Chương trình Java hoàn chỉnh, chạy được

Lưu thành **OptionalOrElseThrowDemo.java**. Ví dụ kiểm chứng: giá trị có sẵn không gọi Supplier, giá trị rỗng mới tạo unchecked exception, method reference của constructor, tra cứu đối tượng, chuỗi xử lý `map`/`filter` và checked exception.

~~~java
import java.io.IOException;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class OptionalOrElseThrowDemo {

    static final class User {
        private final long id;
        private final String name;

        User(long id, String name) {
            this.id = id;
            this.name = name;
        }

        String getName() {
            return name;
        }
    }

    static Optional<User> findUserById(long id) {
        if (id == 7L) {
            return Optional.of(new User(7L, "Lan"));
        }
        return Optional.empty();
    }

    static String requireEndpoint(String raw) throws IOException {
        return Optional.ofNullable(raw)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .orElseThrow(() ->
                        new IOException("Endpoint configuration is missing"));
    }

    public static void main(String[] args) throws IOException {
        AtomicInteger supplierCalls = new AtomicInteger();

        Supplier<IllegalArgumentException> missingCode = () -> {
            supplierCalls.incrementAndGet();
            return new IllegalArgumentException("Code is required");
        };

        String present = Optional.of("READY")
                .orElseThrow(missingCode);
        System.out.println("present = " + present);
        System.out.println("supplier calls after present = "
                + supplierCalls.get());

        try {
            Optional.<String>empty().orElseThrow(missingCode);
        } catch (IllegalArgumentException ex) {
            System.out.println("empty exception = " + ex.getMessage());
        }
        System.out.println("supplier calls after empty = "
                + supplierCalls.get());

        User user = findUserById(7L)
                .orElseThrow(() ->
                        new NoSuchElementException("User 7 not found"));
        System.out.println("found user = " + user.getName());

        try {
            findUserById(8L).orElseThrow(() ->
                    new NoSuchElementException("User 8 not found"));
        } catch (NoSuchElementException ex) {
            System.out.println("lookup exception = " + ex.getMessage());
        }

        String normalized = Optional.of("  java  ")
                .map(String::trim)
                .filter(s -> s.length() >= 3)
                .orElseThrow(() ->
                        new IllegalStateException("Invalid normalized value"));
        System.out.println("normalized = " + normalized);

        try {
            Optional.<String>empty()
                    .orElseThrow(IllegalStateException::new);
        } catch (IllegalStateException ex) {
            System.out.println("constructor reference = "
                    + ex.getClass().getSimpleName());
        }

        System.out.println("endpoint = "
                + requireEndpoint("  https://example.test  "));

        try {
            requireEndpoint("   ");
        } catch (IOException ex) {
            System.out.println("checked exception = " + ex.getMessage());
        }
    }
}
~~~

Biên dịch bằng **JDK 17+** nhưng yêu cầu ngôn ngữ/API tương thích Java 8:

~~~bash
javac --release 8 OptionalOrElseThrowDemo.java
java OptionalOrElseThrowDemo
~~~

**Stdout chính xác:**

~~~text
present = READY
supplier calls after present = 0
empty exception = Code is required
supplier calls after empty = 1
found user = Lan
lookup exception = User 8 not found
normalized = java
constructor reference = IllegalStateException
endpoint = https://example.test
checked exception = Endpoint configuration is missing
~~~

### Đối chiếu kết quả từng bước

1. `Optional.of("READY")` có giá trị nên `orElseThrow(missingCode)` trả `"READY"` mà **không gọi** Supplier. `supplierCalls` bằng `0`.
2. `Optional.empty()` làm Supplier chạy, tăng bộ đếm lên `1`, tạo `IllegalArgumentException`. `catch` bắt exception và in message; không có chuỗi mặc định được trả.
3. Tra cứu id `7` trả `User` có tên `Lan`; id `8` trả `Optional.empty()` nên exception có đúng thông báo `User 8 not found`.
4. `map(String::trim)` đổi `"  java  "` thành `"java"`; `filter` giữ lại vì độ dài `4 >= 3`. Do đó Supplier trong `orElseThrow` không chạy.
5. `IllegalStateException::new` là Supplier tạo exception bằng constructor không tham số. In tên class thay vì in stack trace để stdout ổn định.
6. `requireEndpoint` nhận giá trị có nội dung sau khi `trim` nên trả URL. Khi chuỗi chỉ toàn khoảng trắng, `filter` tạo Optional rỗng và `orElseThrow` ném `IOException`.
7. Mọi thông báo in đều do mã tự xác định; kết quả không phụ thuộc thời gian, locale, truy cập mạng hay phiên bản implementation `Optional`.

## 8. optional.map/filter/flatMap có thể dẫn đến nhánh throw

`orElseThrow` thường nằm **cuối chuỗi** xử lý Optional. Điều kiện “rỗng” không chỉ do nguồn ban đầu:

- `Optional.empty()`: đã rỗng từ đầu.
- `Optional.ofNullable(null)`: chuyển null thành Optional rỗng.
- `optional.filter(predicate)`: nếu có giá trị nhưng predicate trả `false`, kết quả trở thành Optional rỗng.
- `optional.map(mapper)`: nếu có giá trị mà mapper trả `null`, `map` cho Optional rỗng theo hợp đồng.
- `optional.flatMap(mapper)`: mapper trả `Optional.empty()` cũng làm kết quả rỗng.

Ví dụ:

~~~java
String code = Optional.ofNullable(rawCode)
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .orElseThrow(() ->
                new IllegalArgumentException("Code must not be blank"));
~~~

Đây là **đoạn minh họa** giả định `rawCode` là `String` hoặc `null`. Lỗi `"Code must not be blank"` xảy ra không chỉ khi rawCode là null mà còn khi đầu vào chỉ có whitespace.

Nếu cần phân biệt các nguyên nhân (null, blank, không tìm thấy, không đủ quyền), đừng gom hết vào một Optional rỗng rồi cố suy ra nguyên nhân tại `orElseThrow`. Thay vào đó, hãy đặt xác thực đúng tầng, tạo thông điệp phù hợp hoặc dùng một kiểu kết quả giàu thông tin hơn khi cần.

### 8.1. Optional.of(null) khác ofNullable(null)

~~~java
Optional<String> safe = Optional.ofNullable(null); // Optional.empty()
Optional<String> invalid = Optional.of(null);      // NPE ngay ở of(...)
~~~

Đây là **đoạn minh họa**. Ở dòng thứ hai, exception được ném **trước khi có `orElseThrow`**. Không hiểu nhầm rằng mọi trường hợp null đều được xử lý bởi Supplier; Supplier chỉ được hỏi khi có một **Optional instance hợp lệ ở trạng thái empty**.

### 8.2. Biến Optional không được tự là null

Không viết:

~~~java
Optional<String> broken = null;
broken.orElseThrow(IllegalStateException::new); // NPE lúc gọi method.
~~~

Java không thể gọi method trên tham chiếu null. `orElseThrow` không chữa lỗi thiết kế “Optional variable = null”. API Optional chủ yếu được thiết kế làm **kiểu trả về** khi không có kết quả là điều có thể xảy ra; trong mã ứng dụng nên trả `Optional.empty()` thay vì trả `null` cho chính đối tượng `Optional`.

### 8.3. Optional có giá trị null không?

`Optional.of(null)` ném NPE, và `Optional.ofNullable(null)` rỗng. Vì vậy một `Optional<T>` hợp lệ chỉ có thể chứa **giá trị không null** hoặc ở trạng thái empty; `orElseThrow` thành công khi present trả giá trị không null.

## 9. Trường hợp Supplier bị null hoặc trả null

Đây là hai lỗi cấu hình Supplier khác nhau. Với **Optional rỗng**:

~~~java
Optional.<String>empty().orElseThrow(null);
~~~

Sẽ ném `NullPointerException` vì Supplier cần thiết nhưng `null`.

Tương tự:

~~~java
Optional.<String>empty().orElseThrow(() -> null);
~~~

Supplier được gọi nhưng **không cung cấp một exception hợp lệ**. Trên JDK hiện hành, `orElseThrow` ném `NullPointerException` khi Supplier trả null.

**Lưu ý thời điểm:** Nếu Optional có giá trị, Supplier không được gọi; việc `orElseThrow` nhận Supplier null cũng không bị truy cập ở nhánh thành công. Tuy nhiên, **đừng cố ý truyền null Supplier**: giá trị Optional có thể thay đổi giữa các đường gọi khác nhau và mã trở nên khó bảo trì.

### 9.1. Không tái sử dụng một exception instance toàn cục

Ví dụ không nên làm:

~~~java
private static final IllegalStateException SHARED =
        new IllegalStateException("Data missing");

// Không khuyến khích: trả về chính một instance Exception cho mọi lần lỗi.
String value = optional.orElseThrow(() -> SHARED);
~~~

Đây là **mã minh họa rút gọn trong lớp có `optional`**. Exception thường nên tạo mới cho mỗi lần lỗi, vì instance mang trạng thái như stack trace và có thể mang cause/suppressed information. Dùng Supplier tạo mới `() -> new ...` giúp thông tin lỗi và vị trí phát sinh phù hợp hơn, giảm nhầm lẫn giữa các lần thất bại.

### 9.2. Không đưa thao tác tốn chi phí khác thường vào Supplier

Mặc dù Supplier chạy lazily, nhánh thiếu dữ liệu vẫn có thể xảy ra thường xuyên. Không làm một cuộc gọi mạng hoặc truy vấn DB chỉ để **xây thông báo exception** nếu không thực sự cần. Khi đường đi lỗi có tần suất cao, chi phí tạo stack trace/logging có thể đáng kể; hãy đánh giá lại chính sách xử lý lỗi hoặc biểu diễn “không có kết quả” nếu đó là tình huống bình thường.

## 10. Tương thích Java 8 và API ở Java hiện đại

Điểm dễ nhầm do cùng tên phương thức:

| API | Bản Java bắt đầu | Ý nghĩa |
| --- | --- | --- |
| `Optional<T>.orElseThrow(Supplier<? extends X>)` | **Java 8** | Chọn loại/đối tượng ngoại lệ và message khi Optional rỗng. |
| `Optional<T>.orElseThrow()` | **Java 10** | Không truyền Supplier; khi rỗng ném `NoSuchElementException`. |
| `Optional<T>.get()` | Java 8 | Có giá trị thì trả, rỗng thì ném `NoSuchElementException`; Javadoc hiện đại ưu tiên dạng `orElseThrow()` cho trường hợp này. |
| `Optional<T>.orElseGet(Supplier<? extends T>)` | Java 8 | Chọn giá trị dự phòng, **không** ném ngoại lệ qua cơ chế orElseThrow. |
| `Optional<T>.isEmpty()` | **Java 11** | Kiểm tra không có giá trị; **không phải** Java 8. |
| `Optional<T>.stream()` | **Java 9** | Chuyển Optional thành stream 0 hoặc 1 phần tử; **không phải** Java 8. |

Vì đây là bài trong module **Java 8**, ví dụ runnable dùng **`orElseThrow(Supplier)`**, `Optional.of/ofNullable`, `map` và `filter`, tất cả đều có từ Java 8. Khi codebase yêu cầu tương thích Java 8, không dùng `orElseThrow()` không tham số, `isEmpty()` hay `Optional.stream()`.

Trong dự án Java 17/21/25/26, `Optional.orElseThrow()` không tham số là lựa chọn tốt nếu chỉ cần `NoSuchElementException` mặc định. Khi cần message hoặc exception tùy biến, overload **nhận Supplier vẫn là cách hiện hành** và không phải API legacy.

### 10.1. OptionalInt, OptionalLong, OptionalDouble

Các kiểu primitive Optional (`OptionalInt`, `OptionalLong` và `OptionalDouble`) cũng có overload nhận Supplier ngoại lệ từ Java 8. Ví dụ:

~~~java
int port = OptionalInt.empty()
        .orElseThrow(() -> new IllegalStateException("Port missing"));
~~~

Đây là **đoạn minh họa** với import `java.util.OptionalInt`. Khi OptionalInt rỗng, ngoại lệ được ném. Java 8 không có bản `OptionalInt.orElseThrow()` không đối số tương tự phiên bản đời sau; hãy kiểm tra mức Java target nếu sử dụng các overload mới.

### 10.2. Một lần tra cứu, một kết quả rõ ràng

Đừng làm:

~~~java
// Không tốt: thực hiện hai lần tra cứu.
if (!repository.findById(id).isPresent()) {
    throw new NoSuchElementException("Missing");
}
User user = repository.findById(id).get();
~~~

Đây là **mã minh họa**; `repository` và `User` thuộc ứng dụng. Việc tra cứu lặp có thể tốn chi phí và trả kết quả khác nếu dữ liệu thay đổi giữa các lần gọi. Viết:

~~~java
User user = repository.findById(id)
        .orElseThrow(() -> new NoSuchElementException("Missing"));
~~~

Bản này chỉ dùng kết quả của **một lần tìm kiếm**, không có bước kiểm tra/rút giá trị tách biệt.

## 11. Các lỗi phổ biến và hướng sửa

### Lỗi 1 — Dùng orElseThrow ngay cả khi thiếu dữ liệu là bình thường

Nếu không có kết quả là tình huống hợp lệ, hãy trả `Optional` cho caller hoặc dùng fallback phù hợp. Ném exception trong đường xử lý thường xuyên có thể khiến flow khó hiểu và tốn chi phí.

### Lỗi 2 — Hiểu Supplier sẽ chạy ngay khi truyền vào

Lambda `() -> new MyException(...)` được cung cấp cho API; phần **xây exception** chỉ chạy nếu Optional rỗng. Đừng kỳ vọng nó được gọi khi present.

### Lỗi 3 — Tính thông báo trước lambda

~~~java
String message = expensiveMessageBuilder();
String result = optional.orElseThrow(
        () -> new IllegalStateException(message));
~~~

**Không tận dụng tính lazy** của thông báo. Hãy đưa `expensiveMessageBuilder()` vào thân lambda nếu chỉ cần kết quả khi lỗi và hàm phù hợp để gọi ở đó.

### Lỗi 4 — Truyền exception instance thay Supplier

~~~java
// Sai kiểu tham số:
optional.orElseThrow(new IllegalStateException("missing"));
~~~

`orElseThrow` yêu cầu `Supplier<? extends Throwable>`, không nhận trực tiếp một đối tượng exception. Đúng:

~~~java
optional.orElseThrow(() -> new IllegalStateException("missing"));
~~~

### Lỗi 5 — Cố dùng checked exception nhưng không khai báo/catch

Nếu Supplier trả `IOException`, Java yêu cầu xử lý checked exception ở caller hoặc method chứa lời gọi. Xác định loại exception theo hợp đồng ứng dụng.

### Lỗi 6 — Chọn exception quá chung chung

`new RuntimeException("not found")` ít thông tin hơn `NoSuchElementException` hoặc exception nghiệp vụ có tên. Chọn loại và message hữu ích, nhưng không lộ dữ liệu nhạy cảm.

### Lỗi 7 — Dùng null để biểu diễn Optional rỗng

`Optional<String> opt = null` không giống `Optional.empty()`. Lời gọi `opt.orElseThrow(...)` trên null ném NPE **trước khi Supplier có cơ hội chạy**.

### Lỗi 8 — Dùng get() rồi ném exception ở chỗ khác

`get()` trên Optional rỗng đã ném `NoSuchElementException`, khó tùy biến message. Với yêu cầu ngoại lệ cụ thể, dùng `orElseThrow(Supplier)` trực tiếp. Với JDK 10+, nếu chỉ cần ngoại lệ mặc định, `orElseThrow()` là API rõ nghĩa.

### Lỗi 9 — Bắt exception rồi trả null mà không có hợp đồng

~~~java
try {
    return optional.orElseThrow(
            () -> new IllegalStateException("missing"));
} catch (IllegalStateException ex) {
    return null; // Trái với mục tiêu "phải có giá trị".
}
~~~

Đây là **đoạn minh họa trong một method trả về reference type**. Nếu caller không được phép nhận null, việc bắt rồi nuốt lỗi có thể che mất lỗi domain. Bắt khi có chiến lược khôi phục, chuyển đổi lỗi hoặc báo cáo phù hợp.

### Lỗi 10 — Không phân biệt lý do Optional.empty()

Chuỗi `find(...).map(...).filter(...).orElseThrow(...)` có thể rỗng từ nhiều bước khác nhau. Nếu cần thông báo nguyên nhân chính xác, đừng cố suy đoán nguyên nhân chỉ từ trạng thái rỗng cuối cùng; thiết kế bước validation/exception riêng.

### Lỗi 11 — Lạm dụng Optional cho mọi field hoặc tham số

Optional được thiết kế chủ yếu cho kiểu **giá trị trả về** có thể thiếu. Không nhất thiết đưa Optional vào tất cả field, setter, constructor parameter hoặc serializer; đánh giá contract của public API, validation và cách framework xử lý Optional.

### Lỗi 12 — Kỳ vọng Supplier sẽ trả một ngoại lệ nhưng lại trả null

`() -> null` không cung cấp exception hợp lệ; khi Optional rỗng, kết quả là `NullPointerException`. Luôn tạo một exception instance có ý nghĩa.

## 12. Quy tắc chọn nhanh

1. **Có thể không có dữ liệu và caller cần tự quyết định:** trả nguyên `Optional<T>`.
2. **Không có dữ liệu vẫn có giá trị dự phòng cố định:** `orElse(defaultValue)`.
3. **Giá trị dự phòng cần tính lazily:** `orElseGet(() -> computeFallback())`.
4. **Không có dữ liệu là lỗi nghiệp vụ và cần ngoại lệ tùy biến:** `orElseThrow(() -> new DomainException(...))`.
5. **Cần checked exception:** `orElseThrow(() -> new IOException(...))` và khai báo/bắt ngoại lệ theo hợp đồng.
6. **Chỉ cần NoSuchElementException mặc định trên Java 10+:** `orElseThrow()` không đối số.
7. **Code phải chạy trên Java 8:** dùng overload có Supplier; không sử dụng overload không đối số.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Optional.of("A").orElseThrow(() -> new IllegalStateException("missing"))` trả gì và Supplier có chạy không?

**Đáp án:** Trả `"A"`. Supplier không được gọi, nên exception không được tạo.

**Câu 2.** `Optional.<String>empty().orElseThrow(() -> new IllegalArgumentException("bad"))` làm gì?

**Đáp án:** Gọi Supplier tạo `IllegalArgumentException("bad")`, rồi ném exception đó. Không trả `null`.

**Câu 3.** `orElseThrow(IllegalStateException::new)` khác `orElseThrow(() -> new IllegalStateException("bad"))` ở đâu?

**Đáp án:** Cả hai là Supplier, nhưng constructor reference không có tham số không gắn message tùy biến; lambda tạo exception có message `"bad"`.

**Câu 4.** Tại sao `orElse(expensiveFallback())` có thể chạy hàm `expensiveFallback` dù Optional chứa giá trị?

**Đáp án:** Java đánh giá các đối số của method trước khi gọi `orElse`. Nếu cần fallback lazy, dùng `orElseGet(() -> expensiveFallback())`.

**Câu 5.** Có thể dùng `IOException` với `orElseThrow` từ Java 8 không?

**Đáp án:** Có. Generic `X extends Throwable` cho phép checked exception, nhưng compiler yêu cầu `catch` hoặc `throws IOException` ở nơi gọi thích hợp.

**Câu 6.** Một `Optional<String>` rỗng nhận `orElseThrow(() -> null)` sẽ ra sao?

**Đáp án:** Ném `NullPointerException` vì Supplier không cung cấp ngoại lệ hợp lệ.

**Câu 7.** Bản `Optional.orElseThrow()` không tham số có từ Java 8 không?

**Đáp án:** Không. Nó được bổ sung từ Java 10. Trên Java 8, dùng `orElseThrow(Supplier)`.

**Câu 8.** Khi `Optional.ofNullable(raw).map(String::trim).filter(s -> !s.isEmpty())` rỗng, có chắc raw ban đầu là null không?

**Đáp án:** Không. Raw có thể null hoặc chuỗi chỉ chứa khoảng trắng sau khi trim. Cả hai có thể dẫn đến Optional rỗng.

**Câu 9.** Khi nên dùng `orElseThrow` thay cho `orElseGet`?

**Đáp án:** Khi **không có giá trị là lỗi khiến thao tác không được hoàn thành thành công**, thay vì có một cách cung cấp giá trị dự phòng hợp lệ.

## 14. Tóm tắt

- **`Optional<T>.orElseThrow(Supplier<? extends X>)`** trả `T` khi có; khi rỗng, gọi Supplier tạo **`X extends Throwable`** và ném ngoại lệ đó.
- Supplier **chỉ được gọi ở nhánh rỗng**. Đặt việc xây exception và message trong lambda nếu muốn lazy.
- **Checked exception** được hỗ trợ; phải xử lý theo quy tắc `throws`/`catch` của Java.
- **Không nhầm `orElse` (fallback đánh giá ngay), `orElseGet` (fallback giá trị lazy), `orElseThrow` (ngoại lệ lazy).**
- **Chọn exception có ý nghĩa**, message hữu ích và không tiết lộ dữ liệu nhạy cảm; không dùng exception như một fallback cho trường hợp thiếu dữ liệu bình thường.
- `Optional.empty()` không phải `Optional` reference bằng null. `Optional.of(null)` ném NPE trước khi gọi `orElseThrow`.
- **Overload nhận Supplier có từ Java 8 và vẫn là API hiện hành.** Bản không tham số có từ Java 10, phù hợp khi chỉ cần `NoSuchElementException` mặc định.

### Tài liệu chính thức

- [Oracle Java SE 8 — Optional, orElseThrow(Supplier)](https://docs.oracle.com/javase/8/docs/api/java/util/Optional.html)
- [Oracle Java SE 26 — Optional (hai overload orElseThrow và API Note của get)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html)
- [Oracle Java SE 8 — Supplier](https://docs.oracle.com/javase/8/docs/api/java/util/function/Supplier.html)
- [Oracle Java SE 8 — IOException](https://docs.oracle.com/javase/8/docs/api/java/io/IOException.html)
