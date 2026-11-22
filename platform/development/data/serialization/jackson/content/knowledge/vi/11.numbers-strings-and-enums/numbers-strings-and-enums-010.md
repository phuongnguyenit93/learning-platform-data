# Phân biệt thuộc tính enum trong giá trị và trong khóa Map

Enum có thể xuất hiện ở nhiều vị trí trong JSON: một property thông thường, một phần tử trong array, giá trị của `Map` hoặc chính khóa của `Map`. Những vị trí này trông giống nhau trong Java nhưng đi qua các cơ chế serialization/deserialization khác nhau của Jackson.

Ví dụ, `OrderStatus.IN_PROGRESS` khi là giá trị property có thể được ghi thành chuỗi JSON `"IN_PROGRESS"`. Nhưng khi được dùng làm khóa của `Map<OrderStatus, Integer>`, nó trở thành tên property của một JSON object:

```json
{
  "IN_PROGRESS": 3
}
```

JSON object luôn dùng tên member dạng chuỗi. Vì vậy, enum làm giá trị và enum làm khóa cần được hiểu như hai vai trò riêng. Jackson có `EnumSerializer`/`EnumDeserializer` cho enum value và cơ chế key serializer/key deserializer cho khóa map. Bài này trình bày cách cấu hình từng vai trò, cách giữ tên wire ổn định và cách xử lý khi một enum cần hai biểu diễn khác nhau.

Các ví dụ sử dụng Jackson 2.x với package `com.fasterxml.jackson`. `@JsonKey` có từ Jackson 2.12; nếu dự án dùng version cũ hơn, hãy kiểm tra Javadoc và cân nhắc key serializer tùy chỉnh.

## 1. Enum khi là giá trị JSON

Giả sử có enum:

```java
public enum OrderStatus {
    NEW,
    IN_PROGRESS,
    COMPLETED,
    CANCELLED
}
```

Khi enum là property của một POJO:

```java
public class OrderResponse {
    private long id;
    private OrderStatus status;

    public OrderResponse() {
    }

    public OrderResponse(long id, OrderStatus status) {
        this.id = id;
        this.status = status;
    }

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
```

Với cấu hình mặc định, Jackson ghi tên enum bằng `Enum.name()`:

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(
        new OrderResponse(1001, OrderStatus.IN_PROGRESS));
```

JSON tương ứng:

```json
{
  "id": 1001,
  "status": "IN_PROGRESS"
}
```

Khi đọc lại, Jackson tìm constant enum có tên tương ứng:

```java
OrderResponse response = mapper.readValue(json, OrderResponse.class);
OrderStatus status = response.getStatus(); // IN_PROGRESS
```

Đây là cách đơn giản và dễ dự đoán khi tên constant Java cũng là tên giao tiếp mà API muốn công bố. Tuy nhiên, nếu đổi tên constant trong source code, JSON contract cũng có thể thay đổi. Với API công khai hoặc dữ liệu lưu lâu dài, nên cân nhắc một tên wire ổn định độc lập với tên code.

## 2. Enum khi là khóa của `Map`

Xét map đếm số đơn hàng theo trạng thái:

```java
Map<OrderStatus, Integer> counts = new EnumMap<>(OrderStatus.class);
counts.put(OrderStatus.NEW, 4);
counts.put(OrderStatus.IN_PROGRESS, 3);
counts.put(OrderStatus.COMPLETED, 12);
```

Jackson ghi map thành JSON object. Enum key trở thành tên member:

```json
{
  "NEW": 4,
  "IN_PROGRESS": 3,
  "COMPLETED": 12
}
```

Khi deserialize, JSON object member name là chuỗi, sau đó Jackson dùng key deserializer để chuyển chuỗi đó thành enum constant:

```java
Map<OrderStatus, Integer> restored = mapper.readValue(
        json,
        new TypeReference<Map<OrderStatus, Integer>>() {}
);

