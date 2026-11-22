# Xử lý định danh trùng hoặc tham chiếu chưa được giải quyết

## 1. Định danh đối tượng trong một đồ thị JSON

Một JSON object thông thường là cấu trúc cây: mỗi object hoặc array chứa các giá trị con. Nhưng mô hình Java trong ứng dụng có thể là **đồ thị đối tượng** (object graph), nơi nhiều thuộc tính cùng trỏ đến một object, hoặc các object tham chiếu vòng lẫn nhau.

Ví dụ, hai nhân viên có thể cùng tham chiếu đến một quản lý:

    Manager
      /   \
     v     v
    EmployeeA  EmployeeB

Nếu serialize theo cấu trúc lồng nhau đơn giản, Jackson có thể gặp cùng một object nhiều lần. Với quan hệ vòng như parent/child hoặc friend/friend, quá trình serialize có thể lặp vô hạn nếu không có cơ chế xử lý identity phù hợp.

Jackson hỗ trợ **object identity** bằng annotation JsonIdentityInfo. Cơ chế này gắn một ID vào object khi nó được ghi lần đầu. Khi cùng object được tham chiếu lần tiếp theo, Jackson có thể ghi ID thay vì ghi lại toàn bộ object. Khi deserialize, Jackson dùng ID để nối các tham chiếu về đúng một instance.

Ví dụ khái niệm:

    {
      "id": 1,
      "name": "Lan",
      "manager": {
        "id": 2,
        "name": "Minh"
      },
      "mentor": 2
    }

Trong ví dụ, object có ID 2 đã xuất hiện đầy đủ ở manager. Property mentor chỉ cần tham chiếu đến ID đó. Cấu trúc này biểu diễn quan hệ giữa các object mà không cần lặp lại toàn bộ dữ liệu.

Hai vấn đề cần xử lý riêng:

- **Định danh trùng:** hai object khác nhau lại khai báo cùng một ID trong cùng phạm vi identity.
- **Tham chiếu chưa được giải quyết:** JSON chứa một ID tham chiếu nhưng trong quá trình đọc không tìm thấy object tương ứng.

## 2. Khai báo identity bằng JsonIdentityInfo

Để Jackson quản lý identity, đặt JsonIdentityInfo trên kiểu object cần được tham chiếu:

~~~java
import com.fasterxml.jackson.annotation.JsonIdentityInfo;
import com.fasterxml.jackson.annotation.ObjectIdGenerators;

@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id"
)
public class GraphNode {
    private Long id;
    private String name;
    private GraphNode parent;

    public GraphNode() {
    }

