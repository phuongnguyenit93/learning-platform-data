# Serializer hoặc deserializer tùy chỉnh và schema cần bổ sung

Jackson quyết định cách chuyển object Java thành JSON khi trả response và cách đọc JSON thành object Java khi nhận request. springdoc-openapi tạo đặc tả từ controller, kiểu Java, annotation và metadata của ứng dụng. Khi Jackson được cấu hình serializer hoặc deserializer tùy chỉnh, cấu trúc JSON thực tế có thể khác với cấu trúc mà springdoc suy ra từ kiểu Java.

Vì vậy, cần kiểm tra hai phía của hợp đồng: Jackson thực sự ghi/đọc JSON như thế nào và OpenAPI công bố dữ liệu đó ra sao. Nếu serializer biến một value object Java thành chuỗi JSON, schema phải mô tả chuỗi. Nếu deserializer nhận một định dạng đặc biệt, schema cần thể hiện đúng kiểu, format, pattern và ví dụ để client gửi dữ liệu phù hợp.

## 1. Serializer và deserializer hoạt động ở đâu?

Jackson có hai hướng xử lý chính:

- **Serialization**: chuyển object Java thành JSON, thường dùng khi controller trả response.
- **Deserialization**: đọc JSON và tạo object Java, thường dùng khi Spring bind request body vào DTO.

Một số annotation Jackson thường gặp:

| Annotation | Tác dụng |
|---|---|
| <code>@JsonSerialize</code> | Chọn serializer cho kiểu hoặc thuộc tính |
| <code>@JsonDeserialize</code> | Chọn deserializer cho kiểu hoặc thuộc tính |
| <code>@JsonProperty</code> | Đặt tên thuộc tính trong JSON và điều khiển khả năng đọc/ghi |
| <code>@JsonFormat</code> | Điều chỉnh định dạng của một số kiểu dữ liệu, chẳng hạn ngày giờ |
| <code>@JsonIgnore</code> | Bỏ qua thuộc tính trong quá trình xử lý JSON theo cấu hình annotation |
| <code>@JsonCreator</code> | Chỉ định constructor hoặc factory method dùng để tạo object từ JSON |
| <code>@JsonValue</code> | Chọn giá trị được dùng làm biểu diễn JSON cho object hoặc enum |

Có thể đặt serializer/deserializer ở cấp kiểu Java hoặc trên một thuộc tính cụ thể. Đặt ở cấp kiểu áp dụng cho những nơi dùng kiểu đó; đặt ở cấp thuộc tính chỉ điều chỉnh một field hoặc record component.

## 2. Ví dụ: Money trong Java được truyền thành chuỗi JSON

Giả sử ứng dụng lưu tiền bằng value object <code>Money</code> có thuộc tính <code>amount</code>. Nếu không tùy chỉnh, Jackson có thể tuần tự hóa object thành dạng:

~~~json
{
  "total": {
    "amount": 125000.00
  }
}
~~~

Nhưng hợp đồng của API yêu cầu biểu diễn tiền thành một chuỗi có mã tiền tệ:

~~~json
{
  "total": "VND 125000.00"
}
~~~

Đây là thay đổi về wire format. Kiểu Java vẫn là <code>Money</code>, nhưng kiểu JSON bên ngoài là <code>string</code>. Nếu OpenAPI vẫn mô tả <code>total</code> như object có thuộc tính <code>amount</code>, client sẽ sinh mã và gửi dữ liệu theo cấu trúc sai.

### 2.1. Khai báo value object

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

@JsonSerialize(using = MoneySerializer.class)
@JsonDeserialize(using = MoneyDeserializer.class)
public record Money(BigDecimal amount) {

    public Money {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must be a non-negative number"
            );
        }
        amount = amount.setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Hai annotation gắn serializer và deserializer vào kiểu <code>Money</code>. Constructor chuẩn hóa số tiền về hai chữ số thập phân và từ chối giá trị âm hoặc null.

### 2.2. Viết serializer

~~~java
import java.io.IOException;
import java.math.RoundingMode;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {

        String wireValue = "VND "
            + value.amount()
                .setScale(2, RoundingMode.HALF_UP)
                .toPlainString();

        generator.writeString(wireValue);
    }
}
~~~

Serializer ghi ra một JSON string bằng <code>writeString</code>. Vì vậy, <code>Money(125000)</code> trở thành <code>"VND 125000.00"</code>, không phải JSON object.

### 2.3. Viết deserializer

