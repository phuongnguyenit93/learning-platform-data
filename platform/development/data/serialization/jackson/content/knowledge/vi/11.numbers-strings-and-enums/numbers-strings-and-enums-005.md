# Xử lý giá trị số không hữu hạn theo định dạng và cấu hình

Java có thể biểu diễn các giá trị số không hữu hạn như `NaN`, `Double.POSITIVE_INFINITY` và `Double.NEGATIVE_INFINITY` bằng kiểu `double` hoặc `float`. Các giá trị này có thể xuất hiện sau phép tính, ví dụ chia một số thực cho 0, lấy căn bậc hai của số âm hoặc thực hiện phép toán gây tràn số.

JSON chuẩn không định nghĩa `NaN`, `Infinity` hay `-Infinity` là các giá trị number. Vì vậy, khi dùng Jackson để chuyển dữ liệu Java sang JSON hoặc đọc JSON vào `Double`/`Float`, cần hiểu rõ chính sách của parser và generator. Một giá trị có thể hợp lệ trong Java nhưng không thể được biểu diễn như một JSON number chuẩn.

Trong chương **Số, chuỗi và enum** của Data Serialization Jackson, chủ đề này liên quan trực tiếp đến tính tương thích giữa hệ thống: Jackson có thể ghi các giá trị không hữu hạn dưới dạng chuỗi có dấu ngoặc kép theo cấu hình mặc định; parser có thể được cấu hình để chấp nhận token mở rộng không thuộc JSON chuẩn. API công khai nên quyết định rõ cách xử lý các giá trị này thay vì phụ thuộc vào coercion ngầm.

## 1. NaN và Infinity trong Java

Kiểu dấu phẩy động `double` và `float` có các giá trị đặc biệt:

| Giá trị Java | Ý nghĩa |
|---|---|
| `Double.NaN` | Not a Number, kết quả không phải một số thực hữu hạn. |
| `Double.POSITIVE_INFINITY` | Dương vô cực. |
| `Double.NEGATIVE_INFINITY` | Âm vô cực. |
| `Float.NaN` | NaN ở độ chính xác `float`. |
| `Float.POSITIVE_INFINITY` | Dương vô cực ở kiểu `float`. |
| `Float.NEGATIVE_INFINITY` | Âm vô cực ở kiểu `float`. |

Một số phép tính có thể tạo ra các giá trị này:

```java
double positiveInfinity = 1.0 / 0.0;
double negativeInfinity = -1.0 / 0.0;
double notANumber = 0.0 / 0.0;
double invalidRoot = Math.sqrt(-1.0);

System.out.println(positiveInfinity); // Infinity
System.out.println(negativeInfinity); // -Infinity
System.out.println(notANumber);       // NaN
System.out.println(invalidRoot);      // NaN
```

Không phải mọi phép chia cho 0 trong Java đều tạo Infinity. Chia số nguyên cho 0 sẽ ném `ArithmeticException`; các ví dụ trên sử dụng toán hạng `double`, nên tuân theo quy tắc dấu phẩy động.

Có thể kiểm tra một giá trị có hữu hạn hay không bằng:

```java
double value = calculateMeasurement();

if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Measurement must be finite");
}
```

`Double.isFinite()` trả về `false` cho NaN và cả hai giá trị Infinity. `Float.isFinite()` cung cấp phép kiểm tra tương tự cho `float`. Đây là cách kiểm tra hữu ích trước khi lưu, tính toán tiếp hoặc tạo JSON.

## 2. JSON chuẩn không có number NaN hoặc Infinity

Các dạng number hợp lệ của JSON bao gồm số nguyên, số thập phân và ký pháp số mũ, ví dụ:

```json
{
  "integer": 12,
  "decimal": 12.75,
  "exponent": 1.25e6,
  "negative": -0.5
}
```

Các token sau không phải JSON chuẩn:

```text
NaN
Infinity
-Infinity
```

