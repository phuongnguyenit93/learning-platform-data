# Xử lý xung đột tên thuộc tính sau khi làm phẳng

Jackson có thể đưa các thuộc tính của một object con lên cùng cấp với thuộc tính của object cha bằng annotation @JsonUnwrapped. Kỹ thuật này tạo JSON phẳng, thuận tiện cho một số API hoặc định dạng trao đổi cũ. Tuy nhiên, khi object cha và object con có thuộc tính trùng tên, quá trình làm phẳng có thể tạo ra hai field cùng tên trong một JSON object.

Ví dụ, object cha có id của đơn hàng, còn object con có id của khách hàng. Nếu cả hai cùng được làm phẳng mà không đổi tên, JSON có thể chứa hai thuộc tính id. Điều đó làm dữ liệu khó hiểu và khiến việc deserialize không còn xác định rõ giá trị thuộc về đối tượng nào.

Cách xử lý là thiết kế tên wire sao cho duy nhất sau khi áp dụng mọi quy tắc ánh xạ. Jackson hỗ trợ prefix và suffix trên @JsonUnwrapped; ngoài ra có thể đổi tên bằng @JsonProperty, giữ object lồng nhau, hoặc tự làm phẳng bằng tree model với bước kiểm tra collision.

## 1. Làm phẳng object bằng @JsonUnwrapped

Thông thường, một object Java lồng nhau được serialize thành một JSON object con:

~~~java
public class ContactInfo {
    public String email;
    public String phone;
}

public class CustomerResponse {
    public String id;
    public ContactInfo contact;
}
~~~

Dữ liệu JSON có dạng:

~~~json
{
  "id": "CUS-100",
  "contact": {
    "email": "linh@example.com",
    "phone": "0900000000"
  }
}
~~~

Nếu hợp đồng yêu cầu các thuộc tính của contact xuất hiện trực tiếp ở cấp ngoài, có thể dùng @JsonUnwrapped:

~~~java
import com.fasterxml.jackson.annotation.JsonUnwrapped;

public class CustomerResponse {
    public String id;

    @JsonUnwrapped
    public ContactInfo contact;
}
~~~

Kết quả được làm phẳng:

~~~json
{
  "id": "CUS-100",
  "email": "linh@example.com",
  "phone": "0900000000"
}
~~~

Jackson lấy các property của ContactInfo và ghi chúng ở cùng cấp với id. Khi deserialize, các field tương ứng được gom lại để tạo ContactInfo.

Kỹ thuật này hữu ích khi phải tuân theo một wire format phẳng nhưng vẫn muốn mô hình Java được tổ chức thành các object có trách nhiệm riêng.

## 2. Vì sao làm phẳng có thể tạo xung đột tên?

Giả sử response có id riêng của đơn hàng và object customer cũng có id:

~~~java
public class CustomerInfo {
    public String id;
    public String displayName;
}

public class OrderResponse {
    public String id;
    @JsonUnwrapped
    public CustomerInfo customer;
}
~~~

Cả hai thuộc tính Java đều được ánh xạ thành tên JSON id. Output có thể chứa hai field cùng tên:

~~~json
{
  "id": "ORD-100",
  "id": "CUS-17",
  "displayName": "Linh"
}
~~~

Một JSON object nên có tên member duy nhất. RFC 8259 khuyến nghị tên trong object là duy nhất; khi tên bị lặp, hành vi của các consumer có thể khác nhau. Một parser có thể giữ giá trị cuối, parser khác có thể giữ giá trị đầu, báo lỗi hoặc biểu diễn cả hai trong mô hình nội bộ.

Do đó, không nên dựa vào thứ tự field để giải quyết collision. Dù Jackson có thể ghi hoặc đọc một số trường hợp như vậy, output không còn là một hợp đồng rõ ràng và có khả năng tương thích tốt.

Xung đột có thể xuất hiện giữa:

- Property của object cha và property của object con được unwrapped.
- Hai object con cùng được unwrapped vào một cấp.
- Property được đổi tên bằng @JsonProperty và property khác có cùng tên wire.
- Property sau khi áp dụng naming strategy.
- Property tĩnh và field động do @JsonAnyGetter đưa vào output.

