# isSupported() trước khi dùng trường hoặc đơn vị

## 1. Vì sao cần kiểm tra khả năng hỗ trợ?

Một đối tượng ngày giờ chỉ cung cấp những thông tin phù hợp với ý nghĩa của nó. `LocalDate` có ngày lịch nhưng không có giờ; `Instant` có vị trí trên trục thời gian nhưng không tự mang một giờ địa phương. Việc cùng thuộc họ `java.time` không làm chúng hỗ trợ cùng một bộ trường hoặc đơn vị.

`isSupported()` giúp mã tổng quát trả lời **“đối tượng này có khả năng thực hiện loại thao tác đó không?”** trước khi đọc trường hoặc cộng/trừ theo đơn vị. Nó đặc biệt hữu ích khi đầu vào có nhiều kiểu hoặc trường/đơn vị được chọn lúc chạy.

Ví dụ: một tiện ích hiển thị thông tin chỉ đọc `HOUR_OF_DAY` nếu đầu vào có trường đó; một tiện ích cộng lịch chỉ nhận `MONTHS` nếu kiểu đầu vào hỗ trợ cộng tháng. Nhờ vậy, trường hợp không có khả năng hỗ trợ trở thành một nhánh xử lý rõ ràng.

## 2. Hai overload trả lời hai câu hỏi khác nhau

| Chữ ký | Khai báo ở đâu? | Câu hỏi |
| --- | --- | --- |
| `isSupported(TemporalField field)` | `TemporalAccessor` | Có hỗ trợ trường để đọc không? |
| `isSupported(TemporalUnit unit)` | `Temporal` | Có hỗ trợ đơn vị để cộng/trừ không? |

`ChronoField.HOUR_OF_DAY` là **trường**: giờ hiện tại trong ngày là bao nhiêu? `ChronoUnit.HOURS` là **đơn vị**: cộng/trừ bao nhiêu giờ? Khi viết kiểm tra, phải đưa đúng đối tượng mô tả thao tác sắp thực hiện.

```java
LocalDate date = LocalDate.of(2024, 6, 15);
boolean canReadDay = date.isSupported(ChronoField.DAY_OF_MONTH);
boolean canAddDays = date.isSupported(ChronoUnit.DAYS);
```

