# Thiết kế thông báo lỗi constructor dễ kiểm chứng

> **Chương:** Khởi tạo record  
> **Học phần:** `JAVA_VERSION_JAVA16` — khám phá các cải tiến từ Java 16 vẫn hữu ích trong Java hiện đại, đặc biệt là `record`. Bài này hướng dẫn thiết kế thông báo lỗi từ canonical constructor sao cho người phát triển hiểu điều kiện bị vi phạm, API giữ hành vi ổn định và unit test kiểm chứng đúng hợp đồng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Viết thông báo lỗi chỉ rõ component và điều kiện không hợp lệ.
- Phân biệt thông báo chẩn đoán dành cho lập trình viên với thông báo giao diện.
- Giữ thông điệp ổn định, không phụ thuộc chi tiết implementation hoặc thông báo mặc định của JDK.
- Tránh đưa dữ liệu nhạy cảm vào exception message và log.
- Quyết định khi nào nên đưa giá trị thực tế vào thông báo.
- Kiểm thử loại ngoại lệ, thông điệp và mã lỗi theo đúng mức cam kết của API.
- Tổ chức thông báo nhất quán giữa canonical constructor, overload và static factory.

## 1. Thông báo lỗi là một phần của hợp đồng API

Canonical constructor của record xác định điều kiện để một đối tượng hợp lệ được tạo. Khi dữ liệu không đáp ứng điều kiện, constructor ném ngoại lệ. Thông báo đi kèm giúp người gọi xác định component nào sai và cần sửa theo hướng nào.

Ví dụ quá mơ hồ:

```java
throw new IllegalArgumentException("Invalid input");
```

Người gọi không biết component nào sai, giá trị cần đáp ứng điều kiện gì hay lỗi đến từ quy tắc nào.

Thông báo rõ hơn:

```java
throw new IllegalArgumentException(
        "age must be between 0 and 150"
);
```

Thông báo này chỉ ra component `age` và điều kiện cần đáp ứng. Người gọi có thể sửa đầu vào mà không cần đọc implementation để đoán.

Thông báo tốt không cần kể lại toàn bộ quá trình xử lý. Nó cần mô tả hợp đồng bị vi phạm một cách ngắn gọn và hữu ích.

## 2. Cấu trúc của một thông báo dễ kiểm chứng

Với lỗi đầu vào trong constructor, cấu trúc hữu ích thường gồm:

1. **Tên component hoặc tham số:** xác định vị trí dữ liệu có vấn đề.
2. **Điều kiện mong đợi:** nêu miền giá trị, định dạng hoặc quan hệ cần thỏa mãn.
3. **Giá trị thực tế (nếu an toàn và hữu ích):** giúp chẩn đoán lỗi miền số hoặc kích thước.
4. **Mã lỗi ổn định (nếu cần phân loại bằng chương trình):** không buộc caller phân tích câu văn.

Ví dụ:

```java
public record RetryPolicy(int maxAttempts) {
    public RetryPolicy {
        if (maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException(
                    "maxAttempts must be between 1 and 10"
            );
        }
    }
}
```

Thông báo có tên component và điều kiện. Nó không phụ thuộc tên biến nội bộ, số dòng code hay tên phương thức helper.

Không phải thông báo nào cũng cần đủ mọi thành phần. Với một tham chiếu null, tên component có thể đã đủ:

```java
Objects.requireNonNull(name, "name");
```

Nếu muốn diễn đạt đầy đủ hơn, có thể truyền thông điệp cố định:

```java
Objects.requireNonNull(name, "name must not be null");
```

Điều quan trọng là giữ thông báo có chủ đích và nhất quán.

## 3. Nêu điều kiện, không chỉ nói dữ liệu sai

Các câu như `"invalid value"`, `"bad input"` hoặc `"something went wrong"` không giúp người gọi biết cần sửa gì.

Hãy mô tả điều kiện cụ thể:

