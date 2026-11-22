# DateTimeException và UnsupportedTemporalTypeException trong java.time

Khi làm việc với **java.time**, hai ngoại lệ rất dễ gặp là **DateTimeException** và **UnsupportedTemporalTypeException**. Chúng giúp phân biệt hai câu hỏi khác nhau: **giá trị ngày giờ có hợp lệ không?** và **kiểu dữ liệu đang dùng có hỗ trợ trường hoặc đơn vị thời gian được yêu cầu không?** Hiểu sự khác biệt giúp chọn đúng API, kiểm tra dữ liệu đầu vào và tìm nguyên nhân lỗi mà không che giấu sai thiết kế.

Bài học dùng Java 17+ và những kiểu tiêu biểu như **LocalDate**, **LocalTime**, **LocalDateTime**, **Instant**, **ZonedDateTime**, **ChronoField** và **ChronoUnit**.

## 1. Hai ngoại lệ nằm ở đâu trong hệ phân cấp?

~~~text
java.lang.RuntimeException
└── java.time.DateTimeException
    ├── java.time.temporal.UnsupportedTemporalTypeException
    ├── java.time.format.DateTimeParseException
    └── java.time.zone.ZoneRulesException
~~~

Đây là các nhánh thường gặp, không phải danh sách toàn bộ lớp kế thừa.

- **DateTimeException**: ngoại lệ runtime dùng cho các vấn đề liên quan ngày giờ, chẳng hạn ngày không hợp lệ, không thể chuyển đổi một giá trị theo quy tắc yêu cầu hoặc thông tin vùng/offset không phù hợp.
- **UnsupportedTemporalTypeException**: một **DateTimeException chuyên biệt**, thường được ném khi truy cập **TemporalField** hoặc thao tác bằng **TemporalUnit** không được hỗ trợ bởi kiểu temporal đang có. Một số phương thức **get()** cũng ném ngoại lệ này khi trường cần được đọc bằng **getLong()**.
- **DateTimeParseException**: nhánh chuyên biệt phát sinh khi phân tích văn bản ngày giờ thất bại, ví dụ chuỗi không đúng định dạng hoặc chứa ngày sai.
- **ZoneRulesException**: nhánh liên quan không tìm được quy tắc vùng hoặc lỗi tra cứu quy tắc vùng.

Vì chúng kế thừa **RuntimeException**, Java không buộc khai báo **throws** hay **catch**. Điều đó không có nghĩa mọi lỗi nên bị bỏ qua: phải xác định nguyên nhân, kiểm soát lỗi đầu vào và sửa cách dùng API khi sai.

**Quan hệ quan trọng:** mọi **UnsupportedTemporalTypeException** đều là **DateTimeException**, nhưng không phải mọi **DateTimeException** đều liên quan đến trường/đơn vị không được hỗ trợ.

## 2. Khi nào xuất hiện DateTimeException?

### 2.1. Ngày lịch không tồn tại

~~~java
LocalDate invalid = LocalDate.of(2026, 2, 30);
~~~

Ví dụ trên ném **DateTimeException** vì tháng 02/2026 chỉ có 28 ngày. Các trường hợp tương tự gồm tháng 13, ngày 31 của tháng 04, hoặc ngày 29/02 trong năm không nhuận. **LocalDate.of(...)** kiểm tra tính hợp lệ của ngày lịch ngay khi tạo đối tượng, giúp tránh lưu giá trị sai.

Cần phân biệt **giá trị hợp lệ theo lịch** với **giá trị hợp lệ theo nghiệp vụ**: 2026-02-28 hợp lệ với LocalDate nhưng chưa chắc là ngày giao hàng được phép. Ràng buộc “không giao Chủ nhật”, “không nhận ngày quá hạn” phải được kiểm tra riêng bằng quy tắc nghiệp vụ.

### 2.2. Chuỗi đầu vào không phân tích được

