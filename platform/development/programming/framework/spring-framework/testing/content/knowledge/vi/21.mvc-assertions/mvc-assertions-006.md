# DTO sau tuần tự hóa khác với đối tượng trong bộ nhớ

## 1. Kết quả MVC là dữ liệu HTTP sau khi tuần tự hóa

Khi controller trả về một DTO, Spring MVC không gửi nguyên đối tượng Java qua HTTP. Với một REST endpoint, luồng xử lý thường diễn ra như sau:

~~~text
Controller
   |
   | trả về DTO Java
   v
HandlerMethodReturnValueHandler
   |
   | chọn HttpMessageConverter theo kiểu dữ liệu và media type
   v
Jackson HttpMessageConverter
   |
   | ObjectMapper tuần tự hóa DTO
   v
JSON bytes trong HTTP response
   |
   v
MockHttpServletResponse / HTTP client
~~~

Ví dụ, controller có thể trả về một đối tượng Java chứa trường **note = null**. Jackson có thể bỏ hẳn trường đó khỏi JSON nếu cấu hình **@JsonInclude(NON_NULL)**. Tên property cũng có thể được đổi bằng **@JsonProperty** hoặc naming strategy. Một **Instant** trong Java trở thành chuỗi ngày giờ; enum thường trở thành chuỗi; collection được chuyển thành mảng JSON.

Do đó, có hai kết quả khác nhau cần phân biệt:

- **Đối tượng trong bộ nhớ:** DTO Java mà controller hoặc service đang giữ, với kiểu dữ liệu, giá trị và trạng thái của Java.
- **Biểu diễn trên HTTP:** JSON (hoặc định dạng khác) được **HttpMessageConverter** tạo ra và thực sự gửi về client.

Khi kiểm thử kết quả MVC, thứ client nhận được là hợp đồng cần xác nhận. Một assertion trên DTO trong bộ nhớ chưa chứng minh JSON response có đúng tên field, kiểu dữ liệu, định dạng hoặc nội dung hay không.

## 2. Những gì có thể thay đổi khi Jackson tuần tự hóa DTO

### Tên property

DTO có property **orderId**, nhưng API có thể công bố tên **order_id**:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderResponse(
        @JsonProperty("order_id") Long orderId,
        String status
) {
}
~~~

JSON có dạng:

~~~json
{
  "order_id": 42,
  "status": "PAID"
}
~~~

Kiểm thử **$.orderId** sẽ thất bại dù DTO có accessor **orderId()** và giá trị trong bộ nhớ là **42**. Client phải đọc tên property đã được công bố trong JSON.

Tên property còn có thể chịu ảnh hưởng của **PropertyNamingStrategy** hoặc **PropertyNamingStrategies** được cấu hình toàn cục, ví dụ chuyển camelCase thành snake_case.

### Property bị bỏ qua hoặc bị ẩn

**@JsonInclude** quyết định khi nào property được đưa vào JSON:

~~~java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ProfileResponse(
        Long id,
        String displayName,
        String phone
) {
}
~~~

Nếu **phone** là **null**, JSON có thể chỉ chứa **id** và **displayName**. Đối tượng Java vẫn có accessor **phone()** và trả về **null**, nhưng response không có key **phone**.

Cần phân biệt ba trạng thái:

| JSON | Ý nghĩa |
|---|---|
| **{}** | Không có property |
| **{"phone": null}** | Có property với giá trị null |
| **{"phone": ""}** | Có property với chuỗi rỗng |

Ba trạng thái này có thể mang ý nghĩa khác nhau đối với client. **jsonPath("$.phone").doesNotHaveJsonPath()** kiểm tra key không tồn tại; **jsonPath("$.phone").hasJsonPath()** kết hợp **value(nullValue())** kiểm tra key tồn tại với giá trị null. Khi cần phân biệt chính xác, có thể đọc response thành **JsonNode** và dùng **has()** / **hasNonNull()**.

Ngoài **@JsonInclude**, **@JsonIgnore**, **@JsonView**, filter và visibility configuration cũng có thể làm property biến mất khỏi JSON.

### Kiểu dữ liệu Java trở thành kiểu JSON

JSON chỉ có các nhóm giá trị như object, array, string, number, boolean và null. Nó không có kiểu **Instant**, **BigDecimal**, enum hay **UUID** như Java.

