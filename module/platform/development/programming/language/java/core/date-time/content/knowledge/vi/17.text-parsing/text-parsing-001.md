# `parse()` và yêu cầu dữ liệu phù hợp kiểu đích

## 1. Đọc được chữ chưa có nghĩa là tạo được đối tượng

Khi nhận một ô nhập liệu, dòng CSV hoặc trường JSON chứa ngày giờ, chương trình ban đầu chỉ có **chuỗi ký tự**. `parse()` phân tích chuỗi theo quy ước đã chọn và tạo đối tượng thời gian có kiểu cụ thể. Lựa chọn kiểu đích chính là lựa chọn thông tin mà ứng dụng cần lưu: ngày, giờ, ngày–giờ địa phương, hay một thời điểm xác định trên dòng thời gian.

Ví dụ, `2025-06-10` đủ để tạo `LocalDate`, nhưng không đủ để tạo `LocalDateTime` vì chưa có giờ. Chuỗi `2025-06-10T09:15:00` có ngày và giờ nhưng vẫn chưa xác định độ lệch UTC để tạo `OffsetDateTime`. Không thể chữa dữ liệu thiếu bằng cách đổi tên phương thức gọi.

Hãy kiểm tra đồng thời ba yếu tố:

```text
Chuỗi thực tế → bộ định dạng đọc được gì? → kiểu đích cần gì?
                    ↓                          ↓
            cú pháp và giá trị hợp lệ   đủ thông tin để tạo đối tượng
```

Theo [Java SE 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html), việc phân tích gồm đọc các trường rồi phân giải chúng thành giá trị ngày giờ. Việc truy vấn kết quả sang kiểu cụ thể là một yêu cầu bổ sung. Bởi vậy, chọn đúng mẫu ký tự chỉ giải quyết một phần bài toán.

## 2. Chọn kiểu đích trước khi chọn cách phân tích

Bảng dưới dùng các chuỗi ví dụ tự xây dựng cho những lời gọi `parse(text)` mặc định phổ biến:

| Kiểu đích | Thông tin cần có trong ví dụ | Chuỗi phù hợp |
| --- | --- | --- |
| `LocalDate` | Một ngày đầy đủ | `2025-06-10` |
| `LocalTime` | Giờ trong ngày | `09:15:00` |
| `LocalDateTime` | Ngày và giờ địa phương | `2025-06-10T09:15:00` |
| `OffsetTime` | Giờ và độ lệch UTC | `09:15:00+07:00` |
| `OffsetDateTime` | Ngày, giờ và độ lệch UTC | `2025-06-10T09:15:00+07:00` |
| `ZonedDateTime` | Ngày–giờ với thông tin vùng thời gian phù hợp | `2025-06-10T09:15:00+07:00[Asia/Ho_Chi_Minh]` |
| `Instant` | Một thời điểm xác định; ví dụ biểu diễn theo UTC | `2025-06-10T02:15:00Z` |
| `YearMonth` | Năm và tháng | `2025-06` |

Các chuỗi trên là ví dụ, không phải danh sách đầy đủ mọi cách viết được phép. Chẳng hạn, giờ có thể không cần phần giây nếu bộ định dạng hỗ trợ. `ZonedDateTime.parse()` cũng nhận ví dụ chỉ có độ lệch `+07:00` mà không có tên vùng: kết quả khi đó dùng chính độ lệch cố định làm vùng, không tự suy ra `Asia/Ho_Chi_Minh`.

`LocalDateTime` không chứa múi giờ; muốn xác định một thời điểm trên dòng thời gian phải có thêm độ lệch hoặc vùng thời gian. Đây là sự khác biệt về thông tin của kiểu dữ liệu, được nêu tại [Java SE 21 — LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html).

Đừng chọn `Instant` chỉ vì chuỗi nhìn có vẻ giống thời gian ghi nhật ký. Nếu dữ liệu nguồn chỉ là giờ địa phương, cần biết quy ước vùng thời gian của nguồn trước khi chuyển thành thời điểm. `parse()` mặc định không tự lấy vùng của máy để bù cho thông tin đó.

