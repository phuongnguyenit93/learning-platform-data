# Chọn IllegalArgumentException và NullPointerException cho hợp đồng đầu vào

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá các cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này hướng dẫn chọn loại ngoại lệ nhất quán khi xác thực component trong canonical constructor: từ chối tham chiếu null và từ chối giá trị không null nhưng vi phạm hợp đồng dữ liệu.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt đầu vào null với đầu vào có giá trị nhưng không hợp lệ.
- Chọn `NullPointerException` cho component bắt buộc bị null và `IllegalArgumentException` cho giá trị không null vi phạm miền hoặc quan hệ.
- Dùng `Objects.requireNonNull` để kiểm tra null trước khi xử lý dữ liệu.
- Đặt validation trong canonical constructor để mọi đường khởi tạo đều được kiểm tra.
- Xác định khi nào component được phép null và không nên từ chối nó.
- Giữ lại ngoại lệ chuyên biệt của API parse hoặc chuyển đổi khi phù hợp.
- Viết Javadoc và unit test thể hiện rõ hợp đồng ngoại lệ.

## 1. Ngoại lệ là một phần của hợp đồng constructor

Một record không chỉ mô tả tên và kiểu của dữ liệu. Canonical constructor còn xác định dữ liệu nào được chấp nhận để tạo ra một đối tượng hợp lệ.

Ví dụ:

```java
public record Percentage(int value) {
    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "value must be between 0 and 100"
            );
        }
    }
}
```

Đoạn mã xác định rõ miền giá trị hợp lệ của `Percentage`. Nếu người gọi truyền số ngoài khoảng, constructor từ chối tạo record và ném `IllegalArgumentException`.

Với component kiểu tham chiếu, cần quyết định thêm liệu null có được chấp nhận hay không. Nếu component bắt buộc phải có giá trị, hợp đồng nên nói rõ và ném một ngoại lệ phù hợp khi nhận null.

Hai tình huống thường gặp:

- **Tham chiếu null:** bên gọi không cung cấp đối tượng cần thiết, trong khi component bắt buộc phải có.
- **Giá trị không null nhưng không hợp lệ:** đối tượng đã được cung cấp, nhưng nội dung nằm ngoài miền giá trị hoặc vi phạm quy tắc nghiệp vụ.

Phân biệt hai trường hợp giúp người dùng API hiểu nguyên nhân lỗi và xử lý đúng ở phía gọi.

## 2. Dùng NullPointerException khi component bắt buộc không được null

Trong Java, `NullPointerException` là lựa chọn thông dụng khi một đối số tham chiếu bắt buộc nhưng bên gọi truyền null. `Objects.requireNonNull` cung cấp cách kiểm tra rõ ràng và trả lại chính tham chiếu nếu nó khác null.

Ví dụ:

```java
import java.util.Objects;

public record UserName(String value) {

    public UserName {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                    "value must not be blank"
            );
        }
    }
}
```

Có hai điều kiện khác nhau trong constructor:

1. `Objects.requireNonNull(value, "value")` ném `NullPointerException` nếu tham số `value` là null.
2. Nếu `value` không null nhưng sau khi bỏ khoảng trắng trở thành chuỗi rỗng, constructor ném `IllegalArgumentException`.

Việc gán lại tham số ngầm `value` là hợp lệ trong compact constructor. Compiler sẽ gán giá trị cuối cùng vào component field sau khi thân constructor kết thúc bình thường.

Kết quả:

```java
new UserName("  linh  "); // Hợp lệ, lưu "linh"
new UserName("   ");      // IllegalArgumentException
new UserName(null);       // NullPointerException
```

Không cần tự viết kiểm tra null bằng một thông điệp chung nếu `Objects.requireNonNull` đã thể hiện rõ điều kiện. Nếu API chọn `IllegalArgumentException` cho null vì yêu cầu tương thích hoặc hợp đồng riêng, hãy ghi rõ chính sách và áp dụng nhất quán.

## 3. Dùng IllegalArgumentException khi giá trị không null vi phạm quy tắc

`IllegalArgumentException` phù hợp khi giá trị đã được cung cấp nhưng không thỏa điều kiện mà constructor yêu cầu.

Ví dụ với số cổng:

