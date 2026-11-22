# `@Routing`, `RoutingResolver` và thao tác đọc ghi dữ liệu cha-con

Trong Elasticsearch, routing quyết định document được gửi đến shard nào khi index, get, update hoặc delete. Đây là yếu tố quan trọng khi một index có nhiều shard và ứng dụng cần truy cập document bằng một khóa định tuyến ổn định thay vì chỉ dựa vào `_id`.

Routing đặc biệt quan trọng với quan hệ parent-child. Elasticsearch dùng join field để biểu diễn document cha và document con trong cùng một index, nhưng hai document liên quan phải nằm trên cùng shard. Vì vậy, document con cần được index với cùng routing value mà root parent đang dùng; trong cấu hình mặc định, giá trị này thường là ID của parent gốc.

Spring Data Elasticsearch hỗ trợ routing qua ba cơ chế chính:

- `@Routing`: khai báo routing ở cấp entity, lấy giá trị từ một property hoặc SpEL expression.
- `RoutingResolver`: cung cấp logic routing tùy chỉnh cho entity hoặc request không có entity.
- `JoinField` cùng `@JoinTypeRelations`: biểu diễn loại quan hệ và parent ID trong một join field; Spring Data có thể tự suy ra routing từ parent của quan hệ một cấp.

Nắm rõ các cơ chế này giúp thao tác `save`, `get`, `update`, `delete` và truy vấn parent-child đi đúng shard, tránh tình trạng ghi được nhưng đọc không thấy document.

## 1. Routing trong Elasticsearch là gì?

Một index Elasticsearch được chia thành các primary shard. Khi index một document, Elasticsearch cần quyết định shard đích. Mặc định, shard được chọn từ `_id` của document. Nếu request có routing value, Elasticsearch dùng routing value đó để tính shard thay cho `_id`.

Ví dụ:

```http
PUT /orders/_doc/O-100?routing=customer-42
Content-Type: application/json

{
  "order_id": "O-100",
  "customer_id": "customer-42",
  "status": "PAID"
}
```

Document `O-100` được định tuyến bằng `customer-42`. Khi đọc hoặc xóa document này bằng ID, request cần cùng routing value:

```http
GET /orders/_doc/O-100?routing=customer-42
```

Nếu bỏ routing, Elasticsearch có thể tìm ở shard được tính từ ID `O-100`, trong khi document thực tế được lưu ở shard tính từ `customer-42`. Kết quả có thể là 404 dù document vẫn tồn tại.

### 1.1. Routing không phải là ID

Hai khái niệm có mục đích khác nhau:

| Giá trị | Vai trò |
|---|---|
| `_id` | Định danh duy nhất của document trong index. |
| `routing` | Giá trị dùng để chọn shard chứa document. |
| Parent ID | Định danh document cha trong quan hệ join. |

Trong parent-child một cấp, routing thường bằng parent ID. Nhưng routing không nhất thiết luôn bằng `_id` hoặc parent ID; ứng dụng có thể dùng tenant ID, customer ID hoặc một khóa khác nếu mọi document liên quan được định tuyến nhất quán.

### 1.2. Vì sao cần custom routing?

Custom routing hữu ích trong các trường hợp:

- Các document của cùng tenant cần được lưu cùng shard.
- Đơn hàng của cùng khách hàng thường được đọc cùng nhau.
- Parent và child phải nằm cùng shard để join hoạt động.
- Ứng dụng thường truy vấn theo một khóa phân vùng đã biết và muốn giới hạn số shard cần tìm kiếm.

Routing có thể giảm fan-out khi request có routing value phù hợp. Tuy nhiên, routing không tự tạo phân vùng dữ liệu độc lập, không thay thế authorization và có thể gây lệch tải nếu một routing key quá lớn.

## 2. Khai báo `@Routing` trong Spring Data Elasticsearch

`@Routing` là annotation ở cấp class/entity. Giá trị của annotation chỉ định cách Spring Data lấy routing value cho các thao tác trên entity.

Ví dụ entity có property `routing`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Routing;

@Document(indexName = "orders")
@Routing("routing")
public class OrderDocument {

    @Id
    private String id;

    @Field(name = "customer_id", type = FieldType.Keyword)
    private String customerId;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String routing;

    // constructors, getters, setters
}
```

Trong ví dụ, `@Routing("routing")` có nghĩa property tên `routing` được dùng làm routing value. Giá trị này được lấy từ entity khi Spring Data thực hiện thao tác có entity.

Ví dụ lưu document:

```java
OrderDocument order = new OrderDocument();
order.setId("O-100");
order.setCustomerId("customer-42");
order.setStatus("PAID");
order.setRouting("customer-42");

