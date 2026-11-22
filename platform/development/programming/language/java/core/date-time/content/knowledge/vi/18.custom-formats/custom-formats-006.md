# parseBest() để chọn kiểu kết quả phù hợp

## 1. Một bộ định dạng, nhưng dữ liệu có thể giàu thông tin khác nhau

Giả sử một chức năng nhận các chuỗi sau:

```text
2026-10-25T09:05
2026-10-25T09:05+07:00
2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]
```

Cả ba đều có ngày và giờ. Chuỗi đầu chỉ có thời gian địa phương; chuỗi thứ hai bổ sung độ lệch UTC; chuỗi thứ ba còn có mã múi giờ vùng. Nếu luôn ép về `LocalDateTime`, phần độ lệch và múi giờ có thể bị bỏ. Nếu luôn yêu cầu `ZonedDateTime`, đầu vào chỉ có ngày-giờ địa phương lại không đủ dữ liệu để tạo kết quả ấy.

`DateTimeFormatter.parseBest()` giải quyết nhu cầu này: **đọc chuỗi bằng một bộ định dạng rồi thử các cách tạo kiểu kết quả theo thứ tự do bạn quy định**.

Tên `Best` không có nghĩa Java tự chấm điểm để chọn “kiểu chính xác nhất”. Bạn định nghĩa mức ưu tiên bằng danh sách truy vấn; kết quả đầu tiên tạo được sẽ được trả về.

## 2. Chữ ký và cách đọc lời gọi

Dạng sử dụng thường gặp:

```java
TemporalAccessor result = formatter.parseBest(
        text,
        ZonedDateTime::from,
        LocalDateTime::from);
```

Các tham chiếu phương thức `ZonedDateTime::from` và `LocalDateTime::from` đóng vai trò các truy vấn thời gian (`TemporalQuery`). Mỗi truy vấn cố tạo một giá trị cụ thể từ dữ liệu đã đọc và giải quyết.

Quy trình có thể hình dung như sau:

```text
Chuỗi
  |
  v
Đọc và giải quyết bằng formatter
  |
  +-- Lỗi cú pháp/ngày giờ/phần dư --> DateTimeParseException
  |
  v
Thử ZonedDateTime::from
  |
  +-- Thành công --> trả ZonedDateTime
  |
  v
Thử LocalDateTime::from
  |
  +-- Thành công --> trả LocalDateTime
  |
  v
Không truy vấn nào tạo được kết quả --> DateTimeParseException
```

Các truy vấn không chọn lại mẫu văn bản. Bộ định dạng đã xác định văn phạm đầu vào trước đó. Chẳng hạn, `parseBest` trên một bộ định dạng ISO không tự nhận `25/10/2026` bằng cách đoán một pattern khác.

Cần ít nhất hai truy vấn; chỉ truyền một truy vấn gây `IllegalArgumentException`. Khi chỉ muốn đúng một kiểu, dùng `formatter.parse(text, LocalDateTime::from)` hoặc `LocalDateTime.parse(text, formatter)` sẽ diễn tả mục tiêu rõ hơn.

## 3. Vì sao thứ tự truy vấn quyết định việc giữ thông tin?

Với chuỗi có múi giờ, cả hai cách tạo sau đều có thể thành công:

- `ZonedDateTime::from`: giữ ngày, giờ và múi giờ.
- `LocalDateTime::from`: lấy phần ngày-giờ địa phương, không giữ múi giờ trong kết quả.

Nếu đặt `LocalDateTime::from` trước, phương thức trả ngay kiểu đó và không thử truy vấn phía sau. Nó không tiếp tục tìm một kết quả có nhiều thông tin hơn.

Vì vậy, với yêu cầu ưu tiên giữ múi giờ, đặt:

```java
formatter.parseBest(text, ZonedDateTime::from, LocalDateTime::from);
```

Không đặt ngược chỉ vì `LocalDateTime` có vẻ là kiểu “cơ bản” hơn.

Tương tự, khi dùng một bộ định dạng cho phép cả ngày đơn lẻ và ngày kèm giờ, thường ưu tiên `LocalDateTime::from` trước `LocalDate::from` nếu muốn giữ giờ khi có. `LocalDate::from` có thể thành công trên dữ liệu có cả giờ, nên đặt nó trước có thể làm phần giờ biến mất trong kết quả.

Thứ tự phải phản ánh hợp đồng của chức năng, không nhất thiết là một danh sách toàn bộ các lớp ngày giờ Java theo một thứ bậc cố định.

## 4. Kiểu kết quả không phải bản ghi nguyên văn cú pháp nguồn

Một điểm dễ nhầm: `ZonedDateTime` không bắt buộc phải dùng múi giờ vùng như `Asia/Ho_Chi_Minh`. Nó cũng có thể dùng múi giờ có độ lệch cố định như `+07:00`.

Do đó, với danh sách `ZonedDateTime::from, LocalDateTime::from`:

| Đầu vào | Kiểu đầu tiên tạo được | Múi giờ trong kết quả |
|---|---|---|
| `2026-10-25T09:05` | `LocalDateTime` | Không có |
| `2026-10-25T09:05+07:00` | `ZonedDateTime` | `+07:00`, độ lệch cố định |
| `2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]` | `ZonedDateTime` | `Asia/Ho_Chi_Minh`, múi giờ vùng |

Không được thấy kiểu `ZonedDateTime` rồi kết luận chuỗi gốc chắc chắn chứa phần mã vùng trong ngoặc vuông.

Nếu yêu cầu đầu ra chỉ phân biệt “có độ lệch UTC” với “không có độ lệch”, có thể chọn `OffsetDateTime::from` và `LocalDateTime::from`. Nhưng nếu dữ liệu nguồn chứa mã vùng, một kết quả `OffsetDateTime` không giữ mã vùng ấy. Cần quyết định thông tin nào phải được bảo toàn trước khi viết danh sách truy vấn.

Đặt `ZonedDateTime::from` rồi `OffsetDateTime::from` cũng không tạo quy tắc “có mã vùng thì Zoned, chỉ có offset thì Offset”: đầu vào chỉ có offset đã có thể thành công ngay ở truy vấn Zoned đầu tiên. Nếu thật sự cần phân loại theo thành phần nguồn, phải kiểm tra thông tin nguồn phù hợp thay vì chỉ dựa vào thứ tự hai truy vấn này.

Những cấu hình như múi giờ ghi đè hoặc giá trị mặc định của bộ định dạng còn có thể bổ sung thông tin không được gõ trực tiếp. Kết quả phản ánh dữ liệu sau phân tích và giải quyết; nó không tự giữ lịch sử từng thành phần đầu vào.

## 5. Xử lý TemporalAccessor an toàn

`parseBest` trả về `TemporalAccessor` vì các truy vấn có thể tạo những kiểu khác nhau. Sau khi gọi, dùng `instanceof` theo những kiểu bạn đã cho phép:

```java
if (result instanceof ZonedDateTime zoned) {
    // Xử lý giá trị có múi giờ.
} else if (result instanceof LocalDateTime local) {
    // Xử lý ngày-giờ địa phương, chưa xác định một thời điểm duy nhất.
}
```

Các nhánh trên chỉ là cấu trúc minh họa. Trong chương trình thực tế, nhánh có múi giờ có thể chuyển sang `Instant` nếu cần một thời điểm; nhánh địa phương cần thêm chính sách múi giờ của chức năng trước khi làm việc đó.

Không ép kiểu thẳng sang `ZonedDateTime` chỉ vì nó đứng đầu danh sách: chính ý nghĩa của `parseBest` là truy vấn ấy có thể thất bại và một kiểu khác được trả về. Ép kiểu thiếu kiểm tra có thể gây `ClassCastException` sau một lần phân tích vốn đã thành công.

Các truy vấn dùng cho phương thức này phải tạo kết quả thuộc `TemporalAccessor`; tham chiếu `from` của các lớp ngày giờ tiêu chuẩn là lựa chọn thông dụng. Nó không phải phương thức tổng quát để thử các phép chuyển đổi tùy ý sang chuỗi hoặc số.

## 6. Chương trình chạy đầy đủ

Lưu mã sau vào `ParseBestDemo.java`. Chương trình dùng Java 17 trở lên và không cần thư viện ngoài.

```java
import java.time.LocalDateTime;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.temporal.TemporalAccessor;

public class ParseBestDemo {
    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ISO_DATE_TIME;

    public static void main(String[] args) {
        inspect("2026-10-25T09:05");
        inspect("2026-10-25T09:05+07:00");
        inspect("2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]");
        inspect("2026-10-25");
        inspect("2026-02-30T09:05");
        inspect("2026-10-25T09:05junk");

        TemporalAccessor firstLocal = FORMAT.parseBest(
                "2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh]",
                LocalDateTime::from, ZonedDateTime::from);
        System.out.println("reversed="
                + firstLocal.getClass().getSimpleName() + " " + firstLocal);

        LocalDateTime knownType = FORMAT.parse(
                "2026-10-25T09:05", LocalDateTime::from);
        System.out.println("singleQuery=" + knownType);

        try {
            FORMAT.parseBest("2026-10-25T09:05", LocalDateTime::from);
        } catch (IllegalArgumentException e) {
            System.out.println("oneQuery=IllegalArgumentException");
        }
    }

    private static void inspect(String text) {
        try {
            TemporalAccessor parsed = FORMAT.parseBest(
                    text, ZonedDateTime::from, LocalDateTime::from);

            if (parsed instanceof ZonedDateTime zoned) {
                System.out.println("ZonedDateTime=" + zoned
                        + " zone=" + zoned.getZone());
            } else if (parsed instanceof LocalDateTime local) {
                System.out.println("LocalDateTime=" + local);
            } else {
                throw new IllegalStateException("unexpected result type");
            }
        } catch (DateTimeParseException e) {
            System.out.println("ERROR=" + text);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac ParseBestDemo.java
java ParseBestDemo
```

