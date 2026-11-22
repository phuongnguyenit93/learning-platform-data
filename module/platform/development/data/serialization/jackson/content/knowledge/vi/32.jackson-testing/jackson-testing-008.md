# Kiểm thử đa hình, chu trình và tham chiếu định danh

Jackson có thể serialize và deserialize các object graph phức tạp, trong đó một property khai báo kiểu cha nhưng runtime object thuộc subtype, nhiều property cùng trỏ tới một instance, hoặc các object tham chiếu vòng lại nhau. Những cấu trúc này không thể được kiểm tra đầy đủ chỉ bằng một assertion rằng JSON có field mong đợi. Bộ test cần xác nhận cả **hình dạng JSON**, **subtype được tạo**, **quan hệ identity sau khi đọc lại**, và **các trường hợp không hợp lệ bị từ chối đúng cách**.

Ba cơ chế thường gặp là polymorphic type metadata với `@JsonTypeInfo`, object identity với `@JsonIdentityInfo`/`@JsonIdentityReference`, và cặp `@JsonManagedReference`/`@JsonBackReference` cho quan hệ hai chiều dạng cha-con. Chúng giải quyết những vấn đề khác nhau, vì vậy test cần kiểm tra đúng contract của từng cơ chế.

Bài này xây dựng chiến lược kiểm thử bằng JUnit và Jackson Databind: kiểm tra subtype, discriminator thiếu hoặc lạ, object graph có chu trình, object được chia sẻ, ID-only reference, unresolved ID, và quan hệ managed/back reference. Nội dung cũng trình bày cách dùng JSON tree để assertion ổn định, cách giữ fixture tương thích và các lỗi thường gặp khi chỉ kiểm tra giá trị mà bỏ qua identity.

## 1. Ba hành vi cần kiểm thử riêng

| Cơ chế | Câu hỏi cần xác nhận | Dấu hiệu trong JSON |
|---|---|---|
| Polymorphism | Property base type được tạo thành subtype nào? | Discriminator như `"type": "card"` |
| Object identity | Các vị trí có trỏ về cùng một object không? | Object đầy đủ lần đầu, ID ở lần tham chiếu sau |
| Managed/back reference | Quan hệ hai chiều được biểu diễn theo một hướng như thế nào? | Phía back-reference bị bỏ khỏi JSON |

Một test tốt thường kiểm tra nhiều tầng:

1. Serialize object graph.
2. Kiểm tra cấu trúc JSON và type/reference token.
3. Deserialize về kiểu khai báo.
4. Kiểm tra subtype và field cụ thể.
5. Kiểm tra object identity bằng `assertSame` khi contract yêu cầu cùng instance.
6. Kiểm tra input sai như unknown type id, thiếu ID hoặc reference không resolve được.

Không nên dùng một phép so sánh chuỗi JSON duy nhất để chứng minh tất cả các behavior này.

## 2. Cấu hình test và ObjectMapper dùng chung

Ví dụ dưới đây dùng JUnit 5 và Jackson Databind. Có thể tạo mapper một lần trong test class:

~~~java
class PolymorphicIdentityTest {
    private final ObjectMapper mapper = JsonMapper.builder().build();
}
~~~

Nếu production mapper có module, mix-in, naming strategy, visibility hoặc custom handler, test phải dùng cùng cấu hình đó. Một mapper test mặc định có thể pass trong khi mapper production hoạt động khác.

Có thể gom cấu hình vào factory dùng chung:

~~~java
public final class ApplicationJson {
    private ApplicationJson() {
    }

    public static ObjectMapper createMapper() {
        return JsonMapper.builder()
                // Đăng ký đúng module và chính sách production tại đây.
                .build();
    }
}
~~~

Test khởi tạo:

~~~java
private final ObjectMapper mapper = ApplicationJson.createMapper();
~~~

ObjectMapper nên được cấu hình hoàn chỉnh trước khi dùng. Không thay đổi module hoặc feature giữa các test đang chia sẻ cùng mapper.

## 3. Kiểm thử polymorphism với logical type id

Polymorphism thường xuất hiện khi property khai báo kiểu interface hoặc abstract class nhưng JSON cần tạo một implementation cụ thể.

Ví dụ base type:

~~~java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "type"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
public abstract class Payment {
    private BigDecimal amount;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Subtype thứ nhất:

~~~java
public class CardPayment extends Payment {
    private String lastFourDigits;

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }
}
~~~

Subtype thứ hai:

~~~java
public class BankTransferPayment extends Payment {
    private String bankCode;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }
}
~~~

DTO chứa base type:

~~~java
public class PaymentRequest {
    private String requestId;
    private Payment payment;

    public String getRequestId() {
        return requestId;
    }

    public void setRequestId(String requestId) {
        this.requestId = requestId;
    }

    public Payment getPayment() {
        return payment;
    }

    public void setPayment(Payment payment) {
        this.payment = payment;
    }
}
~~~

JSON mẫu:

~~~json
{
  "requestId": "REQ-100",
  "payment": {
    "type": "card",
    "amount": 125.50,
    "lastFourDigits": "4242"
  }
}
~~~

### 3.1. Test deserialize chọn đúng subtype

~~~java
@Test
void shouldDeserializeCardPaymentSubtype() throws Exception {
    String json = """
            {
              "requestId": "REQ-100",
              "payment": {
                "type": "card",
                "amount": 125.50,
                "lastFourDigits": "4242"
              }
            }
            """;

    PaymentRequest request = mapper.readValue(json, PaymentRequest.class);

    assertInstanceOf(CardPayment.class, request.getPayment());

    CardPayment payment = (CardPayment) request.getPayment();
    assertEquals(new BigDecimal("125.50"), payment.getAmount());
    assertEquals("4242", payment.getLastFourDigits());
}
~~~