Integer inProgressCount = restored.get(OrderStatus.IN_PROGRESS); // 3
```

Hai điểm cần nhớ:

- JSON key luôn là chuỗi, kể cả khi kiểu key Java là enum, số hoặc một kiểu khác.
- `Map<OrderStatus, Integer>` cần thông tin generic đầy đủ khi đọc; dùng `Map.class` sẽ làm mất kiểu key/value cụ thể.

Một enum làm value đi qua quy tắc serialize enum thông thường. Một enum làm key đi qua quy tắc chuyển đổi tên map key. Không nên mặc định rằng thay đổi cách ghi enum value sẽ luôn thay đổi map key theo cùng cách.

## 3. Bảng so sánh hai vai trò

| Vai trò trong Java | Vị trí trong JSON | Cơ chế Jackson | Ví dụ |
|---|---|---|---|
| `OrderStatus` là property value | Giá trị của một field | Enum value serializer/deserializer | `{"status":"IN_PROGRESS"}` |
| `OrderStatus` là phần tử array | Một giá trị trong JSON array | Enum value serializer/deserializer | `["NEW","COMPLETED"]` |
| `OrderStatus` là `Map` key | Tên member của JSON object | Key serializer/key deserializer | `{"NEW":4}` |
| `OrderStatus` là `Map` value | Giá trị của member | Enum value serializer/deserializer | `{"latest":"COMPLETED"}` |

Ví dụ một map có enum ở cả key lẫn value:

```java
Map<OrderStatus, OrderStatus> transitions = new EnumMap<>(OrderStatus.class);
transitions.put(OrderStatus.NEW, OrderStatus.IN_PROGRESS);
transitions.put(OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED);
```

JSON:

```json
{
  "NEW": "IN_PROGRESS",
  "IN_PROGRESS": "COMPLETED"
}
```

Trong mỗi entry, key ở bên trái là tên member được key serializer tạo ra; value ở bên phải là JSON string được enum serializer tạo ra. Khi đọc, hai phần cũng được chuyển đổi bằng hai cơ chế tương ứng.

## 4. Đặt tên wire rõ ràng cho enum value bằng `@JsonProperty`

Nếu muốn tên JSON khác tên constant Java, có thể gắn `@JsonProperty` lên từng constant:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public enum OrderStatus {
    @JsonProperty("new")
    NEW,

    @JsonProperty("in_progress")
    IN_PROGRESS,

    @JsonProperty("completed")
    COMPLETED,

    @JsonProperty("cancelled")
    CANCELLED
}
```

Khi enum là value:

```java
String json = mapper.writeValueAsString(OrderStatus.IN_PROGRESS);
// "in_progress"

OrderStatus status = mapper.readValue("\"in_progress\"", OrderStatus.class);
// IN_PROGRESS
```

`@JsonProperty` giúp tên wire không phụ thuộc hoàn toàn vào cách đặt tên constant. Đây là lựa chọn rõ ràng khi mỗi enum constant có một tên bên ngoài cố định.

Với enum key trong map, Jackson cũng có thể dùng tên enum đã được định nghĩa bởi metadata enum. Tuy nhiên, vì map key đi qua key serializer riêng, hãy kiểm tra output của đúng phiên bản Jackson và test cả chiều đọc lẫn chiều ghi. Nếu key cần quy tắc khác với value, dùng `@JsonKey` hoặc key serializer chuyên biệt thay vì dựa vào hiệu ứng gián tiếp của annotation value.

## 5. Dùng `@JsonValue` cho biểu diễn enum value tùy chỉnh

Khi mỗi enum constant có một mã hoặc chuỗi nghiệp vụ riêng, có thể dùng `@JsonValue` trên một field/getter:

```java
import com.fasterxml.jackson.annotation.JsonValue;

public enum PaymentMethod {
    CARD("card"),
    CASH("cash"),
    BANK_TRANSFER("bank_transfer");

    private final String wireValue;

    PaymentMethod(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String getWireValue() {
        return wireValue;
    }
}
```

Khi serialize enum như một giá trị:

```java
String json = mapper.writeValueAsString(PaymentMethod.BANK_TRANSFER);
// "bank_transfer"
```

Với enum, Jackson có thể dùng giá trị từ `@JsonValue` để tra ngược khi deserialize (từ Jackson 2.9 trở lên), miễn là các giá trị không bị trùng:

```java
PaymentMethod method = mapper.readValue(
        "\"bank_transfer\"",
        PaymentMethod.class
);
// BANK_TRANSFER
```

`@JsonValue` phù hợp với biểu diễn enum value. Nếu cùng enum còn được dùng làm key của map và cần một chuỗi key khác, hãy tách biểu diễn key riêng.

## 6. Dùng `@JsonKey` khi enum cần tên khác trong Map key

Từ Jackson 2.12, `@JsonKey` đánh dấu accessor dùng khi một object được serialize làm khóa của map. Nó giải quyết trường hợp một kiểu cần một biểu diễn khi là JSON value và một biểu diễn khác khi là JSON object key.

