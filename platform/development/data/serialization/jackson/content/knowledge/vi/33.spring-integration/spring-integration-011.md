# Kiểm thử HTTP để xác minh cấu hình thực tế đã được áp dụng

Một ObjectMapper được cấu hình đúng trong unit test chưa chứng minh rằng ứng dụng Spring đang dùng chính cấu hình đó khi nhận và trả HTTP. Trong Spring MVC, JSON request/response thường đi qua HttpMessageConverter được chọn bởi DispatcherServlet và handler adapter. Trong Spring WebFlux, JSON đi qua encoder/decoder của codec stack. Bean ObjectMapper được inject trong service có thể khác mapper được converter hoặc codec sử dụng.

Vì vậy, muốn xác minh cấu hình Jackson thực tế, hãy gửi request HTTP qua Spring test infrastructure và kiểm tra cả JSON response lẫn kết quả binding từ JSON request. Test cần đi qua controller, content negotiation và converter/codec của ứng dụng. Khi có thể, dùng full application context để giữ nguyên cấu hình production.

Bài này dùng Spring Boot, Spring MVC và Jackson 2 làm ví dụ chính; phần cuối có hướng tương ứng cho WebFlux. Tên lớp hoặc package có thể thay đổi khi project chuyển sang major version khác của Spring/Jackson, nên hãy dùng API đúng với version đang có trong dependency tree.

## 1. Vì sao test ObjectMapper riêng chưa đủ?

Ví dụ unit test sau chỉ kiểm tra mapper được tạo trực tiếp:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .build();

String json = mapper.writeValueAsString(value);
~~~

Nó không chứng minh rằng:

- Spring Boot đã nạp cấu hình từ application.yml hoặc application.properties.
- Jackson customizer hoặc module bean đã được đăng ký.
- MVC converter đang dùng mapper mong đợi.
- Endpoint thực sự chọn converter JSON cho Content-Type và Accept.
- Request body được deserialize bằng cùng quy tắc mà unit test vừa kiểm tra.
- Một converter khác có thứ tự ưu tiên cao hơn không xử lý request trước.
- Profile hoặc test configuration không ghi đè cấu hình production.

HTTP integration test kiểm tra toàn bộ đường đi quan trọng hơn:

~~~text
HTTP request JSON
       |
       v
DispatcherServlet / HandlerAdapter
       |
       v
HttpMessageConverter được chọn
       |
       v
Jackson ObjectMapper
       |
       v
Controller argument
       |
       v
Application logic
       |
       v
Controller return value
       |
       v
HttpMessageConverter
       |
       v
HTTP response JSON
~~~

Nếu dùng WebFlux, đường đi tương ứng sử dụng WebHandler và codec reader/writer thay cho MVC HttpMessageConverter.

## 2. Cấu hình Spring Boot cần kiểm tra

Ví dụ ứng dụng cần snake_case, hỗ trợ Java time và bỏ qua property null khi serialize.

Có thể cấu hình bằng application.yml:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: non_null
    serialization:
      write-dates-as-timestamps: false
    deserialization:
      adjust-dates-to-context-time-zone: false
~~~

Hoặc dùng Java configuration:

~~~java
@Configuration
public class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.propertyNamingStrategy(
                    PropertyNamingStrategies.SNAKE_CASE
            );
            builder.serializationInclusion(JsonInclude.Include.NON_NULL);
            builder.featuresToDisable(
                    SerializationFeature.WRITE_DATES_AS_TIMESTAMPS,
                    DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE
            );
        };
    }
}
~~~

Spring Boot thường tự đăng ký các Jackson Module bean và các module được nhận diện trên classpath theo cơ chế auto-configuration. Nếu ứng dụng tự khai báo ObjectMapper hoặc converter riêng, hành vi có thể thay đổi. Hãy xác định cấu hình thực tế của project trước khi viết expected JSON.

Không nên vừa cấu hình cùng một feature trong YAML, customizer, ObjectMapper bean và converter bean nếu không có lý do rõ ràng. Nhiều nguồn cấu hình khiến test khó xác định nguồn nào quyết định kết quả cuối cùng.

## 3. Tạo DTO có các thuộc tính dễ nhận diện

Dùng DTO có tên Java khác tên JSON để kiểm tra naming strategy. Thêm một property null và một giá trị ngày giờ để kiểm tra nhiều quy tắc trong cùng HTTP contract.

~~~java
public record CustomerResponse(
        Long customerId,
        String displayName,
        String nickname,
        Instant createdAt
) {}
~~~

Request DTO:

~~~java
public record CreateCustomerRequest(
        String displayName,
        Instant createdAt
) {}
~~~

Với snake_case, các property dự kiến là customer_id, display_name và created_at. Nếu NON_NULL đang có hiệu lực, nickname có giá trị null sẽ không xuất hiện trong response.

Một controller ví dụ:

~~~java
@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public CustomerResponse get(@PathVariable Long id) {
        return service.find(id);
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public CustomerResponse create(
            @RequestBody CreateCustomerRequest request
    ) {
        return service.create(request);
    }
}
~~~

Service có thể là service thật trong integration test hoặc mock trong MVC slice test. Nếu mục tiêu là kiểm tra Jackson HTTP binding, mock service là đủ; nếu mục tiêu còn bao gồm persistence hoặc business flow, dùng integration context và dependency phù hợp.

## 4. Dùng @SpringBootTest và MockMvc để kiểm tra MVC converter

Với Spring MVC, một lựa chọn mạnh là full application context cùng MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerHttpJacksonTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    CustomerService customerService;

    @Test
    void serializesResponseUsingConfiguredJacksonRules() throws Exception {
        Instant createdAt =
                Instant.parse("2026-11-12T10:30:00.123456789Z");

        given(customerService.find(42L)).willReturn(
                new CustomerResponse(
                        42L,
                        "Nguyen An",
                        null,
                        createdAt
                )
        );

        mockMvc.perform(get("/api/customers/42")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.customer_id").value(42))
                .andExpect(jsonPath("$.display_name").value("Nguyen An"))
                .andExpect(jsonPath("$.nickname").doesNotExist())
                .andExpect(jsonPath("$.created_at")
                        .value("2026-11-12T10:30:00.123456789Z"));
    }
}
~~~

Test này đi qua Spring MVC request handling và response conversion. Nó xác minh JSON mà HTTP client thực sự nhận được, thay vì chỉ serialize DTO bằng một mapper được tạo riêng trong test.

Các static import thường dùng:

~~~java
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
~~~

Nếu Spring Boot version đang dùng không còn cung cấp annotation mock bean cũ, dùng cơ chế mock bean tương ứng của version đó hoặc khai báo test configuration thay thế service bean.

## 5. Kiểm tra deserialize từ HTTP request

Chỉ test GET response là chưa đủ. Cấu hình naming strategy, custom deserializer, enum handling hoặc date format cũng ảnh hưởng chiều request binding.

~~~java
@Test
void deserializesRequestBodyUsingConfiguredJacksonRules() throws Exception {
    Instant createdAt =
            Instant.parse("2026-11-12T10:30:00.123456789Z");

    given(customerService.create(any(CreateCustomerRequest.class)))
            .willAnswer(invocation -> {
                CreateCustomerRequest request = invocation.getArgument(0);
                return new CustomerResponse(
                        42L,
                        request.displayName(),
                        null,
                        request.createdAt()
                );
            });

    String requestJson = """
            {
              "display_name": "Nguyen An",
              "created_at": "2026-11-12T10:30:00.123456789Z"
            }
            """;

    mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestJson))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.display_name").value("Nguyen An"))
            .andExpect(jsonPath("$.created_at")
                    .value("2026-11-12T10:30:00.123456789Z"));

    ArgumentCaptor<CreateCustomerRequest> captor =
            ArgumentCaptor.forClass(CreateCustomerRequest.class);

    then(customerService).should().create(captor.capture());

    assertEquals("Nguyen An", captor.getValue().displayName());
    assertEquals(createdAt, captor.getValue().createdAt());
}
~~~

Điểm quan trọng là request JSON dùng display_name và created_at, không phải tên Java camelCase. Nếu Jackson naming strategy không được áp dụng trong converter, Spring có thể trả HTTP 400 do không bind được property hoặc service nhận giá trị null.

Static import bổ sung:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.verify;
import org.mockito.ArgumentCaptor;
~~~

Với record hoặc DTO có creator bắt buộc, missing field có thể làm binding thất bại tùy feature và kiểu tham số. Hãy thiết kế test theo contract cụ thể.

## 6. Test JSON contract thay vì phụ thuộc thứ tự property

JSON object về mặt contract không yêu cầu thứ tự property. Thông thường nên dùng jsonPath để kiểm tra field, value, null/missing và type.

Ví dụ:

~~~java
.andExpect(jsonPath("$.customer_id").value(42))
.andExpect(jsonPath("$.nickname").doesNotExist())
~~~

