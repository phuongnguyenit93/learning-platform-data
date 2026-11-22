# Phiên bản hóa định dạng thời gian và biểu diễn số

Thời gian và số là hai nhóm dữ liệu dễ gây lỗi tương thích khi API thay đổi. Một timestamp có thể là chuỗi ISO-8601, số epoch giây hoặc epoch mili giây. Một số tiền có thể là JSON number, chuỗi thập phân hoặc số nguyên theo đơn vị nhỏ nhất. Các biểu diễn này nhìn qua có vẻ tương đương, nhưng consumer có thể parse theo kiểu khác, mất độ chính xác hoặc hiểu sai đơn vị.

Với Jackson, cần xác định hợp đồng JSON trước rồi cấu hình kiểu Java, serializer/deserializer và mapper theo hợp đồng đó. Không nên để định dạng wire phụ thuộc ngầm vào default của phiên bản Jackson hoặc một tùy chọn runtime chưa được công bố.

Bài học này tập trung vào việc chọn kiểu thời gian, định dạng timestamp, timezone, độ chính xác số, cấu hình Jackson và cách tiến hóa hợp đồng mà không làm hỏng consumer hiện tại.

## 1. Định dạng wire là một phần của hợp đồng dữ liệu

Cùng một thời điểm có thể được biểu diễn theo nhiều cách:

~~~json
{
  "createdAt": "2026-11-12T10:15:30Z",
  "createdAtEpochSeconds": 1794478530,
  "createdAtEpochMillis": 1794478530000
}
~~~

Ba field trên có thể đại diện cùng thời điểm, nhưng consumer cần biết:

- Giá trị là chuỗi hay số?
- Nếu là số, đơn vị là giây, mili giây hay nano giây?
- Thời điểm được tính theo UTC hay theo offset địa phương?
- Có phần thập phân biểu diễn mili/micro/nano giây không?
- Consumer có cần giữ nguyên timezone/region hay chỉ cần một instant trên timeline?

Đổi từ chuỗi sang số, đổi epoch milliseconds thành epoch seconds hoặc bỏ offset khỏi timestamp đều có thể là thay đổi breaking. Vì vậy, hãy coi tên field, kiểu JSON, đơn vị, timezone và precision là một phần của schema API.

## 2. Chọn đúng kiểu Java Time

Jackson hỗ trợ các kiểu trong `java.time` thông qua module Java Time. Trước hết, chọn kiểu Java theo ý nghĩa nghiệp vụ:

| Kiểu Java | Ý nghĩa | Ví dụ biểu diễn |
|---|---|---|
| `LocalDate` | Ngày lịch, không có giờ hoặc múi giờ | `2026-11-12` |
| `LocalTime` | Giờ trong ngày, không có ngày/múi giờ | `09:30:00` |
| `LocalDateTime` | Ngày và giờ địa phương, không xác định instant | `2026-11-12T09:30:00` |
| `OffsetDateTime` | Ngày giờ kèm UTC offset | `2026-11-12T17:30:00+07:00` |
| `ZonedDateTime` | Ngày giờ gắn với ZoneId và bộ quy tắc timezone | `2026-11-12T17:30:00+07:00[Asia/Ho_Chi_Minh]` |
| `Instant` | Một điểm trên timeline UTC | `2026-11-12T10:30:00Z` |
| `Duration` | Khoảng thời gian theo giây/nano giây | Không phải ngày giờ lịch |
| `Period` | Khoảng thời gian theo năm/tháng/ngày lịch | Không phải số giây cố định |

Không dùng `LocalDateTime` cho thời điểm sự kiện toàn hệ thống nếu cần xác định chính xác một instant. Ví dụ `2026-11-12T09:30:00` không cho biết đó là 09:30 ở TP.HCM, London hay UTC.

