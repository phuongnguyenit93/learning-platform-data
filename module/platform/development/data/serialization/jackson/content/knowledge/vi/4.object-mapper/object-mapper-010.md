# Tách cấu hình thư viện khỏi logic nghiệp vụ

`ObjectMapper` là trung tâm của Jackson Databind: nó đọc JSON thành dữ liệu Java và ghi dữ liệu Java thành JSON. Trong ứng dụng nhỏ, việc tạo một `ObjectMapper` ngay tại nơi cần chuyển đổi có vẻ thuận tiện. Nhưng khi ứng dụng phát triển, nhiều nơi có thể cần cùng một quy ước về ngày giờ, tên thuộc tính, giá trị `null`, trường không xác định, enum hoặc cách xử lý kiểu dữ liệu đặc thù. Nếu mỗi service tự tạo và cấu hình mapper, hành vi chuyển đổi sẽ phân tán và khó kiểm soát.

Một thiết kế dễ bảo trì đặt cấu hình Jackson ở ranh giới hạ tầng, hoàn tất cấu hình khi ứng dụng khởi động, sau đó cung cấp mapper hoặc các đối tượng đọc/ghi đã cấu hình cho thành phần cần dùng. Logic nghiệp vụ tập trung vào quy tắc của miền: kiểm tra dữ liệu, quyết định trạng thái, tính toán và lưu trữ. Nó không cần biết JSON được parse bằng Jackson hay thư viện nào.

Tách biệt này có ba mục tiêu:

- **Một nơi quản lý quy ước chuyển đổi:** cấu hình module, annotation, naming strategy, định dạng ngày giờ và chính sách parse được tổ chức tập trung.
- **Hành vi ổn định trong suốt vòng đời ứng dụng:** mapper được cấu hình trước khi dùng và không bị thay đổi tùy tiện giữa các request.
- **Nghiệp vụ ít phụ thuộc hạ tầng:** service không phải tạo mapper, xử lý chi tiết ngoại lệ Jackson hoặc chứa logic định dạng JSON.

## 1. Phân biệt cấu hình Jackson và logic nghiệp vụ

Hai loại trách nhiệm này thường xuất hiện cạnh nhau nhưng giải quyết những vấn đề khác nhau.

| Cấu hình xử lý dữ liệu | Logic nghiệp vụ |
|---|---|
| Đăng ký `JavaTimeModule` để đọc/ghi kiểu ngày giờ Java | Quyết định thời điểm nào đơn hàng được xem là quá hạn |
| Ánh xạ khóa `customer_id` vào thuộc tính `customerId` | Kiểm tra khách hàng có được phép đặt đơn hay không |
| Quy định có chấp nhận trường JSON không biết trước hay không | Quyết định một trường mới có được chấp nhận theo chính sách sản phẩm hay không |
| Quy định cách biểu diễn enum trong JSON | Quyết định trạng thái đơn hàng nào được phép chuyển sang trạng thái tiếp theo |
| Bỏ qua thuộc tính kỹ thuật khi serialize DTO | Quyết định người dùng có quyền xem dữ liệu nhạy cảm hay không |
| Định dạng số hoặc ngày giờ trên hợp đồng API | Tính thuế, chiết khấu, phí giao hàng hoặc số dư |
| Chuyển đổi token JSON thành kiểu Java | Kiểm tra bất biến của đối tượng miền và thực hiện giao dịch |

Jackson có thể thực hiện chuyển đổi cú pháp và kiểu dữ liệu, nhưng không nên trở thành nơi quyết định quy tắc sản phẩm. Ví dụ, serializer có thể định dạng `Instant` thành chuỗi ISO 8601; nó không nên tự truy vấn database để tìm múi giờ của khách hàng rồi quyết định ngày giao hàng có hợp lệ hay không.

Một cách nhận biết hữu ích là hỏi: “Nếu ứng dụng thay Jackson bằng một thư viện JSON khác, quy tắc này có còn đúng và cần được giữ nguyên không?” Nếu câu trả lời là có, quy tắc đó thường thuộc nghiệp vụ hoặc hợp đồng ứng dụng. Nếu quy tắc chỉ mô tả cách dữ liệu được biểu diễn trên dây truyền hoặc trong tệp, nó thường thuộc lớp chuyển đổi dữ liệu.

## 2. Vì sao không nên tạo và cấu hình ObjectMapper ở khắp nơi?

Một cách viết dễ gặp là:

```java
public class OrderService {
    public Order loadOrder(String json) throws JsonProcessingException {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        return mapper.readValue(json, Order.class);
    }
}
```

