# Xử lý số được gửi vào trường kiểu chuỗi hoặc boolean

JSON có kiểu dữ liệu riêng: string, number, boolean, object, array và null. Khi Jackson ánh xạ JSON vào Java, kiểu của giá trị đầu vào đôi khi khác kiểu của thuộc tính đích. Ví dụ, payload gửi số `123` vào thuộc tính Java `String`, hoặc gửi số `1` vào thuộc tính Java `boolean`.

Jackson có thể thực hiện một số chuyển đổi scalar (scalar coercion) để hỗ trợ những dữ liệu như vậy. Tuy nhiên, chuyển đổi tự động có thể che giấu lỗi hợp đồng API hoặc làm thay đổi ý nghĩa dữ liệu. Cần hiểu rõ sự khác nhau giữa JSON number và JSON string, biết khi nào Jackson cho phép coercion và cấu hình chế độ nghiêm ngặt khi hệ thống yêu cầu đúng kiểu.

## 1. Kiểu JSON và kiểu Java không giống nhau

Xét hai payload:

```json
{
  "code": 123,
  "enabled": 1
}
```

Trong JSON:

- `123` là number.
- `1` cũng là number.
- Chúng không phải string vì không có dấu ngoặc kép.
- `true` và `false` mới là hai giá trị boolean của JSON.

Nếu lớp Java khai báo:

```java
public class FeatureRequest {
    private String code;
    private Boolean enabled;

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }
}
```

thì kiểu đích không khớp hoàn toàn với kiểu JSON đầu vào:

| JSON đầu vào | Kiểu Java đích | Có chuyển đổi không? |
|---|---|---|
| `123` (number) | `String` | Jackson thường có thể chuyển scalar number thành chuỗi |
| `12.5` (number) | `String` | Jackson thường có thể chuyển scalar number thành chuỗi |
| `1` (integer) | `Boolean` | Có thể được coercion theo cấu hình/version |
| `0` (integer) | `Boolean` | Có thể được coercion theo cấu hình/version |
| `true` (boolean) | `Boolean` | Ánh xạ trực tiếp |
| `"123"` (string) | `String` | Ánh xạ trực tiếp |
| `"1"` (string) | `Boolean` | Có thể được coercion theo cấu hình/version |

Điểm quan trọng là Jackson đang chuyển đổi kiểu trong lúc data binding. Payload JSON ban đầu vẫn chứa number; nó không tự biến thành string trong hợp đồng JSON.

## 2. Số JSON được ánh xạ vào String

Jackson có thể đọc giá trị scalar number và đưa biểu diễn văn bản của nó vào thuộc tính Java kiểu `String`.

Ví dụ:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

public class StringNumberExample {
    public static class ProductRequest {
        private String productCode;

        public String getProductCode() {
            return productCode;
        }

        public void setProductCode(String productCode) {
            this.productCode = productCode;
        }
    }

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        String json = """
            {
              "productCode": 12345
            }
            """;

        ProductRequest request =
            mapper.readValue(json, ProductRequest.class);

