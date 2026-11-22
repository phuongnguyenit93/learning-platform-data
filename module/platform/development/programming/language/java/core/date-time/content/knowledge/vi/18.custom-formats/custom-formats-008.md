# Tái sử dụng formatter bất biến và cấu hình `Locale` hoặc `ZoneId` tường minh

## 1. Bộ định dạng là một cấu hình có thể dùng lại

Một dịch vụ có thể xuất hàng nghìn ngày giờ theo cùng quy tắc. Nếu quy tắc là cố định, không cần xây lại `DateTimeFormatter` cho từng giá trị. Có thể tạo một bộ định dạng dùng chung, rồi gọi `format()` hoặc `parse()` nhiều lần với các dữ liệu khác nhau.

Điều khiến cách dùng này phù hợp là `DateTimeFormatter` **bất biến** và **an toàn khi dùng giữa nhiều luồng**, theo [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html). Những phương thức như `withLocale()` và `withZone()` trả về cấu hình kết quả; chúng không sửa formatter ban đầu.

Tuy nhiên, an toàn khi dùng chung chưa đồng nghĩa với đúng ý nghĩa dữ liệu. Nếu một nơi cần ngôn ngữ tiếng Anh và vùng UTC, còn nơi khác cần ngôn ngữ khác hoặc vùng của người dùng, phải phân biệt các cấu hình đó. Hai tham số cần đọc rõ là:

- `Locale`: quy ước ngôn ngữ/vùng cho những phần có tính địa phương, chẳng hạn tên tháng.
- `ZoneId`: vùng thời gian để diễn giải hoặc hiển thị một thời điểm khi cấu hình và kiểu dữ liệu yêu cầu.

Không suy ra vùng thời gian từ ngôn ngữ. Người chọn tiếng Anh có thể đang ở Việt Nam; tên tháng tiếng Pháp cũng không có nghĩa dữ liệu bắt buộc thuộc giờ Paris.

## 2. Bất biến thay đổi cách tổ chức mã như thế nào?

Với cấu hình ổn định của ứng dụng, có thể đặt formatter trong một trường `static final`, hoặc một trường `final` của đối tượng dịch vụ được khởi tạo bằng cấu hình đã biết. Phương thức xử lý chỉ dùng bộ định dạng, không thay đổi nó.

Ví dụ minh họa trong thân một lớp:

```java
private static final DateTimeFormatter EXPORT_DATE = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT);
```

`final` ngăn việc gán lại trường tham chiếu; tính bất biến của chính `DateTimeFormatter` mới bảo đảm nội dung cấu hình không bị sửa khi một luồng khác gọi phương thức trên nó. Không cần thêm `synchronized` hoặc tạo `ThreadLocal<DateTimeFormatter>` chỉ để dùng chung formatter này.

Ngược lại, `DateTimeFormatterBuilder` đang xây quy tắc là đối tượng có thể thay đổi và dùng trong một luồng, như mô tả tại [Java SE 21 — DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html). Nếu cần builder, hãy dùng nó lúc khởi tạo, lấy `DateTimeFormatter` kết quả rồi chia sẻ kết quả ấy.

Một cấu hình khác có thể được tạo từ cấu hình nền:

```java
DateTimeFormatter french = EXPORT_DATE.withLocale(Locale.FRENCH);
```

Câu lệnh không đổi `EXPORT_DATE`. Nếu chỉ gọi `EXPORT_DATE.withLocale(...)` rồi bỏ kết quả, các lần dùng `EXPORT_DATE` sau đó vẫn giữ cấu hình cũ. Với mẫu chỉ có trường số như trên, đổi Locale còn có thể không tạo khác biệt dễ nhìn; ví dụ đầy đủ bên dưới dùng tên tháng để quan sát rõ hơn.

## 3. `Locale`: chọn quy ước ngôn ngữ thay vì phụ thuộc môi trường

