# Kiểm thử trường hợp Optional có giá trị và trường hợp rỗng trong Java

## 1. Mục tiêu của kiểm thử Optional

Optional biểu diễn một kết quả có thể có hoặc không có giá trị. Khi kiểm thử phương thức trả về Optional, cần xác nhận cả hai nhánh:

- **Có giá trị:** Optional chứa đúng đối tượng hoặc giá trị mà nghiệp vụ mong đợi.
- **Rỗng:** Optional biểu diễn việc không có kết quả bằng Optional.empty(), không trả về null.

Một kiểm thử chỉ gọi isPresent() hoặc isEmpty() thường chưa đủ. Với trường hợp có giá trị, hãy xác nhận cả nội dung bên trong. Với trường hợp rỗng, hãy xác nhận nhánh xử lý khi không có dữ liệu hoạt động đúng.

Optional là value-based class. Không so sánh hai Optional bằng toán tử == và không phụ thuộc vào việc Optional.empty() có trả về cùng một instance hay không. Dùng equals(), isPresent() hoặc isEmpty() để kiểm tra trạng thái.

## 2. Chuẩn bị dữ liệu kiểm thử rõ ràng

Ví dụ một dịch vụ tra cứu tên người dùng theo mã:

~~~java
import java.util.Map;
import java.util.Optional;

public class UserDirectory {
    private final Map<Integer, String> names = Map.of(
        1, "An",
        2, "Binh"
    );

    public Optional<String> findName(int id) {
        return Optional.ofNullable(names.get(id));
    }
}
~~~

Phương thức trả về:

- Optional chứa tên khi mã tồn tại.
- Optional.empty() khi mã không có trong Map.

Dữ liệu kiểm thử nên cố định và dễ hiểu. Tránh phụ thuộc vào cơ sở dữ liệu, thời gian thực, mạng hoặc trạng thái bên ngoài khi mục tiêu chỉ là kiểm tra cách xử lý Optional. Nếu phương thức cần repository hoặc API khác, có thể thay dependency bằng mock hoặc fake theo cấu trúc kiểm thử của dự án.

## 3. Kiểm thử trường hợp có giá trị

Với mã tồn tại, kiểm thử nên xác nhận Optional không null, có giá trị và giá trị đó chính xác:

~~~java
@Test
void findNameReturnsValueWhenIdExists() {
    UserDirectory directory = new UserDirectory();

    Optional<String> actual = directory.findName(1);

    assertNotNull(actual);
    assertTrue(actual.isPresent());
    assertEquals("An", actual.orElseThrow());
}
~~~

Có thể viết gọn bằng cách so sánh toàn bộ Optional:

~~~java
assertEquals(Optional.of("An"), directory.findName(1));
~~~

Cách so sánh này kiểm tra đồng thời trạng thái và nội dung. Trong bài kiểm thử dài, giữ cả assertTrue(isPresent()) và assertEquals(value, orElseThrow()) có thể giúp thông báo lỗi dễ hiểu hơn, nhưng không cần lặp lại các assertion nếu chúng không bổ sung thông tin.

Không gọi get() một cách vô điều kiện. Nếu kết quả bất ngờ rỗng, get() ném NoSuchElementException và thường khiến nguyên nhân kiểm thử khó đọc hơn. Sau khi xác nhận có giá trị, orElseThrow() thể hiện rõ ý định lấy kết quả bắt buộc phải có.

## 4. Kiểm thử trường hợp rỗng

Với mã không tồn tại, phương thức nên trả về Optional.empty():

~~~java
@Test
void findNameReturnsEmptyWhenIdDoesNotExist() {
    UserDirectory directory = new UserDirectory();

    Optional<String> actual = directory.findName(99);

    assertNotNull(actual);
    assertTrue(actual.isEmpty());
    assertEquals(Optional.empty(), actual);
}
~~~

isEmpty() có từ Java 11. Nếu dự án cần chạy trên Java 9 hoặc Java 10, dùng !isPresent() để kiểm tra nhánh rỗng.

Assertion assertNotNull(actual) giúp phát hiện lỗi hợp đồng API: phương thức trả về Optional không nên trả về null thay cho Optional.empty(). Nếu actual là null, các lời gọi isEmpty() hoặc equals() không thể xác nhận trạng thái rỗng đúng cách.

Không dùng assertSame(Optional.empty(), actual). Optional là value-based class; kiểm tra identity không phải hợp đồng cần xác nhận. Hãy dùng assertEquals(Optional.empty(), actual) hoặc assertTrue(actual.isEmpty()).

## 5. Kiểm thử map và filter ở cả hai trạng thái

