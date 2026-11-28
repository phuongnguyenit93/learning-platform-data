# Gom dữ liệu nhiều tầng tại cơ sở dữ liệu hoặc phía ứng dụng

Khi đọc một nhánh đồ thị nhiều tầng, ứng dụng thường cần trả về một cấu trúc lồng nhau thay vì một danh sách các node và relationship rời rạc. Ví dụ, màn hình chi tiết khách hàng cần hiển thị khách hàng, các đơn hàng của họ và từng sản phẩm trong mỗi đơn. Spring Data Neo4j (SDN) có thể ánh xạ object graph từ kết quả Cypher, nhưng cách tổ chức các record trả về quyết định việc ánh xạ có chính xác và hiệu quả hay không.

Có hai hướng gom dữ liệu chính. **Gom ở cơ sở dữ liệu** dùng Cypher như **collect()**, **COLLECT {}** và **reduce()** để tạo cấu trúc kết quả đã được nhóm trước khi truyền qua mạng. **Gom ở phía ứng dụng** trả về các nhóm node, relationship hoặc các dòng dữ liệu phẳng rồi kết hợp chúng trong tầng mapping/service. SDN cũng hỗ trợ một kiểu gom ở phía client: trả về danh sách lồng nhau của node và relationship để bộ ánh xạ của SDN làm phẳng chúng khi dựng entity graph.

Sau bài học, bạn có thể:

- Giải thích vì sao truy vấn custom của SDN cần một record cho mỗi root entity khi ánh xạ object graph.
- Gom relationship và node bằng **collect()** để ánh xạ một tầng liên kết.
- Gom nhiều tầng bằng **reduce()** ở Cypher hoặc bằng danh sách lồng nhau ở phía client.
- Dùng map projection và **COLLECT {}** để tạo DTO lồng nhau cho API.
- Chọn **Neo4jClient**, DTO projection hoặc entity mapping theo hình dạng kết quả cần trả về.
- Tránh tích Descartes, dữ liệu trùng, truy vấn N+1 và sử dụng bộ nhớ quá mức khi gom dữ liệu.

## 1. Bài toán: từ đồ thị nhiều tầng đến kết quả lồng nhau

Giả sử ứng dụng bán hàng có mô hình:

~~~mermaid
flowchart TD
    C["Customer"]
    O1["Order A"]
    O2["Order B"]
    P1["Product: Keyboard"]
    P2["Product: Mouse"]
    P3["Product: Monitor"]
    C -->|PLACED| O1
    C -->|PLACED| O2
    O1 -->|CONTAINS, quantity=1| P1
    O1 -->|CONTAINS, quantity=2| P2
    O2 -->|CONTAINS, quantity=1| P3
~~~

Màn hình chi tiết khách hàng có thể cần cấu trúc như sau:

~~~json
{
  "customerCode": "C-100",
  "name": "An",
  "orders": [
    {
      "orderCode": "O-100",
      "items": [
        {"sku": "KB-01", "name": "Keyboard", "quantity": 1},
        {"sku": "MS-01", "name": "Mouse", "quantity": 2}
      ]
    },
    {
      "orderCode": "O-101",
      "items": [
        {"sku": "MN-01", "name": "Monitor", "quantity": 1}
      ]
    }
  ]
}
~~~

Đây là dữ liệu có ba tầng: khách hàng, đơn hàng và dòng sản phẩm. Một truy vấn Cypher nối cả ba loại node sẽ tạo nhiều record, mỗi record đại diện cho một đường đi từ khách hàng đến một sản phẩm. Nếu trả về root node lặp lại trong nhiều record, SDN có thể gặp khó khăn khi hợp nhất object graph. Vì vậy, cần xác định rõ nơi gom dữ liệu trước khi viết truy vấn.

## 2. Quy tắc record khi ánh xạ entity bằng SDN

SDN xử lý kết quả custom query theo record. Khi một phương thức repository trả về entity gốc, kết quả nên có **một record cho mỗi root entity**. Những node và relationship liên quan của root cần được gom vào các cột collection trong cùng record để SDN có đủ dữ liệu dựng object graph.

Ví dụ, tìm một bộ phim cùng dàn diễn viên:

~~~cypher
MATCH (m:Movie {title: $title})<-[r:ACTED_IN]-(p:Person)
RETURN m,
       collect(r) AS actingRelationships,
       collect(p) AS actors
~~~