```java
public record ServerPort(int value) {

    public ServerPort {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException(
                    "port must be between 1 and 65535"
            );
        }
    }
}
```

Các giá trị `0`, `-1` và `70000` đều là số nguyên hợp lệ về mặt kiểu dữ liệu, nhưng không hợp lệ đối với miền giá trị của một cổng TCP/UDP.

Một ví dụ khác là kiểm tra quan hệ giữa nhiều component:

```java
import java.time.LocalDate;
import java.util.Objects;

public record DateRange(LocalDate start, LocalDate end) {

    public DateRange {
        start = Objects.requireNonNull(start, "start");
        end = Objects.requireNonNull(end, "end");

        if (start.isAfter(end)) {
            throw new IllegalArgumentException(
                    "start must not be after end"
            );
        }
    }
}
```

Trong record `DateRange`:

- `start == null`: ném `NullPointerException` vì ngày bắt đầu là bắt buộc.
- `end == null`: ném `NullPointerException` vì ngày kết thúc là bắt buộc.
- `start` và `end` đều có giá trị nhưng start sau end: ném `IllegalArgumentException` vì tổ hợp dữ liệu không hợp lệ.

Kiểm tra null trước khi gọi phương thức trên component. Sau đó mới thực hiện validation nghiệp vụ trên từng giá trị và quan hệ giữa chúng.

## 4. Bảng chọn ngoại lệ

| Tình huống trong constructor | Ngoại lệ thường phù hợp | Lý do |
| --- | --- | --- |
| Component bắt buộc nhận null | `NullPointerException` | Tham chiếu bắt buộc không được cung cấp. |
| Chuỗi khác null nhưng rỗng hoặc chỉ có khoảng trắng | `IllegalArgumentException` | Có giá trị, nhưng không thỏa hợp đồng. |
| Số khác null nhưng ngoài miền cho phép | `IllegalArgumentException` | Giá trị nằm ngoài giới hạn. |
| Hai component đều khác null nhưng mâu thuẫn | `IllegalArgumentException` | Tổ hợp đầu vào không hợp lệ. |
| Component được phép null theo mô hình dữ liệu | Không cần ném ngoại lệ vì null | Null là trạng thái được hợp đồng cho phép. |
| Chuỗi có cú pháp sai trong API parse chuyên biệt | Ngoại lệ parse được API quy định, hoặc `IllegalArgumentException` nếu factory chuẩn hóa hợp đồng | Không nên làm mất thông tin lỗi chuyên biệt một cách tùy tiện. |

Đây là quy ước thiết kế phổ biến, không phải quy tắc ngôn ngữ bắt buộc rằng mọi null đều phải tạo `NullPointerException`. Điều quan trọng là chọn chính sách rõ ràng, phù hợp ý nghĩa đầu vào và được công bố cho người sử dụng API.

## 5. Kiểm tra null trước khi gọi phương thức trên component

Một lỗi thường gặp là gọi phương thức trên component trước khi kiểm tra null:

```java
public record UserName(String value) {

    public UserName {
        if (value.isBlank()) {
            throw new IllegalArgumentException(
                    "value must not be blank"
            );
        }
    }
}
```

Nếu `value` là null, lời gọi `isBlank()` tự phát sinh `NullPointerException`. Mã vẫn thất bại, nhưng ngoại lệ đến từ thao tác dereference và thông điệp có thể không nói rõ component nào bắt buộc.

Nên kiểm tra rõ:

```java
import java.util.Objects;

public record UserName(String value) {

    public UserName {
        value = Objects.requireNonNull(value, "value");

        if (value.isBlank()) {
            throw new IllegalArgumentException(
                    "value must not be blank"
            );
        }

        value = value.strip();
    }
}
```

`Objects.requireNonNull` làm rõ hợp đồng và cho phép chỉ định tên tham số trong thông điệp. Sau dòng kiểm tra, constructor có thể xử lý `value` an toàn.

Một cách viết kết hợp kiểm tra và chuẩn hóa cũng hợp lệ:

```java
value = Objects.requireNonNull(value, "value").strip();
```

Chọn cách tách dòng hoặc kết hợp theo độ dễ đọc. Với validation nhiều bước, tách dòng thường giúp người đọc nhận ra từng điều kiện rõ hơn.

