# Phân biệt số epoch giây với epoch mili giây trong hợp đồng dữ liệu

## 1. Một số nguyên không tự mang đơn vị thời gian

Hai giá trị sau đều có thể mô tả cùng vùng thời gian của một sự kiện, nhưng dùng đơn vị khác:

```text
1792886400       : số giây epoch
1792886400123    : số mili giây epoch
```

Nếu gửi một trường chỉ tên `timestamp` mà không công bố đơn vị, bên nhận có thể đưa số giây vào API nhận mili giây. Kết quả vẫn có thể là một ngày hợp lệ, nhưng nằm gần năm 1970 thay vì ngày dự kiến. Lỗi kiểu này không nhất thiết ném ngoại lệ.

Với Java `Instant`, mốc epoch là `1970-01-01T00:00:00Z`. Giá trị dương ở sau mốc, âm ở trước mốc. Đơn vị xác định khoảng cách tính từ mốc; múi giờ hiển thị không thay đổi giá trị số của cùng một thời điểm.

Một con số epoch không phải số ngày trong tháng, giờ địa phương hay một thời lượng độc lập. Nó là cách mã hóa **thời điểm theo mốc và đơn vị đã thỏa thuận**.

## 2. Chọn đúng API theo đơn vị

| Dữ liệu/API | Đơn vị hoặc ý nghĩa |
|---|---|
| `Instant.ofEpochSecond(value)` | Đầu vào là epoch giây nguyên |
| `Instant.ofEpochMilli(value)` | Đầu vào là epoch mili giây |
| `instant.getEpochSecond()` | Phần giây epoch của Instant |
| `instant.toEpochMilli()` | Biểu diễn epoch mili giây, bỏ phần chính xác hơn mili giây |
| `Instant.ofEpochSecond(seconds, nanoAdjustment)` | Tạo từ giây và phần điều chỉnh nano giây |
| `Date.getTime()`, `new Date(long)` | Epoch mili giây trong API legacy |
| `Clock.millis()`, `System.currentTimeMillis()` | Epoch mili giây từ nguồn thời gian tương ứng |

`System.nanoTime()` có mục đích đo khoảng chạy trong tiến trình, không phải epoch nano giây để gửi cho hệ thống khác. Đừng chia nó ra giây rồi coi là một mốc ngày giờ UTC.

Tên biến nên thể hiện đơn vị, chẳng hạn `createdAtEpochSeconds` hoặc `createdAtEpochMillis`. Ở phần xử lý nghiệp vụ, có thể chuyển sớm sang `Instant` để không kéo những số `long` dễ lẫn đơn vị qua nhiều lớp.

Khi cần giữ dạng số ở nhiều chữ ký API, các kiểu bao như `EpochSeconds` và `EpochMillis` giúp compiler phân biệt tham số. Chúng không thay thế kiểm tra dữ liệu bên ngoài nhưng làm nơi gọi rõ nghĩa hơn.

## 3. Mất độ chính xác không đồng nghĩa đổi đơn vị sai

Xét thời điểm:

```text
2026-10-25T00:00:00.123456789Z
```

Các phần của nó:

| Biểu diễn | Giá trị | Khi tạo lại |
|---|---|---|
| Epoch giây nguyên | `1792886400` | `2026-10-25T00:00:00Z` |
| Epoch mili giây | `1792886400123` | `2026-10-25T00:00:00.123Z` |
| Giây và nano giây | `1792886400`, `123456789` | Giữ đúng thời điểm ban đầu |

Nếu chỉ lưu số giây nguyên, bạn chủ động không giữ phần dưới giây. Nếu chỉ lưu mili giây, không giữ phần nhỏ hơn mili giây. Đó là hợp đồng độ chính xác cần thống nhất, khác với lỗi truyền số giây cho API nhận mili giây.

Không viết kiểm tra vòng chuyển đổi yêu cầu bằng tuyệt đối với nguồn nano giây nếu định dạng lưu trữ chỉ cam kết mili giây. Thay vào đó, xác định rõ chính sách giảm độ chính xác và kiểm tra kết quả tương ứng.

Với một Instant đã có giây epoch chuẩn hóa và phần nano giây trong 0–999.999.999, biểu diễn mili giây có thể hiểu là:

```text
epochMillis = epochSeconds * 1000 + nanoOfSecond / 1_000_000
```

Công thức cần xét tràn số và cách biểu diễn giá trị âm. Trong mã sử dụng thông thường, ưu tiên `toEpochMilli()` thay vì lặp lại phép tính ở khắp nơi.

## 4. Giá trị âm làm lộ lỗi chia nguyên

Một mili giây trước epoch là:

```text
1969-12-31T23:59:59.999Z
```

`Instant` biểu diễn nó bằng giây epoch `-1` và phần nano giây `999000000`. Vì thế:

```text
Instant.ofEpochMilli(-1).getEpochSecond() -> -1
```

Nhưng phép chia nguyên Java `-1 / 1000` làm tròn về 0 và trả `0`, không phải `-1`. Nếu đang chuyển một số mili giây sang phần giây theo cách của Instant, cần hiểu quy tắc sàn về phía âm, như `Math.floorDiv(millis, 1000L)`.

Không chỉ kiểm tra dữ liệu sau 1970 rồi kết luận việc chia luôn đúng. Với giá trị âm không chia hết cho 1000, hai cách khác nhau. Cách đơn giản để tránh tự viết sai quy tắc là tạo `Instant.ofEpochMilli(millis)` rồi hỏi `getEpochSecond()`.

Khi hợp đồng dùng số thập phân giây như `-0.001`, còn cần xác định parser số thập phân và cách tách phần giây/phần lẻ. Không chuyển qua `double` rồi mặc định mọi giá trị đều giữ chính xác như số nguyên hoặc `BigDecimal`.

## 5. Tràn số có thể xảy ra trước khi gán vào long

Ví dụ:

```java
int epochSeconds = 2_000_000_000;
long wrong = epochSeconds * 1000;
```

Hai toán hạng đều là `int`, nên phép nhân diễn ra theo `int` và có thể tràn **trước** khi kết quả được gán cho `long`. Dùng biến nhận kiểu long không cứu được kết quả đã sai.

Cách biểu đạt rõ hơn:

```java
long epochMillis = Math.multiplyExact((long) epochSeconds, 1000L);
```

Phép nhân dùng long; `multiplyExact` ném `ArithmeticException` nếu kết quả vượt phạm vi long. Nếu cần cộng phần mili giây lẻ, `Math.addExact` có vai trò tương tự.

Ngay cả long cũng có giới hạn. `Instant` có miền thời gian rộng hơn miền có thể đổi thành một số epoch mili giây long ở hai đầu; `toEpochMilli()` có thể ném `ArithmeticException` nếu không biểu diễn được kết quả.

Không sửa tràn số bằng ép kiểu trở lại một kiểu nhỏ hơn hoặc kẹp số một cách âm thầm. Nếu miền của hợp đồng không cho phép giá trị đó, báo lỗi ở ranh giới nhận dữ liệu.

## 6. Ghi rõ đơn vị trong hợp đồng dữ liệu

Một biểu diễn JSON minh họa:

```json
{
  "occurredAtEpochMillis": 1792886400123
}
```

Tên trường và tài liệu phải thống nhất rằng đây là số nguyên mili giây tính từ epoch UTC đã công bố. Một kiểu khác có thể dùng cặp giây/phần nano giây:

```json
{
  "occurredAt": {
    "epochSeconds": 1792886400,
    "nanoOfSecond": 123456789
  }
}
```

Cần nêu miền hợp lệ của phần lẻ và cách kiểm tra, không chỉ gửi hai con số không có quy tắc. Những JSON này minh họa hợp đồng; cách ánh xạ serializer cụ thể cần được cấu hình và kiểm tra trong ứng dụng.

Hợp đồng nên trả lời:

- Mốc epoch và đơn vị là gì?
- Chỉ cho phép số nguyên hay nhận cả số thập phân?
- Phần nhỏ hơn đơn vị có bị cắt, làm tròn hay bị từ chối?
- Có chấp nhận giá trị trước epoch không?
- Miền thời gian và phạm vi số được hỗ trợ là gì?
- `0` là epoch thật hay có một trạng thái “không có dữ liệu” riêng?

