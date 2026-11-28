# delete, deleteById, deleteAllById và deleteAll

Spring Data Neo4j cung cấp các phương thức xóa qua `Neo4jRepository`, kế thừa từ Spring Data `CrudRepository`. Các phương thức như `delete(entity)`, `deleteById(id)`, `deleteAllById(ids)` và `deleteAll()` giúp xóa node theo entity, định danh hoặc toàn bộ tập node thuộc loại entity của repository.

Trong Neo4j, xóa node còn liên quan đến các relationship đang nối với node đó. Vì vậy, khi dùng API xóa của repository, cần hiểu phạm vi node bị xóa, relationship bị gỡ và các node ở đầu kia còn được giữ lại. Chọn đúng phương thức giúp tránh xóa nhầm dữ liệu dùng chung hoặc làm mất lịch sử nghiệp vụ.

## 1. Repository CRUD và entity cần xóa

Một repository Neo4j thường được khai báo bằng cách kế thừa `Neo4jRepository<T, ID>`:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface ProductRepository extends Neo4jRepository<Product, String> {
}
```

Entity `Product` có định danh `sku` do ứng dụng cấp:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Product")
public class Product {

    @Id
    private String sku;

    private String name;

    protected Product() {
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }
}
```

Kiểu `ID` trong `ProductRepository` phải khớp với kiểu của thuộc tính `@Id`. Khi dùng khóa nghiệp vụ như `sku`, các phương thức `findById`, `deleteById` và `existsById` nhận giá trị SKU. Nếu entity dùng ID do Neo4j sinh, kiểu ID và cách khai báo generated ID phải theo mapping của entity đó.

## 2. `delete(entity)`: xóa entity đã có

`delete(entity)` nhận một instance entity và yêu cầu repository xóa node tương ứng. Cách này phù hợp khi use case đã tải entity, kiểm tra điều kiện nghiệp vụ rồi mới quyết định xóa.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void deleteProduct(String sku) {
        Product product = products.findById(sku)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));

        products.delete(product);
    }
}
```

Luồng xử lý gồm tải entity theo ID, kiểm tra entity tồn tại và gọi `delete(product)`. Vì entity đã được nạp, service cũng có thể kiểm tra trạng thái, quyền sở hữu hoặc quy tắc không cho xóa trước khi thực hiện thao tác.

Không nên tạo một object rỗng chỉ có vài field rồi truyền vào `delete()` nếu không hiểu rõ ID mapping và yêu cầu của phiên bản SDN. Dùng entity đã nạp giúp luồng nghiệp vụ rõ ràng và giảm nhầm lẫn giữa dữ liệu mới với entity đã tồn tại.

## 3. `deleteById(id)`: xóa trực tiếp theo định danh

`deleteById(id)` xóa entity có định danh tương ứng mà không yêu cầu ứng dụng tải toàn bộ entity trước:

```java
@Transactional
public void deleteProductById(String sku) {
    products.deleteById(sku);
}
```

Phương thức này phù hợp khi ứng dụng đã có ID và không cần đọc dữ liệu entity để kiểm tra thêm quy tắc nghiệp vụ. Theo hợp đồng của `CrudRepository`, nếu ID không tồn tại trong persistence store thì thao tác xóa theo ID được bỏ qua một cách im lặng; phương thức không trả về boolean để báo có xóa được node hay không.

Nếu cần phản hồi rõ ràng khi không tìm thấy sản phẩm, hãy tải entity trước rồi quyết định:

```java
@Transactional
public void deleteProductOrFail(String sku) {
    Product product = products.findById(sku)
            .orElseThrow(() -> new IllegalArgumentException("Product not found"));

    products.delete(product);
}
```

Việc đọc trước có thêm một thao tác truy vấn. Trong hệ thống có cập nhật đồng thời, hãy thiết kế transaction và xử lý xung đột phù hợp; không coi `existsById()` hoặc `findById()` riêng lẻ là bảo đảm tuyệt đối rằng trạng thái sẽ không đổi trước lệnh xóa.

## 4. `deleteAllById(ids)`: xóa một tập entity theo ID

Khi cần xóa nhiều entity đã biết định danh, dùng `deleteAllById(Iterable<? extends ID> ids)`:

```java
import java.util.List;