    public GraphNode(Long id, String name) {
        this.id = id;
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public GraphNode getParent() {
        return parent;
    }

    public void setParent(GraphNode parent) {
        this.parent = parent;
    }
}
~~~

ObjectIdGenerators.PropertyGenerator yêu cầu Jackson lấy giá trị ID từ property đã chỉ định. Trong ví dụ, property id phải có giá trị phù hợp và duy nhất trong phạm vi identity của đồ thị.

Một số generator có sẵn:

| Generator | Cách tạo ID | Khi phù hợp |
|---|---|---|
| PropertyGenerator | Dùng một property sẵn có của object | Đối tượng có ID nghiệp vụ hoặc khóa chính |
| IntSequenceGenerator | Tạo dãy số nguyên trong quá trình serialize | Đồ thị chỉ cần ID tạm để nối tham chiếu trong một tài liệu |
| UUIDGenerator | Tạo UUID | Cần ID tổng quát, khó trùng trong phạm vi rộng |
| StringIdGenerator | Dùng chuỗi định danh theo cơ chế generator | Mô hình dùng ID dạng string |

Với PropertyGenerator, field ID phải được Jackson nhận diện khi serialize và deserialize. Nếu ID null, thiếu hoặc không ổn định, việc tạo tham chiếu sẽ không đáng tin cậy. Hãy kiểm tra rằng ID được gán trước khi serialize.

## 3. Cùng một object được tham chiếu nhiều lần

Ví dụ sau tạo hai node. Node alice trỏ đến bob, còn bob trỏ ngược lại alice:

~~~java
GraphNode alice = new GraphNode(1L, "Alice");
GraphNode bob = new GraphNode(2L, "Bob");

alice.setParent(bob);
bob.setParent(alice);
~~~

Đây là một đồ thị có chu trình. Nếu không có identity handling, Jackson có thể tiếp tục đi theo parent vô hạn. Với JsonIdentityInfo, object được ghi đầy đủ ở lần đầu; lần gặp lại cùng instance, Jackson ghi ID tham chiếu.

~~~java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(alice);
System.out.println(json);
~~~

Hình dạng JSON có thể tương tự:

~~~json
{
  "id": 1,
  "name": "Alice",
  "parent": {
    "id": 2,
    "name": "Bob",
    "parent": 1
  }
}
~~~

parent của Bob là số 1, trỏ lại Alice đã được khai báo. Jackson không cần mở rộng Alice thêm lần nữa.

Khi đọc lại:

~~~java
GraphNode restored = mapper.readValue(json, GraphNode.class);

System.out.println(restored.getName()); // Alice
System.out.println(restored.getParent().getName()); // Bob
System.out.println(
        restored == restored.getParent().getParent()
); // true
~~~

Phép so sánh identity cuối cùng kiểm tra tham chiếu Java. Kết quả true cho thấy tham chiếu vòng được nối về cùng instance restored, không phải một bản sao Alice khác có cùng dữ liệu.

## 4. Phân biệt cùng object với hai object có cùng ID

Đây là điểm quan trọng khi chẩn đoán identity:

- Cùng một instance Java xuất hiện ở nhiều vị trí trong đồ thị là trường hợp identity được thiết kế để xử lý.
- Hai instance Java khác nhau nhưng cùng có id = 7 là một xung đột định danh nếu chúng thuộc cùng phạm vi identity.

Ví dụ:

~~~java
GraphNode first = new GraphNode(7L, "First");
GraphNode second = new GraphNode(7L, "Second");

// Đây là hai object khác nhau:
System.out.println(first == second); // false
~~~

Cả hai object cùng khai báo ID 7. Với PropertyGenerator, ID này được dùng để phân giải tham chiếu. Khi deserialize, resolver mặc định không thể ánh xạ cùng một ID đến hai object khác nhau một cách không mơ hồ. SimpleObjectIdResolver phát hiện việc bind một ID đã được gắn với instance khác và báo lỗi.

Một payload minh họa xung đột:

~~~json
{
  "nodes": [
    {"id": 7, "name": "First"},
    {"id": 7, "name": "Second"}
  ]
}
~~~

Khi cả hai phần tử được đọc thành cùng một kiểu có JsonIdentityInfo, Jackson phải đăng ký hai object khác nhau với cùng object ID. Với resolver mặc định, thao tác bind thứ hai gây xung đột, thường xuất hiện dưới dạng lỗi mapping có nguyên nhân là IllegalStateException từ resolver.

Không nên xử lý lỗi này bằng cách tùy tiện chọn object đầu tiên hoặc object cuối cùng. Nếu hai object khác nhau cùng mang ID, mọi tham chiếu đến ID đó sẽ trở nên mơ hồ. Cần sửa dữ liệu nguồn hoặc định nghĩa một quy tắc identity hợp lệ.

## 5. Phạm vi duy nhất của ID: scope

JsonIdentityInfo có thuộc tính scope để xác định phạm vi của identity. ID không chỉ được xét như một con số đơn lẻ; Jackson xây dựng khóa identity dựa trên generator, scope và giá trị ID.

Ví dụ:

~~~java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id",
        scope = GraphNode.class
)
public class GraphNode {
    // ...
}
~~~

