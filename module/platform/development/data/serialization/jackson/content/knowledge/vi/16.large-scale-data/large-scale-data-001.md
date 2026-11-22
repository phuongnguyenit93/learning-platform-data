# Lựa chọn đọc từng phần thay vì tạo toàn bộ đồ thị đối tượng

Khi JSON chứa hàng trăm nghìn bản ghi hoặc các object lồng nhau rất lớn, đọc toàn bộ document thành một danh sách Java hay một cây JsonNode có thể tiêu tốn nhiều bộ nhớ. Ứng dụng phải giữ đồng thời nhiều object, collection, string và node trong heap, kể cả những phần dữ liệu chưa cần xử lý ngay.

Jackson cung cấp Streaming API để đọc JSON tuần tự theo token. Kết hợp Streaming API với data binding theo từng phần tử, ứng dụng có thể xử lý một bản ghi, hoàn tất công việc của bản ghi đó rồi chuyển sang bản ghi tiếp theo. Cách này giảm lượng dữ liệu phải giữ trong bộ nhớ tại cùng một thời điểm.

Lựa chọn giữa đọc toàn bộ đồ thị object và đọc từng phần phụ thuộc kích thước dữ liệu, cấu trúc JSON, nhu cầu truy cập và cách ứng dụng xử lý kết quả. Streaming không phải lúc nào cũng cần thiết; nó phù hợp khi chi phí bộ nhớ hoặc độ trễ của việc chờ toàn bộ document trở thành vấn đề thực tế.

## 1. Đồ thị đối tượng được tạo từ JSON

Giả sử file chứa danh sách đơn hàng:

~~~json
{
  "orders": [
    {
      "id": "ORD-001",
      "customer": {
        "name": "An",
        "email": "an@example.com"
      },
      "items": [
        {"sku": "KB-01", "quantity": 2},
        {"sku": "MS-02", "quantity": 1}
      ]
    },
    {
      "id": "ORD-002",
      "customer": {
        "name": "Binh",
        "email": "binh@example.com"
      },
      "items": [
        {"sku": "BK-10", "quantity": 3}
      ]
    }
  ]
}
~~~

Có thể ánh xạ thành các class Java:

~~~java
public class Order {
    private String id;
    private Customer customer;
    private List<OrderItem> items;

    public Order() {
    }

    // Getter và setter.
}

public class Customer {
    private String name;
    private String email;

    public Customer() {
    }

    // Getter và setter.
}

public class OrderItem {
    private String sku;
    private int quantity;

    public OrderItem() {
    }

    // Getter và setter.
}
~~~

Khi đọc toàn bộ JSON thành một object gốc có property orders kiểu List<Order>, Jackson phải tạo danh sách và các object con tương ứng. Sau khi đọc xong, ứng dụng có thể truy cập bất kỳ đơn hàng nào trong danh sách, nhưng toàn bộ danh sách và các object được giữ trong heap cho đến khi không còn tham chiếu.

Một đồ thị object có thể gồm:
- Object gốc.
- Collection chứa các object con.
- Các object lồng nhau.
- String, số, enum và những giá trị khác.
- Các collection hoặc map nằm sâu hơn trong từng object.

Kích thước heap không chỉ bằng số byte của file JSON. Mỗi Java object có overhead, collection cần vùng lưu tham chiếu, string có cấu trúc nội bộ và object lồng nhau cần bộ nhớ riêng. Vì vậy, một JSON file vài trăm MB có thể tạo ra đồ thị object lớn hơn đáng kể khi được materialize thành Java object.

## 2. Đọc toàn bộ document bằng Data Binding

Cách đơn giản là đọc JSON thành một kiểu Java chứa toàn bộ dữ liệu.

~~~java
ObjectMapper mapper = new ObjectMapper();

List<Order> orders = mapper.readValue(
        input,
        new TypeReference<List<Order>>() {}
);
~~~

Nếu JSON có root object chứa property orders, có thể dùng một class wrapper:

~~~java
public class OrderDocument {
    private List<Order> orders;

    public OrderDocument() {
    }

    public List<Order> getOrders() {
        return orders;
    }

    public void setOrders(List<Order> orders) {
        this.orders = orders;
    }
}
~~~

~~~java
OrderDocument document = mapper.readValue(
        input,
        OrderDocument.class
);

for (Order order : document.getOrders()) {
    process(order);
}
~~~

Cách đọc này dễ viết và dễ hiểu. Nó phù hợp khi:
- Document có kích thước vừa phải.
- Ứng dụng cần truy cập nhiều lần vào nhiều phần của dữ liệu.
- Cần sắp xếp, lọc hoặc tính toán trên toàn bộ tập dữ liệu trong bộ nhớ.
- Mô hình nghiệp vụ thực sự cần toàn bộ object graph cùng tồn tại.
- Giới hạn bộ nhớ đã được đo lường và đáp ứng yêu cầu.

Vấn đề xuất hiện khi danh sách quá lớn. Dù vòng lặp xử lý từng order, toàn bộ List<Order> vẫn đã được tạo trước khi vòng lặp bắt đầu. Việc xử lý tuần tự ở vòng lặp không làm quá trình đọc ban đầu trở thành streaming.

## 3. Đọc toàn bộ JSON thành cây JsonNode

Một cách khác là dùng tree model:

~~~java
JsonNode root = mapper.readTree(input);
JsonNode orders = root.path("orders");

for (JsonNode orderNode : orders) {
    String id = orderNode.path("id").asText();
    processOrderNode(orderNode);
}
~~~

Tree model hữu ích khi cấu trúc JSON động hoặc ứng dụng chỉ biết trước một số property. Tuy nhiên, readTree() vẫn tạo cây node cho document được đọc. Với một document rất lớn, toàn bộ cây có thể chiếm nhiều bộ nhớ.

So sánh:

| Cách đọc | Cấu trúc giữ trong bộ nhớ |
|---|---|
| readValue thành POJO chứa List | Toàn bộ object graph theo kiểu Java |
| readTree thành JsonNode | Toàn bộ cây JSON |
| Streaming parser | Token hiện tại và trạng thái parser; ứng dụng quyết định phần nào cần materialize |
| MappingIterator | Một phần tử Java tại một thời điểm nếu ứng dụng xử lý rồi loại bỏ tham chiếu |

Tree model không phải Streaming API. Nó vẫn có thể phù hợp với JSON nhỏ hoặc khi cần sửa/đọc linh hoạt nhiều vị trí, nhưng không phải lựa chọn tối ưu để duyệt một mảng hàng triệu phần tử nếu không cần giữ toàn bộ cây.

## 4. Streaming API của Jackson

Jackson Core cung cấp các thành phần chính:

- JsonFactory: tạo parser và generator.
- JsonParser: đọc JSON tuần tự và cung cấp từng token.
- JsonGenerator: ghi JSON tuần tự.
- JsonToken: mô tả loại token hiện tại, chẳng hạn START_OBJECT, FIELD_NAME, VALUE_STRING hoặc END_ARRAY.

Thay vì tạo toàn bộ cây, parser đọc dữ liệu theo thứ tự xuất hiện. Ứng dụng có thể quyết định xử lý token nào, bỏ qua nhánh nào hoặc ánh xạ một object con thành POJO.

~~~mermaid
flowchart TD
    A[InputStream] --> B[JsonParser]
    B --> C[Đọc token tiếp theo]
    C --> D{Token hiện tại}
    D -->|Bản ghi bắt đầu| E[Ánh xạ một POJO]
    E --> F[Xử lý bản ghi]
    F --> C
    D -->|Nhánh không cần| G[skipChildren]
    G --> C
    D -->|Kết thúc document| H[Đóng parser và stream]
~~~

