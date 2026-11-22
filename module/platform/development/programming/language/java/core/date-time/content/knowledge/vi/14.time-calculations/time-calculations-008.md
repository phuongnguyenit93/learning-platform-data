# Giới hạn giá trị và xử lý DateTimeException hoặc ArithmeticException trong Java

## 1. Vì sao phép tính thời gian có thể thất bại?

Các kiểu trong `java.time` như `LocalDate`, `LocalDateTime`, `Instant`, `Duration` và `Period` không thể biểu diễn mọi con số vô hạn. Mỗi kiểu có miền giá trị, đơn vị và quy tắc lịch riêng. Khi dữ liệu đầu vào không hợp lệ hoặc phép tính vượt miền hỗ trợ, API sẽ ném ngoại lệ để ngăn kết quả thời gian sai.

Hai nhóm ngoại lệ thường gặp:

- **`DateTimeException`**: lỗi liên quan đến dữ liệu thời gian không hợp lệ hoặc thời điểm/kết quả nằm ngoài miền mà kiểu thời gian hỗ trợ. Đây là lớp runtime trong hệ phân cấp `java.time`.
- **`ArithmeticException`**: lỗi phép toán số học, thường do tràn số hoặc khi chuyển đổi sang đơn vị/kết quả số không thể chứa trong kiểu đích.

Một thao tác có thể ném một trong hai tùy nguyên nhân, và một số API ghi rõ cả hai khả năng. Không nên bắt một loại ngoại lệ rồi giả định đã xử lý mọi lỗi liên quan đến thời gian.

Mục tiêu bài học:

1. Biết giới hạn của các kiểu thời gian Java và nơi đọc thông tin giới hạn.
2. Phân biệt lỗi đầu vào, kết quả ngày tháng không hợp lệ, tràn số và chuyển đơn vị quá lớn.
3. Bắt ngoại lệ tại đúng ranh giới và giữ nguyên nguyên nhân khi chuyển thành lỗi nghiệp vụ.
4. Tránh lỗi tràn trước khi kết quả được gán vào kiểu rộng hơn.
5. Kiểm thử các giá trị sát biên, dữ liệu âm và những thao tác tích lũy.

## 2. DateTimeException: giá trị thời gian không hợp lệ

`DateTimeException` là loại ngoại lệ runtime được dùng bởi API ngày giờ khi có lỗi về trường thời gian hoặc khi không thể thực hiện phép toán trong miền giá trị được hỗ trợ. Các tình huống điển hình:

- Ngày tháng không tồn tại theo lịch: `LocalDate.of(2023, 2, 29)`.
- Giờ nằm ngoài miền: `LocalTime.of(25, 0)`.
- Chuỗi không phân tích được theo formatter: `LocalDate.parse("2023-02-29")`, thường ném lớp con `DateTimeParseException`.
- Phép cộng tạo ra ngày vượt giới hạn của kiểu đích: ví dụ cộng một ngày vào `LocalDate.MAX`.
- Trường giá trị trong một kiểu thời gian nằm ngoài quy tắc mà chronology hoặc API đích cho phép.

Ví dụ ngày không hợp lệ:

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;

public class InvalidDateDemo {
    public static void main(String[] args) {
        try {
            LocalDate.of(2023, 2, 29);
            System.out.println("Date created");
        } catch (DateTimeException ex) {
            System.out.println("Invalid calendar date");
        }
    }
}
~~~

Biên dịch/chạy bằng Java 17+:

~~~bash
javac InvalidDateDemo.java
java InvalidDateDemo
~~~

Stdout:

~~~text
Invalid calendar date
~~~

Năm 2023 không nhuận, vì vậy ngày 29 tháng 2 không tồn tại trong lịch ISO. `LocalDate.of(...)` ném ngoại lệ ngay ở bước tạo; nó không tự chuyển sang ngày 1 tháng 3. Nếu nghiệp vụ muốn điều chỉnh đầu vào không hợp lệ, phải thể hiện chính sách ấy rõ ràng thay vì mặc định nuốt lỗi.

### 2.1. DateTimeParseException là lớp con