~~~java
import java.io.IOException;
import java.math.BigDecimal;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonDeserializer;

public class MoneyDeserializer extends JsonDeserializer<Money> {

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.hasToken(JsonToken.VALUE_STRING)) {
            throw JsonMappingException.from(
                parser,
                "Money must be a string such as VND 125000.00"
            );
        }

        String raw = parser.getText();
        if (!raw.startsWith("VND ")) {
            throw JsonMappingException.from(
                parser,
                "Money must start with VND"
            );
        }

        try {
            return new Money(new BigDecimal(raw.substring(4)));
        } catch (IllegalArgumentException exception) {
            throw JsonMappingException.from(
                parser,
                "Invalid VND amount",
                exception
            );
        }
    }
}
~~~

Deserializer yêu cầu token JSON phải là string và có tiền tố <code>VND </code>. Sau đó nó chuyển phần số thành <code>BigDecimal</code> và tạo value object. JSON gửi số trực tiếp hoặc chuỗi có mã tiền tệ khác sẽ bị từ chối.

Trong code thực tế, nên quy định rõ mã tiền tệ có cố định hay thay đổi, số chữ số thập phân, dấu phân cách và cách làm tròn. Ví dụ này chỉ mô tả VND với hai chữ số thập phân để minh họa serializer/deserializer.

## 3. Bổ sung schema OpenAPI tương ứng với JSON thực tế

DTO dùng <code>Money</code> trong Java:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record InvoiceResponse(
    @Schema(
        implementation = String.class,
        type = "string",
        description = "Tổng tiền theo định dạng VND và hai chữ số thập phân",
        pattern = "^VND [0-9]+\\.[0-9]{2}$",
        example = "VND 125000.00"
    )
    Money total
) {}
~~~

Thuộc tính <code>implementation = String.class</code> và <code>type = "string"</code> hướng dẫn springdoc mô tả thuộc tính <code>total</code> dưới dạng string, phù hợp với output của <code>MoneySerializer</code>. <code>pattern</code> và <code>example</code> cho người tiêu thụ biết định dạng chuỗi được chấp nhận.

Schema tương ứng có thể gần như sau:

~~~yaml
InvoiceResponse:
  type: object
  properties:
    total:
      type: string
      pattern: "^VND [0-9]+\\.[0-9]{2}$"
      description: Tổng tiền theo định dạng VND và hai chữ số thập phân
      example: "VND 125000.00"
~~~

Đối với request, áp dụng cùng schema cho thuộc tính nhận <code>Money</code>:

~~~java
public record CreateInvoiceRequest(
    @Schema(
        implementation = String.class,
        type = "string",
        pattern = "^VND [0-9]+\\.[0-9]{2}$",
        example = "VND 125000.00"
    )
    Money total
) {}
~~~

Nhờ deserializer, request JSON chứa chuỗi <code>"VND 125000.00"</code> được chuyển thành <code>Money</code> trước khi controller xử lý. Nhờ serializer, response chứa cùng value object được ghi ra đúng chuỗi. Schema mô tả wire format chung cho cả hai chiều.

Lưu ý: annotation <code>@Schema</code> bổ sung metadata cho OpenAPI, không thay đổi Jackson. Ngược lại, <code>@JsonSerialize</code> và <code>@JsonDeserialize</code> thay đổi runtime JSON, nhưng không bảo đảm springdoc sẽ tự suy ra đúng schema của chuỗi tùy chỉnh. Hãy kiểm tra đầu ra thực tế tại <code>/v3/api-docs</code>.

## 4. Serializer/deserializer ở cấp thuộc tính

Không phải lúc nào cũng muốn thay đổi cách một kiểu Java được serialize trên toàn ứng dụng. Có thể gắn serializer và deserializer trên một thuộc tính:

~~~java
public record PaymentResponse(
    @JsonSerialize(using = MoneySerializer.class)
    @JsonDeserialize(using = MoneyDeserializer.class)
    @Schema(
        implementation = String.class,
        type = "string",
        example = "VND 125000.00"
    )
    Money amount
) {}
~~~

Trong ví dụ, các annotation chỉ tác động đến thuộc tính <code>amount</code> của DTO này. Một thuộc tính <code>Money</code> ở DTO khác vẫn dùng cấu hình mặc định hoặc serializer riêng của nó.