Test này xác nhận hai điều riêng biệt: Jackson tạo đúng class subtype và các property riêng của subtype được binding. Chỉ kiểm tra `getAmount()` là chưa đủ vì cả hai subtype đều có amount.

### 3.2. Test subtype thứ hai

~~~java
@Test
void shouldDeserializeBankTransferSubtype() throws Exception {
    String json = """
            {
              "requestId": "REQ-101",
              "payment": {
                "type": "bank_transfer",
                "amount": 800.00,
                "bankCode": "VCB"
              }
            }
            """;

    PaymentRequest request = mapper.readValue(json, PaymentRequest.class);

    assertInstanceOf(
            BankTransferPayment.class,
            request.getPayment()
    );

    BankTransferPayment payment =
            (BankTransferPayment) request.getPayment();

    assertEquals("VCB", payment.getBankCode());
    assertEquals(new BigDecimal("800.00"), payment.getAmount());
}
~~~

Hai test riêng giúp phát hiện việc đăng ký subtype thiếu hoặc ánh xạ nhầm logical name.

## 4. Kiểm thử serialize discriminator

Test deserialize thành công chưa chứng minh serializer phát đúng discriminator. Hãy kiểm tra chiều ghi độc lập.

~~~java
@Test
void shouldWriteLogicalTypeNameForCardPayment() throws Exception {
    CardPayment payment = new CardPayment();
    payment.setAmount(new BigDecimal("125.50"));
    payment.setLastFourDigits("4242");

    PaymentRequest request = new PaymentRequest();
    request.setRequestId("REQ-100");
    request.setPayment(payment);

    JsonNode json = mapper.readTree(
            mapper.writeValueAsString(request)
    );

    assertEquals("card", json.path("payment").path("type").asText());
    assertEquals(
            "4242",
            json.path("payment").path("lastFourDigits").asText()
    );
}
~~~

Dùng `JsonNode` giúp test tập trung vào contract cấu trúc. Nó ít nhạy cảm với whitespace, thứ tự property hoặc cách escape mà không làm thay đổi ý nghĩa JSON.

Nếu type metadata là một phần API contract, hãy assert chính xác logical type id. Đừng chỉ assert rằng property `type` tồn tại.

### 4.1. Ghi qua kiểu khai báo base type

Khi serialize root object, nên kiểm tra bằng writer có kiểu tĩnh rõ ràng:

~~~java
String json = mapper.writerFor(Payment.class)
        .writeValueAsString(payment);
~~~

Điều này làm rõ contract rằng giá trị được ghi ở vị trí khai báo là Payment. Trong DTO lồng nhau, property type đã được khai báo sẵn. Với root value, writerFor(baseType) giúp test đúng đường polymorphic root type cần hỗ trợ.

## 5. Kiểm thử round-trip polymorphic

Round-trip test xác nhận subtype và field được giữ qua cả hai chiều:

~~~java
@Test
void shouldRoundTripPolymorphicPayment() throws Exception {
    CardPayment original = new CardPayment();
    original.setAmount(new BigDecimal("125.50"));
    original.setLastFourDigits("4242");

    String json = mapper.writerFor(Payment.class)
            .writeValueAsString(original);

    Payment restored = mapper.readerFor(Payment.class)
            .readValue(json);

    assertInstanceOf(CardPayment.class, restored);

    CardPayment card = (CardPayment) restored;
    assertEquals(original.getAmount(), card.getAmount());
    assertEquals(original.getLastFourDigits(), card.getLastFourDigits());
}
~~~

Đừng chỉ deserialize thành `Payment` rồi assert khác null. Nếu Jackson tạo subtype sai hoặc rơi vào default implementation, test yếu có thể không phát hiện.

Nếu dùng logical type name, test cũng nên giữ fixture JSON có discriminator ổn định. Điều này giúp phát hiện vô tình đổi tên type id khi refactor class.

## 6. Kiểm thử discriminator thiếu hoặc không xác định

Một contract polymorphic thường cần quy định rõ behavior khi discriminator thiếu hoặc lạ.

JSON có type id không đăng ký:

~~~json
{
  "type": "crypto_wallet",
  "amount": 50
}
~~~

Nếu không có default implementation hoặc custom fallback, Jackson thường từ chối type id không biết bằng `InvalidTypeIdException`.

~~~java
@Test
void shouldRejectUnknownTypeId() {
    String json = """
            {
              "type": "crypto_wallet",
              "amount": 50
            }
            """;

    assertThrows(
            InvalidTypeIdException.class,
            () -> mapper.readValue(json, Payment.class)
    );
}
~~~

Discriminator bị thiếu:

~~~java
@Test
void shouldRejectMissingTypeId() {
    String json = """
            {
              "amount": 50
            }
            """;

    assertThrows(
            InvalidTypeIdException.class,
            () -> mapper.readValue(json, Payment.class)
    );
}
~~~

Hai trường hợp này cần test riêng vì missing và unknown có thể được xử lý khác nếu ứng dụng cấu hình defaultImpl, custom type resolver hoặc `requireTypeIdForSubtypes` theo phiên bản Jackson.

Nếu contract cho phép fallback, test phải xác nhận chính xác fallback class và dữ liệu được giữ như thế nào. Không nên chỉ bắt `Exception.class`; dùng exception Jackson phù hợp hoặc `JsonMappingException` nếu behavior khác nhau giữa version được hỗ trợ.

### 6.1. Unknown type không nên âm thầm biến thành subtype tùy ý

