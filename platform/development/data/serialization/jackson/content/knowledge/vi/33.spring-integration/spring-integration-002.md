# Vai trò của bộ chuyển đổi thông điệp HTTP dùng Jackson

Trong Spring MVC, controller thường làm việc với object Java: nhận một request DTO, gọi service và trả về một response DTO. Client lại gửi và nhận dữ liệu qua HTTP dưới dạng byte. Bộ chuyển đổi thông điệp HTTP (HTTP message converter) là lớp trung gian biến đổi giữa hai phía: đọc body HTTP thành object Java và ghi object Java thành body HTTP.

Với JSON, Spring thường sử dụng `MappingJackson2HttpMessageConverter`. Converter này tích hợp Jackson `ObjectMapper` vào vòng đời xử lý request/response của Spring MVC. Nhờ đó controller có thể dùng `@RequestBody`, `@ResponseBody` hoặc `ResponseEntity` mà không phải tự đọc stream, gọi `readValue()` hay ghi JSON bằng tay trong từng endpoint.

Hiểu vai trò của converter giúp giải thích vì sao cùng một DTO có thể được đọc/ghi khác nhau theo `Content-Type`, `Accept`, cấu hình `ObjectMapper`, thứ tự converter và media type của endpoint. Bài học này đi qua luồng đọc/ghi, cách Spring lựa chọn converter, cách cấu hình Jackson trong Spring Boot, xử lý lỗi, kiểm thử và các lưu ý về bảo mật cùng hiệu năng.

## 1. HTTP body và object Java là hai dạng dữ liệu khác nhau

HTTP truyền dữ liệu qua request body và response body dưới dạng byte. Ví dụ client gửi:

~~~http
POST /api/orders
Content-Type: application/json

{
  "customerId": "CUS-100",
  "quantity": 2
}
~~~

Controller muốn nhận một object:

~~~java
@PostMapping("/api/orders")
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Ở đây có một bước chuyển đổi:

~~~text
HTTP request bytes
       |
       v
HTTP message converter
       |
       v
Jackson ObjectMapper
       |
       v
CreateOrderRequest
       |
       v
Controller / application service
~~~

Khi trả response, chiều chuyển đổi đảo ngược:

~~~text
OrderResponse
       |
       v
Jackson ObjectMapper
       |
       v
HTTP message converter
       |
       v
HTTP response bytes
~~~

Converter chịu trách nhiệm kết nối HTTP abstraction của Spring với thư viện xử lý định dạng cụ thể. Controller chỉ khai báo kiểu dữ liệu mong muốn và để Spring thực hiện việc chuyển đổi.

## 2. HttpMessageConverter là gì?

`HttpMessageConverter<T>` là một strategy interface trong Spring Framework. Mỗi converter hỗ trợ một hoặc một số kiểu Java và media type nhất định.

Các trách nhiệm chính:

- Xác định converter có thể đọc một kiểu Java từ media type nào.
- Đọc body của `HttpInputMessage` thành object Java.
- Xác định converter có thể ghi kiểu Java đó ra media type nào.
- Ghi object Java vào `HttpOutputMessage`.
- Cung cấp danh sách media type được hỗ trợ.

Một số converter phổ biến:

| Converter | Định dạng hoặc kiểu dữ liệu |
|---|---|
| `StringHttpMessageConverter` | Chuỗi văn bản |
| `ByteArrayHttpMessageConverter` | Mảng byte |
| `ResourceHttpMessageConverter` | Spring Resource |
| `FormHttpMessageConverter` | Form data |
| `MappingJackson2HttpMessageConverter` | JSON bằng Jackson 2 |
| `Jaxb2RootElementHttpMessageConverter` | XML bằng JAXB khi được cấu hình |
| `ProtobufHttpMessageConverter` | Protocol Buffers khi có module tương ứng |

Spring có thể đăng ký nhiều converter trong cùng một ứng dụng. Converter được chọn dựa trên kiểu dữ liệu, media type và vị trí của nó trong danh sách converter.

## 3. MappingJackson2HttpMessageConverter làm gì?

`MappingJackson2HttpMessageConverter` là converter tích hợp Jackson Databind với Spring MVC. Nó sử dụng `ObjectMapper` để đọc JSON thành object Java và serialize object Java thành JSON.

Các nhiệm vụ chính:

1. Nhận biết media type JSON được hỗ trợ.
2. Kiểm tra kiểu Java có thể deserialize/serialize hay không.
3. Đọc HTTP input stream qua Jackson parser và Databind.
4. Ghi object ra HTTP output stream bằng Jackson generator.
5. Làm việc với cấu hình mapper, module, serializer, deserializer và annotation của Jackson.
6. Báo lỗi chuyển đổi để Spring MVC xử lý ở tầng web.

Trong Spring Framework 6.x, class vẫn mang tên `MappingJackson2HttpMessageConverter` khi ứng dụng dùng Jackson 2. Tên class có số 2 để phân biệt dòng tích hợp Jackson 2. Nếu dự án nâng cấp sang thế hệ Jackson hoặc Spring mới hơn, hãy kiểm tra converter tương ứng trong version đang dùng thay vì suy luận API từ tên class cũ.

## 4. Converter nằm ở đâu trong vòng đời Spring MVC?