`DateTimeParseException` kế thừa `DateTimeException`. Khi parsing văn bản, có thể bắt lớp cụ thể để cung cấp phản hồi tốt hơn:

~~~java
try {
    LocalDate parsed = LocalDate.parse(input);
} catch (DateTimeParseException ex) {
    // input không theo định dạng/ngày mà formatter chấp nhận
}
~~~

Đây là đoạn minh họa, cần có biến `input` và import `java.time.LocalDate`, `java.time.format.DateTimeParseException` trong lớp chứa nó. Nếu chỉ bắt `DateTimeException`, `DateTimeParseException` vẫn được bắt vì quan hệ kế thừa. Bắt ngoại lệ tổng quát phù hợp khi cùng một xử lý áp dụng cho nhiều lỗi thời gian; bắt loại cụ thể phù hợp khi cần phân biệt lỗi parse với lỗi khác.

Đừng dùng `catch (Exception)` cho tất cả đường đi chỉ để tránh chương trình báo lỗi. Nó che cả lỗi không liên quan đến ngày giờ và làm khó phân biệt lỗi dữ liệu với lỗi lập trình.

## 3. ArithmeticException: tràn số khi tính thời gian

`ArithmeticException` thường xuất hiện khi phép toán thời gian dựa trên số nguyên bị tràn, hoặc khi API chuyển sang một đơn vị có miền biểu diễn hẹp hơn. Ví dụ:

- `Duration.toNanos()` nếu tổng nano giây không vừa `long`.
- `Instant.toEpochMilli()` nếu số mili giây tính từ epoch vượt `long`.
- `Period.multipliedBy(...)` hoặc các phép toán thành phần khi kết quả số nguyên không còn vừa kiểu lưu.
- Một phép nhân tự viết như `seconds * 1_000_000_000L` bị tràn trước khi gán.

Ví dụ chuyển đổi Duration lớn:

~~~java
import java.time.Duration;

public class DurationOverflowDemo {
    public static void main(String[] args) {
        Duration longDuration = Duration.ofDays(200_000);

        try {
            System.out.println(longDuration.toNanos());
        } catch (ArithmeticException ex) {
            System.out.println("Duration does not fit in long nanos");
        }
    }
}
~~~

Lệnh chạy:

~~~bash
javac DurationOverflowDemo.java
java DurationOverflowDemo
~~~

Stdout:

~~~text
Duration does not fit in long nanos
~~~

`Duration` biểu diễn thời lượng bằng giây và nano giây, nên có thể chứa khoảng thời gian dài hơn giới hạn của một tổng nano giây `long`. `toNanos()` phải trả về một số nguyên đơn và vì thế có thể báo overflow. Cách giải quyết đúng có thể là giữ `Duration`, giữ cặp giây/nano hoặc đổi sang đơn vị phù hợp; ép kiểu số học không thể khôi phục giá trị đã tràn.

## 4. Giới hạn của kiểu không giống nhau

Một kiểu có thể hỗ trợ phạm vi thời gian rộng, nhưng một phép chuyển đổi ra một đơn vị duy nhất lại có miền nhỏ hơn.

| Kiểu/phương thức | Ý nghĩa giới hạn | Điều cần nhớ |
|---|---|---|
| `LocalDate.MIN` / `MAX` | Giới hạn ngày lịch ISO mà kiểu hỗ trợ | Cộng/trừ sát biên có thể ném `DateTimeException` |
| `LocalTime` | Giờ trong một ngày, đến nano giây | Không biểu diễn ngày kế tiếp khi cộng qua nửa đêm |
| `LocalDateTime.MIN` / `MAX` | Miền ngày và giờ địa phương | Cộng giờ/ngày vượt biên có thể thất bại |
| `Instant.MIN` / `MAX` | Miền thời điểm được kiểu Instant hỗ trợ | Rộng hơn miền của epoch milliseconds `long` |
| `Duration` | Giây và nano giây | `toNanos()` có thể overflow dù Duration hợp lệ |
| `Period` | Thành phần năm, tháng, ngày | Phép nhân/cộng thành phần có thể vượt miền số nguyên |
| `Instant.toEpochMilli()` | Đổi thời điểm sang mili giây từ epoch | Có thể `ArithmeticException` ở các thời điểm rất xa |
| `DateTimeFormatter` | Parsing/formatting theo mẫu và resolver | Dữ liệu không hợp lệ thường ném `DateTimeParseException` |

