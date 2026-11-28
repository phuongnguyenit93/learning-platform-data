# Mô tả đơn vị, múi giờ, định dạng thời gian và định danh tài nguyên

Schema đầu vào của một tool cần giúp mô hình hiểu chính xác ý nghĩa của từng giá trị. Một tham số số có thể là mét, kilomet, giây hoặc số tiền; một chuỗi thời gian có thể là ngày lịch, giờ địa phương hoặc một thời điểm tuyệt đối; một chuỗi định danh có thể là mã tài sản, mã khách hàng hoặc mã cuộc hội thoại. Nếu mô tả chỉ ghi “giá trị”, “thời gian” hay “ID”, mô hình có thể tạo đầu vào đúng kiểu dữ liệu nhưng sai ý nghĩa.

Trong Spring AI, `@Tool` mô tả khả năng mà ứng dụng cung cấp và `@ToolParam` mô tả các tham số của khả năng đó. Nội dung `description` là một phần của hợp đồng mà mô hình dùng để tạo đối số. Schema có thể mô tả kiểu, định dạng và một số giới hạn, nhưng ứng dụng vẫn phải kiểm tra đơn vị, chuyển đổi thời gian, xác thực định danh và kiểm tra quyền trước khi gọi dịch vụ nghiệp vụ.

## 1. Mô tả tham số là hợp đồng ngữ nghĩa

Một schema tốt trả lời được bốn câu hỏi:

1. **Giá trị đại diện cho điều gì?** Ví dụ mã thiết bị, thời điểm bắt đầu hay tổng năng lượng tiêu thụ.
2. **Giá trị dùng đơn vị hoặc định dạng nào?** Ví dụ `kWh`, `VND`, ISO-8601 có offset hoặc mã tài sản do hệ thống cấp.
3. **Giới hạn hợp lệ là gì?** Ví dụ số dương, khoảng thời gian tối đa 31 ngày, hoặc một trong các mã đơn vị được hỗ trợ.
4. **Ứng dụng diễn giải giá trị ra sao?** Ví dụ chuyển về UTC trước khi truy vấn, chuyển đổi đơn vị trước khi tổng hợp hoặc kiểm tra quyền truy cập tài nguyên.

Mô tả chung chung:

```java
@ToolParam(description = "Thời gian bắt đầu")
String from;
```

Mô tả có hợp đồng rõ hơn:

```java
@ToolParam(
        description = "Thời điểm bắt đầu truy vấn theo ISO-8601, bắt buộc có UTC offset, ví dụ 2026-11-27T08:00:00+07:00. Khoảng truy vấn tính từ thời điểm này và không bao gồm thời điểm kết thúc.")
String from;
```

Mô tả nên ngắn, trực tiếp và nhất quán với cách code xử lý. Nếu schema ghi `kWh` nhưng service coi giá trị là `Wh`, hoặc mô tả thời gian có offset nhưng code lại diễn giải như giờ UTC, hợp đồng đã bị phá vỡ dù JSON vẫn hợp lệ.

## 2. Đơn vị đo và độ chính xác của số

Không nên để một số đo đứng riêng mà không có đơn vị. Giá trị `12.5` có thể là 12,5 mét, kilomet, độ C hoặc kilowatt-giờ. Có hai cách biểu diễn phổ biến.

**Cách thứ nhất: đơn vị được cố định trong mô tả tham số.** Cách này phù hợp khi tool chỉ hỗ trợ một đơn vị:

```java
@ToolParam(description = "Khoảng cách tính bằng mét (m), là số không âm")
BigDecimal distanceMeters;
```

**Cách thứ hai: gửi giá trị và đơn vị riêng.** Cách này phù hợp khi người gọi có thể chọn nhiều đơn vị:

```json
{
  "distance": 2.5,
  "unit": "km"
}
```

Ứng dụng cần kiểm tra `unit` thuộc tập được hỗ trợ, sau đó chuyển về một đơn vị chuẩn trước khi tính toán. Không dựa vào suy đoán từ tên biến hoặc ngôn ngữ người dùng.

