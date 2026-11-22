# Thành phần tùy chọn và nhiều dạng đầu vào

## 1. Tùy chọn một phần khác với chọn một trong nhiều cú pháp

Một hệ thống có thể nhận cả ngày đơn lẻ `2026-10-25` và ngày kèm giờ `2026-10-25T09:05`. Hai dạng này chia sẻ phần ngày; phần giờ là phần mở rộng có thể vắng mặt. Đây là trường hợp phù hợp với **thành phần tùy chọn** của `DateTimeFormatterBuilder`.

Một hệ thống khác nhận `2026-10-25` hoặc `25/10/2026`. Thứ tự trường và dấu phân cách khác nhau: đó là **hai cú pháp thay thế**, không đơn thuần là thêm hoặc bớt một hậu tố.

Phân biệt hai nhu cầu ngay từ đầu giúp tránh tạo một bộ định dạng nhận những tổ hợp ngoài dự kiến hoặc âm thầm bỏ mất thông tin.

| Nhu cầu | Cách thể hiện phù hợp |
|---|---|
| Có thể thêm giờ sau một ngày bắt buộc | Nhóm tùy chọn |
| Có thể thêm giây sau giờ và phút | Nhóm tùy chọn lồng nhau |
| Cùng cú pháp nhưng có thể tạo nhiều kiểu kết quả | `parseBest` với thứ tự truy vấn phù hợp |
| Hai cách viết ngày có cấu trúc khác nhau | Các bộ định dạng riêng và quy tắc chọn rõ ràng |
| Thiếu giờ được quy ước là 00:00 | Giá trị mặc định được cấu hình tường minh |

## 2. optionalStart và optionalEnd tạo một nhóm

Một nhóm tùy chọn bắt đầu bằng `optionalStart()` và kết thúc bằng `optionalEnd()`. Những phần bên trong được xem như một khối có thể có hoặc không có khi đọc chuỗi.

Ví dụ cấu trúc ngày bắt buộc, sau đó tùy chọn `T` cùng giờ/phút:

```java
DateTimeFormatter formatter = new DateTimeFormatterBuilder()
        .append(DateTimeFormatter.ISO_LOCAL_DATE)
        .optionalStart()
            .appendLiteral('T')
            .appendValue(ChronoField.HOUR_OF_DAY, 2)
            .appendLiteral(':')
            .appendValue(ChronoField.MINUTE_OF_HOUR, 2)
        .optionalEnd()
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

Đoạn trên là khai báo bộ định dạng; các import và cách sử dụng đầy đủ có ở phần 7.

Nhóm chứa cả dấu `T`, giờ, dấu `:` và phút. Vì thế, dạng không có giờ là ngày đơn lẻ, không phải ngày còn treo một dấu `T` phía sau.

Đặt dấu phân cách ở sai vị trí là một lỗi phổ biến:

```java
.appendLiteral('T')
.optionalStart()
    // Các trường giờ/phút...