Đặc điểm quan trọng là ứng dụng kiểm soát thời điểm tạo object và có thể chỉ giữ dữ liệu cần thiết. Parser vẫn dùng buffer nội bộ, nhưng không cần tạo toàn bộ object graph của document.

## 5. Đọc từng phần tử bằng MappingIterator

Nếu JSON có root là một array các object cùng kiểu, MappingIterator là cách thuận tiện để ánh xạ từng phần tử thành POJO.

~~~json
[
  {"id": "ORD-001", "total": 250000},
  {"id": "ORD-002", "total": 180000},
  {"id": "ORD-003", "total": 320000}
]
~~~

Class:

~~~java
public class OrderSummary {
    private String id;
    private BigDecimal total;

    public OrderSummary() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
~~~

Đọc và xử lý từng phần tử:

~~~java
ObjectMapper mapper = new ObjectMapper();
Path path = Path.of("orders.json");

try (InputStream input = Files.newInputStream(path);
     MappingIterator<OrderSummary> iterator =
             mapper.readerFor(OrderSummary.class).readValues(input)) {

    while (iterator.hasNextValue()) {
        OrderSummary order = iterator.nextValue();
        process(order);
    }
}
~~~

MappingIterator đọc chuỗi giá trị JSON và ánh xạ từng giá trị thành OrderSummary. Ứng dụng chỉ cần giữ object hiện tại trong vòng lặp nếu process() không lưu tham chiếu đến nó.

Lợi ích:
- Không cần tạo List<OrderSummary> chứa toàn bộ file.
- Có thể xử lý bản ghi ngay khi đọc được.
- Có thể ghi kết quả hoặc cập nhật hệ thống theo từng batch.
- Bộ nhớ chủ yếu phụ thuộc parser buffer, object hiện tại và trạng thái mà ứng dụng chủ động giữ lại.

MappingIterator cũng là tài nguyên có thể đóng. Dùng try-with-resources để bảo đảm iterator/parser được đóng khi hoàn tất hoặc khi xảy ra lỗi. Nếu ứng dụng tự mở InputStream, đóng stream trong cùng phạm vi như ví dụ để quản lý vòng đời rõ ràng.

### 5.1. MappingIterator không tự làm cho ứng dụng tiết kiệm bộ nhớ

Nếu vòng lặp thêm mọi object vào một danh sách:

~~~java
List<OrderSummary> allOrders = new ArrayList<>();

try (MappingIterator<OrderSummary> iterator =
             mapper.readerFor(OrderSummary.class).readValues(input)) {

    while (iterator.hasNextValue()) {
        allOrders.add(iterator.nextValue());
    }
}
~~~

thì cuối cùng toàn bộ object vẫn được giữ trong heap. MappingIterator chỉ đọc từng phần tử; cách ứng dụng giữ hoặc loại bỏ kết quả mới quyết định lợi ích bộ nhớ.

Để tiết kiệm bộ nhớ, xử lý xong từng phần tử rồi chỉ giữ lại kết quả tổng hợp cần thiết, ví dụ tổng doanh thu, số lượng bản ghi hoặc một nhóm ID.

### 5.2. Đọc theo batch

Nếu cần gửi dữ liệu đến database hoặc dịch vụ khác theo lô, có thể gom một số phần tử rồi xử lý batch:

~~~java
List<OrderSummary> batch = new ArrayList<>(500);

try (MappingIterator<OrderSummary> iterator =
             mapper.readerFor(OrderSummary.class).readValues(input)) {

    while (iterator.hasNextValue()) {
        batch.add(iterator.nextValue());

        if (batch.size() == 500) {
            processBatch(batch);
            batch.clear();
        }
    }

    if (!batch.isEmpty()) {
        processBatch(batch);
    }
}
~~~

Cách này giới hạn số object được giữ trong batch. Kích thước 500 chỉ là ví dụ; cần chọn dựa trên kích thước từng record, giới hạn database, thời gian transaction và thông lượng hệ thống.

Nếu processBatch() lưu tham chiếu đến list hoặc phần tử sau khi trả về, cần bảo đảm việc clear() không làm thay đổi dữ liệu mà thành phần nhận đang sử dụng. Có thể chuyển bản sao bất biến hoặc để processBatch xử lý đồng bộ trước khi xóa batch.

## 6. Dùng JsonParser để kiểm soát từng token

MappingIterator phù hợp khi mỗi phần tử có thể ánh xạ thành một POJO. Nếu cần chọn lọc field, bỏ qua nhánh lớn hoặc xử lý nhiều kiểu record trong cùng document, có thể dùng JsonParser trực tiếp.

Ví dụ đọc root array và ánh xạ từng object:

~~~java
ObjectMapper mapper = new ObjectMapper();

try (InputStream input = Files.newInputStream(Path.of("orders.json"));
     JsonParser parser = mapper.getFactory().createParser(input)) {

    if (parser.nextToken() != JsonToken.START_ARRAY) {
        throw new IOException("Expected a JSON array");
    }

    while (parser.nextToken() == JsonToken.START_OBJECT) {
        OrderSummary order = mapper.readValue(parser, OrderSummary.class);
        process(order);
    }
}
~~~

Luồng hoạt động:
1. Tạo parser từ InputStream.
2. Đọc token đầu và xác nhận root là START_ARRAY.
3. Tiến đến từng START_OBJECT.
4. Dùng mapper.readValue(parser, OrderSummary.class) để ánh xạ object hiện tại.
5. Xử lý object ngay sau khi đọc.
6. Tiếp tục parser đến phần tử kế tiếp.
7. Khi gặp END_ARRAY, vòng lặp kết thúc.

Cách này kết hợp Streaming API của Core với data binding của Databind. Ứng dụng không phải tự đọc từng field của OrderSummary, nhưng vẫn kiểm soát việc đọc từng object.

Nếu cần kiểm tra cấu trúc nghiêm ngặt hơn, sau vòng lặp có thể xác nhận token hiện tại là END_ARRAY và kiểm tra document không còn token dư ngoài cấu trúc dự kiến.

## 7. Đọc mảng lớn nằm bên trong một object

Dữ liệu thực tế thường không có root là array. Ví dụ:

~~~json
{
  "exportId": "EXP-2026-01",
  "createdAt": "2026-11-12T09:00:00Z",
  "metadata": {
    "source": "warehouse",
    "version": 3
  },
  "orders": [
    {"id": "ORD-001", "total": 250000},
    {"id": "ORD-002", "total": 180000}
  ]
}
~~~

Nếu chỉ cần đọc từng order, không cần tạo toàn bộ object chứa list orders. Có thể dùng parser để duyệt root object, đọc metadata nhỏ và stream qua array orders:

~~~java
ObjectMapper mapper = new ObjectMapper();

try (InputStream input = Files.newInputStream(Path.of("export.json"));
     JsonParser parser = mapper.getFactory().createParser(input)) {

    if (parser.nextToken() != JsonToken.START_OBJECT) {
        throw new IOException("Expected a JSON object");
    }

    while (parser.nextToken() != JsonToken.END_OBJECT) {
        String fieldName = parser.currentName();
        JsonToken valueToken = parser.nextToken();

        if ("exportId".equals(fieldName)
                && valueToken == JsonToken.VALUE_STRING) {
            String exportId = parser.getText();
            System.out.println("Export: " + exportId);

        } else if ("orders".equals(fieldName)
                && valueToken == JsonToken.START_ARRAY) {

            while (parser.nextToken() == JsonToken.START_OBJECT) {
                OrderSummary order =
                        mapper.readValue(parser, OrderSummary.class);
                process(order);
            }

        } else {
            parser.skipChildren();
        }
    }
}
~~~

parser.skipChildren() bỏ qua toàn bộ nội dung của object hoặc array hiện tại mà không cần tạo JsonNode cho nhánh đó. Đây là cách hữu ích khi document có metadata hoặc nhánh dữ liệu mà ứng dụng không cần.

Ví dụ trên giả định các field đầu vào có kiểu đúng như mong đợi và chỉ có một property orders. Nếu hợp đồng yêu cầu kiểm tra đầy đủ, cần xử lý field trùng, sai kiểu, thiếu orders và token kết thúc không hợp lệ theo chính sách của ứng dụng.

## 8. Chỉ đọc một phần cấu trúc thay vì tạo POJO đầy đủ

Có trường hợp ứng dụng chỉ cần một vài field từ mỗi record. Nếu tạo toàn bộ POJO có nhiều property, các object con không cần thiết vẫn tiêu tốn bộ nhớ.

Có thể đọc token trực tiếp:

~~~java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    while (parser.nextToken() != null) {
        if (parser.currentToken() == JsonToken.FIELD_NAME
                && "id".equals(parser.currentName())) {

            parser.nextToken();
            String id = parser.getValueAsString();
            processId(id);
        }
    }
}
~~~