Một số thư viện hoặc hệ thống có thể chấp nhận các token này như phần mở rộng, nhưng tài liệu JSON không định nghĩa chúng là number. Nếu gửi chúng cho một parser tuân thủ JSON nghiêm ngặt, dữ liệu sẽ bị từ chối.

Có thể biểu diễn các tên đó dưới dạng JSON string:

```json
{
  "measurement": "NaN",
  "upperBound": "Infinity",
  "lowerBound": "-Infinity"
}
```

Đây là JSON hợp lệ, nhưng các giá trị đã trở thành **string**, không còn là JSON number. Client phải hiểu hợp đồng chuỗi đặc biệt và tự chuyển đổi nếu muốn tạo giá trị số tương ứng.

## 3. Jackson ghi NaN và Infinity như thế nào?

Jackson có serializer cho `Double` và `Float`. Khi gặp giá trị không hữu hạn, generator mặc định thường ghi chúng dưới dạng chuỗi có dấu ngoặc kép, chẳng hạn `"NaN"`, `"Infinity"` hoặc `"-Infinity"`. Cách ghi này giữ đầu ra là JSON hợp lệ.

Ví dụ:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.LinkedHashMap;
import java.util.Map;

ObjectMapper mapper = new ObjectMapper();

Map<String, Double> metrics = new LinkedHashMap<>();
metrics.put("normal", 12.5);
metrics.put("notAvailable", Double.NaN);
metrics.put("unbounded", Double.POSITIVE_INFINITY);

String json = mapper.writeValueAsString(metrics);
System.out.println(json);
```

Đầu ra có dạng:

```json
{
  "normal": 12.5,
  "notAvailable": "NaN",
  "unbounded": "Infinity"
}
```

Điểm cần chú ý là hai property cuối có kiểu JSON string. Một client mong đợi mọi giá trị của `metrics` đều là number có thể không xử lý được chúng theo cùng một cách.

### 3.1. Feature điều khiển cách ghi

Trong Jackson Core, feature truyền thống là:

```java
JsonGenerator.Feature.QUOTE_NON_NUMERIC_NUMBERS
```

Feature này quyết định các giá trị dấu phẩy động không hữu hạn có được đặt trong dấu ngoặc kép khi ghi hay không. Mặc định thường được bật để tránh tạo token không thuộc JSON chuẩn.

Ví dụ bật rõ ràng:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.getFactory().enable(
        JsonGenerator.Feature.QUOTE_NON_NUMERIC_NUMBERS
);
```

Ở các phiên bản Jackson 2 mới hơn, có thể gặp API cấu hình tương ứng trong `JsonWriteFeature`:

```java
JsonFactory factory = JsonFactory.builder()
        .enable(JsonWriteFeature.WRITE_NAN_AS_STRINGS)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Tên feature và cách cấu hình có thể khác theo phiên bản Jackson. Hãy kiểm tra API của phiên bản dependency đang dùng. Dù dùng tên cũ hay mới, ý nghĩa vẫn là ghi giá trị không hữu hạn dưới dạng chuỗi JSON.

### 3.2. Vì sao không nên tắt quote để ghi token trần?

Nếu tắt `QUOTE_NON_NUMERIC_NUMBERS` (hoặc feature tương ứng), generator có thể ghi:

```text
{"value":NaN}
```

Đây không phải JSON chuẩn. Một parser nghiêm ngặt ở phía nhận có thể từ chối toàn bộ document. Chỉ nên dùng cách này khi cả hai đầu giao tiếp thống nhất rõ một phần mở rộng ngoài chuẩn và hệ thống nhận chắc chắn hỗ trợ nó. Với API REST hoặc dữ liệu trao đổi giữa nhiều nền tảng, hãy giữ đầu ra tuân thủ JSON chuẩn.

Không nhầm `QUOTE_NON_NUMERIC_NUMBERS` với feature ghi mọi số thành chuỗi. Feature này chỉ liên quan đến các giá trị dấu phẩy động không hữu hạn; số hữu hạn vẫn được ghi thành JSON number.

## 4. Jackson đọc token NaN và Infinity như thế nào?

Theo mặc định, parser Jackson từ chối các token không thuộc JSON chuẩn như `NaN`, `Infinity` và `-Infinity`. Ví dụ:

```java
String json = "{\"value\": NaN}";
Measurement measurement = mapper.readValue(json, Measurement.class);
```

Nếu không bật tính năng mở rộng, parser thường ném `JsonParseException` vì `NaN` không phải token JSON hợp lệ.

### 4.1. Cho phép token không hữu hạn bằng `JsonReadFeature`

Trong Jackson 2.10 trở lên, có thể bật `JsonReadFeature.ALLOW_NON_NUMERIC_NUMBERS` khi tạo `JsonFactory`:

```java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.json.JsonReadFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

