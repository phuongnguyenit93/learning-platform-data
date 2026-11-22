# `fallbackPatterns` và tương thích định dạng đầu vào trong Spring Framework

## 1. Vấn đề cần giải quyết

Khi ứng dụng nhận ngày/giờ từ biểu mẫu, URL hoặc dữ liệu do người dùng nhập, cùng một ngày có thể tồn tại dưới nhiều cách viết:

| Nguồn đầu vào | Chuỗi ngày | Ý nghĩa |
| --- | --- | --- |
| Giao diện mới, quy ước ISO | `2026-11-05` | Ngày 5 tháng 11 năm 2026 |
| Giao diện cũ tại Việt Nam | `05/11/2026` | Cùng một ngày |
| Hệ thống cũ dùng dấu chấm | `05.11.2026` | Cùng một ngày |

Nếu chỉ khai báo `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`, Spring có thể phân tích chuỗi ISO nhưng các giá trị cũ không khớp định dạng chính sẽ thất bại. Thay đổi toàn bộ client cùng lúc có thể khó thực hiện trong giai đoạn chuyển đổi.

`fallbackPatterns` của `@DateTimeFormat` cho phép **giữ một định dạng chính** và khai báo **những mẫu bổ sung chỉ để đọc đầu vào**. Đây là công cụ tương thích trong Spring Formatting/Conversion, đặc biệt hữu ích khi di chuyển từ định dạng legacy sang ISO hoặc khi dữ liệu hiển thị từ các phiên bản Java/CLDR khác nhau.

Mục tiêu sau bài học:

- Giải thích lúc nào Spring thử `fallbackPatterns`, chiều parse khác chiều print như thế nào.
- Dùng đúng `@DateTimeFormat` với `LocalDate` và biết cách tích hợp vào Spring MVC.
- Nhận biết sự mơ hồ của mẫu ngày, ảnh hưởng `Locale`/JDK/múi giờ và giới hạn của fallback.
- Kiểm tra cả định dạng chính, định dạng dự phòng, dữ liệu sai và đầu ra chuẩn hóa.

## 2. Cơ chế của `@DateTimeFormat`

Spring cung cấp annotation `org.springframework.format.annotation.DateTimeFormat`, dùng cho trường, phương thức, tham số và annotation khác. Nó hỗ trợ các kiểu ngày/giờ như `java.time.LocalDate`, `LocalDateTime`, `LocalTime`, `java.util.Date` và một số kiểu liên quan. Đối với định dạng đầu vào, annotation khai báo ba cách xác định **định dạng chính**:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `iso` | Dùng mẫu ISO đã định nghĩa sẵn (`DATE`, `TIME`, `DATE_TIME`) | `iso = ISO.DATE` |
| `pattern` | Dùng mẫu cụ thể do ứng dụng kiểm soát | `pattern = "dd/MM/yyyy"` |
| `style` | Dùng kiểu hiển thị phụ thuộc quy tắc vùng và dữ liệu JDK | `style = "S-"` |
| `fallbackPatterns` | Danh sách mẫu tùy chỉnh để thử **khi parse theo mẫu chính thất bại** | `{"dd/MM/yyyy", "dd.MM.yyyy"}` |

Chỉ nên cấu hình một trong `pattern`, `iso` hoặc `style` làm chuẩn chính. Nếu khai báo đồng thời, Spring ưu tiên `pattern` hơn `iso`, và `iso` hơn `style`; cách đó dễ khiến người đọc hiểu sai ý định. Không khai báo gì thì formatter dùng style mặc định (`SS`) — một lựa chọn phụ thuộc locale và môi trường chạy.

`fallbackPatterns` có kiểu `String[]`, mặc định là mảng rỗng. Tính năng này có từ **Spring Framework 5.3.5**. Cú pháp điển hình:

```java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class BookingForm {

    @DateTimeFormat(
        iso = DateTimeFormat.ISO.DATE,
        fallbackPatterns = {"dd/MM/yyyy", "dd.MM.yyyy"}
    )
    private LocalDate bookingDate;

    public LocalDate getBookingDate() {
        return bookingDate;
    }

    public void setBookingDate(LocalDate bookingDate) {
        this.bookingDate = bookingDate;
    }
}
```

Đây là model dùng cho binding; khi đặt trong một ứng dụng Spring MVC, cần khai báo và dùng model theo controller/form tương ứng.

