# Chuyển đổi đối tượng lồng nhau và collection

Trong một ứng dụng Java, một entity thường chứa nhiều object con và collection: khách hàng có địa chỉ, đơn hàng có danh sách dòng hàng, sản phẩm có nhiều nhãn hoặc nhiều biến thể. Khi dùng Spring Data Elasticsearch, các thuộc tính này được chuyển thành object và array trong JSON document. Khi đọc document, converter dựng lại object Java theo kiểu khai báo của entity và metadata mapping.

Để thiết kế đúng, cần phân biệt hai việc: **Spring Data chuyển đổi cấu trúc Java thành JSON như thế nào** và **Elasticsearch lập chỉ mục cấu trúc JSON đó như thế nào**. Một danh sách object có thể được lưu như mảng `object` hoặc mảng `nested`; lựa chọn này ảnh hưởng cách truy vấn giữ quan hệ giữa các field trong cùng phần tử, nhưng không làm thay đổi bản chất việc converter tạo collection Java.

## 1. Từ object Java đến JSON document

Spring Data Elasticsearch sử dụng mapping metadata và `MappingElasticsearchConverter` để đọc/ghi entity. Converter xem kiểu thuộc tính, annotation và các quy tắc chuyển đổi để tạo JSON tương ứng.

Ví dụ một đơn hàng gồm thông tin người nhận và các dòng hàng:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    private Customer customer;

    private List<OrderLine> lines;

    // Constructor, getters và setters
}

public class Customer {
    private String name;
    private Address address;

    // Constructor, getters và setters
}

public class Address {
    private String street;
    private String city;
    private String postalCode;

    // Constructor, getters và setters
}

public class OrderLine {
    private String productCode;
    private Integer quantity;
    private Long unitPriceInCents;

    // Constructor, getters và setters
}
~~~

Khi ghi một entity có dữ liệu, `_source` có cấu trúc JSON tương ứng:

~~~json
{
  "customer": {
    "name": "An Nguyen",
    "address": {
      "street": "12 Example Street",
      "city": "Ho Chi Minh City",
      "postalCode": "700000"
    }
  },
  "lines": [
    {
      "productCode": "KB-001",
      "quantity": 1,
      "unitPriceInCents": 129900
    },
    {
      "productCode": "MS-002",
      "quantity": 2,
      "unitPriceInCents": 45000
    }
  ]
}
~~~

Object `Customer` trở thành JSON object; `Address` trở thành object lồng bên trong; `List<OrderLine>` trở thành JSON array gồm các object. Converter không cần mỗi class con phải là một Elasticsearch document riêng. Trong trường hợp này, chúng là các value object nằm trong document `Order`.

## 2. Chuyển đổi object lồng nhau

### 2.1. POJO lồng nhau

Với một thuộc tính có kiểu class cụ thể, converter biết kiểu đích từ khai báo thuộc tính. Ví dụ `Order.customer` có kiểu `Customer`, còn `Customer.address` có kiểu `Address`. Khi đọc `_source`, converter có đủ thông tin để dựng lại từng object.

Các class con thông thường không cần gắn `@Document`. Annotation `@Document` thường đặt trên aggregate root mà repository quản lý, ví dụ `Order`. Việc một class xuất hiện bên trong document không tự biến class đó thành một document độc lập.

Có thể khai báo mapping field rõ ràng bằng `@Field` khi muốn kiểm soát kiểu Elasticsearch:

~~~java
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class Customer {

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Object)
    private Address address;

    // Constructor, getters và setters
}
~~~

`FieldType.Object` mô tả cách Elasticsearch lập chỉ mục object con. Converter vẫn dùng kiểu Java `Address` để chuyển đổi dữ liệu.

### 2.2. Object nhiều cấp

Object có thể lồng nhiều cấp. Ví dụ `Order.customer.address` được lưu dưới đường dẫn `customer.address.city`. Elasticsearch có thể truy vấn field con bằng đường dẫn đầy đủ:

~~~json
{
  "query": {
    "term": {
      "customer.address.city": "Ho Chi Minh City"
    }
  }
}
~~~

Với mapping `object`, các field con được lập chỉ mục theo đường dẫn. Không cần tạo index riêng cho từng class Java con. Tuy nhiên, cần cân nhắc độ sâu và số lượng field để tránh document có cấu trúc quá phức tạp hoặc phát sinh quá nhiều field động.

### 2.3. Map và cấu trúc linh hoạt

Thuộc tính `Map<String, Object>` có thể dùng khi tên field con hoặc cấu trúc dữ liệu thay đổi theo loại document:

~~~java
import java.util.Map;