orderRepository.save(order);
```

Spring Data sử dụng `customer-42` làm routing khi lưu document. Khi entity được đọc và có đủ property routing, các thao tác dựa trên entity có thể tiếp tục dùng cùng giá trị đó.

### 2.1. Annotation không nằm trên property

Một điểm dễ nhầm là `@Routing` không được đặt trực tiếp trên field `routing`. Annotation được đặt trên class và nhận tên property làm tham số:

```java
@Document(indexName = "orders")
@Routing("routing")
class OrderDocument {
    @Id String id;
    String routing;
}
```

Property `routing` vẫn cần tồn tại trong entity và phải được điền giá trị đúng trước khi ghi.

### 2.2. Dùng SpEL để tính routing

Nếu routing cần được suy ra từ nhiều property, có thể khai báo SpEL expression:

```java
@Document(indexName = "orders")
@Routing("@orderRouting.getRouting(#entity)")
public class OrderDocument {
    // fields and accessors
}
```

Bean `orderRouting` cần có method nhận entity và trả về routing value:

```java
import org.springframework.stereotype.Component;

@Component("orderRouting")
public class OrderRouting {

    public String getRouting(Object entity) {
        if (entity instanceof OrderDocument order) {
            return order.getCustomerId();
        }
        return null;
    }
}
```

Trong SpEL, `#entity` tham chiếu entity đang được xử lý. Method phải trả về `String` routing value hoặc `null` nếu không có routing.

SpEL phù hợp khi quy tắc định tuyến có thể diễn đạt gọn từ entity. Nếu logic phức tạp, phụ thuộc ngữ cảnh request hoặc cần tùy chỉnh theo từng operations instance, `RoutingResolver` thường rõ ràng hơn.

## 3. `RoutingResolver` là gì?

`RoutingResolver` là interface của Spring Data Elasticsearch dùng để xác định routing value. Nó hỗ trợ hai tình huống:

- Có entity: `getRouting(bean)` lấy routing từ object đang được lưu/đọc.
- Không có entity: `getRouting()` trả routing mặc định cho thao tác chỉ có ID hoặc query không gắn entity.

Interface còn có factory method `RoutingResolver.just(value)` để tạo resolver luôn trả về một giá trị cố định.

Package:

```java
import org.springframework.data.elasticsearch.core.routing.RoutingResolver;
```

### 3.1. Routing cố định với `RoutingResolver.just`

Khi biết sẵn routing value, có thể dùng resolver được cung cấp:

```java
String orderId = "O-100";
String customerRouting = "customer-42";

OrderDocument order = operations
        .withRouting(RoutingResolver.just(customerRouting))
        .get(orderId, OrderDocument.class);
```

Để xóa document theo ID:

```java
operations
        .withRouting(RoutingResolver.just(customerRouting))
        .delete(orderId);
```

`withRouting(...)` trả về một bản operations có routing được cấu hình. Có thể dùng bản đó cho thao tác cần cùng routing:

```java
ElasticsearchOperations customerOperations =
        operations.withRouting(RoutingResolver.just(customerRouting));

OrderDocument order = customerOperations.get(orderId, OrderDocument.class);
customerOperations.delete(orderId);
```

Điều này đặc biệt quan trọng với `get(ID)` và `delete(ID)`: request chỉ có ID nên Spring Data không có entity để đọc property routing. Ứng dụng phải cung cấp routing bằng resolver hoặc API phù hợp.

### 3.2. Tạo resolver tùy chỉnh

Nếu mỗi entity có routing khác nhau, có thể implement `RoutingResolver`:

```java
import org.springframework.data.elasticsearch.core.routing.RoutingResolver;

public class TenantRoutingResolver implements RoutingResolver {

    @Override
    public String getRouting() {
        // Used when there is no entity to inspect.
        return null;
    }

    @Override
    public <T> String getRouting(T bean) {
        if (bean instanceof OrderDocument order) {
            return order.getCustomerId();
        }

        if (bean instanceof CustomerDocument customer) {
            return customer.getTenantId();
        }

        return null;
    }
}
```

Áp dụng resolver:

```java
RoutingResolver resolver = new TenantRoutingResolver();
ElasticsearchOperations tenantOperations = operations.withRouting(resolver);

tenantOperations.save(order);
```

`withRouting` tạo một bản `ElasticsearchOperations` có resolver tùy chỉnh. Resolver có thể trả routing dựa trên loại entity, tenant, customer hoặc một quy tắc nghiệp vụ khác.

Không nên viết resolver dựa trên dữ liệu request chưa được xác thực. Nếu routing liên quan tenant, tenant ID cần lấy từ security context hoặc nguồn đáng tin cậy ở server.

### 3.3. Phân biệt `@Routing`, SpEL và `RoutingResolver`

| Cơ chế | Cách hoạt động | Khi phù hợp |
|---|---|---|
| `@Routing("routing")` | Lấy giá trị từ property được chỉ định. | Entity đã có field routing rõ ràng. |
| `@Routing("@bean.method(#entity)")` | Dùng SpEL gọi bean để tính routing. | Quy tắc ngắn dựa trên entity. |
| `RoutingResolver` | Tùy chỉnh logic lấy routing cho operations instance. | Cần logic phức tạp hoặc routing khác nhau theo từng luồng. |
| `RoutingResolver.just(value)` | Luôn trả một routing value cố định. | `get(ID)`, `delete(ID)` hoặc query biết trước routing. |