| Đại lượng | Ví dụ đơn vị | Lưu ý khi thiết kế |
| --- | --- | --- |
| Khoảng cách | `m`, `km`, `mi` | Nêu rõ đơn vị đầu vào và đầu ra; không trộn hệ mét với hệ Anh |
| Khối lượng | `g`, `kg`, `lb` | Xác định có chấp nhận số âm hay không |
| Nhiệt độ | `C`, `F`, `K` | Chuyển đổi theo công thức nhiệt độ, không chỉ nhân hệ số |
| Năng lượng | `Wh`, `kWh`, `J` | Ghi rõ đại lượng là năng lượng hay công suất |
| Thời lượng | `ms`, `s`, `min`, `h` | Phân biệt thời lượng với thời điểm trên lịch |
| Tiền tệ | `VND`, `USD`, `EUR` | Gửi mã tiền tệ riêng; xác định quy tắc làm tròn và số chữ số thập phân |

Với giá trị tiền, nên dùng `BigDecimal` trong Java thay vì `float` hoặc `double` để tránh sai số nhị phân khi tính toán thập phân. Hãy gửi mã tiền tệ theo ISO 4217 hoặc một tập mã được ứng dụng hỗ trợ. Không giả định mọi tiền tệ đều có hai chữ số thập phân; quy tắc scale và làm tròn phải dựa trên loại tiền và nghiệp vụ. Ví dụ, `100000` không đủ nghĩa nếu không biết là VND hay USD.

Với phép tính đo lường, hãy chọn một đơn vị chuẩn nội bộ, chuyển đổi ở ranh giới vào/ra và chỉ làm tròn ở bước được nghiệp vụ quy định. Nếu làm tròn trước khi cộng hoặc so sánh, kết quả có thể khác đáng kể khi xử lý nhiều bản ghi.

Một mô tả đơn vị nên nêu cả giới hạn:

```java
@ToolParam(
        description = "Ngưỡng năng lượng tính bằng kWh, phải lớn hơn hoặc bằng 0 và không vượt quá 100000")
BigDecimal minimumEnergyKwh;
```

Giới hạn trong mô tả giúp mô hình tạo giá trị hợp lý; code vẫn phải kiểm tra `null`, giới hạn số, scale, độ lớn và quy tắc nghiệp vụ. Với đơn vị có nhiều cách viết, nên dùng mã chuẩn như `kWh` thay vì cho phép tùy ý `kilowatt`, `KW giờ`, `số điện`.

## 3. Định dạng thời gian: ngày, giờ địa phương và thời điểm tuyệt đối

Các kiểu thời gian khác nhau trả lời các câu hỏi khác nhau. Trước khi chọn kiểu Java hoặc định dạng JSON, hãy xác định nghiệp vụ cần ngày lịch, giờ trên đồng hồ hay một thời điểm duy nhất trên trục thời gian.

| Nhu cầu | Ví dụ | Kiểu Java thường phù hợp |
| --- | --- | --- |
| Một ngày lịch, không gắn giờ | Ngày sinh, ngày nghỉ | `LocalDate` |
| Giờ trên đồng hồ, chưa gắn múi giờ | Giờ mở cửa 09:00 | `LocalTime` |
| Ngày và giờ địa phương, cần múi giờ riêng | Cuộc hẹn 09:00 tại TP.HCM | `LocalDateTime` kết hợp `ZoneId` |
| Một thời điểm tuyệt đối | Sự kiện đã xảy ra, thời điểm tạo bản ghi | `Instant` |
| Ngày giờ kèm UTC offset | `2026-11-27T08:00:00+07:00` | `OffsetDateTime` |

### ISO-8601 cho thời điểm có offset

Khi tool cần truy vấn một thời điểm, nên yêu cầu chuỗi ISO-8601 có offset, ví dụ:

```text
2026-11-27T08:00:00+07:00
2026-11-27T01:00:00Z
```

Hai chuỗi trên biểu diễn cùng một thời điểm. `Z` là UTC offset bằng 0. Offset cho biết độ lệch so với UTC tại thời điểm đó. Khi nhận `OffsetDateTime`, ứng dụng có thể chuyển sang `Instant` để lưu trữ và truy vấn thống nhất:

```java
OffsetDateTime suppliedTime = OffsetDateTime.parse(input);
Instant queryInstant = suppliedTime.toInstant();
```