Điều cần kiểm tra là tên JSON cuối cùng, không chỉ tên field hoặc getter trong Java.

## 3. Dùng prefix để tạo namespace cho property được làm phẳng

Cách phổ biến nhất là thêm prefix vào mọi property của object con:

~~~java
public class OrderResponse {
    public String id;

    @JsonUnwrapped(prefix = "customer_")
    public CustomerInfo customer;
}
~~~

Với CustomerInfo có id và displayName, JSON sẽ có dạng:

~~~json
{
  "id": "ORD-100",
  "customer_id": "CUS-17",
  "customer_displayName": "Linh"
}
~~~

Tên id của order được giữ nguyên, còn các field của customer có prefix customer_. Nhờ vậy, tên wire không còn trùng nhau.

Prefix có thể mô tả vai trò của object con:

- customer_ cho thông tin khách hàng.
- billing_ cho địa chỉ thanh toán.
- shipping_ cho địa chỉ giao hàng.
- audit_ cho metadata kiểm toán.
- payment_ cho thông tin thanh toán.

Ví dụ hai object con cùng có field id:

~~~java
public class AddressInfo {
    public String id;
    public String city;
}

public class OrderResponse {
    public String id;

    @JsonUnwrapped(prefix = "billing_")
    public AddressInfo billingAddress;

    @JsonUnwrapped(prefix = "shipping_")
    public AddressInfo shippingAddress;
}
~~~

Output:

~~~json
{
  "id": "ORD-100",
  "billing_id": "ADDR-01",
  "billing_city": "Ha Noi",
  "shipping_id": "ADDR-02",
  "shipping_city": "Da Nang"
}
~~~

Prefix không chỉ tránh collision mà còn giúp consumer hiểu field thuộc nhóm dữ liệu nào.

## 4. Dùng suffix khi wire format yêu cầu tên kết thúc theo quy ước

@JsonUnwrapped cũng hỗ trợ suffix:

~~~java
public class OrderResponse {
    public String id;

    @JsonUnwrapped(suffix = "_customer")
    public CustomerInfo customer;
}
~~~

Nếu CustomerInfo có id và displayName, tên JSON trở thành id_customer và displayName_customer.

Có thể kết hợp cả prefix và suffix:

~~~java
public class OrderResponse {
    public String id;

    @JsonUnwrapped(
        prefix = "customer_",
        suffix = "_value"
    )
    public CustomerInfo customer;
}
~~~

Ví dụ kết quả:

~~~json
{
  "id": "ORD-100",
  "customer_id_value": "CUS-17",
  "customer_displayName_value": "Linh"
}
~~~

Prefix và suffix là quy tắc đổi tên áp dụng cho các property được unwrapped. Hãy chọn quy ước dễ đọc và thống nhất giữa producer với consumer. Tránh prefix/suffix quá chung chung hoặc có thể đụng với tên field khác trong object cha.

## 5. Đổi tên riêng một property bằng @JsonProperty

Nếu chỉ có một hoặc vài field gây xung đột, có thể đổi tên wire của property cụ thể:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public class CustomerInfo {
    @JsonProperty("customer_id")
    public String id;

    public String displayName;
}

public class OrderResponse {
    public String id;

    @JsonUnwrapped
    public CustomerInfo customer;
}
~~~

JSON kết quả:

~~~json
{
  "id": "ORD-100",
  "customer_id": "CUS-17",
  "displayName": "Linh"
}
~~~

Cách này phù hợp khi tên wire cần theo một hợp đồng đã tồn tại hoặc từng field có quy ước riêng.

Cần phân biệt tên Java với tên wire:

| Tên Java | Tên JSON |
|---|---|
| OrderResponse.id | id |
| CustomerInfo.id | customer_id |
| CustomerInfo.displayName | displayName |

Jackson dùng tên property sau khi áp dụng annotation và các quy tắc cấu hình để serialize/deserialize. Khi thiết kế, hãy lập danh sách tên JSON cuối cùng và xác nhận không có hai property cùng dùng một tên.