Chỉ so sánh toàn bộ JSON string khi thứ tự hoặc lexical representation thực sự là một phần contract, ví dụ chữ ký số hoặc một consumer không chuẩn phụ thuộc thứ tự. Trong trường hợp thông thường, so sánh cây JSON:

~~~java
MvcResult result = mockMvc.perform(get("/api/customers/42")
        .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andReturn();

JsonNode actual = objectMapper.readTree(
        result.getResponse().getContentAsString()
);

assertEquals(42L, actual.path("customer_id").asLong());
assertEquals("Nguyen An", actual.path("display_name").asText());
assertFalse(actual.has("nickname"));
~~~

Nếu muốn phân biệt missing với explicit null, hãy assert cả hai trạng thái:

~~~java
assertFalse(actual.has("nickname")); // missing

// Nếu contract yêu cầu property hiện diện với null:
// assertTrue(actual.has("nickname"));
// assertTrue(actual.get("nickname").isNull());
~~~

ObjectMapper inject vào test ở đây chỉ được dùng để parse response cho assertion. Chính response body đã được tạo bởi HTTP converter.

## 7. Xác minh mapper bean và MVC converter

Có thể inject mapper và handler adapter để quan sát cấu hình Spring đang tạo:

~~~java
@Autowired
ObjectMapper objectMapper;

@Autowired
RequestMappingHandlerAdapter handlerAdapter;

@Test
void mvcHasJacksonJsonConverter() {
    List<MappingJackson2HttpMessageConverter> converters =
            handlerAdapter.getMessageConverters().stream()
                    .filter(MappingJackson2HttpMessageConverter.class::isInstance)
                    .map(MappingJackson2HttpMessageConverter.class::cast)
                    .toList();

    assertFalse(converters.isEmpty());
}
~~~

Có thể kiểm tra converter hỗ trợ application/json:

~~~java
@Test
void jacksonConverterSupportsApplicationJson() {
    List<MappingJackson2HttpMessageConverter> converters =
            handlerAdapter.getMessageConverters().stream()
                    .filter(MappingJackson2HttpMessageConverter.class::isInstance)
                    .map(MappingJackson2HttpMessageConverter.class::cast)
                    .toList();

    assertTrue(converters.stream().anyMatch(converter ->
            converter.canWrite(CustomerResponse.class,
                    MediaType.APPLICATION_JSON)
    ));
}
~~~

Nếu ứng dụng có nhiều Jackson converter, chỉ kiểm tra tồn tại chưa chứng minh converter cụ thể được chọn cho endpoint. Converter order, supported media types, target class và request Content-Type đều ảnh hưởng lựa chọn.

Một số ứng dụng có thể cố ý sử dụng mapper riêng cho một converter. Vì vậy, đừng luôn assert rằng mọi converter phải dùng cùng một instance với ObjectMapper bean. Hãy kiểm tra cấu hình theo thiết kế thực tế và dùng HTTP contract test để xác nhận hành vi cuối cùng.

Có thể xem mapper của từng converter để debug:

~~~java
for (HttpMessageConverter<?> converter :
        handlerAdapter.getMessageConverters()) {
    if (converter instanceof MappingJackson2HttpMessageConverter jackson) {
        ObjectMapper converterMapper = jackson.getObjectMapper();
        // Kiểm tra feature/module liên quan khi cần.
    }
}
~~~

Không nên dùng kiểm tra nội bộ converter làm test duy nhất. Một converter tồn tại và có feature đúng vẫn có thể không được chọn cho request đang test.

## 8. Khi nào dùng @WebMvcTest?

@WebMvcTest tạo test slice cho tầng MVC. Nó chỉ nạp một phần application context và thường phù hợp để test controller, binding và response serialization nhanh.

~~~java
@WebMvcTest(CustomerController.class)
@Import(JacksonConfiguration.class)
class CustomerControllerSliceTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    CustomerService service;
}
~~~

Nếu JacksonConfiguration không được import hoặc không thuộc slice được nạp, test có thể chạy bằng cấu hình mặc định và cho kết quả khác production. Vì vậy:

- Dùng @WebMvcTest cho controller-focused tests.
- Import rõ cấu hình Jackson cần thiết nếu slice không tự nạp.
- Dùng @SpringBootTest khi cần xác minh auto-configuration, property file, profile và toàn bộ cấu hình ứng dụng.
- Không coi một slice test là bằng chứng đầy đủ rằng production context đang dùng cùng mapper.

Một chiến lược thực tế là có nhiều test nhanh với @WebMvcTest và ít nhất một nhóm integration test chạy full context để khóa cấu hình HTTP thực tế.

## 9. Kiểm tra cấu hình từ application.yml