public class ProductMetadata {
    private Map<String, Object> attributes;

    // Getter và setter
}
~~~

Ví dụ JSON:

~~~json
{
  "attributes": {
    "color": "black",
    "weightGrams": 850,
    "wireless": true
  }
}
~~~

Map cho phép biểu diễn dữ liệu linh hoạt nhưng kiểu Java `Object` không cung cấp schema tĩnh cho từng giá trị. Converter và dynamic mapping phải suy luận hoặc chuyển đổi kiểu từ dữ liệu thực tế. Nếu một key có lúc là số, lúc là chuỗi, mapping Elasticsearch có thể xung đột. Với field quan trọng, nên khai báo schema rõ ràng hoặc chuẩn hóa kiểu trước khi ghi.

## 3. Chuyển đổi collection các kiểu đơn

Các kiểu collection như `List<String>`, `Set<String>` hoặc `List<Long>` có thể được chuyển thành JSON array. Elasticsearch không có một mapping type riêng tên là `array`; mapping mô tả kiểu của từng phần tử.

Ví dụ entity:

~~~java
import java.util.List;
import java.util.Set;

public class Product {

    @Field(type = FieldType.Keyword)
    private List<String> tags;

    @Field(type = FieldType.Long)
    private Set<Long> compatibleModelIds;

    // Constructor, getters và setters
}
~~~

Document có thể chứa:

~~~json
{
  "tags": ["keyboard", "wireless", "office"],
  "compatibleModelIds": [101, 205, 310]
}
~~~

Field `tags` vẫn có mapping `keyword`, còn `compatibleModelIds` có mapping `long`. Một field có thể nhận một giá trị đơn hoặc nhiều giá trị cùng kiểu; Elasticsearch xử lý chúng như các giá trị của cùng field.

### 3.1. List, Set và thứ tự phần tử

`List` giữ thứ tự phần tử trong object Java. JSON array được ghi vào `_source` theo thứ tự đó, vì vậy khi đọc lại qua converter, collection dạng List có thể được dựng theo thứ tự lưu trữ.

`Set` thể hiện ngữ nghĩa không trùng lặp ở phía Java. Khi chuyển đổi, các phần tử được đọc vào Set sẽ tuân theo quy tắc equality/hashCode của class phần tử. Elasticsearch không tự bảo đảm các giá trị trong array là duy nhất.

Đối với truy vấn, không nên giả định Elasticsearch giữ vị trí phần tử của một array scalar để có thể tìm kiếm theo index. Thứ tự trong `_source` phục vụ việc tái tạo dữ liệu; inverted index phục vụ tìm kiếm theo giá trị. Nếu thứ tự là một phần của nghiệp vụ, hãy giữ dữ liệu trong `_source` và thiết kế truy vấn/sắp xếp phù hợp thay vì dựa vào vị trí array trong inverted index.

## 4. Collection các object: `object` hay `nested`?

Đây là quyết định quan trọng khi document chứa danh sách object. Spring Data có thể chuyển `List<OrderLine>` thành array JSON trong cả hai trường hợp. Annotation mapping quyết định Elasticsearch xử lý mảng đó theo `object` hay `nested`.

### 4.1. Mảng object mặc định

Giả sử document có hai dòng hàng:

~~~json
{
  "lines": [
    { "productCode": "KB-001", "quantity": 1 },
    { "productCode": "MS-002", "quantity": 5 }
  ]
}
~~~

Với mapping `object` mặc định, Elasticsearch làm phẳng các giá trị field con khi lập chỉ mục. Có thể hình dung dữ liệu index thành các tập giá trị:

~~~text
lines.productCode = ["KB-001", "MS-002"]
lines.quantity    = [1, 5]
~~~

Khi truy vấn đồng thời `productCode = KB-001` và `quantity = 5`, Elasticsearch có thể ghép hai giá trị thuộc hai object khác nhau và trả về document. Đây là kết quả không mong muốn nếu điều kiện phải khớp trên cùng một dòng hàng.

### 4.2. Dùng `nested` để giữ quan hệ giữa các phần tử

Nếu cần truy vấn nhiều field trên cùng một object trong mảng, khai báo field là `nested`:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class Order {

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;

    // Các thuộc tính khác, getters và setters
}
~~~

Với mapping `nested`, Elasticsearch lập chỉ mục mỗi phần tử object như một document nội bộ riêng và giữ mối quan hệ giữa các field trong phần tử đó. Nested query yêu cầu các điều kiện cùng khớp trên một phần tử:

~~~json
{
  "query": {
    "nested": {
      "path": "lines",
      "query": {
        "bool": {
          "must": [
            { "term": { "lines.productCode": "KB-001" } },
            { "range": { "lines.quantity": { "gte": 5 } } }
          ]
        }
      }
    }
  }
}
~~~

Query trên không khớp với ví dụ ban đầu vì dòng hàng có `productCode = KB-001` có `quantity = 1`, còn dòng hàng có `quantity = 5` là sản phẩm `MS-002`.

Nested có chi phí lưu trữ và truy vấn cao hơn object thông thường. Chỉ dùng khi cần bảo toàn quan hệ giữa các field trong cùng phần tử mảng. Nếu chỉ cần lọc theo từng giá trị độc lập hoặc đọc lại JSON, `object` thường đơn giản hơn.

## 5. Khai báo mapping cho nested collection

Với entity `Order` và `OrderLine`, có thể khai báo mapping tường minh:

~~~java
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Object)
    private Customer customer;

    @Field(type = FieldType.Nested)
    private List<OrderLine> lines;

    // Constructor, getters và setters
}

public class Customer {
    private String name;
    private Address address;

    // Constructor, getters và setters
}

public class Address {
    private String street;
    private String city;

    // Constructor, getters và setters
}

public class OrderLine {
    @Field(type = FieldType.Keyword)
    private String productCode;

    @Field(type = FieldType.Integer)
    private Integer quantity;

    @Field(type = FieldType.Long)
    private Long unitPriceInCents;

    // Constructor, getters và setters
}
~~~

Mapping Elasticsearch tương ứng về mặt ý tưởng:

~~~json
{
  "mappings": {
    "properties": {
      "customer": {
        "properties": {
          "name": { "type": "text" },
          "address": {
            "properties": {
              "street": { "type": "text" },
              "city": { "type": "keyword" }
            }
          }
        }
      },
      "lines": {
        "type": "nested",
        "properties": {
          "productCode": { "type": "keyword" },
          "quantity": { "type": "integer" },
          "unitPriceInCents": { "type": "long" }
        }
      }
    }
  }
}
~~~

Converter sử dụng kiểu Java để tạo và dựng object. Elasticsearch mapping quyết định cách các field được lập chỉ mục. Hai phần cần khớp nhau về tên và kiểu field, nhưng `Nested` không phải một cơ chế chuyển đổi collection riêng trong Java.

## 6. Đọc và ghi qua repository

Repository có thể lưu và đọc toàn bộ aggregate root. Converter tự xử lý các object và collection theo mapping metadata:

~~~java
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface OrderRepository extends ElasticsearchRepository<Order, String> {
}
~~~

Ghi đơn hàng:

~~~java
Order order = new Order();
order.setId("ORD-1001");
order.setCustomer(new Customer(
        "An Nguyen",
        new Address("12 Example Street", "Ho Chi Minh City")));
order.setLines(List.of(
        new OrderLine("KB-001", 1, 129900L),
        new OrderLine("MS-002", 2, 45000L)));

orderRepository.save(order);
~~~

Đọc lại:

~~~java
Order loaded = orderRepository.findById("ORD-1001")
        .orElseThrow();

Customer customer = loaded.getCustomer();
List<OrderLine> lines = loaded.getLines();
~~~

`save` ghi aggregate root thành một document trong index `orders`. `findById` lấy document theo `_id` và converter dựng lại `Customer`, `Address` cùng danh sách `OrderLine`. Không cần gọi repository riêng cho từng object con vì chúng không phải document độc lập.

Khi tìm theo nested fields, có thể dùng repository query method phù hợp nếu biểu diễn được nested query, hoặc dùng `ElasticsearchOperations`/native query để chỉ rõ nested path và điều kiện. Một query trên nested field phải được bọc trong nested query của Elasticsearch; chỉ dùng dot notation không tự tạo ngữ nghĩa nested.

## 7. Chuyển đổi qua `ElasticsearchOperations`

`ElasticsearchOperations` cung cấp API cấp cao để lưu, đọc và tìm kiếm entity. Cách chuyển đổi object/collection vẫn dựa trên mapping converter được cấu hình trong Spring context.

Ví dụ lưu và đọc entity:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public class OrderService {

    private final ElasticsearchOperations operations;

    public OrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Order save(Order order) {
        return operations.save(order);
    }

    public Order find(String id) {
        return operations.get(id, Order.class);
    }
}
~~~

Khi dùng query API, có thể ánh xạ kết quả search hit về entity hoặc đọc source theo projection. Nếu source filtering loại bỏ field cần thiết để dựng object con, kết quả Java sẽ thiếu dữ liệu hoặc converter không thể khôi phục kiểu cụ thể.

## 8. Collection rỗng, null và field không tồn tại