Truy vấn trả về một record cho bộ phim, trong đó:

- **m** là root node.
- **actingRelationships** chứa các relationship **ACTED_IN**.
- **actors** chứa các node **Person** liên quan.

Nếu trả về trực tiếp **m, r, p**, mỗi diễn viên tạo một record. Khi SDN ánh xạ danh sách kết quả, cùng một bộ phim xuất hiện lặp lại trong nhiều record và các relationship có thể không được hợp nhất theo cách ứng dụng mong muốn. Gom các relationship và node trước khi trả về giúp SDN dựng một root entity cùng các liên kết của nó.

### Cẩn thận với tích Descartes

Một lỗi phổ biến là nối nhiều nhánh độc lập trong cùng một truy vấn:

~~~cypher
MATCH (m:Movie {title: $title})<-[acted:ACTED_IN]-(actor:Person)
OPTIONAL MATCH (m)<-[rating:RATED]-(viewer:Person)
RETURN m,
       collect(acted) AS actingRelationships,
       collect(actor) AS actors,
       collect(rating) AS ratings,
       collect(viewer) AS viewers
~~~

Nếu một bộ phim có 5 diễn viên và 100 lượt đánh giá, phép nối có thể tạo ra khoảng 500 dòng trung gian trước khi gom. Vì vậy, cùng một diễn viên và relationship có thể lặp lại nhiều lần trong các collection. **collect(DISTINCT ...)** có thể loại bỏ phần tử trùng trong kết quả, nhưng không nhất thiết loại bỏ chi phí tạo ra tích Descartes.

Khi các nhánh không phụ thuộc lẫn nhau, hãy gom từng nhánh bằng subquery hoặc pattern riêng rồi kết hợp kết quả. Ví dụ với Neo4j hỗ trợ **COLLECT {}**:

~~~cypher
MATCH (m:Movie {title: $title})
RETURN m,
       COLLECT {
           MATCH (m)<-[r:ACTED_IN]-(actor:Person)
           RETURN r
       } AS actingRelationships,
       COLLECT {
           MATCH (m)<-[r:ACTED_IN]-(actor:Person)
           RETURN actor
       } AS actors,
       COLLECT {
           MATCH (m)<-[r:RATED]-(viewer:Person)
           RETURN r
       } AS ratingRelationships,
       COLLECT {
           MATCH (m)<-[r:RATED]-(viewer:Person)
           RETURN viewer
       } AS viewers
~~~

Mỗi subquery chỉ xử lý một nhánh, tránh nhân số dòng giữa dàn diễn viên và lượt đánh giá. **COLLECT {}** được giới thiệu từ Neo4j 5.6; nếu hệ thống chạy phiên bản cũ hơn, hãy dùng các subquery hoặc mẫu **OPTIONAL MATCH** và **WITH** tương thích với phiên bản đó.

## 3. Gom nhiều tầng tại cơ sở dữ liệu bằng reduce()

Khi cần ánh xạ một đồ thị sâu hơn, có thể tìm tất cả các path bắt đầu từ root, sau đó trích xuất node và relationship từ các path. Tuy nhiên, chỉ trả về path chưa đủ vì SDN không ánh xạ trực tiếp kiểu Path thành entity graph. Kết quả cần chứa node và relationship thực tế.

Ví dụ, lấy một bộ phim, các diễn viên của phim và những bộ phim khác mà họ tham gia:

~~~cypher
MATCH path =
    (root:Movie {title: $title})
    <-[:ACTED_IN]-(person:Person)
    -[:ACTED_IN]->(otherMovie:Movie)
WITH root, collect(path) AS paths
WITH root,
     reduce(
         allNodes = [],
         path IN paths |
         allNodes + nodes(path)
     ) AS flattenedNodes,
     reduce(
         allRelationships = [],
         path IN paths |
         allRelationships + relationships(path)
     ) AS flattenedRelationships
WITH root,
     reduce(
         uniqueNodes = [],
         node IN flattenedNodes |
         CASE
             WHEN node IN uniqueNodes THEN uniqueNodes
             ELSE uniqueNodes + node
         END
     ) AS uniqueNodes,
     reduce(
         uniqueRelationships = [],
         relationship IN flattenedRelationships |
         CASE
             WHEN relationship IN uniqueRelationships
                 THEN uniqueRelationships
             ELSE uniqueRelationships + relationship
         END
     ) AS uniqueRelationships
RETURN root, uniqueNodes, uniqueRelationships
~~~