Đoạn trên là mã minh họa trong một phương thức, cần import các kiểu được dùng. Không có một overload không tham số mang nghĩa “kiểu này hỗ trợ mọi phép toán ngày giờ”. [TemporalAccessor.isSupported](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAccessor.html#isSupported(java.time.temporal.TemporalField))

Nếu biến được khai báo là `TemporalAccessor`, chỉ overload nhận trường xuất hiện trên kiểu đó. Muốn kiểm tra đơn vị và gọi `plus`, hợp đồng đầu vào phải là `Temporal`. Không ép kiểu mù quáng chỉ để gọi phương thức, vì một số đối tượng như `MonthDay` không phải `Temporal`.

## 3. Khả năng đọc trường không suy ra khả năng cộng đơn vị

| Đối tượng | Đọc `HOUR_OF_DAY` | Cộng `HOURS` | Giải thích |
| --- | --- | --- | --- |
| `LocalDate` | Không | Không | Chỉ mô tả ngày |
| `LocalTime` | Có | Có | Mô tả giờ trong ngày |
| `Instant` | Không | Có | Có thể tiến một giờ trên trục thời gian mà chưa chọn giờ địa phương |

Với `Instant`, chọn `HOUR_OF_DAY` cần có quy tắc chuyển sang một múi giờ, chẳng hạn `instant.atZone(zone)`. `isSupported` không tự chọn múi giờ của hệ điều hành và không bổ sung dữ liệu còn thiếu. [Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)

Ở chiều ngược lại, một kiểu có thông tin tháng cũng chưa chắc hỗ trợ phép cộng tháng tổng quát. Hãy kiểm tra đúng overload thay vì suy đoán từ tên kiểu hoặc từ một trường khác đã đọc thành công.

## 4. Kiểu xử lý khi không hỗ trợ

Có hai chính sách thông dụng; chọn theo hợp đồng nghiệp vụ:

- **Thông tin tùy chọn:** trả kết quả thể hiện sự vắng mặt, như `OptionalLong.empty()`, hoặc không hiển thị trường.
- **Khả năng bắt buộc:** từ chối đầu vào với lỗi rõ ràng trước khi thực hiện phép toán.

Không trả `0` thay cho trường không được hỗ trợ: giờ 0, giây 0 hoặc ngày epoch 0 đều có thể là dữ liệu thật. Không tự chuyển “không hỗ trợ giờ” thành “mặc định nửa đêm” nếu nghiệp vụ chưa quy định.

Việc kiểm tra `isSupported(unit)` chỉ loại trừ nguyên nhân **đơn vị không được hỗ trợ**. Nó không thay thế kiểm tra giới hạn kết quả hoặc điều kiện nghiệp vụ. [Temporal.isSupported](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/Temporal.html#isSupported(java.time.temporal.TemporalUnit))

## 5. Chương trình minh chứng và xử lý trường hợp thiếu khả năng

Lưu thành `SupportedDemo.java`. Ví dụ dùng dữ liệu cố định, không phụ thuộc ngày giờ máy chạy.

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.Temporal;
import java.time.temporal.TemporalAccessor;
import java.time.temporal.TemporalField;
import java.time.temporal.TemporalUnit;
import java.time.temporal.UnsupportedTemporalTypeException;
import java.util.Objects;
import java.util.OptionalLong;

public class SupportedDemo {
    static OptionalLong readIfSupported(
            TemporalAccessor value, TemporalField field) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(field, "field");
        if (!value.isSupported(field)) {
            return OptionalLong.empty();
        }
        return OptionalLong.of(value.getLong(field));
    }

    static Temporal addRequired(
            Temporal value, long amount, TemporalUnit unit) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(unit, "unit");
        if (!value.isSupported(unit)) {
            throw new IllegalArgumentException("Unsupported unit: " + unit);
        }
        return value.plus(amount, unit);
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 6, 15);
        LocalTime time = LocalTime.of(14, 30);
        Instant moment = Instant.parse("2024-06-15T00:00:00Z");

        System.out.println("dateHour="
                + date.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("timeHour="
                + time.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("instantHour="
                + moment.isSupported(ChronoField.HOUR_OF_DAY));
        System.out.println("instantHours="
                + moment.isSupported(ChronoUnit.HOURS));

        System.out.println("dateRead="
                + readIfSupported(date, ChronoField.HOUR_OF_DAY));
        System.out.println("timeRead="
                + readIfSupported(time, ChronoField.HOUR_OF_DAY));
        System.out.println("instantPlus="
                + addRequired(moment, 2, ChronoUnit.HOURS));
        try {
            addRequired(date, 1, ChronoUnit.HOURS);
        } catch (IllegalArgumentException ex) {
            System.out.println("dateRejectsHours");
        }

        System.out.println("epochDaySupported="
                + date.isSupported(ChronoField.EPOCH_DAY));
        try {
            date.get(ChronoField.EPOCH_DAY);
        } catch (UnsupportedTemporalTypeException ex) {
            System.out.println("epochDayNeedsGetLong");
        }
        System.out.println("epochDay=" + date.getLong(ChronoField.EPOCH_DAY));

        System.out.println("monthSupported="
                + date.isSupported(ChronoField.MONTH_OF_YEAR));
        try {
            date.with(ChronoField.MONTH_OF_YEAR, 13);
        } catch (DateTimeException ex) {
            System.out.println("month13Invalid");
        }

        System.out.println("maxSupportsDays="
                + LocalDate.MAX.isSupported(ChronoUnit.DAYS));
        try {
            LocalDate.MAX.plus(1, ChronoUnit.DAYS);
        } catch (DateTimeException ex) {
            System.out.println("beyondMaxDate");
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 SupportedDemo.java
java SupportedDemo
```

Stdout chính xác:

```text
dateHour=false
timeHour=true
instantHour=false
instantHours=true
dateRead=OptionalLong.empty
timeRead=OptionalLong[14]
instantPlus=2024-06-15T02:00:00Z
dateRejectsHours
epochDaySupported=true
epochDayNeedsGetLong
epochDay=19889
monthSupported=true
month13Invalid
maxSupportsDays=true
beyondMaxDate
```

`readIfSupported` giữ riêng trường hợp không có dữ liệu. Nó dùng `getLong`, tránh giới hạn `int` khi đọc một trường có miền lớn. `addRequired` coi khả năng cộng đơn vị là điều kiện đầu vào bắt buộc, nhưng vẫn để phép cộng báo lỗi nếu kết quả vượt giới hạn.

Các khối `try/catch` cuối chương trình dùng để chứng minh giới hạn của phép kiểm tra. Chúng không phải lời khuyên bắt mọi lỗi trong mọi phép cộng ngày.

## 6. true không đồng nghĩa mọi lời gọi sau đó đều thành công

### 6.1. Hỗ trợ trường khác với đọc được bằng int

`LocalDate` hỗ trợ `EPOCH_DAY`, nhưng miền của trường vượt `int`. Vì vậy `get(EPOCH_DAY)` thất bại dù số của một ngày cụ thể đang nhỏ; dùng `getLong(EPOCH_DAY)`. Kiểm tra hỗ trợ không phải kiểm tra kiểu số đầu ra. [LocalDate: đọc trường](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#get(java.time.temporal.TemporalField))

### 6.2. Hỗ trợ trường khác với giá trị mới hợp lệ

`MONTH_OF_YEAR` được hỗ trợ không làm tháng 13 hợp lệ. Tương tự, ngày 31 không tồn tại trong mọi tháng. Khi đặt trường, cần hiểu miền của trường và quy tắc điều chỉnh cụ thể. Nếu nhận đầu vào người dùng, kiểm tra dữ liệu và phản hồi theo hợp đồng nghiệp vụ.

### 6.3. Hỗ trợ đơn vị khác với kết quả nằm trong miền

`LocalDate.MAX` vẫn hỗ trợ `DAYS`; điều đó mô tả khả năng tính theo ngày của kiểu dữ liệu. Cộng thêm một ngày vượt miền `LocalDate`, nên ném lỗi. Các phép tính lớn khác còn có thể gặp `ArithmeticException` do tràn số.

### 6.4. Đơn vị được hỗ trợ chưa xác định ý nghĩa nghiệp vụ

Một `ZonedDateTime` có thể hỗ trợ cả `DAYS` và `HOURS`, nhưng cộng một ngày lịch khác với cộng 24 giờ khi qua thời điểm đổi giờ mùa hè. `isSupported` không trả lời “đơn vị nào phù hợp với yêu cầu đặt lịch?”. Cần xác định trước ý nghĩa lịch địa phương hay thời lượng thực trôi.

### 6.5. Một đầu mốc hỗ trợ chưa bảo đảm phép tính hai mốc thành công

Đối với `until`/`between`, còn phải bảo đảm mốc còn lại chuyển đổi được sang loại dữ liệu cần thiết. Không chỉ kiểm tra đơn vị trên mốc đầu rồi kết luận một cặp tùy ý như `LocalDate` và `LocalTime` có thể tính khoảng cách.

## 7. null, kiểu khai báo và các kiểm tra không cần thiết

Với các overload theo hợp đồng, đối số trường/đơn vị `null` cho kết quả `false`. Tuy nhiên `date.isSupported(null)` không biên dịch khi biến có cả hai overload: trình biên dịch không biết chọn `TemporalField` hay `TemporalUnit`.

Đoạn minh họa trong một phương thức:

```java
TemporalField missingField = null;
TemporalUnit missingUnit = null;
System.out.println(date.isSupported(missingField)); // false
System.out.println(date.isSupported(missingUnit));  // false
// date.isSupported(null);                         // Mơ hồ overload.
```

`null` ở đây không có nghĩa “chọn trường mặc định”. Hai hàm tiện ích trong chương trình chủ động từ chối `null` bằng `Objects.requireNonNull`, giúp phát hiện lỗi truyền tham số thay vì coi đó là một lựa chọn không được hỗ trợ. Nếu chính đối tượng nhận là `null`, gọi phương thức vẫn gây `NullPointerException`.

Không cần rải kiểm tra trước mọi dòng khi kiểu và thao tác đã được xác định chắc chắn. Ví dụ nghiệp vụ nhận `LocalDate` và luôn đọc `getYear()` có thể dùng API cụ thể trực tiếp. Kiểm tra hữu ích nhất khi có sự khác biệt thật về kiểu hoặc lựa chọn trường/đơn vị.

Đối với trường hoặc đơn vị tùy chỉnh, việc hỗ trợ có thể do chính triển khai đó xác định. Không liệt kê cứng mỗi `ChronoField`/`ChronoUnit` rồi kết luận các đối tượng mở rộng đều không hỗ trợ; gọi hợp đồng API và tuân thủ mô tả triển khai.

## 8. Tự kiểm tra

1. Một hàm nhận `TemporalAccessor` chỉ cần đọc phút nếu có: chọn overload nào và trả gì khi thiếu?
2. Vì sao `Instant` không hỗ trợ `HOUR_OF_DAY` nhưng vẫn cộng được `HOURS`?
3. Sau `isSupported(MONTH_OF_YEAR) == true`, có thể đặt tháng thành 13 không?
4. Vì sao cần xem lại `get` khi trường được hỗ trợ nhưng vẫn có `UnsupportedTemporalTypeException`?
5. Có cần kiểm tra `isSupported(DAYS)` trước mọi `LocalDate.plusDays(1)` không?

Đối chiếu: (1) overload nhận trường, kết quả vắng mặt có biểu diễn rõ; (2) giờ địa phương cần múi giờ, cộng giờ trên trục thời gian thì không; (3) không; (4) có thể miền trường vượt `int`, dùng `getLong` khi phù hợp; (5) không cần nếu hợp đồng kiểu đã rõ, nhưng giới hạn kết quả vẫn phải được xem xét khi có khả năng chạm biên.