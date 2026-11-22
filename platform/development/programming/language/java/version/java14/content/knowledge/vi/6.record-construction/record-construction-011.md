# Kiểm thử tham số `null`, dữ liệu sai và giá trị sau chuẩn hóa khi khởi tạo `record`

## 1. Mục tiêu kiểm thử

Một `record` không chỉ là cú pháp ngắn để lưu dữ liệu. Khi record biểu diễn dữ liệu đầu vào hoặc một giá trị nghiệp vụ, **constructor phải bảo đảm mọi instance được tạo thành công đều thỏa mãn bất biến (invariant)**. Kiểm thử cần xác nhận ba nhóm hành vi:

1. **`null`:** tham số bắt buộc không được `null`; constructor từ chối đầu vào đó bằng ngoại lệ phù hợp.
2. **Dữ liệu không hợp lệ:** giá trị rỗng, sai định dạng, hoặc nằm ngoài khoảng quy định bị từ chối; kiểm tra cả giá trị sát biên.
3. **Giá trị sau chuẩn hóa:** đầu vào hợp lệ nhưng khác cách viết (khoảng trắng thừa, chữ hoa, danh sách có phần tử cần chuẩn hóa) được lưu **đúng dạng chuẩn**. Kiểm tra giá trị qua accessor và tính độc lập với dữ liệu nguồn có thể thay đổi.

Bài dùng cú pháp `record` **chuẩn từ Java 16**, chạy trên JDK 17/21+ mà không bật preview. Java 14 là phiên bản đầu giới thiệu record dưới dạng preview; khi viết mã mới, sử dụng cú pháp và các quy tắc đã ổn định trên Java hiện đại.

## 2. Khởi tạo và kiểm tra trong compact constructor

Xét một chính sách đăng ký ví dụ với record:

- `username` bắt buộc, loại khoảng trắng đầu/cuối bằng `strip()`, chuyển về chữ thường với `Locale.ROOT`, sau đó phải khớp `[a-z][a-z0-9_]{2,15}` (3–16 ký tự ASCII, bắt đầu bằng chữ cái).
- `age` phải nằm trong **[13, 120]** (hai đầu mút đều hợp lệ). Đây là **quy tắc minh họa**, không phải quy định tuổi chung cho mọi ứng dụng.
- `skills` bắt buộc là một danh sách khác `null`; mỗi phần tử khác `null`, sau khi `strip()` và chuyển về chữ thường phải không rỗng. Danh sách có thể rỗng; giữ thứ tự và phần tử trùng, vì chính sách ví dụ không yêu cầu loại trùng.
- Record giữ **bản sao không sửa được** của danh sách để những thay đổi tiếp theo từ phía người gọi không làm đổi trạng thái record.

Một compact constructor hoạt động như sau:

```java
record Username(String value) {
    Username {
        value = java.util.Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

Đây là **khai báo record hoàn chỉnh**, nhưng không có phương thức `main`. Trong `Username { ... }`, biến `value` là **tham số constructor**. Khi constructor kết thúc thành công, Java tự gán giá trị cuối cùng của tham số này vào trường thành phần tương ứng. Vì thế, việc thay đổi `value` trong compact constructor là cách chuẩn hóa được hỗ trợ; không cần và không được gán trực tiếp `this.value` trong thân compact constructor.

### Phân loại lỗi có chủ đích

- `Objects.requireNonNull(param, "param")` ném `NullPointerException` khi một **tham số bắt buộc bị `null`**. Chuỗi tên tham số giúp chẩn đoán.
- Sau khi xác định tham số có giá trị, nếu giá trị **không đáp ứng quy tắc miền** (ví dụ chuỗi toàn khoảng trắng, sai mẫu tên, tuổi vượt ngưỡng) thì ném `IllegalArgumentException`.
- `List.copyOf(list)` tạo collection không sửa được và từ chối phần tử `null`. Nếu cần thông báo lỗi rõ theo từng phần tử, hãy kiểm tra trong vòng lặp trước khi sao chép.

Việc chọn loại ngoại lệ là một **hợp đồng thiết kế**: `NullPointerException` và `IllegalArgumentException` được dùng trong ví dụ cho dễ phân biệt, chứ Java không ép mọi record phải dùng đúng hai loại đó. Ở dự án thực tế, test phải phản ánh hợp đồng đã được công bố.

## 3. Bảng ca kiểm thử cần có

| Nhóm | Dữ liệu đầu vào | Điều cần khẳng định |
| --- | --- | --- |
| `null` ở record component | `username = null` | Ném `NullPointerException` |
| `null` ở collection | `skills = null` | Ném `NullPointerException` |
| `null` trong collection | `skills` chứa phần tử `null` | Ném `NullPointerException` |
| Username trống/sau trim trống | `"   "` | Ném `IllegalArgumentException` |
| Username sai ký tự | `"ada!"` | Ném `IllegalArgumentException` |
| Username quá ngắn | `"ab"` | Ném `IllegalArgumentException` |
| Tuổi dưới biên | `12` | Ném `IllegalArgumentException` |
| Tuổi trên biên | `121` | Ném `IllegalArgumentException` |
| Biên hợp lệ | `13` và `120` | Khởi tạo thành công |
| Thành phần skills rỗng sau chuẩn hóa | `List.of("   ")` | Ném `IllegalArgumentException` |
| Dữ liệu hợp lệ cần chuẩn hóa | `"  ADA_7  "` và `List.of(" Java ", " JVM ")` | `username()` là `"ada_7"`, `skills()` là `["java", "jvm"]` |
| Chống sửa từ nguồn | Sửa danh sách gốc sau khi tạo record | `skills()` của record **không thay đổi** |
| Chống sửa qua accessor | Thử `record.skills().add(...)` | Ném `UnsupportedOperationException` |
| Equality sau chuẩn hóa | Tạo hai record bằng hai cách viết khác nhau nhưng cùng giá trị chuẩn | `equals()` và `hashCode()` tương ứng bằng nhau |

**Điểm quan trọng:** chỉ kiểm tra "constructor không ném lỗi" là chưa đủ cho ca hợp lệ. Phải kiểm tra **giá trị được lưu sau chuẩn hóa**, ranh giới hợp lệ, tính bất biến nông và chính sách equality. Ngược lại, với ca sai, không nên chỉ kiểm tra thông báo log: cần kiểm tra **ngoại lệ thực sự được ném ra**.

## 4. Chương trình Java hoàn chỉnh: record, validation và bộ kiểm thử tự chạy

Lưu toàn bộ mã dưới đây vào **`Main.java`**. Ví dụ dùng cơ chế kiểm thử nhỏ với `check(...)` và `expectThrows(...)` để chạy độc lập bằng JDK, không phụ thuộc thư viện ngoài. Nó **không** dùng lệnh Java `assert` vì lệnh đó mặc định bị tắt nếu không chạy với `-ea`.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class Main {
    record Signup(String username, int age, List<String> skills) {
        Signup {
            username = Objects.requireNonNull(username, "username")
                    .strip()
                    .toLowerCase(Locale.ROOT);

            if (!username.matches("[a-z][a-z0-9_]{2,15}")) {
                throw new IllegalArgumentException("Invalid username");
            }

            if (age < 13 || age > 120) {
                throw new IllegalArgumentException("Age must be 13..120");
            }

            Objects.requireNonNull(skills, "skills");
            List<String> cleaned = new ArrayList<>();

            for (String skill : skills) {
                String value = Objects.requireNonNull(skill, "skill")
                        .strip()
                        .toLowerCase(Locale.ROOT);

                if (value.isEmpty()) {
                    throw new IllegalArgumentException("Blank skill");
                }
                cleaned.add(value);
            }

            skills = List.copyOf(cleaned);
        }
    }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    static void expectThrows(
            Class<? extends Throwable> expected,
            Runnable action
    ) {
        try {
            action.run();
        } catch (Throwable actual) {
            if (expected.isInstance(actual)) {
                return;
            }
            throw new AssertionError(
                    "Expected " + expected.getSimpleName()
                            + ", got " + actual.getClass().getSimpleName(),
                    actual
            );
        }
        throw new AssertionError(
                "Expected " + expected.getSimpleName() + " but nothing thrown"
        );
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of(" Java ", " JVM "));
        Signup a = new Signup("  ADA_7  ", 13, source);

        // Giá trị phải là dạng chuẩn, gồm cả biên tuổi hợp lệ.
        check(a.username().equals("ada_7"), "username normalized");
        check(a.age() == 13, "lower boundary accepted");
        check(a.skills().equals(List.of("java", "jvm")),
                "skills normalized");
        check(new Signup("ada", 120, List.of()).age() == 120,
                "upper boundary accepted");

        // Sửa danh sách nguồn không được thay đổi record.
        source.add("external");
        check(a.skills().equals(List.of("java", "jvm")),
                "defensive copy");
        expectThrows(UnsupportedOperationException.class,
                () -> a.skills().add("new"));

        // Sau chuẩn hóa, các component bằng nhau => record bằng nhau.
        Signup b = new Signup("ada_7", 13, List.of("java", "jvm"));
        check(a.equals(b), "value equality after normalization");
        check(a.hashCode() == b.hashCode(), "equal hash code");

        // Null bắt buộc: tham số và phần tử danh sách.
        expectThrows(NullPointerException.class,
                () -> new Signup(null, 13, List.of("java")));
        expectThrows(NullPointerException.class,
                () -> new Signup("ada", 13, null));
        expectThrows(NullPointerException.class,
                () -> new Signup("ada", 13,
                        Arrays.asList("java", null)));

        // Dữ liệu sai, tuổi ngoài biên và giá trị trống sau chuẩn hóa.
        expectThrows(IllegalArgumentException.class,
                () -> new Signup("   ", 13, List.of("java")));
        expectThrows(IllegalArgumentException.class,
                () -> new Signup("ada!", 13, List.of("java")));
        expectThrows(IllegalArgumentException.class,
                () -> new Signup("ab", 13, List.of("java")));
        expectThrows(IllegalArgumentException.class,
                () -> new Signup("ada", 12, List.of("java")));
        expectThrows(IllegalArgumentException.class,
                () -> new Signup("ada", 121, List.of("java")));
        expectThrows(IllegalArgumentException.class,
                () -> new Signup("ada", 13, List.of("   ")));

        System.out.println("normalized: "
                + a.username() + ", " + a.age() + ", " + a.skills());
        System.out.println("all checks passed");
    }
}
```