~~~java
LocalDate parsed = LocalDate.parse("2026-02-30");
~~~

Lệnh trên ném **DateTimeParseException**, vốn là **DateTimeException**, vì văn bản có dạng ngày ISO nhưng ngày lịch không hợp lệ. Chuỗi “30/02/2026” đưa thẳng vào **LocalDate.parse(...)** mặc định cũng thất bại vì không khớp định dạng ISO yêu cầu.

Trong API nhận dữ liệu người dùng, bắt **DateTimeParseException** để trả lỗi nhập liệu cụ thể. Nếu bắt trực tiếp **DateTimeException** cho mọi trường hợp, sẽ khó phân biệt dữ liệu sai với lỗi triển khai khi truy cập temporal.

### 2.3. Áp dụng offset hoặc vùng theo quy tắc nghiêm ngặt

Một **LocalDateTime** tại vùng có giờ mùa hè có thể không tồn tại trên thực tế. Chẳng hạn **2026-03-08T02:30** tại **America/New_York** nằm trong khoảng đồng hồ nhảy từ 02:00 lên 03:00.

~~~java
ZonedDateTime strict = ZonedDateTime.ofStrict(
        LocalDateTime.of(2026, 3, 8, 2, 30),
        ZoneOffset.ofHours(-5),
        ZoneId.of("America/New_York")
);
~~~

**ZonedDateTime.ofStrict(...)** ném **DateTimeException** khi local date-time và offset không hợp lệ theo quy tắc vùng. Ngược lại, **LocalDateTime.atZone(zone)** mặc định **dịch giờ trong gap tới thời điểm hợp lệ**; không được giả định rằng lệnh đó luôn ném ngoại lệ.

Trong lịch hẹn, hành vi “từ chối giờ không tồn tại”, “dịch sang giờ tiếp theo” hoặc “yêu cầu chọn offset khi giờ trùng lặp” là quyết định nghiệp vụ, cần nêu rõ trước khi xử lý.

## 3. Khi nào xuất hiện UnsupportedTemporalTypeException?

**java.time** tách các kiểu thời gian theo ngữ nghĩa. Một ngày lịch (**LocalDate**) có năm, tháng, ngày nhưng **không chứa giờ**; một giờ đồng hồ (**LocalTime**) có giờ, phút, giây nhưng **không chứa ngày**; **LocalDateTime** có cả ngày và giờ nhưng **không gắn với offset hoặc vùng**. Do đó không phải loại dữ liệu nào cũng thực hiện được cùng một phép toán.

### 3.1. Đọc TemporalField không được hỗ trợ

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);

int day = date.get(ChronoField.DAY_OF_MONTH); // Hợp lệ: 24
int hour = date.get(ChronoField.HOUR_OF_DAY); // UnsupportedTemporalTypeException
~~~

**ChronoField.DAY_OF_MONTH** là thành phần của LocalDate, còn **HOUR_OF_DAY** chỉ có ý nghĩa khi một đối tượng mang thông tin giờ (ví dụ LocalTime, LocalDateTime, ZonedDateTime). Java không tự thay bằng 00:00: nếu tự thêm giờ, đó sẽ là một quyết định phải do nghiệp vụ đưa ra.

Ví dụ khác:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 24, 9, 0);
long seconds = local.getLong(ChronoField.INSTANT_SECONDS);
~~~

Lệnh trên ném **UnsupportedTemporalTypeException**. **LocalDateTime** không có offset/ZoneId nên không thể tự suy ra giây kể từ epoch UTC. Muốn biết thời điểm tuyệt đối, phải quyết định ZoneId hoặc ZoneOffset theo dữ liệu nghiệp vụ rồi đổi sang Instant:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant timestamp = local.atZone(zone).toInstant();
~~~

**Lưu ý:** lệnh **atZone(...)** có chính sách mặc định với DST; nếu đặt lịch ở vùng có DST, cần xác thực gap/overlap theo quy tắc nghiệp vụ trước khi cố định timestamp.