Không yêu cầu model tự thêm chữ `Z` cho giờ địa phương. Nếu người dùng nói “8 giờ sáng ở TP.HCM”, ứng dụng cần biết vùng `Asia/Ho_Chi_Minh` để xác định offset phù hợp tại ngày đó. Nếu chỉ nhận `2026-11-27T08:00:00` mà không có offset hay vùng thời gian, chuỗi này không xác định được một thời điểm tuyệt đối.

### Offset khác với múi giờ khu vực

`+07:00` là offset tại một thời điểm. `Asia/Ho_Chi_Minh` là tên vùng thời gian có quy tắc lịch sử và quy tắc thay đổi theo thời gian. Ở các vùng có giờ mùa hè (DST), offset có thể khác nhau tùy ngày. Vì vậy:

- Dùng `Instant` hoặc ISO-8601 có offset khi cần xác định một thời điểm duy nhất.
- Dùng `ZoneId` như `Europe/Paris` hoặc `America/New_York` khi nghiệp vụ phụ thuộc quy tắc địa phương, chẳng hạn lịch hẹn lặp lại hoặc giờ mở cửa.
- Dùng `LocalDate` khi chỉ cần ngày lịch. Không tự chuyển ngày sinh hoặc ngày nghỉ sang UTC vì có thể làm thay đổi ngày.
- Tránh dùng `LocalDateTime` đơn lẻ cho giao dịch hoặc sự kiện cần thứ tự tuyệt đối.

Nếu nhận ngày giờ địa phương cùng zone, cần xác định cách xử lý thời điểm nằm trong khoảng giờ không tồn tại hoặc bị lặp khi DST đổi. Có thể từ chối đầu vào mơ hồ, yêu cầu người dùng chọn offset hoặc áp dụng quy tắc nghiệp vụ đã công bố. Không để thư viện tự điều chỉnh mà không ghi rõ hành vi.

## 4. Mô tả khoảng thời gian và ranh giới truy vấn

Khi tool nhận `from` và `to`, mô tả rõ cả định dạng lẫn cách tính hai đầu mút. Một quy ước thường dùng là khoảng nửa mở `[from, to)`: bao gồm thời điểm bắt đầu và không bao gồm thời điểm kết thúc. Quy ước này giúp ghép các khoảng liên tiếp mà không đếm trùng bản ghi ở ranh giới.

Ví dụ:

```text
from = 2026-11-27T00:00:00+07:00
to   = 2026-11-28T00:00:00+07:00
```

Đây là một ngày địa phương ở UTC+07:00 theo quy ước `[from, to)`. Khi xử lý, ứng dụng cần:

1. Parse cả hai giá trị theo định dạng đã công bố.
2. Chuyển chúng về cùng trục thời gian, thường là `Instant`.
3. Kiểm tra `from` nhỏ hơn `to`.
4. Giới hạn độ dài khoảng truy vấn để tránh truy xuất dữ liệu quá lớn.
5. Gửi điều kiện truy vấn có cùng quy ước inclusive/exclusive với repository hoặc database.

Không được mặc định `to` là cuối ngày với phần mili giây `23:59:59.999`. Cách đó có thể bỏ sót dữ liệu có độ chính xác cao hơn. Dùng khoảng nửa mở đến đầu ngày kế tiếp thường rõ ràng hơn.

## 5. Định danh tài nguyên: dùng mã nào và thuộc phạm vi nào?

Một tham số như `resourceId` cần cho biết nó định danh loại tài nguyên nào, do hệ thống nào cấp và có thể dùng ở phạm vi nào. Các chuỗi `123`, `A-123` hoặc `customer-01` không tự nói lên đó là đơn hàng, khách hàng hay thiết bị.

Mô tả nên nêu:

- Loại tài nguyên: `assetId`, `orderId`, `documentId` hay `conversationId`.
- Nguồn cấp mã: mã nội bộ do hệ thống nghiệp vụ cấp, mã công khai hay mã từ hệ thống đối tác.
- Định dạng: UUID, chuỗi opaque, mã có prefix hoặc một pattern được công bố.
- Phạm vi: tenant, tổ chức, tài khoản hoặc hệ thống mà mã có hiệu lực.
- Cách tìm: truyền đúng ID, không thay bằng tên hiển thị hoặc nhãn gần giống.