| Kiểu trong DTO | Biểu diễn JSON thường gặp |
|---|---|
| **String** | JSON string |
| **Long**, **Integer** | JSON number |
| **BigDecimal** | JSON number |
| **Boolean** | JSON boolean |
| **Instant**, **LocalDate** | JSON string theo cấu hình serializer |
| **enum** | Thường là tên enum dưới dạng JSON string |
| **List<T>** | JSON array |
| **Map<K,V>** | JSON object nếu key có thể biểu diễn phù hợp |
| **byte[]** | Thường được mã hóa Base64 thành JSON string |

Ví dụ, **Instant** không còn là một object Java có phương thức **toString()** trong response; nó trở thành một chuỗi theo serializer và cấu hình thời gian. **@JsonFormat**, Java Time module và timezone cấu hình có thể ảnh hưởng định dạng đó.

Không nên mặc định mọi enum luôn được ghi thành tên. Cấu hình Jackson hoặc annotation có thể thay đổi cách biểu diễn enum, chẳng hạn ghi theo số thứ tự. Hãy kiểm tra định dạng API thực tế.

### Giá trị được biến đổi hoặc định dạng

Custom serializer, getter, mix-in, module Jackson hoặc **ResponseBodyAdvice** có thể làm giá trị trên response khác với trường Java ban đầu. Một getter cũng có thể cung cấp giá trị tính toán mà Jackson xem là property.

Ví dụ:

~~~java
public class PriceResponse {

    private final BigDecimal amount;

    public PriceResponse(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getFormattedAmount() {
        return amount.toPlainString() + " VND";
    }
}
~~~

Jackson có thể đưa cả **amount** và **formattedAmount** vào JSON vì chúng là getter có thể nhận diện như property, trừ khi có cấu hình hoặc annotation loại trừ. Việc DTO có field nào không đồng nghĩa response chỉ có đúng các field đó.

### Thứ tự và cách trình bày JSON

JSON object là tập hợp các member có tên; client thường không nên phụ thuộc vào thứ tự property hoặc khoảng trắng. Jackson có thể ghi property theo thứ tự khác nhau tùy cấu hình, annotation hoặc thay đổi phiên bản.

Hai response sau có cùng cấu trúc dữ liệu:

~~~json
{"id":42,"status":"PAID"}
~~~

~~~json
{
  "status": "PAID",
  "id": 42
}
~~~

Vì vậy, assertion trên JSON nên so sánh cấu trúc và giá trị. Chỉ kiểm tra chuỗi JSON nguyên văn khi định dạng chữ, thứ tự hoặc khoảng trắng thực sự là một phần hợp đồng đã được yêu cầu.

## 3. Ví dụ DTO và response của Spring MVC

Giả sử API trả thông tin đơn hàng. DTO sử dụng tên property **order_id**, bỏ qua **note** khi null và chứa thời điểm tạo đơn.

### DTO

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record OrderResponse(
        @JsonProperty("order_id") Long orderId,
        BigDecimal total,
        OrderStatus status,
        String note,
        Instant createdAt
) {
}
~~~

### Enum

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

### Controller

~~~java
import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class OrderController {

    @GetMapping(
            value = "/orders/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderResponse getOrder(@PathVariable Long id) {
        return new OrderResponse(
                id,
                new BigDecimal("1250.00"),
                OrderStatus.PAID,
                null,
                Instant.parse("2026-11-13T02:00:00Z")
        );
    }
}
~~~

Đối tượng Java mà controller tạo ra có năm component. Component **note** có giá trị **null**. Với cấu hình Jackson nhận annotation trên DTO và Java Time module phù hợp, response JSON có thể là:

~~~json
{
  "order_id": 42,
  "total": 1250.00,
  "status": "PAID",
  "createdAt": "2026-11-13T02:00:00Z"
}
~~~

Những điểm khác biệt có thể quan sát ngay:

- **orderId** trong DTO được công bố thành **order_id**.
- **note** tồn tại như một component của record nhưng không xuất hiện trong JSON.
- **total** được biểu diễn thành JSON number, không phải một đối tượng **BigDecimal**.
- **status** được biểu diễn thành JSON string.
- **createdAt** được biểu diễn thành chuỗi ISO-8601 theo cấu hình Java Time.

Ví dụ dùng thời điểm cố định để kết quả kiểm thử có tính xác định. Không nên dùng **Instant.now()** trong assertion so sánh một chuỗi thời gian cố định.

## 4. Xác nhận JSON thực tế bằng MockMvc

Với Spring Boot, **@WebMvcTest** có thể dựng MVC slice cho controller và cấu hình message converter. Kiểm thử cần xác nhận status, content type và các property trong response body.

~~~java
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void shouldReturnTheSerializedOrderDto() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/orders/{id}", 42L)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.order_id").value(42))
                .andExpect(jsonPath("$.total").value(1250.00))
                .andExpect(jsonPath("$.status").value("PAID"))
                .andExpect(jsonPath("$.createdAt")
                        .value("2026-11-13T02:00:00Z"))
                .andExpect(jsonPath("$.note").doesNotHaveJsonPath())
                .andReturn();

        String responseBody = result.getResponse()
                .getContentAsString(StandardCharsets.UTF_8);

        JsonNode json = objectMapper.readTree(responseBody);

        assertThat(json.has("order_id")).isTrue();
        assertThat(json.has("orderId")).isFalse();
        assertThat(json.has("note")).isFalse();
    }
}
~~~

