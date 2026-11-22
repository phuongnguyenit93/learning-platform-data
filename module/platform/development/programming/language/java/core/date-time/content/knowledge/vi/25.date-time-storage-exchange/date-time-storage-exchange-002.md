# Quy ước ISO-8601 và offset tường minh trên giao diện trao đổi

## 1. Vì sao một chuỗi ngày giờ đẹp vẫn có thể mơ hồ?

Hai dịch vụ cùng nhận chuỗi `2024-08-20T09:15:30`. Dịch vụ A hiểu là giờ Việt Nam, dịch vụ B hiểu là UTC. Cả hai đều đọc được năm, tháng, ngày, giờ, nhưng chúng tạo ra hai thời điểm cách nhau bảy giờ.

Vấn đề không nằm ở dấu gạch ngang hay chữ `T`. Chuỗi thiếu thông tin liên hệ giữa giờ địa phương với UTC. Khi trường dữ liệu có nghĩa là **thời điểm một sự kiện xảy ra**, giao diện trao đổi phải truyền đủ thông tin để bên nhận xác định cùng một thời điểm.

Ba ví dụ sau có ý nghĩa khác nhau:

| Chuỗi | Thông tin đang có | Có xác định một thời điểm không? |
| --- | --- | --- |
| `2024-08-20` | Một ngày trên lịch | Không; có thể là ngày sinh hoặc ngày nghiệp vụ |
| `2024-08-20T09:15:30` | Ngày giờ địa phương | Chưa, nếu chưa có quy tắc múi giờ kèm theo |
| `2024-08-20T09:15:30+07:00` | Ngày giờ và độ lệch so với UTC | Có |

Bài này tập trung vào chuỗi thời điểm trên giao diện trao đổi giữa hệ thống: trường JSON, thông điệp, dữ liệu import/export hoặc tham số giao tiếp. Không phải mọi dữ liệu ngày giờ đều cần offset; yêu cầu này gắn với ý nghĩa của trường.

Mục tiêu là biết đọc offset, chọn kiểu Java phù hợp và xây một hợp đồng có thể kiểm thử, thay vì chỉ ghi “định dạng ISO”.

## 2. ISO-8601 là nền tảng, hợp đồng API cần cụ thể hơn

ISO-8601 bao quát nhiều cách biểu diễn ngày giờ. Trong hệ sinh thái Java, bạn gặp dạng ngày mở rộng, dạng cơ bản, ngày thứ tự trong năm, ngày theo tuần và nhiều kiểu kết hợp giờ/offset. Vì vậy, nhãn “ISO-8601” chưa trả lời hết các câu hỏi triển khai.

Một hợp đồng trao đổi cần chốt ít nhất:

- Trường biểu diễn ngày, giờ địa phương hay thời điểm?
- Có bắt buộc offset không? Cho nhận `Z`, `+00:00`, `+07:00` hay dạng khác?
- Có bắt buộc giây? Phần lẻ giây được bao nhiêu chữ số?
- Có nhận tên vùng như `Asia/Ho_Chi_Minh` trong cùng chuỗi không?
- Nhận chữ thường, dấu cách, năm mở rộng, giây nhuận hoặc 24:00 không?
- Đầu ra chuẩn hóa về UTC hay giữ offset đầu vào?
- Giá trị thiếu, giá trị sai và vượt phạm vi được xử lý thế nào?

RFC 3339 là một quy ước dành cho dấu thời gian Internet, được xây dựng như một profile của ISO-8601. Không nên coi mọi chuỗi Java đọc được bằng một formatter có tên ISO đều là chuỗi RFC 3339 đúng hợp đồng. Xem [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339.html).

Trong bài, chúng ta sẽ chọn **một hợp đồng ví dụ có giới hạn rõ ràng** và triển khai nó. Hợp đồng đó không phải trình xác thực toàn bộ ISO-8601 hay toàn bộ RFC 3339.

## 3. Đọc offset đúng chiều

Offset là độ lệch của giờ địa phương so với UTC:

```text
giờ địa phương = UTC + offset
UTC = giờ địa phương - offset
```

Ví dụ:

```text
2024-08-20T09:15:30+07:00
              ↓ cùng thời điểm
2024-08-20T02:15:30Z
```