        System.out.println(request.getProductCode());
    }
}
```

Kết quả:

```text
12345
```

Trong ví dụ, JSON number `12345` được gán vào `productCode` dưới dạng chuỗi Java `"12345"`.

### 2.1. Serialize lại sẽ phát ra JSON string

Sau khi đã đọc số vào thuộc tính String, nếu ghi object trở lại JSON:

```java
String output = mapper.writeValueAsString(request);
System.out.println(output);
```

Kết quả có dạng:

```json
{"productCode":"12345"}
```

Đầu vào dùng number, nhưng đầu ra dùng string vì kiểu Java của property là `String`. Việc coercion vì thế có thể làm thay đổi kiểu JSON khi dữ liệu đi qua ứng dụng.

Nếu API yêu cầu `productCode` luôn là chuỗi, client nên gửi:

```json
{
  "productCode": "12345"
}
```

Cách này thể hiện đúng hợp đồng và tránh phụ thuộc vào coercion.

### 2.2. Không dùng coercion để định nghĩa quy tắc mã định danh

Các giá trị như mã khách hàng, mã sản phẩm, số điện thoại, số tài khoản hoặc mã bưu chính thường nhìn giống số nhưng có ý nghĩa là định danh, không phải đại lượng để tính toán.

Ví dụ:

```json
{
  "postalCode": "00123"
}
```

Nếu gửi thành number:

```json
{
  "postalCode": 123
}
```

thì các số 0 ở đầu đã mất ngay từ payload. Jackson không thể khôi phục thông tin đó khi chuyển number thành String.

Vì vậy, nếu dữ liệu có thể chứa số 0 ở đầu, ký tự chữ hoặc không tham gia phép tính, hãy định nghĩa nó là JSON string ngay từ phía gửi.

Đối với số thập phân, định dạng văn bản có thể có khác biệt như `12.50`, `12.5` hoặc dạng số mũ. Không nên dựa vào việc chuyển number sang String để bảo toàn định dạng gốc của dữ liệu nghiệp vụ. Nếu định dạng có ý nghĩa, hãy gửi dữ liệu dưới dạng string theo một quy ước được công bố.

## 3. Số nguyên JSON được ánh xạ vào Boolean

Trong một số cấu hình Jackson 2.x, scalar coercion cho phép số nguyên được chuyển thành boolean. Quy ước thường gặp là:

- `0` được hiểu là `false`.
- `1` được hiểu là `true`.
- Một số đường coercion permissive có thể xem số nguyên khác 0 là true.

Ví dụ với JSON:

```json
{
  "enabled": 1,
  "archived": 0
}
```

và lớp Java:

```java
public class Flags {
    private boolean enabled;
    private Boolean archived;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Boolean getArchived() {
        return archived;
    }

    public void setArchived(Boolean archived) {
        this.archived = archived;
    }
}
```

Khi cấu hình Jackson cho phép coercion tương ứng, kết quả có thể là:

```text
enabled = true
archived = false
```

Đây là hành vi chuyển đổi của thư viện, không phải kiểu boolean của JSON. JSON chuẩn biểu diễn boolean bằng `true` và `false`; việc dùng `1` và `0` là quy ước riêng của một số hệ thống cũ.

### 3.1. Phân biệt số nguyên và số thập phân

Không nên giả định mọi JSON number đều có thể chuyển thành Boolean. Các parser và cấu hình Jackson có quy tắc riêng cho token integer và float; một số phiên bản/configuration cho phép integer coercion nhưng vẫn từ chối float-to-boolean.

Ví dụ:

```json
{
  "enabled": 1.0
}
```

không nên được xem là tương đương với:

```json
{
  "enabled": 1
}
```

nếu hợp đồng dùng cờ số nguyên 0/1. Hãy kiểm thử token thực tế mà hệ thống gửi và không dựa vào việc mọi biểu diễn số đều được chuyển đổi như nhau.

### 3.2. Boolean primitive và Boolean wrapper

Java có hai kiểu thường dùng:

| Kiểu | Có thể nhận null? | Giá trị mặc định khi field không được gán |
|---|---|---|
| `boolean` | Không | `false` |
| `Boolean` | Có | `null` |

Ví dụ:

```java
public class Request {
    private boolean active;
    private Boolean verified;
}
```

Nếu JSON không có key `active`, field primitive có thể giữ giá trị mặc định `false`. Nếu JSON không có key `verified`, field wrapper có thể giữ `null`.

Khi JSON có key với giá trị `null`, cách xử lý lại là một trường hợp riêng. Với primitive, Jackson có thể chuyển thành giá trị mặc định hoặc báo lỗi tùy feature; với wrapper, giá trị null có thể được giữ lại.

Nếu ứng dụng cần phân biệt rõ ba trạng thái "không gửi", "gửi false" và "gửi true", kiểu `Boolean` thường phù hợp hơn `boolean`, nhưng vẫn cần quy định riêng cách xử lý null.

## 4. Phân biệt JSON number với chuỗi chứa chữ số

Hai payload sau không giống nhau:

```json
{"enabled": 1}
```

```json
{"enabled": "1"}
```

Trường hợp đầu là JSON integer token. Trường hợp sau là JSON string token chứa ký tự `1`.

Jackson có các đường coercion khác nhau cho từng input shape. Với một số cấu hình scalar coercion, chuỗi `"true"`, `"false"`, `"1"` hoặc `"0"` có thể được chuyển thành Boolean. Nhưng không nên xem tất cả các dạng này là hợp đồng ổn định nếu chưa quy định rõ phiên bản và cấu hình mapper.

Đối với API mới, nên yêu cầu boolean JSON thực sự:

```json
{
  "enabled": true
}
```

Nếu phải tích hợp với hệ thống legacy gửi `0`/`1`, hãy định nghĩa rõ mapping và chỉ chấp nhận các giá trị được phép.

## 5. Vì sao coercion tự động có thể nguy hiểm?

Coercion giúp tương thích với dữ liệu không đồng nhất, nhưng cũng có thể che giấu lỗi từ phía client.

### 5.1. Che giấu sai kiểu trong hợp đồng

Giả sử API yêu cầu:

```json
{
  "quantity": "12"
}
```

Nhưng client gửi:

```json
{
  "quantity": 12
}
```

Nếu mapper tự chuyển số thành chuỗi, request vẫn có thể được xử lý. Client không nhận ra rằng mình đang gửi sai kiểu theo hợp đồng.

### 5.2. Làm mất ý nghĩa hoặc định dạng

Mã định danh, số điện thoại, mã vùng và mã sản phẩm có thể có số 0 đầu hoặc định dạng riêng. Chuyển number sang String không khôi phục được các ký tự đã mất.

### 5.3. Boolean từ số không rõ ý nghĩa nghiệp vụ

Nếu hệ thống chấp nhận mọi số khác 0 là true, giá trị `2`, `-1` hoặc `99` có thể bị hiểu thành cùng một trạng thái. Điều đó có thể che giấu dữ liệu lỗi hoặc lỗi mapping từ hệ thống nguồn.

Nếu hợp đồng chỉ cho phép 0 và 1, cần kiểm tra chính xác hai giá trị này thay vì chấp nhận quy tắc "khác 0 là true".

### 5.4. Đầu ra có thể khác kiểu đầu vào

Một số được đọc vào String và serialize lại sẽ thành chuỗi có dấu ngoặc kép. Một số nguyên được đọc vào Boolean và serialize lại sẽ thành `true` hoặc `false`. Vì vậy, không nên mặc định rằng đọc rồi ghi JSON sẽ bảo toàn nguyên vẹn kiểu token ban đầu.

## 6. Cấu hình strict coercion trong Jackson 2.12+

Từ Jackson 2.12, hệ thống coercion configuration cho phép kiểm soát chuyển đổi theo kiểu logic và hình dạng input. Đây là cách rõ ràng để từ chối number khi đích là String hoặc Boolean.

Ví dụ cấu hình mapper:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.type.LogicalType;

ObjectMapper mapper = JsonMapper.builder().build();

// Không chấp nhận JSON integer/float cho thuộc tính String.
mapper.coercionConfigFor(LogicalType.Textual)
    .setCoercion(CoercionInputShape.Integer, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);

// Chỉ nhận boolean đúng kiểu JSON cho thuộc tính Boolean.
mapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(CoercionInputShape.Integer, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
```

