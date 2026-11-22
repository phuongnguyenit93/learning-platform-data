# Kiểm thử hai nhánh có và không có giá trị với `Optional.orElseThrow` (Java 10+)

## 1. Mục tiêu của bài học

`Optional<T>` biểu diễn một kết quả **có thể có hoặc không có giá trị**. Khi mã gọi `orElseThrow()`, Java thực hiện một trong hai nhánh:

- **Có giá trị (*present*):** trả chính giá trị kiểu `T` đang được chứa.
- **Không có giá trị (*empty*):** ném `NoSuchElementException`.

Phương thức `Optional.orElseThrow()` **không tham số** được bổ sung từ **Java 10** và vẫn dùng được trong Java hiện nay. Bên cạnh đó, overload `orElseThrow(Supplier<? extends X>)` đã có từ Java 8, cho phép tạo ngoại lệ tùy chỉnh khi Optional rỗng.

```java
Optional<String> present = Optional.of("An");
Optional<String> absent = Optional.empty();

String name = present.orElseThrow(); // "An"
// absent.orElseThrow();             // ném NoSuchElementException
```

Đoạn trên là mã minh họa trong một phương thức, cần `import java.util.Optional;`.

**Kiểm thử đầy đủ không thể chỉ gọi một lần với giá trị có sẵn.** Bài test cần chứng minh cả kết quả thành công và ngoại lệ được ném đúng khi không có giá trị. Nếu dùng overload tùy chỉnh, cần thêm một điều: **supplier tạo ngoại lệ chỉ được gọi ở nhánh empty**.

## 2. Hợp đồng chính xác của hai overload

| Cách gọi | Nhánh present | Nhánh empty | Có từ |
| --- | --- | --- | --- |
| `optional.orElseThrow()` | Trả giá trị kiểu `T` | Ném `NoSuchElementException` | Java 10 |
| `optional.orElseThrow(exceptionSupplier)` | Trả giá trị kiểu `T`, **không gọi supplier** | Gọi supplier để lấy và ném ngoại lệ `X` | Java 8 |

Các chữ ký trong Javadoc:

```java
public T orElseThrow();

public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X;
```

Đây là **chữ ký API**, không phải các phương thức bạn phải tự triển khai.

Với overload thứ nhất, lớp ngoại lệ `NoSuchElementException` là **một phần hợp đồng**. Không nên phụ thuộc vào chuỗi thông điệp cụ thể của ngoại lệ này trong test, vì hợp đồng API không bắt buộc một nội dung message cố định.

Với overload thứ hai, đối tượng exception chỉ cần được tạo **nếu Optional rỗng**. Supplier có thể là constructor reference như `IllegalArgumentException::new` hoặc lambda chứa ngữ cảnh:

```java
String name = optional.orElseThrow(
        () -> new IllegalArgumentException("Không tìm thấy tên"));
```

Ở đoạn minh họa này, `optional` được giả định có kiểu `Optional<String>`.

**Nếu supplier là `null` hoặc trả về `null` và Optional rỗng**, overload thứ hai ném `NullPointerException`. Ở nhánh có giá trị, supplier không được gọi. Dù vậy, truyền supplier `null` không phải một thiết kế nên chủ động sử dụng.

## 3. Chuẩn bị hai đầu vào kiểm thử độc lập

Để test có tính quyết định, không nên dựa vào database, mạng hoặc dữ liệu có thể thay đổi. Tạo hai Optional ngay trong test:

```java
Optional<String> present = Optional.of("ready");
Optional<String> empty = Optional.empty();
```

Một số cách tạo trạng thái:

| Biểu thức | Trạng thái | Gọi `orElseThrow()` |
| --- | --- | --- |
| `Optional.of("A")` | Có `"A"` | Trả `"A"` |
| `Optional.of("")` | Có **chuỗi rỗng** `""` | Trả `""`, **không ném** |
| `Optional.empty()` | Không có giá trị | Ném `NoSuchElementException` |
| `Optional.ofNullable(null)` | Không có giá trị | Ném `NoSuchElementException` |
| `Optional.ofNullable("A")` | Có `"A"` | Trả `"A"` |
| `Optional.of(null)` | **Ném `NullPointerException` ngay lúc tạo** | Chưa đến bước gọi `orElseThrow()` |