Có thể kết hợp `@JsonValue` và `@JsonKey` trên cùng enum:

```java
import com.fasterxml.jackson.annotation.JsonKey;
import com.fasterxml.jackson.annotation.JsonValue;

public enum PaymentMethod {
    CARD("card", "payment-card"),
    CASH("cash", "cash-payment");

    private final String valueName;
    private final String keyName;

    PaymentMethod(String valueName, String keyName) {
        this.valueName = valueName;
        this.keyName = keyName;
    }

    @JsonValue
    public String valueName() {
        return valueName;
    }

    @JsonKey
    public String keyName() {
        return keyName;
    }
}
```

Kết quả tùy theo vị trí sử dụng:

```java
String valueJson = mapper.writeValueAsString(PaymentMethod.CARD);
// "card"

Map<PaymentMethod, Integer> fees = Map.of(PaymentMethod.CARD, 1000);
String mapJson = mapper.writeValueAsString(fees);
// {"payment-card":1000}
```

Ở đây:

- `@JsonValue` cung cấp biểu diễn khi enum là value.
- `@JsonKey` cung cấp biểu diễn khi enum là key của map.

Đây là cách hữu ích khi API muốn value là mã ngắn `card` nhưng key phải có namespace `payment-card`. Tên key và tên value có thể độc lập mà không cần tạo hai enum khác nhau.

`@JsonKey` là annotation cho serialization của map key. Không nên cho rằng chỉ khai báo `@JsonKey` thì Jackson sẽ tự biết cách chuyển chuỗi key tùy chỉnh ngược về enum trong mọi trường hợp. Nếu biểu diễn key không trùng với cách enum key deserializer mặc định nhận diện, hãy đăng ký `KeyDeserializer` như phần tiếp theo.

## 7. Deserialize Map key bằng `KeyDeserializer`

JSON object không có kiểu key riêng trong cú pháp. Jackson nhận tên field dưới dạng chuỗi, sau đó chuyển chuỗi thành kiểu key Java. Với enum, mặc định Jackson thường tìm enum constant theo tên/metadata đã cấu hình. Khi key dùng một quy ước riêng như `payment-card`, có thể viết `KeyDeserializer`.

```java
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.KeyDeserializer;

import java.io.IOException;

public class PaymentMethodKeyDeserializer extends KeyDeserializer {
    @Override
    public Object deserializeKey(String key, DeserializationContext context)
            throws IOException {
        return switch (key) {
            case "payment-card" -> PaymentMethod.CARD;
            case "cash-payment" -> PaymentMethod.CASH;
            default -> context.handleWeirdKey(
                    PaymentMethod.class,
                    key,
                    "Expected payment-card or cash-payment"
            );
        };
    }
}
```

Đăng ký key deserializer bằng `SimpleModule`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule module = new SimpleModule();
module.addKeyDeserializer(
        PaymentMethod.class,
        new PaymentMethodKeyDeserializer()
);

ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(module);
```

Đọc map:

```java
Map<PaymentMethod, Integer> fees = mapper.readValue(
        "{\"payment-card\":1000,\"cash-payment\":0}",
        new TypeReference<Map<PaymentMethod, Integer>>() {}
);

Integer cardFee = fees.get(PaymentMethod.CARD); // 1000
```

Custom key deserializer nên từ chối key không hợp lệ thay vì trả về một enum mặc định tùy tiện. Nếu nghiệp vụ cho phép giá trị dự phòng, hãy quy định rõ chính sách và ghi nhận key không nhận diện được.

### 7.1. Khác biệt giữa `JsonDeserializer` và `KeyDeserializer`

`JsonDeserializer<T>` đọc một JSON value thông thường, ví dụ chuỗi, số, object hoặc array. `KeyDeserializer` đọc tên member của JSON object để tạo key cho map.

| Thành phần | Đầu vào | Dùng cho |
|---|---|---|
| `JsonDeserializer<PaymentMethod>` | JSON value như `"card"` | Property value, phần tử array, map value |
| `KeyDeserializer` | Tên field như `"payment-card"` | `Map<PaymentMethod, V>` key |

Nếu chỉ viết custom `JsonDeserializer<PaymentMethod>`, điều đó không tự động thay thế key deserializer của `Map<PaymentMethod, V>`. Cần đăng ký đúng extension point theo vị trí của enum.

## 8. Dùng `@JsonCreator` cho enum value có quy tắc đọc riêng

Khi enum value cần chuẩn hóa chữ hoa/thường, chấp nhận alias hoặc trả lỗi theo quy tắc riêng, có thể dùng factory method với `@JsonCreator`:

```java
import com.fasterxml.jackson.annotation.JsonCreator;