.optionalEnd()
```

Đây chỉ là đoạn minh họa cấu trúc sai cho yêu cầu đang xét: `T` đã nằm ngoài nhóm nên trở thành bắt buộc. Không dùng đoạn này nếu muốn nhận ngày đơn lẻ không có `T`.

Để ghép một bộ định dạng con thành phần tùy chọn, có thể dùng `appendOptional(childFormatter)` thay cho việc tự bọc bằng một cặp nhóm. Vẫn cần xác định đúng dấu phân cách nào thuộc nhóm.

## 3. Lồng nhóm để diễn đạt quan hệ phụ thuộc

Nếu cho phép giây, cấu trúc mong muốn là:

```text
ngày [ T giờ:phút [ :giây ] ]
```

Dấu ngoặc vuông trong sơ đồ chỉ phần tùy chọn, không phải ký tự người dùng nhập. Nhóm giây nằm trong nhóm giờ nên chỉ có thể xuất hiện sau giờ và phút.

Các đầu vào hợp lệ:

```text
2026-10-25
2026-10-25T09:05
2026-10-25T09:05:30
```

Các đầu vào như `2026-10-25T`, `2026-10-25T09` hoặc `2026-10-25T09:05:` không phải những cách “bỏ trống phần tùy chọn” hợp lệ. Khi đọc toàn bộ chuỗi, nhóm không hoàn chỉnh sẽ để lại phần dư hoặc gây lỗi; không được coi dấu phân cách thừa là dữ liệu có thể bỏ qua.

Dùng `optionalEnd()` theo thứ tự đóng nhóm trong trước rồi nhóm ngoài. Đóng một nhóm khi không có nhóm nào đang mở gây lỗi dựng bộ định dạng. Dù `toFormatter()` có thể hoàn tất các nhóm đang mở, nên viết cặp mở/đóng rõ ràng để người đọc kiểm tra ranh giới.

Với pattern, cấu trúc tương ứng cho các ví dụ năm bốn chữ số có thể viết:

```java
DateTimeFormatter.ofPattern("uuuu-MM-dd['T'HH:mm[:ss]]", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

Builder phù hợp khi muốn thể hiện từng nhóm và từng trường bằng API. Không cần dùng pattern lẫn builder cho cùng một cấu trúc chỉ để tăng số lượng cách viết.

## 4. Cú pháp tùy chọn không tự tạo đủ trường cho mọi kiểu kết quả

Một bộ định dạng có thể đọc được ngày đơn lẻ nhưng `LocalDateTime.parse` vẫn không tạo được kết quả nếu thiếu giờ/phút. Thành phần tùy chọn cho phép dữ liệu vắng mặt; nó không tự quyết định rằng thiếu giờ nghĩa là nửa đêm.

Khi muốn giữ khác biệt giữa “chỉ có ngày” và “có cả giờ”, dùng:

```java
TemporalAccessor result = formatter.parseBest(
        text, LocalDateTime::from, LocalDate::from);
```

`parseBest` đọc hết chuỗi bằng **một bộ định dạng**, rồi thử các truy vấn chuyển sang kiểu kết quả theo thứ tự đã cho. Cần ít nhất hai truy vấn và nên đặt kiểu nhiều thông tin hơn trước.

Với ngày-giờ, `LocalDateTime::from` thành công nên giữ cả giờ. Với ngày đơn lẻ, truy vấn đầu không đủ dữ liệu; `LocalDate::from` có thể thành công.

Nếu đảo thứ tự thành `LocalDate::from, LocalDateTime::from`, ngày-giờ cũng có thể chuyển ngay thành `LocalDate`, làm mất phần giờ ở giá trị trả về. Đó là kết quả của thứ tự truy vấn, không phải Java nhận diện sai chuỗi.

`parseBest` không phải chức năng chọn giữa nhiều pattern không liên quan. Nó chọn **kiểu kết quả từ dữ liệu đã được bộ định dạng đọc**, không tự thử `dd/MM/uuuu` khi bộ định dạng chỉ mô tả `uuuu-MM-dd`.

## 5. Giá trị mặc định phải là một quyết định có ý nghĩa

Nếu quy định của ứng dụng là ngày không kèm giờ được xem là `00:00`, có thể thêm giá trị mặc định sau khi ghép cấu trúc:

```java
DateTimeFormatter withMidnight = new DateTimeFormatterBuilder()
        .append(formatter)
        .parseDefaulting(ChronoField.HOUR_OF_DAY, 0)
        .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
        .toFormatter(Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

`parseDefaulting` bổ sung trường khi trường đó chưa có; nó không ghi đè giờ thực sự đã được đọc. Đặt các mặc định sau các phần nhập liệu để tránh chúng tham gia quá sớm rồi xung đột với giá trị có trong đầu vào.

Cần hiểu tác động: sau khi mặc định, dữ liệu “không cung cấp giờ” và dữ liệu “người dùng cung cấp đúng 00:00” có thể cho cùng `LocalDateTime`. Nếu hai trường hợp có ý nghĩa nghiệp vụ khác nhau, hãy giữ kiểu ngày đơn lẻ hoặc lưu thông tin nguồn riêng.

Giá trị mặc định còn không cung cấp múi giờ. `LocalDateTime` lúc 00:00 chưa phải một thời điểm duy nhất trên trục thời gian; không tự suy ra UTC hoặc múi giờ máy chạy từ việc thiếu giờ.

## 6. Nhiều cú pháp thay thế: giới hạn và thứ tự phải rõ ràng

Đối với hai cách viết `uuuu-MM-dd` và `dd/MM/uuuu`, có thể giữ hai bộ định dạng nghiêm ngặt rồi thử trong một thứ tự cố định. Chỉ bắt `DateTimeParseException` của từng lần thử để chuyển sang cú pháp tiếp theo; nếu tất cả đều thất bại, báo rằng không có dạng đầu vào được hỗ trợ nào khớp.

Không dùng một danh sách rất lớn các pattern để “đoán được càng nhiều càng tốt”. Chuỗi như `03/04/2026` mơ hồ giữa ngày/tháng và tháng/ngày; nếu chấp nhận cả hai, thứ tự thử có thể quyết định một ngày khác mà không có dấu hiệu lỗi. Hợp đồng nhập phải xác định ý nghĩa hoặc yêu cầu người dùng làm rõ.

Cũng không hiểu pattern `[uuuu-MM-dd][dd/MM/uuuu]` là toán tử “một trong hai”. Đây là **hai nhóm tùy chọn nối tiếp**: nó không tự áp đặt rằng phải chọn chính xác một nhóm. Khi định dạng một `LocalDate` có đủ trường, cả hai phần đều có thể được in, tạo chuỗi ghép của hai dạng. Với việc đọc, những tổ hợp không mong muốn còn tùy vào trường bị trùng và kiểm tra xung đột.

Dùng các bộ định dạng riêng giúp dễ xác định từng cú pháp được nhận, kiểm thử từng nhánh và chọn một dạng đầu ra thống nhất.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `OptionalDateInputDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.time.temporal.TemporalAccessor;
import java.util.Locale;

public class OptionalDateInputDemo {
    private static final DateTimeFormatter FLEX =
            new DateTimeFormatterBuilder()
                    .append(DateTimeFormatter.ISO_LOCAL_DATE)
                    .optionalStart()
                        .appendLiteral('T')
                        .appendValue(ChronoField.HOUR_OF_DAY, 2)
                        .appendLiteral(':')
                        .appendValue(ChronoField.MINUTE_OF_HOUR, 2)
                        .optionalStart()
                            .appendLiteral(':')
                            .appendValue(ChronoField.SECOND_OF_MINUTE, 2)
                        .optionalEnd()
                    .optionalEnd()
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final DateTimeFormatter WITH_MIDNIGHT =
            new DateTimeFormatterBuilder()
                    .append(FLEX)
                    .parseDefaulting(ChronoField.HOUR_OF_DAY, 0)
                    .parseDefaulting(ChronoField.MINUTE_OF_HOUR, 0)
                    .toFormatter(Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    private static final DateTimeFormatter[] DATE_FORMATS = {
            DateTimeFormatter.ISO_LOCAL_DATE,
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT)
    };

    public static void main(String[] args) {
        for (String text : new String[]{
                "2026-10-25", "2026-10-25T09:05",
                "2026-10-25T09:05:30", "2026-10-25T",
                "2026-10-25T09", "2026-10-25T09:05:",
                "2026-02-30", "2026-10-25T25:00"
        }) {
            inspect(text);
        }

        System.out.println("formatDate="
                + FLEX.format(LocalDate.of(2026, 10, 25)));
        System.out.println("formatDateTime="
                + FLEX.format(LocalDateTime.of(2026, 10, 25, 9, 5)));
        System.out.println("defaulted="
                + LocalDateTime.parse("2026-10-25", WITH_MIDNIGHT));

        System.out.println("iso=" + parseKnownDate("2026-10-25"));
        System.out.println("slash=" + parseKnownDate("25/10/2026"));
        try {
            parseKnownDate("10-25-2026");
        } catch (IllegalArgumentException e) {
            System.out.println("other=ERROR");
        }
    }

    private static void inspect(String text) {
        try {
            TemporalAccessor result = FLEX.parseBest(
                    text, LocalDateTime::from, LocalDate::from);
            String type = result instanceof LocalDateTime
                    ? "LocalDateTime" : "LocalDate";
            System.out.println(text + " -> " + type + " " + result);
        } catch (DateTimeParseException e) {
            System.out.println(text + " -> ERROR");
        }
    }

    private static LocalDate parseKnownDate(String text) {
        for (DateTimeFormatter format : DATE_FORMATS) {
            try {
                return LocalDate.parse(text, format);
            } catch (DateTimeParseException ignored) {
                // Try the next format in the explicit input contract.
            }
        }
        throw new IllegalArgumentException("unsupported date format");
    }
}
```

Biên dịch và chạy:

```shell
javac OptionalDateInputDemo.java
java OptionalDateInputDemo
```

Kết quả chuẩn:

```text
2026-10-25 -> LocalDate 2026-10-25
2026-10-25T09:05 -> LocalDateTime 2026-10-25T09:05
2026-10-25T09:05:30 -> LocalDateTime 2026-10-25T09:05:30
2026-10-25T -> ERROR
2026-10-25T09 -> ERROR
2026-10-25T09:05: -> ERROR
2026-02-30 -> ERROR
2026-10-25T25:00 -> ERROR
formatDate=2026-10-25
formatDateTime=2026-10-25T09:05:00
defaulted=2026-10-25T00:00
iso=2026-10-25
slash=2026-10-25
other=ERROR
```

`ERROR` là nhãn do chương trình in khi từ chối đầu vào, không phải nguyên văn ngoại lệ của Java. `inspect` kiểm tra cấu trúc ngày tùy chọn giờ; `parseKnownDate` minh họa riêng việc thử hai cú pháp ngày đã quy định. Chúng là hai chức năng độc lập, không phải mọi chuỗi trong chương trình đều được đưa qua cả hai cách xử lý.

Ngày 30/02 và giờ 25:00 bị từ chối vì bộ định dạng dùng `ResolverStyle.STRICT`. Một phần được phép vắng mặt không có nghĩa phần hiện diện được phép chứa giá trị sai.

## 8. Định dạng lại không giữ lịch sử phần đã bị bỏ qua

Khi phân tích `2026-10-25T09:05`, kết quả `LocalDateTime` có giây bằng 0. Khi định dạng lại bằng `FLEX`, đối tượng có trường giây nên nhóm `:ss` được in thành `:00`.

Điều đó giải thích dòng:

```text
formatDateTime=2026-10-25T09:05:00
```

Nhóm tùy chọn khi **định dạng** quyết định dựa vào việc đối tượng có cung cấp các trường cần thiết cho nhóm hay không. Nó không kiểm tra “trước đó người dùng có gõ trường giây không”, và cũng không tự bỏ nhóm chỉ vì giá trị giây bằng 0.

Ngược lại, `LocalDate` không có giờ nên toàn bộ nhóm thời gian bị bỏ khi định dạng. Muốn đầu ra luôn không có giây, chọn một bộ định dạng đầu ra chỉ có giờ/phút. Muốn giữ nguyên cách viết nguồn, cần lưu chuỗi gốc hoặc metadata về phần hiện diện; đối tượng ngày giờ thường không giữ lịch sử ấy.

Dạng ISO hiện trong các dòng kết quả của `parseBest` là `toString()` của đối tượng, có quy tắc hiển thị riêng. Đừng dùng sự ngắn gọn của `LocalDateTime.toString()` để suy ra `FLEX.format(...)` sẽ in giống hệt.

## 9. Lỗi thường gặp và cách tự kiểm tra

- Đặt `T` hoặc `:` ngoài nhóm nên một dấu phân cách vẫn bắt buộc dù trường bị tùy chọn.
- Làm giờ và phút tùy chọn độc lập, vô tình cho phép tổ hợp mà chức năng không muốn nhận.
- Gọi `LocalDateTime.parse` cho ngày đơn lẻ rồi cho rằng optional bị hỏng, trong khi vấn đề là thiếu trường cho kiểu kết quả.
- Đặt `LocalDate::from` đầu tiên trong `parseBest`, làm mất giờ từ đầu vào có giờ.
- Dùng mặc định nửa đêm mà không thống nhất ý nghĩa “không có giờ”.
- Ghép các pattern trong nhiều cặp `[]` và nghĩ chúng là các nhánh lựa chọn loại trừ nhau.
- Chỉ thử đầu vào hợp lệ; không kiểm tra các đoạn bị cắt dở như dấu `T` hoặc dấu `:` cuối chuỗi.

Để thực hành, thêm `2026-10-25T09:05:00` và so sánh với đầu vào không có giây: hai dạng tạo cùng một giá trị `LocalDateTime`. Sau đó đổi thứ tự truy vấn trong `parseBest` và quan sát phần giờ biến mất ở kết quả. Cuối cùng, thử `2026-10-25T09:05x` để xác nhận phần dư vẫn bị từ chối khi đọc toàn bộ chuỗi.

Tham khảo: [DateTimeFormatterBuilder — optionalStart, optionalEnd, appendOptional và parseDefaulting](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) và [DateTimeFormatter — parseBest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#parseBest(java.lang.CharSequence,java.time.temporal.TemporalQuery...)) trong Java SE 21.
