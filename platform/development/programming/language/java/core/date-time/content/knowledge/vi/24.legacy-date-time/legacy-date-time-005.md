# Calendar lenient và chuẩn hóa giá trị ngoài phạm vi

## 1. Đặt một ngày sai nhưng vẫn nhận được một ngày hợp lệ

Trong `java.util.Calendar`, câu lệnh đặt ngày 29/02/2023 không nhất thiết bị từ chối ngay. Khi cho phép diễn giải mềm dẻo (`lenient`), `GregorianCalendar` có thể hiểu các trường đó thành ngày 01/03/2023.

Đây là **chuẩn hóa giá trị**, không phải xác nhận rằng ngày người dùng đã nhập tồn tại. Nếu ứng dụng dùng kết quả để lưu một ngày sinh hoặc ngày chứng từ mà yêu cầu phải giữ đúng ngày nhập, việc chuẩn hóa có thể che mất lỗi.

Ví dụ, hai câu hỏi khác nhau là:

- “Nếu đi qua đầu tháng 2 thêm 28 ngày, ta đến ngày nào?”
- “Ngày 29/02/2023 có phải một ngày hợp lệ không?”

Chế độ lenient hữu ích cho một số phép diễn giải giá trị vượt phạm vi, nhưng không tự đáp ứng mục tiêu của câu hỏi thứ hai.

## 2. Lenient và non-lenient có ý nghĩa gì?

`Calendar` có thuộc tính kiểm soát cách diễn giải các trường:

```java
calendar.setLenient(true);  // Cho phép chuẩn hóa.
calendar.setLenient(false); // Từ chối trường không nhất quán khi tính giá trị.
```

`isLenient()` đọc cấu hình hiện tại. `GregorianCalendar` mới tạo mặc định ở chế độ lenient, nên cần cấu hình tường minh nếu mục tiêu là kiểm tra nghiêm ngặt.

Trong các ví dụ hiện đại ở bài này:

| Bộ trường được đặt | Kết quả lenient trong GregorianCalendar/UTC | Nếu non-lenient khi tính |
|---|---|---|
| Năm 2023, tháng 2, ngày 29 | `2023-03-01` | Lỗi |
| Năm 2024, tháng 2, ngày 30 | `2024-03-01` | Lỗi |
| Năm 2023, trường tháng 12, ngày 1 | `2024-01-01` | Lỗi |
| Năm 2023, tháng 1, ngày 0 | `2022-12-31` | Lỗi |
| 25/10/2026, giờ trong ngày 25 | `2026-10-26T01:00` | Lỗi |

Hàng “trường tháng 12” phải đọc theo quy ước Calendar: tháng được đánh số từ 0, nên giá trị 12 là vượt qua `DECEMBER == 11`, không phải tháng 12 thông thường của người dùng.

Các kết quả là ví dụ với `GregorianCalendar` và một bộ trường được thiết lập rõ ràng. Không coi chúng là công thức chung cho mọi lớp triển khai Calendar, mọi tổ hợp trường xung đột hoặc mọi dữ liệu lịch sử.

## 3. Calendar trì hoãn việc tính toán sau set

`Calendar` duy trì cả giá trị thời điểm và các trường lịch. `set(...)` có thể chỉ cập nhật các trường, đánh dấu rằng cần tính lại; nó không bắt buộc hoàn tất mọi kiểm tra ngay tại lời gọi.

Luồng thường gặp:

```text
set các trường
    |
    v
trạng thái cần tính lại
    |
    v
get / getTimeInMillis / getTime / phép tính liên quan
    |
    +--> chuẩn hóa nếu lenient
    |
    +--> báo IllegalArgumentException nếu non-lenient và trường sai
```

Ví dụ:

```java
calendar.setLenient(false);
calendar.set(2023, Calendar.FEBRUARY, 29);
// Lời gọi set có thể chưa báo lỗi.
long millis = calendar.getTimeInMillis(); // Buộc diễn giải; ngày sai bị từ chối.
```

Đoạn này minh họa trình tự và giả định biến `calendar` đã được tạo phù hợp. Chương trình đầy đủ ở phần 7 làm rõ lời gọi nào thành công và lời gọi nào ném ngoại lệ.