Ví dụ này minh họa cách tìm field id trong một luồng token. Trong ứng dụng thực tế, nên theo dõi cấu trúc object và array để tránh nhầm một field id ở nhánh lồng nhau khác. Nếu cần đọc một phần tử cụ thể, hãy duy trì trạng thái parser hoặc viết một hàm xử lý object theo token.

### 8.1. Bỏ qua object/array không cần thiết

~~~java
if (parser.currentToken() == JsonToken.FIELD_NAME
        && "debugPayload".equals(parser.currentName())) {

    parser.nextToken();
    parser.skipChildren();
}
~~~

skipChildren() đặc biệt hữu ích khi field chứa object hoặc array rất lớn nhưng ứng dụng không cần dữ liệu bên trong. Parser vẫn phải đọc qua byte/character của nhánh đó để đến vị trí tiếp theo, nhưng không tạo toàn bộ object graph cho nhánh bị bỏ qua.

Nếu nguồn dữ liệu hỗ trợ seek hoặc range read thì có thể có cách bỏ qua ở tầng nguồn, nhưng một JSON stream tuần tự thông thường vẫn phải tiêu thụ dữ liệu để tiến tới token sau.

## 9. Chọn giữa POJO, tree model và streaming

Ba cách đọc có mục đích khác nhau:

| Cách tiếp cận | Đặc điểm | Phù hợp khi |
|---|---|---|
| Data Binding toàn bộ | Tạo object graph theo kiểu Java | Dữ liệu vừa phải, cần thao tác toàn bộ model |
| Tree Model | Tạo cây JsonNode | Cấu trúc động, cần truy cập nhiều vị trí hoặc sửa cây |
| Streaming API | Đọc token tuần tự | Dữ liệu lớn, chỉ cần xử lý một phần hoặc từng record |

Có thể kết hợp các cách:
- Dùng streaming parser để đi đến một object con.
- Dùng mapper.readValue(parser, Type.class) để tạo một POJO cho object đó.
- Dùng tree model cho một nhánh nhỏ có cấu trúc linh hoạt.
- Dùng JsonGenerator để ghi kết quả ra output stream mà không giữ toàn bộ output string.

Không cần tự viết custom deserializer chỉ để đọc một file lớn nếu MappingIterator hoặc parser streaming đã đáp ứng yêu cầu. Bắt đầu từ API cấp cao nhất có thể giải quyết bài toán; chỉ chuyển xuống token-level khi cần kiểm soát chi tiết.

## 10. Ghi kết quả theo luồng bằng JsonGenerator

Nếu ứng dụng đọc nhiều record rồi tạo JSON mới, không nên gom toàn bộ kết quả thành List và serialize lại nếu dữ liệu rất lớn.

JsonGenerator cho phép ghi từng phần tử:

~~~java
ObjectMapper mapper = new ObjectMapper();

