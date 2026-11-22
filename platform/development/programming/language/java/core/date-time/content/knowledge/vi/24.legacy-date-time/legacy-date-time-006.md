# `SimpleDateFormat`: mẫu định dạng, `Locale` và múi giờ

## 1. Ba cấu hình phối hợp để đọc và ghi ngày giờ

`SimpleDateFormat` là bộ định dạng thuộc API cũ `java.text`, dùng `Date` làm giá trị ngày giờ khi chuyển giữa đối tượng và chuỗi. Nó vẫn xuất hiện trong thư viện hoặc mã cũ, nên cần hiểu rõ cách cấu hình thay vì sao chép một mẫu nhìn có vẻ đúng.

Ba câu hỏi phải tách riêng:

- **Mẫu định dạng:** các trường xuất hiện theo thứ tự và ký tự phân cách nào?
- **Locale:** những phần văn bản như tên tháng, thứ, AM/PM dùng quy ước ngôn ngữ/vùng nào?
- **Múi giờ:** một thời điểm được diễn giải thành giờ địa phương ở đâu, hoặc chuỗi thiếu vùng được hiểu theo vùng nào?

Cùng một `Date` có thể được ghi thành 02:15 UTC hoặc 09:15 ở Việt Nam. Đổi Locale có thể làm `Jun` thành `juin`, nhưng không tự chuyển 02:15 thành 09:15.

[Java SE 21 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html) mô tả cú pháp mẫu và cách đọc/ghi theo Locale. Với mã mới dùng `java.time`, thường chọn `DateTimeFormatter`; bài này tập trung cách xử lý đúng khi phải làm việc với API cũ.

## 2. Đọc mẫu theo đúng ký tự hoa/thường

| Ký hiệu thường gặp | Ý nghĩa trong `SimpleDateFormat` | Ví dụ |
| --- | --- | --- |
| `yyyy` | Năm | `2025` |
| `MM` | Tháng dạng số khi ghi | `06` |
| `MMM` / `MMMM` | Tên tháng rút gọn / đầy đủ | `Jun` / `June` với Locale tiếng Anh |
| `dd` | Ngày trong tháng | `10` |
| `HH` | Giờ 24 giờ, 0–23 | `09`, `21` |
| `hh` và `a` | Giờ 12 giờ và dấu AM/PM | `09 PM` |
| `mm` | Phút | `15` |
| `ss` | Giây | `30` |
| `SSS` | Mili giây | `007` |
| `XXX` | Độ lệch kiểu ISO với dấu `:` | `+07:00` hoặc `Z` |
| `Z` | Độ lệch kiểu RFC 822 | `+0700` |
| `z` | Tên/mô tả vùng | Phụ thuộc vùng và dữ liệu Locale |

Những cặp dễ nhầm là `MM` với `mm`, `dd` với `DD`, `yyyy` với `YYYY`. Trong API này, `D` là ngày thứ mấy trong năm, còn `Y` là năm theo tuần. Vì vậy `YYYY-MM-dd` có thể ghép sai loại năm với tháng/ngày ở ranh giới năm.

Đoạn chữ cố định cần đặt trong dấu nháy đơn của mẫu, chẳng hạn `"yyyy-MM-dd 'at' HH:mm"`. Để biểu diễn một dấu nháy đơn trong văn bản, mẫu dùng hai dấu nháy đơn liên tiếp. Với chuỗi ISO có chữ `T`, dùng `"yyyy-MM-dd'T'HH:mm:ssXXX"`.

Số ký tự lặp lại ảnh hưởng cách ghi như thêm 0 ở đầu hoặc chọn tên đầy đủ. Tuy nhiên, ở chiều đọc số, `SimpleDateFormat` không luôn yêu cầu đúng độ rộng như người đọc suy từ số chữ trong mẫu. `setLenient(false)` kiểm tra tính hợp lệ ngày, không phải một biểu thức kiểm tra hình thức đầy đủ của chuỗi.

## 3. Cấu hình Locale tường minh

Có thể tạo bộ định dạng bằng:

```java
SimpleDateFormat format = new SimpleDateFormat(
        "dd MMM yyyy HH:mm:ss XXX", Locale.ENGLISH);
```

