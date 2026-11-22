# Enum và giá trị được tuần tự hóa thực tế

Enum trong Java giúp giới hạn một thuộc tính vào tập giá trị đã biết, ví dụ trạng thái đơn hàng chỉ có thể là chờ thanh toán, đã thanh toán hoặc đã hủy. Tuy nhiên, tên constant trong mã nguồn không nhất thiết là giá trị mà API gửi qua JSON. Jackson có thể tuần tự hóa enum thành tên constant, chuỗi tùy chỉnh, số hoặc một object. **springdoc-openapi** phải mô tả đúng giá trị được truyền trên HTTP để client hiểu và gửi dữ liệu hợp lệ.

Khi thiết kế schema enum, cần phân biệt ba lớp:

1. **Giá trị nội bộ trong Java:** tên constant hoặc thuộc tính của enum.
2. **Giá trị JSON thực tế:** kết quả do Jackson serializer ghi ra response và giá trị deserializer chấp nhận ở request.
3. **Giá trị OpenAPI:** các phần tử trong thuộc tính schema **enum**, cùng kiểu dữ liệu và định dạng của chúng.

Nếu ba lớp này không khớp, Swagger UI có thể gợi ý giá trị sai, tài liệu có thể mô tả sai response và client sinh từ OpenAPI có thể gửi request không được server chấp nhận.

## 1. Enum mặc định trong Java và JSON

Khi không có cấu hình đặc biệt, Jackson thường tuần tự hóa enum thành tên constant:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

Một DTO sử dụng enum:

~~~java
public record OrderView(
    String id,
    OrderStatus status
) {}
~~~

Response JSON mặc định có dạng:

~~~json
{
  "id": "ORD-1001",
  "status": "PENDING"
}
~~~

Schema OpenAPI tương ứng cần thể hiện thuộc tính status là chuỗi và liệt kê đúng các giá trị được phép:

~~~yaml
OrderStatus:
  type: string
  enum:
    - PENDING
    - PAID
    - CANCELLED
~~~

Giá trị enum phân biệt chữ hoa và chữ thường. Ví dụ, PENDING và pending là hai giá trị khác nhau trong hợp đồng. Không dùng tên hiển thị trong giao diện như Đang chờ nếu API thực tế truyền PENDING.

## 2. Phân biệt tên constant và wire value

Trong hệ thống thực tế, API thường cần giá trị ổn định, dễ đọc hoặc tương thích với hệ thống khác. Tên constant có thể dùng quy ước Java như PENDING_PAYMENT, trong khi JSON dùng chuỗi pending-payment.

~~~java
public enum OrderStatus {
    PENDING_PAYMENT,
    PAID,
    CANCELLED
}
~~~

Nếu Jackson vẫn dùng cấu hình mặc định, response sẽ chứa PENDING_PAYMENT. Muốn đổi giá trị gửi qua HTTP, cần cấu hình serialization bằng annotation hoặc serializer. Không nên chỉ đổi mô tả OpenAPI thành pending-payment trong khi Jackson vẫn ghi PENDING_PAYMENT.

Một enum nên có một định nghĩa rõ ràng về giá trị wire. Ví dụ:

~~~java
public enum OrderStatus {
    PENDING_PAYMENT("pending-payment"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    public String getWireValue() {
        return wireValue;
    }
}
~~~

Chỉ có field wireValue chưa làm Jackson tự động dùng nó. Cần đánh dấu cách serialize ở phần tiếp theo.

## 3. Dùng @JsonValue để tuần tự hóa giá trị tùy chỉnh

Annotation **@JsonValue** đánh dấu phương thức hoặc field mà Jackson dùng làm giá trị JSON cho enum. Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING_PAYMENT("pending-payment"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String getWireValue() {
        return wireValue;
    }
}
~~~

Khi serialize, giá trị nhận được là chuỗi tùy chỉnh:

~~~json
{
  "status": "pending-payment"
}
~~~

Khi dùng enum với @JsonValue, cần kiểm tra cả hai chiều:

- Serialization: constant PENDING_PAYMENT được ghi thành chuỗi pending-payment.
- Deserialization: request có giá trị pending-payment có được chuyển về constant PENDING_PAYMENT hay không.

Jackson hỗ trợ dùng giá trị @JsonValue của enum trong quá trình deserialization ở các phiên bản phù hợp. Tuy vậy, nếu cần kiểm soát rõ alias, lỗi đầu vào hoặc quy tắc chuyển đổi, hãy khai báo factory bằng @JsonCreator.

## 4. Dùng @JsonCreator để đọc giá trị JSON

@JsonCreator cho phép chỉ định cách tạo enum từ giá trị đầu vào. Có thể kết hợp với @JsonValue để định nghĩa wire value chuẩn:

~~~java
import java.util.Arrays;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING_PAYMENT("pending-payment"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String getWireValue() {
        return wireValue;
    }

    @JsonCreator
    public static OrderStatus fromWireValue(String value) {
        return Arrays.stream(values())
            .filter(status -> status.wireValue.equals(value))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown order status: " + value)
            );
    }
}
~~~