map biến đổi giá trị bên trong Optional khi có giá trị. Nếu Optional rỗng, mapper không được gọi và kết quả vẫn rỗng:

~~~java
@Test
void mapTransformsPresentValueAndPreservesEmpty() {
    UserDirectory directory = new UserDirectory();

    Optional<String> found = directory.findName(1)
        .map(String::toUpperCase);
    Optional<String> missing = directory.findName(99)
        .map(String::toUpperCase);

    assertEquals(Optional.of("AN"), found);
    assertEquals(Optional.empty(), missing);
}
~~~

filter giữ giá trị nếu predicate đúng. Nếu predicate sai hoặc Optional ban đầu rỗng, kết quả là Optional.empty():

~~~java
@Test
void filterKeepsMatchingValueAndEmptiesNonMatchingValue() {
    Optional<String> name = Optional.of("An");

    assertEquals(Optional.of("An"), name.filter(value -> value.startsWith("A")));
    assertEquals(Optional.empty(), name.filter(value -> value.startsWith("B")));
    assertEquals(Optional.empty(), Optional.<String>empty()
        .filter(value -> value.startsWith("A")));
}
~~~

Hai phép biến đổi này thường được dùng trong chuỗi xử lý Optional. Khi kiểm thử, hãy bao gồm cả nhánh có giá trị và nhánh rỗng để chắc rằng thao tác biến đổi không làm mất hoặc tạo ra dữ liệu ngoài ý muốn.

## 6. Kiểm thử giá trị mặc định và Supplier

orElse trả về giá trị mặc định khi Optional rỗng. orElseGet nhận Supplier và chỉ gọi Supplier khi Optional rỗng.

~~~java
@Test
void orElseReturnsFallbackOnlyForEmptyResult() {
    assertEquals("An", Optional.of("An").orElse("Guest"));
    assertEquals("Guest", Optional.<String>empty().orElse("Guest"));
}

@Test
void orElseGetCallsSupplierOnlyForEmptyResult() {
    AtomicInteger calls = new AtomicInteger();
    Supplier<String> fallback = () -> {
        calls.incrementAndGet();
        return "Guest";
    };

    assertEquals("An", Optional.of("An").orElseGet(fallback));
    assertEquals(0, calls.get());

    assertEquals("Guest", Optional.<String>empty().orElseGet(fallback));
    assertEquals(1, calls.get());
}
~~~

Điểm cần kiểm tra là Supplier không được gọi khi Optional có giá trị. Đây là khác biệt quan trọng vì biểu thức truyền vào orElse được đánh giá trước khi phương thức được gọi, còn Supplier của orElseGet chỉ chạy khi cần fallback.

Nếu fallback tạo đối tượng tốn tài nguyên hoặc có tác dụng phụ, kiểm thử số lần gọi Supplier giúp phát hiện việc thực thi thừa.

## 7. Kiểm thử orElseThrow và các factory method

orElseThrow() không tham số trả về giá trị khi Optional có dữ liệu và ném NoSuchElementException khi rỗng:

~~~java
@Test
void orElseThrowReturnsValueOrThrowsForEmpty() {
    assertEquals("An", Optional.of("An").orElseThrow());

    assertThrows(
        NoSuchElementException.class,
        () -> Optional.<String>empty().orElseThrow()
    );
}
~~~

Cũng nên phân biệt hai cách tạo Optional từ dữ liệu có thể null:

- Optional.of(value) yêu cầu value khác null và ném NullPointerException nếu truyền null.
- Optional.ofNullable(value) chấp nhận null và chuyển nó thành Optional.empty().

~~~java
@Test
void factoriesHandleNullAsSpecified() {
    assertThrows(
        NullPointerException.class,
        () -> Optional.<String>of(null)
    );

    assertEquals(Optional.empty(), Optional.ofNullable(null));
    assertEquals(Optional.of("An"), Optional.ofNullable("An"));
}
~~~

Nếu một phương thức đã khai báo trả về Optional, nó nên luôn trả về một đối tượng Optional không null. Đừng dùng Optional.ofNullable(result) trong kiểm thử để che giấu việc phương thức trả về null; hãy assertNotNull(result) để phát hiện lỗi hợp đồng.

## 8. Bộ kiểm thử JUnit Jupiter hoàn chỉnh

JUnit Jupiter cung cấp @Test và các assertion như assertEquals, assertTrue, assertNotNull, assertThrows. Ví dụ sau đặt lớp cần kiểm thử bên trong test class để có thể đọc và chạy độc lập trong một dự án đã cấu hình JUnit Jupiter.

**Tệp UserDirectoryTest.java:**