Ví dụ mô tả:

```java
@ToolParam(
        description = "Mã định danh tài sản (assetId) do hệ thống quản lý tài sản cấp. Truyền nguyên văn ID từ kết quả tra cứu trước đó; không truyền tên hiển thị, số thứ tự trong danh sách hoặc mã khách hàng.")
String assetId;
```

Nếu ID là UUID, có thể mô tả định dạng UUID và kiểm tra bằng `UUID.fromString`. Nếu ID là chuỗi opaque do hệ thống cấp, đừng tự áp đặt regex UUID hoặc tách cấu trúc bên trong. Ứng dụng nên coi ID là giá trị không có ý nghĩa nội tại ngoài việc tra cứu tài nguyên tương ứng.

### ID không thay thế xác thực và phân quyền

Biết một `orderId` không có nghĩa người gọi có quyền đọc đơn hàng. ID do mô hình gửi cũng là dữ liệu không đáng tin cậy. Ứng dụng cần lấy principal và tenant từ security context đã xác thực, sau đó kiểm tra quyền ở service hoặc repository:

```java
@Tool(description = "Đọc thông tin tài sản mà người dùng hiện tại được phép truy cập")
AssetDetails getAsset(
        @ToolParam(description = "Mã tài sản do hệ thống cấp") String assetId,
        ToolContext toolContext) {

    String principalId = (String) toolContext.getContext().get("principalId");
    String tenantId = (String) toolContext.getContext().get("tenantId");

    if (principalId == null || tenantId == null) {
        throw new AccessDeniedException("Thiếu ngữ cảnh xác thực");
    }

    return assetService.findForPrincipalAndTenant(assetId, principalId, tenantId);
}
```

Đây là ví dụ ranh giới trách nhiệm; ứng dụng cần kiểm tra kiểu dữ liệu, sự hiện diện và tính tin cậy của context trước khi dùng. `ToolContext` phải được tạo từ phiên đã xác thực, không lấy `principalId` hoặc `tenantId` từ prompt. Service cần thực hiện truy vấn có điều kiện tenant và quyền truy cập, tránh tìm theo ID toàn cục rồi mới lọc ở tầng hiển thị.

Nếu người dùng chỉ cung cấp tên như “máy bơm ở tầng 2”, hãy dùng một bước tìm kiếm để trả về danh sách tài nguyên có thể khớp. Khi có nhiều kết quả, yêu cầu người dùng chọn đúng tài nguyên; không để model tự chọn một ID mơ hồ rồi gọi tool có tác động.

## 6. Ví dụ Spring AI kết hợp đơn vị, thời gian và ID

Giả sử ứng dụng có tool đọc dữ liệu năng lượng của một tài sản trong một khoảng thời gian. Tool nhận ID tài sản, hai thời điểm ISO-8601 có offset và đơn vị đầu ra. Nó chuyển thời điểm sang `Instant`, kiểm tra khoảng truy vấn, xác thực quyền và chỉ sau đó gọi service.