Với định nghĩa trên:

| Giá trị JSON | Kết quả |
| --- | --- |
| pending-payment | PENDING_PAYMENT |
| paid | PAID |
| cancelled | CANCELLED |
| PENDING_PAYMENT | Không được chấp nhận nếu factory không định nghĩa alias này |
| unknown | Bị từ chối |

Factory cần có quy tắc rõ ràng cho giá trị không hợp lệ. Khi exception được ném trong lúc binding request, Spring/Jackson thường chuyển lỗi thành response lỗi đầu vào, thường là 400 tùy cấu hình exception handler.

Nếu API cần chấp nhận nhiều giá trị cũ nhưng chỉ phát ra một giá trị chuẩn, có thể xử lý alias trong @JsonCreator:

~~~java
@JsonCreator
public static OrderStatus fromWireValue(String value) {
    return switch (value) {
        case "pending-payment", "PENDING_PAYMENT", "pending" ->
            PENDING_PAYMENT;
        case "paid", "PAID" -> PAID;
        case "cancelled", "CANCELLED" -> CANCELLED;
        default -> throw new IllegalArgumentException(
            "Unknown order status: " + value
        );
    };
}
~~~

Khi đó, request có thể gửi nhiều alias, nhưng response vẫn chỉ phát ra giá trị chuẩn do @JsonValue trả về. Đây là điểm quan trọng khi mô tả schema: tập giá trị chấp nhận ở request có thể rộng hơn tập giá trị được phát ra ở response.

## 5. Dùng @JsonProperty trên từng enum constant

Nếu chỉ cần ánh xạ tên constant sang chuỗi cụ thể, có thể đặt @JsonProperty trực tiếp trên từng constant:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public enum PaymentStatus {
    @JsonProperty("awaiting-payment")
    PENDING,

    @JsonProperty("settled")
    PAID,

    @JsonProperty("reversed")
    REFUNDED
}
~~~

Jackson dùng các chuỗi được khai báo để serialize và deserialize enum theo cấu hình tương ứng:

~~~json
{
  "paymentStatus": "awaiting-payment"
}
~~~

Cách này phù hợp khi mỗi constant có một giá trị JSON đơn giản. Nếu cần alias, chuẩn hóa input hoặc xử lý logic chuyển đổi phức tạp, @JsonCreator giúp thể hiện quy tắc rõ ràng hơn.

Nên chọn một chiến lược nhất quán cho một enum. Tránh kết hợp nhiều cơ chế ánh xạ như @JsonProperty, @JsonValue, @JsonCreator và serializer tùy chỉnh mà không xác định thứ tự ưu tiên cũng như hành vi thực tế của ObjectMapper.

## 6. Khi Jackson cấu hình enum thành số hoặc object

Enum không phải lúc nào cũng được serialize thành chuỗi. Cấu hình ObjectMapper hoặc annotation có thể thay đổi kiểu JSON.

### Serialize enum thành số

Jackson có thể được cấu hình ghi enum thành ordinal hoặc một mã số. Ví dụ, nếu ứng dụng sử dụng mã số nghiệp vụ:

~~~java
public enum PaymentStatus {
    PENDING(10),
    PAID(20),
    REFUNDED(30);

    private final int code;

    PaymentStatus(int code) {
        this.code = code;
    }

    @JsonValue
    public int getCode() {
        return code;
    }
}
~~~

Response JSON sẽ chứa số:

~~~json
{
  "paymentStatus": 10
}
~~~

Schema OpenAPI lúc này phải mô tả kiểu integer, không phải string:

~~~yaml
type: integer
format: int32
enum:
  - 10
  - 20
  - 30
~~~

Không nên dùng ordinal làm mã API ổn định. Ordinal phụ thuộc thứ tự khai báo constant; khi thêm hoặc sắp xếp lại enum, giá trị đã phát hành có thể thay đổi. Dùng mã nghiệp vụ tường minh nếu API cần số.

### Serialize enum thành object

Với cấu hình **@JsonFormat(shape = JsonFormat.Shape.OBJECT)** hoặc custom serializer, enum có thể được ghi thành object thay vì scalar. Ví dụ:

~~~json
{
  "paymentStatus": {
    "code": "awaiting-payment",
    "label": "Đang chờ thanh toán"
  }
}
~~~

Trong trường hợp này, schema không còn là một enum string đơn giản. Cần mô tả object với các property code và label, đúng kiểu dữ liệu và ràng buộc. Kiểm tra JSON thực tế trước khi quyết định schema.

### Cấu hình toàn cục ảnh hưởng đến wire value

Các cấu hình Jackson như **WRITE_ENUMS_USING_TO_STRING**, **WRITE_ENUMS_USING_INDEX**, **READ_ENUMS_USING_TO_STRING** hoặc **ACCEPT_CASE_INSENSITIVE_ENUMS** có thể thay đổi cách đọc/ghi enum. Phạm vi tác động phụ thuộc phiên bản Jackson và cách cấu hình ObjectMapper trong Spring Boot.

Nếu enum override toString() hoặc ứng dụng bật WRITE_ENUMS_USING_TO_STRING, giá trị phát ra có thể khác tên constant. Nếu bật WRITE_ENUMS_USING_INDEX, JSON có thể chứa số ordinal. Không được giả định schema chỉ dựa trên mã enum Java; hãy xác minh với ObjectMapper đang được Spring sử dụng.

## 7. Mô tả enum trong OpenAPI bằng @Schema

Springdoc thường suy luận schema enum từ kiểu Java và thư viện Jackson. Với enum mặc định, nó có thể tạo schema có type string và danh sách enum. Khi giá trị wire tùy chỉnh hoặc cấu hình serialization làm thay đổi kiểu dữ liệu, cần kiểm tra kết quả và bổ sung metadata nếu cần.

### Khai báo allowableValues

Có thể mô tả các giá trị được phép bằng **@Schema(allowableValues = ...)**:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record OrderView(
    String id,

    @Schema(
        description = "Trạng thái đơn hàng trong API",
        type = "string",
        allowableValues = {
            "pending-payment",
            "paid",
            "cancelled"
        },
        example = "pending-payment"
    )
    OrderStatus status
) {}
~~~

Trong ví dụ, schema mô tả các giá trị chuỗi mà API phát ra. Đảm bảo danh sách allowableValues khớp với giá trị do Jackson serialize. Nếu chỉ sửa annotation mà không sửa ObjectMapper, tài liệu có thể trở nên sai lệch.

Với mã số, khai báo kiểu phù hợp:

~~~java
@Schema(
    type = "integer",
    format = "int32",
    allowableValues = {"10", "20", "30"},
    example = "10"
)
PaymentStatus paymentStatus
~~~

Kiểm tra OpenAPI sinh ra để chắc chắn enum được biểu diễn thành số chứ không phải chuỗi chứa số. Thuộc tính allowableValues của annotation nhận chuỗi, còn kiểu của schema quyết định cách các giá trị được biểu diễn trong đặc tả.

### Dùng enumAsRef để tái sử dụng schema

Khi một enum xuất hiện ở nhiều request và response, có thể tạo schema dùng chung trong components bằng **@Schema(enumAsRef = true)**:

Ví dụ dưới đây giả định enum dùng cách serialize mặc định, tức JSON chứa tên constant. Nếu enum đang dùng **@JsonValue** hoặc **@JsonProperty**, danh sách trong component cần phản ánh đúng wire value tương ứng.

~~~java
@Schema(
    name = "OrderStatus",
    description = "Các trạng thái đơn hàng được API hỗ trợ",
    enumAsRef = true
)
public enum OrderStatus {
    PENDING_PAYMENT,
    PAID,
    CANCELLED
}
~~~

Các thuộc tính dùng enum có thể tham chiếu schema:

~~~yaml
components:
  schemas:
    OrderStatus:
      type: string
      description: Các trạng thái đơn hàng được API hỗ trợ
      enum:
        - PENDING_PAYMENT
        - PAID
        - CANCELLED
~~~

Ở request hoặc response, schema có thể dùng:

~~~yaml
status:
  $ref: '#/components/schemas/OrderStatus'
~~~

Việc dùng enumAsRef giúp tránh lặp danh sách enum ở nhiều nơi và làm thay đổi giá trị enum có một điểm quản lý tập trung. Tuy nhiên, chỉ dùng schema chung khi các operation thật sự có cùng tập giá trị và cùng kiểu wire value.

## 8. Request và response có thể có tập enum khác nhau

Một API đôi khi chấp nhận alias cũ ở request nhưng chỉ phát ra giá trị chuẩn ở response. Ví dụ:

- Request chấp nhận pending-payment, pending hoặc PENDING_PAYMENT.
- Response chỉ trả pending-payment.

Một schema enum dùng chung không thể diễn đạt chính xác hai tập giá trị khác nhau nếu không bổ sung cách mô tả riêng. Khi đó có thể:

1. Tạo kiểu enum hoặc DTO riêng cho request và response.
2. Khai báo schema riêng cho request property và response property bằng annotation phù hợp.
3. Dùng OpenApiCustomizer để điều chỉnh schema theo operation khi annotation không đủ.
4. Đơn giản hóa hợp đồng, chỉ chấp nhận một wire value chuẩn nếu không cần hỗ trợ alias.

Ví dụ tách kiểu:

~~~java
public enum OrderStatusInput {
    PENDING_PAYMENT,
    PENDING,
    PAID,
    CANCELLED
}

public enum OrderStatusOutput {
    PENDING_PAYMENT,
    PAID,
    CANCELLED
}
~~~

Đây là một lựa chọn mô hình hóa. Nếu cần giữ cùng domain enum bên trong, có thể dùng DTO biên hoặc converter để chuyển đổi từ input contract sang kiểu nghiệp vụ và từ kiểu nghiệp vụ sang output contract.

Đừng đưa mọi alias mà server tình cờ chấp nhận vào schema response. Schema của response cần phản ánh giá trị server thực sự phát ra; schema của request cần phản ánh các giá trị client được phép gửi.

## 9. Enum trong query parameter, path parameter và header

Enum có thể xuất hiện ở nhiều vị trí ngoài JSON body. Ví dụ:

~~~java
@GetMapping("/api/orders")
List<OrderView> findOrders(
    @RequestParam OrderStatus status
) {
    return orderService.findByStatus(status);
}
~~~

OpenAPI mô tả query parameter có schema enum:

~~~yaml
parameters:
  - name: status
    in: query
    required: true
    schema:
      type: string
      enum:
        - pending-payment
        - paid
        - cancelled
~~~

Nếu Spring nhận enum bằng tên constant mặc định nhưng Jackson response lại dùng @JsonValue tùy chỉnh, cần kiểm tra riêng quy tắc chuyển đổi query parameter. Spring MVC conversion service không nhất thiết dùng cùng cơ chế với Jackson JSON deserialization.

Điều này có nghĩa:

- @JsonValue có thể điều khiển JSON body nhưng không tự động bảo đảm query parameter được parse theo wire value đó.
- @JsonCreator của Jackson cũng không mặc nhiên được dùng cho @RequestParam hoặc @PathVariable.
- Nếu API dùng wire value tùy chỉnh trong query/path, hãy cung cấp converter Spring như **Converter<String, OrderStatus>** và kiểm tra cả request binding lẫn OpenAPI parameter enum.

Ví dụ converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
public class OrderStatusConverter implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromWireValue(source);
    }
}
~~~

Converter này giúp Spring MVC chuyển giá trị query hoặc path thành enum theo quy tắc của ứng dụng. Schema OpenAPI vẫn cần mô tả đúng tập wire value mà converter chấp nhận.

## 10. Kiểm tra giá trị thực tế bằng ObjectMapper

Trước khi kiểm tra OpenAPI, hãy xác nhận ObjectMapper đang dùng trong ứng dụng ghi và đọc enum như thế nào.

Ví dụ kiểm thử:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderStatusJsonTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesCanonicalWireValue() throws Exception {
        String json = objectMapper.writeValueAsString(
            OrderStatus.PENDING_PAYMENT
        );

        assertThat(json).isEqualTo("\"pending-payment\"");
    }

    @Test
    void readsWireValue() throws Exception {
        OrderStatus status = objectMapper.readValue(
            "\"pending-payment\"",
            OrderStatus.class
        );

        assertThat(status).isEqualTo(OrderStatus.PENDING_PAYMENT);
    }
}
~~~

Đây là kiểm tra ở cấp Jackson. Nó giúp xác nhận serialization/deserialization độc lập với Springdoc. Nếu ứng dụng có nhiều ObjectMapper hoặc cấu hình converter riêng, cần kiểm tra đúng mapper được dùng cho HTTP message conversion.

## 11. Kiểm tra enum trong OpenAPI được sinh ra

Sau khi khởi động ứng dụng, lấy tài liệu:

~~~bash
curl -sS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra schema enum:

~~~bash
jq '.components.schemas.OrderStatus' openapi.json
~~~

Kiểm tra operation có request hoặc response dùng enum:

~~~bash
jq '.paths["/api/orders"].get' openapi.json
~~~

Đối chiếu các điểm:

1. Kiểu schema là string, integer hay object đúng với JSON thực tế.
2. Danh sách enum có đúng wire value và đúng chữ hoa/chữ thường.
3. Giá trị example nằm trong tập enum.
4. Schema request và response có phản ánh khác biệt nếu server chấp nhận alias.
5. Parameter query/path/header dùng cùng quy tắc chuyển đổi mà Spring MVC thực thi.
6. Nếu dùng enumAsRef, các property tham chiếu đúng component và không có schema trùng tên.

Có thể bổ sung assertion trong kiểm thử tích hợp để đọc /v3/api-docs và xác nhận danh sách enum. Nếu schema dùng $ref, cần resolve reference đến components.schemas trước khi so sánh giá trị.

## 12. Lỗi thường gặp

**Swagger UI hiển thị tên constant thay vì wire value.** Kiểm tra ObjectMapper có dùng @JsonValue hoặc @JsonProperty hay không. Sau đó kiểm tra schema được sinh ra. Nếu schema vẫn dùng tên constant, bổ sung @Schema(allowableValues) hoặc điều chỉnh schema bằng customizer và kiểm thử lại.

**Response trả chuỗi nhưng OpenAPI mô tả integer.** Kiểm tra @JsonValue, WRITE_ENUMS_USING_INDEX hoặc serializer tùy chỉnh. Kiểu OpenAPI phải khớp JSON thực tế.

**Request JSON chấp nhận giá trị nhưng query parameter lại báo lỗi.** JSON deserialization và Spring MVC conversion là hai đường xử lý khác nhau. Tạo Converter<String, Enum> nếu cần dùng wire value tùy chỉnh trong query hoặc path.

**Thêm alias nhưng schema không thể hiện đầy đủ.** Xác định alias chỉ dành cho request hay cũng được phát ra trong response. Nếu hai chiều khác nhau, dùng schema riêng thay vì một enum dùng chung gây hiểu nhầm.

**Đổi thứ tự constant làm thay đổi API.** Kiểm tra ứng dụng có serialize ordinal/index hay không. Dùng mã wire ổn định, tường minh thay vì phụ thuộc thứ tự constant.

**Enum thành object nhưng schema vẫn là string.** Kiểm tra @JsonFormat(shape = OBJECT) hoặc custom serializer và khai báo schema object tương ứng.

## 13. Checklist thiết kế enum cho API

- [ ] Xác định giá trị enum thực tế mà JSON response phát ra.
- [ ] Xác định tập giá trị mà JSON request chấp nhận.
- [ ] Xác định riêng quy tắc binding cho query, path và header parameter.
- [ ] Chọn một chiến lược Jackson rõ ràng: mặc định, @JsonValue, @JsonProperty hoặc custom serializer.
- [ ] Dùng @JsonCreator nếu cần kiểm soát parsing hoặc hỗ trợ alias.
- [ ] Không dùng ordinal làm giá trị API ổn định.
- [ ] Mô tả đúng type và enum trong OpenAPI.
- [ ] Dùng @Schema(enumAsRef = true) khi schema thực sự được chia sẻ.
- [ ] Kiểm tra ObjectMapper và JSON runtime.
- [ ] Kiểm tra /v3/api-docs và Swagger UI sau khi thay đổi enum.

## 14. Kết luận

Enum Java chỉ là biểu diễn nội bộ của tập trạng thái. Giá trị API phụ thuộc vào cách Jackson serialize và deserialize, cách Spring MVC bind parameter và schema mà springdoc sinh ra. Hãy xác định wire value trước, cấu hình Jackson nhất quán, mô tả đúng kiểu cùng danh sách enum trong OpenAPI và kiểm tra cả request lẫn response thực tế. Khi request có alias hoặc cách binding khác response, dùng hợp đồng riêng cho từng chiều để client không phải đoán giá trị hợp lệ.

## 15. Nguồn tham khảo

- [Jackson Annotations — JsonValue](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonValue.html): đánh dấu giá trị được dùng khi serialize enum hoặc thuộc tính.
- [Jackson Annotations — JsonCreator](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonCreator.html): định nghĩa constructor hoặc factory dùng để tạo giá trị từ JSON.
- [Swagger Core — Schema annotation](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/media/Schema.html): thuộc tính allowableValues và enumAsRef của schema annotation.
- [Springdoc OpenAPI documentation](https://springdoc.org/): cách springdoc tạo và tùy biến schema OpenAPI từ ứng dụng Spring.