Với `ofPattern(pattern)` không truyền Locale, thư viện dùng Locale mặc định thuộc nhóm `FORMAT` tại thời điểm tạo formatter. Một hằng `static final` được tạo theo mặc định đó không trở thành chính sách ngôn ngữ rõ ràng chỉ vì nó được dùng lại.

Nếu hợp đồng xuất dùng tên tháng tiếng Anh, hãy viết `ofPattern(pattern, Locale.ENGLISH)`. Nếu là dạng trao đổi trung lập với các trường số đã xác định, `Locale.ROOT` là lựa chọn thể hiện ý định rõ ràng. Với giao diện người dùng, Locale có thể đến từ tùy chọn ngôn ngữ/vùng của người đó.

Cần phân biệt hai kiểu cấu hình:

| Cách tạo | Điều được quyết định |
| --- | --- |
| `ofPattern("dd MMM uuuu", locale)` | Giữ thứ tự ngày–tháng–năm của mẫu; tên tháng phụ thuộc Locale |
| `ofLocalizedDate(style).withLocale(locale)` | Cho phép phong cách địa phương quyết định mẫu hiển thị phù hợp |

Đổi Locale không tự sắp xếp lại các trường của một mẫu đã viết cố định, cũng không dịch các đoạn chữ cố định được đặt trong mẫu. Nếu dùng các chữ số hoặc dấu thập phân theo quy tắc riêng, còn có `DecimalStyle`; không nên coi `withLocale()` là lệnh thay mọi khía cạnh của dữ liệu.

Tên tháng và cách hiển thị địa phương dựa trên dữ liệu ngôn ngữ của runtime. Với một định dạng trao đổi cần ổn định chặt chẽ giữa hệ thống, ưu tiên quy ước chuẩn hoặc mẫu số cụ thể thay vì phụ thuộc vào văn bản địa phương.

## 4. `ZoneId`: cùng một thời điểm có thể hiển thị khác nhau

Một `Instant` biểu diễn thời điểm trên dòng thời gian; nó không tự mang giờ địa phương để điền vào các trường như ngày, giờ, phút của mẫu. Khi bộ định dạng có `withZone(zone)`, nó có ngữ cảnh để biểu diễn thời điểm đó theo vùng đã chọn.

Với thời điểm `2025-06-10T02:00:00Z`:

```text
UTC                  → 2025-06-10 02:00
Asia/Ho_Chi_Minh      → 2025-06-10 09:00
```

Đó vẫn là một thời điểm; formatter chỉ tạo cách nhìn theo vùng. Nó không sửa `Instant` gốc. Khi cần xuất ngày giờ cho báo cáo, phải xác định vùng của báo cáo trước khi định dạng, vì ở gần ranh giới ngày, hai vùng còn có thể cho hai ngày lịch khác nhau.

`ofPattern()` tự nó không gắn vùng mặc định. Nếu muốn vùng máy đang chạy, phải lựa chọn `ZoneId.systemDefault()` có chủ đích. Nếu ứng dụng có vùng nghiệp vụ cố định, hãy cấu hình mã vùng đó; nếu vùng do người dùng chọn, truyền lựa chọn đó vào điểm hiển thị. Không lấy ngầm cấu hình máy chủ để đại diện cho mọi người dùng.

## 5. Chương trình kiểm chứng đầy đủ