## 3. Hai cách gọi thường gặp

### Dùng quy ước mặc định của kiểu

Các lệnh sau là mã minh họa đặt trong một phương thức:

```java
LocalDate date = LocalDate.parse("2025-06-10");
LocalDateTime dateTime = LocalDateTime.parse("2025-06-10T09:15:00");
```

Đầu vào cần tuân theo định dạng mà lời gọi mặc định chấp nhận. Vì vậy `LocalDate.parse("10/06/2025")` không thành công chỉ vì người đọc hiểu đó là ngày 10 tháng 6.

### Cung cấp `DateTimeFormatter`

Khi hợp đồng đầu vào dùng ngày/tháng/năm, hãy biểu diễn rõ quy tắc đó:

```java
// Minh họa trong một phương thức, với import java.time.* và java.time.format.*.
DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("dd/MM/uuuu", java.util.Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
LocalDate date = LocalDate.parse("10/06/2025", formatter);
```

`dd` là ngày trong tháng, `MM` là tháng, `uuuu` là năm. Chữ hoa/thường có ý nghĩa: `mm` là phút, không phải tháng; `YYYY` là năm theo tuần, không thay thế cho năm lịch. Với ngày ISO thông thường và chế độ chặt chẽ, dùng `uuuu` giúp tránh nhu cầu phân giải năm trong kỷ nguyên của `yyyy` khi không cung cấp kỷ nguyên.

`ResolverStyle.STRICT` yêu cầu ngày có thật. Việc tạo mẫu bằng `ofPattern()` mặc định dùng `SMART`, có thể điều chỉnh một số ngày về cuối tháng. Vì thế, kiểm tra được dấu `/` và số chữ số không đồng nghĩa đã từ chối `31/02/2025`. Nếu có tên tháng dạng chữ, còn cần chọn `Locale` phù hợp với ngôn ngữ nguồn; không đoán dựa vào máy đang chạy.

## 4. Chương trình chạy đầy đủ: cú pháp, ngày hợp lệ và thiếu thông tin

Lưu mã vào `ParseTargetDemo.java`. Chương trình dùng Java 17 trở lên và không có thư viện ngoài:

```java
import java.time.*;
import java.time.format.*;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;
import java.util.function.Supplier;

public class ParseTargetDemo {
    private static void show(String label, Supplier<?> action) {
        try {
            System.out.println(label + " = " + action.get());
        } catch (DateTimeParseException ex) {
            System.out.println(label + " = DateTimeParseException");
        }
    }

    public static void main(String[] args) {
        show("date", () -> LocalDate.parse("2024-02-29"));
        show("time", () -> LocalTime.parse("09:15:00"));
        show("date-time", () -> LocalDateTime.parse("2025-06-10T09:15:00"));
        show("offset", () -> OffsetDateTime.parse("2025-06-10T09:15:00+07:00"));
        show("instant", () -> Instant.parse("2025-06-10T02:15:00Z"));

        show("date-only to date-time", () -> LocalDateTime.parse(
                "2025-06-10", DateTimeFormatter.ISO_LOCAL_DATE));
        show("no offset", () -> OffsetDateTime.parse(
                "2025-06-10T09:15:00", DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        show("wrong syntax", () -> LocalDate.parse("10/06/2025"));
        show("trailing space", () -> LocalDate.parse("2025-06-10 "));

        DateTimeFormatter strict = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        show("custom valid", () -> LocalDate.parse("29/02/2024", strict));
        show("custom invalid", () -> LocalDate.parse("31/02/2025", strict));
        DateTimeFormatter smart = DateTimeFormatter
                .ofPattern("dd/MM/uuuu", Locale.ROOT);
        show("smart adjusted", () -> LocalDate.parse("31/02/2025", smart));

        TemporalAccessor fields = DateTimeFormatter.ISO_LOCAL_DATE_TIME
                .parse("2025-06-10T09:15:00");
        System.out.println("extract date = " + LocalDate.from(fields));
        System.out.println("extract time = " + LocalTime.from(fields));
        show("explicit date projection", () -> LocalDate.parse(
                "2025-06-10T09:15:00", DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        System.out.println("offset as zone = " + ZonedDateTime
                .parse("2025-06-10T09:15:00+07:00").getZone());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ParseTargetDemo.java
java ParseTargetDemo
```