`+07:00` nghĩa là giờ đang viết đi trước UTC bảy giờ. Đổi sang UTC phải trừ bảy giờ. Với offset âm, phép trừ offset âm làm tăng giờ UTC và có thể đổi ngày.

`Z` biểu diễn thời điểm theo độ lệch 0 trong việc tính toán. `+00:00` cũng có độ lệch số học 0. Đừng kết luận hai chuỗi khác nhau về thời điểm chỉ vì một chuỗi dùng `Z` và chuỗi kia dùng `+00:00`.

### 3.1 Offset không phải tên vùng

`+07:00` nói về độ lệch. `Asia/Ho_Chi_Minh` là tên vùng có quy tắc theo thời gian. Nhiều vùng có thể cùng một offset tại một thời điểm, nên không suy ngược duy nhất tên vùng từ `+07:00`.

Một dấu thời gian có offset phù hợp để xác định thời điểm đã xảy ra. Một lịch họp “09:00 mỗi thứ Hai tại New York” còn cần vùng và quy tắc lịch địa phương; giữ mỗi offset của lần họp đầu không đủ cho các lần sau khi quy tắc giờ thay đổi.

Nếu cần cả thời điểm và vùng nghiệp vụ, có thể thiết kế hai trường riêng hoặc dùng một định dạng mở rộng đã được hai bên thống nhất:

```json
{
  "occurredAt": "2024-08-20T02:15:30.000Z",
  "displayZone": "Asia/Ho_Chi_Minh"
}
```

Tên `displayZone` trong ví dụ là vùng phục vụ trình bày. Với lịch hẹn tương lai, ý nghĩa vùng có thể thuộc chính quy tắc lịch hẹn; cần đặt tên và hợp đồng phù hợp hơn.

### 3.2 Không suy đoán thêm ý nghĩa từ Z

Trong chương trình Java, `Z` và `+00:00` cùng quy về offset 0. Tuy nhiên, một giao thức có thể phân biệt thêm ý nghĩa về thông tin offset địa phương đã biết hay chưa biết.

