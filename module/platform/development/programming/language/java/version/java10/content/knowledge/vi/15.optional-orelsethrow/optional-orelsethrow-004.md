# Phân biệt `Optional.orElseThrow()` không đối số với `orElseThrow(Supplier)` (Java 10+)

## 1. Mục tiêu

`java.util.Optional<T>` biểu diễn một giá trị **có thể có hoặc không có**. Khi muốn lấy giá trị nhưng **không chấp nhận trường hợp rỗng**, Java cung cấp hai overload cùng tên:

~~~java
T orElseThrow()

<X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
~~~

Chúng có cùng quy tắc khi `Optional` **có giá trị**: trả về giá trị `T` đang chứa. Sự khác nhau xuất hiện khi `Optional` **rỗng**:

- **`orElseThrow()` không đối số:** tự ném `NoSuchElementException`. Overload này được bổ sung từ **Java 10**.
- **`orElseThrow(exceptionSupplier)`:** gọi `Supplier` để tạo một ngoại lệ do lập trình viên chỉ định rồi ném ngoại lệ đó. Overload này đã có từ **Java 8** và vẫn được sử dụng trong Java hiện đại.

Ví dụ nhanh:

~~~java
Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();

System.out.println(present.orElseThrow()); // Java

// absent.orElseThrow();
// Ném NoSuchElementException.

String value = absent.orElseThrow(
        () -> new IllegalArgumentException("Thiếu tên người dùng"));
// Ném IllegalArgumentException với thông điệp cụ thể.
~~~

Đoạn trên là **mã minh họa trong phương thức**, cần import `java.util.Optional`. Lời gọi cuối **cố ý ném ngoại lệ** và phải được bắt hoặc để lan truyền ở nơi sử dụng thật; chương trình chạy độc lập ở mục 7 có xử lý chính xác.

**Mục tiêu bài học:** chọn overload đúng với hợp đồng API, hiểu khi nào `Supplier` chạy, sử dụng checked exception hợp lệ, phân biệt với `get()`, `orElse()`, `orElseGet()`, và tránh che giấu sự vắng mặt của dữ liệu.

## 2. Bảng quyết định nhanh

| Tình trạng `Optional<T>` | `orElseThrow()` | `orElseThrow(supplier)` |
| --- | --- | --- |
| Có giá trị `T` | Trả về chính giá trị `T` | Trả về chính giá trị `T`, **không gọi supplier** |
| Rỗng | Ném `NoSuchElementException` | Gọi supplier, rồi ném ngoại lệ do supplier trả về |
| Muốn tùy chỉnh loại ngoại lệ | Không | Có |
| Muốn thông điệp lỗi chứa ID/ngữ cảnh | Không có tham số tùy chỉnh | Có, ví dụ `() -> new UserNotFoundException(id)` |
| Muốn ném checked exception | Bản thân phương thức ném unchecked `NoSuchElementException` | Có thể trả một checked exception, theo quy tắc `throws` hoặc `catch` |
| Mốc phiên bản | Java 10+ | Java 8+ |
| Rủi ro khi supplier là `null` | Không có supplier | Khi Optional rỗng, ném `NullPointerException` |
| Rủi ro khi supplier trả `null` | Không áp dụng | Khi Optional rỗng, kết quả là `NullPointerException` |

`Optional.empty()` không chứa `null` như một value bình thường; nó biểu thị **không có value**. `Optional.ofNullable(null)` cũng tạo `Optional.empty()`, vì thế cùng đi vào nhánh ném ngoại lệ.

## 3. `orElseThrow()` không đối số: ngắn, rõ, cố định ngoại lệ

Chữ ký:

~~~java
public T orElseThrow()
~~~

Hành vi:
1. Nếu có value, trả lại value.
2. Nếu rỗng, ném `java.util.NoSuchElementException` (*unchecked exception*).

Ví dụ:

~~~java
var name = Optional.of("An");
System.out.println(name.orElseThrow()); // An

var missing = Optional.<String>empty();
// missing.orElseThrow(); // Ném NoSuchElementException
~~~

Viết `Optional.<String>empty()` là cách ghi rõ kiểu generic của `Optional` rỗng. Không nên suy luận rằng một `Optional` rỗng mang giá trị `null` kiểu `String`; nó không chứa value nào.