Không dùng logic chọn subtype bằng cách đoán từ field xuất hiện trong JSON. Discriminator nên là allowlist logical name do ứng dụng quản lý. Nếu cần hỗ trợ type mới, cập nhật registry và test rõ ràng.

Với input không tin cậy, tránh class-name type id và default typing permissive. Logical id như `card` hoặc `bank_transfer` giúp contract không phụ thuộc package Java.

## 7. Kiểm thử discriminator trong collection

Polymorphism thường xuất hiện trong list:

~~~java
public class BatchRequest {
    private List<Payment> payments;

    public List<Payment> getPayments() {
        return payments;
    }

    public void setPayments(List<Payment> payments) {
        this.payments = payments;
    }
}
~~~

JSON:

~~~json
{
  "payments": [
    {
      "type": "card",
      "amount": 10,
      "lastFourDigits": "1111"
    },
    {
      "type": "bank_transfer",
      "amount": 20,
      "bankCode": "VCB"
    }
  ]
}
~~~

Test:

~~~java
@Test
void shouldDeserializeDifferentSubtypesInOneCollection() throws Exception {
    String json = """
            {
              "payments": [
                {
                  "type": "card",
                  "amount": 10,
                  "lastFourDigits": "1111"
                },
                {
                  "type": "bank_transfer",
                  "amount": 20,
                  "bankCode": "VCB"
                }
              ]
            }
            """;

    BatchRequest batch = mapper.readValue(json, BatchRequest.class);

    assertEquals(2, batch.getPayments().size());
    assertInstanceOf(CardPayment.class, batch.getPayments().get(0));
    assertInstanceOf(
            BankTransferPayment.class,
            batch.getPayments().get(1)
    );
}
~~~

Test collection nên kiểm tra cả thứ tự phần tử nếu thứ tự có ý nghĩa. Thêm một phần tử có type id không hợp lệ ở giữa batch để xác nhận ứng dụng từ chối toàn batch hay xử lý record độc lập theo contract.

## 8. Polymorphism và generic wrapper

Khi base type nằm trong wrapper generic, test cần cung cấp đúng generic type:

~~~java
public class ApiEnvelope<T> {
    private String version;
    private T data;

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }
}
~~~

Đọc envelope chứa Payment:

~~~java
ApiEnvelope<Payment> envelope = mapper.readValue(
        json,
        new TypeReference<ApiEnvelope<Payment>>() {}
);
~~~

Test cần assert subtype bên trong `data`. Nếu chỉ truyền `ApiEnvelope.class`, generic type có thể bị mất và property `data` không được deserialize thành Payment như mong muốn.

## 9. Object identity: shared reference và cycle khác nhau

Một object graph có thể có cùng một object được tham chiếu từ nhiều property. Ví dụ hai order cùng trỏ tới một Customer. Đây là shared reference.

Một graph có cycle khi một object có đường tham chiếu quay lại chính nó, trực tiếp hoặc qua các object khác. Ví dụ Node A trỏ tới Node B và Node B trỏ lại A.

~~~text
Shared reference:

        +------> Customer <------+
        |                        |
      Order A                  Order B


Cycle:

      +-------------------------+
      |                         |
      v                         |
     Node A ------> Node B -----+
~~~

Nếu serialize thuần bằng nested object, shared reference có thể bị ghi lặp và cycle có thể dẫn tới đệ quy vô hạn. `@JsonIdentityInfo` cho Jackson một identity để nhận ra object đã xuất hiện và biểu diễn reference bằng ID.

Test cần phân biệt:

- Hai object có giá trị bằng nhau nhưng là hai instance khác nhau.
- Hai property cùng trỏ tới một instance.
- Một object graph có cycle quay về instance ban đầu.

## 10. Khai báo object identity bằng PropertyGenerator

Ví dụ node có ID ổn định:

~~~java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class GraphNode {
    private String id;
    private String label;
    private GraphNode next;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public GraphNode getNext() {
        return next;
    }

    public void setNext(GraphNode next) {
        this.next = next;
    }
}
~~~

Property `id` là object identity. Mỗi object cần có ID hợp lệ và duy nhất trong scope tương ứng của graph. Nếu ID null, thiếu hoặc trùng, test phải phát hiện vì reference có thể không được tạo hoặc resolve như dự kiến.

### 10.1. Test graph có cycle

Tạo hai node tham chiếu vòng:

~~~java
GraphNode first = new GraphNode();
first.setId("N-1");
first.setLabel("first");

GraphNode second = new GraphNode();
second.setId("N-2");
second.setLabel("second");

first.setNext(second);
second.setNext(first);
~~~

Test serialize và deserialize:

~~~java
@Test
void shouldRoundTripCyclicGraph() throws Exception {
    GraphNode first = node("N-1", "first");
    GraphNode second = node("N-2", "second");

    first.setNext(second);
    second.setNext(first);

    String json = mapper.writeValueAsString(first);

    GraphNode restored = mapper.readValue(json, GraphNode.class);

    assertEquals("N-1", restored.getId());
    assertEquals("N-2", restored.getNext().getId());

    assertSame(
            restored,
            restored.getNext().getNext()
    );
}
~~~

Assertion cuối cùng rất quan trọng. Nó xác nhận `second.next` trỏ về chính instance root đã deserialize, không chỉ là một object khác có cùng ID hoặc field values.

Helper:

~~~java
private static GraphNode node(String id, String label) {
    GraphNode node = new GraphNode();
    node.setId(id);
    node.setLabel(label);
    return node;
}
~~~

### 10.2. Kiểm tra JSON chứa ID reference

Không chỉ kiểm tra deserialize thành công. Hãy kiểm tra lần tham chiếu quay về node đã xuất hiện được biểu diễn bằng ID:

~~~java
@Test
void shouldWriteObjectIdForRepeatedNode() throws Exception {
    GraphNode first = node("N-1", "first");
    GraphNode second = node("N-2", "second");

    first.setNext(second);
    second.setNext(first);

    JsonNode json = mapper.readTree(
            mapper.writeValueAsString(first)
    );

    assertEquals("N-1", json.path("id").asText());
    assertEquals("N-2", json.path("next").path("id").asText());
    assertEquals("N-1", json.path("next").path("next").asText());
    assertTrue(json.path("next").path("next").isValueNode());
}
~~~

Hình dạng chính xác của ID reference phụ thuộc cấu hình identity và serializer. Với PropertyGenerator và cấu hình mặc định, reference thường là scalar ID. Nếu contract cần một hình dạng cụ thể, assert đúng hình dạng đó bằng JSON tree.

## 11. Kiểm thử shared reference bằng assertSame

Shared reference không cần cycle. Tạo hai property cùng trỏ tới một Customer:

~~~java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class Customer {
    private String id;
    private String name;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Wrapper:

~~~java
public class CustomerPair {
    private Customer primary;
    private Customer secondary;

    public Customer getPrimary() {
        return primary;
    }

    public void setPrimary(Customer primary) {
        this.primary = primary;
    }

    public Customer getSecondary() {
        return secondary;
    }

    public void setSecondary(Customer secondary) {
        this.secondary = secondary;
    }
}
~~~

Test:

~~~java
@Test
void shouldPreserveSharedObjectIdentity() throws Exception {
    Customer shared = customer("C-1", "An");

    CustomerPair original = new CustomerPair();
    original.setPrimary(shared);
    original.setSecondary(shared);

    String json = mapper.writeValueAsString(original);
    CustomerPair restored = mapper.readValue(json, CustomerPair.class);

    assertEquals("C-1", restored.getPrimary().getId());
    assertEquals("C-1", restored.getSecondary().getId());
    assertSame(restored.getPrimary(), restored.getSecondary());
}
~~~

Hai assertion equals kiểm tra giá trị. `assertSame` kiểm tra object identity. Nếu chỉ dùng `assertEquals`, hai instance riêng có cùng ID và name vẫn có thể làm test pass dù graph semantics đã bị mất.

Helper:

~~~java
private static Customer customer(String id, String name) {
    Customer customer = new Customer();
    customer.setId(id);
    customer.setName(name);
    return customer;
}
~~~

## 12. Phân biệt shared instance với hai object bằng nhau

Đây là một negative case quan trọng. Tạo hai Customer instance có cùng field values nhưng không phải cùng object:

~~~java
Customer first = customer("C-1", "An");
Customer second = customer("C-1", "An");

assertNotSame(first, second);
~~~

Nếu identity được xác định bằng property ID, hai object khác instance nhưng cùng ID trong một graph có thể tạo xung đột hoặc bị hiểu thành cùng identity. Không thiết kế graph có hai object khác nhau cùng ID nếu ID được dùng làm khóa định danh.

Test domain nên xác nhận ID duy nhất trước khi serialize hoặc tạo graph hợp lệ với ID khác nhau:

~~~java
CustomerPair pair = new CustomerPair();
pair.setPrimary(customer("C-1", "An"));
pair.setSecondary(customer("C-2", "An"));
~~~

Nếu hai object cùng ID là tình huống có thể xảy ra từ database/import, cần test behavior của ứng dụng và quyết định từ chối graph ở tầng domain. Không dựa vào serializer để giải quyết xung đột ID.

## 13. @JsonIdentityReference(alwaysAsId = true)

`@JsonIdentityInfo` mặc định có thể ghi object đầy đủ ở lần xuất hiện đầu và ID ở những lần sau. Nếu một property phải luôn ghi ID, dùng:

~~~java
@JsonIdentityReference(alwaysAsId = true)
private Customer customer;
~~~

Ví dụ:

~~~java
public class Order {
    private String id;

    @JsonIdentityReference(alwaysAsId = true)
    private Customer customer;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }
}
~~~

Test output property là scalar ID:

~~~java
@Test
void shouldAlwaysWriteCustomerReferenceAsId() throws Exception {
    Order order = new Order();
    order.setId("O-1");
    order.setCustomer(customer("C-1", "An"));

    JsonNode json = mapper.readTree(
            mapper.writeValueAsString(order)
    );

    assertTrue(json.path("customer").isTextual());
    assertEquals("C-1", json.path("customer").asText());
}
~~~

Vì `alwaysAsId` yêu cầu ID ngay cả khi object chưa được serialize đầy đủ ở vị trí khác, consumer cần một cách giải quyết ID. JSON chỉ có `"customer": "C-1"` không tự mang theo tên và dữ liệu Customer.

## 14. Test ID-only reference được resolve trong cùng graph

Nếu object đầy đủ đã xuất hiện ở một property khác trong cùng document, các reference sau có thể được liên kết về cùng instance.

Envelope:

~~~java
// Đảm bảo object Customer được ghi trước các ID reference trong orders.
@JsonPropertyOrder({"customer", "orders"})
public class OrderEnvelope {
    private Customer customer;
    private List<Order> orders;

    public Customer getCustomer() {
        return customer;
    }

    public void setCustomer(Customer customer) {
        this.customer = customer;
    }

    public List<Order> getOrders() {
        return orders;
    }

    public void setOrders(List<Order> orders) {
        this.orders = orders;
    }
}
~~~

Customer có `@JsonIdentityInfo`; Order có `@JsonIdentityReference(alwaysAsId = true)` trên property customer.

