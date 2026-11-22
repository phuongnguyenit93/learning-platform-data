# Null field và default mapping trong Spring Batch

Khi Spring Batch đọc JSON, một field có thể bị thiếu, được gửi rõ ràng với giá trị null, là chuỗi rỗng, là collection rỗng hoặc chứa một giá trị cụ thể. Những trường hợp này không giống nhau về ý nghĩa dữ liệu. Nếu mapper tự động biến tất cả thành một giá trị mặc định, batch có thể ghi sai dữ liệu, bỏ qua lỗi đầu vào hoặc làm mất thông tin mà hệ thống nguồn muốn truyền.

Với JSON reader dùng Jackson, cách xử lý field null và default mapping chủ yếu do cấu hình ObjectMapper, annotation trên DTO và logic chuyển đổi sang domain model quyết định. Spring Batch quản lý việc đọc item, transaction, skip và restart; nó không tự suy ra quy tắc mặc định cho từng field nghiệp vụ.

Điểm quan trọng là xác định rõ hợp đồng dữ liệu: field nào bắt buộc, field nào được phép bỏ trống, khi nào giá trị mặc định được áp dụng và khi nào dữ liệu phải bị từ chối. Sau đó triển khai quy tắc nhất quán ở đúng lớp mapping.

## 1. Phân biệt missing, null, empty và value

Một JSON property có thể xuất hiện theo nhiều cách:

| JSON đầu vào | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| Property bị thiếu | Producer không gửi field | { "id": 10 } |
| Property có giá trị null | Producer gửi field nhưng không có giá trị | { "id": 10, "note": null } |
| Chuỗi rỗng | Có chuỗi nhưng không có ký tự | { "id": 10, "note": "" } |
| Collection rỗng | Có collection nhưng không có phần tử | { "id": 10, "tags": [] } |
| Object rỗng | Có object nhưng không có property con | { "id": 10, "address": {} } |
| Giá trị cụ thể | Producer gửi dữ liệu | { "id": 10, "note": "urgent" } |

Không nên tự động coi các trường hợp này là tương đương. Ví dụ:

- note bị thiếu có thể có nghĩa producer chưa cung cấp ghi chú.
- note: null có thể có nghĩa producer muốn xóa ghi chú cũ.
- note: "" có thể có nghĩa ghi chú được cố ý đặt thành rỗng.
- tags: [] có thể có nghĩa producer xác nhận không có tag nào.

Quy tắc default phải được xác định theo hợp đồng dữ liệu. Nếu batch biến mọi trường hợp thành chuỗi rỗng, 0 hoặc collection rỗng, thông tin về ý định của producer có thể bị mất.

## 2. JSON reader và Jackson mapping trong Spring Batch

Spring Batch cung cấp JsonItemReader để đọc một JSON document có dạng mảng các object và trả về từng object như một item. JsonObjectReader chịu trách nhiệm chuyển từng JSON object thành kiểu Java. JacksonJsonObjectReader là implementation sử dụng Jackson.

Ví dụ input:

~~~json
[
  {
    "id": 101,
    "customerId": "C-10",
    "quantity": 2,
    "note": "priority"
  },
  {
    "id": 102,
    "customerId": "C-11",
    "note": null
  }
]
~~~

Reader có thể được cấu hình như sau:

~~~java
@Bean
@StepScope
JsonItemReader<OrderInput> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ObjectMapper objectMapper) {

    JacksonJsonObjectReader<OrderInput> objectReader =
        new JacksonJsonObjectReader<>(OrderInput.class, objectMapper);

    return new JsonItemReaderBuilder<OrderInput>()
        .name("orderJsonReader")
        .resource(new FileSystemResource(inputFile))
        .jsonObjectReader(objectReader)
        .saveState(true)
        .build();
}
~~~

JsonItemReader quản lý việc đọc từng object từ tài liệu JSON; Jackson mapping quyết định field nào được gán và cách xử lý null. saveState(true) liên quan đến restart checkpoint của reader, không phải cấu hình default cho property.

Nếu nguồn là NDJSON (mỗi dòng là một JSON object độc lập), không nên giả định JsonItemReader đọc từng dòng như một mảng. Có thể dùng FlatFileItemReader kết hợp LineMapper gọi Jackson ObjectMapper.readValue() cho mỗi dòng, hoặc một reader riêng phù hợp định dạng nguồn.

## 3. Jackson xử lý property bị thiếu như thế nào?

Với một mutable Java bean có constructor mặc định và field initializer, Jackson thường chỉ gán property xuất hiện trong JSON. Nếu property bị thiếu, initializer có thể được giữ nguyên.

Ví dụ:

~~~java
public class OrderInput {