| Thông báo yếu | Thông báo hữu ích hơn |
| --- | --- |
| `"Invalid value"` | `"port must be between 1 and 65535"` |
| `"Bad name"` | `"name must not be blank"` |
| `"Invalid range"` | `"start must not be after end"` |
| `"Wrong size"` | `"tags must contain at most 20 elements"` |
| `"Missing data"` | `"currency must not be null"` |
| `"Invalid format"` | `"date must use ISO-8601 format yyyy-MM-dd"` |

Thông báo nên mô tả hợp đồng chứ không mô tả dòng code đã thất bại. Ví dụ, `"value.strip() failed"` không hữu ích bằng `"username must not be blank"`.

Khi điều kiện phức tạp, hãy nêu các component liên quan và quan hệ mong đợi:

```java
throw new IllegalArgumentException(
        "endDate must be on or after startDate"
);
```

Người gọi biết cả hai component tham gia vào điều kiện.

## 4. Phân biệt thông báo cho null và giá trị sai miền

Loại ngoại lệ và thông điệp cần phản ánh đúng nguyên nhân. Với component tham chiếu bắt buộc:

- Null có thể được báo bằng `NullPointerException`, thường dùng `Objects.requireNonNull`.
- Giá trị không null nhưng không đáp ứng hợp đồng có thể được báo bằng `IllegalArgumentException`.

Ví dụ:

```java
import java.util.Objects;

public record UserName(String value) {

    public UserName {
        value = Objects.requireNonNull(
                value,
                "value must not be null"
        ).strip();

        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                    "value must not be blank"
            );
        }
    }
}
```

Hai lỗi có hai thông điệp riêng:

```java
new UserName(null);  // NullPointerException: value must not be null
new UserName("  "); // IllegalArgumentException: value must not be blank
```

Thông báo null nên nêu component bắt buộc. Thông báo giá trị sai nên nêu điều kiện mà giá trị khác null cần đáp ứng. Không nên dùng một câu chung cho mọi lỗi vì người gọi và unit test sẽ khó phân biệt nguyên nhân.

## 5. Đặt thông báo trong canonical constructor

Record có thể được tạo qua canonical constructor, constructor bổ sung hoặc static factory. Các đường tạo nên đi qua cùng canonical constructor để bảo vệ bất biến chung và giữ thông báo nhất quán.

Ví dụ:

```java
public record PageRequest(int page, int size) {

    public PageRequest {
        if (page < 1) {
            throw new IllegalArgumentException(
                    "page must be greater than or equal to 1"
            );
        }

        if (size < 1 || size > 200) {
            throw new IllegalArgumentException(
                    "size must be between 1 and 200"
            );
        }
    }

    public PageRequest(int page) {
        this(page, 20);
    }

    public static PageRequest firstPage(int size) {
        return new PageRequest(1, size);
    }
}
```

Dù người gọi sử dụng `new PageRequest(0, 20)`, `new PageRequest(1, 0)` hay `PageRequest.firstPage(0)`, lỗi của `page` hoặc `size` đều được phát ra từ canonical constructor.

Không nên viết một thông báo khác nhau cho cùng điều kiện trong từng overload. Khi quy tắc thay đổi, việc tập trung validation giúp thông điệp và hành vi không bị lệch.

## 6. Giữ thông báo ổn định qua refactor

Thông báo lỗi công khai nên phản ánh hợp đồng dữ liệu, không phản ánh cách code hiện tại được viết.

Không nên:

```java
throw new IllegalArgumentException(
        "Validation failed in UserName.java at line 42"
);
```

Hoặc:

```java
throw new IllegalArgumentException(
        "normalizeValue() returned an empty string"
);
```

Tên file, số dòng, tên helper và tên biến cục bộ có thể thay đổi khi refactor. Nếu test hoặc caller phụ thuộc chúng, một thay đổi nội bộ vô hại cũng có thể làm hỏng tích hợp.

Nên dùng thông báo gắn với hợp đồng:

```java
throw new IllegalArgumentException(
        "username must not be blank"
);
```