Đặt annotation ở cấp thuộc tính hữu ích khi cùng một kiểu Java cần nhiều wire format khác nhau. Ví dụ, một API cũ nhận chuỗi tiền tệ còn API mới nhận object gồm <code>amount</code> và <code>currency</code>. Mỗi thuộc tính cần serializer/deserializer và schema tương ứng riêng.

## 5. Đăng ký serializer/deserializer bằng Jackson Module

Ngoài annotation, có thể đăng ký serializer và deserializer thông qua <code>SimpleModule</code>. Cách này phù hợp khi không muốn gắn annotation Jackson vào domain model hoặc cần cấu hình tập trung:

~~~java
import com.fasterxml.jackson.databind.Module;
import com.fasterxml.jackson.databind.module.SimpleModule;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Module moneyModule() {
        SimpleModule module = new SimpleModule("money-wire-format");
        module.addSerializer(Money.class, new MoneySerializer());
        module.addDeserializer(Money.class, new MoneyDeserializer());
        return module;
    }
}
~~~

Spring Boot tự đăng ký các bean kiểu Jackson <code>Module</code> vào <code>ObjectMapper</code> mà framework quản lý. Cách này giúp HTTP message converter và các thành phần dùng mapper do Spring quản lý chia sẻ cấu hình.

Đây là phương án thay thế cho annotation cấp kiểu ở phần trước. Nếu chọn đăng ký bằng module, hãy bỏ <code>@JsonSerialize</code> và <code>@JsonDeserialize</code> trên <code>Money</code> trong ví dụ đó. Chọn một chiến lược nhất quán; nếu vừa gắn annotation ở cấp kiểu, vừa đăng ký module cho cùng kiểu, hãy xác minh serializer nào được chọn theo cấu hình Jackson thực tế. Tránh đăng ký nhiều serializer cạnh tranh cho một kiểu mà không kiểm tra thứ tự và kết quả.

Với Spring Boot, không nên tự tạo một <code>new ObjectMapper()</code> trong controller hoặc service để xử lý request riêng, vì mapper đó có thể không có module, naming strategy, date/time module hoặc cấu hình mà ứng dụng đã thiết lập.

## 6. Dùng @JsonComponent trong Spring Boot

Spring Boot hỗ trợ phát hiện các component Jackson được đánh dấu bằng <code>@JsonComponent</code>. Cách này hữu ích khi muốn Spring quản lý serializer/deserializer mà không khai báo từng module bean.

Ví dụ khung khai báo:

~~~java
import java.io.IOException;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer extends JsonSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers) throws IOException {
            generator.writeString("VND " + value.amount().toPlainString());
        }
    }
}
~~~

Có thể bổ sung nested deserializer tương ứng trong cùng component. Khi dùng cách này, bỏ cấu hình serializer/deserializer trùng lặp ở nơi khác hoặc xác minh rõ cách Spring Boot đăng ký chúng. Ví dụ khung trên chỉ minh họa cơ chế phát hiện component; cần giữ cùng quy tắc định dạng và xử lý lỗi như phần serializer/deserializer ở trên.

<code>@JsonComponent</code> cũng là một phương án thay thế cho annotation cấp kiểu hoặc module bean trong các ví dụ trước. Không đăng ký cả ba cách cho cùng một kiểu nếu không có chủ đích rõ ràng.

## 7. Khi nào dùng @JsonFormat, @JsonValue hoặc @JsonCreator?

Không phải mọi định dạng tùy chỉnh đều cần viết hai lớp serializer và deserializer. Jackson có các annotation gọn hơn cho những trường hợp đơn giản:

| Cơ chế | Trường hợp phù hợp |
|---|---|
| <code>@JsonFormat</code> | Định dạng ngày giờ, số hoặc enum theo khả năng hỗ trợ của kiểu |
| <code>@JsonValue</code> | Một object hoặc enum được biểu diễn bằng một giá trị đơn giản |
| <code>@JsonCreator</code> | Constructor/factory nhận giá trị JSON để tạo object |
| <code>@JsonSerialize</code> / <code>@JsonDeserialize</code> | Logic chuyển đổi tùy chỉnh hoặc cần kiểm soát token JSON |
| Jackson <code>Module</code> | Đăng ký logic chuyển đổi tập trung, dùng chung |

Ví dụ value object đơn giản có thể dùng <code>@JsonValue</code> để ghi ra một chuỗi:

~~~java
import com.fasterxml.jackson.annotation.JsonValue;

public record ProductCode(String value) {

    @JsonValue
    public String jsonValue() {
        return value;
    }
}
~~~