public enum PaymentState {
    PENDING,
    PAID,
    FAILED;

    @JsonCreator
    public static PaymentState fromJson(String value) {
        if (value == null) {
            return null;
        }

        return switch (value.trim().toLowerCase(Locale.ROOT)) {
            case "pending", "waiting" -> PENDING;
            case "paid", "success" -> PAID;
            case "failed", "error" -> FAILED;
            default -> throw new IllegalArgumentException(
                    "Unknown payment state: " + value);
        };
    }
}
```

Factory trên áp dụng cho enum khi được đọc như JSON value. Nếu cùng chuỗi alias cần được chấp nhận làm map key, hãy kiểm tra hành vi key deserializer của version đang dùng; khi cần quy tắc riêng, triển khai `KeyDeserializer` tương ứng.

Không nên tự động chuẩn hóa mọi chuỗi đầu vào nếu hợp đồng yêu cầu phân biệt chính xác. Quy tắc alias và case-insensitive phải được xem là một phần của API contract.

## 9. Các feature enum thường gặp và phạm vi của chúng

Jackson có một số feature ảnh hưởng cách enum value được ghi/đọc:

| Feature | Tác động chính | Lưu ý |
|---|---|---|
| `WRITE_ENUMS_USING_TO_STRING` | Dùng `toString()` thay cho `name()` khi serialize enum; có thể ảnh hưởng cả enum map key | Chỉ override `toString()` nếu thật sự muốn nó trở thành wire representation; kiểm tra riêng map key theo version |
| `READ_ENUMS_USING_TO_STRING` | Dùng `toString()` khi đọc enum value | Cần giữ `toString()` ổn định và duy nhất |
| `WRITE_ENUMS_USING_INDEX` | Ghi enum value theo ordinal/index | Dễ làm dữ liệu cũ đổi nghĩa khi thêm/sắp xếp constant; thường không phù hợp API lâu dài |
| `READ_UNKNOWN_ENUM_VALUES_AS_NULL` | Cho enum value không nhận diện được thành null | Có thể làm mất tín hiệu dữ liệu không hợp lệ |
| `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` | Dùng constant có `@JsonEnumDefaultValue` cho enum value không nhận diện được | Cần khai báo default có ý nghĩa nghiệp vụ |

Ví dụ cấu hình `toString()`:

```java
ObjectMapper mapper = new ObjectMapper()
        .enable(SerializationFeature.WRITE_ENUMS_USING_TO_STRING)
        .enable(DeserializationFeature.READ_ENUMS_USING_TO_STRING);
```

`WRITE_ENUMS_USING_TO_STRING` là cấu hình ở mức mapper và có thể ảnh hưởng cả cách enum được ghi làm key của `Map`; `READ_ENUMS_USING_TO_STRING` điều khiển cách đọc enum theo `toString()`. Chúng không tạo ra hai tên độc lập cho cùng enum ở hai vai trò value và key. Nếu cần value dùng một chuỗi còn key dùng chuỗi khác, hãy dùng biểu diễn key riêng bằng `@JsonKey` hoặc `KeySerializer`, đồng thời đăng ký `KeyDeserializer` nếu cần đọc lại key tùy chỉnh. Luôn kiểm tra cả hai vai trò với version Jackson thực tế.

### 9.1. Vì sao không nên ghi enum theo ordinal?

Giả sử enum ban đầu:

```java
enum Priority {
    LOW,
    NORMAL,
    HIGH
}
```

Nếu ghi theo ordinal, `HIGH` có thể thành `2`. Sau này thêm `URGENT` vào giữa hoặc đổi thứ tự constant, cùng số `2` có thể mang nghĩa khác. Dữ liệu đã lưu trong database, file hoặc cache sẽ trở nên khó tương thích.

Với dữ liệu trao đổi lâu dài, dùng tên wire tường minh như `low`, `normal`, `high` thường ổn định hơn ordinal. Nếu buộc phải dùng mã số, hãy khai báo mã riêng bất biến, không dùng `ordinal()` làm định danh nghiệp vụ.

## 10. Enum key phải có biểu diễn duy nhất

JSON object không nên có hai member trùng tên. Nếu hai enum constant cùng được chuyển thành một key, dữ liệu có thể bị ghi thành các member trùng nhau và khi đọc lại một giá trị có thể ghi đè giá trị kia tùy parser/configuration.

Ví dụ thiết kế nguy hiểm:

```java
enum Channel {
    WEB("online"),
    MOBILE("online");