Thông báo này vẫn đúng dù implementation đổi từ `strip()` sang một helper chuẩn hóa khác.

Nếu chỉ refactor nội bộ mà hợp đồng đầu vào không đổi, thông báo lỗi cũng không nên phải đổi.

## 7. Có nên đưa giá trị thực tế vào thông báo?

Đưa giá trị thực tế có thể hữu ích khi nó an toàn và giúp chẩn đoán. Với số cổng, hiển thị giá trị sai có thể giúp người gọi tìm ra lỗi nhanh hơn:

```java
public record ServerPort(int value) {
    public ServerPort {
        if (value < 1 || value > 65535) {
            throw new IllegalArgumentException(
                    "port must be between 1 and 65535; received " + value
            );
        }
    }
}
```

Tuy nhiên, không nên tự động đưa mọi đầu vào vào thông điệp.

Các dữ liệu không nên xuất hiện trực tiếp trong exception message hoặc log nếu chúng có thể nhạy cảm:

- Mật khẩu, API key, access token hoặc refresh token.
- Số định danh cá nhân, email hoặc dữ liệu khách hàng.
- Nội dung tệp, payload hoặc chuỗi truy vấn có thể chứa thông tin riêng tư.
- Dữ liệu thanh toán hoặc thông tin xác thực.

Ví dụ không an toàn:

```java
throw new IllegalArgumentException(
        "apiKey is invalid: " + apiKey
);
```

Nên viết:

```java
throw new IllegalArgumentException(
        "apiKey must be a non-blank value"
);
```

Thông báo vẫn chỉ ra component và điều kiện nhưng không làm lộ giá trị bí mật.

Với dữ liệu không nhạy cảm, hãy cân nhắc kích thước và định dạng. Không nên đưa một chuỗi rất dài vào exception message. Có thể giới hạn độ dài hoặc chỉ hiển thị metadata an toàn.

## 8. Thông báo kỹ thuật không nên phụ thuộc locale mặc định

Nếu thông báo được dùng trong log kỹ thuật hoặc test, việc định dạng theo locale mặc định có thể khiến kết quả thay đổi giữa môi trường.

Ví dụ, cách định dạng số hoặc ngày theo locale có thể khác giữa máy phát triển và CI. Một test so sánh chính xác chuỗi có thể thất bại dù điều kiện validation không thay đổi.

Với thông báo kỹ thuật ổn định:

- Dùng câu chữ và định dạng thống nhất.
- Dùng biểu diễn chuẩn khi cần hiển thị số hoặc ngày.
- Không dựa vào locale mặc định cho chuỗi mà test cần so sánh chính xác.
- Không dùng exception message nội bộ làm nội dung giao diện.

Nếu sản phẩm cần đa ngôn ngữ, nên ánh xạ mã lỗi ổn định sang nội dung đã bản địa hóa ở tầng ứng dụng hoặc giao diện.

## 9. Dùng mã lỗi khi caller cần phân loại bằng chương trình

Thông điệp văn bản dành cho người đọc. Nếu caller cần phân biệt nhiều nguyên nhân một cách ổn định, đừng bắt họ phân tích câu văn. Có thể cung cấp mã lỗi có cấu trúc.

Ví dụ một exception chuyên biệt:

```java
// File: InvalidRecordInputException.java
import java.util.Objects;

public final class InvalidRecordInputException
        extends IllegalArgumentException {

    private final String code;

    public InvalidRecordInputException(String code, String message) {
        super(message);
        this.code = Objects.requireNonNull(code, "code");
    }

    public String code() {
        return code;
    }
}
```

Record sử dụng exception đó:

```java
// File: Money.java
public record Money(long minorUnits, String currency) {

    public Money {
        if (minorUnits < 0) {
            throw new InvalidRecordInputException(
                    "MONEY_AMOUNT_NEGATIVE",
                    "minorUnits must be greater than or equal to 0"
            );
        }

        currency = java.util.Objects.requireNonNull(
                currency, "currency must not be null"
        );

        currency = currency.strip().toUpperCase(
                java.util.Locale.ROOT
        );

        if (!currency.matches("[A-Z]{3}")) {
            throw new InvalidRecordInputException(
                    "MONEY_CURRENCY_FORMAT",
                    "currency must contain three ASCII letters"
            );
        }
    }
}
```

Caller có thể xử lý theo mã:

```java
try {
    Money money = new Money(-100, "VND");
} catch (InvalidRecordInputException ex) {
    switch (ex.code()) {
        case "MONEY_AMOUNT_NEGATIVE" ->
                System.out.println("Amount is below zero");
        case "MONEY_CURRENCY_FORMAT" ->
                System.out.println("Currency format is invalid");
        default ->
                throw ex;
    }
}
```

Mã lỗi phải ổn định và có ý nghĩa rõ ràng. Nếu API không cần caller phân loại lỗi theo mã, dùng exception chuẩn với thông điệp tốt thường đơn giản hơn. Không nên tạo hệ thống exception riêng chỉ để thay một câu thông báo ngắn.

Nếu chọn exception chuyên biệt, hãy xem mã lỗi là một phần API: tránh đổi hoặc tái sử dụng mã cho một ý nghĩa khác sau khi đã phát hành.

## 10. Phân biệt thông báo chẩn đoán và thông báo giao diện

Exception message trong constructor thường là thông tin chẩn đoán dành cho lập trình viên hoặc log kỹ thuật. Nó không mặc nhiên phù hợp để hiển thị trực tiếp cho người dùng cuối.

Ví dụ thông báo kỹ thuật:

```java
throw new IllegalArgumentException(
        "password must contain at least 12 characters"
);
```

Ứng dụng có thể chuyển lỗi này thành thông báo giao diện phù hợp:

```java
String userMessage = messageCatalog.get("PASSWORD_TOO_SHORT");
```

Cách thiết kế tốt:

- Constructor hoặc domain layer xác định lỗi theo hợp đồng dữ liệu.
- Tầng ứng dụng ánh xạ lỗi sang mã hoặc loại lỗi phù hợp.
- Tầng giao diện chọn câu chữ theo ngôn ngữ và ngữ cảnh người dùng.
- Log kỹ thuật chỉ ghi metadata cần thiết, không ghi bí mật.

Không nên phụ thuộc vào việc parse chuỗi `getMessage()` để xác định ngôn ngữ hoặc loại lỗi. Nội dung có thể thay đổi; mã lỗi hoặc kiểu exception mới là tín hiệu có cấu trúc phù hợp hơn.

## 11. Giữ cause khi chuyển đổi ngoại lệ

Một factory có thể gọi API parse và chuyển đổi lỗi sang exception thuộc hợp đồng của domain. Khi chuyển đổi, hãy giữ ngoại lệ gốc làm cause để không mất thông tin chẩn đoán.

Ví dụ:

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
        if (text == null) {
            throw new NullPointerException("text must not be null");
        }

        final int parsed;
        try {
            parsed = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "text must contain a decimal port number",
                    ex
            );
        }

        return new Port(parsed);
    }
}
```

Thông báo ngoài mô tả hợp đồng của factory. Cause giữ lại chi tiết rằng lỗi phân tích số bắt nguồn từ `NumberFormatException`.

Không nên bắt mọi `RuntimeException` rồi ném một lỗi mới với thông điệp chung. Hãy bắt đúng loại ngoại lệ mà bạn muốn chuyển đổi, để lỗi lập trình hoặc lỗi trạng thái không bị che khuất.

## 12. Kiểm thử thông báo lỗi ở mức hợp đồng

Không phải lúc nào cũng cần kiểm tra toàn bộ thông điệp. Hãy chọn mức kiểm thử theo điều API thực sự cam kết.

| Mức kiểm tra | Khi phù hợp | Ví dụ |
| --- | --- | --- |
| Chỉ kiểm tra loại exception | Câu chữ là chi tiết chẩn đoán, không phải hợp đồng công khai | Xác nhận constructor ném `IllegalArgumentException`. |
| Kiểm tra thông điệp chính xác | API cam kết giữ nguyên thông điệp ổn định | So sánh `getMessage()` với chuỗi đã công bố. |
| Kiểm tra mã lỗi hoặc trường có cấu trúc | Caller cần phân loại lỗi bằng chương trình | So sánh `ex.code()` với mã ổn định. |

Ví dụ JUnit Jupiter chỉ kiểm tra loại ngoại lệ:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ServerPortTest {

    @Test
    void rejectsPortOutsideAllowedRange() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new ServerPort(70000)
        );
    }
}
```