### 3.2. Cộng/trừ TemporalUnit không được hỗ trợ

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
LocalDate next = date.plus(1, ChronoUnit.DAYS);  // Hợp lệ
LocalDate wrong = date.plus(1, ChronoUnit.HOURS); // UnsupportedTemporalTypeException
~~~

**ChronoUnit.DAYS** dùng được với LocalDate vì đối tượng mang ngày lịch. **ChronoUnit.HOURS** không phù hợp: LocalDate không biểu diễn giờ trong ngày. Đừng ép LocalDate sang LocalDateTime một cách tùy tiện chỉ để phép toán chạy được; hãy hỏi tại sao nghiệp vụ cần đơn vị “giờ” và đầu vào có đủ thời gian/ngữ cảnh vùng hay không.

Tương tự:

- **LocalTime.plus(1, ChronoUnit.MONTHS)** không hợp lệ vì LocalTime không có lịch tháng.
- **LocalDate.plus(1, ChronoUnit.MONTHS)** hợp lệ: thêm một tháng lịch.
- **Instant.plus(1, ChronoUnit.MONTHS)** không được hỗ trợ: một tháng không tương ứng với lượng giây cố định trên trục thời gian. Nếu cần tháng theo lịch, chuyển về vùng/ngày thích hợp và áp dụng quy tắc lịch.

### 3.3. Trường có hỗ trợ nhưng get() vẫn có thể ném lỗi

Đây là điểm dễ nhầm nhất: **isSupported(field) == true** không bảo đảm **get(field)** sẽ trả về một số nguyên **int**. Một số trường có miền giá trị rộng nên API chỉ cho đọc qua **getLong(field)**.

~~~java
LocalDate epochDate = LocalDate.of(1970, 1, 1);

boolean available = epochDate.isSupported(ChronoField.EPOCH_DAY); // true
long epochDay = epochDate.getLong(ChronoField.EPOCH_DAY);       // 0
int wrong = epochDate.get(ChronoField.EPOCH_DAY); // UnsupportedTemporalTypeException
~~~

Tương tự, **Instant** hỗ trợ **ChronoField.INSTANT_SECONDS** nhưng phải đọc bằng **getLong(...)**:

~~~java
Instant epoch = Instant.EPOCH;
long seconds = epoch.getLong(ChronoField.INSTANT_SECONDS); // 0
int wrong = epoch.get(ChronoField.INSTANT_SECONDS); // UnsupportedTemporalTypeException
~~~

Lý do không nằm ở giá trị 0 có vừa **int** hay không; hợp đồng của **get(field)** không hỗ trợ những trường như **EPOCH_DAY** hay **INSTANT_SECONDS** vì miền giá trị tổng quát vượt phạm vi an toàn của **int**. Không thử chuyển kiểu **(int)** hoặc xử lý ngoại lệ bằng cách trả 0 giả: dùng **getLong(field)** hoặc API ngữ nghĩa như **Instant.getEpochSecond()**.

## 4. Phân biệt TemporalField và TemporalUnit

| Khái niệm | Đại diện | Câu hỏi | Ví dụ |
|---|---|---|---|
| **TemporalField** | **ChronoField** | Đọc/đặt một thành phần nào? | YEAR, DAY_OF_MONTH, HOUR_OF_DAY, EPOCH_DAY |
| **TemporalUnit** | **ChronoUnit** | Cộng, trừ, đo bằng đơn vị gì? | DAYS, HOURS, MONTHS, SECONDS |
| **TemporalAccessor** | giao diện để đọc temporal | Có thể đọc field này không? | isSupported(field), getLong(field), range(field) |
| **Temporal** | giao diện mở rộng để điều chỉnh | Có thể thao tác với unit này không? | plus(amount, unit), minus(amount, unit), isSupported(unit) |

Các API có cùng tên **isSupported** nhưng nhận tham số khác nhau:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);