Chọn một nguồn routing rõ ràng cho mỗi luồng thao tác. Nếu vừa có annotation, vừa có resolver tùy chỉnh, cần hiểu resolver được gắn vào operations instance sẽ quyết định routing mà instance đó sử dụng.

## 4. Quan hệ cha-con trong Elasticsearch

Elasticsearch không phải cơ sở dữ liệu quan hệ. Quan hệ parent-child được biểu diễn bằng kiểu mapping `join`, trong đó parent và child là các document riêng biệt trong cùng một index.

Ví dụ diễn đàn:

- `question` là document cha.
- `answer` là document con của question.
- `comment` cũng là document con của question.
- `vote` là document con của answer.

```text
question Q1
   |
   +---- answer A1
   |        |
   |        +---- vote V1
   |        +---- vote V2
   |
   +---- answer A2
   |
   +---- comment C1
```

Parent-child join có một số ràng buộc quan trọng:

- Parent và child phải nằm trong cùng index.
- Các document liên quan phải nằm trên cùng shard.
- Một child document có một parent theo quan hệ join đã khai báo.
- Quan hệ được mô tả bằng một join field trong mapping.
- Elasticsearch không tự tạo cascade update/delete như ORM quan hệ.

Parent-child phù hợp khi document cha và con cần được cập nhật độc lập hoặc số lượng child lớn, nhưng không nên dùng chỉ để mô phỏng mọi quan hệ dữ liệu. Join query có chi phí cao hơn các truy vấn field thông thường; nếu dữ liệu đọc thường xuyên theo một cấu trúc cố định, denormalization hoặc nested mapping có thể phù hợp hơn.

## 5. Khai báo join mapping bằng `@JoinTypeRelations`

Spring Data Elasticsearch hỗ trợ join mapping qua `JoinField` và annotation `@JoinTypeRelations`.

Ví dụ entity dùng chung cho question, answer, comment và vote:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.annotations.Routing;
import org.springframework.data.elasticsearch.core.join.JoinField;

@Document(indexName = "statements")
@Routing("routing")
public class Statement {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String text;

    @Field(type = FieldType.Keyword)
    private String routing;

    @JoinTypeRelations(relations = {
            @JoinTypeRelation(parent = "question", children = {"answer", "comment"}),
            @JoinTypeRelation(parent = "answer", children = "vote")
    })
    private JoinField<String> relation;

    // constructors, getters, setters
}
```

Trong ví dụ:

- `@JoinTypeRelations` khai báo đồ thị các loại quan hệ.
- `question` có thể có `answer` và `comment`.
- `answer` có thể có `vote`.
- `JoinField<String>` lưu tên relation và parent ID.
- Generic type `String` phải cùng kiểu với property `@Id`.
- `@Routing("routing")` khai báo property `routing` được dùng làm routing value khi entity cần custom routing.

Spring Data có thể tạo mapping join tương ứng khi tạo index:

```json
{
  "properties": {
    "relation": {
      "type": "join",
      "relations": {
        "question": ["answer", "comment"],
        "answer": "vote"
      }
    },
    "routing": {
      "type": "keyword"
    }
  }
}
```

Chỉ một join field được khai báo cho một index. Có thể định nghĩa nhiều relation trong field đó, nhưng không tạo nhiều join field độc lập để mô phỏng các quan hệ khác nhau trong cùng index.

## 6. `JoinField` biểu diễn parent và child

`JoinField<ID>` có hai dạng constructor thường dùng:

```java
new JoinField<>("question")
new JoinField<>("answer", questionId)
```

- Với parent/root document, chỉ truyền tên relation.
- Với child document, truyền tên relation và ID của parent.

Ví dụ:

```java
Statement question = new Statement();
question.setId("Q-100");
question.setText("How is the weather?");
question.setRelation(new JoinField<>("question"));

Statement answer = new Statement();
answer.setId("A-101");
answer.setText("Sunny");
answer.setRelation(new JoinField<>("answer", question.getId()));
```

Document cha và con là hai document độc lập. `JoinField` không chứa toàn bộ object parent và không tự lưu child vào một mảng bên trong parent.

Khi Elasticsearch serialize join field, document cha có thể được biểu diễn:

```json
{
  "id": "Q-100",
  "text": "How is the weather?",
  "relation": "question"
}
```

Document con:

```json
{
  "id": "A-101",
  "text": "Sunny",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  }
}
```

Hình thức JSON trên thể hiện ý nghĩa của join field; khi thao tác qua Spring Data, hãy để converter xử lý `JoinField` thay vì tự tạo source JSON nếu không cần thiết.

## 7. Lưu parent trước, sau đó lưu child

Ví dụ lưu question và hai answer:

```java
Statement savedQuestion = repository.save(
        createStatement("How is the weather?", new JoinField<>("question"))
);

Statement sunnyAnswer = repository.save(
        createStatement("Sunny", new JoinField<>("answer", savedQuestion.getId()))
);