@Transactional
public void deleteProducts(List<String> skus) {
    products.deleteAllById(skus);
}
```

Phương thức nhận một tập ID và xóa các entity tương ứng. ID không tồn tại được bỏ qua theo hợp đồng `CrudRepository`. Phương thức không trả về danh sách ID đã xóa hoặc số lượng node thực sự bị xóa.

Một số điểm cần cân nhắc:

- Xác thực tập ID đầu vào trước khi gọi repository, đặc biệt khi ID đến từ request bên ngoài.
- Nếu cần kiểm tra quyền xóa hoặc trạng thái từng entity, hãy tải và kiểm tra dữ liệu theo quy tắc nghiệp vụ trước khi xóa.
- Với danh sách rất lớn, cân nhắc chia thành các lô phù hợp và theo dõi thời gian transaction, bộ nhớ cùng tải database.
- Không giả định API luôn thực hiện một câu Cypher duy nhất hoặc có hiệu năng giống nhau ở mọi phiên bản SDN; hãy đo trên phiên bản và dữ liệu thực tế.

Nếu cần biết những ID nào thực sự tồn tại, có thể truy vấn trước hoặc thực hiện một lệnh tùy chỉnh trả về số lượng đã khớp. Đừng suy ra số node đã xóa chỉ từ số phần tử trong danh sách đầu vào.

## 5. `deleteAll(entities)` và `deleteAll()`: hai phạm vi khác nhau

`CrudRepository` có hai dạng `deleteAll` cần phân biệt:

```java
products.deleteAll(productsToRemove);
products.deleteAll();
```

- `deleteAll(Iterable<? extends Product> entities)` xóa các entity được truyền vào.
- `deleteAll()` không tham số xóa toàn bộ entity thuộc loại mà repository quản lý.

Với `ProductRepository`, `deleteAll()` có phạm vi các node được ánh xạ như `Product`; nó không có nghĩa là xóa mọi node và mọi dữ liệu trong toàn bộ Neo4j database. Tuy vậy, nếu nhiều thành phần ứng dụng cùng dùng label `Product`, thao tác này có thể ảnh hưởng đến tất cả node khớp với loại entity đó, kể cả node được tạo từ một luồng khác. Hãy xác nhận phạm vi dữ liệu trước khi gọi.

`deleteAll()` là thao tác có phạm vi rộng và không nhận điều kiện lọc. Không gọi nó trong endpoint nghiệp vụ thông thường nếu mục tiêu chỉ là xóa một nhóm sản phẩm. Khi cần xóa theo trạng thái hoặc thời gian tạo, hãy viết phương thức có điều kiện rõ ràng hoặc custom Cypher có tham số.

## 6. Node deletion và relationship cleanup

Neo4j không cho phép xóa node bằng `DELETE` khi node vẫn còn relationship. Cypher cung cấp `DETACH DELETE` để xóa node cùng tất cả relationship đi vào hoặc đi ra node đó.

Ví dụ một sản phẩm được nhiều đơn hàng tham chiếu:

```cypher
MATCH (p:Product {sku: $sku})
DETACH DELETE p;
```

Sau lệnh này:

- Node `Product` được xóa.
- Các relationship nối với sản phẩm, chẳng hạn `CONTAINS`, bị xóa.
- Các node ở đầu kia như `PurchaseOrder` vẫn tồn tại.
- Property trên các relationship đã bị xóa cũng không còn.

Các phương thức xóa entity của SDN xử lý việc gỡ các relationship gắn với node được xóa theo cơ chế persistence của framework. Điều đó không có nghĩa các node lân cận cũng bị xóa theo. Khi dùng custom Cypher, cần chủ động chọn `DELETE` hay `DETACH DELETE` theo mục tiêu.

Đặc biệt, nếu relationship mang dữ liệu lịch sử như số lượng và đơn giá của dòng hàng, xóa node `Product` có thể xóa luôn các relationship lịch sử đó. Hãy cân nhắc quy tắc lưu trữ, audit và vòng đời dữ liệu trước khi xóa một node dùng chung.

## 7. Xóa relationship nhưng giữ hai node

Không phải lúc nào cũng cần xóa node. Nếu mục tiêu chỉ là hủy quan hệ giữa hai thực thể, hãy xóa relationship trực tiếp:

```cypher
MATCH (u:User {userId: $userId})
      -[r:MEMBER_OF {membershipKey: $membershipKey}]->
      (g:Group)