Đoạn code có thể hoạt động trong một ví dụ nhỏ, nhưng gây ra nhiều vấn đề khi được lặp lại ở nhiều service:

1. **Cấu hình bị trùng lặp:** mỗi nơi phải nhớ đăng ký module, đặt naming strategy và bật/tắt các feature giống nhau.
2. **Hành vi không nhất quán:** hai service có thể đọc cùng một JSON nhưng xử lý `null`, ngày giờ hoặc trường lạ khác nhau.
3. **Chi phí khởi tạo không cần thiết:** tạo mapper mới cho từng lần gọi làm lặp lại quá trình xây dựng cấu hình và cache nội bộ.
4. **Khó thay đổi chính sách:** khi hợp đồng API đổi, nhóm phát triển phải tìm mọi nơi tạo mapper để cập nhật.
5. **Khó kiểm thử:** test service vô tình phụ thuộc vào cấu hình Jackson cục bộ, khiến lỗi chuyển đổi và lỗi nghiệp vụ bị trộn lẫn.
6. **Ranh giới trách nhiệm mờ:** service vừa xử lý đơn hàng vừa quyết định JSON được biểu diễn ra sao.

Một `ObjectMapper` được cấu hình đầy đủ có thể được tái sử dụng giữa nhiều luồng. Tài liệu Jackson khuyến nghị cấu hình mapper hoàn tất trước khi các thao tác đọc/ghi bắt đầu. Sau khi đưa mapper vào sử dụng, không nên tiếp tục thay đổi cấu hình dùng chung. Nếu mỗi request lại gọi `configure`, `registerModule` hoặc thay đổi feature, kết quả có thể phụ thuộc thời điểm và thứ tự xử lý.

## 3. Đặt cấu hình ở một điểm khởi tạo rõ ràng

Trong ứng dụng Java thuần, có thể tạo một lớp chuyên trách xây dựng mapper:

```java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class JacksonConfiguration {
    private JacksonConfiguration() {
    }

    public static ObjectMapper createObjectMapper() {
        ObjectMapper mapper = new ObjectMapper();

        mapper.registerModule(new JavaTimeModule());
        mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);

        return mapper;
    }
}
```

Ứng dụng gọi `createObjectMapper()` ở giai đoạn khởi tạo, sau đó chia sẻ instance đã hoàn tất cấu hình:

```java
public class Application {
    public static void main(String[] args) {
        ObjectMapper mapper = JacksonConfiguration.createObjectMapper();

        StudentJsonAdapter adapter = new StudentJsonAdapter(mapper);
        StudentApplicationService service = new StudentApplicationService();

        // Lắp ghép các thành phần và khởi động ứng dụng.
    }
}
```

Các feature trong ví dụ chỉ minh họa chính sách có thể tập trung tại một nơi. Không nên mặc định mọi dự án đều phải bỏ qua trường không biết hoặc loại bỏ tất cả giá trị `null`. Chọn chính sách theo hợp đồng dữ liệu và yêu cầu tương thích của hệ thống.

Một nguyên tắc quan trọng: **không tạo mapper mới trong mỗi request hoặc mỗi lần gọi service**. Mapper nên được tạo và cấu hình một lần cho mỗi bộ quy tắc chuyển đổi, rồi được tái sử dụng. Nếu có nhiều hợp đồng JSON thực sự khác nhau, có thể tạo các mapper riêng ở giai đoạn khởi động, mỗi mapper có tên và mục đích rõ ràng.

## 4. ObjectMapper dùng chung và tính an toàn đa luồng

`ObjectMapper` là đối tượng có cấu hình. Nó có thể được sử dụng đồng thời bởi nhiều thread khi việc cấu hình đã hoàn tất trước khi mapper được dùng. Điều này làm cho một instance dùng chung trong ứng dụng thường là lựa chọn hợp lý.

Ví dụ một adapter nhận mapper qua constructor:

```java
public final class StudentJsonAdapter {
    private final ObjectMapper mapper;

    public StudentJsonAdapter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public StudentResponse read(String json) throws JsonProcessingException {
        return mapper.readValue(json, StudentResponse.class);
    }

    public String write(StudentResponse response) throws JsonProcessingException {
        return mapper.writeValueAsString(response);
    }
}
```

Các thành phần khác nhận adapter hoặc mapper thông qua constructor injection, thay vì tự tạo mapper. Không sửa cấu hình của mapper sau khi adapter đã bắt đầu phục vụ request.

Ví dụ không nên làm:

```java
public String write(Object value, boolean pretty) throws JsonProcessingException {
    mapper.configure(SerializationFeature.INDENT_OUTPUT, pretty);
    return mapper.writeValueAsString(value);
}
```