```java
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;

import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.stereotype.Component;
import org.springframework.security.access.AccessDeniedException;

@Component
class EnergyTools {

    private final EnergyQueryService energyQueryService;

    EnergyTools(EnergyQueryService energyQueryService) {
        this.energyQueryService = energyQueryService;
    }

    @Tool(description = "Đọc tổng năng lượng tiêu thụ của một tài sản trong khoảng thời gian")
    EnergySummary getEnergy(
            @ToolParam(
                    description = "Mã tài sản do hệ thống cấp; truyền chính xác ID, không dùng tên hiển thị")
            String assetId,

            @ToolParam(
                    description = "Thời điểm bắt đầu theo ISO-8601 có UTC offset, ví dụ 2026-11-27T00:00:00+07:00")
            String from,

            @ToolParam(
                    description = "Thời điểm kết thúc theo ISO-8601 có UTC offset; khoảng truy vấn là [from, to)")
            String to,

            @ToolParam(
                    description = "Đơn vị năng lượng đầu ra; chỉ nhận Wh hoặc kWh")
            String unit,

            ToolContext toolContext) {

        if (assetId == null || assetId.isBlank()) {
            throw new IllegalArgumentException("assetId là bắt buộc");
        }

        if (toolContext == null || toolContext.getContext() == null) {
            throw new AccessDeniedException("Thiếu ngữ cảnh xác thực");
        }
        Object principalValue = toolContext.getContext().get("principalId");
        Object tenantValue = toolContext.getContext().get("tenantId");
        if (!(principalValue instanceof String principalId) || principalId.isBlank()
                || !(tenantValue instanceof String tenantId) || tenantId.isBlank()) {
            throw new AccessDeniedException("Thiếu ngữ cảnh xác thực");
        }

        Instant start = parseInstant(from, "from");
        Instant end = parseInstant(to, "to");
        if (!start.isBefore(end)) {
            throw new IllegalArgumentException("from phải sớm hơn to");
        }
        if (Duration.between(start, end).compareTo(Duration.ofDays(31)) > 0) {
            throw new IllegalArgumentException("Khoảng truy vấn không được vượt quá 31 ngày");
        }

        EnergyUnit outputUnit = EnergyUnit.fromCode(unit);
        return energyQueryService.getForPrincipal(
                assetId, principalId, tenantId, start, end, outputUnit);
    }

    private Instant parseInstant(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(fieldName + " là bắt buộc");
        }
        try {
            return OffsetDateTime.parse(value).toInstant();
        }
        catch (DateTimeParseException ex) {
            throw new IllegalArgumentException(
                    fieldName + " phải là ISO-8601 có UTC offset", ex);
        }
    }
}
```

Trong ví dụ, `EnergyUnit.fromCode` cần từ chối mọi giá trị ngoài `Wh` và `kWh`; `EnergyQueryService` chịu trách nhiệm kiểm tra quyền truy cập tài sản và chuyển đổi số đo theo quy tắc chính xác. Đoạn code đã kiểm tra context, định dạng thời gian, thứ tự mốc và giới hạn 31 ngày; các kiểu `EnergySummary`, `EnergyUnit` và service là kiểu miền do ứng dụng định nghĩa.

`OffsetDateTime.parse` yêu cầu chuỗi có offset hoặc `Z`. Vì vậy, đầu vào `2026-11-27T08:00:00` sẽ bị từ chối thay vì được diễn giải ngầm theo múi giờ máy chủ. Đây là hành vi phù hợp khi hợp đồng tool yêu cầu thời điểm tuyệt đối.

## 7. Đầu ra cũng cần có đơn vị và định dạng rõ ràng

Không chỉ đầu vào mới cần mô tả. Kết quả tool nên giữ thông tin đơn vị và ngữ cảnh thời gian để mô hình không diễn giải sai.

Ví dụ kết quả có cấu trúc:

```json
{
  "assetId": "asset-8f31",
  "from": "2026-11-26T17:00:00Z",
  "to": "2026-11-27T17:00:00Z",
  "interval": "[from,to)",
  "energy": "125.450",
  "unit": "kWh"
}
```

Nên dùng DTO có tên trường rõ nghĩa, kèm unit và mốc thời gian đã chuẩn hóa. Với số thập phân cần độ chính xác, cân nhắc biểu diễn decimal theo dạng chuỗi nếu hợp đồng JSON/provider cần tránh làm tròn ngoài ý muốn. Nếu kết quả hiển thị theo múi giờ địa phương, nên trả thêm tên vùng như `Asia/Ho_Chi_Minh` hoặc cung cấp cả thời điểm UTC và thời điểm hiển thị.

Không trả một con số như `125.45` mà thiếu đơn vị. Cũng không nên chỉ trả chuỗi “hôm qua” hoặc “lúc 8 giờ” vì cách diễn giải phụ thuộc ngày hiện tại và múi giờ. Hãy trả thời điểm tuyệt đối, sau đó để lớp trình bày chuyển thành ngôn ngữ tự nhiên.

## 8. Kiểm thử schema và cách diễn giải giá trị

Kiểm thử cần bao gồm cả schema mà Spring AI tạo ra và logic xử lý tại runtime. Một unit test gọi trực tiếp phương thức không chứng minh rằng mô hình đã nhận đúng mô tả; một test schema cũng không chứng minh service kiểm tra quyền đúng.

