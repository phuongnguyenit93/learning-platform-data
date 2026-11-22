# Bảo toàn độ chính xác thập phân với BigDecimal

Khi JSON chứa giá tiền, thuế, tỷ lệ hoặc số đo cần độ chính xác thập phân, kiểu Java `BigDecimal` thường phù hợp hơn `double` và `float`. `BigDecimal` biểu diễn một số thập phân bằng giá trị nguyên không dấu phẩy động cùng scale, nhờ đó tránh được sai số nhị phân thường gặp khi dùng kiểu dấu phẩy động.

Jackson hỗ trợ đọc và ghi `BigDecimal` trực tiếp. Nếu kiểu đích của property là `BigDecimal`, Jackson có thể đọc token JSON dạng number thành giá trị thập phân mà không phải chuyển qua `double`. Khi ghi, `BigDecimal` được xuất thành JSON number. Để giữ độ chính xác xuyên suốt, cần chú ý cả kiểu Java, cách tạo `BigDecimal`, cấu hình khi đọc kiểu không xác định và các phép tính/định dạng sau khi ánh xạ.

## 1. Vì sao `double` có thể làm sai số thập phân?

`double` sử dụng biểu diễn dấu phẩy động nhị phân theo chuẩn IEEE 754. Nhiều số thập phân hữu hạn không thể biểu diễn chính xác bằng một phân số nhị phân hữu hạn. Vì vậy, một giá trị quen thuộc như `0.1` có thể được lưu thành một giá trị gần đúng.

```java
double amount = 0.1 + 0.2;
System.out.println(amount); // thường hiển thị 0.30000000000000004
```

Đây không phải lỗi riêng của Jackson. Nó là đặc tính của kiểu `double`. Nếu một giá trị tiền được chuyển từ JSON sang `double`, rồi chuyển tiếp sang `BigDecimal`, phần sai số nhị phân có thể đã xuất hiện trước khi Jackson ghi JSON.

```java
BigDecimal wrong = new BigDecimal(0.1);
System.out.println(wrong);
// 0.1000000000000000055511151231257827021181583404541015625

BigDecimal exact = new BigDecimal("0.1");
System.out.println(exact); // 0.1
```

`new BigDecimal(double)` chuyển chính giá trị nhị phân đang lưu trong `double` sang thập phân chính xác, nên kết quả có thể dài và khác giá trị thập phân mà người dùng dự định nhập. Với dữ liệu đến từ JSON, chuỗi nhập liệu hoặc cấu hình, nên tạo `BigDecimal` từ chuỗi thập phân gốc.

Nếu đã có một `double` và muốn tạo `BigDecimal` theo biểu diễn chuỗi chuẩn của nó, `BigDecimal.valueOf(double)` thường tránh được phần khai triển nhị phân dài:

```java
BigDecimal value = BigDecimal.valueOf(0.1);
System.out.println(value); // 0.1
```

Tuy nhiên, khi nguồn dữ liệu vốn là số thập phân chính xác, cách tốt nhất vẫn là không chuyển qua `double` ngay từ đầu.

## 2. Khai báo `BigDecimal` trong model Java

Một DTO có thể khai báo property tiền dưới dạng `BigDecimal`:

```java
import java.math.BigDecimal;

public class InvoiceRequest {
    private String invoiceCode;
    private BigDecimal totalAmount;

    public InvoiceRequest() {
    }

    public String getInvoiceCode() {
        return invoiceCode;
    }

    public void setInvoiceCode(String invoiceCode) {
        this.invoiceCode = invoiceCode;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
```

JSON gửi số tiền dưới dạng number:

```json
{
  "invoiceCode": "INV-2026-001",
  "totalAmount": 1234567890.123456789
}
```

Đọc bằng `ObjectMapper`:

```java
ObjectMapper mapper = new ObjectMapper();

InvoiceRequest request = mapper.readValue(json, InvoiceRequest.class);
BigDecimal amount = request.getTotalAmount();

System.out.println(amount); // 1234567890.123456789
```

Vì kiểu đích đã là `BigDecimal`, Jackson sử dụng deserializer cho `BigDecimal`. Giá trị không cần đi qua `double` trước khi được gán cho property. Hãy giữ kiểu `BigDecimal` trong các tầng tiếp theo nếu nghiệp vụ vẫn yêu cầu độ chính xác đó.

## 3. Jackson ghi `BigDecimal` thành JSON number

Jackson có serializer tích hợp cho `BigDecimal`. Ví dụ:

```java
BigDecimal amount = new BigDecimal("1234567890.123456789");
String json = mapper.writeValueAsString(amount);

System.out.println(json);
```

Kết quả là một JSON number:

```json
1234567890.123456789
```