Hai request đồng thời có thể cần hai cách ghi khác nhau. Việc thay đổi feature trên mapper dùng chung khiến một request có khả năng ảnh hưởng request khác. Hãy tạo `ObjectWriter` riêng cho mỗi chính sách ghi hoặc cấu hình writer ngay khi khởi tạo adapter.

## 5. Dùng ObjectReader và ObjectWriter cho chính sách theo từng thao tác

Jackson cung cấp `ObjectReader` và `ObjectWriter` để tạo các cách đọc/ghi chuyên biệt từ một `ObjectMapper`.

- `ObjectReader` giữ kiểu đích và các tùy chọn giải tuần tự hóa.
- `ObjectWriter` giữ kiểu nguồn và các tùy chọn tuần tự hóa.
- Cả hai là đối tượng bất biến theo cách sử dụng thông thường: các phương thức `with` hoặc `without` trả về cấu hình reader/writer mới, không sửa mapper gốc.
- Reader/writer đã tạo có thể được tái sử dụng, giúp tránh phải thay đổi cấu hình mapper chung cho từng request.

Ví dụ hai chính sách đọc khác nhau:

```java
ObjectReader strictReader = mapper.readerFor(PartnerEvent.class)
    .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

ObjectReader compatibleReader = mapper.readerFor(LegacyEvent.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Một chính sách ghi có định dạng dễ đọc cho tác vụ xuất báo cáo:

```java
ObjectWriter reportWriter = mapper.writerFor(Report.class)
    .with(SerializationFeature.INDENT_OUTPUT);

String reportJson = reportWriter.writeValueAsString(report);
```

Trong khi đó, writer mặc định của API có thể giữ JSON gọn:

```java
ObjectWriter apiWriter = mapper.writerFor(ApiResponse.class)
    .without(SerializationFeature.INDENT_OUTPUT);
```

Các reader/writer này nên được tạo tại nơi lắp ghép adapter hoặc trong constructor của adapter, rồi tái sử dụng. Nếu mỗi request cần một lựa chọn khác nhau, tạo reader/writer mới từ mapper thường rõ ràng và an toàn hơn việc thay đổi mapper dùng chung.

Ví dụ adapter giữ reader/writer riêng:

```java
public final class PartnerEventCodec {
    private final ObjectReader reader;
    private final ObjectWriter writer;

    public PartnerEventCodec(ObjectMapper mapper) {
        this.reader = mapper.readerFor(PartnerEvent.class)
            .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        this.writer = mapper.writerFor(PartnerEvent.class);
    }

    public PartnerEvent decode(String json) throws IOException {
        return reader.readValue(json);
    }

    public String encode(PartnerEvent event) throws JsonProcessingException {
        return writer.writeValueAsString(event);
    }
}
```

## 6. Tổ chức ranh giới giữa ứng dụng và Jackson

Một kiến trúc phân lớp thường có thể chia thành các vùng trách nhiệm:

```text
                 HTTP / Message / File
                         |
                         v
              Adapter nhận dữ liệu ngoài
                         |
                         v
               DTO / Request Model
                         |
                         v
              Chuyển thành Command
                         |
                         v
               Application Service
                         |
                         v
               Domain Model / Rules

      Jackson Configuration
              |
              v
       Jackson Adapter / Framework
```

Jackson được dùng ở ranh giới đọc/ghi. Application Service nhận command hoặc kiểu dữ liệu của ứng dụng, thực hiện use case và gọi domain. Domain model không cần biết JSON có tên khóa nào, được parse bởi `ObjectMapper` nào hoặc serializer nào được đăng ký.

### 6.1. Dùng DTO cho hợp đồng trao đổi

Ví dụ request từ bên ngoài:

```json
{
  "customer_id": "b9c7e4e4-7e32-4e0e-bce1-1f9c4f1f9c10",
  "quantity": 2
}
```

DTO có thể phản ánh tên khóa của hợp đồng:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.UUID;

public record CreateOrderRequest(
    @JsonProperty("customer_id") UUID customerId,
    int quantity
) {
}
```

Sau khi Jackson tạo DTO, adapter hoặc controller chuyển nó thành command của ứng dụng:

```java
public record CreateOrderCommand(CustomerId customerId, int quantity) {
}

public final class CreateOrderMapper {
    public CreateOrderCommand toCommand(CreateOrderRequest request) {
        return new CreateOrderCommand(
            new CustomerId(request.customerId()),
            request.quantity()
        );
    }
}
```

Application Service làm việc với command:

```java
public final class CreateOrderService {
    public OrderId create(CreateOrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        // Kiểm tra khách hàng, giá, tồn kho và tạo đơn hàng.
        return createOrder(command);
    }
}
```