**Điểm dễ nhầm:** `Optional.of("")` là **present**, không phải empty. Chuỗi rỗng, số `0`, `false` hoặc danh sách rỗng vẫn có thể là những **giá trị hợp lệ** chứa trong Optional nếu kiểu tương ứng cho phép.

`Optional.empty()` đại diện cho sự vắng mặt. Không kiểm tra nó bằng `== Optional.empty()` vì API không hứa một instance singleton theo identity; khi cần biết trạng thái, dùng `isPresent()`, `isEmpty()` hoặc trực tiếp kiểm thử hành vi.

## 4. Nhánh present: kiểm tra giá trị trả về, không chỉ kiểm tra “không lỗi”

Một test yếu có thể chỉ gọi:

```java
Optional.of("ready").orElseThrow();
```

Nó chứng minh lời gọi không ném ngoại lệ trong lần chạy ấy, nhưng **không xác nhận giá trị trả về đúng**. Test tốt nên so sánh kết quả với dữ liệu mong đợi:

```java
var input = Optional.of("ready");
var actual = input.orElseThrow();

if (!"ready".equals(actual)) {
    throw new AssertionError("Sai giá trị ở nhánh present");
}
```

Nếu Optional chứa object có thuộc tính nghiệp vụ, hãy xác minh các thuộc tính quan trọng:

```java
record User(long id, String name) {}

var user = Optional.of(new User(7, "An")).orElseThrow();
// Kiểm tra user.id() == 7 và user.name().equals("An").
```

Đây là đoạn minh họa; `record User` nên khai báo ở cấp lớp hoặc phù hợp với ngữ cảnh Java, còn các câu lệnh có `var` phải đặt trong block/phương thức.

**Khuyến nghị:** ở nhánh thành công, test **đúng giá trị hoặc trạng thái object được trả về**. Nếu chỉ dùng `assertDoesNotThrow(...)` mà không kiểm tra kết quả, một thay đổi ngoài ý muốn có thể không bị phát hiện.

## 5. Nhánh empty: xác minh đúng kiểu ngoại lệ

Với overload không tham số:

```java
Optional<String> empty = Optional.empty();

// Lời gọi sau ném NoSuchElementException:
empty.orElseThrow();
```

Khi viết unit test, không gọi trực tiếp rồi coi việc test bị crash là thành công. Cần bọc trong một assertion **mong đợi đúng ngoại lệ**. Với JUnit Jupiter:

```java
assertThrows(NoSuchElementException.class,
        () -> Optional.<String>empty().orElseThrow());
```

Đây là đoạn **JUnit minh họa**, cần dependency và test runner JUnit Jupiter; cần static import `assertThrows`, import `NoSuchElementException`, `Optional`.

Lưu ý:

- `Optional.<String>empty()` cung cấp kiểu rõ ràng khi cần; không ảnh hưởng trạng thái empty.
- `assertThrows(NoSuchElementException.class, executable)` thành công khi hành động ném đúng lớp ngoại lệ hoặc một lớp con tương thích.
- Nếu không có ngoại lệ, assertion **thất bại**.
- Nếu ném một ngoại lệ không phù hợp, assertion cũng **thất bại**.
- Không nên bắt `NoSuchElementException` rồi **bỏ qua** trong test vì cách đó có thể khiến test thành công dù lời gọi không ném gì.

Nếu yêu cầu kiểm tra **chính xác lớp ngoại lệ**, JUnit Jupiter còn có `assertThrowsExactly`. Với hợp đồng `orElseThrow()`, dùng `assertThrows(NoSuchElementException.class, ...)` thường đủ và dễ hiểu.

## 6. Kiểm thử overload tùy chỉnh: loại, thông điệp và sự lười tạo exception

Giả sử API cần ném `IllegalArgumentException` khi không tìm thấy user:

```java
var missing = Optional.<String>empty();

String value = missing.orElseThrow(
        () -> new IllegalArgumentException("User 99 not found"));
```

Lời gọi này ném `IllegalArgumentException` có thông điệp do **ứng dụng tự thiết kế**. Trong test nên xác minh:

1. **Đúng loại exception** khi empty.
2. **Đúng thông điệp hoặc thuộc tính nghiệp vụ** nếu message là một phần hợp đồng đã đặt ra.
3. **Không tạo exception** nếu Optional có giá trị.

Ví dụ JUnit:

```java
var error = assertThrows(IllegalArgumentException.class,
        () -> Optional.<String>empty().orElseThrow(
                () -> new IllegalArgumentException("User 99 not found")));

assertEquals("User 99 not found", error.getMessage());
```

Vì chính ứng dụng đặt message trên nên kiểm tra chuỗi này là hợp lý nếu nó quan trọng. Điều đó khác với việc cố kiểm tra một message JDK không cam kết.

### Kiểm tra supplier có thực sự lazy không?

Supplier của overload tùy chỉnh **không được gọi** ở nhánh present. Có thể kiểm tra rõ bằng một counter:

```java
var calls = new AtomicInteger();

var result = Optional.of("ready").orElseThrow(() -> {
    calls.incrementAndGet();
    return new IllegalStateException("unexpected");
});

// result.equals("ready") == true
// calls.get() == 0
```

Đoạn minh họa cần `import java.util.concurrent.atomic.AtomicInteger;`.

Sau đó gọi nhánh empty bằng một supplier tương đương để xác minh counter tăng:

```java
// Bọc trong assertThrows ở bài test:
Optional.<String>empty().orElseThrow(() -> {
    calls.incrementAndGet();
    return new IllegalStateException("missing");
});

// Nếu ngoại lệ được bắt đúng, calls.get() tăng từ 0 thành 1.
```

Không gọi các câu lệnh trên nối tiếp nhau ngoài test có xử lý ngoại lệ: lời gọi empty sẽ ném trước khi chuyển sang câu lệnh kế tiếp.

**Tại sao nên test sự lazy?** Một lời gọi supplier có thể tạo exception với message tốn công tính toán hoặc có side effect ngoài ý muốn. Hợp đồng của `orElseThrow(exceptionSupplier)` là **chỉ yêu cầu exception khi thực sự không có giá trị**; test giúp phòng việc code bị viết lại thành một đường xử lý gọi supplier sớm.

## 7. Ma trận kiểm thử tối thiểu

| Trường hợp | Dữ liệu | Hành vi kỳ vọng | Assertion trọng tâm |
| --- | --- | --- | --- |
| Không tham số, present | `Optional.of("A")` | Trả `"A"` | So sánh giá trị |
| Không tham số, empty | `Optional.empty()` | `NoSuchElementException` | `assertThrows` |
| Tùy chỉnh, present | `Optional.of("A")` | Trả `"A"`, supplier không gọi | Giá trị + số lần gọi `0` |
| Tùy chỉnh, empty | `Optional.empty()` | Ném exception do supplier sinh ra | Loại, message, số lần gọi `1` |
| Giá trị là chuỗi rỗng | `Optional.of("")` | Trả `""`, không ném | So sánh chuỗi rỗng |
| Đầu vào nullable | `Optional.ofNullable(null)` | Tạo empty, sau đó ném `NoSuchElementException` khi unwrap | Test riêng hai bước |
| Lỗi tại lúc tạo Optional | `Optional.of(null)` | Ném `NullPointerException` **trước** unwrap | Không quy lỗi cho `orElseThrow` |

**Nguyên tắc:** mỗi test nên có một mục đích rõ và một đầu vào quyết định. Không cần mô phỏng nhiều trạng thái ngẫu nhiên mới kiểm tra được hợp đồng của `Optional`.

## 8. Chương trình Java 17+ hoàn chỉnh: chạy test không cần thư viện ngoài

Tạo tệp `OptionalBranchesDemo.java`:

```java
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalBranchesDemo {

    record User(long id, String name) { }

    static Optional<User> findUser(long id) {
        return id == 7
                ? Optional.of(new User(7, "An"))
                : Optional.empty();
    }

    static void require(boolean passed, String description) {
        if (!passed) {
            throw new AssertionError(description);
        }
    }

    static <E extends Throwable> E expectException(
            Class<E> type, Runnable action) {
        try {
            action.run();
        } catch (Throwable thrown) {
            if (!type.isInstance(thrown)) {
                throw new AssertionError(
                        "Wrong exception: " + thrown, thrown);
            }
            return type.cast(thrown);
        }
        throw new AssertionError(
                "Expected " + type.getSimpleName());
    }

    public static void main(String[] args) {
        // Nhánh 1: có dữ liệu => trả đúng object/value
        var user = findUser(7).orElseThrow();
        require("An".equals(user.name()), "present branch");
        System.out.println("present=" + user.name());

        // Nhánh 2: không có dữ liệu => NoSuchElementException
        var missing = expectException(NoSuchElementException.class,
                () -> findUser(99).orElseThrow());
        System.out.println(
                "empty=" + missing.getClass().getSimpleName());

        // Nhánh empty với exception nghiệp vụ được cung cấp
        var customized = expectException(
                IllegalArgumentException.class,
                () -> findUser(99).orElseThrow(
                        () -> new IllegalArgumentException(
                                "User 99 not found")));
        require("User 99 not found".equals(
                customized.getMessage()), "custom message");
        System.out.println("custom=" + customized.getMessage());

        // Supplier phải không được gọi ở nhánh có dữ liệu
        var callCount = new AtomicInteger();
        var alreadyThere = findUser(7).orElseThrow(() -> {
            callCount.incrementAndGet();
            return new IllegalStateException("must not run");
        });
        require(alreadyThere.id() == 7 && callCount.get() == 0,
                "supplier evaluated for present value");
        System.out.println(
                "supplier.presentCalls=" + callCount.get());

        // Supplier chỉ được gọi khi empty
        expectException(IllegalStateException.class,
                () -> findUser(99).orElseThrow(() -> {
                    callCount.incrementAndGet();
                    return new IllegalStateException("missing");
                }));
        require(callCount.get() == 1,
                "supplier not invoked exactly once");
        System.out.println(
                "supplier.emptyCalls=" + callCount.get());

        // ofNullable(null) tạo empty, không phải present-null
        expectException(NoSuchElementException.class,
                () -> Optional.<String>ofNullable(null)
                        .orElseThrow());
        System.out.println("nullInput=NoSuchElementException");

        // "" vẫn là giá trị hiện diện
        var emptyString = Optional.of("").orElseThrow();
        require(emptyString.isEmpty(),
                "empty string is a present value");
        System.out.println("emptyStringPresent="
                + Optional.of(emptyString).isPresent());

        System.out.println("tests=PASS");
    }
}
```

Chạy:

```bash
javac OptionalBranchesDemo.java
java OptionalBranchesDemo
```

Kết quả chuẩn:

```text
present=An
empty=NoSuchElementException
custom=User 99 not found
supplier.presentCalls=0
supplier.emptyCalls=1
nullInput=NoSuchElementException
emptyStringPresent=true
tests=PASS
```

**Cách đọc output và vai trò của từng assertion:**

- `present=An` chỉ xuất hiện sau khi kiểm tra tên của object trả về.
- `empty=NoSuchElementException` cho biết test đã bắt đúng lớp ngoại lệ ở nhánh vắng giá trị.
- `custom=User 99 not found` xác nhận cả ngoại lệ tùy chỉnh và thông điệp do ứng dụng đặt.
- `supplier.presentCalls=0` chứng minh không gọi supplier khi Optional chứa giá trị.
- `supplier.emptyCalls=1` chứng minh supplier được gọi đúng một lần để tạo ngoại lệ khi Optional rỗng.
- `nullInput=NoSuchElementException` chứng minh `ofNullable(null)` tạo empty trước khi gọi `orElseThrow`.
- `emptyStringPresent=true` nhắc rằng chuỗi rỗng là một **giá trị**, không phải một Optional rỗng.
- `tests=PASS` chỉ được in khi các kiểm tra phía trên không ném `AssertionError`.

Trong chương trình này, helper `expectException` **bắt ngoại lệ mong đợi**, nhưng **ném AssertionError** nếu xảy ra loại khác hoặc không có ngoại lệ. Đây là khác biệt quan trọng so với kiểu `try/catch` trống khiến test dễ cho kết quả sai.

## 9. Viết unit test với JUnit Jupiter