Test:

~~~java
@Test
void shouldResolveIdOnlyReferenceFromSameDocument() throws Exception {
    Customer shared = customer("C-1", "An");

    Order first = new Order();
    first.setId("O-1");
    first.setCustomer(shared);

    Order second = new Order();
    second.setId("O-2");
    second.setCustomer(shared);

    OrderEnvelope original = new OrderEnvelope();
    original.setCustomer(shared);
    original.setOrders(List.of(first, second));

    String json = mapper.writeValueAsString(original);

    JsonNode tree = mapper.readTree(json);
    assertTrue(tree.path("customer").isObject());
    assertEquals(
            "C-1",
            tree.path("orders").get(0).path("customer").asText()
    );

    OrderEnvelope restored =
            mapper.readValue(json, OrderEnvelope.class);

    assertSame(
            restored.getCustomer(),
            restored.getOrders().get(0).getCustomer()
    );
    assertSame(
            restored.getCustomer(),
            restored.getOrders().get(1).getCustomer()
    );
}
~~~

Test này xác nhận cả wire shape lẫn graph identity sau deserialize. Nếu object đầy đủ nằm sau reference hoặc graph dùng creator/property đặc biệt, behavior forward reference có thể khác; hãy test thứ tự và kiểu DTO thực tế.

## 15. Test unresolved object ID

Một ID reference không có object definition trong document cần một resolver hoặc cơ chế lookup được cấu hình. Jackson mặc định không tự truy vấn database để tìm entity.

JSON chỉ có reference:

~~~json
{
  "id": "O-1",
  "customer": "C-404"
}
~~~

Nếu Customer có object identity nhưng chưa xuất hiện trong graph, deserialize thường kết thúc bằng lỗi unresolved object ID.

~~~java
@Test
void shouldRejectUnresolvedCustomerId() {
    String json = """
            {
              "id": "O-1",
              "customer": "C-404"
            }
            """;

    assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, Order.class)
    );
}
~~~

Dùng `JsonMappingException` làm kiểu tổng quát nếu codebase hỗ trợ nhiều Jackson version hoặc wrapper exception. Nếu test gắn với một version cụ thể, có thể assert subtype như `UnresolvedForwardReference` sau khi xác nhận exception thực tế của cấu hình đó.

### 15.1. Reference trong document khác không dùng chung cache mặc định

Giả sử một lần đọc có object Customer đầy đủ:

~~~json
{"id":"C-1","name":"An"}
~~~

Một lần đọc độc lập khác chỉ có:

~~~json
{"id":"O-1","customer":"C-1"}
~~~

Hai lần `readValue()` độc lập không mặc định chia sẻ object ID registry. Object được đăng ký trong context của tài liệu đầu không tự xuất hiện trong context của tài liệu thứ hai.

Nếu API nhận ID từ client để liên kết database entity, thường nên deserialize vào DTO có `customerId`, rồi service thực hiện lookup và authorization. Nếu thực sự cần resolver tùy chỉnh, test vòng đời resolver, scope, cache isolation và behavior khi ID không tồn tại.

## 16. Test ID bị thiếu, null hoặc trùng

Với `ObjectIdGenerators.PropertyGenerator`, ID property là nguồn identity. Cần kiểm thử:

- Object có ID hợp lệ.
- ID null.
- ID bị thiếu khi deserialize.
- Hai object khác nhau có cùng ID.
- ID có kiểu JSON không phù hợp.
- Reference trỏ tới ID chưa được đăng ký.

Không nên giả định mọi tình huống này đều có cùng exception. Kết quả phụ thuộc generator, property visibility, creator, Jackson version và thời điểm ID được đọc.

Ví dụ test cho null ID theo chính sách domain:

~~~java
@Test
void shouldRejectNodeWithoutIdentityBeforeSerialization() {
    GraphNode node = node(null, "missing-id");

    assertThrows(
            IllegalArgumentException.class,
            () -> validateIdentity(node)
    );
}
~~~

Ở đây `validateIdentity` là validation của ứng dụng, không phải API Jackson. Kiểm tra identity trước serialize giúp thông báo lỗi domain rõ ràng hơn và tránh phụ thuộc vào exception nội bộ.

Với duplicate ID, nên kiểm tra uniqueness khi tạo graph hoặc tại domain boundary. Test cần chứng minh ứng dụng từ chối hai entity khác nhau cùng ID trước khi đưa graph vào serializer.

## 17. @JsonManagedReference và @JsonBackReference

Hai annotation này giải quyết một dạng quan hệ hai chiều phổ biến: parent chứa danh sách child, child trỏ ngược về parent.

~~~java
public class Parent {
    private String id;

    @JsonManagedReference
    private List<Child> children;

    // Getter và setter
}

public class Child {
    private String id;

    @JsonBackReference
    private Parent parent;

    // Getter và setter
}
~~~

Khi serialize Parent, Jackson ghi children nhưng bỏ property parent ở phía child. Khi deserialize, Jackson có thể thiết lập lại quan hệ back-reference.

JSON:

~~~json
{
  "id": "P-1",
  "children": [
    {
      "id": "C-1"
    }
  ]
}
~~~

### 17.1. Test JSON không chứa back-reference

~~~java
@Test
void shouldOmitBackReferenceFromJson() throws Exception {
    Parent parent = new Parent();
    parent.setId("P-1");

    Child child = new Child();
    child.setId("C-1");
    child.setParent(parent);

    parent.setChildren(List.of(child));

    JsonNode json = mapper.readTree(
            mapper.writeValueAsString(parent)
    );

    assertTrue(json.path("children").get(0).isObject());
    assertFalse(json.path("children").get(0).has("parent"));
}
~~~