Service không cần import `ObjectMapper`, `JsonProperty` hoặc `JsonProcessingException`. Quy tắc số lượng phải lớn hơn không vẫn đúng nếu command đến từ HTTP, message queue, batch job hoặc một test trực tiếp.

### 6.2. Không để serializer thực hiện nghiệp vụ

Custom serializer/deserializer hữu ích khi cần chuyển đổi biểu diễn đặc thù, chẳng hạn kiểu `Money` được biểu diễn thành một object gồm `amount` và `currency`, hoặc một kiểu ID được biểu diễn thành chuỗi. Tuy nhiên, serializer nên thực hiện chuyển đổi xác định và không có tác dụng phụ.

Một serializer không nên:

- Truy vấn database để lấy dữ liệu bổ sung.
- Gọi HTTP service hoặc message broker.
- Kiểm tra quyền truy cập của người dùng.
- Thay đổi trạng thái entity hoặc thực hiện giao dịch.
- Quyết định quy tắc chiết khấu, phí hoặc trạng thái đơn hàng.

Những hành vi đó làm serialization khó dự đoán, khó test và có thể phát sinh N+1 query hoặc side effect khi chỉ cần ghi JSON. Hãy chuẩn bị dữ liệu cần thiết ở application/service layer, sau đó chuyển thành DTO có cấu trúc rõ ràng để Jackson serialize.

## 7. Tích hợp trong ứng dụng Spring Boot

Trong Spring Boot, Jackson thường đã được tích hợp với HTTP message converter. Khi controller khai báo `@RequestBody` hoặc trả về một DTO, framework sử dụng mapper được cấu hình trong application context. Vì vậy, không nên tạo một `ObjectMapper` riêng trong từng controller hoặc service nếu muốn tuân theo cấu hình chung của ứng dụng.

Có thể tùy chỉnh cấu hình tập trung bằng `Jackson2ObjectMapperBuilderCustomizer`:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JacksonConfiguration {
    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> builder.featuresToDisable(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES
        );
    }
}
```

Customizer cho phép điều chỉnh builder mà Spring Boot dùng để tạo mapper. Đây là nơi thích hợp để đặt chính sách chung của ứng dụng. Cần kiểm tra phiên bản Spring Boot đang dùng vì cách tích hợp và các module được auto-configure có thể khác nhau giữa các phiên bản.

Nếu cần đăng ký serializer, deserializer hoặc module riêng, có thể cung cấp bean `Module` hoặc cấu hình builder theo cơ chế mà phiên bản Spring Boot hỗ trợ. Nên ưu tiên cơ chế mở rộng của framework để giữ một mapper nhất quán cho MVC, WebFlux hoặc các thành phần khác đang dùng mapper đó.

Controller có thể chỉ tập trung vào việc nhận request, gọi use case và trả response:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final CreateOrderService service;
    private final CreateOrderMapper requestMapper;

    public OrderController(
            CreateOrderService service,
            CreateOrderMapper requestMapper) {
        this.service = service;
        this.requestMapper = requestMapper;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {

        CreateOrderCommand command = requestMapper.toCommand(request);
        OrderId id = service.create(command);
        return ResponseEntity.ok(new OrderResponse(id.value()));
    }
}
```

Trong luồng này, Spring/Jackson chuyển body thành `CreateOrderRequest`; controller chuyển DTO thành command; service thực hiện nghiệp vụ. Cấu hình JSON nằm trong application context và không cần xuất hiện trong code xử lý đơn hàng.

## 8. Khi nào cần nhiều ObjectMapper?

Một mapper dùng chung là lựa chọn mặc định hợp lý khi toàn ứng dụng tuân theo một hợp đồng JSON thống nhất. Tuy nhiên, có trường hợp nhiều tích hợp bên ngoài có quy ước khác nhau:

- API nội bộ yêu cầu trường không xác định phải gây lỗi.
- Một đối tác cũ cho phép bỏ qua trường mới để duy trì tương thích.
- Một định dạng file lịch sử dùng ngày giờ hoặc enum theo quy ước riêng.
- Một giao thức yêu cầu tên thuộc tính khác với API công khai.
- Một hệ thống cần serializer đặc thù cho một kiểu dữ liệu.

Không nên sửa mapper toàn cục theo từng đối tác. Hãy tạo cấu hình riêng cho từng hợp đồng và đặt tên rõ ràng, ví dụ `internalApiMapper`, `legacyPartnerMapper` hoặc `auditFileMapper`. Mỗi mapper cần được tạo và cấu hình một lần khi khởi động.

