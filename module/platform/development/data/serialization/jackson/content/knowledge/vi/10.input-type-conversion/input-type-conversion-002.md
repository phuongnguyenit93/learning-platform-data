# Xử lý chuỗi được gửi vào trường kiểu số

Trong JSON, một giá trị số và một chuỗi chứa chữ số là hai kiểu dữ liệu khác nhau:

```json
{
  "quantity": 12,
  "price": "1250.50"
}
```

`quantity` là JSON number, còn `price` là JSON string. Tuy nhiên, trong một số hệ thống, dữ liệu số lại được gửi dưới dạng chuỗi, chẳng hạn form HTML, dữ liệu từ hệ thống cũ hoặc API có hợp đồng đầu vào không thống nhất. Khi Jackson ánh xạ JSON vào một field Java kiểu `int`, `long`, `Integer`, `BigDecimal` hoặc kiểu số khác, ứng dụng cần quyết định có cho phép chuyển chuỗi đó thành số hay không.

Jackson Databind hỗ trợ **scalar coercion**: chuyển đổi một số kiểu JSON scalar sang kiểu Java scalar khác. Với các phiên bản Jackson thông dụng, chuỗi có nội dung số có thể được chuyển thành kiểu số theo cấu hình mặc định. Từ Jackson 2.12, `CoercionConfig` cho phép kiểm soát chi tiết hơn việc chuyển đổi theo kiểu logic hoặc kiểu Java cụ thể.

## 1. Phân biệt JSON number và JSON string

Hai payload sau không giống nhau về kiểu token JSON:

```json
{
  "quantity": 12
}
```

```json
{
  "quantity": "12"
}
```

Payload thứ nhất chứa token number. Payload thứ hai chứa token string. Nếu model Java là:

```java
public record OrderRequest(int quantity) {
}
```

Jackson nhận token number và ánh xạ trực tiếp vào `int`. Với token string chứa chữ số, Jackson có thể thực hiện coercion theo cấu hình:

```java
ObjectMapper mapper = new ObjectMapper();

OrderRequest request = mapper.readValue(
        "{\"quantity\":\"12\"}",
        OrderRequest.class
);

System.out.println(request.quantity()); // 12
```

Khả năng chuyển đổi này hữu ích khi tích hợp với nguồn dữ liệu không gửi đúng kiểu JSON mà model mong đợi. Dù vậy, ứng dụng nên hiểu rõ đây là một chính sách chuyển kiểu, không phải bằng chứng rằng payload tuân thủ hợp đồng JSON.

Với API mới do ứng dụng kiểm soát, trường số thường nên được gửi bằng JSON number. Ví dụ `"quantity": 12` thể hiện kiểu dữ liệu rõ ràng hơn `"quantity": "12"` và giúp consumer khác nhau ít phải tự suy đoán.

## 2. Jackson chuyển chuỗi số thành kiểu số như thế nào?

Jackson có thể chuyển một chuỗi như `"12"` thành các kiểu số tương ứng khi kiểu đích cho phép và coercion được bật. Ví dụ:

```java
public record NumericData(
        int quantity,
        long totalCount,
        Integer retryCount,
        BigDecimal amount,
        Double ratio
) {
}

String json = """
        {
          "quantity": "12",
          "totalCount": "9000000000",
          "retryCount": "3",
          "amount": "1250.75",
          "ratio": "0.85"
        }
        """;

NumericData data = mapper.readValue(json, NumericData.class);
```

Khi chuỗi có định dạng số mà kiểu đích chấp nhận, Jackson chuyển nó thành giá trị số. Các kiểu số khác nhau có giới hạn và quy tắc riêng:

- `int` và `Integer` chỉ biểu diễn số nguyên trong phạm vi 32-bit.
- `long` và `Long` biểu diễn số nguyên trong phạm vi 64-bit.
- `BigInteger` biểu diễn số nguyên có độ lớn tùy ý theo giới hạn bộ nhớ.
- `float` và `double` dùng biểu diễn dấu phẩy động nhị phân, có thể có sai số làm tròn.
- `BigDecimal` phù hợp khi cần biểu diễn số thập phân với độ chính xác thập phân, ví dụ số tiền.