Sau cấu hình:

- `{"code": 123}` vào thuộc tính String sẽ bị từ chối.
- `{"enabled": 1}` vào thuộc tính Boolean sẽ bị từ chối.
- `{"enabled": "true"}` cũng bị từ chối vì input là string.
- `{"enabled": true}` vẫn được chấp nhận vì JSON token đã là boolean.

Coercion config ở trên áp dụng theo logical type, nên ảnh hưởng tới các thuộc tính tương ứng được mapper xử lý. Nếu chỉ một field cần quy tắc khác biệt, cân nhắc custom deserializer hoặc một DTO đầu vào riêng để giới hạn phạm vi chính sách.

### 6.1. Strict coercion chỉ cho String, vẫn cho phép boolean string

Nếu API muốn từ chối số vào Boolean nhưng vẫn chấp nhận `"true"` và `"false"` dưới dạng string, chỉ cấu hình các input shape số:

```java
mapper.coercionConfigFor(LogicalType.Boolean)
    .setCoercion(CoercionInputShape.Integer, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);
```

Cấu hình này thể hiện chính sách hẹp hơn. Cần test cả token number lẫn token string vì chúng là hai input shape khác nhau.

### 6.2. Phiên bản cũ hơn

Coercion configuration theo `LogicalType` có từ Jackson 2.12. Nếu ứng dụng dùng phiên bản cũ hơn, API này có thể không có sẵn. Khi đó có thể:

- Nâng Jackson lên một phiên bản phù hợp với framework.
- Dùng custom deserializer cho kiểu hoặc field cần kiểm soát.
- Nhận giá trị vào DTO trung gian có kiểu phù hợp rồi xác thực/chuyển đổi tường minh ở tầng mapping.

