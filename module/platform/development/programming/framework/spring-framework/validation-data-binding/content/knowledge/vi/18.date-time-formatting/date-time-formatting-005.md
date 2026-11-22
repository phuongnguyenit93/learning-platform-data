# Cấu hình định dạng ngày giờ dùng chung trong Spring Framework

## 1. Bài toán và kết quả mong muốn

Một ứng dụng có nhiều controller, form và tham số URL chứa ngày, giờ. Nếu mỗi trường đều phải khai báo `@DateTimeFormat` riêng, định dạng dễ không đồng nhất: nơi nhận `2026-11-05`, nơi nhận `05/11/2026`, nơi nhận `11/05/2026`. Spring Framework cho phép **đăng ký formatter ngày/giờ tập trung** vào `FormatterRegistry` để áp dụng quy tắc parse và print mặc định cho các kiểu dữ liệu phù hợp.

Ví dụ, với quy tắc ISO nhất quán:

| Kiểu Java | Chuỗi đầu vào minh họa | Kết quả sau khi parse |
| --- | --- | --- |
| `LocalDate` | `2026-11-05` | Ngày 05/11/2026 |
| `LocalTime` | `14:30:45` | 14 giờ 30 phút 45 giây |
| `LocalDateTime` | `2026-11-05T14:30:45` | Ngày và giờ địa phương, chưa gắn múi giờ |
| `OffsetDateTime` | `2026-11-05T14:30:45+07:00` | Ngày giờ kèm độ lệch UTC +07:00 |

**Cấu hình dùng chung** là quy tắc mặc định trong **conversion service/formatter registry cụ thể** được cấu hình; không có nghĩa mọi nơi trong ứng dụng tự động sử dụng cùng một định dạng. Cần xác định nơi đăng ký và đường xử lý dữ liệu: Spring MVC, Spring WebFlux, các phép chuyển đổi thuần Java, dữ liệu JSON hay cấu hình `application.properties`.

Mục tiêu sau bài học:

1. Hiểu `Formatter` parse/print và quan hệ giữa `FormattingConversionService`, `FormatterRegistry`, `DateTimeFormatterRegistrar`.
2. Đăng ký định dạng ISO hoặc pattern tùy biến **một lần** cho Spring MVC.
3. Biết cách cấu hình nhanh bằng thuộc tính `spring.mvc.format.*` của Spring Boot khi phù hợp.
4. Phân biệt `java.time` với `java.util.Date`; global format với `@DateTimeFormat`; form/query với JSON.
5. Kiểm thử hành vi hợp lệ, sai định dạng, năm nhuận, locale và offset/múi giờ.

## 2. Spring áp dụng formatter ở đâu?

Đối với giá trị dạng văn bản ở biên ứng dụng, Spring cần hai chiều chuyển đổi:

~~~text
HTTP query / path variable / form field
              |
       chuỗi từ client
              |
       Formatter.parse(...)
              |
    LocalDate / LocalTime / ...
              |
    controller, bean property
              |
       Formatter.print(...)
              |
        chuỗi hiển thị
~~~

`Formatter<T>` gồm `Parser<T>` và `Printer<T>`. Nó nhận `Locale`, vì định dạng ngày/giờ dạng chữ (tên tháng, AM/PM...) có thể phụ thuộc ngôn ngữ/vùng. `FormattingConversionService` kết hợp formatter với hệ thống `Converter`, còn `FormatterRegistry` là giao diện đăng ký các quy tắc này. Đăng ký theo loại dữ liệu có thể tạo mặc định dùng chung; `@DateTimeFormat` gắn vào trường/tham số có thể chọn quy tắc riêng.

Các lớp thường dùng:

- `DateTimeFormatterRegistrar`, package `org.springframework.format.datetime.standard`: đăng ký formatter cho các loại `java.time`, chẳng hạn `LocalDate`, `LocalTime`, `LocalDateTime` và các loại có offset.
- `DateFormatterRegistrar`, package `org.springframework.format.datetime`: phục vụ kiểu cũ `Date`/`Calendar` và cấu hình `DateFormatter`; không thay cho registrar `java.time`.
- `WebMvcConfigurer.addFormatters(FormatterRegistry)`: đưa đăng ký vào hạ tầng binding/formatting **Spring MVC**.
- `WebFluxConfigurer.addFormatters(FormatterRegistry)`: điểm mở rộng tương ứng của **Spring WebFlux**.
- `DefaultFormattingConversionService`: thuận tiện khi cần dùng `ConversionService` riêng ngoài request MVC.

Một converter kiểu `String → LocalDate` có thể làm được việc parse nhưng `Formatter` tiện hơn khi cần cả chiều in ra String và xử lý theo `Locale`. Với bài toán ngày giờ, nên ưu tiên API formatter sẵn có thay vì tự lặp `LocalDate.parse(...)` trong nhiều controller.

## 3. Chọn chuẩn thống nhất trước khi cấu hình

Không có một định dạng văn bản nào tối ưu cho mọi giao diện. Hãy chọn theo loại dữ liệu và hợp đồng với client:

| Ngữ cảnh | Định dạng thường phù hợp | Lưu ý |
| --- | --- | --- |
| `<input type="date">` trong HTML | `yyyy-MM-dd` | Giá trị gửi đi theo quy cách HTML; cách trình duyệt *hiển thị* có thể tùy ngôn ngữ. |
| `<input type="time">` | `HH:mm` hoặc `HH:mm:ss` | Xác định có gửi giây không. |
| `<input type="datetime-local">` | `yyyy-MM-dd'T'HH:mm`, có thể có giây | Không mang offset hoặc tên vùng giờ. |
| Query/form nội bộ cần máy đọc ổn định | ISO-8601 | Tránh nhầm ngày/tháng theo vùng. |
| Form nhập tay cho người dùng Việt Nam | `dd/MM/yyyy` | Cần hướng dẫn và xác thực ngày không tồn tại. |
| Thời điểm giao dịch giữa các hệ thống | ISO-8601 có offset hoặc UTC | Dùng `OffsetDateTime`/`Instant` phù hợp, không coi `LocalDateTime` là một thời điểm toàn cầu. |

`LocalDate` chỉ có ngày; `LocalTime` chỉ có giờ; `LocalDateTime` là tổ hợp ngày và giờ *không mang timezone/offset*. `OffsetDateTime` có độ lệch so với UTC; `ZonedDateTime` có `ZoneId`. Hai chuỗi `2026-11-05T14:30:45` và `2026-11-05T14:30:45+07:00` có ý nghĩa khác nhau. Global formatter phải bảo toàn sự khác biệt này.

Nếu dùng biểu diễn thời điểm qua nhiều múi giờ, thường nên trao đổi chuỗi có offset hoặc UTC; việc chọn timezone hiển thị thuộc biên giao diện/ứng dụng. Không nên đưa `ZoneId.systemDefault()` vào mọi phép parse mà không có yêu cầu rõ ràng, vì mỗi server có thể đặt timezone khác nhau.

## 4. Cách khuyến nghị trong Spring MVC: đăng ký ISO một lần

Trong ứng dụng Spring MVC, viết một lớp cấu hình được component scan phát hiện:

~~~java
package demo.web;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class GlobalDateTimeWebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
~~~

Đây là **đoạn tích hợp Spring MVC**, cần `spring-webmvc` và ứng dụng web. Nó không phải chương trình Java có thể chạy độc lập bằng `java GlobalDateTimeWebConfig`.

Cơ chế:

1. Spring MVC khởi tạo conversion service dùng cho web binding.
2. `WebMvcConfigurer.addFormatters` cho phép bổ sung các formatter vào registry ấy.
3. `DateTimeFormatterRegistrar` đăng ký formatter `java.time` theo ISO.
4. Khi binding một tham số/người dùng gửi giá trị String cho thuộc tính `LocalDate`, `LocalTime` hoặc `LocalDateTime` tương ứng, Spring dùng cấu hình này nếu không có quy tắc cụ thể hơn của trường/tham số.

Không cần viết `@DateTimeFormat` trên mọi tham số khi tất cả cùng tuân thủ một quy ước. Spring MVC mặc định đã có nhiều formatter; mã trên chủ động đặt quy tắc ISO dùng chung cho nhóm ngày/giờ.

Ví dụ controller sử dụng định dạng mặc định:

~~~java
package demo.web;

import java.time.LocalDate;
import java.time.LocalTime;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ScheduleController {

    @GetMapping("/schedule")
    public String schedule(
            @RequestParam LocalDate date,
            @RequestParam LocalTime time) {
        return date + " " + time;
    }

    @GetMapping("/schedule/legacy-input")
    public String legacyInput(
            @RequestParam
            @DateTimeFormat(pattern = "dd/MM/yyyy") LocalDate date) {
        return date.toString();
    }
}
~~~

Đây cũng là **đoạn tích hợp** trong cùng ứng dụng MVC. Khi đã đăng ký ISO ở trên:

~~~http
GET /schedule?date=2026-11-05&time=14%3A30%3A45
~~~

Giá trị trả về trong response body là:

~~~text
2026-11-05 14:30:45
~~~

Endpoint thứ hai cho thấy ngoại lệ tại vị trí được chú thích:

~~~http
GET /schedule/legacy-input?date=05%2F11%2F2026
~~~

Body:

~~~text
2026-11-05
~~~

`@DateTimeFormat(pattern = "dd/MM/yyyy")` áp dụng riêng cho tham số đó, còn những vị trí không ghi chú tiếp tục theo global registry. Việc in `date.toString()` trong controller là kết quả của Java `LocalDate`, không phải minh chứng formatter global đã được dùng ở chiều print; muốn kiểm chứng chiều in, dùng `ConversionService.convert(value, String.class)` hoặc data binding/view thực sự.

Trong Spring Boot, thêm `WebMvcConfigurer` như trên thường giữ nguyên auto-configuration MVC. Tránh thêm `@EnableWebMvc` chỉ để cấu hình formatter, vì annotation này yêu cầu tự quản lý nhiều cấu hình MVC và có thể làm mất các tùy chỉnh tự động của Boot.

## 5. Chọn pattern tùy biến thay vì ISO

Nếu quy định giao diện yêu cầu nhập `05/11/2026` và `14:30:45`, dùng các setter của `DateTimeFormatterRegistrar`:

~~~java
package demo.web;

import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CustomDateTimeWebConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar = new DateTimeFormatterRegistrar();

        registrar.setDateFormatter(
            DateTimeFormatter.ofPattern("dd/MM/uuuu")
                .withResolverStyle(ResolverStyle.STRICT));

        registrar.setTimeFormatter(
            DateTimeFormatter.ofPattern("HH:mm:ss")
                .withResolverStyle(ResolverStyle.STRICT));

        registrar.setDateTimeFormatter(
            DateTimeFormatter.ofPattern("dd/MM/uuuu HH:mm:ss")
                .withResolverStyle(ResolverStyle.STRICT));

        registrar.registerFormatters(registry);
    }
}
~~~

**Dùng một trong hai lớp cấu hình `GlobalDateTimeWebConfig` hoặc `CustomDateTimeWebConfig`** như chính sách chung cho nhóm kiểu trên. Tránh đồng thời đăng ký hai bộ quy tắc trùng đối tượng đích rồi dựa vào thứ tự ngầm định.

Giải thích:

- `setDateFormatter(...)` ảnh hưởng định dạng cho `LocalDate`.
- `setTimeFormatter(...)` áp dụng cho `LocalTime` **và `OffsetTime`**.
- `setDateTimeFormatter(...)` áp dụng cho `LocalDateTime`, `OffsetDateTime` và `ZonedDateTime`.
- Một setter formatter rõ ràng có ưu tiên hơn cờ `setUseIsoFormat(true)` hay style mặc định đối với nhóm kiểu tương ứng. Vì vậy không nên trộn chúng mà không xác định trường hợp cụ thể.
- `ResolverStyle.STRICT` giúp từ chối lịch không hợp lệ. Trong `DateTimeFormatter`, `uuuu` là proleptic year, phù hợp với parse strict của ngày ISO hiện đại; `yyyy` biểu diễn year-of-era và có thể cần thông tin era trong strict mode.

**Cảnh báo quan trọng về offset:** Các pattern `HH:mm:ss` và `dd/MM/uuuu HH:mm:ss` **không chứa offset**. Chúng phù hợp với `LocalTime` và `LocalDateTime` nhưng có thể gây lỗi parse `OffsetTime`/`OffsetDateTime`/`ZonedDateTime` vì thiếu thông tin offset/vùng giờ bắt buộc. Nếu ứng dụng sử dụng các kiểu đó, ưu tiên ISO có offset hoặc đăng ký chính sách phù hợp theo từng kiểu; không mặc định pattern local đủ cho mọi temporal type.

Nếu cần yêu cầu nghiêm ngặt “client chỉ gửi ISO” mà không có ngoại lệ, cấu hình `setUseIsoFormat(true)` ở mục 4 thường rõ ràng, an toàn hơn và phù hợp với các input chuẩn HTML.

## 6. Spring Boot: cấu hình chung bằng application.properties

Với Spring Boot MVC, có thể khai báo định dạng mặc định mà không phải viết class cấu hình Java:

~~~properties
# application.properties
spring.mvc.format.date=dd/MM/yyyy
spring.mvc.format.time=HH:mm:ss
spring.mvc.format.date-time=yyyy-MM-dd HH:mm:ss
~~~

Hoặc trong `application.yml`:

~~~yaml
spring:
  mvc:
    format:
      date: "dd/MM/yyyy"
      time: "HH:mm:ss"
      date-time: "yyyy-MM-dd HH:mm:ss"
~~~

Các thuộc tính là **định dạng phục vụ Spring MVC**:

| Property | Nhóm kiểu điển hình |
| --- | --- |
| `spring.mvc.format.date` | `java.util.Date` và `LocalDate` |
| `spring.mvc.format.time` | `LocalTime` và `OffsetTime` |
| `spring.mvc.format.date-time` | `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime` |

Trong file properties trên, `date-time` được chọn cho dữ liệu ngày giờ **không có offset**, nên không đủ cho các kiểu offset/zoned khi parse một chuỗi timestamp tương ứng; cần thiết kế riêng nếu có dùng chúng. Với API trao đổi có timezone, một quy tắc ISO rõ ràng sẽ thuận tiện hơn.

Tại sao ví dụ Boot dùng `yyyy`, còn mã `DateTimeFormatter` strict ở trên dùng `uuuu`? Thuộc tính `spring.mvc.format.date` còn phục vụ `java.util.Date` theo cơ chế `java.text`, nơi `yyyy` là năm thông thường; còn `DateTimeFormatter` và `ResolverStyle.STRICT` có ngữ nghĩa khác như mục 5. **Không thay hàng loạt `yyyy` bằng `uuuu` trong mọi bộ parser**, vì `SimpleDateFormat` có ký hiệu khác cho `u`.

Cấu hình properties là lựa chọn nhanh khi một bộ pattern đủ dùng và ứng dụng đã sử dụng auto-configuration của Spring Boot. `WebMvcConfigurer` phù hợp hơn khi cần `DateTimeFormatter` đặc biệt, `ResolverStyle`, quy tắc tùy theo loại hoặc formatter tự viết. Nếu vừa khai báo properties vừa đăng ký formatter trùng loại, hãy kiểm thử quy tắc có hiệu lực thay vì giả định một ưu tiên chung cho mọi phiên bản/cấu hình.