Test này xác nhận chiều serialize. Không thể chỉ kiểm tra object sau deserialize vì một serializer có thể vô tình ghi thêm back-reference mà test graph vẫn pass.

### 17.2. Test quan hệ được khôi phục sau deserialize

~~~java
@Test
void shouldRestoreManagedBackReference() throws Exception {
    String json = """
            {
              "id": "P-1",
              "children": [
                {"id": "C-1"}
              ]
            }
            """;

    Parent restored = mapper.readValue(json, Parent.class);

    assertEquals(1, restored.getChildren().size());
    assertSame(
            restored,
            restored.getChildren().get(0).getParent()
    );
}
~~~

Ở đây `assertSame` xác nhận child.parent chính là root Parent vừa được tạo.

### 17.3. Named references khi có nhiều quan hệ

Nếu một class có nhiều cặp parent-child độc lập, đặt tên reference tương ứng:

~~~java
@JsonManagedReference("orders")
private List<Order> orders;

@JsonBackReference("orders")
private Customer customer;
~~~

Tên ở hai phía phải khớp. Test cần bao gồm tất cả cặp quan hệ để phát hiện nhầm tên hoặc annotation bị đặt sai property.

## 18. Phân biệt object identity với managed/back reference

Hai cơ chế không thể thay thế nhau trong mọi tình huống.

| Tiêu chí | `@JsonIdentityInfo` | Managed/back reference |
|---|---|---|
| Cách biểu diễn | Object đầy đủ và ID reference | Ghi phía managed, bỏ phía back |
| Giữ shared object identity | Có thể | Không phải mục tiêu chính |
| Biểu diễn cycle | Qua ID | Bỏ cạnh back-reference đã khai báo |
| JSON có ID scalar | Có thể, nhất là với `alwaysAsId` | Không |
| Hợp với graph nhiều đường tham chiếu | Có | Chủ yếu quan hệ hai chiều theo cặp |
| Consumer cần hiểu ID | Có khi reference xuất hiện | Không cần ID reference |

Nếu contract cần nhiều property cùng trỏ về một object và phải giữ identity, test `@JsonIdentityInfo`. Nếu chỉ cần bỏ một cạnh parent reference để JSON có dạng cây, test managed/back reference.

Không gắn cả hai cơ chế tùy tiện trên cùng một quan hệ. Hãy xác định wire format mong muốn rồi kiểm tra riêng chiều serialize và deserialize.

## 19. Kiểm tra JSON bằng tree thay vì so sánh chuỗi

So sánh chuỗi JSON toàn bộ thường dễ vỡ vì thứ tự property, whitespace và cách escape có thể thay đổi mà semantics không đổi.

Ví dụ không nên dùng làm assertion duy nhất:

~~~java
assertEquals(
        "{\"type\":\"card\",\"amount\":125.5}",
        json
);
~~~

Thay vào đó:

~~~java
JsonNode tree = mapper.readTree(json);

assertEquals("card", tree.path("type").asText());
assertEquals(
        new BigDecimal("125.50"),
        tree.path("amount").decimalValue()
);
~~~

Với object identity, kiểm tra rõ node là object hay scalar:

~~~java
assertTrue(tree.path("customer").isTextual());
assertEquals("C-1", tree.path("customer").asText());
~~~

Với managed/back reference, kiểm tra property bị lược bỏ:

~~~java
assertFalse(tree.path("children").get(0).has("parent"));
~~~

Chỉ assert textual output chính xác khi chính textual form là contract, ví dụ một file snapshot mà consumer yêu cầu thứ tự và format cụ thể.

## 20. Kiểm tra graph bằng identity và equality

Java có hai khái niệm khác nhau:

- `equals()`: hai object có được xem là tương đương theo logic class hay không.
- `==`/`assertSame()`: hai reference có trỏ tới đúng cùng một instance hay không.

Trong test object graph:

~~~java
assertEquals(expected.getId(), actual.getId());
assertSame(actual, actual.getNext().getNext());
~~~

Assertion đầu kiểm tra giá trị. Assertion sau kiểm tra cycle quay về root.

Nếu class không override equals/hashCode, `assertEquals` thường tương đương kiểm tra identity; nhưng không nên dựa vào chi tiết đó. Dùng `assertSame` khi contract yêu cầu cùng instance và `assertNotSame` khi cần chứng minh hai instance khác nhau.

## 21. Test property path khi lỗi xảy ra trong subtype hoặc reference

Khi một field subtype sai kiểu, exception có thể mang path qua property chứa base type. Ví dụ `payment.amount` nhận chuỗi không hợp lệ.

~~~java
@Test
void shouldExposePathForInvalidSubtypeProperty() {
    String json = """
            {
              "requestId": "REQ-1",
              "payment": {
                "type": "card",
                "amount": "not-a-number",
                "lastFourDigits": "4242"
              }
            }
            """;

    JsonMappingException exception = assertThrows(
            JsonMappingException.class,
            () -> mapper.readValue(json, PaymentRequest.class)
    );

    List<String> fields = exception.getPath().stream()
            .map(JsonMappingException.Reference::getFieldName)
            .filter(Objects::nonNull)
            .toList();

    assertTrue(fields.contains("payment"));
    assertTrue(fields.contains("amount"));
}
~~~

Path giúp xác định lỗi thuộc subtype property nào. Tuy nhiên, type id không hợp lệ có thể thất bại trước khi Jackson tạo subtype và path có thể khác. Test unknown discriminator riêng, không dùng cùng assertion path như invalid field.