Không nên nâng riêng một module Jackson mà không kiểm tra version alignment với Core, Databind và framework đang quản lý dependency.

## 7. Chuyển đổi tường minh cho cờ số 0/1

Nếu hệ thống nguồn bắt buộc gửi số nguyên 0 hoặc 1, có thể nhận vào kiểu số nguyên rồi tự chuyển đổi sau khi xác thực.

DTO đầu vào:

```java
public class LegacyFeatureRequest {
    private Integer enabled;

    public Integer getEnabled() {
        return enabled;
    }

    public void setEnabled(Integer enabled) {
        this.enabled = enabled;
    }
}
```

Mapper nghiệp vụ:

```java
public boolean toBooleanFlag(Integer value) {
    if (value == null) {
        throw new IllegalArgumentException("enabled is required");
    }

    return switch (value) {
        case 0 -> false;
        case 1 -> true;
        default -> throw new IllegalArgumentException(
            "enabled must be 0 or 1"
        );
    };
}
```

Cách làm này có lợi ích:

- Chỉ chấp nhận hai giá trị đã định nghĩa.
- Không vô tình hiểu `2` hoặc `-1` là true.
- Có thể trả lỗi validation cụ thể.
- Quy tắc legacy nằm ở ranh giới tích hợp, không lan vào domain model.

Nếu field là số thập phân hoặc dữ liệu có thể đến dưới dạng string, hãy xác định riêng có cho phép các dạng đó không. Đừng âm thầm parse mọi kiểu về số nguyên.

## 8. Dùng custom deserializer khi cần quy tắc riêng

Nếu API cần nhận nhiều dạng nhưng muốn kiểm soát chính xác, có thể viết deserializer riêng.

Ví dụ chỉ nhận JSON boolean hoặc integer 0/1:

```java
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;

import java.io.IOException;

public class StrictBooleanDeserializer
        extends JsonDeserializer<Boolean> {

    @Override
    public Boolean deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        JsonToken token = parser.currentToken();

        if (token == JsonToken.VALUE_TRUE) {
            return true;
        }

        if (token == JsonToken.VALUE_FALSE) {
            return false;
        }

        if (token == JsonToken.VALUE_NUMBER_INT) {
            int value = parser.getIntValue();

            if (value == 1) {
                return true;
            }
            if (value == 0) {
                return false;
            }
        }

        throw JsonMappingException.from(
            parser,
            "Expected JSON boolean or integer 0/1"
        );
    }

    @Override
    public Boolean getNullValue(DeserializationContext context) {
        return null;
    }
}
```

Gắn deserializer vào field:

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;

public class FeatureRequest {
    @JsonDeserialize(using = StrictBooleanDeserializer.class)
    private Boolean enabled;

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }
}
```

Trong ví dụ này, JSON boolean và integer 0/1 được chấp nhận. Số nguyên khác, số thập phân và string đều bị từ chối. Nếu field bắt buộc, cần kiểm tra thêm trường hợp key bị thiếu; `getNullValue` ở trên chỉ mô tả cách xử lý token null, không tự biến một property bị thiếu thành lỗi.

Custom deserializer phù hợp khi quy tắc chỉ áp dụng cho một field hoặc một kiểu domain cụ thể. Với chính sách chung cho mọi String/Boolean, coercion configuration thường dễ quản lý hơn.

## 9. Kiểm tra token trước khi ánh xạ bằng JsonNode

Khi cấu trúc JSON thay đổi giữa các nguồn hoặc cần báo lỗi cụ thể theo kiểu token, có thể đọc thành `JsonNode` trước:

```java
JsonNode root = mapper.readTree(json);
JsonNode enabledNode = root.path("enabled");

