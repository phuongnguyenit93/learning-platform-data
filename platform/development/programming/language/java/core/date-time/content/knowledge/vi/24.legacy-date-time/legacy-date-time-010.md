# Khác biệt lịch Gregorian lịch sử khi di chuyển dữ liệu cũ

## 1. Cùng các con số ngày tháng chưa chắc là cùng một ngày

Khi đổi mã từ `GregorianCalendar` sang `LocalDate`, những ngày hiện đại thường trông như chuyển đổi trực tiếp. Với dữ liệu lịch sử, sao chép năm/tháng/ngày hoặc chuyển qua thời điểm có thể cho hai kết quả khác nhau.

Ví dụ trong bài, `GregorianCalendar` mặc định ghi các trường `1582-10-04`, nhưng thời điểm tương ứng khi nhìn bằng lịch ISO của `LocalDate` là ngày `1582-10-14` ở UTC. Sao chép nguyên ba trường vào `LocalDate.of(1582, 10, 4)` lại cho ngày ISO 4 tháng 10, tức một lựa chọn khác.

Không thể kết luận cứ khác con số là chuyển đổi sai. Phải biết dữ liệu nguồn muốn giữ **cùng vị trí trên dòng thời gian/ngày** hay giữ **nhãn năm–tháng–ngày đã ghi**. Hai mục tiêu này không luôn đồng nhất khi hệ lịch khác nhau.

## 2. `GregorianCalendar` mặc định là lịch lai

Theo [Java SE 21 — GregorianCalendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html), lớp này mặc định dùng Julian trước mốc chuyển sang Gregorian và dùng Gregorian từ mốc đó. Mốc mặc định là ngày Gregorian `1582-10-15`, có thể thay bằng `setGregorianChange()`.

Với cấu hình mặc định trong ví dụ UTC, ngày Julian 4 tháng 10 năm 1582 được tiếp nối bởi ngày Gregorian 15 tháng 10. Khoảng nhãn ngày 5–14 tháng 10 không tồn tại trong lịch lai đó. Đây là quy tắc của cấu hình đang dùng; không phải mô tả rằng mọi nơi trên thế giới đều chuyển lịch cùng một ngày.

Julian coi năm chia hết cho 4 là năm nhuận. Gregorian loại các năm thế kỷ không chia hết cho 400. Vì vậy, năm 1500 có ngày 29 tháng 2 theo Julian, nhưng không có theo Gregorian. Khác biệt không chỉ là bỏ một số nhãn ngày ở năm 1582; quy tắc năm nhuận trước mốc cũng khác.

Một đối tượng cũ còn có thể đã được đặt mốc chuyển đổi riêng. Chỉ biết tên lớp `GregorianCalendar` chưa đủ để kết luận dữ liệu của nó dùng cùng quy tắc với một đối tượng mới mặc định.

## 3. `LocalDate` dùng Gregorian kéo dài về quá khứ

[Java SE 21 — LocalDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html) dùng lịch ISO tương đương Gregorian kéo dài theo quy tắc nhất quán về quá khứ, thường gọi là **proleptic Gregorian**. Nó không tự chuyển sang Julian trước ngày 15 tháng 10 năm 1582.

Hệ quả có thể kiểm tra:

| Tình huống | GregorianCalendar mặc định | LocalDate ISO |
| --- | --- | --- |
| Sau ngày mang nhãn `1582-10-04` | Nhãn kế tiếp là `1582-10-15` | Ngày tiếp theo là `1582-10-05` |
| Dựng ngày `1582-10-10` | Không hợp lệ trong khoảng chuyển đổi khi kiểm tra chặt chẽ | Hợp lệ |
| Dựng ngày `1500-02-29` | Hợp lệ ở phần Julian | Không hợp lệ theo Gregorian |

`LocalDate` không sai chỉ vì cho phép ngày nằm trong khoảng nhãn bị bỏ của lịch lai; nó đang dùng một mô hình lịch khác. Ngược lại, mô hình Gregorian kéo dài cũng không tự chứng minh đó là nhãn mà một tài liệu lịch sử tại một địa phương đã dùng.