Với thời điểm tạo bản ghi, thời điểm giao dịch hoặc log event, `Instant` thường là lựa chọn phù hợp. Nếu cần giữ offset người dùng gửi, dùng `OffsetDateTime`. Nếu nghiệp vụ phụ thuộc quy tắc vùng như lịch làm việc tại một thành phố, giữ thêm `ZoneId` hoặc `ZonedDateTime`.

## 3. Phân biệt Instant, offset và timezone

Ba khái niệm này liên quan nhưng không đồng nghĩa.

- **Instant:** một điểm duy nhất trên timeline, thường được trao đổi theo UTC.
- **Offset:** độ lệch cố định so với UTC tại thời điểm đó, ví dụ `+07:00`.
- **ZoneId:** tên vùng timezone như `Asia/Ho_Chi_Minh`, có bộ quy tắc lịch sử và quy tắc thay đổi theo thời gian.

Ví dụ:

~~~text
2026-11-12T17:30:00+07:00
2026-11-12T10:30:00Z
~~~

Hai chuỗi trên biểu diễn cùng một instant.

Nhưng offset `+07:00` không nói rằng thời điểm thuộc vùng `Asia/Ho_Chi_Minh`. Nhiều vùng có thể dùng cùng offset ở một thời điểm nhưng có quy tắc lịch sử hoặc tương lai khác nhau.

Nếu cần lên lịch một sự kiện địa phương trong tương lai, chẳng hạn "09:00 tại Paris vào ngày 15 tháng 3", lưu ngày giờ địa phương cùng ZoneId. Không chỉ lưu offset hiện tại, vì quy tắc daylight saving time có thể thay đổi.

Với thời điểm đã xảy ra, lưu `Instant` và nếu cần cho audit thì giữ thêm zone/offset gốc do người gửi cung cấp.

## 4. Dùng ISO-8601 hoặc RFC 3339 cho API

Đối với API JSON, chuỗi timestamp theo ISO-8601/RFC 3339 thường dễ đọc và ít mơ hồ hơn số epoch không có tên đơn vị.

Ví dụ:

~~~json
{
  "eventDate": "2026-11-12",
  "localStart": "2026-11-12T09:30:00",
  "occurredAt": "2026-11-12T10:30:00Z",
  "clientTime": "2026-11-12T17:30:00+07:00"
}
~~~

Quy ước có thể dùng:

- `LocalDate`: `YYYY-MM-DD`.
- `Instant`: UTC với hậu tố `Z`.
- `OffsetDateTime`: ngày giờ có offset `+HH:MM` hoặc `-HH:MM`.
- Tránh chuỗi local date-time không offset nếu field thực chất là một instant.

RFC 3339 là profile timestamp của ISO-8601 dành cho Internet protocols. Trong OpenAPI/JSON Schema, field timestamp thường được mô tả là `type: string, format: date-time`; ngày lịch là `type: string, format: date`. Hãy công bố precision và quy tắc timezone kèm schema, vì chỉ ghi `date-time` chưa mô tả hết các yêu cầu nghiệp vụ.

## 5. Đăng ký JavaTimeModule

Jackson Databind cần module Java Time để hỗ trợ các kiểu `java.time`:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Khi tắt `WRITE_DATES_AS_TIMESTAMPS`, các kiểu ngày giờ được hỗ trợ thường được ghi thành chuỗi theo formatter tương ứng. Đây là cấu hình hữu ích cho hợp đồng JSON dùng ISO-8601.

Có thể đăng ký qua `ObjectMapper.registerModule(new JavaTimeModule())` nếu mapper được tạo theo cách thông thường.

Trong ứng dụng framework, kiểm tra mapper thực tế do framework cấu hình. Đừng tạo thêm một ObjectMapper riêng trong service chỉ để parse timestamp nếu mapper production đã có module, naming strategy hoặc custom serializer khác.

## 6. Cẩn thận với WRITE_DATES_AS_TIMESTAMPS

