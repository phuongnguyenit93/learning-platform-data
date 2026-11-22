# Đánh giá chuyển đổi số thực sang số nguyên

JSON có một kiểu number, nhưng Jackson phải ánh xạ giá trị đó vào kiểu Java cụ thể mà ứng dụng yêu cầu. Khi JSON chứa một số có phần thập phân nhưng thuộc tính Java là int, long hoặc một kiểu nguyên khác, Jackson phải quyết định có cho phép chuyển đổi hay không và nếu cho phép thì xử lý phần thập phân như thế nào.

Jackson Databind có feature ACCEPT_FLOAT_AS_INT để điều khiển việc chuyển JSON floating-point number sang kiểu Java integral. Trong cấu hình mặc định của Jackson 2.x, feature này được bật: giá trị thập phân được chuyển bằng cách cắt phần lẻ, không phải làm tròn. Ví dụ 12.9 thành 12 và -12.9 thành -12.

Hành vi này tiện cho một số dữ liệu, nhưng có thể làm mất thông tin. Nếu hợp đồng yêu cầu số lượng nguyên, số lần thử hoặc số thứ tự phải là số nguyên đúng nghĩa, ứng dụng nên từ chối input có token số thực thay vì âm thầm cắt phần thập phân.

## 1. JSON number và kiểu số Java

JSON định nghĩa một dạng number chung. Cùng một kiểu JSON number có thể được biểu diễn bằng nhiều cách viết:

~~~json
12
~~~

~~~json
12.0
~~~

~~~json
12.75
~~~

~~~json
1.2e1
~~~

Các giá trị trên đều là JSON number hợp lệ. Tuy nhiên, parser có thể phân loại token theo cách viết số nguyên hoặc số dấu phẩy động:

- 12 là token số nguyên.
- 12.0 có dấu thập phân nên là token số thực.
- 12.75 là token số thực có phần lẻ khác không.
- 1.2e1 dùng ký hiệu exponent nên là token số thực, dù giá trị toán học bằng 12.

Kiểu Java đích quyết định cách Jackson chuyển đổi:

| Kiểu đích Java | Ý nghĩa |
|---|---|
| int, Integer | Số nguyên 32-bit. |
| long, Long | Số nguyên 64-bit. |
| short, Short | Số nguyên 16-bit. |
| byte, Byte | Số nguyên 8-bit. |
| BigInteger | Số nguyên có độ lớn tùy ý. |
| float, Float | Số dấu phẩy động độ chính xác đơn. |
| double, Double | Số dấu phẩy động độ chính xác kép. |
| BigDecimal | Số thập phân có độ chính xác tùy ý, phù hợp với các phép tính cần kiểm soát decimal. |

JSON không nói rằng một trường có ý nghĩa là int hay BigDecimal. Hợp đồng API và kiểu Java của ứng dụng quyết định cách diễn giải.

## 2. Hành vi mặc định của Jackson khi đọc số thực vào số nguyên

Feature DeserializationFeature.ACCEPT_FLOAT_AS_INT quyết định Jackson có cho phép chuyển token JSON dạng floating-point thành kiểu Java integral hay không.

Trong Jackson Databind 2.x, feature này mặc định được bật. Khi bật, Jackson loại bỏ phần thập phân bằng cách cắt về phía zero (truncate toward zero), không làm tròn đến số nguyên gần nhất.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

Integer a = mapper.readValue("12.9", Integer.class);   // 12
Integer b = mapper.readValue("12.1", Integer.class);   // 12
Integer c = mapper.readValue("-12.9", Integer.class);  // -12
Integer d = mapper.readValue("-12.1", Integer.class);  // -12
Integer e = mapper.readValue("12.0", Integer.class);   // 12
~~~

Với số âm, cắt về zero khác với làm tròn xuống theo hướng âm vô hạn:

- -12.9 được cắt thành -12.
- floor(-12.9) sẽ là -13.
- round(-12.9) theo quy tắc làm tròn thông thường cũng có thể cho kết quả khác tùy quy tắc xử lý điểm giữa.