Trong dự án có dependency và test runner **JUnit Jupiter**, nên dùng assertion chuyên dụng thay vì tự viết helper. Ví dụ tệp `OptionalBranchesTest.java`:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class OptionalBranchesTest {

    private static Optional<String> lookup(int id) {
        return id == 7
                ? Optional.of("An")
                : Optional.empty();
    }

    @Test
    void returnsValueWhenPresent() {
        String value = assertDoesNotThrow(
                () -> lookup(7).orElseThrow());
        assertEquals("An", value);
    }

    @Test
    void throwsNoSuchElementWhenEmpty() {
        assertThrows(NoSuchElementException.class,
                () -> lookup(99).orElseThrow());
    }

    @Test
    void throwsCustomExceptionWhenEmpty() {
        var ex = assertThrows(IllegalArgumentException.class,
                () -> lookup(99).orElseThrow(
                        () -> new IllegalArgumentException("User 99 missing")));
        assertEquals("User 99 missing", ex.getMessage());
    }

    @Test
    void doesNotCallSupplierWhenPresent() {
        var calls = new AtomicInteger();
        String name = lookup(7).orElseThrow(() -> {
            calls.incrementAndGet();
            return new IllegalStateException("should not run");
        });
        assertEquals("An", name);
        assertEquals(0, calls.get());
    }

    @Test
    void callsSupplierOnceWhenEmpty() {
        var calls = new AtomicInteger();
        assertThrows(IllegalStateException.class,
                () -> lookup(99).orElseThrow(() -> {
                    calls.incrementAndGet();
                    return new IllegalStateException("missing");
                }));
        assertEquals(1, calls.get());
    }

    @Test
    void emptyStringIsStillPresent() {
        assertEquals("", Optional.of("").orElseThrow());
    }
}
```

**Phạm vi chạy:** tệp JUnit này cần thư viện `org.junit.jupiter` và test engine/runner được cấu hình bằng Maven, Gradle hoặc IDE. Nó không phải chương trình chạy độc lập bằng lệnh `java OptionalBranchesTest` như ví dụ ở phần 8; không cần `main` vì JUnit tìm các phương thức có `@Test`.

- `assertDoesNotThrow` làm rõ nhánh thành công; `assertEquals` xác minh giá trị.
- `assertThrows` xác minh nhánh lỗi; lấy exception trả về để kiểm tra thông điệp do ứng dụng kiểm soát.
- Mỗi test tạo state riêng, không phụ thuộc thứ tự chạy hay kết quả các test khác.
- Test tính lazy kiểm tra riêng cả present và empty; không trộn vào một test khó đọc.

**Lưu ý phiên bản:** cú pháp annotation `@Test`, `assertEquals`, `assertThrows` và `assertDoesNotThrow` thuộc mô hình JUnit Jupiter hiện hành. Đọc tài liệu JUnit dành cho dependency của dự án; không dùng lệnh biên dịch JUnit thuần khi classpath chưa được cấu hình.

## 10. Test ở lớp API: thật sự gọi nguồn nào tạo Optional?

Nhiều lỗi chỉ xuất hiện khi method trả `Optional` được triển khai sai. Giả sử repository:

```java
static Optional<String> findLabel(long id) {
    if (id == 7) {
        return Optional.of("An");
    }
    return Optional.empty();
}
```

Đoạn minh họa đặt trong một lớp, cần `import java.util.Optional;`.

Hãy tách **hai hợp đồng**:

1. **Hợp đồng repository:** với id tồn tại, trả `Optional.of(label)`; với id không tồn tại, trả `Optional.empty()`, **không trả `null` thay cho Optional**.
2. **Hợp đồng phía gọi:** gọi `findLabel(id).orElseThrow()` trả label nếu có và ném `NoSuchElementException` nếu empty.

Việc test thẳng `Optional.of("An").orElseThrow()` là một **unit test của API Optional**. Nếu đang test service thực tế, cần test cả cách service/repository tạo Optional và xử lý giá trị vắng mặt, có thể dùng fake repository hoặc stub để chủ động điều khiển hai nhánh. Đừng cho rằng vì `Optional` của JDK đã hoạt động đúng nên service của bạn chắc chắn dùng nó đúng.

Ví dụ các ranh giới thường cần cả hai nhánh: tìm user theo id, tìm cấu hình bắt buộc, tra khóa trong Map, hoặc tìm phần tử đầu tiên thỏa điều kiện.

## 11. Bốn điều kiện biên cần phân biệt

### 11.1. `Optional.ofNullable(null)` khác `Optional.of(null)`

```java
Optional<String> a = Optional.ofNullable(null);
// a.isEmpty() == true
// a.orElseThrow() ném NoSuchElementException