## 6. Không mặc định mọi component đều bắt buộc khác null

Null chỉ nên bị từ chối khi mô hình dữ liệu hoặc hợp đồng API quy định component đó là bắt buộc.

Ví dụ, một hồ sơ có thể cho phép thiếu tên hiển thị phụ:

```java
import java.util.Objects;

public record Profile(String username, String nickname) {

    public Profile {
        username = Objects.requireNonNull(
                username, "username"
        ).strip();

        if (username.isEmpty()) {
            throw new IllegalArgumentException(
                    "username must not be blank"
            );
        }

        if (nickname != null) {
            nickname = nickname.strip();

            if (nickname.isEmpty()) {
                nickname = null;
            }
        }
    }
}
```

Trong ví dụ này:

- `username` là bắt buộc, nên null bị từ chối.
- `nickname` là tùy chọn, nên null được chấp nhận.
- Nếu nickname có giá trị nhưng chỉ gồm khoảng trắng, chính sách ví dụ chuẩn hóa nó thành null.

Quyết định chuyển chuỗi rỗng thành null là chính sách nghiệp vụ, không phải yêu cầu của Java. Nếu ứng dụng cần phân biệt "không được cung cấp", "đã cung cấp chuỗi rỗng" và "có nội dung", hãy giữ các trạng thái riêng thay vì tự động chuẩn hóa.

Nếu dùng `Optional` làm component, bản thân đối tượng `Optional` thường nên không null, còn `Optional.empty()` biểu diễn giá trị vắng mặt:

```java
import java.util.Objects;
import java.util.Optional;

public record Profile(String username, Optional<String> nickname) {

    public Profile {
        username = Objects.requireNonNull(username, "username");
        nickname = Objects.requireNonNull(nickname, "nickname");
    }
}
```

`new Profile("linh", Optional.empty())` hợp lệ. `new Profile("linh", null)` bị từ chối vì component Optional bắt buộc phải có đối tượng Optional.

## 7. Đặt validation chung trong canonical constructor

Record có thể có constructor bổ sung. Các constructor không phải canonical phải ủy quyền đến constructor khác của cùng record bằng `this(...)`. Vì vậy, canonical constructor là nơi thích hợp để bảo vệ bất biến chung của component.

Ví dụ:

```java
import java.util.Objects;

public record RetryPolicy(int maxAttempts, String name) {

    public RetryPolicy {
        name = Objects.requireNonNull(name, "name").strip();

        if (maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException(
                    "maxAttempts must be between 1 and 10"
            );
        }

        if (name.isEmpty()) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }
    }

    public RetryPolicy(int maxAttempts) {
        this(maxAttempts, "default");
    }

    public RetryPolicy() {
        this(3);
    }
}
```

Dù người gọi sử dụng constructor nào, quá trình cuối cùng vẫn đi qua canonical constructor:

- Constructor không tham số cung cấp mặc định.
- Constructor một tham số bổ sung tên mặc định.
- Canonical constructor kiểm tra null, chuẩn hóa tên và kiểm tra giới hạn số lần thử.

Không nên lặp cùng validation trong từng overload. Nếu các constructor bổ sung tự kiểm tra theo cách khác nhau, chính sách ngoại lệ có thể không nhất quán.

## 8. Factory method cũng cần hợp đồng ngoại lệ rõ ràng

Static factory có thể kiểm tra điều kiện đặc thù của nguồn đầu vào, sau đó gọi canonical constructor để kiểm tra bất biến chung.

Ví dụ:

```java
import java.util.Objects;

public record UserId(String value) {

    public UserId {
        value = Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                    "value must not be blank"
            );
        }
    }

    public static UserId parse(String text) {
        text = Objects.requireNonNull(text, "text").strip();

        String prefix = "user:";
        if (!text.startsWith(prefix)) {
            throw new IllegalArgumentException(
                    "expected format user:<id>"
            );
        }

        return new UserId(text.substring(prefix.length()));
    }
}
```

Hợp đồng của factory:

- `text == null`: `NullPointerException` vì văn bản đầu vào là bắt buộc.
- Chuỗi không có tiền tố `user:`: `IllegalArgumentException` vì định dạng không hợp lệ.
- Phần ID sau tiền tố rỗng: canonical constructor từ chối bằng `IllegalArgumentException`.
- Phần ID hợp lệ: factory tạo `UserId` thông qua canonical constructor.