Nếu thông điệp là một phần hợp đồng ổn định, hãy kiểm tra rõ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class RetryPolicyTest {

    @Test
    void reportsTheInvalidComponentAndExpectedRange() {
        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> new RetryPolicy(0)
        );

        assertEquals(
                "maxAttempts must be between 1 and 10",
                ex.getMessage()
        );
    }
}
```

Nếu API dùng mã lỗi, kiểm tra mã thay vì phụ thuộc câu văn:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class MoneyTest {

    @Test
    void reportsStableErrorCodeForNegativeAmount() {
        InvalidRecordInputException ex = assertThrows(
                InvalidRecordInputException.class,
                () -> new Money(-1, "VND")
        );

        assertEquals("MONEY_AMOUNT_NEGATIVE", ex.code());
    }
}
```

Chỉ kiểm tra chính xác thông điệp khi dự án chủ động cam kết thông điệp đó ổn định. Nếu không, test loại exception và điều kiện phát sinh thường đủ để kiểm chứng hợp đồng mà không khóa implementation vào câu chữ.

## 13. Tránh kiểm thử thông báo mặc định của JDK

Các thông báo do JVM hoặc thư viện JDK tự tạo có thể không phải hợp đồng mà ứng dụng kiểm soát.

Ví dụ:

```java
Objects.requireNonNull(value);
```

Hoặc:

```java
Integer.parseInt("abc");
```

Không nên viết test phụ thuộc vào câu chữ mặc định của `NullPointerException` hoặc `NumberFormatException` do JDK tạo ra. Hãy kiểm tra loại exception, hoặc tự cung cấp thông điệp khi constructor cần một thông báo thuộc hợp đồng của mình:

```java
Objects.requireNonNull(value, "value must not be null");
```

Nếu cần kiểm tra message chính xác, chỉ kiểm tra message do code của bạn chủ động đặt và cam kết duy trì. Điều này giúp test ít phụ thuộc phiên bản JDK và implementation.

## 14. Thứ tự validation ảnh hưởng đến lỗi quan sát được

Nếu nhiều component cùng không hợp lệ, constructor thường phát hiện và ném ngoại lệ tại điều kiện đầu tiên. Vì vậy, thứ tự validation quyết định lỗi nào được quan sát trước.

Ví dụ:

```java
import java.util.Objects;

public record DateRange(String start, String end) {

    public DateRange {
        start = Objects.requireNonNull(
                start, "start must not be null"
        );
        end = Objects.requireNonNull(
                end, "end must not be null"
        );

        if (start.isBlank()) {
            throw new IllegalArgumentException(
                    "start must not be blank"
            );
        }

        if (end.isBlank()) {
            throw new IllegalArgumentException(
                    "end must not be blank"
            );
        }
    }
}
```

Nếu cả `start` và `end` đều null, constructor kiểm tra `start` trước nên thông báo đầu tiên là `"start must not be null"`. Đây là hành vi xác định từ thứ tự câu lệnh.

Không nên thay đổi thứ tự validation tùy tiện nếu ứng dụng hoặc test đã dựa vào lỗi đầu tiên. Nếu thứ tự không phải hợp đồng, test nên tạo từng trường hợp lỗi riêng để không khóa thứ tự nội bộ không cần thiết.