Không lấy `0` làm giá trị thiếu ngầm nếu epoch là một giá trị hợp lệ. Cũng không đổi đơn vị của một trường đã công bố từ giây sang mili giây mà giữ nguyên tên và để bên nhận tự thích nghi; cần phiên bản hợp đồng hoặc trường mới rõ ràng.

### Không đoán bằng số chữ số

Các số giây khoảng thời gian hiện đại thường ngắn hơn số mili giây tương ứng ba chữ số, nhưng đó không phải một cơ chế nhận diện đơn vị tin cậy. Dữ liệu lịch sử, giá trị 0, số âm hoặc thời điểm xa có độ dài khác. Một số bị nhân nhầm còn có thể rơi trong miền hợp lệ của kiểu đích.

Có thể dùng miền nghiệp vụ để phát hiện bất thường, nhưng nó không thay thế đơn vị. Nếu hợp đồng yêu cầu mili giây mà bên gửi gửi giây, ưu tiên sửa hoặc từ chối dữ liệu theo nguồn, không âm thầm tự nhân dựa trên một ngưỡng đoán.

### Số JSON còn có giới hạn tương tác giữa ngôn ngữ

Một phía nhận có thể đọc số JSON bằng kiểu IEEE 754 binary64, như `Number` thông thường của JavaScript. Không phải mọi số nguyên long của Java đều được biểu diễn chính xác ở đó; vùng số nguyên bảo toàn liên tục thường được xét là từ `-(2^53-1)` đến `2^53-1`.

Epoch mili giây trong ví dụ nằm trong miền ấy, nhưng không được suy ra rằng mọi epoch nano giây hoặc mọi giá trị long đều an toàn khi đi qua cùng đường số JSON. Nếu cần phạm vi lớn hơn, thống nhất chuỗi số hoặc cấu trúc phần giây/phần lẻ và parser phù hợp ở hai phía. Không thêm dấu nháy vào dữ liệu chỉ ở một bên mà không cập nhật schema.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `EpochUnitContractDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

```java
import java.time.Instant;

public class EpochUnitContractDemo {
    record EpochSeconds(long value) {
        Instant toInstant() {
            return Instant.ofEpochSecond(value);
        }
    }

    record EpochMillis(long value) {
        Instant toInstant() {
            return Instant.ofEpochMilli(value);
        }
    }