Nếu bật `SerializationFeature.WRITE_DATES_AS_TIMESTAMPS`, Java Time module có thể ghi nhiều kiểu thời gian dưới dạng số hoặc cấu trúc số.

Ví dụ `LocalDateTime` có thể được ghi thành array các thành phần ngày giờ thay vì chuỗi:

~~~json
[2026, 11, 12, 9, 30, 0]
~~~

Đây là JSON hợp lệ nhưng có thể không phù hợp với consumer mong đợi RFC 3339 string.

Với `Instant`, timestamp số còn phụ thuộc cấu hình nano/ milli giây. Vì vậy, không nên để một feature toàn mapper quyết định wire format mà không có test hợp đồng.

Để API ổn định, cấu hình rõ:

~~~java
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
~~~

Sau đó kiểm thử output thực tế của từng kiểu ngày giờ quan trọng. Nếu một field legacy cần numeric timestamp, xử lý riêng ở property hoặc DTO thay vì bật timestamps toàn mapper cho mọi field.

## 7. Epoch seconds và epoch milliseconds

Nếu hợp đồng bắt buộc dùng số epoch, phải đặt tên field hoặc tài liệu hóa đơn vị rõ ràng.

~~~json
{
  "createdAtEpochSeconds": 1794479400,
  "createdAtEpochMillis": 1794479400000
}
~~~

Không dùng tên chung chung như `createdAt: 1794479400` nếu consumer không thể biết đơn vị.

Jackson Java Time module có hai feature quan trọng:

- `SerializationFeature.WRITE_DATE_TIMESTAMPS_AS_NANOSECONDS`: khi ghi timestamp số, điều khiển việc dùng độ chính xác nano giây hay mili giây theo kiểu và serializer.
- `DeserializationFeature.READ_DATE_TIMESTAMPS_AS_NANOSECONDS`: điều khiển cách diễn giải timestamp số khi đọc.

Với các kiểu instant, khi chế độ nano giây được bật, timestamp có thể được biểu diễn bằng số giây với phần thập phân. Khi tắt, giá trị số được biểu diễn/diễn giải theo mili giây. Cấu hình mặc định và chi tiết có thể phụ thuộc kiểu Java Time và phiên bản module; hãy khóa rõ behavior trong mapper và test.

Đổi đơn vị mà không đổi tên field là thay đổi breaking. Ví dụ một consumer hiểu số là milliseconds nhưng server bắt đầu gửi seconds sẽ tạo thời điểm sai lệch 1.000 lần.

Nếu cần chuyển đổi thủ công:

~~~java
Instant fromSeconds = Instant.ofEpochSecond(epochSeconds);
Instant fromMillis = Instant.ofEpochMilli(epochMillis);

long seconds = instant.getEpochSecond();
long millis = instant.toEpochMilli();
~~~

Không nhân hoặc chia timestamp bằng một hằng số ở nhiều nơi rải rác. Đặt conversion tại boundary và dùng tên biến/field thể hiện đơn vị.

## 8. Precision thời gian: giây, mili, micro và nano giây

`Instant` có độ chính xác tới nano giây trong mô hình Java:

~~~java
Instant instant = Instant.parse("2026-11-12T10:30:00.123456789Z");
~~~

Nhưng hệ thống bên dưới có thể chỉ lưu đến milliseconds hoặc microseconds. Nếu serialize 9 chữ số rồi database chỉ giữ 3 chữ số, round-trip không còn giữ nguyên giá trị.

Cần thống nhất:

- Độ chính xác nguồn có thể tạo ra.
- Độ chính xác database lưu được.
- Độ chính xác JSON API phát ra.
- Quy tắc truncate hay round khi giảm precision.

Ví dụ, nếu API chỉ hỗ trợ milliseconds, có thể chuẩn hóa trước khi ghi:

~~~java
Instant normalized = instant.truncatedTo(ChronoUnit.MILLIS);
~~~