Ví dụ hai mapper có chính sách đọc khác nhau:

```java
public final class JsonMapperRegistry {
    private final ObjectMapper internalApiMapper;
    private final ObjectMapper legacyPartnerMapper;

    public JsonMapperRegistry() {
        this.internalApiMapper = createBaseMapper()
            .copy()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        this.legacyPartnerMapper = createBaseMapper()
            .copy()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    }

    private ObjectMapper createBaseMapper() {
        ObjectMapper mapper = new ObjectMapper();
        mapper.registerModule(new JavaTimeModule());
        return mapper;
    }

    public ObjectMapper internalApiMapper() {
        return internalApiMapper;
    }

    public ObjectMapper legacyPartnerMapper() {
        return legacyPartnerMapper;
    }
}
```

`copy()` tạo một mapper độc lập dựa trên cấu hình hiện có. Không nên gọi `copy()` cho mỗi request; nếu cần nhiều chính sách ổn định, hãy tạo các instance đó ở giai đoạn khởi tạo. Với khác biệt chỉ nằm ở một vài tùy chọn cho một kiểu đích, `ObjectReader` hoặc `ObjectWriter` thường nhẹ và rõ ràng hơn việc tạo thêm mapper.

Mỗi mapper riêng cần có phạm vi sử dụng rõ ràng. Nếu mapper của đối tác A vô tình được dùng để đọc request nội bộ, chính sách bỏ qua trường lạ hoặc định dạng ngày giờ có thể làm thay đổi hành vi ngoài dự kiến.

## 9. Quản lý module, annotation và naming strategy

Cấu hình Jackson tập trung thường bao gồm các nhóm sau:

| Nhóm | Ví dụ | Vị trí quản lý phù hợp |
|---|---|---|
| Module | `JavaTimeModule`, module tự viết | Cấu hình mapper hoặc builder |
| Feature đọc | `FAIL_ON_UNKNOWN_PROPERTIES`, coercion | Cấu hình mapper hoặc reader theo hợp đồng |
| Feature ghi | `INDENT_OUTPUT`, cách xử lý giá trị rỗng | Cấu hình mapper hoặc writer theo mục đích |
| Inclusion | Bỏ qua `null`, `NON_EMPTY` | Cấu hình chung hoặc DTO/kiểu có hợp đồng riêng |
| Naming strategy | `SNAKE_CASE`, `LOWER_CAMEL_CASE` | Mapper dành cho hợp đồng tương ứng |
| Annotation | `@JsonProperty`, `@JsonAlias`, `@JsonIgnore` | DTO hoặc kiểu dữ liệu được kiểm soát |
| Mix-in | Gắn quy tắc Jackson vào kiểu không thể sửa mã nguồn | Cấu hình adapter/mapper |
| Serializer/deserializer | Chuyển đổi kiểu đặc thù | Module hoặc package hạ tầng JSON |
| Read constraints | Độ sâu, độ dài chuỗi/số | `JsonFactory`/mapper ở biên nhận dữ liệu |

Không phải mọi quy tắc đều nên đặt ở cấu hình toàn cục. Ví dụ, một DTO public API có thể dùng `@JsonProperty` vì tên khóa là một phần hợp đồng riêng của DTO. Một naming strategy chỉ nên áp dụng cho mapper nếu toàn bộ hợp đồng do mapper đó xử lý cùng tuân theo quy ước.

Nếu dùng `@JsonIgnore` để bỏ một trường, hãy chắc chắn trường đó thực sự không thuộc hợp đồng. Nếu cùng một model cần hiển thị khác nhau ở nhiều API, DTO riêng thường dễ hiểu hơn việc tích lũy nhiều annotation hoặc view phức tạp trên một entity.

### 9.1. Dùng mix-in khi không sở hữu lớp nguồn

Đôi khi cần cấu hình Jackson cho lớp từ thư viện bên ngoài mà không thể thêm annotation vào mã nguồn của lớp đó. Mix-in cho phép khai báo annotation ở một lớp khác:

```java
abstract class ExternalUserMixin {
    @JsonProperty("user_name")
    abstract String getName();
}

ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalUser.class, ExternalUserMixin.class);
```

Mix-in nên được đăng ký trong cấu hình mapper tương ứng. Tránh thêm mix-in tùy tiện tại nơi xử lý nghiệp vụ, vì quy tắc ánh xạ sẽ trở nên khó tìm và có thể ảnh hưởng nhiều luồng sử dụng cùng mapper.

## 10. Xử lý lỗi tại ranh giới dữ liệu

Jackson có thể phát hiện JSON sai cú pháp, kiểu không thể chuyển đổi, trường không được phép theo cấu hình hoặc dữ liệu vượt giới hạn parser. Những lỗi này thường phát sinh trước khi use case nghiệp vụ được gọi.