Nếu chuỗi không thể parse thành kiểu số đích, Jackson thường ném lỗi ánh xạ như `InvalidFormatException`. Nếu giá trị vượt phạm vi kiểu đích, quá trình chuyển đổi cũng có thể thất bại. Không nên coi coercion là cơ chế tự động làm sạch mọi chuỗi đầu vào.

## 3. Ví dụ với dữ liệu từ form hoặc hệ thống bên ngoài

Nhiều form gửi giá trị dưới dạng chuỗi, kể cả khi trường trên giao diện được xem là số. Ví dụ payload:

```json
{
  "productId": "501",
  "quantity": "4",
  "unitPrice": "199.90"
}
```

Model nhận dữ liệu:

```java
public record ProductOrderRequest(
        Long productId,
        Integer quantity,
        BigDecimal unitPrice
) {
}
```

Có thể đọc trực tiếp nếu coercion phù hợp đang được bật:

```java
ProductOrderRequest request = mapper.readValue(
        json,
        ProductOrderRequest.class
);
```

Kết quả là các field Java có kiểu số tương ứng. Tầng xử lý nghiệp vụ vẫn cần kiểm tra `productId` có tồn tại, `quantity` có lớn hơn 0, và `unitPrice` có nằm trong chính sách giá hợp lệ hay không.

Nếu API có thể thay đổi, nên thống nhất hợp đồng để gửi số dưới dạng JSON number. Nếu phải hỗ trợ client cũ gửi chuỗi, hãy coi việc chấp nhận chuỗi là một chính sách tương thích có chủ đích và ghi nhận thời điểm có thể loại bỏ nó.

## 4. Kiểm soát coercion bằng CoercionConfig

Từ Jackson 2.12, `CoercionConfig` cung cấp cách kiểm soát chuyển đổi dựa trên hình dạng token đầu vào và kiểu dữ liệu đích. Đây là lựa chọn rõ ràng khi muốn quy định trường số có chấp nhận JSON string hay không.

Các lớp API thường dùng:

- `CoercionInputShape`: hình dạng dữ liệu đầu vào, ví dụ `String`, `EmptyString`, `BlankString`, `Integer`, `Float`, `Boolean`, `Array` hoặc `Object`.
- `CoercionAction`: hành động Jackson thực hiện, ví dụ `TryConvert`, `Fail`, `AsNull` hoặc `AsEmpty`.
- `LogicalType`: nhóm kiểu logic như `Integer`, `Float`, `Textual`, `Boolean`, `DateTime`.

### 4.1. Từ chối chuỗi cho nhóm kiểu số nguyên

Nếu hợp đồng yêu cầu trường số nguyên phải được gửi dưới dạng JSON number, có thể từ chối JSON string cho nhóm kiểu số nguyên:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.type.LogicalType;

ObjectMapper strictMapper = new ObjectMapper();

strictMapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Sau cấu hình này, một field kiểu `int` hoặc `Integer` thuộc nhóm logic số nguyên sẽ từ chối chuỗi như `"12"` thay vì tự chuyển thành số. JSON number `12` vẫn được đọc theo quy tắc bình thường.

### 4.2. Từ chối chuỗi cho nhóm số dấu phẩy động

Nếu cần chính sách tương tự cho nhóm số dấu phẩy động, cấu hình thêm:

```java
strictMapper.coercionConfigFor(LogicalType.Float)
        .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Nhóm `LogicalType.Float` bao gồm các kiểu số dấu phẩy động mà Jackson phân loại vào nhóm này, có thể bao gồm `float`, `double` và các kiểu số thập phân tương ứng. Nếu ứng dụng cần chính sách khác nhau cho một class cụ thể, có thể dùng cấu hình theo kiểu Java thay vì nhóm logic.

### 4.3. Chỉ áp dụng cho một kiểu Java

Có thể cấu hình riêng cho `Integer.class`:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.coercionConfigFor(Integer.class)
        .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Cấu hình theo class giúp phân biệt chính sách của `Integer` với những kiểu số khác. Khi có cả cấu hình theo logical type và cấu hình theo class, cấu hình cụ thể cho kiểu đích có thể có độ ưu tiên cao hơn cấu hình nhóm. Hãy cấu hình rõ ràng và kiểm tra đúng kiểu Java mà model đang sử dụng, đặc biệt khi có cả primitive và wrapper.

### 4.4. Chấp nhận chuyển đổi tường minh

Nếu muốn ghi rõ rằng chuỗi được phép chuyển thành số, có thể đặt hành động `TryConvert`:

```java
mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.String, CoercionAction.TryConvert);
```

`TryConvert` yêu cầu Jackson thử chuyển đổi theo parser/deserializer của kiểu đích. Nó không có nghĩa mọi chuỗi đều hợp lệ. Chuỗi `"abc"` vẫn không phải một số nguyên hợp lệ và sẽ gây lỗi.

Các hành động `AsNull` và `AsEmpty` có thể được dùng cho một số trường hợp khi chính sách nghiệp vụ cho phép, nhưng cần đặc biệt cẩn thận với kiểu primitive, wrapper và dữ liệu bắt buộc. Không nên biến một chuỗi sai định dạng thành `0` hoặc `null` chỉ để tránh lỗi nếu điều đó làm mất khả năng phát hiện dữ liệu hỏng.

## 5. Khác biệt giữa chuỗi rỗng, chuỗi trắng và JSON null

Các giá trị sau không giống nhau:

```json
{
  "a": "",
  "b": "   ",
  "c": null,
  "d": "0"
}
```

| Đầu vào | Ý nghĩa |
|---|---|
| `""` | JSON string rỗng |
| `"   "` | JSON string chứa khoảng trắng |
| `null` | JSON null token |
| `"0"` | JSON string có ký tự số 0 |
| `0` | JSON number có giá trị 0 |

Jackson có các `CoercionInputShape` riêng cho `EmptyString` và `BlankString`. Vì vậy, chính sách đối với chuỗi rỗng hoặc chỉ có khoảng trắng có thể được đặt độc lập với chuỗi có nội dung. Ví dụ:

```java
mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail)
        .setCoercion(CoercionInputShape.BlankString, CoercionAction.Fail);
```

Không nên suy luận rằng nếu `"12"` được chuyển thành `12` thì `""` hoặc `"   "` cũng phải được chuyển thành một giá trị số nào đó. Kết quả của empty/blank coercion phụ thuộc cấu hình Jackson và kiểu đích.

JSON `null` lại là một trường hợp riêng. Với kiểu wrapper như `Integer`, null có thể được gán thành `null` theo chính sách mặc định. Với primitive như `int`, Java không có giá trị null; `DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES` có thể được bật để từ chối JSON null thay vì dùng giá trị mặc định của primitive.

```java
ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

Feature trên xử lý JSON null cho primitive. Nó không phải cấu hình để từ chối chuỗi `""`, `"null"` hoặc chuỗi trắng; các trường hợp đó cần chính sách coercion phù hợp.

## 6. Chuỗi số không hợp lệ và lỗi ánh xạ

Khi chuỗi không biểu diễn được số theo kiểu đích, Jackson sẽ báo lỗi. Ví dụ:

```java
public record PaymentRequest(BigDecimal amount, Integer quantity) {
}

String invalidJson = """
        {
          "amount": "12,500.00",
          "quantity": "three"
        }
        """;

PaymentRequest request = mapper.readValue(
        invalidJson,
        PaymentRequest.class
);
```

Với cấu hình số mặc định, chuỗi `"three"` không thể chuyển thành `Integer`, vì vậy Jackson ném lỗi deserialize. Chuỗi `"12,500.00"` cũng không phải biểu diễn thập phân chuẩn mà `BigDecimal` mặc định mong đợi, vì dấu phẩy phân tách hàng nghìn không tự động được hiểu theo locale.

Không nên xóa dấu phẩy, dấu chấm hoặc ký tự tiền tệ bằng một phép replace chung trước khi parse. Quy tắc `1,234.56` và `1.234,56` có thể khác nhau theo locale. Nếu hợp đồng đầu vào yêu cầu định dạng có dấu phân cách hoặc ký hiệu tiền tệ, hãy tạo parser/deserializer chuyên biệt và kiểm tra locale/format một cách tường minh.