Không tự làm tròn nếu nghiệp vụ yêu cầu cắt phần dư; hai cách có thể tạo kết quả khác nhau gần ranh giới giây.

Nếu consumer dùng JavaScript `Date`, độ chính xác thường chỉ đến milliseconds. Nếu gửi nano giây, consumer đó có thể bỏ phần precision bổ sung khi parse. Cần công bố rõ precision để client không giả định giữ được toàn bộ chữ số.

## 9. Dùng @JsonFormat cho format riêng của property

Khi một API legacy yêu cầu pattern riêng, có thể dùng `@JsonFormat` trên property:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.LocalDate;

public class ReportRequest {
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "dd-MM-uuuu")
    private LocalDate reportDate;

    public LocalDate getReportDate() {
        return reportDate;
    }

    public void setReportDate(LocalDate reportDate) {
        this.reportDate = reportDate;
    }
}
~~~

JSON:

~~~json
{
  "reportDate": "12-11-2026"
}
~~~

Dùng `uuuu` khi cần strict proleptic year với `DateTimeFormatter`; pattern `yyyy` là year-of-era và có ngữ nghĩa khác trong strict parsing.

Với timestamp có offset, pattern phải giữ được offset. Tuy nhiên, chỉ nên tự định nghĩa pattern khi hợp đồng thực sự yêu cầu; formatter ISO tiêu chuẩn thường dễ tương tác hơn.

Không gắn timezone tùy tiện cho `LocalDateTime`. Kiểu này không đại diện một instant và không chứa offset. Nếu cần timezone, đổi kiểu sang `OffsetDateTime`/`ZonedDateTime` hoặc truyền ZoneId riêng rồi quy đổi theo quy tắc nghiệp vụ.

## 10. DST và lịch địa phương

Một thời gian địa phương có thể không tồn tại hoặc bị lặp lại khi chuyển daylight saving time ở một số vùng.

Ví dụ ở vùng có DST:

- Đồng hồ nhảy từ 01:59 lên 03:00: một số giờ local không tồn tại.
- Đồng hồ quay lại từ 02:00 về 01:00: một số giờ local xuất hiện hai lần.

Một `LocalDateTime` như `2026-10-25T02:30` có thể chưa đủ để xác định instant nếu vùng timezone có overlap vào thời điểm đó.

Với lịch hẹn hoặc lịch chạy định kỳ:

~~~java
LocalDateTime local = LocalDateTime.of(2026, 10, 25, 2, 30);
ZoneId zone = ZoneId.of("Europe/Paris");

List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
~~~

- Không có offset hợp lệ: local time nằm trong DST gap.
- Có một offset: thời điểm xác định duy nhất.
- Có hai offset: local time nằm trong DST overlap và cần chọn offset theo chính sách.

Hãy quyết định rõ hệ thống sẽ từ chối giờ không tồn tại, tự dịch sang giờ hợp lệ tiếp theo hay áp dụng quy tắc khác. Với giờ bị lặp, xác định chọn lần xuất hiện đầu hay sau. Không để behavior này ngầm phụ thuộc vào cách gọi `atZone()`.

## 11. Biểu diễn số: JSON number, string hay integer theo đơn vị nhỏ nhất?

JSON có một kiểu number về mặt cú pháp, nhưng client có thể ánh xạ nó vào kiểu số khác nhau.

Ví dụ cùng một giá trị:

~~~json
{
  "amount": 1250.50,
  "amountText": "1250.50",
  "amountMinorUnits": 125050
}
~~~

Các lựa chọn:

| Biểu diễn | Ưu điểm | Rủi ro/đánh đổi |
|---|---|---|
| JSON number thập phân | Dễ đọc, tương thích với BigDecimal ở Java | Một số client parse thành binary floating point và mất precision |
| Chuỗi decimal | Giữ chính xác chữ số và scale theo quy ước chuỗi | Consumer phải parse; schema cần mô tả format |
| Số nguyên minor units | Tránh sai số thập phân trong phép tính tiền | Phải biết currency scale và đơn vị; không phải currency nào cũng có 2 chữ số |
| JSON number nguyên lớn | Gọn và dễ xử lý với BigInteger | Một số runtime như JavaScript không giữ mọi integer lớn chính xác |