Truy vấn thực hiện các bước:

1. Tìm tất cả path đi từ bộ phim gốc qua diễn viên đến phim khác.
2. Gom các path theo root bằng **collect(path)**.
3. Dùng **nodes(path)** và **relationships(path)** để lấy thành phần của từng path.
4. Làm phẳng các danh sách lồng nhau bằng **reduce()**.
5. Loại bỏ node và relationship trùng, sau đó trả về một record cho root.

Kết quả gồm root node, danh sách node và danh sách relationship. SDN có thể dùng các thành phần này để dựng object graph nhiều tầng, miễn là entity mapping mô tả đúng các label và relationship type liên quan.

**reduce()** chạy ở phía Neo4j. Cơ sở dữ liệu cần giữ các path và danh sách trung gian trong bộ nhớ để gom chúng. Với nhánh đồ thị lớn hoặc có nhiều path trùng lặp, chi phí này có thể tăng đáng kể. Hãy giới hạn độ sâu, lọc root trước khi mở rộng graph và kiểm tra kế hoạch truy vấn bằng **PROFILE**.

Ví dụ trên dùng **MATCH path**, vì vậy root không có nhánh phù hợp sẽ không xuất hiện trong kết quả. Nếu vẫn cần trả về root không có quan hệ con, hãy bắt đầu bằng **MATCH** root rồi dùng **OPTIONAL MATCH path = ...**. Khi đó **collect(path)** tạo danh sách rỗng nếu không có path; các bước **reduce()** tiếp theo cần giữ được trường hợp danh sách rỗng.

## 4. Gom danh sách lồng nhau ở phía client để SDN làm phẳng

Nếu không muốn làm phẳng và loại trùng bằng **reduce()** trong Cypher, SDN cho phép trả về các danh sách lồng nhau của node và relationship. Bộ ánh xạ của SDN sẽ chuyển các danh sách này thành danh sách phẳng khi dựng entity graph.

Dùng lại ví dụ bộ phim và các path:

~~~cypher
MATCH path =
    (root:Movie {title: $title})
    <-[:ACTED_IN]-(person:Person)
    -[:ACTED_IN]->(otherMovie:Movie)
RETURN root,
       collect(nodes(path)) AS nodePaths,
       collect(relationships(path)) AS relationshipPaths
~~~

Hai collection có thể có cấu trúc như:

~~~text
nodePaths:
[
  [movieA, personA, movieB],
  [movieA, personA, movieC],
  [movieA, personB, movieD]
]

relationshipPaths:
[
  [actedInA, actedInB],
  [actedInA, actedInC],
  [actedInD, actedInE]
]
~~~

SDN nhận các danh sách lồng nhau này và làm phẳng chúng trong quá trình mapping. Ứng dụng không cần viết vòng lặp để nối lại các node và relationship nếu mục tiêu là dựng entity graph theo mapping đã khai báo.

Hướng này chuyển một phần công việc gom dữ liệu sang phía client. Nó tránh phải viết biểu thức **reduce()** dài trong Cypher, nhưng các danh sách lồng nhau vẫn được truyền qua Bolt và chiếm bộ nhớ ở phía ứng dụng. Record trả về vẫn phải chứa đầy đủ node và relationship cần thiết để hydrate entity.

### So sánh hai cách gom graph cho SDN

| Tiêu chí | Gom ở database bằng reduce | Gom ở client bằng danh sách lồng nhau |
|---|---|---|
| Cách làm phẳng | Cypher dùng **reduce()** và loại phần tử trùng | SDN làm phẳng danh sách node/relationship trong mapping |
| Độ phức tạp Cypher | Cao hơn | Đơn giản hơn |
| Bộ nhớ database | Cần giữ path và danh sách trung gian | Ít công việc reduce hơn |
| Bộ nhớ client | Nhận danh sách phẳng | Nhận các danh sách lồng nhau rồi làm phẳng |
| Phù hợp khi | Cần kiểm soát chính xác tập node/relationship trả về | Muốn để SDN xử lý việc làm phẳng object graph |

Không có một lựa chọn luôn nhanh hơn. Quyết định phụ thuộc vào số lượng path, số node/relationship trùng lặp và giới hạn bộ nhớ của Neo4j server cũng như ứng dụng.

## 5. Tạo cấu trúc DTO lồng nhau ngay trong Cypher