Factory nên kiểm tra cú pháp hoặc quy tắc riêng của nguồn; canonical constructor bảo vệ trạng thái cuối cùng của record. Tránh sao chép toàn bộ validation chung ở từng factory.

## 9. Không ép mọi lỗi parse thành IllegalArgumentException

Các API chuyển đổi trong JDK có thể ném ngoại lệ chuyên biệt. Hãy hiểu hợp đồng của API được gọi trước khi quyết định có chuyển đổi ngoại lệ hay không.

Ví dụ:

```java
int value = Integer.parseInt("abc");
// NumberFormatException
```

`NumberFormatException` là lớp con của `IllegalArgumentException`. Do đó, nó đã phù hợp với nhóm lỗi đối số không hợp lệ, đồng thời giữ thêm thông tin rằng việc phân tích số thất bại.

Với ngày tháng:

```java
import java.time.LocalDate;

LocalDate date = LocalDate.parse("2026-99-40");
// DateTimeParseException
```

`DateTimeParseException` là ngoại lệ chuyên biệt của API thời gian và không phải lớp con của `IllegalArgumentException`. Một factory có thể giữ nguyên ngoại lệ này để người gọi biết lỗi đến từ bộ phân tích ngày tháng.

Nếu hợp đồng API muốn chuẩn hóa lỗi định dạng thành `IllegalArgumentException`, hãy chuyển đổi có chủ đích và giữ nguyên nguyên nhân:

```java
public record Port(int value) {

    public Port {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException(
                    "port must be between 1 and 65535"
            );
        }
    }

    public static Port parse(String text) {
        text = java.util.Objects.requireNonNull(text, "text");

        final int parsed;
        try {
            parsed = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "port must be a decimal integer",
                    ex
            );
        }

        return new Port(parsed);
    }
}
```

Ở đây factory chuyển riêng lỗi cú pháp số thành `IllegalArgumentException` và giữ `NumberFormatException` làm cause. Canonical constructor tiếp tục kiểm tra miền cổng.

Không nên viết `catch (RuntimeException ex)` rồi chuyển mọi lỗi thành `IllegalArgumentException`. Cách đó có thể che khuất lỗi lập trình, lỗi trạng thái hoặc ngoại lệ có ý nghĩa chuyên biệt.

## 10. Phân biệt lỗi đối số với lỗi trạng thái

`IllegalArgumentException` và `NullPointerException` thường phù hợp khi dữ liệu truyền vào constructor không thỏa hợp đồng. Một số ngoại lệ khác có ý nghĩa riêng:

| Ngoại lệ | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| `NullPointerException` | Tham chiếu bắt buộc bị null | `Objects.requireNonNull(name, "name")` |
| `IllegalArgumentException` | Giá trị hoặc tổ hợp giá trị không hợp lệ | Port ngoài khoảng 1–65535 |
| `NumberFormatException` | Chuỗi không thể phân tích thành số theo cú pháp yêu cầu | `Integer.parseInt("abc")` |
| `DateTimeParseException` | Văn bản ngày giờ không thể phân tích theo formatter | `LocalDate.parse("2026-99-40")` |
| `IndexOutOfBoundsException` | Chỉ số nằm ngoài phạm vi của cấu trúc | Truy cập phần tử tại index không tồn tại |
| `IllegalStateException` | Trạng thái hiện tại của đối tượng không cho phép thao tác | Gọi thao tác sau khi tài nguyên đã đóng |

Không dùng `IllegalStateException` để thay cho lỗi đối số chỉ vì constructor đang chạy. Đối tượng chưa được tạo thành công; điều cần xác định là dữ liệu đầu vào có đáp ứng hợp đồng hay không.

Cũng không dùng `AssertionError` hoặc câu lệnh `assert` để thay thế validation đầu vào công khai. Assertion có thể bị tắt khi chạy JVM và chủ yếu dành cho kiểm tra giả định nội bộ trong quá trình phát triển.

## 11. Thông điệp ngoại lệ nên hữu ích và ổn định