Với unresolved object ID, exception cũng có thể chứa path tới property reference. Nếu ứng dụng hiển thị lỗi cho API client, chuẩn hóa path thay vì trả nguyên exception message hoặc class name nội bộ.

## 22. Test fixture cho polymorphism và identity

Nên lưu fixture đại diện cho các contract quan trọng:

~~~text
src/test/resources/
  jackson/
    polymorphism/
      card-payment-v1.json
      bank-transfer-v1.json
      unknown-payment-type.json
      missing-payment-type.json
    identity/
      cyclic-nodes-v1.json
      shared-customer-v1.json
      unresolved-customer-id.json
    references/
      parent-children-v1.json
~~~

Fixture giúp kiểm tra dữ liệu đã phát hành và không phụ thuộc hoàn toàn vào serializer hiện tại.

Ví dụ đọc fixture:

~~~java
@Test
void shouldReadPublishedCardPaymentFixture() throws Exception {
    try (InputStream input = getClass()
            .getResourceAsStream(
                    "/jackson/polymorphism/card-payment-v1.json"
            )) {
        assertNotNull(input);

        Payment payment = mapper.readValue(input, Payment.class);

        assertInstanceOf(CardPayment.class, payment);
    }
}
~~~

Không tạo fixture đầu vào bằng chính mapper đang được test trong setup của test consumer. Nếu làm vậy, producer và consumer cùng mắc một lỗi contract vẫn có thể pass.

## 23. Compatibility khi thay đổi subtype

Khi hệ thống thêm hoặc đổi subtype, cần xem type id là một phần contract dữ liệu.

Ví dụ:

- `card` là logical id đã phát hành.
- Class Java được refactor từ CardPayment sang StoredCardPayment.
- JSON cũ vẫn cần deserialize về class mới.

Nếu dùng `JsonTypeInfo.Id.NAME`, có thể giữ logical id `card` ổn định dù class Java đổi tên. Test fixture cũ xác nhận behavior này.

~~~java
@Test
void shouldKeepPublishedLogicalTypeIdStable() throws Exception {
    String fixture = """
            {
              "type": "card",
              "amount": 125.50,
              "lastFourDigits": "4242"
            }
            """;

    Payment payment = mapper.readValue(fixture, Payment.class);

    assertInstanceOf(CardPayment.class, payment);
}
~~~

Khi thay subtype implementation, giữ type id cũ hoặc cung cấp migration mapping có chủ đích. Không đổi logical name chỉ vì tên class đã thay đổi.

## 24. Test default typing và validator nếu hệ thống legacy sử dụng

Một số hệ thống cũ dùng default typing hoặc `JsonTypeInfo.Id.CLASS`. Trong trường hợp này, test phải xác nhận validator từ chối class ngoài allowlist.

Không nên chỉ test subtype hợp lệ. Cần một test negative với class không thuộc hierarchy được phép, và xác nhận mapper từ chối trước khi dữ liệu được binding vào class đó.

Nếu có thể thay contract, ưu tiên logical type name và subtype registry rõ ràng. Test security cần dùng đúng mapper production, vì một mapper test không có validator có thể tạo cảm giác an toàn sai.

Không dùng `LaissezFaireSubTypeValidator` trong test như một cách làm payload class-name deserialize thành công rồi coi đó là behavior mong muốn cho dữ liệu không tin cậy.

## 25. Parameterized test cho nhiều subtype

Khi có nhiều subtype, JUnit 5 parameterized test giúp kiểm tra registry nhất quán:

~~~java
@ParameterizedTest
@CsvSource({
        "card, CardPayment",
        "bank_transfer, BankTransferPayment"
})
void shouldResolveRegisteredSubtype(
        String typeId,
        String expectedSimpleName
) throws Exception {
    String json = """
            {
              "type": "%s",
              "amount": 10
            }
            """.formatted(typeId);

    Payment payment = mapper.readValue(json, Payment.class);

    assertEquals(
            expectedSimpleName,
            payment.getClass().getSimpleName()
    );
}
~~~

Nếu subtype có required property riêng, nên có test cụ thể cho từng subtype ngoài test registry tổng quát. Không để một test chung với amount field chứng minh nhầm rằng mọi subtype đều được binding đầy đủ.

## 26. Test nhiều cycle và nhiều shared references

Một graph phức tạp có thể chứa:

- A trỏ tới B và C.
- B trỏ tới C.
- C trỏ lại A.
- Một collection chứa lại A.
- Một map giữ reference tới B.

Test nên xác nhận từng cạnh có ý nghĩa identity. Ví dụ:

~~~java
assertSame(root, restored.getChild().getParent());
assertSame(restored.getShared(), restored.getLeft().getShared());
assertSame(restored.getShared(), restored.getRight().getShared());
~~~

Không chỉ kiểm tra root ID và số phần tử. Một graph có thể giữ đúng các giá trị nhưng làm mất shared identity, dẫn tới lỗi khi ứng dụng sửa một object qua một đường tham chiếu và kỳ vọng đường khác nhìn thấy thay đổi đó.

Nếu domain không yêu cầu object identity sau deserialize, có thể chỉ cần kiểm tra value semantics. Hãy ghi rõ expectation thay vì luôn yêu cầu `assertSame` cho mọi graph.

## 27. Những lỗi thường gặp khi kiểm thử

**Chỉ assert JSON có property discriminator.** Cần xác nhận logical type id chính xác và subtype thực tế sau deserialize.

**Chỉ assert base type không null.** Điều này không chứng minh subtype đúng. Dùng `assertInstanceOf` và kiểm tra field riêng.

**Chỉ kiểm tra equals cho shared reference.** Hai instance riêng có thể bằng nhau theo giá trị. Dùng `assertSame` khi identity là contract.