boolean canReadHour = date.isSupported(ChronoField.HOUR_OF_DAY); // false
boolean canAddHour = date.isSupported(ChronoUnit.HOURS);        // false
boolean canAddDay = date.isSupported(ChronoUnit.DAYS);          // true
~~~

**get(...)** và **getLong(...)** dùng **TemporalField**. **plus(amount, unit)** và **minus(amount, unit)** dùng **TemporalUnit**. Một loại dữ liệu có thể hỗ trợ trường đọc nhưng phép toán cộng tương ứng chưa chắc phù hợp; kiểm tra đúng overload cho điều định làm.

## 5. Ví dụ hoàn chỉnh Java 17+: so sánh các trường hợp ngoại lệ

Tạo tệp **DateTimeExceptionsDemo.java**:

~~~java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;
import java.time.temporal.UnsupportedTemporalTypeException;

public class DateTimeExceptionsDemo {

    private static void check(String name, Runnable operation) {
        try {
            operation.run();
            System.out.println(name + " -> OK");
        } catch (UnsupportedTemporalTypeException e) {
            System.out.println(name + " -> UnsupportedTemporalTypeException");
        } catch (DateTimeParseException e) {
            System.out.println(name + " -> DateTimeParseException");
        } catch (DateTimeException e) {
            System.out.println(name + " -> DateTimeException");
        }
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(1970, 1, 1);

        check("invalid-date", () -> LocalDate.of(2026, 2, 30));
        check("invalid-parse", () -> LocalDate.parse("2026-02-30"));
        check("hour-on-date", () -> date.get(ChronoField.HOUR_OF_DAY));
        check("hours-plus-date", () -> date.plus(1, ChronoUnit.HOURS));

        System.out.println("supports-epoch-day=" +
                date.isSupported(ChronoField.EPOCH_DAY));
        check("epoch-day-get", () -> date.get(ChronoField.EPOCH_DAY));
        System.out.println("epoch-day-getLong=" +
                date.getLong(ChronoField.EPOCH_DAY));

        check("instant-seconds-get",
                () -> Instant.EPOCH.get(ChronoField.INSTANT_SECONDS));
        System.out.println("instant-seconds-getLong=" +
                Instant.EPOCH.getLong(ChronoField.INSTANT_SECONDS));

        check("local-without-zone", () -> LocalDateTime
                .of(2026, 5, 1, 12, 0)
                .getLong(ChronoField.INSTANT_SECONDS));

        check("strict-dst-gap", () -> ZonedDateTime.ofStrict(
                LocalDateTime.of(2026, 3, 8, 2, 30),
                ZoneOffset.ofHours(-5),
                ZoneId.of("America/New_York")));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DateTimeExceptionsDemo.java
java DateTimeExceptionsDemo
~~~

Đầu ra với Java 17+ và quy tắc múi giờ có hiệu lực cho New York năm 2026:

~~~text
invalid-date -> DateTimeException
invalid-parse -> DateTimeParseException
hour-on-date -> UnsupportedTemporalTypeException
hours-plus-date -> UnsupportedTemporalTypeException
supports-epoch-day=true
epoch-day-get -> UnsupportedTemporalTypeException
epoch-day-getLong=0
instant-seconds-get -> UnsupportedTemporalTypeException
instant-seconds-getLong=0
local-without-zone -> UnsupportedTemporalTypeException
strict-dst-gap -> DateTimeException
~~~

**Cách đọc kết quả:**

1. **invalid-date** sai ngày lịch khi tạo đối tượng: **DateTimeException**.
2. **invalid-parse** thất bại trong quá trình đọc chuỗi: **DateTimeParseException**, thuộc họ DateTimeException.
3. **hour-on-date** và **hours-plus-date** đòi hỏi thông tin giờ mà LocalDate không mang: **UnsupportedTemporalTypeException**.
4. **supports-epoch-day=true** nhưng **epoch-day-get** vẫn lỗi, trong khi **getLong** cho 0: chọn phương thức truy cập đúng.
5. **Instant.EPOCH** có trường INSTANT_SECONDS nhưng **getLong**, không phải **get**, là API phù hợp.
6. **local-without-zone** cho thấy LocalDateTime không tương đương Instant.
7. **strict-dst-gap** cho thấy yêu cầu một offset không hợp lệ tại giờ địa phương bị bỏ qua dẫn tới DateTimeException.

Trong hàm **check**, thứ tự **catch** phải đặt các lớp con trước **DateTimeException**; bắt lớp cha trước sẽ khiến các nhánh con không thể tới được và Java báo lỗi biên dịch. Hàm này phục vụ **minh họa phân loại ngoại lệ**; trong sản phẩm thật không nên nuốt mọi DateTimeException rồi cho luồng xử lý tiếp tục như thể thành công.

## 6. Xác định khả năng hỗ trợ trước khi thao tác

Khi làm việc với một **TemporalAccessor** chưa biết kiểu cụ thể, có thể kiểm tra trường được hỗ trợ, sau đó dùng phương thức phù hợp:

~~~java
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.util.OptionalInt;

public class ReadHourDemo {

    static OptionalInt hourOfDay(TemporalAccessor value) {
        if (!value.isSupported(ChronoField.HOUR_OF_DAY)) {
            return OptionalInt.empty();
        }
        return OptionalInt.of(value.get(ChronoField.HOUR_OF_DAY));
    }

    public static void main(String[] args) {
        System.out.println(hourOfDay(LocalDate.of(2026, 10, 24)));
        System.out.println(hourOfDay(LocalTime.of(9, 15)));
    }
}
~~~

Chạy:

~~~bash
javac ReadHourDemo.java
java ReadHourDemo
~~~

Kết quả:

~~~text
OptionalInt.empty
OptionalInt[9]
~~~

Trong trường hợp này, **HOUR_OF_DAY** nằm trong miền **int**, nên **get(...)** phù hợp. Nếu đang xử lý **EPOCH_DAY** hay **INSTANT_SECONDS**, dùng **getLong(...)**. Nếu hợp đồng chỉ chấp nhận LocalTime, có thể định nghĩa tham số **LocalTime** ngay từ đầu để tránh nhầm kiểu. Dùng giao diện **TemporalAccessor** phù hợp khi thật sự nhận nhiều kiểu thời gian.

Với phép cộng trên **Temporal**, kiểm tra **isSupported(ChronoUnit.HOURS)** nếu cần làm việc với một đối tượng đa hình. Tuy nhiên, nếu phép cộng một giờ là yêu cầu bắt buộc mà kiểu truyền vào không hỗ trợ, **báo lỗi thiết kế hoặc hợp đồng rõ ràng** tốt hơn tự chuyển thành một kiểu khác theo giả định.

Một số TemporalField/TemporalUnit tùy biến có thể có quy tắc riêng. **isSupported(...)** không phải cam kết rằng mọi thao tác sẽ thành công: vẫn có thể gặp lỗi do miền giá trị, trạng thái dữ liệu hoặc phép toán.

## 7. Thiết kế xử lý lỗi đúng lớp trách nhiệm

### 7.1. Kiểm tra dữ liệu người dùng: phản hồi rõ, giữ nguyên nguyên nhân

Giả sử API nhận **startDate** theo ISO **yyyy-MM-dd**. Phần chuyển chuỗi thành đối tượng có thể đặt ở ranh giới đầu vào:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;

public class DateInput {
    public static LocalDate parseStartDate(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("startDate is required");
        }
        try {
            return LocalDate.parse(raw);
        } catch (DateTimeParseException e) {
            throw new IllegalArgumentException(
                    "startDate must be a valid ISO date (yyyy-MM-dd)", e);
        }
    }
}
~~~

Đây là lớp tiện ích không có **main**, dùng được trong controller/service hoặc validation layer. **LocalDate.parse** mặc định dùng định dạng ISO và kiểm tra tính hợp lệ. Cách chuyển thành **IllegalArgumentException** chỉ minh họa cách xây dựng thông điệp lỗi; HTTP 400 hay mã lỗi ứng dụng nên được quyết định ở tầng API.

Trong hệ thống thực tế:

- Trả thông báo giúp người dùng sửa trường cụ thể, nhưng không phơi stack trace hoặc chi tiết nội bộ.
- Giữ **cause** khi bọc ngoại lệ để log và chẩn đoán.
- Kiểm tra cả **null**, chuỗi trống và ràng buộc nghiệp vụ, vì không phải trường hợp nào cũng là DateTimeParseException.
- Phân biệt lỗi parse với lỗi phép toán trên một kiểu temporal sai trong code.

### 7.2. Lỗi do lập trình: sửa mô hình và phương thức được gọi

Nếu service ném **UnsupportedTemporalTypeException** do lấy **HOUR_OF_DAY** từ **LocalDate**, lựa chọn đúng thường là:

- Đổi mô hình/đầu vào sang **LocalDateTime** hoặc **LocalTime** nếu thực sự cần giờ; hoặc
- Bỏ truy cập giờ nếu nghiệp vụ chỉ có ngày; hoặc
- Kết hợp LocalDate với một giờ đã được chính sách nghiệp vụ xác định, thay vì tự chọn 00:00.

Trả **null**, **0**, hay **1970-01-01** trong catch sẽ che giấu thiếu thông tin. Đừng biến lỗi sai thiết kế thành dữ liệu giả.

### 7.3. Khi cần phân loại lỗi từ thư viện dùng chung

Một adapter có thể nhận dữ liệu nhiều kiểu và phân biệt:

~~~java
try {
    // Một phép xử lý thời gian đã được xác định rõ
} catch (UnsupportedTemporalTypeException e) {
    // Field/unit không tương thích: kiểm tra kiểu dữ liệu và API gọi
} catch (DateTimeParseException e) {
    // Văn bản ngày giờ không parse được: lỗi đầu vào
} catch (DateTimeException e) {
    // Vấn đề ngày giờ khác: xem ngữ cảnh và cause
}
~~~

Đoạn trên **chỉ minh họa thứ tự catch**, chưa phải một chương trình độc lập. Nên bắt loại ngoại lệ **sát nơi có thể xử lý hiệu quả**. Không dùng catch rộng bao quanh toàn bộ yêu cầu HTTP rồi quy mọi DateTimeException thành “người dùng nhập sai”: một số có thể đến từ bug bên trong ứng dụng.

### 7.4. Các loại lỗi không thuộc hai ngoại lệ này

Không giả định mọi vấn đề ngày giờ đều ném DateTimeException:

| Tình huống | Nhóm lỗi có thể gặp | Bài học |
|---|---|---|
| Truyền **null** vào API yêu cầu đối tượng khác null | **NullPointerException** | Kiểm tra hợp đồng null riêng |
| Pattern không hợp lệ khi gọi **DateTimeFormatter.ofPattern(...)** | **IllegalArgumentException** | Sai cấu hình formatter, khác với parse chuỗi |
| Tính toán số học quá lớn ở một số phép xử lý | **ArithmeticException** hoặc ngoại lệ thời gian tùy phép toán | Không giả định một loại catch bao hết |
| Ngày hợp lệ nhưng trái quy tắc kinh doanh | Ngoại lệ/validation do ứng dụng định nghĩa | java.time chỉ kiểm tra tính hợp lệ theo dữ liệu thời gian |
| Giờ DST được **atZone** tự điều chỉnh | Có thể **không ném ngoại lệ** | Phải kiểm tra chính sách nghiệp vụ, không dựa vào catch |

Các mục “có thể gặp” phản ánh hành vi tùy API cụ thể; khi triển khai cần xem hợp đồng phương thức đang gọi.

## 8. Xử lý DST để tránh DateTimeException ngoài ý muốn

Giả sử người dùng đặt lịch tại New York vào **2026-03-08 02:30**. Vùng này có gap DST, nên không có Instant tương ứng với giờ địa phương đó. Trước khi tạo lịch, có thể kiểm tra:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public class ResolveWallTimeDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        LocalDateTime requested = LocalDateTime.of(2026, 3, 8, 2, 30);
        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(requested);