if (enabledNode.isBoolean()) {
    boolean enabled = enabledNode.booleanValue();
} else if (enabledNode.isIntegralNumber()) {
    int flag = enabledNode.intValue();

    if (flag != 0 && flag != 1) {
        throw new IllegalArgumentException("enabled must be 0 or 1");
    }

    boolean enabled = flag == 1;
} else {
    throw new IllegalArgumentException(
        "enabled must be a boolean or integer 0/1"
    );
}
```

Cách này cho phép phân biệt rõ token boolean, integer, float, string, null và missing. Đổi lại, ứng dụng phải tự quản lý việc kiểm tra và ánh xạ các trường. Với DTO ổn định, deserializer hoặc coercion config thường gọn hơn.

## 10. Kiểm thử các trường hợp coercion

Nên kiểm tra không chỉ payload hợp lệ mà cả những kiểu token không được phép.

Ví dụ với cấu hình strict coercion ở mục 6:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.cfg.CoercionAction;
import com.fasterxml.jackson.databind.cfg.CoercionInputShape;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.databind.type.LogicalType;
import org.junit.jupiter.api.Test;

class ScalarCoercionTest {
    private final ObjectMapper mapper = createStrictMapper();

    private static ObjectMapper createStrictMapper() {
        ObjectMapper mapper = JsonMapper.builder().build();
        mapper.coercionConfigFor(LogicalType.Textual)
            .setCoercion(CoercionInputShape.Integer, CoercionAction.Fail)
            .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);
        mapper.coercionConfigFor(LogicalType.Boolean)
            .setCoercion(CoercionInputShape.Integer, CoercionAction.Fail)
            .setCoercion(CoercionInputShape.Float, CoercionAction.Fail)
            .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
        return mapper;
    }

    @Test
    void acceptsCorrectJsonTypes() throws Exception {
        FeatureRequest request = mapper.readValue(
            """
            {
              "code": "123",
              "enabled": true
            }
            """,
            FeatureRequest.class
        );

        assertEquals("123", request.getCode());
        assertEquals(Boolean.TRUE, request.getEnabled());
    }

    @Test
    void rejectsNumberForStringProperty() {
        assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(
                """
                {"code": 123, "enabled": true}
                """,
                FeatureRequest.class
            )
        );
    }

    @Test
    void rejectsNumberForBooleanProperty() {
        assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(
                """
                {"code": "123", "enabled": 1}
                """,
                FeatureRequest.class
            )
        );
    }
}
```

Trong test hoàn chỉnh, `createStrictMapper()` cần trả về mapper đã cấu hình coercion như mục 6. Có thể bổ sung test cho float, chuỗi `"1"`, null và property bị thiếu để bảo đảm chính sách được thực thi nhất quán.

## 11. Chọn chính sách theo hợp đồng API

| Nhu cầu | Cách xử lý phù hợp |
|---|---|
| Mã định danh phải là chuỗi | Yêu cầu JSON string và từ chối number-to-string |
| Số lượng, giá tiền là số | Dùng kiểu số phù hợp; không đổi sang String chỉ để nhận dữ liệu dễ hơn |
| Cờ trạng thái theo JSON chuẩn | Dùng `true`/`false` và từ chối numeric coercion |
| Hệ thống cũ gửi cờ 0/1 | Nhận Integer, xác thực chỉ 0/1, rồi chuyển thành Boolean |
| Chỉ một field có quy tắc đặc biệt | Dùng custom deserializer hoặc DTO trung gian |
| Toàn ứng dụng cần strict typing | Cấu hình coercion theo logical type và kiểm thử contract |

Nguyên tắc nên áp dụng là kiểu Java của DTO phản ánh đúng ý nghĩa dữ liệu. `String` dành cho văn bản hoặc định danh; `Boolean` dành cho trạng thái hai giá trị; kiểu số dành cho đại lượng có thể tính toán. Nếu một nguồn legacy gửi kiểu khác, chuyển đổi tại ranh giới tích hợp và xác thực rõ ràng.

## 12. Ghi nhớ

- JSON number `123` khác JSON string `"123"`; dấu ngoặc kép quyết định kiểu token.
- Jackson có thể chuyển number vào String; khi serialize lại, property String sẽ được ghi thành JSON string.
- Một số cấu hình Jackson cho phép integer coercion sang Boolean, thường dùng quy ước 0=false và 1=true; không nên dựa vào coercion rộng cho hợp đồng mới.
- Phân biệt integer token với float token và numeric token với string chứa chữ số.
- Từ Jackson 2.12, dùng `CoercionConfig` để từ chối input shape không mong muốn theo logical type.
- Nếu hệ thống legacy gửi 0/1, nhận số nguyên và xác thực chính xác hai giá trị trước khi chuyển đổi.
- Phân biệt field bị thiếu, null và giá trị false; dùng `Boolean` khi cần biểu diễn trạng thái chưa được cung cấp.