    private Long id;
    private Integer quantity = 1;
    private String currency = "VND";

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Với JSON:

~~~json
{ "id": 101 }
~~~

quantity có thể giữ giá trị khởi tạo là 1, và currency giữ VND vì Jackson không nhận được property để gán. Đây là default do Java object initialization cung cấp, không phải Spring Batch tự đặt.

Hành vi này phụ thuộc cách DTO được tạo. Với constructor-based mapping, record hoặc immutable object, Jackson có thể truyền null hoặc giá trị mặc định cho tham số constructor bị thiếu thay vì giữ field initializer như mutable bean. Vì vậy, cần test chính kiểu DTO đang dùng.

## 4. Property bị thiếu khác với explicit JSON null

Nếu JSON có property với giá trị null, Jackson mặc định có thể gán null cho property reference type. Điều này khác với property bị thiếu.

Với DTO ở ví dụ trước:

~~~json
{ "id": 101, "quantity": null, "currency": null }
~~~

quantity và currency có thể bị gán thành null, dù field initializer ban đầu là 1 và VND. Field initializer chỉ có tác dụng khi không có thao tác gán ghi đè nó.

Bảng sau mô tả hành vi phổ biến với mutable bean:

| Property | Kết quả thường gặp |
| --- | --- |
| Không xuất hiện trong JSON | Giữ initializer hoặc giá trị ban đầu |
| Xuất hiện với null | Gán null cho reference property |
| Xuất hiện với giá trị | Gán giá trị đã deserialize |

Đây là lý do không thể chỉ khai báo field initializer rồi giả định mọi JSON null đều nhận default. Nếu explicit null cũng cần giữ default, hãy khai báo null handling rõ ràng.

## 5. Dùng @JsonSetter để quy định cách xử lý explicit null

Jackson có @JsonSetter với thuộc tính nulls. Có thể chọn cách xử lý khi property xuất hiện và giá trị của nó là JSON null.

Các lựa chọn thường dùng của Nulls:

| Giá trị | Hành vi |
| --- | --- |
| Nulls.SET | Gán null theo mặc định cho property reference |
| Nulls.SKIP | Bỏ qua thao tác gán khi giá trị JSON là null |
| Nulls.FAIL | Ném lỗi mapping khi property có giá trị null |
| Nulls.AS_EMPTY | Dùng giá trị rỗng do deserializer của kiểu đó cung cấp |
| Nulls.DEFAULT | Dùng cấu hình mặc định của Jackson cho property |

Ví dụ giữ default khi field bị thiếu hoặc explicit null:

~~~java
public class OrderInput {

    private String currency = "VND";

    public String getCurrency() {
        return currency;
    }

    @JsonSetter(value = "currency", nulls = Nulls.SKIP)
    public void setCurrency(String currency) {
        this.currency = currency;
    }
}
~~~

Với DTO này:

- JSON không có currency: setter không được gọi, initializer VND được giữ.
- JSON có currency: null: Jackson bỏ qua việc gán theo Nulls.SKIP, initializer vẫn được giữ.
- JSON có currency: USD: setter được gọi và giá trị thành USD.

Chỉ dùng cách này khi missing và explicit null thực sự có cùng ý nghĩa nghiệp vụ. Nếu null có nghĩa xóa giá trị còn missing có nghĩa không cập nhật, phải giữ được sự khác biệt đó.

## 6. Dùng Nulls.FAIL cho field không chấp nhận null

Nếu property được gửi rõ ràng nhưng có giá trị null là dữ liệu không hợp lệ, có thể cấu hình Nulls.FAIL:

~~~java
public class OrderInput {

    private String customerId;

    @JsonSetter(value = "customerId", nulls = Nulls.FAIL)
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }
}
~~~

JSON sau sẽ gây lỗi mapping:

~~~json
{ "customerId": null }
~~~

Tuy nhiên, Nulls.FAIL xử lý explicit null. Nó không nhất thiết làm property bị thiếu trở thành lỗi trong mọi kiểu DTO. Nếu customerId không xuất hiện, setter có thể không được gọi và field vẫn null.

Để kiểm tra property bắt buộc, dùng validation sau deserialize hoặc constructor/creator strict phù hợp. Ví dụ:

~~~java
public void validate() {
    if (customerId == null || customerId.isBlank()) {
        throw new InvalidOrderException("customerId is required");
    }
}
~~~

Nếu cần phân biệt thiếu property và explicit null, sử dụng JsonNode hoặc một representation có presence flag trước khi chuyển sang domain object.

## 7. Dùng Nulls.AS_EMPTY cho collection và chuỗi

Nulls.AS_EMPTY yêu cầu Jackson dùng empty value do deserializer cung cấp cho kiểu dữ liệu. Ví dụ, với một số kiểu collection, null có thể được chuyển thành collection rỗng; với String, empty value thường là chuỗi rỗng.