Statement rainyAnswer = repository.save(
        createStatement("Rainy", new JoinField<>("answer", savedQuestion.getId()))
);
```

Nên lưu parent trước để có ID và routing cần thiết cho child. Trong ứng dụng thực tế, cần bảo đảm ID cha đã được tạo và có thể xác định trước khi tạo `JoinField` của child.

### 7.1. Routing tự động cho quan hệ một cấp

Khi dùng join type, Spring Data Elasticsearch tự động dùng property `parent` của `JoinField` làm routing value trong quan hệ parent-child một cấp.

Ví dụ child answer có parent `Q-100`, routing mặc định là `Q-100`. Nhờ đó parent và child được gửi đến cùng shard.

Điều này đúng với quan hệ một cấp:

```text
question Q-100 (root)
    |
    +---- answer A-101 (routing = Q-100)
    +---- answer A-102 (routing = Q-100)
```

Khi child có parent trực tiếp là root, parent ID cũng chính là routing value cần dùng.

### 7.2. Quan hệ nhiều cấp phải route về root parent

Với quan hệ nhiều cấp:

```text
question Q-100
    |
    +---- answer A-101
              |
              +---- vote V-201
```

Vote có parent trực tiếp là answer `A-101`, nhưng cả ba document phải ở cùng shard. Vì vậy routing của vote phải là routing value của root question `Q-100`, không phải ID của answer `A-101`. Trong ví dụ mặc định này, routing value của root question chính là ID `Q-100`.

Ví dụ:

```java
Statement vote = new Statement();
vote.setId("V-201");
vote.setText("+1 for the answer");
vote.setRouting(savedQuestion.getId());
vote.setRelation(new JoinField<>("vote", sunnyAnswer.getId()));

repository.save(vote);
```

Ở đây:

- `JoinField` lưu parent trực tiếp là `A-101`.
- `routing` lưu root parent là `Q-100`.

Đây là khác biệt quan trọng: parent ID trong `JoinField` mô tả quan hệ logic, còn routing xác định shard. Với cây nhiều cấp, hai giá trị này không nhất thiết giống nhau. Nếu root parent được lưu bằng custom routing khác ID của nó, descendant phải dùng đúng custom routing đó; không tự suy ra routing bằng cách lấy root ID.

## 8. `@Routing` và `RoutingResolver` trong parent-child

Một entity có thể dùng `@Routing("routing")` để lấy routing từ property. Trong ví dụ question/answer/vote:

- Root question có thể dùng ID của chính nó làm routing khi cần.
- Answer một cấp có thể lấy parent ID từ `JoinField` theo cơ chế routing join mặc định.
- Vote nhiều cấp phải được gán routing root question rõ ràng.

Ví dụ builder cho entity:

```java
private Statement newQuestion(String id, String text) {
    Statement statement = new Statement();
    statement.setId(id);
    statement.setText(text);
    statement.setRelation(new JoinField<>("question"));
    statement.setRouting(id);
    return statement;
}

private Statement newAnswer(String id, String text, Statement question) {
    Statement statement = new Statement();
    statement.setId(id);
    statement.setText(text);
    statement.setRelation(new JoinField<>("answer", question.getId()));
    statement.setRouting(question.getId());
    return statement;
}

private Statement newVote(String id, String text,
                          Statement answer, Statement rootQuestion) {
    Statement statement = new Statement();
    statement.setId(id);
    statement.setText(text);
    statement.setRelation(new JoinField<>("vote", answer.getId()));
    statement.setRouting(rootQuestion.getId());
    return statement;
}
```

Với các quan hệ một cấp, Spring Data có thể suy ra routing từ parent của `JoinField`. Nếu entity khai báo routing property/SpEL riêng, hãy đảm bảo giá trị được cung cấp cho những trường hợp cần route tường minh, đặc biệt với quan hệ nhiều cấp.

### 8.1. Resolver cho cây quan hệ nhiều cấp

Nếu nhiều loại child cần cùng một quy tắc tìm root parent, có thể gom logic vào resolver:

```java
public class StatementRoutingResolver implements RoutingResolver {

    @Override
    public String getRouting() {
        return null;
    }

    @Override
    public <T> String getRouting(T bean) {
        if (bean instanceof Statement statement) {
            return statement.getRouting();
        }
        return null;
    }
}
```

Sau đó dùng:

```java
ElasticsearchOperations statementOperations =
        operations.withRouting(new StatementRoutingResolver());

statementOperations.save(vote);
```

Resolver này giả định service đã gán `routing` root chính xác lên entity. Nếu resolver phải truy vấn repository để tìm root parent, cần cân nhắc chi phí và tránh tạo vòng lặp giữa thao tác save và việc resolve routing.

## 9. Đọc document bằng ID khi có routing

Khi một document được lưu với routing, cùng routing value phải được cung cấp cho các thao tác get/delete theo ID.

Ví dụ lấy vote `V-201` được lưu với routing `Q-100`:

```java
String voteId = "V-201";
String rootRouting = "Q-100";

Statement vote = operations
        .withRouting(RoutingResolver.just(rootRouting))
        .get(voteId, Statement.class);