Không nên diễn giải hành vi này là “làm tròn số”. Jackson đang bỏ phần lẻ khi ép kiểu sang số nguyên.

Một số ví dụ theo kiểu đích:

| JSON number | Kiểu đích | Kết quả khi cho phép coercion |
|---|---|---|
| 7 | Integer | 7 |
| 7.0 | Integer | 7 |
| 7.8 | Integer | 7 |
| -7.8 | Integer | -7 |
| 7.8 | Long | 7 |
| 7.8 | BigInteger | 7 |

Các ví dụ minh họa phép chuyển đổi khi giá trị nằm trong phạm vi kiểu đích. Chúng không có nghĩa mọi giá trị số thực đều có thể chuyển an toàn sang mọi kiểu nguyên.

## 3. Vì sao cắt phần thập phân có thể nguy hiểm?

Việc chuyển đổi có thể hợp lệ về mặt kỹ thuật nhưng sai ý nghĩa nghiệp vụ.

### Số lượng

Nếu JSON gửi:

~~~json
{
  "quantity": 2.7
}
~~~

và DTO khai báo:

~~~java
public record OrderItemRequest(int quantity) {}
~~~

Jackson có thể tạo object với quantity bằng 2 khi ACCEPT_FLOAT_AS_INT đang bật. Nếu ứng dụng chỉ kiểm tra quantity lớn hơn 0, request có thể vượt qua validation dù client gửi số lượng không nguyên.

### Tiền và tỷ lệ

Nếu một trường amount nhận 1250.99 nhưng DTO dùng long, phần lẻ có thể bị bỏ. Đây thường là sai lầm nghiêm trọng vì giá trị tiền đã thay đổi trước khi logic nghiệp vụ chạy.

Với tiền, hãy dùng BigDecimal và xác định rõ currency, scale cùng quy tắc làm tròn. Đừng chuyển sang long chỉ vì muốn tránh số thập phân.

### Thời gian, phần trăm và phép đo

Một số trường có thể trông giống số nguyên nhưng ý nghĩa của chúng không cho phép cắt tùy ý. Ví dụ, tỷ lệ 3.75% chuyển thành 3% làm mất thông tin. Nếu đơn vị cần số thập phân, hãy giữ kiểu decimal trong mô hình dữ liệu.

### Chỉ số và số lần lặp

Với page number, retry count hoặc số lượng phần tử, phần lẻ thường phải bị từ chối. Việc tự động cắt có thể khiến request sai định dạng được xử lý như request hợp lệ.

Nguyên tắc thiết kế: nếu miền dữ liệu yêu cầu một số nguyên, hãy kiểm tra đầu vào là số nguyên. Không dùng phép coercion để thay thế validation.

## 4. Từ chối số thực khi kiểu Java đích là số nguyên

Nếu hợp đồng yêu cầu token JSON phải là số nguyên, hãy tắt ACCEPT_FLOAT_AS_INT:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;

ObjectMapper strictMapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();
~~~

Đọc số nguyên vẫn thành công:

~~~java
Integer quantity = strictMapper.readValue("12", Integer.class);
~~~

Nhưng các token số thực sẽ bị từ chối:

~~~java
strictMapper.readValue("12.5", Integer.class);
~~~

Jackson ném lỗi mapping vì input có dạng floating-point trong khi kiểu đích là integral và coercion đã bị tắt.

Điểm cần chú ý: 12.0 vẫn là token số thực vì JSON có phần thập phân. Dù giá trị toán học không có phần lẻ, strict mode vẫn có thể từ chối. Tương tự, 1e3 là cách viết dùng exponent và được parser xử lý như floating-point token.

Nếu hợp đồng yêu cầu cú pháp số nguyên, đây là hành vi phù hợp. Nếu hợp đồng cho phép 12.0 nhưng muốn từ chối 12.5, cần một bước kiểm tra giá trị toán học cụ thể thay vì chỉ dựa vào token shape.