Giới hạn chính xác và ngoại lệ cần xem trong Javadoc của phương thức cụ thể, thay vì giả định mọi kiểu có cùng miền hoặc mọi phép toán luôn ném một loại ngoại lệ.

### 4.1. Cộng sát biên

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;

public class DateBoundaryDemo {
    public static void main(String[] args) {
        System.out.println("Max date: " + LocalDate.MAX);

        try {
            LocalDate.MAX.plusDays(1);
        } catch (DateTimeException ex) {
            System.out.println("Beyond LocalDate range");
        }
    }
}
~~~

Stdout:

~~~text
Max date: +999999999-12-31
Beyond LocalDate range
~~~

`LocalDate.MAX` là ngày cuối cùng trong miền `LocalDate`. `plusDays(1)` không được phép tạo một ngày ngoài miền, nên ném ngoại lệ. Không nên chuyển kết quả về chuỗi trước khi tính rồi cố xử lý bằng ký tự; hãy để API thời gian kiểm tra miền, và xử lý ngoại lệ tại lớp có thể quyết định báo lỗi, từ chối yêu cầu hay dùng một kiểu khác.

## 5. Phân biệt lỗi dữ liệu với overflow

Cùng một thao tác “cộng thời gian” có thể thất bại vì nguyên nhân khác nhau:

| Tình huống | Nguyên nhân | Cách xử lý phù hợp |
|---|---|---|
| `LocalDate.of(2023, 2, 29)` | Ngày không hợp lệ theo lịch | Báo lỗi validation cho đầu vào |
| `LocalDate.MAX.plusDays(1)` | Kết quả vượt miền ngày | Từ chối phép tính hoặc xác định giới hạn nghiệp vụ |
| `LocalDate.parse("tomorrow")` | Chuỗi không phải ngày ISO | Yêu cầu định dạng ngày hợp lệ |
| `Duration.ofDays(200_000).toNanos()` | Tổng nano không vừa `long` | Giữ Duration hoặc chọn đơn vị khác |
| `Instant.MAX.toEpochMilli()` | Epoch millis vượt miền `long` | Kiểm tra miền thời gian trước khi xuất ra millis |
| `seconds * 1_000_000_000L` tự viết | Phép nhân tràn trước khi lưu | Kiểm tra trước khi nhân hoặc dùng biểu diễn khác |

Không nên phản hồi “ngày không hợp lệ” cho mọi `ArithmeticException`: lỗi có thể nói rằng giá trị đã vượt miền số khi đổi đơn vị, chứ ngày gốc không sai. Ngược lại, không nên quy lỗi validation đơn giản cho overflow.

Nếu API công khai cần một kiểu lỗi thống nhất, hãy chuyển đổi ở ranh giới hệ thống nhưng giữ loại lỗi và nguyên nhân ban đầu trong log hoặc trường `cause` của exception. Đừng xóa thông tin gốc bằng cách ném một lỗi chung không có nguyên nhân.

## 6. Vì sao gán sang long sau phép nhân vẫn có thể sai?

Java tính biểu thức theo kiểu của các toán hạng. Vì vậy:

~~~java
long nanos = seconds * 1_000_000_000;
~~~

nếu `seconds` là `int` thì phép nhân xảy ra bằng số nguyên `int` trước khi gán sang `long`. Nếu tràn, giá trị đã sai từ trước; biến đích rộng hơn không sửa được nó. Thêm hậu tố `L` thay đổi kiểu phép nhân:

~~~java
long nanos = seconds * 1_000_000_000L;
~~~

Tuy nhiên, cách này vẫn có thể tràn `long` nếu `seconds` lớn. Chọn kiểu rộng hơn không đồng nghĩa bỏ qua kiểm tra giới hạn.

Các quy tắc an toàn:

- Kiểm tra miền trước khi nhân/chia khi chuyển đổi đơn vị.
- Dùng `Math.multiplyExact(a, b)` hoặc `Math.addExact(a, b)` khi tự viết số học nguyên cần phát hiện overflow.
- Giữ `Instant`/`Duration` ở dạng gốc nếu không cần quy về một số nguyên tổng.
- Tránh tổng nano tuyệt đối trong `long` cho những khoảng thời gian rất dài.
- Khi API JDK đã có phương thức chuyển đổi, ưu tiên dùng nó hơn tự xây lại công thức không kiểm tra overflow.

Ví dụ phát hiện tràn tường minh:

~~~java
public class ExactArithmeticDemo {
    public static void main(String[] args) {
        long seconds = Long.MAX_VALUE;

        try {
            long millis = Math.multiplyExact(seconds, 1_000L);
            System.out.println(millis);
        } catch (ArithmeticException ex) {
            System.out.println("Milliseconds overflow long");
        }
    }
}
~~~

Stdout:

~~~text
Milliseconds overflow long
~~~

Đây là phép tính số học minh họa. Nó không thay thế chính sách miền thời gian cụ thể, nhưng cho thấy cách yêu cầu Java **báo overflow** thay vì để kết quả quay vòng im lặng.

## 7. Hạn chế của chuyển đổi đơn vị

### 7.1. Instant sang epoch milliseconds

`Instant` hỗ trợ miền thời gian rộng, còn `toEpochMilli()` trả `long` mili giây từ epoch. Thời điểm quá xa có thể không vừa `long`:

~~~java
import java.time.Instant;

public class InstantMillisBoundaryDemo {
    public static void main(String[] args) {
        try {
            System.out.println(Instant.MAX.toEpochMilli());
        } catch (ArithmeticException ex) {
            System.out.println("Instant is outside epoch-millis range");
        }
    }
}
~~~

Stdout:

~~~text
Instant is outside epoch-millis range
~~~

Nếu hệ thống chỉ nhận epoch milliseconds, validation cần bao gồm cả **miền ngày hỗ trợ** và **độ chính xác**. Một Instant có thể hợp lệ nhưng không thể đổi ra `long` millis; một Instant khác đổi được nhưng mất phần nano dưới mili.

### 7.2. Duration sang nano giây

`Duration.toNanos()` trả `long` tổng nano giây. Với thời lượng dài, số nano có thể vượt giới hạn `long`; việc Duration được tạo thành công không bảo đảm phép chuyển tổng nano thành công.

Nếu cần khoảng thời gian dài:

- Giữ đối tượng `Duration`, và dùng `getSeconds()` cùng `getNano()` nếu cần hai thành phần.
- Nếu cần số nano tổng và miền dữ liệu rộng hơn, cân nhắc `BigInteger` với quy định đơn vị rõ ràng.
- Chỉ dùng `toNanos()` khi giới hạn nghiệp vụ bảo đảm kết quả nằm trong miền `long`.

Đừng xử lý bằng cách bắt `ArithmeticException` rồi trả `Long.MAX_VALUE` như thể đó là giá trị thật; điều đó biến overflow thành dữ liệu sai. Chỉ saturate (chặn ở giới hạn) nếu quy tắc nghiệp vụ chủ động yêu cầu, và hãy đặt tên/định nghĩa hành vi đó rõ ràng.

### 7.3. Period và thành phần năm/tháng/ngày

`Period` lưu ba trường nguyên, không phải tổng số giây. Một phép nhân period có thể khiến trường vượt giới hạn `int`:

~~~java
import java.time.Period;

public class PeriodOverflowDemo {
    public static void main(String[] args) {
        try {
            Period huge = Period.ofMonths(Integer.MAX_VALUE);
            System.out.println(huge.multipliedBy(2));
        } catch (ArithmeticException ex) {
            System.out.println("Period component overflow");
        }
    }
}
~~~

Stdout:

~~~text
Period component overflow
~~~

Không được “sửa” overflow bằng cách coi tháng là 30 ngày. Tháng không có độ dài cố định; nếu bài toán là số ngày tuyệt đối, dùng ngày bắt đầu/kết thúc và API như `ChronoUnit.DAYS.between`. Nếu bài toán là thay đổi lịch, giữ `Period` hoặc áp dụng lên `LocalDate` có kiểm tra miền.