## 4. Chọn điều cần bảo toàn trước khi chuyển

### Giữ cùng thời điểm hoặc cùng ngày đã mã hóa

Nếu dữ liệu nguồn thực sự lưu một thời điểm, chuyển qua `Instant` sẽ giữ giá trị thời điểm. Sau đó phải chọn vùng để lấy ngày ISO:

```java
// Minh họa trong một phương thức; legacy là GregorianCalendar nguồn.
LocalDate isoDate = legacy.toInstant()
        .atZone(ZoneOffset.UTC)
        .toLocalDate();
```

UTC chỉ là vùng đã chọn cho ví dụ. Dữ liệu thật có thể cần vùng của nguồn hoặc vùng nghiệp vụ khác. Chọn vùng khác có thể đổi ngày địa phương độc lập với khác biệt Julian/Gregorian, nên hai vấn đề phải được xét riêng.

### Giữ nguyên các trường ngày đã ghi

Nếu hợp đồng nói các con số nguồn đã mang nghĩa ngày ISO hoặc một ngày dân sự cần được diễn giải lại, có thể phải dựng `LocalDate` từ các trường theo quyết định đó. Nhưng đó là **diễn giải lại các trường**, không bảo đảm giữ thời điểm mà Calendar cũ đã tính.

Sao chép còn phải xử lý tháng Calendar bắt đầu từ 0 và kỷ nguyên `ERA`. Với dữ liệu trước Công nguyên, chỉ lấy `Calendar.YEAR` không đủ vì năm trong kỷ nguyên không giống năm liên tục có năm 0 của ISO. Đoạn sao chép trong chương trình chỉ minh họa các ngày thuộc Công nguyên đã chọn, không phải hàm tổng quát cho mọi năm lịch sử.

Với tài liệu thực sự được ghi theo Julian hoặc mốc chuyển đổi địa phương riêng, cần giữ metadata và xác định phép chuyển tương ứng. Không đổi tên cột thành ISO rồi sao chép nhãn mà bỏ thông tin hệ lịch.

## 5. Chương trình kiểm chứng đầy đủ

Lưu mã vào `HistoricalGregorianMigrationDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.*;
import java.util.*;

public class HistoricalGregorianMigrationDemo {
    private static GregorianCalendar legacy(boolean prolepticGregorian) {
        GregorianCalendar value = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        if (prolepticGregorian) {
            value.setGregorianChange(new Date(Long.MIN_VALUE));
        }
        value.clear();
        value.setLenient(false);
        return value;
    }

    private static String fields(Calendar value) {
        return String.format(Locale.ROOT, "%04d-%02d-%02d",
                value.get(Calendar.YEAR),
                value.get(Calendar.MONTH) + 1,
                value.get(Calendar.DAY_OF_MONTH));
    }

    private static LocalDate sameDay(GregorianCalendar value) {
        return value.toInstant().atZone(ZoneOffset.UTC).toLocalDate();
    }

    public static void main(String[] args) {
        GregorianCalendar beforeCutover = legacy(false);
        beforeCutover.set(1582, Calendar.OCTOBER, 4);
        System.out.println("legacy fields = " + fields(beforeCutover));
        System.out.println("same instant ISO date = " + sameDay(beforeCutover));
        LocalDate copiedFields = LocalDate.of(
                beforeCutover.get(Calendar.YEAR),
                beforeCutover.get(Calendar.MONTH) + 1,
                beforeCutover.get(Calendar.DAY_OF_MONTH));
        System.out.println("copied fields ISO date = " + copiedFields);

        beforeCutover.add(Calendar.DAY_OF_MONTH, 1);
        System.out.println("legacy plus one day = " + fields(beforeCutover));
        System.out.println("same instant after = " + sameDay(beforeCutover));

        GregorianCalendar gap = legacy(false);
        gap.set(1582, Calendar.OCTOBER, 10);
        try {
            gap.getTimeInMillis();
        } catch (IllegalArgumentException ex) {
            System.out.println("legacy cutover gap = IllegalArgumentException");
        }
        System.out.println("ISO date in gap = " + LocalDate.of(1582, 10, 10));

        GregorianCalendar julianLeap = legacy(false);
        julianLeap.set(1500, Calendar.FEBRUARY, 29);
        System.out.println("legacy 1500 leap fields = " + fields(julianLeap));
        System.out.println("same day ISO = " + sameDay(julianLeap));
        try {
            LocalDate.of(1500, 2, 29);
        } catch (DateTimeException ex) {
            System.out.println("ISO 1500-02-29 = DateTimeException");
        }

        GregorianCalendar pureGregorian = legacy(true);
        pureGregorian.set(1500, Calendar.MARCH, 1);
        System.out.println("pure Gregorian fields = " + fields(pureGregorian));
        System.out.println("pure Gregorian ISO = " + sameDay(pureGregorian));

        GregorianCalendar fromModern = GregorianCalendar.from(
                LocalDate.of(1500, 3, 1).atStartOfDay(ZoneOffset.UTC));
        System.out.println("from modern fields = " + fields(fromModern));
        System.out.println("from modern pure Gregorian = "
                + (fromModern.getGregorianChange().getTime() == Long.MIN_VALUE));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HistoricalGregorianMigrationDemo.java
java HistoricalGregorianMigrationDemo
```