        if (offsets.isEmpty()) {
            System.out.println("GAP: local time does not exist");
        } else if (offsets.size() == 2) {
            System.out.println("OVERLAP: choose an offset");
        } else {
            System.out.println("VALID: " + offsets.get(0));
        }
    }
}
~~~

Chạy:

~~~bash
javac ResolveWallTimeDemo.java
java ResolveWallTimeDemo
~~~

Kết quả theo quy tắc vùng áp dụng cho New York năm 2026:

~~~text
GAP: local time does not exist
~~~

**Ý nghĩa:** **getValidOffsets** trả 0 offset cho gap, thông thường 1 cho giờ hợp lệ, và 2 cho overlap. Nếu có 2, ứng dụng phải có chính sách chọn một offset hoặc cho người dùng chọn. Nếu có 0, ứng dụng phải từ chối hoặc quyết định dịch giờ. **ofStrict(...)** thích hợp khi muốn yêu cầu một offset chính xác đã được xác nhận và thất bại nếu không hợp lệ.

Những quy tắc này phụ thuộc dữ liệu múi giờ IANA mà JDK cung cấp; dữ liệu lịch tương lai có thể thay đổi nếu luật địa phương thay đổi. Khi đặt lịch tương lai, lưu **LocalDateTime + ZoneId** (và thông tin xử lý gap/overlap nếu cần) để giữ đúng ý định đặt lịch, thay vì chỉ giữ timestamp đã quy đổi.