Nếu đổi tên một property trong object con, hãy kiểm tra cả chiều deserialize. @JsonProperty xác định tên wire chính cho property đó; consumer phải gửi đúng tên đã công bố.

## 6. Giữ object lồng nhau nếu không bắt buộc phải làm phẳng

Không phải lúc nào cũng cần @JsonUnwrapped. Nếu hợp đồng API cho phép object lồng nhau, cấu trúc sau thường rõ ràng hơn:

~~~json
{
  "id": "ORD-100",
  "customer": {
    "id": "CUS-17",
    "displayName": "Linh"
  }
}
~~~

Java:

~~~java
public class OrderResponse {
    public String id;
    public CustomerInfo customer;
}
~~~

Ưu điểm:

- Tên id có thể tồn tại ở nhiều cấp mà không xung đột.
- Cấu trúc JSON thể hiện rõ quan hệ cha/con.
- Dễ mở rộng object con mà không thêm nhiều field ở root.
- Consumer có thể ánh xạ từng object vào DTO riêng.
- Ít phụ thuộc vào quy tắc unwrapping của Jackson.

Nếu đang thiết kế API mới, hãy ưu tiên cấu trúc lồng nhau khi nó phản ánh đúng mô hình dữ liệu. Chỉ làm phẳng khi wire contract yêu cầu, khi cần tương thích với định dạng hiện có hoặc khi cấu trúc phẳng thực sự có lợi cho consumer.

## 7. Xung đột sau khi áp dụng naming strategy

Tên Java có thể khác tên JSON do naming strategy. Ví dụ, mapper dùng SNAKE_CASE:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Property Java customerId có thể được ghi thành customer_id. Nếu một property khác đã được đặt tên tường minh thành customer_id, hai tên wire có thể đụng nhau.

Tương tự, @JsonProperty có thể ghi đè tên mặc định của naming strategy. Vì vậy, kiểm tra tên field Java bằng mắt là chưa đủ.

Một quy trình kiểm tra nên xem xét:

1. Tên property được Jackson phát hiện từ field, getter, setter hoặc creator.
2. Tên bị thay đổi bởi @JsonProperty hay naming strategy.
3. Prefix/suffix được áp dụng bởi @JsonUnwrapped.
4. Tên động được thêm bởi @JsonAnyGetter.
5. Các tên cuối cùng có duy nhất trong cùng object hay không.

Nếu hai property có cùng tên sau khi áp dụng các quy tắc này, hãy đổi một tên bằng annotation hoặc prefix/suffix. Không dùng @JsonPropertyOrder để xử lý vì annotation đó chỉ điều khiển thứ tự, không đổi tên và không loại bỏ collision.

## 8. Hai object con được unwrapped cùng lúc

Một response có thể flatten nhiều object con:

~~~java
public class AuditInfo {
    public String id;
    public String createdBy;
}

public class PaymentInfo {
    public String id;
    public String status;
}

public class OrderResponse {
    public String id;

    @JsonUnwrapped(prefix = "audit_")
    public AuditInfo audit;

    @JsonUnwrapped(prefix = "payment_")
    public PaymentInfo payment;
}
~~~

JSON:

~~~json
{
  "id": "ORD-100",
  "audit_id": "AUD-01",
  "audit_createdBy": "system",
  "payment_id": "PAY-01",
  "payment_status": "paid"
}
~~~

Nếu cả hai object con không có prefix, chúng cùng đưa id lên root và tạo collision. Prefix riêng tạo namespace cho từng nhóm.

Khi có nhiều lớp unwrapped lồng nhau, hãy tính tên cuối cùng xuyên suốt tất cả cấp. Đừng chỉ kiểm tra từng object con riêng lẻ: hai nhánh có thể không trùng tên bên trong nhưng vẫn trùng sau khi cùng được đưa lên một parent.

Với cấu trúc lồng sâu hoặc nhiều nhóm dữ liệu, một quy ước prefix thống nhất giúp tránh phải đổi tên thủ công từng field.

## 9. @JsonAnyGetter và @JsonAnySetter cũng có thể tạo collision

@JsonUnwrapped phù hợp với một POJO con có cấu trúc đã biết. Nếu cần đưa các field động từ Map lên root object, Jackson có @JsonAnyGetter:

~~~java
public class ExtensibleResponse {
    public String id;

    private final Map<String, Object> attributes = new LinkedHashMap<>();

    @JsonAnyGetter
    public Map<String, Object> attributes() {
        return attributes;
    }

    @JsonAnySetter
    public void addAttribute(String name, Object value) {
        attributes.put(name, value);
    }
}
~~~

@JsonAnyGetter ghi các entry của Map như các property cùng cấp với id. @JsonAnySetter nhận những property chưa được ánh xạ vào property thông thường khi deserialize.

Nhưng nếu Map attributes chứa key id, output có thể có tên id trùng với property id của class. Vì vậy, field động cũng cần namespace hoặc danh sách tên bị cấm.

Ví dụ kiểm tra tên dành riêng trước khi thêm:

~~~java
private static final Set<String> RESERVED_NAMES =
    Set.of("id", "status", "createdAt");

public void addAttribute(String name, Object value) {
    if (RESERVED_NAMES.contains(name)) {
        throw new IllegalArgumentException(
            "Reserved JSON property name: " + name
        );
    }

    attributes.put(name, value);
}
~~~

Trong hệ thống thực tế, hãy kiểm tra tên sau khi áp dụng quy tắc chuẩn hóa tương ứng. Nếu tên field động có thể đến từ đối tác, có thể dùng prefix như ext_ để tránh va chạm với property tĩnh.

@JsonAnyGetter và @JsonAnySetter giải quyết field động; chúng không phải cách thay thế trực tiếp cho @JsonUnwrapped trên một POJO có schema cố định.

## 10. @JsonUnwrapped không phải cách flatten mọi loại dữ liệu

@JsonUnwrapped được thiết kế chủ yếu để làm phẳng property của POJO. Không nên mặc định annotation này có thể làm phẳng mọi cấu trúc như Map, JsonNode, array hoặc collection.

Nếu dữ liệu con là Map động, cân nhắc @JsonAnyGetter hoặc tự đưa các entry vào ObjectNode. Nếu dữ liệu là JsonNode, tree model cho phép kiểm tra và đổi tên field rõ ràng trước khi gắn vào output.

Nếu kiểu dữ liệu có custom serializer hoặc cấu trúc đặc biệt, hãy kiểm tra khả năng hỗ trợ của phiên bản Jackson đang dùng. Một số cách ánh xạ phức tạp, đặc biệt creator-based immutable object, có thể có giới hạn với unwrapped properties. Không nên giả định mọi tổ hợp @JsonUnwrapped, constructor @JsonCreator và custom deserializer đều hoạt động giống nhau trên mọi phiên bản.

Với DTO bất biến dùng constructor creator, hãy viết test trên phiên bản Jackson thực tế. Nếu binding unwrapped không được hỗ trợ theo cách cần thiết, các lựa chọn an toàn là dùng wrapper DTO có setter, đọc JsonNode rồi chuyển đổi, hoặc viết custom deserializer.

## 11. Tự làm phẳng bằng ObjectNode khi cần kiểm soát collision

Khi quy tắc flatten phức tạp hoặc cần xử lý field động, có thể tạo JSON output bằng tree model. Cách này cho phép kiểm tra tên trước khi gắn property.

Ví dụ:

~~~java
ObjectNode flattenOrder(
        ObjectMapper mapper,
        OrderResponse order) {

    ObjectNode output = mapper.createObjectNode();

    putUnique(output, "id", mapper.valueToTree(order.id()));

    ObjectNode customer = mapper.valueToTree(order.customer());

    customer.fields().forEachRemaining(entry -> {
        String flattenedName = "customer_" + entry.getKey();
        putUnique(output, flattenedName, entry.getValue().deepCopy());
    });

    return output;
}

private static void putUnique(
        ObjectNode target,
        String name,
        JsonNode value) {

    if (target.has(name)) {
        throw new IllegalArgumentException(
            "Duplicate JSON property after flattening: " + name
        );
    }

    target.set(name, value);
}
~~~