Lưu mã vào `ReusableFormatterDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.*;
import java.time.format.*;
import java.util.Locale;
import java.util.concurrent.*;

public class ReusableFormatterDemo {
    private static final DateTimeFormatter DAY_TEXT = DateTimeFormatter
            .ofPattern("dd MMM uuuu", Locale.ENGLISH);
    private static final DateTimeFormatter MOMENT_BASE = DateTimeFormatter
            .ofPattern("uuuu-MM-dd HH:mm:ss XXX '['VV']'", Locale.ROOT);
    private static final ZoneId SOURCE_ZONE = ZoneId.of("Asia/Ho_Chi_Minh");
    private static final DateTimeFormatter MOMENT_HCM =
            MOMENT_BASE.withZone(SOURCE_ZONE);
    private static final DateTimeFormatter MOMENT_UTC =
            MOMENT_BASE.withZone(ZoneId.of("UTC"));

    public static void main(String[] args) throws Exception {
        LocalDate day = LocalDate.of(2025, 6, 10);
        DateTimeFormatter french = DAY_TEXT.withLocale(Locale.FRENCH);
        System.out.println("English = " + DAY_TEXT.format(day));
        System.out.println("French = " + french.format(day));
        System.out.println("English again = " + DAY_TEXT.format(day));

        Instant event = Instant.parse("2025-06-10T02:00:00Z");
        System.out.println("HCM = " + MOMENT_HCM.format(event));
        System.out.println("UTC = " + MOMENT_UTC.format(event));
        System.out.println("instant unchanged = " + event);

        DateTimeFormatter sourceInput = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm:ss", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT)
                .withZone(SOURCE_ZONE);
        Instant parsed = sourceInput.parse(
                "2025-06-10 09:00:00", Instant::from);
        System.out.println("source local -> instant = " + parsed);
        System.out.println("plain local = "
                + LocalDateTime.parse("2025-06-10 09:00:00", sourceInput));

        try {
            MOMENT_HCM.format(day);
        } catch (DateTimeException ex) {
            System.out.println("date without time = DateTimeException");
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Callable<String> job = () -> MOMENT_HCM.format(event);
            Future<String> first = pool.submit(job);
            Future<String> second = pool.submit(job);
            System.out.println("shared formatter = "
                    + first.get().equals(second.get()));
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ReusableFormatterDemo.java
java ReusableFormatterDemo
```

Kết quả:

```text
English = 10 Jun 2025
French = 10 juin 2025
English again = 10 Jun 2025
HCM = 2025-06-10 09:00:00 +07:00 [Asia/Ho_Chi_Minh]
UTC = 2025-06-10 02:00:00 Z [UTC]
instant unchanged = 2025-06-10T02:00:00Z
source local -> instant = 2025-06-10T02:00:00Z
plain local = 2025-06-10T09:00
date without time = DateTimeException
shared formatter = true
```

Các dòng tên tháng minh họa đầu ra với Locale đã chọn. Các mẫu giờ dùng `XXX` để ghi độ lệch dạng `+07:00` hoặc `Z`, còn `VV` ghi mã vùng. Dấu `[` và `]` được đặt trong dấu nháy đơn của mẫu để trở thành ký tự hiển thị; chúng không mở nhóm tùy chọn trong mẫu này.

Đoạn dùng `ExecutorService` gửi hai công việc độc lập cùng dùng `MOMENT_HCM`, lấy kết quả theo thứ tự bằng `Future.get()` rồi so sánh. Đây là minh họa cách dùng chung; bảo đảm an toàn luồng đến từ hợp đồng API, không được suy ra chỉ từ việc hai công việc thử nghiệm cho kết quả bằng nhau. `shutdown()` giải phóng việc nhận thêm công việc khi đã dùng xong nhóm luồng.

## 6. Những điều chương trình cho thấy

### Cấu hình phái sinh không làm đổi bản gốc

`french` được tạo bằng `DAY_TEXT.withLocale(Locale.FRENCH)`. Sau khi dùng nó, `DAY_TEXT` vẫn in `Jun` như ban đầu. Tương tự, `MOMENT_HCM` và `MOMENT_UTC` cùng bắt đầu từ `MOMENT_BASE` nhưng có vùng khác nhau; không có lần gọi nào âm thầm đổi vùng của formatter còn lại.

Nhờ vậy có thể xây một cấu hình nền rồi tạo các biến thể theo nhu cầu. Nếu cấu hình đến từ từng yêu cầu người dùng, giữ biến thể trong phạm vi yêu cầu hoặc một đối tượng cấu hình phù hợp; không cần gán lại một biến toàn cục để chuyển ngôn ngữ/vùng qua lại.

### Vùng cung cấp ngữ cảnh khi chuỗi chưa có vùng