```

Nếu gọi:

```java
Statement vote = operations.get("V-201", Statement.class);
```

mà không cung cấp routing, request có thể tìm sai shard và không tìm thấy document.

### 9.1. Đọc parent và child

Đối với question `Q-100`, routing thường là `Q-100`:

```java
Statement question = operations
        .withRouting(RoutingResolver.just("Q-100"))
        .get("Q-100", Statement.class);
```

Đối với answer `A-101`, routing vẫn là `Q-100`:

```java
Statement answer = operations
        .withRouting(RoutingResolver.just("Q-100"))
        .get("A-101", Statement.class);
```

Đối với vote `V-201`, routing cũng là `Q-100`:

```java
Statement vote = operations
        .withRouting(RoutingResolver.just("Q-100"))
        .get("V-201", Statement.class);
```

Trong cây quan hệ, các document cùng root share cùng routing. Lưu lại root routing hoặc có cách xác định nó từ ID là một phần của thiết kế dữ liệu.

### 9.2. Xóa document theo ID

Xóa child cũng cần routing:

```java
operations
        .withRouting(RoutingResolver.just("Q-100"))
        .delete("V-201");
```

Nếu xóa theo entity, Spring Data có thể lấy routing từ entity metadata/property. Nếu xóa theo ID thuần, không có entity để suy ra route nên cần `RoutingResolver.just(...)` hoặc resolver phù hợp.

## 10. Cập nhật document cha-con

Khi cập nhật entity bằng `save`, phải giữ nguyên join relation và routing value:

```java
Statement answer = operations
        .withRouting(RoutingResolver.just("Q-100"))
        .get("A-101", Statement.class);

answer.setText("Updated answer text");
answer.setRouting("Q-100");