scope hữu ích khi các nhóm kiểu có không gian ID riêng. Tuy nhiên, scope không phải cách chữa dữ liệu trùng ID trong cùng một nhóm đối tượng. Nếu hai GraphNode trong cùng scope có cùng ID nhưng là hai thực thể khác nhau, xung đột vẫn tồn tại.

Khi thiết kế ID, cần xác định rõ:

- ID duy nhất trong một loại object, trong một tài liệu hay trên toàn hệ thống?
- Các subtype có dùng chung một namespace ID không?
- Hai nguồn dữ liệu có thể tạo ID trùng nhau không?
- ID có ổn định khi lưu và đọc lại ở các phiên bản khác nhau không?

Nếu ID chỉ duy nhất trong từng tenant hoặc từng loại node, có thể cần composite ID, resolver có namespace hoặc một mô hình dữ liệu thể hiện rõ phạm vi đó. Không nên giả định một số nguyên đơn lẻ là duy nhất toàn cục nếu hệ thống không bảo đảm điều đó.

## 6. Tham chiếu xuất hiện trước object được định nghĩa

Một tham chiếu có thể xuất hiện trong JSON trước khi object đầy đủ được đọc. Trường hợp này gọi là **forward reference**.

Ví dụ envelope có một property selected tham chiếu ID 2, trong khi object ID 2 chỉ được khai báo ở danh sách nodes phía sau:

~~~json
{
  "selected": 2,
  "nodes": [
    {"id": 1, "name": "A"},
    {"id": 2, "name": "B"}
  ]
}
~~~

Các lớp Java:

~~~java
public class GraphEnvelope {
    private GraphNode selected;
    private List<GraphNode> nodes;

    public GraphNode getSelected() {
        return selected;
    }

    public void setSelected(GraphNode selected) {
        this.selected = selected;
    }

    public List<GraphNode> getNodes() {
        return nodes;
    }

    public void setNodes(List<GraphNode> nodes) {
        this.nodes = nodes;
    }
}
~~~

Khi Jackson đọc selected: 2, object có ID 2 chưa được bind. Jackson có thể ghi nhận một forward reference đang chờ. Khi đọc đến phần tử có id 2, resolver đăng ký object và tham chiếu đang chờ được nối vào object đó.

~~~java
GraphEnvelope envelope = mapper.readValue(json, GraphEnvelope.class);

GraphNode selected = envelope.getSelected();
GraphNode nodeWithId2 = envelope.getNodes().get(1);

System.out.println(selected == nodeWithId2); // true
~~~

Điều này cho phép thứ tự property hoặc phần tử trong JSON không nhất thiết phải đặt object được định nghĩa trước mọi nơi tham chiếu đến nó.

## 7. Tham chiếu không bao giờ được giải quyết

Nếu JSON tham chiếu ID 99 nhưng không có object nào mang ID đó trong phạm vi resolver, Jackson không thể nối tham chiếu:

~~~json
{
  "selected": 99,
  "nodes": [
    {"id": 1, "name": "A"},
    {"id": 2, "name": "B"}
  ]
}
~~~

Với cấu hình mặc định thông thường, DeserializationFeature.FAIL_ON_UNRESOLVED_OBJECT_IDS được bật. Khi kết thúc quá trình đọc mà vẫn còn object reference chưa được giải quyết, Jackson báo UnresolvedForwardReference.

Ví dụ bắt lỗi:

~~~java
try {
    mapper.readValue(json, GraphEnvelope.class);
    throw new AssertionError("Expected an unresolved object reference");
} catch (UnresolvedForwardReference expected) {
    System.out.println("Reference target was not found");
}
~~~

Lỗi này khác với unknown property hoặc unknown type id:

| Loại lỗi | Ý nghĩa |
|---|---|
| UnrecognizedPropertyException | JSON có field mà kiểu Java không nhận diện |
| InvalidTypeIdException | Type discriminator không ánh xạ được đến subtype |
| UnresolvedForwardReference | JSON có object ID reference nhưng không tìm thấy object tương ứng |
| Xung đột bind object ID | Nhiều object khác nhau cùng được đăng ký dưới một ID trong cùng scope |