## 8. Bắt đúng ngoại lệ ở ranh giới phù hợp

Một mẫu tốt là chỉ bao quanh thao tác có thể thất bại, chuyển nó thành lỗi theo ngữ nghĩa của lớp đang xử lý, và giữ nguyên nguyên nhân:

~~~java
import java.time.DateTimeException;
import java.time.LocalDate;

public class DeadlineService {
    public LocalDate shiftDate(LocalDate date, long days) {
        try {
            return date.plusDays(days);
        } catch (DateTimeException | ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Requested date is outside the supported range", ex);
        }
    }
}
~~~

Đây là lớp minh họa cho tình huống dịch chuyển ngày do đầu vào người dùng; trong dự án thật cần quyết định kiểu lỗi công khai phù hợp. Hai loại ngoại lệ được bắt riêng trong multi-catch, sau đó được giữ làm **cause** khi ném lỗi nghiệp vụ. Nếu hợp đồng muốn phân biệt lỗi ngày với overflow số học, hãy tạo hai nhánh xử lý thay vì gộp chúng.

Không bắt `Throwable` hoặc `Error` để xử lý giới hạn thời gian. Lỗi nghiêm trọng của JVM không phải dữ liệu đầu vào bình thường. Cũng không nên bắt `RuntimeException` quá rộng ở tầng thấp vì có thể che lỗi lập trình.

## 9. Validation trước, nhưng không thay thế kiểm tra ở thao tác cuối

Kiểm tra đầu vào có ích khi muốn thông báo sớm:

~~~java
static LocalDate parseDate(String text) {
    try {
        return LocalDate.parse(text);
    } catch (DateTimeParseException ex) {
        throw new IllegalArgumentException(
                "Expected an ISO date such as 2024-02-29", ex);
    }
}
~~~

Đoạn này dành cho lớp có import `java.time.LocalDate` và `java.time.format.DateTimeParseException`. Nó phân biệt chuỗi không parse được với việc tính toán sau đó vượt miền.

Dù đã validate trước, vẫn phải giữ xử lý ngoại lệ cho phép tính cuối cùng. Ví dụ, đầu vào `LocalDate.MAX` hợp lệ, nhưng `plusDays(1)` không hợp lệ. Validation trên trường ban đầu không thể đảm bảo mọi phép tính tiếp theo sẽ nằm trong miền.

Nếu đầu vào là các thành phần riêng rẽ, có thể validate miền hợp lệ trước khi tạo đối tượng; tuy nhiên, để đảm bảo đúng quy tắc lịch, dùng chính factory `LocalDate.of` hoặc `LocalTime.of` thay cho việc chỉ kiểm tra mỗi trường riêng biệt. Ngày 29/02 là ví dụ: tháng và ngày riêng lẻ nằm trong khoảng phổ biến nhưng tổ hợp có thể không hợp lệ cho năm đó.

## 10. Chương trình tổng hợp chạy độc lập