**Biên dịch và chạy (JDK 17 trở lên):**

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout mong đợi khi tất cả phép kiểm tra đều thành công:**

```text
normalized: ada_7, 13, [java, jvm]
all checks passed
```

Nếu một `check` thất bại hoặc ngoại lệ không đúng như mong đợi, chương trình sẽ ném `AssertionError`; khi đó sẽ **không** in đủ hai dòng thành công ở cuối. `expectThrows` kiểm tra loại ngoại lệ bằng `Class.isInstance`. Việc kiểm tra trên tập ví dụ này là một bộ test đơn giản để học cơ chế constructor; các dự án thực tế nên đặt test trong hệ thống kiểm thử của dự án.

### Đọc kết quả sau khởi tạo đúng cách

- Trường `username` thực sự là `"ada_7"`, không còn dấu cách ở hai đầu và không còn chữ hoa, vì compact constructor đã gán lại **tham số** trước khi Java tự gán vào trường của record.
- `age()` giữ nguyên số `13`; kiểm tra biên trên `120` cũng thành công. Giá trị `12` và `121` bị từ chối.
- `skills()` chứa `"java"`, `"jvm"` theo đúng thứ tự; bản gốc có khoảng trắng/chữ hoa bị chuẩn hóa.
- Thao tác `source.add("external")` chỉ tác động đến danh sách ban đầu. Record đã giữ `List.copyOf(cleaned)` nên danh sách trong record không thay đổi.
- Accessor `skills()` trả về danh sách không sửa được; gọi `add` trực tiếp lên danh sách đó ném `UnsupportedOperationException`.
- Hai lần tạo `Signup` từ những đầu vào khác cách viết có thể tạo record bằng nhau, vì **`equals` mặc định của record sử dụng các component đã được lưu sau chuẩn hóa**.