repository.save(answer);
```

Trong ví dụ thực tế, nếu repository sử dụng cùng mapping/routing configuration, có thể gọi save qua operations instance đã cấu hình resolver:

```java
statementOperations.save(answer);
```

Các nguyên tắc khi cập nhật:

- Không vô tình thay đổi `JoinField` từ child thành parent hoặc đổi parent ID.
- Không bỏ mất routing root khi chuyển entity qua DTO rồi dựng lại.
- Không thay đổi routing value tùy tiện giữa các lần cập nhật.
- Khi đổi routing key, cần coi đó là một thao tác di chuyển document giữa shard, không phải cập nhật field thông thường.

Nếu dùng `UpdateQuery` hoặc thao tác update theo ID, cần truyền routing vào request tương ứng. Tên method/builder có thể khác giữa các phiên bản Spring Data Elasticsearch; hãy kiểm tra API version của dự án và bảo đảm request update có cùng routing đã dùng khi index.

### 10.1. Đổi routing value không phải chỉ sửa property

Routing quyết định shard lưu document. Nếu đổi `routing` từ `Q-100` sang `Q-200`, chỉ ghi đè property trong `_source` không tự di chuyển document từ shard cũ sang shard mới.

Quy trình di chuyển thường cần:

1. Đọc document bằng routing cũ.
2. Index document vào cùng index với routing mới (và ID phù hợp).
3. Xác nhận document mới đã được ghi thành công.
4. Xóa bản cũ bằng ID và routing cũ.
5. Cập nhật tham chiếu/checkpoint liên quan.

Với parent-child, việc đổi root routing còn ảnh hưởng toàn bộ cây quan hệ. Phải di chuyển tất cả document liên quan theo cùng quy trình và giữ join parent IDs nhất quán. Không nên đổi routing root nếu không có kế hoạch migration toàn bộ cây.

## 11. Tìm kiếm parent-child bằng `has_child` và `has_parent`

Spring Data Elasticsearch hỗ trợ join mapping và lưu dữ liệu qua `JoinField`. Tuy nhiên, để truy vấn quan hệ, cần dùng native query thông qua `NativeQuery`/custom repository; query method thông thường không tự biểu diễn đầy đủ parent-child join.

Hai query quan trọng:

- `has_child`: trả về parent document nếu có child document khớp query.
- `has_parent`: trả về child document nếu parent document khớp query.

### 11.1. `has_child`

Ví dụ tìm question có ít nhất một answer chứa từ `sunny`:

```json
GET /statements/_search
{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "text": "sunny"
        }
      },
      "score_mode": "none"
    }
  }
}
```

Query chạy trên child type `answer`. Nếu có answer khớp, document cha tương ứng được trả về.

### 11.2. `has_parent`

Ví dụ tìm các answer thuộc question có trạng thái `OPEN`:

```json
GET /statements/_search
{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "term": {
          "status": "OPEN"
        }
      },
      "score": false
    }
  }
}
```

Query chạy trên parent type `question`. Nếu parent khớp điều kiện, child document tương ứng được trả về.

### 11.3. Dùng Java API Client DSL với `NativeQuery`

Trong Spring Data Elasticsearch 5.x+, có thể tạo native query bằng Elasticsearch Java API Client:

```java
import co.elastic.clients.elasticsearch._types.ChildScoreMode;
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query hasSunnyAnswer = Query.of(q -> q
        .hasChild(hc -> hc
                .type("answer")
                .query(childQuery -> childQuery
                        .match(m -> m
                                .field("text")
                                .query("sunny")
                        )
                )
                .scoreMode(ChildScoreMode.None)
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(hasSunnyAnswer)
        .build();

SearchHits<Statement> hits = operations.search(query, Statement.class);
```

`ChildScoreMode.None` có nghĩa score của child không được dùng để tính score parent. Có thể chọn các mode khác như `Avg`, `Max`, `Min` hoặc `Sum` tùy mục tiêu xếp hạng và API client version.

### 11.4. Tìm child theo điều kiện parent

Ví dụ:

```java
Query childrenOfOpenQuestions = Query.of(q -> q
        .hasParent(hp -> hp
                .parentType("question")
                .query(parentQuery -> parentQuery
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("OPEN"))
                        )
                )
                .score(false)
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(childrenOfOpenQuestions)
        .build();

SearchHits<Statement> answers = operations.search(query, Statement.class);
```

`has_parent` trả về child documents. Nếu cần truy vấn một child theo parent ID đã biết, có thể dùng `parent_id` query thay cho `has_parent`:

```json
GET /statements/_search
{
  "query": {
    "parent_id": {
      "type": "answer",
      "id": "Q-100"
    }
  }
}
```

`parent_id` hữu ích khi đã biết parent ID và muốn lấy các child thuộc type cụ thể.

## 12. Routing cho search parent-child

Khi search trên toàn index, Elasticsearch có thể gửi query đến nhiều shard. Nếu biết routing value, có thể giới hạn request vào shard tương ứng bằng routing parameter hoặc operations instance đã cấu hình routing.

Ví dụ tìm answer thuộc question `Q-100`:

```java
ElasticsearchOperations questionOperations =
        operations.withRouting(RoutingResolver.just("Q-100"));

SearchHits<Statement> answers = questionOperations.search(
        query,
        Statement.class
);
```

Routing giúp query chỉ nhắm đến shard có cây quan hệ đó, miễn là mọi document trong cây đã được index với cùng routing. Nếu route sai, query có thể không tìm thấy document dù điều kiện `has_child` hoặc `has_parent` đúng.

Nếu query cần tìm parent trên toàn bộ index mà không biết routing, không nên ép một routing value tùy ý. Khi đó để search trên các shard phù hợp; kết quả đúng phụ thuộc mapping và việc index child đã được route chính xác.

## 13. Lấy child document khớp bằng `inner_hits`

`has_child` thường trả parent document. Nếu giao diện cần hiển thị cả child document đã làm parent khớp, có thể cấu hình `inner_hits` trong query.

Ví dụ Query DSL:

```json
GET /statements/_search
{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "text": "sunny"
        }
      },
      "inner_hits": {
        "name": "matching_answers",
        "size": 5
      }
    }
  }
}
```

Response chứa parent hit và phần `inner_hits.matching_answers` gồm các child answer khớp query. `inner_hits` hữu ích khi cần hiển thị quan hệ trong một response, nhưng làm response lớn hơn và tăng chi phí xử lý. Hãy giới hạn số inner hit và chỉ bật khi use case cần.

## 14. Đọc, ghi và xóa qua Repository hay `ElasticsearchOperations`?

Repository phù hợp với CRUD cơ bản khi entity có routing rõ ràng và các method không cần tham số routing riêng. `ElasticsearchOperations` hữu ích khi cần kiểm soát routing, native query hoặc các thao tác chỉ có ID.

| Thao tác | Repository | `ElasticsearchOperations` |
|---|---|---|
| Lưu parent/child entity có routing metadata | `save(entity)` | `save(entity)` |
| Đọc theo ID có routing cố định | Method repository ID-only có thể không có tham số route. | `withRouting(RoutingResolver.just(route)).get(id, Type.class)` |
| Xóa theo entity | `delete(entity)` | `delete(entity)` |
| Xóa theo ID có routing | Không phải mọi repository method đều nhận route. | `withRouting(...).delete(id)` |
| Query `has_child`/`has_parent` | Cần custom repository implementation. | `NativeQuery` + `search(...)` |
| Tùy chỉnh resolver | Thường cấu hình qua custom operations hoặc luồng service. | `withRouting(resolver)` |

Với parent-child, nên đặt logic thao tác quan hệ trong một service hoặc custom repository để bảo đảm parent ID, root routing và join type luôn nhất quán.

## 15. Không có cascade delete/update như ORM

Join field chỉ lưu thông tin quan hệ. Elasticsearch không cung cấp foreign key constraint hoặc cascade delete theo kiểu JPA.

Ví dụ nếu xóa question `Q-100`, các answer và comment không tự động bị xóa như một cascade ORM. Ứng dụng cần thiết kế quy trình xóa:

1. Xác định root routing của cây.
2. Tìm hoặc xác định các child document liên quan.
3. Xóa các child theo routing đúng.
4. Xóa root parent.
5. Xác nhận không còn document mồ côi theo quy tắc nghiệp vụ.

Với cây nhiều cấp, cần xóa theo thứ tự hoặc dùng delete-by-query có filter phù hợp và routing chính xác. Nếu thao tác xóa có thể retry, hãy thiết kế idempotent để xóa lại không làm hỏng trạng thái.

Tương tự, cập nhật parent không tự cập nhật các child. Nếu child cần sao chép một số field của parent để search nhanh, ứng dụng phải tự cập nhật các bản sao đó hoặc chọn denormalization có chiến lược đồng bộ.

## 16. Những lỗi thường gặp với routing và parent-child

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lưu được nhưng `get(id)` trả `null`/404 | Document được index với routing nhưng get không truyền cùng routing. | Dùng `withRouting(RoutingResolver.just(value))` cho ID-only get. |
| Child không tìm thấy parent | Child được index với routing khác shard của parent. | Đảm bảo child dùng routing root parent. |
| Quan hệ một cấp hoạt động, quan hệ ba cấp lỗi | Routing mặc định từ parent trực tiếp của JoinField không phải root routing. | Gán routing của root ancestor cho descendant nhiều cấp. |
| `@Routing` không lấy được giá trị | Tên property trong annotation sai hoặc property chưa được gán. | Kiểm tra `@Routing("propertyName")` và entity value. |
| SpEL trả routing null | Bean name, method hoặc `#entity` expression sai. | Kiểm tra bean được đăng ký và method trả String/null. |
| Custom resolver hoạt động với save nhưng không với get theo ID | Resolver chỉ có logic `getRouting(bean)`, còn ID-only operation không có bean. | Cài đặt `getRouting()` phù hợp hoặc dùng `RoutingResolver.just(value)`. |
| Search join không trả kết quả | Sai join type, parent ID, index hoặc routing. | Kiểm tra mapping, JoinField, routing và Query DSL. |
| `has_child` trả nhiều parent hơn dự kiến | Child query quá rộng hoặc join type không đúng. | Kiểm tra child type và điều kiện query. |
| Parent bị xóa nhưng child còn tồn tại | Elasticsearch không tự cascade delete. | Xây dựng quy trình xóa toàn bộ cây. |
| Query parent-child chậm | Join query tốn chi phí, nhiều child hoặc shard phân phối không phù hợp. | Hạn chế join query, tối ưu routing hoặc cân nhắc denormalization/nested. |
| Một shard quá nóng | Routing key có cardinality thấp hoặc một tenant/parent có lượng document quá lớn. | Đánh giá phân phối routing và thiết kế shard/partition phù hợp. |
| Không thể đổi routing chỉ bằng update field | Routing quyết định shard, không chỉ là field trong `_source`. | Reindex document với routing mới rồi xóa bản cũ. |