Nếu dùng tên tháng/AM-PM theo một ngôn ngữ nhất định trong hợp đồng nguồn, phải chọn Locale phù hợp. Đừng dựa vào Locale mặc định của máy chủ để đọc tệp tiếng Anh rồi chờ nó hoạt động giống máy người viết.

Đổi Locale không tự sắp xếp lại một mẫu cố định đã viết như `dd MMM yyyy`. Nếu muốn định dạng ngày theo phong cách thông thường của một vùng thay vì một hợp đồng mẫu riêng, các phương thức `DateFormat.getDateInstance()`/`getDateTimeInstance()` là một hướng khác.

Locale còn có thể ảnh hưởng các thành phần hỗ trợ định dạng/lịch trong API cũ, nên ở ranh giới dữ liệu cần biết hệ lịch của nguồn. Không suy ra rằng chỉ vì tên tháng nhìn đúng thì mọi trường ngày đã được diễn giải theo hợp đồng mong muốn.

Tránh năm hai chữ số nếu nguồn cần ý nghĩa năm ổn định. Việc diễn giải `yy` có cửa sổ thế kỷ phụ thuộc cấu hình bộ định dạng; chuỗi năm bốn chữ số thường rõ ràng hơn. Nếu bắt buộc nhận năm hai chữ số, cần quy định cửa sổ diễn giải và cấu hình nó thay vì đoán.

## 4. Múi giờ tác động đến cả ghi và đọc

`Date` biểu diễn thời điểm theo mili giây; nó không giữ một múi giờ riêng như `ZonedDateTime`. Formatter dùng `setTimeZone(...)` để chọn cách nhìn thời điểm đó khi xuất chuỗi.

Ví dụ, thời điểm `2025-06-10T02:15:30Z` được ghi thành `2025-06-10 09:15:30 +07:00` khi formatter dùng `Asia/Ho_Chi_Minh`. Đối tượng thời điểm ban đầu không bị cộng thêm bảy giờ.

Ở chiều đọc:

- Nếu chuỗi không có độ lệch/vùng, vùng đã cấu hình cung cấp ngữ cảnh để hiểu giờ địa phương.
- Nếu mẫu và chuỗi có độ lệch như `+07:00`, thông tin ấy tham gia xác định thời điểm; không coi múi giờ cấu hình như lệnh bỏ qua độ lệch đã ghi trong chuỗi.