**Khi nào phù hợp?** Khi sự vắng mặt là vi phạm một tiền điều kiện đã biết của đoạn code, và **ngoại lệ chung `NoSuchElementException` đã đủ** thể hiện điều đó. Ví dụ, thuật toán vừa bảo đảm có kết quả bằng bước lọc/kiểm tra ở trên, còn `orElseThrow()` đóng vai trò “phải có kết quả”.

~~~java
int max = List.of(3, 8, 2).stream()
        .max(Integer::compareTo)
        .orElseThrow();

System.out.println(max); // 8
~~~

Đoạn này cần import `java.util.List`, và `max` có giá trị vì nguồn không rỗng. Nếu nguồn là một stream rỗng, `max` trả `Optional.empty()`, và `orElseThrow()` ném `NoSuchElementException`.

**Không nên dựa vào văn bản chi tiết của thông báo từ ngoại lệ mặc định** như một hợp đồng nghiệp vụ. Loại ngoại lệ `NoSuchElementException` mới là quy tắc được bảo đảm. Khi ứng dụng cần thông báo có mã truy vấn hoặc lý do cụ thể, chọn overload `Supplier`.

### Quan hệ với `Optional.get()`

`Optional.get()` (đã có từ Java 8) cũng trả value hoặc ném `NoSuchElementException` khi rỗng. Trong tài liệu API hiện đại, **`orElseThrow()` là cách thể hiện rõ ý định hơn `get()`**: đọc mã sẽ hiểu ngay “nếu không có thì ném ngoại lệ”.

~~~java
var title = Optional.of("Guide");
String a = title.get();          // Hợp lệ, vẫn tồn tại
String b = title.orElseThrow();  // Hợp lệ, diễn đạt ý định rõ
~~~

Không phải `get()` đã biến mất khỏi JDK; điều cần tránh là gọi `get()` **không suy xét trạng thái rỗng** hoặc giả định nó sẽ trả về `null`.

## 4. `orElseThrow(Supplier)`: chọn ngoại lệ phù hợp nghiệp vụ

Chữ ký tổng quát:

~~~java
public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
~~~

`Supplier` nằm trong `java.util.function`. Nó đại diện cho một hàm **không nhận đối số** và **trả về một object**; ở đây object phải là một `Throwable` có thể được ném.

Cách dùng với lambda:

~~~java
Optional<String> result = Optional.empty();

String name = result.orElseThrow(
        () -> new IllegalArgumentException("Không tìm thấy tên"));
~~~

Cách dùng với constructor reference:

~~~java
String name = result.orElseThrow(IllegalStateException::new);
~~~

Cả hai đoạn trên **cố ý gây ngoại lệ** khi `result` rỗng, không phải chương trình chạy hoàn chỉnh không bắt lỗi.

Sự khác biệt về cách biểu đạt:
- `IllegalStateException::new` phù hợp khi chỉ cần loại ngoại lệ, không cần nội dung tùy biến.
- `() -> new IllegalArgumentException("Không tìm thấy tên")` phù hợp khi cần thông điệp cụ thể.
- `() -> new UserNotFoundException(userId)` phù hợp khi hệ thống có exception nghiệp vụ riêng, cho phép tầng cao hơn xử lý đúng loại lỗi.

Ví dụ ở một phương thức tìm người dùng:

~~~java
static User requireUser(String userId) {
    return findUser(userId)
            .orElseThrow(() ->
                    new UserNotFoundException("User " + userId + " not found"));
}
~~~

Đây là đoạn minh họa: ứng dụng cần định nghĩa `User`, `UserNotFoundException` và `findUser(...)`. Chương trình hoàn chỉnh ở mục 7 sẽ đưa ra phiên bản có đầy đủ kiểu và phương thức.

**Ưu điểm:** exception có thể mang ID, mã nghiệp vụ hoặc ngữ cảnh hữu ích để xử lý. Không nên đưa mật khẩu, token bí mật hoặc dữ liệu cá nhân nhạy cảm vào thông báo lỗi một cách vô tình.

## 5. Khi nào `Supplier` thật sự được gọi?

**Chỉ khi `Optional` rỗng.**

Ví dụ:

~~~java
AtomicInteger created = new AtomicInteger();

String name = Optional.of("An").orElseThrow(() -> {
    created.incrementAndGet();
    return new IllegalArgumentException("Missing");
});

System.out.println(name);          // An
System.out.println(created.get()); // 0
~~~

`AtomicInteger` được import từ `java.util.concurrent.atomic`; đoạn minh họa cần import `Optional`.

Sau đó:

~~~java
try {
    Optional.<String>empty().orElseThrow(() -> {
        created.incrementAndGet();
        return new IllegalArgumentException("Missing");
    });
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage()); // Missing
}

System.out.println(created.get()); // 1
~~~

`Supplier` **được truyền như một hàm**. Khi Optional có value, Java **không thực thi thân lambda**, do đó không cần tạo exception object và không chạy các phép tính xây thông báo bên trong lambda.

### Đừng tạo exception trước rồi coi đó là lazy

Cách dùng đúng:

~~~java
String user = lookupUserName(id).orElseThrow(
        () -> new IllegalArgumentException("Unknown user: " + id));
~~~

Đây là snippet cần khai báo `lookupUserName(String)` và `id`; chỉ minh họa ý tưởng.

Không viết:

~~~java
// String user = lookupUserName(id).orElseThrow(
//         new IllegalArgumentException("Unknown user"));
// Lỗi biên dịch: cần Supplier, không phải đối tượng exception.
~~~

Nếu thực hiện phép toán đắt đỏ **trước** khi tạo lambda, phần việc đó vẫn có thể chạy ngay:

~~~java
String detailedMessage = buildLargeErrorMessage(id);
String user = lookupUserName(id).orElseThrow(
        () -> new IllegalArgumentException(detailedMessage));
~~~

Dù `Optional` có giá trị, lệnh `buildLargeErrorMessage(id)` phía trước **đã chạy**. Để thật sự lazy, chuyển phép xây dựng thông điệp vào lambda:

~~~java
String user = lookupUserName(id).orElseThrow(
        () -> new IllegalArgumentException(buildLargeErrorMessage(id)));
~~~

**Kết luận:** tính lazy chỉ bảo đảm phần việc nằm **bên trong `Supplier`** không chạy khi Optional có value. Biểu thức chuẩn bị ở bên ngoài vẫn được đánh giá bình thường.

## 6. Checked exception: khác biệt quan trọng nhất khi chọn overload

`NoSuchElementException`, `IllegalArgumentException` và `IllegalStateException` đều thuộc nhóm **unchecked** (`RuntimeException`), không bắt buộc khai báo `throws`.

Trong khi đó, overload nhận `Supplier` có tham số kiểu **`X extends Throwable`** và khai báo **`throws X`**, nên có thể ném checked exception:

~~~java
static String requireConfigValue(String key) throws IOException {
    Optional<String> value = readConfig(key);
    return value.orElseThrow(
            () -> new IOException("Missing configuration: " + key));
}
~~~

Đây là snippet minh họa, cần định nghĩa `readConfig(String)` trả `Optional<String>` và import `java.io.IOException`.

Trong ví dụ:
- Nếu `readConfig(key)` trả value, phương thức trả chính value đó.
- Nếu rỗng, supplier tạo một `IOException`, rồi `orElseThrow` ném nó.
- Vì `IOException` là checked exception, phương thức `requireConfigValue` phải **khai báo `throws IOException`** hoặc bắt ngoại lệ bên trong.

Một đoạn xử lý ở nơi gọi:

~~~java
try {
    String config = requireConfigValue("timeout");
    System.out.println(config);
} catch (IOException ex) {
    System.out.println("Config error: " + ex.getMessage());
}
~~~

Đây là mã minh họa trong phương thức, không phải ứng dụng đầy đủ.

**Quy tắc biên dịch:** generic method suy ra kiểu ngoại lệ `X` từ lambda/constructor reference. Nếu supplier tạo checked exception, Java kiểm tra nghĩa vụ `catch`/`throws` ở lời gọi. Không thể “lách” checked exception bằng cách dùng `var` hoặc `Optional`.

Không nên chọn loại exception chỉ dựa trên sở thích:
- `NoSuchElementException`: không có giá trị như điều kiện tối thiểu của phép đọc.
- `IllegalArgumentException`: đối số/tên định danh không hợp lệ theo hợp đồng.
- `IllegalStateException`: trạng thái hiện tại không đáp ứng tiền điều kiện.
- `IOException` hoặc exception nghiệp vụ: phù hợp khi caller cần xử lý tình huống thiếu dữ liệu theo một hợp đồng rõ ràng.

Điều quan trọng là **ý nghĩa lỗi trong API**, không phải luôn dùng exception càng cụ thể càng tốt.

## 7. Chương trình Java 17+ hoàn chỉnh: cả hai overload và tính lazy