## 5. Bật strict mode cho một ObjectReader

Không phải mọi kiểu dữ liệu trong ứng dụng đều cần cùng chính sách. Có thể tạo reader strict riêng cho DTO nhận số nguyên:

~~~java
ObjectReader quantityReader = mapper
    .readerFor(Integer.class)
    .without(DeserializationFeature.ACCEPT_FLOAT_AS_INT);

Integer quantity = quantityReader.readValue("12");
~~~

Với DTO:

~~~java
public record InventoryRequest(int quantity, long warehouseId) {}

ObjectReader inventoryReader = mapper
    .readerFor(InventoryRequest.class)
    .without(DeserializationFeature.ACCEPT_FLOAT_AS_INT);

InventoryRequest request = inventoryReader.readValue(
    """
    {
      "quantity": 12,
      "warehouseId": 9001
    }
    """
);
~~~

Nếu input gửi quantity là 12.5, quá trình deserialize thất bại. Reader này chỉ áp dụng cấu hình cho đường đọc mà nó thực sự được dùng.

Trong Spring MVC, request body thường được đọc bởi HTTP message converter. Tạo một ObjectReader riêng trong service không tự thay đổi cách converter deserialize @RequestBody. Nếu cần strict mode cho endpoint, hãy cấu hình mapper/converter tương ứng hoặc chủ động dùng reader trong đường nhận dữ liệu.

## 6. Dùng CoercionConfig để kiểm soát theo logical type

Từ Jackson 2.12, coercion configuration cho phép kiểm soát chuyển đổi theo kiểu logic và hình dạng input. Cách này hữu ích khi muốn điều chỉnh một loại coercion cụ thể mà không phải tắt toàn bộ feature liên quan.

Ví dụ từ chối floating-point token khi target thuộc nhóm kiểu nguyên:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.type.LogicalType;

ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);
~~~

Cấu hình trên đặt hành động Fail cho input có hình dạng Float khi target thuộc logical type Integer. Nó áp dụng theo nhóm kiểu nguyên thay vì chỉ một thuộc tính cụ thể.

Các CoercionAction phổ biến gồm:

| Action | Ý nghĩa |
|---|---|
| Fail | Từ chối chuyển đổi và ném lỗi mapping. |
| TryConvert | Thử chuyển đổi theo khả năng của deserializer. |
| AsNull | Chuyển input thành null nếu kiểu đích cho phép. |
| AsEmpty | Dùng empty value của deserializer. |

Với dữ liệu số, AsNull hoặc AsEmpty có thể làm mất thông tin về input ban đầu. Nếu yêu cầu là số nguyên đúng định dạng, Fail thường là chính sách dễ hiểu và an toàn hơn.

CoercionConfig là API cấu hình nâng cao. Hãy xác nhận phiên bản Jackson đang dùng hỗ trợ API này và kiểm tra cả mapper thực tế sau khi framework áp dụng customizer hoặc module. Nếu chỉ cần từ chối float-to-integer trên toàn mapper, ACCEPT_FLOAT_AS_INT là cách đơn giản hơn.

## 7. Nếu muốn làm tròn, hãy định nghĩa quy tắc nghiệp vụ

Jackson không làm tròn số thực khi coercion sang số nguyên. Nếu nghiệp vụ yêu cầu làm tròn, hãy nhận dữ liệu bằng kiểu có thể giữ phần thập phân rồi thực hiện phép làm tròn rõ ràng.

Ví dụ dùng BigDecimal:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal input = new BigDecimal("12.75");

int rounded = input.setScale(0, RoundingMode.HALF_UP).intValueExact();
~~~

Với HALF_UP, 12.75 thành 13. Nếu nghiệp vụ yêu cầu cắt phần lẻ, có thể dùng RoundingMode.DOWN:

~~~java
int truncated = input.setScale(0, RoundingMode.DOWN).intValueExact();
~~~

RoundingMode.DOWN cắt về zero, nên -12.75 thành -12. RoundingMode.FLOOR sẽ cho -13 đối với -12.75. Hai quy tắc này không giống nhau.