Các assertion trong test này kiểm tra đúng dữ liệu được gửi về client:

- **status().isOk()** xác nhận HTTP status.
- **contentTypeCompatibleWith(...)** xác nhận response có media type JSON tương thích.
- **jsonPath(...)** xác nhận tên property và giá trị sau tuần tự hóa.
- **doesNotHaveJsonPath()** xác nhận **note** đã bị bỏ khỏi JSON.
- **MvcResult** cho phép lấy nguyên response body để kiểm tra sâu hơn bằng **JsonNode**.

Nếu chỉ kiểm tra đối tượng **OrderResponse** trong controller hoặc service, test sẽ không phát hiện trường hợp Jackson ghi **order_id** thay vì **orderId**, bỏ **note**, hoặc format ngày giờ khác dự kiến.

**ObjectMapper** được inject trong test giúp đọc response JSON. Trong ứng dụng có cấu hình converter tùy chỉnh, cần bảo đảm mapper dùng để đọc/so sánh và mapper được MVC converter sử dụng có cấu hình phù hợp. Việc inject **ObjectMapper** mặc định không tự chứng minh mọi converter tùy chỉnh đều dùng chính instance đó.

## 5. Kiểm tra JSON theo cấu trúc thay vì so sánh chuỗi

### Dùng jsonPath cho các property quan trọng

**jsonPath** phù hợp khi chỉ cần xác nhận một vài phần của API contract. Có thể kiểm tra:

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.order_id").value(42))
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.items.length()").value(2));
~~~

Cú pháp và assertion cần phù hợp với kiểu JSON thực tế. Một số ví dụ:

- **isArray()** kiểm tra property là mảng.
- **isMap()** kiểm tra property là object JSON.
- **isEmpty()** kiểm tra giá trị rỗng theo matcher tương ứng.
- **doesNotHaveJsonPath()** kiểm tra property không tồn tại; **hasJsonPath()** xác nhận property tồn tại kể cả khi giá trị là null.
- **value(...)** kiểm tra giá trị của property.

Không dùng **value("1250.00")** nếu response chứa JSON number. Chuỗi **"1250.00"** và số **1250.00** là hai kiểu JSON khác nhau.

### Dùng JsonNode khi cần phân biệt null và không tồn tại

**JsonNode** hữu ích khi response có cấu trúc lồng nhau hoặc cần kiểm tra chính xác sự hiện diện của key:

~~~java
JsonNode root = objectMapper.readTree(responseBody);

assertThat(root.has("note")).isFalse();
assertThat(root.has("order_id")).isTrue();
assertThat(root.path("order_id").asLong()).isEqualTo(42L);
~~~

Nếu muốn kiểm tra key tồn tại và có giá trị null:

~~~java
JsonNode root = objectMapper.readTree(responseBody);

assertThat(root.has("note")).isTrue();
assertThat(root.get("note").isNull()).isTrue();
~~~

**has("note")** trả về **true** khi key tồn tại, kể cả khi giá trị JSON là null. **hasNonNull("note")** chỉ trả về **true** khi key tồn tại và khác null. **path("missing")** trả về node missing thay vì **null** Java, nên cần chọn API kiểm tra đúng mục tiêu.

### Dùng content().json khi cần so sánh một JSON document

Có thể kiểm tra cả cấu trúc response bằng JSON assertion:

~~~java
mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk())
        .andExpect(content().json("""
                {
                  "order_id": 42,
                  "total": 1250.00,
                  "status": "PAID",
                  "createdAt": "2026-11-13T02:00:00Z"
                }
                """));
~~~

JSON comparison thường không yêu cầu thứ tự property trong object. Đây là cách gọn khi muốn xác nhận nhiều property cùng lúc. Tuy nhiên, nếu response lớn, **jsonPath** cho các field quan trọng hoặc **JsonNode** cho cấu trúc cần kiểm tra thường dễ đọc và dễ xác định nguyên nhân lỗi hơn.