~~~java
public class OrderInput {

    private List<String> tags = new ArrayList<>();

    @JsonSetter(value = "tags", nulls = Nulls.AS_EMPTY)
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Với JSON:

~~~json
{ "tags": null }
~~~

Jackson có thể gán một list rỗng. Điều này chỉ đúng nếu hợp đồng dữ liệu xem null và empty list là tương đương.

Nếu cần phân biệt:

- property bị thiếu: không thay đổi tag hiện có;
- tags: null: xóa hoặc từ chối;
- tags: []: xác nhận không có tag;

thì không dùng AS_EMPTY để gộp chúng. Hãy giữ presence/null state và xử lý ở domain mapping.

## 8. Xử lý null bên trong collection bằng contentNulls

nulls áp dụng cho chính property collection. contentNulls áp dụng cho từng phần tử bên trong collection.

Ví dụ từ chối phần tử null trong danh sách:

~~~java
public class OrderInput {

    private List<String> tags;

    @JsonSetter(
        value = "tags",
        nulls = Nulls.AS_EMPTY,
        contentNulls = Nulls.FAIL
    )
    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Với JSON:

~~~json
{ "tags": null }
~~~

property có thể được chuyển thành list rỗng. Nhưng:

~~~json
{ "tags": ["priority", null] }
~~~

sẽ bị từ chối vì một phần tử collection là null.

Điều này hữu ích khi field collection được phép vắng mặt hoặc null nhưng từng phần tử phải có giá trị. Hãy xác định riêng chính sách cho container và cho content.

## 9. Tránh dùng primitive khi cần phân biệt null

Java primitive như int, long, boolean không thể chứa null. Nếu JSON không có property, primitive thường giữ giá trị mặc định của Java như 0 hoặc false. Nếu JSON gửi explicit null, Jackson có thể chuyển thành giá trị mặc định hoặc ném lỗi tùy cấu hình.

Ví dụ:

~~~java
public class OrderInput {
    private int quantity;
    private boolean expedited;
}
~~~

Với JSON:

~~~json
{ "id": 101 }
~~~

quantity có thể là 0 và expedited là false. Ứng dụng không thể biết producer đã gửi số 0/false hay property bị thiếu nếu chỉ nhìn primitive sau deserialize.

Khi presence có ý nghĩa, dùng wrapper:

~~~java
public class OrderInput {
    private Integer quantity;
    private Boolean expedited;
}
~~~

Wrapper cho phép giữ null để phân biệt với 0 và false. Sau đó validation hoặc domain mapper quyết định có dùng default hay từ chối.

Jackson có thể bật DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES để explicit null vào primitive gây lỗi thay vì âm thầm biến thành giá trị mặc định:

~~~java
objectMapper.enable(
    DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES
);
~~~

Tùy chọn này không biến property bị thiếu thành lỗi trong mọi trường hợp. Missing property và explicit null là hai trường hợp cần cấu hình/kiểm tra riêng.

## 10. Default cho constructor và Java record

Với constructor-based DTO hoặc Java record, Jackson tạo object bằng cách gọi constructor. Field initializer của mutable bean không phải mô hình default đáng tin cậy cho constructor parameter.

Ví dụ record:

~~~java
public record OrderInput(
    Long id,
    Integer quantity,
    String currency
) {}
~~~

Nếu property bị thiếu, reference component có thể nhận null. Với primitive component, giá trị có thể trở thành giá trị primitive mặc định nếu cấu hình cho phép. Nếu explicit null được truyền cho component, hành vi còn phụ thuộc null handling và feature của Jackson.

Một cách thể hiện default tường minh là dùng constructor/factory riêng:

~~~java
public record OrderInput(
    Long id,
    Integer quantity,
    String currency
) {
    public Order toDomain() {
        int effectiveQuantity =
            quantity == null ? 1 : quantity;
        String effectiveCurrency =
            currency == null ? "VND" : currency;

        return Order.create(
            Objects.requireNonNull(id, "id is required"),
            effectiveQuantity,
            effectiveCurrency
        );
    }
}
~~~

Ví dụ trên gộp missing và explicit null thành cùng default. Nếu hai trường hợp cần ý nghĩa khác nhau, không thể chỉ dựa vào giá trị record sau deserialize; cần giữ thêm presence information.

## 11. Jackson creator properties và strict deserialization

Với constructor hoặc factory có JsonCreator, Jackson cung cấp các feature để kiểm soát property bắt buộc:

- FAIL_ON_MISSING_CREATOR_PROPERTIES: lỗi khi creator property bắt buộc không xuất hiện.
- FAIL_ON_NULL_CREATOR_PROPERTIES: lỗi khi creator property nhận null.
- FAIL_ON_NULL_FOR_PRIMITIVES: lỗi khi explicit null được gán vào primitive.

Ví dụ cấu hình strict:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
~~~

Các feature creator có phạm vi rộng và có thể ảnh hưởng mọi constructor/creator mà mapper xử lý. Chỉ bật ở mapper phù hợp với input contract; nếu một số creator property được phép vắng mặt, hãy dùng mapper hoặc DTO riêng và validation có chủ đích.

JsonProperty(required = true) cũng thường được dùng để mô tả property bắt buộc, đặc biệt với creator properties. Không nên dựa vào annotation này như một validation tổng quát cho mọi mutable bean. Kiểm tra behavior của phiên bản Jackson và kiểu DTO thực tế.

## 12. @JsonProperty(defaultValue) không tự áp dụng default

Jackson có thuộc tính defaultValue trên JsonProperty, nhưng giá trị này chủ yếu là metadata cho module/framework hoặc công cụ introspection. Jackson databind không tự động gán default runtime chỉ vì khai báo:

~~~java
@JsonProperty(value = "quantity", defaultValue = "1")
private Integer quantity;
~~~

Không nên giả định property bị thiếu sẽ tự nhận 1. Hãy dùng một trong các cách có hành vi runtime rõ ràng:

- Field initializer/setter default trên mutable bean.
- JsonSetter(nulls = ...) cho explicit null.
- Constructor/factory tự áp dụng default.
- Domain mapper hoặc normalizer.
- Custom deserializer khi cần phân biệt presence và null.

Nếu dùng JSON Schema, keyword default cũng thường là annotation mô tả giá trị gợi ý, không tự sửa JSON đầu vào trừ khi validator/processor được cấu hình để áp dụng default. Cần kiểm tra công cụ cụ thể đang dùng.

## 13. Phân biệt default kỹ thuật và default nghiệp vụ

Không phải default nào cũng nên đặt trong Jackson DTO. Có thể chia thành hai nhóm:

| Loại default | Ví dụ | Nơi phù hợp |
| --- | --- | --- |
| Default định dạng/input | Property tùy chọn bị thiếu được hiểu là list rỗng theo contract JSON | DTO/deserialization layer |
| Default nghiệp vụ | Đơn hàng không chỉ định currency thì dùng currency theo tenant | Domain mapper/domain service |
| Default vận hành | Input file lấy từ job parameter hoặc cấu hình triển khai | JobParameters/configuration |
| Default persistence | Cột database có giá trị mặc định khi insert | Database schema/SQL writer |

Ví dụ, VND có thể là default của hợp đồng JSON nếu mọi producer đều dùng cùng currency. Nhưng nếu currency phụ thuộc tenant hoặc thị trường, default nên được quyết định bởi domain service có đủ context, không hardcode trong Jackson DTO.

Tương tự, quantity mặc định bằng 1 có thể là quy tắc nghiệp vụ. Đặt nó trong domain factory giúp các đường vào khác (REST, batch, message) áp dụng cùng quy tắc.

## 14. Chuẩn hóa dữ liệu sau deserialize

Một cách dễ kiểm soát là deserialize vào input DTO, sau đó chạy validation/normalization trước khi tạo domain object:

~~~java
public class OrderInputNormalizer {