Nếu muốn dùng Calendar để xác nhận đầu vào legacy, phải buộc tính toán bên trong khối xử lý lỗi. Một hàm chỉ gọi `set` rồi trả thành công có thể chưa kiểm tra điều kiện mà bạn nghĩ nó đã kiểm tra.

Cũng không gọi `get(...)` để in dữ liệu trung gian trước khi hoàn tất thiết lập rồi coi thao tác ấy hoàn toàn vô hại: việc đọc có thể làm chuẩn hóa trạng thái, ảnh hưởng những gì các lệnh `set` tiếp theo đang thao tác.

## 4. Thiết lập đầu vào sạch để tránh phụ thuộc trạng thái cũ

Một `Calendar` thường được tạo với ngày giờ hiện tại. Đặt riêng năm/tháng/ngày không nhất thiết xóa hết các trường giờ, giây hoặc mili giây đã có.

Một mẫu dùng cho ví dụ kiểm tra độc lập:

```java
GregorianCalendar calendar = new GregorianCalendar(
        TimeZone.getTimeZone("UTC"), Locale.ROOT);
calendar.clear();
calendar.setLenient(false);
calendar.set(2024, Calendar.FEBRUARY, 29, 0, 0, 0);
calendar.getTimeInMillis();
```

`clear()` làm các trường chưa được xác định; khi tính, `GregorianCalendar` dùng những giá trị mặc định phù hợp cho trường còn thiếu. Trong đoạn này, giờ/phút/giây được đặt tường minh và mili giây mặc định là 0, nên không còn phần mili giây của lúc tạo đối tượng.

`clear()` không xóa múi giờ đã chọn hoặc tự đổi chế độ lenient. Nó cũng không có nghĩa mọi cấu hình của Calendar đều được đưa về một trạng thái toàn cục giống nhau; mục đích ở đây là loại các trường thời gian còn sót trước khi đặt dữ liệu mới.

Chọn UTC giúp ví dụ về tràn trường không lẫn với khoảng giờ bị bỏ qua/lặp do DST. Với chức năng thật dựa trên vùng cụ thể, cần chọn vùng ấy và kiểm tra cả các tình huống ngày-giờ địa phương không tồn tại. Không dùng UTC để âm thầm thay ý nghĩa đầu vào vốn là giờ của người dùng ở vùng khác.

### Dùng tên hằng cho trường tháng

`Calendar.JANUARY` là 0, `Calendar.FEBRUARY` là 1, ..., `Calendar.DECEMBER` là 11. Dùng hằng giúp tránh nhầm khi đọc mã.

Nếu nhận tháng 1–12 từ giao diện, chuyển đúng ở ranh giới rồi kiểm tra. Đừng coi lenient là cách tự sửa lỗi quên trừ 1: tháng lệch vẫn có thể tạo một ngày hợp lệ nhưng sai tháng yêu cầu.

## 5. Chuẩn hóa xong không còn nguyên bộ trường sai ban đầu

Giả sử đặt 29/02/2023 trong chế độ lenient rồi gọi `toInstant()`. Calendar đã chuẩn hóa thành 01/03/2023. Nếu sau đó mới gọi `setLenient(false)`, việc đọc tiếp thấy một ngày hợp lệ là 01/03, không tự nhớ và từ chối bộ trường 29/02 từng được đặt trước đó.

Do đó trình tự đúng cho mục tiêu từ chối đầu vào sai là:

1. Tạo hoặc chuẩn bị trạng thái sạch.
2. Chọn non-lenient trước khi buộc tính từ bộ trường nhập.
3. Đặt đầy đủ các trường cần thiết.
4. Buộc tính và xử lý lỗi.

Giữ dữ liệu nhập gốc riêng nếu cần báo lỗi hoặc đối chiếu. Không lấy các trường đã được chuẩn hóa từ Calendar rồi dùng chính chúng để chứng minh dữ liệu gốc hợp lệ.

Nếu tái sử dụng Calendar cho nhiều bản ghi, một lỗi hoặc thao tác đọc trước đó còn để lại trạng thái có thể khó theo dõi. Tạo một đối tượng cục bộ cho một lần xác nhận thường dễ kiểm tra hơn việc dùng một Calendar thay đổi dùng chung.