Kết quả:

```text
legacy fields = 1582-10-04
same instant ISO date = 1582-10-14
copied fields ISO date = 1582-10-04
legacy plus one day = 1582-10-15
same instant after = 1582-10-15
legacy cutover gap = IllegalArgumentException
ISO date in gap = 1582-10-10
legacy 1500 leap fields = 1500-02-29
same day ISO = 1500-03-10
ISO 1500-02-29 = DateTimeException
pure Gregorian fields = 1500-03-01
pure Gregorian ISO = 1500-03-01
from modern fields = 1500-03-01
from modern pure Gregorian = true
```

Mọi Calendar trong bài đều được cấu hình UTC và xóa các trường có sẵn trước khi đặt ngày. Hàm `fields()` in nhãn từ các trường Calendar, còn `sameDay()` lấy ngày ISO của cùng thời điểm ở UTC. Hai hàm cố ý trả lời hai câu hỏi khác nhau để khác biệt không bị che bởi một cách định dạng duy nhất.

## 6. Đọc các tình huống di chuyển trong kết quả

### Nhãn cũ và nhãn ISO khác nhau nhưng có thể cùng một thời điểm

`legacy fields` là `1582-10-04`; `same instant ISO date` là `1582-10-14`. Đây là ngày Julian và ngày Gregorian kéo dài tương ứng theo cấu hình thử nghiệm. `copied fields ISO date` vẫn là `1582-10-04`, cho thấy cách sao chép ba con số đã chọn một ngày ISO khác.

Sau khi cộng một ngày trên Calendar, nhãn chuyển thành `1582-10-15`. Khi đổi cùng thời điểm sang ISO, ngày cũng là 15 tháng 10. Không thể sửa toàn bộ dữ liệu bằng cách cộng một số ngày cố định cho mọi bản ghi: khác biệt tùy giai đoạn và cấu hình lịch.

### Chế độ chặt chẽ phát hiện khoảng chuyển đổi theo lịch nguồn

Calendar ở trạng thái không linh hoạt từ chối nhãn `1582-10-10` khi tính mili giây. `set()` trước đó có thể đã trở về mà chưa kiểm tra, nên chương trình chủ động gọi `getTimeInMillis()` để buộc phép tính.

Cùng các số đó tạo được `LocalDate`. Vì vậy, “đầu vào cũ từng bị từ chối” không có nghĩa `LocalDate` cũng phải từ chối theo cùng khoảng chuyển đổi. Ngược lại, không dùng chế độ linh hoạt để tự chuẩn hóa dữ liệu sai rồi coi như đã biết ý nghĩa lịch sử của nó.

### Năm nhuận cũ cũng có thể làm ngày hợp lệ thay đổi