Để đọc chuỗi trở lại, có thể dùng constructor creator:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public record ProductCode(String value) {

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public ProductCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Product code is required");
        }
    }

    @JsonValue
    public String jsonValue() {
        return value;
    }
}
~~~

Với định dạng ngày giờ, hãy cân nhắc <code>@JsonFormat</code> và cấu hình Java Time module trước khi viết serializer riêng. Dù dùng cơ chế nào, schema OpenAPI vẫn cần mô tả đúng định dạng JSON cuối cùng.

## 8. Tùy chỉnh schema khi annotation chưa đủ

Trong các trường hợp schema phức tạp, có thể bổ sung hoặc sửa schema bằng OpenAPI model và customizer. Ví dụ, serializer tạo ra chuỗi nhưng nhiều DTO dùng chung một kiểu Java và cần schema nhất quán; nhóm có thể định nghĩa component schema dùng lại rồi tham chiếu ở các thuộc tính.

Một component schema cho định dạng tiền:

~~~yaml
components:
  schemas:
    VndAmount:
      type: string
      description: Số tiền VND có hai chữ số thập phân
      pattern: "^VND [0-9]+\\.[0-9]{2}$"
      example: "VND 125000.00"
~~~

Trong DTO, tham chiếu component:

~~~java
public record InvoiceResponse(
    @Schema(ref = "#/components/schemas/VndAmount")
    Money total
) {}
~~~

Nếu springdoc vẫn sinh schema không đúng, có thể dùng <code>OpenApiCustomizer</code> để sửa schema trong tài liệu đầu ra. Customizer chỉ tác động đặc tả OpenAPI; nó không thay đổi cách Jackson ghi hoặc đọc JSON. Luôn kiểm tra rằng cả hai phía được cập nhật cùng nhau.

Với nhiều nhóm tài liệu <code>GroupedOpenApi</code>, chọn phạm vi customizer phù hợp. Nếu schema tùy chỉnh cần xuất hiện trong mọi tài liệu nhóm, cân nhắc <code>GlobalOpenApiCustomizer</code>; nếu chỉ một nhóm cần, đăng ký customizer ở cấu hình nhóm đó.

## 9. Đồng bộ serialization, deserialization và validation

Ba lớp cần nhất quán:

1. **Jackson** xác định token JSON, tên field và định dạng dữ liệu thực tế.
2. **OpenAPI Schema** mô tả kiểu, format, pattern, ví dụ và giới hạn mà client cần tuân theo.
3. **Validation và nghiệp vụ** quyết định dữ liệu nào được chấp nhận khi request đến server.

Ví dụ với <code>Money</code>:

| Thành phần | Quy tắc |
|---|---|
| Serializer | Ghi object thành chuỗi như <code>"VND 125000.00"</code> |
| Deserializer | Chỉ đọc chuỗi có tiền tố <code>VND </code> và phần số hợp lệ |
| OpenAPI | <code>type: string</code>, pattern và example tương ứng |
| Validation/domain rule | Không chấp nhận số tiền âm, áp dụng scale hai chữ số |

Nếu deserializer từ chối chuỗi không đúng pattern, schema nên mô tả cùng pattern. Nếu constructor từ chối số âm, schema có thể mô tả pattern không âm, nhưng runtime vẫn phải kiểm tra vì pattern và validation có thể khác về chi tiết.

Đặc biệt, kiểm tra null riêng. Jackson thường xử lý JSON null thông qua cơ chế null value riêng, không gọi phương thức <code>deserialize</code> như khi nhận một token string. Nếu kiểu không được phép null, hãy bảo đảm Bean Validation hoặc logic constructor/service thực sự từ chối null; schema cũng cần thể hiện tính bắt buộc và khả năng null phù hợp.

## 10. Kiểm tra bằng ObjectMapper và endpoint thực tế

Không chỉ đọc annotation rồi kết luận output đã đúng. Hãy kiểm tra JSON do mapper của Spring tạo ra.

Ví dụ kiểm tra serializer/deserializer:

~~~java
import java.math.BigDecimal;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class MoneyJsonTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesMoneyAsString() throws Exception {
        String json = objectMapper.writeValueAsString(
            new Money(new BigDecimal("125000.00"))
        );

        assertThat(json).isEqualTo("\"VND 125000.00\"");
    }

    @Test
    void readsMoneyFromString() throws Exception {
        Money money = objectMapper.readValue(
            "\"VND 125000.00\"",
            Money.class
        );

        assertThat(money.amount())
            .isEqualByComparingTo("125000.00");
    }
}
~~~

