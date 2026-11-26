# Lỗi serialization

## Mục tiêu

Trong Spring MVC, controller thường trả về DTO, EntityModel, CollectionModel hoặc PagedModel. Trước khi gửi response, HTTP message converter dùng Jackson để chuyển object thành JSON hoặc HAL JSON. Nếu object graph chứa kiểu dữ liệu Jackson không xử lý được, có vòng tham chiếu, proxy persistence hoặc cấu hình hypermedia không phù hợp, quá trình ghi response có thể thất bại.

Lỗi thường xuất hiện dưới dạng HttpMessageNotWritableException ở tầng Spring MVC, nhưng nguyên nhân gốc thường nằm sâu hơn trong exception của Jackson hoặc persistence provider. Muốn sửa đúng, cần đọc exception gốc và xác định object/property cụ thể gây lỗi.

Sau bài học, bạn có thể:

- Nhận diện lỗi serialization trong luồng trả response của Spring MVC.
- Phân biệt lỗi thiếu serializer, vòng tham chiếu, lazy proxy và lỗi module Jackson.
- Tránh serialize trực tiếp entity JPA trong representation HATEOAS.
- Cấu hình Jackson và Spring HATEOAS đúng cách.
- Xử lý các kiểu ngày giờ, custom type và thuộc tính không cần công khai.
- Kiểm thử JSON/HAL response để phát hiện lỗi trước khi triển khai.

## Serialization xảy ra ở đâu?

Controller không nhất thiết tự tạo chuỗi JSON. Khi controller trả một object, Spring MVC chọn HttpMessageConverter phù hợp với kiểu response và media type mà client yêu cầu. Với JSON, converter thường dùng Jackson ObjectMapper để duyệt các property và ghi chúng thành JSON.

Luồng đơn giản:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Controller]
    B --> C[Service và assembler]
    C --> D[DTO hoặc RepresentationModel]
    D --> E[Spring HttpMessageConverter]
    E --> F[Jackson ObjectMapper]
    F --> G[JSON hoặc HAL JSON]
    G --> H[HTTP response]
~~~

Nếu Jackson không thể serialize một property, lỗi xảy ra khi response được ghi. Vì vậy, controller có thể đã chạy xong và service đã trả dữ liệu, nhưng client vẫn nhận lỗi HTTP do bước serialization thất bại.

Trong Spring MVC, exception bên ngoài có thể là HttpMessageNotWritableException. Hãy xem nguyên nhân lồng bên trong:

- InvalidDefinitionException: Jackson không có cách serialize kiểu dữ liệu hoặc cấu trúc được khai báo.
- JsonMappingException: lỗi khi ánh xạ một property hoặc nhánh cụ thể của object graph.
- StackOverflowError hoặc lỗi phát hiện vòng lặp: object graph tham chiếu qua lại.
- LazyInitializationException: serializer truy cập quan hệ JPA lazy khi persistence context đã đóng.

Đừng chỉ đọc dòng đầu tiên của stack trace. Thông tin như tên class, property path và nguyên nhân lồng bên trong thường chỉ ra chính xác trường gây lỗi.

## Lỗi không tìm thấy serializer

Một lỗi phổ biến có dạng:

~~~text
InvalidDefinitionException:
No serializer found for class ... and no properties discovered
to create BeanSerializer
~~~

Jackson đã gặp một object nhưng không tìm thấy property có thể serialize. Nguyên nhân thường gặp:

- Class không có public getter và không phải record có component được Jackson nhận diện.
- Field bị ẩn theo visibility configuration.
- Kiểu trả về là một object rỗng hoặc wrapper tùy biến không có property được công bố.
- Một thư viện hoặc kiểu đặc biệt cần Jackson module riêng.
- Ứng dụng dùng ObjectMapper tự tạo, thiếu module mà mapper do Spring Boot hoặc Spring HATEOAS cung cấp.

Ví dụ class không có getter:

~~~java
public class OrderResponse {

    private final String id;
    private final String status;

    public OrderResponse(String id, String status) {
        this.id = id;
        this.status = status;
    }
}
~~~

Jackson có thể không nhìn thấy property theo visibility mặc định. Hãy công bố getter hoặc dùng record:

~~~java
public record OrderResponse(String id, String status) {
}
~~~

Nếu tên property hoặc visibility cần tùy chỉnh, dùng annotation Jackson như JsonProperty hoặc cấu hình visibility có chủ đích. Không nên thay đổi visibility toàn cục chỉ để một class lỗi được serialize, vì có thể vô tình làm lộ field nội bộ của các response khác.

Không nên xử lý nhanh bằng cách tắt SerializationFeature.FAIL_ON_EMPTY_BEANS cho toàn ứng dụng. Cấu hình này có thể biến lỗi rõ ràng thành JSON rỗng hoặc object không có dữ liệu hữu ích, khiến lỗi hợp đồng API khó phát hiện hơn. Hãy sửa class hoặc serializer thực sự cần thiết.

## Vòng tham chiếu vô hạn trong object graph

Jackson duyệt object graph theo các property có thể serialize. Entity JPA có quan hệ hai chiều thường tạo chu trình:

~~~text
Customer
  -> orders
      -> customer
          -> orders
              -> customer
                  ...
~~~

Ví dụ:

~~~java
class Customer {
    private List<Order> orders;
}

class Order {
    private Customer customer;
}
~~~

Nếu cả hai chiều đều được serialize, Jackson có thể lặp vô hạn và gây StackOverflowError hoặc lỗi phát hiện self-reference.

### Ưu tiên DTO cho response

Trong API HATEOAS, nên chuyển entity thành DTO hoặc representation model trước khi serialize. DTO chỉ chứa dữ liệu cần công bố và không giữ tham chiếu ngược tới toàn bộ object graph persistence:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        int orderCount) {
}

public record OrderSummary(
        Long id,
        String status,
        String customerName) {
}
~~~

Assembler lấy dữ liệu cần thiết từ entity và tạo representation:

~~~java
EntityModel<OrderSummary> toModel(Order order) {
    OrderSummary response = new OrderSummary(
            order.getId(),
            order.getStatus().name(),
            order.getCustomer().getName());

    return EntityModel.of(response)
            .add(linkTo(methodOn(OrderController.class)
                    .findById(order.getId())).withSelfRel());
}
~~~

Client điều hướng qua links hypermedia thay vì nhận toàn bộ object graph entity. Đây cũng là cách kiểm soát trường dữ liệu được công khai.

### Khi buộc phải serialize quan hệ hai chiều

Jackson có các annotation để quản lý tham chiếu:

- JsonManagedReference đánh dấu chiều được serialize.
- JsonBackReference đánh dấu chiều ngược lại không được serialize như một object lồng nữa.
- JsonIdentityInfo cho phép biểu diễn object bằng định danh để xử lý tham chiếu lặp.
- JsonIgnore có thể loại bỏ property khỏi JSON khi quan hệ ngược không cần công bố.

Ví dụ:

~~~java
class Customer {

    @JsonManagedReference
    private List<Order> orders;
}

class Order {

    @JsonBackReference
    private Customer customer;
}
~~~

Các annotation này hữu ích trong một số mô hình serialization, nhưng chúng gắn chặt entity với định dạng JSON. Với REST API có hợp đồng riêng và links HATEOAS, DTO/model response thường dễ kiểm soát và tiến hóa hơn.

## LazyInitializationException khi Jackson truy cập entity

Một response có thể gặp lỗi:

~~~text
LazyInitializationException:
could not initialize proxy - no Session
~~~

Lỗi này thường xuất hiện khi Jackson gọi getter của một quan hệ lazy sau khi transaction hoặc persistence context đã đóng. Ví dụ controller trả entity trực tiếp, rồi serializer đọc order.getLines() để tạo JSON. Việc truy cập getter lúc serialize kích hoạt lazy loading ngoài session.