Khi `BigDecimal` là property của object, nó cũng được ghi thành number:

```java
InvoiceRequest request = new InvoiceRequest();
request.setInvoiceCode("INV-2026-001");
request.setTotalAmount(new BigDecimal("1234567890.123456789"));

String json = mapper.writeValueAsString(request);
```

Kết quả có dạng:

```json
{
  "invoiceCode": "INV-2026-001",
  "totalAmount": 1234567890.123456789
}
```

Giá trị không được đặt trong dấu ngoặc kép, vì vậy kiểu JSON vẫn là number. Đây là điểm khác biệt với cách ghi số tiền thành chuỗi:

```json
{
  "totalAmount": "1234567890.123456789"
}
```

Number và string là hai kiểu JSON khác nhau. Chỉ chuyển `BigDecimal` thành chuỗi nếu hợp đồng API quy định rõ field là string, chẳng hạn để tương thích với client không thể giữ độ chính xác số lớn. Không tự ý đổi kiểu field giữa các phiên bản API.

### 3.1. Dùng plain notation khi không muốn ký pháp số mũ

`BigDecimal` có thể biểu diễn cùng một giá trị bằng ký pháp số mũ. Ví dụ:

```java
BigDecimal amount = new BigDecimal("1E+3");
System.out.println(amount.toString()); // 1E+3
System.out.println(amount.toPlainString()); // 1000
```

JSON cho phép biểu diễn số bằng ký pháp số mũ, nhưng một số hệ thống tích hợp muốn đầu ra luôn ở dạng thập phân thông thường. Jackson cung cấp feature `WRITE_BIGDECIMAL_AS_PLAIN` để ghi `BigDecimal` theo plain notation:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(SerializationFeature.WRITE_BIGDECIMAL_AS_PLAIN);

String json = mapper.writeValueAsString(new BigDecimal("1E+3"));
System.out.println(json); // 1000
```

Feature này thay đổi cách trình bày số, không đổi kiểu JSON thành string và không làm tròn giá trị. Tên API và vị trí cấu hình có thể thay đổi/deprecate giữa các phiên bản Jackson 2; hãy kiểm tra phiên bản đang dùng. Nếu không có yêu cầu về plain notation, serializer mặc định thường đã phù hợp.

## 4. Đọc số thập phân vào kiểu không xác định

Khi đọc trực tiếp vào property `BigDecimal`, Jackson biết kiểu đích và có thể tạo `BigDecimal`. Nhưng nếu đọc JSON vào `Object`, `Map<String, Object>` hoặc một cấu trúc không có kiểu cụ thể cho giá trị số, Jackson cần chọn một kiểu mặc định cho floating-point number.

Theo cấu hình mặc định thường dùng, số thực trong dữ liệu không định kiểu được biểu diễn bằng `Double`. Khi cần giữ số thập phân chính xác trong `Object` hoặc `Map`, bật:

```java
DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS
```

Ví dụ:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

Map<String, Object> values = mapper.readValue(
        "{\"amount\": 0.1, \"tax\": 0.075}",
        new TypeReference<Map<String, Object>>() {}
);

BigDecimal amount = (BigDecimal) values.get("amount");
BigDecimal tax = (BigDecimal) values.get("tax");
```

Feature này dành cho floating-point number được đọc theo kiểu không định kiểu. Nó không cần thiết khi DTO đã khai báo rõ property là `BigDecimal`. Hãy bật nó khi API thực sự cần đọc các cấu trúc động như `Map<String, Object>` mà vẫn muốn số thập phân được giữ ở dạng `BigDecimal`.

## 5. Đọc và ghi `BigDecimal` bằng streaming API

Khi làm việc trực tiếp với `JsonParser` và `JsonGenerator`, Jackson cung cấp các phương thức chuyên biệt cho số thập phân.

Đọc numeric token thành `BigDecimal`:

```java
try (JsonParser parser = mapper.getFactory().createParser(
        "{\"amount\": 123.4500}"
)) {
    parser.nextToken(); // START_OBJECT
    parser.nextToken(); // FIELD_NAME: amount
    parser.nextToken(); // VALUE_NUMBER_FLOAT

    BigDecimal amount = parser.getDecimalValue();
    System.out.println(amount); // 123.4500
}
```

Ghi `BigDecimal` thành numeric token:

```java
try (JsonGenerator generator = mapper.getFactory().createGenerator(outputStream)) {
    generator.writeStartObject();
    generator.writeNumberField("amount", new BigDecimal("123.4500"));
    generator.writeEndObject();
}
```

`writeNumberField()` ghi giá trị số, không phải chuỗi. Nếu tự xây dựng serializer, hãy dùng `JsonGenerator.writeNumber(BigDecimal)` hoặc `writeNumberField()` thay vì gọi `toString()` rồi ghi bằng `writeStringField()`.