`sourceInput` đọc ngày–giờ không có vùng trong chuỗi, nhưng được cấu hình `withZone(SOURCE_ZONE)`. Kết quả có đủ ngữ cảnh để truy vấn `Instant::from`, nên 09:00 của nguồn được diễn giải thành 02:00 UTC trong ví dụ.

Đó là quy định nguồn thuộc `Asia/Ho_Chi_Minh`, không phải vùng mà formatter khám phá từ văn bản. Nếu văn bản trực tiếp cung cấp mã vùng, vùng đọc từ văn bản được dùng thay cho vùng ghi đè trong bước phân tích. Khi văn bản có độ lệch, độ lệch còn tham gia xác định thời điểm. Vì vậy, không dùng `withZone()` như một thao tác xóa hoặc viết lại mọi thông tin vùng/độ lệch của đầu vào.

Lời gọi tạo `LocalDateTime` ở dòng sau vẫn trả kiểu không chứa vùng. Cấu hình formatter không biến mọi kiểu đích thành kiểu có vùng; muốn giữ hoặc sử dụng thông tin ấy cần chọn kiểu đích như `ZonedDateTime` hoặc truy vấn ra `Instant` theo mục đích.

### Có vùng không tự tạo ra giờ bị thiếu

`MOMENT_HCM.format(day)` thất bại vì `day` là `LocalDate` và mẫu đòi cả giờ. Một vùng thời gian không tự bổ sung giờ hẹn. Muốn tạo mốc đầu ngày hoặc giờ xác định, phải lựa chọn rõ như `date.atStartOfDay(zone)` hoặc `date.atTime(hour, minute).atZone(zone)` trước bước cần thời điểm.

Khi nguồn dùng vùng có chuyển đổi giờ mùa hè, việc diễn giải ngày–giờ địa phương còn phải tuân theo quy tắc vùng ở ngày ấy. Không thay tên vùng bằng một độ lệch cố định chỉ vì độ lệch hiện tại đang giống nhau.

## 7. Chọn phạm vi tái sử dụng phù hợp

| Trường hợp | Cách tổ chức cấu hình |
| --- | --- |
| Định dạng cố định của ứng dụng | Hằng `static final DateTimeFormatter` có tên theo mục đích |
| Vùng/Locale cố định từ cấu hình dịch vụ | Trường `final`, tạo sau khi đọc cấu hình |
| Hiển thị theo người dùng | Tạo biến thể từ formatter nền với Locale/vùng của người dùng |
| Đọc tệp của một nguồn cụ thể | Formatter riêng mô tả hợp đồng và vùng của nguồn nếu nguồn quy định |

Tái sử dụng giúp tránh dựng lại cùng quy tắc một cách không cần thiết, nhưng không phải lý do để gộp các ý nghĩa khác nhau vào một formatter toàn cục. Formatter nhập liệu có thể dùng `STRICT`, trong khi formatter xuất chỉ phục vụ một hình thức trình bày; tên và cấu hình nên phản ánh mục đích đó.

Nếu sau khi đo thực tế cần bộ nhớ đệm cho nhiều cấu hình, khóa phải mô tả đầy đủ các khác biệt liên quan, không chỉ chuỗi mẫu: Locale, vùng, chế độ phân giải và những tùy chỉnh khác có thể thay đổi hành vi. Không cần thêm bộ nhớ đệm không giới hạn cho mọi tổ hợp do người dùng đưa vào khi chưa có nhu cầu rõ ràng.

Bài tập: từ `MOMENT_BASE`, tạo một biến thể dùng `ZoneId.of("Asia/Tokyo")` rồi định dạng cùng `event`. Với thời điểm trong chương trình, phần giờ sẽ là 11:00 và độ lệch `+09:00`; `MOMENT_HCM` vẫn phải xuất 09:00. Sau đó giải thích tại sao chỉ đổi `Locale` sang tiếng Nhật không đủ để thực hiện việc đổi vùng này.