Nếu cấu hình Jackson nằm trong YAML, test phải load đúng profile và property source. Ví dụ:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: non_null
~~~

Full context test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class JacksonApplicationConfigurationTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

Kiểm tra file application-test.yml có thể ghi đè property. Test properties trong annotation, environment variable của CI hoặc test configuration cũng có thể ghi đè YAML.

Khi một test không phản ánh cấu hình production, kiểm tra:

1. Active profiles.
2. Property source precedence.
3. Bean ObjectMapper tùy chỉnh.
4. Jackson2ObjectMapperBuilderCustomizer.
5. Module beans.
6. Custom HttpMessageConverters.
7. Test slice exclusions/imports.

Không thêm một cấu hình test mới chỉ để làm test pass nếu nó vô tình khác production. Mục tiêu là xác minh cấu hình ứng dụng thực sự cần triển khai.

## 10. Kiểm tra custom serializer/deserializer qua endpoint

Giả sử ứng dụng có kiểu Money và custom serializer ghi thành object:

~~~java
public record Money(String currency, BigDecimal amount) {}
~~~

Serializer:

~~~java
public class MoneySerializer extends StdSerializer<Money> {
    public MoneySerializer() {
        super(Money.class);
    }

    @Override
    public void serialize(
            Money value,
            JsonGenerator gen,
            SerializerProvider provider
    ) throws IOException {
        gen.writeStartObject();
        gen.writeStringField("currency", value.currency());
        gen.writeNumberField("amount", value.amount());
        gen.writeEndObject();
    }
}
~~~

Đăng ký qua module bean:

~~~java
@Bean
Module moneyModule() {
    SimpleModule module = new SimpleModule("money-module");
    module.addSerializer(Money.class, new MoneySerializer());
    module.addDeserializer(Money.class, new MoneyDeserializer());
    return module;
}
~~~

Endpoint trả DTO có Money:

~~~java
public record InvoiceResponse(String invoiceId, Money total) {}
~~~

HTTP test:

~~~java
mockMvc.perform(get("/api/invoices/INV-1")
        .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.total.currency").value("VND"))
        .andExpect(jsonPath("$.total.amount").value(125000));
~~~

Test này chứng minh module ảnh hưởng tới response thực tế. Nên có test POST/PUT tương ứng để xác minh custom deserializer được dùng khi nhận request.

## 11. Kiểm tra Java Time qua HTTP

Unit test JavaTimeModule không xác nhận converter production đã đăng ký module. Tạo endpoint trả về Instant/OffsetDateTime và kiểm tra HTTP body:

~~~java
public record EventResponse(
        String eventId,
        Instant occurredAt
) {}
~~~

HTTP test:

~~~java
mockMvc.perform(get("/api/events/evt-1")
        .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.occurred_at")
                .value("2026-11-12T10:30:00.123456789Z"));
~~~

Nếu endpoint nhận request chứa timestamp, gửi JSON fixture độc lập và capture giá trị Java được truyền vào service. Assert Instant hoặc OffsetDateTime theo contract, không chỉ assert status 200.

Nếu ứng dụng cần giữ offset, hãy assert offset. Nếu chỉ cần thời điểm tuyệt đối, assert Instant. Nếu cần region ZoneId, JSON phải mang đủ thông tin và test phải xác nhận ZoneId sau deserialize.

## 12. Kiểm tra content negotiation và media type

Spring chọn converter dựa trên kiểu dữ liệu, Content-Type, Accept và cấu hình endpoint.

Response:

~~~java
mockMvc.perform(get("/api/customers/42")
        .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
        ));
~~~

Request:

~~~java
mockMvc.perform(post("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(requestJson))
        .andExpect(status().isOk());
~~~

Test thêm các trường hợp:

- Content-Type không hỗ trợ.
- Accept không tương thích với produces.
- Body trống.
- JSON sai cú pháp.
- JSON có field sai kiểu.
- JSON thiếu property bắt buộc.
- Request có charset nếu endpoint hỗ trợ.

Không phải lỗi nào cũng là lỗi Jackson. Ví dụ 406 thường liên quan response content negotiation; 415 liên quan request media type không được hỗ trợ; 400 có thể là parse/binding/validation error.

## 13. Phân biệt parse error, binding error và validation error

Một HTTP test nên xác nhận ứng dụng phản hồi có chủ đích với từng loại input:

| Tình huống | Vấn đề | Kết quả thường gặp |
|---|---|---|
| JSON sai cú pháp | Parser không đọc được | 400 Bad Request |
| JSON hợp lệ nhưng field sai kiểu | Jackson không bind được | 400 Bad Request |
| Creator/target type không hợp lệ | Cấu hình model/deserializer sai | Thường 400 hoặc lỗi server tùy exception handling |
| Bean Validation thất bại | Object bind được nhưng vi phạm constraint | 400 hoặc status theo API contract |
| Content-Type không hỗ trợ | Không có converter phù hợp | 415 Unsupported Media Type |
| Accept không phù hợp | Không có representation được chọn | 406 Not Acceptable |

Nếu lỗi creator là do bug cấu hình server, không nên biến nó thành lỗi client một cách mù quáng. Exception handler cần phân loại đúng nguyên nhân. Test HTTP nên khóa status và error response theo contract ứng dụng.

Ví dụ JSON sai cú pháp:

~~~java
mockMvc.perform(post("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{ invalid json"))
        .andExpect(status().isBadRequest());
~~~

Ví dụ field sai kiểu:

~~~java
String invalidType = """
        {
          "display_name": "An",
          "created_at": 12345
        }
        """;
~~~

Expected status phụ thuộc kiểu DTO, deserializer và error handling; test cần dùng đúng contract của ứng dụng.

## 14. Kiểm tra enum và unknown properties

Nếu ứng dụng có enum:

~~~java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
~~~

HTTP test nên xác nhận cả giá trị hợp lệ và giá trị không hợp lệ. Cấu hình READ_UNKNOWN_ENUM_VALUES_AS_NULL hoặc READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE có thể thay đổi hành vi.

Tương tự, FAIL_ON_UNKNOWN_PROPERTIES quyết định field lạ có bị từ chối không:

~~~java
String payloadWithExtraField = """
        {
          "display_name": "An",
          "created_at": "2026-11-12T10:30:00Z",
          "unexpected": true
        }
        """;
~~~

Nếu API strict, assert lỗi theo contract. Nếu API forward-compatible và bỏ qua field lạ, assert request vẫn được bind và field không được chuyển vào domain ngoài ý muốn.

Đừng chỉ kiểm tra ObjectMapper feature trực tiếp. Hãy gửi payload qua endpoint để xác nhận converter đang dùng cùng hành vi.

## 15. Kiểm tra null, missing và inclusion qua HTTP

Ví dụ response có nickname null. Nếu NON_NULL đang bật, property không xuất hiện:

~~~java
.andExpect(jsonPath("$.nickname").doesNotExist());
~~~

Nếu contract yêu cầu explicit null:

~~~java
.andExpect(jsonPath("$.nickname").value(nullValue()));
~~~

Với request PATCH, cần phân biệt field missing và explicit null. DTO đơn giản có thể làm mất presence. Hãy test bằng JsonNode hoặc tri-state model nếu API có semantics:

- Missing: giữ giá trị cũ.
- Null: xóa giá trị.
- Value: thay thế giá trị.

HTTP integration test là nơi phù hợp để xác minh semantics này vì request body được parser thật xử lý và controller nhận đúng representation.

## 16. Test converter thực tế khi có nhiều converter

Một ứng dụng có thể đăng ký converter cho JSON, XML, String, byte array hoặc định dạng riêng. Thứ tự và supported media types ảnh hưởng converter được chọn.

Có thể inspect danh sách converter:

~~~java
@Autowired
RequestMappingHandlerAdapter adapter;

@Test
void listsConfiguredMessageConverters() {
    List<HttpMessageConverter<?>> converters =
            adapter.getMessageConverters();

    assertTrue(converters.stream().anyMatch(
            MappingJackson2HttpMessageConverter.class::isInstance
    ));
}
~~~

Nếu ứng dụng có custom converter, hãy xác minh converter đó có được đặt trước hoặc sau converter Jackson theo chủ đích. Một test response từ endpoint có Content-Type cụ thể sẽ xác nhận đường đi được chọn tốt hơn chỉ inspect danh sách.

Không nên thêm converter tùy chỉnh chỉ để test có thể tìm thấy nó. Kiểm tra cấu hình ứng dụng đang dùng và xác nhận bằng request thực.

## 17. Kiểm thử WebFlux bằng WebTestClient

Với Spring WebFlux, JSON thường được xử lý bởi HttpMessageReader/Writer và codec, không phải MVC MappingJackson2HttpMessageConverter.

Ví dụ dùng WebTestClient với full context:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CustomerWebFluxJacksonTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void usesConfiguredJsonCodec() {
        webTestClient.get()
                .uri("/api/customers/42")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                )
                .expectBody()
                .jsonPath("$.customer_id").isEqualTo(42)
                .jsonPath("$.display_name").isEqualTo("Nguyen An");
    }
}
~~~