**Không kiểm tra chiều serialize.** Deserialize pass không chứng minh JSON phát ra đúng type id hoặc reference shape.

**Bỏ qua missing và unknown discriminator.** Đây là hai negative case quan trọng, đặc biệt khi thêm subtype mới.

**Dùng default implementation mà không test fallback.** Fallback có thể che lỗi type id và làm consumer xử lý nhầm loại dữ liệu.

**Cho rằng ID-only reference tự lookup database.** Jackson chỉ resolve object đã đăng ký trong graph hoặc qua resolver được cấu hình.

**Không kiểm tra unresolved ID.** Payload thiếu object definition có thể thất bại ở cuối quá trình deserialize.

**Dùng ID trùng cho hai instance khác nhau.** Identity registry có thể không thể phân biệt chúng theo contract. Kiểm tra uniqueness ở domain layer.

**Nhầm managed/back reference với object identity.** Một cơ chế bỏ cạnh back; cơ chế kia biểu diễn object ID.

**So sánh toàn bộ JSON string khi thứ tự không phải contract.** Dùng JsonNode để kiểm tra structure và values.

**Tạo fixture bằng mapper đang test.** Producer và consumer cùng sai có thể vẫn pass. Giữ fixture độc lập, versioned.

**Test mapper khác production.** Module, mix-in, subtype registry hoặc validator thiếu có thể làm kết quả không đại diện.

**Bắt Exception.class cho mọi negative test.** Assert exception Jackson cụ thể khi contract phụ thuộc version, hoặc dùng superclass phù hợp và kiểm tra nguyên nhân/path.

## 28. Ma trận kiểm thử đề xuất

| Nhóm | Case hợp lệ | Case không hợp lệ |
|---|---|---|
| Polymorphism | Mỗi subtype được đăng ký; subtype trong list; round-trip | Type id thiếu, type id lạ, field subtype sai kiểu |
| Type contract | Logical id ổn định qua refactor | Class name không được phép, subtype không tương thích |
| Object identity | Lần xuất hiện đầu và reference sau | ID null, duplicate ID, unresolved ID |
| Cycle | A → B → A; graph nhiều node | Chu trình không có identity handling |
| Shared reference | Hai property cùng instance | Hai instance khác nhau cùng ID |
| alwaysAsId | ID-only property có definition trong document | ID-only reference không có definition |
| Managed/back reference | Back-reference bị bỏ và được khôi phục | Sai reference name, nhiều pair cấu hình nhầm |
| Compatibility | Fixture phiên bản cũ đọc được | Logical type id bị đổi hoặc subtype bị gỡ |
| Error reporting | Path tới property lỗi | Type id lỗi trước khi subtype được tạo |

Không phải mọi dự án đều cần mọi case, nhưng những behavior đang dùng trong production phải có ít nhất một positive test và một negative test phù hợp.

## 29. Quy trình viết test có hệ thống

Khi thêm polymorphism hoặc object identity vào model:

1. Xác định declared base type và danh sách subtype hợp lệ.
2. Chốt logical discriminator và hình dạng JSON.
3. Test serialize từng subtype qua declared base type.
4. Test deserialize từng subtype và property riêng.
5. Test discriminator thiếu, unknown và subtype field sai.
6. Xác định graph có shared object, cycle hay chỉ parent-child.
7. Chọn identity annotation hoặc managed/back reference theo contract.
8. Test JSON shape cho object definition và reference.
9. Deserialize lại rồi dùng assertSame cho những cạnh phải giữ identity.
10. Test unresolved ID và ID uniqueness.
11. Lưu fixture độc lập có version.
12. Chạy test bằng mapper production đã đăng ký đủ module, mix-in và validator.
13. Khi đổi Jackson version hoặc subtype registry, chạy lại toàn bộ compatibility/security tests.

## 30. Kết luận

Kiểm thử đa hình, chu trình và tham chiếu định danh cần xác nhận cả dữ liệu lẫn cấu trúc object graph. Với polymorphism, hãy kiểm tra logical discriminator, subtype được tạo, field riêng của subtype và các trường hợp missing/unknown type id. Với object identity, hãy kiểm tra ID reference trong JSON và dùng `assertSame` sau deserialize để xác nhận các cạnh thực sự trỏ tới cùng instance. Với managed/back reference, kiểm tra property back bị lược khỏi JSON và quan hệ ngược được khôi phục.

Round-trip test rất hữu ích nhưng chưa đủ nếu chỉ dùng mapper tạo ra fixture. Hãy kết hợp structural assertions bằng JsonNode, fixture versioned độc lập, positive/negative cases và mapper production thực tế. Đặc biệt, phân biệt shared reference với hai object bằng nhau theo giá trị, và phân biệt ID reference trong cùng document với ID cần lookup từ database. Những test này giúp thay đổi subtype, annotation hoặc Jackson version không âm thầm làm hỏng contract và object graph của ứng dụng.

## Tài liệu tham khảo

- [Jackson Annotations — JsonTypeInfo API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonTypeInfo.html)
- [Jackson Annotations — JsonSubTypes API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonSubTypes.html)
- [Jackson Annotations — JsonIdentityInfo API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIdentityInfo.html)
- [Jackson Annotations — JsonIdentityReference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIdentityReference.html)
- [Jackson Annotations — JsonManagedReference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonManagedReference.html)
- [Jackson Annotations — JsonBackReference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonBackReference.html)
- [Jackson Databind — InvalidTypeIdException API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/exc/InvalidTypeIdException.html)
- [Jackson Databind — UnresolvedForwardReference API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/deser/UnresolvedForwardReference.html)