Ở tầng adapter, có thể chuyển lỗi thư viện thành lỗi của lớp tích hợp:

```java
public final class JacksonPartnerEventAdapter {
    private final ObjectReader reader;

    public JacksonPartnerEventAdapter(ObjectMapper mapper) {
        this.reader = mapper.readerFor(PartnerEvent.class);
    }

    public PartnerEvent decode(String json) {
        try {
            return reader.readValue(json);
        } catch (JsonProcessingException exception) {
            throw new InvalidPartnerPayloadException(
                "Partner event does not match the expected format",
                exception
            );
        }
    }
}
```

Với đầu vào là `String`, ví dụ chuyển `JsonProcessingException` thành lỗi tích hợp vì lỗi chính thường là nội dung không khớp định dạng mong đợi. Nếu adapter đọc trực tiếp từ `InputStream`, cần xử lý thêm lỗi I/O do nguồn đọc có thể thất bại độc lập với lỗi JSON. `InvalidPartnerPayloadException` là kiểu ngoại lệ minh họa do ứng dụng định nghĩa.

Tầng HTTP có thể chuyển `InvalidPartnerPayloadException` thành phản hồi 400 hoặc mã lỗi tích hợp phù hợp. Service nghiệp vụ không cần phụ thuộc vào `JsonMappingException` để quyết định trạng thái đơn hàng.

Khi ghi log, tránh ghi toàn bộ JSON đầu vào nếu payload có token, mật khẩu, dữ liệu cá nhân hoặc thông tin thanh toán. Nên log mã tương quan, nguồn tích hợp, loại lỗi và vị trí lỗi cần thiết; dữ liệu nhạy cảm phải được che hoặc loại bỏ theo chính sách log của ứng dụng.

## 11. Kiểm thử cấu hình và kiểm thử nghiệp vụ độc lập

Tách cấu hình giúp xác định đúng nơi cần kiểm thử.

### 11.1. Kiểm thử hợp đồng JSON ở lớp adapter

Kiểm thử adapter nên xác nhận JSON thực tế được chuyển đổi đúng theo hợp đồng:

- Tên khóa được ánh xạ đúng.
- Ngày giờ được đọc/ghi đúng quy ước múi giờ và định dạng.
- Chính sách trường lạ hoạt động như mong muốn.
- Giá trị `null`, trường thiếu và enum được xử lý theo hợp đồng.
- Serializer/deserializer tùy chỉnh tạo ra biểu diễn mong đợi.
- JSON sai cú pháp hoặc sai kiểu được chuyển thành lỗi tích hợp phù hợp.

Ví dụ kiểm thử đơn giản:

```java
class StudentJsonAdapterTest {
    private final ObjectMapper mapper =
        JacksonConfiguration.createObjectMapper();

    private final StudentJsonAdapter adapter =
        new StudentJsonAdapter(mapper);

    @Test
    void readsStudentJson() throws Exception {
        String json = """
            {"id": 23, "name": "Lan", "active": true}
            """;

        StudentResponse student = adapter.read(json);

        assertEquals(23L, student.getId());
        assertEquals("Lan", student.getName());
        assertTrue(student.isActive());
    }
}
```

Với hợp đồng quan trọng, nên có các mẫu JSON cố định (golden files hoặc fixture) đại diện cho request/response đã thống nhất. Không nên chỉ kiểm tra round-trip `Java -> JSON -> Java`, vì nếu cả hai chiều cùng dùng sai quy ước thì round-trip vẫn có thể thành công.

### 11.2. Kiểm thử nghiệp vụ không cần Jackson

Nếu application service nhận command hoặc domain object, unit test của nó có thể tạo trực tiếp các kiểu đó:

```java
class CreateOrderServiceTest {
    @Test
    void rejectsNonPositiveQuantity() {
        CreateOrderService service = new CreateOrderService();
        CreateOrderCommand command = new CreateOrderCommand(
            new CustomerId(UUID.randomUUID()),
            0
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> service.create(command)
        );
    }
}
```

Test này kiểm tra quy tắc nghiệp vụ mà không cần tạo JSON, mapper hoặc fixture serialization. Khi hợp đồng JSON thay đổi nhưng quy tắc số lượng vẫn giữ nguyên, test nghiệp vụ không phải thay đổi theo.

Nếu một thành phần ứng dụng thực sự cần một cổng chuyển đổi JSON, có thể kiểm thử nó qua interface và dùng implementation giả trong unit test. Tuy nhiên, không cần tạo abstraction chỉ để che mọi lần gọi Jackson. Hãy tạo ranh giới khi nó làm rõ trách nhiệm, hỗ trợ nhiều adapter hoặc giúp phần nghiệp vụ không phụ thuộc thư viện hạ tầng.