Tạo tệp **OptionalOrElseThrowDemo.java**:

~~~java
import java.io.IOException;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalOrElseThrowDemo {

    record User(String id, String name) {}

    static Optional<User> findUser(String id) {
        if ("u-1".equals(id)) {
            return Optional.of(new User("u-1", "An"));
        }
        return Optional.empty();
    }

    static User requireUser(String id) {
        return findUser(id).orElseThrow(
                () -> new IllegalArgumentException("Missing user: " + id));
    }

    static String findRequiredName(String id) throws IOException {
        return findUser(id)
                .map(User::name)
                .orElseThrow(
                        () -> new IOException("Name not found for " + id));
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("Java");
        Optional<String> absent = Optional.empty();

        // Java 10+: không đối số, giá trị có sẵn.
        System.out.println("no-arg present = " + present.orElseThrow());

        // Rỗng: no-arg ném NoSuchElementException.
        try {
            absent.orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println("no-arg empty = "
                    + ex.getClass().getSimpleName());
        }

        // Supplier không được chạy nếu Optional có giá trị.
        var supplierCalls = new AtomicInteger();

        String value = present.orElseThrow(() -> {
            supplierCalls.incrementAndGet();
            return new IllegalStateException("unused");
        });
        System.out.println("custom present = " + value);
        System.out.println("supplier calls with value = "
                + supplierCalls.get());

        // Khi rỗng, Supplier chạy và tạo custom exception.
        try {
            absent.orElseThrow(() -> {
                supplierCalls.incrementAndGet();
                return new IllegalArgumentException("Name is required");
            });
        } catch (IllegalArgumentException ex) {
            System.out.println("custom empty = " + ex.getMessage());
        }

        System.out.println("supplier calls after empty = "
                + supplierCalls.get());

        // Constructor reference cũng là một Supplier.
        try {
            absent.orElseThrow(IllegalStateException::new);
        } catch (IllegalStateException ex) {
            System.out.println("constructor reference = "
                    + ex.getClass().getSimpleName());
        }

        // Kiểm tra lỗi nghiệp vụ có ngữ cảnh ID.
        System.out.println("user present = " + requireUser("u-1").name());

        try {
            requireUser("u-2");
        } catch (IllegalArgumentException ex) {
            System.out.println("user missing = " + ex.getMessage());
        }

        // Checked exception do Supplier tạo ra.
        try {
            findRequiredName("u-2");
        } catch (IOException ex) {
            System.out.println("checked exception = " + ex.getMessage());
        }

        // ofNullable chuyển null thành Optional rỗng.
        String maybeNull = null;
        try {
            Optional.ofNullable(maybeNull).orElseThrow();
        } catch (NoSuchElementException ex) {
            System.out.println("ofNullable null = NoSuchElementException");
        }

        // Một Supplier null chỉ là vấn đề khi Optional rỗng.
        System.out.println("null supplier present = "
                + present.orElseThrow(null));

        try {
            absent.orElseThrow(null);
        } catch (NullPointerException ex) {
            System.out.println("null supplier empty = NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac OptionalOrElseThrowDemo.java
java OptionalOrElseThrowDemo
~~~

**Đầu ra chính xác:**

~~~text
no-arg present = Java
no-arg empty = NoSuchElementException
custom present = Java
supplier calls with value = 0
custom empty = Name is required
supplier calls after empty = 1
constructor reference = IllegalStateException
user present = An
user missing = Missing user: u-2
checked exception = Name not found for u-2
ofNullable null = NoSuchElementException
null supplier present = Java
null supplier empty = NullPointerException
~~~

### Phân tích kết quả

1. **Cùng có value:** `present.orElseThrow()` và `present.orElseThrow(supplier)` đều trả `"Java"`.
2. **Không đối số với empty:** Java ném `NoSuchElementException`; ta in tên loại ngoại lệ chứ không dựa vào thông báo nội bộ của JDK.
3. **Supplier với value:** counter vẫn `0`, chứng minh thân lambda không được gọi.
4. **Supplier với empty:** counter tăng lên `1`, và `IllegalArgumentException` tùy chỉnh chứa thông điệp `Name is required`.
5. **Constructor reference:** `IllegalStateException::new` cung cấp một supplier sinh ngoại lệ không cần thông điệp.
6. **Tình huống nghiệp vụ:** `requireUser("u-1")` lấy user; `requireUser("u-2")` ném exception mang ID rõ ràng.
7. **Checked exception:** `findRequiredName("u-2")` khai báo `throws IOException`; nơi gọi bắt và in thông điệp.
8. **`ofNullable(null)`:** tạo Optional rỗng, vì thế no-arg ném `NoSuchElementException`.
9. **Supplier `null`:** khi có value, supplier không được gọi và vẫn trả `"Java"`. Khi rỗng, Java cần gọi supplier, vì thế ném `NullPointerException`.

Chương trình không cần thư viện bên ngoài. `record User` là cú pháp có sẵn trong JDK 17; chính hai overload `orElseThrow` tuân theo quy tắc đã có từ Java 8/10.

## 8. Các tình huống biên và ngoại lệ cần hiểu đúng

### 8.1. Supplier trả về `null`

~~~java
Optional<String> absent = Optional.empty();

try {
    absent.orElseThrow(() -> null);
} catch (NullPointerException ex) {
    System.out.println("supplier returned null");
}
~~~

Đoạn này chạy được khi đặt trong một phương thức và import `Optional`. Supplier **đã chạy** nhưng trả `null` thay vì một `Throwable`; Java không thể ném một exception object hợp lệ, nên kết quả là `NullPointerException`.

**Khuyến nghị:** luôn trả về một exception object khác `null`. Không dùng `null` để biểu thị “không có lỗi” trong supplier: nhánh này chỉ chạy khi Optional đã rỗng và cần ném lỗi.

### 8.2. Supplier bản thân ném một runtime exception

~~~java
Optional.<String>empty().orElseThrow(() -> {
    throw new IllegalStateException("supplier itself failed");
});
~~~

Đây là đoạn minh họa **cố ý ném exception**. `Supplier.get()` có thể ném một unchecked exception khi đang chạy, khiến lời gọi `orElseThrow` kết thúc với exception đó. Điều này khác với trường hợp supplier **trả về một exception** và `orElseThrow` ném nó.

Thực tế nên giữ supplier đơn giản (ví dụ `() -> new NotFoundException(id)`) để việc phân tích lỗi dễ hơn, tránh I/O hoặc tác dụng phụ trong quá trình xây ngoại lệ.

### 8.3. Supplier tính thông điệp lỗi có thể tốn kém

~~~java
String result = optional.orElseThrow(() ->
        new IllegalArgumentException(
                "Invalid request: " + buildDiagnosticContext()));
~~~

Nếu `optional` có value, `buildDiagnosticContext()` **không chạy** vì nằm trong lambda. Nếu `optional` rỗng, mã xây thông điệp thực thi; việc tính toán có thể tốn thời gian, và chính quá trình đó cũng có thể phát sinh lỗi khác.

Đây là lý do nên đặt **đúng phần việc cần lazy** vào supplier, thay vì tính toán hết ở ngoài rồi mới truyền lambda.

### 8.4. `Optional` không phải cơ chế bắt ngoại lệ

~~~java
Optional<String> value = findValue();

// value.orElseThrow() không tự bắt IOException hoặc lỗi khác
// xảy ra trước đó trong findValue().
~~~

`Optional` biểu diễn sự hiện diện/vắng mặt **của value đã được hàm trả về**. Nó không có nghĩa rằng mọi lỗi của hàm gọi là “Optional empty”. Nếu truy xuất dữ liệu gặp lỗi mạng, lỗi quyền hoặc dữ liệu hỏng, hãy quyết định rõ lỗi nào cần ném trực tiếp và trường hợp nào là **không tìm thấy dữ liệu bình thường**.

### 8.5. Khác nhau giữa `Optional.of(null)` và `Optional.ofNullable(null)`

~~~java
// Optional.of(null); // Ném NullPointerException ngay lúc tạo Optional.

Optional<String> value = Optional.ofNullable(null);
// value đang rỗng; value.orElseThrow() mới ném NoSuchElementException.
~~~

Không thể dùng `Optional.of(null)` để thử nhánh `orElseThrow` khi rỗng, vì chương trình đã lỗi trước khi có một Optional hợp lệ.

### 8.6. Không phải mọi trạng thái rỗng đều là lỗi

Nếu Optional rỗng là trường hợp **hợp lệ**, việc gọi `orElseThrow` vô điều kiện sẽ biến nó thành exception. Có thể thích hợp hơn khi dùng giá trị mặc định, nhánh tùy chọn hoặc trả nguyên `Optional` cho tầng gọi.

Ví dụ, một hệ thống tìm nickname có thể không cần ném lỗi khi người dùng chưa khai báo nickname, nhưng một bước xác nhận tài khoản bắt buộc lại có thể cần lỗi nghiệp vụ khi thiếu hồ sơ.

## 9. So sánh với các phương thức Optional liên quan

| Phương thức | Optional có value | Optional rỗng | Khi nào nên dùng |
| --- | --- | --- | --- |
| `get()` | Trả value | Ném `NoSuchElementException` | Vẫn hợp lệ; `orElseThrow()` thường diễn đạt ý định rõ hơn |
| `orElseThrow()` | Trả value | Ném `NoSuchElementException` | Thiếu value là lỗi và ngoại lệ chung đã đủ |
| `orElseThrow(() -> new E(...))` | Trả value, không gọi supplier | Ném `E` do supplier tạo | Cần loại ngoại lệ hoặc thông điệp riêng |
| `orElse(defaultValue)` | Trả value | Trả `defaultValue` | Thiếu value là tình huống bình thường có giá trị thay thế |
| `orElseGet(() -> defaultValue())` | Trả value, không gọi supplier | Gọi supplier tạo **value thay thế** | Giá trị mặc định tốn kém, chỉ cần tạo khi rỗng |
| `ifPresent(consumer)` | Thực hiện hành động | Không làm gì | Không nhất thiết lấy `T` để tiếp tục tính toán |
| `map(mapper)` | Biến đổi value, trả Optional mới | Trả Optional rỗng | Còn xử lý kết quả tùy chọn thay vì ép phải có value |
| `filter(predicate)` | Giữ hoặc bỏ value theo điều kiện | Vẫn rỗng | Điều kiện nghiệp vụ được biểu diễn trước khi quyết định ném lỗi |

**Sự khác nhau cốt lõi giữa hai kiểu Supplier:**
- `orElseGet(Supplier<? extends T>)` yêu cầu supplier sinh **value `T` để trả về**.
- `orElseThrow(Supplier<? extends X>)` yêu cầu supplier sinh **ngoại lệ `X` để ném**.

Đừng nhầm tên `orElseGet` và `orElseThrow`. Cả hai có nhánh lazy nhưng **mục đích và kiểu object tạo ra khác nhau**.

### Lưu ý về `orElse` và tính eager

~~~java
String result = Optional.of("exists")
        .orElse(expensiveFallback());
~~~

`expensiveFallback()` được gọi **trước** khi `orElse(...)` nhận đối số theo quy tắc đánh giá biểu thức Java, dù Optional đã có value. Nếu chỉ muốn tạo fallback khi rỗng:

~~~java
String result = Optional.of("exists")
        .orElseGet(() -> expensiveFallback());
~~~

Nếu muốn **ném lỗi** khi rỗng, dùng `orElseThrow` chứ không phải tạo một giá trị mặc định.

Các đoạn trên là mã minh họa cần định nghĩa phương thức `expensiveFallback()`, không phải chương trình độc lập.

## 10. Cách lựa chọn overload trong API thực tế

### Tình huống A — Kết quả phải tồn tại theo tiền điều kiện đã được bảo đảm

Ví dụ một thuật toán làm việc với tập số không rỗng:

~~~java
int largest = numbers.stream()
        .max(Integer::compareTo)
        .orElseThrow();
~~~

Nếu hợp đồng đã yêu cầu `numbers` không rỗng, `NoSuchElementException` là chỉ báo ngắn gọn khi tiền điều kiện bị vi phạm. Đây là đoạn minh họa cần khai báo `numbers` là collection kiểu `Integer`.

### Tình huống B — Thiếu tài nguyên cần báo một lỗi nghiệp vụ cụ thể

~~~java
User user = repository.findById(userId)
        .orElseThrow(() ->
                new UserNotFoundException("User " + userId + " not found"));
~~~

Kiểu `UserNotFoundException` và `repository` phụ thuộc ứng dụng. Phương án này phù hợp nếu tầng gọi cần phân biệt “không tìm thấy người dùng” với các loại lỗi khác.

Không dùng `NoSuchElementException` chung cho mọi tình huống khi ứng dụng có hợp đồng lỗi cụ thể (ví dụ HTTP 404, lỗi xác thực hoặc trạng thái tài nguyên), vì điều đó làm mất ý nghĩa ở tầng trên.

### Tình huống C — Cần checked exception theo interface của tầng gọi

~~~java
static String requireSetting(String key) throws IOException {
    return findSetting(key)
            .orElseThrow(() -> new IOException("No setting: " + key));
}
~~~

Đoạn này cần định nghĩa `findSetting(String)` trả `Optional<String>`. Nơi gọi phải bắt hoặc khai báo `IOException`, theo hợp đồng checked exception của Java.

### Tình huống D — Thiếu dữ liệu là bình thường, không nên ném lỗi

~~~java
String nickname = findNickname(userId).orElse("Guest");
~~~

Nếu nickname chỉ là thông tin tùy chọn, giá trị thay thế `"Guest"` có thể phù hợp hơn ngoại lệ. Đừng sử dụng `orElseThrow` chỉ vì muốn loại bỏ `Optional` khỏi biến trả về.

### Tình huống E — Có dữ liệu nhưng chưa hợp lệ

~~~java
String validCode = maybeCode
        .filter(code -> code.length() == 6)
        .orElseThrow(() ->
                new IllegalArgumentException("Code must have 6 characters"));
~~~

`filter` có thể khiến một Optional đang có value trở thành rỗng nếu điều kiện không đạt. Khi đó `orElseThrow` nhận thấy rỗng và ném lỗi đã chọn. Mã minh họa cần khai báo `maybeCode` là `Optional<String>`.

Hãy lưu ý cách viết này có thể gom hai trường hợp “thiếu mã” và “mã sai độ dài” vào cùng loại exception. Nếu API cần phân biệt, dùng các bước kiểm tra hoặc thông điệp riêng.

## 11. Những lỗi và hiểu lầm phổ biến

**Hiểu lầm 1 — “Hai overload `orElseThrow` giống nhau hoàn toàn.”**  
Không. Nhánh có value giống nhau, nhánh rỗng khác loại ngoại lệ và cách tạo lỗi. Không đối số luôn ném `NoSuchElementException`; có supplier ném ngoại lệ mà supplier cung cấp.

**Hiểu lầm 2 — “`orElseThrow()` bắt đầu từ Java 8 vì Optional có từ Java 8.”**  
Không. `Optional` và `orElseThrow(Supplier)` có từ Java 8; overload **không đối số** có từ Java 10. Với dự án target Java 8/9, không thể gọi `orElseThrow()` không đối số.

**Hiểu lầm 3 — “Supplier luôn chạy dù Optional có value.”**  
Không. Khi có value, supplier không được gọi. Chỉ các biểu thức **bên ngoài** lambda vẫn thực thi bình thường trước lời gọi.

**Hiểu lầm 4 — “Cứ truyền trực tiếp một exception object vào `orElseThrow`.”**  
Không. Phương thức yêu cầu `Supplier`; hãy viết `() -> new IllegalArgumentException(...)` hoặc `IllegalArgumentException::new`.

**Hiểu lầm 5 — “Supplier nhận vào value bị thiếu.”**  
Không. `Supplier.get()` **không có tham số**. Nếu cần ID hoặc key để xây thông điệp, lambda có thể **capture** biến từ phạm vi bên ngoài (biến cục bộ phải final hoặc effectively final).

**Hiểu lầm 6 — “Supplier có thể trả `null` để bỏ qua lỗi.”**  
Không. Khi rỗng, supplier trả `null` dẫn đến `NullPointerException`; không tạo ra value mặc định.

**Hiểu lầm 7 — “Dùng checked exception trong supplier thì không cần `throws`.”**  
Không. Chữ ký generic `throws X` cho phép checked exception nhưng vẫn yêu cầu bắt hoặc khai báo tại lời gọi phù hợp.

**Hiểu lầm 8 — “`orElseThrow` giúp tránh mọi `NullPointerException`.”**  
Không. `Optional.of(null)` vẫn lỗi ngay khi tạo. Supplier `null` khi Optional rỗng cũng gây `NullPointerException`. Các lỗi null trong mã tạo dữ liệu hoặc trong lambda không tự biến thành `NoSuchElementException`.

**Hiểu lầm 9 — “Có thể kiểm tra Optional rỗng bằng `get()` rồi mới chọn orElseThrow.”**  
Không cần. Dùng `orElseThrow` trực tiếp khi hợp đồng bắt buộc có value. Nếu muốn xử lý nhánh có/không có, cân nhắc `ifPresentOrElse`, `map`, `orElse`, hoặc trả `Optional` thay vì gọi `get` để kiểm tra.

**Hiểu lầm 10 — “Luôn nên ném lỗi khi Optional rỗng.”**  
Không. `Optional.empty()` là một trạng thái hợp lệ trong rất nhiều API tìm kiếm. Chọn ném lỗi ở **ranh giới nghiệp vụ yêu cầu giá trị bắt buộc**, không tự động biến mọi trường hợp không tìm thấy thành exception.

## 12. Tự kiểm tra kiến thức

**Câu 1.** `Optional.of("A").orElseThrow()` trả gì?  
**Đáp án:** `"A"`, vì Optional có value.

**Câu 2.** `Optional.<String>empty().orElseThrow()` ném ngoại lệ gì?  
**Đáp án:** `NoSuchElementException`, loại unchecked exception.

**Câu 3.** `Optional.empty().orElseThrow(() -> new IllegalStateException("bad"))` khi rỗng có ném `NoSuchElementException` không?  
**Đáp án:** Không. Nó ném `IllegalStateException` từ supplier với thông điệp `"bad"`.

**Câu 4.** Supplier trong `Optional.of("A").orElseThrow(() -> new RuntimeException())` có được gọi không?  
**Đáp án:** Không. Khi đã có value, Java trả value và không gọi supplier.

**Câu 5.** Đưa trực tiếp `new IOException("missing")` vào tham số có hợp lệ không?  
**Đáp án:** Không. Tham số phải là `Supplier`, ví dụ `() -> new IOException("missing")`. Caller còn phải tuân thủ `throws IOException` hoặc `catch`.

**Câu 6.** Vì sao `Optional.empty().orElseThrow(null)` có thể ném `NullPointerException`?  
**Đáp án:** Khi rỗng, `orElseThrow` phải gọi `Supplier.get()`; supplier `null` không thể được gọi.

**Câu 7.** `orElseGet(() -> "Guest")` khác gì `orElseThrow(() -> new IllegalStateException())`?  
**Đáp án:** Cả hai đều chỉ gọi supplier khi Optional rỗng, nhưng cái đầu **trả value thay thế**, cái sau **ném ngoại lệ**.

**Câu 8.** Nếu `Optional.ofNullable(null)` được truyền vào no-arg `orElseThrow()`, điều gì xảy ra?  
**Đáp án:** `ofNullable(null)` tạo Optional rỗng; sau đó `orElseThrow()` ném `NoSuchElementException`.

**Câu 9.** Có thể dùng `orElseThrow(Supplier)` để ném checked exception từ Java 10+ không?  
**Đáp án:** Có. Overload này chấp nhận supplier tạo một `Throwable` cụ thể và khai báo generic `throws X`, nên Java yêu cầu bắt hoặc khai báo ngoại lệ checked tương ứng.

**Câu 10.** Khi nào nên chọn overload không đối số thay vì supplier?  
**Đáp án:** Khi giá trị bắt buộc phải có và `NoSuchElementException` đã đủ rõ, không cần thông điệp hay loại exception nghiệp vụ riêng.

## 13. Ghi nhớ cuối bài

1. **`orElseThrow()` (Java 10+)**: trả value nếu có; rỗng thì ném **`NoSuchElementException`**.
2. **`orElseThrow(Supplier)` (Java 8+)**: trả value nếu có; rỗng thì **gọi supplier và ném ngoại lệ được tạo**.
3. **Supplier lazy**: chỉ được gọi khi rỗng. Đưa phần xây thông điệp và tạo exception vào lambda để tránh công việc thừa.
4. **Checked exception được hỗ trợ** ở overload supplier, nhưng vẫn phải tuân thủ quy tắc `throws`/`catch` của Java.
5. `Optional.get()` vẫn tồn tại nhưng `orElseThrow()` thường diễn đạt ý định “phải có giá trị” rõ hơn trong code hiện đại.
6. Khi sự vắng mặt là một trường hợp bình thường, dùng `orElse`, `orElseGet`, xử lý nhánh hoặc giữ `Optional` — **không ném ngoại lệ theo thói quen**.

**Tài liệu Oracle còn áp dụng:**
- [Java SE 10 — Optional và hai overload orElseThrow](https://docs.oracle.com/javase/10/docs/api/java/util/Optional.html).
- [Java SE 17 — Optional API, orElseThrow(), orElseThrow(Supplier)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).
- [Java SE 17 — Supplier functional interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html).
- [Java SE 17 — NoSuchElementException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NoSuchElementException.html).