DELETE r;
```

Lệnh này xóa đúng relationship `MEMBER_OF` đã khớp, còn node `User` và `Group` vẫn tồn tại. Property trên relationship cũng bị xóa cùng relationship.

Nếu relationship được ánh xạ bằng `@RelationshipProperties`, hãy cân nhắc cập nhật collection trên entity root qua SDN hoặc dùng custom Cypher có điều kiện cụ thể. Sau khi cập nhật trực tiếp bằng Cypher, không tiếp tục lưu một object graph cũ có thể chứa relationship vừa bị xóa mà chưa đồng bộ lại trạng thái.

## 8. Xóa có điều kiện bằng custom Cypher

Các phương thức CRUD chuẩn xóa theo entity hoặc ID. Nếu cần điều kiện nghiệp vụ như chỉ xóa sản phẩm đã ngừng kinh doanh và chưa được tham chiếu, có thể viết query riêng:

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends Neo4jRepository<Product, String> {

    @Query("""
        MATCH (p:Product {sku: $sku, status: 'DISCONTINUED'})
        WHERE NOT EXISTS {
            MATCH (:PurchaseOrder)-[:CONTAINS]->(p)
        }
        DETACH DELETE p
        RETURN count(p) AS deletedCount
        """)
    long deleteDiscontinuedIfUnused(@Param("sku") String sku);
}
```

Ví dụ chỉ xóa sản phẩm có trạng thái `DISCONTINUED` và không có relationship `CONTAINS` từ đơn hàng. `deletedCount` cho biết số node được khớp và xóa. Hãy điều chỉnh điều kiện theo mô hình thực tế: một sản phẩm có thể còn relationship khác như `SIMILAR_TO`, `SUPPLIED_BY` hoặc `STORED_AT`, và các liên kết đó cũng cần được xem xét trước khi xóa.

Custom delete query nên thể hiện rõ điều kiện match và trả về số lượng nếu use case cần xác nhận kết quả. Tránh ghép chuỗi đầu vào vào Cypher; sử dụng tham số như `$sku`.

## 9. Transaction và quy tắc nghiệp vụ khi xóa

Một lệnh xóa có thể ảnh hưởng đến nhiều relationship. Nếu một use case cần kiểm tra điều kiện, ghi audit và xóa dữ liệu trong cùng một đơn vị công việc, hãy đặt các thao tác trong service có `@Transactional`:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductDeletionService {

    private final ProductRepository products;
    private final ProductAuditRepository audits;

    public ProductDeletionService(ProductRepository products,
                                  ProductAuditRepository audits) {
        this.products = products;
        this.audits = audits;
    }

    @Transactional
    public void remove(String sku) {
        Product product = products.findById(sku)
                .orElseThrow(() -> new IllegalArgumentException("Product not found"));

        audits.recordDeletion(product.getSku(), product.getName());
        products.delete(product);
    }
}
```

Đây là ví dụ minh họa; `ProductAuditRepository` đại diện cho cơ chế audit của ứng dụng. Nếu audit được ghi vào cùng Neo4j database và cùng transaction manager, thay đổi audit và thao tác xóa có thể cùng commit hoặc rollback. Nếu audit nằm ở hệ thống khác, một transaction Neo4j không tự bảo đảm tính nguyên tử xuyên hệ thống; cần cơ chế sự kiện hoặc quy trình phối hợp phù hợp.

Transaction cũng không thay thế kiểm tra quyền và quy tắc domain. Hãy xác định ai được phép xóa, điều kiện nào ngăn xóa và dữ liệu liên quan cần được bảo toàn ra sao.

## 10. Xóa cứng hay xóa mềm?

Xóa cứng loại bỏ node hoặc relationship khỏi graph. Trong nhiều nghiệp vụ, cần giữ lịch sử hoặc khả năng khôi phục; khi đó có thể dùng xóa mềm bằng property trạng thái:

```cypher
MATCH (p:Product {sku: $sku})
SET p.status = 'ARCHIVED',
    p.archivedAt = datetime();