Không phải kết quả nào cũng cần được ánh xạ thành entity graph. Với màn hình đọc hoặc API, đôi khi chỉ cần một cấu trúc DTO lồng nhau. Cypher hỗ trợ **map projection** để tạo map từ node, đồng thời bổ sung các trường tính toán hoặc collection.

Ví dụ gom khách hàng, đơn hàng và các dòng sản phẩm:

~~~cypher
MATCH (c:Customer {customerCode: $customerCode})
RETURN c {
    .customerCode,
    .name,
    orders: COLLECT {
        MATCH (c)-[:PLACED]->(o:Order)
        RETURN o {
            .orderCode,
            .placedAt,
            items: COLLECT {
                MATCH (o)-[r:CONTAINS]->(p:Product)
                RETURN p {
                    .sku,
                    .name,
                    quantity: r.quantity
                }
                ORDER BY p.sku
            }
        }
        ORDER BY o.placedAt DESC
    }
} AS customer
~~~

Mỗi cấp được gom riêng:

- Truy vấn ngoài trả về một map khách hàng.
- **COLLECT {}** thứ nhất trả về danh sách đơn hàng của khách hàng.
- **COLLECT {}** bên trong trả về danh sách sản phẩm của từng đơn.
- Map projection chọn đúng các property cần gửi cho client.

Nếu khách hàng chưa có đơn hàng, collection **orders** là danh sách rỗng. Nếu một đơn chưa có dòng sản phẩm, **items** cũng là danh sách rỗng. Điều này giúp API có cấu trúc ổn định và không phải xử lý một chuỗi giá trị null do **OPTIONAL MATCH**.

**COLLECT {}** phải có **RETURN** cuối cùng và chỉ trả về đúng một cột. Khác với hàm tổng hợp **collect()**, subquery **COLLECT {}** không tự loại bỏ giá trị null; nếu có thể sinh null, hãy lọc rõ bằng **WHERE**.

### Dùng multi-level projection khi kết quả vẫn là entity graph

Nếu cấu trúc lồng nhau phản ánh trực tiếp các property và relationship đã khai báo trên entity, có thể dùng interface projection nhiều tầng:

~~~java
import java.util.List;

public interface CustomerSummary {

    String getCustomerCode();

    String getName();

    List<OrderSummary> getOrders();

    interface OrderSummary {
        String getOrderCode();
        List<ItemSummary> getItems();
    }

    interface ItemSummary {
        Integer getQuantity();
        ProductSummary getProduct();
    }

    interface ProductSummary {
        String getSku();
        String getName();
    }
}
~~~

Các accessor phải tương ứng với property của entity và relationship trong domain model. SDN tạo projection proxy nhiều tầng và chỉ truy vấn các thuộc tính cần thiết cho projection. Projection có thể tránh đi theo chu trình của graph, nên kết quả được dựng thành cấu trúc không chu trình. Các lớp **@RelationshipProperties** cũng được tính là một tầng trong projection.

Interface projection phù hợp khi muốn đọc một phần của mô hình miền. Nếu kết quả cần thêm phép tính hoặc map tùy chỉnh không tồn tại trong entity, hãy cân nhắc custom query cùng DTO hoặc **Neo4jClient**.

### Đọc map lồng nhau bằng Neo4jClient

Với kết quả map tùy chỉnh, có thể dùng **Neo4jClient** để nhận record dưới dạng map rồi chuyển thành DTO:

~~~java
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerReadRepository {

    private final Neo4jClient neo4jClient;

    public CustomerReadRepository(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Map<String, Object> findCustomerView(String customerCode) {
        return neo4jClient.query("""
            MATCH (c:Customer {customerCode: $customerCode})
            RETURN c {
                .customerCode,
                .name,
                orders: COLLECT {
                    MATCH (c)-[:PLACED]->(o:Order)
                    RETURN o {
                        .orderCode,
                        .placedAt,
                        items: COLLECT {
                            MATCH (o)-[r:CONTAINS]->(p:Product)
                            RETURN p {
                                .sku,
                                .name,
                                quantity: r.quantity
                            }
                        }
                    }
                }
            } AS customer
            """)
            .bind(customerCode).to("customerCode")
            .fetch()
            .one()
            .orElseThrow();
    }
}
~~~

**fetch().one()** trả về một record dưới dạng **Map<String, Object>**. Trường **customer** là map lồng nhau; các trường **orders** và **items** là collection. Tầng service có thể chuyển cấu trúc này thành record/DTO cụ thể hoặc trả về một view model đã được kiểm soát.

Nếu muốn tự chuyển từng record thành kiểu Java, **Neo4jClient** cung cấp **fetchAs(Target.class).mappedBy(...)**. Hàm mapping nhận **TypeSystem** và **Record**, nhờ đó có thể đọc các map/list lồng nhau hoặc dùng mapping function có sẵn trong **Neo4jMappingContext** cho các node entity đã được khai báo.

Lưu ý: DTO projection của SDN hỗ trợ các property đơn giản, entity đã biết và collection của chúng; map không phải kiểu property được hỗ trợ trong cơ chế DTO projection đó. Khi kết quả Cypher chứa map tùy ý như ví dụ trên, dùng **Neo4jClient** với map hoặc mapping function riêng sẽ rõ ràng hơn.

## 6. Gom dữ liệu ở Java từ các record phẳng

Một lựa chọn khác là để Cypher trả về từng dòng dữ liệu phẳng, sau đó nhóm chúng trong Java. Cách này hữu ích khi phép biến đổi có nhiều quy tắc nghiệp vụ, cần kiểm tra dữ liệu hoặc tạo view model không trùng với entity graph.

Truy vấn trả về một dòng cho mỗi sản phẩm trong đơn hàng:

~~~cypher
MATCH (c:Customer {customerCode: $customerCode})
      -[:PLACED]->(o:Order)
OPTIONAL MATCH (o)-[r:CONTAINS]->(p:Product)
RETURN o.orderCode AS orderCode,
       o.placedAt AS placedAt,
       p.sku AS sku,
       p.name AS productName,
       r.quantity AS quantity
ORDER BY o.placedAt DESC, p.sku
~~~

DTO đại diện cho một dòng:

~~~java
import java.time.LocalDateTime;

public record OrderLineRow(
    String orderCode,
    LocalDateTime placedAt,
    String sku,
    String productName,
    Long quantity
) {
}
~~~

Dùng **Neo4jClient** để ánh xạ record:

~~~java
import java.util.List;

import org.springframework.data.neo4j.core.Neo4jClient;

public class OrderLineReader {

    private final Neo4jClient neo4jClient;

    public OrderLineReader(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public List<OrderLineRow> findOrderLines(String customerCode) {
        return neo4jClient.query("""
            MATCH (c:Customer {customerCode: $customerCode})
                  -[:PLACED]->(o:Order)
            OPTIONAL MATCH (o)-[r:CONTAINS]->(p:Product)
            RETURN o.orderCode AS orderCode,
                   o.placedAt AS placedAt,
                   p.sku AS sku,
                   p.name AS productName,
                   r.quantity AS quantity
            ORDER BY o.placedAt DESC, p.sku
            """)
            .bind(customerCode).to("customerCode")
            .fetchAs(OrderLineRow.class)
            .mappedBy((types, record) -> new OrderLineRow(
                record.get("orderCode").asString(),
                record.get("placedAt").asLocalDateTime(),
                record.get("sku").isNull()
                    ? null
                    : record.get("sku").asString(),
                record.get("productName").isNull()
                    ? null
                    : record.get("productName").asString(),
                record.get("quantity").isNull()
                    ? null
                    : record.get("quantity").asLong()
            ))
            .all()
            .stream()
            .toList();
    }
}
~~~

Sau đó gom các dòng theo mã đơn hàng:

~~~java
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class OrderGrouper {

    public record OrderItemView(
        String sku,
        String productName,
        Long quantity
    ) {
    }

    public record OrderView(
        String orderCode,
        LocalDateTime placedAt,
        List<OrderItemView> items
    ) {
    }

    private static class OrderAccumulator {
        final String orderCode;
        final LocalDateTime placedAt;
        final List<OrderItemView> items = new ArrayList<>();

        OrderAccumulator(String orderCode, LocalDateTime placedAt) {
            this.orderCode = orderCode;
            this.placedAt = placedAt;
        }
    }

    public List<OrderView> groupOrders(List<OrderLineRow> rows) {
        Map<String, OrderAccumulator> grouped = new LinkedHashMap<>();

        for (OrderLineRow row : rows) {
            OrderAccumulator order = grouped.computeIfAbsent(
                row.orderCode(),
                code -> new OrderAccumulator(code, row.placedAt())
            );

            // OPTIONAL MATCH tạo một dòng có sku = null nếu đơn chưa có sản phẩm.
            if (row.sku() != null) {
                order.items.add(new OrderItemView(
                    row.sku(),
                    row.productName(),
                    row.quantity()
                ));
            }
        }

        return grouped.values().stream()
            .map(order -> new OrderView(
                order.orderCode,
                order.placedAt,
                List.copyOf(order.items)
            ))
            .toList();
    }
}
~~~

**LinkedHashMap** giữ thứ tự đơn hàng theo lần đầu xuất hiện trong kết quả đã được sắp xếp. **computeIfAbsent** bảo đảm mỗi mã đơn chỉ tạo một accumulator. Dòng có **sku = null** vẫn giúp giữ đơn hàng không có sản phẩm, nhưng không tạo một item giả trong danh sách.

Khi gom dữ liệu phẳng, hãy chọn khóa nhóm ổn định và duy nhất. Nếu dùng tên hoặc thuộc tính có thể thay đổi, các đơn hàng khác nhau có thể bị gộp nhầm. Trong ví dụ, **orderCode** cần được bảo đảm duy nhất bằng quy tắc dữ liệu của ứng dụng và constraint tương ứng.

## 7. Chọn nơi gom dữ liệu

| Tiêu chí | Gom trong Cypher | Gom bằng mapping SDN | Gom trong Java service |
|---|---|---|---|
| Hình dạng kết quả | Một record chứa map/list lồng nhau hoặc root cùng collection | Root và collection node/relationship, kể cả list lồng nhau | Các dòng DTO hoặc map được nhóm thành view model |
| Công việc chính | **collect()**, **COLLECT {}**, map projection, **reduce()** | SDN ánh xạ node/relationship và làm phẳng collection | Dùng map/DTO và cấu trúc nhóm trong Java |
| Mục tiêu phù hợp | API đọc có cấu trúc cố định, cần giảm dữ liệu truyền | Cần hydrate entity graph nhiều tầng | Logic nghiệp vụ hoặc định dạng trả về phức tạp |
| Rủi ro chính | Tốn bộ nhớ database, Cypher khó bảo trì | Trả sai record hoặc thiếu node/relationship | Tốn bộ nhớ ứng dụng, dễ tạo N+1 nếu truy vấn từng nhóm |

Hãy ưu tiên gom ở database khi cấu trúc đầu ra rõ ràng, có thể diễn đạt tốt bằng Cypher và giảm được lượng dữ liệu truyền. Dùng SDN mapping khi mục tiêu là dựng entity graph theo các annotation miền. Gom ở service khi logic chuyển đổi phức tạp hoặc kết quả là view model chuyên biệt.

Không nên tải từng root rồi gọi thêm một truy vấn cho từng nhánh hoặc từng node con. Mẫu đó tạo ra lỗi **N+1 queries**: một truy vấn lấy danh sách root, sau đó thêm một truy vấn cho mỗi root hoặc mỗi relationship. Hãy gom dữ liệu trong một truy vấn hoặc tải theo lô có giới hạn.

## 8. Phân trang, giới hạn và hiệu năng

Gom dữ liệu nhiều tầng có thể tạo ra kết quả lớn ngay cả khi số root entity ít. Một khách hàng có vài nghìn đơn hàng, mỗi đơn có hàng trăm dòng sản phẩm, có thể tạo object graph rất lớn. Hãy kiểm soát lượng dữ liệu trước khi mở rộng các nhánh:

- Lọc root bằng label và property có index trước khi đi theo relationship.
- Giới hạn số root trước khi mở rộng các nhánh sâu; không đặt **LIMIT** ở cuối truy vấn sau khi đã nhân bản root thành nhiều dòng nếu mục tiêu là phân trang root.
- Giới hạn độ sâu và tránh variable-length path không có giới hạn trên trong graph lớn.
- Chỉ trả về các property và relationship mà màn hình hoặc use case thực sự cần.
- Dùng **DISTINCT** khi có thể phát sinh phần tử trùng, nhưng hãy giải quyết nguyên nhân tích Descartes thay vì chỉ dựa vào **DISTINCT**.
- Với kết quả rất lớn, chia thành các trang root hoặc batch và xử lý từng phần thay vì giữ toàn bộ graph trong bộ nhớ.
- Dùng **EXPLAIN** để xem kế hoạch và **PROFILE** để đo số dòng trung gian, DB hits và operator thực thi.

Khi phân trang, hãy xác định root trước rồi mới gom các nhánh của từng root. Ví dụ có thể lấy trang đơn hàng theo **orderCode** hoặc thời điểm, sau đó dùng **COLLECT {}** để lấy item cho từng đơn. Nếu áp dụng **LIMIT** sau một phép nối tạo nhiều dòng cho mỗi root, một đơn hàng có nhiều item có thể chiếm hết trang và làm mất các root khác.

## 9. Những lỗi thường gặp

**Trả về nhiều record cho cùng root entity.** SDN ánh xạ theo record. Hãy gom các node và relationship liên quan để mỗi root có một record khi trả về entity graph.

**Trả về Path với kỳ vọng SDN tự hydrate một root entity.** Khi cần gom nhiều nhánh vào một root, hãy trích xuất **nodes(path)** và **relationships(path)** rồi gom chúng. Trường hợp muốn trả về tất cả node trên các path như những kết quả riêng là một mục tiêu khác; hãy chọn hình dạng kết quả theo root mà repository cần ánh xạ.

**Gom các nhánh độc lập trong cùng một MATCH.** Số dòng trung gian có thể tăng theo tích số phần tử của từng nhánh. Hãy gom riêng bằng subquery hoặc pattern phù hợp.

**Không loại node và relationship trùng khi làm phẳng nhiều path.** Một node có thể xuất hiện trong nhiều path. Dùng **DISTINCT** hoặc **reduce()** với phép kiểm tra phần tử đã có trước khi trả về collection phẳng.

**Dùng DTO projection để nhận map tùy ý.** DTO projection của SDN hỗ trợ property đơn giản, entity đã biết và collection của chúng; map không nằm trong nhóm kiểu được hỗ trợ. Dùng **Neo4jClient.fetch()** hoặc mapping function riêng khi kết quả có map lồng nhau.

**Nhầm collection rỗng với null.** Hàm **collect()** bỏ qua giá trị null; **COLLECT {}** không tự loại null. Hãy lọc dữ liệu khi cần bảo đảm danh sách không chứa null.

**Gom bằng Java nhưng không có khóa nhóm ổn định.** Chọn ID hoặc business key duy nhất cho mỗi root, tránh gộp nhầm các thực thể.

**Truy vấn con theo từng root.** Tránh vòng lặp gọi repository cho từng node. Hãy dùng một truy vấn có collection hoặc lấy dữ liệu theo batch.

## 10. Tự kiểm tra

1. Vì sao truy vấn custom trả về entity graph nên có một record cho mỗi root entity?
2. **collect(r)** và **collect(p)** giúp SDN dựng relationship và node liên quan như thế nào?
3. Vì sao trả về nhiều Path không đồng nghĩa SDN có thể tự ánh xạ toàn bộ graph?
4. Khi nào nên dùng **reduce()** để gom các node và relationship từ nhiều path?
5. Vì sao gom các nhánh độc lập bằng nhiều **COLLECT {}** có thể tránh tích Descartes?
6. Khi nào nên dùng **Neo4jClient** thay cho DTO projection của repository?
7. Vì sao cần phân trang root trước khi mở rộng các relationship nhiều tầng?

**Bài tập thực hành:** Xây dựng truy vấn lấy khách hàng, các đơn hàng và sản phẩm trong từng đơn. Viết một phiên bản Cypher dùng map projection và **COLLECT {}** để trả về map lồng nhau, sau đó đọc bằng **Neo4jClient**. Viết phiên bản thứ hai trả về các dòng đơn hàng/sản phẩm phẳng và gom chúng bằng **LinkedHashMap** trong Java. So sánh số record, dữ liệu truyền qua mạng, độ phức tạp mapping và lượng bộ nhớ cần dùng. Cuối cùng, tạo một truy vấn nhiều nhánh có nguy cơ tích Descartes, dùng **PROFILE** để quan sát số dòng trung gian và sửa truy vấn bằng cách gom từng nhánh riêng.

## Tài liệu tham khảo

- [Spring Data Neo4j — Custom queries and multi-level graph mapping](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
- [Spring Data Neo4j — Neo4jClient and custom result mapping](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Data Neo4j — Multi-level projections](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Neo4j Cypher Manual — COLLECT subqueries](https://neo4j.com/docs/cypher-manual/current/subqueries/collect/)
- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/)
- [Neo4j Cypher Manual — Map projections](https://neo4j.com/docs/cypher-manual/5/expressions/map-expressions/)