### Thứ tự Spring xử lý

```text
Văn bản đầu vào
      |
      v
Parse bằng định dạng chính (ở đây: ISO.DATE)
      |
      +--- thành công ---> Giá trị LocalDate
      |
      +--- thất bại
              |
              v
     Thử fallbackPatterns[0]: dd/MM/yyyy
              |
              +--- thành công ---> Giá trị LocalDate
              |
              +--- thất bại
                      |
                      v
             Thử fallbackPatterns[1]: dd.MM.yyyy
                      |
                      +--- thành công ---> Giá trị LocalDate
                      |
                      +--- thất bại ---> Lỗi chuyển đổi kiểu/binding
```

Spring thử các fallback theo thứ tự cấu hình. Mẫu đầu tiên đọc thành công sẽ được sử dụng; không có bước "đoán" format hợp lý nhất theo nội dung hoặc vùng địa lý. Do đó **thứ tự fallback là một quyết định về tương thích đầu vào**, cần kiểm thử và ghi rõ trong hợp đồng dữ liệu.

**Điểm quan trọng nhất:** `fallbackPatterns` chỉ tác động đến **parse**. Khi **print** đối tượng ngày/giờ thành chuỗi thông qua Spring formatting, định dạng được sử dụng luôn là `pattern`, `iso` hoặc `style` chính. Ví dụ cả ba chuỗi trên có thể tạo cùng `LocalDate.of(2026, 11, 5)`, nhưng khi in theo annotation trong ví dụ, kết quả là `2026-11-05`.

Nói cách khác:

```text
parse("2026-11-05") ──┐
parse("05/11/2026") ───┼──> LocalDate(2026-11-05) ──print──> "2026-11-05"
parse("05.11.2026") ───┘
```

Đây là **tương thích đầu vào kèm chuẩn hóa đầu ra**, không phải cơ chế ghi nhớ format ban đầu của từng người dùng.

## 3. Ví dụ Java 17 chạy độc lập với Spring Formatting

Ví dụ sử dụng `DefaultFormattingConversionService` của Spring Core/Context, không cần mở HTTP server. Ta dùng `TypeDescriptor` của một field có `@DateTimeFormat` để giữ annotation trong quá trình chuyển đổi. Nếu chỉ gọi `convert(text, LocalDate.class)` thì đường chuyển đổi **không có thông tin annotation của field**, vì thế ví dụ sẽ không chứng minh được tác dụng của `fallbackPatterns` riêng cho field.

Tạo một dự án Gradle trống với các tệp sau. Ví dụ cố định Spring Framework `6.2.14` để dễ tái hiện; với ứng dụng Spring Boot, hãy sử dụng phiên bản Spring Framework do BOM của Boot quản lý.

**`settings.gradle`**:

```groovy
rootProject.name = 'datetime-fallback-demo'
```

**`build.gradle`**:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'DateFallbackDemo'
}
```

**`src/main/java/DateFallbackDemo.java`**:

```java
import java.lang.reflect.Field;
import java.time.LocalDate;
import java.util.Locale;

import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.support.DefaultFormattingConversionService;

public class DateFallbackDemo {

    public static class BookingForm {
        @DateTimeFormat(
            iso = DateTimeFormat.ISO.DATE,
            fallbackPatterns = {"dd/MM/yyyy", "dd.MM.yyyy"}
        )
        public LocalDate bookingDate;
    }