Khi gặp UnresolvedForwardReference, hãy kiểm tra ID tham chiếu có tồn tại không, kiểu dữ liệu của ID có khớp không, object định nghĩa có nằm trong cùng phạm vi identity không và property có đang được đọc bằng kiểu được cấu hình identity hay không.

## 8. Chính sách với tham chiếu chưa được giải quyết

Có thể tắt FAIL_ON_UNRESOLVED_OBJECT_IDS:

~~~java
ObjectMapper tolerantMapper = new ObjectMapper()
        .disable(
                DeserializationFeature.FAIL_ON_UNRESOLVED_OBJECT_IDS
        );
~~~

Khi tắt feature này, những tham chiếu không được giải quyết có thể bị bỏ qua và property tương ứng được đặt thành null. Đây là một chính sách tolerant, nhưng nó làm mất thông tin tham chiếu trong payload.

Chỉ nên dùng khi nghiệp vụ cho phép một liên kết không tồn tại được xem như không có liên kết. Ví dụ, một metadata tùy chọn có thể được bỏ qua nếu object đích đã bị xóa. Với quan hệ bắt buộc như chủ sở hữu giao dịch, tài khoản nguồn hoặc node cha cần thiết để bảo đảm toàn vẹn đồ thị, nên giữ chính sách strict và báo lỗi.

Tắt feature không tạo ra object còn thiếu và cũng không tự sửa ID sai. Nó chỉ thay đổi cách Jackson xử lý tham chiếu còn treo khi kết thúc quá trình deserialize.

## 9. ObjectIdResolver chịu trách nhiệm gì?

Jackson dùng ObjectIdResolver để quản lý việc liên kết object ID với object Java trong quá trình deserialization. Resolver hỗ trợ các thao tác chính:

- bindItem(id, object): đăng ký object với một identity key.
- resolveId(id): tìm object đã được đăng ký theo identity key.
- newForDeserialization(context): tạo resolver cho lần đọc dữ liệu.
- canUseFor(resolverType): xác định resolver hiện tại có thể được tái sử dụng cho loại resolver được yêu cầu hay không.

Resolver mặc định thường là SimpleObjectIdResolver. Nó giữ mapping trong bộ nhớ của lần deserialization. Khi một ID đã được gắn với một object, việc bind cùng ID cho một object khác sẽ gây xung đột thay vì âm thầm thay thế.

Có thể chỉ định resolver trong annotation:

~~~java
@JsonIdentityInfo(
        generator = ObjectIdGenerators.PropertyGenerator.class,
        property = "id",
        resolver = SimpleObjectIdResolver.class
)
public class GraphNode {
    // ...
}
~~~

Thông thường không cần khai báo resolver mặc định một cách tường minh. Thuộc tính resolver hữu ích khi ứng dụng có một chiến lược phân giải identity đặc biệt.

## 10. Khi nào cần resolver tùy chỉnh?

Một resolver tùy chỉnh có thể hữu ích nếu object ID phải được tra cứu từ một registry hoặc kho dữ liệu đã được kiểm soát, hoặc nếu hệ thống cần một namespace identity riêng. Tuy nhiên, resolver cần tuân thủ vòng đời deserialization và hợp đồng của Jackson.

Khung triển khai resolver cục bộ:

~~~java
import com.fasterxml.jackson.annotation.ObjectIdGenerator;
import com.fasterxml.jackson.annotation.ObjectIdResolver;

import java.util.HashMap;
import java.util.Map;

public class ApplicationObjectIdResolver implements ObjectIdResolver {
    private final Map<ObjectIdGenerator.IdKey, Object> items =
            new HashMap<>();