    private final String key;

    Channel(String key) {
        this.key = key;
    }

    @JsonKey
    public String key() {
        return key;
    }
}
```

Hai constant cùng trả về `online`. Khi làm key map, chúng không còn phân biệt được trong JSON object. Hãy bảo đảm mỗi enum constant được dùng làm key có wire key duy nhất. Nếu hai trạng thái cần cùng một nhãn hiển thị, hãy tạo một mã key riêng không trùng.

Ngoài ra, không nên dùng nhãn hiển thị đã dịch theo locale làm map key nếu payload cần ổn định. `"Đang xử lý"` có thể thay đổi theo ngôn ngữ hoặc cách viết; key nên là mã kỹ thuật ổn định như `in_progress`.

## 11. Khi nào map key nên là enum và khi nào nên dùng cấu trúc khác?

Enum map key phù hợp khi:

- Tập key hữu hạn và được định nghĩa trong code.
- Mỗi key có một mã chuỗi duy nhất, ổn định.
- JSON object là hình thức tự nhiên cho dữ liệu dạng tra cứu.

Ví dụ:

```json
{
  "NEW": 4,
  "IN_PROGRESS": 3,
  "COMPLETED": 12
}
```

Nếu key cần mang nhiều field, không có biểu diễn chuỗi duy nhất hoặc phải giữ metadata phức tạp, JSON object có thể không còn phù hợp. Dùng array các entry:

```json
[
  {
    "status": "NEW",
    "count": 4
  },
  {
    "status": "IN_PROGRESS",
    "count": 3
  }
]
```

Lúc này enum trở thành property value của từng entry, nên có thể dùng enum value serializer/deserializer thông thường. Cấu trúc array cũng cho phép thêm field vào mỗi entry mà không phải nhồi toàn bộ thông tin vào tên key.

## 12. Ví dụ tổng hợp: một enum có value và key riêng

Giả sử hệ thống thanh toán cần:

- Khi `PaymentMethod` là value, dùng `"card"` hoặc `"cash"`.
- Khi `PaymentMethod` là map key, dùng `"payment-card"` hoặc `"cash-payment"`.

Enum:

```java
public enum PaymentMethod {
    CARD("card", "payment-card"),
    CASH("cash", "cash-payment");

    private final String valueName;
    private final String keyName;

    PaymentMethod(String valueName, String keyName) {
        this.valueName = valueName;
        this.keyName = keyName;
    }

    @JsonValue
    public String valueName() {
        return valueName;
    }

    @JsonKey
    public String keyName() {
        return keyName;
    }
}
```

Giá trị enum:

```java
String valueJson = mapper.writeValueAsString(PaymentMethod.CARD);
// "card"
```

Map:

```java
Map<PaymentMethod, Integer> fees = new EnumMap<>(PaymentMethod.class);
fees.put(PaymentMethod.CARD, 1000);
fees.put(PaymentMethod.CASH, 0);

String feesJson = mapper.writeValueAsString(fees);
```

JSON:

```json
{
  "payment-card": 1000,
  "cash-payment": 0
}
```

Khi đọc lại map, đăng ký `PaymentMethodKeyDeserializer` như phần 7 để chuyển hai tên key về enum. Khi đọc một property value như `"card"`, `@JsonValue` có thể được dùng để tra ngược enum constant.

Ví dụ này cho thấy không nên giả định một enum chỉ có một tên JSON duy nhất. Tên value và tên map key có thể là hai hợp đồng khác nhau, và mỗi chiều cần được cấu hình tương ứng.

## 13. Kiểm thử riêng enum value và enum map key

Một test nên kiểm tra cả hai vai trò thay vì chỉ serialize enum đứng riêng:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

class EnumJsonTest {
    private final ObjectMapper mapper = createMapperWithPaymentKeyDeserializer();

    @Test
    void writesEnumAsValueUsingValueName() throws Exception {
        String json = mapper.writeValueAsString(PaymentMethod.CARD);
        assertEquals("\"card\"", json);
    }

    @Test
    void writesEnumMapKeyUsingKeyName() throws Exception {
        Map<PaymentMethod, Integer> fees = Map.of(PaymentMethod.CARD, 1000);
        String json = mapper.writeValueAsString(fees);
        assertEquals("{\"payment-card\":1000}", json);
    }

    @Test
    void readsEnumMapKeyUsingKeyDeserializer() throws Exception {
        Map<PaymentMethod, Integer> fees = mapper.readValue(
                "{\"payment-card\":1000}",
                new TypeReference<Map<PaymentMethod, Integer>>() {}
        );
        assertEquals(1000, fees.get(PaymentMethod.CARD));
    }
}
```