## 17. Hiệu năng và giới hạn của parent-child

Parent-child giúp lưu parent và child độc lập, nhưng join query cần phối hợp dữ liệu trên shard và có thể tốn kém hơn truy vấn thông thường.

Một số nguyên tắc:

- Dùng parent-child khi child có vòng đời cập nhật độc lập hoặc số lượng child lớn khiến nested document không phù hợp.
- Giữ quan hệ trong cùng index và cùng shard.
- Chọn routing key có phân phối hợp lý để tránh một shard quá nóng.
- Không tạo quá nhiều tầng join nếu có thể lưu root ID trực tiếp trong document.
- Giới hạn `has_child`/`has_parent` query và đo hiệu năng bằng dữ liệu thực tế.
- Dùng `inner_hits` có giới hạn khi cần lấy child; tránh tải toàn bộ child không cần thiết.
- Cân nhắc lưu một số field cha vào child nếu query thường xuyên cần chúng và chi phí đồng bộ chấp nhận được.
- Nếu query chủ yếu đọc parent kèm danh sách child nhỏ, nested mapping hoặc denormalization có thể đơn giản hơn.

Elasticsearch cảnh báo `has_child` query có thể chậm và hiệu năng giảm khi số child khớp trỏ đến nhiều parent khác nhau. Không nên dùng join query như cách mặc định cho mọi màn hình danh sách.

### 17.1. Routing theo tenant có thể gây lệch shard

Nếu mọi document của một tenant đều dùng tenant ID làm routing, các document đó tập trung trên một shard. Điều này có thể giảm fan-out cho query tenant, nhưng tenant lớn có thể tạo hot shard.

Nếu một tenant có dữ liệu quá lớn, cần cân nhắc routing key kết hợp, partition theo tenant và loại dữ liệu, hoặc chiến lược index riêng. Không có routing key tốt cho mọi workload; phải đo phân bố document và query thực tế.

### 17.2. Routing không phải cơ chế bảo mật

Biết routing value không đồng nghĩa người dùng được phép đọc dữ liệu đó. Routing chỉ điều hướng request đến shard. Ứng dụng vẫn phải kiểm tra tenant/user authorization và cấu hình Elasticsearch security phù hợp.

## 18. Kiểm thử routing và join type

Nên kiểm thử trên Elasticsearch thật hoặc Testcontainers với mapping join đã tạo. Mock repository không thể xác nhận document có được ghi vào cùng shard hay join query có trả đúng parent/child.

Một kịch bản integration test:

1. Tạo index `statements` với join mapping.
2. Lưu question `Q-100`.
3. Lưu answer `A-101` với parent `Q-100`.
4. Lưu vote `V-201` với parent trực tiếp `A-101` nhưng routing root `Q-100`.
5. Refresh index.
6. Đọc từng document bằng ID cùng routing `Q-100`.
7. Thử đọc child không truyền routing và xác nhận không tìm thấy theo cách dự kiến của index.
8. Chạy `has_child` để tìm question có answer phù hợp.
9. Chạy `has_parent` để tìm child thuộc question thỏa điều kiện.
10. Xóa child theo routing và xác nhận document không còn.
11. Xóa root và kiểm tra quy trình dọn dẹp child riêng.

Các assertion nên kiểm tra cả:

- `_id` của parent/child.
- Giá trị `relation` và parent ID.
- Routing thực tế của document.
- Kết quả get/delete theo đúng route.
- Kết quả join query.
- Hành vi khi parent hoặc child bị thiếu.

Không dùng `Thread.sleep` để chờ document searchable. Trong test, refresh index rõ ràng sau khi index các document liên quan.

## 19. Quy trình thiết kế thao tác đọc ghi cha-con

1. **Xác định mô hình:** chọn loại parent/child và xác định root parent.
2. **Khai báo mapping:** dùng `@JoinTypeRelations` và một property `JoinField<ID>`.
3. **Khai báo routing:** chọn property qua `@Routing`, SpEL hoặc `RoutingResolver`.
4. **Tạo parent:** index root document và xác định ID/routing.
5. **Tạo child:** dùng `new JoinField<>(childType, parentId)` và routing của root parent.
6. **Tạo descendant:** nếu nhiều cấp, vẫn dùng routing của root ancestor, còn JoinField giữ parent trực tiếp.
7. **Đọc theo ID:** truyền đúng routing qua operations resolver khi không có entity.
8. **Cập nhật/xóa:** giữ route cũ và relation; nếu đổi route, thực hiện migration toàn cây.
9. **Truy vấn quan hệ:** dùng `has_child`, `has_parent` hoặc `parent_id` qua `NativeQuery`/custom repository.
10. **Kiểm thử:** xác nhận routing, join query, cleanup và hiệu năng trên Elasticsearch thật.

## 20. Những điểm cần nhớ

- Routing quyết định shard; `_id` định danh document; parent ID mô tả quan hệ join.
- Khi document được lưu với routing, get/delete theo ID cần cùng routing value.
- `@Routing` là annotation cấp class, chỉ định property hoặc SpEL expression dùng làm routing.
- `RoutingResolver` có `getRouting()` cho thao tác không có entity, `getRouting(bean)` cho entity và `just(value)` cho routing cố định.
- `operations.withRouting(resolver)` trả về một bản `ElasticsearchOperations` có routing tùy chỉnh.
- Parent-child dùng join field và các document riêng biệt trong cùng index.
- `JoinField<ID>` chứa relation name và parent ID; generic ID phải khớp kiểu `@Id`.
- `@JoinTypeRelations` khai báo các loại parent/child được phép.
- Parent và child phải nằm trên cùng shard; Spring Data tự suy ra parent routing cho quan hệ một cấp.
- Với quan hệ nhiều cấp, descendant phải route về root parent, trong khi `JoinField` vẫn giữ parent trực tiếp.
- `has_child` trả parent khi child khớp; `has_parent` trả child khi parent khớp; `parent_id` tìm child theo parent ID.
- Parent-child không có cascade delete/update; ứng dụng phải quản lý vòng đời toàn cây.
- Join query có chi phí; cân nhắc nested hoặc denormalization nếu workload phù hợp hơn.
- Routing không phải cơ chế authorization và routing key có thể gây hot shard nếu phân phối không đều.

`@Routing`, `RoutingResolver` và `JoinField` phối hợp để bảo đảm document cha-con được ghi vào đúng shard và có thể đọc lại bằng cùng routing value. Hãy tách bạch routing với parent ID, luôn giữ root routing cho quan hệ nhiều cấp, và xây dựng service chịu trách nhiệm nhất quán cho toàn bộ thao tác lưu, đọc, cập nhật, xóa và truy vấn quan hệ.

## Tài liệu tham khảo

- [Spring Data Elasticsearch — Join-Type implementation](https://docs.spring.io/spring-data/elasticsearch/docs/5.1.7/reference/html/#elasticsearch.join-types)
- [Spring Data Elasticsearch — Routing values](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/routing.html)
- [Spring Data Elasticsearch — `RoutingResolver` API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/routing/RoutingResolver.html)
- [Spring Data Elasticsearch — `JoinField` API](https://docs.spring.io/spring-data/elasticsearch/docs/5.1.x/api/org/springframework/data/elasticsearch/core/join/JoinField.html)
- [Elasticsearch — Parent-join field](https://www.elastic.co/guide/en/elasticsearch/reference/current/parent-join.html)
- [Elasticsearch — `has_child` query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-has-child-query.html)
- [Elasticsearch — `has_parent` query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-has-parent-query.html)