// Optional.of(null); // Ném NullPointerException NGAY khi gọi of(...)
```

Cần nêu rõ **lỗi xảy ra ở bước nào**. Không quy `NullPointerException` của `Optional.of(null)` thành kết quả của `orElseThrow()`.

### 11.2. Có giá trị nhưng giá trị “rỗng” theo nghiệp vụ

```java
var a = Optional.of("");
var b = Optional.of(0);
var c = Optional.of(false);
var d = Optional.of(List.of());

// Tất cả đều có giá trị. orElseThrow() không ném.
```

`Optional` chỉ biểu diễn **có/không có đối tượng giá trị khác null**, không tự kiểm tra “chuỗi có ký tự không?”, “số có dương không?” hoặc “list có phần tử không?”. Muốn “chuỗi trắng” trở thành trạng thái empty, cần thể hiện điều đó trong pipeline:

```java
Optional<String> clean = Optional.of("   ")
        .map(String::trim)
        .filter(s -> !s.isEmpty());

// clean.isEmpty() == true
// clean.orElseThrow() ném NoSuchElementException
```

Đó là kết quả của **quy tắc filter do ứng dụng cung cấp**, không phải cơ chế tự động của `orElseThrow`.

### 11.3. Supplier không hợp lệ

```java
var missing = Optional.<String>empty();

// missing.orElseThrow((java.util.function.Supplier<RuntimeException>) null);
// Ném NullPointerException vì supplier là null khi Optional empty.

// missing.orElseThrow(() -> null);
// Ném NullPointerException vì supplier trả về null.
```

Với Optional **có giá trị**, supplier không cần được gọi. Dù vậy, code sạch nên cung cấp một supplier hợp lệ ngay từ đầu. Test không nên dùng supplier null như một “thủ thuật” để xác minh laziness khi một counter hoặc test double có thể làm ý định rõ hơn.

### 11.4. Ngoại lệ tùy chỉnh có thể là checked exception

Overload `orElseThrow(Supplier<? extends X>)` cho phép `X extends Throwable`, không chỉ exception runtime. Ví dụ:

```java
static String requireData(Optional<String> input)
        throws java.io.IOException {
    return input.orElseThrow(
            () -> new java.io.IOException("missing input"));
}
```

Đây là phương thức minh họa đặt trong một lớp, cần `java.util.Optional`. Vì `IOException` là checked exception, phương thức bao ngoài phải **khai báo hoặc xử lý** nó theo quy tắc Java. Nhánh có giá trị vẫn trả String mà không tạo exception.

## 12. Khi nào nên dùng `orElseThrow` thay vì các cách xử lý khác?

| Ý định nghiệp vụ | API thường phù hợp | Nhánh empty |
| --- | --- | --- |
| Thiếu giá trị là lỗi; chấp nhận `NoSuchElementException` | `orElseThrow()` | Ném `NoSuchElementException` |
| Thiếu giá trị là lỗi có ngữ cảnh | `orElseThrow(() -> new DomainException(...))` | Ném exception từ supplier |
| Thiếu giá trị có fallback cố định | `orElse(defaultValue)` | Trả fallback |
| Thiếu giá trị cần tính fallback khi cần | `orElseGet(() -> computeDefault())` | Chỉ lúc empty mới gọi supplier |
| Thiếu giá trị cần được xử lý mềm | `ifPresentOrElse(...)`, `map`/`flatMap`, hoặc giữ Optional | Không nhất thiết ném exception |

Chẳng hạn, trong một API **bắt buộc** phải có cấu hình:

```java
var config = findRequiredConfig(key)
        .orElseThrow(() -> new IllegalStateException(
                "Required config is absent"));