Không nên chuyển toàn bộ response thành chuỗi rồi dùng **contains()** để xác nhận JSON. Chuỗi con có thể xuất hiện ở vị trí sai, trong property khác hoặc trong một giá trị string; nó không chứng minh cấu trúc JSON đúng.

## 6. Khi cần kiểm tra giá trị số chính xác

**BigDecimal** được Jackson ghi thành JSON number. Vấn đề có thể xuất hiện khi test hoặc client parse JSON number sang kiểu floating-point như **double**, vì **double** không biểu diễn chính xác mọi số thập phân.

Nếu API có yêu cầu về giá trị thập phân chính xác, có thể đọc JSON tree với cấu hình dùng **BigDecimal** cho số thập phân:

~~~java
import java.math.BigDecimal;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;

JsonNode root = objectMapper.reader()
        .with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
        .readTree(responseBody);

BigDecimal total = root.get("total").decimalValue();

assertThat(total).isEqualByComparingTo(new BigDecimal("1250.00"));
~~~

**isEqualByComparingTo** so sánh giá trị số của **BigDecimal**, không yêu cầu cùng scale. Nếu scale cũng là yêu cầu của hợp đồng, cần kiểm tra scale hoặc biểu diễn JSON cụ thể theo mục tiêu đó.

Nếu API chủ ý công bố số tiền dưới dạng JSON string, DTO hoặc serializer cần thể hiện rõ hợp đồng đó, và test phải xác nhận string. Không nên để test vô tình chấp nhận cả number lẫn string khi client cần một kiểu duy nhất.

## 7. Kiểm thử đúng cấu hình HttpMessageConverter

Kết quả tuần tự hóa phụ thuộc converter thực sự xử lý response. Vì vậy, cách dựng MockMvc có ảnh hưởng đến độ tin cậy của test.

### Dùng WebApplicationContext

Khi cần xác nhận cấu hình MVC của ứng dụng, có thể dựng MockMvc từ **WebApplicationContext**:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitWebConfig(classes = WebConfig.class)
class OrderMvcTest {

    @Autowired
    private WebApplicationContext context;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(context)
                .build();
    }
}
~~~

Cách này dùng các thành phần MVC được đăng ký trong context, bao gồm các **HttpMessageConverter** đã cấu hình. Trong Spring Boot, **@WebMvcTest** hoặc **@SpringBootTest** kết hợp **@AutoConfigureMockMvc** là các lựa chọn phổ biến tùy phạm vi test.

### Cẩn thận với standaloneSetup

**MockMvcBuilders.standaloneSetup(controller)** thuận tiện cho test controller nhỏ, nhưng nó tự thiết lập hạ tầng MVC và converter mặc định. Nếu production dùng một **ObjectMapper** tùy chỉnh, serializer riêng hoặc converter được đăng ký bổ sung, standalone test có thể không chạy cùng cấu hình đó.

Khi kết quả tuần tự hóa là điều cần xác nhận, hãy dùng **webAppContextSetup** hoặc cấu hình converter tường minh cho standalone MockMvc. Nếu không, test có thể pass với cấu hình test nhưng response trong ứng dụng thật lại khác.

### Cấu hình Java Time

Nếu DTO có **Instant**, **LocalDate** hoặc **LocalDateTime**, cần có Java Time module tương thích với phiên bản Jackson đang dùng và cấu hình format phù hợp. Spring Boot thường tự đăng ký module có trên classpath. Trong ứng dụng Spring MVC cấu hình thủ công, cần đăng ký module đó với **ObjectMapper** được dùng bởi **MappingJackson2HttpMessageConverter**.

Đừng chỉ kiểm tra một chuỗi ngày giờ do **ObjectMapper** tự tạo trong unit test nếu controller production sử dụng converter khác. Hãy kiểm tra response MockMvc chạy qua MVC configuration tương ứng.

## 8. Request DTO cũng có thể khác sau khi giải tuần tự hóa

Chiều request có luồng ngược lại:

~~~text
HTTP JSON request
   |
   v
HttpMessageConverter
   |
   | Jackson giải tuần tự hóa
   v
DTO Java trong controller
~~~

JSON đầu vào được chuyển thành object Java. Các khác biệt có thể xảy ra khi:

- Property JSON thiếu và constructor hoặc field Java dùng giá trị mặc định.
- Property JSON là **null**, trong khi primitive Java không thể giữ null.
- **@JsonProperty** ánh xạ tên JSON sang tên component hoặc field khác.
- **@JsonAlias** cho phép nhiều tên đầu vào.
- Unknown property bị từ chối hoặc bị bỏ qua theo cấu hình.
- Custom deserializer chuyển đổi chuỗi thành kiểu Java hoặc chuẩn hóa giá trị.
- **@JsonCreator** quyết định cách tạo DTO.