### 6.1. Xử lý lỗi tại tầng phù hợp

Jackson thường ném `JsonProcessingException` hoặc kiểu con như `InvalidFormatException` khi nội dung không thể ánh xạ thành kiểu đích. Ở API layer, có thể bắt lỗi này để trả về lỗi request có cấu trúc, chỉ ra field không hợp lệ.

```java
try {
    PaymentRequest request = mapper.readValue(json, PaymentRequest.class);
    process(request);
} catch (JsonProcessingException exception) {
    // Chuyển thành lỗi đầu vào không hợp lệ theo hợp đồng API.
}
```

Không nên nuốt lỗi rồi tự thay giá trị sai bằng `0`. Cách đó làm dữ liệu lỗi tiếp tục đi vào nghiệp vụ và có thể gây sai lệch kết quả tính toán.

## 7. Phân biệt coercion với validation

Coercion trả lời câu hỏi: **Jackson có thể chuyển token đầu vào thành kiểu Java đích hay không?** Validation trả lời câu hỏi: **Giá trị đã chuyển đổi có hợp lệ theo quy tắc nghiệp vụ hay không?**

Ví dụ chuỗi `"-5"` có thể được chuyển thành `Integer` thành công, nhưng số lượng sản phẩm không được phép âm. Đây là lỗi validation, không phải lỗi parse số.

```java
public record StockRequest(
        @NotNull
        @Positive
        Integer quantity
) {
}
```

Sau khi deserialize, ứng dụng cần chạy Bean Validation hoặc kiểm tra domain tương ứng. Với Spring MVC, `@Valid` trên request body có thể kích hoạt validation theo cấu hình ứng dụng.

Tương tự, một chuỗi `"999999999"` có thể chuyển thành `Integer` hợp lệ nhưng vượt ngưỡng nghiệp vụ. Ngược lại, chuỗi `"999999999999999999999999"` có thể vượt phạm vi `Integer` ngay ở bước deserialize.

## 8. Chọn kiểu số phù hợp với dữ liệu

Việc chuyển chuỗi thành số không loại bỏ giới hạn của kiểu đích:

| Kiểu Java | Dùng khi | Lưu ý |
|---|---|---|
| `Integer` / `int` | Số nguyên có phạm vi nhỏ | `int` primitive không chứa được null |
| `Long` / `long` | Số nguyên có phạm vi lớn hơn | Vẫn có giới hạn 64-bit |
| `BigInteger` | Số nguyên lớn | Không có giới hạn bit cố định như primitive, nhưng vẫn giới hạn bởi tài nguyên |
| `Double` / `double` | Giá trị gần đúng dạng dấu phẩy động | Có thể có sai số nhị phân |
| `BigDecimal` | Số thập phân cần độ chính xác, ví dụ tiền | Nên kiểm soát scale và rounding ở nghiệp vụ |

Đối với tiền, thường nên dùng `BigDecimal` thay cho `double`. Ví dụ:

```java
public record InvoiceRequest(BigDecimal totalAmount) {
}

InvoiceRequest invoice = mapper.readValue(
        "{\"totalAmount\":\"1250.75\"}",
        InvoiceRequest.class
);
```

`BigDecimal` giữ giá trị thập phân theo biểu diễn decimal, phù hợp hơn cho phép tính tài chính cần kiểm soát scale/rounding. Việc chọn số chữ số thập phân, làm tròn và giới hạn giá trị vẫn thuộc quy tắc nghiệp vụ.

## 9. Float-to-integer là một loại coercion khác

Không nên nhầm chuyển JSON string thành số với chuyển JSON number có phần thập phân thành kiểu nguyên.

Ví dụ:

```json
{
  "quantity": 12.8
}
```

Ở đây, token đầu vào là JSON floating-point number, không phải string. Jackson có `DeserializationFeature.ACCEPT_FLOAT_AS_INT` để kiểm soát việc chấp nhận giá trị float khi kiểu đích là số nguyên. Đây là chính sách riêng với coercion từ `CoercionInputShape.String`.