    public NormalizedOrder normalize(OrderInput input) {
        if (input.getId() == null) {
            throw new InvalidOrderException("id is required");
        }

        Integer quantity = input.getQuantity();
        if (quantity == null) {
            quantity = 1;
        }
        if (quantity <= 0) {
            throw new InvalidOrderException(
                "quantity must be greater than zero"
            );
        }

        String currency = input.getCurrency();
        if (currency == null || currency.isBlank()) {
            currency = "VND";
        }

        return new NormalizedOrder(
            input.getId(),
            quantity,
            currency,
            input.getNote()
        );
    }
}
~~~

Normalizer là ví dụ khi contract quy định null/blank quantity và currency đều nhận default. Nếu explicit null có nghĩa xóa hoặc từ chối, hãy sửa quy tắc tương ứng thay vì áp dụng default chung.

Không sửa trực tiếp DTO input nếu nó được log, audit hoặc dùng để đối chiếu payload gốc. Tạo normalized object riêng giúp giữ lại dữ liệu đầu vào và kết quả sau chuẩn hóa.

## 15. Phân biệt missing và null bằng JsonNode

Nếu nghiệp vụ cần phân biệt property không tồn tại với property explicit null, JsonNode cung cấp API phù hợp:

- has("field"): property có tồn tại hay không.
- hasNonNull("field"): property tồn tại và không phải JSON null.
- get("field"): trả node hoặc null nếu property không tồn tại.
- isNull(): kiểm tra JSON null.

Ví dụ:

~~~java
public OrderInput map(JsonNode node) {
    boolean noteWasProvided = node.has("note");
    JsonNode noteNode = node.get("note");

    String note;
    if (!noteWasProvided) {
        note = null; // không được gửi
    } else if (noteNode == null || noteNode.isNull()) {
        note = null; // explicit null
    } else {
        note = noteNode.asText();
    }

    return new OrderInput(
        node.path("id").asLong(),
        noteWasProvided,
        note
    );
}
~~~

DTO có thể giữ presence flag:

~~~java
public record OrderInput(
    long id,
    boolean noteProvided,
    String note
) {}
~~~

Sau đó domain mapper có thể áp dụng patch semantics:

- noteProvided == false: giữ ghi chú hiện tại.
- noteProvided == true và note == null: xóa ghi chú.
- noteProvided == true và note khác null: cập nhật ghi chú.

Đây là cách hữu ích khi batch xử lý JSON dạng update/patch, nơi missing và null có ý nghĩa khác nhau.

## 16. Custom deserializer cho quy tắc phức tạp

Khi một field có quy tắc parsing phức tạp, có thể dùng JsonDeserializer:

~~~java
public class QuantityDeserializer
        extends JsonDeserializer<Integer> {

    @Override
    public Integer deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        JsonNode node = parser.getCodec().readTree(parser);
        if (node.isInt()) {
            return node.intValue();
        }
        if (node.isTextual() && node.asText().isBlank()) {
            return null;
        }
        throw JsonMappingException.from(
            parser,
            "quantity must be an integer"
        );
    }
}
~~~

Đăng ký trên property:

~~~java
public class OrderInput {