Các trạng thái sau có ý nghĩa khác nhau trong JSON:

~~~json
{
  "lines": [
    { "productCode": "KB-001", "quantity": 1 }
  ],
  "tags": [],
  "comment": null
}
~~~

- `lines` có phần tử: collection có dữ liệu.
- `tags` là mảng rỗng: field tồn tại trong source nhưng không có phần tử.
- `comment` là `null`: field có giá trị null trong source.
- Field bị lược bỏ hoàn toàn: document không chứa thuộc tính đó.

Elasticsearch mặc định không lập chỉ mục giá trị `null` như một term có thể tìm kiếm; có thể dùng `null_value` trong một số kiểu mapping nếu cần biểu diễn giá trị thay thế cho việc lập chỉ mục. `_source` vẫn có thể lưu giá trị null ban đầu.

Khi đọc, hành vi gán giá trị phụ thuộc constructor, property accessor và cấu hình mapping converter của entity. Với collection, nên quyết định rõ ứng dụng coi field bị thiếu/null là `null` hay collection rỗng. Nếu nghiệp vụ yêu cầu luôn có danh sách, có thể khởi tạo collection rỗng trong constructor hoặc factory và kiểm tra hành vi khi converter dựng object.

Không nên mặc định `null`, field không tồn tại và `[]` là tương đương. Chúng có thể mang ý nghĩa khác nhau khi cập nhật document, kiểm tra sự tồn tại hoặc hiển thị dữ liệu.

## 9. Generic collection và kiểu phần tử

Khai báo kiểu phần tử cụ thể giúp converter biết cần dựng object nào:

~~~java
private List<OrderLine> lines;
private Set<String> tags;
private Map<String, Address> offices;
~~~

Với `List<OrderLine>`, generic type cung cấp thông tin `OrderLine` để chuyển đổi từng phần tử. Với `Map<String, Address>`, converter có thể chuyển đổi value theo kiểu `Address`.

Trường hợp khai báo raw collection hoặc kiểu quá tổng quát làm giảm thông tin kiểu:

~~~java
private List values;
private List<Object> attributes;
~~~

Khi đó converter không có kiểu phần tử cụ thể để dựng class con. Các phần tử có thể được đọc thành kiểu đơn giản hoặc cấu trúc Map tùy dữ liệu và mapping metadata; không nên giả định converter luôn tự suy ra class nghiệp vụ đúng.

Ưu tiên khai báo generic type cụ thể. Nếu dữ liệu thực sự đa hình, dùng interface/abstract class cùng type hint hoặc `@TypeAlias` và bảo đảm implementation được mapping context nhận diện. Nếu schema linh hoạt, dùng `Map<String, Object>` có chủ đích và tự xác thực kiểu dữ liệu.

Java generic type erasure cũng có nghĩa kiểu tham số không còn đầy đủ ở mọi tình huống runtime. Các property được khai báo trực tiếp trên entity thường cung cấp generic metadata cho Spring Data; các cấu trúc generic tự tạo hoặc converter tùy chỉnh có thể cần khai báo type rõ ràng hơn.

## 10. Custom conversion cho object đặc biệt

Các kiểu phổ biến như String, số, boolean, ngày giờ, collection, Map và POJO thường được converter hỗ trợ trực tiếp. Nếu object có biểu diễn đặc biệt, chẳng hạn một value object cần chuyển thành chuỗi hoặc cấu trúc JSON riêng, có thể đăng ký custom converter.

Ví dụ một value object `Money` muốn lưu dưới dạng số tiền theo đơn vị cent:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyToLongConverter implements Converter<Money, Long> {

    @Override
    public Long convert(Money source) {
        return source.amountInCents();
    }
}
~~~

Converter đọc theo chiều ngược lại:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class LongToMoneyConverter implements Converter<Long, Money> {

    @Override
    public Money convert(Long source) {
        return Money.ofCents(source);
    }
}
~~~

Đăng ký hai converter trong `ElasticsearchCustomConversions` theo cơ chế cấu hình của phiên bản Spring Data Elasticsearch đang dùng. Khi converter được đăng ký đúng, mapping converter có thể dùng chúng khi ghi/đọc thuộc tính `Money`.

Chỉ tạo custom converter khi cách ánh xạ mặc định không đáp ứng yêu cầu. Converter phải xác định rõ chiều đọc và chiều ghi, tránh đăng ký hai converter mơ hồ cùng source/target type. Cũng cần kiểm thử dữ liệu cũ vì thay đổi biểu diễn JSON có thể làm document đã lưu không còn đọc được.

## 11. Cập nhật một phần và thay thế collection