`createMapperWithPaymentKeyDeserializer()` là nơi tạo mapper và đăng ký module như phần 7. Nếu output object có nhiều entry, không nên kiểm tra thứ tự chuỗi trừ khi thứ tự đó là một phần hợp đồng; thay vào đó, parse JSON rồi so sánh các key/value theo cấu trúc.

Các trường hợp biên nên có test riêng:

- Enum value hợp lệ và enum key hợp lệ.
- Value/key không được nhận diện.
- Hai constant có key trùng nhau.
- Key null nếu ứng dụng có cho phép.
- Tên alias cũ khi đang chuyển đổi hợp đồng.
- Map rỗng và map có nhiều entry.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Enum property ghi `IN_PROGRESS` thay vì `in_progress` | Chưa khai báo wire name cho enum value | Dùng `@JsonProperty` hoặc `@JsonValue` |
| Enum value đúng nhưng map key vẫn khác mong đợi | Value serializer và key serializer là hai cơ chế riêng | Dùng `@JsonKey` hoặc custom key serializer |
| Map key không đọc được sau khi đổi tên | Key deserializer không biết chuỗi wire tùy chỉnh | Đăng ký `KeyDeserializer` |
| `Map.class` trả về key/value không đúng kiểu | Đã làm mất thông tin generic | Dùng `TypeReference<Map<EnumType, ValueType>>` hoặc `JavaType` |
| Hai entry bị trùng tên JSON | Hai enum constant có cùng biểu diễn key | Đảm bảo key wire duy nhất |
| Dữ liệu cũ đổi nghĩa sau khi thêm enum constant | Đã dùng ordinal/index làm định danh | Dùng mã chuỗi hoặc mã số tường minh, ổn định |
| `toString()` thay đổi làm JSON đổi theo | Bật `WRITE_ENUMS_USING_TO_STRING` hoặc dùng `toString()` làm wire value | Tách method wire riêng và kiểm soát hợp đồng |

## 15. Quy tắc lựa chọn

| Nhu cầu | Cách phù hợp |
|---|---|
| Enum value dùng đúng tên constant | Mặc định của Jackson |
| Enum value có tên API riêng | `@JsonProperty` trên constant hoặc `@JsonValue` trên accessor |
| Enum value cần alias/chuẩn hóa đầu vào | `@JsonCreator` cho enum value |
| Enum map key dùng cùng tên constant | Key serializer/deserializer enum mặc định |
| Enum map key cần tên riêng với enum value | `@JsonKey` cho ghi và `KeyDeserializer` cho đọc khi cần |
| Quy tắc map key phức tạp hoặc phụ thuộc hệ thống | Custom key serializer/deserializer hoặc đổi JSON thành array entry |
| Cần schema ổn định lâu dài | Wire name tường minh, duy nhất; tránh ordinal và nhãn hiển thị |

## 16. Kết luận

Enum trong một JSON value và enum trong khóa `Map` đi qua hai đường xử lý khác nhau. Với value, Jackson dùng enum serializer/deserializer và có thể áp dụng `@JsonProperty`, `@JsonValue`, `@JsonCreator` hoặc feature enum. Với map key, Jackson chuyển enum thành tên member dạng chuỗi và dùng key serializer/key deserializer. `@JsonKey` cho phép chỉ định biểu diễn khi enum được dùng làm key, còn `KeyDeserializer` xử lý việc chuyển tên key tùy chỉnh trở lại enum.

Hãy xác định rõ enum đang ở vai trò nào trước khi cấu hình, giữ tên wire duy nhất và ổn định, đồng thời kiểm thử cả chiều đọc lẫn chiều ghi cho property value và map key. Điều này tránh việc một thay đổi tưởng như chỉ ảnh hưởng enum value lại làm hỏng JSON object dùng enum làm key.