    @JsonDeserialize(using = QuantityDeserializer.class)
    private Integer quantity;
}
~~~

Deserializer thường được gọi khi property xuất hiện. Nếu property hoàn toàn bị thiếu, không có token để deserialize nên default cho missing vẫn cần được xử lý riêng. Với explicit null, Jackson có null provider và cấu hình Nulls quyết định có gọi deserializer hay không. Đừng giả định custom deserializer luôn nhận được cả missing lẫn null.

Không tạo custom deserializer chỉ để thay null bằng 0 nếu có thể diễn đạt rõ bằng JsonSetter, field initializer hoặc normalizer. Custom deserializer phù hợp khi định dạng đầu vào thực sự cần parsing riêng.

## 17. Nested object và default mapping

Nested object cũng có các trạng thái missing, null và object rỗng:

~~~json
{ "id": 101 }
~~~

~~~json
{ "id": 101, "shippingAddress": null }
~~~

~~~json
{ "id": 101, "shippingAddress": {} }
~~~

Chúng có thể biểu thị:

- Không cung cấp địa chỉ.
- Chủ động xóa địa chỉ.
- Có địa chỉ nhưng thiếu các thành phần.

Với mutable DTO, field initializer có thể cung cấp object mặc định khi property bị thiếu:

~~~java
public class OrderInput {

    private AddressInput shippingAddress = new AddressInput();

    @JsonSetter(
        value = "shippingAddress",
        nulls = Nulls.SKIP
    )
    public void setShippingAddress(AddressInput address) {
        this.shippingAddress = address;
    }
}
~~~

Khi property null, setter bị bỏ qua và object mặc định được giữ. Nhưng object rỗng {} vẫn được deserialize thành một AddressInput mới; các field con có thể null. Hãy validate nested object riêng, không giả định object rỗng là một địa chỉ hợp lệ.

## 18. Collection default và null phần tử

Với collection, cần quyết định riêng:

- Property bị thiếu có trở thành empty list hay giữ trạng thái chưa cung cấp?
- Explicit null có được xem là empty list hay là lỗi?
- Empty list có nghĩa xóa tất cả phần tử hay không thay đổi?
- Phần tử null trong list có được chấp nhận không?

Ví dụ DTO dùng empty list khi missing:

~~~java
public class OrderInput {