Thông điệp nên cho người gọi biết component hoặc điều kiện nào không hợp lệ:

```java
throw new IllegalArgumentException(
        "maxAttempts must be between 1 and 10"
);
```

Thông điệp tốt thường:

- Nêu tên component.
- Nêu điều kiện mong đợi hoặc miền giá trị.
- Không phụ thuộc vào chi tiết nội bộ của implementation.
- Không chứa dữ liệu nhạy cảm như mật khẩu, token hoặc nội dung bí mật.
- Không buộc test phải phụ thuộc vào thông điệp mặc định do JDK tạo ra.

Với null, có thể dùng thông điệp cố định:

```java
Objects.requireNonNull(apiKey, "apiKey");
```

Không nên đưa chính giá trị đầu vào vào thông điệp nếu nó có thể chứa dữ liệu nhạy cảm. Tên tham số thường đã đủ để xác định vị trí cần sửa.

## 12. Ghi rõ ngoại lệ trong Javadoc

Constructor công khai nên mô tả điều kiện đầu vào và ngoại lệ mà bên gọi có thể gặp.

Ví dụ:

```java
public record Percentage(int value) {

    /**
     * @throws IllegalArgumentException if value is outside 0 through 100
     */
    public Percentage {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException(
                    "value must be between 0 and 100"
            );
        }
    }
}
```

Với component tham chiếu bắt buộc, bổ sung `@throws NullPointerException`:

```java
public record UserName(String value) {

    /**
     * @throws NullPointerException if value is null
     * @throws IllegalArgumentException if value is blank
     */
    public UserName {
        value = java.util.Objects.requireNonNull(value, "value").strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException("value must not be blank");
        }
    }
}
```

Tài liệu nên mô tả điều kiện, không chỉ liệt kê tên ngoại lệ. Người gọi cần biết cách cung cấp dữ liệu đúng.

## 13. Kiểm thử loại ngoại lệ và điều kiện gây lỗi