Khi nhận tên vùng từ cấu hình, lưu ý [TimeZone.getTimeZone(String)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html#getTimeZone(java.lang.String)) có thể quay về GMT với ID không được nhận diện. Ví dụ bên dưới nhận `ZoneId` đã xác định rồi chuyển bằng `TimeZone.getTimeZone(zone)` để tránh việc một lỗi gõ ID âm thầm trở thành lựa chọn GMT.

Không dùng tên viết tắt mơ hồ như `CST` khi hợp đồng cần biết vùng cụ thể. Tên vùng như `Asia/Ho_Chi_Minh` hoặc độ lệch đã được quy định sẽ diễn đạt lựa chọn rõ hơn.

## 5. Chương trình kiểm chứng đầy đủ

Lưu mã vào `LegacyFormatterSettingsDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.text.*;
import java.time.*;
import java.util.*;

public class LegacyFormatterSettingsDemo {
    private static SimpleDateFormat formatter(
            String pattern, Locale locale, ZoneId zone) {
        SimpleDateFormat format = new SimpleDateFormat(pattern, locale);
        format.setTimeZone(TimeZone.getTimeZone(zone));
        format.setLenient(false);
        return format;
    }

    private static Date parseAll(SimpleDateFormat format, String text)
            throws ParseException {
        ParsePosition position = new ParsePosition(0);
        Date result = format.parse(text, position);
        if (result == null || position.getIndex() != text.length()) {
            int error = position.getErrorIndex();
            throw new ParseException("Invalid complete date",
                    error >= 0 ? error : position.getIndex());
        }
        return result;
    }

    public static void main(String[] args) throws ParseException {
        ZoneId utc = ZoneOffset.UTC;
        ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
        Date moment = Date.from(Instant.parse("2025-06-10T02:15:30Z"));

        SimpleDateFormat english = formatter(
                "dd MMM yyyy HH:mm:ss XXX", Locale.ENGLISH, utc);
        SimpleDateFormat french = formatter(
                "dd MMM yyyy HH:mm:ss XXX", Locale.FRENCH, utc);
        System.out.println("English UTC = " + english.format(moment));
        System.out.println("French UTC = " + french.format(moment));

        SimpleDateFormat local = formatter(
                "yyyy-MM-dd HH:mm:ss XXX", Locale.ROOT, hcm);
        System.out.println("HCM = " + local.format(moment));
        System.out.println("original instant = " + moment.toInstant());

        SimpleDateFormat source = formatter(
                "yyyy-MM-dd HH:mm", Locale.ROOT, hcm);
        Date parsed = parseAll(source, "2025-06-10 09:15");
        System.out.println("local input -> instant = " + parsed.toInstant());

        SimpleDateFormat withOffset = formatter(
                "yyyy-MM-dd'T'HH:mm:ssXXX", Locale.ROOT, utc);
        Date offsetParsed = parseAll(
                withOffset, "2025-06-10T09:15:30+07:00");
        System.out.println("offset input -> instant = "
                + offsetParsed.toInstant());

        SimpleDateFormat dateOnly = formatter("yyyy-MM-dd", Locale.ROOT, utc);
        try {
            parseAll(dateOnly, "2025-02-29");
        } catch (ParseException ex) {
            System.out.println("invalid date = ParseException");
        }
        try {
            parseAll(dateOnly, "2025-06-10tail");
        } catch (ParseException ex) {
            System.out.println("trailing input = ParseException");
        }

        Date fraction = Date.from(Instant.parse("2025-06-10T02:15:30.007Z"));
        System.out.println("legacy SSS = "
                + formatter("HH:mm:ss.SSS", Locale.ROOT, utc).format(fraction));
        SimpleDateFormat quoted = formatter(
                "yyyy-MM-dd 'at' HH:mm", Locale.ENGLISH, hcm);
        System.out.println("quoted text = " + quoted.format(moment));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LegacyFormatterSettingsDemo.java
java LegacyFormatterSettingsDemo
```

Kết quả đã kiểm chứng với dữ liệu Locale của runtime dùng trong bài:

```text
English UTC = 10 Jun 2025 02:15:30 Z
French UTC = 10 juin 2025 02:15:30 Z
HCM = 2025-06-10 09:15:30 +07:00
original instant = 2025-06-10T02:15:30Z
local input -> instant = 2025-06-10T02:15:00Z
offset input -> instant = 2025-06-10T02:15:30Z
invalid date = ParseException
trailing input = ParseException
legacy SSS = 02:15:30.007
quoted text = 2025-06-10 at 09:15
```

Các thời điểm đầu vào được tạo từ chuỗi ISO cố định; các formatter đều được đặt vùng tường minh. Vì vậy khác biệt giờ trong ví dụ đến từ cấu hình đã chọn, không phải giờ hiện tại của máy.

## 6. Những điểm cần quan sát từ chương trình

### Mẫu giống nhau nhưng Locale khác

`english` và `french` dùng cùng mẫu và vùng UTC. Giờ vẫn là 02:15:30, còn tên tháng thay đổi từ `Jun` sang `juin`. Ngôn ngữ và vùng thời gian đang đảm nhận hai vai trò độc lập.

Tên tháng hiển thị dựa trên dữ liệu Locale của runtime. Với hợp đồng trao đổi cần chuỗi ổn định hơn, thường dùng trường tháng dạng số và quy ước múi giờ/độ lệch rõ ràng.

### Chuỗi thiếu vùng cần vùng của nguồn

`source` đọc `2025-06-10 09:15` theo vùng Việt Nam nên nhận thời điểm `2025-06-10T02:15:00Z`. Phần giây không xuất hiện trong mẫu đầu vào và được hoàn thiện thành 0 trong ví dụ. Nếu đọc cùng chuỗi theo UTC thì thời điểm sẽ khác; không thể chọn vùng chỉ theo điều thuận tiện cho nơi chạy chương trình.

`withOffset` lại đọc chuỗi có `+07:00`, nên thời điểm tương ứng là 02:15:30 UTC. Chương trình in `Date.toInstant()` để nhìn rõ giá trị thời điểm; `Date.toString()` có cách biểu diễn theo vùng môi trường và có thể khiến người đọc nhầm rằng dữ liệu đã bị đổi.

### Ngày sai và phần dư là hai kiểm tra khác nhau

Hàm `formatter()` gọi `setLenient(false)` để ngày `2025-02-29` bị từ chối. Nhưng chỉ đặt chế độ đó chưa bảo đảm phải tiêu thụ hết chuỗi.

[Java SE 21 — DateFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DateFormat.html) cho phép thao tác phân tích với `ParsePosition`, qua đó biết đã đọc đến vị trí nào. Hàm `parseAll()` yêu cầu kết quả không `null` và vị trí cuối bằng độ dài chuỗi. Nhờ vậy `2025-06-10tail` không bị coi là hợp lệ chỉ vì phần đầu đọc được một ngày.

`parseAll()` vẫn không biến mẫu số của API cũ thành bộ kiểm tra mọi độ rộng chính xác. Nếu hợp đồng cần đúng số chữ số, phải kiểm tra hình thức tương ứng hoặc chọn bộ phân tích có cấu hình đáp ứng yêu cầu đó. Không nhầm ba việc: đọc được tiền tố, có ngày hợp lệ và khớp toàn bộ quy tắc chuỗi.

## 7. Đừng sao chép mẫu giữa API cũ và mới mà không đối chiếu

Trong `SimpleDateFormat`, `S` là trường mili giây. `SSS` ghi giá trị 7 mili giây thành `007`, như dòng `legacy SSS` của bài. Trong `DateTimeFormatter`, `S` biểu diễn chữ số phần lẻ của giây. Sự giống nhau ở một mẫu ba chữ số không bảo đảm mọi số lượng chữ `S` hoặc cách phân tích đều tương đương.

Đặc biệt, `u` trong `SimpleDateFormat` là số thứ trong tuần, không phải năm liên tục như `u` trong `DateTimeFormatter`. Vì vậy, không dùng `uuuu` của API hiện đại để thay trực tiếp cho `yyyy` trong mẫu cũ.

Khi chuyển đổi mã, cần kiểm tra các mẫu thực tế, mốc cuối/đầu năm, phần lẻ, độ lệch và dữ liệu có tên tháng. Một mẫu nhìn giống nhau không phải bằng chứng rằng cả hai API đọc và ghi cùng ý nghĩa.

## 8. Dùng formatter có trạng thái trong mã cũ

`SimpleDateFormat` có thể thay đổi bằng `applyPattern()`, `setTimeZone()` hoặc các cấu hình khác; nó không phải formatter bất biến để tùy ý dùng chung nhiều luồng. Tạo instance riêng cho phạm vi xử lý phù hợp hoặc có cơ chế đồng bộ đầy đủ nếu bắt buộc chia sẻ. Trường `static final` chỉ cố định tham chiếu, không làm đối tượng này an toàn luồng.

Việc phân tích còn dùng trạng thái Calendar bên trong; thông tin vùng có thể bị ảnh hưởng bởi dữ liệu đã đọc. Khi tái sử dụng formatter cho nguồn khác, phải giữ rõ cấu hình và vòng đời, không giả định nó có cùng tính chất với `DateTimeFormatter`.

Không cần thay toàn bộ ứng dụng chỉ để đọc một giao diện cũ. Có thể cô lập việc chuyển `Date`/chuỗi ở ranh giới, giữ phép tính nghiệp vụ trên kiểu `java.time` phù hợp, rồi đổi lại khi API bên ngoài yêu cầu.

Bài tập: giữ nguyên `moment` nhưng đổi formatter đầu ra sang vùng UTC và mẫu `yyyy-MM-dd HH:mm:ss Z`. Kết quả phần độ lệch phải là `+0000`, trong khi với `XXX` nó là `Z`. Sau đó thay `HH:mm` thành `hh:mm a` cho một thời điểm 21 giờ theo vùng đã chọn và xác nhận thông tin PM được giữ; không bỏ `a` nếu nguồn dùng giờ 12 giờ mà vẫn cần phân biệt sáng/chiều.