Không nên chuyển JSON number sang double rồi mới làm tròn nếu dữ liệu cần giữ độ chính xác thập phân. BigDecimal nhận trực tiếp từ chuỗi decimal hoặc được Jackson deserialize trực tiếp từ JSON number giúp tránh thêm sai số dấu phẩy động nhị phân.

Ví dụ DTO:

~~~java
public record PriceAdjustmentRequest(BigDecimal adjustment) {}
~~~

Deserialize:

~~~java
PriceAdjustmentRequest request =
    mapper.readValue(json, PriceAdjustmentRequest.class);

int wholeUnits = request.adjustment()
    .setScale(0, RoundingMode.HALF_UP)
    .intValueExact();
~~~

Việc làm tròn nên nằm ở lớp nghiệp vụ hoặc lớp chuyển đổi có chủ đích, nơi quy tắc được đặt tên, kiểm thử và tài liệu hóa. Không để hành vi mặc định của JSON mapper quyết định quy tắc tiền hoặc phép đo.

## 8. Kiểm tra giá trị có thực sự là số nguyên mà không làm tròn

Đôi khi API cho phép gửi JSON number dạng 12.0 nhưng chỉ chấp nhận nếu giá trị toán học là số nguyên. Khi đó, có thể deserialize thành BigDecimal, kiểm tra phần thập phân rồi chuyển đổi chính xác.

~~~java
BigDecimal value = mapper.readValue(json, BigDecimal.class);

if (value.stripTrailingZeros().scale() > 0) {
    throw new IllegalArgumentException("Value must be a whole number");
}

int quantity = value.intValueExact();
~~~

Giải thích:

- stripTrailingZeros loại bỏ các số 0 thập phân không cần thiết.
- scale lớn hơn 0 sau khi chuẩn hóa cho thấy còn phần thập phân khác 0.
- intValueExact từ chối nếu giá trị không phải số nguyên hoặc vượt phạm vi int.

Kết quả:

| Input | Sau stripTrailingZeros | Kết quả kiểm tra |
|---|---|---|
| 12 | 12 | Hợp lệ |
| 12.0 | 12 | Hợp lệ |
| 12.000 | 12 | Hợp lệ |
| 12.5 | 12.5 | Không hợp lệ |
| -12.0 | -12 | Hợp lệ |
| 2147483648 | 2147483648 | Là số nguyên nhưng vượt phạm vi int |

Nếu cần long, dùng longValueExact. Nếu miền giá trị lớn hơn nữa, có thể dùng BigInteger sau khi xác nhận giá trị không có phần lẻ.

Cách này phân biệt hai quy tắc:

- Strict token rule: chỉ chấp nhận JSON token có dạng số nguyên.
- Mathematical integer rule: chấp nhận cả 12 và 12.0 vì chúng biểu diễn cùng một giá trị nguyên.

Hợp đồng cần nói rõ đang áp dụng quy tắc nào.

## 9. Kiểm tra phạm vi của kiểu số nguyên

Ngay cả khi input không có phần thập phân, nó vẫn có thể vượt phạm vi kiểu Java.

Ví dụ int có phạm vi từ -2,147,483,648 đến 2,147,483,647. Giá trị lớn hơn không thể được lưu chính xác trong int.

~~~java
BigInteger raw = mapper.readValue("3000000000", BigInteger.class);

int value = raw.intValueExact();
~~~

intValueExact ném ArithmeticException nếu giá trị vượt phạm vi hoặc không phải số nguyên. Tương tự, longValueExact kiểm tra phạm vi long.

Đối với Jackson, đọc trực tiếp vào Integer hoặc Long với giá trị ngoài phạm vi thường dẫn đến lỗi mapping/overflow thay vì một kết quả nguyên chính xác. Không nên dựa vào việc cắt hoặc wrap số để xử lý overflow.