Khi lưu lại toàn bộ entity, Spring Data chuyển object hiện tại thành document theo cơ chế save. Nếu collection đã thay đổi, document được ghi sẽ phản ánh trạng thái collection trong object được gửi.

Ví dụ một đơn hàng trước đó có hai dòng hàng, nhưng object mới chỉ còn một dòng. Khi thay thế document bằng thao tác save phù hợp, `_source.lines` sẽ phản ánh collection mới. Hãy phân biệt thao tác thay thế toàn bộ document với update một phần bằng `UpdateQuery` hoặc API tương ứng; update một phần có thể chỉ sửa field được chỉ định và giữ các field khác.

Với nested array, nếu cần thêm hoặc xóa một phần tử, cần xác định thao tác cập nhật có thể biểu diễn chính xác bằng API update đang dùng hay cần đọc aggregate, thay đổi collection rồi ghi lại document. Không nên giả định một repository save sẽ tự động phát hiện và đồng bộ từng phần tử con như ORM quan hệ.

Elasticsearch không có quan hệ foreign key hay cơ chế cascade như JPA. Object lồng nhau được lưu trong cùng document; thay đổi document là thay đổi aggregate JSON đó. Nếu object con cần vòng đời, tìm kiếm hoặc cập nhật độc lập, hãy cân nhắc mô hình hóa nó thành document riêng và tham chiếu bằng ID.

## 12. Lỗi thường gặp khi chuyển đổi object và collection

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Object con không được chuyển đổi đúng | Property khai báo kiểu quá tổng quát hoặc cấu trúc JSON không khớp với class. | Dùng kiểu Java cụ thể, kiểm tra tên field và constructor/accessor. |
| Collection object đọc được nhưng query ghép nhầm field giữa các phần tử | Mapping đang là `object` và truy vấn yêu cầu điều kiện cùng phần tử. | Đổi mapping sang `nested`, tạo lại index/reindex và dùng nested query. |
| Giá trị trong Map có kiểu không nhất quán | Dynamic mapping suy ra kiểu từ document đầu tiên rồi gặp giá trị khác kiểu. | Chuẩn hóa kiểu dữ liệu hoặc khai báo schema rõ ràng. |
| Collection trả về null dù mong muốn danh sách rỗng | Field bị thiếu/null hoặc constructor không khởi tạo collection. | Xác định semantics của null/empty và khởi tạo theo yêu cầu domain. |
| Generic list đọc thành Map hoặc kiểu đơn giản | Generic type bị khai báo raw hoặc là `Object`. | Khai báo kiểu phần tử cụ thể hoặc cấu hình polymorphic type conversion. |
| Custom converter không được gọi | Converter chưa được đăng ký hoặc source/target type không khớp. | Kiểm tra `ElasticsearchCustomConversions` và chiều converter. |
| Nested query không trả kết quả | Query thiếu `nested` wrapper hoặc path không đúng. | Kiểm tra mapping và `path` trong nested query. |

## 13. Quy trình thiết kế object và collection

Khi thiết kế entity cho Spring Data Elasticsearch, có thể đi theo thứ tự:

1. Xác định đâu là aggregate root được lưu thành document; class con nào chỉ là value object.
2. Dùng POJO có kiểu cụ thể cho object lồng nhau; dùng generic collection có khai báo kiểu phần tử rõ ràng.
3. Chọn `object` cho cấu trúc JSON thông thường; chọn `nested` khi query cần giữ quan hệ field trong cùng phần tử mảng.
4. Chọn mapping type cho field con theo mục đích tìm kiếm: `text`, `keyword`, số, ngày giờ hoặc boolean.
5. Quyết định semantics của List, Set, Map, null và collection rỗng trong domain.
6. Dùng custom conversion chỉ khi cần một biểu diễn lưu trữ riêng và đăng ký rõ converter đọc/ghi.
7. Lưu document mẫu, đọc lại qua repository/`ElasticsearchOperations` và kiểm tra kiểu runtime cùng dữ liệu collection.
8. Kiểm tra truy vấn nested và source filtering nếu ứng dụng chỉ lấy một phần document.

Spring Data Elasticsearch chuyển object lồng nhau thành JSON object và collection thành JSON array dựa trên kiểu thuộc tính Java. Elasticsearch mapping quyết định cách các field đó được lập chỉ mục: `object` phù hợp với object thông thường, còn `nested` giữ quan hệ giữa field trong từng phần tử khi truy vấn. Khai báo kiểu phần tử rõ ràng, chọn đúng mapping và xác định semantics của collection giúp dữ liệu có thể được ghi, đọc và tìm kiếm nhất quán.