    @Override
    public void bindItem(
            ObjectIdGenerator.IdKey id,
            Object value
    ) {
        Object existing = items.get(id);
        if (existing != null && existing != value) {
            throw new IllegalStateException(
                    "Duplicate object identity: " + id.key
            );
        }
        items.put(id, value);
    }

    @Override
    public Object resolveId(ObjectIdGenerator.IdKey id) {
        return items.get(id);
    }

    @Override
    public ObjectIdResolver newForDeserialization(Object context) {
        return new ApplicationObjectIdResolver();
    }

    @Override
    public boolean canUseFor(ObjectIdResolver resolverType) {
        return resolverType != null
                && resolverType.getClass() == getClass();
    }
}
~~~

Đây là khung minh họa resolver cục bộ, không phải một registry toàn cục. Trong ứng dụng thực tế, cần điều chỉnh chữ ký theo phiên bản Jackson đang dùng và cân nhắc thread safety, phạm vi tenant, vòng đời context và cách xử lý ID không tồn tại. Không nên giữ một map mutable dùng chung giữa nhiều lần deserialize nếu chưa thiết kế đồng bộ và cách ly dữ liệu rõ ràng.

Resolver tùy chỉnh cũng không nên tự động bỏ qua duplicate ID. Nếu cùng một ID được gắn cho hai object khác nhau, hãy xác định đó là lỗi dữ liệu hay một quy tắc hợp nhất có chủ ý. Nếu có quy tắc hợp nhất, nó phải được định nghĩa rõ và bảo đảm mọi reference đều trỏ đến cùng một thực thể có ý nghĩa.

## 11. Dùng JsonIdentityReference(alwaysAsId = true)

JsonIdentityInfo cho phép Jackson ghi object đầy đủ lần đầu rồi dùng ID ở những lần tham chiếu sau. Nếu một property luôn chỉ nên xuất ID, có thể dùng JsonIdentityReference(alwaysAsId = true):

~~~java
public class GraphEnvelope {
    @JsonIdentityReference(alwaysAsId = true)
    private GraphNode selected;

    private List<GraphNode> nodes;

    // getters/setters
}
~~~

Khi serialize, selected có thể được ghi dưới dạng số ID thay vì một object lồng nhau. Danh sách nodes cần chứa các object đầy đủ để consumer có thể phân giải ID.

Ví dụ hình dạng:

~~~json
{
  "selected": 2,
  "nodes": [
    {"id": 1, "name": "A"},
    {"id": 2, "name": "B"}
  ]
}
~~~

Nếu payload chỉ có selected: 2 mà không có object ID 2 ở nơi khác, consumer cần một resolver có thể tìm được object đó; nếu không, tham chiếu sẽ chưa được giải quyết. alwaysAsId không tự tạo dữ liệu đích.

## 12. Phân biệt object identity với managed/back references

Jackson còn có JsonManagedReference và JsonBackReference để xử lý một số quan hệ hai chiều, thường là parent/child:

- JsonManagedReference đánh dấu chiều được serialize bình thường.
- JsonBackReference đánh dấu chiều ngược lại, thường bị bỏ khỏi JSON và được khôi phục khi deserialize.

Cách này phù hợp khi quan hệ có một chiều chính và một chiều ngược chỉ dùng để điều hướng trong mô hình Java.

JsonIdentityInfo giải quyết bài toán rộng hơn: biểu diễn object identity bằng ID để nhiều nhánh có thể tham chiếu cùng một object và có thể tạo đồ thị có chu trình.

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Parent có danh sách child, child có back-reference về parent | Managed/back references |
| Nhiều property cùng trỏ đến một object dùng chung | Object identity |
| Đồ thị có chu trình và cần giữ cùng instance sau deserialize | Object identity |
| Payload cần tham chiếu object bằng ID tường minh | Object identity |

Không nên gắn cả hai cơ chế lên cùng một quan hệ mà không hiểu thứ tự và ý nghĩa của từng annotation. Hãy chọn mô hình biểu diễn phù hợp với hợp đồng JSON.