Không nên coi việc bật Open Session in View là cách sửa mặc định. Cách đó có thể che giấu truy vấn phát sinh trong quá trình serialize và khiến response tạo nhiều SQL không dự đoán được.

Hãy tải đúng dữ liệu trong service và chuyển sang DTO khi persistence context còn hoạt động:

~~~java
@Transactional(readOnly = true)
public OrderDetailResponse getOrder(UUID id) {
    Order order = repository.findDetailById(id)
            .orElseThrow(OrderNotFoundException::new);

    return OrderDetailResponse.from(
            order,
            order.getLines().stream()
                    .map(OrderLineResponse::from)
                    .toList());
}
~~~

Repository có thể dùng fetch join, EntityGraph hoặc projection tùy truy vấn. Mục tiêu là nạp dữ liệu cần cho response một cách có chủ đích, sau đó serialize DTO không phụ thuộc session.

Nếu dùng assembler, thực hiện việc ánh xạ trong service transaction hoặc bảo đảm dữ liệu cần thiết đã được tải trước khi transaction kết thúc. Đừng để Jackson quyết định lúc nào phải truy vấn database.

## Lỗi với ngày giờ và kiểu dữ liệu đặc biệt

Jackson cần module phù hợp để serialize một số kiểu dữ liệu. Ví dụ, Java Time API có LocalDate, LocalDateTime, OffsetDateTime và Instant. Nếu thiếu Java Time module, có thể gặp InvalidDefinitionException thông báo kiểu java.time chưa được hỗ trợ.

Với Jackson 2, module tương ứng là jackson-datatype-jsr310 và JavaTimeModule:

~~~xml
<dependency>
    <groupId>com.fasterxml.jackson.datatype</groupId>
    <artifactId>jackson-datatype-jsr310</artifactId>
</dependency>
~~~

Trong ứng dụng Spring Boot, dependency và Jackson auto-configuration thường giúp đăng ký module phù hợp. Nếu tự tạo ObjectMapper, hãy bảo đảm mapper đó đăng ký JavaTimeModule hoặc được xây dựng từ cấu hình Jackson do Spring quản lý.

Có thể định dạng property cụ thể bằng JsonFormat:

~~~java
public record OrderResponse(
        UUID id,
        @JsonFormat(pattern = "yyyy-MM-dd")
        LocalDate expectedDeliveryDate) {
}
~~~

Chỉ dùng JsonFormat khi hợp đồng yêu cầu định dạng cụ thể. Với timestamp có múi giờ, chọn kiểu như OffsetDateTime hoặc Instant phù hợp với ý nghĩa dữ liệu; không biến timestamp thành chuỗi tùy ý chỉ để tránh lỗi serializer.

Các kiểu thư viện khác như tiền tệ, geometry hoặc custom value object cũng có thể cần module hay serializer riêng. Hãy kiểm tra dependency, module đã đăng ký và định dạng JSON mà client cần.

## Cấu hình Jackson và Spring HATEOAS

Spring HATEOAS dùng Jackson module và cấu hình riêng để serialize Link, RepresentationModel, HAL links và embedded resources. Nếu ứng dụng dùng Spring Boot với starter HATEOAS, ưu tiên cấu hình auto-configuration của framework.

Với ứng dụng cấu hình Spring MVC thủ công, bật hypermedia support:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.config.EnableHypermediaSupport;
import org.springframework.hateoas.config.EnableHypermediaSupport.HypermediaType;

@Configuration
@EnableHypermediaSupport(type = HypermediaType.HAL)
class HypermediaConfiguration {
}
~~~

Khi cấu hình này được bật, Spring HATEOAS đăng ký các thành phần cần thiết cho HAL serialization. Trong Spring Boot, starter HATEOAS thường tự cấu hình hypermedia support; hãy kiểm tra cấu hình hiện tại trước khi thêm một ObjectMapper hoặc cấu hình hypermedia thứ hai.