try (InputStream input = Files.newInputStream(Path.of("orders.json"));
     MappingIterator<OrderSummary> iterator =
             mapper.readerFor(OrderSummary.class).readValues(input);
     OutputStream output = Files.newOutputStream(Path.of("order-summary.json"));
     JsonGenerator generator = mapper.getFactory().createGenerator(output)) {

    generator.writeStartArray();

    while (iterator.hasNextValue()) {
        OrderSummary order = iterator.nextValue();

        if (order.getTotal().signum() > 0) {
            mapper.writeValue(generator, order);
        }
    }

    generator.writeEndArray();
}
~~~

Generator ghi dấu bắt đầu array, từng object thỏa điều kiện và dấu kết thúc array. Dữ liệu đầu ra được tạo tuần tự thay vì phải tạo một String hoặc List chứa tất cả kết quả.

Trong ứng dụng thật, cần xác định rõ quyền sở hữu và vòng đời của parser, iterator, generator và stream. Tránh để nhiều thành phần cùng đóng một tài nguyên ngoài ý muốn; nếu dùng mapper.writeValue(generator, value), kiểm tra cấu hình auto-close target của generator khi generator còn được sử dụng để ghi các phần tử tiếp theo. Một cách an toàn là cấu hình generator không tự đóng target sau mỗi lần ghi value, hoặc dùng serializer trực tiếp phù hợp với pipeline.

Một lựa chọn đơn giản hơn khi chỉ ghi từng object là dùng writer/serializer thích hợp trên generator và quản lý rõ trạng thái generator. Điều quan trọng là chỉ gọi writeStartArray một lần, ghi các phần tử đúng thứ tự rồi writeEndArray.

## 11. Bộ nhớ và độ phức tạp xử lý

Giả sử file có N record và mỗi record có kích thước trung bình S.

Khi đọc toàn bộ thành List:
- Ứng dụng giữ khoảng N object cùng lúc.
- Bộ nhớ tăng theo tổng kích thước object graph của N record.
- Thời điểm bắt đầu xử lý nghiệp vụ thường đến sau khi phần lớn hoặc toàn bộ document đã được ánh xạ.

Khi đọc tuần tự:
- Ứng dụng có thể chỉ giữ một record tại một thời điểm.
- Bộ nhớ chủ yếu phụ thuộc parser buffer, kích thước record đang xử lý và dữ liệu ứng dụng chủ động giữ lại.
- Có thể bắt đầu xử lý trước khi đọc hết file.

Nếu xử lý theo batch kích thước B, bộ nhớ phần dữ liệu nghiệp vụ thường tỷ lệ với B record thay vì N record, cộng parser buffer và trạng thái khác.

~~~mermaid
flowchart LR
    A[Toàn bộ document] --> B[Materialize N object]
    B --> C[Giữ N record trong heap]
    D[JSON stream] --> E[Đọc record 1]
    E --> F[Xử lý và loại bỏ]
    F --> G[Đọc record 2]
    G --> H[Xử lý và loại bỏ]
    H --> I[Tiếp tục đến hết]
~~~

Đây là mô hình khái niệm, không phải cam kết một con số heap cụ thể. Một record đơn lẻ quá lớn vẫn có thể chiếm nhiều bộ nhớ. Nếu ứng dụng tích lũy kết quả, giữ cache hoặc đưa object vào queue không giới hạn, lợi ích streaming cũng giảm.

## 12. Streaming không đồng nghĩa với không tạo object

Có hai mức xử lý:

### 12.1. Streaming kết hợp data binding từng record

~~~java
OrderSummary order = mapper.readValue(parser, OrderSummary.class);
process(order);
~~~

Parser đọc luồng tuần tự nhưng mỗi record vẫn trở thành POJO đầy đủ. Đây thường là lựa chọn cân bằng giữa hiệu năng và khả năng bảo trì.

### 12.2. Xử lý token hoàn toàn