RFC 9557 cập nhật diễn giải của RFC 3339 về `Z`, đồng thời định nghĩa cú pháp mở rộng chứa thông tin như tên vùng. Vì vậy, không tự suy ra rằng một chuỗi kết thúc bằng `Z` chứng minh người gửi sinh sống ở múi giờ UTC. Xem [RFC 9557: cập nhật RFC 3339](https://www.rfc-editor.org/rfc/rfc9557.html#section-2).

Nếu cần giữ sự khác nhau về cách biểu diễn hoặc trạng thái thông tin nguồn, lưu metadata đó riêng. `OffsetDateTime` không bảo toàn mọi khác biệt ký tự hay ý nghĩa bổ sung của giao thức sau khi parse.

## 4. Chọn kiểu Java theo nội dung trao đổi

| Nhu cầu | Kiểu thường phù hợp | Lưu ý |
| --- | --- | --- |
| Chỉ một ngày | `LocalDate` | Ví dụ `2024-08-20`; không tự thêm offset |
| Ngày giờ địa phương theo hợp đồng riêng | `LocalDateTime` | Chưa tự xác định một thời điểm |
| Ngày giờ kèm offset đầu vào | `OffsetDateTime` | Giữ được độ lệch số học |
| Thời điểm chuẩn hóa để so sánh/lưu | `Instant` | Không giữ offset người gửi |
| Ngày giờ gắn quy tắc vùng | `ZonedDateTime` | Cần quy ước tên vùng khi trao đổi |

`OffsetDateTime` lưu ngày giờ và offset; `Instant` biểu diễn thời điểm; `ZonedDateTime` bổ sung quy tắc vùng. Sự phân biệt này được mô tả trong [Java SE 21 OffsetDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/OffsetDateTime.html).

Ví dụ đọc một trường dấu thời gian có offset:

```java
OffsetDateTime received = OffsetDateTime.parse(
        "2024-08-20T09:15:30+07:00",
        DateTimeFormatter.ISO_OFFSET_DATE_TIME);
Instant eventTime = received.toInstant();
```

Đây là bước chuyển đối tượng; không cộng/trừ thủ công thêm bảy giờ sau `toInstant()`. Offset trong chuỗi đã được dùng để xác định thời điểm.

## 5. Formatter chuẩn không thay cho toàn bộ hợp đồng

`DateTimeFormatter.ISO_OFFSET_DATE_TIME` là lựa chọn tốt để xử lý ngày giờ có offset, nhưng khả năng đọc của nó rộng hơn nhiều hợp đồng API cụ thể. Ví dụ, formatter có thể nhận offset với thành phần giây; phần phút của offset có thể được bỏ trong lúc parse.

`ISO_DATE_TIME` còn cho phép các phần tùy chọn như offset hoặc tên vùng. Chọn nó rồi mặc định “offset luôn bắt buộc” dễ tạo khoảng trống trong kiểm tra đầu vào.

`ISO_INSTANT` khi ghi tạo biểu diễn UTC với `Z`, nhưng số chữ số phần lẻ giây có thể thay đổi theo giá trị. Tên formatter không tự cam kết “luôn đúng ba chữ số mili giây”. Các khác biệt được nêu trong [DateTimeFormatter: các formatter dựng sẵn](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#predefined).

Một cách triển khai dễ đọc gồm hai tầng:

```text
Kiểm tra hình dạng thuộc hợp đồng
                 ↓
Parse và kiểm tra tính hợp lệ của ngày/giờ/offset
                 ↓
Chuyển sang kiểu nghiệp vụ
                 ↓
Ghi theo dạng đầu ra chuẩn hóa
```

Kiểm tra hình dạng không thể tự chứng minh 29/02 là hợp lệ. Parse hợp lệ theo một formatter rộng cũng chưa chứng minh chuỗi thuộc đúng tập dạng mà API đã công bố. Hai tầng bổ sung cho nhau.

## 6. Một hợp đồng trao đổi cụ thể

Giả sử trường `occurredAt` là thời điểm sự kiện, hệ thống đích hỗ trợ mili giây. Ta chọn quy ước sau cho ví dụ:

| Thành phần | Quy ước được chọn |
| --- | --- |
| Ngày | `uuuu-MM-dd`, năm 0001–9999 |
| Phân cách ngày/giờ | Chữ `T` hoa |
| Giờ | `HH:mm:ss`, giây bắt buộc |
| Phần lẻ giây | Không có hoặc 1–3 chữ số sau dấu chấm |
| Offset | Bắt buộc `Z` hoa hoặc `±HH:mm` |
| Phạm vi offset | Phạm vi Java hỗ trợ, từ -18:00 đến +18:00; hai đầu có phút bằng 00 |
| Dạng loại trừ | Không nhận `-00:00`, tên vùng trong ngoặc, giây trong offset, giây nhuận, 24:00, khoảng trắng thừa |
| Dạng đầu ra | UTC, `Z`, luôn đúng ba chữ số phần lẻ giây |
| Phạm vi đầu ra | Sau chuyển sang UTC vẫn phải nằm trong năm 0001–9999 |

Đây là các lựa chọn của ví dụ, không phải phát biểu rằng chuẩn ISO cấm mọi dạng bị loại trừ. Từ chối `-00:00` là quyết định của hợp đồng này để không nhận một cách biểu diễn có thể mang ý nghĩa bổ sung mà mô hình không giữ được.

Đầu vào `.1` tương ứng 100 mili giây; `.12` tương ứng 120 mili giây; `.123` tương ứng 123 mili giây. Dạng `.1234` bị từ chối, kể cả khi một thư viện parse tổng quát đọc được.

Khi chuẩn hóa, offset ban đầu không còn trong chuỗi đầu ra. Nếu yêu cầu kiểm toán cần giữ nguyên chuỗi gốc, hãy lưu nó riêng bên cạnh giá trị đã xác thực, với mục đích sử dụng rõ ràng.

## 7. Chương trình kiểm chứng hợp đồng

Lưu thành `IsoExchangeContractDemo.java`. Chương trình dùng Java chuẩn, không cần thư viện JSON vì trọng tâm là quy tắc của một trường văn bản.

```text
javac --release 17 IsoExchangeContractDemo.java
java IsoExchangeContractDemo
```

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeFormatterBuilder;
import java.util.regex.Pattern;

public class IsoExchangeContractDemo {
    private static final Pattern WIRE = Pattern.compile(
            "[0-9]{4}-[0-9]{2}-[0-9]{2}T"
            + "[0-9]{2}:[0-9]{2}:[0-9]{2}"
            + "(?:[.][0-9]{1,3})?"
            + "(?:Z|[+-][0-9]{2}:[0-9]{2})");

    private static final DateTimeFormatter OUTPUT =
            new DateTimeFormatterBuilder().appendInstant(3).toFormatter();

    private static OffsetDateTime parseWire(String text) {
        if (text == null || !WIRE.matcher(text).matches()
                || text.endsWith("-00:00")) {
            throw new IllegalArgumentException("Invalid timestamp shape");
        }
        try {
            OffsetDateTime parsed = OffsetDateTime.parse(
                    text, DateTimeFormatter.ISO_OFFSET_DATE_TIME);
            if (parsed.getYear() < 1 || parsed.getYear() > 9999) {
                throw new IllegalArgumentException("Local year out of range");
            }
            canonical(parsed.toInstant());
            return parsed;
        } catch (DateTimeException ex) {
            throw new IllegalArgumentException("Invalid timestamp value", ex);
        }
    }

    private static String canonical(Instant instant) {
        if (instant == null || instant.getNano() % 1_000_000 != 0) {
            throw new IllegalArgumentException("Millisecond precision required");
        }
        int year = instant.atOffset(ZoneOffset.UTC).getYear();
        if (year < 1 || year > 9999) {
            throw new IllegalArgumentException("UTC year out of range");
        }
        return OUTPUT.format(instant);
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static boolean rejected(String input) {
        try {
            parseWire(input);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        OffsetDateTime localOffset = parseWire(
                "2024-08-20T09:15:30+07:00");
        OffsetDateTime utc = parseWire("2024-08-20T02:15:30Z");
        check(localOffset.isEqual(utc), "same instant");
        check(!localOffset.equals(utc), "different local fields and offsets");
        System.out.println("same-instant=" + localOffset.isEqual(utc));
        System.out.println("same-offset-date-time=" + localOffset.equals(utc));
        System.out.println("canonical=" + canonical(localOffset.toInstant()));

        OffsetDateTime fractional = parseWire(
                "2024-08-20T09:15:30.12+07:00");
        check(fractional.getNano() == 120_000_000, "fraction scale");
        String normalized = canonical(fractional.toInstant());
        check(normalized.equals("2024-08-20T02:15:30.120Z"),
                "fixed millisecond output");
        check(parseWire(normalized).toInstant().equals(fractional.toInstant()),
                "canonical round trip");
        check(canonical(parseWire(normalized).toInstant()).equals(normalized),
                "canonical idempotence");
        check(parseWire("2024-08-20T02:15:30+00:00")
                .toInstant().equals(utc.toInstant()), "zero offset");
        System.out.println("fractional-canonical=" + normalized);

        String[] bad = {
            "2024-08-20T09:15:30",
            "2024-08-20T09:15+07:00",
            "2024-08-20 09:15:30+07:00",
            "2024-08-20t09:15:30z",
            "2024-08-20T09:15:30+0700",
            "2024-08-20T09:15:30+07",
            "2024-08-20T09:15:30+07:00:30",
            "2024-08-20T09:15:30+07:00[Asia/Ho_Chi_Minh]",
            "2024-02-30T09:15:30Z",
            "2024-08-20T24:00:00Z",
            "2016-12-31T23:59:60Z",
            "2024-08-20T09:15:30.1234Z",
            "2024-08-20T09:15:30-00:00",
            "2024-08-20T09:15:30+18:01",
            "0000-01-01T00:00:00Z",
            "0001-01-01T00:00:00+01:00",
            "2024-08-20T09:15:30Z ",
            null
        };
        int rejectedCount = 0;
        for (String input : bad) {
            check(rejected(input), "must reject: " + input);
            rejectedCount++;
        }
        System.out.println("rejected=" + rejectedCount + "/" + bad.length);

        boolean preciseRejected = false;
        try {
            canonical(Instant.parse("2024-08-20T02:15:30.000000001Z"));
        } catch (IllegalArgumentException expected) {
            preciseRejected = true;
        }
        check(preciseRejected, "do not silently discard nanos");
        System.out.println("excess-precision-rejected=" + preciseRejected);

        String a = "2024-01-01T00:30:00+01:00";
        String b = "2023-12-31T23:45:00Z";
        check(a.compareTo(b) > 0, "textual order");
        check(parseWire(a).toInstant().isBefore(parseWire(b).toInstant()),
                "chronological order");
        System.out.println("text-a-after-b=" + (a.compareTo(b) > 0));
        System.out.println("instant-a-before-b="
                + parseWire(a).toInstant().isBefore(parseWire(b).toInstant()));
        System.out.println("PASS");
    }
}
```

Kết quả:

```text
same-instant=true
same-offset-date-time=false
canonical=2024-08-20T02:15:30.000Z
fractional-canonical=2024-08-20T02:15:30.120Z
rejected=18/18
excess-precision-rejected=true
text-a-after-b=true
instant-a-before-b=true
PASS
```

### 7.1 Vì sao kiểm tra hình dạng rồi mới parse?

Biểu thức chính quy giới hạn đúng tập ký tự và cách viết đã chọn. `matches()` yêu cầu khớp toàn bộ chuỗi nên không nhận phần dư. Nó cũng không tự `trim()`; khoảng trắng ngoài hợp đồng bị từ chối.

Bước `OffsetDateTime.parse(...)` kiểm tra ngày thực tế và phạm vi giờ/offset. Chuỗi `2024-02-30T09:15:30Z` có hình dạng đúng nhưng vẫn bị loại ở bước này.

Bước `canonical(...)` kiểm tra phần chính xác và năm UTC. Dữ liệu sát đầu năm 0001 có offset dương có thể chuyển sang năm 0000 tại UTC; ví dụ chủ động loại trường hợp đó vì đầu ra phải nằm trong phạm vi đã công bố.

### 7.2 Vì sao không để formatter tự cắt nano giây?

`appendInstant(3)` giúp tạo đúng ba chữ số phần lẻ khi ghi. Nhưng nếu giá trị nội bộ có phần nhỏ hơn mili giây, cần quyết định trước việc từ chối, cắt hay làm tròn.

Ví dụ chọn từ chối phần dư, nên `canonical` kiểm tra chia hết cho một triệu nano giây trước khi ghi. Đầu vào từ `parseWire` vốn chỉ có tối đa ba chữ số; kiểm tra này còn bảo vệ khi gọi `canonical` trực tiếp với một `Instant` tạo ở nơi khác.

### 7.3 Vì sao cùng thời điểm mà equals trả false?

Hai `OffsetDateTime` đầu chương trình giữ các trường địa phương và offset khác nhau. `equals` kiểm tra cả biểu diễn đó. `isEqual` hoặc so sánh `toInstant()` kiểm tra cùng thời điểm.

Khi khử trùng lặp sự kiện, không dùng chuỗi nguyên bản làm đại diện cho thời điểm nếu giao thức cho phép nhiều offset. Ngược lại, nếu cần giữ offset người gửi cho kiểm toán, chỉ lưu `Instant` sẽ không đáp ứng hết yêu cầu.

## 8. Đầu vào có offset, đầu ra chuẩn hóa: điều gì được giữ?

Chuẩn hóa hai chuỗi:

```text
2024-08-20T09:15:30+07:00
2024-08-20T02:15:30Z
```

về cùng dạng:

```text
2024-08-20T02:15:30.000Z
```

giữ thời điểm và độ chính xác của ví dụ. Nó thay cách viết, số giờ địa phương, offset thể hiện và số chữ số phần lẻ.

Một hợp đồng tốt phân biệt hai kiểu khứ hồi:

| Yêu cầu | Điều có thể kiểm tra |
| --- | --- |
| Khứ hồi ngữ nghĩa | Parse rồi ghi rồi parse vẫn cùng `Instant` |
| Khứ hồi nguyên văn | Chuỗi sau cùng giống từng ký tự của chuỗi đầu |

Ví dụ chỉ cam kết khứ hồi ngữ nghĩa và tính ổn định của dạng chuẩn hóa. Nếu cần nguyên văn, phải giữ chuỗi nguồn riêng; không trông chờ `toString()` nhớ nó.

Không gắn `Z` vào cuối một `LocalDateTime` chỉ bằng nối chuỗi. Động tác đó tuyên bố offset 0 mà chưa xác định thời điểm từ nguồn. Cần biết múi giờ/offset thật và chuyển đúng ý nghĩa trước khi ghi.

## 9. Sắp xếp và so sánh dữ liệu trao đổi

Hai chuỗi đầu vào có offset khác nhau không bảo đảm sắp xếp từ điển giống thứ tự thời gian. Phần cuối chương trình cho phản ví dụ:

- `2024-01-01T00:30:00+01:00` là 23:30 UTC ngày 31/12/2023.
- `2023-12-31T23:45:00Z` xảy ra sau đó 15 phút.

Năm trong chuỗi đầu lớn hơn, nhưng thời điểm lại sớm hơn. Hãy parse và so sánh `Instant` khi dữ liệu chưa chuẩn hóa.

Nếu mọi chuỗi đều theo cùng UTC, cùng độ rộng năm và cùng độ chính xác cố định như đầu ra của ví dụ, thứ tự từ điển mới có điều kiện phù hợp để trùng thứ tự thời gian. Không áp dụng kết luận này sang tập chuỗi có độ rộng, offset hoặc phần lẻ khác nhau.

Thứ tự sự kiện còn có thể cần khóa phụ khi nhiều sự kiện chung một mili giây. Định dạng thời gian không tự cung cấp tính duy nhất hay thứ tự tuyệt đối cho các sự kiện đồng thời.

## 10. Đưa quy ước vào giao diện trao đổi thực tế

Với một trường JSON như `occurredAt`, tài liệu cần nêu ý nghĩa và quy tắc kiểm tra, không chỉ một ví dụ đẹp. Có thể công bố:

```text
occurredAt:
- Thời điểm sự kiện xảy ra.
- Nhận năm 0001–9999, giây bắt buộc và tối đa 3 chữ số phần lẻ.
- Offset bắt buộc: Z hoặc ±HH:mm theo phạm vi đã công bố.
- Trả UTC với đúng 3 chữ số mili giây.
- Không tự dùng múi giờ của máy chủ khi thiếu offset.
- Thiếu, null, chuỗi trống hoặc giá trị sai được báo theo hợp đồng lỗi.
```

Đây là mô tả rút gọn; các trường hợp bị loại trừ ở bảng hợp đồng vẫn cần được ghi trong đặc tả đầy đủ.

Nếu dùng JSON serializer/deserializer, kiểm tra nó thực sự đọc/ghi theo hợp đồng này. Khai báo kiểu `Instant` hay `OffsetDateTime` trong Java không tự chứng minh cấu hình thư viện đáp ứng số chữ số phần lẻ, tập offset hay chính sách lỗi.

Không dùng định dạng cho người đọc như `20/08/2024 09:15` làm giao thức máy nếu hợp đồng đang yêu cầu dấu thời gian có offset. Giao diện người dùng có thể hiển thị theo locale; dữ liệu trao đổi vẫn nên theo quy ước đã thống nhất.

Nếu thời điểm nằm trong query string hoặc form, cần mã hóa theo tầng giao thức. Dấu `+` của offset có thể bị tầng form giải mã thành khoảng trắng nếu ghép tham số thô. Dùng bộ dựng URI/form phù hợp rồi kiểm tra giá trị sau giải mã, thay vì sửa bằng thay chuỗi ngẫu nhiên trong bộ parse ngày giờ.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nhận chuỗi thiếu offset rồi dùng múi giờ máy chủ | Kết quả khác giữa các môi trường | Từ chối theo hợp đồng hoặc yêu cầu vùng ở một trường rõ ràng |
| Nối `Z` vào giờ địa phương | Gán nhầm offset 0, đổi thời điểm | Diễn giải bằng vùng/offset đúng rồi chuẩn hóa |
| Dùng formatter rộng hơn đặc tả mà không kiểm tra thêm | Nhận các dạng đối tác không hỗ trợ | Giới hạn hình dạng và kiểm tra giá trị |
| Gọi `toString()` rồi kỳ vọng luôn có giây và ba chữ số lẻ | Dạng đầu ra có thể không cố định | Dùng formatter đầu ra cụ thể và kiểm thử |
| Xem `+07:00` là tên vùng duy nhất | Mất quy tắc địa phương cho lịch tương lai | Truyền `ZoneId` khi nghiệp vụ cần |
| Cắt phần lẻ không thông báo | Mất độ chính xác | Chốt rõ từ chối/cắt/làm tròn và kiểm thử |
| Sắp xếp trực tiếp các chuỗi có offset khác nhau | Thứ tự thời gian sai | So sánh `Instant` |
| Tưởng hậu tố `[Asia/Ho_Chi_Minh]` được mọi API chấp nhận | Lỗi tương thích | Chỉ dùng khi hai bên công bố hỗ trợ cùng định dạng |

Hậu tố tên vùng trong chuỗi Java không phải lý do để tự coi một parser hỗ trợ mọi định dạng mở rộng Internet. Nếu chọn RFC 9557 hoặc một hợp đồng mở rộng khác, cần xác định cú pháp, metadata và hành vi khi offset không khớp vùng theo đúng giao thức đó.

## 12. Thực hành và tự kiểm tra

### Bài 1 — Nhận diện thiếu thông tin

Trường `paidAt` nhận `2024-08-20T09:15:30`. Có thể tự hiểu là UTC vì server chạy UTC không?

**Gợi ý giải:** chỉ khi hợp đồng đã định nghĩa rõ như vậy; với hợp đồng trong bài thì phải từ chối vì thiếu offset. Múi giờ của server không phải dữ kiện của người gửi.

### Bài 2 — Đổi đúng chiều

`2024-08-20T09:15:30-04:00` tương ứng bao nhiêu giờ UTC?

**Gợi ý giải:** 13:15:30 UTC cùng ngày. Trừ offset âm là cộng bốn giờ. Dùng `OffsetDateTime.parse(...).toInstant()` để kiểm chứng.

### Bài 3 — Giữ thời điểm hay giữ biểu diễn?

Đối tác gửi `2024-08-20T09:15:30+07:00`, hệ thống trả `2024-08-20T02:15:30.000Z`. Có phải đã làm mất thời điểm gốc không?

**Gợi ý giải:** thời điểm vẫn giữ. Offset và cách viết đã được chuẩn hóa. Nếu cần lưu ngữ cảnh người gửi, bổ sung dữ liệu riêng theo hợp đồng.

### Bài 4 — Mở rộng độ chính xác

Đối tác mới cần micro giây. Có nên chỉ bỏ kiểm tra ba chữ số ở đầu vào?

**Gợi ý giải:** chưa đủ. Phải cập nhật mô hình lưu, formatter đầu ra, chính sách chuyển sang hệ thống cũ và kiểm thử khứ hồi. Nếu đầu ra vẫn ba chữ số, dữ liệu nhận thêm có thể bị mất.

### Bài 5 — Xây bộ kiểm thử hợp đồng

Bổ sung trường hợp ngày nhuận hợp lệ, ngày nhuận sai, offset âm, đổi ngày khi về UTC, phần lẻ `.0`, `.001`, chuỗi thừa ký tự và tên vùng chưa được hỗ trợ.

**Gợi ý giải:** mỗi trường hợp phải xác nhận rõ nhận/từ chối. Với giá trị được nhận, kiểm tra `Instant`, đầu ra chuẩn hóa và parse lại. Không chỉ kiểm tra “không ném ngoại lệ”.

### Bài 6 — Thiết kế trường chỉ có ngày

Một trường `birthDate` chỉ ghi ngày sinh. Có nên ép truyền `2000-01-01T00:00:00Z` để mọi trường đều có offset?

**Gợi ý giải:** không nếu ý nghĩa chỉ là ngày. Chọn `2000-01-01` và `LocalDate`. Yêu cầu offset tường minh cần áp dụng đúng cho trường biểu diễn thời điểm, tránh thêm giả định không thuộc dữ liệu.