Một lỗi thường gặp là tự tạo ObjectMapper bằng new ObjectMapper() rồi dùng mapper đó để serialize response. Mapper độc lập có thể thiếu JavaTimeModule, module HATEOAS, naming strategy, custom serializer hoặc các thiết lập do Spring Boot quản lý.

Ví dụ không nên tự serialize trong controller:

~~~java
// Tránh cách làm này trong controller.
String json = new ObjectMapper().writeValueAsString(model);
return ResponseEntity.ok(json);
~~~

Hãy trả object representation và để Spring MVC chọn message converter:

~~~java
@GetMapping(
        value = "/api/orders/{id}",
        produces = "application/hal+json")
EntityModel<OrderResponse> findById(@PathVariable UUID id) {
    return assembler.toModel(orderService.findById(id));
}
~~~

Nếu cần tùy chỉnh Jackson, ưu tiên các cơ chế cấu hình mà Spring Boot/Spring Framework cung cấp như builder customizer, module bean hoặc serializer bean. Tránh thay thế hoàn toàn ObjectMapper đã được framework cấu hình trừ khi bạn chủ động đăng ký lại tất cả module và thành phần cần thiết.

## Kiểm tra content negotiation và HAL media type

Một response có links nhưng không xuất hiện _links có thể do client yêu cầu media type không phù hợp hoặc endpoint đang trả JSON thông thường.

HAL JSON dùng media type application/hal+json. Trong test, có thể yêu cầu media type bằng MediaTypes.HAL_JSON:

~~~java
mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$._links.self.href").exists());
~~~

Nếu endpoint khai báo produces, bảo đảm media type đó tương thích với Accept của client. Nếu ứng dụng hỗ trợ cả application/json và application/hal+json, kiểm thử từng representation để xác định đúng converter và serializer được dùng.

Đừng kiểm tra HAL bằng cách gọi ObjectMapper mới trong một unit test đơn giản rồi kết luận cấu hình HTTP đã đúng. Kiểm thử qua MockMvc hoặc WebTestClient xác nhận cả content negotiation, message converter và hypermedia serialization.

## Thuộc tính không cần công khai và custom serializer

Một số lỗi hoặc dữ liệu ngoài ý muốn xuất hiện vì response chứa property không nên serialize:

- Trường mật khẩu, token hoặc dữ liệu nội bộ.
- Proxy, session hoặc object từ thư viện không thuộc hợp đồng API.
- Quan hệ entity lớn hoặc có vòng tham chiếu.
- Custom type chưa có serializer phù hợp.

Dùng DTO để xác định chính xác response shape. Với property cần loại khỏi JSON, có thể dùng JsonIgnore hoặc JsonProperty(access = JsonProperty.Access.WRITE_ONLY/READ_ONLY) tùy mục đích. Không dùng annotation chỉ để che một lỗi lazy loading nếu nguyên nhân gốc là response đang serialize entity không phù hợp.

Khi thực sự cần một kiểu custom, viết JsonSerializer và đăng ký qua Jackson module hoặc cơ chế cấu hình Spring:

~~~java
public class MoneySerializer extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money value,
            JsonGenerator generator,
            SerializerProvider serializers) throws IOException {

        generator.writeStartObject();
        generator.writeStringField("currency", value.currencyCode());
        generator.writeNumberField("amount", value.amount());
        generator.writeEndObject();
    }
}
~~~

Serializer cần có định dạng ổn định và được kiểm thử độc lập. Chỉ tạo custom serializer khi DTO hoặc serializer có sẵn không đáp ứng được hợp đồng JSON cần công bố.

## Quy trình chẩn đoán lỗi serialization