Vì vậy, kiểm thử request binding nên gửi JSON thực tế qua MockMvc và xác nhận controller nhận được kết quả đúng. Việc tạo trực tiếp **new RequestDto(...)** chỉ kiểm tra logic Java sau binding, không kiểm tra Jackson có ánh xạ request JSON đúng hay không.

Ví dụ:

~~~java
mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "order_id": 42,
                          "status": "PAID"
                        }
                        """))
        .andExpect(status().isCreated());
~~~

Nếu cần xác nhận giá trị controller nhận được, có thể mock service mà controller gọi và dùng **ArgumentCaptor** để kiểm tra DTO được truyền vào. Như vậy test xác nhận cả JSON request được bind và giá trị sau binding.

## 9. Những lỗi kiểm thử thường gặp

| Cách kiểm thử hoặc hiện tượng | Vì sao chưa đủ hoặc sai | Cách xử lý |
|---|---|---|
| So sánh DTO trong bộ nhớ rồi kết luận response đúng | Chưa đi qua **HttpMessageConverter** | Gửi request MockMvc và kiểm tra response body |
| Dùng tên field Java trong JSONPath | API có thể đổi tên bằng **@JsonProperty** hoặc naming strategy | Dùng đúng tên property trên JSON |
| Mong đợi null nhưng property bị bỏ qua | **@JsonInclude(NON_NULL)** hoặc filter loại property | Kiểm tra **hasJsonPath()** / **doesNotHaveJsonPath()** hoặc cấu trúc bằng **JsonNode** |
| Mong đợi chuỗi nhưng JSON trả số | JSON number và JSON string là hai kiểu khác nhau | Assertion theo kiểu dữ liệu thực tế và hợp đồng API |
| So sánh toàn bộ JSON dưới dạng chuỗi | Thứ tự property và khoảng trắng có thể khác | Dùng **jsonPath**, **JsonNode** hoặc **content().json** |
| Dùng standaloneSetup nhưng bỏ qua converter tùy chỉnh | Cấu hình test không giống cấu hình ứng dụng | Dùng **webAppContextSetup** hoặc đăng ký converter chính xác |
| Kiểm tra ngày giờ bằng now() | Giá trị thay đổi theo thời điểm chạy test | Dùng thời điểm cố định và xác nhận format/timezone |
| Deserialize response về cùng DTO rồi chỉ so sánh object | Bước đọc lại có thể che giấu field bị bỏ qua hoặc giá trị mặc định | Kiểm tra JSON tree hoặc property trực tiếp trên response |
| Chỉ kiểm tra HTTP 200 | Status đúng không chứng minh body đúng | Kiểm tra status, content type và các property quan trọng |

Một lỗi dễ gặp khác là tạo **new ObjectMapper()** trong test rồi dùng nó để kết luận MVC response đúng. Mapper mới không tự động có các module, naming strategy, serializer, mix-in hoặc cấu hình mà ứng dụng đã đăng ký. Dùng mapper được cấu hình trong context để đọc response, và quan trọng hơn, để MockMvc đi qua đúng converter mà ứng dụng sử dụng.

## 10. Chọn assertion theo điều cần xác nhận

| Điều cần xác nhận | Assertion phù hợp |
|---|---|
| HTTP status và content type | **status()** và **content()** |
| Một property hoặc giá trị lồng nhau | **jsonPath()** |
| Key có tồn tại, null hay không | **JsonNode.has()**, **hasNonNull()**, **isNull()** |
| Nhiều property trong một JSON document | **content().json(...)** |
| Số thập phân cần độ chính xác | Đọc JSON với **USE_BIG_DECIMAL_FOR_FLOATS** rồi so sánh **BigDecimal** |
| Định dạng chuỗi ngày giờ công khai | **jsonPath()** với chuỗi thời gian cố định |
| Request JSON được ánh xạ thành DTO đúng | Gửi JSON qua MockMvc và kiểm tra argument truyền tới service |

Một bài kiểm thử MVC đáng tin cậy xác nhận dữ liệu ở đúng ranh giới HTTP. DTO trong bộ nhớ là đầu vào của quá trình tuần tự hóa; JSON response là kết quả client nhận được. Khi test kiểm tra đúng biểu diễn JSON, nó mới phát hiện được các thay đổi do annotation, cấu hình Jackson và **HttpMessageConverter** gây ra.