Với API cần trả về tất cả lỗi cùng lúc, mô hình ném một exception đầu tiên có thể không phù hợp. Khi đó, hãy cân nhắc API validation riêng trả danh sách lỗi; constructor vẫn chỉ tạo record sau khi dữ liệu hợp lệ.

## 15. Thông báo cho lỗi quan hệ giữa các component

Một record có thể có nhiều component riêng lẻ hợp lệ nhưng kết hợp lại không hợp lệ. Thông báo nên nêu cả hai component và quan hệ mong đợi.

Ví dụ:

```java
import java.time.LocalDate;
import java.util.Objects;

public record Booking(LocalDate checkIn, LocalDate checkOut) {

    public Booking {
        checkIn = Objects.requireNonNull(
                checkIn, "checkIn must not be null"
        );
        checkOut = Objects.requireNonNull(
                checkOut, "checkOut must not be null"
        );

        if (!checkOut.isAfter(checkIn)) {
            throw new IllegalArgumentException(
                    "checkOut must be after checkIn"
            );
        }
    }
}
```

Thông báo `"invalid booking"` quá chung. Thông báo `"checkOut must be after checkIn"` nêu được component liên quan và quy tắc nghiệp vụ.

Với dữ liệu ngày, câu chữ về quan hệ thường đã đủ. Không nhất thiết nối cả hai ngày vào message nếu điều đó không giúp chẩn đoán đáng kể.

## 16. Javadoc nên mô tả điều kiện, không cam kết quá mức

Javadoc của constructor công khai nên mô tả:

- Ý nghĩa của từng component.
- Điều kiện dữ liệu hợp lệ.
- Ngoại lệ phát sinh khi điều kiện không được đáp ứng.
- Chính sách null nếu component tham chiếu.
- Mã lỗi hoặc message ổn định nếu chúng thực sự là API công khai.

Ví dụ:

```java
public record RetryPolicy(int maxAttempts) {

    /**
     * @throws IllegalArgumentException if maxAttempts is outside the allowed range
     */
    public RetryPolicy {
        if (maxAttempts < 1 || maxAttempts > 10) {
            throw new IllegalArgumentException(
                    "maxAttempts must be between 1 and 10"
            );
        }
    }
}
```

Nếu thông điệp chỉ phục vụ chẩn đoán, không cần hứa rằng câu văn sẽ không bao giờ đổi. Nếu caller được phép dựa vào mã lỗi, hãy tài liệu hóa mã đó và chính sách tương thích.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng thông báo `"Invalid input"` cho mọi lỗi | Người gọi không biết component hoặc điều kiện nào sai. | Nêu tên component và điều kiện mong đợi. |
| Đưa tên file, số dòng hoặc tên helper vào message | Thông báo dễ lỗi thời sau refactor. | Mô tả hợp đồng dữ liệu. |
| Đưa password, token hoặc dữ liệu riêng tư vào message | Có thể làm lộ bí mật qua log và telemetry. | Chỉ nêu component và điều kiện. |
| Dùng message mặc định của JDK làm hợp đồng | Test có thể phụ thuộc phiên bản hoặc implementation. | Tự đặt message nếu cần ổn định. |
| Test luôn so sánh toàn bộ message dù API không cam kết | Test giòn và cản trở cải tiến câu chữ. | Kiểm tra loại exception; chỉ so message khi đó là hợp đồng. |
| Caller phân tích câu văn để phân loại lỗi | Thay đổi câu chữ có thể phá caller. | Dùng loại exception hoặc mã lỗi có cấu trúc. |
| Chuyển mọi RuntimeException thành lỗi đầu vào | Che khuất lỗi lập trình và mất cause. | Chỉ bắt ngoại lệ cụ thể, giữ cause. |
| Dùng một message cho null và sai miền | Khó xác định loại lỗi và cách sửa. | Tách thông báo theo điều kiện. |
| Thông báo quan hệ chỉ nói `"invalid range"` | Không biết hai component nào mâu thuẫn. | Nêu cả component và quan hệ. |
| Để thứ tự validation thay đổi tùy tiện | Lỗi đầu tiên quan sát được có thể thay đổi. | Giữ thứ tự có chủ đích hoặc không cam kết thứ tự trong API. |
| Hiển thị nguyên văn exception message cho người dùng | Câu kỹ thuật khó hiểu hoặc có thể lộ thông tin. | Ánh xạ mã lỗi sang thông báo giao diện. |