Cấu hình codec có thể được tùy chỉnh qua WebFluxConfigurer hoặc ServerCodecConfigurer. Nếu cần xác minh behavior, gửi request/response qua WebTestClient và kiểm tra JSON contract.

Không dùng test MVC converter để kết luận WebFlux codec đã được cấu hình. Hai stack có hạ tầng khác nhau dù cùng dùng Jackson.

## 18. MockMvc, WebTestClient và real HTTP khác nhau thế nào?

| Công cụ | Đường đi được kiểm tra | Phù hợp |
|---|---|---|
| MockMvc với web application context | DispatcherServlet, controller, MVC converters và filter được cấu hình | Spring MVC integration test nhanh |
| WebTestClient bindToApplicationContext | WebFlux application pipeline trong test context | WebFlux integration test |
| WebTestClient/RestAssured qua RANDOM_PORT | HTTP server thực, socket và server stack | Kiểm tra end-to-end HTTP gần runtime |
| Test ObjectMapper trực tiếp | Mapper API riêng lẻ | Unit test serializer/deserializer, không xác minh HTTP integration |

MockMvc không mở network socket thật, nhưng nó vẫn chạy request qua MVC infrastructure. Nếu cần xác minh embedded server, port, filter chain hoặc cấu hình container, dùng RANDOM_PORT và client HTTP.

Không cần dùng real server cho mọi test. Chọn công cụ theo lớp hành vi muốn khóa.

## 19. Dùng @JsonTest cho serializer-focused test, không thay HTTP test

Spring Boot có thể cung cấp @JsonTest để kiểm tra JSON serialization/deserialization trong slice test:

~~~java
@JsonTest
class CustomerJsonTest {

    @Autowired
    JacksonTester<CustomerResponse> json;

    @Test
    void serializesCustomer() throws Exception {
        CustomerResponse response = new CustomerResponse(
                42L,
                "Nguyen An",
                null,
                Instant.parse("2026-11-12T10:30:00Z")
        );

        assertThat(json.write(response))
                .hasJsonPathStringValue("$.display_name");
    }
}
~~~

@JsonTest hữu ích để test DTO, annotation, serializer/deserializer và cấu hình JSON slice. Nó không chứng minh MVC converter hoặc WebFlux codec của endpoint đang dùng cùng cấu hình. Giữ cả serializer-focused tests và HTTP integration tests nếu contract HTTP quan trọng.

## 20. Tránh kiểm tra cấu hình sai context

Các nguyên nhân phổ biến khiến HTTP test pass nhưng production khác:

- Dùng @WebMvcTest mà quên import customizer/configuration.
- Test profile có application-test.yml khác production.
- Test khai báo @TestConfiguration tạo mapper mới.
- Có nhiều ObjectMapper bean và @Primary không như dự kiến.
- Custom converter dùng mapper riêng.
- WebFlux và MVC cùng tồn tại, test nhầm stack.
- Test dùng standaloneSetup thay vì application context.
- Test chỉ gọi controller method trực tiếp.
- JSON fixture trong test được tạo bằng cùng mapper nên writer và reader cùng che giấu một contract sai.

Để giảm rủi ro, dùng fixture JSON literal độc lập cho request. Với response, assert field và format mà client bên ngoài nhìn thấy. Nếu cần test compatibility, dùng fixture được lưu theo version contract thay vì serialize input bằng mapper đang kiểm tra.

## 21. Kiểm tra mapper bean là một test bổ sung

Có thể inject ObjectMapper để kiểm tra feature và module đã được cấu hình:

~~~java
@SpringBootTest
class JacksonBeanConfigurationTest {

    @Autowired
    ObjectMapper mapper;

    @Test
    void mapperHasExpectedNamingStrategy() {
        assertEquals(
                PropertyNamingStrategies.SNAKE_CASE,
                mapper.getPropertyNamingStrategy()
        );
    }

    @Test
    void mapperHasJavaTimeSupport() throws Exception {
        Instant instant = Instant.parse("2026-11-12T10:30:00Z");

        String json = mapper.writeValueAsString(instant);

        assertEquals("\"2026-11-12T10:30:00Z\"", json);
    }
}
~~~

Đây là test cấu hình bean, hữu ích để chỉ ra nguyên nhân khi HTTP contract test thất bại. Nhưng nó không thay thế HTTP test vì converter/codec có thể dùng mapper khác.