JsonFactory factory = JsonFactory.builder()
        .enable(JsonReadFeature.ALLOW_NON_NUMERIC_NUMBERS)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Sau đó parser có thể chấp nhận các token mở rộng này và ánh xạ chúng vào kiểu dấu phẩy động phù hợp:

```java
public class Measurement {
    private double value;

    public double getValue() {
        return value;
    }

    public void setValue(double value) {
        this.value = value;
    }
}

Measurement result = mapper.readValue(
        "{\"value\": NaN}",
        Measurement.class
);

System.out.println(Double.isNaN(result.getValue())); // true
```

Với các phiên bản cũ hơn, Jackson có feature tương ứng `JsonParser.Feature.ALLOW_NON_NUMERIC_NUMBERS`. API cũ có thể được đánh dấu deprecated trong phiên bản mới; ưu tiên `JsonReadFeature` khi phiên bản hỗ trợ.

### 4.2. Cho phép đọc không có nghĩa dữ liệu là JSON chuẩn

`ALLOW_NON_NUMERIC_NUMBERS` mở rộng ngữ pháp mà parser chấp nhận. Nó không làm `NaN` hoặc `Infinity` trở thành number theo chuẩn JSON. Một hệ thống khác dùng parser strict vẫn có thể từ chối dữ liệu đó.

Chỉ bật feature này khi đầu vào đến từ một nguồn được kiểm soát và hợp đồng dữ liệu cho phép các token mở rộng. Đối với request public, thông thường nên yêu cầu client gửi JSON chuẩn và dùng một biểu diễn được thỏa thuận nếu cần thể hiện trạng thái không hữu hạn.

## 5. Xử lý giá trị không hữu hạn trước khi tuần tự hóa

Nếu hợp đồng API yêu cầu field phải luôn là JSON number hữu hạn, cách rõ ràng nhất là kiểm tra giá trị ở tầng ứng dụng trước khi gọi Jackson.

```java
public record SensorReading(String sensorId, Double value) {
    public void validate() {
        if (value != null && !Double.isFinite(value)) {
            throw new IllegalArgumentException(
                    "value must be a finite number"
            );
        }
    }
}
```

Khi chuẩn bị response:

```java
SensorReading reading = sensorService.read(sensorId);
reading.validate();

String json = mapper.writeValueAsString(reading);
```

Kiểm tra trước giúp lỗi xuất hiện tại ranh giới nghiệp vụ với thông báo rõ ràng, thay vì phụ thuộc vào việc generator chuyển giá trị thành chuỗi hoặc ghi token mở rộng. Trong ứng dụng thực tế, có thể dùng Bean Validation với custom constraint `@Finite` cho `Double`/`Float`, hoặc kiểm tra trong service/domain model.

### 5.1. Chọn chính sách thay thế một cách tường minh

Không phải ứng dụng nào cũng muốn từ chối dữ liệu. Tùy ý nghĩa nghiệp vụ, có thể:

- **Từ chối:** ném lỗi validation nếu giá trị không hữu hạn.
- **Biểu diễn trạng thái riêng:** thay giá trị bằng enum hoặc trường trạng thái như `"status": "UNAVAILABLE"`.
- **Dùng null:** chỉ khi hợp đồng định nghĩa rõ null có nghĩa là không có số đo; không nên âm thầm đổi Infinity hoặc NaN thành null.
- **Dùng string:** chỉ khi API định nghĩa rõ các giá trị đặc biệt như `"NaN"` và `"Infinity"` là chuỗi sentinel.

Ví dụ biểu diễn số đo và trạng thái tách biệt:

```java
public record MeasurementResponse(
        Double value,
        String status
) {
    public static MeasurementResponse from(double value) {
        if (Double.isNaN(value)) {
            return new MeasurementResponse(null, "NOT_A_NUMBER");
        }
        if (value == Double.POSITIVE_INFINITY) {
            return new MeasurementResponse(null, "ABOVE_RANGE");
        }
        if (value == Double.NEGATIVE_INFINITY) {
            return new MeasurementResponse(null, "BELOW_RANGE");
        }
        return new MeasurementResponse(value, "OK");
    }
}
```

JSON đầu ra giữ `value` là number hữu hạn hoặc null và dùng `status` để mô tả lý do:

```json
{
  "value": null,
  "status": "NOT_A_NUMBER"
}
```

Đây là hợp đồng rõ ràng hơn việc để client phải đoán một chuỗi đặc biệt có ý nghĩa gì.

## 6. `BigDecimal` không biểu diễn NaN hoặc Infinity

`BigDecimal` chỉ biểu diễn các giá trị thập phân hữu hạn. Không thể tạo:

```java
new BigDecimal("NaN");
new BigDecimal("Infinity");
```

Các biểu thức này ném `NumberFormatException`. Nếu nghiệp vụ cần biểu diễn trạng thái không xác định hoặc vượt miền, hãy dùng một kiểu mô hình khác thay vì cố gắng lưu các giá trị đặc biệt vào `BigDecimal`.

Ví dụ có thể dùng wrapper:

```java
public record DecimalMeasurement(
        BigDecimal value,
        MeasurementStatus status
) {
}

public enum MeasurementStatus {
    VALID,
    NOT_AVAILABLE,
    ABOVE_RANGE,
    BELOW_RANGE
}
```

Khi `status` là `VALID`, `value` chứa `BigDecimal` hữu hạn. Với trạng thái khác, `value` có thể null theo hợp đồng đã định nghĩa. Cách này tránh trộn khái niệm số học với trạng thái đo lường.

## 7. Phân biệt NaN với giá trị null và chuỗi đặc biệt

Ba dạng dữ liệu sau có ý nghĩa khác nhau:

```json
{"value": null}
```

```json
{"value": "NaN"}
```

```text
{"value": NaN}
```

| Biểu diễn | JSON chuẩn? | Kiểu JSON | Ý nghĩa |
|---|---|---|---|
| `null` | Có | Null | Không có giá trị theo hợp đồng. |
| `"NaN"` | Có | String | Một chuỗi có nội dung `NaN`; cần quy ước riêng nếu dùng làm sentinel. |
| `NaN` | Không | Không có kiểu JSON chuẩn tương ứng | Token mở rộng mà một số parser có thể chấp nhận. |

Đừng dùng ba dạng này thay thế nhau mà không xác định ý nghĩa nghiệp vụ. Ví dụ, null có thể có nghĩa thiết bị chưa gửi số đo, trong khi NaN có thể có nghĩa phép tính không xác định. Nếu hai trạng thái cần được phân biệt, hãy mô hình hóa bằng trường trạng thái riêng.

## 8. Ảnh hưởng tới client và hệ thống tích hợp

Một client có thể xử lý JSON number theo quy tắc riêng của ngôn ngữ. Nếu Jackson ghi `"NaN"`, client nhận string và không thể coi đó là number mà không chuyển đổi. Nếu server ghi token `NaN` không có dấu ngoặc kép, parser strict có thể từ chối toàn bộ document.