```

Nếu việc không tìm thấy là một trạng thái bình thường, dùng exception có thể làm code gọi phức tạp và tạo điều khiển luồng bằng lỗi không cần thiết. Khi đó trả tiếp `Optional` hoặc dùng fallback là lựa chọn hợp lý hơn.

**Đừng nhầm `orElse` với `orElseGet`:** đối số của `orElse(fallbackExpression)` được đánh giá khi gọi phương thức theo quy tắc biểu thức Java, ngay cả nếu Optional có giá trị; `orElseGet(supplier)` chỉ gọi supplier khi empty. Điều này tương tự tính lazy của exceptionSupplier ở `orElseThrow(exceptionSupplier)`, nhưng khác **hành động**: một bên trả fallback, bên kia ném ngoại lệ.

## 13. Những lỗi trong unit test và cách khắc phục

| Cách test hoặc giả định sai | Hậu quả | Cách viết đúng |
| --- | --- | --- |
| Chỉ test `Optional.of(value).orElseThrow()` | Bỏ sót nhánh empty | Có test riêng `Optional.empty()` |
| Chỉ kiểm tra “không ném” mà không assert giá trị | Có thể bỏ qua giá trị trả về sai | `assertEquals(expected, actual)` |
| Gọi `Optional.empty().orElseThrow()` trong test mà không `assertThrows` | Test thất bại vì exception dù đó là kết quả mong đợi | Dùng `assertThrows(NoSuchElementException.class, ...)` |
| `try { call(); } catch (NoSuchElementException ignored) {}` | Test vẫn qua nếu `call()` không ném | Dùng `assertThrows` hoặc helper có nhánh fail khi không ném |
| Assert message cố định của `NoSuchElementException` no-arg | Phụ thuộc chi tiết không phải hợp đồng ổn định | Assert lớp exception |
| Kỳ vọng `Optional.of("")` là empty | Nhầm giá trị rỗng với vắng mặt | Test riêng empty string và `Optional.empty()` |
| Dùng `Optional.of(null)` để tạo empty | Ném `NullPointerException` trước khi unwrap | Dùng `Optional.empty()` hoặc `ofNullable(null)` |
| Supplier có side effect nhưng không test nhánh present | Có thể bỏ sót việc gọi supplier quá sớm | Đếm số lần gọi; present phải là `0` |
| Lấy `Optional.empty() == otherEmpty` để khẳng định trạng thái | Identity không phải hợp đồng của Optional | Dùng `isEmpty()` hoặc kiểm tra hành vi |
| Biến `Optional<T>` do method trả về lại là `null` | NPE khi gọi method trên tham chiếu null, không phải NoSuchElementException của empty | Sửa hợp đồng method: trả `Optional.empty()` |
| Một test phụ thuộc DB/mạng và thời điểm chạy chỉ để kiểm tra Optional | Kết quả không xác định, khó tái lập | Dùng đầu vào dựng trực tiếp/fake repository |
| Coi `get()` là cách khuyến nghị khi chắc chắn có giá trị | Javadoc ưu tiên `orElseThrow()` để thể hiện ý định | Dùng `orElseThrow()` khi thiếu giá trị là lỗi |

## 14. Quy tắc thiết kế test ổn định và có thể bảo trì

1. **Arrange / Act / Assert:** tạo `Optional` rõ ràng, thực hiện đúng một lời gọi, rồi kiểm tra giá trị hoặc exception.
2. **Mỗi nhánh có ít nhất một test:** present, empty; thêm kiểm tra supplier laziness khi dùng overload.
3. **Không assert chi tiết JDK không hứa:** ví dụ message chính xác của exception mặc định hoặc identity của `Optional.empty()`.
4. **Với thông điệp do ứng dụng đặt:** có thể assert thông điệp nếu nó là hợp đồng cần giữ.
5. **Kiểm tra bất biến của side effect:** supplier custom phải chỉ chạy khi empty.
6. **Dùng dữ liệu quyết định:** `Optional.of(...)` và `Optional.empty()` hoặc fake repository không phụ thuộc IO.
7. **Đặt tên test nêu hành vi:** `returnsValueWhenPresent`, `throwsWhenEmpty`, `doesNotCallSupplierWhenPresent`.
8. **Chú ý trường hợp “present nhưng rỗng theo nghiệp vụ”:** chuỗi rỗng, list rỗng, số `0`... cần được phân biệt với Optional không chứa giá trị.
9. **Không biến mọi empty thành exception:** việc coi thiếu dữ liệu là lỗi hay trạng thái được phép phải do hợp đồng nghiệp vụ quyết định.
10. **Nếu dùng checked exception:** kiểm tra chữ ký `throws`/cách xử lý đúng trong code production và test.

## 15. Bài tập tự kiểm tra

### Câu 1: Hai nhánh cơ bản

```java
Optional<Integer> a = Optional.of(42);
Optional<Integer> b = Optional.empty();
```

Điều gì xảy ra với `a.orElseThrow()` và `b.orElseThrow()`?

**Đáp án:** `a.orElseThrow()` trả `42`; `b.orElseThrow()` ném `NoSuchElementException`. Nên test giá trị của `a` và loại exception của `b`.

### Câu 2: Supplier có được gọi không?

```java
var calls = new AtomicInteger();
var a = Optional.of("ok").orElseThrow(() -> {
    calls.incrementAndGet();
    return new IllegalArgumentException("missing");
});
```

Sau lời gọi, `calls.get()` là bao nhiêu?

**Đáp án:** `0`, vì Optional có `"ok"`; không cần tạo exception. `a` có giá trị `"ok"`.

### Câu 3: Vì sao một assertion bắt exception là cần thiết?

Một người viết test:

```java
try {
    Optional.of("A").orElseThrow();
} catch (NoSuchElementException ignored) {
}
```

Test này có xác minh nhánh empty không?

**Đáp án:** Không. Không có ngoại lệ nào phát sinh, nhưng test vẫn chạy hết mà không báo sai. Cần một `assertThrows`/helper thất bại nếu không ném exception và phải gọi với `Optional.empty()`.

### Câu 4: Present có phải là dữ liệu hợp lệ về nghiệp vụ?

```java
String text = Optional.of("").orElseThrow();
```

Có lỗi không?

**Đáp án:** Không. `Optional` chứa chuỗi rỗng `""`, nên `orElseThrow()` trả chuỗi ấy. Nếu ứng dụng cấm chuỗi rỗng, cần `filter` hoặc validator riêng trước khi unwrap.

### Câu 5: Empty có thông điệp riêng

Muốn thiếu user ném `IllegalArgumentException("user 9 missing")`, viết thế nào?

**Đáp án:**

```java
var user = lookup(9).orElseThrow(
        () -> new IllegalArgumentException("user 9 missing"));