~~~java
while (parser.nextToken() != null) {
    switch (parser.currentToken()) {
        case FIELD_NAME -> handleFieldName(parser.currentName());
        case VALUE_STRING -> handleText(parser.getText());
        case VALUE_NUMBER_INT -> handleNumber(parser.getLongValue());
        default -> {
            // Xử lý token cấu trúc theo trạng thái hiện tại.
        }
    }
}
~~~

Ứng dụng tự đọc token và chỉ giữ những giá trị cần thiết. Cách này có thể giảm allocation khi record rất lớn hoặc chỉ cần một vài field, nhưng code phức tạp hơn: phải theo dõi trạng thái object/array, kiểu token, field lồng nhau và lỗi dữ liệu.

Hãy chọn token-level khi có lợi ích đo lường được. Nếu record có schema ổn định và vừa phải, ánh xạ thành một POJO rồi xử lý thường dễ phát triển hơn.

## 13. Những giới hạn và chi phí của đọc từng phần

Streaming giảm bộ nhớ nhưng có một số đánh đổi.

### 13.1. Khó truy cập ngược

Sau khi parser đi qua một token và nguồn không hỗ trợ seek, không thể quay lại tùy ý. Nếu nghiệp vụ cần so sánh nhiều record hoặc truy vấn lại dữ liệu cũ, phải lưu thông tin cần thiết ở nơi khác hoặc đọc lại nguồn.

### 13.2. Khó xử lý nghiệp vụ cần toàn bộ tập dữ liệu

Một số phép tính cần toàn bộ dữ liệu, ví dụ sắp xếp toàn cục hoặc tính percentile chính xác. Streaming vẫn có thể xử lý bằng thuật toán ngoài bộ nhớ, database, external sort hoặc cấu trúc thống kê gọn, nhưng không tự giải quyết mọi yêu cầu.

### 13.3. Một record lớn vẫn cần bộ nhớ

Nếu một record chứa một array hàng triệu phần tử và ứng dụng ánh xạ toàn bộ record thành POJO, toàn bộ array đó vẫn được tạo. Khi cần, phải stream sâu hơn bên trong record thay vì chỉ stream ở cấp danh sách ngoài.

### 13.4. Lỗi giữa chừng và kết quả từng phần

Nếu file hỏng ở record thứ 500.000, 499.999 record trước đó có thể đã được xử lý. Ứng dụng cần xác định:
- Có chấp nhận kết quả từng phần không?
- Có cần transaction cho toàn bộ file hay cho từng batch?
- Có cần lưu checkpoint để tiếp tục từ vị trí nào?
- Có thể bỏ qua record lỗi hay phải dừng toàn bộ import?

Streaming làm cho việc xử lý sớm hơn, nhưng cũng khiến tác động của lỗi giữa luồng cần được thiết kế rõ.

### 13.5. Backpressure và tốc độ xử lý

Nếu parser đọc nhanh hơn database hoặc dịch vụ đích xử lý, queue có thể tăng không giới hạn. Cần giới hạn batch/queue và điều tiết tốc độ đọc theo tốc độ xử lý. Streaming ở tầng Jackson không tự cung cấp cơ chế backpressure cho toàn bộ pipeline nghiệp vụ.

## 14. Xử lý lỗi và vị trí trong luồng

Khi đọc từng phần, exception có thể xảy ra sau khi nhiều record đã được xử lý. Jackson cung cấp JsonLocation và JsonMappingException path để hỗ trợ chẩn đoán.

~~~java
try (MappingIterator<OrderSummary> iterator =
             mapper.readerFor(OrderSummary.class).readValues(input)) {

    long recordNumber = 0;

    while (iterator.hasNextValue()) {
        recordNumber++;
        OrderSummary order = iterator.nextValue();

        try {
            process(order);
        } catch (RuntimeException e) {
            throw new IllegalStateException(
                    "Failed to process record " + recordNumber,
                    e
            );
        }
    }
} catch (JsonProcessingException e) {
    JsonLocation location = e.getLocation();

    if (location != null) {
        System.err.printf(
                "JSON error at line %d, column %d, byte offset %d%n",
                location.getLineNr(),
                location.getColumnNr(),
                location.getByteOffset()
        );
    }

    if (e instanceof JsonMappingException mappingException) {
        System.err.println(mappingException.getPathReference());
    }

    throw e;
}
~~~