Đối với tiền, chọn một representation và công bố rõ currency, scale, rounding mode. Không giả định mọi tiền tệ đều có hai chữ số thập phân.

## 12. BigDecimal và Double khác nhau

`BigDecimal` biểu diễn số thập phân bằng precision/scale, phù hợp cho tiền và số đo cần độ chính xác thập phân. `double` dùng binary floating point nên nhiều số thập phân không thể biểu diễn chính xác.

Ví dụ:

~~~java
BigDecimal exact = new BigDecimal("0.1");
double approximate = 0.1;
~~~

Không tạo BigDecimal từ double nếu cần giá trị decimal chính xác:

~~~java
BigDecimal unsafe = new BigDecimal(0.1);
BigDecimal safe = new BigDecimal("0.1");
~~~

Giá trị `unsafe` chứa biểu diễn binary floating point đã làm tròn của double. Dùng String hoặc `BigDecimal.valueOf(double)` khi phải bắt đầu từ double, nhưng với dữ liệu tiền tệ nên nhận decimal trực tiếp từ input đã được kiểm soát.

Khi deserialize JSON number vào field `BigDecimal`, Jackson có thể đọc decimal chính xác theo nội dung số. Khi deserialize vào `Double`, độ chính xác binary floating point áp dụng.

## 13. Cấu hình BigDecimal cho dữ liệu không có kiểu đích cụ thể

Nếu DTO khai báo rõ:

~~~java
private BigDecimal amount;
~~~

Jackson biết kiểu đích và deserialize vào BigDecimal.

Nhưng với kiểu tổng quát như `Object`, `Map<String, Object>` hoặc một số trường hợp tree model, Jackson phải chọn kiểu Java cho number không có target type cụ thể.

Có thể cấu hình:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
    .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
    .build();
~~~

- `USE_BIG_DECIMAL_FOR_FLOATS`: dùng BigDecimal cho floating-point number trong untyped deserialization.
- `USE_BIG_INTEGER_FOR_INTS`: dùng BigInteger cho integer trong untyped deserialization.

Hai feature này không có nghĩa mọi field Float/Double/Integer đã khai báo tường minh đều tự đổi kiểu. Chúng chủ yếu tác động đến number không có kiểu đích cụ thể.

Nếu dữ liệu được đọc vào `JsonNode`, cách node số được tạo cũng chịu ảnh hưởng bởi cấu hình tương ứng và phiên bản Jackson. Khi cần giữ chính xác decimal trong tree, hãy bật và kiểm thử `USE_BIG_DECIMAL_FOR_FLOATS` trên mapper dùng để đọc tree.

## 14. BigDecimal và cách ghi số dạng plain hay scientific notation

Một `BigDecimal` có thể có biểu diễn dạng scientific notation:

~~~java
BigDecimal value = new BigDecimal("1E+3");
~~~

JSON number cho phép exponent, vì vậy `1E+3` là biểu diễn số hợp lệ và tương đương 1000 về giá trị. Nhưng một số consumer hoặc hợp đồng muốn dạng plain:

~~~json
1000
~~~

Jackson Core có tùy chọn `WRITE_BIGDECIMAL_AS_PLAIN` (ở các phiên bản mới có thể cấu hình qua `StreamWriteFeature.WRITE_BIGDECIMAL_AS_PLAIN`) để yêu cầu ghi BigDecimal không dùng exponent.

Ví dụ với API Core tương ứng phiên bản:

~~~java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamWriteFeature.WRITE_BIGDECIMAL_AS_PLAIN)
    .build();

ObjectMapper mapper = JsonMapper.builder(factory)
    .build();