## 6. Miền của từng trường khác với tính hợp lệ của tổ hợp

Kiểm tra `DAY_OF_MONTH` nằm trong 1–31 chưa đủ. Ngày 31 có thể tồn tại trong tháng 1 nhưng không tồn tại trong tháng 2.

Hai lời gọi trả thông tin khác nhau:

| Lời gọi | Ý nghĩa |
|---|---|
| `getMaximum(Calendar.DAY_OF_MONTH)` | Giá trị lớn nhất tổng quát mà trường có thể có trong lịch này |
| `getActualMaximum(Calendar.DAY_OF_MONTH)` | Giá trị lớn nhất theo ngữ cảnh hiện tại của Calendar |

Với tháng 2 năm 2023, giá trị tổng quát là 31 nhưng giá trị thực tế là 28. Phép hỏi giá trị thực tế cũng cần một ngữ cảnh ngày/tháng/năm có thể diễn giải; không dùng nó như cách tránh toàn bộ bước xác nhận tổ hợp đầu vào.

`setLenient(false)` tập trung vào diễn giải các trường lịch, không phải một bộ quy tắc nghiệp vụ. Một ngày có thật vẫn có thể bị cấm vì nằm ngoài thời hạn cho phép. Các điều kiện như “ngày kết thúc không trước ngày bắt đầu” phải kiểm tra riêng sau khi tạo giá trị hợp lệ.

Các thao tác `set`, `add` và `roll` còn có hợp đồng khác nhau. Non-lenient không có nghĩa mọi phép cộng vào một ngày hợp lệ đều phải báo lỗi khi độ dài tháng thay đổi; đừng suy ra hành vi của `add` chỉ từ ví dụ đặt bộ trường không hợp lệ.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `CalendarLeniencyDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Nó chọn rõ GregorianCalendar, UTC và xóa các trường trước khi đặt dữ liệu để kết quả không phụ thuộc lúc chạy.

```java
import java.util.Calendar;
import java.util.GregorianCalendar;
import java.util.Locale;
import java.util.TimeZone;

public class CalendarLeniencyDemo {
    private static GregorianCalendar calendar(boolean lenient) {
        GregorianCalendar result = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        result.clear();
        result.setLenient(lenient);
        return result;
    }

    private static void show(String label, int year, int month, int day) {
        Calendar value = calendar(true);
        value.set(year, month, day, 0, 0, 0);
        System.out.println(label + "=" + value.toInstant());
    }