## 9. Checklist chẩn đoán khi gặp stack trace

Khi thấy **DateTimeException** hoặc **UnsupportedTemporalTypeException**, kiểm tra theo thứ tự:

1. **Ngoại lệ chính xác là lớp nào?** Nhìn tên lớp, stack trace và thao tác đang thực hiện; DateTimeParseException là nhánh riêng.
2. **Đối tượng thực tế là kiểu gì?** LocalDate không có giờ, LocalTime không có ngày, LocalDateTime không có vùng, Instant không có tháng lịch độc lập.
3. **Đang hỏi TemporalField hay dùng TemporalUnit?** Truy xuất thông tin khác với cộng/trừ đơn vị.
4. **Field/unit đó có được hỗ trợ?** Kiểm tra **isSupported(...)** đúng tham số khi thao tác trên kiểu đa hình.
5. **Nếu field được hỗ trợ, có gọi get() nhầm thay vì getLong()?** Đặc biệt **EPOCH_DAY** và **INSTANT_SECONDS**.
6. **Giá trị ngày giờ có hợp lệ không?** Tháng/ngày, năm nhuận, vùng/offset và trường hợp DST gap/overlap.
7. **Thiếu thông tin ngữ cảnh nào?** Nếu cần Instant mà chỉ có LocalDateTime, phải xác định vùng hoặc offset hợp lệ.
8. **Lỗi do input hay do code?** Đầu vào sai cần trả validation rõ ràng; truy cập trường sai cần sửa thiết kế.
9. **Đã kiểm tra ranh giới chưa?** Ngày 29/02, 30/02, cuối tháng, chuyển DST, cùng timestamp ở các múi giờ khác nhau.