~~~

Tên API/feature cần đối chiếu với phiên bản Jackson Core đang dùng. Nếu hợp đồng yêu cầu đúng dạng chuỗi decimal với số chữ số cụ thể, hãy định dạng thành String theo quy tắc nghiệp vụ thay vì chỉ dựa vào plain-number output.

Plain notation không tự đặt scale. `1.0`, `1.00` và `1` có cùng giá trị số nhưng có thể mang ý nghĩa scale khác nhau trong hợp đồng. Nếu scale quan trọng, định nghĩa rõ số chữ số thập phân và kiểm thử output.

## 15. Integer lớn và giới hạn JavaScript

JavaScript `Number` dùng IEEE-754 double. Integer chỉ được biểu diễn chính xác liên tục đến:

~~~text
9007199254740991
~~~

Đây là `Number.MAX_SAFE_INTEGER`. Nếu API gửi ID, account number hoặc counter lớn hơn giới hạn này dưới dạng JSON number, một số consumer JavaScript có thể làm tròn và thay đổi giá trị.

Ví dụ:

~~~json
{
  "accountId": 9007199254740993
}
~~~

Consumer parse thành JavaScript Number có thể không giữ chính xác integer ban đầu.

Với identifier lớn, thường nên dùng chuỗi:

~~~json
{
  "accountId": "9007199254740993"
}
~~~

Đừng dùng kiểu số chỉ vì giá trị trông giống số. Nếu không thực hiện phép toán số học và chỉ dùng làm định danh, String thường là biểu diễn phù hợp hơn.

Trong Java:

- `int`: số nguyên 32-bit.
- `long`: số nguyên 64-bit.
- `BigInteger`: số nguyên có độ lớn tùy ý.

Kiểu Java có thể giữ chính xác giá trị, nhưng không đảm bảo consumer khác cũng giữ được nếu wire type là JSON number.

## 16. Coercion: có chấp nhận số được gửi dưới dạng string không?

Một số payload có thể gửi:

~~~json
{
  "quantity": "42"
}
~~~

trong khi DTO khai báo:

~~~java
private int quantity;
~~~

Jackson có các quy tắc coercion cho phép hoặc từ chối chuyển đổi giữa string và number tùy cấu hình, kiểu đích và phiên bản. Không nên dựa vào coercion ngầm như một phần của hợp đồng API.

Nếu schema yêu cầu JSON number, hãy gửi:

~~~json
{
  "quantity": 42
}
~~~

Nếu schema yêu cầu string decimal, hãy khai báo field String và parse bằng logic được kiểm soát. Với API cần strict typing, cấu hình coercion/validation rõ ràng và test các trường hợp:

- Number được gửi thành String.
- String rỗng hoặc chỉ có whitespace.
- Decimal được gửi vào integer.
- Integer vượt miền kiểu đích.
- Boolean hoặc null gửi vào numeric field.
- Exponent notation như `1.25e3`.

Một payload parse thành công không nhất thiết là payload tuân thủ hợp đồng.

## 17. NaN và Infinity không phải JSON number chuẩn

IEEE-754 có các giá trị `NaN`, `Infinity` và `-Infinity`. JSON chuẩn không định nghĩa chúng là number hợp lệ.

Nếu ứng dụng dùng Float/Double, kiểm tra giá trị trước khi serialize:

~~~java
if (!Double.isFinite(measurement)) {
    throw new IllegalArgumentException("measurement must be finite");
}
~~~

Không phụ thuộc vào cấu hình cho phép ghi non-numeric number dưới dạng token đặc biệt hoặc chuỗi. Nếu cần biểu diễn trạng thái không có số đo, hãy dùng null hoặc một field status riêng theo schema.

## 18. Phiên bản hóa hợp đồng thời gian và số

Một API nên có chính sách thay đổi tương thích.

### 18.1. Thay đổi thường có thể tương thích