## 13. Kiểm thử định danh trùng và tham chiếu chưa giải quyết

Một bộ test cho object graph nên kiểm tra cả trường hợp hợp lệ và lỗi dữ liệu:

| Ca kiểm thử | Input | Kết quả mong đợi |
|---|---|---|
| T01 — Shared reference | Hai property tham chiếu cùng một ID/object | Sau deserialize, hai property trỏ đến cùng instance |
| T02 — Circular reference | A tham chiếu B, B tham chiếu A | Đọc được đồ thị và không lặp vô hạn |
| T03 — Forward reference | ID được tham chiếu xuất hiện trước object đầy đủ | Tham chiếu được nối khi object được đăng ký sau đó |
| T04 — Missing target | ID được tham chiếu không xuất hiện ở đâu | UnresolvedForwardReference với strict setting |
| T05 — Tolerant unresolved | Tắt FAIL_ON_UNRESOLVED_OBJECT_IDS | Tham chiếu chưa giải quyết được xử lý theo chính sách tolerant, thường thành null |
| T06 — Duplicate identity | Hai object khác nhau cùng ID trong cùng scope | Resolver mặc định báo xung đột |
| T07 — Null identity | Object dùng property ID nhưng ID không có giá trị hợp lệ | Bị phát hiện qua validation hoặc lỗi identity theo ngữ cảnh |

Ví dụ test cho tham chiếu chưa giải quyết:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.deser.UnresolvedForwardReference;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ObjectIdentityTest {
    private final ObjectMapper strictMapper = new ObjectMapper();

    @Test
    void rejectsReferenceWhoseTargetDoesNotExist() {
        String json = """
                {
                  "selected": 99,
                  "nodes": [
                    {"id": 1, "name": "A"}
                  ]
                }
                """;

        assertThrows(
                UnresolvedForwardReference.class,
                () -> strictMapper.readValue(json, GraphEnvelope.class)
        );
    }

    @Test
    void canApplyTolerantPolicyForUnresolvedReference() throws Exception {
        ObjectMapper tolerantMapper = new ObjectMapper()
                .disable(
                        DeserializationFeature.FAIL_ON_UNRESOLVED_OBJECT_IDS
                );

        String json = """
                {
                  "selected": 99,
                  "nodes": [
                    {"id": 1, "name": "A"}
                  ]
                }
                """;

        GraphEnvelope result = tolerantMapper.readValue(
                json,
                GraphEnvelope.class
        );

        assertNull(result.getSelected());
    }
}
~~~

Tùy cách property được khai báo và phiên bản Jackson, ngoại lệ có thể được bọc trong lỗi mapping ở ranh giới gọi. Khi kiểm thử, nên xác nhận loại lỗi gốc hoặc nguyên nhân tương ứng nếu framework bao ngoại lệ.

## 14. Kiểm tra ID trước khi serialize

Với ID lấy từ property, nên kiểm tra tính duy nhất trước khi tạo JSON. Một cách đơn giản là duyệt đồ thị và phát hiện hai instance khác nhau cùng ID:

~~~java
Map<Long, GraphNode> byId = new HashMap<>();

for (GraphNode node : allNodes) {
    GraphNode previous = byId.putIfAbsent(node.getId(), node);
    if (previous != null && previous != node) {
        throw new IllegalArgumentException(
                "Duplicate GraphNode id: " + node.getId()
        );
    }
}
~~~

Đoạn mã trên giả định allNodes đã là danh sách các node cần kiểm tra và ID không null. Với đồ thị có thể có chu trình, quá trình thu thập node cần dùng một tập identity-based để tránh duyệt vô hạn. Có thể dùng IdentityHashMap hoặc một set dựa trên identity thay vì equals, vì hai node có thể được coi là bằng nhau theo business fields nhưng vẫn là hai instance khác nhau.