Unit test nên kiểm tra loại ngoại lệ cho từng trường hợp trong hợp đồng. Với JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class UserNameTest {

    @Test
    void rejectsNullWithNullPointerException() {
        assertThrows(
                NullPointerException.class,
                () -> new UserName(null)
        );
    }

    @Test
    void rejectsBlankWithIllegalArgumentException() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new UserName("   ")
        );
    }

    @Test
    void acceptsAndNormalizesValidValue() {
        UserName userName = new UserName("  linh  ");

        assertEquals("linh", userName.value());
    }
}
```

Với `DateRange`, nên kiểm tra cả ba trường hợp:

- start null hoặc end null: `NullPointerException`.
- start sau end: `IllegalArgumentException`.
- start bằng end hoặc start trước end: khởi tạo thành công.

Nên ưu tiên kiểm tra loại ngoại lệ và kết quả hợp đồng. Chỉ kiểm tra chính xác thông điệp khi thông điệp đó được xem là một phần API ổn định mà dự án cam kết duy trì. Tránh phụ thuộc vào thông điệp mặc định của JDK vì chúng có thể khác nhau giữa phiên bản hoặc cách phát sinh lỗi.

## 14. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `IllegalArgumentException` cho mọi trường hợp null mà không có lý do | Hợp đồng không phân biệt rõ thiếu tham chiếu và giá trị sai. | Dùng `NullPointerException` cho component bắt buộc null theo quy ước API. |
| Gọi phương thức trên tham số trước khi kiểm tra null | Phát sinh NPE từ dereference, thông điệp kém rõ. | Dùng `Objects.requireNonNull` trước. |
| Dùng `NullPointerException` cho số ngoài miền | Nhầm giá trị sai miền với tham chiếu null. | Dùng `IllegalArgumentException`. |
| Từ chối mọi component null | Không biểu diễn được trạng thái null hợp lệ của miền dữ liệu. | Xác định component nào thực sự bắt buộc. |
| Lặp validation trong từng overload | Các đường tạo có thể trả về loại ngoại lệ khác nhau. | Đặt bất biến chung trong canonical constructor. |
| Chuyển mọi `RuntimeException` thành `IllegalArgumentException` | Che khuất lỗi và mất loại ngoại lệ có ý nghĩa. | Chỉ chuyển đổi ngoại lệ cụ thể khi hợp đồng yêu cầu. |
| Dùng `assert` để kiểm tra input công khai | Assertion có thể bị tắt. | Dùng validation tường minh và ngoại lệ phù hợp. |
| Kiểm tra thông điệp mặc định của JDK trong test | Test dễ phụ thuộc phiên bản hoặc implementation. | Kiểm tra loại ngoại lệ và hợp đồng; dùng thông điệp do API tự định nghĩa nếu cần. |
| Ghi dữ liệu nhạy cảm vào thông điệp lỗi | Có thể làm lộ thông tin qua log hoặc telemetry. | Nêu tên component và điều kiện, không in giá trị bí mật. |

## 15. Bài tập tự luyện

### Bài 1: Chọn ngoại lệ cho tên người dùng

Record `UserName(String value)` yêu cầu value khác null và không rỗng sau khi bỏ khoảng trắng. Nên dùng ngoại lệ nào cho từng trường hợp?

**Đáp án:**

- `value == null`: `NullPointerException`.
- value chỉ chứa khoảng trắng: `IllegalArgumentException`.
- value hợp lệ: lưu chuỗi đã chuẩn hóa.

### Bài 2: Kiểm tra miền giá trị

Viết record `Temperature(double celsius)` từ chối giá trị không hữu hạn và giá trị thấp hơn `-273.15`.

**Đáp án tham khảo:**

```java
public record Temperature(double celsius) {
    public Temperature {
        if (!Double.isFinite(celsius) || celsius < -273.15) {
            throw new IllegalArgumentException(
                    "celsius must be finite and at least -273.15"
            );
        }
    }
}
```

Component primitive không thể null. Các giá trị NaN, vô cực hoặc thấp hơn giới hạn là giá trị không hợp lệ nên dùng `IllegalArgumentException`.

### Bài 3: Xác thực quan hệ component

Record `DateRange(LocalDate start, LocalDate end)` yêu cầu cả hai ngày khác null và start không sau end. Hãy xác định ngoại lệ cho từng lỗi.

**Đáp án:**

- start null hoặc end null: `NullPointerException`.
- start sau end: `IllegalArgumentException`.
- Các trường hợp còn lại: khởi tạo thành công.

### Bài 4: Giữ ngoại lệ parse

Một factory gọi `Integer.parseInt(text)`. Nếu text là `"abc"`, API JDK ném ngoại lệ gì? Có bắt buộc chuyển nó thành `IllegalArgumentException` không?

**Đáp án:** `NumberFormatException`, vốn là lớp con của `IllegalArgumentException`. Không bắt buộc chuyển đổi. Có thể giữ ngoại lệ gốc để bảo toàn thông tin; chỉ chuyển thành một ngoại lệ khác nếu hợp đồng API cần chuẩn hóa và phải giữ nguyên cause.

### Bài 5: Component null hợp lệ

Record `Profile(String username, String nickname)` cho phép nickname không được cung cấp. Có nên gọi `Objects.requireNonNull(nickname)` không?

**Đáp án:** Không, nếu null thực sự là trạng thái được hợp đồng cho phép. Chỉ kiểm tra username bắt buộc; xử lý nickname theo chính sách nullable đã công bố.

## Ghi nhớ

Dùng `NullPointerException` khi component tham chiếu bắt buộc nhưng nhận null; dùng `IllegalArgumentException` khi giá trị đã có nhưng nằm ngoài miền hoặc vi phạm quan hệ dữ liệu. `Objects.requireNonNull` giúp kiểm tra null rõ ràng trước khi xử lý. Đặt bất biến chung trong canonical constructor để mọi đường tạo record cùng tuân thủ hợp đồng. Không từ chối null nếu miền dữ liệu cho phép, không chuyển đổi bừa bãi ngoại lệ parse chuyên biệt và hãy ghi rõ điều kiện trong Javadoc cùng unit test.

## Tài liệu tham khảo

- [Java API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)).
- [Java API — NullPointerException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NullPointerException.html).
- [Java API — IllegalArgumentException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/IllegalArgumentException.html).
- [Java API — NumberFormatException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NumberFormatException.html).
- [Java API — DateTimeParseException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeParseException.html).
- [Java Language Specification — Java SE 26, `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