- Thêm field tùy chọn mới mà consumer cũ bỏ qua được.
- Mở rộng enum nếu consumer có chính sách unknown value an toàn.
- Bổ sung field metadata không làm thay đổi ý nghĩa field hiện tại.
- Tăng độ dài chuỗi timestamp nếu consumer đã chấp nhận ISO-8601 theo formatter linh hoạt và hợp đồng cho phép precision cao hơn.

Ngay cả thay đổi additive cũng cần kiểm tra consumer strict unknown-property hoặc schema validation nghiêm ngặt.

### 18.2. Thay đổi thường là breaking

- Đổi timestamp string thành epoch number.
- Đổi epoch milliseconds thành epoch seconds.
- Bỏ timezone/offset khỏi field vốn là instant.
- Đổi field tiền từ JSON number sang string.
- Đổi integer sang decimal hoặc ngược lại.
- Thay đổi đơn vị như milliseconds thành microseconds.
- Giảm precision làm mất dữ liệu consumer đang sử dụng.
- Đổi ý nghĩa null, giá trị mặc định hoặc cách làm tròn.

Đừng âm thầm tái sử dụng cùng tên field với kiểu hoặc đơn vị mới.

### 18.3. Chiến lược thêm field mới

Nếu cần đổi representation, có thể giữ field cũ trong giai đoạn chuyển tiếp và thêm field mới có tên thể hiện semantics:

~~~json
{
  "createdAtEpochMillis": 1794479400000,
  "createdAt": "2026-11-12T10:30:00Z",
  "amount": "1250.50",
  "currency": "USD"
}
~~~

Tài liệu cần chỉ rõ field nào là canonical, field nào deprecated, thời điểm ngừng hỗ trợ và quy tắc khi cả hai cùng xuất hiện.

Không để client gửi hai field mâu thuẫn mà server tự chọn một cách không công bố. Nếu cả hai cùng có mặt, nên xác thực chúng biểu diễn cùng giá trị hoặc từ chối payload.

## 19. Kiểm thử hợp đồng với ObjectMapper

Test serialization và deserialization riêng biệt. Đừng chỉ kiểm tra object sau khi round-trip vì serializer và deserializer cùng sai theo một cách vẫn có thể cho kết quả nội bộ giống nhau.

Ví dụ với Instant:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import java.time.Instant;

class TimestampContractTest {
    private final ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();

    @Test
    void writesCanonicalUtcTimestamp() throws Exception {
        Instant instant = Instant.parse("2026-11-12T10:30:00Z");

        String json = mapper.writeValueAsString(instant);

        assertEquals("\"2026-11-12T10:30:00Z\"", json);
    }

    @Test
    void readsTimestampWithOffsetAsInstant() throws Exception {
        Instant instant = mapper.readValue(
            "\"2026-11-12T17:30:00+07:00\"",
            Instant.class
        );

        assertEquals(
            Instant.parse("2026-11-12T10:30:00Z"),
            instant
        );
    }
}
~~~

Test với offset xác nhận các timestamp có offset khác nhau nhưng cùng instant được chuẩn hóa đúng về timeline UTC.

Với số tiền:

~~~java
BigDecimal amount = new BigDecimal("1250.50");
String json = mapper.writeValueAsString(amount);

BigDecimal decoded = mapper.readValue(json, BigDecimal.class);

assertEquals(0, amount.compareTo(decoded));
~~~

Nếu scale là một phần của hợp đồng, kiểm tra thêm `scale()` hoặc `equals()`. `compareTo()` so sánh giá trị số, còn `BigDecimal.equals()` xét cả scale.

Nên có test contract cho:

- Timestamp UTC, offset dương và offset âm.
- Timestamp thiếu offset nếu API không cho phép.
- Precision giây/mili/nano.
- Epoch seconds và milliseconds nếu được hỗ trợ.
- Ngày lịch và local date-time.
- DST gap/overlap cho lịch địa phương.
- Decimal exponent, trailing zeros và số rất lớn.
- Integer vượt giới hạn 32/64-bit.
- JSON number so với numeric string.
- NaN/Infinity và null.