| Nhóm kiểm thử | Trường hợp cần có | Kết quả mong đợi |
| --- | --- | --- |
| Đơn vị | Giá trị hợp lệ với `Wh`, `kWh`; đơn vị không hỗ trợ | Chấp nhận mã hợp lệ, từ chối mã không hỗ trợ |
| Độ chính xác | Số thập phân nhiều chữ số, giá trị biên | Không mất độ chính xác trước bước làm tròn nghiệp vụ |
| Thời gian | ISO-8601 có `Z`, có offset, thiếu offset, sai định dạng | Parse đúng thời điểm; từ chối chuỗi thiếu thông tin theo hợp đồng |
| Khoảng thời gian | `from < to`, bằng nhau, `from > to`, khoảng quá dài | Chấp nhận khoảng hợp lệ và từ chối khoảng sai/vượt giới hạn |
| Múi giờ | Hai chuỗi có offset khác nhau nhưng cùng Instant | Truy vấn cùng một thời điểm tuyệt đối |
| Định danh | ID tồn tại, sai định dạng, không tồn tại, thuộc tenant khác | Không trả dữ liệu ngoài phạm vi quyền |
| Ngữ cảnh | Thiếu principal hoặc tenant trong `ToolContext` | Từ chối trước khi gọi service |
| Schema | Description chứa đơn vị, format và quy ước khoảng | Schema được tạo đúng và mô tả gửi tới model đầy đủ |

Ví dụ kiểm thử chuyển đổi thời gian:

```java
@Test
void parsesEquivalentOffsetsAsSameInstant() {
    Instant first = OffsetDateTime
            .parse("2026-11-27T08:00:00+07:00")
            .toInstant();

    Instant second = OffsetDateTime
            .parse("2026-11-27T01:00:00Z")
            .toInstant();

    assertThat(first).isEqualTo(second);
}

@Test
void rejectsDateTimeWithoutOffset() {
    assertThatThrownBy(() -> OffsetDateTime.parse("2026-11-27T08:00:00"))
            .isInstanceOf(DateTimeParseException.class);
}
```

Ngoài test trực tiếp, cần kiểm tra schema callback/tool được gửi đến model: mô tả có ghi rõ đơn vị, format, offset, kiểu ID và giới hạn hay không. Nếu provider có chế độ strict hoặc ràng buộc schema riêng, hãy chạy contract test với đúng provider và model dùng trong triển khai.

## 9. Quy trình viết schema có ý nghĩa rõ ràng

Khi thiết kế một tool, hãy thực hiện lần lượt:

1. Đặt tên tham số theo loại dữ liệu cụ thể, chẳng hạn `assetId`, `from`, `to`, `energyUnit` thay vì `id`, `start`, `end`, `unit` nếu tên ngắn gây mơ hồ.
2. Ghi đơn vị trong tên hoặc mô tả; nếu có nhiều đơn vị, truyền mã đơn vị riêng và kiểm tra allowlist.
3. Chọn kiểu thời gian theo nghiệp vụ: `LocalDate` cho ngày lịch, `Instant` cho thời điểm tuyệt đối, `OffsetDateTime` cho thời điểm có offset, hoặc `LocalDateTime` kèm `ZoneId` cho giờ địa phương.
4. Quy định định dạng, offset, múi giờ, độ chính xác và ranh giới khoảng thời gian.
5. Mô tả nguồn cấp và phạm vi của ID; không coi ID là bằng chứng quyền truy cập.
6. Lấy principal và tenant từ ngữ cảnh xác thực do ứng dụng cấp, rồi kiểm tra quyền tại service.
7. Kiểm tra và chuẩn hóa dữ liệu ở runtime; không phụ thuộc hoàn toàn vào mô tả hoặc schema.
8. Kiểm thử cả giá trị hợp lệ, sai định dạng, sai đơn vị, biên thời gian và truy cập tài nguyên trái phép.

Một schema tốt giúp mô hình tạo ra đối số có đúng ý nghĩa, còn ứng dụng chịu trách nhiệm bảo đảm giá trị đó hợp lệ và người gọi có quyền sử dụng. Với các tham số về đơn vị, thời gian và định danh tài nguyên, mô tả rõ ràng cùng validation ở phía server là điều kiện để tool calling hoạt động nhất quán và an toàn.