1. Xác định lỗi xảy ra ở response nào, media type nào và property nào.
2. Đọc exception gốc và property path trong JsonMappingException/InvalidDefinitionException.
3. Nếu không tìm thấy serializer, kiểm tra getter, record component, visibility và module cho kiểu đặc biệt.
4. Nếu có vòng lặp, kiểm tra quan hệ hai chiều và chuyển entity thành DTO hoặc cấu hình identity/reference phù hợp.
5. Nếu gặp LazyInitializationException, tải dữ liệu trong service transaction và ánh xạ DTO trước khi trả response.
6. Nếu HAL links hoặc embedded resources biến mất, kiểm tra ObjectMapper do Spring quản lý, hypermedia support và Accept header.
7. Viết test HTTP xác nhận status, content type, dữ liệu, links và embedded resources.

## Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| No serializer found for class | Không có property Jackson nhìn thấy hoặc thiếu serializer/module. | Thêm getter/record component, JsonProperty hoặc module phù hợp. |
| Infinite recursion / StackOverflowError | Quan hệ hai chiều hoặc object graph có chu trình. | Trả DTO; cân nhắc JsonManagedReference/JsonBackReference hoặc JsonIdentityInfo nếu phù hợp. |
| LazyInitializationException | Jackson truy cập quan hệ lazy sau khi session đóng. | Fetch dữ liệu cần thiết trong service và ánh xạ DTO. |
| Java time type not supported | Thiếu JavaTimeModule hoặc mapper tùy chỉnh không đăng ký module. | Thêm jackson-datatype-jsr310 và dùng mapper được cấu hình đúng. |
| _links hoặc _embedded không xuất hiện | Sai media type, thiếu HATEOAS module hoặc dùng ObjectMapper độc lập. | Bật hypermedia support và kiểm tra Accept/content type. |
| Thuộc tính nhạy cảm xuất hiện trong JSON | Response serialize entity hoặc object có quá nhiều field. | Tạo DTO, dùng JsonIgnore/JsonProperty có chủ đích. |
| Custom type serialize sai định dạng | Jackson không có serializer phù hợp hoặc serializer không đúng hợp đồng. | Viết và đăng ký JsonSerializer, sau đó kiểm thử JSON. |

## Kiểm thử response serialization

Một test tích hợp nên xác minh cả dữ liệu và hypermedia:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
        .andExpect(jsonPath("$.id").value(orderId.toString()))
        .andExpect(jsonPath("$.expectedDeliveryDate").exists())
        .andExpect(jsonPath("$._links.self.href").exists());
~~~

Với collection, kiểm tra _embedded và link collection. Với response có ngày giờ, kiểm tra định dạng theo hợp đồng. Với entity có quan hệ hai chiều, kiểm tra response không chứa object graph lặp hoặc trường persistence không được công khai.

Khi cần kiểm thử custom serializer, có thể kiểm tra JSON được tạo từ ObjectMapper trong Spring application context. Dùng đúng mapper được cấu hình trong ứng dụng, không tạo mapper mới chỉ cho test vì như vậy test có thể bỏ qua lỗi cấu hình production.

## Kết luận

Phần lớn lỗi serialization trong API HATEOAS xuất phát từ object graph được trả về, module Jackson chưa được cấu hình hoặc media type không phù hợp. Hãy giữ response model tách khỏi entity persistence, tải dữ liệu cần thiết trước khi serialize, dùng ObjectMapper do Spring quản lý và kiểm thử qua HTTP converter. Khi xác định đúng exception gốc và property gây lỗi, việc sửa serialization sẽ có mục tiêu rõ ràng và hợp đồng JSON/HAL ổn định hơn.

## Tài liệu tham khảo

- Spring Framework Reference Documentation, HTTP message conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html
- Spring HATEOAS Reference Documentation: https://docs.spring.io/spring-hateoas/docs/current/reference/html/
- Jackson Databind documentation: https://github.com/FasterXML/jackson-databind
- Jackson Java 8 date/time module: https://github.com/FasterXML/jackson-modules-java8