## 12. Những anti-pattern cần tránh

### 12.1. Tạo ObjectMapper trong từng phương thức

```java
public Result handle(String json) throws JsonProcessingException {
    ObjectMapper mapper = new ObjectMapper();
    return mapper.readValue(json, Result.class);
}
```

Việc này phân tán cấu hình và lặp lại khởi tạo. Hãy inject mapper đã cấu hình hoặc inject adapter chuyên trách.

### 12.2. Dùng static mutable mapper cho toàn ứng dụng

Một biến static có thể tạo cảm giác dùng chung đơn giản, nhưng ai cũng có thể thay đổi feature hoặc đăng ký module trên cùng instance. Khi nhiều package cùng sửa mapper, khó xác định cấu hình cuối cùng. Ưu tiên dependency injection hoặc một registry có quyền sở hữu và cấu hình rõ ràng.

### 12.3. Thay đổi mapper dùng chung theo từng request

Không bật/tắt `SerializationFeature` hoặc `DeserializationFeature` trên mapper singleton trong lúc request đang chạy. Tạo `ObjectReader`/`ObjectWriter` riêng hoặc mapper riêng cho hợp đồng có chính sách độc lập.

### 12.4. Để domain entity trở thành hợp đồng JSON mặc định

Serialize trực tiếp entity persistence có thể làm lộ trường nội bộ, kích hoạt lazy loading, gây vòng tham chiếu hoặc làm API phụ thuộc cấu trúc database. DTO giúp kiểm soát rõ dữ liệu công khai và cho phép thay đổi persistence model độc lập với API.

### 12.5. Đặt quy tắc nghiệp vụ trong custom serializer

Serializer có side effect hoặc truy cập service khiến việc ghi JSON trở thành một thao tác nghiệp vụ ẩn. Hãy chuẩn bị dữ liệu trước khi serialize và giữ serializer ở phạm vi chuyển đổi biểu diễn.

### 12.6. Nuốt lỗi parse hoặc trả về đối tượng rỗng

```java
try {
    return mapper.readValue(json, Request.class);
} catch (Exception ignored) {
    return new Request();
}
```

Đoạn code này biến dữ liệu sai thành một request có vẻ hợp lệ, khiến lỗi khó truy tìm và có thể tạo hành vi sai trong nghiệp vụ. Hãy chuyển lỗi thành kết quả lỗi rõ ràng tại biên tích hợp và để tầng gọi quyết định phản hồi phù hợp.

## 13. Quy trình thiết kế cấu hình Jackson

Khi thêm một tích hợp JSON mới, có thể thực hiện theo trình tự sau:

1. Xác định hợp đồng dữ liệu: tên trường, kiểu, giá trị thiếu/null, ngày giờ, enum, trường mở rộng và phiên bản.
2. Xác định phạm vi chính sách: dùng chung toàn ứng dụng, riêng một API hay riêng một đối tác.
3. Chọn mô hình DTO cho dữ liệu vào/ra; không để cấu trúc persistence quyết định hợp đồng ngoài.
4. Đặt cấu hình Jackson tại composition root, framework configuration hoặc module hạ tầng tương ứng.
5. Hoàn tất mapper trước khi chia sẻ; dùng reader/writer cho khác biệt theo thao tác.
6. Đặt chuyển đổi DTO sang command/domain ở adapter hoặc assembler; để service và domain giữ logic nghiệp vụ.
7. Chuyển lỗi Jackson thành lỗi ở ranh giới tích hợp; không làm lộ dữ liệu nhạy cảm trong log hoặc response.
8. Kiểm thử hợp đồng JSON riêng với kiểm thử use case; bổ sung fixture cho các trường hợp tương thích quan trọng.
9. Khi thay đổi cấu hình chung, đánh giá ảnh hưởng tới tất cả adapter đang dùng mapper đó.

## 14. Bảng phân công trách nhiệm tham khảo