    public static void main(String[] args) {
        Instant original = Instant.parse("2026-10-25T00:00:00.123456789Z");
        long seconds = original.getEpochSecond();
        long millis = original.toEpochMilli();

        System.out.println("original=" + original);
        System.out.println("epochSeconds=" + seconds);
        System.out.println("epochMillis=" + millis);
        System.out.println("fromSeconds="
                + new EpochSeconds(seconds).toInstant());
        System.out.println("fromMillis="
                + new EpochMillis(millis).toInstant());
        System.out.println("wrongUnit=" + Instant.ofEpochMilli(seconds));
        System.out.println("fullPrecision="
                + Instant.ofEpochSecond(seconds, original.getNano()));
        System.out.println("millisecondsMatchFormula="
                + (millis == Math.addExact(
                        Math.multiplyExact(seconds, 1000L),
                        original.getNano() / 1_000_000L)));

        long beforeEpochMillis = -1L;
        System.out.println("negativeInstant="
                + Instant.ofEpochMilli(beforeEpochMillis));
        System.out.println("naiveNegativeSeconds="
                + beforeEpochMillis / 1000L);
        System.out.println("floorNegativeSeconds="
                + Math.floorDiv(beforeEpochMillis, 1000L));
        System.out.println("apiNegativeSeconds="
                + Instant.ofEpochMilli(beforeEpochMillis).getEpochSecond());

        int largeSeconds = 2_000_000_000;
        long overflowedBeforeAssignment = largeSeconds * 1000;
        long correctMillis = Math.multiplyExact((long) largeSeconds, 1000L);
        System.out.println("intMultiply=" + overflowedBeforeAssignment);
        System.out.println("longMultiply=" + correctMillis);

        try {
            Math.multiplyExact(Long.MAX_VALUE, 1000L);
        } catch (ArithmeticException e) {
            System.out.println("overflow=ArithmeticException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac EpochUnitContractDemo.java
java EpochUnitContractDemo
```

Kết quả chuẩn:

```text
original=2026-10-25T00:00:00.123456789Z
epochSeconds=1792886400
epochMillis=1792886400123
fromSeconds=2026-10-25T00:00:00Z
fromMillis=2026-10-25T00:00:00.123Z
wrongUnit=1970-01-21T18:01:26.400Z
fullPrecision=2026-10-25T00:00:00.123456789Z
millisecondsMatchFormula=true
negativeInstant=1969-12-31T23:59:59.999Z
naiveNegativeSeconds=0
floorNegativeSeconds=-1
apiNegativeSeconds=-1
intMultiply=-1454759936
longMultiply=2000000000000
overflow=ArithmeticException
```

`wrongUnit` cố ý đưa epoch giây vào `ofEpochMilli` để chứng minh một số sai đơn vị vẫn có thể tạo được Instant mà không ném lỗi. Không dùng lời gọi ấy trong mã xử lý dữ liệu đúng.

Hai record trong chương trình giữ tên đơn vị ở cấp kiểu. Chúng cho phép viết hàm nhận `EpochMillis` khác với hàm nhận `EpochSeconds`, thay vì chỉ nhìn một tham số long không có ý nghĩa. Các record chưa thêm miền nghiệp vụ: nếu chức năng chỉ nhận ngày trong một khoảng cụ thể, cần kiểm tra bổ sung.

Dòng `overflow` là nhãn do chương trình in khi `multiplyExact` phát hiện tràn, không phải toàn bộ thông điệp JDK. Tràn ở phép nhân int phía trước không tự ném ngoại lệ, nên kết quả âm bị in ra dù đầu vào dương.

## 8. Kiểm tra một đường lưu trữ/trao đổi thực tế

Khi đưa hợp đồng vào API hoặc cơ sở dữ liệu, kiểm tra cả hai chiều:

1. Bên gửi chuyển từ Instant sang đúng đơn vị và độ chính xác.
2. Dữ liệu được ghi/serialize không đổi kiểu số hoặc mất chữ số ngoài dự kiến.
3. Bên nhận dùng đúng API đọc đơn vị ấy.
4. Giá trị đọc lại khớp thời điểm theo mức chính xác đã công bố.

Có các bộ dữ liệu kiểm tra riêng cho: epoch 0, mốc dương có phần lẻ, giá trị âm sát epoch, ranh giới miền nghiệp vụ, số vượt khả năng kiểu nhận và một giá trị cố ý sai đơn vị.

Không so sánh trực tiếp một số epoch giây với một số epoch mili giây để kiểm tra thứ tự sự kiện. Chuẩn hóa sang Instant hoặc cùng một đơn vị trước. Tương tự, tổng “timestamp + TTL” chỉ có nghĩa khi TTL là lượng thời gian đúng đơn vị và phép cộng được kiểm tra tràn; dùng `Instant.plus(Duration)` có thể diễn đạt rõ hơn.

Việc đổi múi giờ hiển thị không sửa được lỗi sai đơn vị. Một thời điểm rơi gần năm 1970 do hiểu giây thành mili giây vẫn sai dù in ở UTC, Việt Nam hay vùng khác.

## 9. Tự thực hành

1. Dùng `Instant.ofEpochMilli(0)` và `Instant.ofEpochSecond(0)`. Cả hai cùng ra epoch; giải thích vì sao kiểm thử chỉ với 0 không phát hiện lỗi đơn vị.
2. Thử mili giây `-1001`: phần giây epoch là `-2`, trong khi phép chia Java `/ 1000` trả `-1`. So sánh với `Math.floorDiv`.
3. Thay nguồn bằng một thời điểm không có phần lẻ. Vòng epoch giây có thể giữ đúng; chỉ ra vì sao điều đó không chứng minh mọi Instant đều đi qua giây nguyên mà không mất dữ liệu.
4. Thiết kế chữ ký cho một hàm đọc hạn dùng từ epoch mili giây. Đặt tên trường/tham số hoặc chọn kiểu bao để người đọc không phải đoán đơn vị.

Tham khảo: [Instant — epoch APIs](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html), [Math — floorDiv và các phép toán Exact](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html) và [RFC 8259, mục 6 — số trong JSON](https://www.rfc-editor.org/rfc/rfc8259#section-6).