Nếu ID được tạo tự động, cần bảo đảm generator không cấp trùng trong phạm vi được chọn. Nếu ID là khóa database, hãy kiểm tra tính duy nhất ở tầng lưu trữ và bảo đảm object graph không chứa bản sao mâu thuẫn của cùng khóa.

## 15. Lưu ý khi xử lý dữ liệu không đáng tin cậy

Object identity ảnh hưởng đến cách Jackson liên kết các object trong bộ nhớ. Dữ liệu đầu vào có thể cố tình tạo:

- ID trùng để gây xung đột hoặc làm sai quan hệ.
- Tham chiếu tới ID không tồn tại để làm quá trình đọc thất bại.
- Đồ thị có độ sâu hoặc số lượng node rất lớn để tiêu tốn CPU và heap.
- Nhiều tham chiếu chéo khiến cấu trúc khó kiểm tra.

Để kiểm soát:

- Đặt giới hạn kích thước body, độ sâu lồng nhau và độ dài token bằng cấu hình parser phù hợp.
- Giới hạn số node và số quan hệ mà nghiệp vụ cho phép.
- Kiểm tra ID null, ID trùng và reference thiếu ở ranh giới đầu vào.
- Không tắt FAIL_ON_UNRESOLVED_OBJECT_IDS chỉ để tránh lỗi nếu quan hệ là bắt buộc.
- Không dùng resolver toàn cục dùng chung giữa request nếu chưa có cách ly tenant, đồng bộ và quản lý vòng đời.
- Chỉ cho phép các kiểu và quan hệ đã được mô hình hóa trong hợp đồng.

Một payload deserialize thành công vẫn cần validation nghiệp vụ. Jackson chỉ bảo đảm mapping theo cấu hình; nó không chứng minh đồ thị có ý nghĩa hoặc người gửi được phép tạo các quan hệ đó.

## 16. Quy trình chẩn đoán lỗi identity

Khi gặp lỗi trong quá trình serialize hoặc deserialize, có thể lần lượt kiểm tra:

1. Kiểu đích đã được gắn JsonIdentityInfo chưa?
2. Generator có đúng với mô hình ID không? Nếu dùng PropertyGenerator, property ID có được nhận diện và có giá trị chưa?
3. ID có duy nhất trong cùng generator và scope không?
4. Hai vị trí tham chiếu có thật sự cùng trỏ đến một instance hay là hai instance khác nhau cùng ID?
5. JSON có object định nghĩa ID được tham chiếu không?
6. Object định nghĩa có xuất hiện sau reference (forward reference) hay hoàn toàn không có?
7. FAIL_ON_UNRESOLVED_OBJECT_IDS đang bật hay tắt?
8. Có resolver tùy chỉnh nào thay đổi quy tắc bind/resolve hoặc phạm vi identity không?
9. Quan hệ có thực sự cần object identity, hay managed/back references đã đủ?

Hãy giữ một JSON fixture tối thiểu tái hiện lỗi và một test cho từng trường hợp. Cách này giúp phân biệt duplicate ID với unresolved reference, vốn có cách khắc phục khác nhau.

## 17. Kết luận

JsonIdentityInfo cho phép Jackson biểu diễn object graph bằng ID: object được ghi đầy đủ lần đầu, các lần tham chiếu sau có thể chỉ ghi ID và khi deserialize các reference được nối về cùng instance. Với PropertyGenerator, ID phải ổn định và duy nhất trong phạm vi identity. Hai object khác nhau cùng ID gây xung đột resolver; một ID tham chiếu không có object tương ứng tạo ra unresolved forward reference. FAIL_ON_UNRESOLVED_OBJECT_IDS mặc định giúp phát hiện tham chiếu thiếu; tắt nó có thể khiến reference không giải quyết được trở thành null và chỉ phù hợp khi nghiệp vụ cho phép. Hãy kiểm tra ID trước khi serialize, kiểm thử shared/circular/forward references và chọn resolver hoặc managed/back references theo đúng cấu trúc đồ thị.
