# Chuyển `TimeZone` với `ZoneId` và kiểm tra mã múi giờ không hợp lệ

## 1. Hai kiểu cùng nói về vùng thời gian nhưng có hợp đồng khác nhau

Mã cũ như `Calendar` hoặc `SimpleDateFormat` thường nhận `java.util.TimeZone`; mã `java.time` dùng `ZoneId` và `ZoneOffset`. Khi nối hai API, cần chuyển đúng kiểu và biết điều gì xảy ra nếu mã vùng sai.

Hai chiều chuyển phổ biến là:

```java
// Minh họa trong một phương thức.
ZoneId modern = ZoneId.of("Asia/Ho_Chi_Minh");
TimeZone legacy = TimeZone.getTimeZone(modern);
ZoneId restored = legacy.toZoneId();
```

Với mã vùng chuẩn được cả hai phía hỗ trợ, đây là cách nối rõ ràng. Tuy nhiên, không nên giả định mọi đối tượng tùy biến, ID bí danh hoặc cách viết độ lệch đều quay lại thành chuỗi y hệt ban đầu.

[Java SE 21 — TimeZone](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TimeZone.html) có cả API nhận chuỗi và API chuyển với `ZoneId`. Cách kiểm tra lỗi của API nhận chuỗi cũ là điểm đặc biệt cần nắm trước khi đưa vào luồng cấu hình.

## 2. Bẫy quay về GMT khi mã chuỗi sai

Lời gọi cũ:

```java
TimeZone zone = TimeZone.getTimeZone("Asia/Ho_Chi_Minh_typo");
```

không bảo đảm sẽ ném ngoại lệ vì tên không tồn tại. Với mã không nhận diện được, `TimeZone.getTimeZone(String)` trả một vùng GMT. Nếu ứng dụng chỉ kiểm tra `zone != null`, cấu hình sai vẫn đi qua và có thể làm các giờ/ngày hiển thị lệch.