Kết quả chuẩn đã kiểm chứng:

```text
LocalDateTime=2026-10-25T09:05
ZonedDateTime=2026-10-25T09:05+07:00 zone=+07:00
ZonedDateTime=2026-10-25T09:05+07:00[Asia/Ho_Chi_Minh] zone=Asia/Ho_Chi_Minh
ERROR=2026-10-25
ERROR=2026-02-30T09:05
ERROR=2026-10-25T09:05junk
reversed=LocalDateTime 2026-10-25T09:05
singleQuery=2026-10-25T09:05
oneQuery=IllegalArgumentException
```

`ERROR` là nhãn của chương trình khi bắt `DateTimeParseException`, không phải thông điệp mặc định của Java. Các trường hợp kiểm tra có mục đích khác nhau:

- Ngày đơn lẻ bị từ chối vì `ISO_DATE_TIME` cần phần ngày và giờ; thêm truy vấn `LocalDate::from` sẽ không tự làm bộ định dạng này nhận được ngày đơn lẻ.
- Ngày 30/02 bị từ chối khi giải quyết trường theo lịch.
- Phần `junk` bị từ chối vì `parseBest` yêu cầu xử lý hết chuỗi.
- Dòng `reversed` cho thấy việc đảo thứ tự làm mất thông tin múi giờ trong kiểu kết quả.
- Dòng cuối phân biệt lỗi cấu hình không đủ số truy vấn với lỗi dữ liệu đầu vào.

Các trường hợp vùng/độ lệch trong chương trình được chọn nhất quán. Việc xử lý chuỗi chứa độ lệch mâu thuẫn với múi giờ là một hợp đồng riêng của bước giải quyết ngày giờ; `parseBest` không tự biến việc thử nhiều kiểu thành phép xác nhận rằng mọi thông tin nguồn đều nhất quán theo chính sách nghiệp vụ mong muốn.

## 7. Những giới hạn cần giữ rõ

### Không tự thêm dữ liệu khi thiếu

Nếu đầu vào chỉ có ngày-giờ địa phương, không có offset hoặc múi giờ, không nên tự hiểu nó là UTC chỉ vì truy vấn Zoned không thành công. Kết quả `LocalDateTime` chưa xác định một thời điểm duy nhất. Quy tắc bổ sung múi giờ thuộc về lớp xử lý có ngữ cảnh phù hợp.

### Không phải cơ chế kiểm tra mọi yêu cầu nghiệp vụ

Phân tích thành công không chứng minh lịch hẹn nằm trong giờ làm việc, hạn chót ở tương lai hay múi giờ thuộc danh sách được cho phép. Những điều kiện ấy phải kiểm tra trên kết quả sau khi biết kiểu dữ liệu.

### Không giữ nguyên cách viết

`toString()` của kết quả có thể lược giây bằng 0 hoặc dùng cách thể hiện chuẩn của kiểu. Nếu muốn giữ chuỗi nguồn cho mục đích đối chiếu, phải lưu nó riêng. Chọn một kiểu đủ thông tin không đồng nghĩa bảo toàn cách viết từng ký tự.

### Không mở rộng cú pháp bằng cách thêm truy vấn

Muốn nhận thêm một cấu trúc văn bản, cần sửa bộ định dạng hoặc thiết kế các bộ định dạng riêng có hợp đồng rõ ràng. Thêm kiểu vào danh sách chỉ mở rộng cách tạo kết quả từ cùng dữ liệu đã đọc.

## 8. Tự thực hành

1. Thêm đầu vào `2026-10-25T02:05Z`. Với thứ tự đang dùng, nó trả về `ZonedDateTime`; múi giờ kết quả là `Z`, không phải một mã vùng.
2. Đặt `LocalDateTime::from` trước và quan sát cùng đầu vào trở thành ngày-giờ địa phương, không còn độ lệch trong kiểu kết quả.
3. Chỉ giữ truy vấn Zoned bằng `FORMAT.parse(text, ZonedDateTime::from)`: đầu vào không có múi giờ/offset sẽ không tạo được kết quả ấy. Cách gọi này phù hợp khi hợp đồng bắt buộc kiểu có múi giờ.

Trước mỗi lần dùng `parseBest`, hãy xác định riêng văn phạm đầu vào, thứ tự ưu tiên kết quả và cách xử lý khi thông tin ít hơn yêu cầu của chức năng. Ba lựa chọn rõ ràng này giúp phương thức giữ được đúng thông tin thay vì âm thầm thu hẹp dữ liệu.

Tham khảo: [DateTimeFormatter — parseBest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parseBest(java.lang.CharSequence,java.time.temporal.TemporalQuery...)) và [ZonedDateTime — from](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZonedDateTime.html#from(java.time.temporal.TemporalAccessor)) trong Java SE 21.