Kết quả:

```text
date = 2024-02-29
time = 09:15
date-time = 2025-06-10T09:15
offset = 2025-06-10T09:15+07:00
instant = 2025-06-10T02:15:00Z
date-only to date-time = DateTimeParseException
no offset = DateTimeParseException
wrong syntax = DateTimeParseException
trailing space = DateTimeParseException
custom valid = 2024-02-29
custom invalid = DateTimeParseException
smart adjusted = 2025-02-28
extract date = 2025-06-10
extract time = 09:15
explicit date projection = 2025-06-10
offset as zone = +07:00
```

Hàm `show` cố ý chỉ in tên ngoại lệ để kết quả dễ so sánh giữa các JDK; nó là cách trình diễn, không phải chính sách xử lý lỗi cho ứng dụng. `Supplier<?>` chỉ giúp truyền thao tác cần chạy vào hàm này.

### Đọc kết quả theo nguyên nhân

- `wrong syntax`: chuỗi dùng `/`, trong khi bộ định dạng mặc định cần dạng ngày ISO với `-`.
- `trailing space`: dấu cách cuối chuỗi chưa được tiêu thụ; lời gọi phân tích toàn bộ chuỗi không mặc nhiên bỏ qua nó.
- `custom invalid`: mẫu đọc được các con số nhưng chế độ `STRICT` từ chối ngày 31 tháng 2.
- `date-only to date-time`: `ISO_LOCAL_DATE` đọc được ngày, nhưng kết quả thiếu giờ để tạo `LocalDateTime`.
- `no offset`: `ISO_LOCAL_DATE_TIME` đọc được ngày–giờ, nhưng kết quả thiếu độ lệch UTC để tạo `OffsetDateTime`.

Ba nhóm đầu liên quan đến cú pháp hoặc tính hợp lệ của ngày; hai nhóm cuối cho thấy **đúng định dạng vẫn có thể thiếu dữ liệu cho kiểu đích**. Bắt cùng một `DateTimeParseException` không có nghĩa mọi trường hợp có cùng nguyên nhân.

Các dòng in giờ không còn `:00` là cách đối tượng chọn biểu diễn chuỗi khi phần giây bằng 0. Dữ liệu đã tạo đúng, nhưng không có cam kết rằng `parsed.toString()` giống nguyên văn đầu vào. Muốn xuất lại theo một định dạng cố định, hãy gọi `format()` với bộ định dạng đầu ra phù hợp.

## 5. `DateTimeFormatter.parse()` và việc lấy kiểu cụ thể

Trong chương trình, `DateTimeFormatter.ISO_LOCAL_DATE_TIME.parse(text)` trả về một `TemporalAccessor`. Có thể hiểu đây là giao diện để truy cập những trường thời gian đã phân tích và phân giải; không nên ép kiểu trực tiếp nó thành `LocalDateTime` bằng phép cast.

Ta đã dùng `LocalDate.from(fields)` và `LocalTime.from(fields)` để lấy riêng ngày và giờ. Có thể gộp bước phân tích và truy vấn bằng cách viết sau trong một phương thức:

```java
LocalDateTime value = DateTimeFormatter.ISO_LOCAL_DATE_TIME.parse(
        "2025-06-10T09:15:00", LocalDateTime::from);
```

`LocalDateTime::from` chỉ rõ kiểu mong muốn. Nếu dữ liệu đã phân tích không đủ thông tin cho truy vấn ấy, thao tác vẫn thất bại.

Một chi tiết đáng quan sát trong chương trình là `explicit date projection`: `LocalDate.parse(text, ISO_LOCAL_DATE_TIME)` thành công với chuỗi có cả ngày và giờ, bởi bộ định dạng đã đọc hết chuỗi rồi kiểu đích lấy phần ngày. Trái lại, `LocalDate.parse(text)` mặc định sẽ không tự chấp nhận phần `T09:15:00` còn dư. Vì vậy, không thể kết luận rằng mọi `parse()` của kiểu đơn giản đều tự bỏ phần dữ liệu thừa.