Với JavaScript, `JSON.parse()` không chấp nhận token trần `NaN` hoặc `Infinity`. JavaScript có giá trị `NaN` và `Infinity` trong runtime, nhưng `JSON.stringify()` có quy tắc riêng: các giá trị không hữu hạn trong object thường được chuyển thành `null`. Vì vậy, việc round-trip giữa Java và JavaScript có thể làm mất sự khác biệt giữa các trạng thái nếu API không mô hình hóa chúng rõ ràng.

Khi tích hợp nhiều ngôn ngữ, hãy định nghĩa schema cho field có thể không hữu hạn. Ví dụ:

```json
{
  "value": 12.5,
  "status": "OK"
}
```

hoặc:

```json
{
  "value": null,
  "status": "NOT_AVAILABLE"
}
```

Hợp đồng có thể giới hạn `value` là number hữu hạn hoặc null và giới hạn `status` vào enum đã công bố. Điều này dễ kiểm tra và tương thích hơn token mở rộng.

## 9. Kiểm thử hành vi của Jackson

Khi API có property `Double` hoặc `Float`, nên kiểm thử cả giá trị hữu hạn lẫn không hữu hạn để xác nhận cấu hình mapper.

Ví dụ kiểm tra serializer mặc định ghi NaN dưới dạng chuỗi:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class NonFiniteNumberTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void nonFiniteDoubleIsWrittenAsJsonStringByDefault() throws Exception {
        String json = mapper.writeValueAsString(Double.NaN);
        JsonNode node = mapper.readTree(json);

        assertTrue(node.isTextual());
        assertEquals("NaN", node.asText());
    }

    @Test
    void finiteDoubleRemainsJsonNumber() throws Exception {
        String json = mapper.writeValueAsString(12.5d);
        JsonNode node = mapper.readTree(json);

        assertTrue(node.isNumber());
        assertEquals(12.5d, node.doubleValue());
    }
}
```

Nếu ứng dụng bật `ALLOW_NON_NUMERIC_NUMBERS`, cần có test cho cả parser mở rộng và parser strict để tránh vô tình áp dụng cấu hình cho những API không được phép nhận token này. Kiểm thử nên gắn với mapper thực tế mà ứng dụng inject, không chỉ một mapper mặc định được tạo riêng trong test.

## 10. Lựa chọn cấu hình theo hợp đồng dữ liệu

| Nhu cầu | Cách xử lý phù hợp |
|---|---|
| Chỉ chấp nhận JSON chuẩn | Không bật `ALLOW_NON_NUMERIC_NUMBERS`; kiểm tra `Double`/`Float` hữu hạn trước khi ghi. |
| Đầu ra phải luôn là JSON number hữu hạn | Từ chối NaN/Infinity ở validation hoặc serializer tùy chỉnh. |
| Cần ghi giá trị đặc biệt dưới dạng chuỗi | Giữ quote non-numeric numbers và công bố rõ sentinel string trong schema. |
| Đọc token NaN/Infinity từ hệ thống cũ đã thỏa thuận | Bật `JsonReadFeature.ALLOW_NON_NUMERIC_NUMBERS` trên mapper riêng cho tích hợp đó. |
| Cần phân biệt không có số đo với phép tính không xác định | Dùng null/status hoặc enum trạng thái tường minh. |
| Dữ liệu cần độ chính xác thập phân | Dùng `BigDecimal`; mô hình hóa trạng thái ngoài miền riêng. |

NaN và Infinity là giá trị hợp lệ của kiểu dấu phẩy động Java, nhưng không phải JSON number chuẩn. Jackson cung cấp feature riêng cho việc ghi chúng dưới dạng chuỗi và cho phép parser đọc token mở rộng. Đối với API trao đổi dữ liệu, hãy quyết định rõ có chấp nhận các giá trị này không, kiểm tra `Double.isFinite()` hoặc `Float.isFinite()` tại ranh giới phù hợp, và mô hình hóa trạng thái đặc biệt bằng một hợp đồng JSON tường minh để các client khác ngôn ngữ có thể xử lý nhất quán.