## 10. Lỗi thường gặp và cách sửa

| Cách viết dễ lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| **LocalDate.of(2026, 2, 30)** | Ngày lịch không hợp lệ | Kiểm tra ngày đầu vào; xử lý DateTimeException tại ranh giới thích hợp |
| **LocalDate.parse("2026-02-30")** | Văn bản không thành ngày hợp lệ | Xử lý DateTimeParseException và báo trường sai |
| **LocalDate.get(HOUR_OF_DAY)** | LocalDate không có giờ | Cần LocalTime/LocalDateTime hoặc không hỏi giờ |
| **LocalTime.plus(1, MONTHS)** | LocalTime không có tháng | Cần LocalDate/LocalDateTime nếu nghiệp vụ có lịch |
| **LocalDate.get(EPOCH_DAY)** | get() không hỗ trợ trường có miền rộng | Dùng getLong(EPOCH_DAY) |
| **Instant.get(INSTANT_SECONDS)** | get() không phù hợp với trường | Dùng getLong(...) hoặc getEpochSecond() |
| **LocalDateTime.getLong(INSTANT_SECONDS)** | Không có vùng/offset để xác định Instant | Gắn ZoneId/ZoneOffset hợp lệ rồi toInstant() |
| **ZonedDateTime.ofStrict(...)** với giờ DST gap | Giờ/offset không hợp lệ theo ZoneRules | Kiểm tra getValidOffsets, áp dụng chính sách |
| **catch(DateTimeException)** trước **catch(UnsupportedTemporalTypeException)** | Catch lớp con bị che, code không biên dịch | Bắt lớp con trước lớp cha |
| **catch(DateTimeException) { return null; }** | Nuốt lỗi, sinh trạng thái khó chẩn đoán | Xử lý ở tầng phù hợp hoặc để lỗi nổi lên |
| Tưởng **atZone** luôn ném lỗi ở gap | API có quy tắc điều chỉnh mặc định | Chủ động kiểm tra khoảng thời gian bất thường |