Nếu giá trị có thể lớn hơn long, dùng BigInteger. Nếu là decimal cần giữ độ chính xác, dùng BigDecimal. Chọn kiểu Java theo miền giá trị, không chỉ theo một ví dụ payload nhỏ.

## 10. Kiểm tra hành vi bằng JUnit

Test nên xác nhận hành vi mặc định, strict mode và trường hợp số thực có giá trị toán học nguyên.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

class FloatToIntegerTest {

    private final ObjectMapper defaultMapper = new ObjectMapper();

    private final ObjectMapper strictMapper = JsonMapper.builder()
        .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
        .build();

    @Test
    void defaultConfigurationTruncatesFloatingPointInput() throws Exception {
        assertEquals(12, defaultMapper.readValue("12.9", Integer.class));
        assertEquals(-12, defaultMapper.readValue("-12.9", Integer.class));
        assertEquals(12, defaultMapper.readValue("12.0", Integer.class));
    }

    @Test
    void strictConfigurationRejectsFloatingPointToken() {
        assertThrows(
            JsonProcessingException.class,
            () -> strictMapper.readValue("12.9", Integer.class)
        );
    }

    @Test
    void strictConfigurationStillAcceptsIntegerToken() throws Exception {
        assertEquals(12, strictMapper.readValue("12", Integer.class));
    }
}
~~~

Test đầu tiên chứng minh hành vi mặc định là truncate toward zero. Test thứ hai xác nhận strict mode từ chối token số thực. Test thứ ba bảo đảm việc tắt coercion không làm hỏng input số nguyên hợp lệ.

Nếu ứng dụng dùng CoercionConfig, hãy thêm test cho cấu hình đó. Nếu DTO dùng primitive int thay vì Integer, cũng cần test riêng null và missing property vì đây là hai quy tắc khác với float-to-integer.

## 11. Chọn chính sách theo ý nghĩa trường dữ liệu

| Trường dữ liệu | Kiểu Java thường phù hợp | Chính sách nên cân nhắc |
|---|---|---|
| Số lượng sản phẩm | int hoặc long | Từ chối token thập phân. |
| Số lần retry | int | Từ chối float, kiểm tra giới hạn không âm. |
| Mã định danh số | String hoặc kiểu identifier | Không ép kiểu số nếu số 0 đầu có ý nghĩa. |
| Tiền | BigDecimal | Giữ decimal, quy định scale và rounding riêng. |
| Tỷ lệ phần trăm | BigDecimal hoặc double tùy yêu cầu | Không cắt phần thập phân nếu miền dữ liệu cho phép decimal. |
| Số đo vật lý | BigDecimal hoặc double | Xác định precision và đơn vị. |
| Số thứ tự trang | int | Từ chối float, kiểm tra giới hạn trang. |

Một API có thể có nhiều trường số với chính sách khác nhau. Không nhất thiết phải tắt coercion toàn cục nếu một số trường hợp có lý do tương thích để chấp nhận float. Tuy nhiên, nếu hợp đồng của ứng dụng yêu cầu integer token cho các kiểu nguyên, strict reader hoặc coercion config giúp chính sách rõ ràng.

## Kết luận

Jackson mặc định cho phép chuyển floating-point token sang kiểu Java integral thông qua ACCEPT_FLOAT_AS_INT, và phần thập phân bị cắt về phía zero thay vì làm tròn. Điều đó có thể gây mất dữ liệu hoặc làm sai quy tắc nghiệp vụ nếu trường thực sự yêu cầu số nguyên.

Hãy tắt ACCEPT_FLOAT_AS_INT hoặc cấu hình CoercionConfig để từ chối float khi cần strict input. Nếu nghiệp vụ muốn làm tròn hoặc chấp nhận decimal có giá trị toán học nguyên như 12.0, hãy nhận bằng BigDecimal rồi kiểm tra/chuyển đổi tường minh. Cuối cùng, kiểm thử cả số dương, số âm, token decimal, exponent và giới hạn kiểu để bảo đảm Jackson đang thực hiện đúng hợp đồng.