Lưu thành **`DateTimeExceptionsDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.Period;
import java.time.format.DateTimeParseException;

public class DateTimeExceptionsDemo {
    public static void main(String[] args) {
        try {
            LocalDate.of(2023, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("Invalid date rejected");
        }

        try {
            LocalDate.parse("not-a-date");
        } catch (DateTimeParseException ex) {
            System.out.println("Invalid text rejected");
        }

        try {
            LocalDate.MAX.plusDays(1);
        } catch (DateTimeException ex) {
            System.out.println("LocalDate boundary rejected");
        }

        try {
            Duration.ofDays(200_000).toNanos();
        } catch (ArithmeticException ex) {
            System.out.println("Duration-to-nanos overflow");
        }

        try {
            Instant.MAX.toEpochMilli();
        } catch (ArithmeticException ex) {
            System.out.println("Instant-to-millis overflow");
        }

        try {
            Period.ofMonths(Integer.MAX_VALUE).multipliedBy(2);
        } catch (ArithmeticException ex) {
            System.out.println("Period component overflow");
        }
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac DateTimeExceptionsDemo.java
java DateTimeExceptionsDemo
~~~

Stdout:

~~~text
Invalid date rejected
Invalid text rejected
LocalDate boundary rejected
Duration-to-nanos overflow
Instant-to-millis overflow
Period component overflow
~~~

Chương trình thể hiện ba loại tình huống: trường lịch không hợp lệ, chuỗi parse sai, và phép chuyển/cộng vượt miền biểu diễn. Các trường hợp được bắt theo loại ngoại lệ của từng API. Nếu đang xử lý ở production, nên ghi log có cấu trúc (operation, input đã được làm sạch, kiểu exception), tránh ghi dữ liệu nhạy cảm hoặc phụ thuộc thông điệp exception không ổn định qua phiên bản.

## 11. Chiến lược kiểm thử sát biên

Kiểm thử “một giá trị bình thường” không đủ để xác nhận xử lý giới hạn. Nên có kiểm thử cho:

| Nhóm | Ví dụ kiểm thử | Kỳ vọng |
|---|---|---|
| Giá trị hợp lệ bình thường | `LocalDate.of(2024, 2, 29)` | Thành công |
| Ngày lịch không hợp lệ | `LocalDate.of(2023, 2, 29)` | `DateTimeException` |
| Parse sai | `LocalDate.parse("nope")` | `DateTimeParseException` |
| Giá trị cuối miền | `LocalDate.MAX` | Có thể tạo/đọc |
| Cộng vượt biên | `LocalDate.MAX.plusDays(1)` | Ngoại lệ phù hợp API |
| Chuyển đơn vị tràn | `Duration.ofDays(200_000).toNanos()` | `ArithmeticException` |
| Chuyển thời điểm quá xa | `Instant.MAX.toEpochMilli()` | `ArithmeticException` |
| Phép nhân period tràn | `Period.ofMonths(Integer.MAX_VALUE).multipliedBy(2)` | `ArithmeticException` |
| Giảm độ phân giải | `Instant` có phần nano lẻ → epochMillis | Kết quả mất phần dưới ms nếu không overflow |
| Dữ liệu âm | Thời điểm trước epoch | Xác minh dấu và quy tắc làm tròn |

Trong unit test, kiểm tra **loại ngoại lệ** và kết quả mong muốn, không nhất thiết so khớp toàn bộ thông điệp exception vì câu chữ có thể thay đổi. Với API đầu vào, kiểm tra hợp đồng lỗi công khai, ví dụ HTTP 400 cho dữ liệu không hợp lệ nếu đó là quy ước của ứng dụng.

## 12. Những lỗi thường gặp và cách tránh

1. **Bắt mỗi DateTimeException:** không xử lý được một số overflow khi đổi thành tổng số mili/nano.
2. **Bắt mỗi ArithmeticException:** không xử lý ngày/tháng sai hoặc chuỗi parse không hợp lệ.
3. **Bắt Exception quá rộng:** che lỗi lập trình, IO hoặc lỗi không liên quan.
4. **Gán sang long sau khi phép nhân đã tràn int:** dùng toán hạng long ngay từ đầu, nhưng vẫn kiểm tra overflow.
5. **Dùng giá trị lớn nhất làm fallback:** biến lỗi thành thời gian giả; chỉ chặn giới hạn khi nghiệp vụ định nghĩa rõ.
6. **Giả định đối tượng hợp lệ thì mọi phép tính trên nó hợp lệ:** cộng thêm một ngày ở sát biên vẫn có thể thất bại.
7. **Giả định mọi Instant chuyển được sang epochMillis:** miền Instant rộng hơn số long milli.
8. **Gọi Duration.toNanos() với thời lượng bất kỳ:** tổng nano có thể vượt long; giữ Duration nếu có thể.
9. **Xem Period như một số ngày:** không đổi tháng/năm thành 30/365 ngày để né vấn đề miền.
10. **Nuốt exception rồi tiếp tục:** dữ liệu kết quả không rõ nguồn gốc và che nguyên nhân thực.
11. **Chỉ test ngày bình thường:** hãy thử ngày không nhuận, giá trị MIN/MAX, trước epoch và phép tính tích lũy.
12. **Dựa vào thông điệp exception làm logic:** ưu tiên lớp ngoại lệ và điều kiện đầu vào; thông điệp phục vụ chẩn đoán.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Khác biệt chính giữa `DateTimeException` và `ArithmeticException` là gì?

**Đáp án:** `DateTimeException` liên quan đến giá trị/thao tác ngày giờ không hợp lệ hoặc vượt miền kiểu thời gian. `ArithmeticException` thường báo phép toán số hoặc chuyển đổi đơn vị bị tràn. Hãy xem API cụ thể vì một thao tác có thể nêu nhiều loại ngoại lệ.

**Câu 2.** Tại sao `LocalDate.of(2023, 2, 29)` khác `LocalDate.MAX.plusDays(1)`?

**Đáp án:** Trường hợp đầu tạo một tổ hợp ngày không hợp lệ theo lịch; trường hợp sau bắt đầu từ ngày hợp lệ nhưng kết quả vượt giới hạn biểu diễn của LocalDate.

**Câu 3.** Vì sao `Duration.ofDays(200_000)` có thể hợp lệ nhưng `toNanos()` thất bại?

**Đáp án:** Duration lưu giây và nano tách rời. Tổng nano cần một `long` duy nhất có thể vượt miền của kiểu đó.

**Câu 4.** `Instant.MAX` có thể tồn tại nhưng `Instant.MAX.toEpochMilli()` thất bại tại sao?

**Đáp án:** `Instant` có miền thời gian rộng hơn miền biểu diễn mili giây bằng `long`.

**Câu 5.** Vì sao phép nhân gán vào `long` vẫn có thể sai?

**Đáp án:** Nếu các toán hạng là `int`, phép nhân diễn ra ở kiểu int và có thể tràn trước khi kết quả được gán sang long. Dùng toán hạng long hoặc `Math.multiplyExact`, đồng thời kiểm tra tràn long.

**Câu 6.** Có nên bắt `DateTimeException` rồi trả “hôm nay” làm giá trị mặc định?

**Đáp án:** Không, trừ khi nghiệp vụ công khai quy định như vậy. Tự thay bằng ngày hiện tại có thể che đầu vào sai và gây dữ liệu sai âm thầm.

**Câu 7.** Kiểm tra trước trường ngày có loại bỏ nhu cầu xử lý ngoại lệ ở phép cộng không?

**Đáp án:** Không. Giá trị đầu vào hợp lệ vẫn có thể cho kết quả vượt biên khi tính.

**Câu 8.** Có nên trả `Long.MAX_VALUE` khi `Duration.toNanos()` overflow?

**Đáp án:** Không nên tự làm vậy nếu nghiệp vụ chưa định nghĩa chính sách chặn ở giới hạn; giá trị đó không phải duration chính xác và có thể gây lỗi về sau.

## 14. Quy tắc thực hành

- Dùng factory ngày giờ để kiểm tra tổ hợp ngày/giờ ngay ở ranh giới nhập liệu.
- Bắt `DateTimeParseException` cho dữ liệu chuỗi, `DateTimeException` cho lỗi lịch/miền thời gian, và `ArithmeticException` cho overflow/chuyển đơn vị không vừa kiểu.
- Đọc Javadoc của phương thức cụ thể; không khẳng định mọi lỗi thời gian ném cùng một loại.
- Giữ `Instant` và `Duration` ở dạng gốc nếu chưa cần quy về epochMillis hoặc tổng nanos.
- Dùng `Math.addExact`/`multiplyExact` cho phép toán nguyên viết thủ công và xác định chính sách rõ nếu overflow xảy ra.
- Kiểm thử MIN/MAX, ngày nhuận, đầu vào âm, dữ liệu parse sai và phép chuyển đơn vị có thể vượt miền.
- Khi chuyển exception sang lỗi nghiệp vụ, giữ cause và thông tin chẩn đoán hữu ích; không nuốt ngoại lệ hoặc tạo giá trị thời gian giả.

Tóm lại, xử lý thời gian an toàn không chỉ là bắt ngoại lệ. Cần hiểu **giới hạn kiểu**, **quy tắc lịch**, **kiểu số trung gian** và **ngữ nghĩa chuyển đổi**. Đó là cách phân biệt dữ liệu thực sự không hợp lệ với một phép tính hợp lệ nhưng không thể biểu diễn bằng kiểu đích.