## 20. Tài liệu hóa schema

OpenAPI/JSON Schema nên thể hiện cả kiểu JSON lẫn semantics.

Ví dụ:

~~~yaml
properties:
  occurredAt:
    type: string
    format: date-time
    description: Timestamp RFC 3339, normalized to UTC, precision milliseconds.
    example: "2026-11-12T10:30:00.123Z"

  amount:
    type: string
    pattern: '^-?[0-9]+(\\.[0-9]{2})?$'
    description: Decimal amount with exactly two fractional digits.

  accountId:
    type: string
    description: Identifier; do not parse as a floating-point number.
~~~

Nếu amount là JSON number, khai báo `type: number` và precision/scale theo khả năng schema tool. JSON Schema number không tự bảo đảm consumer dùng decimal arithmetic chính xác.

Schema cần nói rõ:

- Timezone/offset bắt buộc hay không.
- Timestamp chuẩn UTC hay giữ offset gốc.
- Precision tối đa và quy tắc truncate/round.
- Epoch unit nếu dùng số.
- Currency và scale của tiền.
- Range và giới hạn integer.
- Numeric string có được chấp nhận hay không.
- Null, missing và default semantics.

## 21. Checklist khi thay đổi định dạng thời gian hoặc số

Trước khi phát hành một version API mới, hãy trả lời:

1. Kiểu Java phản ánh đúng ý nghĩa nghiệp vụ chưa?
2. JSON type là string, number hay integer?
3. Timestamp có timezone/offset không? Nếu không, đó có thực sự là local wall-clock time?
4. Numeric timestamp dùng seconds, milliseconds hay đơn vị khác?
5. Precision thời gian là seconds, milliseconds, microseconds hay nanoseconds?
6. Decimal cần giữ scale hay chỉ cần giá trị số?
7. Consumer JavaScript có thể làm mất precision của integer lớn không?
8. Có chấp nhận exponent notation hoặc numeric string không?
9. Null và field bị thiếu có semantics riêng không?
10. Mapper production có cấu hình module/features giống test không?
11. Thay đổi có phá consumer cũ hoặc schema validation không?
12. Có migration/deprecation window và contract tests không?

## 22. Ghi nhớ

- Định dạng thời gian và số là một phần của hợp đồng JSON: kiểu, đơn vị, timezone, precision và scale đều cần được công bố.
- Dùng `Instant` cho thời điểm trên timeline; dùng `LocalDate` cho ngày lịch và `LocalDateTime` chỉ khi không cần xác định instant.
- Phân biệt UTC instant, offset và ZoneId; offset không thay thế quy tắc timezone của một vùng.
- Ưu tiên chuỗi ISO-8601/RFC 3339 cho timestamp API và cấu hình `JavaTimeModule` cùng `WRITE_DATES_AS_TIMESTAMPS` rõ ràng.
- Epoch seconds và milliseconds không thể hoán đổi; đặt tên field và test đơn vị.
- Thống nhất precision thời gian xuyên suốt API, database và consumer.
- Dùng `BigDecimal` cho decimal chính xác; tránh tạo nó từ double nếu cần giá trị thập phân chính xác.
- `USE_BIG_DECIMAL_FOR_FLOATS` và `USE_BIG_INTEGER_FOR_INTS` giúp kiểm soát untyped number, không thay đổi mọi field đã khai báo kiểu cụ thể.
- JSON number lớn có thể mất precision ở consumer JavaScript; identifier lớn thường nên dùng String.
- Đổi kiểu JSON, đơn vị, timezone semantics hoặc precision thường là breaking change; thêm field mới và deprecate field cũ theo lộ trình.
- Kiểm thử output JSON độc lập với round-trip và tài liệu hóa schema cho consumer.