Với controller dùng `@RequestBody`, Spring MVC gọi cơ chế đọc message converter để chuyển request body thành tham số method. Với controller trả về object qua `@ResponseBody` hoặc `ResponseEntity`, Spring gọi cơ chế ghi message converter để tạo response body.

Luồng request:

~~~text
Client
  |
  | HTTP request + Content-Type
  v
DispatcherServlet
  |
  v
HandlerMapping / HandlerAdapter
  |
  v
RequestResponseBodyMethodProcessor
  |
  v
HttpMessageConverter selection
  |
  v
MappingJackson2HttpMessageConverter
  |
  v
ObjectMapper.readValue(...)
  |
  v
Controller method argument
~~~

Luồng response:

~~~text
Controller return value
  |
  v
ResponseBody / ResponseEntity handling
  |
  v
Content negotiation
  |
  v
HttpMessageConverter selection
  |
  v
MappingJackson2HttpMessageConverter
  |
  v
ObjectMapper.writeValue(...)
  |
  v
HTTP response body
~~~

Tên các thành phần nội bộ giúp hình dung cơ chế, nhưng ứng dụng thường không cần gọi trực tiếp `RequestResponseBodyMethodProcessor`. Hãy dùng annotation controller và cấu hình converter qua các extension point công khai của Spring MVC.

## 5. Đọc request bằng @RequestBody

Ví dụ DTO:

~~~java
public class CreateOrderRequest {
    private String customerId;
    private int quantity;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public OrderResponse create(
            @Valid @RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
~~~

Khi request có `Content-Type: application/json`, Spring tìm converter có thể đọc `CreateOrderRequest` từ media type này. Converter Jackson đọc body và tạo DTO trước khi method controller được gọi.

Nếu JSON sai cú pháp hoặc không ánh xạ được vào kiểu Java, lỗi xảy ra ở bước chuyển đổi. Controller method thường chưa được thực thi. Đây là điểm quan trọng khi thiết kế error handling: lỗi parse request khác với lỗi nghiệp vụ xảy ra sau khi controller đã nhận DTO.

`@RequestBody` mặc định yêu cầu body có mặt. Nếu body có thể vắng mặt, dùng `required = false` và xử lý null một cách tường minh. Không nên giả định body rỗng tự động trở thành object rỗng.

## 6. Ghi response bằng @ResponseBody và @RestController

`@ResponseBody` yêu cầu Spring ghi return value vào HTTP response body thông qua message converter. `@RestController` kết hợp `@Controller` và `@ResponseBody` cho các method của controller.

~~~java
@GetMapping(
    value = "/{id}",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public OrderResponse get(@PathVariable String id) {
    return orderService.findById(id);
}
~~~

Nếu method trả `OrderResponse`, converter Jackson serialize object thành JSON. Spring đặt header response phù hợp với media type đã chọn.

Với `ResponseEntity`, controller có thể kiểm soát status và header:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {

    OrderResponse response = orderService.create(request);

    return ResponseEntity
        .status(HttpStatus.CREATED)
        .body(response);
}
~~~

`ResponseEntity` không tự serialize JSON. Nó cung cấp status, headers và body; body vẫn được converter phù hợp ghi ra HTTP response.

## 7. Content-Type và Accept quyết định điều gì?

Hai HTTP header thường liên quan trực tiếp tới converter:

- `Content-Type`: định dạng thực tế của request body.
- `Accept`: những định dạng client có thể nhận trong response.

Ví dụ request:

~~~http
POST /api/orders
Content-Type: application/json
Accept: application/json
~~~

Spring dùng `Content-Type` để tìm converter có thể đọc body. Khi ghi response, Spring xét kiểu return value, media type mà endpoint có thể tạo và yêu cầu `Accept` của client.

Nếu client gửi `Content-Type: text/plain` trong khi endpoint chỉ nhận JSON, Spring thường trả `415 Unsupported Media Type`. Nếu client yêu cầu một response media type mà endpoint không thể tạo, Spring có thể trả `406 Not Acceptable`.

Không nhầm hai header:

| Header | Ý nghĩa | Ảnh hưởng |
|---|---|---|
| `Content-Type` | Body hiện tại được mã hóa theo định dạng nào | Chọn converter đọc request |
| `Accept` | Client chấp nhận response định dạng nào | Content negotiation và chọn converter ghi |
| `Content-Length` | Số byte của body nếu được cung cấp | Có thể hỗ trợ kiểm soát kích thước; không phải media type |
| `Content-Encoding` | Cách body được mã hóa/nén ở tầng truyền tải | Cần giải mã phù hợp trước khi parse nội dung |

## 8. Media type JSON mà converter hỗ trợ

Converter Jackson thường hỗ trợ `application/json` và các media type thuộc nhóm `application/*+json`, chẳng hạn:

- `application/json`
- `application/problem+json`
- `application/vnd.acme.order+json`

Media type dạng `+json` hữu ích khi API dùng vendor-specific media type hoặc chuẩn JSON chuyên biệt. Nó vẫn biểu thị nội dung JSON, nhưng có thể mang semantics hoặc version riêng.

Có thể giới hạn media type của endpoint:

~~~java
@PostMapping(
    value = "/orders",
    consumes = "application/vnd.acme.order+json",
    produces = "application/vnd.acme.order+json"
)
public OrderResponse createPartnerOrder(
        @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Nếu converter hỗ trợ media type này và endpoint khai báo tương thích, Spring có thể dùng Jackson để đọc/ghi. Cần kiểm tra cấu hình thực tế của converter và content negotiation khi dùng media type tùy chỉnh.

Không nên khai báo `produces`/`consumes` chỉ để “ép JSON” mà không hiểu client đang gửi header gì. Hãy coi media type là một phần của hợp đồng API.

## 9. Spring lựa chọn converter như thế nào?

Về khái niệm, Spring xét:

1. Kiểu Java cần đọc hoặc ghi.
2. Media type của request hoặc media type response được thương lượng.
3. Converter có trả về `canRead(...)` hoặc `canWrite(...)` hay không.
4. Thứ tự converter trong danh sách.
5. Một số thông tin bổ sung như generic type, target type và các điều kiện của handler.

Converter đầu tiên phù hợp có thể được dùng. Vì vậy, thứ tự đăng ký có ý nghĩa khi nhiều converter cùng hỗ trợ một media type hoặc kiểu dữ liệu.

Ví dụ `StringHttpMessageConverter` và Jackson có thể cùng tham gia vào những trường hợp liên quan tới text. Một method trả về `String` thường được xử lý như nội dung text thay vì object JSON được serialize thành chuỗi JSON. Nếu cần trả JSON string literal, hãy cân nhắc kiểu response và contract rõ ràng, hoặc trả DTO chứa field string.

Không thêm converter tổng quát nhận `*/*` ở đầu danh sách nếu chưa hiểu tác động. Converter quá rộng có thể chiếm request/response mà converter chuyên biệt đáng lẽ phải xử lý.

## 10. Converter có hỗ trợ generic type

API thường trả collection hoặc kiểu generic:

~~~java
@GetMapping
public List<OrderResponse> list() {
    return orderService.findAll();
}
~~~

Jackson cần biết kiểu phần tử để serialize đúng. Spring có các abstraction hỗ trợ generic type, chẳng hạn `GenericHttpMessageConverter`, để converter nhận thêm thông tin kiểu như `List<OrderResponse>` thay vì chỉ thấy raw `List`.

Đối với request body generic, có thể khai báo:

~~~java
@PostMapping("/bulk")
public BulkResult createBulk(
        @RequestBody List<CreateOrderRequest> requests) {
    return orderService.createBulk(requests);
}
~~~

Spring truyền thông tin generic tới converter hỗ trợ kiểu đó, và Jackson có thể ánh xạ từng phần tử theo `CreateOrderRequest`.

Nếu dùng wrapper generic:

~~~java
public class ApiEnvelope<T> {
    private T data;
    private String requestId;

    // Getter và setter.
}
~~~

Spring/Jackson cần giữ generic type metadata để deserialize `ApiEnvelope<CreateOrderRequest>` đúng. Tránh tự lấy raw `Class` rồi gọi `readValue` mà làm mất kiểu tham số. Trong code thủ công, dùng `TypeReference<T>` hoặc `JavaType` khi cần.

## 11. ObjectMapper là phần cốt lõi của converter

Converter Jackson không tự định nghĩa toàn bộ quy tắc JSON. Nó sử dụng `ObjectMapper` để quyết định:

- Property nào được serialize/deserialize.
- Naming strategy.
- Date/time format.
- Enum representation.
- Null handling.
- Unknown property policy.
- Custom serializer/deserializer.
- Jackson module.
- Polymorphic type handling.
- Parser constraints.
- Serialization features.

Ví dụ, cùng một DTO có thể tạo output khác nhau nếu mapper dùng naming strategy khác:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Property Java `customerId` sẽ được ánh xạ theo quy tắc snake_case, ví dụ `customer_id`, nếu không có annotation ghi đè.

Vì vậy, khi JSON request không map được hoặc response có format khác mong đợi, hãy kiểm tra mapper mà converter thực sự đang dùng. Một `new ObjectMapper()` trong unit test có thể không giống mapper được Spring Boot cấu hình trong ứng dụng.

## 12. Spring Boot tự cấu hình Jackson

Trong ứng dụng Spring Boot có starter web, auto-configuration thường tạo mapper và đăng ký JSON message converter phù hợp. Boot cũng có thể tự nhận các Jackson module trên classpath và áp dụng cấu hình từ application properties.

Ví dụ:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
    default-property-inclusion: NON_NULL
    deserialization:
      fail-on-unknown-properties: true
    serialization:
      write-dates-as-timestamps: false
~~~

Các property chính xác và cách binding phụ thuộc phiên bản Spring Boot. Hãy kiểm tra configuration metadata/Javadoc của version dự án, đặc biệt khi dùng nhiều mapper hoặc custom converter.

Khi Boot đã cấu hình mapper, đừng tạo một `ObjectMapper` mới trong controller hoặc service chỉ để parse một request. Làm như vậy có thể bỏ qua module, naming strategy, customizer, security constraints và serializer mà ứng dụng đang dùng.

## 13. Tùy chỉnh mapper bằng Jackson2ObjectMapperBuilderCustomizer

Trong Spring Boot, `Jackson2ObjectMapperBuilderCustomizer` là một extension point thuận tiện để bổ sung cấu hình cho builder mà Boot sử dụng:

~~~java
@Configuration
public class JacksonConfiguration {
    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> {
            builder.featuresToDisable(
                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
            );
            builder.featuresToEnable(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
            );
        };
    }
}
~~~

Cách này phù hợp khi muốn bổ sung quy tắc chung cho mapper do Boot tạo. Nếu cần custom serializer/deserializer hoặc module, có thể đăng ký module tương ứng qua builder hoặc bean theo cơ chế Boot hỗ trợ.

Đừng sao chép toàn bộ cấu hình mapper vào nhiều nơi. Một chính sách JSON nhất quán giúp request và response không có hành vi bất ngờ giữa các controller.

## 14. Cung cấp ObjectMapper riêng

Nếu ứng dụng cần kiểm soát toàn bộ mapper, có thể khai báo bean `ObjectMapper`:

~~~java
@Configuration
public class JacksonConfiguration {
    @Bean
    ObjectMapper apiObjectMapper() {
        return JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
    }
}
~~~

Khi Spring Boot hoặc Spring MVC sử dụng bean này cho converter, các quy tắc sẽ áp dụng cho JSON của ứng dụng. Tuy nhiên, khai báo mapper riêng có thể làm thay đổi hoặc thay thế một phần auto-configuration. Cần xác nhận các module, customizer và feature mà ứng dụng cần vẫn được giữ lại.

Nếu chỉ muốn thay đổi một vài feature, customizer thường ít xâm lấn hơn việc tự tạo mapper hoàn toàn mới.

Mapper nên được cấu hình xong trước khi sử dụng. Sau đó tái sử dụng bean singleton; không sửa cấu hình của mapper trong lúc request đang chạy.

## 15. Tùy chỉnh converter qua WebMvcConfigurer

`WebMvcConfigurer` cho phép ứng dụng tùy chỉnh danh sách HTTP message converter.

Nếu chỉ muốn sửa converter mặc định đã được Spring đăng ký, `extendMessageConverters` thường phù hợp hơn:

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {
    private final ObjectMapper objectMapper;

    public WebConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {

        for (HttpMessageConverter<?> converter : converters) {
            if (converter instanceof MappingJackson2HttpMessageConverter jackson) {
                jackson.setObjectMapper(objectMapper);
            }
        }
    }
}
~~~

Đoạn code minh họa việc gắn mapper ứng dụng vào converter Jackson. Nếu ứng dụng đã inject đúng mapper mặc định, không cần thay lại chỉ để lặp cấu hình.

`configureMessageConverters` dùng khi muốn tự cấu hình danh sách converter. Trong nhiều cấu hình Spring MVC, khi tự thêm converter vào danh sách theo cách này, ứng dụng có thể phải chịu trách nhiệm đăng ký đầy đủ các converter cần thiết. Vì vậy, hãy chọn extension point theo mục tiêu:

- `extendMessageConverters`: chỉnh sửa hoặc bổ sung sau khi converter mặc định được tạo.
- `configureMessageConverters`: kiểm soát danh sách converter theo cách chủ động hơn.

Không đăng ký cùng một converter nhiều lần hoặc thêm converter Jackson chung trước converter chuyên biệt mà không kiểm tra thứ tự.

## 16. Thêm converter cho vendor media type

Giả sử API đối tác dùng `application/vnd.acme.order+json` và cần mapper riêng. Có thể tạo converter chuyên biệt:

~~~java
@Bean
MappingJackson2HttpMessageConverter partnerJsonConverter(
        @Qualifier("partnerObjectMapper") ObjectMapper partnerMapper) {

    MappingJackson2HttpMessageConverter converter =
        new MappingJackson2HttpMessageConverter(partnerMapper);

    converter.setSupportedMediaTypes(
        List.of(MediaType.valueOf("application/vnd.acme.order+json"))
    );

    return converter;
}
~~~

Sau đó đăng ký converter ở vị trí phù hợp trong danh sách. Vì converter Jackson mặc định cũng có thể hỗ trợ `application/*+json`, converter chuyên biệt cần đứng trước converter tổng quát nếu muốn nó được chọn cho vendor media type đó.

Một cấu hình có thể dùng:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    converters.add(0, partnerJsonConverter);
}
~~~

Đoạn trên giả định `partnerJsonConverter` đã được inject vào configuration. Trong code thật, hãy dùng constructor injection thay vì tạo bean hoặc lấy dependency theo cách không rõ ràng.

Không tạo mapper riêng chỉ để đổi tên một field nếu `@JsonProperty`, mix-in hoặc view có thể diễn đạt hợp đồng đơn giản hơn. Nhiều mapper đồng nghĩa nhiều chính sách cần kiểm thử và tài liệu hóa.

## 17. Thứ tự converter và lỗi cấu hình phổ biến

Giả sử một custom converter khai báo hỗ trợ `*/*`. Nếu đặt nó ở đầu danh sách, nó có thể nhận cả JSON, text hoặc binary trước converter phù hợp. Hậu quả có thể là response sai định dạng hoặc request không đọc được.

Khi thêm converter, hãy kiểm tra:

- `canRead(targetType, contentType)`.
- `canWrite(returnType, acceptType)`.
- `getSupportedMediaTypes()`.
- Vị trí converter trong danh sách.
- Các converter mặc định có còn được đăng ký không.
- Media type của endpoint có tương thích không.
- Generic type có được giữ không.

Nếu một request `application/json` lại được xử lý thành `String` hoặc byte array, hãy xem converter nào được chọn. Không vội sửa Jackson DTO khi vấn đề thực ra là converter order.

## 18. Validation diễn ra sau khi converter đọc DTO

Converter Jackson chịu trách nhiệm chuyển đổi JSON thành object. Bean Validation là bước riêng, thường được kích hoạt khi controller đặt `@Valid` hoặc `@Validated` phù hợp.

~~~java
public class CreateOrderRequest {
    @NotBlank
    private String customerId;

    @Min(1)
    @Max(100)
    private int quantity;

    // Getter và setter.
}
~~~

Controller:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
public OrderResponse create(
        @Valid @RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

Luồng:

~~~text
JSON bytes
   |
   v
Jackson converter
   |
   v
CreateOrderRequest
   |
   v
Bean Validation
   |
   +--> valid --> controller method
   |
   +--> invalid --> validation exception
~~~

Nếu JSON sai cú pháp hoặc mapping thất bại, Bean Validation chưa có object hợp lệ để kiểm tra. Nếu JSON hợp lệ nhưng `quantity` bằng 0, validation mới phát hiện lỗi.

Không dùng `FAIL_ON_UNKNOWN_PROPERTIES` thay cho validation. Unknown property policy quyết định cách xử lý field không nhận diện; validation kiểm tra dữ liệu đã ánh xạ có thỏa điều kiện hay không.

## 19. Phân biệt lỗi chuyển đổi và lỗi nghiệp vụ

Các lỗi có thể xuất hiện ở những giai đoạn khác nhau:

| Tình huống | Giai đoạn | Phản hồi HTTP thường gặp |
|---|---|---|
| JSON sai cú pháp | Jackson converter đọc request | 400 Bad Request |
| JSON không map được kiểu DTO | Jackson converter đọc request | 400 Bad Request |
| Request thiếu Content-Type phù hợp | Converter selection | 415 Unsupported Media Type |
| Client yêu cầu media type không được hỗ trợ | Content negotiation | 406 Not Acceptable |
| DTO vi phạm Bean Validation | Validation sau deserialize | 400 Bad Request |
| Quy tắc nghiệp vụ từ chối thao tác | Service/domain | Tùy API contract, ví dụ 409 hoặc 422 |
| Serialize response thất bại | Converter ghi response | Lỗi server; response có thể đã bắt đầu |

Mã HTTP cuối cùng phụ thuộc cấu hình exception handling và hợp đồng API. Bảng trên là hướng thiết kế phổ biến, không phải bảo đảm mọi ứng dụng tự động trả đúng các mã này.

## 20. Xử lý lỗi bằng @RestControllerAdvice

Jackson parse lỗi thường được Spring bọc trong `HttpMessageNotReadableException`. Lỗi ghi response có thể được biểu diễn bằng `HttpMessageNotWritableException`. Có thể xử lý lỗi đầu vào ở một nơi:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> handleUnreadable(
            HttpMessageNotReadableException exception) {

        ApiError error = new ApiError(
            "INVALID_REQUEST_BODY",
            "The request body is invalid"
        );

        return ResponseEntity.badRequest().body(error);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception) {

        ApiError error = new ApiError(
            "VALIDATION_FAILED",
            "One or more request fields are invalid"
        );

        return ResponseEntity.badRequest().body(error);
    }
}

public record ApiError(String code, String message) {
}
~~~

Không trả `exception.getMessage()`, cause hoặc stack trace trực tiếp cho client. Message từ parser có thể chứa tên property, dữ liệu đầu vào hoặc chi tiết triển khai nội bộ. Nếu cần chẩn đoán, ghi log có kiểm soát với request ID và exception object ở boundary phù hợp.

Lỗi `HttpMediaTypeNotSupportedException` và `HttpMediaTypeNotAcceptableException` có thể được xử lý riêng nếu API muốn một error schema nhất quán cho 415 và 406.

## 21. Giữ exception gốc trong log

Converter có thể bọc lỗi Jackson thành exception của Spring. Khi log ở boundary, hãy truyền exception object để giữ cause chain:

~~~java
logger.warn(
    "Could not read request body; requestId={}",
    requestId,
    exception
);
~~~

Không chỉ ghi:

~~~java
logger.warn("Could not read request body: {}", exception.getMessage());
~~~

Cách thứ hai thường bỏ mất stack trace và nguyên nhân kỹ thuật. Tuy nhiên, không log cùng một stack trace ở mọi tầng; chọn boundary chịu trách nhiệm ghi log đầy đủ để tránh log trùng.

Không ghi raw request body nếu nó có thể chứa password, token, dữ liệu cá nhân hoặc payload rất lớn. Request ID, endpoint, media type, loại lỗi và parser location thường hữu ích hơn.

## 22. Cấu hình giới hạn đọc cho request JSON

Converter Jackson sử dụng `ObjectMapper` và `JsonFactory` bên dưới. Có thể đặt `StreamReadConstraints` để giới hạn nesting depth, string length và number length ở những phiên bản Jackson hỗ trợ:

~~~java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(32)
    .maxStringLength(65_536)
    .maxNumberLength(128)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Nếu mapper này được dùng bởi converter, các giới hạn parser áp dụng cho request mà converter đọc. Hãy tích hợp mapper vào cấu hình Spring Boot hoặc converter theo extension point phù hợp.

Các giới hạn này không giới hạn tổng byte request, số phần tử array, số request đồng thời hoặc thời gian xử lý. Những giới hạn đó cần được đặt ở proxy/server, upload boundary, service, executor hoặc stream wrapper.

Đừng tạo một mapper mới cho mỗi request để áp dụng quota. Cấu hình một mapper/converter theo policy và tái sử dụng.

## 23. Bảo mật khi deserialize request

HTTP request là dữ liệu không tin cậy. Converter Jackson là ranh giới nơi dữ liệu bên ngoài đi vào object Java; vì vậy cấu hình deserialize cần được xem xét như một phần của bảo mật API.

Một số nguyên tắc:

- Dùng request DTO chuyên biệt thay vì deserialize trực tiếp vào JPA entity hoặc object nội bộ.
- Chỉ công khai các field client được phép gửi.
- Không bật polymorphic default typing toàn cục cho payload không tin cậy.
- Nếu dùng polymorphic deserialization, giới hạn subtype bằng allowlist hoặc thiết kế type discriminator rõ ràng.
- Cấu hình unknown property policy theo hợp đồng.
- Dùng validation cho field bắt buộc, range và format.
- Giới hạn nesting, string và number token.
- Giới hạn tổng byte request ở HTTP layer.
- Không log hoặc trả raw payload và stack trace.
- Không để field client gửi trực tiếp quyết định role, owner, balance hoặc quyền truy cập.

Converter chỉ thực hiện data binding; nó không thay thế authorization. Một DTO deserialize thành công vẫn phải được xác thực quyền trước khi service thực hiện thay đổi dữ liệu.

## 24. Hiệu năng và streaming qua converter

`MappingJackson2HttpMessageConverter` làm việc với stream HTTP và Jackson parser/generator. Nó không cần tạo một chuỗi JSON trung gian cho mọi request/response theo cách gọi `writeValueAsString()` rồi ghi chuỗi ra socket.

Tuy nhiên, cần phân biệt stream serialization với dữ liệu nguồn đã được materialize:

~~~java
@GetMapping("/orders")
public List<OrderResponse> list() {
    return orderService.findAll();
}
~~~

Converter có thể serialize danh sách ra response stream, nhưng `List<OrderResponse>` đã tồn tại trong bộ nhớ trước khi converter ghi. Việc dùng converter không tự biến một collection lớn thành database cursor hoặc stream có giới hạn bộ nhớ.

Với export rất lớn, có thể dùng `StreamingResponseBody` để tạo response theo luồng:

~~~java
@GetMapping(
    value = "/orders/export",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public StreamingResponseBody export() {
    return output -> {
        try (JsonGenerator generator =
                objectMapper.getFactory().createGenerator(output);
             Stream<Order> orders = orderService.streamOrders()) {

            generator.writeStartArray();

            for (Order order : (Iterable<Order>) orders::iterator) {
                objectMapper.writeValue(generator, order);
            }

            generator.writeEndArray();
            generator.flush();
        }
    };
}
~~~

Đây là ví dụ minh họa. Trong ứng dụng thực tế, cần kiểm tra ownership của servlet output stream, transaction/cursor của nguồn dữ liệu, exception sau khi response đã bắt đầu và cách container quản lý việc đóng stream. Có thể dùng `SequenceWriter` thay cho vòng lặp generator nếu muốn phát các object cùng kiểu theo sequence.

Khi stream response, lỗi xảy ra sau khi một phần body đã được gửi có thể khiến client nhận JSON không hoàn chỉnh. Nếu cần bảo đảm output hoàn chỉnh trước khi công bố, hãy ghi vào file/object storage tạm rồi trả link sau khi export thành công.

## 25. Converter và multipart/form-data

`MappingJackson2HttpMessageConverter` chuyên xử lý body JSON. Nó không thay thế converter cho multipart form upload.

Một endpoint multipart có thể nhận metadata JSON trong một part và file trong part khác:

~~~java
@PostMapping(
    value = "/imports",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ImportResponse importFile(
        @RequestPart("metadata") ImportMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    return importService.importFile(metadata, file);
}
~~~

Spring sử dụng cơ chế multipart resolver để tách các part. Part `metadata` có thể được chuyển đổi qua message converter Jackson nếu media type và kiểu Java phù hợp. Part `file` được xử lý như dữ liệu multipart/resource theo abstraction tương ứng.

Cần giới hạn kích thước upload ở servlet/container, Spring Boot multipart properties và hạ tầng proxy. `StreamReadConstraints` chỉ kiểm soát một số đặc tính JSON bên trong part metadata; nó không giới hạn kích thước file upload.

## 26. Kiểm thử converter trong Spring MVC

Unit test DTO hoặc `ObjectMapper` không chứng minh Spring MVC đã chọn đúng converter. Nên có MVC test kiểm tra toàn bộ request/response path.

Ví dụ với MockMvc:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @Test
    void readsJsonRequestAndWritesJsonResponse() throws Exception {
        given(orderService.create(any()))
            .willReturn(new OrderResponse("ORD-1", "CREATED"));

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "customerId": "CUS-100",
                      "quantity": 2
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ))
            .andExpect(jsonPath("$.id").value("ORD-1"))
            .andExpect(jsonPath("$.status").value("CREATED"));
    }
}
~~~

Test này xác nhận controller nhận request JSON và trả response JSON qua cấu hình MVC test. Với endpoint trả `201 Created`, hãy assert status tương ứng thay vì `isOk()`.

Bổ sung test cho:

- JSON sai cú pháp trả 400 theo error contract.
- `Content-Type` không hỗ trợ trả 415.
- `Accept` không tương thích trả 406.
- Validation thất bại trả error schema đúng.
- Vendor media type được chấp nhận khi endpoint công bố.
- Mapper custom được converter sử dụng.
- Date/time, enum, naming strategy và null policy đúng.
- Generic response giữ đúng kiểu phần tử.
- Response không lộ stack trace hoặc cause.

## 27. Kiểm thử trực tiếp converter

Khi cần cô lập converter, có thể tạo `MappingJackson2HttpMessageConverter` và dùng `MockHttpInputMessage`/`MockHttpOutputMessage` của Spring test.

Ví dụ đọc:

~~~java
@Test
void jacksonConverterReadsJson() throws Exception {
    ObjectMapper mapper = new ObjectMapper();
    MappingJackson2HttpMessageConverter converter =
        new MappingJackson2HttpMessageConverter(mapper);

    MockHttpInputMessage input = new MockHttpInputMessage(
        """
        {"customerId":"CUS-1","quantity":2}
        """.getBytes(StandardCharsets.UTF_8)
    );

    input.getHeaders().setContentType(MediaType.APPLICATION_JSON);

    CreateOrderRequest request = (CreateOrderRequest)
        converter.read(CreateOrderRequest.class, input);

    assertEquals("CUS-1", request.getCustomerId());
    assertEquals(2, request.getQuantity());
}
~~~

Ví dụ ghi:

~~~java
@Test
void jacksonConverterWritesJson() throws Exception {
    MappingJackson2HttpMessageConverter converter =
        new MappingJackson2HttpMessageConverter(new ObjectMapper());

    OrderResponse response = new OrderResponse("ORD-1", "CREATED");
    MockHttpOutputMessage output = new MockHttpOutputMessage();

    converter.write(response, MediaType.APPLICATION_JSON, output);

    String json = output.getBodyAsString(StandardCharsets.UTF_8);

    assertTrue(json.contains("\"id\":\"ORD-1\""));
}
~~~

Test trực tiếp hữu ích cho hành vi converter và media type. MVC test vẫn cần thiết để xác nhận converter được Spring chọn đúng trong danh sách thực tế.

Các method và overload cụ thể có thể khác nhẹ giữa các phiên bản Spring Framework; hãy điều chỉnh theo API của dependency dự án.

## 28. Khi nào cần custom HttpMessageConverter?

Không cần tạo custom converter chỉ vì muốn đổi một annotation hoặc format ngày. Hãy tận dụng `ObjectMapper`, Jackson module, serializer/deserializer hoặc cấu hình media type trước.

Custom converter phù hợp khi:

- Định dạng không được converter mặc định hỗ trợ.
- Protocol yêu cầu framing hoặc envelope riêng.
- Cần đọc/ghi một kiểu đặc biệt qua HTTP abstraction.
- Cần kiểm soát chính sách parse/serialize khác biệt rõ ràng.
- Cần tích hợp thư viện định dạng khác Jackson.

Nếu custom converter chỉ bọc `ObjectMapper.readValue()` và `writeValue()` nhưng không xử lý đúng media type, charset, generic type, stream ownership hoặc lỗi I/O, nó có thể làm mất những hành vi Spring đã cung cấp.

Khi triển khai `HttpMessageConverter`, cần định nghĩa `canRead`, `canWrite`, supported media types, read và write một cách nhất quán. Cân nhắc generic type nếu converter phải hỗ trợ `List<T>` hoặc wrapper generic.

## 29. Những hiểu lầm thường gặp

### Nghĩ @RequestBody tự gọi Jackson trực tiếp

Spring MVC chọn converter phù hợp; converter Jackson mới gọi Databind. Việc chọn converter còn phụ thuộc media type và kiểu Java.

### Nghĩ ObjectMapper bean tự động được dùng ở mọi nơi

Converter có thể được cấu hình bằng mapper khác, đặc biệt khi ứng dụng đăng ký nhiều converter. Hãy kiểm tra mapper mà converter thực tế giữ.

### Nhầm Content-Type với Accept

Content-Type mô tả request body; Accept mô tả response client muốn nhận. Hai header ảnh hưởng hai chiều converter khác nhau.

### Tạo ObjectMapper mới trong controller

Mapper mới có thể thiếu module, naming strategy, customizer và parser constraints. Inject mapper đã được cấu hình hoặc để converter mặc định sử dụng mapper của ứng dụng.

### Đăng ký custom converter ở đầu danh sách mà không giới hạn media type

Converter tổng quát có thể chiếm request/response của converter chuyên biệt. Kiểm tra `canRead`, `canWrite` và thứ tự.

### Nghĩ converter làm collection lớn trở thành streaming nguồn

Converter ghi JSON ra stream, nhưng `List` trả về từ service vẫn có thể được materialize hoàn toàn. Dùng cursor/stream và `StreamingResponseBody` khi cần nguồn dữ liệu streaming.

### Nghĩ converter tự chạy Bean Validation

Deserialize và validation là hai bước khác nhau. Dùng `@Valid` hoặc validation logic rõ ràng.

### Trả lỗi Jackson thô cho client

Message parser có thể lộ chi tiết nội bộ hoặc dữ liệu đầu vào. Dùng error code/message ổn định và log cause nội bộ có kiểm soát.

### Dùng configureMessageConverters cho một thay đổi nhỏ

Có thể vô tình thay đổi danh sách converter mặc định. Nếu chỉ muốn chỉnh converter có sẵn, xem xét `extendMessageConverters`.

### Nghĩ multipart file cũng do Jackson converter đọc

Multipart được xử lý bởi cơ chế multipart; Jackson có thể xử lý part JSON riêng, không phải nội dung file nói chung.

## 30. Quy trình làm việc với Jackson HTTP message converter

1. Xác định endpoint nhận hoặc trả kiểu Java nào.
2. Xác định `Content-Type`, `Accept`, `consumes` và `produces`.
3. Xác nhận converter nào hỗ trợ kiểu và media type đó.
4. Kiểm tra thứ tự converter khi có nhiều converter tương thích.
5. Xác định `ObjectMapper` thực sự được converter sử dụng.
6. Cấu hình module, naming, date/time, null, enum và unknown property policy ở mapper phù hợp.
7. Dùng DTO request/response chuyên biệt và validation sau deserialize.
8. Đặt giới hạn parser và giới hạn tổng request ở đúng tầng.
9. Chuyển lỗi parse/validation sang response công khai ổn định.
10. Không lộ cause, stack trace hoặc raw payload cho client.
11. Dùng `extendMessageConverters` khi chỉ cần chỉnh converter mặc định; dùng cấu hình danh sách đầy đủ khi thật sự muốn kiểm soát toàn bộ.
12. Khi thêm converter, giới hạn media type và kiểm tra thứ tự.
13. Dùng `StreamingResponseBody` hoặc protocol xuất riêng khi dữ liệu response quá lớn để materialize.
14. Kiểm thử bằng MockMvc để xác nhận toàn bộ MVC conversion path.
15. Kiểm tra cả status code, media type, body, mapper custom và trường hợp lỗi.

## 31. Bảng ghi nhớ

| Nhu cầu | Thành phần/cách làm |
|---|---|
| Chuyển HTTP body thành object | `HttpMessageConverter` |
| JSON bằng Jackson 2 | `MappingJackson2HttpMessageConverter` |
| Đọc tham số controller | `@RequestBody` |
| Ghi return value | `@ResponseBody`, `@RestController` |
| Kiểm soát status/header/body | `ResponseEntity<T>` |
| Xác định định dạng request | `Content-Type` |
| Thương lượng định dạng response | `Accept`, `produces` |
| Tùy chỉnh mapper trong Boot | `Jackson2ObjectMapperBuilderCustomizer` |
| Thay đổi converter mặc định | `WebMvcConfigurer.extendMessageConverters` |
| Tự kiểm soát danh sách converter | `configureMessageConverters` |
| Validate DTO sau deserialize | `@Valid` và Bean Validation |
| Xử lý lỗi parse | `HttpMessageNotReadableException` |
| Xử lý lỗi serialize | `HttpMessageNotWritableException` |
| Test toàn bộ MVC conversion | MockMvc / `@WebMvcTest` |
| Test riêng converter | `MockHttpInputMessage`, `MockHttpOutputMessage` |
| Response rất lớn | Cursor/stream và `StreamingResponseBody` |

## 32. Kết luận

HTTP message converter là cầu nối giữa byte của HTTP và object Java trong Spring MVC. `MappingJackson2HttpMessageConverter` dùng `ObjectMapper` để đọc JSON cho `@RequestBody` và ghi JSON cho `@ResponseBody` hoặc `ResponseEntity`. Spring chọn converter dựa trên kiểu dữ liệu, `Content-Type`, `Accept`, media type của endpoint và thứ tự converter đã đăng ký.

Hãy cấu hình mapper dùng chung qua cơ chế Spring Boot phù hợp, kiểm tra converter thực sự đang dùng mapper nào, và chỉ thêm converter chuyên biệt khi có hợp đồng media type hoặc định dạng riêng. Tách parsing khỏi Bean Validation và nghiệp vụ; xử lý lỗi bằng response ổn định; đặt giới hạn tài nguyên ở parser lẫn HTTP/application layer; và kiểm thử bằng MockMvc để xác nhận toàn bộ luồng request/response. Với dữ liệu lớn, nhớ rằng converter có thể ghi ra stream nhưng không tự biến một collection đã materialize thành nguồn streaming.