Hàm putUnique từ chối tên đã tồn tại thay vì ghi đè âm thầm. Khi thêm một object con khác, dùng prefix riêng và cùng hàm kiểm tra.

Trong code thực tế, nếu value là Java null, hãy chuyển rõ thành NullNode hoặc dùng putNull thay vì truyền Java null cho set(). Cũng cần kiểm tra order.customer() có null hay không trước khi gọi valueToTree.

Tree model đặc biệt hữu ích khi:

- Prefix phụ thuộc dữ liệu hoặc loại message.
- Một số field cần được đổi tên theo quy tắc riêng.
- Có nhiều nguồn dữ liệu động cùng được gộp.
- Cần báo lỗi rõ khi hai nguồn tạo cùng tên.
- Muốn kiểm tra và loại bỏ các field bị cấm trước khi serialize.

Nếu cần deserialize lại output phẳng, có thể tách các field theo prefix, tạo subtree rồi dùng treeToValue để ánh xạ vào DTO con. Cần kiểm tra các field bắt buộc và từ chối tên không hợp lệ theo hợp đồng.

## 12. Collision không được giải quyết bằng thứ tự field

Một số người cố đưa field cha lên trước hoặc sau field con bằng @JsonPropertyOrder, với hy vọng consumer sẽ lấy đúng giá trị. Cách này không an toàn.

Ví dụ:

~~~json
{
  "id": "ORD-100",
  "id": "CUS-17"
}
~~~

Đổi thứ tự hai field không làm tên trở nên duy nhất. Consumer vẫn phải quyết định xử lý duplicate name như thế nào, và các parser có thể khác nhau.

Các cơ chế sau không giải quyết collision:

- @JsonPropertyOrder: chỉ điều khiển thứ tự ghi.
- INDENT_OUTPUT: chỉ thay đổi khoảng trắng và cách trình bày.
- ORDER_MAP_ENTRIES_BY_KEYS: chỉ sắp xếp entry của Map.
- SORT_PROPERTIES_ALPHABETICALLY: chỉ sắp xếp property, không đổi tên trùng.
- @JsonAlias: bổ sung tên được chấp nhận khi đọc, không tạo namespace cho hai giá trị cùng tên.

Cần đổi tên, thêm prefix/suffix, giữ cấu trúc lồng nhau hoặc từ chối dữ liệu có collision.

## 13. Kiểm thử serialize và deserialize sau khi làm phẳng

Một test nên xác nhận cả hai chiều:

- Output có tên property duy nhất.
- Prefix/suffix được áp dụng đúng.
- Giá trị của object cha không bị nhầm với object con.
- Deserialize tạo lại đúng object con.
- Các field không biết hoặc field động được xử lý theo hợp đồng.

Ví dụ với mutable bean:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.annotation.JsonUnwrapped;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class UnwrappedCollisionTest {

    public static class CustomerInfo {
        public String id;
        public String displayName;

        public CustomerInfo() {}
    }

    public static class OrderResponse {
        public String id;

        @JsonUnwrapped(prefix = "customer_")
        public CustomerInfo customer;

        public OrderResponse() {}
    }

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void prefixKeepsFlattenedNamesUniqueAndRoundTrips() throws Exception {
        OrderResponse order = new OrderResponse();
        order.id = "ORD-100";

        order.customer = new CustomerInfo();
        order.customer.id = "CUS-17";
        order.customer.displayName = "Linh";

        String json = mapper.writeValueAsString(order);
        JsonNode tree = mapper.readTree(json);

        assertTrue(tree.has("id"));
        assertTrue(tree.has("customer_id"));
        assertTrue(tree.has("customer_displayName"));
        assertEquals("ORD-100", tree.path("id").asText());
        assertEquals("CUS-17", tree.path("customer_id").asText());

        OrderResponse restored =
            mapper.readValue(json, OrderResponse.class);

        assertEquals("ORD-100", restored.id);
        assertEquals("CUS-17", restored.customer.id);
        assertEquals("Linh", restored.customer.displayName);
    }
}
~~~

Test này dùng class mutable có constructor không tham số để minh họa binding unwrapped thông thường. Nếu dự án dùng record hoặc constructor @JsonCreator, hãy kiểm tra riêng trên đúng phiên bản Jackson vì khả năng hỗ trợ creator property có thể khác.