    public static void main(String[] args) throws Exception {
        var conversionService = new DefaultFormattingConversionService();

        Field field = BookingForm.class.getField("bookingDate");
        TypeDescriptor dateField = new TypeDescriptor(field);
        TypeDescriptor text = TypeDescriptor.valueOf(String.class);

        try {
            LocaleContextHolder.setLocale(Locale.US);

            String[] inputs = {
                "2026-11-05",
                "05/11/2026",
                "05.11.2026"
            };

            for (String input : inputs) {
                LocalDate date = (LocalDate)
                    conversionService.convert(input, text, dateField);

                String printed = (String)
                    conversionService.convert(date, dateField, text);

                System.out.println(input + " -> " + date + " -> " + printed);
            }

            try {
                conversionService.convert("31/02/2026", text, dateField);
                System.out.println("UNEXPECTED_SUCCESS");
            } catch (ConversionFailedException expected) {
                System.out.println("31/02/2026 -> rejected");
            }
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
```

Chạy với Gradle đã cài sẵn:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, sử dụng `./gradlew run --quiet` trên Linux/macOS hoặc `gradlew.bat run --quiet` trên Windows.

Kết quả chuẩn cần nhận được:

```text
2026-11-05 -> 2026-11-05 -> 2026-11-05
05/11/2026 -> 2026-11-05 -> 2026-11-05
05.11.2026 -> 2026-11-05 -> 2026-11-05
31/02/2026 -> rejected
```

**Giải thích từng phần:**

1. `DefaultFormattingConversionService` đăng ký các cơ chế chuyển đổi/format mặc định, bao gồm xử lý `@DateTimeFormat` cho Java Time.
2. `new TypeDescriptor(field)` mang theo annotation của `BookingForm.bookingDate`; đây là lý do fallback được áp dụng đúng tại nơi khai báo.
3. `convert(input, text, dateField)` diễn giải chuỗi thành `LocalDate` bằng mẫu chính rồi đến các mẫu dự phòng.
4. `convert(date, dateField, text)` sử dụng chiều in của cùng annotation; cả ba trường hợp đều xuất ISO.
5. `LocaleContextHolder.setLocale(Locale.US)` cung cấp locale tường minh cho ví dụ không có HTTP request. `finally` xóa trạng thái theo luồng, tránh rò rỉ ngữ cảnh qua lần chạy khác.
6. `31/02/2026` không phải ngày hợp lệ: fallback cho phép nhiều **cách viết**, chứ không biến một ngày sai thành ngày hợp lệ.

Trong mã này, `LocalDate` biểu diễn ngày lịch, **không có giờ hay múi giờ**. Bài toán chỉ cần ngày nên không nên đổi sang `Date` hoặc `Instant` một cách tùy tiện.

## 4. Áp dụng vào Spring MVC

Trong ứng dụng Spring MVC hoặc Spring Boot có Web MVC, `ConversionService` được dùng tại các điểm binding của request. Có thể đặt `@DateTimeFormat` trên thuộc tính của `@ModelAttribute` hoặc trực tiếp trên tham số controller.

Ví dụ controller độc lập về ý tưởng (giả định ứng dụng Spring MVC đã được cấu hình và chạy):

```java
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BookingPreviewController {

    @GetMapping("/bookings/preview")
    public String preview(
        @RequestParam("date")
        @DateTimeFormat(
            iso = DateTimeFormat.ISO.DATE,
            fallbackPatterns = {"dd/MM/yyyy", "dd.MM.yyyy"}
        )
        LocalDate date
    ) {
        return date.toString();
    }
}
```

Có thể thử bằng các request sau:

```bash
curl -G 'http://localhost:8080/bookings/preview' \
  --data-urlencode 'date=2026-11-05'

curl -G 'http://localhost:8080/bookings/preview' \
  --data-urlencode 'date=05/11/2026'

curl -G 'http://localhost:8080/bookings/preview' \
  --data-urlencode 'date=05.11.2026'
```

Trong ứng dụng có controller trên, cả ba request hợp lệ đều trả về body:

```text
2026-11-05
```

Ở controller này, `LocalDate.toString()` tự xuất ISO để minh họa giá trị nhận được; việc **Spring gọi formatter khi print** đã được chứng minh trực tiếp trong ví dụ `ConversionService` ở mục 3. Đừng nhầm rằng trả về một `String` từ `@RestController` sẽ tự kích hoạt chiều `print` của `@DateTimeFormat`.

Với request chứa `date=31/02/2026`, quá trình chuyển đổi `@RequestParam` thất bại; theo xử lý lỗi MVC mặc định, yêu cầu thông thường sẽ nhận HTTP **400 Bad Request**. Kết cấu response lỗi cụ thể phụ thuộc cấu hình của ứng dụng. Với `@ModelAttribute`, lỗi chuyển đổi field có thể xuất hiện trong `BindingResult`; nên hiển thị thông báo cho người dùng thay vì nuốt lỗi và thay bằng một ngày mặc định.

**Ranh giới quan trọng:** `@RequestBody` JSON thường được xử lý bởi Jackson qua `HttpMessageConverter`. `@DateTimeFormat(fallbackPatterns = ...)` trên field **không tự đảm bảo** rằng Jackson chấp nhận các mẫu ngày cũ trong JSON. Nếu cần hỗ trợ nhiều định dạng ngày trong JSON, hãy cấu hình quy ước JSON rõ ràng (ví dụ deserializer tùy chỉnh) và kiểm thử riêng đường đó. Đối với API trao đổi dữ liệu giữa hệ thống, thường nên dùng một format chuẩn như ISO 8601 thay vì mở rộng đầu vào vô hạn.

## 5. Thiết kế định dạng dự phòng an toàn

### Chọn định dạng chính có tính ổn định

Ưu tiên ISO cho dữ liệu trao đổi, vì một ngày lịch `2026-11-05` có ý nghĩa rõ ràng ở nhiều môi trường. Dùng fallback để **tiếp nhận các mẫu cũ có căn cứ**, ví dụ `dd/MM/yyyy` khi hệ thống cũ từng yêu cầu nhập như vậy, rồi chuẩn hóa sau khi binding.

Nếu cần hiển thị ngày theo thói quen địa phương ở giao diện, vẫn có thể chọn `pattern = "dd/MM/yyyy"` làm chính và chỉ nhận ISO như fallback. Khi đó chiều `print` sẽ là `05/11/2026`. Hãy quyết định theo hợp đồng giao diện; không coi chuỗi hiển thị là format lưu trữ duy nhất trong hệ thống.

### Tránh hai mẫu đọc cùng một chuỗi nhưng cho hai ngày khác nhau

Cặp `dd/MM/yyyy` và `MM/dd/yyyy` có thể cùng chấp nhận `03/04/2026`:

- Theo `dd/MM/yyyy`, đó là ngày **3 tháng 4**.
- Theo `MM/dd/yyyy`, đó là ngày **4 tháng 3**.

Spring sẽ dùng mẫu thành công trước; `fallbackPatterns` không có bộ phát hiện nhập nhằng. Nếu khách hàng đến từ nhiều thị trường, nên yêu cầu định dạng tường minh theo từng giao diện/đường API, hoặc buộc dùng ISO. Chỉ đổi thứ tự mẫu không làm hết mơ hồ.

### Phân biệt định dạng với dữ liệu không hợp lệ

- `2026-11-05`: đúng ISO.DATE.
- `05/11/2026`: đúng mẫu dự phòng `dd/MM/yyyy`.
- `05.11.2026`: đúng mẫu dự phòng `dd.MM.yyyy`.
- `31/02/2026`: ngày không tồn tại; phải báo lỗi.
- `2026-11-05xyz`: có phần đuôi ngoài định dạng; không nên chấp nhận.
- Giá trị trống hoặc thiếu: cần có quy tắc riêng về trường bắt buộc, chẳng hạn Bean Validation `@NotNull` cho field thích hợp. Fallback không thay thế kiểm tra bắt buộc.

`fallbackPatterns` **không** có nghĩa là bật chế độ parser luôn dễ dãi (*lenient*), cũng không dùng để kiểm tra ngày có nằm trong thời hạn đăng ký, có phải ngày nghỉ hay có quyền sửa lịch hay không. Đó là quy tắc nghiệp vụ/validation riêng.

### Giữ hợp đồng ngày, giờ và múi giờ rõ ràng

`LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime` và `Instant` có ngữ nghĩa khác nhau. Một mẫu fallback hợp lệ phải tương thích kiểu dữ liệu đích. Ví dụ `ISO.DATE` chỉ chứa ngày, không tự chuyển một thời điểm có múi giờ thành ngày của người dùng.

Với kiểu legacy `java.util.Date`, Javadoc của Spring quy định khi dùng `iso` thì mặc định dùng **UTC** cho formatting, còn `style`/`pattern` dùng timezone mặc định của JVM; các fallback dùng cùng quy tắc timezone với định dạng chính. Vì thế nếu nghiệp vụ cần timezone xác định, phải quản lý timezone chủ động và kiểm thử rõ. Với `LocalDate` ở ví dụ chính, không có vấn đề chuyển đổi múi giờ do bản thân kiểu dữ liệu không mang giờ.

### `Locale` vẫn có vai trò

Một pattern thuần chữ số như `dd/MM/yyyy` thường dễ kiểm soát. Với pattern chứa tên tháng hoặc AM/PM, cách parse còn phụ thuộc `Locale` mà Spring cung cấp ở ngữ cảnh hiện tại. `fallbackPatterns` không thể tự gán một locale khác cho từng phần tử.

Ví dụ `"05 Nov 2026"` có thể cần locale tiếng Anh; đổi thứ tự fallback trong một request đang dùng locale khác không bảo đảm parser hiểu được tên tháng. Khi cần nhiều **ngôn ngữ đầu vào**, không chỉ nhiều dấu phân cách, hãy thiết kế lựa chọn locale rõ ràng hoặc một parser tùy chỉnh có kiểm soát.

## 6. Tương thích JDK 20+ và dữ liệu locale (CLDR)

Bên cạnh các format do client cũ gửi, dữ liệu đầu vào còn có thể thay đổi khi nâng phiên bản Java. Các kiểu định dạng dựa trên `DateFormat`/`FormatStyle` lấy pattern từ dữ liệu locale (CLDR); mẫu được trả về có thể khác nhau giữa các JDK. Spring cảnh báo rằng thay đổi trên **JDK 20 trở lên** có thể ảnh hưởng ngày/giờ được parse hoặc hiển thị bằng style phụ thuộc locale.

Một ví dụ thực tế trong tài liệu Spring là dấu cách trước `AM`/`PM`: một số môi trường sử dụng dấu cách thông thường (U+0020), môi trường khác sử dụng **narrow no-break space** (U+202F). Hai chuỗi có thể trông giống nhau trên màn hình nhưng khác ký tự Unicode. Nếu ứng dụng lưu hoặc nhận đầu vào dưới một trong hai dạng, parser dựa trên pattern của JDK khác có thể không khớp.

Hướng xử lý được Spring khuyến nghị:

1. Với hợp đồng mới, ưu tiên ISO hoặc pattern cụ thể đã được kiểm soát.
2. Nếu phải tiếp nhận chuỗi cũ, liệt kê các fallback đã được xác minh, kể cả khác biệt ký tự khoảng trắng khi thực sự cần.
3. Kiểm thử trên các JDK, locale và bản dữ liệu thực tế của hệ thống; dùng UTF-8 cho trao đổi văn bản.
4. Tránh chủ động bật chế độ lenient quá rộng chỉ để vượt qua một lỗi nhập liệu, vì như vậy dễ khiến ngày không hợp lệ được chuyển thành ngày khác.

Đối với một ứng dụng đã dùng `@DateTimeFormat(style = "-S")`, việc thay bằng ISO hoặc pattern cố định là lựa chọn đáng cân nhắc trước khi thêm rất nhiều fallback. Fallback giúp duy trì tương thích trong giai đoạn chuyển đổi, không thay thế một hợp đồng nhập xuất ổn định.

## 7. Kiểm thử cần có khi phát hành

Cùng một cấu hình `ISO.DATE` + `{"dd/MM/yyyy", "dd.MM.yyyy"}`, hãy kiểm tra các nhóm dưới đây:

| Nhóm | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Định dạng chính | `2026-11-05` | Parse thành `LocalDate(2026-11-05)` |
| Fallback thứ nhất | `05/11/2026` | Parse thành cùng ngày |
| Fallback thứ hai | `05.11.2026` | Parse thành cùng ngày |
| Đầu ra chuẩn | Giá trị từ bất kỳ dòng trên | Formatter print ra `2026-11-05` |
| Ngày không hợp lệ | `31/02/2026` | Báo lỗi chuyển đổi |
| Mẫu không được hỗ trợ | `11-05-2026` | Báo lỗi nếu không khớp mẫu nào |
| Chuỗi thừa | `2026-11-05x` | Không tự bỏ ký tự cuối |
| Input mơ hồ | `03/04/2026` nếu cho phép cả D/M và M/D | Cần hợp đồng loại bỏ nhập nhằng |
| Locale | Nhập tên tháng/AM-PM | Chạy dưới các locale thực tế |
| Môi trường | JDK cũ và JDK mới | Kiểm tra thay đổi CLDR/style |

Ngoài kiểm thử parser đơn lẻ, nên có ít nhất một bài **test Spring MVC** (ví dụ `MockMvc`) chứng minh đúng field hoặc tham số nhận giá trị từ HTTP, và một bài test lỗi 400 hoặc `BindingResult`. Đặc biệt, test riêng nhánh Jackson nếu endpoint dùng `@RequestBody`: thành công ở form binding không có nghĩa JSON đã tương thích.

Để vận hành an toàn khi đang hỗ trợ client cũ:

- Ghi tài liệu format chính và các format dự phòng được chấp nhận.
- Xác định nguồn nào cần fallback, tránh cho mọi endpoint chấp nhận mọi mẫu.
- Nếu có kế hoạch loại bỏ định dạng cũ, theo dõi mức sử dụng bằng đo lường ở ranh giới request hoặc custom parsing. `@DateTimeFormat` không tự cung cấp một trường cho biết mẫu fallback nào vừa khớp.
- Khi không còn client phụ thuộc, giảm dần fallback đã hết nhu cầu; giữ tập format nhỏ để dễ kiểm thử và giảm mơ hồ.

## 8. Lỗi thường gặp và cách sửa

| Lỗi thiết kế | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ fallback ảnh hưởng chiều in | Output không giữ format người dùng đã nhập | Hiểu rằng chỉ định dạng chính dùng để print |
| Khai báo đồng thời `pattern`, `iso`, `style` | Quy tắc ưu tiên gây hiểu nhầm | Chỉ chọn một format chính |
| Trộn `dd/MM/yyyy` với `MM/dd/yyyy` | Một chuỗi có hai cách hiểu | Cố định format theo giao diện/nguồn dữ liệu |
| Chỉ test một chuỗi hợp lệ | Bỏ sót ngày giả, input thừa và format legacy | Lập ma trận test đầy đủ |
| Dùng style phụ thuộc locale làm hợp đồng API | JDK/CLDR thay đổi có thể phá tương thích | Dùng ISO hoặc pattern cụ thể |
| Mong annotation tự chạy cho JSON | Jackson không dùng cùng pipeline binding | Thiết kế serializer/deserializer JSON riêng |
| Dùng `Date` để biểu diễn ngày lịch | Có thể phát sinh lệch ngày do timezone | Dùng `LocalDate` khi nghiệp vụ chỉ cần ngày |
| Cố ép parser thành lenient | Nhập sai có thể biến thành ngày khác | Chỉ chấp nhận các mẫu dự phòng cần thiết |

### Tự kiểm tra

1. Cả `05/11/2026` và `05.11.2026` được parse vào một `LocalDate`. Nếu định dạng chính là `ISO.DATE`, chuỗi nào được Spring formatter dùng khi in? **`2026-11-05`**, bất kể chuỗi đầu vào ban đầu.
2. Nếu thêm cả `MM/dd/yyyy` vào fallback, `03/04/2026` có chắc được hiểu đúng ý người dùng không? **Không**; mẫu thành công trước thắng, nên phải giải quyết mơ hồ bằng hợp đồng đầu vào.
3. `fallbackPatterns` có giúp Jackson đọc JSON trong `@RequestBody` không? **Không tự động**; phải kiểm tra đường JSON riêng.
4. Vì sao một style định dạng giờ có thể hỏng sau khi nâng JDK dù Java code không đổi? Dữ liệu locale/CLDR và ký tự khoảng trắng có thể thay đổi theo JDK.
5. Khi nào nên thay `fallbackPatterns` bằng custom `Formatter`/parser? Khi có nhiều quy tắc không thể biểu diễn an toàn bằng pattern cố định, cần nhận biết nguồn hoặc locale riêng, hay cần đo đạc/chặn mơ hồ bằng logic có kiểm soát.

## 9. Tài liệu tham khảo

- [Spring Framework — `@DateTimeFormat` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html): cú pháp `iso`, `pattern`, `style`, `fallbackPatterns`, ý nghĩa parse/print và timezone.
- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): cách annotation tham gia cơ chế `FormattingConversionService`.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService` và `TypeDescriptor`.
- [Spring Framework Wiki — Date and Time Formatting with JDK 20 and higher](https://github.com/spring-projects/spring-framework/wiki/Date-and-Time-Formatting-with-JDK-20-and-higher): thay đổi CLDR, ký tự khoảng trắng và khuyến nghị tương thích.

**Ghi nhớ:** thiết kế một format chính đáng tin cậy, dùng `fallbackPatterns` để nhận những format cũ được xác định rõ, kiểm tra dữ liệu không hợp lệ và không nhầm parse của Spring MVC với xử lý JSON của Jackson.