~~~java
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UserDirectoryTest {
    private final UserDirectory directory = new UserDirectory();

    @Test
    void findNameReturnsValueWhenIdExists() {
        Optional<String> actual = directory.findName(1);

        assertNotNull(actual);
        assertTrue(actual.isPresent());
        assertEquals("An", actual.orElseThrow());
    }

    @Test
    void findNameReturnsEmptyWhenIdDoesNotExist() {
        Optional<String> actual = directory.findName(99);

        assertNotNull(actual);
        assertTrue(actual.isEmpty());
        assertEquals(Optional.empty(), actual);
    }

    @Test
    void mapTransformsPresentValueAndPreservesEmpty() {
        assertEquals(
            Optional.of("AN"),
            directory.findName(1).map(String::toUpperCase)
        );
        assertEquals(
            Optional.empty(),
            directory.findName(99).map(String::toUpperCase)
        );
    }

    @Test
    void filterKeepsMatchingValueAndEmptiesNonMatchingValue() {
        Optional<String> name = directory.findName(1);

        assertEquals(Optional.of("An"), name.filter(value -> value.startsWith("A")));
        assertEquals(Optional.empty(), name.filter(value -> value.startsWith("B")));
        assertEquals(Optional.empty(), directory.findName(99)
            .filter(value -> value.startsWith("A")));
    }

    @Test
    void orElseGetCallsSupplierOnlyForEmptyResult() {
        AtomicInteger calls = new AtomicInteger();
        Supplier<String> fallback = () -> {
            calls.incrementAndGet();
            return "Guest";
        };

        assertEquals("An", directory.findName(1).orElseGet(fallback));
        assertEquals(0, calls.get());

        assertEquals("Guest", directory.findName(99).orElseGet(fallback));
        assertEquals(1, calls.get());
    }

    @Test
    void orElseThrowFailsForEmptyResult() {
        assertEquals("An", directory.findName(1).orElseThrow());
        assertThrows(
            NoSuchElementException.class,
            () -> directory.findName(99).orElseThrow()
        );
    }

    @Test
    void factoriesHandleNullAsSpecified() {
        assertThrows(
            NullPointerException.class,
            () -> Optional.<String>of(null)
        );
        assertEquals(Optional.empty(), Optional.ofNullable(null));
    }

    private static final class UserDirectory {
        private final Map<Integer, String> names = Map.of(
            1, "An",
            2, "Binh"
        );

        Optional<String> findName(int id) {
            return Optional.ofNullable(names.get(id));
        }
    }
}
~~~

Chạy bằng Maven trong dự án đã khai báo JUnit Jupiter ở test scope:

~~~bash
mvn test
~~~

Hoặc chạy task test của Gradle nếu dự án dùng Gradle và đã cấu hình JUnit Platform:

~~~bash
./gradlew test
~~~

JUnit Jupiter cần có trong test dependencies và test engine cần được bật theo cấu hình build của dự án. Không cần thêm dependency vào ứng dụng production chỉ để sử dụng các assertion trong test.

## 9. Smoke test không cần framework

Khi muốn xác minh nhanh hành vi Optional bằng JDK, có thể dùng một chương trình Java độc lập với assertion đơn giản:

**Tệp OptionalCasesDemo.java:**

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class OptionalCasesDemo {
    private static final Map<Integer, String> USERS = Map.of(
        1, "An",
        2, "Binh"
    );

    private static Optional<String> findName(int id) {
        return Optional.ofNullable(USERS.get(id));
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Optional<String> found = findName(1);
        check(found.isPresent(), "expected a value");
        check(found.equals(Optional.of("An")), "unexpected value");
        System.out.println("found present: " + found.isPresent());
        System.out.println("found value: " + found.orElseThrow());

        Optional<String> missing = findName(99);
        check(missing.isEmpty(), "expected empty");
        check(missing.equals(Optional.empty()), "unexpected empty result");
        System.out.println("missing empty: " + missing.isEmpty());

        check(found.map(String::toUpperCase).equals(Optional.of("AN")),
                "map value failed");
        check(missing.map(String::toUpperCase).isEmpty(),
                "map empty failed");
        System.out.println("map value: " + found.map(String::toUpperCase).orElseThrow());
        System.out.println("map empty: " + missing.map(String::toUpperCase).isEmpty());

        check(found.filter(name -> name.startsWith("A")).isPresent(),
                "filter match failed");
        check(found.filter(name -> name.startsWith("B")).isEmpty(),
                "filter mismatch failed");
        System.out.println("filter accepted: "
                + found.filter(name -> name.startsWith("A")).isPresent());
        System.out.println("filter rejected: "
                + found.filter(name -> name.startsWith("B")).isEmpty());

        AtomicInteger calls = new AtomicInteger();
        Supplier<String> fallback = () -> {
            calls.incrementAndGet();
            return "Guest";
        };

        check(found.orElseGet(fallback).equals("An"), "present fallback failed");
        check(calls.get() == 0, "fallback should not run for present value");
        System.out.println("orElseGet calls for present: " + calls.get());

        check(missing.orElseGet(fallback).equals("Guest"), "empty fallback failed");
        check(calls.get() == 1, "fallback should run once for empty value");
        System.out.println("orElseGet calls for empty: " + calls.get());

        check(Optional.ofNullable(null).isEmpty(), "ofNullable(null) should be empty");
        try {
            Optional.of(null);
            throw new AssertionError("Optional.of(null) should fail");
        } catch (NullPointerException expected) {
            System.out.println("Optional.of(null): rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all OptionalCasesDemo.java
java OptionalCasesDemo
~~~

Kết quả chuẩn:

~~~text
found present: true
found value: An
missing empty: true
map value: AN
map empty: true
filter accepted: true
filter rejected: true
orElseGet calls for present: 0
orElseGet calls for empty: 1
Optional.of(null): rejected
~~~

Chương trình dùng check() để dừng ngay khi kết quả sai. Vì vậy output trên chỉ được in đầy đủ nếu các điều kiện kiểm thử đều đúng.

## 10. Những lỗi thường gặp khi viết test

- **Chỉ kiểm tra isPresent():** trường hợp có giá trị vẫn có thể trả về sai nội dung. Hãy kiểm tra cả giá trị mong đợi.
- **Dùng get() không kiểm tra:** nếu Optional rỗng, get() ném NoSuchElementException. Dùng orElseThrow() sau khi đã xác nhận trạng thái.
- **So sánh bằng ==:** Optional là value-based class. Dùng equals(), isPresent() hoặc isEmpty().
- **Chấp nhận phương thức trả về null:** một API trả Optional phải trả Optional.empty() khi không có kết quả. Dùng assertNotNull để kiểm tra hợp đồng.
- **Bọc kết quả bằng ofNullable trong test:** thao tác này có thể biến lỗi trả về null thành Optional.empty() và che mất lỗi của phương thức.
- **Chỉ kiểm thử nhánh có giá trị:** luôn có ca kiểm thử cho mã không tìm thấy, dữ liệu vắng mặt hoặc predicate không khớp.
- **Không kiểm tra Supplier:** nếu fallback có tác dụng phụ hoặc chi phí cao, xác nhận orElseGet chỉ chạy khi Optional rỗng.
- **Nhầm of và ofNullable:** of(null) ném NullPointerException; ofNullable(null) tạo Optional.empty().
- **Kiểm thử phụ thuộc dữ liệu bên ngoài:** dùng dữ liệu cố định hoặc fake dependency để kết quả ổn định và dễ tái hiện.

## 11. Checklist cho một bộ test Optional

| Trường hợp | Điều cần xác nhận |
|---|---|
| Có dữ liệu | Optional không null, present và chứa đúng giá trị |
| Không có dữ liệu | Optional không null và empty |
| map với present | Giá trị được biến đổi đúng |
| map với empty | Kết quả vẫn empty |
| filter khớp | Giá trị được giữ lại |
| filter không khớp | Kết quả empty |
| orElse/orElseGet | Fallback đúng với từng trạng thái |
| orElseThrow | Giá trị được trả về hoặc exception được ném đúng |
| of/ofNullable | null được xử lý đúng theo hợp đồng |
| Supplier | Chỉ được gọi khi cần fallback |

Không phải mọi phương thức đều cần đủ tất cả các ca trên. Chọn test theo hành vi thực tế của phương thức đang kiểm tra. Với một phương thức tra cứu đơn giản, hai ca có giá trị và rỗng là nền tảng; thêm các ca biến đổi hoặc fallback khi phương thức sử dụng các thao tác đó.

## 12. Ghi nhớ

Kiểm thử Optional phải xác nhận cả trạng thái và dữ liệu. Trường hợp có kết quả cần kiểm tra giá trị chính xác; trường hợp không có kết quả cần kiểm tra Optional.empty(), không phải null. Dùng JUnit Jupiter để viết test rõ ràng, dùng orElseThrow() khi cần lấy giá trị bắt buộc và kiểm tra Supplier nếu fallback có tác dụng phụ. Luôn bao gồm cả nhánh có giá trị và nhánh rỗng để bảo đảm hợp đồng của phương thức.