    private List<String> tags = new ArrayList<>();

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Với JSON không có tags, initializer giữ list rỗng. Nếu tags: null, Jackson mặc định có thể gán null; nếu không muốn điều đó, thêm JsonSetter(nulls = Nulls.SKIP) hoặc AS_EMPTY theo hợp đồng.

Tránh dùng Collections.emptyList() rồi sau đó sửa list trực tiếp. Nếu processor cần bổ sung tag, dùng collection mutable hoặc tạo collection mới.

## 19. Cấu hình ObjectMapper dùng trong batch

Có thể cấu hình một ObjectMapper bean để reader sử dụng chung:

~~~java
@Bean
ObjectMapper batchObjectMapper() {
    return JsonMapper.builder()
        .findAndAddModules()
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
        .build();
}
~~~

findAndAddModules() có thể đăng ký module có mặt trên classpath, chẳng hạn module Java Time. Cấu hình FAIL_ON_UNKNOWN_PROPERTIES khiến JSON có field lạ bị từ chối; điều này hữu ích nếu schema phải nghiêm ngặt nhưng có thể gây lỗi khi producer thêm field tương thích. Chọn strictness theo versioning policy của contract.

Không nên thay đổi cấu hình ObjectMapper sau khi đã bắt đầu dùng nó trong reader hoặc nhiều thread. Hãy cấu hình đầy đủ trước khi inject. Nếu một nhóm job có null policy khác nhau, có thể dùng mapper riêng cho từng contract thay vì thay đổi mapper toàn cục trong lúc chạy.

## 20. Default mapping và database writer

Sau khi JSON được deserialize và normalize, writer có thể ghi giá trị null xuống database. Cần phân biệt SQL NULL với default của database.

Ví dụ SQL:

~~~sql
insert into imported_order (order_id, note, quantity)
values (:orderId, :note, :quantity)
~~~

Nếu note được bind với giá trị null, database thường ghi SQL NULL. Default constraint của cột thường chỉ được áp dụng khi cột bị bỏ khỏi danh sách insert hoặc câu lệnh dùng từ khóa DEFAULT, tùy database.

Vì vậy:

- JSON property missing không tự động kích hoạt database default.
- JSON explicit null có thể trở thành SQL NULL.
- Java DTO field initializer có thể cung cấp giá trị để writer bind.
- Database default là một lớp quy tắc khác và cần được gọi rõ trong SQL khi muốn dùng.

Với JdbcBatchItemWriter và BeanPropertyItemSqlParameterSourceProvider, property null thường được bind như SQL NULL. Nếu cần để database tự dùng default, hãy viết SQL bỏ cột đó hoặc dùng câu lệnh có DEFAULT phù hợp với database. Đừng kỳ vọng parameter null tương đương với không truyền parameter.

## 21. Default mapping theo JobParameters và cấu hình job

Một số giá trị mặc định không thuộc payload JSON mà thuộc lần chạy job, ví dụ tenant mặc định, business date hoặc tên nguồn. Những giá trị này nên đến từ JobParameters hoặc application configuration.

Ví dụ:

~~~java
@Bean
@StepScope
JsonItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['tenantId'] ?: 'DEFAULT'}") String tenantId,
        ObjectMapper objectMapper) {

    // Reader dùng inputFile; tenantId được truyền vào processor
    // hoặc mapper theo contract của job.
    return new JsonItemReaderBuilder<OrderInput>()
        .name("orderJsonReader")
        .resource(new FileSystemResource(inputFile))
        .jsonObjectReader(
            new JacksonJsonObjectReader<>(OrderInput.class, objectMapper)
        )
        .saveState(true)
        .build();
}
~~~

Ví dụ SpEL default chỉ minh họa cách lấy giá trị cấu hình. Nếu tenant là định danh dữ liệu quan trọng, thường nên yêu cầu job parameter rõ ràng thay vì âm thầm dùng DEFAULT, tránh đọc/ghi nhầm tenant.

Job parameter xác định phạm vi execution; JSON field mô tả từng item. Không trộn hai nguồn giá trị nếu chúng có ownership khác nhau.

## 22. Validation sau JSON mapping

Deserialize thành công không đồng nghĩa dữ liệu hợp lệ về nghiệp vụ. JSON có thể đúng cú pháp nhưng thiếu ID, có quantity âm hoặc currency không được hỗ trợ.

Có thể dùng Bean Validation:

~~~java
public class OrderInput {

    @NotNull
    private Long id;

    @NotNull
    @Positive
    private Integer quantity;

    @NotBlank
    private String currency;
}
~~~

Processor thực hiện validation:

~~~java
public class ValidatingOrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final Validator validator;
    private final OrderDomainMapper mapper;

    @Override
    public Order process(OrderInput input) {
        Set<ConstraintViolation<OrderInput>> violations =
            validator.validate(input);

        if (!violations.isEmpty()) {
            throw new InvalidOrderException(
                violations.toString()
            );
        }

        return mapper.toDomain(input);
    }
}
~~~

Nếu validation exception được cấu hình skip, item lỗi có thể bị loại theo skip policy. Lỗi JSON parse hoặc type mismatch xảy ra ngay trong reader và được xử lý theo exception/policy của phase read. Không phải mọi mapping error đều nên skip.

## 23. Skip và retry khi JSON có null hoặc thiếu field

Phân loại lỗi theo khả năng phục hồi:

| Tình huống | Xử lý thường phù hợp |
| --- | --- |
| Field tùy chọn bị thiếu và có default hợp lệ | Áp dụng default theo contract |
| Explicit null không được phép | Fail mapping hoặc validation |
| Một record có dữ liệu nghiệp vụ sai | Skip nếu nghiệp vụ cho phép |
| JSON hỏng cú pháp hoặc schema không tương thích | Thường fail hoặc cách ly nguồn theo policy |
| Lỗi đọc file/storage tạm thời | Có thể retry theo exception phù hợp |
| Giá trị null có nghĩa xóa dữ liệu | Giữ presence semantics và xử lý như một lệnh update |

Không retry một JSON record có quantity âm hoặc currency sai với hy vọng lần sau dữ liệu tự đúng. Retry phù hợp với lỗi tạm thời của resource; dữ liệu không hợp lệ cần validation, skip hoặc fail.

Nếu dùng JsonItemReader, một lỗi deserialize có thể xảy ra trước khi processor nhận được item. Muốn skip lỗi parse, cấu hình skip exception phù hợp với loại exception thực tế của reader và test với phiên bản Spring Batch/Jackson đang dùng.

## 24. Kiểm thử null/default mapping ở cấp ObjectMapper

Unit test DTO với ObjectMapper giúp xác nhận rõ hành vi missing, null và value. Ví dụ:

~~~java
@Test
void keepsDefaultWhenCurrencyIsMissing() throws Exception {
    OrderInput input =
        objectMapper.readValue("{\"id\":101}", OrderInput.class);

    assertThat(input.getCurrency()).isEqualTo("VND");
}

@Test
void keepsDefaultWhenCurrencyIsExplicitNull() throws Exception {
    OrderInput input = objectMapper.readValue(
        "{\"id\":101,\"currency\":null}",
        OrderInput.class
    );

    assertThat(input.getCurrency()).isEqualTo("VND");
}

@Test
void acceptsExplicitCurrency() throws Exception {
    OrderInput input = objectMapper.readValue(
        "{\"id\":101,\"currency\":\"USD\"}",
        OrderInput.class
    );

    assertThat(input.getCurrency()).isEqualTo("USD");
}
~~~

Hai test đầu chỉ đúng nếu DTO dùng initializer cùng JsonSetter(nulls = Nulls.SKIP) như ví dụ trước. Nếu bỏ annotation, explicit null có thể ghi đè initializer. Test nên dùng mapper và DTO giống cấu hình production.

Với Nulls.FAIL, xác nhận explicit null ném JsonMappingException hoặc exception tương ứng. Với property missing, viết test riêng để tránh nhầm lẫn rằng Nulls.FAIL cũng làm field bắt buộc.

## 25. Ma trận test cho các dạng JSON

Với mỗi field quan trọng, nên có bộ test bao phủ các trạng thái:

| Input | Kết quả cần xác định |
| --- | --- |
| Property không có | Default, absent flag hay validation error |
| Property là null | Skip, set null, empty hoặc error |
| Property là chuỗi rỗng | Giữ empty, normalize hay error |
| Property là 0/false | Giá trị hợp lệ hay vi phạm business rule |
| Property là [] | Collection rỗng hay thao tác xóa |
| Property là {} | Object rỗng có hợp lệ không |
| Property có kiểu sai | Mapping error, không âm thầm dùng default |
| Collection có phần tử null | Chấp nhận, bỏ qua hay fail |
| Field lạ | Bỏ qua hay từ chối theo schema policy |

Đặc biệt, test riêng missing và explicit null. Đây là hai trường hợp dễ bị gộp nhầm khi dùng primitive, constructor-based DTO hoặc custom deserializer.

## 26. Integration test với JsonItemReader

Unit test ObjectMapper không chứng minh JsonItemReader đọc toàn bộ file và áp dụng mapper đúng trong step. Hãy thêm integration test với file JSON thực:

1. Tạo file JSON có nhiều object, bao gồm field missing, explicit null, empty string và value.
2. Cấu hình JsonItemReader với JacksonJsonObjectReader và đúng ObjectMapper production.
3. Chạy step với processor normalize/validate và writer thu thập hoặc lưu kết quả.
4. Xác nhận từng item có default/null semantics mong muốn.
5. Thử một record không hợp lệ và xác nhận skip/fail theo policy.
6. Chạy lại/restart nếu reader cần checkpoint và xác nhận mapping không thay đổi.

Ví dụ file fixture:

~~~json
[
  { "id": 1, "quantity": 3, "currency": "USD" },
  { "id": 2 },
  { "id": 3, "quantity": null, "currency": null },
  { "id": 4, "quantity": 0, "currency": "" }
]
~~~

Kết quả mong đợi phải được xác định trong test theo contract. Không viết assertion rằng mọi trường hợp đều dùng default nếu nghiệp vụ chưa quyết định missing, null, zero và empty có cùng ý nghĩa hay không.