## 6. Bảo toàn scale và quy tắc làm tròn

`BigDecimal` lưu cả giá trị và scale. Hai số `12.5` và `12.50` có cùng giá trị số nhưng scale khác nhau:

```java
BigDecimal a = new BigDecimal("12.5");
BigDecimal b = new BigDecimal("12.50");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
System.out.println(a.scale());           // 1
System.out.println(b.scale());           // 2
```

`compareTo()` so sánh giá trị số, còn `equals()` xét cả giá trị và scale. Khi kiểm tra hai số tiền tương đương về giá trị, thường dùng `compareTo() == 0`; nếu scale là một phần của hợp đồng dữ liệu, hãy kiểm tra scale riêng.

### 6.1. Quy định scale cho tiền tệ

Nếu một loại tiền tệ yêu cầu hai chữ số thập phân, có thể chuẩn hóa bằng `setScale()`:

```java
BigDecimal price = new BigDecimal("19.999");
BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 20.00
```

Không gọi `setScale(2)` mà không truyền rounding mode khi scale hiện tại cần giảm và giá trị không thể biểu diễn chính xác ở scale mới; thao tác đó có thể ném `ArithmeticException`. Hãy chọn quy tắc làm tròn theo chính sách tài chính hoặc nghiệp vụ, chẳng hạn `HALF_UP`, `HALF_EVEN`, `DOWN` hoặc `CEILING`.

### 6.2. Phép chia cần quy định scale hoặc precision

Phép chia có thể tạo số thập phân vô hạn tuần hoàn. Ví dụ `1 / 3` không có biểu diễn thập phân hữu hạn. Vì vậy:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal result = one.divide(
        three,
        4,
        RoundingMode.HALF_UP
);

System.out.println(result); // 0.3333
```

Hoặc dùng `MathContext` để giới hạn precision:

```java
MathContext context = new MathContext(8, RoundingMode.HALF_EVEN);
BigDecimal result = one.divide(three, context);
```

Nếu gọi `divide()` không có scale hoặc `MathContext` cho kết quả thập phân vô hạn, `BigDecimal` có thể ném `ArithmeticException`. Quy tắc làm tròn nên nằm ở tầng nghiệp vụ hoặc domain service, không nên để serializer tự làm tròn số tiền khi xuất JSON.

## 7. Không chuyển qua `double` ở giữa luồng dữ liệu

Một lỗi phổ biến là đọc số thành `double`, thực hiện phép tính, rồi chuyển lại `BigDecimal` trước khi ghi:

```java
double amount = mapper.readValue("0.1", Double.class);
BigDecimal decimal = new BigDecimal(amount);
String json = mapper.writeValueAsString(decimal);
```

Ở đây, giá trị thập phân ban đầu đã được chuyển sang dấu phẩy động nhị phân. Khi tạo `BigDecimal` từ `double`, sai số được giữ lại chứ không tự biến mất.

Hãy đọc trực tiếp vào `BigDecimal`:

```java
BigDecimal amount = mapper.readValue("0.1", BigDecimal.class);
String json = mapper.writeValueAsString(amount);
```

Nếu phải làm việc với dữ liệu động, bật `USE_BIG_DECIMAL_FOR_FLOATS` trước khi đọc. Khi tính toán, tiếp tục sử dụng các phép toán của `BigDecimal` (`add`, `subtract`, `multiply`, `divide`) thay cho toán tử dấu phẩy động.

## 8. `BigDecimal` trong collection, map và wrapper

Jackson xử lý `BigDecimal` giống các kiểu số khác khi nó nằm trong cấu trúc tổng quát, miễn là kiểu đích được cung cấp đầy đủ.

Ví dụ đọc danh sách số thập phân:

```java
List<BigDecimal> prices = mapper.readValue(
        "[19.99, 20.50, 0.0001]",
        new TypeReference<List<BigDecimal>>() {}
);
```

Đọc map có value là `BigDecimal`:

```java
Map<String, BigDecimal> rates = mapper.readValue(
        "{\"VAT\": 0.10, \"discount\": 0.075}",
        new TypeReference<Map<String, BigDecimal>>() {}
);
```

Với wrapper:

```java
public record MoneyResponse(String currency, BigDecimal amount) {
}