## 5. Kiểm thử với JUnit Jupiter trong dự án thực tế

Khi dự án đã cấu hình JUnit Jupiter, cách viết sau giúp mỗi nhóm kiểm thử có tên rõ ràng. Ví dụ giả định `Signup` là một kiểu record truy cập được từ lớp test (ví dụ khai báo trong cùng package). Đây là **đoạn lớp test**, cần đặt trong source set kiểm thử và có dependency JUnit Jupiter tương ứng.

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

class SignupTest {
    @Test
    void normalizesStoredValues() {
        Signup value = new Signup(
                "  ADA_7  ", 13, List.of(" Java ", " JVM "));
        assertEquals("ada_7", value.username());
        assertEquals(List.of("java", "jvm"), value.skills());
        assertEquals(
                new Signup("ada_7", 13, List.of("java", "jvm")),
                value
        );
    }

    @Test
    void rejectsNullAndInvalidData() {
        assertThrows(NullPointerException.class,
                () -> new Signup(null, 13, List.of()));
        assertThrows(NullPointerException.class,
                () -> new Signup("ada", 13, null));
        assertThrows(NullPointerException.class,
                () -> new Signup("ada", 13,
                        Arrays.asList("java", null)));

        assertThrows(IllegalArgumentException.class,
                () -> new Signup("  ", 13, List.of()));
        assertThrows(IllegalArgumentException.class,
                () -> new Signup("ada!", 13, List.of()));
        assertThrows(IllegalArgumentException.class,
                () -> new Signup("ada", 12, List.of()));
        assertThrows(IllegalArgumentException.class,
                () -> new Signup("ada", 121, List.of()));
    }