| Thành phần | Nên chịu trách nhiệm | Không nên chịu trách nhiệm |
|---|---|---|
| Jackson configuration | Tạo mapper, đăng ký module, feature, naming strategy và constraints | Quyết định quyền truy cập hoặc trạng thái nghiệp vụ |
| JSON adapter / HTTP converter | Đọc/ghi JSON, ánh xạ DTO, chuyển lỗi thư viện thành lỗi tích hợp | Tự thực hiện giao dịch nghiệp vụ hoặc truy vấn dữ liệu tùy tiện trong serializer |
| DTO / request-response model | Mô tả hợp đồng dữ liệu ngoài, annotation cần thiết cho biểu diễn | Chứa toàn bộ logic nghiệp vụ và persistence behavior |
| Assembler / mapper ứng dụng | Chuyển DTO thành command hoặc domain input, chuyển kết quả thành response | Quản lý cấu hình toàn cục của Jackson |
| Application service | Điều phối use case, kiểm tra quy tắc ứng dụng và gọi domain/repository | Tạo mapper hoặc tự xử lý token JSON |
| Domain model | Bảo vệ invariant, hành vi và quy tắc miền | Phụ thuộc annotation hoặc exception của Jackson |
| Repository / persistence adapter | Đọc ghi dữ liệu lưu trữ theo hợp đồng persistence | Quyết định định dạng JSON công khai của API |

Tùy quy mô ứng dụng, một controller có thể đồng thời đóng vai trò adapter và assembler đơn giản. Điều quan trọng là ranh giới vẫn rõ: phần nghiệp vụ nhận dữ liệu đã được chuyển thành kiểu ứng dụng, còn cấu hình thư viện được quản lý ở nơi khởi tạo hạ tầng.

## 15. Khi nào nên tạo abstraction cho JSON?

Nếu toàn bộ ứng dụng chỉ dùng Jackson tại một vài adapter, việc inject `ObjectMapper` trực tiếp vào adapter có thể đủ rõ ràng. Không cần tạo interface cho mọi thư viện chỉ vì muốn áp dụng nguyên tắc dependency inversion.

Một interface riêng hữu ích khi:

- Nhiều module ứng dụng cần một hợp đồng chuyển đổi độc lập với thư viện cụ thể.
- Ứng dụng có nhiều implementation, ví dụ Jackson cho JSON và một adapter khác cho định dạng trao đổi khác.
- Muốn mock hoặc thay thế adapter ở kiểm thử mà không cần kéo dependency Jackson vào lớp ứng dụng.
- Muốn chuẩn hóa cách chuyển lỗi và cách ghi nhận dữ liệu tích hợp.

Ví dụ cổng chuyển đổi đơn giản:

```java
public interface JsonCodec {
    <T> T decode(String json, Class<T> targetType);
    String encode(Object value);
}
```

Implementation dùng Jackson nằm trong package hạ tầng:

```java
public final class JacksonJsonCodec implements JsonCodec {
    private final ObjectMapper mapper;

    public JacksonJsonCodec(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public <T> T decode(String json, Class<T> targetType) {
        try {
            return mapper.readValue(json, targetType);
        } catch (JsonProcessingException exception) {
            throw new JsonCodecException("Invalid JSON payload", exception);
        }
    }

    @Override
    public String encode(Object value) {
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new JsonCodecException("Cannot encode JSON payload", exception);
        }
    }
}
```

`JsonCodecException` là ngoại lệ do ứng dụng định nghĩa. Nếu cần hỗ trợ kiểu tổng quát phức tạp như `List<Order>`, hãy thiết kế hợp đồng type token của ứng dụng hoặc các phương thức cụ thể cho use case; tránh đưa `TypeReference` của Jackson vào interface nếu mục tiêu là tách phụ thuộc thư viện.

Không nên dùng `JsonCodec` ở mọi nơi một cách máy móc. Với Spring MVC, framework đã chuyển request body thành DTO trước khi gọi controller; việc tạo thêm một tầng codec trong controller có thể không mang lại lợi ích. Dùng abstraction ở nơi nó thể hiện một ranh giới tích hợp thật sự.

## 16. Tổng kết

`ObjectMapper` nên được xem là thành phần hạ tầng có cấu hình và vòng đời rõ ràng. Hãy xây dựng mapper tại giai đoạn khởi động, hoàn tất module và feature trước khi chia sẻ, rồi tái sử dụng trong adapter. Với khác biệt nhỏ theo từng kiểu hoặc thao tác, dùng `ObjectReader` và `ObjectWriter`; với nhiều hợp đồng độc lập, tạo mapper riêng cho từng hợp đồng thay vì thay đổi mapper toàn cục theo request.

JSON adapter chịu trách nhiệm chuyển đổi biểu diễn và xử lý lỗi parse. DTO mô tả hợp đồng bên ngoài. Assembler chuyển DTO thành command hoặc domain input. Application service và domain model giữ quy tắc nghiệp vụ. Cách phân chia này giúp thay đổi Jackson, thay đổi định dạng JSON hoặc thêm một kênh tích hợp mà không kéo theo việc sửa các quy tắc cốt lõi của ứng dụng.