Số record trong ví dụ là số phần tử ứng dụng đã xử lý, không phải vị trí byte. Với lỗi mapping, path cho biết property trong object; location cho biết vị trí trong nguồn JSON.

Nếu cần tiếp tục sau record lỗi, không thể mặc nhiên bỏ qua mọi exception rồi gọi nextValue(). Parser có thể đã ở trạng thái không xác định hoặc cấu trúc JSON có thể bị hỏng. Chỉ nên phục hồi khi có ranh giới record rõ ràng và cơ chế xử lý lỗi được thiết kế cho định dạng đầu vào.

## 15. Các nguyên tắc vận hành khi đọc dữ liệu lớn

- Đo kích thước file, kích thước record và heap thực tế trước khi chọn chiến lược.
- Dùng Data Binding toàn bộ khi dữ liệu vừa phải và ứng dụng cần toàn bộ model.
- Dùng MappingIterator khi đầu vào là chuỗi các giá trị cùng kiểu và cần xử lý từng phần tử.
- Dùng JsonParser trực tiếp khi cần kiểm soát cấu trúc, bỏ qua nhánh hoặc chỉ đọc một số field.
- Dùng JsonGenerator để ghi kết quả lớn theo luồng.
- Xử lý từng record hoặc batch hữu hạn; tránh tích lũy danh sách/queue không giới hạn.
- Quản lý parser, iterator, generator và stream bằng try-with-resources.
- Xác định chính sách transaction, checkpoint và lỗi giữa chừng.
- Giới hạn kích thước payload, độ sâu lồng nhau và kích thước record theo yêu cầu hệ thống.
- Không log toàn bộ dữ liệu nhạy cảm chỉ để debug lỗi stream.
- Kiểm tra cấu hình parser và giới hạn bảo vệ của phiên bản Jackson đang sử dụng khi nhận dữ liệu không đáng tin cậy.

## 16. Cách chọn chiến lược theo tình huống

| Tình huống | Lựa chọn phù hợp |
|---|---|
| File JSON nhỏ, cần thao tác mọi order | readValue thành List hoặc wrapper POJO |
| File lớn, root là array các record cùng kiểu | MappingIterator |
| Root là object nhưng có một array rất lớn | JsonParser và ánh xạ từng phần tử |
| Chỉ cần vài field trong mỗi record | JsonParser xử lý token hoặc DTO rút gọn |
| Cấu trúc thay đổi và cần sửa một cây nhỏ | JsonNode |
| Đọc và ghi chuyển đổi từng record | Parser/MappingIterator kết hợp JsonGenerator |
| Cần sort hoặc truy vấn toàn cục | Database, external processing hoặc lưu trữ có kiểm soát |

Ví dụ một pipeline nhập đơn hàng có thể:
1. Mở InputStream của file.
2. Dùng JsonParser tìm property orders.
3. Ánh xạ mỗi object order thành một OrderSummary.
4. Validate và xử lý order.
5. Gom tối đa một batch hữu hạn.
6. Ghi batch vào database trong transaction.
7. Giải phóng batch rồi tiếp tục.
8. Ghi nhận tiến độ để có thể điều tra hoặc tiếp tục khi cần.

Lựa chọn đọc từng phần thay vì tạo toàn bộ đồ thị đối tượng giúp kiểm soát bộ nhớ và bắt đầu xử lý sớm hơn với JSON lớn. Jackson cung cấp nhiều mức API: MappingIterator cho từng giá trị, JsonParser cho từng token và JsonGenerator cho output tuần tự. Hãy chọn mức trừu tượng phù hợp với cấu trúc dữ liệu và chỉ giữ trong heap những object mà bước xử lý hiện tại thực sự cần.