Ví dụ dùng AssertJ trong Spring Boot test. Khi kiểm tra tích hợp, có thể gọi endpoint bằng MockMvc hoặc WebTestClient để xác nhận HTTP message converter dùng đúng mapper mà Spring quản lý.

Tiếp theo, tải đặc tả OpenAPI:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Xác minh:

- Thuộc tính <code>total</code> có <code>type: string</code>, không phải object.
- Pattern và example khớp với serializer/deserializer.
- Schema của request và response đều đúng.
- Không còn component <code>Money</code> mô tả một object chứa <code>amount</code> nếu wire format thực tế là string.
- Swagger UI hiển thị ví dụ request đúng định dạng.

Thử thêm dữ liệu sai như chuỗi không có tiền tố <code>VND </code>, giá trị không phải string, số âm và chuỗi không phải số. Xác nhận server trả lỗi phù hợp theo quy ước API.

## 11. Lỗi thường gặp

**Serializer đổi object thành string nhưng schema vẫn là object.** Bổ sung <code>@Schema(implementation = String.class)</code>, <code>type = "string"</code> hoặc component schema tương ứng; sau đó kiểm tra JSON OpenAPI.

**Chỉ viết serializer mà quên deserializer.** Response có thể đúng nhưng request không thể đọc định dạng đó. Nếu API nhận kiểu này từ client, cần deserializer hoặc creator tương ứng.

**Chỉ viết deserializer mà schema không nói rõ định dạng.** Client không biết phải gửi string, object hay token nào. Bổ sung type, pattern, format và ví dụ.

**Dùng ObjectMapper tự tạo trong service.** Mapper riêng có thể không có module và cấu hình của Spring Boot. Ưu tiên mapper do Spring quản lý hoặc đăng ký module qua bean.

**Đăng ký nhiều serializer cạnh tranh.** Annotation cấp kiểu, annotation cấp field và module có thể cùng tham gia cấu hình. Kiểm tra mapper thực tế và chỉ giữ chiến lược rõ ràng.

**Dựa vào @Schema để thay đổi JSON runtime.** Annotation OpenAPI chỉ mô tả tài liệu; phải dùng Jackson hoặc logic ứng dụng để thay đổi serialization.

**Dựa vào serializer để tự cập nhật OpenAPI.** springdoc không thực thi serializer với mọi payload để suy ra schema. Cần bổ sung schema tường minh khi wire format khác với kiểu Java.

**Không kiểm tra null và dữ liệu sai định dạng.** Serializer/deserializer tùy chỉnh phải có hành vi rõ cho token không hợp lệ, null, giá trị vượt miền và lỗi parse.

## 12. Danh sách rà soát trước khi công bố

- [ ] Đã xác định JSON wire format trước và sau serializer/deserializer.
- [ ] Serializer tạo đúng kiểu JSON: string, number, object, array hoặc null.
- [ ] Deserializer đọc đúng token và từ chối định dạng không hợp lệ.
- [ ] Đã chọn phạm vi annotation kiểu, thuộc tính hoặc Jackson Module phù hợp.
- [ ] Spring Boot dùng đúng ObjectMapper và module đã đăng ký.
- [ ] Schema OpenAPI mô tả kiểu JSON thực tế thay vì chỉ phản ánh kiểu Java.
- [ ] Pattern, format, example và giới hạn khớp với quy tắc runtime.
- [ ] Request và response được kiểm tra riêng.
- [ ] Đã kiểm tra <code>/v3/api-docs</code>, Swagger UI và HTTP endpoint thực tế.

## Tài liệu tham khảo

- [Jackson – Custom Serializers and Deserializers](https://github.com/FasterXML/jackson-databind): API serializer/deserializer và data binding.
- [Jackson Annotations – JsonSerialize](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/annotation/JsonSerialize.html): chọn serializer tùy chỉnh.
- [Jackson Annotations – JsonDeserialize](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/annotation/JsonDeserialize.html): chọn deserializer tùy chỉnh.
- [Spring Boot – Customize the Jackson ObjectMapper](https://docs.spring.io/spring-boot/reference/features/json.html): cấu hình Jackson, module bean và <code>@JsonComponent</code>.
- [Swagger Core – Schema annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): bổ sung type, implementation, pattern và example cho schema.
- [springdoc-openapi](https://springdoc.org/): sinh và tùy chỉnh OpenAPI từ ứng dụng Spring Boot.