Một cách xử lý cho hợp đồng đầu vào dùng mã của API hiện đại là xác nhận bằng `ZoneId.of(text)` trước, rồi mới chuyển sang `TimeZone`. [Java SE 21 — ZoneId.of()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html#of(java.lang.String)) từ chối cú pháp không hợp lệ hoặc ID vùng không tìm được quy tắc bằng ngoại lệ thuộc nhóm `DateTimeException`.

Không dùng quy tắc “kết quả có ID GMT tức là đầu vào sai”: `GMT` là một lựa chọn hợp lệ. Cũng không chỉ so sánh chuỗi đầu vào với chuỗi đầu ra, vì một số cách viết hợp lệ được chuẩn hóa thành ID khác.

Nếu đầu vào bị thiếu hoặc `null`, đó là một trường hợp kiểm tra cấu hình riêng. `DateTimeException` không phải nhãn bao trùm mọi lỗi đầu vào, chẳng hạn tham số `null` có thể gây `NullPointerException`.

## 3. Mã vùng và độ lệch cố định không thay thế hoàn toàn cho nhau

`ZoneId` có thể biểu diễn mã vùng có tập quy tắc như `Europe/Paris` hoặc một độ lệch cố định như `+05:30`. Một vùng có thể có độ lệch khác nhau tại những thời điểm khác nhau; một `ZoneOffset` giữ độ lệch đã xác định.

Trong dữ liệu runtime của ví dụ, Paris có độ lệch `+01:00` ở tháng 1 năm 2025 và `+02:00` ở tháng 7. Nếu chỉ lấy độ lệch hiện tại rồi thay toàn bộ vùng bằng độ lệch ấy, các ngày thuộc giai đoạn khác có thể bị diễn giải sai.

Tương tự, `TimeZone.getRawOffset()` không phải phép chuyển sang `ZoneId`. Nó trả độ lệch chuẩn theo mili giây, chưa thay thế tập quy tắc vùng hoặc độ lệch áp dụng tại mọi thời điểm. Muốn nối API, dùng phương thức chuyển phù hợp; muốn biết độ lệch tại một thời điểm, truy vấn quy tắc với thời điểm ấy.

Không chọn vùng chỉ bằng cách tìm “vùng nào có độ lệch giống nhau hôm nay”. Nhiều vùng có thể cùng độ lệch ở một ngày nhưng khác lịch sử hoặc quy tắc chuyển đổi.

## 4. Chương trình kiểm chứng đầy đủ

Lưu mã vào `ZoneBridgeValidationDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.*;
import java.util.*;

public class ZoneBridgeValidationDemo {
    private static TimeZone checkedLegacyZone(String text) {
        ZoneId validated = ZoneId.of(text);
        return TimeZone.getTimeZone(validated);
    }

    public static void main(String[] args) {
        ZoneId modern = ZoneId.of("Asia/Ho_Chi_Minh");
        TimeZone legacy = TimeZone.getTimeZone(modern);
        ZoneId restored = legacy.toZoneId();
        System.out.println("legacy ID = " + legacy.getID());
        System.out.println("restored ID = " + restored.getId());
        System.out.println("region equal = " + modern.equals(restored));

        String typo = "Asia/Ho_Chi_Minh_typo";
        System.out.println("legacy typo fallback = "
                + TimeZone.getTimeZone(typo).getID());
        try {
            checkedLegacyZone(typo);
        } catch (DateTimeException ex) {
            System.out.println("checked typo = DateTimeException");
        }
        try {
            checkedLegacyZone("not a valid zone!");
        } catch (DateTimeException ex) {
            System.out.println("checked syntax = DateTimeException");
        }
        System.out.println("valid GMT = " + checkedLegacyZone("GMT").getID());

        ZoneId fixed = ZoneOffset.ofHoursMinutes(5, 30);
        TimeZone fixedLegacy = TimeZone.getTimeZone(fixed);
        ZoneId fixedRestored = fixedLegacy.toZoneId();
        System.out.println("fixed input ID = " + fixed.getId());
        System.out.println("fixed legacy ID = " + fixedLegacy.getID());
        System.out.println("fixed restored ID = " + fixedRestored.getId());
        System.out.println("fixed ID equal = " + fixed.equals(fixedRestored));
        System.out.println("fixed normalized equal = "
                + fixed.normalized().equals(fixedRestored.normalized()));

        ZoneId paris = ZoneId.of("Europe/Paris");
        Instant winter = Instant.parse("2025-01-15T12:00:00Z");
        Instant summer = Instant.parse("2025-07-15T12:00:00Z");
        System.out.println("Paris winter offset = "
                + paris.getRules().getOffset(winter));
        System.out.println("Paris summer offset = "
                + paris.getRules().getOffset(summer));

        TimeZone custom = new SimpleTimeZone(7 * 60 * 60 * 1000, "OfficeCustom");
        try {
            custom.toZoneId();
        } catch (DateTimeException ex) {
            System.out.println("custom unknown ID = DateTimeException");
        }
        TimeZone copy = (TimeZone) legacy.clone();
        copy.setID("OfficeCopy");
        System.out.println("original legacy ID = " + legacy.getID());
        System.out.println("copy legacy ID = " + copy.getID());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ZoneBridgeValidationDemo.java
java ZoneBridgeValidationDemo
```

Kết quả đã kiểm chứng với dữ liệu vùng của runtime dùng trong bài:

```text
legacy ID = Asia/Ho_Chi_Minh
restored ID = Asia/Ho_Chi_Minh
region equal = true
legacy typo fallback = GMT
checked typo = DateTimeException
checked syntax = DateTimeException
valid GMT = GMT
fixed input ID = +05:30
fixed legacy ID = GMT+05:30
fixed restored ID = GMT+05:30
fixed ID equal = false
fixed normalized equal = true
Paris winter offset = +01:00
Paris summer offset = +02:00
custom unknown ID = DateTimeException
original legacy ID = Asia/Ho_Chi_Minh
copy legacy ID = OfficeCopy
```

## 5. Diễn giải từng nhóm kết quả

### Mã vùng chuẩn đi qua hai API

`Asia/Ho_Chi_Minh` chuyển sang `TimeZone` rồi trở lại `ZoneId` với cùng ID trong thí nghiệm. Không có phép cộng/trừ giờ nào ở bước chuyển kiểu này; ta đang chuyển cách biểu diễn vùng, không chuyển một thời điểm hoặc sửa đồng hồ hệ thống.

Nếu muốn đổi một `Instant` sang ngày–giờ trong vùng, dùng thao tác riêng như `instant.atZone(zoneId)`. Chuyển `TimeZone` sang `ZoneId` chưa tạo ra một ngày hoặc thời điểm cụ thể.

### Mã sai được phát hiện trước khi đi vào API cũ

`checkedLegacyZone()` gọi `ZoneId.of(text)` trước. Mã có lỗi gõ hoặc cú pháp không hợp lệ đều bị chặn bằng ngoại lệ; chuỗi `GMT` vẫn được chấp nhận đúng nghĩa của nó. Hàm không đổi lỗi thành GMT để tiếp tục chạy như cấu hình bình thường.

Lỗi cú pháp và lỗi thiếu dữ liệu quy tắc có thể có lớp ngoại lệ cụ thể khác nhau trong nhóm `DateTimeException`. Trong ví dụ, chỉ in tên nhóm để kết quả dễ đối chiếu; ứng dụng có thể giữ nguyên nguyên nhân hoặc chuyển thành thông báo cấu hình cụ thể ở ranh giới nhập.

### Chuỗi ID có thể đổi dù độ lệch vẫn tương đương

Độ lệch `+05:30` chuyển sang ID cũ `GMT+05:30`, rồi trở về `ZoneId` với tiền tố GMT. `equals()` của ID cho `false` vì hai cách định danh khác nhau. Sau `normalized()`, cả hai vùng cố định có biểu diễn độ lệch tương ứng nên cho `true`.

Điều này không có nghĩa mọi hai vùng có cùng độ lệch tại một thời điểm đều có thể chuẩn hóa thành cùng vùng. `normalized()` giúp rút vùng có quy tắc cố định thành `ZoneOffset`; nó không bỏ lịch chuyển đổi của vùng có quy tắc thay đổi để lấy một độ lệch tùy ý.

Nếu hợp đồng cần bảo toàn chuỗi ID do người dùng nhập, hãy lưu chuỗi gốc hoặc một dạng chuẩn đã thống nhất riêng. Không dùng vòng chuyển API như một cam kết bảo toàn nguyên văn mọi ID.

## 6. Đối tượng `TimeZone` tùy biến cần được xét riêng

`new SimpleTimeZone(..., "OfficeCustom")` trong bài có độ lệch +07:00 nhưng ID không thuộc tập vùng mà `ZoneId` nhận diện. `toZoneId()` thất bại; không thể tự suy ra một ID vùng chuẩn chỉ từ việc đối tượng cũ đang có độ lệch ấy.

[Java SE 21 — SimpleTimeZone](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SimpleTimeZone.html) cho phép mô tả một độ lệch chuẩn và các quy tắc chuyển đổi nhất định của API cũ. Việc chuyển qua ID không phải một cơ chế tổng quát xuất toàn bộ tập quy tắc tùy biến sang mô hình hiện đại.

Nếu một `TimeZone` đã được đổi ID, đổi độ lệch hoặc có quy tắc riêng, phải xác định muốn bảo toàn điều gì: đúng ID nghiệp vụ, một độ lệch cố định hay toàn bộ quy tắc. Không tự gắn tên của một vùng chuẩn vào đối tượng tùy biến rồi coi hai tập quy tắc đương nhiên giống nhau.

Chiều ngược lại cũng cần phạm vi tương thích: một `ZoneId` từ nhà cung cấp quy tắc tùy biến có thể hợp lệ trong API hiện đại nhưng chưa chắc được API cũ hiểu đầy đủ. Hàm kiểm tra của bài nhắm tới các ID theo hợp đồng đã chọn và ví dụ vùng chuẩn; không tuyên bố mọi tập ID của hai API là giống hệt nhau.

Nếu hệ thống còn nhận các dạng ID riêng của `TimeZone`, cần mô tả hợp đồng tương thích đó riêng. Không dùng `ZoneId.of()` rồi kết luận mọi dạng không nhận được đều là lỗi theo **mọi** quy ước API cũ; các API có miền cú pháp và giới hạn hỗ trợ khác nhau.

## 7. Tên rút gọn, danh sách ID và khả năng thay đổi

Tránh tên ba chữ cái mơ hồ như `CST` trong cấu hình mới. Chúng có thể được hiểu theo cơ chế tương thích cũ hoặc chỉ một ánh xạ nhất định, trong khi nguồn dữ liệu khác nghĩ tới vùng khác. Nếu buộc phải hỗ trợ một bộ bí danh, hãy có ánh xạ được quy định tường minh, chẳng hạn sử dụng một bảng alias phù hợp tại ranh giới, không mặc nhiên chấp nhận mọi chữ viết tắt.

Danh sách `ZoneId.getAvailableZoneIds()` hữu ích khi chọn các ID vùng được cung cấp, nhưng không phải danh sách mọi biểu diễn độ lệch cố định có thể được `ZoneId.of()` chấp nhận. Nếu giao diện cho phép cả vùng và độ lệch, một kiểm tra thành viên đơn giản trong danh sách vùng có thể từ chối dữ liệu độ lệch hợp lệ.

`TimeZone` có thể thay đổi bằng các phương thức đặt cấu hình; `ZoneId` là bất biến. Hai dòng cuối chương trình tạo bản sao `TimeZone`, đổi ID của bản sao và xác nhận ID gốc vẫn giữ nguyên. Dùng bản sao khi cần thay cấu hình cục bộ trên dữ liệu cũ, thay vì vô tình sửa một đối tượng dùng chung.

Đổi `TimeZone.setDefault()` là tác động toàn cục, không phải cách chuyển kiểu. Không thay vùng mặc định của cả JVM chỉ để phục vụ một phép định dạng hoặc một kiểm thử; truyền vùng cụ thể tới nơi cần sử dụng sẽ làm phụ thuộc dễ nhìn hơn.

## 8. Quy trình kiểm tra ở ranh giới cấu hình

Một luồng xử lý rõ ràng có thể gồm:

1. Xác định hợp đồng chấp nhận: ID vùng chuẩn, độ lệch cố định hoặc bí danh đã định nghĩa.
2. Kiểm tra chuỗi theo hợp đồng, xử lý thiếu dữ liệu và từ chối lỗi thay vì âm thầm chọn GMT.
3. Giữ `ZoneId` ở phần mã hiện đại; chuyển sang `TimeZone` ngay nơi API cũ yêu cầu.
4. Với vùng/đối tượng tùy biến, kiểm chứng quy tắc được bảo toàn thay vì chỉ so chuỗi hoặc một độ lệch tại hiện tại.

Dữ liệu vùng được runtime cung cấp và có thể thay đổi giữa các bản cập nhật. Khi kiểm tra lịch sử hoặc lịch hẹn tương lai, cần biết bộ dữ liệu vùng mà môi trường đang dùng; việc đổi lớp Java không tự làm hai môi trường có cùng phiên bản quy tắc.

Bài tập: thay độ lệch +05:30 trong chương trình bằng -03:00. So sánh ID trước/sau chuyển đổi và giá trị sau `normalized()`. Sau đó thử một ID vùng bị gõ sai rồi giải thích vì sao `TimeZone.getTimeZone(text) != null` không chứng minh cấu hình đúng, trong khi `GMT` hợp lệ cũng không được xem là lỗi chỉ vì nó giống giá trị quay về mặc định.