Nếu hợp đồng yêu cầu số lượng phải là số nguyên, hãy cân nhắc tắt feature này:

```java
ObjectMapper mapper = new ObjectMapper()
        .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT);
```

Như vậy, hai câu hỏi cần được cấu hình riêng:

- Có cho phép `"12"` (JSON string) thành `Integer` không? Dùng scalar coercion/`CoercionConfig`.
- Có cho phép `12.8` (JSON number dạng float) thành `Integer` không? Dùng `ACCEPT_FLOAT_AS_INT`.

Việc tách hai chính sách giúp API không vô tình chấp nhận dữ liệu có kiểu hoặc độ chính xác khác hợp đồng.

## 10. Giới hạn coercion ở một property hoặc kiểu dữ liệu

Không phải lúc nào cũng nên áp dụng một chính sách toàn cục. Nếu chỉ một property legacy nhận số dạng chuỗi, có thể tạo DTO đầu vào riêng hoặc custom deserializer cho property đó. Cách này giới hạn ảnh hưởng đến những payload khác.

Một lựa chọn là giữ đầu vào dưới dạng `String` rồi chuyển đổi rõ ràng trong lớp chuyển đổi request:

```java
public record LegacyOrderPayload(String quantity) {
}

public record OrderCommand(int quantity) {
}

OrderCommand toCommand(LegacyOrderPayload payload) {
    int quantity;
    try {
        quantity = Integer.parseInt(payload.quantity());
    } catch (NumberFormatException exception) {
        throw new IllegalArgumentException("quantity must be an integer", exception);
    }

    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    return new OrderCommand(quantity);
}
```

Lợi ích của cách này là ứng dụng có thể kiểm soát thông báo lỗi, format và validation ở đúng boundary. Đổi lại, code phải tự chuyển đổi và xử lý lỗi. Chọn cách này khi contract legacy có quy tắc riêng hoặc khi không muốn nới coercion cho toàn mapper.

## 11. Bảng lựa chọn chính sách

| Nhu cầu | Cách tiếp cận |
|---|---|
| Chấp nhận chuỗi số hợp lệ cho field số | Giữ coercion phù hợp hoặc đặt `CoercionAction.TryConvert` |
| Bắt buộc JSON number cho nhóm số nguyên | `coercionConfigFor(LogicalType.Integer)` với `String -> Fail` |
| Bắt buộc JSON number cho nhóm số thập phân | `coercionConfigFor(LogicalType.Float)` với `String -> Fail` |
| Chỉ từ chối chuỗi với một kiểu Java | `coercionConfigFor(Integer.class)` hoặc class đích tương ứng |
| Từ chối chuỗi rỗng/trắng | Cấu hình riêng `EmptyString` và `BlankString` |
| Từ chối JSON null cho primitive | `FAIL_ON_NULL_FOR_PRIMITIVES` |
| Từ chối JSON float vào kiểu nguyên | `ACCEPT_FLOAT_AS_INT` |
| Chỉ một DTO legacy chấp nhận chuỗi số | DTO String riêng hoặc custom deserializer |
| Kiểm tra số dương, giới hạn, scale | Bean Validation hoặc domain validation sau deserialize |

## 12. Ghi nhớ

Jackson có thể chuyển chuỗi chứa chữ số thành field Java kiểu số thông qua scalar coercion. Khả năng này hữu ích khi tương thích với nguồn dữ liệu cũ, nhưng cần được xem là một quyết định của hợp đồng đầu vào. Chuỗi không hợp lệ, vượt phạm vi hoặc có format theo locale không tự động được sửa thành số.

Hãy phân biệt JSON string với JSON number, chuỗi rỗng với JSON null, và coercion với validation. Dùng `CoercionConfig` từ Jackson 2.12 trở lên để đặt chính sách cụ thể theo logical type hoặc Java class; dùng `FAIL_ON_NULL_FOR_PRIMITIVES` và `ACCEPT_FLOAT_AS_INT` cho hai trường hợp khác nhau. Với dữ liệu nghiệp vụ quan trọng, chọn kiểu số phù hợp và không âm thầm thay dữ liệu sai bằng giá trị mặc định.