Calendar mặc định chấp nhận `1500-02-29` trong phần Julian và chuyển cùng ngày thành `1500-03-10` ISO. `LocalDate.of(1500, 2, 29)` từ chối vì quy tắc Gregorian không coi năm 1500 là năm nhuận.

Nếu di chuyển bằng cách dựng lại `LocalDate` từ trường mà gặp lỗi như vậy, không nên tự đổi ngày 29 về 28 để cho chương trình chạy. Trước tiên phải xác định dữ liệu là ngày Julian có nghĩa hay một giá trị sai trong nguồn vốn đã được định nghĩa là ISO.

## 7. Cấu hình Gregorian thuần và phương thức chuyển từ API mới

`setGregorianChange(new Date(Long.MIN_VALUE))` được dùng trong ví dụ để chọn Gregorian thuần trong miền thời gian Calendar hỗ trợ. Đối tượng được cấu hình **trước khi** đặt các trường ngày, nên năm/tháng/ngày đầu vào được diễn giải theo lựa chọn ấy.

Khi dựng ngày `1500-03-01`, các trường và ngày ISO của cùng thời điểm trùng nhau. Đây là cấu hình cụ thể, không phải chứng cứ mọi Calendar mặc định đều đã dùng Gregorian thuần.

`GregorianCalendar.from(zonedDateTime)` trong chương trình cũng tạo đối tượng dùng Gregorian thuần, được xác nhận bằng mốc chuyển đổi `Long.MIN_VALUE`. Do vậy, chuyển từ `java.time` sang Calendar qua API này không có nghĩa quay về đúng cấu hình lịch lai của một Calendar cũ mặc định.

Không dùng việc đổi mốc trên các đối tượng nguồn như thao tác “sửa dữ liệu” hàng loạt mà chưa có hợp đồng. Nếu nhãn đã được đọc theo một lịch, đổi quy tắc diễn giải có thể làm thay ý nghĩa cần bảo toàn. Chọn cấu hình trước khi diễn giải dữ liệu và kiểm chứng cả chiều đọc lẫn chiều ghi.

## 8. Kiểm tra những gì khi xử lý dữ liệu cũ?

Một kế hoạch di chuyển có thể bắt đầu từ các câu hỏi cụ thể:

1. Nguồn lưu thời điểm/mili giây hay chỉ lưu các trường/nguyên văn nhãn ngày?
2. Nguồn đã dùng lớp lịch nào, mốc chuyển đổi nào, chế độ linh hoạt nào và vùng nào?
3. Đích cần giữ cùng thời điểm hay giữ/diễn giải lại nhãn ngày, và có cần giữ lịch nguồn để giải thích không?
4. Dữ liệu có ngày quanh mốc chuyển đổi, năm thế kỷ khác quy tắc nhuận hoặc kỷ nguyên trước Công nguyên không?

Kiểm chứng bằng bản ghi ở cả hai phía của mốc và một năm như 1500 dễ làm lộ sự khác biệt hơn chỉ thử ngày hiện đại. Đồng thời, bảo toàn chuỗi nguồn hoặc metadata phù hợp nếu cần đối chiếu; sau khi chỉ còn ngày ISO đã chuyển, có thể không suy ra được nguyên văn nhãn lịch sử ban đầu.

Không suy ra thực tiễn lịch sử của một quốc gia chỉ từ Locale hoặc vùng thời gian của đối tượng. `GregorianCalendar` chỉ hỗ trợ một mốc chuyển đổi Julian/Gregorian cho cấu hình đó; dữ liệu lịch sử phức tạp có thể cần quy tắc hoặc mô hình chuyên biệt ngoài phạm vi lớp này.

Bài tập: lấy Calendar mặc định biểu diễn `1582-10-04`, chuyển qua cùng thời điểm sang ngày ISO rồi so với `LocalDate.of(1582, 10, 4)`. Giải thích vì sao hai kết quả khác nhau không được sửa bằng cách thay ngẫu nhiên múi giờ. Sau đó thử một ngày sau mốc như `1600-03-01` với cùng UTC để thấy hai mô hình đã dùng chung quy tắc Gregorian trong giai đoạn đó.