    public static void main(String[] args) {
        Calendar defaultCalendar = new GregorianCalendar(
                TimeZone.getTimeZone("UTC"), Locale.ROOT);
        System.out.println("defaultLenient=" + defaultCalendar.isLenient());

        show("nonLeapFeb29", 2023, Calendar.FEBRUARY, 29);
        show("leapFeb30", 2024, Calendar.FEBRUARY, 30);
        show("month12", 2023, 12, 1);
        show("januaryDayZero", 2023, Calendar.JANUARY, 0);

        Calendar hourOverflow = calendar(true);
        hourOverflow.set(2026, Calendar.OCTOBER, 25, 25, 0, 0);
        System.out.println("hour25=" + hourOverflow.toInstant());

        Calendar strict = calendar(false);
        strict.set(2023, Calendar.FEBRUARY, 29, 0, 0, 0);
        System.out.println("strictSet=accepted");
        try {
            strict.getTimeInMillis();
        } catch (IllegalArgumentException e) {
            System.out.println("strictRead=IllegalArgumentException");
        }

        Calendar lateSwitch = calendar(true);
        lateSwitch.set(2023, Calendar.FEBRUARY, 29, 0, 0, 0);
        System.out.println("normalized=" + lateSwitch.toInstant());
        lateSwitch.setLenient(false);
        System.out.println("strictAfterNormalization=" + lateSwitch.toInstant());

        Calendar february = calendar(false);
        february.set(2023, Calendar.FEBRUARY, 1, 0, 0, 0);
        System.out.println("genericMaximum="
                + february.getMaximum(Calendar.DAY_OF_MONTH));
        System.out.println("actualMaximum="
                + february.getActualMaximum(Calendar.DAY_OF_MONTH));

        Calendar validLeap = calendar(false);
        validLeap.set(2024, Calendar.FEBRUARY, 29, 0, 0, 0);
        System.out.println("strictValid=" + validLeap.toInstant());
    }
}
```

Biên dịch và chạy:

```shell
javac CalendarLeniencyDemo.java
java CalendarLeniencyDemo
```

Kết quả chuẩn:

```text
defaultLenient=true
nonLeapFeb29=2023-03-01T00:00:00Z
leapFeb30=2024-03-01T00:00:00Z
month12=2024-01-01T00:00:00Z
januaryDayZero=2022-12-31T00:00:00Z
hour25=2026-10-26T01:00:00Z
strictSet=accepted
strictRead=IllegalArgumentException
normalized=2023-03-01T00:00:00Z
strictAfterNormalization=2023-03-01T00:00:00Z
genericMaximum=31
actualMaximum=28
strictValid=2024-02-29T00:00:00Z
```

`strictSet=accepted` mô tả lời gọi `set` đã hoàn thành, không có nghĩa ngày đã được xác nhận. Ngay khi `getTimeInMillis()` buộc tính, ngoại lệ được ném ra và chương trình in nhãn `strictRead`.

Hai dòng `normalized` và `strictAfterNormalization` cho thấy chuyển chế độ quá muộn không khôi phục dữ liệu nhập trước khi chuẩn hóa. Dòng `strictValid` xác nhận non-lenient vẫn nhận ngày 29/02 trong năm nhuận hợp lệ.

Các tên ngoại lệ trong stdout là nhãn do mã in khi bắt lỗi, không phải toàn bộ thông điệp JDK.

## 8. Quan hệ với parsing hiện đại và việc chuyển đổi mã cũ

`Calendar.setLenient(false)` không đồng nghĩa đã cấu hình mọi parser trong chương trình. Một `SimpleDateFormat` có cấu hình diễn giải riêng cần được xem xét ở đúng đối tượng; `DateTimeFormatter` hiện đại dùng `ResolverStyle` cho bước giải quyết trường.

Nếu đầu vào là chuỗi `uuuu-MM-dd` và mục tiêu là một ngày ISO hợp lệ trong mã mới, có thể dùng:

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
LocalDate date = LocalDate.parse(text, strict);
```

Đây là đoạn minh họa, cần các import `java.time`/`java.time.format` và biến `text`. `LocalDate.of(year, month, day)` cũng trực tiếp kiểm tra bộ ba ngày ISO khi dữ liệu đã là số.

Không thay Calendar lenient bằng parsing nghiêm ngặt rồi khẳng định hành vi luôn được bảo toàn: mã cũ có thể đã cố ý dựa vào chuẩn hóa. Trước khi chuyển, cần quyết định đó là hành vi cần giữ hay lỗi cần sửa, sau đó có kiểm tra cho các đầu vào từng bị điều chỉnh.

Với dữ liệu lịch sử, GregorianCalendar còn có cấu hình chuyển tiếp Julian/Gregorian, khác với mô hình ISO kéo dài của LocalDate. Các ví dụ trong bài dùng ngày hiện đại; không suy rộng kết quả chuyển đổi trường cho mọi năm trong quá khứ mà không kiểm tra hệ lịch.

## 9. Tự thực hành

1. Đặt `2023, Calendar.APRIL, 31` ở chế độ lenient và dự đoán kết quả `2023-05-01`; thử lại non-lenient và xác nhận lỗi xuất hiện khi tính.
2. Với `2024, Calendar.JANUARY, 32`, giải thích vì sao chuẩn hóa đi sang 01/02, không chỉ đổi trường ngày thành 31.
3. Thử nhận tháng người dùng bằng số 2 nhưng truyền trực tiếp vào trường MONTH. Nhận diện rằng Calendar hiểu đó là tháng 3; đây là lỗi quy ước đầu vào mà leniency không tự sửa đúng ý người dùng.
4. Thay thứ tự trong ví dụ `lateSwitch` để non-lenient được chọn trước khi đọc. Xác nhận lúc này bộ trường 29/02/2023 bị từ chối thay vì đã chuẩn hóa thành 01/03.

Tham khảo: [Calendar — leniency và cách đặt/đọc trường](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Calendar.html) và [GregorianCalendar](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/GregorianCalendar.html) trong Java SE 21.