Việc lấy riêng ngày làm mất thông tin giờ ở giá trị kết quả. Chỉ chọn cách đó khi hợp đồng nghiệp vụ thực sự cần một ngày; nếu cần bảo toàn thời điểm giao dịch, phải giữ kiểu có đủ thông tin.

## 6. Bổ sung dữ liệu thiếu phải là quyết định tường minh

Nếu biểu mẫu chỉ hỏi ngày nhưng nghiệp vụ quy định cuộc hẹn bắt đầu lúc 09:00, hãy phân tích ngày rồi bổ sung giờ một cách đọc được:

```java
// Minh họa trong một phương thức.
LocalDate date = LocalDate.parse("2025-06-10");
LocalDateTime appointment = date.atTime(9, 0);
OffsetDateTime withOffset = appointment.atOffset(ZoneOffset.of("+07:00"));
Instant instant = withOffset.toInstant();
```

Ở đây 09:00 và `+07:00` đến từ quy định đã biết của ứng dụng. Chúng không được suy ra từ chuỗi ngày. Không tự chọn nửa đêm hoặc vùng mặc định của máy chỉ để tránh ngoại lệ: cùng một chuỗi thiếu dữ liệu có thể có nhiều cách diễn giải hợp lệ về kỹ thuật nhưng khác nhau về nghiệp vụ.

Bộ định dạng cũng có thể được cấu hình để cung cấp giá trị mặc định, nhưng đó vẫn là một quy tắc mà người thiết kế phải quyết định. Trước khi dùng cơ chế đó, hãy xác định rõ trường nào nguồn thật sự cung cấp và trường nào được ứng dụng bổ sung.

## 7. Cách xử lý lỗi và tự kiểm tra

Khi đầu vào do người dùng cung cấp không phân tích được, có thể bắt `DateTimeParseException` tại ranh giới nhập liệu rồi báo định dạng cần nhập. `getParsedString()` và `getErrorIndex()` hỗ trợ chẩn đoán; vị trí lỗi không thay thế việc kiểm tra thiếu trường cho kiểu đích. Không phụ thuộc vào nguyên văn thông báo ngoại lệ để phân loại nghiệp vụ vì thông điệp có thể thay đổi.

Không dùng `null` hoặc “thời gian hiện tại” làm giá trị thay thế âm thầm cho mọi lỗi phân tích. Đầu vào vắng mặt, chuỗi sai định dạng và ngày không tồn tại là những tình huống khác nhau cần được mô hình hóa theo yêu cầu ứng dụng. Mẫu định dạng do lập trình viên viết sai cũng cần được sửa trong cấu hình/mã, thay vì báo cho người dùng rằng ngày họ nhập sai.

Trước khi hoàn tất một lời gọi `parse()`, tự trả lời:

1. Chuỗi được quy định theo định dạng nào, có cho phép khoảng trắng hoặc tên tháng theo ngôn ngữ nào không?
2. Bộ định dạng có đọc toàn bộ chuỗi và kiểm tra ngày theo mức chặt chẽ cần thiết không?
3. Kết quả có đủ dữ liệu cho kiểu đích, đặc biệt là giờ, độ lệch và vùng thời gian không?
4. Nếu lấy riêng một phần hoặc bổ sung mặc định, việc mất/bù thông tin đó có được yêu cầu nghiệp vụ cho phép không?

Bài tập: thay `ISO_LOCAL_DATE_TIME` bằng `ISO_LOCAL_DATE` trong ví dụ truy vấn `LocalDateTime::from` và chỉ truyền `2025-06-10`. Dự đoán rằng chuỗi ngày được đọc đúng nhưng truy vấn đích thất bại vì thiếu giờ. Sau đó sửa bằng `LocalDate.parse(text).atTime(9, 0)` và giải thích rõ 09:00 đến từ quy định của ứng dụng, không đến từ dữ liệu nhập.