    @Test
    void preservesValueAfterCallerMutatesInputList() {
        List<String> supplied = new ArrayList<>(List.of(" Java "));
        Signup value = new Signup("ada", 120, supplied);
        supplied.add("changed");

        assertEquals(List.of("java"), value.skills());
        assertThrows(UnsupportedOperationException.class,
                () -> value.skills().add("other"));
    }
}
```

Để biên dịch lớp test trên, cần khai báo `Signup` như một record độc lập trong cùng package hoặc điều chỉnh tham chiếu thành `Main.Signup` nếu giữ record lồng trong `Main` ở ví dụ trước. Không nên sao chép lớp test rồi chạy chỉ bằng `javac SignupTest.java` khi chưa có JUnit trên classpath; hãy dùng lệnh test của hệ thống build đã cấu hình (ví dụ `./gradlew test` trong dự án Gradle có JUnit Platform).

**Chú ý:** `assertThrows(IllegalArgumentException.class, ...)` của JUnit trả về đối tượng ngoại lệ để có thể kiểm tra thông báo nếu đó là hợp đồng API. Không cần buộc test khớp nguyên văn thông báo lỗi nếu thông báo chỉ dùng để hỗ trợ chẩn đoán và có thể thay đổi.

## 6. Nên kiểm thử gì ở các ranh giới?

### 6.1 `null` và giá trị rỗng là hai ca khác nhau

`null` biểu thị **không có tham chiếu**. Chuỗi `""` là một đối tượng `String` tồn tại nhưng **không chứa ký tự**; `"   "` có các ký tự khoảng trắng và trở thành rỗng sau `strip()`. Vì vậy ba ca dưới đây không thay thế nhau:

```java
// Các lệnh nằm trong phương thức kiểm thử:
new Signup(null, 18, List.of());  // NullPointerException
new Signup("", 18, List.of());    // IllegalArgumentException
new Signup("   ", 18, List.of()); // IllegalArgumentException
```

Đoạn trên **cố ý phát sinh ngoại lệ** nên không chạy nối tiếp như một luồng thành công; phải đặt từng lời gọi trong `assertThrows` hoặc cơ chế `expectThrows` tương đương. Có thể thêm ca `"	"` để kiểm tra chính sách xóa whitespace. Nếu hệ thống cho phép `null` ở một component tùy chọn, cần diễn đạt rõ cách mặc định hóa hoặc ngữ nghĩa `null`; đừng tự áp dụng `requireNonNull` cho mọi dữ liệu.

### 6.2 Kiểm tra cả giá trị ngay trước và ngay sau biên

Nếu quy tắc là tuổi trong **13–120**, kiểm thử tối thiểu: `12` (sai), `13` (đúng), `120` (đúng), `121` (sai). Chỉ thử một tuổi hợp lệ như `25` không phát hiện được lỗi so sánh `<` thành `<=` hay `>` thành `>=`.

Tương tự, username theo regex trong ví dụ có chiều dài từ 3 đến 16; nên kiểm tra `"ab"` (2 ký tự, sai), `"abc"` (3 ký tự, đúng), chuỗi đúng 16 ký tự (đúng) và chuỗi 17 ký tự (sai). Việc dùng `matches` đối chiếu **toàn chuỗi**, chứ không chỉ tìm một đoạn khớp.

### 6.3 Kiểm tra trạng thái đã lưu, không chỉ biến đầu vào

Trong compact constructor, nếu gọi `username.strip()` nhưng **không gán kết quả trở lại `username`**, biến truyền vào record không tự đổi vì `String` bất biến:

```java
record IncorrectName(String name) {
    IncorrectName {
        name.strip(); // Sai mục tiêu: bỏ qua kết quả chuẩn hóa
    }
}
```

Đây là **mã hợp lệ về cú pháp nhưng sai yêu cầu chuẩn hóa**, vì record vẫn lưu tên gốc. Cách đúng:

```java
record CorrectName(String name) {
    CorrectName {
        name = java.util.Objects.requireNonNull(name, "name").strip();
    }
}
```

Trong test, phải gọi `new CorrectName(" A ").name()` và xác nhận nhận `"A"`. Chỉ kiểm tra constructor không ném ngoại lệ sẽ không phát hiện lỗi ở `IncorrectName`.

### 6.4 Kiểm tra bản sao phòng vệ theo hai chiều

Có hai đường có thể làm dữ liệu nội bộ thay đổi:

1. **Từ nguồn vào**: sau khi tạo record, người gọi sửa danh sách đã truyền vào. Test phải chứng minh kết quả accessor giữ nguyên.
2. **Từ accessor ra**: người gọi nhận danh sách qua accessor và cố sửa. Test phải chứng minh thao tác bị từ chối, hoặc accessor trả bản sao phòng vệ đúng chính sách.

`List.copyOf` xử lý hai yêu cầu đối với **cấu trúc danh sách**, nhưng là **sao chép nông**. Nếu phần tử là đối tượng mutable, phải cân nhắc copy từng phần tử hoặc mô hình khác. Không nên tuyên bố mọi record đều deep immutable.

### 6.5 Kiểm tra equality trên giá trị chuẩn

Với record, việc chuẩn hóa thay đổi kết quả `equals`/`hashCode`:

```java
var first = new Signup(" ADA_7 ", 13, List.of(" Java "));
var second = new Signup("ada_7", 13, List.of("java"));
System.out.println(first.equals(second)); // true
```

Đoạn này đặt trong phương thức có thể truy cập `Signup`. Hai record được tạo thành các object khác nhau, nhưng các component **sau chuẩn hóa** giống nhau nên bằng nhau theo equality mặc định. Khi chuẩn hóa collection, test thêm `hashCode` và lưu ý một record chỉ bất biến nông nếu thành phần của nó chứa cấu trúc mutable.

## 7. Những sai lầm thường gặp và cách tránh

| Sai lầm | Hệ quả | Cách kiểm thử/khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra tạo được record | Bỏ sót giá trị chưa chuẩn hóa | Assert từng accessor sau khởi tạo |
| Chỉ kiểm tra `null` | Bỏ sót chuỗi trống, blank, sai định dạng | Phân ca cho từng loại dữ liệu không hợp lệ |
| Chỉ kiểm tra giá trị giữa khoảng | Bỏ sót sai điều kiện ở biên | Dùng đúng bộ trước biên / tại biên / sau biên |
| Dùng `value.strip();` không gán | Chuỗi gốc vẫn được lưu | `value = value.strip();` và assert accessor |
| Gọi `strip()` trước khi kiểm tra `null` | Phát sinh NPE nhưng thiếu tên tham số mong muốn | `Objects.requireNonNull` trước khi xử lý |
| Chỉ dùng `final` của record để suy ra bất biến sâu | Danh sách/mảng chứa bên trong vẫn có thể sửa | Defensive copy và test cả hai chiều |
| Sửa trực tiếp `this.component` trong compact constructor | Không hợp lệ theo quy tắc khởi tạo record | Gán lại tham số component; để Java tự gán trường |
| Test gọi `assert condition;` nhưng không bật `-ea` | Phép kiểm tra có thể bị bỏ qua | Dùng JUnit assertions hoặc helper ném `AssertionError` |
| Chỉ kiểm tra exception message | Test mong manh, có thể bỏ sót loại lỗi | Kiểm tra loại ngoại lệ và hành vi; message chỉ nếu là contract |
| Dùng `toLowerCase()` phụ thuộc locale mặc định | Kết quả có thể khác giữa môi trường | Chọn `Locale.ROOT` khi chuẩn hóa mã/identifier không phụ thuộc ngôn ngữ |
| Coi `List.copyOf` tự chuẩn hóa mọi phần tử | Không tự trim/lowercase; chỉ sao chép cấu trúc và cấm sửa | Chuẩn hóa từng phần tử trước khi `List.copyOf` |

## 8. Áp dụng trong hệ thống thực tế

Khi dùng record cho DTO, kết quả truy vấn, thông điệp hoặc giá trị nghiệp vụ, hãy viết **hợp đồng dữ liệu** trước: trường nào bắt buộc, phạm vi hợp lệ, cách chuẩn hóa, có cho phép danh sách rỗng hay phần tử trùng hay không, và lỗi trả ra là gì. Sau đó:

1. Đặt các invariant đồng nhất trong compact constructor hoặc canonical constructor thích hợp, để **mọi lần tạo đối tượng hợp lệ** đều đi qua kiểm tra.
2. Viết test thành công với dữ liệu ở dạng **chưa chuẩn hóa** và assert giá trị đã lưu; thêm test với đầu vào đã chuẩn để chứng minh cùng kết quả.
3. Viết test riêng cho `null`, blank, ký tự sai, giá trị ngoài biên và collection chứa `null`.
4. Nếu có component tham chiếu mutable, kiểm tra chiến lược copy và tính ổn định của `equals`/`hashCode`.
5. Chọn rõ chính sách xử lý đầu vào thay vì lặng lẽ “sửa” dữ liệu vốn không hợp lệ. Ví dụ tên trống sau `strip()` phải bị từ chối trong hợp đồng này; không thay bằng giá trị giả.

Một số framework có cơ chế kiểm tra dữ liệu ở lớp API (ví dụ validation annotations), nhưng kiểm tra tại biên HTTP **không thay thế** hoàn toàn invariant trong constructor khi record còn được tạo từ batch, test, service hoặc các đường gọi khác. Khi thiết kế record phục vụ serializer/deserializer, cần đối chiếu cách framework gọi canonical constructor và hỗ trợ record ở phiên bản đang sử dụng.

**Ghi nhớ:** Kiểm thử khởi tạo record phải xác nhận **bị từ chối đúng khi đầu vào sai** và **được lưu đúng dạng chuẩn khi đầu vào hợp lệ**. Dùng ca `null`, blank, giới hạn biên, giá trị sau chuẩn hóa, defensive copy và equality để bảo vệ các invariant thực tế. Đây là những quy tắc vẫn áp dụng cho record chuẩn trong Java hiện đại.

### Tham khảo

- [JEP 395 — Records (chuẩn từ Java 16)](https://openjdk.org/jeps/395)
- [Java Language Specification — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java SE API — `List.copyOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