**Phân biệt conversion service:** Spring MVC có conversion service riêng, không nhất thiết là service dùng để đọc và bind `application.properties`/`@ConfigurationProperties`. Vì vậy chỉnh `spring.mvc.format.*` không đồng nghĩa thay đổi cách Spring Boot parse mọi giá trị cấu hình môi trường.

## 7. Java 17+ runnable: một formatting service dùng chung

Ta có thể kiểm chứng chính xác parse/print bằng một chương trình Spring Core nhỏ **không cần web server**. Ví dụ dùng **Java 17** và **Spring Framework 6.2.19**; hoạt động độc lập với phần MVC ở các mục trước.

Cấu trúc:

~~~text
global-date-time/
├── pom.xml
└── src/
    ├── main/java/demo/GlobalDateTimeDemo.java
    └── test/java/demo/GlobalDateTimeDemoTest.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>global-date-time</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/GlobalDateTimeDemo.java`:

~~~java
package demo;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;

import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.format.support.FormattingConversionService;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;

public class GlobalDateTimeDemo {

    static FormattingConversionService buildService() {
        // Không nạp các formatter mặc định:
        // chủ động đăng ký chính sách định dạng ISO dùng chung.
        var service = new DefaultFormattingConversionService(false);

        var registrar = new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(service);
        return service;
    }

    public static void main(String[] args) {
        var conversionService = buildService();

        LocalDate date =
            conversionService.convert("2026-11-05", LocalDate.class);
        LocalTime time =
            conversionService.convert("14:30:45", LocalTime.class);
        LocalDateTime dateTime =
            conversionService.convert(
                "2026-11-05T14:30:45", LocalDateTime.class);

        System.out.println("date=" + date);
        System.out.println("time=" + time);
        System.out.println("dateTime=" + dateTime);

        String printed =
            conversionService.convert(dateTime, String.class);
        System.out.println("printed=" + printed);
    }
}
~~~

Chạy tại thư mục chứa `pom.xml` (cần JDK 17+, Maven, quyền tải dependency lần đầu):

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.GlobalDateTimeDemo
~~~

Stdout do chương trình tạo ra (không tính thông điệp riêng của Maven nếu có):

~~~text
date=2026-11-05
time=14:30:45
dateTime=2026-11-05T14:30:45
printed=2026-11-05T14:30:45
~~~

Giải thích:

1. `DefaultFormattingConversionService(false)` không tự đăng ký các **default formatter**; chúng ta thêm registrar ISO có chủ đích. Nó vẫn có hệ thống converter nền cần thiết.
2. `convert(String, LocalDate.class)`/`convert(String, LocalTime.class)`/`convert(String, LocalDateTime.class)` kiểm tra chiều parse.
3. `convert(dateTime, String.class)` kiểm tra chiều print, vốn khác với gọi `dateTime.toString()` trực tiếp.
4. Không cần khai báo pattern trong từng lời gọi. Tất cả dùng chung một service đã đăng ký.
5. Cấu hình service như vậy **chỉ ảnh hưởng các phép chuyển đổi đi qua chính service đó**. Đừng mặc định một bean tùy ý trong Spring Core sẽ tự thay thế service của Spring MVC.

Với trường hợp dùng service như một Spring bean để định dạng cả hệ thống core (ngoài web), có thể khai báo `@Bean FormattingConversionService` trong `@Configuration`; kiểm tra các thành phần thật sự được inject service đó. Nếu thay default formatters bằng `false` trong một ứng dụng lớn, cần đăng ký lại các formatter mặc định khác vẫn cần, chẳng hạn xử lý `@NumberFormat`. Spring MVC đã có cơ chế riêng để mở rộng cấu hình nên không cần tự thay toàn bộ service chỉ cho bài toán này.

## 8. Kiểm thử parse, print và dữ liệu sai

Đặt tệp `src/test/java/demo/GlobalDateTimeDemoTest.java`:

~~~java
package demo;

import java.time.LocalDate;
import java.time.LocalDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;

import static org.junit.jupiter.api.Assertions.*;

class GlobalDateTimeDemoTest {

    @Test
    void parsesAndPrintsDateWithGlobalIsoFormat() {
        var service = GlobalDateTimeDemo.buildService();

        LocalDate date = service.convert("2026-11-05", LocalDate.class);

        assertEquals(LocalDate.of(2026, 11, 5), date);
        assertEquals("2026-11-05", service.convert(date, String.class));
    }

    @Test
    void parsesDateTimeWithTimeSeparatorT() {
        var service = GlobalDateTimeDemo.buildService();

        var result =
            service.convert("2026-11-05T14:30:45", LocalDateTime.class);

        assertEquals(LocalDateTime.of(2026, 11, 5, 14, 30, 45),
                     result);
    }

    @Test
    void rejectsImpossibleCalendarDate() {
        var service = GlobalDateTimeDemo.buildService();

        assertThrows(
            ConversionFailedException.class,
            () -> service.convert("2026-02-30", LocalDate.class)
        );
    }

    @Test
    void rejectsWrongDateSyntax() {
        var service = GlobalDateTimeDemo.buildService();

        assertThrows(
            ConversionFailedException.class,
            () -> service.convert("05/11/2026", LocalDate.class)
        );
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Maven Surefire phải báo **4 test được thực thi, 0 lỗi/0 thất bại** khi cấu hình và dependencies hoạt động đúng. Đây là các kiểm thử tích hợp mức `FormattingConversionService`: một bộ formatter giống cơ chế dùng trong Spring được đăng ký vào service, còn kiểm thử HTTP thực tế nên có thêm test controller/MockMvc trong ứng dụng MVC.

Không viết test chỉ xác nhận `LocalDate.parse("2026-11-05")` rồi kết luận cấu hình Spring đúng: đoạn test như thế bỏ qua formatter registry, dù Java parse thành công.

Nếu thay chính sách từ ISO sang `dd/MM/yyyy`, phải đổi đồng thời dữ liệu kiểm thử, expected output, API consumers và tài liệu hợp đồng. Các lỗi “ngày hợp lệ nhưng sai format” và “định dạng đúng nhưng ngày lịch không tồn tại” đều cần được kiểm tra.

## 9. Cấu hình cho kiểu cũ java.util.Date và Calendar

`DateTimeFormatterRegistrar` dùng `java.time`. Nếu dự án vẫn có `java.util.Date`/`Calendar`, cần xét `DateFormatterRegistrar` riêng.

Ví dụ chỉ minh họa phần thêm vào `addFormatters`, cùng các import tương ứng:

~~~java
import java.util.TimeZone;

import org.springframework.format.datetime.DateFormatter;
import org.springframework.format.datetime.DateFormatterRegistrar;

// Bên trong addFormatters(FormatterRegistry registry):
DateFormatter dateFormatter = new DateFormatter("dd/MM/yyyy");
dateFormatter.setLenient(false);
dateFormatter.setTimeZone(TimeZone.getTimeZone("Asia/Ho_Chi_Minh"));

DateFormatterRegistrar legacyRegistrar = new DateFormatterRegistrar();
legacyRegistrar.setFormatter(dateFormatter);
legacyRegistrar.registerFormatters(registry);
~~~

`setFormatter` là bước quan trọng: nếu không đặt formatter cụ thể, registrar không thêm global formatter cho các trường `Date`/`Calendar` không có annotation. Đăng ký này không làm thay đổi cấu hình `LocalDate` ở `DateTimeFormatterRegistrar`.

Lưu ý `Date` biểu diễn một **instant/timestamp**, còn biểu diễn ngày/tháng khi parse/print phụ thuộc timezone. `LocalDate` chỉ biểu diễn ngày lịch, không phụ thuộc timezone theo cách tương tự. Khi chuyển giữa chúng, phải xác định quy tắc vùng giờ, tránh trường hợp “lệch một ngày” do hệ thống chạy ở timezone khác.

Dự án mới thường dễ bảo trì hơn với các kiểu `java.time` như `LocalDate`, `LocalDateTime` và `Instant`. Chỉ dùng formatter legacy khi thực sự có thuộc tính kiểu cũ cần tương thích.

## 10. Phạm vi tác động: Form, URL, JSON và cấu hình ứng dụng

Một lỗi triển khai phổ biến là định nghĩa “global” quá rộng. Cùng một thời gian đi qua các tầng khác nhau:

| Luồng dữ liệu | Cơ chế chính | Cấu hình phù hợp |
| --- | --- | --- |
| `@RequestParam LocalDate` | Spring MVC argument binding | `WebMvcConfigurer.addFormatters` hoặc `spring.mvc.format.date` |
| `@PathVariable LocalDate` | Spring MVC type conversion | MVC formatter registry; lưu ý encoding URL |
| `@ModelAttribute` chứa ngày | `WebDataBinder` / conversion/formatting | MVC registry và/hoặc `@DateTimeFormat` trên field |
| HTML form input | Giá trị theo quy định của trình duyệt, qua binder | Phối hợp format gửi lên với formatter MVC |
| `@RequestBody` JSON | Jackson hoặc JSON codec/message converter | Cấu hình serializer/deserializer, `@JsonFormat` hoặc Jackson modules |
| `@ResponseBody` trả object JSON | Jackson hoặc codec JSON | Cấu hình serialization JSON |
| `@ConfigurationProperties` | Spring Boot application property binding | Application conversion service, không mặc định dùng MVC registry |
| Logic thuần Java gọi `ConversionService` | Conversion service được inject/khởi tạo | Đăng ký formatter vào chính instance đó |
| Spring WebFlux web binding | WebFlux formatter registry | `WebFluxConfigurer.addFormatters` |

**Global formatter của Spring MVC không tự đổi định dạng JSON.** Ví dụ:

~~~java
record Appointment(LocalDate date, LocalDateTime startAt) {}
~~~

Nếu controller trả `Appointment` dưới dạng JSON, việc JSON chứa `"2026-11-05"` và `"2026-11-05T14:30:45"` hay một biểu diễn khác được quyết định bởi Jackson/module/cấu hình JSON tương ứng, không phải chỉ bởi `DateTimeFormatterRegistrar` trong MVC.

Tương tự, annotation Jackson:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

record DatePayload(
    @JsonFormat(pattern = "dd/MM/yyyy") LocalDate date) {}
~~~

Đây là đoạn minh họa cho JSON với dependency Jackson, **không phải chương trình độc lập**. `@JsonFormat` giải quyết serialization/deserialization JSON tại loại/thuộc tính áp dụng; `@DateTimeFormat` giải quyết Spring field formatting và type conversion.

Trong ứng dụng dùng cả query parameter và JSON, nên viết test **hai đường** để chắc chắn mỗi nơi dùng đúng chuẩn đã công bố.

## 11. @DateTimeFormat là ngoại lệ cục bộ, không phải thay toàn bộ global

Giả sử phần lớn form dùng ISO; một màn hình nhập tay cần `dd/MM/yyyy`. Cách giải quyết là giữ global ISO và chỉ đặt annotation nơi cần:

~~~java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class SearchForm {
    @DateTimeFormat(pattern = "dd/MM/yyyy")
    private LocalDate fromDate;

    public LocalDate getFromDate() {
        return fromDate;
    }

    public void setFromDate(LocalDate fromDate) {
        this.fromDate = fromDate;
    }
}
~~~

Đây là một bean dùng cho MVC binding, không phải chương trình độc lập. Tại `fromDate`, `@DateTimeFormat` khai báo cách parse/print của chính field; các field không có annotation vẫn đi theo quy tắc global áp dụng với type của chúng.

Có ba cách phổ biến viết annotation:

- `@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)`: dùng chuẩn ISO ngày.
- `@DateTimeFormat(pattern = "dd/MM/yyyy")`: pattern được xác định cụ thể ở field.
- `@DateTimeFormat(style = "S-")`: style ngắn, phụ thuộc locale/JDK và phù hợp hơn cho giao diện có yêu cầu địa phương hóa.

Cần tránh giả định rằng style mặc định giống nhau trên mọi phiên bản JDK/locale. Spring Framework lưu ý định dạng theo style có thể thay đổi theo Java runtime (đặc biệt từ JDK 20), nên với giao thức máy đọc, ưu tiên ISO hoặc pattern cụ thể. Annotation cũng hỗ trợ `fallbackPatterns` khi có nhu cầu tương thích các định dạng đầu vào cũ; fallback dùng cho **parsing**, còn printing vẫn dùng format chính.

Đặt annotation có chủ đích để xử lý ngoại lệ; không đặt `@DateTimeFormat` cho mọi trường chỉ vì chưa có cấu hình chung.

## 12. Locale, timezone và độ chính xác của định dạng

### Locale không đồng nghĩa timezone

`Locale` xác định ngôn ngữ/vùng cho nhiều mẫu hiển thị, ví dụ tên tháng hoặc thứ; `TimeZone`/`ZoneId` xác định quan hệ giữa thời điểm và đồng hồ tại một vùng. Hai khái niệm khác nhau. Có thể dùng `Locale.forLanguageTag("vi-VN")` nhưng chọn timezone `UTC`; locale không tự đổi dữ liệu sang UTC+7.

`DateTimeFormatter.ofPattern("dd/MM/uuuu")` sử dụng ký hiệu số cố định nên chuỗi ít lệ thuộc locale; formatter kiểu `ofLocalizedDate(FormatStyle.SHORT)` có thể biểu diễn khác nhau giữa locale và thay đổi theo dữ liệu locale của runtime.

Với `Instant`, `OffsetDateTime` hoặc `ZonedDateTime`, muốn hiển thị một thời điểm theo giờ Việt Nam thì phải xác định zone, chẳng hạn:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

Instant instant = Instant.parse("2026-11-05T07:30:45Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

String display = DateTimeFormatter
        .ofPattern("dd/MM/uuuu HH:mm:ss")
        .withZone(zone)
        .format(instant);

// display = "05/11/2026 14:30:45"
~~~

Đoạn này có thể đặt trong phương thức Java và chạy với JDK 17 (các `import` đã nêu); nó minh họa **chuyển thời điểm theo zone**. Cấu hình pattern chỉ có `dd/MM/uuuu` trên `LocalDate` không thể thay thế xử lý timezone đối với instant.

### Dùng ký hiệu pattern đúng

| Ký hiệu | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `dd` | Ngày trong tháng (2 chữ số) | Không phải “ngày của tuần”. |
| `MM` | Tháng (2 chữ số) | `mm` là phút, không phải tháng. |
| `uuuu` | Năm proleptic trong `java.time` | Hữu ích khi parse strict bằng `DateTimeFormatter`. |
| `yyyy` | Năm theo era trong `DateTimeFormatter`; năm thông thường trong `SimpleDateFormat` | Chọn theo engine và resolver style thực tế. |
| `HH` | Giờ 0–23 | `hh` là giờ 1–12, thường cần AM/PM. |
| `mm` | Phút | Không đổi nhầm với `MM`. |
| `ss` | Giây | Cần thống nhất có bắt buộc giây hay không. |
| `XXX` | Offset dạng `+07:00` | Dùng khi pattern có yêu cầu lưu offset. |
| `'T'` | Chữ T cố định giữa ngày và giờ | Ví dụ `yyyy-MM-dd'T'HH:mm:ss`; dấu nháy trong pattern là ký tự literal. |

Một lỗi thường gặp: dùng `YYYY` thay `yyyy`/`uuuu`. `YYYY` là tuần-năm (week-based year); gần cuối/năm mới, nó có thể khác năm lịch và gây sai dữ liệu.

### Không biến “giờ không timezone” thành thời điểm tuyệt đối

Nhập `2026-11-05 14:30:45` vào `LocalDateTime` chỉ có nghĩa một thời gian trên đồng hồ địa phương. Muốn suy ra instant phải biết `ZoneId`, và tại vùng có daylight saving time cần xử lý giờ không tồn tại hoặc lặp lại. Cấu hình chung nên công bố rõ kiểu dữ liệu đích, vùng giờ và cách trao đổi.

## 13. Dữ liệu lỗi và validation

Formatter chịu trách nhiệm **chuỗi có parse được thành kiểu đích không**. Validation chịu trách nhiệm **giá trị đã parse có đáp ứng quy tắc nghiệp vụ không**.

Ví dụ:

1. `"2026-11-05"` parse thành `LocalDate` thành công theo ISO.
2. `"05/11/2026"` sai cú pháp ISO; conversion thất bại nếu không có quy tắc riêng.
3. `"2026-02-30"` trông giống ISO nhưng là ngày không tồn tại; parse strict thất bại.
4. `"2026-11-05"` có thể hợp lệ về kiểu nhưng không được phép đặt lịch trong quá khứ; quy tắc này thuộc validation/business logic.
5. Giá trị **thiếu** hay **trống** phụ thuộc request binding/required/validation; không thể suy ra chỉ từ một formatter rằng mọi chuỗi trống đều phải trở thành giá trị mặc định.

Trong controller có thể dùng Bean Validation, ví dụ `@FutureOrPresent` trên `LocalDate` trong DTO phù hợp. Khi parse lỗi, Spring MVC có thể tạo lỗi binding/argument conversion trước khi validation nghiệp vụ chạy; HTTP status và response body thực tế còn phụ thuộc handler và exception handling được cấu hình.

Không dùng giá trị mặc định như ngày hiện tại mỗi khi parse lỗi trừ khi nghiệp vụ thật sự yêu cầu; cách này dễ che dữ liệu đầu vào sai và gây thay đổi hành vi không thể truy vết.

## 14. HTML form: vì sao global dd/MM/yyyy đôi khi không hoạt động?

Giả sử trình duyệt hiển thị bộ chọn ngày theo tiếng Việt. Người dùng thấy `05/11/2026`, nhưng HTML chuẩn:

~~~html
<input type="date" name="date">
~~~

gửi **giá trị ngày theo `yyyy-MM-dd`**, ví dụ `date=2026-11-05`. Trình duyệt hiển thị một kiểu và submit một kiểu khác là bình thường. Nếu Spring MVC bị cấu hình chỉ parse `dd/MM/yyyy`, form HTML chuẩn có thể bị lỗi binding.

Tương tự:

~~~html
<input type="datetime-local" name="startsAt">
~~~

giá trị gửi thường chứa dấu `T`, ví dụ `2026-11-05T14:30`, và **không có offset**. Một custom pattern mong chờ dấu cách (`dd/MM/yyyy HH:mm:ss`) sẽ không khớp. Cũng cần thống nhất việc giá trị thiếu giây có được chấp nhận hay không.

Cách xử lý:

- Với các điều khiển `type=date`, `type=time`, `type=datetime-local`, ưu tiên ISO phù hợp với HTML.
- Nếu muốn hiển thị `dd/MM/yyyy`, có thể định dạng riêng ở nhãn/view hoặc dùng input văn bản có hướng dẫn rõ ràng.
- Nếu API phải nhận nhiều định dạng cũ, quyết định chính sách tương thích ở biên (annotation `fallbackPatterns` hoặc parser/formatter cụ thể), không âm thầm đổi global cho toàn bộ app.
- Kiểm thử một request thật của trình duyệt; đừng chỉ đoán từ cách ô input được render.

## 15. Nếu ứng dụng dùng Spring WebFlux

Thay điểm đăng ký của Spring MVC bằng `WebFluxConfigurer`:

~~~java
package demo.webflux;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.datetime.standard.DateTimeFormatterRegistrar;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class DateTimeWebFluxConfig implements WebFluxConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        var registrar = new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
~~~

Đoạn này cần dependency Spring WebFlux, là **cấu hình tích hợp** thay thế cho `WebMvcConfigurer` ở ứng dụng reactive; không đăng ký cả hai với kỳ vọng cùng một registry. Các tham số query/path/form của WebFlux và JSON codec vẫn là những cơ chế khác nhau.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Khai báo `@DateTimeFormat` ở mọi controller, mỗi nơi một kiểu | Hợp đồng định dạng phân tán, khó thay đổi | Chọn global phù hợp rồi chỉ annotate ngoại lệ. |
| Đăng ký formatter ở `ConversionService` khác service dùng cho Spring MVC | Controller không nhận quy tắc mong đợi | Cấu hình qua `WebMvcConfigurer.addFormatters` và kiểm thử request. |
| Nghĩ `spring.mvc.format.*` cũng áp dụng cho JSON | JSON phản hồi không theo pattern được khai báo | Cấu hình Jackson/JSON codec riêng. |
| Dùng `dd/MM/yyyy` làm format bắt buộc cho `<input type=date>` | Trình duyệt gửi `yyyy-MM-dd`, parse lỗi | Đặt ISO cho HTML date field hoặc điều chỉnh ranh giới phù hợp. |
| Dùng `LocalDateTime` thay cho thời điểm tuyệt đối | Lẫn giờ theo timezone, dữ liệu giữa vùng sai | Dùng `Instant`/`OffsetDateTime` hoặc thêm chính sách `ZoneId`. |
| Pattern local không có offset nhưng nhận `OffsetDateTime` | Thiếu thông tin để tạo giá trị đích | Dùng ISO có offset hoặc pattern có offset. |
| Nhầm `MM` với `mm` | Tháng/phút sai | Review và test pattern với giá trị phân biệt được. |
| Nhầm `YYYY` với năm lịch | Sai năm tại biên tuần-năm | Dùng `uuuu` hoặc `yyyy` phù hợp engine. |
| Trộn `yyyy`/`uuuu` vô điều kiện ở java.time và java.text | Parse strict hoặc formatter legacy cho kết quả không mong muốn | Hiểu cú pháp từng formatter và viết test. |
| Dùng style dựa locale làm hợp đồng API dài hạn | Khác output theo locale/JDK | Dùng ISO hoặc pattern cố định cho giao thức máy. |
| Chỉ test chiều parse | Giao diện in ra format khác đầu vào | Test cả `String → T` và `T → String`. |
| Đăng ký nhiều formatter cùng kiểu mà không kiểm soát thứ tự | Hành vi phụ thuộc thứ tự đăng ký | Quy định một nguồn cấu hình và kiểm chứng thực tế. |
| Ném lỗi parse rồi tự đổi sang ngày hiện tại | Che lỗi dữ liệu người dùng | Báo lỗi binding rõ ràng, giữ nguyên semantics. |
| Thêm `@EnableWebMvc` vào Boot chỉ để có formatter | Thay đổi cách MVC auto-config hoạt động | Dùng `WebMvcConfigurer` hoặc properties. |

## 17. Checklist triển khai

1. Liệt kê các trường `LocalDate`, `LocalTime`, `LocalDateTime` và kiểu có offset đang nhận ở biên web.
2. Chốt **chuẩn chuỗi** cho từng loại (ISO hay pattern nghiệp vụ) và xác định form HTML, query API, JSON có cùng chuẩn hay không.
3. Chọn cách cấu hình: `spring.mvc.format.*` (Boot MVC đơn giản) hoặc `WebMvcConfigurer.addFormatters` (cần registrar tùy biến).
4. Nếu dùng legacy `Date`/`Calendar`, kiểm tra `DateFormatterRegistrar` và chính sách timezone riêng.
5. Giữ `@DateTimeFormat` ở những trường thực sự cần ngoại lệ; kiểm tra tương tác với formatter chung.
6. Viết test cả parse và print; tối thiểu có ngày hợp lệ, ngày sai, sai cú pháp, ngày nhuận, giá trị có offset và request từ trình duyệt.
7. Kiểm tra test riêng cho JSON và configuration properties nếu dự án dùng chúng.
8. Kiểm tra timezone của server, hợp đồng UTC/offset và locale thực tế của người dùng.
9. Tài liệu hóa các pattern được công bố; thay đổi pattern ở một registry có thể là breaking change cho client.

**Tự kiểm tra:** (a) Vì sao `@RequestParam LocalDate` có thể theo global ISO mà JSON `@RequestBody` vẫn dùng cấu hình Jackson riêng? (b) Khi `<input type=date>` hiển thị ngày theo tiếng Việt, nó gửi `dd/MM/yyyy` hay `yyyy-MM-dd`? (c) Vì sao `LocalDateTime` không đủ để chỉ ra một instant? (d) Muốn formatter dùng chung chỉ cho MVC thì nên cấu hình ở đâu? Đáp án lần lượt: đây là hai pipeline conversion/serialization khác nhau; HTML date submit theo `yyyy-MM-dd`; `LocalDateTime` không có offset/zone; đăng ký vào MVC qua `WebMvcConfigurer.addFormatters` hoặc dùng thuộc tính `spring.mvc.format.*`.

## 18. Tài liệu chính thức

- Spring Framework, *Spring Field Formatting*: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework 6.2, *Configuring a Global Date and Time Format*: https://docs.spring.io/spring-framework/reference/6.2/core/validation/format-configuring-formatting-globaldatetimeformat.html
- Spring Framework, *Spring MVC Type Conversion*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Spring Boot, *Servlet Web Applications — Spring MVC Conversion Service*: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Framework, *WebFlux Config*: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Javadoc `DateTimeFormatterRegistrar`: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/format/datetime/standard/DateTimeFormatterRegistrar.html
- Javadoc `DateFormatterRegistrar`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/datetime/DateFormatterRegistrar.html
- Javadoc `@DateTimeFormat`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html