```

Đây là đoạn minh họa, giả định `lookup` trả `Optional<User>` phù hợp. Test nên kiểm tra đúng loại `IllegalArgumentException` và message do ứng dụng cung cấp, đồng thời có test nhánh present chứng minh supplier không bị gọi.

## Kết luận

Với `Optional.orElseThrow()` của Java 10+, cần kiểm thử **đủ hai nhánh**:

- **Present:** trả đúng giá trị; không ném ngoại lệ.
- **Empty:** ném đúng `NoSuchElementException`.

Với `orElseThrow(exceptionSupplier)`, còn phải đảm bảo **supplier chỉ chạy ở nhánh empty**, tạo đúng exception tùy chỉnh và thông điệp khi hợp đồng yêu cầu. `Optional.ofNullable(null)` tạo empty, trong khi `Optional.of("")` vẫn chứa một giá trị; phân biệt các trường hợp này giúp test không bỏ sót tình huống biên.

Mã ví dụ có thể kiểm chứng hoàn toàn bằng Java 17+ không phụ thuộc thư viện ngoài; trong dự án sử dụng JUnit Jupiter, `assertEquals`, `assertThrows` và `assertDoesNotThrow` giúp các yêu cầu trở thành những assertion rõ ràng, dễ bảo trì.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `Optional.orElseThrow()` và overload có `Supplier`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html#orElseThrow()): hiện hành, không tham số từ Java 10; hành vi khi present/empty và tùy chỉnh exception.
- [Java SE 26 — `Optional.of`, `ofNullable`, `empty`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html): cách tạo trạng thái có/không có giá trị và lưu ý identity.
- [JUnit — Tài liệu hiện hành về JUnit Jupiter](https://docs.junit.org/current/user-guide/): cách viết test với `@Test`, `assertEquals`, `assertThrows` và `assertDoesNotThrow`.