Một số customizer hoặc builder có thể tạo mapper có behavior tương đương nhưng object identity khác. Assert behavior thường bền vững hơn assert cùng instance, trừ khi thiết kế ứng dụng yêu cầu chia sẻ đúng một mapper.

## 22. Kiểm tra cấu hình nhiều ObjectMapper theo media type

Nếu ứng dụng cố ý dùng mapper riêng cho từng converter, hãy test từng endpoint/media type tương ứng. Ví dụ endpoint JSON public dùng snake_case, endpoint nội bộ dùng một converter khác. Không ép mọi converter phải có cùng naming strategy nếu đó là chủ đích.

Tuy nhiên, nhiều mapper làm tăng độ phức tạp. Hãy ghi rõ endpoint nào dùng converter nào, vì sao cần khác biệt và test contract riêng cho từng đường đi.

Nếu chỉ cần khác biệt theo type/property, cân nhắc mix-in, annotation hoặc ObjectWriter/ObjectReader phù hợp thay vì tạo nhiều converter toàn cục.

## 23. Kiểm tra request body có charset và dữ liệu Unicode

HTTP JSON thường dùng UTF-8. Test nên có dữ liệu Unicode để phát hiện encode/decode sai:

~~~java
String requestJson = """
        {
          "display_name": "Nguyễn An – 東京",
          "created_at": "2026-11-12T10:30:00Z"
        }
        """;

mockMvc.perform(post("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .characterEncoding(StandardCharsets.UTF_8.name())
        .content(requestJson))
        .andExpect(status().isOk());
~~~

Kiểm tra giá trị Java mà service nhận, không chỉ status. Nếu ứng dụng xử lý ký tự ngoài ASCII, test response body cũng nên xác nhận chúng được giữ nguyên.

## 24. Kiểm tra lỗi và error response do Jackson binding

Ứng dụng có thể chuẩn hóa lỗi bằng @ControllerAdvice:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> handleUnreadable(
            HttpMessageNotReadableException exception
    ) {
        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_JSON", "Request body is invalid")
        );
    }
}
~~~

Test:

~~~java
mockMvc.perform(post("/api/customers")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{ invalid"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("INVALID_JSON"));
~~~

Không trả stack trace, tên class nội bộ hoặc toàn bộ payload nhạy cảm cho client. Log server có thể giữ exception cause và correlation ID theo chính sách bảo mật.

Nếu exception do lỗi cấu hình server như thiếu deserializer cho một kiểu bắt buộc, hãy phân loại phù hợp; không nên luôn trả cùng một mã “invalid client JSON” nếu client không thể sửa vấn đề.

## 25. Test thực tế qua port ngẫu nhiên

Khi cần kiểm tra embedded server, dùng RANDOM_PORT:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CustomerRealHttpTest {

    @LocalServerPort
    int port;

    @Test
    void returnsConfiguredJsonOverHttp() {
        RestClient client = RestClient.create();

        String body = client.get()
                .uri("http://localhost:" + port + "/api/customers/42")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(String.class);

        assertNotNull(body);
        assertTrue(body.contains("customer_id"));
    }
}
~~~

Ví dụ này dùng RestClient của Spring Framework ở các version có API đó. Với version cũ hơn, dùng TestRestTemplate, WebTestClient hoặc HTTP client hiện có trong project.

Để test mạnh hơn, parse response bằng JsonNode và assert field/type/value. Không chỉ kiểm tra body contains một chuỗi nếu có thể kiểm tra cấu trúc JSON.

RANDOM_PORT tốn thời gian hơn MockMvc nhưng kiểm tra thêm server startup, port binding và HTTP stack thực tế.

## 26. Một test matrix hữu ích cho cấu hình Jackson HTTP

| Cấu hình cần xác minh | Request test | Response test |
|---|---|---|
| Naming strategy | Gửi snake_case, kiểm tra DTO/service nhận đúng | Kiểm tra property xuất snake_case |
| JavaTimeModule | Gửi ISO timestamp | Kiểm tra ISO timestamp output |
| Offset/timezone | Gửi offset khác UTC | Assert instant và offset theo contract |
| Inclusion null | Gửi explicit null nếu được hỗ trợ | Kiểm tra field null bị bỏ hay giữ |
| Unknown properties | Gửi field lạ | Assert accept/reject theo policy |
| Enum policy | Gửi enum hợp lệ/không hợp lệ | Kiểm tra representation enum |
| Custom serializer | Không áp dụng trực tiếp | Kiểm tra output shape |
| Custom deserializer | Kiểm tra service nhận domain value đúng | Không áp dụng trực tiếp |
| Polymorphic typing | Gửi discriminator hợp lệ và lạ | Kiểm tra type metadata nếu contract yêu cầu |
| Content negotiation | Content-Type/Accept khác nhau | Kiểm tra status và response media type |
| Validation | Gửi payload bind được nhưng sai constraint | Kiểm tra status/error body |

Không nhất thiết gộp mọi cấu hình vào một test. Tách test theo hành vi giúp khi lỗi xuất hiện có thể xác định feature nào bị mất.

## 27. Quy trình điều tra khi HTTP test không dùng cấu hình mong đợi

Khi test cho kết quả khác unit test mapper:

1. Xác nhận test đang chạy MVC hay WebFlux.
2. Xác nhận request có Content-Type application/json và Accept phù hợp.
3. Kiểm tra endpoint consumes/produces.
4. Xem converter/codec được đăng ký trong context.
5. Kiểm tra converter order và mapper được converter sử dụng.
6. Kiểm tra ObjectMapper bean, customizer và module beans.
7. Kiểm tra active profile và property source.
8. Kiểm tra test slice có loại bỏ config nào không.
9. Dùng JSON fixture độc lập để tránh writer/reader cùng che giấu lỗi.
10. Kiểm tra exception cause và HTTP error handler.

Nếu converter riêng được cấu hình, sửa đúng bean/configuration đang được dùng. Đừng thêm customizer thứ hai mà không xác định precedence, vì có thể chỉ che vấn đề trong test.

## 28. Những cách test dễ tạo cảm giác an toàn giả

### Chỉ serialize bằng mapper tự tạo

Test không đi qua Spring và không xác minh HTTP converter.

### Chỉ assert mapper bean có feature

Converter có thể dùng mapper khác.

### Chỉ test GET

Response serialization có thể đúng trong khi request deserialization sai.

### Chỉ dùng @WebMvcTest

Slice có thể bỏ qua cấu hình auto-configuration hoặc bean production cần thiết.

### Tạo request JSON bằng chính ObjectMapper đang test

Nếu writer và reader cùng hiểu sai format theo một cách nhất quán, round-trip vẫn pass. Dùng JSON literal hoặc fixture từ contract độc lập.

### Chỉ assert status 200

Endpoint có thể trả JSON với property name, date format hoặc null policy sai mà status vẫn 200.

### Chỉ inspect converter list

Converter tồn tại không chứng minh nó được chọn cho request cụ thể.

## 29. Gợi ý cấu trúc test suite

Một project Spring MVC có thể chia test thành ba lớp:

~~~text
Jackson unit tests
  - serializer/deserializer riêng
  - annotation, module, precision và edge cases

MVC slice tests
  - @WebMvcTest
  - request binding và response JSON của từng controller
  - import Jackson config cần thiết

Full application HTTP tests
  - @SpringBootTest + @AutoConfigureMockMvc
  - application.yml/profile/customizer/module/converter thật
  - một số endpoint đại diện cho contract quan trọng
~~~

Nếu ứng dụng dùng WebFlux, thay lớp MVC test bằng WebTestClient và kiểm tra codec stack. Nếu có yêu cầu embedded server, bổ sung một số test RANDOM_PORT thay vì chạy real server cho mọi trường hợp.

Cách chia này giữ test nhanh ở tầng nhỏ và vẫn có bằng chứng rằng cấu hình được triển khai thực sự đi qua HTTP pipeline.

## 30. Ghi nhớ

Muốn xác minh cấu hình Jackson trong Spring đã được áp dụng, hãy kiểm tra JSON qua endpoint HTTP. Với Spring MVC, request/response đi qua HttpMessageConverter; với WebFlux, đi qua codec encoder/decoder. ObjectMapper bean test riêng chỉ là kiểm tra bổ sung vì converter/codec có thể dùng mapper khác.

Dùng @SpringBootTest cùng MockMvc để kiểm tra full MVC context; dùng @WebMvcTest cho controller slice khi import đầy đủ config; dùng WebTestClient cho WebFlux và RANDOM_PORT khi cần embedded server. Test cả request deserialization lẫn response serialization, Content-Type/Accept, naming strategy, Java time, null inclusion, custom module và lỗi binding.

Dùng JSON fixture độc lập, assert field/value/type theo contract và kiểm tra converter/codec khi cần điều tra. Không dựa riêng vào mapper bean, converter list, status 200 hoặc round-trip bằng cùng một mapper. Một HTTP contract test tốt chứng minh client thực sự gửi được JSON mà ứng dụng hiểu và nhận được JSON mà API cam kết.