## 11. Câu hỏi tự kiểm tra

**1. Vì sao LocalDate.of(2026, 2, 30) không ném UnsupportedTemporalTypeException?** Vì kiểu LocalDate hoàn toàn hỗ trợ ngày/tháng/năm; chỉ có **giá trị lịch** không hợp lệ. Đây là DateTimeException.

**2. LocalDate.isSupported(EPOCH_DAY) trả true; vậy date.get(EPOCH_DAY) chắc chắn chạy được?** Không. **get()** chỉ trả int; phải dùng **getLong(EPOCH_DAY)**.

**3. Vì sao LocalDateTime không đọc được INSTANT_SECONDS?** Thiếu thông tin vùng/offset để xác định một điểm trên trục thời gian. Cần thêm ngữ cảnh đã được nghiệp vụ xác nhận.

**4. Có nên bắt DateTimeException cho cả parser và service?** Chỉ khi thực sự xử lý được lỗi tổng quát. Với đầu vào, ưu tiên **DateTimeParseException**; với lỗi không hỗ trợ field/unit, sửa mô hình hoặc API.

**5. Một giờ địa phương tại DST gap có luôn tạo DateTimeException?** Không. **ofStrict** có thể ném, nhưng **atZone** mặc định có thể dịch sang giờ hợp lệ. Phải biết chính xác phương thức đang gọi.

**6. LocalDate.plus(1, HOURS) thất bại thì thêm 00:00 để chạy có đúng không?** Chưa chắc. LocalDate không có giờ; muốn cộng giờ cần quy tắc nghiệp vụ xác định thời gian và có thể cả vùng. Không thêm dữ liệu giả để né ngoại lệ.

**Ghi nhớ:** **DateTimeException** biểu thị một lỗi thời gian ở mức khái quát; **UnsupportedTemporalTypeException** chỉ rõ kiểu temporal không đáp ứng field/unit hoặc cách truy cập đang dùng; **DateTimeParseException** chỉ lỗi parse. Cần sửa nguyên nhân theo đúng tầng: giá trị đầu vào, ngữ nghĩa của kiểu dữ liệu, phương thức truy cập hay quy tắc vùng thời gian.