```

Xóa mềm giữ node và relationship, vì vậy các truy vấn đọc cần lọc trạng thái phù hợp. Nó hữu ích khi cần audit, khôi phục, giữ tham chiếu lịch sử hoặc chờ một quy trình dọn dữ liệu sau này. Tuy nhiên, xóa mềm không tự giải quyết việc ẩn dữ liệu; tất cả truy vấn nghiệp vụ cần áp dụng điều kiện trạng thái nhất quán.

Chọn chiến lược theo vòng đời dữ liệu:

| Nhu cầu | Hướng xử lý |
|---|---|
| Dữ liệu thử nghiệm hoặc dữ liệu không còn tham chiếu | Xóa cứng theo ID hoặc điều kiện rõ ràng |
| Cần giữ lịch sử giao dịch | Giữ node/relationship lịch sử hoặc snapshot dữ liệu cần thiết |
| Cần ẩn khỏi luồng nghiệp vụ nhưng vẫn khôi phục được | Xóa mềm bằng trạng thái và thời điểm lưu trữ |
| Cần loại bỏ dữ liệu theo chính sách lưu trữ | Quy trình purge có phạm vi, kiểm tra và audit |

## 11. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nhầm `deleteById` với xóa relationship | Node bị xóa cùng các relationship gắn với nó | Dùng Cypher `DELETE r` nếu chỉ muốn xóa một liên kết |
| Gọi `deleteAll()` khi chỉ muốn xóa một nhóm nhỏ | Toàn bộ node thuộc loại entity của repository có thể bị xóa | Dùng `deleteAllById` hoặc query có điều kiện |
| Cho rằng node ở đầu kia cũng bị xóa | Có thể thiết kế sai kỳ vọng về dữ liệu còn lại | Hiểu rằng node lân cận được giữ lại, relationship gắn với node bị xóa được gỡ |
| Xóa node dùng chung mà không kiểm tra tham chiếu | Mất các relationship và dữ liệu nghiệp vụ liên quan | Kiểm tra relationship và quy tắc domain trước khi xóa |
| Mong `deleteById` trả về kết quả thành công | Không biết ID có tồn tại hay không từ giá trị trả về | Tải entity trước hoặc dùng custom query trả về count |
| Dùng `DELETE` cho node còn relationship trong Cypher | Neo4j từ chối thao tác | Dùng `DETACH DELETE` nếu mục tiêu là xóa node cùng relationship |
| Cập nhật Cypher rồi lưu entity cũ | Object graph trong bộ nhớ có thể không còn đồng bộ | Tải lại entity hoặc kết thúc transaction/context phù hợp |
| Xóa cứng dữ liệu cần audit | Mất khả năng truy vết hoặc khôi phục | Cân nhắc archive, soft delete hoặc lưu audit trước khi purge |

## 12. Bài tập thực hành

Tạo một sản phẩm và hai đơn hàng tham chiếu đến nó:

```cypher
CREATE (p:Product {sku: 'PRD-900', name: 'Keyboard', status: 'ACTIVE'})
CREATE (o1:PurchaseOrder {orderId: 'ORD-900'})
CREATE (o2:PurchaseOrder {orderId: 'ORD-901'})
CREATE (o1)-[:CONTAINS {quantity: 2}]->(p)
CREATE (o2)-[:CONTAINS {quantity: 1}]->(p);
```

Thực hiện các yêu cầu:

1. Viết `ProductRepository` kế thừa `Neo4jRepository<Product, String>`.
2. Dùng `deleteById("PRD-900")` trong môi trường thử nghiệm và quan sát node sản phẩm cùng các relationship `CONTAINS` bị ảnh hưởng.
3. Tạo lại dữ liệu, sau đó dùng `deleteAllById(List.of("PRD-900", "UNKNOWN"))` và giải thích vì sao ID không tồn tại được bỏ qua.
4. Tạo thêm nhiều sản phẩm rồi gọi `deleteAll()` trong database thử nghiệm; xác nhận phạm vi chỉ là node `Product` được repository quản lý.
5. Dùng Cypher `DELETE r` để xóa một relationship `CONTAINS` nhưng giữ lại hai node đầu cuối.
6. Viết custom query chỉ xóa sản phẩm `DISCONTINUED` và không còn được đơn hàng tham chiếu.
7. Thử chuyển sản phẩm sang `ARCHIVED` thay vì xóa cứng và điều chỉnh truy vấn đọc để bỏ qua sản phẩm đã archive.

Sau bài tập, cần phân biệt được xóa một entity, xóa theo ID, xóa nhiều ID và xóa toàn bộ entity của repository; đồng thời giải thích tác động của node deletion đến các relationship và node lân cận.

## Kết luận

`delete(entity)` xóa entity đã nạp, `deleteById(id)` xóa theo định danh, `deleteAllById(ids)` xóa tập entity theo ID và `deleteAll()` xóa toàn bộ entity thuộc loại repository quản lý. Khi node bị xóa, các relationship gắn với node cũng được gỡ, còn các node lân cận vẫn tồn tại. Nếu chỉ cần hủy liên kết, hãy xóa relationship riêng bằng Cypher. Với dữ liệu dùng chung hoặc cần lưu lịch sử, kiểm tra tham chiếu và cân nhắc xóa mềm trước khi xóa cứng. Đặt các bước kiểm tra, audit và xóa trong transaction phù hợp để bảo vệ tính nhất quán của ứng dụng.