## 27. Kiểm thử mapping khi schema JSON thay đổi

Producer có thể thêm field, đổi kiểu hoặc thay cách biểu diễn null. Cần xác định compatibility policy:

- Thêm property tùy chọn: có thể được chấp nhận nếu FAIL_ON_UNKNOWN_PROPERTIES tắt.
- Thêm property không được hỗ trợ: strict mapper có thể fail, giúp phát hiện contract drift.
- Đổi number thành string: cần quyết định có coercion hay không.
- Đổi field thành nullable: cần test Nulls policy.
- Đổi default: có thể làm thay đổi kết quả của các file cũ khi restart/reprocess.
- Đổi nested object thành null: cần test riêng null handling và domain invariant.

Với batch cần xử lý lại file cũ, lưu schema version hoặc batch version trong metadata. Mapper có thể chọn cách chuyển đổi theo version thay vì thay default toàn cục khiến cùng một payload cho kết quả khác giữa các lần triển khai.

## 28. Những lỗi thường gặp khi xử lý null và default mapping

**Coi missing và null là một:** producer có thể dùng null để xóa field còn missing để giữ nguyên. Giữ presence information nếu contract cần phân biệt.

**Chỉ dùng field initializer:** initializer không ngăn explicit null ghi đè field. Thêm null policy hoặc normalizer phù hợp.

**Dùng primitive cho field nullable:** không phân biệt được missing/null với 0 hoặc false. Dùng wrapper khi presence có ý nghĩa.

**Cho rằng JsonProperty(defaultValue) tự gán default:** thuộc tính này không tự áp dụng runtime default trong Jackson databind. Dùng initializer, setter, creator hoặc mapper.

**Cho rằng Nulls.FAIL bắt cả property missing:** annotation xử lý explicit null; validate missing riêng.

**Dùng AS_EMPTY cho mọi field:** empty string/list có thể khác null về nghiệp vụ. Chỉ gộp khi contract cho phép.

**Không cấu hình contentNulls:** property list có thể hợp lệ nhưng phần tử null bên trong vẫn lọt qua. Đặt policy cho collection element.

**Đặt business default trong DTO:** default phụ thuộc tenant, currency hoặc ngày nghiệp vụ nên ở domain/configuration layer có context.

**Bắt mọi mapping exception rồi trả object mặc định:** làm dữ liệu lỗi trở thành item có vẻ hợp lệ. Phân loại parse, validation và infrastructure error.

**Nhầm JSON null với SQL NULL và database default:** parameter null thường ghi SQL NULL; database default không tự áp dụng khi cột được bind null.

**Dùng custom deserializer cho property missing:** deserializer thường không được gọi nếu property không xuất hiện. Xử lý missing ở creator, normalizer hoặc representation có presence flag.

**Không test mapper production thực tế:** test với ObjectMapper mặc định có thể khác mapper được cấu hình trong batch. Inject đúng bean và test cả reader.

## 29. Quy trình thiết kế null/default mapping cho production

Trước tiên, xác định ý nghĩa của từng field trong JSON contract. Với mỗi property, ghi rõ field có bắt buộc không, missing có khác explicit null không, empty string/collection có hợp lệ không và default đến từ producer contract hay nghiệp vụ. Đừng áp dụng một chính sách chung cho mọi field.

Tiếp theo, chọn cách mapping phù hợp. Dùng wrapper type khi cần phân biệt null với primitive default; dùng field initializer và JsonSetter cho mutable DTO khi missing/null có default rõ ràng; dùng Nulls.FAIL cho explicit null không được phép; dùng contentNulls cho collection element; dùng constructor/factory hoặc JsonNode khi cần kiểm soát presence. Đặt default phụ thuộc nghiệp vụ ở normalizer/domain mapper, không giấu trong Jackson config.

Cuối cùng, cấu hình ObjectMapper trước khi dùng và inject cùng mapper đó vào JacksonJsonObjectReader. Test từng trạng thái JSON ở unit level, sau đó test toàn bộ JsonItemReader/step với file fixture thực. Kiểm tra cả lỗi parse, validation, skip/fail policy và cách writer bind null xuống database. Nếu batch cần restart/reprocess file cũ, quản lý schema version và giữ default semantics tương thích.

Null field và default mapping là một phần của hợp đồng dữ liệu giữa producer và batch job. Property missing, explicit null, empty và value phải được xử lý có chủ đích. Jackson cung cấp các công cụ như JsonSetter, Nulls, creator features và custom deserializer; Spring Batch đưa object đã map vào pipeline để validation, skip, retry và ghi dữ liệu. Khi default được đặt đúng lớp và test bao phủ từng dạng input, batch tránh được việc âm thầm biến dữ liệu thiếu hoặc sai thành giá trị nghiệp vụ không chính xác.