Ngoài round-trip test, nên kiểm tra tên JSON bằng tree hoặc parser. Nếu chỉ deserialize rồi so sánh object, một số trường hợp duplicate key có thể bị parser xử lý theo một quy tắc cụ thể và test không phát hiện output không rõ ràng.

Có thể kiểm tra duplicate field trong quá trình parse bằng cơ chế STRICT_DUPLICATE_DETECTION của JsonParser:

~~~java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper strictMapper = new ObjectMapper(factory);
~~~

Khi parser gặp tên field lặp trong một object, strict duplicate detection có thể báo lỗi. Hãy dùng nó trong test hoặc tại ranh giới nhận dữ liệu nếu hợp đồng yêu cầu từ chối duplicate names. Nó giúp phát hiện vấn đề, nhưng không thay thế việc thiết kế tên property duy nhất khi serialize.

## 14. Quy trình xử lý xung đột tên sau khi flatten

Khi thêm một property unwrapped, hãy xác định tất cả tên wire có thể được tạo ra:

1. Liệt kê property của object cha.
2. Liệt kê property của từng object con được unwrapped.
3. Áp dụng @JsonProperty và naming strategy.
4. Thêm prefix/suffix của từng nhánh.
5. Thêm các field động do @JsonAnyGetter hoặc custom serializer tạo ra.
6. Kiểm tra tên cuối cùng có duy nhất trong cùng object hay không.
7. Kiểm tra cả serialize và deserialize.
8. Thử input có field thiếu, null, field lạ và duplicate name nếu những trường hợp đó thuộc phạm vi hợp đồng.

Có thể lập bảng tên wire:

| Nguồn | Property Java | Tên JSON cuối cùng |
|---|---|---|
| OrderResponse | id | id |
| CustomerInfo | id | customer_id |
| CustomerInfo | displayName | customer_displayName |
| PaymentInfo | id | payment_id |
| PaymentInfo | status | payment_status |

Bảng này làm lộ collision trước khi triển khai. Nó cũng là tài liệu hữu ích cho consumer của API.

Nếu hai nguồn vẫn tạo cùng tên, hãy dừng quá trình tạo output và báo lỗi cấu hình hoặc dữ liệu. Không âm thầm ghi đè một giá trị bằng giá trị khác vì như vậy có thể làm mất thông tin.

## 15. Chọn giải pháp theo loại cấu trúc

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Một POJO con có vài field trùng tên với cha | @JsonUnwrapped(prefix = "...") hoặc suffix. |
| Chỉ một property con cần tên wire khác | @JsonProperty trên property con. |
| Nhiều POJO con được flatten | Dùng prefix riêng cho từng nhánh. |
| Map chứa field động | @JsonAnyGetter/@JsonAnySetter và kiểm tra tên dành riêng. |
| JsonNode cần flatten có kiểm soát | Dùng ObjectNode, đổi tên từng field và từ chối collision. |
| API cho phép cấu trúc lồng nhau | Giữ object con thay vì flatten. |
| Immutable creator có unwrapped property | Xác nhận hỗ trợ trên phiên bản thực tế; cân nhắc wrapper DTO hoặc custom deserializer. |
| Tên bị trùng sau naming strategy | Đổi tên wire tường minh hoặc thay quy tắc đặt tên. |

## Kết luận

Làm phẳng object bằng @JsonUnwrapped đưa property của object con lên cùng cấp với object cha. Nếu hai nguồn có tên JSON giống nhau, output có thể chứa duplicate member và consumer không còn cách diễn giải nhất quán.

Hãy dùng prefix hoặc suffix để tạo namespace, đổi tên field bằng @JsonProperty khi cần, hoặc giữ object lồng nhau nếu hợp đồng cho phép. Với Map và dữ liệu động, dùng @JsonAnyGetter hoặc tree model cùng kiểm tra collision. Đánh giá tên sau khi áp dụng annotation, naming strategy và mọi quy tắc flatten; kiểm thử cả hai chiều để bảo đảm mỗi property có một tên wire duy nhất.