MoneyResponse response = mapper.readValue(
        "{\"currency\":\"VND\",\"amount\":125000.00}",
        MoneyResponse.class
);
```

Nếu đọc cùng dữ liệu vào `Map<String, Object>` thay vì `MoneyResponse`, hãy cân nhắc `USE_BIG_DECIMAL_FOR_FLOATS` để số thập phân không bị chuyển thành `Double`.

## 9. JSON number và giới hạn của hệ thống tiêu thụ

JSON định nghĩa một dạng number, không có kiểu riêng tên `BigDecimal`. `BigDecimal` là kiểu Java dùng để giữ số thập phân chính xác khi ánh xạ. Các hệ thống khác có thể dùng kiểu số với giới hạn độ chính xác khác nhau.

Đặc biệt, JavaScript thường dùng `Number` theo chuẩn IEEE 754 double precision cho giá trị số thông thường. Vì vậy, một client JavaScript có thể làm mất độ chính xác khi xử lý số nguyên rất lớn hoặc số thập phân có nhiều chữ số, dù server Java đã đọc và ghi `BigDecimal` chính xác.

Nếu hợp đồng cần truyền một giá trị vượt quá khả năng biểu diễn an toàn của client, hai bên cần thống nhất biểu diễn. Có thể dùng JSON string chứa số thập phân hoặc số nguyên dạng chuỗi, nhưng đó là thay đổi kiểu dữ liệu API và client phải parse theo thư viện decimal phù hợp. Không nên tự chuyển number thành string ở một endpoint mà không cập nhật hợp đồng và client.

Ví dụ hai hợp đồng khác nhau:

```json
{
  "amount": 12345678901234567890.123456789
}
```

```json
{
  "amount": "12345678901234567890.123456789"
}
```

Ở ví dụ đầu, `amount` là JSON number; ở ví dụ sau, `amount` là JSON string. Hãy chọn theo khả năng của các hệ thống tham gia và mô tả rõ trong OpenAPI/schema.

## 10. Những điều cần tránh

- Không dùng `double` hoặc `float` cho giá trị cần chính xác thập phân xuyên suốt.
- Không tạo `BigDecimal` từ `double` nếu ý định ban đầu là một số thập phân chính xác; ưu tiên constructor nhận chuỗi.
- Không đọc vào `Object`/`Map<String, Object>` rồi mặc định rằng số thực đã là `BigDecimal`; cấu hình `USE_BIG_DECIMAL_FOR_FLOATS` nếu cần.
- Không gọi `doubleValue()` trước khi tính toán hoặc ghi JSON nếu cần giữ chính xác.
- Không nhầm JSON number với JSON string; `writeNumber()` và `writeString()` tạo hai kiểu JSON khác nhau.
- Không tự làm tròn trong serializer; làm tròn theo quy tắc nghiệp vụ ở tầng tính toán.
- Không dùng `equals()` khi mục tiêu chỉ là so sánh giá trị số mà scale có thể khác; cân nhắc `compareTo()`.
- Không giả định client JavaScript hoặc hệ thống ngoài có độ chính xác giống `BigDecimal`; kiểm tra hợp đồng và giới hạn của bên nhận.

## 11. Chọn cách cấu hình và sử dụng

| Tình huống | Cách làm phù hợp |
|---|---|
| Property Java có kiểu `BigDecimal` | Đọc trực tiếp bằng `ObjectMapper.readValue()`; không cần ép qua `Double`. |
| Ghi `BigDecimal` ra JSON | Dùng serializer mặc định hoặc `JsonGenerator.writeNumber()` để tạo JSON number. |
| Muốn tránh ký pháp số mũ | Cân nhắc `SerializationFeature.WRITE_BIGDECIMAL_AS_PLAIN` theo phiên bản Jackson. |
| Đọc số thập phân trong `Object` hoặc `Map<String, Object>` | Bật `USE_BIG_DECIMAL_FOR_FLOATS`. |
| Đọc danh sách/map/wrapper chứa số thập phân | Cung cấp `TypeReference`/`JavaType` và khai báo value là `BigDecimal`. |
| Chuẩn hóa số tiền | Dùng `setScale(scale, roundingMode)` theo chính sách tiền tệ. |
| Chia số có kết quả tuần hoàn | Dùng overload `divide()` có scale/rounding hoặc `MathContext`. |
| Client không giữ được độ chính xác JSON number | Thống nhất hợp đồng string và cách parse decimal ở client. |

`BigDecimal` chỉ giúp bảo toàn độ chính xác khi toàn bộ luồng dữ liệu tiếp tục dùng biểu diễn thập phân chính xác. Hãy khai báo đúng kiểu trong DTO, để Jackson đọc trực tiếp vào `BigDecimal`, tránh chuyển qua `double`, quy định rõ scale và rounding ở tầng nghiệp vụ, rồi ghi ra JSON number theo hợp đồng API. Với dữ liệu không định kiểu hoặc client có giới hạn số học khác Java, cần cấu hình và thỏa thuận biểu diễn rõ ràng để không mất độ chính xác ở một bước trung gian.