## 18. Bài tập tự luyện

### Bài 1: Cải thiện thông báo

Thông báo hiện tại:

```java
throw new IllegalArgumentException("Invalid data");
```

Record `ServerPort(int value)` chỉ chấp nhận cổng từ 1 đến 65535. Hãy viết lại thông báo.

**Đáp án:**

```java
throw new IllegalArgumentException(
        "value must be between 1 and 65535"
);
```

Thông báo chỉ rõ component và miền giá trị.

### Bài 2: Tránh lộ bí mật

Record `ApiCredential(String token)` yêu cầu token không null và không rỗng. Vì sao thông báo sau không phù hợp?

```java
throw new IllegalArgumentException("Invalid token: " + token);
```

**Đáp án:** Token có thể là bí mật và bị ghi vào log hoặc telemetry. Nên dùng `Objects.requireNonNull(token, "token must not be null")` và thông báo `"token must not be blank"` cho chuỗi rỗng, không đưa giá trị token vào message.

### Bài 3: Kiểm thử message hay loại exception?

API chỉ cam kết ném `IllegalArgumentException` khi `age` âm, không cam kết câu chữ cụ thể. Nên kiểm thử như thế nào?

**Đáp án:** Dùng `assertThrows(IllegalArgumentException.class, ...)`. Không so sánh toàn bộ `getMessage()` vì câu chữ không thuộc hợp đồng đã cam kết.

### Bài 4: Kiểm thử mã lỗi

Một exception chuyên biệt cung cấp `code()` và API cam kết mã `MONEY_AMOUNT_NEGATIVE` cho số tiền âm. Nên kiểm thử gì?

**Đáp án:** Bắt exception bằng `assertThrows` và so sánh `ex.code()` với `"MONEY_AMOUNT_NEGATIVE"`. Chỉ kiểm tra message nếu API cũng cam kết message ổn định.

### Bài 5: Thông báo cho quan hệ component

Record `Booking(LocalDate checkIn, LocalDate checkOut)` yêu cầu checkOut sau checkIn. Hãy viết message cho trường hợp vi phạm.

**Đáp án:**

```java
throw new IllegalArgumentException(
        "checkOut must be after checkIn"
);
```

Thông báo nêu hai component và quan hệ mong đợi.

## Ghi nhớ

Thông báo lỗi constructor tốt cần nêu component và điều kiện bị vi phạm, ổn định qua refactor và không làm lộ dữ liệu nhạy cảm. Hãy phân biệt thông tin chẩn đoán với thông báo giao diện; nếu caller cần phân loại lỗi, dùng loại exception hoặc mã lỗi có cấu trúc thay vì phân tích câu văn. Unit test chỉ nên kiểm tra message chính xác khi API cam kết giữ nó ổn định; với thông báo do JDK tự tạo, ưu tiên kiểm tra loại ngoại lệ và hành vi. Đặt validation chung trong canonical constructor để mọi đường khởi tạo cùng phát ra một hợp đồng lỗi nhất quán.

## Tài liệu tham khảo

- [Java API — IllegalArgumentException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/IllegalArgumentException.html).
- [Java API — NullPointerException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NullPointerException.html).
- [Java API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)).
- [JUnit Jupiter User Guide — Assertions](https://junit.org/junit5/docs/current/user-guide/#writing-tests-assertions).
- [Java Language Specification — Java SE 26, `8.10` Record Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10).
- [JEP 395 — Records (hoàn thiện trong Java 16)](https://openjdk.org/jeps/395).
